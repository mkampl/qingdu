<script setup lang="ts">
import { computed, ref } from "vue";

import * as api from "@/api/client";
import { ApiError, getApiBase, getDefaultApiBase, setApiBase } from "@/api/client";
import { useAppModalsStore } from "@/stores/app-modals";
import { useAuthStore } from "@/stores/auth";
import {
  useSettingsStore,
  type ColorMode,
  type HskVersion,
  type PinyinMode,
} from "@/stores/settings";
import { useToastStore } from "@/stores/toast";
import { useUserWordsStore } from "@/stores/userWords";

import Modal from "@/components/ui/Modal.vue";

const modals = useAppModalsStore();
const settings = useSettingsStore();
const auth = useAuthStore();
const toasts = useToastStore();
const userWords = useUserWordsStore();

// Use computed setters so the radios/select bind directly to the store.
const pinyinMode = computed<PinyinMode>({
  get: () => settings.pinyinMode,
  set: (v) => (settings.pinyinMode = v),
});
const hskVersion = computed<HskVersion>({
  get: () => settings.hskVersion,
  set: (v) => (settings.hskVersion = v),
});
const showLegend = computed<boolean>({
  get: () => settings.showLegend,
  set: (v) => (settings.showLegend = v),
});
const theme = computed({
  get: () => settings.theme,
  set: (v: "light" | "dark") => (settings.theme = v),
});
const colorMode = computed<ColorMode>({
  get: () => settings.colorMode,
  set: (v) => (settings.colorMode = v),
});
const reminderEnabled = computed<boolean>({
  get: () => settings.reminderEnabled,
  set: (v) => (settings.reminderEnabled = v),
});
const reminderTime = computed<string>({
  get: () => settings.reminderTime,
  set: (v) => (settings.reminderTime = v),
});
const hapticsEnabled = computed<boolean>({
  get: () => settings.hapticsEnabled,
  set: (v) => (settings.hapticsEnabled = v),
});
const autoLearnOnClick = computed<boolean>({
  get: () => settings.autoLearnOnClick,
  set: (v) => (settings.autoLearnOnClick = v),
});

const colorOptions: { value: ColorMode; label: string; hint: string }[] = [
  {
    value: "progress",
    label: "By progress",
    hint: "Blue = new to you · accent = learning · plain = known/ignored",
  },
  { value: "hsk", label: "By HSK", hint: "Color every word by its HSK level" },
  { value: "off", label: "Off", hint: "Plain text, no highlights" },
];

const pinyinOptions: { value: PinyinMode; label: string; hint: string }[] = [
  {
    value: "auto",
    label: "Auto",
    hint: "Show pinyin only for words above your estimated reading level",
  },
  { value: "on", label: "Always", hint: "Show pinyin on every word" },
  { value: "off", label: "Never", hint: "Hide pinyin everywhere" },
];

const hskOptions: { value: HskVersion; label: string; hint: string }[] = [
  { value: "new", label: "New HSK", hint: "2021 standard, 9 levels" },
  { value: "old", label: "Old HSK", hint: "Pre-2021, 6 levels" },
];

// --- Onboarding shortcut: bulk-mark HSK levels as known ---
//
// Two-step button: click once to surface a confirm row showing the
// expected count (calls /api/words/import-hsk's "dry run" semantics is
// overkill here; we estimate from the in-memory dict instead — see
// roughCount below).
const importLevel = ref<number>(4);
const importing = ref(false);
const pendingConfirm = ref(false);
const lastResult = ref<{
  inserted: number;
  skipped: number;
  total_eligible: number;
} | null>(null);

const importMaxLevel = computed(() => (settings.hskVersion === "new" ? 9 : 6));

// HSK 1 ≈ 150 words, HSK 2 ≈ 300, ..., HSK 6 ≈ 5k, HSK 9 ≈ 11k. Used just
// for the "about N words" hint; the real count comes back in the API
// response after the import lands.
function roughCount(level: number, version: "new" | "old"): number {
  if (version === "new") {
    return [0, 500, 770, 1000, 1100, 1500, 1500, 1600, 1700, 1800][level] ?? 0;
  }
  return [0, 150, 300, 600, 1200, 2500, 5000][level] ?? 0;
}

