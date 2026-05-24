<script setup lang="ts">
/**
 * Read-only public view for a shared text. No auth required. Reuses
 * ReadingText for layout consistency; word-state buttons and bulk
 * actions remain hidden because the viewer isn't authed.
 *
 * Route: /s/:token
 */
import { computed, onMounted, ref } from "vue";

import * as api from "@/api/client";
import type { PublicSharedText } from "@/api/client";
import ReadingText from "@/components/reader/ReadingText.vue";
import WordPopover from "@/components/reader/WordPopover.vue";

const props = defineProps<{ token: string }>();

const loading = ref(true);
const error = ref<string | null>(null);
const data = ref<PublicSharedText | null>(null);

const characterCount = computed(() => data.value?.content.length ?? 0);
const wordCount = computed(() =>
  data.value
    ? Array.from(data.value.content).filter((c) => /[一-鿿]/.test(c)).length
    : 0,
);

onMounted(async () => {
  try {
    data.value = await api.fetchSharedText(props.token);
  } catch (e) {
    error.value =
      e instanceof Error ? e.message : "Couldn't load that shared text.";
  } finally {
    loading.value = false;
  }
});
</script>

<template>
  <section class="mx-auto max-w-3xl px-4 py-10 sm:px-6 sm:py-14">
    <header class="mb-6">
      <p class="font-mono text-[11px] uppercase tracking-[0.22em] text-fg-subtle">
        Shared text
      </p>
      <h1
        v-if="data?.title"
        class="text-cn-serif mt-1 font-display text-3xl font-medium leading-snug text-fg sm:text-4xl"
      >
        {{ data.title }}
      </h1>
      <p
        v-if="data"
        class="mt-3 font-mono text-[10px] uppercase tracking-wider text-fg-subtle"
      >
        {{ characterCount.toLocaleString() }} chars ·
        {{ wordCount.toLocaleString() }} hanzi
      </p>
    </header>

    <div
      v-if="loading"
      class="flex items-center justify-center py-16"
      role="status"
    >
      <span
        class="inline-block size-6 animate-spin rounded-full border-2 border-fg-muted border-t-transparent"
        aria-hidden="true"
      />
    </div>

    <div
      v-else-if="error"
      class="rounded-md border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-800 dark:border-red-900 dark:bg-red-950/40 dark:text-red-200"
    >
      {{ error }}
    </div>

    <article
      v-else-if="data?.analysisData"
      class="relative"
    >
      <ReadingText :analysis="data.analysisData" />
    </article>

    <p
      v-else-if="data"
      class="text-cn-serif text-base text-fg whitespace-pre-line"
    >
      {{ data.content }}
    </p>

    <!-- WordPopover still works for anonymous viewers — pinyin / meaning are
         in the analysis payload; the "Learning / I know this" buttons hide
         themselves when the viewer isn't authed. -->
    <WordPopover />
  </section>
</template>
