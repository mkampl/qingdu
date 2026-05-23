<script setup lang="ts">
/**
 * Continuous narration player. Sticks to the bottom of the reader on
 * desktop, sits in the natural flow on mobile. Subscribes to the analysis
 * store so the queue auto-syncs to whatever the current text is; sentence
 * boundaries are derived once via groupIntoSentences().
 */
import { computed, watch } from "vue";

import type { AnalysisResponse } from "@/api/types";
import { useAudioPlayerStore } from "@/stores/audio-player";
import {
  groupIntoSentences,
  type Sentence,
} from "@/components/reader/utils";

const props = defineProps<{ analysis: AnalysisResponse }>();

const player = useAudioPlayerStore();

const sentences = computed<Sentence[]>(() =>
  groupIntoSentences(props.analysis.words),
);

// Sync the player queue whenever the text changes. We rebuild from scratch
// because indexing into a partial-overlap previous queue would be brittle.
watch(
  sentences,
  (next) => {
    player.setQueue(
      next
        .filter((s) => s.text && s.text.trim().length > 0)
        .map((s) => ({ key: s.key, text: s.text })),
    );
  },
  { immediate: true },
);

const cursorDisplay = computed(() => {
  if (!player.hasQueue) return "—";
  return `${player.cursor + 1} / ${player.total}`;
});

const rateOptions = [0.5, 0.75, 1, 1.25, 1.5, 1.75];
</script>

<template>
  <div
    v-if="player.hasQueue"
    class="sticky bottom-0 z-30 mx-auto mt-6 w-full max-w-3xl px-2 pb-2 sm:bottom-3 sm:pb-3"
    role="region"
    aria-label="Audio player"
  >
    <div
      class="flex items-center gap-2 rounded-full border border-border bg-bg-elevated/95 px-2 py-1.5 shadow-lg backdrop-blur-sm sm:gap-3 sm:px-3 sm:py-2"
    >
      <!-- Rewind / Play-Pause / Forward -->
      <button
        type="button"
        class="inline-flex size-9 items-center justify-center rounded-full text-fg-muted transition-colors hover:bg-bg-sunken hover:text-fg disabled:opacity-40"
        aria-label="Previous sentence"
        :disabled="player.cursor === 0"
        @click="player.rewind()"
      >
        <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
          <path d="M9.5 2.5l-4 4.5 4 4.5M5 2.5v9" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" />
        </svg>
      </button>

      <button
        type="button"
        class="inline-flex size-10 items-center justify-center rounded-full bg-accent text-accent-fg transition-opacity hover:opacity-90 disabled:opacity-50"
        :aria-label="player.playing ? 'Pause' : 'Play'"
        :disabled="player.loading"
        @click="player.toggle()"
      >
        <span
          v-if="player.loading"
          class="inline-block size-4 animate-spin rounded-full border-2 border-current border-t-transparent"
        />
        <svg
          v-else-if="player.playing"
          width="16"
          height="16"
          viewBox="0 0 16 16"
          fill="currentColor"
          aria-hidden="true"
        >
          <rect x="4" y="3" width="3" height="10" rx="0.5" />
          <rect x="9" y="3" width="3" height="10" rx="0.5" />
        </svg>
        <svg v-else width="16" height="16" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
          <path d="M4.5 3l8 5-8 5V3z" />
        </svg>
      </button>

      <button
        type="button"
        class="inline-flex size-9 items-center justify-center rounded-full text-fg-muted transition-colors hover:bg-bg-sunken hover:text-fg disabled:opacity-40"
        aria-label="Next sentence"
        :disabled="player.cursor + 1 >= player.total"
        @click="player.advance()"
      >
        <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
          <path d="M4.5 2.5l4 4.5-4 4.5M9 2.5v9" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" />
        </svg>
      </button>

      <!-- Cursor / progress -->
      <div class="hidden flex-1 items-center gap-3 sm:flex">
        <span
          class="font-mono text-[10px] uppercase tracking-wider text-fg-subtle tabular-nums"
        >
          {{ cursorDisplay }}
        </span>
        <div class="relative h-[3px] flex-1 overflow-hidden rounded-full bg-bg-sunken">
          <div
            class="h-full rounded-full bg-accent transition-[width] duration-200"
            :style="{
              width:
                player.total > 0
                  ? `${((player.cursor + (player.playing ? 0.5 : 0)) / player.total) * 100}%`
                  : '0%',
            }"
          />
        </div>
      </div>

      <!-- Speed picker — compact menu via <select> for mobile parity. -->
      <label class="inline-flex items-center gap-1">
        <span class="sr-only">Playback speed</span>
        <select
          :value="player.playbackRate"
          class="appearance-none rounded-full border border-border-subtle bg-bg-elevated px-2 py-1 font-mono text-[11px] text-fg-muted hover:text-fg focus:border-accent focus:outline-none"
          @change="
            player.setRate(parseFloat(($event.target as HTMLSelectElement).value))
          "
        >
          <option v-for="r in rateOptions" :key="r" :value="r">{{ r }}×</option>
        </select>
      </label>

      <!-- Listen-mode toggle — collapses the input panel & stats so the
           text takes the whole column. -->
      <button
        type="button"
        class="inline-flex size-9 items-center justify-center rounded-full text-fg-muted transition-colors hover:bg-bg-sunken hover:text-fg"
        :class="{
          'bg-bg-sunken text-fg': player.listenMode,
        }"
        :aria-pressed="player.listenMode"
        title="Listen mode — text-only layout"
        aria-label="Toggle listen mode"
        @click="player.setListenMode(!player.listenMode)"
      >
        <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
          <path
            d="M3 7a4 4 0 018 0v3a1.5 1.5 0 01-1.5 1.5h-.5v-4h1V7a3 3 0 00-6 0v1h1v4h-.5A1.5 1.5 0 013 10V7z"
            fill="currentColor"
          />
        </svg>
      </button>
    </div>

    <p
      v-if="player.error"
      class="mt-1 text-center font-mono text-[10px] uppercase tracking-wider text-red-700 dark:text-red-300"
    >
      {{ player.error }}
    </p>
  </div>
</template>