const roughTotal = computed(() => {
  let n = 0;
  for (let i = 1; i <= importLevel.value; i++) {
    n += roughCount(i, settings.hskVersion);
  }
  return n;
});

const csvUrl = computed(() => api.wordsCsvUrl());
const ankiUrl = computed(() => api.wordsAnkiUrl());

// --- Phase #96: daily auto-enrol target ---
//
// Bound from auth.user so the UI always reflects the server's truth; on
// change, optimistic-update the local user then call the PATCH. 0 means
// auto-enrol is disabled; the toggle below flips between 0 and the user's
// chosen target (default 5 the first time they enable it).
const dailyNewWords = computed<number>({
  get: () => auth.user?.daily_new_words ?? 0,
  set: (v) => {
    void auth.updateSettings({ daily_new_words: clampDaily(v) }).catch(() => {
      toasts.error("Couldn't save daily target.");
    });
  },
});

const dailyEnabled = computed<boolean>({
  get: () => dailyNewWords.value > 0,
  set: (v) => {
    // Toggling on restores to 5 (the recommended default); toggling off
    // zeroes the target without losing the user's chosen number while
    // they're in this session (they can flip back on without retyping).
    dailyNewWords.value = v ? 5 : 0;
  },
});

// --- Phase #96 follow-up: Simplified vs Traditional display ---
const displayScript = computed<"auto" | "simp" | "trad">({
  get: () => auth.user?.display_script ?? "auto",
  set: (v) => {
    void auth.updateSettings({ display_script: v }).catch(() => {
      toasts.error("Couldn't save script preference.");
    });
  },
});

// --- Phase #117 — FSRS retention target ---
// Three bands map to FSRS desired_retention values that the SRS library
// actually accepts (the meaningful tuning range is 0.85-0.97):
//   relaxed → 0.90 — the FSRS library default. Fewer reviews, more
//             forgetting; review 3 of a "Good" streak lands at ~10d.
//   normal  → 0.95 — qingdu's default since Phase #117. Lines up with
//             classic Anki SM-2 intuition; review 3 ≈ 4d.
//   strict  → 0.97 — keeps almost everything fresh; review 3 ≈ 2d.
type ReviewBand = "relaxed" | "normal" | "strict";
const BAND_TO_RETENTION: Record<ReviewBand, number> = {
  relaxed: 0.9,
  normal: 0.95,
  strict: 0.97,
};
function bandFor(r: number | undefined): ReviewBand {
  if (r === undefined) return "normal";
  if (r <= 0.92) return "relaxed";
  if (r >= 0.96) return "strict";
  return "normal";
}
const reviewBand = computed<ReviewBand>({
  get: () => bandFor(auth.user?.review_retention),
  set: (v) => {
    void auth.updateSettings({ review_retention: BAND_TO_RETENTION[v] }).catch(() => {
      toasts.error("Couldn't save review challenge.");
    });
  },
});

// --- Phase #119 — Review window ---
type ReviewWindow = "now" | "today" | "tomorrow";
const reviewWindow = computed<ReviewWindow>({
  get: () => (auth.user?.review_window as ReviewWindow) ?? "today",
  set: (v) => {
    void auth.updateSettings({ review_window: v }).catch(() => {
      toasts.error("Couldn't save review window.");
    });
  },
});
const reviewWindowOptions: { value: ReviewWindow; label: string; hint: string }[] = [
  {
    value: "now",
    label: "Just due",
    hint: "Only cards whose FSRS due_at has already passed. Strict — wait for each card to flip due.",
  },
  {
    value: "today",
    label: "Today",
    hint: "Default — pull every card due before midnight tonight so a once-a-day session covers the whole day.",
  },
  {
    value: "tomorrow",
    label: "Today + tomorrow",
    hint: "Pre-pull tomorrow's batch too. Useful if you know you won't be around to review tomorrow.",
  },
];

const reviewBandOptions: { value: ReviewBand; label: string; hint: string }[] = [
  {
    value: "relaxed",
    label: "Relaxed",
    hint: "Fewer reviews, more forgetting accepted. After 3 Good clicks: ~10 days.",
  },
  {
    value: "normal",
    label: "Normal",
    hint: "Anki SM-2-like rhythm. After 3 Good clicks: ~4 days.",
  },
  {
    value: "strict",
    label: "Strict",
    hint: "Almost nothing slips through. After 3 Good clicks: ~2 days.",
  },
];

