<script setup lang="ts">
/**
 * Read-only public view for a shared text. No auth required. Reuses
 * the same chrome as the authed reader — TOC sidebar, stats panel,
 * grammar panel — except the save/share controls in StatsPanel are
 * hidden (the viewer can't save someone else's text into their own
 * library from this surface).
 *
 * The analysis store gets populated with the share data on mount so
 * that the reader's curated-sentence-translation lookup (Phase #100)
 * hits — without this, package-imported texts would fall through to
 * /api/translate even though the curated translations rode along in
 * `analysisData.sentence_translations`.
 *
 * Route: /s/:token
 */
import { computed, onBeforeUnmount, onMounted, ref } from "vue";

import * as api from "@/api/client";
import type { PublicSharedText } from "@/api/client";
import GrammarPanel from "@/components/reader/GrammarPanel.vue";
import ReadingText from "@/components/reader/ReadingText.vue";
import StatsPanel from "@/components/reader/StatsPanel.vue";
import TocSidebar from "@/components/reader/TocSidebar.vue";
import type { Section } from "@/components/reader/utils";
import WordPopover from "@/components/reader/WordPopover.vue";
import { useAnalysisStore } from "@/stores/analysis";
import { useReaderStore } from "@/stores/reader";

const props = defineProps<{ token: string }>();

const analysis = useAnalysisStore();
const reader = useReaderStore();

const loading = ref(true);
const error = ref<string | null>(null);
const data = ref<PublicSharedText | null>(null);
const sections = ref<Section[]>([]);
const articleRef = ref<HTMLElement | null>(null);

const characterCount = computed(() => data.value?.content.length ?? 0);
const wordCount = computed(() =>
  data.value
    ? Array.from(data.value.content).filter((c) => /[一-鿿]/.test(c)).length
    : 0,
);

onMounted(async () => {
  try {
    const fetched = await api.fetchSharedText(props.token);
    data.value = fetched;
    if (fetched.analysisData) {
      // Hydrate the analysis store so the reader's curated-translation
      // lookup (Phase #100) and the grammar / stats panels all have a
      // single source of truth — same shape the authed reader uses.
      analysis.loadSaved(fetched.content, fetched.analysisData);
    }
  } catch (e) {
    error.value =
      e instanceof Error ? e.message : "Couldn't load that shared text.";
  } finally {
    loading.value = false;
  }
});

// Clear the analysis store on unmount so that navigating back to the
// regular reader (in the same tab) doesn't see leftover shared data.
onBeforeUnmount(() => {
  analysis.reset();
  reader.reset();
});
</script>

<template>
  <section
    class="mx-auto grid max-w-6xl grid-cols-1 gap-x-12 gap-y-8 px-5 pt-10 pb-24 sm:px-8 md:grid-cols-[1fr_320px] md:pt-14 lg:px-10"
  >
    <div>
      <header class="mb-6">
        <p
          class="font-mono text-[11px] uppercase tracking-[0.22em] text-fg-subtle"
        >
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

      <article v-else-if="data?.analysisData" ref="articleRef" class="relative">
        <ReadingText
          :analysis="data.analysisData"
          @sections="(s) => (sections = s)"
        />
      </article>

      <p
        v-else-if="data"
        class="text-cn-serif text-base text-fg whitespace-pre-line"
      >
        {{ data.content }}
      </p>
    </div>

    <!-- Right sidebar — same composition as the authed reader, but the
         StatsPanel save section is hidden via show-save=false. -->
    <aside
      v-if="data?.analysisData"
      class="md:sticky md:top-6 md:self-start md:max-h-[calc(100vh-3rem)] md:overflow-y-auto md:pr-1 scrollbar-quiet space-y-8"
    >
      <TocSidebar
        v-if="sections.length"
        :sections="sections"
        :article-el="articleRef"
      />

      <StatsPanel
        :statistics="data.analysisData.statistics"
        :words="data.analysisData.words"
        :show-save="false"
      />

      <GrammarPanel :grammar="data.analysisData.grammar" />
    </aside>

    <!-- Word info popover, mounted at the body root via Teleport. -->
    <WordPopover />
  </section>
</template>
