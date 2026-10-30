<script setup lang="ts">
/**
 * SRS review session. Mixed mode (default) shows each card at the stage
 * the server picks (intro / trace / produce / read); the single modes are
 * Recognition, Dictation, Writing and Cloze.
 *
 * Grading flow:
 *   1. user is shown the prompt for the current card
 *   2. user reveals the answer, submits it, or finishes the writing quiz
 *   3. user picks Again / Hard / Good / Easy; writing and typed answers
 *      suggest a grade (writing auto-grades after a countdown)
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
import RevealedAnswer from "@/components/review/RevealedAnswer.vue";
import ReviewStart from "@/components/review/ReviewStart.vue";
import ScopeBanner from "@/components/review/ScopeBanner.vue";
import SessionComplete from "@/components/review/SessionComplete.vue";
import StatTiles from "@/components/review/StatTiles.vue";
import WordDetails from "@/components/reader/WordDetails.vue";
import WordReadings from "@/components/reader/WordReadings.vue";
import { customGlosses, leadGloss } from "@/utils/glosses";
import { useOpenLibraryText } from "@/composables/use-open-library-text";
import { useOpenSavedText } from "@/composables/use-open-saved-text";
import { useAuthStore } from "@/stores/auth";
import { useAuthModalsStore } from "@/stores/auth-modals";
import { useReviewStore } from "@/stores/review";
import { useSettingsStore } from "@/stores/settings";
import { success as hapticSuccess, tap as hapticTap } from "@/services/native";
import { checkPinyin, type PinyinVerdict } from "@/utils/pinyin-answer";
import {
  formatHskLevel,
  formatInterval,
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

// A session focused on a text's pre-learned words leads back to that text
// ("saved:<id>" or "library:<slug>"; a pasted text has no place to go).
const openSavedText = useOpenSavedText();
const openLibraryText = useOpenLibraryText();
const scopeText = computed<{ savedId: number } | { slug: string } | null>(() => {
  const m = /^(saved|library):(.+)$/.exec(review.scope?.textKey ?? "");
  if (!m) return null;
  const id = Number(m[2]);
  if (m[1] === "saved") return Number.isInteger(id) ? { savedId: id } : null;
  return { slug: m[2] };
});

async function backToText() {
  const to = scopeText.value;
  if (!to) return;
  const opened =
    "savedId" in to
      ? await openSavedText(to.savedId)
      : await openLibraryText(to.slug);
  if (opened) review.reset();
}

function endPractice() {
  const to = review.practiceReturnTo || "/words";
  review.reset();
  void router.push(to);
}

// Auto-end practice once its single card is graded, back to My Words.
// sessionGraded > 0 keeps the empty state on first mount from firing it.
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

// Writing-quiz result for the card, turned into a suggested FSRS grade.
const writingMistakes = ref(0);
const writingStrokes = ref(0);
const writingDone = ref(false);

// Cloze state: the typed word is compared against card.word, which the
// server sends in the user's display script.
const clozeInput = ref("");
const clozeFeedback = ref<"" | "correct" | "wrong">("");

// Intro stage: TTS and stroke order play on mount; "Got it" sets this and
// swaps the card to the trace surface.
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
// Under each grade button: when the card comes back after that grade
// (practice grades change nothing, so it keeps the words).
const GRADE_WORDS = ["", "< 10m", "sooner", "on schedule", "later"];
function gradeCaption(g: ReviewGrade): string {
  const s = card.value?.intervals?.[g];
  return s == null || review.practiceMode ? GRADE_WORDS[g] : formatInterval(s);
}
// The grade row, Again to Easy; each button's grade is its 1-4 key.
const GRADE_BUTTONS: {
  grade: ReviewGrade;
  label: string;
  hover: string;
  darkHover: string;
  ring: string;
  bar: string;
  text: string;
}[] = [
  {
    grade: 1,
    label: "Again",
    hover: "hover:border-red-500 hover:bg-red-50",
    darkHover: "dark:hover:bg-red-500/10",
    ring: "ring-2 ring-red-400/60",
    bar: "bg-red-500",
    text: "text-red-700 dark:text-red-300",
  },
  {
    grade: 2,
    label: "Hard",
    hover: "hover:border-amber-500 hover:bg-amber-50",
    darkHover: "dark:hover:bg-amber-500/10",
    ring: "ring-2 ring-amber-400/60",
    bar: "bg-amber-500",
    text: "text-amber-700 dark:text-amber-300",
  },
  {
    grade: 3,
    label: "Good",
    hover: "hover:border-emerald-500 hover:bg-emerald-50",
    darkHover: "dark:hover:bg-emerald-500/10",
    ring: "ring-2 ring-emerald-400/60",
    bar: "bg-emerald-500",
    text: "text-emerald-700 dark:text-emerald-300",
  },
  {
    grade: 4,
    label: "Easy",
    hover: "hover:border-sky-500 hover:bg-sky-50",
    darkHover: "dark:hover:bg-sky-500/10",
    ring: "ring-2 ring-sky-400/60",
    bar: "bg-sky-500",
    text: "text-sky-700 dark:text-sky-300",
  },
];
// The meaning the card leads with: the focused text's or list's, else the
// learner's own (glossary, then a text's, then a package's), else none
// (the dictionary's headline leads).
const cardFocus = computed(() => card.value?.focus_gloss ?? leadGloss(card.value?.glosses));
// The writing pass straight after the intro animation (see autoGradeForWriting).
const firstEncounter = computed(() => card.value?.prompt_stage === "intro");
const writingAutoGrade = computed(() =>
  autoGradeForWriting(writingMistakes.value, writingStrokes.value, firstEncounter.value),
);
const total = computed(() => review.queue.length);
const idx = computed(() => Math.min(review.cursor + 1, total.value));

// The surface the card renders. In Mixed mode the server picks it via
// prompt_stage; in single mode it is the ReviewMode the user picked.
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
    // After 'Got it' an intro card swaps to trace, so a new word is
    // written in the same encounter; FSRS grades once, on the writing
    // quiz's completion.
    if (stage === "intro" && introReady.value) return "trace";
    return stage;
  }
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
  // Else "Got it" then End session would start the next session's first
  // intro card on trace.
  introReady.value = false;
}

async function start(mode: QueueMode) {
  resetCardState();
  await review.loadQueue(mode);
}

// Open state of the start screen's Advanced disclosure (the four single
// modes), kept here so it survives a session. Choosing a mode persists
// settings.reviewSingleMode.
const advancedOpen = ref(false);

function startMixed() {
  void start("mixed");
}

function startSingle(mode: ReviewMode) {
  // Later "Start review" calls (Today panel, streak chip) use single mode
  // too, until the user switches back to Mixed.
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

// The playing TTS audio, so a new playTts() stops the previous one (no
// echo) and revokes its blob URL.
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

// Grade row — visible after reveal in recognition / read, after an answer
// in dictation / cloze, after a writing quiz completes. Intro never shows
// it ('Got it' swaps to trace). Shared by the template and the keyboard
// handler.
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
  // Light tap for Again/Hard, stronger feedback for Good/Easy.
  if (g >= 3) hapticSuccess(settings.hapticsEnabled);
  else hapticTap(settings.hapticsEnabled);
  cancelAutoGrade();
  // On success the cursor moves and the review.current watcher resets
  // the per-card state. On failure the card stays as it is, with the
  // error banner offering a retry.
  await review.grade(g, surfaceMode());
}

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

// --- Auto-grade countdown for writing surfaces ----------------------------
//
// After the writing quiz completes, the suggested grade (from the
// mistake/stroke ratio) fires after a delay. Clicking any grade cancels
// the timer and uses that grade instead.

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
    // Writing surfaces auto-grade once the WritingQuiz completes. Intro
    // never grades itself ('Got it' swaps to trace).
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
);

// New card on screen: drop the previous card's UI state and audio, then
// auto-play TTS once. Watches the card, not the surface, so an
// intro→trace flip on the same card doesn't replay the audio.
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

// Focus mode while a card is loaded: hides the header, stats and
// sparkline so the card (and writing canvas) fits on a phone screen.
const focusMode = computed(() => review.current !== null);

// Due count by the user's review window (review.dueNow, as for the nav
// badge), or the focused scope's due count.
const effectiveDueCount = computed(() =>
  review.scope ? (review.scopeInfo?.due ?? 0) : review.dueNow,
);
// The counter strip: a focused session counts only its own words.
const statTiles = computed((): Record<string, number> => {
  const info = review.scopeInfo;
  if (review.scope) {
    return {
      "Due now": info?.due_now ?? 0,
      "Due today": info?.due_today ?? 0,
      "In review": info?.total ?? 0,
      Learned: info?.learned ?? 0,
    };
  }
  return {
    "Due now": review.stats.due_now,
    "Due today": review.stats.due_today,
    Learning: review.stats.learning,
    "Reviewed today": review.stats.reviewed_today,
  };
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

    <!-- Practice-mode banner, above the card so it stays visible in focus
         mode. -->
    <div
      v-if="review.practiceMode"
      class="mb-6 flex items-start gap-3 rounded-md border border-amber-300/60 bg-amber-50/70 px-4 py-3 text-sm text-amber-800 dark:border-amber-700/50 dark:bg-amber-500/10 dark:text-amber-200"
      role="status"
    >
      <span aria-hidden="true">🎯</span>
      <div class="flex-1 leading-snug">
        <p class="font-medium">Practice mode — nothing is graded.</p>
        <p class="text-xs opacity-80">
          Grading here doesn't change your reviews: due dates, streak and
          stats stay as they are. End practice any time to return to your
          list.
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
        @click="review.retry()"
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
    <ScopeBanner
      v-if="auth.isAuthed && review.scope"
      :scope="review.scope"
      :info="review.scopeInfo"
      :can-go-back="scopeText !== null"
      @back="backToText"
      @clear="clearScope"
    />

    <!-- 7-day activity sparkline, above the counter strip. -->
    <WeeklySparkline v-if="auth.isAuthed && !focusMode && !review.scope" class="mb-4" />

    <!-- Stats strip; smaller numbers on mobile. -->
    <StatTiles v-if="auth.isAuthed && !focusMode" :tiles="statTiles" />

    <!-- Daily-target progress. Hidden when the target is 0 (auto-enrol
         off in Settings). -->
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

    <!-- Start screen. Mixed mode is the default button; the four single
         modes sit behind an Advanced disclosure. -->
    <ReviewStart
      v-if="auth.isAuthed && review.queue.length === 0 && !review.loading"
      v-model:advanced-open="advancedOpen"
      :due-count="effectiveDueCount"
      :scoped="review.scope !== null"
      :single-mode="settings.reviewSingleMode"
      :in-rotation="review.stats.in_rotation"
      @start-mixed="startMixed"
      @start-single="startSingle"
      @switch-to-mixed="switchToMixed"
    />

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
        <!-- Intro stage, for new cards: hanzi, pinyin, meaning, stroke
             animation, TTS. "Got it" moves on to the trace stage. -->
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
            :focus="cardFocus"
            headline-class="font-display text-base leading-snug text-fg"
          />
          <WordDetails :word="card.word" class="mx-auto mt-3 max-w-md" />
          <ContextSentence
            v-if="card.cloze_sentence"
            :sentence="card.cloze_sentence"
            :word="card.word"
            :source="card.sentence_source"
          />

          <!-- Stroke animation, restarted per card by :key. For multi-char
               words auto-advance draws every character in turn. -->
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

        <!-- Trace stage: pinyin + meaning above the canvas, the user writes
             the hanzi in hanzi-writer's stroke quiz. TTS plays on mount.
             The outline follows the user's setting. -->
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
              :glosses="customGlosses(card.glosses, cardFocus)"
              :focus="cardFocus"
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

        <!-- Produce stage: no outline and no TTS; the hanzi comes from
             pinyin + meaning alone. -->
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
              :glosses="customGlosses(card.glosses, cardFocus)"
              :focus="cardFocus"
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
          <p
            class="font-cn-serif leading-none text-fg sm:text-7xl"
            :class="revealed ? 'mt-2 text-5xl' : 'mt-4 text-6xl'"
          >
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
          <RevealedAnswer v-else :card="card" :focus="cardFocus">
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
          </RevealedAnswer>
        </template>

        <!-- Recognition mode -->
        <template v-else-if="activeSurface === 'recognition'">
          <p
            v-if="card.hsk_level"
            class="mb-4 font-mono text-[10px] uppercase tracking-wider text-fg-subtle"
          >
            {{ formatHskLevel(card.hsk_level) }}
          </p>
          <p
            class="font-cn-serif leading-none text-fg sm:text-7xl"
            :class="revealed ? 'text-5xl' : 'text-6xl'"
          >
            {{ card.word }}
          </p>
          <RevealedAnswer v-if="revealed" :card="card" :focus="cardFocus" />

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
              :focus="cardFocus"
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
            :glosses="customGlosses(card.glosses, cardFocus)"
            :focus="cardFocus"
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
              :focus="cardFocus"
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

      <!-- Grade row (see gradeRowVisible). On a phone it sticks to the
           bottom of the screen, so a long sentence above can't push it
           out of view. -->
      <div
        v-if="gradeRowVisible"
        class="sticky bottom-0 z-10 -mx-3 grid grid-cols-4 gap-2 bg-bg/95 px-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] pt-2 backdrop-blur sm:static sm:mx-0 sm:bg-transparent sm:p-0 sm:backdrop-blur-none"
      >
        <button
          v-for="b in GRADE_BUTTONS"
          :key="b.grade"
          type="button"
          :disabled="review.grading"
          :class="[
            'relative overflow-hidden rounded-lg border border-border bg-bg-elevated px-3 py-3 transition-colors',
            b.hover,
            'disabled:opacity-50',
            b.darkHover,
            autoGradePending === b.grade ? b.ring : '',
          ]"
          @click="gradeAndAdvance(b.grade)"
        >
          <span
            v-if="autoGradePending === b.grade"
            :style="{ animationDuration: `${autoGradeDelayMs}ms` }"
            :class="['qd-auto-grade-progress absolute inset-x-0 bottom-0 h-0.5', b.bar]"
          />

          <p :class="['font-display text-base font-medium', b.text]">
            {{ b.label }}
          </p>
          <p
            class="mt-0.5 font-mono text-[9px] uppercase tracking-wider text-fg-subtle"
          >
            {{ gradeCaption(b.grade) }}
          </p>
        </button>
      </div>
    </div>

    <!-- Session complete -->
    <SessionComplete
      v-else-if="
        auth.isAuthed && review.sessionGraded > 0 && review.queue.length > 0
      "
      :graded="review.sessionGraded"
      :due="effectiveDueCount"
      :can-go-back="scopeText !== null"
      @continue="start(review.queueMode)"
      @back="backToText"
      @done="review.reset()"
    />
  </section>
</template>

<style scoped>
/* Auto-grade countdown bar along the bottom of the suggested grade button.
 * The inline animation-duration matches the auto-grade timeout. */

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
