<script setup lang="ts">
/** Recognition mode: the hanzi; Show answer (space) reveals the rest. */
import type { ReviewCard } from "@/api/client";
import type { WordGloss } from "@/api/types";
import RevealedAnswer from "@/components/review/RevealedAnswer.vue";
import { formatHskLevel } from "@/utils/review";

defineProps<{
  card: ReviewCard;
  focus: WordGloss | null;
  revealed: boolean;
}>();

const emit = defineEmits<{
  (e: "reveal"): void;
}>();
</script>

<template>
  <p
    v-if="card.hsk_level"
    class="mb-4 font-mono text-[10px] uppercase tracking-wider text-fg-subtle"
  >
    {{ formatHskLevel(card.hsk_level) }}
  </p>
  <p
    class="font-cn-serif leading-none text-fg sm:text-7xl"
    :class="revealed ? 'text-5xl' : 'text-6xl'"
  >
    {{ card.word }}
  </p>
  <RevealedAnswer v-if="revealed" :card="card" :focus="focus" />

  <button
    v-if="!revealed"
    type="button"
    class="mt-8 inline-flex items-center gap-2 rounded-full border border-border bg-bg-elevated px-5 py-2 text-sm font-medium text-fg-muted transition-colors hover:bg-bg-sunken hover:text-fg"
    @click="emit('reveal')"
  >
    Show answer
    <span class="font-mono text-[9px] uppercase tracking-wider opacity-70">
      (space)
    </span>
  </button>
</template>
