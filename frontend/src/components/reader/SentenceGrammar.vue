<script setup lang="ts">
/**
 * "Explain grammar" under a sentence's translation: how the sentence is
 * built, a word-by-word gloss, and the grammar points it uses (links to
 * the grammar section). Asked from the server's LLM on demand; the button
 * only shows on servers that offer it.
 */
import { computed, ref } from "vue";
import { RouterLink } from "vue-router";

import * as api from "@/api/client";
import type { SentenceGrammar } from "@/api/client";
import { useAuthStore } from "@/stores/auth";
import { useCapabilitiesStore } from "@/stores/capabilities";

const props = defineProps<{ text: string }>();

const auth = useAuthStore();
const capabilities = useCapabilitiesStore();
const available = computed(() => auth.isAuthed && capabilities.llmFeature("explain_sentence"));

const data = ref<SentenceGrammar | null>(null);
const loading = ref(false);
const error = ref<string | null>(null);

async function explain() {
  if (loading.value) return;
  loading.value = true;
  error.value = null;
  try {
    data.value = await api.explainSentence(props.text);
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Couldn't explain this sentence.";
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <div v-if="available" class="mt-2" @click.stop>
    <button
      v-if="!data"
      type="button"
      class="inline-flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-wider text-accent hover:underline disabled:opacity-50"
      :disabled="loading"
      @click="explain"
    >
      <span
        v-if="loading"
        class="inline-block size-3 animate-spin rounded-full border-2 border-current border-t-transparent"
      />
      {{ loading ? "Explaining…" : "Explain grammar" }}
    </button>
    <p v-if="error" class="text-xs text-red-700 dark:text-red-300">{{ error }}</p>
    <div v-if="data" class="space-y-2 rounded-md bg-bg-sunken/60 px-3 py-2 text-sm">
      <!-- Pinyin over every Chinese word the explanation quotes. -->
      <p v-if="data.breakdown_parts?.length" class="leading-[2.1] text-fg">
        <template v-for="(part, i) in data.breakdown_parts" :key="i">
          <ruby v-if="part.pinyin" class="text-cn-serif">
            {{ part.text }}<rt class="text-[10px] font-sans text-fg-muted">{{ part.pinyin }}</rt>
          </ruby>
          <template v-else>{{ part.text }}</template>
        </template>
      </p>
      <p v-else class="text-fg">{{ data.breakdown }}</p>
      <p v-if="data.literal" class="text-xs italic text-fg-muted">{{ data.literal }}</p>
      <ul v-if="data.points.length" class="flex flex-wrap gap-1.5">
        <li v-for="p in data.points" :key="p.id">
          <RouterLink
            :to="`/grammar/${p.id}`"
            class="inline-flex items-baseline gap-1 rounded-full border border-accent/40 px-2 py-0.5 text-xs text-fg hover:border-accent"
            :title="p.span"
          >
            <span class="font-mono text-[9px] text-fg-subtle">HSK {{ p.level }}</span>
            {{ p.title }}
          </RouterLink>
        </li>
      </ul>
    </div>
  </div>
</template>
