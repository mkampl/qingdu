<script setup lang="ts">
/**
 * SRS review session — Phase B.
 *
 * Two modes ship now: Recognition (flashcard) and Dictation (listen-and-type).
 * Cloze is reserved for when the backend can hand back a sample sentence per
 * card; until then the chip is shown with a "soon" badge.
 *
 * Grading flow:
 *   1. user is shown the prompt for the current card
 *   2. user reveals the answer (recognition) or submits it (dictation)
 *   3. user picks Again / Hard / Good / Easy (recognition) — dictation auto-
 *      derives Good from a correct answer, Again from an incorrect one
 *   4. store applies the grade, advances the cursor, optimistic stats tick
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import * as api from "@/api/client";
import type { QueueMode, ReviewGrade, ReviewMode } from "@/api/client";
import WeeklySparkline from "@/components/reader/WeeklySparkline.vue";
import StrokeOrder from "@/components/reader/StrokeOrder.vue";
import WritingQuiz from "@/components/reader/WritingQuiz.vue";
import ContextSentence from "@/components/review/ContextSentence.vue";
import WordDetails from "@/components/reader/WordDetails.vue";
import WordReadings from "@/components/reader/WordReadings.vue";
import { customGlosses } from "@/utils/glosses";
import { useAuthStore } from "@/stores/auth";
import { useAuthModalsStore } from "@/stores/auth-modals";
import { useReviewStore } from "@/stores/review";
import { useSettingsStore } from "@/stores/settings";
import { success as hapticSuccess, tap as hapticTap } from "@/services/native";
import { checkPinyin, type PinyinVerdict } from "@/utils/pinyin-answer";
import {
  formatHskLevel,
  reviewShortcutBlocked,
  autoGradeForWriting,
  suggestedGradeForMistakes,
} from "@/utils/review";

const review = useReviewStore();
const router = useRouter();
const route = useRoute();

// /review?text=<text key> or ?list=<id> focuses the session on one
// text's pre-learned words or one vocab list (stores/review scope).
watch(
  () => [route.query.text, route.query.list] as const,
  ([text, list]) => {
    const listId = Number(list);
    void review.setScope(
      typeof text === "string" && text
        ? { textKey: text }
        : typeof list === "string" && Number.isInteger(listId)
          ? { listId }
          : null,
    );
  },
  { immediate: true },
);

function clearScope() {
  void router.replace({ path: "/review" });
}

function endPractice() {
  const to = review.practiceReturnTo || "/words";
  review.reset();
  void router.push(to);
}

// Auto-end practice once the single practice card has been graded so the
// user lands back on My Words instead of the Start Review screen. Guard
// on sessionGraded > 0 so the empty state on first mount doesn't fire
// this before the card has even loaded.
watch(
  () => [
    review.practiceMode,
    review.sessionGraded,
    review.current,
    review.loading,
  ] as const,
  ([practice, graded, current, loading]) => {
    if (practice && graded > 0 && current === null && !loading) {
      endPractice();
    }
  },
);
const auth = useAuthStore();
const authModals = useAuthModalsStore();
const settings = useSettingsStore();

const revealed = ref(false);
const dictationInput = ref("");
const dictationFeedback = ref<"" | "correct" | "toneless" | "tone" | "wrong">("");
const DICTATION_VERDICT = {
  correct: "Correct",
  toneless: "Right sound — type the tones too (mǎ or ma3)",
  tone: "Wrong tone",
  wrong: "Not quite",
  "": "",
} as const;
const ttsLoading = ref(false);

const modes: {
  id: ReviewMode;
  label: string;
  hint: string;
  available: boolean;
}[] = [
  {
    id: "recognition",
    label: "Recognition",
    hint: "See the character, recall the meaning",
    available: true,
  },
  {
    id: "dictation",
    label: "Dictation",
    hint: "Listen, type what you hear",
    available: true,
  },
  {
    id: "writing",
    label: "Writing",
    hint: "Draw the character stroke by stroke",
    available: true,
  },
  {
    id: "cloze",
    label: "Cloze",
    hint: "Fill the blank in a real sentence from your saved texts",
    available: true,
  },
];

// Writing-quiz state — tracks per-card mistakes from hanzi-writer's
// onMistake/onCorrectStroke callbacks. ReviewView turns this into a
// suggested FSRS grade on completion.
const writingMistakes = ref(0);
const writingStrokes = ref(0);
const writingDone = ref(false);

// Cloze state — user types the missing word, we compare against
// card.word (or its trad/simp equivalent, since the card.word the
// server sent us is already in the user's display script).
const clozeInput = ref("");
const clozeFeedback = ref<"" | "correct" | "wrong">("");

// Phase 1.3b — intro stage. The card auto-plays TTS and animates
// stroke order on mount; the user just absorbs. The auto-Good
// countdown is gated on the user tapping "Got it" — without a tap
// the card just sits there with audio + strokes, no time pressure.
const introReady = ref(false);

function onWritingComplete(payload: {
  totalMistakes: number;
  totalStrokes: number;
  skipped: boolean;
}) {
  writingMistakes.value = payload.totalMistakes;
  writingStrokes.value = payload.totalStrokes;
  writingDone.value = true;
}

const card = computed(() => review.current);
// The writing pass straight after the intro animation (see autoGradeForWriting).
const firstEncounter = computed(() => card.value?.prompt_stage === "intro");
const writingAutoGrade = computed(() =>
  autoGradeForWriting(writingMistakes.value, writingStrokes.value, firstEncounter.value),
);
const total = computed(() => review.queue.length);
const idx = computed(() => Math.min(review.cursor + 1, total.value));

// Phase 1.3b — the active "surface" the card renders. In Mixed mode the
// server picks via prompt_stage (intro/trace/produce); in Advanced
// single-mode it locks to whatever ReviewMode the user picked.
type Surface =
  | "intro"
  | "trace"
  | "produce"
  | "read"
  | "recognition"
  | "dictation"
  | "writing"
  | "cloze";

const activeSurface = computed<Surface>(() => {
  if (review.queueMode === "mixed") {
    const stage = (card.value?.prompt_stage as Surface) ?? "intro";
    // Phase 1.3b follow-up — the intro stage is absorption only; after
    // the user taps 'Got it' the same card swaps to the trace surface
    // so they write it in the same encounter. FSRS only grades once,
    // on the writing-quiz completion. Without this, fresh cards would
    // disappear from today's queue (next due ≥ 1d) and the user would
    // wait until tomorrow to write them for the first time.
    if (stage === "intro" && introReady.value) return "trace";
    return stage;
  }
  // Single-mode — surface is the queueMode itself (one of the four
  // ReviewModes; mixed is excluded by the conditional above).
  return review.queueMode as Surface;
});

// Per-card UI state. Cleared whenever the card on screen changes (new
// session, next card, re-inserted card) — see the review.current watcher.
function resetCardState() {
  cancelAutoGrade();
  revealed.value = false;
  readInput.value = "";
  readVerdict.value = "";
  dictationInput.value = "";
  dictationFeedback.value = "";
  writingMistakes.value = 0;
  writingStrokes.value = 0;
  writingDone.value = false;
  clozeInput.value = "";
  clozeFeedback.value = "";
  // Without this an intro card tapped "Got it" on, then End session, made
  // the next session's first intro card skip straight to trace.
  introReady.value = false;
}

async function start(mode: QueueMode) {
  resetCardState();
  await review.loadQueue(mode);
}

async function retryReview() {
  await review.retry();
}

// Phase 1.3 — Advanced single-mode disclosure. Hidden by default;
// expands to expose the four ReviewModes for power users who want to
// drill one modality. Flipping the toggle persists to settings so the
// preference survives next session.
const advancedOpen = ref(false);

function startMixed() {
  void start("mixed");
}

function startSingle(mode: ReviewMode) {
  // Persist the user's intent: they explicitly chose single-mode here,
  // so future "Start review" calls (from /today panel, streak chip)
  // default to it too. Flip back to Mixed by tapping "Mixed (default)".
  settings.reviewSingleMode = true;
  void start(mode);
}

function switchToMixed() {
  settings.reviewSingleMode = false;
  void start("mixed");
}

function reveal() {
  revealed.value = true;
}

// Read stage: the hanzi alone; the learner recalls sound, tone and meaning,
// optionally types the pinyin, then reveals and grades themselves. The
// word's audio only plays once the answer is out.
const readInput = ref("");
const readVerdict = ref<"" | PinyinVerdict>("");
const READ_VERDICT: Record<PinyinVerdict, string> = {
  exact: "Right, tones too",
  toneless: "Right sound — tones not typed",
  "wrong-tone": "Wrong tone",
  wrong: "Not this word",
};

function revealRead() {
  if (!card.value || revealed.value) return;
  const typed = readInput.value.trim();
  readVerdict.value = typed ? checkPinyin(typed, card.value.pinyin || "") : "";
  revealed.value = true;
  void playTts();
}

// Hold a reference to the currently-playing TTS audio so back-to-back
// playTts() calls (intro auto-play + intro→trace surface flip both
// firing) don't stack into an echo. Each new play stops the previous
// one cleanly and revokes its blob URL.
let activeTtsAudio: HTMLAudioElement | null = null;
let activeTtsUrl: string | null = null;

function stopActiveTts() {
  if (activeTtsAudio) {
    try {
      activeTtsAudio.pause();
      activeTtsAudio.currentTime = 0;
    } catch {
      // ignore — element may have been GC'd
    }
    activeTtsAudio = null;
  }
  if (activeTtsUrl) {
    URL.revokeObjectURL(activeTtsUrl);
    activeTtsUrl = null;
  }
}

// Bumped by every playTts() and whenever the card changes or the view
// unmounts. A fetch that resolves after that is dropped instead of
// playing the previous card's audio over the current one.
let ttsSeq = 0;

function cancelTts() {
  ttsSeq += 1;
  stopActiveTts();
  ttsLoading.value = false;
}

async function playTts() {
  if (!card.value) return;
  stopActiveTts();
  const seq = ++ttsSeq;
  ttsLoading.value = true;
  try {
    const r = await api.tts(card.value.word);
    if (!r.ok) throw new Error("TTS failed");
    const blob = await r.blob();
    if (seq !== ttsSeq) return;
    const url = URL.createObjectURL(blob);
    const audio = new Audio(url);
    activeTtsAudio = audio;
    activeTtsUrl = url;
    audio.addEventListener("ended", () => {
      if (activeTtsAudio === audio) {
        URL.revokeObjectURL(url);
        activeTtsAudio = null;
        activeTtsUrl = null;
      }
    });
    await audio.play();
  } catch {
    /* keep button responsive */
  } finally {
    if (seq === ttsSeq) ttsLoading.value = false;
  }
}

