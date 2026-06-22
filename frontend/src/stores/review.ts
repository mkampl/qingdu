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

// Canonical cycle order. Recognition first (pure recall), then Cloze
// (context anchors the meaning), then Dictation (force production from
// audio), then Writing (motor recall). Each step compounds the previous
// one's signal so a card that survives the cycle is genuinely retained.
export const CYCLE_ORDER: ReviewMode[] = [
  "recognition",
  "cloze",
  "dictation",
  "writing",
];

/**
 * Review queue + stats. The queue is fetched lazily when the user enters
 * /review (or hits a "start review" CTA) and stays in memory until they
 * leave; grading peels cards off the front. Stats are refreshed on auth
 * hydrate so the nav badge is correct on cold load.
 *
 * Phase 1.3 — Mixed mode is the default: a single card cycles through
 * Recognition → Cloze → Dictation → Writing before FSRS schedules its
 * next due_at. `currentCycleMode` tracks where we are in that loop;
 * `singleMode` (mirrored from settings) flips back to the legacy
 * one-grade-one-FSRS-step behaviour for power users.
 */
export const useReviewStore = defineStore("review", () => {
  const queue = ref<ReviewCard[]>([]);
  const queueMode = ref<QueueMode>("mixed");
  /** The modality being tested on the *current* card. In Mixed mode this
   *  advances through CYCLE_ORDER as the user grades each modality on
   *  the same card. In single-mode this just mirrors queueMode. */
  const currentCycleMode = ref<ReviewMode>("recognition");
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

  function nextModeFor(card: ReviewCard, completed: ReviewMode[]): ReviewMode {
    // Walk CYCLE_ORDER, skipping anything already done. Skip cloze when
    // the row has no sample sentence (the modality would be impossible).
    for (const m of CYCLE_ORDER) {
      if (completed.includes(m)) continue;
      if (m === "cloze" && card.has_sample_sentence === false) continue;
      return m;
    }
    // Every applicable mode done — caller should treat this as cycle
    // complete. Default to recognition (won't be reached in practice).
    return "recognition";
  }

  function resumeCycleFor(card: ReviewCard): ReviewMode {
    const done = card.cycle_modes_completed ?? [];
    return nextModeFor(card, done);
  }

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
      // Set the starting modality. Mixed mode: resume on whichever step
      // the first card was last seen at (cycle_modes_completed). Single
      // mode: lock to the picked modality for the whole session.
      if (mode === "mixed" && r.cards.length > 0) {
        currentCycleMode.value = resumeCycleFor(r.cards[0]);
      } else if (mode !== "mixed") {
        currentCycleMode.value = mode;
      }
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
    const settings = useSettingsStore();
    const cycle = !settings.reviewSingleMode;
    try {
      const response = await api.gradeReviewCard(
        card.word,
        g,
        currentCycleMode.value,
        cycle,
      );
      sessionGraded.value += 1;

      // Mixed-mode: the same card stays in front; advance the modality.
      // Single-mode + mixed-mode-cycle-completed: move to the next card.
      if (cycle && !response.cycle_complete) {
        // Cycle still in flight — keep card visible, swap modality.
        // The server tells us which mode comes next; fall back locally
        // if it didn't (which shouldn't happen for a passing grade).
        const next = response.cycle_next_mode
          ? response.cycle_next_mode
          : nextModeFor(card, response.cycle_modes_completed);
        currentCycleMode.value = next;
        // Patch the in-memory card so a queue reload won't desync.
        queue.value[cursor.value] = {
          ...card,
          cycle_modes_completed: response.cycle_modes_completed,
        };
        // Failing grade resets the cycle — show the modality the user
        // just failed at as the new start (recognition), not where the
        // server thinks we are. The response already reflects "[]".
        if (response.cycle_modes_completed.length === 0) {
          currentCycleMode.value = nextModeFor(card, []);
        }
      } else {
        // Cycle done (or single-mode). Phase #118 (5a) — Anki-style
        // learning-queue re-insert: if FSRS scheduled the card within
        // the next 20 minutes, splice it onto the queue tail so the
        // cursor will reach it again this session.
        const dueAt = response.due_at
          ? new Date(response.due_at).getTime()
          : null;
        const cutoff = Date.now() + 20 * 60_000;
        if (dueAt !== null && dueAt <= cutoff) {
          queue.value = [
            ...queue.value,
            {
              ...card,
              due_at: response.due_at,
              stability: response.stability,
              difficulty: response.difficulty,
              cycle_modes_completed: [],
            },
          ];
        }

        cursor.value += 1;
        const nextCard = current.value;
        if (cycle && nextCard) {
          currentCycleMode.value = resumeCycleFor(nextCard);
        }
        // Optimistic stats update — refreshStats reconciles right after.
        stats.value = {
          ...stats.value,
          due_now: Math.max(0, stats.value.due_now - 1),
          reviewed_today: stats.value.reviewed_today + 1,
        };
      }
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
    currentCycleMode.value = "recognition";
  }

  // Back-compat alias — older view code reads `review.mode` and expects
  // the modality currently rendered on screen. That's currentCycleMode
  // in the Mixed-mode world.
  const mode = computed<ReviewMode>(() => currentCycleMode.value);

  return {
    queue,
    queueMode,
    currentCycleMode,
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
