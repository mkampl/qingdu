<script setup lang="ts">
/**
 * Read stage: only the hanzi; sound, tone and meaning come from memory.
 * Typing the pinyin is optional and checked against the card; Show answer
 * (space) reveals and the learner grades themselves.
 */
import type { ReviewCard } from "@/api/client";
import type { WordGloss } from "@/api/types";
import RevealedAnswer from "@/components/review/RevealedAnswer.vue";
import type { PinyinVerdict } from "@/utils/pinyin-answer";

defineProps<{
  card: ReviewCard;
  focus: WordGloss | null;
  revealed: boolean;
  verdict: "" | PinyinVerdict;
}>();

const input = defineModel<string>({ required: true });

const emit = defineEmits<{
  (e: "reveal"): void;
}>();

const VERDICT: Record<PinyinVerdict, string> = {
  exact: "Right, tones too",
  toneless: "Right sound — tones not typed",
  "wrong-tone": "Wrong tone",
  wrong: "Not this word",
};
</script>

<template>
  <p class="font-mono text-[10px] uppercase tracking-wider text-accent">
    Read · stability {{ Math.round(card.stability ?? 0) }}d
  </p>
  <p
    class="font-cn-serif leading-none text-fg sm:text-7xl"
    :class="revealed ? 'mt-2 text-5xl' : 'mt-4 text-6xl'"
  >
    {{ card.word }}
  </p>
  <template v-if="!revealed">
    <p class="mt-6 text-sm text-fg-muted">
      Say it with its tone and meaning — then check.
    </p>
    <input
      v-model="input"
      type="text"
      placeholder="Pinyin with tones (optional)"
      autocomplete="off"
      autocapitalize="off"
      autocorrect="off"
      spellcheck="false"
      class="mt-4 w-full max-w-xs rounded-lg border border-border bg-bg-elevated px-4 py-2 text-center text-base text-fg focus:border-accent focus:outline-none"
      @keydown.enter.prevent="emit('reveal')"
    />
    <div>
      <button
        type="button"
        class="mt-5 inline-flex items-center gap-2 rounded-full border border-border bg-bg-elevated px-5 py-2 text-sm font-medium text-fg-muted transition-colors hover:bg-bg-sunken hover:text-fg"
        @click="emit('reveal')"
      >
        Show answer
        <span class="font-mono text-[9px] uppercase tracking-wider opacity-70">
          (space)
        </span>
      </button>
    </div>
  </template>
  <RevealedAnswer v-else :card="card" :focus="focus">
    <p
      v-if="verdict"
      class="font-mono text-[11px] uppercase tracking-wider"
      :class="
        verdict === 'exact'
          ? 'text-emerald-600 dark:text-emerald-300'
          : verdict === 'toneless'
            ? 'text-amber-700 dark:text-amber-300'
            : 'text-red-700 dark:text-red-300'
      "
    >
      {{ VERDICT[verdict] }}
    </p>
  </RevealedAnswer>
</template>
