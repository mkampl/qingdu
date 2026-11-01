<script setup lang="ts">
/**
 * What the word means in the sentence it was clicked in, asked of the LLM
 * on request. Offered only where there is something to choose: several
 * senses or readings, or a meaning from the user's lists next to the
 * dictionary's. The answer is dropped when the word or sentence changes.
 */
import { computed, ref, watch } from "vue";

import * as api from "@/api/client";
import { ApiError } from "@/api/client";
import type { WordInfo } from "@/api/types";
import { useAuthStore } from "@/stores/auth";
import { useCapabilitiesStore } from "@/stores/capabilities";

const props = defineProps<{
  word: WordInfo;
  sentence: string | null;
}>();

const auth = useAuthStore();
const capabilities = useCapabilitiesStore();

const sense = ref<api.WordSense | null>(null);
const loading = ref(false);
const error = ref<string | null>(null);

const canAsk = computed(() => {
  const w = props.word;
  return (
    capabilities.llmFeature("word_sense") &&
    auth.isAuthed &&
    !!w.text &&
    !(w.parts ?? []).length &&
    !!props.sentence?.includes(w.text) &&
    ((w.meanings?.length ?? 0) > 1 ||
      (w.readings?.length ?? 0) > 1 ||
      !!w.glossary_source ||
      (w.user_glosses ?? []).some((g) => g.source !== "dictionary"))
  );
});

watch(
  () => [props.word.text, props.sentence],
  () => {
    sense.value = null;
    error.value = null;
  },
);

async function ask() {
  const w = props.word;
  const sentence = props.sentence;
  if (!sentence || loading.value) return;
  // Meanings the user's lists or a glossary give the word.
  const glosses = (w.user_glosses ?? []).filter((g) => g.source !== "dictionary").map((g) => g.meaning);
  if (w.glossary_source && w.meaning) glosses.push(w.meaning);
  loading.value = true;
  error.value = null;
  try {
    sense.value = await api.getWordSense(w.text, sentence, [...new Set(glosses)].slice(0, 5));
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : "Couldn't ask.";
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <div v-if="canAsk" class="mt-3">
    <div v-if="sense" class="rounded-md border border-accent/40 bg-accent/5 px-3 py-2">
      <p class="font-mono text-[10px] uppercase tracking-wider text-accent">
        In this sentence<template v-if="sense.pinyin"> · {{ sense.pinyin }}</template>
      </p>
      <p class="mt-0.5 font-display text-[14px] leading-snug text-fg">{{ sense.meaning }}</p>
      <p v-if="sense.note" class="mt-1 text-xs text-fg-muted">{{ sense.note }}</p>
    </div>
    <button
      v-else
      type="button"
      class="font-mono text-[10px] uppercase tracking-wider text-fg-subtle hover:text-accent disabled:opacity-60"
      :disabled="loading"
      @click="ask"
    >
      {{ loading ? "Looking…" : "Meaning in this sentence" }}
    </button>
    <p v-if="error" class="mt-1 text-xs text-red-700 dark:text-red-300">{{ error }}</p>
  </div>
</template>