const scriptOptions: {
  value: "auto" | "simp" | "trad";
  label: string;
  hint: string;
}[] = [
  {
    value: "auto",
    label: "Auto",
    hint: "Show Chinese exactly as it appears in the source — no conversion.",
  },
  {
    value: "simp",
    label: "Simplified (简体)",
    hint: "Convert every Chinese surface to Simplified, no matter what was stored.",
  },
  {
    value: "trad",
    label: "Traditional (繁體)",
    hint: "Convert every Chinese surface to Traditional.",
  },
];

function clampDaily(v: number): number {
  if (!Number.isFinite(v)) return 0;
  return Math.max(0, Math.min(30, Math.round(v)));
}

async function runImport() {
  if (!auth.isAuthed) {
    toasts.info("Sign in to import HSK words.");
    return;
  }
  importing.value = true;
  try {
    const r = await api.importHskKnown(importLevel.value, settings.hskVersion);
    lastResult.value = r;
    pendingConfirm.value = false;
    toasts.success(
      `Marked ${r.inserted.toLocaleString()} new word${r.inserted === 1 ? "" : "s"} as known.`,
    );
    // Refresh the store so the header counter ticks immediately.
    userWords.hydrate(true);
  } catch (e) {
    toasts.error(
      e instanceof ApiError ? e.message : "Couldn't import HSK words.",
    );
  } finally {
    importing.value = false;
  }
}

// --- Phase 1.6: server-switcher --------------------------------------------
//
// Runtime override for the API base URL. Set to the empty string here when
// the user is on the default; the input doubles as the override field. The
// "Test" button hits /api/health on whatever URL is in the field so a
// typo'd server doesn't strand the user mid-config.

const apiBaseDefault = getDefaultApiBase();
const apiBaseInput = ref(getApiBase());
const apiBaseTesting = ref(false);
const apiBaseStatus = ref<
  | { kind: "idle" }
  | { kind: "ok"; vocabCount: number }
  | { kind: "error"; message: string }
>({ kind: "idle" });

const apiBaseChanged = computed(
  () => apiBaseInput.value.replace(/\/$/, "") !== getApiBase(),
);
const apiBaseIsDefault = computed(
  () => apiBaseInput.value.replace(/\/$/, "") === apiBaseDefault,
);

async function testApiBase() {
  const target = apiBaseInput.value.replace(/\/$/, "");
  if (!target) {
    apiBaseStatus.value = {
      kind: "error",
      message: "Enter a URL like https://qingdu.example.com",
    };
    return;
  }
  apiBaseTesting.value = true;
  apiBaseStatus.value = { kind: "idle" };
  try {
    const r = await fetch(`${target}/api/health`, { method: "GET" });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const body = (await r.json()) as { vocab_count?: number };
    apiBaseStatus.value = {
      kind: "ok",
      vocabCount: body.vocab_count ?? 0,
    };
  } catch (e) {
    apiBaseStatus.value = {
      kind: "error",
      message:
        e instanceof Error
          ? `Couldn't reach that URL — ${e.message}`
          : "Couldn't reach that URL",
    };
  } finally {
    apiBaseTesting.value = false;
  }
}

function saveApiBase() {
  const target = apiBaseInput.value.replace(/\/$/, "");
  // Empty input is interpreted as "reset to default" so the user can
  // wipe the override by clearing the field.
  setApiBase(target === apiBaseDefault || target === "" ? null : target);
  toasts.success(
    "Server updated. You may need to sign in again on the new server.",
  );
  modals.closeAll();
  // Force a clean reload so every store hydrates against the new URL.
  setTimeout(() => window.location.reload(), 400);
}

function resetApiBase() {
  apiBaseInput.value = apiBaseDefault;
  apiBaseStatus.value = { kind: "idle" };
}
</script>

