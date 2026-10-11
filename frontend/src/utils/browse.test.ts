import { describe, expect, it } from "vitest";

import {
  browseEmptyText,
  browseLevels,
  browseStateCount,
  mapBrowseLevel,
  parseBrowseState,
  shiftBrowseCounts,
} from "@/utils/browse";

describe("browse helpers", () => {
  it("offers the levels of the chosen HSK version", () => {
    expect(browseLevels("new").map((l) => l.key)).toEqual([
      "all",
      ...Array.from({ length: 9 }, (_, i) => `new-${i + 1}`),
    ]);
    expect(browseLevels("old").map((l) => l.key)).toEqual([
      "all",
      ...Array.from({ length: 6 }, (_, i) => `old-${i + 1}`),
    ]);
  });

  it("maps the selected level when the version changes", () => {
    expect(mapBrowseLevel("new-3", "old")).toBe("old-3");
    expect(mapBrowseLevel("new-8", "old")).toBe("old-6");
    expect(mapBrowseLevel("old-2", "new")).toBe("new-2");
    expect(mapBrowseLevel("all", "old")).toBe("all");
  });

  it("words the empty state for level, search and both", () => {
    expect(browseEmptyText("all", "xyz")).toBe("No words match “xyz”.");
    expect(browseEmptyText("new-3", "")).toBe("No words in HSK 3.");
    expect(browseEmptyText("new-3", " 猫 ")).toBe("No words in HSK 3 match “猫”.");
  });

  it("words the empty state for a state filter", () => {
    expect(browseEmptyText("new-3", "", "known")).toBe("No known words in HSK 3.");
    expect(browseEmptyText("all", "猫", "new")).toBe("No new words matching “猫”.");
  });

  it("parses the state from the URL, defaulting to all", () => {
    expect(parseBrowseState("known")).toBe("known");
    expect(parseBrowseState(["learning"])).toBe("learning");
    expect(parseBrowseState("mastered")).toBe("all");
    expect(parseBrowseState(undefined)).toBe("all");
  });

  it("counts chips and moves a word between states", () => {
    const counts = { new: 5, learning: 2, known: 3, ignored: 0 };
    expect(browseStateCount(counts, "all")).toBe(10);
    expect(browseStateCount(counts, "known")).toBe(3);
    expect(browseStateCount(null, "known")).toBeNull();
    expect(shiftBrowseCounts(counts, "new", "known")).toEqual({
      new: 4,
      learning: 2,
      known: 4,
      ignored: 0,
    });
    expect(shiftBrowseCounts(counts, "known", "known")).toBe(counts);
  });
});
