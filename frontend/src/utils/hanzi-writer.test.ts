import { describe, expect, it, vi } from "vitest";

const { loadCharacterData } = vi.hoisted(() => ({ loadCharacterData: vi.fn() }));
vi.mock("hanzi-writer", () => ({ default: { loadCharacterData } }));

import { hanziInk, loadStrokeData } from "@/utils/hanzi-writer";

describe("loadStrokeData", () => {
  it("returns the writer and the character's stroke data", async () => {
    loadCharacterData.mockResolvedValueOnce({ strokes: ["a", "b"] });
    const { HanziWriter, data } = await loadStrokeData("一");
    expect(loadCharacterData).toHaveBeenCalledWith("一");
    expect(HanziWriter.loadCharacterData).toBe(loadCharacterData);
    expect(data).toEqual({ strokes: ["a", "b"] });
  });

  it("gives null data for a rare character", async () => {
    loadCharacterData.mockRejectedValueOnce(new Error("404"));
    const { data } = await loadStrokeData("玅");
    expect(data).toBeNull();
  });
});

describe("hanziInk", () => {
  it("pairs ink and outline per theme", () => {
    expect(hanziInk("light")).toEqual({ ink: "#1f2937", outline: "#dddddd" });
    expect(hanziInk("dark")).toEqual({ ink: "#e5e7eb", outline: "#4b5563" });
  });
});
