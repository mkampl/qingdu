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
import { useRouter } from "vue-router";

import * as api from "@/api/client";
import type { QueueMode, ReviewGrade, ReviewMode } from "@/api/client";
import ClozeMode from "@/components/review/ClozeMode.vue";
import DictationMode from "@/components/review/DictationMode.vue";
import GradeRow from "@/components/review/GradeRow.vue";
import IntroStage from "@/components/review/IntroStage.vue";
import PracticeBanner from "@/components/review/PracticeBanner.vue";
import ReadStage from "@/components/review/ReadStage.vue";
import RecognitionMode from "@/components/review/RecognitionMode.vue";
import ReviewErrorBanner from "@/components/review/ReviewErrorBanner.vue";
import ReviewSignIn from "@/components/review/ReviewSignIn.vue";
import ReviewStart from "@/components/review/ReviewStart.vue";
import ReviewStats from "@/components/review/ReviewStats.vue";
import ScopeBanner from "@/components/review/ScopeBanner.vue";
import SessionComplete from "@/components/review/SessionComplete.vue";
import SessionHeader from "@/components/review/SessionHeader.vue";
import WritingMode from "@/components/review/WritingMode.vue";
import WritingStage from "@/components/review/WritingStage.vue";
import { useAutoGrade } from "@/composables/use-auto-grade";
import { useReviewCard } from "@/composables/use-review-card";
import { useReviewScope } from "@/composables/use-review-scope";
import { useTtsPlayer } from "@/composables/use-tts-player";
import { leadGloss } from "@/utils/glosses";
import { useAuthStore } from "@/stores/auth";
import { useReviewStore } from "@/stores/review";
import { useSettingsStore } from "@/stores/settings";
import { success as hapticSuccess, tap as hapticTap } from "@/services/native";
import {
  autoGradeDelayFor,
  autoGradeForWriting,
  DICTATION_GRADE,
  reviewShortcutBlocked,
  suggestedGradeForMistakes,
  surfaceMode,
} from "@/utils/review";

const review = useReviewStore();
const router = useRouter();
const { canGoBack, clearScope, backToText } = useReviewScope();

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
const settings = useSettingsStore();

const { loading: ttsLoading, play: playAudio, cancel: cancelTts } = useTtsPlayer();

const card = computed(() => review.current);
const {
  surface: activeSurface,
  firstEncounter,
  gradeRowVisible,
  revealed,
  readInput,
  readVerdict,
  dictationInput,
  dictationFeedback,
  clozeInput,
  clozeFeedback,
  writingMistakes,
  writingStrokes,
  writingDone,
  introReady,
  reset: resetCard,
  reveal,
  revealRead: revealReadAnswer,
  submitDictation,
  submitCloze,
  onWritingComplete,
} = useReviewCard(card, () => review.queueMode);
// The meaning the card leads with: the focused text's or list's, else the
// learner's own (glossary, then a text's, then a package's), else none
// (the dictionary's headline leads).
const cardFocus = computed(() => card.value?.focus_gloss ?? leadGloss(card.value?.glosses));
const cardKey = computed(() => `${card.value?.word}-${review.cursor}`);

// After the writing quiz completes, the suggested grade fires after a
// delay (Settings → Review → Auto-grade after writing; 0 = off). Clicking
// any grade or tapping the card cancels it.
const autoGradeDelayMs = computed(() =>
  autoGradeDelayFor(settings.autoGradeDelayMs, card.value?.cloze_sentence),
);
const {
  pending: autoGradePending,
  schedule: scheduleAutoGrade,
  cancel: cancelAutoGrade,
} = useAutoGrade(autoGradeDelayMs, (g) => void gradeAndAdvance(g));