// Grade row — visible after reveal in recognition, after answer in
// dictation, after the writing quiz completes, after a cloze answer.
// Intro never reaches this row directly: tapping 'Got it' on an intro
// card swaps the surface to trace, and the row appears once the trace
// WritingQuiz completes. Shared by the template and the keyboard handler.
const gradeRowVisible = computed(
  () =>
    (activeSurface.value === "recognition" && revealed.value) ||
    (activeSurface.value === "read" && revealed.value) ||
    (activeSurface.value === "dictation" && dictationFeedback.value !== "") ||
    (activeSurface.value === "writing" && writingDone.value) ||
    (activeSurface.value === "cloze" && clozeFeedback.value !== "") ||
    (activeSurface.value === "trace" && writingDone.value) ||
    (activeSurface.value === "produce" && writingDone.value),
);

// Keyboard shortcuts SRS users expect: space reveals, 1-4 grade. Skipped
// while typing in the dictation/cloze inputs, while a dialog is open on
// top (Settings, shortcuts help, …), and Space is left alone when it
// would activate a focused button.
function onReviewKeydown(e: KeyboardEvent) {
  if (reviewShortcutBlocked(e)) return;
  if (!card.value) return;
  if (e.key === " ") {
    if (activeSurface.value === "recognition" && !revealed.value) {
      e.preventDefault();
      reveal();
    } else if (activeSurface.value === "read" && !revealed.value) {
      e.preventDefault();
      revealRead();
    }
    return;
  }
  if (
    ["1", "2", "3", "4"].includes(e.key) &&
    gradeRowVisible.value &&
    !review.grading
  ) {
    e.preventDefault();
    void gradeAndAdvance(Number(e.key) as ReviewGrade);
  }
}

// The event-log modality for the surface the user just completed. The
// stage surfaces (intro/trace/produce) are all hanzi-writing exercises.
function surfaceMode(): ReviewMode {
  const s = activeSurface.value;
  if (s === "intro" || s === "trace" || s === "produce") return "writing";
  if (s === "read") return "recognition";
  return s;
}

async function gradeAndAdvance(g: ReviewGrade) {
  if (!card.value) return;
  // Light tap for Again/Hard, medium thump for Good/Easy — feels right
  // because a confident answer wants a more satisfying confirmation.
  if (g >= 3) hapticSuccess(settings.hapticsEnabled);
  else hapticTap(settings.hapticsEnabled);
  cancelAutoGrade();
  // On success the cursor moves and the review.current watcher resets
  // the per-card state. On failure the card stays as it is, with the
  // error banner offering a retry.
  await review.grade(g, surfaceMode());
}

// Intro stage — passive absorption. TTS auto-plays and strokes animate
// on card open, but the auto-Good countdown waits for the user to tap
// "Got it". Without that gate the timer would fire even when the user
// is just listening or hasn't looked yet — too aggressive on a fresh
// word.
function introContinue() {
  introReady.value = true;
}
// When the queue runs out during a session, refresh stats so the
// session-complete screen shows the true "still due" count rather than
// whatever the optimistic per-grade decrement left in place.
watch(
  () => review.current,
  (cur, prev) => {
    if (prev && !cur && review.queue.length > 0) {
      void review.refreshStats();
    }
  },
);

// --- Phase #118 (2b) — Auto-grade countdown for writing mode ---------------
//
// After writing-quiz completion, the user sees a suggested grade derived
// from the mistake/stroke ratio. 2s later it auto-fires, mirroring the
// "answer is right, advance automatically" pattern Duolingo/WaniKani use
// and saving a tap on the common case. Any rating button click cancels
// the timer and fires the clicked rating instead, so the auto-grade
// stays a Default rather than a forced choice.

