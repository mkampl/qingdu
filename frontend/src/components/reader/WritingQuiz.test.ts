import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";

// Minimal hanzi-writer stand-in: every char has 4 strokes, and the test
// drives quiz completion through the captured onComplete callbacks.
const quizzes: Array<{ onComplete: (info: { totalMistakes: number }) => void }> = [];
vi.mock("hanzi-writer", () => ({
  default: {
    loadCharacterData: vi.fn(async () => ({ strokes: ["a", "b", "c", "d"] })),
    create: vi.fn(() => ({
      quiz: (opts: { onComplete: (info: { totalMistakes: number }) => void }) => {
        quizzes.push(opts);
      },
      cancelQuiz: vi.fn(),
      animateCharacter: (o?: { onComplete?: () => void }) => o?.onComplete?.(),
    })),
  },
}));

import WritingQuiz from "./WritingQuiz.vue";

type Payload = { totalMistakes: number; totalStrokes: number; skipped: boolean };

describe("WritingQuiz stroke accounting", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    quizzes.length = 0;
  });

  it("counts a char's strokes once even when the writer is rebuilt", async () => {
    const w = mount(WritingQuiz, { props: { word: "一", showOutline: false } });
    await flushPromises();
    // Outline toggle re-creates the writer for the same char.
    await w.setProps({ showOutline: true });
    await flushPromises();
    await w.setProps({ showOutline: false });
    await flushPromises();
    expect(quizzes.length).toBe(3);
    quizzes[quizzes.length - 1].onComplete({ totalMistakes: 1 });
    const [payload] = w.emitted("complete")![0] as [Payload];
    expect(payload).toEqual({ totalMistakes: 1, totalStrokes: 4, skipped: false });
  });

  it("scores a skipped char as all strokes wrong", async () => {
    const w = mount(WritingQuiz, { props: { word: "你好" } });
    await flushPromises();
    quizzes[0].onComplete({ totalMistakes: 0 });
    await new Promise((r) => setTimeout(r, 750)); // linger before next char
    await flushPromises();
    const skip = w.findAll("button").find((b) => b.text() === "Skip");
    await skip!.trigger("click");
    const [payload] = w.emitted("complete")![0] as [Payload];
    expect(payload).toEqual({ totalMistakes: 4, totalStrokes: 8, skipped: true });
  });
});
