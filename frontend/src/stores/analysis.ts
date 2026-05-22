import { defineStore } from "pinia";
import { computed, ref } from "vue";

import * as api from "@/api/client";
import type { AnalysisResponse } from "@/api/types";

export const useAnalysisStore = defineStore("analysis", () => {
  const inputText = ref("");
  const result = ref<AnalysisResponse | null>(null);
  const loading = ref(false);
  const error = ref<string | null>(null);
  /**
   * Backend id of the saved-text record this analysis represents. Set when
   * `loadSaved()` is called from the library; null when the user is reading
   * a fresh analysis they haven't saved yet (so we don't try to PATCH).
   */
  const savedTextId = ref<number | null>(null);
  /**
   * 0..1 fraction — last-known reading progress for the loaded saved text.
   * Used by ReaderView to restore scroll position after the article renders.
   */
  const initialProgress = ref<number>(0);
  let activeRequest: AbortController | null = null;

  const hasResult = computed(() => result.value !== null);

  async function analyze(text: string) {
    inputText.value = text;
    error.value = null;
    if (!text.trim()) {
      result.value = null;
      return;
    }

    // Cancel any in-flight analysis so the UI never shows stale results.
    if (activeRequest) activeRequest.abort();
    activeRequest = new AbortController();

    loading.value = true;
    try {
      result.value = await api.analyze(text, activeRequest.signal);
      // A fresh analysis isn't a saved record yet.
      savedTextId.value = null;
      initialProgress.value = 0;
    } catch (e) {
      if (e instanceof DOMException && e.name === "AbortError") return;
      error.value = e instanceof Error ? e.message : "Analysis failed";
      throw e;
    } finally {
      loading.value = false;
    }
  }

  function reset() {
    inputText.value = "";
    result.value = null;
    error.value = null;
    savedTextId.value = null;
    initialProgress.value = 0;
  }

  /**
   * Hydrate the store from a previously-saved text without re-hitting
   * /api/analyze. Used when opening a saved text from the library so the
   * reader matches what the user actually saved.
   */
  function loadSaved(
    text: string,
    data: AnalysisResponse,
    options: { id: number; progress?: number } | null = null,
  ) {
    if (activeRequest) activeRequest.abort();
    inputText.value = text;
    result.value = data;
    error.value = null;
    loading.value = false;
    savedTextId.value = options?.id ?? null;
    initialProgress.value = Math.max(0, Math.min(1, options?.progress ?? 0));
  }

  /** Mark the current analysis as saved (called by ReaderView after POST /save). */
  function adoptSavedId(id: number) {
    savedTextId.value = id;
  }

  return {
    inputText,
    result,
    loading,
    error,
    savedTextId,
    initialProgress,
    hasResult,
    analyze,
    reset,
    loadSaved,
    adoptSavedId,
  };
});
