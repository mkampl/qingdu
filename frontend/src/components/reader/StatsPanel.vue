<script setup lang="ts">
import { computed, ref } from "vue";

import type { AnalysisStatistics, WordInfo } from "@/api/types";
import { useSettingsStore } from "@/stores/settings";
import { useUserWordsStore } from "@/stores/userWords";
import Button from "@/components/ui/Button.vue";

import LevelStrata from "./LevelStrata.vue";
import { levelNumber } from "./utils";

const props = withDefaults(
  defineProps<{
    statistics: AnalysisStatistics;
    /** Flat word list from the current analysis. Used to compute the
     *  progress-mode breakdown (new / learning / known) for this text. */
    words?: WordInfo[];
    canSave?: boolean;
    saved?: boolean;
    saving?: boolean;
    /** True when the analysis is linked to an existing saved-text record. */
    isUpdate?: boolean;
    /** True when the loaded saved-text content has been edited locally. */
    isEdited?: boolean;
    /** When false, the entire Save / Share / library section is hidden —
     *  used by the public-share view where the viewer is reading someone
     *  else's text and "Save to my library" doesn't fit. */
    showSave?: boolean;
  }>(),
  { showSave: true },
);

const emit = defineEmits<{ (e: "save"): void; (e: "share"): void }>();

const settings = useSettingsStore();
const userWords = useUserWordsStore();

const CJK_RE = /[一-鿿]/;

/** Distinct learnable words in this text. Mirrors the backend's
 *  comprehension calculation so the headline numbers line up. */
const uniqueCjkWords = computed<string[]>(() => {
  const out = new Set<string>();
  for (const w of props.words ?? []) {
    if (!w.text || w.text === "\n") continue;
    if (w.translation_source === "linebreak") continue;
    if (!CJK_RE.test(w.text)) continue;
    out.add(w.text);
  }
  return Array.from(out);
});

/**
 * Per-text {new, learning, known} breakdown for progress mode. We use
 * unique words (not occurrences) so a paragraph that repeats 的 fifty
 * times doesn't dominate the chart.
 */
const progressBreakdown = computed(() => {
  let learning = 0;
  let known = 0;
  for (const word of uniqueCjkWords.value) {
    const state = userWords.stateOf(word);
    if (state === "learning") learning += 1;
    else if (state === "known" || state === "ignored") known += 1;
  }
  const total = uniqueCjkWords.value.length;
  const newCount = Math.max(0, total - learning - known);
  return { new: newCount, learning, known, total };
});

const compositionExpanded = ref(false);

const distribution = computed(() =>
  settings.hskVersion === "old"
    ? props.statistics.hsk_distribution_old
    : props.statistics.hsk_distribution_new,
);
const totalHskWords = computed(() =>
  settings.hskVersion === "old"
    ? props.statistics.hsk_words_old
    : props.statistics.hsk_words_new,
);
const estimatedLevel = computed(() =>
  settings.hskVersion === "old"
    ? props.statistics.estimated_level_old
    : props.statistics.estimated_level_new,
);
const estimatedNumber = computed(() => levelNumber(estimatedLevel.value));
const coveragePct = computed(() => {
  const total = props.statistics.total_words || 1;
  return Math.round((totalHskWords.value / total) * 100);
});
</script>

