import { describe, expect, it } from "vitest";

import type { WordInfo } from "@/api/types";

import { effectiveWordState, isClickableWord, placePopover } from "./utils";

function w(partial: Partial<WordInfo>): WordInfo {
  return { text: "", is_hsk: false, ...partial } as WordInfo;
}

describe("isClickableWord", () => {
  it("opens HSK words and words with a meaning", () => {
    expect(isClickableWord(w({ text: "学习", is_hsk: true }))).toBe(true);
    expect(isClickableWord(w({ text: "饕餮", meaning: "glutton" }))).toBe(true);
  });

  it("opens non-HSK Chinese words without a dictionary hit", () => {
    // Coloured "new" and counted in progress, so they must be markable.
    expect(isClickableWord(w({ text: "嘚瑟" }))).toBe(true);
  });

  it("ignores punctuation, latin and line breaks", () => {
    expect(isClickableWord(w({ text: "，" }))).toBe(false);
    expect(isClickableWord(w({ text: "abc" }))).toBe(false);
    expect(isClickableWord(w({ text: "\n", translation_source: "linebreak" }))).toBe(false);
  });
});

describe("placePopover", () => {
  const viewport = { width: 1024, height: 800 };

  it("sits under the word when it fits", () => {
    const p = placePopover({
      anchor: { top: 100, bottom: 120, left: 500, width: 40 },
      viewport,
      height: 300,
    });
    expect(p.top).toBe(128);
    expect(p.left).toBe(500 + 20 - 160);
    expect(p.maxHeight).toBe(800 - 12 - 128);
  });

  it("flips above near the bottom and caps the height to the room there", () => {
    const p = placePopover({
      anchor: { top: 700, bottom: 720, left: 500, width: 40 },
      viewport,
      height: 900,
    });
    expect(p.maxHeight).toBe(700 - 8 - 12);
    expect(p.top).toBe(12);
    expect(p.top + p.maxHeight).toBeLessThanOrEqual(700);
  });

  it("never runs past the viewport bottom", () => {
    const p = placePopover({
      anchor: { top: 380, bottom: 400, left: 10, width: 20 },
      viewport: { width: 360, height: 640 },
      height: 1200,
    });
    expect(p.top + p.maxHeight).toBeLessThanOrEqual(640 - 12);
    expect(p.left).toBe(12);
  });
});

describe("effectiveWordState", () => {
  it("prefers the live store", () => {
    expect(effectiveWordState("learning", true, "known")).toBe("learning");
    expect(effectiveWordState("learning", false, "known")).toBe("learning");
  });

  it("uses the token state before the store hydrates", () => {
    expect(effectiveWordState(null, false, "known")).toBe("known");
    expect(effectiveWordState(null, false, undefined)).toBeNull();
  });

  it("trusts the hydrated store over a stale token state", () => {
    expect(effectiveWordState(null, true, "known")).toBeNull();
  });
});
