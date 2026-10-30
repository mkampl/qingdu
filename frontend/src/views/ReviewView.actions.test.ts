// Every button of the review screen reaches the handler it is meant for:
// the start screen, the scope banner, the grade row and the session end.
import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "@/api/client";
import type { ReviewCard } from "@/api/client";
import { useAuthStore } from "@/stores/auth";
import { useReviewStore } from "@/stores/review";
import { useSettingsStore } from "@/stores/settings";

const route = vi.hoisted(() => ({ query: {} as Record<string, string> }));
const replace = vi.hoisted(() => vi.fn());
const openSaved = vi.hoisted(() => vi.fn());

vi.mock("vue-router", () => ({
  useRouter: () => ({ push: vi.fn(), replace }),
  useRoute: () => route,
}));
vi.mock("@/services/notifications", () => ({
  rememberDueCount: vi.fn(),
  rememberStreak: vi.fn(),
}));
vi.mock("@/composables/use-open-saved-text", () => ({
  useOpenSavedText: () => openSaved,
}));

import ReviewView from "./ReviewView.vue";

function card(word: string): ReviewCard {
  return {
    word,
    pinyin: "yī",
    meaning: "one",
    meanings: [],
    hsk_level: "new-3",
    stability: null,
    difficulty: null,
    due_at: null,
    prompt_stage: "produce",
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

function mountView() {
  return mount(ReviewView, {
    global: {
      stubs: {
        WeeklySparkline: true,
        StrokeOrder: true,
        WritingQuiz: true,
        MeaningTags: true,
        RouterLink: { props: ["to"], template: '<a :href="to"><slot /></a>' },
      },
    },
  });
}

function button(w: VueWrapper, text: string | RegExp) {
  const b = w
    .findAll("button")
    .find((x) => (typeof text === "string" ? x.text() === text : text.test(x.text())));
  if (!b) throw new Error(`no button ${text}`);
  return b;
}

const GRADED = { word: "一", due_at: null, stability: 2, difficulty: 5 } as never;

describe("ReviewView actions", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    route.query = {};
    replace.mockReset();
    openSaved.mockReset().mockResolvedValue(true);
    useAuthStore().user = { username: "a", review_window: "today" } as never;
    vi.spyOn(api, "getReviewStats").mockResolvedValue({ ...STATS });
    vi.spyOn(api, "getWordStats").mockResolvedValue({} as never);
    vi.spyOn(api, "tts").mockResolvedValue(new Response("x"));
  });
  afterEach(() => {
    vi.restoreAllMocks();
    document.body.innerHTML = "";
  });

  it.each([
    ["Again", 1],
    ["Hard", 2],
    ["Good", 3],
    ["Easy", 4],
  ] as const)("the %s button grades %i", async (label, grade) => {
    vi.spyOn(api, "getReviewQueue").mockResolvedValue({
      mode: "recognition",
      cards: [card("一")],
    });
    const gradeSpy = vi.spyOn(api, "gradeReviewCard").mockResolvedValue(GRADED);
    const w = mountView();
    await useReviewStore().loadQueue("recognition");
    await flushPromises();
    await button(w, /^Show answer/).trigger("click");
    await button(w, new RegExp(`^${label}`)).trigger("click");
    await flushPromises();
    expect(gradeSpy).toHaveBeenCalledExactlyOnceWith("一", grade, "recognition");
    w.unmount();
  });

  it("disables the grade row while a grade is in flight", async () => {
    vi.spyOn(api, "getReviewQueue").mockResolvedValue({
      mode: "recognition",
      cards: [card("一"), card("二")],
    });
    let done: (v: never) => void = () => {};
    vi.spyOn(api, "gradeReviewCard").mockImplementation(
      () => new Promise((r) => (done = r)),
    );
    const w = mountView();
    await useReviewStore().loadQueue("recognition");
    await flushPromises();
    await button(w, /^Show answer/).trigger("click");
    await button(w, /^Good/).trigger("click");
    for (const l of ["Again", "Hard", "Good", "Easy"]) {
      expect(button(w, new RegExp(`^${l}`)).attributes("disabled")).toBeDefined();
    }
    done(GRADED);
    await flushPromises();
    w.unmount();
  });

  it("number keys grade with the same numbers as the buttons", async () => {
    vi.spyOn(api, "getReviewQueue").mockResolvedValue({
      mode: "recognition",
      cards: [card("一")],
    });
    const gradeSpy = vi.spyOn(api, "gradeReviewCard").mockResolvedValue(GRADED);
    const w = mountView();
    await useReviewStore().loadQueue("recognition");
    await flushPromises();
    window.dispatchEvent(new KeyboardEvent("keydown", { key: " " }));
    await flushPromises();
    expect(w.text()).toContain("Again");
    window.dispatchEvent(new KeyboardEvent("keydown", { key: "2" }));
    await flushPromises();
    expect(gradeSpy).toHaveBeenCalledExactlyOnceWith("一", 2, "recognition");
    w.unmount();
  });

  it("auto-grade: countdown bar on the suggested button, a tap cancels it", async () => {
    vi.useFakeTimers();
    try {
      useSettingsStore().autoGradeDelayMs = 1000;
      vi.spyOn(api, "getReviewQueue").mockResolvedValue({
        mode: "writing",
        cards: [card("一")],
      });
      const gradeSpy = vi.spyOn(api, "gradeReviewCard").mockResolvedValue(GRADED);
      const w = mountView();
      await useReviewStore().loadQueue("writing");
      await flushPromises();
      w.findComponent({ name: "WritingQuiz" }).vm.$emit("complete", {
        totalMistakes: 0,
        totalStrokes: 1,
        skipped: false,
      });
      await flushPromises();
      const bars = w.findAll(".qd-auto-grade-progress");
      expect(bars).toHaveLength(1);
      const pending = bars[0].element.closest("button")!;
      expect(pending.className).toMatch(/ring-2/);
      expect(bars[0].attributes("style")).toMatch(/animation-duration: \d+ms/);
      // A tap anywhere on the card cancels the countdown.
      await w.find("div.rounded-2xl").trigger("pointerdown");
      expect(w.findAll(".qd-auto-grade-progress")).toHaveLength(0);
      await vi.advanceTimersByTimeAsync(5000);
      expect(gradeSpy).not.toHaveBeenCalled();
      w.unmount();
    } finally {
      vi.useRealTimers();
    }
  });

  it("start screen: mixed, single modes and back to mixed", async () => {
    const queue = vi
      .spyOn(api, "getReviewQueue")
      .mockResolvedValue({ mode: "mixed", cards: [] });
    const settings = useSettingsStore();
    settings.reviewSingleMode = false;
    const w = mountView();
    await flushPromises();
    expect(w.find('a[href="/tones"]').exists()).toBe(true);
    await button(w, /^Start review/).trigger("click");
    await flushPromises();
    expect(queue).toHaveBeenLastCalledWith("mixed", 30, null);
    await button(w, /^Dictation/).trigger("click");
    await flushPromises();
    expect(queue).toHaveBeenLastCalledWith("dictation", 30, null);
    expect(settings.reviewSingleMode).toBe(true);
    expect(w.text()).toContain("Pick a mode to begin");
    expect((w.find("details").element as HTMLDetailsElement).open).toBe(true);
    await button(w, /Use Mixed mode/).trigger("click");
    await flushPromises();
    expect(queue).toHaveBeenLastCalledWith("mixed", 30, null);
    expect(settings.reviewSingleMode).toBe(false);
    w.unmount();
  });

  it("scope banner: back to text and all reviews", async () => {
    route.query = { text: "saved:7" };
    vi.mocked(api.getReviewStats).mockResolvedValue({
      ...STATS,
      scope: { title: "My text", due: 2, total: 5, due_now: 2 },
    } as never);
    const w = mountView();
    await flushPromises();
    expect(w.text()).toContain("My text");
    expect(w.text()).toContain("2 due · 5 words");
    expect(w.text()).toContain("Start these 2");
    expect(w.find("details").exists()).toBe(false);
    expect(w.find('a[href="/tones"]').exists()).toBe(false);
    await button(w, "← Back to text").trigger("click");
    await flushPromises();
    expect(openSaved).toHaveBeenCalledExactlyOnceWith(7);
    await button(w, "All reviews").trigger("click");
    expect(replace).toHaveBeenCalledWith({ path: "/review" });
    w.unmount();
  });

  it("scope banner: a pasted text has no way back", async () => {
    route.query = { text: "pasted:abc" };
    const w = mountView();
    await flushPromises();
    expect(w.text()).toContain("All reviews");
    expect(w.text()).not.toContain("Back to text");
    w.unmount();
  });

  it("session complete: continue, back to text, done", async () => {
    route.query = { text: "saved:7" };
    vi.mocked(api.getReviewStats).mockResolvedValue({
      ...STATS,
      scope: { title: "My text", due: 3, total: 5, due_now: 3 },
    } as never);
    const queue = vi.spyOn(api, "getReviewQueue").mockResolvedValue({
      mode: "dictation",
      cards: [card("一")],
    });
    vi.spyOn(api, "gradeReviewCard").mockResolvedValue(GRADED);
    const review = useReviewStore();
    const w = mountView();
    await flushPromises();
    await review.loadQueue("dictation");
    await flushPromises();
    await review.grade(3, "dictation");
    await flushPromises();
    expect(w.text()).toContain("Session complete.");
    expect(w.text()).toContain("1 card reviewed.");
    await button(w, /^Continue \(\d+\)$/).trigger("click");
    await flushPromises();
    expect(queue).toHaveBeenLastCalledWith("dictation", 30, { textKey: "saved:7" });

    await review.grade(3, "dictation");
    await flushPromises();
    await w.findAll("button").filter((b) => b.text() === "← Back to text").at(-1)!.trigger("click");
    await flushPromises();
    expect(openSaved).toHaveBeenCalledWith(7);

    await review.loadQueue("dictation");
    await review.grade(3, "dictation");
    await flushPromises();
    await button(w, "Done").trigger("click");
    expect(review.queue).toHaveLength(0);
    expect(review.sessionGraded).toBe(0);
    w.unmount();
  });
});