// Settings → Review → Auto-grade after writing (0 = off, default 2 s).
// A context sentence appears with the result, so the countdown grows by
// the time it takes to read it; a tap on the card stops the countdown.
const autoGradeDelayMs = computed(() => {
  const base = settings.autoGradeDelayMs;
  const sentence = card.value?.cloze_sentence;
  return base > 0 && sentence ? base + 1500 + Math.min(3500, 150 * sentence.length) : base;
});
const autoGradeTimer = ref<number | null>(null);
const autoGradePending = ref<ReviewGrade | null>(null);

function cancelAutoGrade() {
  if (autoGradeTimer.value !== null) {
    window.clearTimeout(autoGradeTimer.value);
    autoGradeTimer.value = null;
  }
  autoGradePending.value = null;
}

function scheduleAutoGrade(g: ReviewGrade) {
  cancelAutoGrade();
  if (autoGradeDelayMs.value <= 0) return;
  autoGradePending.value = g;
  autoGradeTimer.value = window.setTimeout(() => {
    autoGradeTimer.value = null;
    autoGradePending.value = null;
    void gradeAndAdvance(g);
  }, autoGradeDelayMs.value);
}

watch(
  () =>
    [
      activeSurface.value,
      writingDone.value,
      writingMistakes.value,
      writingStrokes.value,
    ] as const,
  ([surface, done, mistakes, strokes]) => {
    cancelAutoGrade();
    // Writing-style surfaces autograde once the WritingQuiz fires its
    // complete event. Intro doesn't grade on its own anymore — the user
    // taps 'Got it' which swaps the surface to trace; that surface's
    // writing-quiz completion is what produces the FSRS grade.
    if (
      (surface === "writing" || surface === "trace" || surface === "produce") &&
      done
    ) {
      scheduleAutoGrade(
        surface === "writing"
          ? suggestedGradeForMistakes(mistakes, strokes)
          : autoGradeForWriting(mistakes, strokes, firstEncounter.value),
      );
    }
  },
  { immediate: false },
);

// New card on screen: drop the previous card's UI state and audio, then
// auto-play TTS once for this encounter. We watch the card (not the
// surface) so an intro→trace flip on the *same* card doesn't re-fire
// the audio — that flip was the source of the echo a user reported on
// v1.0.34 (intro auto-play + transition auto-play overlapped).
watch(
  () => review.current,
  (cur, prev) => {
    if (cur === prev) return;
    cancelTts();
    resetCardState();
    if (!cur) return;
    if (activeSurface.value === "intro" || activeSurface.value === "trace") {
      void playTts();
    }
  },
  { immediate: true },
);

// Phase #119 — Mobile focus-mode. Stays on as long as a card is loaded,
// regardless of whether we're in the write-phase or the result-phase.
// The previous version only kicked in on writingDone, which left the
// writing canvas pushed below the fold during the *active* drawing
// (user had to scroll down to find their canvas) — defeated the purpose.
// Cleared automatically when review.current becomes null (queue exhausted,
// session reset, or load failure) so the stats + sparkline come back
// for the "start a new session" decision.
const focusMode = computed(() => review.current !== null);

// Phase #119 — the queue-cutoff lives server-side per user.review_window.
// The UI gates need to mirror that so "Due now: 0 / Due today: 17" with
// window=today doesn't lock the user out of starting a session.
// review.dueNow already resolves this the same way (see stores/review.ts)
// so the home-screen badge and this view can't disagree.
const effectiveDueCount = computed(() =>
  review.scope ? (review.scopeInfo?.due ?? 0) : review.dueNow,
);
// The counter strip: a focused session counts only its own words.
const statTiles = computed((): Record<string, number> => {
  const info = review.scopeInfo;
  if (review.scope) {
    const tiles: Record<string, number> = {
      "Due now": info?.due_now ?? 0,
      "Due today": info?.due_today ?? 0,
      "In review": info?.total ?? 0,
      Learned: info?.learned ?? 0,
    };
    return tiles;
  }
  const tiles: Record<string, number> = {
    "Due now": review.stats.due_now,
    "Due today": review.stats.due_today,
    Learning: review.stats.learning,
    "Reviewed today": review.stats.reviewed_today,
  };
  return tiles;
});
watch(focusMode, (v) => {
  review.inFocus = v;
});

function submitCloze() {
  if (!card.value || clozeFeedback.value !== "") return;
  const guess = clozeInput.value.trim();
  if (!guess) return;
  clozeFeedback.value = guess === card.value.word ? "correct" : "wrong";
}

async function clozeContinue() {
  // Correct → Good (3). Wrong → Again (1). Grade row stays available
  // after so the user can override with Easy/Hard.
  await gradeAndAdvance(clozeFeedback.value === "correct" ? 3 : 1);
}

function submitDictation() {
  if (!card.value || dictationFeedback.value !== "") return;
  const guess = dictationInput.value.trim();
  if (!guess) return;
  if (guess === card.value.word.trim()) {
    dictationFeedback.value = "correct";
    return;
  }
  const verdict = checkPinyin(guess, card.value.pinyin || "");
  dictationFeedback.value =
    verdict === "exact"
      ? "correct"
      : verdict === "toneless"
        ? "toneless"
        : verdict === "wrong-tone"
          ? "tone"
          : "wrong";
}

async function dictationContinue() {
  // Correct → Good (3). Right syllables typed without tones → Hard (2).
  // A wrong tone or wrong word → Again (1). The user can override with
  // the explicit grade row after the answer is revealed.
  const grade = { correct: 3, toneless: 2, tone: 1, wrong: 1, "": 1 } as const;
  await gradeAndAdvance(grade[dictationFeedback.value]);
}

onBeforeUnmount(() => {
  cancelAutoGrade();
  cancelTts();
  review.inFocus = false;
  window.removeEventListener("keydown", onReviewKeydown);
});

onMounted(() => {
  if (auth.isAuthed) review.refreshStats();
  window.addEventListener("keydown", onReviewKeydown);
});

</script>

