<script setup lang="ts">
import { computed } from "vue";

import type { ReviewFocus } from "@/api/client";
import { useAuthStore } from "@/stores/auth";
import { useSettingsStore } from "@/stores/settings";
import { useToastStore } from "@/stores/toast";
import { browserTimeZone, timeZoneOptions } from "@/utils/timezone";
import type { AutoGradeDelay } from "@/utils/review";

import OptionFieldset from "@/components/settings/OptionFieldset.vue";
import SettingsSection from "@/components/settings/SettingsSection.vue";

const settings = useSettingsStore();
const auth = useAuthStore();
const toasts = useToastStore();

// Device-local settings bind straight to the store through computed setters.
const showLegend = computed<boolean>({
  get: () => settings.showLegend,
  set: (v) => (settings.showLegend = v),
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
</script>

<template>
  <SettingsSection title="Review" open>
    <OptionFieldset v-if="auth.isAuthed"
      v-model="reviewFocus"
      :options="reviewFocusOptions"
    >
      Review focus
    </OptionFieldset>

    <!-- Review window -->
    <OptionFieldset v-if="auth.isAuthed"
      v-model="reviewWindow"
      :options="reviewWindowOptions"
    >
      Review window
    </OptionFieldset>

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
    <OptionFieldset v-if="auth.isAuthed"
      v-model="reviewBand"
      :options="reviewBandOptions"
    >
      Review challenge
    </OptionFieldset>

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
  </SettingsSection>
</template>
