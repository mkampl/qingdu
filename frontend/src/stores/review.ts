import { computed, ref } from "vue";
import { defineStore } from "pinia";

import * as api from "@/api/client";
import type {
  QueueMode,
  ReviewCard,
  ReviewGrade,
  ReviewMode,
  ReviewStatsResponse,
} from "@/api/client";
import { useSettingsStore } from "@/stores/settings";
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
 *
 * Phase 1.3b — Mixed mode is the default queue source. Each card carries
 * a server-picked `prompt_stage` (intro / trace / produce) derived from
 * its FSRS stability; the SPA renders the right review surface per card
 * and a single grade advances FSRS in the usual single-step way. Power
 * users can pick a single ReviewMode via the Advanced disclosure; that
 * locks the queue to one modality and bypasses stage selection.
 */
export const useReviewStore = defineStore("review", () => {
  const queue = ref<ReviewCard[]>([]);
  const queueMode = ref<QueueMode>("mixed");
  const cursor = ref(0);
  const sessionGraded = ref(0);
  const stats = ref<ReviewStatsResponse>({ ...DEFAULT_STATS });
  const loading = ref(false);
  const grading = ref(false);
  const error = ref<string | null>(null);
  // Phase #119 — mobile focus-mode flag (collapses header/footer during
  // the result phase). Lives in the store so App.vue can read it.
  const inFocus = ref(false);

  const current = computed<ReviewCard | null>(
    () => queue.value[cursor.value] ?? null,
  );
  const hasNext = computed(() => cursor.value + 1 < queue.value.length);
  const remaining = computed(() =>
    Math.max(0, queue.value.length - cursor.value),
  );
  const dueNow = computed(() => stats.value.due_now);

  // Back-compat alias — older components read `review.mode` expecting
  // the modality currently rendered. In stage-based mixed mode the
  // server picks the surface, so we surface a reasonable default for
  // legacy paths; Advanced single-mode returns the locked mode.
  const mode = computed<ReviewMode>(() => {
    if (queueMode.value === "mixed") {
      // The Advanced single-mode templates still key on this for the
      // cloze/recognition/dictation/writing branches — but stage-based
      // rendering uses card.prompt_stage instead, so this value is just
      // a fallback for any legacy reference.
      return "recognition";
    }
    return queueMode.value;
  });

  async function loadQueue(targetMode?: QueueMode) {
    const settings = useSettingsStore();
    const mode: QueueMode =
      targetMode ?? (settings.reviewSingleMode ? "recognition" : "mixed");
    loading.value = true;
    error.value = null;
    queueMode.value = mode;
    cursor.value = 0;
    sessionGraded.value = 0;
    try {
      const r = await api.getReviewQueue(mode, 30);
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
      const response = await api.gradeReviewCard(card.word, g, mode.value);
      sessionGraded.value += 1;

      // Phase #118 (5a) — Anki-style learning-queue re-insert. If FSRS
      // scheduled the card within the next 20 minutes (Again → +1min,
      // Hard → +6min, Good while still in learning → +10min), splice
      // it onto the back of the queue so the cursor reaches it again
      // this session.
      const dueAt = response.due_at ? new Date(response.due_at).getTime() : null;
      const cutoff = Date.now() + 20 * 60_000;
      if (dueAt !== null && dueAt <= cutoff) {
        queue.value = [
          ...queue.value,
          {
            ...card,
            due_at: response.due_at,
            stability: response.stability,
            difficulty: response.difficulty,
            prompt_stage: response.prompt_stage,
          },
        ];
      }

      cursor.value += 1;
      // Optimistic stats update — refreshStats reconciles right after.
      stats.value = {
        ...stats.value,
        due_now: Math.max(0, stats.value.due_now - 1),
        reviewed_today: stats.value.reviewed_today + 1,
      };
      void refreshStats();
      // Streak might have just bumped (first activity today). Pull the
      // freshest word-stats so the flame chip updates without a reload.
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
    inFocus.value = false;
  }

  return {
    queue,
    queueMode,
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
    inFocus,
    loadQueue,
    grade,
    refreshStats,
    reset,
  };
});
