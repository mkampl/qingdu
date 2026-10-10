import { defineStore } from "pinia";
import { computed, ref } from "vue";

import * as api from "@/api/client";
import { ApiError } from "@/api/client";
import type { VocabularyListSummary } from "@/api/types";
import { useAuthStore } from "@/stores/auth";

/**
 * Session-scoped cache of the user's vocab lists. Used by the word popover
 * (to show the list picker without re-fetching on every word click) and by
 * the library views (which can call `ensureLoaded()` instead of duplicating
 * loading logic).
 *
 * Stale-while-revalidate: `invalidate()` keeps the current lists on screen
 * and refetches in the background, so the popover / glossary picker never
 * blank out after an edit. Call it after every list mutation (lists,
 * sections, words). `clear()` is the hard reset for logout / user switch.
 */
export const useVocabListsStore = defineStore("vocabLists", () => {
  const lists = ref<VocabularyListSummary[]>([]);
  const fetching = ref(false);
  const error = ref<string | null>(null);
  const loadedAt = ref<number | null>(null);
  const hasLoaded = ref(false);

  // Bumped by invalidate()/clear(); a response from an older generation is
  // dropped so a request started before an edit can't overwrite newer data.
  let generation = 0;
  let inflight: Promise<void> | null = null;
  let inflightGeneration = -1;

  const isEmpty = computed(() => lists.value.length === 0);
  /** True only for the first load — a background refresh keeps the old data. */
  const loading = computed(() => fetching.value && !hasLoaded.value);

  function ensureLoaded(force = false): Promise<void> {
    if (inflight && inflightGeneration === generation) return inflight;
    if (loadedAt.value !== null && !force) return Promise.resolve();
    // Anonymous users can't see lists — skip the call so we don't log
    // a 401 every time the Reader's popover / glossary picker mounts.
    if (!useAuthStore().isAuthed) return Promise.resolve();

    const gen = generation;
    fetching.value = true;
    error.value = null;
    const p = (async () => {
      try {
        const next = await api.listVocabularyLists();
        if (gen !== generation) return;
        lists.value = next;
        loadedAt.value = Date.now();
        hasLoaded.value = true;
      } catch (e) {
        if (gen !== generation) return;
        error.value =
          e instanceof ApiError ? e.message : "Couldn't load your vocab lists.";
      } finally {
        // Only the latest request clears the in-flight marker.
        if (inflightGeneration === gen) {
          inflight = null;
          fetching.value = false;
        }
      }
    })();
    inflight = p;
    inflightGeneration = gen;
    return p;
  }

  /** Mark the cache stale after a mutation and refetch in the background. */
  function invalidate(): Promise<void> {
    generation += 1;
    loadedAt.value = null;
    return ensureLoaded(true);
  }

  /** Drop everything — logout or a different account signing in. */
  function clear() {
    generation += 1;
    inflight = null;
    fetching.value = false;
    lists.value = [];
    loadedAt.value = null;
    hasLoaded.value = false;
    error.value = null;
  }

  return {
    lists,
    loading,
    fetching,
    error,
    loadedAt,
    isEmpty,
    ensureLoaded,
    invalidate,
    clear,
  };
});
