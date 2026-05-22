import { defineStore } from "pinia";
import { computed, ref } from "vue";

import * as api from "@/api/client";
import type { AnalysisResponse } from "@/api/types";

export const useAnalysisStore = defineStore("analysis", () => {
  const inputText = ref("");
  const result = ref<AnalysisResponse | null>(null);
  const loading = ref(false);
  const error = ref<string | null>(null);
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
  }

  return {
    inputText,
    result,
    loading,
    error,
    hasResult,
    analyze,
    reset,
  };
});
