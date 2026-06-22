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
 */
export const useVocabListsStore = defineStore("vocabLists", () => {
  const lists = ref<VocabularyListSummary[]>([]);
  const loading = ref(false);
  const error = ref<string | null>(null);
  const loadedAt = ref<number | null>(null);

  const isEmpty = computed(() => lists.value.length === 0);

  async function ensureLoaded(force = false): Promise<void> {
    if (loading.value) return;
    if (loadedAt.value !== null && !force) return;
    // Anonymous users can't see lists — skip the call so we don't log
    // a 401 every time the Reader's popover / glossary picker mounts.
    if (!useAuthStore().isAuthed) return;
    loading.value = true;
    error.value = null;
    try {
      lists.value = await api.listVocabularyLists();
      loadedAt.value = Date.now();
    } catch (e) {
      error.value =
        e instanceof ApiError ? e.message : "Couldn't load your vocab lists.";
    } finally {
      loading.value = false;
    }
  }

  /** Drop the cache — call this on auth change or after creating/deleting a list. */
  function invalidate() {
    lists.value = [];
    loadedAt.value = null;
    error.value = null;
  }

  return { lists, loading, error, loadedAt, isEmpty, ensureLoaded, invalidate };
});
