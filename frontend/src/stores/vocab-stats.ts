import { defineStore } from "pinia";
import { ref } from "vue";

import * as api from "@/api/client";

/**
 * Tracks /api/vocabulary-stats. Used by the reader to show a "Loading
 * vocabulary…" state instead of an opaque 503 when the user clicks Analyze
 * during the backend's cold-start window (vocab download + jieba init).
 *
 * Cheap polling: starts on mount, stops once the backend reports ready,
 * and won't churn after that. Network failures are non-fatal — we just keep
 * the last-known state.
 */
export const useVocabStatsStore = defineStore("vocabStats", () => {
  const ready = ref(false);
  const count = ref(0);
  let timer: ReturnType<typeof setTimeout> | null = null;
  let polling = false;

  async function refresh() {
    try {
      const data = await api.vocabularyStats();
      ready.value = Boolean(data.loaded);
      count.value = data.count ?? 0;
    } catch {
      // Silent — the periodic re-check will try again.
    }
  }

  async function startPolling() {
    if (polling) return;
    polling = true;
    while (polling && !ready.value) {
      await refresh();
      if (ready.value) break;
      await new Promise<void>((resolve) => {
        timer = setTimeout(() => resolve(), 2000);
      });
    }
    polling = false;
  }

  function stop() {
    polling = false;
    if (timer) {
      clearTimeout(timer);
      timer = null;
    }
  }

  return { ready, count, refresh, startPolling, stop };
});
