<script setup lang="ts">
import { computed, ref, watch } from "vue";

import * as api from "@/api/client";
import { ApiError, getApiBase, getDefaultApiBase, setApiBase, setToken } from "@/api/client";
import type { ReviewFocus } from "@/api/client";
import { useAppModalsStore } from "@/stores/app-modals";
import { useAuthStore } from "@/stores/auth";
import {
  useSettingsStore,
  type ColorMode,
  type HskVersion,
  type PinyinMode,
} from "@/stores/settings";
import { isNative } from "@/services/native";
import { useCapabilitiesStore } from "@/stores/capabilities";
import { useToastStore } from "@/stores/toast";
import { useUserWordsStore } from "@/stores/userWords";
import { formatUtcDate } from "@/utils/time";
import { browserTimeZone, timeZoneOptions } from "@/utils/timezone";
import type { AutoGradeDelay } from "@/utils/review";

import Modal from "@/components/ui/Modal.vue";

const modals = useAppModalsStore();
const settings = useSettingsStore();
const auth = useAuthStore();
const toasts = useToastStore();
const capabilities = useCapabilitiesStore();
const userWords = useUserWordsStore();

// Use computed setters so the radios/select bind directly to the store.
const pinyinMode = computed<PinyinMode>({
  get: () => settings.pinyinMode,
  set: (v) => (settings.pinyinMode = v),
});
const hskVersion = computed<HskVersion>({
  get: () => settings.hskVersion,
  set: (v) => {
    settings.hskVersion = v;
    // Daily auto-enrol on the server draws from this list.
    if (auth.user) void auth.syncHskVersion();
  },
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
const autoGradeDelayMs = computed<AutoGradeDelay>({
  get: () => settings.autoGradeDelayMs,
  set: (v) => (settings.autoGradeDelayMs = v),
});
const autoGradeOptions: { value: AutoGradeDelay; label: string }[] = [
  { value: 0, label: "Off" },
  { value: 1000, label: "1 s" },
  { value: 2000, label: "2 s" },
  { value: 3000, label: "3 s" },
];

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
// Two-step button: the first click shows a confirm row with an estimated
// count (roughCount); the real count comes back from the import.
const importLevel = ref<number>(4);
const importing = ref(false);
const pendingConfirm = ref(false);
const lastResult = ref<{
  inserted: number;
  skipped: number;
  total_eligible: number;
} | null>(null);

const importMaxLevel = computed(() => (settings.hskVersion === "new" ? 9 : 6));

// Approximate new words per level, only for the "about N words" hint.
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

async function download(path: string) {
  try {
    await api.openDownload(path);
  } catch (e) {
    toasts.error(e instanceof Error ? e.message : "Couldn't start the download");
  }
}

// --- Account deletion ---
// Two-step inline confirm + password re-entry; irreversible.
const deleteArmed = ref(false);
const deletePassword = ref("");
const deleteBusy = ref(false);

async function confirmDeleteAccount() {
  if (!deletePassword.value) return;
  deleteBusy.value = true;
  try {
    await api.deleteAccount(deletePassword.value);
    setToken(null);
    toasts.success("Your account and all its data are gone. 再见!");
    modals.closeAll();
    setTimeout(() => window.location.reload(), 600);
  } catch (e) {
    toasts.error(
      e instanceof ApiError ? e.message : "Couldn't delete the account.",
    );
  } finally {
    deleteBusy.value = false;
  }
}

// --- API tokens for external integrations ---
// Read/write access to word state for outside apps (e.g. a speaking
// companion's own whisper/LLM/TTS stack), scoped and revocable. Loaded
// lazily on first modal open rather than at import time, since most
// sessions never open Settings.
const apiTokens = ref<api.ApiTokenSummary[]>([]);
const apiTokensLoaded = ref(false);
const newTokenName = ref("");
const newTokenScopes = ref<api.ApiTokenScope[]>(["read:words"]);
const creatingToken = ref(false);
const revealedToken = ref<api.CreatedApiToken | null>(null);
const revokingTokenId = ref<number | null>(null);

async function loadApiTokens() {
  try {
    const { tokens } = await api.listApiTokens();
    apiTokens.value = tokens;
    apiTokensLoaded.value = true;
  } catch (e) {
    toasts.error(e instanceof ApiError ? e.message : "Couldn't load API tokens.");
  }
}

watch(
  () => modals.settingsOpen,
  (open) => {
    if (open && auth.isAuthed && !apiTokensLoaded.value) void loadApiTokens();
  },
);

async function createToken() {
  const name = newTokenName.value.trim();
  if (!name || newTokenScopes.value.length === 0) return;
  creatingToken.value = true;
  try {
    const created = await api.createApiToken(name, [...newTokenScopes.value]);
    revealedToken.value = created;
    newTokenName.value = "";
    await loadApiTokens();
  } catch (e) {
    toasts.error(e instanceof ApiError ? e.message : "Couldn't create the token.");
  } finally {
    creatingToken.value = false;
  }
}

async function revokeToken(id: number) {
  revokingTokenId.value = id;
  try {
    await api.revokeApiToken(id);
    apiTokens.value = apiTokens.value.filter((t) => t.id !== id);
    toasts.success("Token revoked.");
  } catch (e) {
    toasts.error(e instanceof ApiError ? e.message : "Couldn't revoke the token.");
  } finally {
    revokingTokenId.value = null;
  }
}

async function copyRevealedToken() {
  if (!revealedToken.value) return;
  try {
    await navigator.clipboard.writeText(revealedToken.value.token);
    toasts.success("Copied.");
  } catch {
    // Clipboard API can be unavailable (no HTTPS, no permission) — the
    // token stays selectable in the field either way, so this is a
    // soft failure.
  }
}

// --- Daily auto-enrol target ---
// Bound to auth.user so the UI shows the server's value; 0 means
// auto-enrol is off.
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
  // On sets the recommended default of 5; off sets 0.
  set: (v) => {
    dailyNewWords.value = v ? 5 : 0;
  },
});

