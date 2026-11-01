<script setup lang="ts">
/**
 * Writing mode: the stroke quiz with an outline toggle (the user's
 * setting), then the result and the suggested grade.
 */
import { computed } from "vue";

import type { ReviewCard } from "@/api/client";
import type { WordGloss } from "@/api/types";
import WritingQuiz from "@/components/reader/WritingQuiz.vue";
import type { WritingResult } from "@/composables/use-review-card";
import { useSettingsStore } from "@/stores/settings";
import { customGlosses } from "@/utils/glosses";
import { suggestedGradeForMistakes } from "@/utils/review";

const props = defineProps<{
  card: ReviewCard;
  focus: WordGloss | null;
  /** Remounts the quiz per card. */
  cardKey: string;
  mistakes: number;
  strokes: number;
  done: boolean;
}>();

const emit = defineEmits<{
  (e: "complete", payload: WritingResult): void;
}>();

const settings = useSettingsStore();
const suggested = computed(() => suggestedGradeForMistakes(props.mistakes, props.strokes));
</script>

<template>
  <div class="mb-3 flex justify-center">
    <button
      type="button"
      class="font-mono text-[10px] uppercase tracking-wider text-fg-subtle transition-colors hover:text-fg"
      :aria-pressed="settings.writingShowOutline"
      @click="settings.writingShowOutline = !settings.writingShowOutline"
    >
      Outline: {{ settings.writingShowOutline ? "on" : "off" }}
    </button>
  </div>
  <WritingQuiz
    :key="cardKey"
    :word="card.word"
    :pinyin="card.pinyin"
    :meaning="card.meaning"
    :meanings="card.meanings"
    :glosses="customGlosses(card.glosses, focus)"
    :focus="focus"
    :show-outline="settings.writingShowOutline"
    @complete="emit('complete', $event)"
  />
  <div v-if="done" class="mt-4 space-y-1 text-center">
    <p
      class="font-mono text-[11px] uppercase tracking-wider"
      :class="
        suggested >= 3
          ? 'text-emerald-600 dark:text-emerald-300'
          : suggested === 2
            ? 'text-amber-700 dark:text-amber-300'
            : 'text-red-700 dark:text-red-300'
      "
    >
      {{
        mistakes === 0
          ? `Perfect (${strokes} stroke${strokes === 1 ? "" : "s"})`
          : `${mistakes} mistake${mistakes === 1 ? "" : "s"} on ${strokes} stroke${strokes === 1 ? "" : "s"}`
      }}
    </p>
    <p class="font-mono text-[10px] uppercase tracking-wider text-fg-subtle">
      Suggested grade:
      {{ ["", "Again", "Hard", "Good", "Easy"][suggested] }}
    </p>
  </div>
</template>
