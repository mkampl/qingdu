process.env.TZ = "America/New_York";

import { createPinia, setActivePinia } from "pinia";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "@/api/client";
import type { ReviewCard } from "@/api/client";
import { useReviewStore } from "@/stores/review";

vi.mock("@/services/notifications", () => ({
  rememberDueCount: vi.fn(),
  rememberStreak: vi.fn(),
}));

function card(word: string): ReviewCard {
  return {
    word,
    pinyin: "",
    meaning: "",
    meanings: [],
    hsk_level: null,
    stability: null,
    difficulty: null,
    due_at: null,
    prompt_stage: "intro",
    has_sample_sentence: false,
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

describe("review store", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    vi.spyOn(api, "getReviewStats").mockResolvedValue({ ...STATS });
    vi.spyOn(api, "getWordStats").mockResolvedValue({} as never);
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("re-inserts an Again card although due_at arrives as naive UTC", async () => {
    const review = useReviewStore();
    review.queue = [card("一")];
    // One minute from now, written the way older servers do (no offset).
    const soon = new Date(Date.now() + 60_000).toISOString().replace("Z", "");
    vi.spyOn(api, "gradeReviewCard").mockResolvedValue({
      word: "一",
      due_at: soon,
      stability: 0.2,
      difficulty: 5,
      prompt_stage: "intro",
    });
    expect(await review.grade(1, "writing")).toBe(true);
    expect(review.queue.map((c) => c.word)).toEqual(["一", "一"]);
    expect(review.current?.word).toBe("一");
  });

  it("keeps the card and exposes a retryable error when grading fails", async () => {
    const review = useReviewStore();
    review.queue = [card("一")];
    const gradeSpy = vi
      .spyOn(api, "gradeReviewCard")
      .mockRejectedValueOnce(new Error("Network down"))
      .mockResolvedValueOnce({
        word: "一",
        due_at: "2099-01-01T00:00:00Z",
        stability: 3,
        difficulty: 5,
        prompt_stage: "trace",
      });

    expect(await review.grade(3, "writing")).toBe(false);
    expect(review.error).toBe("Network down");
    expect(review.errorKind).toBe("grade");
    expect(review.cursor).toBe(0);

    expect(await review.retry()).toBe(true);
    expect(gradeSpy).toHaveBeenLastCalledWith("一", 3, "writing");
    expect(review.error).toBeNull();
    expect(review.cursor).toBe(1);
  });

  it("reports an empty queue instead of silently showing the start screen", async () => {
    vi.spyOn(api, "getReviewQueue").mockResolvedValue({ mode: "cloze", cards: [] });
    const review = useReviewStore();
    await review.loadQueue("cloze");
    expect(review.errorKind).toBe("empty");
    expect(review.error).toMatch(/saved text/);
  });

  it("applies only the newest stats response", async () => {
    let resolveFirst: (v: typeof STATS) => void = () => {};
    vi.spyOn(api, "getReviewStats")
      .mockImplementationOnce(() => new Promise((r) => (resolveFirst = r)))
      .mockResolvedValueOnce({ ...STATS, due_in_window: 7 });
    const review = useReviewStore();
    const first = review.refreshStats();
    await review.refreshStats();
    resolveFirst({ ...STATS, due_in_window: 99 });
    await first;
    expect(review.stats.due_in_window).toBe(7);
  });

  it("reads the badge count from due_in_window", async () => {
    const review = useReviewStore();
    review.stats = { ...STATS, due_today: 3, due_in_window: 8 };
    expect(review.dueNow).toBe(8);
  });
});