// --- Simplified vs Traditional display ---
const displayScript = computed<"auto" | "simp" | "trad">({
  get: () => auth.user?.display_script ?? "auto",
  set: (v) => {
    void auth.updateSettings({ display_script: v }).catch(() => {
      toasts.error("Couldn't save script preference.");
    });
  },
});

// --- FSRS retention target ---
// Three bands map to FSRS desired_retention values (the meaningful tuning
// range is 0.85-0.97):
//   relaxed → 0.90 — the FSRS library default. Fewer reviews, more
//             forgetting; review 3 of a "Good" streak lands at ~10d.
//   normal  → 0.95 — qingdu's default. Lines up with
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

// --- Review window ---
type ReviewWindow = "now" | "today" | "tomorrow";
const reviewWindow = computed<ReviewWindow>({
  get: () => (auth.user?.review_window as ReviewWindow) ?? "today",
  set: (v) => {
    void auth.updateSettings({ review_window: v }).catch(() => {
      toasts.error("Couldn't save review window.");
    });
  },
});
// --- Review focus: what the mixed session trains after the intro ---
const reviewFocus = computed<ReviewFocus>({
  get: () => auth.user?.review_focus ?? "both",
  set: (v) => {
    void auth.updateSettings({ review_focus: v }).catch(() => {
      toasts.error("Couldn't save review focus.");
    });
  },
});
const reviewFocusOptions: { value: ReviewFocus; label: string; hint: string }[] = [
  {
    value: "both",
    label: "Reading and writing",
    hint: "Default — read the hanzi (sound, tone, meaning) while a word is young, write it from memory once it is established.",
  },
  {
    value: "reading",
    label: "Reading",
    hint: "After the first encounter, always read: the hanzi alone, recall sound, tone and meaning.",
  },
  {
    value: "writing",
    label: "Writing",
    hint: "Always write the hanzi from pinyin and meaning — trace while young, from memory once established.",
  },
];

