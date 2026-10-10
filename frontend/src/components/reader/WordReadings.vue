<script setup lang="ts">
/**
 * A word's dictionary meaning: the main reading's headline (with its
 * register badges) and other senses, then, for a polyphone, a smaller
 * "Other readings" section with each further reading's pinyin, gloss,
 * a few senses and a common word that uses it (长 zhǎng, as in 校长).
 *
 * Shared by the reader popover and the review card so a word reads the
 * same in both places. Callers pass sizes through the class props.
 */
import { computed } from "vue";
import type { WordReading } from "@/api/types";
import { otherMeanings } from "@/utils/meanings";
import { otherReadings } from "@/utils/readings";
import MeaningTags from "./MeaningTags.vue";

const props = withDefaults(
  defineProps<{
    meaning?: string | null;
    meanings?: string[] | null;
    meaningTags?: string[] | null;
    readings?: WordReading[] | null;
    /** Cap on the main reading's other senses (default: all). */
    maxMeanings?: number;
    headlineClass?: string;
    listClass?: string;
  }>(),
  {
    meaning: "",
    meanings: () => [],
    meaningTags: () => [],
    readings: null,
    maxMeanings: undefined,
    headlineClass: "font-display text-[15px] leading-snug text-fg",
    listClass: "mt-1 space-y-0.5 text-xs text-fg-muted",
  },
);

const senses = computed(() =>
  otherMeanings(props.meaning, props.meanings, props.maxMeanings),
);
const others = computed(() => otherReadings(props.readings));
</script>

<template>
  <div>
    <p v-if="meaning" :class="headlineClass">
      {{ meaning }}<MeaningTags :tags="meaningTags" />
    </p>
    <ul v-if="senses.length" :class="listClass">
      <li v-for="(m, i) in senses" :key="i">{{ m }}</li>
    </ul>

    <div
      v-if="others.length"
      class="mt-3 border-t border-border-subtle pt-2 text-left"
    >
      <p class="font-mono text-[9px] uppercase tracking-wider text-fg-subtle">
        Other readings
      </p>
      <ul class="mt-1 space-y-1.5">
        <li v-for="r in others" :key="r.pinyin" class="text-xs leading-snug">
          <span class="font-sans text-[13px] text-fg">{{ r.pinyin }}</span>
          <span class="ml-1.5 text-fg-muted">
            {{ r.primary }}<MeaningTags :tags="r.tags" /><template
              v-for="s in r.senses"
              :key="s"
              >; {{ s }}</template
            >
          </span>
          <span v-if="r.example" class="block text-[11px] text-fg-subtle">
            as in
            <span class="font-cn-serif text-[13px] text-fg-muted">{{
              r.example.word
            }}</span>
            {{ r.example.pinyin }} · {{ r.example.meaning }}
          </span>
        </li>
      </ul>
    </div>
  </div>
</template>
