<script setup lang="ts">
/**
 * How readable the open text is for the signed-in user: the share of
 * running words they know, how much more counts once the words in review
 * are learned, and how many missing words stand between them and the
 * 95 % that makes a text comfortable to read. Counted by the server
 * (POST /api/readability) and refreshed whenever a word state changes.
 */
import { computed, onBeforeUnmount, ref, watch } from "vue";

import * as api from "@/api/client";
import type { ReadabilityResponse } from "@/api/client";
import PrelearnModal from "@/components/reader/PrelearnModal.vue";
import { useAnalysisStore } from "@/stores/analysis";
import { useAuthStore } from "@/stores/auth";
import { useUserWordsStore } from "@/stores/userWords";

const props = defineProps<{
  /** Names the text for its pre-learned words (utils/text-key). */
  textKey: string;
  /** Shown as the context sentence's source on the review cards. */
  title: string | null;
}>();

const analysis = useAnalysisStore();
const auth = useAuthStore();
const userWords = useUserWordsStore();

const data = ref<ReadabilityResponse | null>(null);
const prelearnOpen = ref(false);
let seq = 0;
let timer: ReturnType<typeof setTimeout> | null = null;

const tokens = computed(() => analysis.result?.words.map((w) => w.text) ?? []);
// Package and glossary terms count as words even outside the dictionary.
const extra = computed(() =>
  (analysis.result?.words ?? [])
    .filter(
      (w) =>
        w.translation_source === "package" ||
        w.translation_source === "glossary",
    )
    .map((w) => w.text),
);

async function load() {
  if (!auth.isAuthed || !tokens.value.length) {
    data.value = null;
    return;
  }
  const mine = ++seq;
  try {
    const r = await api.getReadability(tokens.value, extra.value, props.textKey);
    if (mine === seq) data.value = r;
  } catch {
    if (mine === seq) data.value = null;
  }
}

function schedule(delay = 600) {
  if (timer) clearTimeout(timer);
  timer = setTimeout(() => void load(), delay);
}

watch(
  () => [analysis.result, auth.isAuthed, props.textKey] as const,
  () => schedule(0),
  { immediate: true },
);
// Marking a word in the text changes what the user knows. Skipped while
// the pre-learn dialog writes states itself and hands back the result.
watch(
  () => userWords.states,
  () => {
    if (!prelearnOpen.value) schedule();
  },
);

function onPrelearned(r: ReadabilityResponse) {
  if (timer) clearTimeout(timer);
  seq++;
  data.value = r;
}
onBeforeUnmount(() => {
  if (timer) clearTimeout(timer);
});

const pct = (x: number) => Math.floor(x * 100);
const knownWidth = computed(() => `${(data.value?.known_pct ?? 0) * 100}%`);
const progressWidth = computed(() => {
  const d = data.value;
  return d ? `${(d.with_progress_pct - d.known_pct) * 100}%` : "0%";
});
const thresholdLeft = computed(() => `${(data.value?.threshold ?? 0.95) * 100}%`);
const showProgress = computed(
  () => !!data.value && data.value.in_progress > 0,
);

defineExpose({ refresh: load, data });
</script>

<template>
  <section
    v-if="data && data.total > 0"
    class="mb-6 rounded-lg border border-border-subtle bg-bg-elevated px-4 py-3"
    aria-label="How readable this text is for you"
  >
    <div class="flex flex-wrap items-baseline gap-x-3 gap-y-1">
      <p class="text-sm text-fg">
        You know
        <span class="font-display text-lg font-medium">{{ pct(data.known_pct) }}%</span>
        of this text
      </p>
      <p v-if="showProgress" class="text-xs text-fg-muted">
        {{ pct(data.with_progress_pct) }}% with the words in review
      </p>
      <span
        v-if="data.unlocked"
        class="inline-flex items-center gap-1 rounded-full bg-emerald-500/15 px-2.5 py-0.5 font-mono text-[10px] uppercase tracking-wider text-emerald-600 dark:text-emerald-400"
      >
        <svg width="10" height="10" viewBox="0 0 12 12" fill="none" aria-hidden="true">
          <path
            d="M2 6.5l2.5 2.5L10 3"
            stroke="currentColor"
            stroke-width="1.6"
            stroke-linecap="round"
            stroke-linejoin="round"
          />
        </svg>
        Readable
      </span>
    </div>

    <div
      class="relative mt-2 h-1.5 overflow-hidden rounded-full bg-bg-sunken"
      role="progressbar"
      :aria-valuenow="pct(data.known_pct)"
      aria-valuemin="0"
      aria-valuemax="100"
    >
      <div class="absolute inset-y-0 left-0 flex w-full">
        <div class="h-full bg-accent" :style="{ width: knownWidth }" />
        <div class="h-full bg-accent/35" :style="{ width: progressWidth }" />
      </div>
      <div
        class="absolute inset-y-0 w-px bg-fg-muted"
        :style="{ left: thresholdLeft }"
        aria-hidden="true"
      />
    </div>

    <p v-if="!data.unlocked" class="mt-2 text-xs text-fg-muted">
      <template v-if="data.to_unlock > 0">
        Learn
        <span class="font-medium text-fg">{{ data.to_unlock }}</span>
        more word{{ data.to_unlock === 1 ? "" : "s" }} to read it comfortably
        ({{ pct(data.threshold) }}%).
      </template>
      <template v-else>
        Readable once the words in review are learned.
      </template>
    </p>
    <div class="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1">
      <button
        v-if="data.missing_count > 0"
        type="button"
        class="rounded-full border border-accent px-2.5 py-1 font-mono text-[10px] uppercase tracking-wider text-accent transition-colors hover:bg-accent/10"
        @click="prelearnOpen = true"
      >
        Pre-learn missing words
      </button>
      <p
        v-if="data.prelearned && data.prelearned.total"
        class="text-xs text-fg-muted"
      >
        {{ data.prelearned.total }} pre-learned for this text ·
        {{ data.prelearned.learned }} learned so far
      </p>
    </div>
    <PrelearnModal
      :open="prelearnOpen"
      :data="data"
      :words="analysis.result?.words ?? []"
      :text-key="textKey"
      :title="title"
      :source-text-id="analysis.savedTextId"
      :library-slug="analysis.librarySlug"
      @close="prelearnOpen = false"
      @done="onPrelearned"
    />
  </section>
</template>
