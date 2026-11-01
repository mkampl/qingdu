import { describe, expect, it } from "vitest";
import type { SavedTextSummary } from "@/api/types";
import { matchesSearch, parseTags, previewSnippet } from "./saved-text";

describe("parseTags", () => {
  it("returns [] for empty, null or malformed input", () => {
    expect(parseTags(null)).toEqual([]);
    expect(parseTags(undefined)).toEqual([]);
    expect(parseTags("")).toEqual([]);
    expect(parseTags("not json")).toEqual([]);
    expect(parseTags('{"a": 1}')).toEqual([]);
  });

  it("keeps only string entries of a JSON array", () => {
    expect(parseTags('["news", 3, "hsk4", null]')).toEqual(["news", "hsk4"]);
  });
});

describe("previewSnippet", () => {
  it("collapses whitespace and truncates with an ellipsis", () => {
    expect(previewSnippet(undefined)).toBe("");
    expect(previewSnippet("  你好\n\n世界  ")).toBe("你好 世界");
    expect(previewSnippet("abcdef", 3)).toBe("abc…");
  });
});

describe("matchesSearch", () => {
  const text = { title: "Chunjie", tags: '["Festival"]' } as SavedTextSummary;

  it("matches title and tags case-insensitively", () => {
    expect(matchesSearch(text, "")).toBe(true);
    expect(matchesSearch(text, "chun")).toBe(true);
    expect(matchesSearch(text, "FEST")).toBe(true);
    expect(matchesSearch(text, "zhongqiu")).toBe(false);
  });
});
