<script setup lang="ts">
/**
 * Trace and produce stages: pinyin + meaning above the canvas, the learner
 * writes the hanzi in hanzi-writer's stroke quiz. Trace shows the outline
 * per the user's setting; produce never does. The result line names the
 * grade the auto-grade will give.
 */
import { computed } from "vue";

import type { ReviewCard } from "@/api/client";
import type { WordGloss } from "@/api/types";
import WritingQuiz from "@/components/reader/WritingQuiz.vue";
import ContextSentence from "@/components/review/ContextSentence.vue";
import type { WritingResult } from "@/composables/use-review-card";
import { customGlosses } from "@/utils/glosses";
import { autoGradeForWriting } from "@/utils/review";

const props = defineProps<{
  stage: "trace" | "produce";
  card: ReviewCard;
  focus: WordGloss | null;
  /** Remounts the quiz per card. */
  cardKey: string;
  showOutline: boolean;
  mistakes: number;
  strokes: number;
  done: boolean;
  firstEncounter: boolean;
}>();

const emit = defineEmits<{
  (e: "complete", payload: WritingResult): void;
}>();

const autoGrade = computed(() =>
  autoGradeForWriting(props.mistakes, props.strokes, props.firstEncounter),
);
</script>

<template>
  <p class="font-mono text-[10px] uppercase tracking-wider text-accent">
    {{ stage === "trace" ? "Trace" : "Produce" }} · stability
    {{ Math.round(card.stability ?? 0) }}d
  </p>
  <div class="mt-3">
    <WritingQuiz
      :key="cardKey"
      :word="card.word"
      :pinyin="card.pinyin"
      :meaning="card.meaning"
      :meanings="card.meanings"
      :glosses="customGlosses(card.glosses, focus)"
      :focus="focus"
      :show-outline="showOutline"
      @complete="emit('complete', $event)"
    />
  </div>
  <p
    v-if="done"
    class="mt-4 font-mono text-[10px] uppercase tracking-wider text-fg-subtle"
  >
    {{ mistakes }} mistake{{ mistakes === 1 ? "" : "s" }} over
    {{ strokes }} strokes — auto-grading
    <span class="text-fg">
      {{ ["", "Again", "Hard", "Good", "Easy"][autoGrade] }}
    </span>
  </p>
  <p
    v-if="stage === 'trace' && done && firstEncounter && autoGrade === 3"
    class="mt-1 text-xs text-fg-muted"
  >
    First look — it comes back later in this session to write from memory.
  </p>
  <ContextSentence
    v-if="done && card.cloze_sentence"
    :sentence="card.cloze_sentence"
    :word="card.word"
    :source="card.sentence_source"
  />
</template>
