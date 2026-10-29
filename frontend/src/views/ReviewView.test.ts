import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "@/api/client";
import type { ReviewCard } from "@/api/client";
import { useAuthStore } from "@/stores/auth";
import { useReviewStore } from "@/stores/review";
import { useSettingsStore } from "@/stores/settings";

vi.mock("vue-router", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useRoute: () => ({ query: {} }),
}));
vi.mock("@/services/notifications", () => ({
  rememberDueCount: vi.fn(),
  rememberStreak: vi.fn(),
  rememberActiveToday: vi.fn(),
}));

import ReviewView from "./ReviewView.vue";

function card(word: string, stage: string, extra: Partial<ReviewCard> = {}): ReviewCard {
  return {
    word,
    pinyin: "yī",
    meaning: "one",
    meanings: [],
    hsk_level: "new-3",
    stability: null,
    difficulty: null,
    due_at: null,
    prompt_stage: stage,
    has_sample_sentence: false,
    ...extra,
  } as ReviewCard;
}

const STATS = {
  due_now: 1,
  due_today: 1,
  due_in_window: 1,
  learning: 1,
  in_rotation: 1,
  reviewed_today: 0,
  new_today: 0,
  daily_target: 0,
};

function mountView() {
  return mount(ReviewView, {
    global: {
      stubs: {
        WeeklySparkline: true,
        StrokeOrder: true,
        WritingQuiz: true,
        MeaningTags: true,
      },
    },
  });
}

