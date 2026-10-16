import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import type { WordGloss } from "@/api/types";
import WordReadings from "./WordReadings.vue";

const pkg: WordGloss = { source: "package", tag: "Dao De Jing", meaning: "the Tao", pinyin: "dào" };
const list: WordGloss = { source: "list", tag: "Dao list", meaning: "the Way", pinyin: null };
const dict: WordGloss = { source: "dictionary", tag: null, meaning: "road", pinyin: "dào" };

describe("WordReadings", () => {
  it("lists the word's own meanings after the dictionary's", () => {
    const w = mount(WordReadings, {
      props: { meaning: "road; way", meanings: ["road; way", "to say"], glosses: [dict, pkg, list] },
    });
    const text = w.text();
    expect(text.indexOf("road; way")).toBeLessThan(text.indexOf("the Tao"));
    expect(text).toContain("to say");
    expect(text).toContain("Dao list");
    expect(text).not.toContain("Dict");
  });

  it("leads with the focused meaning and keeps the dictionary's below", () => {
    const w = mount(WordReadings, {
      props: { meaning: "road; way", meanings: ["road; way", "to say"], glosses: [dict, pkg, list], focus: pkg },
    });
    const text = w.text();
    expect(text.indexOf("the Tao")).toBeLessThan(text.indexOf("road; way"));
    expect(text).toContain("Dictionary:");
    expect(text).not.toContain("to say");
    // The focused gloss is not listed twice.
    expect(text.split("the Tao").length).toBe(2);
    expect(text).toContain("the Way");
  });
});
