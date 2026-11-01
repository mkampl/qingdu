process.env.TZ = "America/New_York";

import { afterEach, describe, expect, it } from "vitest";
import {
  autoGradeDelayFor,
  autoGradeForWriting,
  DICTATION_GRADE,
  dictationVerdict,
  dueCountForWindow,
  formatHskLevel,
  formatInterval,
  normalizeAutoGradeDelay,
  reviewShortcutBlocked,
  reviewSurface,
  shouldReinsert,
  suggestedGradeForMistakes,
  surfaceMode,
} from "./review";
import { emptyScores, scoreTotals, shownScore, skippedScore } from "./writing-score";

describe("shouldReinsert", () => {
  const now = Date.UTC(2026, 0, 15, 23, 0);

  it("re-inserts a card FSRS schedules a minute out (naive UTC from old servers)", () => {
    // Read as local time this would be 23:01 EST = five hours away.
    expect(shouldReinsert("2026-01-15T23:01:00", now)).toBe(true);
    expect(shouldReinsert("2026-01-15T23:01:00Z", now)).toBe(true);
  });

  it("leaves cards due later than the learning window alone", () => {
    expect(shouldReinsert("2026-01-15T23:30:00Z", now)).toBe(false);
    expect(shouldReinsert("2026-01-17T00:00:00Z", now)).toBe(false);
    expect(shouldReinsert(null, now)).toBe(false);
  });
});

describe("dueCountForWindow", () => {
  const stats = { due_now: 2, due_today: 5, due_in_window: 9 };

  it("uses the server's window count when present", () => {
    expect(dueCountForWindow(stats, "tomorrow")).toBe(9);
    expect(dueCountForWindow(stats, "now")).toBe(9);
  });

  it("falls back for servers without due_in_window", () => {
    expect(dueCountForWindow({ due_now: 2, due_today: 5 }, "now")).toBe(2);
    expect(dueCountForWindow({ due_now: 2, due_today: 5 }, "today")).toBe(5);
  });
});

describe("formatHskLevel", () => {
  it("never shows the raw level key", () => {
    expect(formatHskLevel("new-3")).toBe("HSK 3");
    expect(formatHskLevel("old-4")).toBe("HSK 4 (old)");
    expect(formatHskLevel("new-7-9")).toBe("HSK 7–9");
    expect(formatHskLevel(5)).toBe("HSK 5");
    expect(formatHskLevel(null)).toBe("");
  });
});

describe("auto-grade delay setting", () => {
  it("accepts the offered values and defaults to 2 s", () => {
    expect(normalizeAutoGradeDelay(0)).toBe(0);
    expect(normalizeAutoGradeDelay(3000)).toBe(3000);
    expect(normalizeAutoGradeDelay(undefined)).toBe(2000);
    expect(normalizeAutoGradeDelay(1234)).toBe(2000);
  });
});

describe("writing score", () => {
  it("skip is scored on the ratio scale", () => {
    // 2-char word: first char perfect (15 strokes), second skipped (15).
    const scores = emptyScores(2);
    scores[0] = { strokes: 15, mistakes: 0 };
    scores[1] = skippedScore(15);
    const t = scoreTotals(scores);
    expect(t).toEqual({ strokes: 30, mistakes: 15 });
    // Half the word unknown → Again. A flat +5 would give 5/30 → Hard.
    expect(suggestedGradeForMistakes(t.mistakes, t.strokes)).toBe(1);
    expect(suggestedGradeForMistakes(5, 30)).toBe(2);
  });

  it("show-me counts double and skipping a lone char is Again", () => {
    expect(scoreTotals([shownScore(4)])).toEqual({ strokes: 4, mistakes: 8 });
    const t = scoreTotals([skippedScore(1)]);
    expect(suggestedGradeForMistakes(t.mistakes, t.strokes)).toBe(1);
  });

  it("counts each char's strokes once however often the writer is rebuilt", () => {
    const scores = emptyScores(1);
    // Recording is assignment per char, so a re-init cannot double it.
    scores[0] = { ...scores[0], strokes: 8 };
    scores[0] = { ...scores[0], strokes: 8 };
    expect(scoreTotals(scores).strokes).toBe(8);
  });
});

