import { describe, expect, it } from "vitest";
import { contentHash, textKeyFor } from "./text-key";

describe("textKeyFor", () => {
  it("names saved and library texts by id and slug", () => {
    expect(textKeyFor({ savedTextId: 7, librarySlug: "x", content: "" })).toBe("saved:7");
    expect(textKeyFor({ savedTextId: null, librarySlug: "hsk1_01", content: "" })).toBe(
      "library:hsk1_01",
    );
  });

  it("names other texts by their content, ignoring surrounding space", () => {
    const a = textKeyFor({ savedTextId: null, librarySlug: null, content: " 我喜欢看书。\n" });
    expect(a).toBe(`text:${contentHash("我喜欢看书。")}`);
    expect(a).toMatch(/^text:[0-9a-f]{8}-6$/);
    expect(a).not.toBe(textKeyFor({ savedTextId: null, librarySlug: null, content: "我喜欢看报。" }));
  });
});
