import { computed, ref, type Ref } from "vue";

import type { QueueMode, ReviewCard } from "@/api/client";
import { checkPinyin, type PinyinVerdict } from "@/utils/pinyin-answer";
import {
  dictationVerdict,
  reviewSurface,
  type DictationFeedback,
} from "@/utils/review";

export interface WritingResult {
  totalMistakes: number;
  totalStrokes: number;
  skipped: boolean;
}

/**
 * The answer state of the card on screen: which surface it renders, what
 * the learner typed or wrote, and whether the grade row is due. `reset()`
 * clears it for the next card.
 */
export function useReviewCard(card: Ref<ReviewCard | null>, queueMode: () => QueueMode) {
  const revealed = ref(false);

  // Read stage: optional typed pinyin, checked on reveal.
  const readInput = ref("");
  const readVerdict = ref<"" | PinyinVerdict>("");

  const dictationInput = ref("");
  const dictationFeedback = ref<DictationFeedback>("");

  // The typed word is compared against card.word, which the server sends
  // in the user's display script.
  const clozeInput = ref("");
  const clozeFeedback = ref<"" | "correct" | "wrong">("");

  // Writing-quiz result for the card, turned into a suggested FSRS grade.
  const writingMistakes = ref(0);
  const writingStrokes = ref(0);
  const writingDone = ref(false);

  // Intro stage: "Got it" sets this and swaps the card to the trace surface.
  const introReady = ref(false);

  const surface = computed(() =>
    reviewSurface(queueMode(), card.value?.prompt_stage, introReady.value),
  );

  // The writing pass straight after the intro animation (see autoGradeForWriting).
  const firstEncounter = computed(() => card.value?.prompt_stage === "intro");

  // Grade row: after reveal in recognition / read, after an answer in
  // dictation / cloze, after a writing quiz completes. Intro never shows
  // it ('Got it' swaps to trace).
  const gradeRowVisible = computed(() => {
    const s = surface.value;
    return (
      ((s === "recognition" || s === "read") && revealed.value) ||
      (s === "dictation" && dictationFeedback.value !== "") ||
      (s === "cloze" && clozeFeedback.value !== "") ||
      ((s === "writing" || s === "trace" || s === "produce") && writingDone.value)
    );
  });

  function reset() {
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

  function reveal() {
    revealed.value = true;
  }

  /** Reveals the read stage's answer; false when there was nothing to reveal. */
  function revealRead(): boolean {
    if (!card.value || revealed.value) return false;
    const typed = readInput.value.trim();
    readVerdict.value = typed ? checkPinyin(typed, card.value.pinyin || "") : "";
    revealed.value = true;
    return true;
  }

  function submitDictation() {
    if (!card.value || dictationFeedback.value !== "") return;
    const guess = dictationInput.value.trim();
    if (!guess) return;
    dictationFeedback.value = dictationVerdict(guess, card.value.word, card.value.pinyin || "");
  }

  function submitCloze() {
    if (!card.value || clozeFeedback.value !== "") return;
    const guess = clozeInput.value.trim();
    if (!guess) return;
    clozeFeedback.value = guess === card.value.word ? "correct" : "wrong";
  }

  function onWritingComplete(payload: WritingResult) {
    writingMistakes.value = payload.totalMistakes;
    writingStrokes.value = payload.totalStrokes;
    writingDone.value = true;
  }

  return {
    surface,
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
    reset,
    reveal,
    revealRead,
    submitDictation,
    submitCloze,
    onWritingComplete,
  };
}
