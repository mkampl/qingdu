<script setup lang="ts">
/**
 * The answer under a recognition or read card once it is revealed:
 * pinyin, meanings (other readings folded), measure words and parts
 * (folded), and the context sentence. The default slot goes first (the
 * read stage's verdict on the typed pinyin).
 */
import type { ReviewCard } from "@/api/client";
import type { WordGloss } from "@/api/types";
import WordDetails from "@/components/reader/WordDetails.vue";
import WordReadings from "@/components/reader/WordReadings.vue";
import ContextSentence from "@/components/review/ContextSentence.vue";

defineProps<{
  card: ReviewCard;
  /** The meaning the card leads with (see WordReadings). */
  focus: WordGloss | null;
}>();
</script>

<template>
  <div class="mt-4 space-y-1.5 sm:mt-6">
    <slot />
    <p class="font-sans text-base text-fg-muted">{{ card.pinyin }}</p>
    <WordReadings
      class="mx-auto max-w-md"
      :meaning="card.meaning"
      :meanings="card.meanings"
      :meaning-tags="card.meaning_tags"
      :readings="card.readings"
      :glosses="card.glosses"
      :focus="focus"
      headline-class="font-display text-xl text-fg"
      list-class="mt-1 space-y-0.5 text-sm text-fg-muted"
      :max-meanings="3"
      collapse-others
    />
    <WordDetails :word="card.word" collapsible class="mx-auto max-w-md pt-2" />
    <ContextSentence
      v-if="card.cloze_sentence"
      :sentence="card.cloze_sentence"
      :word="card.word"
      :source="card.sentence_source"
    />
  </div>
</template>