// Per-card UI state. Cleared whenever the card on screen changes (new
// session, next card, re-inserted card) — see the review.current watcher.
function resetCardState() {
  cancelAutoGrade();
  resetCard();
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

// The word's audio only plays on the read stage once the answer is out.
function revealRead() {
  if (revealReadAnswer()) void playTts();
}

// A new playTts() stops the previous clip (no echo). cancelTts() runs when
// the card changes, so a late fetch doesn't play the previous card's audio
// over the current one; the player also cancels on unmount.
async function playTts() {
  if (!card.value) return;
  const word = card.value.word;
  await playAudio(() => api.tts(word));
}

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

async function gradeAndAdvance(g: ReviewGrade) {
  if (!card.value) return;
  // Light tap for Again/Hard, stronger feedback for Good/Easy.
  if (g >= 3) hapticSuccess(settings.hapticsEnabled);
  else hapticTap(settings.hapticsEnabled);
  cancelAutoGrade();
  // On success the cursor moves and the review.current watcher resets
  // the per-card state. On failure the card stays as it is, with the
  // error banner offering a retry.
  await review.grade(g, surfaceMode(activeSurface.value));
}

async function dictationContinue() {
  // The user can override with the explicit grade row after the answer
  // is revealed.
  await gradeAndAdvance(DICTATION_GRADE[dictationFeedback.value]);
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
watch(focusMode, (v) => {
  review.inFocus = v;
});

onBeforeUnmount(() => {
  cancelAutoGrade();
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
    <PracticeBanner v-if="review.practiceMode" @end="endPractice" />

    <ReviewErrorBanner v-if="auth.isAuthed && review.error" />

    <ReviewSignIn v-if="!auth.isAuthed" />

    <!-- Focused session: only the words of one text or vocab list. -->
    <ScopeBanner
      v-if="auth.isAuthed && review.scope"
      :scope="review.scope"
      :info="review.scopeInfo"
      :can-go-back="canGoBack"
      @back="backToText"
      @clear="clearScope"
    />

    <ReviewStats v-if="auth.isAuthed && !focusMode" />

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
      <SessionHeader
        :surface="activeSurface"
        :cursor="review.cursor"
        :total="review.queue.length"
        :practice="review.practiceMode"
        @end="review.practiceMode ? endPractice() : review.reset()"
      />

      <!-- Card -->
      <div
        class="rounded-2xl border border-border-subtle bg-bg-elevated px-4 py-6 text-center sm:px-10 sm:py-14"
        @pointerdown="cancelAutoGrade"
      >
        <IntroStage
          v-if="activeSurface === 'intro'"
          :card="card"
          :focus="cardFocus"
          :card-key="cardKey"
          @continue="introReady = true"
        />
        <WritingStage
          v-else-if="activeSurface === 'trace' || activeSurface === 'produce'"
          :stage="activeSurface"
          :card="card"
          :focus="cardFocus"
          :card-key="cardKey"
          :show-outline="activeSurface === 'trace' && settings.writingShowOutline"
          :mistakes="writingMistakes"
          :strokes="writingStrokes"
          :done="writingDone"
          :first-encounter="firstEncounter"
          @complete="onWritingComplete"
        />
        <ReadStage
          v-else-if="activeSurface === 'read'"
          v-model="readInput"
          :card="card"
          :focus="cardFocus"
          :revealed="revealed"
          :verdict="readVerdict"
          @reveal="revealRead"
        />
        <RecognitionMode
          v-else-if="activeSurface === 'recognition'"
          :card="card"
          :focus="cardFocus"
          :revealed="revealed"
          @reveal="reveal"
        />
        <DictationMode
          v-else-if="activeSurface === 'dictation'"
          v-model="dictationInput"
          :card="card"
          :focus="cardFocus"
          :feedback="dictationFeedback"
          :tts-loading="ttsLoading"
          @play="playTts"
          @submit="submitDictation"
          @continue="dictationContinue"
        />
        <WritingMode
          v-else-if="activeSurface === 'writing'"
          :card="card"
          :focus="cardFocus"
          :card-key="cardKey"
          :mistakes="writingMistakes"
          :strokes="writingStrokes"
          :done="writingDone"
          @complete="onWritingComplete"
        />
        <ClozeMode
          v-else-if="activeSurface === 'cloze'"
          v-model="clozeInput"
          :card="card"
          :focus="cardFocus"
          :feedback="clozeFeedback"
          @submit="submitCloze"
        />
      </div>

      <!-- Grade row (see gradeRowVisible). -->
      <GradeRow
        v-if="gradeRowVisible"
        :intervals="card.intervals"
        :practice="review.practiceMode"
        :disabled="review.grading"
        :pending="autoGradePending"
        :delay-ms="autoGradeDelayMs"
        @grade="gradeAndAdvance"
      />
    </div>

    <!-- Session complete -->
    <SessionComplete
      v-else-if="
        auth.isAuthed && review.sessionGraded > 0 && review.queue.length > 0
      "
      :graded="review.sessionGraded"
      :due="effectiveDueCount"
      :can-go-back="canGoBack"
      @continue="start(review.queueMode)"
      @back="backToText"
      @done="review.reset()"
    />
  </section>
</template>
