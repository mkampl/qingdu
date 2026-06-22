<script setup lang="ts">
import { computed, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import VocabBrowseView from "@/views/VocabBrowseView.vue";
import VocabListsView from "@/views/VocabListsView.vue";

type Tab = "browse" | "lists";

const route = useRoute();
const router = useRouter();

// Tab is driven by the URL query so deep links and the back button work.
// Default is Browse — the HSK catalog is the more useful entry point for
// new users; existing users who've curated lists can flip to Lists in a tap.
const tab = computed<Tab>(() =>
  route.query.tab === "lists" ? "lists" : "browse",
);

function setTab(next: Tab) {
  void router.replace({ query: { ...route.query, tab: next } });
}

// Keep the URL canonical — if someone hits /vocab without a query, stamp
// ?tab=browse so refresh / share preserves state.
watch(
  () => route.query.tab,
  (current) => {
    if (current !== "browse" && current !== "lists") {
      void router.replace({ query: { ...route.query, tab: "browse" } });
    }
  },
  { immediate: true },
);
</script>

<template>
  <section class="mx-auto max-w-6xl px-4 py-6 sm:px-8 sm:py-10 md:py-14 lg:px-10">
    <header class="mb-5 sm:mb-10">
      <div class="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span
          class="font-mono text-[11px] uppercase tracking-[0.22em] text-fg-subtle"
        >
          Vocabulary
        </span>
        <h1 class="font-display text-xl font-medium tracking-tight text-fg sm:text-2xl">
          {{ tab === "browse" ? "Browse HSK" : "My lists" }}
        </h1>
      </div>

      <!-- Tab switcher. Stays in the header so it's the first thing the
           user sees; tab state lives in the URL so reload + share work. -->
      <div
        role="tablist"
        aria-label="Vocabulary section"
        class="mt-4 inline-flex rounded-full border border-border-subtle bg-bg-elevated p-1"
      >
        <button
          type="button"
          role="tab"
          :aria-selected="tab === 'browse'"
          class="rounded-full px-3 py-1 text-xs font-medium transition-colors sm:px-4 sm:py-1.5 sm:text-sm"
          :class="
            tab === 'browse'
              ? 'bg-bg-sunken text-fg'
              : 'text-fg-muted hover:text-fg'
          "
          @click="setTab('browse')"
        >
          HSK browse
        </button>
        <button
          type="button"
          role="tab"
          :aria-selected="tab === 'lists'"
          class="rounded-full px-3 py-1 text-xs font-medium transition-colors sm:px-4 sm:py-1.5 sm:text-sm"
          :class="
            tab === 'lists'
              ? 'bg-bg-sunken text-fg'
              : 'text-fg-muted hover:text-fg'
          "
          @click="setTab('lists')"
        >
          My lists
        </button>
      </div>
    </header>

    <VocabBrowseView v-if="tab === 'browse'" />
    <VocabListsView v-else />
  </section>
</template>