describe("reviewShortcutBlocked", () => {
  afterEach(() => {
    document.body.innerHTML = "";
  });

  function key(k: string, target: EventTarget | null = document.body): KeyboardEvent {
    const e = new KeyboardEvent("keydown", { key: k });
    Object.defineProperty(e, "target", { value: target });
    return e;
  }

  it("lets digits and Space through on the bare page", () => {
    expect(reviewShortcutBlocked(key("3"))).toBe(false);
    expect(reviewShortcutBlocked(key(" "))).toBe(false);
  });

  it("ignores keys while a modal is open", () => {
    const dialog = document.createElement("div");
    dialog.setAttribute("aria-modal", "true");
    document.body.appendChild(dialog);
    expect(reviewShortcutBlocked(key("3"))).toBe(true);
  });

  it("leaves Space to a focused button but still takes digits", () => {
    const btn = document.createElement("button");
    document.body.appendChild(btn);
    expect(reviewShortcutBlocked(key(" ", btn))).toBe(true);
    expect(reviewShortcutBlocked(key("2", btn))).toBe(false);
  });

  it("ignores typing in inputs", () => {
    const input = document.createElement("input");
    document.body.appendChild(input);
    expect(reviewShortcutBlocked(key("1", input))).toBe(true);
  });
});

describe("autoGradeForWriting", () => {
  it("never gives Easy for the pass right after the intro", () => {
    expect(autoGradeForWriting(0, 8, true)).toBe(3);
    expect(autoGradeForWriting(0, 8, false)).toBe(4);
  });

  it("keeps lower grades as they are", () => {
    expect(autoGradeForWriting(2, 8, true)).toBe(2);
    expect(autoGradeForWriting(5, 8, true)).toBe(1);
  });
});

describe("formatInterval", () => {
  it("shows the next review in the largest whole unit", () => {
    expect(formatInterval(20)).toBe("< 1m");
    expect(formatInterval(600)).toBe("10m");
    expect(formatInterval(3 * 3600)).toBe("3h");
    expect(formatInterval(5 * 86400)).toBe("5d");
    expect(formatInterval(70 * 86400)).toBe("2mo");
    expect(formatInterval(550 * 86400)).toBe("1.5y");
  });
});

describe("reviewSurface / surfaceMode", () => {
  it("mixed mode follows the stage; intro turns to trace after Got it", () => {
    expect(reviewSurface("mixed", "read", false)).toBe("read");
    expect(reviewSurface("mixed", undefined, false)).toBe("intro");
    expect(reviewSurface("mixed", "intro", true)).toBe("trace");
    expect(reviewSurface("mixed", "produce", true)).toBe("produce");
  });

  it("single mode is the picked mode", () => {
    expect(reviewSurface("cloze", "intro", true)).toBe("cloze");
  });

  it("logs stage surfaces as writing and read as recognition", () => {
    expect(surfaceMode("intro")).toBe("writing");
    expect(surfaceMode("trace")).toBe("writing");
    expect(surfaceMode("produce")).toBe("writing");
    expect(surfaceMode("read")).toBe("recognition");
    expect(surfaceMode("dictation")).toBe("dictation");
  });
});

describe("dictationVerdict", () => {
  it("accepts the hanzi or the toned pinyin", () => {
    expect(dictationVerdict("妈", " 妈 ", "mā")).toBe("correct");
    expect(dictationVerdict("ma1", "妈", "mā")).toBe("correct");
  });

  it("tells toneless, wrong tone and wrong apart, with their grades", () => {
    expect(dictationVerdict("ma", "妈", "mā")).toBe("toneless");
    expect(dictationVerdict("ma3", "妈", "mā")).toBe("tone");
    expect(dictationVerdict("ni3", "妈", "mā")).toBe("wrong");
    expect(DICTATION_GRADE.toneless).toBe(2);
    expect(DICTATION_GRADE.tone).toBe(1);
  });
});

describe("autoGradeDelayFor", () => {
  it("adds reading time for a context sentence, capped", () => {
    expect(autoGradeDelayFor(2000, null)).toBe(2000);
    expect(autoGradeDelayFor(2000, "一二三四")).toBe(2000 + 1500 + 600);
    expect(autoGradeDelayFor(2000, "字".repeat(100))).toBe(2000 + 1500 + 3500);
  });

  it("stays off at 0", () => {
    expect(autoGradeDelayFor(0, "一二三")).toBe(0);
  });
});
