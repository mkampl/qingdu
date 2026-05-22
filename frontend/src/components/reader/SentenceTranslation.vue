<script setup lang="ts">
import { computed } from "vue";

import { useReaderStore } from "@/stores/reader";

const props = defineProps<{ text: string }>();

const reader = useReaderStore();

const state = computed(() => reader.sentenceTranslations.get(props.text));

const sourceLabel = computed(() => {
  if (!state.value || state.value.status !== "ok") return null;
  const source = state.value.data.source;
  if (source === "deepl") return "DeepL";
  if (source === "google") return "Google";
  if (source === "mymemory") return "MyMemory";
  if (source === "cache") return "Cached";
  return source;
});
</script>

<template>
  <div
    class="my-2 ml-3 flex w-full max-w-prose flex-col gap-2 border-l-2 border-accent/40 bg-bg-elevated px-4 py-3 text-sm shadow-[0_1px_0_0_var(--color-border-subtle)] sm:ml-6"
  >
    <!-- Loading -->
    <template v-if="!state || state.status === 'loading'">
      <span
        class="inline-flex items-center gap-2 font-display text-fg-muted italic"
      >
        <span
          class="inline-block size-3 animate-spin rounded-full border-2 border-current border-t-transparent"
        />
        Translating…
      </span>
    </template>

    <!-- Error -->
    <template v-else-if="state.status === 'error'">
      <span class="font-display text-sm italic text-red-700 dark:text-red-300">
        Couldn't translate this sentence — {{ state.message }}.
      </span>
    </template>

    <!-- Result -->
    <template v-else-if="state.status === 'ok'">
      <p class="font-display text-[15px] leading-snug text-fg">
        {{ state.data.translation }}
      </p>
      <div class="flex items-center justify-between gap-3">
        <span
          class="font-mono text-[10px] uppercase tracking-wider text-fg-subtle"
        >
          via {{ sourceLabel }}
        </span>
        <span
          v-if="state.data.cached"
          class="font-mono text-[10px] uppercase tracking-wider text-fg-subtle"
        >
          cached
        </span>
      </div>
    </template>
  </div>
</template>
