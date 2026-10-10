import { describe, expect, it } from "vitest";

import { browseEmptyText, browseLevels, mapBrowseLevel } from "@/utils/browse";

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
});
