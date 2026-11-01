<script setup lang="ts">
/**
 * The popover's two foldouts for a CJK word: measure words and character
 * parts, and stroke order. Stroke order collapses for each new word (the
 * hanzi-writer chunk only loads on expand); the details foldout stays as
 * the user left it (`detailsOpen`, held by the popover).
 */
import { ref, watch } from "vue";

import type { WordInfo } from "@/api/types";

import StrokeOrder from "./StrokeOrder.vue";
import WordDetails from "./WordDetails.vue";

const props = defineProps<{
  word: WordInfo;
}>();

const detailsOpen = defineModel<boolean>("detailsOpen", { required: true });

const strokeOrderOpen = ref(false);
watch(
  () => props.word,
  () => {
    strokeOrderOpen.value = false;
  },
);
</script>

<template>
  <div class="mt-4 border-t border-border-subtle pt-3">
    <button
      type="button"
      class="flex w-full items-center justify-between text-fg-muted transition-colors hover:text-fg"
      :aria-expanded="detailsOpen"
      @click="detailsOpen = !detailsOpen"
    >
      <span class="font-mono text-[10px] uppercase tracking-wider">
        Characters &amp; measure word
      </span>
      <svg
        width="10"
        height="10"
        viewBox="0 0 10 10"
        fill="none"
        class="transition-transform"
        :class="{ 'rotate-90': detailsOpen }"
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
    <WordDetails v-if="detailsOpen" :word="word.text" class="mt-3" />
  </div>

  <div class="mt-4 border-t border-border-subtle pt-3">
    <button
      type="button"
      class="flex w-full items-center justify-between text-fg-muted transition-colors hover:text-fg"
      :aria-expanded="strokeOrderOpen"
      @click="strokeOrderOpen = !strokeOrderOpen"
    >
      <span class="font-mono text-[10px] uppercase tracking-wider">
        Stroke order
      </span>
      <svg
        width="10"
        height="10"
        viewBox="0 0 10 10"
        fill="none"
        class="transition-transform"
        :class="{ 'rotate-90': strokeOrderOpen }"
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
    <div v-if="strokeOrderOpen" class="mt-3">
      <StrokeOrder :chars="word.text" />
    </div>
  </div>
</template>
