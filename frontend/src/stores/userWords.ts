import { computed, ref } from "vue";
import { defineStore } from "pinia";

import * as api from "@/api/client";
import type { UserWordState, WordStatsResponse } from "@/api/client";

/**
 * Per-user word-state cache. Mirrors the server's /api/words/state on hydrate
 * and applies optimistic local updates around POST/DELETE. Absence of a word
 * in `states` means 'new' (the user has never interacted with it).
 *
 * The Reader reads this thousands of times per render via `stateOf(word)`, so
 * the underlying structure is a plain object with O(1) lookups — not a Map,
 * not reactive deep — and is only swapped wholesale when remote data arrives.
 */
export const useUserWordsStore = defineStore("userWords", () => {
  const states = ref<Record<string, UserWordState>>({});
  const stats = ref<WordStatsResponse>({
    learning: 0,
    known: 0,
    ignored: 0,
    streak: 0,
  });
  const hydrated = ref(false);
  const loading = ref(false);

  const total = computed(
    () => stats.value.learning + stats.value.known + stats.value.ignored,
  );

  function stateOf(word: string): UserWordState | null {
    return states.value[word] ?? null;
  }

  function recomputeStats() {
    const next: WordStatsResponse = {
      learning: 0,
      known: 0,
      ignored: 0,
      // Preserve streak across optimistic updates — it's a server-derived
      // value, not something we can recompute from the local states.
      streak: stats.value.streak,
    };
    for (const s of Object.values(states.value)) {
      next[s] += 1;
    }
    stats.value = next;
  }

  async function hydrate(force = false) {
    if (hydrated.value && !force) return;
    loading.value = true;
    try {
      const [statesResp, statsResp] = await Promise.all([
        api.listUserWordStates(),
        api.getWordStats(),
      ]);
      states.value = { ...statesResp.states };
      stats.value = statsResp;
      hydrated.value = true;
    } catch {
      // Anonymous calls hit 401; that's fine — leave the store empty.
      hydrated.value = true;
    } finally {
      loading.value = false;
    }
  }

  /** Refresh just the server-side stats (streak, totals) without
   *  re-fetching the full word-state map. Used after grading reviews. */
  async function refreshStats() {
    try {
      stats.value = await api.getWordStats();
    } catch {
      /* keep prior */
    }
  }

  async function setState(
    word: string,
    state: UserWordState,
    sourceTextId?: number | null,
  ) {
    const prev = states.value[word];
    // Optimistic — reassign object to keep reactivity cheap & shallow.
    states.value = { ...states.value, [word]: state };
    recomputeStats();
    try {
      await api.setUserWordState(word, state, sourceTextId);
    } catch (err) {
      // Roll back on failure.
      const next = { ...states.value };
      if (prev) next[word] = prev;
      else delete next[word];
      states.value = next;
      recomputeStats();
      throw err;
    }
  }

  async function clearState(word: string) {
    const prev = states.value[word];
    if (!prev) return;
    const next = { ...states.value };
    delete next[word];
    states.value = next;
    recomputeStats();
    try {
      await api.clearUserWordState(word);
    } catch (err) {
      states.value = { ...states.value, [word]: prev };
      recomputeStats();
      throw err;
    }
  }

  async function bulkMarkKnown(words: string[], sourceTextId?: number | null) {
    const unique = Array.from(new Set(words.filter((w) => !!w)));
    if (!unique.length) return { updated: 0, total: 0 };
    const prev = { ...states.value };
    const next = { ...states.value };
    for (const w of unique) next[w] = "known";
    states.value = next;
    recomputeStats();
    try {
      return await api.bulkMarkKnown(unique, sourceTextId);
    } catch (err) {
      states.value = prev;
      recomputeStats();
      throw err;
    }
  }

  function reset() {
    states.value = {};
    stats.value = { learning: 0, known: 0, ignored: 0, streak: 0 };
    hydrated.value = false;
  }

  return {
    states,
    stats,
    hydrated,
    loading,
    total,
    stateOf,
    hydrate,
    setState,
    clearState,
    bulkMarkKnown,
    refreshStats,
    reset,
  };
});
