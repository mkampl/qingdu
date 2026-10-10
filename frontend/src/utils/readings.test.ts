import { describe, expect, it } from "vitest";
import type { WordReading } from "@/api/types";
import { otherReadings } from "./readings";

const chang: WordReading = {
  pinyin: "cháng",
  primary: "long",
  meanings: ["long", "(bound form) length"],
  meaning_tags: [],
  is_main: true,
  example: null,
};
const zhang: WordReading = {
  pinyin: "zhǎng",
  primary: "chief",
  meanings: ["chief", "head", "elder", "to grow", "to develop"],
  meaning_tags: [],
  is_main: false,
  example: { word: "校长", pinyin: "xiào zhǎng", meaning: "principal" },
};

describe("otherReadings", () => {
  it("lists every reading but the main one, with up to three more senses", () => {
    expect(otherReadings([chang, zhang])).toEqual([
      {
        pinyin: "zhǎng",
        primary: "chief",
        tags: [],
        senses: ["head", "elder", "to grow"],
        example: { word: "校长", pinyin: "xiào zhǎng", meaning: "principal" },
      },
    ]);
  });

  it("respects the main flag rather than the position", () => {
    const flipped = [
      { ...chang, is_main: false },
      { ...zhang, is_main: true },
    ];
    expect(otherReadings(flipped).map((r) => r.pinyin)).toEqual(["cháng"]);
  });

  it("returns nothing for a single reading or no readings", () => {
    expect(otherReadings([chang])).toEqual([]);
    expect(otherReadings(null)).toEqual([]);
    expect(otherReadings(undefined)).toEqual([]);
  });

  it("caps the extra senses and keeps tags and a missing example", () => {
    const hao: WordReading = {
      pinyin: "hào",
      primary: "to be fond of",
      meanings: ["to be fond of", "a", "b", "c", "d"],
      meaning_tags: ["literary"],
      is_main: false,
    };
    const [r] = otherReadings([{ ...chang, pinyin: "hǎo" }, hao], 2);
    expect(r.senses).toEqual(["a", "b"]);
    expect(r.tags).toEqual(["literary"]);
    expect(r.example).toBeNull();
  });
});
