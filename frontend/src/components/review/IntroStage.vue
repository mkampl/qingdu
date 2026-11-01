<script setup lang="ts">
/**
 * Intro stage, for new cards: hanzi, pinyin, meaning, stroke animation.
 * "Got it" moves on to the trace stage.
 */
import type { ReviewCard } from "@/api/client";
import type { WordGloss } from "@/api/types";
import StrokeOrder from "@/components/reader/StrokeOrder.vue";
import WordDetails from "@/components/reader/WordDetails.vue";
import WordReadings from "@/components/reader/WordReadings.vue";
import ContextSentence from "@/components/review/ContextSentence.vue";

defineProps<{
  card: ReviewCard;
  focus: WordGloss | null;
  /** Restarts the stroke animation per card. */
  cardKey: string;
}>();

const emit = defineEmits<{
  (e: "continue"): void;
}>();
</script>

<template>
  <p class="font-mono text-[10px] uppercase tracking-wider text-accent">
    New · listen + read + watch
  </p>
  <p class="mt-3 font-mono text-sm tracking-widest text-fg-muted">
    {{ card.pinyin }}
  </p>
  <p class="font-cn-serif text-6xl text-fg sm:text-7xl">
    {{ card.word }}
  </p>
  <WordReadings
    class="mx-auto mt-4 max-w-md"
    :meaning="card.meaning"
    :meanings="card.meanings"
    :meaning-tags="card.meaning_tags"
    :readings="card.readings"
    :glosses="card.glosses"
    :focus="focus"
    headline-class="font-display text-base leading-snug text-fg"
  />
  <WordDetails :word="card.word" class="mx-auto mt-3 max-w-md" />
  <ContextSentence
    v-if="card.cloze_sentence"
    :sentence="card.cloze_sentence"
    :word="card.word"
    :source="card.sentence_source"
  />

  <!-- For multi-char words auto-advance draws every character in turn. -->
  <div class="mt-6 flex justify-center">
    <StrokeOrder :key="cardKey" :chars="card.word" auto-advance />
  </div>

  <div
    class="sticky bottom-0 -mx-4 mt-6 flex flex-col items-center gap-2 bg-bg-elevated/95 pb-3 pt-3 backdrop-blur sm:static sm:mx-0 sm:bg-transparent sm:pb-0 sm:pt-0 sm:backdrop-blur-none"
  >
    <button
      type="button"
      class="rounded-full bg-accent px-5 py-2 text-sm font-medium text-accent-fg transition-opacity hover:opacity-90"
      @click="emit('continue')"
    >
      Got it · try writing it
    </button>
    <p class="font-mono text-[10px] uppercase tracking-wider text-fg-subtle">
      Listen + watch · then write it from memory
    </p>
  </div>
</template>