<template>
  <Modal
    :open="modals.settingsOpen"
    size="md"
    close-on-backdrop
    @close="modals.closeAll()"
  >
    <template #header>
      <div class="flex items-baseline gap-3">
        <h2 class="font-display text-xl font-medium tracking-tight text-fg">
          Settings
        </h2>
        <span
          class="font-mono text-[10px] uppercase tracking-[0.18em] text-fg-subtle"
        >
          Saved on this device
        </span>
      </div>
    </template>

    <div class="space-y-7">
      <!-- Word color mode -->
      <fieldset>
        <legend
          class="mb-3 font-mono text-[11px] uppercase tracking-[0.2em] text-fg-subtle"
        >
          Word coloring
        </legend>
        <div class="space-y-2">
          <label
            v-for="opt in colorOptions"
            :key="opt.value"
            class="flex cursor-pointer items-start gap-3 rounded-md border border-border-subtle px-3 py-2 transition-colors hover:bg-bg-sunken"
            :class="{
              'border-accent bg-bg-sunken': colorMode === opt.value,
            }"
          >
            <input
              v-model="colorMode"
              type="radio"
              :value="opt.value"
              class="mt-1 accent-accent"
            />
            <span class="flex-1">
              <span class="block font-display text-base text-fg">
                {{ opt.label }}
              </span>
              <span class="block text-xs text-fg-muted">{{ opt.hint }}</span>
            </span>
          </label>
        </div>
      </fieldset>

      <!-- Pinyin -->
      <fieldset>
        <legend
          class="mb-3 font-mono text-[11px] uppercase tracking-[0.2em] text-fg-subtle"
        >
          Pinyin display
        </legend>
        <div class="space-y-2">
          <label
            v-for="opt in pinyinOptions"
            :key="opt.value"
            class="flex cursor-pointer items-start gap-3 rounded-md border border-border-subtle px-3 py-2 transition-colors hover:bg-bg-sunken"
            :class="{
              'border-accent bg-bg-sunken': pinyinMode === opt.value,
            }"
          >
            <input
              v-model="pinyinMode"
              type="radio"
              :value="opt.value"
              class="mt-1 accent-accent"
            />
            <span class="flex-1">
              <span class="block font-display text-base text-fg">
                {{ opt.label }}
              </span>
              <span class="block text-xs text-fg-muted">{{ opt.hint }}</span>
            </span>
          </label>
        </div>
      </fieldset>

      <!-- HSK version -->
      <fieldset>
        <legend
          class="mb-3 font-mono text-[11px] uppercase tracking-[0.2em] text-fg-subtle"
        >
          HSK version
        </legend>
        <div class="grid grid-cols-2 gap-2">
          <label
            v-for="opt in hskOptions"
            :key="opt.value"
            class="flex cursor-pointer items-start gap-3 rounded-md border border-border-subtle px-3 py-2 transition-colors hover:bg-bg-sunken"
            :class="{
              'border-accent bg-bg-sunken': hskVersion === opt.value,
            }"
          >
            <input
              v-model="hskVersion"
              type="radio"
              :value="opt.value"
              class="mt-1 accent-accent"
            />
            <span class="flex-1">
              <span class="block font-display text-base text-fg">
                {{ opt.label }}
              </span>
              <span class="block text-xs text-fg-muted">{{ opt.hint }}</span>
            </span>
          </label>
        </div>
      </fieldset>

      <!-- Phase #119 — Review window -->
      <fieldset v-if="auth.isAuthed">
        <legend
          class="mb-3 font-mono text-[11px] uppercase tracking-[0.2em] text-fg-subtle"
        >
          Review window
        </legend>
        <div class="space-y-2">
          <label
            v-for="opt in reviewWindowOptions"
            :key="opt.value"
            class="flex cursor-pointer items-start gap-3 rounded-md border border-border-subtle px-3 py-2 transition-colors hover:bg-bg-sunken"
            :class="{
              'border-accent bg-bg-sunken': reviewWindow === opt.value,
            }"
          >
            <input
              v-model="reviewWindow"
              type="radio"
              :value="opt.value"
              class="mt-1 accent-accent"
            />
            <span class="flex-1">
              <span class="block font-display text-base text-fg">
                {{ opt.label }}
              </span>
              <span class="block text-xs text-fg-muted">{{ opt.hint }}</span>
            </span>
          </label>
        </div>
      </fieldset>

      <!-- Phase #117 — FSRS retention -->
      <fieldset v-if="auth.isAuthed">
        <legend
          class="mb-3 font-mono text-[11px] uppercase tracking-[0.2em] text-fg-subtle"
        >
          Review challenge
        </legend>
        <div class="space-y-2">
          <label
            v-for="opt in reviewBandOptions"
            :key="opt.value"
            class="flex cursor-pointer items-start gap-3 rounded-md border border-border-subtle px-3 py-2 transition-colors hover:bg-bg-sunken"
            :class="{
              'border-accent bg-bg-sunken': reviewBand === opt.value,
            }"
          >
            <input
              v-model="reviewBand"
              type="radio"
              :value="opt.value"
              class="mt-1 accent-accent"
            />
            <span class="flex-1">
              <span class="block font-display text-base text-fg">
                {{ opt.label }}
              </span>
              <span class="block text-xs text-fg-muted">{{ opt.hint }}</span>
            </span>
          </label>
        </div>
      </fieldset>

      <!-- Behaviour on word tap -->
      <label
        class="flex cursor-pointer items-start gap-3 rounded-md border border-border-subtle px-3 py-2 transition-colors hover:bg-bg-sunken"
        :class="{ 'border-accent bg-bg-sunken': autoLearnOnClick }"
      >
        <input
          v-model="autoLearnOnClick"
          type="checkbox"
          class="mt-1 accent-accent"
        />
        <span class="flex-1">
          <span class="block font-display text-base text-fg">
            Auto-add tapped words to learning
          </span>
          <span class="block text-xs text-fg-muted">
            Off by default — a tap just shows the gloss. Use the
            <span class="font-medium text-fg">Learning</span> button in the
            popover to enrol a word into the SRS queue, or turn this on if
            you'd rather every tap promote 'new' words automatically.
          </span>
        </span>
      </label>

      <!-- Legend -->
      <label
        class="flex cursor-pointer items-start gap-3 rounded-md border border-border-subtle px-3 py-2 transition-colors hover:bg-bg-sunken"
        :class="{ 'border-accent bg-bg-sunken': showLegend }"
      >
        <input
          v-model="showLegend"
          type="checkbox"
          class="mt-1 accent-accent"
        />
        <span class="flex-1">
          <span class="block font-display text-base text-fg">
            Show HSK colour legend
          </span>
          <span class="block text-xs text-fg-muted">
            Adds a small key under the composition stats explaining each level's
            wash colour.
          </span>
        </span>
      </label>

      <!-- Theme — same toggle as the header crescent, included here for
           discoverability. -->
      <fieldset>
        <legend
          class="mb-3 font-mono text-[11px] uppercase tracking-[0.2em] text-fg-subtle"
        >
          Appearance
        </legend>
        <div class="grid grid-cols-2 gap-2">
          <label
            class="flex cursor-pointer items-center gap-2 rounded-md border border-border-subtle px-3 py-2 transition-colors hover:bg-bg-sunken"
            :class="{ 'border-accent bg-bg-sunken': theme === 'light' }"
          >
            <input
              v-model="theme"
              type="radio"
              value="light"
              class="accent-accent"
            />
            <span class="font-display text-base text-fg">Light</span>
          </label>
          <label
            class="flex cursor-pointer items-center gap-2 rounded-md border border-border-subtle px-3 py-2 transition-colors hover:bg-bg-sunken"
            :class="{ 'border-accent bg-bg-sunken': theme === 'dark' }"
          >
            <input
              v-model="theme"
              type="radio"
              value="dark"
              class="accent-accent"
            />
            <span class="font-display text-base text-fg">Dark</span>
          </label>
        </div>
      </fieldset>

      <!-- Phase #116 — native-only daily reminder. Shown on all platforms;
           on web the toggle saves the preference but never schedules anything
           (the native plugin is a no-op outside the Capacitor wrapper). -->
      <fieldset>
        <legend
          class="mb-3 font-mono text-[11px] uppercase tracking-[0.2em] text-fg-subtle"
        >
          Daily reminder
        </legend>
        <label class="flex cursor-pointer items-center gap-3 rounded-md border border-border-subtle px-3 py-2 transition-colors hover:bg-bg-sunken">
          <input
            v-model="reminderEnabled"
            type="checkbox"
            class="mt-0 accent-accent"
          />
          <span class="flex-1">
            <span class="block font-display text-base text-fg">
              Remind me daily
            </span>
            <span class="block text-xs text-fg-muted">
              A local notification at a fixed time. Body shows the
              due-count from the last time the app was open — close enough
              to motivate a return visit without needing a server push.
            </span>
          </span>
        </label>
        <label
          v-if="reminderEnabled"
          class="mt-2 flex items-center gap-3 px-3"
        >
          <span class="font-display text-sm text-fg-muted">Time</span>
          <input
            v-model="reminderTime"
            type="time"
            class="rounded-md border border-border-subtle bg-bg px-2 py-1 font-mono text-sm tabular-nums text-fg focus:border-accent focus:outline-none"
          />
        </label>
      </fieldset>

      <fieldset>
        <legend
          class="mb-3 font-mono text-[11px] uppercase tracking-[0.2em] text-fg-subtle"
        >
          Feedback
        </legend>
        <label class="flex cursor-pointer items-center gap-3 rounded-md border border-border-subtle px-3 py-2 transition-colors hover:bg-bg-sunken">
          <input
            v-model="hapticsEnabled"
            type="checkbox"
            class="mt-0 accent-accent"
          />
          <span class="flex-1">
            <span class="block font-display text-base text-fg">
              Haptic taps
            </span>
            <span class="block text-xs text-fg-muted">
              Subtle vibration on word-tap and review grade. Android only;
              ignored on web.
            </span>
          </span>
        </label>
      </fieldset>

      <!-- Phase #96 follow-up — global trad/simp toggle. Auth-gated since
           it lives on the user row server-side; the conversion is applied
           at every endpoint that returns Chinese. -->
      <fieldset v-if="auth.isAuthed">
        <legend
          class="mb-3 font-mono text-[11px] uppercase tracking-[0.2em] text-fg-subtle"
        >
          Script
        </legend>
        <div class="space-y-2">
          <label
            v-for="opt in scriptOptions"
            :key="opt.value"
            class="flex cursor-pointer items-start gap-3 rounded-md border border-border-subtle px-3 py-2 transition-colors hover:bg-bg-sunken"
            :class="{
              'border-accent bg-bg-sunken': displayScript === opt.value,
            }"
          >
            <input
              v-model="displayScript"
              type="radio"
              :value="opt.value"
              class="mt-1 accent-accent"
            />
            <span class="flex-1">
              <span class="block font-display text-base text-fg">
                {{ opt.label }}
              </span>
              <span class="block text-xs text-fg-muted">{{ opt.hint }}</span>
            </span>
          </label>
        </div>
      </fieldset>

      <!-- Phase #96 — daily systematic-learning target. Auth-gated because
           the value lives on the user row server-side. Off by default;
           the checkbox flips the target between 0 and 5 (default), with a
           numeric input revealed when on. -->
      <fieldset v-if="auth.isAuthed">
        <legend
          class="mb-3 font-mono text-[11px] uppercase tracking-[0.2em] text-fg-subtle"
        >
          Daily learning
        </legend>
        <label
          class="flex cursor-pointer items-start gap-3 rounded-md border border-border-subtle px-3 py-2 transition-colors hover:bg-bg-sunken"
        >
          <input
            v-model="dailyEnabled"
            type="checkbox"
            class="mt-1 accent-accent"
          />
          <span class="flex-1">
            <span class="block font-display text-base text-fg">
              Auto-enrol new HSK words
            </span>
            <span class="block text-xs text-fg-muted">
              Adds the next N HSK words to your queue daily.
            </span>
          </span>
        </label>
        <label v-if="dailyEnabled" class="mt-3 flex items-center gap-3 pl-6">
          <span
            class="font-mono text-[10px] uppercase tracking-wider text-fg-subtle"
          >
            New words / day
          </span>
          <input
            v-model.number="dailyNewWords"
            type="number"
            min="1"
            max="30"
            class="w-20 rounded-md border border-border bg-bg-elevated px-3 py-1.5 text-sm text-fg focus:border-accent focus:outline-none"
          />
          <span class="font-mono text-[10px] text-fg-subtle">1–30</span>
        </label>
      </fieldset>

      <!-- Onboarding shortcuts — auth-gated. Single batch mark-as-known
           pass to skip the cold-start grind for intermediate learners. -->
      <fieldset v-if="auth.isAuthed">
        <legend
          class="mb-3 font-mono text-[11px] uppercase tracking-[0.2em] text-fg-subtle"
        >
          Onboarding shortcuts
        </legend>
        <p class="mb-3 text-xs text-fg-muted">
          Bulk-mark every word up to a level as known.
        </p>
        <div class="flex flex-wrap items-end gap-3">
          <label class="flex flex-col gap-1">
            <span
              class="font-mono text-[10px] uppercase tracking-wider text-fg-subtle"
            >
              Up to HSK
            </span>
            <select
              v-model.number="importLevel"
              :disabled="importing"
              class="rounded-md border border-border bg-bg-elevated px-2 py-1.5 text-sm text-fg focus:border-accent focus:outline-none"
            >
              <option v-for="n in importMaxLevel" :key="n" :value="n">
                HSK {{ n }}
              </option>
            </select>
          </label>
          <div class="flex flex-col gap-1">
            <span
              class="font-mono text-[10px] uppercase tracking-wider text-fg-subtle"
            >
              About
            </span>
            <span class="font-display text-base text-fg tabular-nums">
              ~{{ roughTotal.toLocaleString() }} words
            </span>
          </div>
          <div class="ml-auto flex items-center gap-2">
            <template v-if="!pendingConfirm">
              <button
                type="button"
                class="rounded-md bg-accent px-3 py-1.5 text-xs font-medium text-accent-fg transition-opacity hover:opacity-90 disabled:opacity-50"
                :disabled="importing"
                @click="pendingConfirm = true"
              >
                Mark as known
              </button>
            </template>
            <template v-else>
              <button
                type="button"
                class="font-mono text-[10px] uppercase tracking-wider text-fg-subtle transition-colors hover:text-fg"
                :disabled="importing"
                @click="pendingConfirm = false"
              >
                Cancel
              </button>
              <button
                type="button"
                class="rounded-md bg-accent px-3 py-1.5 text-xs font-medium text-accent-fg transition-opacity hover:opacity-90 disabled:opacity-50"
                :disabled="importing"
                @click="runImport"
              >
                <span v-if="importing" class="inline-flex items-center gap-1.5">
                  <span
                    class="inline-block size-3 animate-spin rounded-full border-2 border-current border-t-transparent"
                  />
                  Marking…
                </span>
                <span v-else>Confirm</span>
              </button>
            </template>
          </div>
        </div>
        <p
          v-if="lastResult"
          class="mt-3 font-mono text-[10px] uppercase tracking-wider text-fg-subtle"
        >
          {{ lastResult.inserted.toLocaleString() }} added ·
          {{ lastResult.skipped.toLocaleString() }} already tracked ·
          {{ lastResult.total_eligible.toLocaleString() }} eligible
        </p>
      </fieldset>

      <!-- Phase G4 — data export. Two anchors download via the
           require_auth_flexible token-in-query pattern so the browser
           handles the file download natively. -->
      <fieldset v-if="auth.isAuthed">
        <legend
          class="mb-3 font-mono text-[11px] uppercase tracking-[0.2em] text-fg-subtle"
        >
          Export
        </legend>
        <p class="mb-3 text-xs text-fg-muted leading-relaxed">
          Take your data with you. CSV is a flat dump of every word state + FSRS
          scheduling fields; the Anki deck includes everything you're learning
          or already know with HSK level annotations.
        </p>
        <div class="flex flex-wrap gap-2">
          <a
            :href="csvUrl"
            class="inline-flex items-center gap-1.5 rounded-md border border-border bg-bg-elevated px-3 py-1.5 text-xs font-medium text-fg-muted transition-colors hover:bg-bg-sunken hover:text-fg"
            download
          >
            <svg
              width="11"
              height="11"
              viewBox="0 0 11 11"
              fill="none"
              aria-hidden="true"
            >
              <path
                d="M5.5 1.5v6M3 5l2.5 2.5L8 5M2 9.5h7"
                stroke="currentColor"
                stroke-width="1.4"
                stroke-linecap="round"
                stroke-linejoin="round"
              />
            </svg>
            words.csv
          </a>
          <a
            :href="ankiUrl"
            class="inline-flex items-center gap-1.5 rounded-md border border-border bg-bg-elevated px-3 py-1.5 text-xs font-medium text-fg-muted transition-colors hover:bg-bg-sunken hover:text-fg"
            download
          >
            <svg
              width="11"
              height="11"
              viewBox="0 0 11 11"
              fill="none"
              aria-hidden="true"
            >
              <path
                d="M5.5 1.5v6M3 5l2.5 2.5L8 5M2 9.5h7"
                stroke="currentColor"
                stroke-width="1.4"
                stroke-linecap="round"
                stroke-linejoin="round"
              />
            </svg>
            words.apkg
          </a>
        </div>
      </fieldset>

      <!-- Phase 1.6 — server-switcher for self-hosters. The default URL
           the maintainer ships is just a demo host; F-Droid / Capacitor
           users can repoint at their own backend without rebuilding.
           Hidden on web builds where the SPA is same-origin anyway (no
           cross-origin call would succeed without CORS on a custom host
           and the user already knows what server they hit). -->
      <fieldset v-if="apiBaseDefault !== ''">
        <legend
          class="mb-3 font-mono text-[11px] uppercase tracking-[0.2em] text-fg-subtle"
        >
          Server
        </legend>
        <p class="mb-3 text-xs text-fg-muted leading-relaxed">
          By default this app talks to
          <code class="rounded bg-bg-sunken px-1 py-0.5 font-mono text-[11px] text-fg">{{ apiBaseDefault }}</code> —
          a public demo server. Point it at your own Qingdu instance to
          keep your data on infrastructure you control. Changing server
          signs you out; the new server has its own accounts.
        </p>
        <label class="block">
          <span class="mb-1 block font-mono text-[10px] uppercase tracking-wider text-fg-subtle">
            API URL
          </span>
          <input
            v-model="apiBaseInput"
            type="url"
            inputmode="url"
            autocomplete="off"
            spellcheck="false"
            placeholder="https://qingdu.example.com"
            class="w-full rounded-md border border-border-subtle bg-bg px-3 py-2 font-mono text-sm text-fg focus:border-accent focus:outline-none"
          />
        </label>
        <div class="mt-3 flex flex-wrap items-center gap-2">
          <button
            type="button"
            class="inline-flex items-center gap-1.5 rounded-md border border-border bg-bg-elevated px-3 py-1.5 text-xs font-medium text-fg-muted transition-colors hover:bg-bg-sunken hover:text-fg disabled:cursor-not-allowed disabled:opacity-50"
            :disabled="apiBaseTesting || !apiBaseInput"
            @click="testApiBase"
          >
            <span v-if="apiBaseTesting" class="inline-flex items-center gap-1.5">
              <span
                class="inline-block size-3 animate-spin rounded-full border-2 border-current border-t-transparent"
              />
              Testing…
            </span>
            <span v-else>Test</span>
          </button>
          <button
            type="button"
            class="inline-flex items-center rounded-md bg-accent px-3 py-1.5 text-xs font-medium text-accent-fg transition-colors hover:bg-accent/90 disabled:cursor-not-allowed disabled:opacity-50"
            :disabled="!apiBaseChanged"
            @click="saveApiBase"
          >
            Save &amp; reload
          </button>
          <button
            v-if="!apiBaseIsDefault"
            type="button"
            class="text-xs text-fg-muted underline-offset-2 hover:text-fg hover:underline"
            @click="resetApiBase"
          >
            Use default
          </button>
        </div>
        <p
          v-if="apiBaseStatus.kind === 'ok'"
          class="mt-3 text-xs text-emerald-700 dark:text-emerald-300"
        >
          ✓ Connected. Vocab loaded ({{ apiBaseStatus.vocabCount.toLocaleString() }} entries).
        </p>
        <p
          v-else-if="apiBaseStatus.kind === 'error'"
          class="mt-3 text-xs text-red-700 dark:text-red-300"
        >
          {{ apiBaseStatus.message }}
        </p>
      </fieldset>
    </div>
  </Modal>
</template>
