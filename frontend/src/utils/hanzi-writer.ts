import type { Theme } from "@/stores/settings";

/**
 * hanzi-writer plus the stroke data for one character. The library is
 * imported on first use so it stays out of the main bundle; the data comes
 * from the package's CDN. Rare characters and variant forms (玅) have no
 * stroke data: `data` is null for them.
 */
export async function loadStrokeData(char: string) {
  const HanziWriter = (await import("hanzi-writer")).default;
  const data = await HanziWriter.loadCharacterData(char).catch(() => null);
  return { HanziWriter, data };
}

/**
 * Stroke and outline colours per theme. hanzi-writer only parses hex/rgb,
 * so the OKLCH theme tokens can't be passed through: gray-800 ink on light,
 * gray-200 on dark, where gray-800 would disappear against the canvas.
 */
export function hanziInk(theme: Theme): { ink: string; outline: string } {
  return theme === "dark"
    ? { ink: "#e5e7eb", outline: "#4b5563" }
    : { ink: "#1f2937", outline: "#dddddd" };
}
