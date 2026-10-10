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
import { useAuthStore } from "@/stores/auth";
import { useSettingsStore } from "@/stores/settings";
import { useUserWordsStore } from "@/stores/userWords";
import { dueCountForWindow, shouldReinsert } from "@/utils/review";

const DEFAULT_STATS: ReviewStatsResponse = {
  due_now: 0,
  due_today: 0,
  due_in_window: 0,
  learning: 0,
  in_rotation: 0,
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
  // What failed, so ReviewView can offer the matching retry: reload the
  // queue, or re-send the grade that didn't go through.
  const errorKind = ref<"queue" | "grade" | "empty" | null>(null);
  let failedGrade: { grade: ReviewGrade; surface?: ReviewMode } | null = null;
  let failedPractice: { word: string; returnTo: string | null } | null = null;
  // Phase #119 — mobile focus-mode flag (collapses header/footer during
  // the result phase). Lives in the store so App.vue can read it.
  const inFocus = ref(false);
  // Practice mode — session started from WordsView for a specific word.
  // When true, grade() short-circuits the server call so FSRS state,
  // streak, and stats stay untouched. ReviewView renders a persistent
  // banner reminding the user the session is out-of-competition.
  const practiceMode = ref(false);
  // Where "End practice" goes back to — the /words URL including its
  // filter query, so the list comes back the way the user left it.
  const practiceReturnTo = ref<string | null>(null);

  const current = computed<ReviewCard | null>(
    () => queue.value[cursor.value] ?? null,
  );
  const hasNext = computed(() => cursor.value + 1 < queue.value.length);
  const remaining = computed(() =>
    Math.max(0, queue.value.length - cursor.value),
  );
  // What a session would open with right now under user.review_window.
  // The server counts it with the same window definition the queue uses
  // (stats.due_in_window), so the badge, the Start gate and the queue
  // can't disagree — "tomorrow" used to read due_today and undercount.
  const dueNow = computed(() => {
    const auth = useAuthStore();
    return dueCountForWindow(stats.value, auth.user?.review_window ?? "today");
  });

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
    clearError();
    queueMode.value = mode;
    cursor.value = 0;
    sessionGraded.value = 0;
    try {
      const r = await api.getReviewQueue(mode, 30);
      queue.value = r.cards;
      if (r.cards.length === 0) {
        // The Start gate said there was something due, but nothing came
        // back (e.g. cloze with no saved-text sentences). Say so instead
        // of silently dropping back to the start screen.
        errorKind.value = "empty";
        error.value =
          mode === "cloze"
            ? "None of your due words appear in a saved text yet, so there's nothing to fill in. Try another mode."
            : "Nothing to review right now.";
      }
      // Phase #96 — fetching the queue triggers server-side auto-enrol,
      // which bumps `new_today` and may add to `due_now`. Refresh stats
      // so the SPA badges reflect what the backend just enrolled.
      void refreshStats();
    } catch (e) {
      errorKind.value = "queue";
      error.value =
        e instanceof Error ? e.message : "Couldn't load review queue";
      queue.value = [];
    } finally {
      loading.value = false;
    }
  }

  async function startPractice(word: string, returnTo: string | null = null) {
    loading.value = true;
    clearError();
    practiceMode.value = true;
    practiceReturnTo.value = returnTo;
    queueMode.value = "mixed";
    cursor.value = 0;
    sessionGraded.value = 0;
    try {
      const r = await api.getPracticeCard(word);
      queue.value = [r.card];
    } catch (e) {
      errorKind.value = "queue";
      failedPractice = { word, returnTo };
      error.value =
        e instanceof Error ? e.message : "Couldn't load practice card";
      queue.value = [];
      practiceMode.value = false;
    } finally {
      loading.value = false;
    }
  }

  /** Grade the current card. Resolves true once the grade is stored
   *  (or, in practice mode, counted) and the cursor has moved on. */
  async function grade(g: ReviewGrade, surface?: ReviewMode): Promise<boolean> {
    const card = current.value;
    if (!card || grading.value) return false;
    // Practice mode — no server call, no FSRS mutation, no streak update.
    // Just count the modality attempt so the SPA's UI counter still ticks
    // and the cursor advances so the session ends naturally after all
    // modes have been tried.
    if (practiceMode.value) {
      sessionGraded.value += 1;
      cursor.value += 1;
      return true;
    }
    grading.value = true;
    clearError();
    try {
      // `surface` is the modality the user actually just performed —
      // ReviewView passes it in mixed mode. Without it every mixed-mode
      // grade was logged as mode:"recognition" (the legacy fallback of
      // `mode`), mislabelling per-modality stats server-side.
      const response = await api.gradeReviewCard(card.word, g, surface ?? mode.value);
      sessionGraded.value += 1;

      // Phase #118 (5a) — Anki-style learning-queue re-insert. If FSRS
      // scheduled the card within the next 20 minutes (Again → +1min,
      // Hard → +6min, Good while still in learning → +10min), splice
      // it onto the back of the queue so the cursor reaches it again
      // this session. due_at is UTC; shouldReinsert parses it as such.
      const reinsert = shouldReinsert(response.due_at);
      if (reinsert) {
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
      // Optimistic stats update — refreshAfterGrade reconciles right
      // after. A re-inserted card is still due, so the counts stay.
      const left = (n: number) => Math.max(0, n - (reinsert ? 0 : 1));
      stats.value = {
        ...stats.value,
        due_now: left(stats.value.due_now),
        due_today: left(stats.value.due_today),
        due_in_window: left(stats.value.due_in_window),
        reviewed_today: stats.value.reviewed_today + 1,
      };
      void refreshAfterGrade();
      return true;
    } catch (e) {
      errorKind.value = "grade";
      failedGrade = { grade: g, surface };
      error.value = e instanceof Error ? e.message : "Couldn't save grade";
      return false;
    } finally {
      grading.value = false;
    }
  }

  /** Re-run whatever failed last. Resolves true when it went through. */
  async function retry(): Promise<boolean> {
    if (errorKind.value === "grade" && failedGrade) {
      const { grade: g, surface } = failedGrade;
      return grade(g, surface);
    }
    if (errorKind.value === "queue" && failedPractice) {
      const { word, returnTo } = failedPractice;
      await startPractice(word, returnTo);
      return error.value === null;
    }
    if (errorKind.value === "queue" || errorKind.value === "empty") {
      await loadQueue(queueMode.value);
      return error.value === null;
    }
    return false;
  }

  function clearError() {
    error.value = null;
    errorKind.value = null;
    failedGrade = null;
    failedPractice = null;
  }

  // Streak might have just bumped (first activity today). Pull the word
  // stats first so the streak handed to the notification cache in
  // refreshStats is the fresh one, not the value from before this grade.
  async function refreshAfterGrade() {
    await useUserWordsStore().refreshStats();
    await refreshStats();
  }

  // Only the newest stats response is applied: with fast grading several
  // requests are in flight, and an older one landing last used to roll
  // the counters back.
  let statsSeq = 0;
  async function refreshStats() {
    const seq = ++statsSeq;
    try {
      const fresh = await api.getReviewStats();
      if (seq !== statsSeq) return;
      stats.value = { ...DEFAULT_STATS, ...fresh };
      const notif = await import("@/services/notifications");
      // dueNow (not the raw stats field) so the reminder body matches
      // what /review actually opens with per the user's window setting.
      notif.rememberDueCount(dueNow.value);
      // Phase 1.8 — pipe streak into the notification cache too so the
      // streak-at-risk ping has the right number to lead with.
      notif.rememberStreak(useUserWordsStore().stats.streak);
      if (stats.value.reviewed_today > 0) {
        // The user has reviewed at least once today — flag activity so
        // the evening at-risk ping doesn't fire if streak isn't actually
        // in danger.
        notif.rememberActiveToday();
      }
    } catch {
      // Anonymous calls hit 401 — leave defaults in place.
    }
  }

  function reset() {
    queue.value = [];
    cursor.value = 0;
    sessionGraded.value = 0;
    // Leave stats alone — they reflect the user's persistent learning
    // state (due counts, streak, total learning words). Pressing Done
    // ends the session, not the day's stats.
    clearError();
    inFocus.value = false;
    practiceMode.value = false;
    practiceReturnTo.value = null;
  }

  // Logout variant: stats must go too, or the next account signing in on
  // the same device briefly inherits the previous user's due-count badge.
  function resetAll() {
    reset();
    stats.value = { ...DEFAULT_STATS };
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
    errorKind,
    current,
    hasNext,
    remaining,
    dueNow,
    inFocus,
    practiceMode,
    practiceReturnTo,
    loadQueue,
    startPractice,
    grade,
    retry,
    clearError,
    refreshStats,
    reset,
    resetAll,
  };
});