<template>
  <aside
    class="flex flex-col gap-7 text-sm"
    aria-label="Composition and actions"
  >
    <!-- Estimated reading level — display-typography moment. -->
    <section>
      <p
        class="font-mono text-[10px] uppercase tracking-[0.2em] text-fg-subtle"
      >
        Estimated level
      </p>
      <div class="mt-1.5 flex items-baseline gap-2">
        <span class="font-display text-4xl font-medium leading-none text-fg">
          {{ estimatedNumber !== null ? estimatedNumber : "—" }}
        </span>
        <span class="font-display text-base text-fg-muted">
          /
          {{ settings.hskVersion === "old" ? "6" : "9" }}
        </span>
        <span
          class="font-mono text-[10px] uppercase tracking-wider text-fg-subtle"
        >
          {{ settings.hskVersion === "old" ? "old HSK" : "new HSK" }}
        </span>
      </div>
    </section>

    <!-- Composition strata. Switches with colorMode so the sidebar
         matches what the reader is showing on the page:
         - progress: blue/accent/plain breakdown of THIS text's unique
           CJK words (HSK distribution demoted to a collapsible).
         - hsk / off: HSK distribution headline. -->
    <section
      v-if="settings.colorMode === 'progress' && progressBreakdown.total > 0"
    >
      <p
        class="mb-2 font-mono text-[10px] uppercase tracking-[0.2em] text-fg-subtle"
      >
        Your progress
      </p>
      <div
        class="relative h-3 w-full overflow-hidden rounded-[2px] border border-border-subtle bg-bg-sunken"
        :title="`${progressBreakdown.known} known · ${progressBreakdown.learning} learning · ${progressBreakdown.new} new (of ${progressBreakdown.total} unique words)`"
      >
        <div class="flex h-full w-full">
          <!-- Known on the left (the "done" portion). -->
          <div
            v-if="progressBreakdown.known"
            class="h-full transition-[flex-basis]"
            :style="{
              flexBasis: `${(progressBreakdown.known / progressBreakdown.total) * 100}%`,
              backgroundColor:
                'color-mix(in oklch, var(--color-fg-subtle), transparent 70%)',
              boxShadow: 'inset -1px 0 0 0 var(--color-bg-elevated)',
            }"
          />
          <!-- Learning in the accent color (warm coral). -->
          <div
            v-if="progressBreakdown.learning"
            class="h-full transition-[flex-basis]"
            :style="{
              flexBasis: `${(progressBreakdown.learning / progressBreakdown.total) * 100}%`,
              backgroundColor:
                'color-mix(in oklch, var(--color-accent), transparent 25%)',
              boxShadow: 'inset -1px 0 0 0 var(--color-bg-elevated)',
            }"
          />
          <!-- New on the right (blue). -->
          <div
            v-if="progressBreakdown.new"
            class="h-full transition-[flex-basis]"
            :style="{
              flexBasis: `${(progressBreakdown.new / progressBreakdown.total) * 100}%`,
              backgroundColor:
                'color-mix(in oklch, var(--color-progress-new), transparent 25%)',
            }"
          />
        </div>
      </div>
      <ul
        class="mt-1.5 flex flex-wrap gap-x-3 gap-y-0.5 text-[10px] tabular-nums"
      >
        <li class="flex items-center gap-1 text-fg-muted">
          <span
            class="inline-block size-2 rounded-sm"
            :style="{
              backgroundColor:
                'color-mix(in oklch, var(--color-fg-subtle), transparent 70%)',
            }"
          />
          <span class="font-mono uppercase tracking-wider">Known</span>
          <span class="text-fg">{{ progressBreakdown.known }}</span>
        </li>
        <li class="flex items-center gap-1 text-fg-muted">
          <span
            class="inline-block size-2 rounded-sm"
            :style="{
              backgroundColor:
                'color-mix(in oklch, var(--color-accent), transparent 25%)',
            }"
          />
          <span class="font-mono uppercase tracking-wider">Learning</span>
          <span class="text-fg">{{ progressBreakdown.learning }}</span>
        </li>
        <li class="flex items-center gap-1 text-fg-muted">
          <span
            class="inline-block size-2 rounded-sm"
            :style="{
              backgroundColor:
                'color-mix(in oklch, var(--color-progress-new), transparent 25%)',
            }"
          />
          <span class="font-mono uppercase tracking-wider">New</span>
          <span class="text-fg">{{ progressBreakdown.new }}</span>
        </li>
      </ul>

      <!-- HSK distribution still useful but demoted under a disclosure. -->
      <button
        type="button"
        class="mt-3 flex w-full items-center justify-between text-fg-muted transition-colors hover:text-fg"
        :aria-expanded="compositionExpanded"
        @click="compositionExpanded = !compositionExpanded"
      >
        <span class="font-mono text-[10px] uppercase tracking-wider">
          HSK composition
        </span>
        <svg
          width="10"
          height="10"
          viewBox="0 0 10 10"
          fill="none"
          class="transition-transform"
          :class="{ 'rotate-90': compositionExpanded }"
          aria-hidden="true"
        >
          <path
            d="M3.5 2l3 3-3 3"
            stroke="currentColor"
            stroke-width="1.4"
            stroke-linecap="round"
            stroke-linejoin="round"
          />
        </svg>
      </button>
      <div v-if="compositionExpanded" class="mt-2">
        <LevelStrata
          :distribution="distribution"
          :total-hsk-words="totalHskWords"
          :estimated-level="estimatedLevel"
        />
      </div>
    </section>

    <!-- HSK composition strata (headline when colorMode !== 'progress'). -->
    <section v-else>
      <p
        class="mb-2 font-mono text-[10px] uppercase tracking-[0.2em] text-fg-subtle"
      >
        Composition
      </p>
      <LevelStrata
        :distribution="distribution"
        :total-hsk-words="totalHskWords"
        :estimated-level="estimatedLevel"
      />
    </section>

    <!-- Counts grid -->
    <section
      class="grid grid-cols-3 gap-x-3 gap-y-1 border-t border-border-subtle pt-5"
    >
      <div>
        <p class="font-display text-2xl font-medium leading-none text-fg">
          {{ statistics.total_words.toLocaleString() }}
        </p>
        <p
          class="mt-1 font-mono text-[9px] uppercase tracking-wider text-fg-subtle"
        >
          Tokens
        </p>
      </div>
      <div>
        <p class="font-display text-2xl font-medium leading-none text-fg">
          {{ statistics.total_characters.toLocaleString() }}
        </p>
        <p
          class="mt-1 font-mono text-[9px] uppercase tracking-wider text-fg-subtle"
        >
          Chars
        </p>
      </div>
      <div>
        <p class="font-display text-2xl font-medium leading-none text-fg">
          {{ coveragePct }}<span class="text-base text-fg-muted">%</span>
        </p>
        <p
          class="mt-1 font-mono text-[9px] uppercase tracking-wider text-fg-subtle"
        >
          HSK
        </p>
      </div>
    </section>

    <!-- HSK colour legend — opt-in via Settings. Two columns of swatches so
         it stays compact in the margin panel. -->
    <section
      v-if="settings.showLegend"
      class="border-t border-border-subtle pt-5"
    >
      <p
        class="mb-2 font-mono text-[10px] uppercase tracking-[0.2em] text-fg-subtle"
      >
        Levels
      </p>
      <ul class="grid grid-cols-2 gap-x-3 gap-y-1.5 text-xs">
        <li
          v-for="n in settings.hskVersion === 'old' ? 6 : 9"
          :key="n"
          class="flex items-center gap-2"
        >
          <span
            class="inline-block size-2.5 rounded-sm"
            :style="{
              backgroundColor: `color-mix(in oklch, var(--color-hsk-${n}), transparent 40%)`,
              boxShadow: `inset 0 0 0 1px color-mix(in oklch, var(--color-hsk-${n}), transparent 10%)`,
            }"
          />
          <span class="text-fg-muted">HSK {{ n }}</span>
        </li>
      </ul>
    </section>

    <!-- Save action — label and disabled state reflect:
           - anonymous           -> 'Sign in to save'
           - fresh analysis      -> 'Save text' (primary)
           - just saved          -> 'Saved' (disabled)
           - loaded saved text   -> 'Saved' (disabled)
           - loaded + edited     -> 'Update' (primary, enabled)
    -->
    <section v-if="showSave" class="border-t border-border-subtle pt-5">
      <Button
        :variant="canSave ? 'primary' : 'secondary'"
        full
        :loading="saving"
        :disabled="!canSave || (saved && !isEdited)"
        @click="emit('save')"
      >
        <template v-if="!canSave">Sign in to save</template>
        <template v-else-if="isEdited">
          <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
            <path
              d="M2 9.5l8-8M2 9.5l3 0M2 9.5l0-3"
              stroke="currentColor"
              stroke-width="1.4"
              stroke-linecap="round"
            />
          </svg>
          Update
        </template>
        <template v-else-if="saved">
          <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
            <path
              d="M2 6.5l3 3 5-7"
              stroke="currentColor"
              stroke-width="1.5"
              stroke-linecap="round"
              stroke-linejoin="round"
            />
          </svg>
          Saved
        </template>
        <template v-else>Save text</template>
      </Button>
      <!-- Share button — only meaningful once a text is saved (we need
           the record id to mint the token). Click opens ShareModal. -->
      <button
        v-if="isUpdate"
        type="button"
        class="mt-2 inline-flex w-full items-center justify-center gap-1.5 rounded-md border border-border-subtle bg-bg-elevated px-3 py-1.5 text-xs font-medium text-fg-muted transition-colors hover:bg-bg-sunken hover:text-fg"
        @click="emit('share')"
      >
        <svg
          width="11"
          height="11"
          viewBox="0 0 11 11"
          fill="none"
          aria-hidden="true"
        >
          <path
            d="M3 5.5l5-2.5M3 5.5l5 2.5M2 5.5a1.2 1.2 0 110 .01M8.5 3a1.2 1.2 0 110 .01M8.5 8a1.2 1.2 0 110 .01"
            stroke="currentColor"
            stroke-width="1.3"
            stroke-linecap="round"
            stroke-linejoin="round"
          />
        </svg>
        Share link
      </button>
      <p
        class="mt-2 font-mono text-[9px] uppercase tracking-wider text-fg-subtle"
      >
        {{
          !canSave
            ? "Texts you save show up here later"
            : isEdited
              ? "Save your edits to this text"
              : isUpdate
                ? "In your library"
                : "Adds to your library"
        }}
      </p>
    </section>
  </aside>
</template>