<template>
  <section
    :class="[
      'mx-auto max-w-3xl',
      focusMode
        ? 'px-3 py-3 sm:px-6 sm:py-6'
        : 'px-4 py-10 sm:px-6 sm:py-14',
    ]"
  >
    <header v-if="!focusMode" class="mb-6 sm:mb-8">
      <p
        class="font-mono text-[11px] uppercase tracking-[0.22em] text-fg-subtle"
      >
        {{ review.practiceMode ? "Practice" : "Spaced repetition" }}
      </p>
      <h1
        class="mt-1 font-display text-2xl font-medium tracking-tight text-fg sm:text-4xl"
      >
        {{ review.practiceMode ? "Practice this word" : "Review" }}
      </h1>
    </header>

    <!-- Practice-mode banner. Lives above the card body so it never
         disappears when the SPA drops into focus-mode for writer /
         cloze — the whole point is that the user sees this the entire
         time. FSRS state, streak, and stats are all untouched. -->
    <div
      v-if="review.practiceMode"
      class="mb-6 flex items-start gap-3 rounded-md border border-amber-300/60 bg-amber-50/70 px-4 py-3 text-sm text-amber-800 dark:border-amber-700/50 dark:bg-amber-500/10 dark:text-amber-200"
      role="status"
    >
      <span aria-hidden="true">🎯</span>
      <div class="flex-1 leading-snug">
        <p class="font-medium">Practice mode — nothing is graded.</p>
        <p class="text-xs opacity-80">
          Grade buttons don't advance FSRS. Streak, due date, and stats
          all stay put. End practice any time to return to your list.
        </p>
      </div>
      <button
        type="button"
        class="rounded-md border border-amber-300/60 bg-amber-50 px-3 py-1 font-mono text-[10px] uppercase tracking-wider text-amber-800 hover:bg-amber-100 dark:border-amber-700/50 dark:bg-amber-500/20 dark:text-amber-100 dark:hover:bg-amber-500/30"
        @click="endPractice"
      >
        End practice
      </button>
    </div>

    <!-- Review errors: queue load, grade save, or an empty queue. A failed
         grade keeps the card on screen; Retry re-sends the same grade. -->
    <div
      v-if="auth.isAuthed && review.error"
      :class="[
        'mb-6 flex items-start gap-3 rounded-md border px-4 py-3 text-sm',
        review.errorKind === 'empty'
          ? 'border-border-subtle bg-bg-elevated text-fg-muted'
          : 'border-red-300/60 bg-red-50/70 text-red-800 dark:border-red-800/50 dark:bg-red-500/10 dark:text-red-200',
      ]"
      :role="review.errorKind === 'empty' ? 'status' : 'alert'"
    >
      <p class="flex-1 leading-snug">
        <span v-if="review.errorKind === 'grade'" class="font-medium">
          Couldn't save that grade.
        </span>
        <span v-else-if="review.errorKind === 'queue'" class="font-medium">
          Couldn't load your review queue.
        </span>
        {{ review.error }}
      </p>
      <button
        v-if="review.errorKind === 'grade' || review.errorKind === 'queue'"
        type="button"
        class="shrink-0 rounded-md border border-current/30 px-3 py-1 font-mono text-[10px] uppercase tracking-wider transition-opacity hover:opacity-80 disabled:opacity-50"
        :disabled="review.grading || review.loading"
        @click="retryReview"
      >
        Retry
      </button>
      <button
        type="button"
        class="shrink-0 px-1 font-mono text-[10px] uppercase tracking-wider opacity-70 transition-opacity hover:opacity-100"
        aria-label="Dismiss"
        @click="review.clearError()"
      >
        ✕
      </button>
    </div>

    <!-- Not authed -->
    <div
      v-if="!auth.isAuthed"
      class="rounded-lg border border-border-subtle bg-bg-elevated px-6 py-10 text-center"
    >
      <p class="font-display text-lg text-fg">Sign in to review your words.</p>
      <p class="mt-2 text-sm text-fg-muted">
        Review draws from the words you track in the reader —
        <span class="font-medium">Learning</span> words often,
        <span class="font-medium">Known</span> words now and then.
      </p>
      <button
        type="button"
        class="mt-4 inline-flex items-center rounded-full bg-accent px-4 py-1.5 text-sm font-medium text-accent-fg transition-opacity hover:opacity-90"
        @click="authModals.openLogin()"
      >
        Sign in
      </button>
    </div>

    <!-- Focused session: only the words of one text or vocab list. -->
    <div
      v-if="auth.isAuthed && review.scope"
      class="mb-4 flex flex-wrap items-center justify-between gap-2 rounded-lg border border-accent/40 bg-accent/5 px-4 py-2.5"
    >
      <p class="text-sm text-fg">
        <span class="font-mono text-[10px] uppercase tracking-wider text-accent">
          {{ review.scope.listId !== undefined ? "List" : "Text" }}
        </span>
        <span class="ml-2 font-medium">{{ review.scopeInfo?.title || "Focused review" }}</span>
        <span v-if="review.scopeInfo" class="ml-2 text-xs text-fg-muted">
          {{ review.scopeInfo.due }} due · {{ review.scopeInfo.total }} words
        </span>
      </p>
      <button
        type="button"
        class="font-mono text-[10px] uppercase tracking-wider text-fg-subtle hover:text-fg"
        @click="clearScope"
      >
        All reviews
      </button>
    </div>

    <!-- 7-day activity sparkline — only when authed; lives above the
         counter strip so the "how's the habit going?" view lands first. -->
    <WeeklySparkline v-if="auth.isAuthed && !focusMode && !review.scope" class="mb-4" />

    <!-- Stats strip — denser typography on mobile where four 60px-wide cards
         used to wear text-2xl numbers. -->
    <div
      v-if="auth.isAuthed && !focusMode"
      class="mb-6 grid grid-cols-2 gap-2 sm:grid-cols-4 sm:gap-3"
    >
      <div
        v-for="(stat, key) in statTiles"
        :key="key"
        class="rounded-lg border border-border-subtle bg-bg-elevated px-3 py-2 sm:px-4 sm:py-3"
      >
        <p
          class="font-mono text-[10px] uppercase tracking-wider text-fg-subtle"
        >
          {{ key }}
        </p>
        <p class="mt-0.5 font-display text-xl tabular-nums text-fg sm:mt-1 sm:text-2xl">
          {{ stat.toLocaleString() }}
        </p>
      </div>
    </div>

    <!-- Phase #96 — daily-target progress strip. Hidden when target is 0
         (auto-enrol disabled in Settings) so the chrome stays clean for
         users who want full control over their learning pool. -->
    <p
      v-if="auth.isAuthed && review.stats.daily_target > 0 && !focusMode && !review.scope"
      class="-mt-2 mb-6 font-mono text-[10px] uppercase tracking-wider text-fg-subtle"
    >
      New today:
      <span class="text-fg tabular-nums">{{ review.stats.new_today }}</span>
      / {{ review.stats.daily_target }}
      <span v-if="review.stats.new_today >= review.stats.daily_target">
        — today's batch enrolled
      </span>
    </p>

    <!-- Phase 1.3 — Start screen. Mixed mode (every card cycles
         Recognition → Cloze → Dictation → Writing) is the default
         button; the four single-modality picks live behind an Advanced
         disclosure so they're available to power users who want to
         drill one modality at a time. -->
    <div
      v-if="auth.isAuthed && review.queue.length === 0 && !review.loading"
      class="space-y-4"
    >
      <p
        class="font-mono text-[11px] uppercase tracking-[0.2em] text-fg-subtle"
      >
        {{ settings.reviewSingleMode ? "Pick a mode to begin" : "Ready to review" }}
      </p>

      <!-- Default: progressive Mixed-mode Start. The hint copy from
           v1.0.30 cluttered the home for users who already know what
           Start does — collapsed to a single tight button. -->
      <button
        v-if="!settings.reviewSingleMode"
        type="button"
        :disabled="effectiveDueCount === 0"
        class="group flex w-full items-center justify-between rounded-lg border border-accent/40 bg-accent/5 px-5 py-3.5 text-left transition-colors hover:bg-accent/10 disabled:cursor-not-allowed disabled:opacity-50"
        @click="startMixed"
      >
        <span class="font-display text-lg font-medium text-fg">
          <template v-if="review.scope">
            Start these {{ effectiveDueCount }}
          </template>
          <template v-else>Start review</template>
        </span>
        <span class="font-mono text-[10px] uppercase tracking-wider text-fg-muted group-hover:text-fg">
          →
        </span>
      </button>

      <!-- Advanced disclosure — single-modality picks. Always visible
           when the user previously chose single-mode (so they can find
           it and either continue or switch back). -->
      <details
        v-if="!review.scope"
        :open="settings.reviewSingleMode || advancedOpen"
        class="group rounded-lg border border-border-subtle bg-bg-elevated"
        @toggle="advancedOpen = ($event.target as HTMLDetailsElement).open"
      >
        <summary class="flex cursor-pointer items-center justify-between px-4 py-2.5 font-mono text-[10px] uppercase tracking-wider text-fg-muted hover:text-fg">
          {{ settings.reviewSingleMode ? "Single-mode picker" : "Advanced — drill one modality" }}
          <span class="text-fg-subtle">⌃</span>
        </summary>
        <div class="border-t border-border-subtle px-4 py-3">
          <button
            v-if="settings.reviewSingleMode"
            type="button"
            class="mb-3 w-full rounded-md border border-accent/40 bg-accent/5 px-3 py-2 text-left text-xs font-medium text-accent transition-colors hover:bg-accent/10"
            @click="switchToMixed"
          >
            ← Use Mixed mode (recommended)
          </button>
          <div class="grid gap-2 sm:grid-cols-2 sm:gap-3">
            <button
              v-for="m in modes"
              :key="m.id"
              type="button"
              :disabled="!m.available || effectiveDueCount === 0"
              class="rounded-md border border-border-subtle bg-bg px-3 py-2.5 text-left transition-colors hover:border-accent hover:bg-bg-sunken disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:border-border-subtle disabled:hover:bg-bg"
              @click="startSingle(m.id)"
            >
              <span class="block font-display text-sm font-medium text-fg">
                {{ m.label }}
              </span>
              <span class="block text-xs text-fg-muted">{{ m.hint }}</span>
            </button>
          </div>
        </div>
      </details>

      <!-- Tone practice: hear a word, pick its tones (no grading). -->
      <RouterLink
        v-if="!review.scope"
        to="/tones"
        class="flex items-center justify-between rounded-lg border border-border-subtle bg-bg-elevated px-4 py-2.5 transition-colors hover:border-accent"
      >
        <span>
          <span class="block font-display text-sm font-medium text-fg">Tone practice</span>
          <span class="block text-xs text-fg-muted">Hear a word, pick its tones (mǎi or mài?)</span>
        </span>
        <span class="font-mono text-[10px] uppercase tracking-wider text-fg-muted">→</span>
      </RouterLink>

      <div
        v-if="effectiveDueCount === 0 && review.stats.in_rotation > 0"
        class="mt-2 rounded-lg border border-border-subtle bg-bg-elevated px-5 py-4 text-center text-sm text-fg-muted"
      >
        Nothing's due right now — come back later. Your
        {{ review.stats.in_rotation.toLocaleString() }} Learning and Known
        words come back on their own schedule.
      </div>
      <div
        v-else-if="review.stats.in_rotation === 0"
        class="mt-2 rounded-lg border border-border-subtle bg-bg-elevated px-5 py-4 text-center text-sm text-fg-muted"
      >
        Nothing to review yet. Click any word in the reader and choose
        "Learning" (or "Known") from the popover — both join your review
        rotation.
      </div>
    </div>

    <!-- Loading state -->
    <div
      v-else-if="review.loading"
      class="flex items-center justify-center py-16"
    >
      <span
        class="inline-block size-6 animate-spin rounded-full border-2 border-fg-muted border-t-transparent"
      />
    </div>

    <!-- Session header + card -->
    <div v-else-if="card" class="space-y-4 sm:space-y-6">
      <div class="flex items-center justify-between">
        <p
          class="font-mono text-[11px] uppercase tracking-[0.2em] text-fg-subtle"
        >
          {{ activeSurface }} · card {{ idx }} / {{ total }}
        </p>
        <button
          type="button"
          class="font-mono text-[10px] uppercase tracking-wider text-fg-subtle transition-colors hover:text-fg"
          @click="review.practiceMode ? endPractice() : review.reset()"
        >
          {{ review.practiceMode ? "End practice" : "End session" }}
        </button>
      </div>

      <!-- Progress bar -->
      <div class="h-[3px] w-full overflow-hidden rounded-full bg-bg-sunken">
        <div
          class="h-full rounded-full bg-accent transition-[width] duration-200"
          :style="{
            width: total > 0 ? `${(review.cursor / total) * 100}%` : '0%',
          }"
        />
      </div>


      <!-- Card -->
      <div
        class="rounded-2xl border border-border-subtle bg-bg-elevated px-4 py-6 text-center sm:px-10 sm:py-14"
        @pointerdown="cancelAutoGrade"
      >
        <!-- Phase 1.3b — intro stage. Fresh / never-reviewed cards.
             Everything's shown from the start: hanzi big, pinyin, meaning,
             stroke animation, and TTS auto-plays. No quiz, no typing —
             just absorption. A 'Continue' button skips the cooldown
             ahead to the auto-Good countdown. -->
        <template v-if="activeSurface === 'intro'">
          <p
            class="font-mono text-[10px] uppercase tracking-wider text-accent"
          >
            New · listen + read + watch
          </p>
          <p class="mt-3 font-mono text-sm tracking-widest text-fg-muted">
            {{ card.pinyin }}
          </p>
          <p class="font-cn-serif text-6xl text-fg sm:text-7xl">
            {{ card.word }}
          </p>
          <WordReadings
            class="mx-auto mt-4 max-w-md"
            :meaning="card.meaning"
            :meanings="card.meanings"
            :meaning-tags="card.meaning_tags"
            :readings="card.readings"
              :glosses="card.glosses"
              :focus="card.focus_gloss"
            headline-class="font-display text-base leading-snug text-fg"
          />
          <WordDetails :word="card.word" class="mx-auto mt-3 max-w-md" />
          <ContextSentence
            v-if="card.cloze_sentence"
            :sentence="card.cloze_sentence"
            :word="card.word"
            :source="card.sentence_source"
          />

          <!-- Stroke animation: auto-replays each card via the :key bind
               so the animation restarts when the cursor advances. For
               multi-char words (e.g. 修为) auto-advance cycles through
               every character in sequence — the user sees each one drawn
               from scratch without having to tap the chips. -->
          <div class="mt-6 flex justify-center">
            <StrokeOrder
              :key="`${card.word}-${review.cursor}`"
              :chars="card.word"
              auto-advance
            />
          </div>

          <div
            class="sticky bottom-0 -mx-4 mt-6 flex flex-col items-center gap-2 bg-bg-elevated/95 pb-3 pt-3 backdrop-blur sm:static sm:mx-0 sm:bg-transparent sm:pb-0 sm:pt-0 sm:backdrop-blur-none"
          >
            <button
              type="button"
              class="rounded-full bg-accent px-5 py-2 text-sm font-medium text-accent-fg transition-opacity hover:opacity-90"
              @click="introContinue"
            >
              Got it · try writing it
            </button>
            <p
              class="font-mono text-[10px] uppercase tracking-wider text-fg-subtle"
            >
              Listen + watch · then write it from memory
            </p>
          </div>
        </template>

        <!-- Phase 1.3b — trace stage (1d ≤ stability < 10d). Past the
             first encounter; pinyin + meaning sit above the canvas and
             the user produces the hanzi via hanzi-writer's stroke quiz.
             TTS auto-plays on mount so audio still anchors motor memory.
             showOutline mirrors the user's preference so beginners can
             trace; the produce stage forces no-outline. -->
        <template v-else-if="activeSurface === 'trace'">
          <p
            class="font-mono text-[10px] uppercase tracking-wider text-accent"
          >
            Trace · stability {{ Math.round(card.stability ?? 0) }}d
          </p>
          <div class="mt-3">
            <WritingQuiz
              :key="`${card.word}-${review.cursor}`"
              :word="card.word"
              :pinyin="card.pinyin"
              :meaning="card.meaning"
              :meanings="card.meanings"
              :glosses="customGlosses(card.glosses, card.focus_gloss)"
              :focus="card.focus_gloss ?? null"
              :show-outline="settings.writingShowOutline"
              @complete="onWritingComplete"
            />
          </div>
          <p
            v-if="writingDone"
            class="mt-4 font-mono text-[10px] uppercase tracking-wider text-fg-subtle"
          >
            {{ writingMistakes }} mistake{{ writingMistakes === 1 ? "" : "s" }} over
            {{ writingStrokes }} strokes — auto-grading
            <span class="text-fg">
              {{ ["", "Again", "Hard", "Good", "Easy"][writingAutoGrade] }}
            </span>
          </p>
          <p
            v-if="writingDone && firstEncounter && writingAutoGrade === 3"
            class="mt-1 text-xs text-fg-muted"
          >
            First look — it comes back later in this session to write from memory.
          </p>
          <ContextSentence
            v-if="writingDone && card.cloze_sentence"
            :sentence="card.cloze_sentence"
            :word="card.word"
            :source="card.sentence_source"
          />
        </template>

        <!-- Phase 1.3b — produce stage (stability ≥ 10d). Established
             card; outline is forced off so the user has to recall the
             hanzi from pinyin + meaning. No TTS this round — sound
             cues are gone too. -->
        <template v-else-if="activeSurface === 'produce'">
          <p
            class="font-mono text-[10px] uppercase tracking-wider text-accent"
          >
            Produce · stability {{ Math.round(card.stability ?? 0) }}d
          </p>
          <div class="mt-3">
            <WritingQuiz
              :key="`${card.word}-${review.cursor}`"
              :word="card.word"
              :pinyin="card.pinyin"
              :meaning="card.meaning"
              :meanings="card.meanings"
              :glosses="customGlosses(card.glosses, card.focus_gloss)"
              :focus="card.focus_gloss ?? null"
              :show-outline="false"
              @complete="onWritingComplete"
            />
          </div>
          <p
            v-if="writingDone"
            class="mt-4 font-mono text-[10px] uppercase tracking-wider text-fg-subtle"
          >
            {{ writingMistakes }} mistake{{ writingMistakes === 1 ? "" : "s" }} over
            {{ writingStrokes }} strokes — auto-grading
            <span class="text-fg">
              {{ ["", "Again", "Hard", "Good", "Easy"][writingAutoGrade] }}
            </span>
          </p>
          <ContextSentence
            v-if="writingDone && card.cloze_sentence"
            :sentence="card.cloze_sentence"
            :word="card.word"
            :source="card.sentence_source"
          />
        </template>

        <!-- Read stage: the reading direction. Only the hanzi; sound, tone
             and meaning come from memory. Typing the pinyin is optional
             and checked against the card; Show answer (space) reveals,
             plays the word and the learner grades themselves. -->
        <template v-else-if="activeSurface === 'read'">
          <p
            class="font-mono text-[10px] uppercase tracking-wider text-accent"
          >
            Read · stability {{ Math.round(card.stability ?? 0) }}d
          </p>
          <p class="mt-4 font-cn-serif text-6xl leading-none text-fg sm:text-7xl">
            {{ card.word }}
          </p>
          <template v-if="!revealed">
            <p class="mt-6 text-sm text-fg-muted">
              Say it with its tone and meaning — then check.
            </p>
            <input
              v-model="readInput"
              type="text"
              placeholder="Pinyin with tones (optional)"
              autocomplete="off"
              autocapitalize="off"
              autocorrect="off"
              spellcheck="false"
              class="mt-4 w-full max-w-xs rounded-lg border border-border bg-bg-elevated px-4 py-2 text-center text-base text-fg focus:border-accent focus:outline-none"
              @keydown.enter.prevent="revealRead"
            />
            <div>
              <button
                type="button"
                class="mt-5 inline-flex items-center gap-2 rounded-full border border-border bg-bg-elevated px-5 py-2 text-sm font-medium text-fg-muted transition-colors hover:bg-bg-sunken hover:text-fg"
                @click="revealRead"
              >
                Show answer
                <span class="font-mono text-[9px] uppercase tracking-wider opacity-70">
                  (space)
                </span>
              </button>
            </div>
          </template>
          <div v-else class="mt-6 space-y-1.5">
            <p
              v-if="readVerdict"
              class="font-mono text-[11px] uppercase tracking-wider"
              :class="
                readVerdict === 'exact'
                  ? 'text-emerald-600 dark:text-emerald-300'
                  : readVerdict === 'toneless'
                    ? 'text-amber-700 dark:text-amber-300'
                    : 'text-red-700 dark:text-red-300'
              "
            >
              {{ READ_VERDICT[readVerdict] }}
            </p>
            <p class="font-sans text-base text-fg-muted">{{ card.pinyin }}</p>
            <WordReadings
              class="mx-auto max-w-md"
              :meaning="card.meaning"
              :meanings="card.meanings"
              :meaning-tags="card.meaning_tags"
              :readings="card.readings"
              :glosses="card.glosses"
              :focus="card.focus_gloss"
              headline-class="font-display text-xl text-fg"
              list-class="mt-1 space-y-0.5 text-sm text-fg-muted"
            />
            <WordDetails :word="card.word" class="mx-auto max-w-md pt-2" />
            <ContextSentence
              v-if="card.cloze_sentence"
              :sentence="card.cloze_sentence"
              :word="card.word"
              :source="card.sentence_source"
            />
          </div>
        </template>

        <!-- Recognition mode -->
        <template v-else-if="activeSurface === 'recognition'">
          <p
            v-if="card.hsk_level"
            class="mb-4 font-mono text-[10px] uppercase tracking-wider text-fg-subtle"
          >
            {{ formatHskLevel(card.hsk_level) }}
          </p>
          <p class="font-cn-serif text-6xl leading-none text-fg sm:text-7xl">
            {{ card.word }}
          </p>
          <div v-if="revealed" class="mt-6 space-y-1.5">
            <p class="font-sans text-base text-fg-muted">{{ card.pinyin }}</p>
            <WordReadings
              class="mx-auto max-w-md"
              :meaning="card.meaning"
              :meanings="card.meanings"
              :meaning-tags="card.meaning_tags"
              :readings="card.readings"
              :glosses="card.glosses"
              :focus="card.focus_gloss"
              headline-class="font-display text-xl text-fg"
              list-class="mt-1 space-y-0.5 text-sm text-fg-muted"
            />
            <WordDetails :word="card.word" class="mx-auto max-w-md pt-2" />
            <ContextSentence
              v-if="card.cloze_sentence"
              :sentence="card.cloze_sentence"
              :word="card.word"
              :source="card.sentence_source"
            />
          </div>

          <button
            v-if="!revealed"
            type="button"
            class="mt-8 inline-flex items-center gap-2 rounded-full border border-border bg-bg-elevated px-5 py-2 text-sm font-medium text-fg-muted transition-colors hover:bg-bg-sunken hover:text-fg"
            @click="reveal"
          >
            Show answer
            <span
              class="font-mono text-[9px] uppercase tracking-wider opacity-70"
            >
              (space)
            </span>
          </button>
        </template>

        <!-- Dictation mode -->
        <template v-else-if="activeSurface === 'dictation'">
          <button
            type="button"
            class="mx-auto inline-flex size-20 items-center justify-center rounded-full border border-border bg-bg-elevated text-fg-muted transition-colors hover:bg-bg-sunken hover:text-fg disabled:opacity-50"
            :disabled="ttsLoading"
            aria-label="Play word"
            @click="playTts"
          >
            <span
              v-if="ttsLoading"
              class="inline-block size-6 animate-spin rounded-full border-2 border-current border-t-transparent"
            />
            <svg v-else width="28" height="28" viewBox="0 0 28 28" fill="none">
              <path d="M5 10h4l5-4v16l-5-4H5v-8z" fill="currentColor" />
              <path
                d="M18 9c2 2 2 8 0 10M21 6c4 3 4 13 0 16"
                stroke="currentColor"
                stroke-width="1.8"
                stroke-linecap="round"
              />
            </svg>
          </button>

          <div class="mt-8">
            <input
              v-model="dictationInput"
              :readonly="dictationFeedback !== ''"
              type="text"
              placeholder="Hanzi or pinyin with tones (mǎ / ma3)"
              autocomplete="off"
              autocapitalize="off"
              autocorrect="off"
              spellcheck="false"
              class="w-full max-w-md rounded-lg border border-border bg-bg-elevated px-4 py-3 text-center font-cn-serif text-2xl text-fg focus:border-accent focus:outline-none"
              @keydown.enter.prevent="
                dictationFeedback === ''
                  ? submitDictation()
                  : dictationContinue()
              "
            />
          </div>

          <div v-if="dictationFeedback === ''" class="mt-6">
            <button
              type="button"
              class="rounded-full bg-accent px-5 py-2 text-sm font-medium text-accent-fg transition-opacity hover:opacity-90 disabled:opacity-50"
              :disabled="!dictationInput.trim()"
              @click="submitDictation"
            >
              Check
            </button>
          </div>

          <div v-else class="mt-6 space-y-2">
            <p
              class="font-mono text-[11px] uppercase tracking-wider"
              :class="
                dictationFeedback === 'correct'
                  ? 'text-emerald-600 dark:text-emerald-300'
                  : dictationFeedback === 'toneless'
                    ? 'text-amber-700 dark:text-amber-300'
                    : 'text-red-700 dark:text-red-300'
              "
            >
              {{ DICTATION_VERDICT[dictationFeedback] }}
            </p>
            <p class="font-cn-serif text-3xl text-fg">{{ card.word }}</p>
            <p class="font-sans text-sm text-fg-muted">{{ card.pinyin }}</p>
            <WordReadings
              class="mx-auto max-w-md"
              :meaning="card.meaning"
              :meanings="card.meanings"
              :meaning-tags="card.meaning_tags"
              :readings="card.readings"
              :glosses="card.glosses"
              :focus="card.focus_gloss"
              headline-class="font-display text-base text-fg"
            />
            <ContextSentence
              v-if="card.cloze_sentence"
              :sentence="card.cloze_sentence"
              :word="card.word"
              :source="card.sentence_source"
            />
          </div>
        </template>

        <!-- Writing mode -->
        <template v-else-if="activeSurface === 'writing'">
          <div class="mb-3 flex justify-center">
            <button
              type="button"
              class="font-mono text-[10px] uppercase tracking-wider text-fg-subtle transition-colors hover:text-fg"
              :aria-pressed="settings.writingShowOutline"
              @click="
                settings.writingShowOutline = !settings.writingShowOutline
              "
            >
              Outline: {{ settings.writingShowOutline ? "on" : "off" }}
            </button>
          </div>
          <WritingQuiz
            :key="`${card.word}-${review.cursor}`"
            :word="card.word"
            :pinyin="card.pinyin"
            :meaning="card.meaning"
            :meanings="card.meanings"
            :glosses="customGlosses(card.glosses, card.focus_gloss)"
            :focus="card.focus_gloss ?? null"
            :show-outline="settings.writingShowOutline"
            @complete="onWritingComplete"
          />
          <div v-if="writingDone" class="mt-4 space-y-1 text-center">
            <p
              class="font-mono text-[11px] uppercase tracking-wider"
              :class="
                suggestedGradeForMistakes(writingMistakes, writingStrokes) >= 3
                  ? 'text-emerald-600 dark:text-emerald-300'
                  : suggestedGradeForMistakes(writingMistakes, writingStrokes) === 2
                    ? 'text-amber-700 dark:text-amber-300'
                    : 'text-red-700 dark:text-red-300'
              "
            >
              {{
                writingMistakes === 0
                  ? `Perfect (${writingStrokes} stroke${writingStrokes === 1 ? "" : "s"})`
                  : `${writingMistakes} mistake${writingMistakes === 1 ? "" : "s"} on ${writingStrokes} stroke${writingStrokes === 1 ? "" : "s"}`
              }}
            </p>
            <p
              class="font-mono text-[10px] uppercase tracking-wider text-fg-subtle"
            >
              Suggested grade:
              {{
                ["", "Again", "Hard", "Good", "Easy"][
                  suggestedGradeForMistakes(writingMistakes, writingStrokes)
                ]
              }}
            </p>
          </div>
        </template>

        <!-- Cloze mode — sentence with the target word blanked. -->
        <template v-else-if="activeSurface === 'cloze'">
          <p
            class="font-mono text-[10px] uppercase tracking-wider text-fg-subtle"
          >
            Fill the blank
          </p>
          <p class="mt-3 font-cn-serif text-2xl leading-relaxed text-fg">
            {{ card.cloze_template ?? card.cloze_sentence }}
          </p>
          <div v-if="clozeFeedback === ''" class="mt-6 mx-auto max-w-xs">
            <input
              v-model="clozeInput"
              type="text"
              autocomplete="off"
              autocapitalize="off"
              spellcheck="false"
              placeholder="Type the missing word"
              class="w-full rounded-md border border-border bg-bg-elevated px-3 py-2 text-center font-cn-serif text-xl text-fg focus:border-accent focus:outline-none"
              @keydown.enter="submitCloze"
            />
            <button
              type="button"
              class="mt-3 w-full rounded-md bg-accent px-4 py-2 text-sm font-medium text-accent-fg transition-opacity hover:opacity-90 disabled:opacity-40"
              :disabled="!clozeInput.trim()"
              @click="submitCloze"
            >
              Submit
            </button>
          </div>
          <div v-else class="mt-6 space-y-2 text-center">
            <p
              class="font-mono text-[11px] uppercase tracking-wider"
              :class="
                clozeFeedback === 'correct'
                  ? 'text-emerald-600 dark:text-emerald-300'
                  : 'text-red-700 dark:text-red-300'
              "
            >
              {{ clozeFeedback === "correct" ? "Correct" : "Not quite" }}
            </p>
            <p class="font-cn-serif text-3xl text-fg">{{ card.word }}</p>
            <p class="font-sans text-sm text-fg-muted">{{ card.pinyin }}</p>
            <WordReadings
              class="mx-auto max-w-xs"
              :meaning="card.meaning"
              :meanings="card.meanings"
              :meaning-tags="card.meaning_tags"
              :readings="card.readings"
              :glosses="card.glosses"
              :focus="card.focus_gloss"
              headline-class="font-display text-base text-fg"
            />
            <p
              class="mx-auto mt-3 max-w-md font-cn-serif text-lg leading-relaxed text-fg-muted"
            >
              {{ card.cloze_sentence }}
            </p>
          </div>
        </template>
      </div>

      <!-- Grade row — visible after reveal in recognition, after answer in
           dictation, after the writing quiz completes, after a cloze answer.
           Intro never reaches this row directly: tapping 'Got it' on an
           intro card swaps the surface to trace, and the grade row appears
           once the trace WritingQuiz completes. -->
      <!-- On a phone the row sticks to the bottom of the screen, so a long
           sentence or gloss above can never push it out of view. -->
      <div
        v-if="gradeRowVisible"
        class="sticky bottom-0 z-10 -mx-3 grid grid-cols-4 gap-2 bg-bg/95 px-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] pt-2 backdrop-blur sm:static sm:mx-0 sm:bg-transparent sm:p-0 sm:backdrop-blur-none"
      >
        <button
          type="button"
          :disabled="review.grading"
          :class="[
            'relative overflow-hidden rounded-lg border border-border bg-bg-elevated px-3 py-3 transition-colors hover:border-red-500 hover:bg-red-50 disabled:opacity-50 dark:hover:bg-red-500/10',
            autoGradePending === 1 ? 'ring-2 ring-red-400/60' : '',
          ]"
          @click="gradeAndAdvance(1)"
        >
          <span
            v-if="autoGradePending === 1"
            :style="{ animationDuration: `${autoGradeDelayMs}ms` }"
            class="qd-auto-grade-progress absolute inset-x-0 bottom-0 h-0.5 bg-red-500"
          />

          <p
            class="font-display text-base font-medium text-red-700 dark:text-red-300"
          >
            Again
          </p>
          <p
            class="mt-0.5 font-mono text-[9px] uppercase tracking-wider text-fg-subtle"
          >
            &lt; 10m
          </p>
        </button>
        <button
          type="button"
          :disabled="review.grading"
          :class="[
            'relative overflow-hidden rounded-lg border border-border bg-bg-elevated px-3 py-3 transition-colors hover:border-amber-500 hover:bg-amber-50 disabled:opacity-50 dark:hover:bg-amber-500/10',
            autoGradePending === 2 ? 'ring-2 ring-amber-400/60' : '',
          ]"
          @click="gradeAndAdvance(2)"
        >
          <span
            v-if="autoGradePending === 2"
            :style="{ animationDuration: `${autoGradeDelayMs}ms` }"
            class="qd-auto-grade-progress absolute inset-x-0 bottom-0 h-0.5 bg-amber-500"
          />

          <p
            class="font-display text-base font-medium text-amber-700 dark:text-amber-300"
          >
            Hard
          </p>
          <p
            class="mt-0.5 font-mono text-[9px] uppercase tracking-wider text-fg-subtle"
          >
            soon
          </p>
        </button>
        <button
          type="button"
          :disabled="review.grading"
          :class="[
            'relative overflow-hidden rounded-lg border border-border bg-bg-elevated px-3 py-3 transition-colors hover:border-emerald-500 hover:bg-emerald-50 disabled:opacity-50 dark:hover:bg-emerald-500/10',
            autoGradePending === 3 ? 'ring-2 ring-emerald-400/60' : '',
          ]"
          @click="gradeAndAdvance(3)"
        >
          <span
            v-if="autoGradePending === 3"
            :style="{ animationDuration: `${autoGradeDelayMs}ms` }"
            class="qd-auto-grade-progress absolute inset-x-0 bottom-0 h-0.5 bg-emerald-500"
          />

          <p
            class="font-display text-base font-medium text-emerald-700 dark:text-emerald-300"
          >
            Good
          </p>
          <p
            class="mt-0.5 font-mono text-[9px] uppercase tracking-wider text-fg-subtle"
          >
            schedule
          </p>
        </button>
        <button
          type="button"
          :disabled="review.grading"
          :class="[
            'relative overflow-hidden rounded-lg border border-border bg-bg-elevated px-3 py-3 transition-colors hover:border-sky-500 hover:bg-sky-50 disabled:opacity-50 dark:hover:bg-sky-500/10',
            autoGradePending === 4 ? 'ring-2 ring-sky-400/60' : '',
          ]"
          @click="gradeAndAdvance(4)"
        >
          <span
            v-if="autoGradePending === 4"
            :style="{ animationDuration: `${autoGradeDelayMs}ms` }"
            class="qd-auto-grade-progress absolute inset-x-0 bottom-0 h-0.5 bg-sky-500"
          />

          <p
            class="font-display text-base font-medium text-sky-700 dark:text-sky-300"
          >
            Easy
          </p>
          <p
            class="mt-0.5 font-mono text-[9px] uppercase tracking-wider text-fg-subtle"
          >
            push back
          </p>
        </button>
      </div>
    </div>

    <!-- Session complete -->
    <div
      v-else-if="
        auth.isAuthed && review.sessionGraded > 0 && review.queue.length > 0
      "
      class="rounded-lg border border-border-subtle bg-bg-elevated px-6 py-10 text-center"
    >
      <p class="font-display text-xl font-medium text-fg">Session complete.</p>
      <p class="mt-2 text-sm text-fg-muted">
        {{ review.sessionGraded.toLocaleString() }} card{{
          review.sessionGraded === 1 ? "" : "s"
        }}
        reviewed.
        <template v-if="effectiveDueCount > 0">
          {{ effectiveDueCount.toLocaleString() }} still due — keep going?
        </template>
        <template v-else>
          Nothing else due right now. Come back later.
        </template>
      </p>
      <div class="mt-6 flex justify-center gap-3">
        <button
          v-if="effectiveDueCount > 0"
          type="button"
          class="rounded-full bg-accent px-4 py-1.5 text-sm font-medium text-accent-fg transition-opacity hover:opacity-90"
          @click="start(review.queueMode)"
        >
          Continue ({{ effectiveDueCount }})
        </button>
        <button
          type="button"
          class="rounded-full border border-border px-4 py-1.5 text-sm text-fg-muted transition-colors hover:bg-bg-sunken hover:text-fg"
          @click="review.reset()"
        >
          Done
        </button>
      </div>
    </div>
  </section>
</template>

<style scoped>
/* Auto-grade countdown progress bar — fills bottom of the suggested
 * grade button over the auto-grade delay (inline animation-duration from
 * settings.autoGradeDelayMs). Width syncs with the
 * setTimeout, so users see exactly when the auto-fire is coming. */
.qd-auto-grade-progress {
  transform-origin: left;
  animation: qd-auto-grade-fill 2000ms linear forwards;
}

@keyframes qd-auto-grade-fill {
  from {
    transform: scaleX(0);
  }
  to {
    transform: scaleX(1);
  }
}
</style>
