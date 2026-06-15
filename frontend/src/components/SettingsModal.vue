<script setup lang="ts">
import { computed, ref } from "vue";

import * as api from "@/api/client";
import { ApiError } from "@/api/client";
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
        <p class="mb-3 text-xs text-fg-muted leading-relaxed">
          When enabled, each time you open <em>Review</em> fresh HSK words top
          up your learning pool until you've hit today's target. They're picked
          at random within the lowest level you haven't finished yet, so you
          progress sequentially.
        </p>
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
              Off by default — only enable if you want a steady drip of new
              vocabulary alongside the words you mark yourself.
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
        <p class="mb-3 text-xs text-fg-muted leading-relaxed">
          Already comfortable with some HSK? Bulk-mark every word up to a level
          as known. You can still change individual words later by clicking them
          in the reader.
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
    </div>
  </Modal>
</template>
