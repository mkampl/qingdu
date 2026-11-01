<script setup lang="ts">
/**
 * The word's meanings in the popover. A pill names the user's glossary
 * when one overrode the meaning. With tagged glosses (the word was
 * clicked in a package context) each shows its provenance chip, so
 * dictionary and package meanings sit side by side; otherwise the flat
 * meaning + meanings list.
 */
import type { WordInfo } from "@/api/types";
import GlossChip from "@/components/ui/GlossChip.vue";

import WordReadings from "./WordReadings.vue";

defineProps<{
  word: WordInfo;
}>();
</script>

<template>
  <div
    v-if="word.glossary_source"
    class="mt-3 inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 font-mono text-[10px] uppercase tracking-wider"
    :style="{
      backgroundColor: 'color-mix(in oklch, var(--color-glossary), transparent 80%)',
      color: 'var(--color-glossary)',
    }"
    :title="`From your glossary list “${word.glossary_source}”`"
  >
    <svg width="9" height="9" viewBox="0 0 9 9" fill="none" aria-hidden="true">
      <path
        d="M1.5 1.5h6M1.5 4h6M1.5 6.5h4"
        stroke="currentColor"
        stroke-width="1.4"
        stroke-linecap="round"
      />
    </svg>
    {{ word.glossary_source }}
  </div>

  <div v-if="word.user_glosses && word.user_glosses.length" class="mt-4 space-y-2">
    <div v-for="(g, i) in word.user_glosses" :key="i" class="flex items-start gap-2">
      <GlossChip :gloss="g" class="mt-0.5" />
      <p class="font-display text-[14px] leading-snug text-fg">
        {{ g.meaning }}
      </p>
    </div>
  </div>
  <WordReadings
    v-else-if="word.meaning || word.meanings?.length"
    class="mt-4"
    :meaning="word.meaning"
    :meanings="word.meanings"
    :meaning-tags="word.meaning_tags"
    :readings="word.readings"
    list-class="mt-1 list-inside space-y-0.5 text-xs text-fg-muted"
  />
</template>
