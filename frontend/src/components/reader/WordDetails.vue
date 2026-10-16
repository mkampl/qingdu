<script setup lang="ts">
/**
 * A word's measure words (一本书) and what its characters are made of
 * (好 = 女 woman + 子 son, "A woman with a son"). Loaded on demand from
 * GET /api/vocab/details; shown in the word popover and on review cards.
 */
import { computed, ref, watch } from "vue";

import * as api from "@/api/client";
import type { WordDetails } from "@/api/client";

const props = defineProps<{ word: string }>();

// Details don't change while the app runs: one request per word.
const cache = new Map<string, Promise<WordDetails | null>>();

function fetchDetails(word: string): Promise<WordDetails | null> {
  let p = cache.get(word);
  if (!p) {
    p = api.getWordDetails(word).catch(() => null);
    cache.set(word, p);
  }
  return p;
}

const data = ref<WordDetails | null>(null);
watch(
  () => props.word,
  async (word) => {
    data.value = null;
    if (!word || !/[㐀-鿿]/.test(word)) return;
    const d = await fetchDetails(word);
    if (props.word === word) data.value = d;
  },
  { immediate: true },
);

/** First sense only: "woman, girl; female" -> "woman". */
function short(def: string | null): string {
  return (def ?? "").split(/[;,]/)[0].trim();
}

// Characters worth explaining: those with parts or a hint.
const chars = computed(() =>
  (data.value?.characters ?? []).filter((c) => c.parts.length || c.hint),
);
const hasAny = computed(() => !!data.value && (data.value.classifiers.length > 0 || chars.value.length > 0));
</script>

<template>
  <div v-if="hasAny && data" class="space-y-2 text-left text-sm">
    <p v-if="data.classifiers.length" class="text-fg-muted">
      <span class="mr-1 font-mono text-[10px] uppercase tracking-wider text-fg-subtle">
        Measure word
      </span>
      <template v-for="(c, i) in data.classifiers" :key="c.hanzi">
        <span v-if="i" class="text-fg-subtle"> · </span>
        <span class="text-cn-serif text-fg">一{{ c.hanzi }}{{ data.word }}</span>
        <span class="text-xs"> {{ c.pinyin }}</span>
      </template>
    </p>
    <ul v-if="chars.length" class="space-y-1.5">
      <li v-for="c in chars" :key="c.char" class="leading-snug">
        <span class="text-cn-serif text-lg text-fg">{{ c.char }}</span>
        <template v-if="c.parts.length">
          <span class="text-fg-subtle"> = </span>
          <template v-for="(p, i) in c.parts" :key="p.char">
            <span v-if="i" class="text-fg-subtle"> + </span>
            <span class="inline-flex items-baseline gap-1 rounded bg-bg-sunken px-1.5 py-0.5">
              <span class="text-cn-serif text-fg">{{ p.char }}</span>
              <span v-if="short(p.definition)" class="text-xs text-fg-muted">{{ short(p.definition) }}</span>
            </span>
          </template>
        </template>
        <span v-if="c.hint" class="mt-0.5 block text-xs italic text-fg-muted">{{ c.hint }}</span>
      </li>
    </ul>
  </div>
</template>