// --- Timezone: where "today" starts (streak, due today, new words) ---
// Filled from the device on first load; changeable here, e.g. after a move.
const deviceTimeZone = browserTimeZone();
const timeZone = computed<string>({
  get: () => auth.user?.timezone ?? "UTC",
  set: (v) => {
    void auth.updateSettings({ timezone: v }).catch(() => {
      toasts.error("Couldn't save timezone.");
    });
  },
});
const timeZoneChoices = computed(() => timeZoneOptions(auth.user?.timezone, deviceTimeZone));

const reviewWindowOptions: { value: ReviewWindow; label: string; hint: string }[] = [
  {
    value: "now",
    label: "Just due",
    hint: "Only cards that are due right now. Cards due later today wait.",
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

// --- Server switcher ---
// Runtime override for the API base URL. "Test" probes whatever URL is in
// the field so a typo'd server doesn't strand the user.

const apiBaseDefault = getDefaultApiBase();
// The Server section shows on web builds with a baked-in default and on
// every native build. F-Droid builds ship an empty default (first-launch
// ServerPicker), and that picker promises "switch later in Settings".
const serverSectionVisible = apiBaseDefault !== "" || isNative();
// On native-with-no-default there is no "default server" to name in the
// copy; show the server currently in use instead.
const apiBaseCurrent = getApiBase() || "(not set)";
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
  // Shared probe with the first-launch ServerPicker (client.ts testServer)
  // so the two testers can't disagree about what a valid server is.
  const result = await api.testServer(target);
  apiBaseTesting.value = false;
  apiBaseStatus.value = result.ok
    ? { kind: "ok", vocabCount: result.vocabCount }
    : { kind: "error", message: `Couldn't verify that URL — ${result.message}` };
}

function saveApiBase() {
  const target = apiBaseInput.value.replace(/\/$/, "");
  // Empty input is interpreted as "reset to default" so the user can
  // wipe the override by clearing the field.
  setApiBase(target === apiBaseDefault || target === "" ? null : target);
  // The JWT is signed by the old server's SECRET_KEY and would fail on
  // the new one; clearing it makes the "sign in again" toast true.
  setToken(null);
  toasts.success(
    "Server updated. Sign in again on the new server.",
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
          :title="
            auth.isAuthed
              ? 'Reading and review settings follow your account to every device; theme, reminders and vibration stay on this device.'
              : undefined
          "
        >
          {{ auth.isAuthed ? "Saved to your account" : "Saved on this device" }}
        </span>
      </div>
    </template>

    <div class="space-y-3">
      <!-- Five collapsible sections; the two most used (Display, Review)
           open by default. Native <details> handles keyboard and a11y. -->
      <details class="group rounded-md" open>
        <summary class="flex cursor-pointer list-none items-center justify-between rounded-md border border-border-subtle bg-bg-elevated px-3 py-2 hover:bg-bg-sunken">
          <span class="font-mono text-[11px] uppercase tracking-[0.2em] text-fg-subtle">Display</span>
          <svg class="size-3 text-fg-subtle transition-transform group-open:rotate-90" viewBox="0 0 12 12" fill="none"><path d="M4 2l4 4-4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
        </summary>
        <div class="mt-4 space-y-7 pl-1">
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

        </div>
      </details>

      <details class="group rounded-md" open>
        <summary class="flex cursor-pointer list-none items-center justify-between rounded-md border border-border-subtle bg-bg-elevated px-3 py-2 hover:bg-bg-sunken">
          <span class="font-mono text-[11px] uppercase tracking-[0.2em] text-fg-subtle">Review</span>
          <svg class="size-3 text-fg-subtle transition-transform group-open:rotate-90" viewBox="0 0 12 12" fill="none"><path d="M4 2l4 4-4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
        </summary>
        <div class="mt-4 space-y-7 pl-1">
      <fieldset v-if="auth.isAuthed">
        <legend
          class="mb-3 font-mono text-[11px] uppercase tracking-[0.2em] text-fg-subtle"
        >
          Review focus
        </legend>
        <div class="space-y-2">
          <label
            v-for="opt in reviewFocusOptions"
            :key="opt.value"
            class="flex cursor-pointer items-start gap-3 rounded-md border border-border-subtle px-3 py-2 transition-colors hover:bg-bg-sunken"
            :class="{
              'border-accent bg-bg-sunken': reviewFocus === opt.value,
            }"
          >
            <input
              v-model="reviewFocus"
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

      <!-- Review window -->
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

      <!-- Local day boundary -->
      <fieldset v-if="auth.isAuthed">
        <legend
          class="mb-3 font-mono text-[11px] uppercase tracking-[0.2em] text-fg-subtle"
        >
          Timezone
        </legend>
        <p class="mb-2 text-xs text-fg-muted">
          Your day starts at midnight here: streak, "due today" and new words
          roll over then.
        </p>
        <div class="flex flex-wrap items-center gap-3">
          <select
            v-model="timeZone"
            aria-label="Timezone"
            class="min-w-0 max-w-full rounded-md border border-border bg-bg-elevated px-2 py-1.5 text-sm text-fg focus:border-accent focus:outline-none"
          >
            <option v-for="tz in timeZoneChoices" :key="tz" :value="tz">
              {{ tz.replace(/_/g, " ") }}
            </option>
          </select>
          <button
            v-if="deviceTimeZone && deviceTimeZone !== timeZone"
            type="button"
            class="font-mono text-[11px] uppercase tracking-wider text-accent hover:underline"
            @click="timeZone = deviceTimeZone"
          >
            Use this device's ({{ deviceTimeZone.replace(/_/g, " ") }})
          </button>
        </div>
      </fieldset>

      <!-- FSRS retention -->
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

      <!-- Auto-grade delay after a writing quiz (device-local) -->
      <fieldset>
        <legend
          class="mb-1 font-mono text-[11px] uppercase tracking-[0.2em] text-fg-subtle"
        >
          Auto-grade after writing
        </legend>
        <p class="mb-3 text-xs text-fg-muted">
          After you finish drawing, the suggested grade fires on its own after
          this delay. Off means you always pick the grade yourself.
        </p>
        <div class="grid grid-cols-4 gap-2" role="radiogroup" aria-label="Auto-grade delay">
          <label
            v-for="opt in autoGradeOptions"
            :key="opt.value"
            class="flex cursor-pointer items-center justify-center rounded-md border border-border-subtle px-2 py-1.5 text-sm transition-colors hover:bg-bg-sunken"
            :class="{ 'border-accent bg-bg-sunken text-fg': autoGradeDelayMs === opt.value, 'text-fg-muted': autoGradeDelayMs !== opt.value }"
          >
            <input
              v-model="autoGradeDelayMs"
              type="radio"
              :value="opt.value"
              class="sr-only"
            />
            {{ opt.label }}
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
            Off: a tap only shows the meaning; the
            <span class="font-medium text-fg">Learning</span> button adds a
            word to your reviews. On: every new word you tap goes into your
            reviews.
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
            Show HSK color legend
          </span>
          <span class="block text-xs text-fg-muted">
            Adds a small key under the composition stats explaining each level's
            wash color.
          </span>
        </span>
      </label>

        </div>
      </details>

      <details class="group rounded-md">
        <summary class="flex cursor-pointer list-none items-center justify-between rounded-md border border-border-subtle bg-bg-elevated px-3 py-2 hover:bg-bg-sunken">
          <span class="font-mono text-[11px] uppercase tracking-[0.2em] text-fg-subtle">Appearance &amp; reminders</span>
          <svg class="size-3 text-fg-subtle transition-transform group-open:rotate-90" viewBox="0 0 12 12" fill="none"><path d="M4 2l4 4-4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
        </summary>
        <div class="mt-4 space-y-7 pl-1">
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

      <!-- Daily reminder. Shown on all platforms; on web the toggle saves
           the preference but never schedules anything (the native plugin is
           a no-op outside the Capacitor wrapper). -->
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
              A notification at a fixed time with your number of due cards
              (as of your last visit).
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

      <!-- Global trad/simp toggle. Auth-gated since
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

        </div>
      </details>

      <details v-if="auth.isAuthed" class="group rounded-md">
        <summary class="flex cursor-pointer list-none items-center justify-between rounded-md border border-border-subtle bg-bg-elevated px-3 py-2 hover:bg-bg-sunken">
          <span class="font-mono text-[11px] uppercase tracking-[0.2em] text-fg-subtle">Learning</span>
          <svg class="size-3 text-fg-subtle transition-transform group-open:rotate-90" viewBox="0 0 12 12" fill="none"><path d="M4 2l4 4-4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
        </summary>
        <div class="mt-4 space-y-7 pl-1">
      <!-- Daily auto-enrol target. Off by default; the checkbox flips the
           target between 0 and 5, with a numeric input revealed when on. -->
      <fieldset>
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

      <!-- Onboarding shortcut: one batch mark-as-known pass so intermediate
           learners skip the cold start. -->
      <fieldset>
        <legend
          class="mb-3 font-mono text-[11px] uppercase tracking-[0.2em] text-fg-subtle"
        >
          Onboarding shortcuts
        </legend>
        <p class="mb-3 text-xs text-fg-muted">
          Bulk-mark every word up to a level as known — or
          <RouterLink to="/welcome" class="text-accent hover:underline" @click="modals.settingsOpen = false">
            take the placement test
          </RouterLink>
          to find your level.
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

        </div>
      </details>

      <!-- Everything inside is auth-gated or server-related; logged-out on
           a same-origin web build the section would expand to nothing. -->
      <details v-if="auth.isAuthed || serverSectionVisible" class="group rounded-md">
        <summary class="flex cursor-pointer list-none items-center justify-between rounded-md border border-border-subtle bg-bg-elevated px-3 py-2 hover:bg-bg-sunken">
          <span class="font-mono text-[11px] uppercase tracking-[0.2em] text-fg-subtle">Data &amp; account</span>
          <svg class="size-3 text-fg-subtle transition-transform group-open:rotate-90" viewBox="0 0 12 12" fill="none"><path d="M4 2l4 4-4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
        </summary>
        <div class="mt-4 space-y-7 pl-1">
      <!-- What the server this app talks to offers (GET /api/capabilities). -->
      <p v-if="capabilities.caps" class="text-xs text-fg-muted">
        <span class="font-mono text-[10px] uppercase tracking-wider text-fg-subtle">This server</span>
        ·
        <template v-if="capabilities.llm?.available">
          AI help available ({{ capabilities.llm.model }})
        </template>
        <template v-else-if="capabilities.llm?.configured">
          AI help configured but not reachable right now
        </template>
        <template v-else>No AI help configured</template>
        · translation via {{ capabilities.caps.translation.join(", ") }}
      </p>
      <!-- Data export. Each button opens the download as a
           plain link with a short-lived ticket (api.openDownload), so the
           browser handles the file natively and no session token lands in
           a URL. -->
      <fieldset v-if="auth.isAuthed">
        <legend
          class="mb-3 font-mono text-[11px] uppercase tracking-[0.2em] text-fg-subtle"
        >
          Export
        </legend>
        <p class="mb-3 text-xs text-fg-muted leading-relaxed">
          Take your data with you. Everything is the complete account —
          texts, word states with scheduling, lists, and review history —
          as one JSON file. CSV and Anki cover just your words.
        </p>
        <div class="flex flex-wrap gap-2">
          <button
            type="button"
            @click="download(api.FULL_EXPORT_PATH)"
            class="inline-flex items-center gap-1.5 rounded-md border border-accent/40 bg-bg-elevated px-3 py-1.5 text-xs font-medium text-fg transition-colors hover:bg-bg-sunken"
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
            everything.json
          </button>
          <button
            type="button"
            @click="download(api.WORDS_CSV_PATH)"
            class="inline-flex items-center gap-1.5 rounded-md border border-border bg-bg-elevated px-3 py-1.5 text-xs font-medium text-fg-muted transition-colors hover:bg-bg-sunken hover:text-fg"
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
          </button>
          <button
            type="button"
            @click="download(api.WORDS_ANKI_PATH)"
            class="inline-flex items-center gap-1.5 rounded-md border border-border bg-bg-elevated px-3 py-1.5 text-xs font-medium text-fg-muted transition-colors hover:bg-bg-sunken hover:text-fg"
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
          </button>
        </div>
      </fieldset>

      <!-- Personal API tokens for external integrations,
           e.g. a speaking-companion app that wants to read which words
           you already know and report newly-encountered ones back. -->
      <fieldset v-if="auth.isAuthed">
        <legend
          class="mb-3 font-mono text-[11px] uppercase tracking-[0.2em] text-fg-subtle"
        >
          API tokens
        </legend>
        <p class="mb-3 text-xs text-fg-muted leading-relaxed">
          Let another app of yours read your known/learning words or report
          new ones it taught you — without sharing your password. Create a
          token scoped to just what it needs; revoke it any time.
        </p>

        <ul v-if="apiTokens.length" class="mb-3 space-y-1.5">
          <li
            v-for="t in apiTokens"
            :key="t.id"
            class="flex items-center justify-between gap-2 rounded-md border border-border-subtle bg-bg-elevated px-3 py-2 text-xs"
          >
            <span class="min-w-0">
              <span class="block truncate font-medium text-fg">{{ t.name }}</span>
              <span class="block font-mono text-[10px] text-fg-subtle">
                {{ t.token_prefix }}… · {{ t.scopes.join(", ") }}
                <template v-if="t.last_used_at"> · last used {{ formatUtcDate(t.last_used_at) }}</template>
                <template v-else> · never used</template>
              </span>
            </span>
            <button
              type="button"
              class="shrink-0 rounded-md border border-red-300 px-2 py-1 text-[11px] font-medium text-red-700 transition-colors hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-red-800 dark:text-red-300 dark:hover:bg-red-950/40"
              :disabled="revokingTokenId === t.id"
              @click="revokeToken(t.id)"
            >
              {{ revokingTokenId === t.id ? "Revoking…" : "Revoke" }}
            </button>
          </li>
        </ul>
        <p v-else-if="apiTokensLoaded" class="mb-3 text-xs text-fg-subtle">
          No tokens yet.
        </p>

        <div
          v-if="revealedToken"
          class="mb-3 rounded-md border border-accent/40 bg-bg-sunken p-3"
        >
          <p class="mb-2 text-xs text-fg-muted">
            Copy this now — it won't be shown again.
          </p>
          <div class="flex items-center gap-2">
            <code
              class="min-w-0 flex-1 truncate rounded bg-bg px-2 py-1.5 font-mono text-[11px] text-fg"
              >{{ revealedToken.token }}</code
            >
            <button
              type="button"
              class="shrink-0 rounded-md border border-border bg-bg-elevated px-2 py-1.5 text-[11px] font-medium text-fg-muted transition-colors hover:bg-bg-sunken hover:text-fg"
              @click="copyRevealedToken"
            >
              Copy
            </button>
          </div>
          <button
            type="button"
            class="mt-2 text-[11px] text-fg-muted underline-offset-2 hover:text-fg hover:underline"
            @click="revealedToken = null"
          >
            Done
          </button>
        </div>

        <div class="space-y-2">
          <label class="block">
            <span class="mb-1 block font-mono text-[10px] uppercase tracking-wider text-fg-subtle">
              Name
            </span>
            <input
              v-model="newTokenName"
              type="text"
              placeholder="e.g. speaking companion"
              class="w-full max-w-xs rounded-md border border-border-subtle bg-bg px-3 py-2 text-sm text-fg focus:border-accent focus:outline-none"
            />
          </label>
          <div class="flex flex-wrap gap-3">
            <label
              v-for="scope in api.API_TOKEN_SCOPES"
              :key="scope"
              class="flex items-center gap-1.5 text-xs text-fg-muted"
            >
              <input
                v-model="newTokenScopes"
                type="checkbox"
                :value="scope"
                class="accent-accent"
              />
              {{ scope }}
            </label>
          </div>
          <button
            type="button"
            class="rounded-md bg-accent px-3 py-1.5 text-xs font-medium text-accent-fg transition-colors hover:bg-accent/90 disabled:cursor-not-allowed disabled:opacity-50"
            :disabled="!newTokenName.trim() || newTokenScopes.length === 0 || creatingToken"
            @click="createToken"
          >
            {{ creatingToken ? "Creating…" : "Create token" }}
          </button>
        </div>
      </fieldset>

      <!-- Server switcher for self-hosters. Shown on every
           native build (F-Droid ships no baked-in default — the first-
           launch ServerPicker promises "switch later in Settings") and on
           web builds that carry a default URL. Hidden only on same-origin
           web builds, where the user already knows what server they hit. -->
      <fieldset v-if="serverSectionVisible">
        <legend
          class="mb-3 font-mono text-[11px] uppercase tracking-[0.2em] text-fg-subtle"
        >
          Server
        </legend>
        <p class="mb-3 text-xs text-fg-muted leading-relaxed">
          This app currently talks to
          <code class="rounded bg-bg-sunken px-1 py-0.5 font-mono text-[11px] text-fg">{{ apiBaseCurrent }}</code>.
          Point it at your own Qingdu instance to keep your data on
          infrastructure you control. Changing server signs you out; the
          new server has its own accounts.
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

      <!-- Self-service account deletion. Inline two-step
           confirm + password re-entry; there is no email, so there is no
           undo path once this runs. -->
      <fieldset v-if="auth.isAuthed && !auth.isAdmin">
        <legend
          class="mb-3 font-mono text-[11px] uppercase tracking-[0.2em] text-fg-subtle"
        >
          Delete account
        </legend>
        <p class="mb-3 text-xs text-fg-muted leading-relaxed">
          Removes your account and everything in it — texts, words, lists,
          review history — immediately and permanently. Download your data
          first if you might want it back.
        </p>
        <button
          v-if="!deleteArmed"
          type="button"
          class="rounded-md border border-red-300 px-3 py-1.5 text-xs font-medium text-red-700 transition-colors hover:bg-red-50 dark:border-red-800 dark:text-red-300 dark:hover:bg-red-950/40"
          @click="deleteArmed = true"
        >
          Delete my account…
        </button>
        <div v-else class="space-y-2">
          <label class="block">
            <span class="mb-1 block font-mono text-[10px] uppercase tracking-wider text-fg-subtle">
              Confirm with your password
            </span>
            <input
              v-model="deletePassword"
              type="password"
              autocomplete="current-password"
              class="w-full max-w-xs rounded-md border border-border-subtle bg-bg px-3 py-2 text-sm text-fg focus:border-accent focus:outline-none"
            />
          </label>
          <div class="flex items-center gap-2">
            <button
              type="button"
              class="rounded-md bg-red-600 px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-red-700 disabled:cursor-not-allowed disabled:opacity-50"
              :disabled="!deletePassword || deleteBusy"
              @click="confirmDeleteAccount"
            >
              {{ deleteBusy ? "Deleting…" : "Yes, delete everything" }}
            </button>
            <button
              type="button"
              class="text-xs text-fg-muted underline-offset-2 hover:text-fg hover:underline"
              @click="deleteArmed = false; deletePassword = ''"
            >
              Cancel
            </button>
          </div>
        </div>
      </fieldset>
        </div>
      </details>
    </div>
  </Modal>
</template>
