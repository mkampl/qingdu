import { ref } from "vue";
import { describe, expect, it } from "vitest";

import type { QueueMode, ReviewCard } from "@/api/client";
import { useReviewCard } from "./use-review-card";

function setup(stage: string, mode: QueueMode = "mixed") {
  const card = ref({ word: "妈", pinyin: "mā", prompt_stage: stage } as ReviewCard);
  return useReviewCard(card, () => mode);
}

describe("useReviewCard", () => {
  it("read stage: reveal checks the typed pinyin once and opens the grade row", () => {
    const c = setup("read");
    expect(c.gradeRowVisible.value).toBe(false);
    c.readInput.value = "ma1";
    expect(c.revealRead()).toBe(true);
    expect(c.readVerdict.value).toBe("exact");
    expect(c.gradeRowVisible.value).toBe(true);
    expect(c.revealRead()).toBe(false);
  });

  it("intro swaps to trace on Got it; the grade row waits for the quiz", () => {
    const c = setup("intro");
    c.introReady.value = true;
    expect(c.surface.value).toBe("trace");
    expect(c.firstEncounter.value).toBe(true);
    expect(c.gradeRowVisible.value).toBe(false);
    c.onWritingComplete({ totalMistakes: 1, totalStrokes: 6, skipped: false });
    expect(c.gradeRowVisible.value).toBe(true);
    c.reset();
    expect(c.surface.value).toBe("intro");
    expect(c.writingDone.value).toBe(false);
  });

  it("dictation and cloze ignore empty and repeated submits", () => {
    const d = setup("intro", "dictation");
    d.submitDictation();
    expect(d.dictationFeedback.value).toBe("");
    d.dictationInput.value = "ma";
    d.submitDictation();
    expect(d.dictationFeedback.value).toBe("toneless");
    d.dictationInput.value = "妈";
    d.submitDictation();
    expect(d.dictationFeedback.value).toBe("toneless");

    const z = setup("intro", "cloze");
    z.clozeInput.value = " 妈 ";
    z.submitCloze();
    expect(z.clozeFeedback.value).toBe("correct");
    expect(z.gradeRowVisible.value).toBe(true);
  });
});
