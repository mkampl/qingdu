import { computed, ref } from "vue";
import { defineStore } from "pinia";

import * as api from "@/api/client";
import type {
  ReviewCard,
  ReviewGrade,
  ReviewMode,
  ReviewStatsResponse,
} from "@/api/client";
import { useUserWordsStore } from "@/stores/userWords";

const DEFAULT_STATS: ReviewStatsResponse = {
  due_now: 0,
  due_today: 0,
  learning: 0,
  reviewed_today: 0,
  new_today: 0,
  daily_target: 0,
};

/**
 * Review queue + stats. The queue is fetched lazily when the user enters
 * /review (or hits a "start review" CTA) and stays in memory until they
 * leave; grading peels cards off the front. Stats are refreshed on auth
 * hydrate so the nav badge is correct on cold load.
 */
export const useReviewStore = defineStore("review", () => {
  const queue = ref<ReviewCard[]>([]);
  const mode = ref<ReviewMode>("recognition");
  const cursor = ref(0);
  const sessionGraded = ref(0);
  const stats = ref<ReviewStatsResponse>({ ...DEFAULT_STATS });
  const loading = ref(false);
  const grading = ref(false);
  const error = ref<string | null>(null);

  const current = computed<ReviewCard | null>(
    () => queue.value[cursor.value] ?? null,
  );
  const hasNext = computed(() => cursor.value + 1 < queue.value.length);
  const remaining = computed(() =>
    Math.max(0, queue.value.length - cursor.value),
  );
  const dueNow = computed(() => stats.value.due_now);

  async function loadQueue(targetMode: ReviewMode = mode.value) {
    loading.value = true;
    error.value = null;
    mode.value = targetMode;
    cursor.value = 0;
    sessionGraded.value = 0;
    try {
      const r = await api.getReviewQueue(targetMode, 30);
      queue.value = r.cards;
      // Phase #96 — fetching the queue triggers server-side auto-enrol,
      // which bumps `new_today` and may add to `due_now`. Refresh stats
      // so the SPA badges reflect what the backend just enrolled.
      void refreshStats();
    } catch (e) {
      error.value =
        e instanceof Error ? e.message : "Couldn't load review queue";
      queue.value = [];
    } finally {
      loading.value = false;
    }
  }

  async function grade(g: ReviewGrade) {
    const card = current.value;
    if (!card || grading.value) return;
    grading.value = true;
    try {
      await api.gradeReviewCard(card.word, g, mode.value);
      sessionGraded.value += 1;
      // Move to the next card; the just-graded one drops out of view.
      cursor.value += 1;
      // Optimistic stats update so the strip ticks down without waiting
      // on the round-trip — refreshStats() reconciles right after.
      stats.value = {
        ...stats.value,
        due_now: Math.max(0, stats.value.due_now - 1),
        reviewed_today: stats.value.reviewed_today + 1,
      };
      // Pull the authoritative numbers — due_today, new_today, learning
      // all move during a session (auto-enrol, FSRS reschedules, etc.)
      // and optimistic-only updates drift fast.
      void refreshStats();
      // Streak might have just bumped (first activity today). Pull the
      // freshest word-stats so the flame badge updates without a manual reload.
      void useUserWordsStore().refreshStats();
    } catch (e) {
      error.value = e instanceof Error ? e.message : "Couldn't save grade";
    } finally {
      grading.value = false;
    }
  }

  async function refreshStats() {
    try {
      stats.value = await api.getReviewStats();
      // Cache the count so the daily-reminder notification body has a
      // current-ish number even when the app is closed and we can't hit
      // the API from the background.
      const { rememberDueCount } = await import("@/services/notifications");
      rememberDueCount(stats.value.due_now);
    } catch {
      // Anonymous calls hit 401 — leave defaults in place.
    }
  }

  function reset() {
    queue.value = [];
    cursor.value = 0;
    sessionGraded.value = 0;
    stats.value = { ...DEFAULT_STATS };
    error.value = null;
  }

  return {
    queue,
    mode,
    cursor,
    sessionGraded,
    stats,
    loading,
    grading,
    error,
    current,
    hasNext,
    remaining,
    dueNow,
    loadQueue,
    grade,
    refreshStats,
    reset,
  };
});
