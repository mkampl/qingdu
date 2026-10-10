import { describe, expect, it } from "vitest";
import { isSameSense, otherMeanings } from "./meanings";

describe("otherMeanings", () => {
  it("drops the headline's own sense even when it is not meanings[0]", () => {
    const meanings = [
      "(literary) to call out; to command",
      "(bound form) bugle; trumpet",
      "to mark; to label",
      "day of the month",
      "number in a series",
    ];
    expect(otherMeanings("day of the month", meanings)).toEqual([
      "(literary) to call out; to command",
      "(bound form) bugle; trumpet",
      "to mark; to label",
      "number in a series",
    ]);
  });

  it("matches a headline whose register tag was stripped", () => {
    expect(otherMeanings("male", ["(bound form) male", "baron"])).toEqual(["baron"]);
    expect(otherMeanings("father; dad", ["(coll.) father; dad"])).toEqual([]);
  });

  it("matches a headline whose editorial prefix was stripped", () => {
    const meanings = [
      "(third-person singular) (since the early 20th century, usu. male) he; him; his",
      "(bound form) other; another; some other",
    ];
    expect(otherMeanings("he; him; his", meanings)).toEqual([
      "(bound form) other; another; some other",
    ]);
  });

  it("matches a headline whose trailing note was dropped", () => {
    const meanings = [
      "you (Note: In Taiwan, 妳 is used to address females, but in mainland China, it is not commonly used. Instead…",
    ];
    expect(otherMeanings("you", meanings)).toEqual([]);
  });

  it("keeps everything after index 0 when the headline is meanings[0]", () => {
    expect(otherMeanings("water", ["water", "(after a name) ... River", "to swim"])).toEqual([
      "(after a name) ... River",
      "to swim",
    ]);
  });

  it("returns all senses when there is no headline", () => {
    expect(otherMeanings("", ["a", "b"])).toEqual(["a", "b"]);
    expect(otherMeanings(undefined, ["a"])).toEqual(["a"]);
  });

  it("handles missing lists, blanks and duplicates", () => {
    expect(otherMeanings("x", undefined)).toEqual([]);
    expect(otherMeanings("x", null)).toEqual([]);
    expect(otherMeanings("x", ["", "  ", "y", "y"])).toEqual(["y"]);
  });

  it("caps at max", () => {
    expect(otherMeanings("a", ["a", "b", "c", "d"], 2)).toEqual(["b", "c"]);
  });

  it("does not drop a different sense that only shares a prefix", () => {
    expect(otherMeanings("to go", ["to go back; to return"])).toEqual(["to go back; to return"]);
  });
});

describe("isSameSense", () => {
  it("treats a truncated sense as the same as its full headline", () => {
    expect(isSameSense("up; upper; above; previous", "(bound form) up; upper; above…")).toBe(true);
    expect(isSameSense("up; upper; above…", "(bound form) up; upper; above; previous")).toBe(true);
  });

  it("is case and whitespace insensitive", () => {
    expect(isSameSense("Water ", "water")).toBe(true);
  });

  it("is false for different senses and empty input", () => {
    expect(isSameSense("male", "baron")).toBe(false);
    expect(isSameSense("", "x")).toBe(false);
  });
});
