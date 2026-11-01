<script setup lang="ts">
/** Cloze mode: the sentence with the target word blanked; type the word. */
import type { ReviewCard } from "@/api/client";
import type { WordGloss } from "@/api/types";
import WordReadings from "@/components/reader/WordReadings.vue";

defineProps<{
  card: ReviewCard;
  focus: WordGloss | null;
  feedback: "" | "correct" | "wrong";
}>();

const input = defineModel<string>({ required: true });

const emit = defineEmits<{
  (e: "submit"): void;
}>();
</script>

<template>
  <p class="font-mono text-[10px] uppercase tracking-wider text-fg-subtle">
    Fill the blank
  </p>
  <p class="mt-3 font-cn-serif text-2xl leading-relaxed text-fg">
    {{ card.cloze_template ?? card.cloze_sentence }}
  </p>
  <div v-if="feedback === ''" class="mt-6 mx-auto max-w-xs">
    <input
      v-model="input"
      type="text"
      autocomplete="off"
      autocapitalize="off"
      spellcheck="false"
      placeholder="Type the missing word"
      class="w-full rounded-md border border-border bg-bg-elevated px-3 py-2 text-center font-cn-serif text-xl text-fg focus:border-accent focus:outline-none"
      @keydown.enter="emit('submit')"
    />
    <button
      type="button"
      class="mt-3 w-full rounded-md bg-accent px-4 py-2 text-sm font-medium text-accent-fg transition-opacity hover:opacity-90 disabled:opacity-40"
      :disabled="!input.trim()"
      @click="emit('submit')"
    >
      Submit
    </button>
  </div>
  <div v-else class="mt-6 space-y-2 text-center">
    <p
      class="font-mono text-[11px] uppercase tracking-wider"
      :class="
        feedback === 'correct'
          ? 'text-emerald-600 dark:text-emerald-300'
          : 'text-red-700 dark:text-red-300'
      "
    >
      {{ feedback === "correct" ? "Correct" : "Not quite" }}
    </p>
    <p class="font-cn-serif text-3xl text-fg">{{ card.word }}</p>
    <p class="font-sans text-sm text-fg-muted">{{ card.pinyin }}</p>
    <WordReadings
      class="mx-auto max-w-xs"
      :meaning="card.meaning"
      :meanings="card.meanings"
      :meaning-tags="card.meaning_tags"
      :readings="card.readings"
      :glosses="card.glosses"
      :focus="focus"
      headline-class="font-display text-base text-fg"
    />
    <p
      class="mx-auto mt-3 max-w-md font-cn-serif text-lg leading-relaxed text-fg-muted"
    >
      {{ card.cloze_sentence }}
    </p>
  </div>
</template>
