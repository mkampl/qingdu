import { describe, expect, it } from "vitest";

import type { VocabularySection } from "@/api/types";
import {
  createEditGate,
  defaultSectionName,
  listCounts,
  sectionContaining,
} from "@/utils/vocab-lists";

function section(name: string, hanzi: string[] = []): VocabularySection {
  return {
    name,
    words: hanzi.map((h) => ({ hanzi: h, pinyin: "", meaning: "", level: "Custom" as never })),
  };
}

describe("vocab list helpers", () => {
  it("defaults the section to the list's first one, else Main", () => {
    expect(defaultSectionName({ sections: [section("Chapter 3"), section("B")] })).toBe(
      "Chapter 3",
    );
    expect(defaultSectionName({ sections: [] })).toBe("Main");
    expect(defaultSectionName(undefined)).toBe("Main");
  });

  it("finds the section that already holds a word", () => {
    const list = { sections: [section("Main", ["你好"]), section("Extra", ["再见"])] };
    expect(sectionContaining(list, "再见")).toBe("Extra");
    expect(sectionContaining(list, "谢谢")).toBeNull();
  });

  it("edit gate lets exactly one of Enter / Escape / blur act per edit", () => {
    const gate = createEditGate();
    expect(gate.take()).toBe(false); // nothing being edited
    gate.begin();
    expect(gate.take()).toBe(true); // Escape (cancel) or Enter (commit)
    expect(gate.take()).toBe(false); // the blur that follows is ignored
    gate.begin();
    expect(gate.take()).toBe(true);
  });

  it("counts empty sections like the detail page does", () => {
    expect(listCounts({ sections: [section("A"), section("B"), section("C", ["一", "二"])] })).toEqual(
      { sections: 3, words: 2 },
    );
  });
});
