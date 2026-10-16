import { describe, expect, it } from "vitest";
import type { WordGloss } from "@/api/types";
import { customGlosses, glossLabel, glossTitle } from "./glosses";

const dict: WordGloss = { source: "dictionary", tag: null, meaning: "road; way", pinyin: "dào" };
const pkg: WordGloss = { source: "package", tag: "Dao De Jing", meaning: "the Tao", pinyin: "dào" };
const list: WordGloss = { source: "list", tag: "Dao list", meaning: "the Way", pinyin: null };

describe("glosses", () => {
  it("labels each provenance", () => {
    expect([dict, pkg, list].map(glossLabel)).toEqual(["Dict", "Dao De Jing", "Dao list"]);
    expect(glossTitle(list)).toBe("From your list Dao list");
  });

  it("keeps the non-dictionary meanings, minus the focused one", () => {
    expect(customGlosses([dict, pkg, list])).toEqual([pkg, list]);
    expect(customGlosses([dict, pkg, list], { ...pkg })).toEqual([list]);
    expect(customGlosses(undefined)).toEqual([]);
  });

  it("shows a meaning two sources share once", () => {
    const other: WordGloss = { ...list, tag: "Dao glossary" };
    expect(customGlosses([dict, list, other])).toEqual([list]);
    expect(customGlosses([dict, list, other], { ...other })).toEqual([]);
  });
});