describe("ReviewView", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    useAuthStore().user = { username: "a", review_window: "today" } as never;
    vi.spyOn(api, "getReviewStats").mockResolvedValue({ ...STATS });
    vi.spyOn(api, "getWordStats").mockResolvedValue({} as never);
    vi.spyOn(api, "tts").mockResolvedValue(new Response("x"));
  });
  afterEach(() => {
    vi.restoreAllMocks();
    document.body.innerHTML = "";
  });

  it("starts the next session's intro card on the intro, not on trace", async () => {
    const queue = vi
      .spyOn(api, "getReviewQueue")
      .mockResolvedValue({ mode: "mixed", cards: [card("一", "intro")] });
    const w = mountView();
    await flushPromises();
    await w.find("button.group").trigger("click"); // Start review
    await flushPromises();
    expect(w.text()).toContain("Got it");
    await w.findAll("button").find((b) => b.text().startsWith("Got it"))!.trigger("click");
    expect(w.text()).toMatch(/Trace/i);
    await w.findAll("button").find((b) => b.text() === "End session")!.trigger("click");
    await flushPromises();
    await w.find("button.group").trigger("click");
    await flushPromises();
    expect(queue).toHaveBeenCalledTimes(2);
    expect(w.text()).toContain("Got it");
  });

  it("shows a grade failure with a retry that re-sends the grade", async () => {
    vi.spyOn(api, "getReviewQueue").mockResolvedValue({
      mode: "recognition",
      cards: [card("一", "produce"), card("二", "produce")],
    });
    const gradeSpy = vi
      .spyOn(api, "gradeReviewCard")
      .mockRejectedValueOnce(new Error("Network down"))
      .mockResolvedValueOnce({
        word: "一",
        due_at: "2099-01-01T00:00:00Z",
        stability: 20,
        difficulty: 5,
        prompt_stage: "produce",
      });
    const review = useReviewStore();
    const w = mountView();
    await review.loadQueue("recognition");
    await flushPromises();
    // Recognition card: the HSK level is shown formatted.
    expect(w.text()).toContain("HSK 3");
    expect(w.text()).not.toContain("new-3");
    await w.findAll("button").find((b) => b.text().startsWith("Show answer"))!.trigger("click");
    await w.findAll("button").find((b) => b.text().startsWith("Good"))!.trigger("click");
    await flushPromises();
    expect(w.find('[role="alert"]').text()).toContain("Network down");
    // The card is still there, answer still revealed.
    expect(w.text()).toContain("card 1 / 2");
    await w.findAll("button").find((b) => b.text() === "Retry")!.trigger("click");
    await flushPromises();
    expect(gradeSpy).toHaveBeenCalledTimes(2);
    expect(w.find('[role="alert"]').exists()).toBe(false);
    expect(w.text()).toContain("card 2 / 2");
  });

  it("ignores grade shortcuts while a dialog is open", async () => {
    vi.spyOn(api, "getReviewQueue").mockResolvedValue({
      mode: "recognition",
      cards: [card("一", "produce")],
    });
    const gradeSpy = vi.spyOn(api, "gradeReviewCard");
    const review = useReviewStore();
    const w = mountView();
    await review.loadQueue("recognition");
    await flushPromises();
    await w.findAll("button").find((b) => b.text().startsWith("Show answer"))!.trigger("click");
    const dialog = document.createElement("div");
    dialog.setAttribute("aria-modal", "true");
    document.body.appendChild(dialog);
    window.dispatchEvent(new KeyboardEvent("keydown", { key: "3" }));
    await flushPromises();
    expect(gradeSpy).not.toHaveBeenCalled();
    w.unmount();
  });

  it("drops TTS that resolves after the view is gone", async () => {
    let resolveTts: (r: Response) => void = () => {};
    vi.spyOn(api, "tts").mockImplementation(
      () => new Promise<Response>((r) => (resolveTts = r)),
    );
    const played = vi.fn(() => Promise.resolve());
    vi.stubGlobal(
      "Audio",
      class {
        play = played;
        pause() {}
        addEventListener() {}
        currentTime = 0;
      },
    );
    vi.spyOn(api, "getReviewQueue").mockResolvedValue({
      mode: "mixed",
      cards: [card("一", "intro")],
    });
    const review = useReviewStore();
    const w = mountView();
    await review.loadQueue("mixed");
    await flushPromises();
    expect(api.tts).toHaveBeenCalledWith("一");
    w.unmount();
    resolveTts(new Response("audio"));
    await flushPromises();
    expect(played).not.toHaveBeenCalled();
    vi.unstubAllGlobals();
  });

  it("uses the auto-grade delay setting; Off never auto-grades", async () => {
    vi.useFakeTimers();
    try {
      useSettingsStore().autoGradeDelayMs = 0;
      vi.spyOn(api, "getReviewQueue").mockResolvedValue({
        mode: "writing",
        cards: [card("一", "produce")],
      });
      const gradeSpy = vi.spyOn(api, "gradeReviewCard");
      const review = useReviewStore();
      const w = mountView();
      await review.loadQueue("writing");
      await flushPromises();
      w.findComponent({ name: "WritingQuiz" }).vm.$emit("complete", {
        totalMistakes: 0,
        totalStrokes: 1,
        skipped: false,
      });
      await vi.advanceTimersByTimeAsync(5000);
      expect(gradeSpy).not.toHaveBeenCalled();
      w.unmount();
    } finally {
      vi.useRealTimers();
    }
  });

  it("grades a clean first pass after the intro Good, not Easy", async () => {
    vi.useFakeTimers();
    try {
      useSettingsStore().autoGradeDelayMs = 1000;
      vi.spyOn(api, "getReviewQueue").mockResolvedValue({
        mode: "mixed",
        cards: [card("一", "intro")],
      });
      const gradeSpy = vi
        .spyOn(api, "gradeReviewCard")
        .mockResolvedValue({ word: "一", due_at: null, stability: 2.3, difficulty: 5 } as never);
      const review = useReviewStore();
      const w = mountView();
      await review.loadQueue("mixed");
      await flushPromises();
      await w.findAll("button").find((b) => b.text().startsWith("Got it"))!.trigger("click");
      w.findComponent({ name: "WritingQuiz" }).vm.$emit("complete", {
        totalMistakes: 0,
        totalStrokes: 1,
        skipped: false,
      });
      await flushPromises();
      expect(w.text()).toContain("First look");
      await vi.advanceTimersByTimeAsync(1500);
      expect(gradeSpy).toHaveBeenCalledWith("一", 3, "writing");
      w.unmount();
    } finally {
      vi.useRealTimers();
    }
  });

  it("read stage: hanzi only, typed pinyin checked, audio after the reveal", async () => {
    vi.spyOn(api, "getReviewQueue").mockResolvedValue({
      mode: "mixed",
      cards: [card("一", "read", { stability: 3 })],
    });
    const gradeSpy = vi
      .spyOn(api, "gradeReviewCard")
      .mockResolvedValue({ word: "一", due_at: null, stability: 9, difficulty: 5 } as never);
    const review = useReviewStore();
    const w = mountView();
    await review.loadQueue("mixed");
    await flushPromises();

    expect(w.text()).toMatch(/Read · stability 3d/i);
    expect(w.text()).not.toContain("yī");
    expect(api.tts).not.toHaveBeenCalled();

    const input = w.find('input[placeholder^="Pinyin"]');
    await input.setValue("yi1");
    await input.trigger("keydown", { key: "Enter" });
    await flushPromises();
    expect(w.text()).toContain("Right, tones too");
    expect(w.text()).toContain("yī");
    expect(api.tts).toHaveBeenCalledWith("一");

    await w.findAll("button").find((b) => b.text().startsWith("Good"))!.trigger("click");
    await flushPromises();
    expect(gradeSpy).toHaveBeenCalledWith("一", 3, "recognition");
  });
});
