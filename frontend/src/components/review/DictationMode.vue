<script setup lang="ts">
/**
 * Dictation mode: the word is played; the learner types the hanzi or the
 * pinyin with tones. Enter checks, and once checked, grades.
 */
import type { ReviewCard } from "@/api/client";
import type { WordGloss } from "@/api/types";
import WordReadings from "@/components/reader/WordReadings.vue";
import ContextSentence from "@/components/review/ContextSentence.vue";
import type { DictationFeedback } from "@/utils/review";

defineProps<{
  card: ReviewCard;
  focus: WordGloss | null;
  feedback: DictationFeedback;
  ttsLoading: boolean;
}>();

const input = defineModel<string>({ required: true });

const emit = defineEmits<{
  (e: "play"): void;
  (e: "submit"): void;
  (e: "continue"): void;
}>();

const VERDICT: Record<DictationFeedback, string> = {
  correct: "Correct",
  toneless: "Right sound — type the tones too (mǎ or ma3)",
  tone: "Wrong tone",
  wrong: "Not quite",
  "": "",
};
</script>

<template>
  <button
    type="button"
    class="mx-auto inline-flex size-20 items-center justify-center rounded-full border border-border bg-bg-elevated text-fg-muted transition-colors hover:bg-bg-sunken hover:text-fg disabled:opacity-50"
    :disabled="ttsLoading"
    aria-label="Play word"
    @click="emit('play')"
  >
    <span
      v-if="ttsLoading"
      class="inline-block size-6 animate-spin rounded-full border-2 border-current border-t-transparent"
    />
    <svg v-else width="28" height="28" viewBox="0 0 28 28" fill="none">
      <path d="M5 10h4l5-4v16l-5-4H5v-8z" fill="currentColor" />
      <path
        d="M18 9c2 2 2 8 0 10M21 6c4 3 4 13 0 16"
        stroke="currentColor"
        stroke-width="1.8"
        stroke-linecap="round"
      />
    </svg>
  </button>

  <div class="mt-8">
    <input
      v-model="input"
      :readonly="feedback !== ''"
      type="text"
      placeholder="Hanzi or pinyin with tones (mǎ / ma3)"
      autocomplete="off"
      autocapitalize="off"
      autocorrect="off"
      spellcheck="false"
      class="w-full max-w-md rounded-lg border border-border bg-bg-elevated px-4 py-3 text-center font-cn-serif text-2xl text-fg focus:border-accent focus:outline-none"
      @keydown.enter.prevent="feedback === '' ? emit('submit') : emit('continue')"
    />
  </div>

  <div v-if="feedback === ''" class="mt-6">
    <button
      type="button"
      class="rounded-full bg-accent px-5 py-2 text-sm font-medium text-accent-fg transition-opacity hover:opacity-90 disabled:opacity-50"
      :disabled="!input.trim()"
      @click="emit('submit')"
    >
      Check
    </button>
  </div>

  <div v-else class="mt-6 space-y-2">
    <p
      class="font-mono text-[11px] uppercase tracking-wider"
      :class="
        feedback === 'correct'
          ? 'text-emerald-600 dark:text-emerald-300'
          : feedback === 'toneless'
            ? 'text-amber-700 dark:text-amber-300'
            : 'text-red-700 dark:text-red-300'
      "
    >
      {{ VERDICT[feedback] }}
    </p>
    <p class="font-cn-serif text-3xl text-fg">{{ card.word }}</p>
    <p class="font-sans text-sm text-fg-muted">{{ card.pinyin }}</p>
    <WordReadings
      class="mx-auto max-w-md"
      :meaning="card.meaning"
      :meanings="card.meanings"
      :meaning-tags="card.meaning_tags"
      :readings="card.readings"
      :glosses="card.glosses"
      :focus="focus"
      headline-class="font-display text-base text-fg"
    />
    <ContextSentence
      v-if="card.cloze_sentence"
      :sentence="card.cloze_sentence"
      :word="card.word"
      :source="card.sentence_source"
    />
  </div>
</template>
