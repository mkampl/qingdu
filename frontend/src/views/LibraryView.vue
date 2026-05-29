<script setup lang="ts">
/**
 * Library: the full bundled HSK 1-9 reading collection. Anonymous-readable.
 * Filterable by HSK band + free-text search across title/topic; the For-You
 * personalisation lives in DiscoverView and depends on auth + a non-empty
 * known-word set, which this page intentionally does not require.
 */

import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";

import * as api from "@/api/client";
import type { LibraryManifestItem } from "@/api/client";
import type { AnalysisResponse } from "@/api/types";
import { useAnalysisStore } from "@/stores/analysis";
import { useToastStore } from "@/stores/toast";

const analysis = useAnalysisStore();
const toast = useToastStore();
const router = useRouter();

const items = ref<LibraryManifestItem[]>([]);
const loading = ref(false);
const error = ref<string | null>(null);

const selectedLevels = ref<Set<number>>(new Set());
const search = ref("");
const sortKey = ref<"hsk" | "chars-asc" | "chars-desc">("hsk");

onMounted(async () => {
  loading.value = true;
  try {
    const r = await api.listLibrary();
    items.value = r.items;
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Couldn't load library";
  } finally {
    loading.value = false;
  }
});

function toggleLevel(n: number) {
  const next = new Set(selectedLevels.value);
  if (next.has(n)) next.delete(n);
  else next.add(n);
  selectedLevels.value = next;
}

function clearLevels() {
  selectedLevels.value = new Set();
}

const filtered = computed(() => {
  const term = search.value.trim().toLowerCase();
  let list = items.value.filter((it) => {
    if (selectedLevels.value.size && !selectedLevels.value.has(it.hsk_level)) {
      return false;
    }
    if (
      term &&
      !it.title.toLowerCase().includes(term) &&
      !it.topic.toLowerCase().includes(term)
    ) {
      return false;
    }
    return true;
  });
  if (sortKey.value === "hsk") {
    list = list.slice().sort((a, b) => a.hsk_level - b.hsk_level || a.slug.localeCompare(b.slug));
  } else if (sortKey.value === "chars-asc") {
    list = list.slice().sort((a, b) => a.char_count - b.char_count);
  } else {
    list = list.slice().sort((a, b) => b.char_count - a.char_count);
  }
  return list;
});

const countByLevel = computed(() => {
  const c: Record<number, number> = {};
  for (const it of items.value) c[it.hsk_level] = (c[it.hsk_level] ?? 0) + 1;
  return c;
});

async function open(slug: string) {
  try {
    const entry = await api.getLibraryEntry(slug);
    analysis.loadSaved(entry.text, entry.analyzed as AnalysisResponse, null);
    router.push("/");
  } catch (e) {
    toast.error(e instanceof Error ? e.message : "Couldn't open that text");
  }
}
</script>

<template>
  <section class="mx-auto max-w-6xl px-5 py-10 sm:px-8 md:py-14 lg:px-10">
    <header class="mb-10 flex items-baseline justify-between gap-4">
      <div class="flex items-baseline gap-3">
        <span
          class="font-mono text-[11px] font-medium uppercase tracking-[0.22em] text-fg-subtle"
        >
          Library
        </span>
        <span class="h-px w-12 bg-border-subtle" aria-hidden="true" />
        <h1
          class="font-display text-2xl font-medium tracking-tight text-fg sm:text-3xl"
        >
          Bundled reading texts
        </h1>
      </div>
    </header>

    <p class="mb-8 max-w-prose text-sm leading-relaxed text-fg-muted">
      180 short texts, 20 per HSK level, written to demonstrate the
      vocabulary and grammar of each level. Click one to open it in the
      reader. No login required to browse — sign in to track progress and
      get personalised recommendations on
      <RouterLink to="/discover" class="font-medium text-accent hover:underline">
        Discover
      </RouterLink>.
    </p>

    <!-- Filter bar -->
    <div class="mb-8 flex flex-wrap items-center gap-3">
      <button
        type="button"
        :class="[
          'rounded-full border px-3 py-1 font-mono text-[11px] uppercase tracking-wider transition-colors',
          selectedLevels.size === 0
            ? 'border-accent bg-accent/10 text-accent'
            : 'border-border bg-bg-elevated text-fg-muted hover:text-fg',
        ]"
        @click="clearLevels"
      >
        All
      </button>
      <button
        v-for="n in 9"
        :key="n"
        type="button"
        :class="[
          'rounded-full border px-3 py-1 font-mono text-[11px] uppercase tracking-wider transition-colors',
          selectedLevels.has(n)
            ? 'border-accent bg-accent/10 text-accent'
            : 'border-border bg-bg-elevated text-fg-muted hover:text-fg',
        ]"
        @click="toggleLevel(n)"
      >
        HSK {{ n }}
        <span class="ml-1 text-fg-subtle">{{ countByLevel[n] || 0 }}</span>
      </button>
      <div class="flex-1" />
      <input
        v-model="search"
        type="search"
        placeholder="Search title or topic"
        class="w-48 rounded-md border border-border bg-bg-elevated px-3 py-1.5 text-sm placeholder:text-fg-subtle focus:border-accent focus:outline-none"
      />
      <select
        v-model="sortKey"
        class="rounded-md border border-border bg-bg-elevated px-3 py-1.5 text-sm focus:border-accent focus:outline-none"
      >
        <option value="hsk">Sort: HSK level</option>
        <option value="chars-asc">Sort: shortest first</option>
        <option value="chars-desc">Sort: longest first</option>
      </select>
    </div>

    <p v-if="loading" class="py-12 text-center text-sm text-fg-subtle">
      Loading…
    </p>
    <p v-else-if="error" class="py-12 text-center text-sm text-rose-600">
      {{ error }}
    </p>
    <p
      v-else-if="filtered.length === 0"
      class="py-12 text-center text-sm text-fg-subtle"
    >
      Nothing matches. Try clearing the filters.
    </p>
    <ul
      v-else
      class="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3"
    >
      <li v-for="item in filtered" :key="item.slug">
        <button
          type="button"
          class="group flex h-full w-full flex-col gap-2 rounded-lg border border-border bg-bg-elevated p-4 text-left transition-shadow hover:shadow-md"
          @click="open(item.slug)"
        >
          <div class="flex items-start justify-between gap-2">
            <p
              class="text-cn-serif text-base font-medium leading-snug text-fg group-hover:text-accent"
            >
              {{ item.title }}
            </p>
            <span
              class="shrink-0 rounded-full bg-accent/15 px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider text-accent"
            >
              HSK {{ item.hsk_level }}
            </span>
          </div>
          <p class="font-display text-[11px] italic text-fg-subtle">
            {{ item.topic.replace(/-/g, " ") }}
          </p>
          <div class="mt-auto flex items-center gap-2 pt-2">
            <span
              class="rounded-full bg-bg-sunken px-2 py-0.5 font-mono text-[10px] tracking-wider text-fg-muted"
            >
              {{ item.char_count }} 字
            </span>
            <span
              class="rounded-full bg-bg-sunken px-2 py-0.5 font-mono text-[10px] tracking-wider text-fg-muted"
            >
              {{ item.total_unique_words }} unique
            </span>
            <span
              v-if="item.grammar_pattern"
              class="rounded-full bg-bg-sunken px-2 py-0.5 font-mono text-[10px] tracking-wider text-fg-muted"
              :title="`Demonstrates grammar pattern: ${item.grammar_pattern}`"
            >
              {{ item.grammar_pattern }}
            </span>
          </div>
        </button>
      </li>
    </ul>
  </section>
</template>
