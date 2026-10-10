import type { HskVersion } from "@/stores/settings";

/** Level chips for /vocab?tab=browse — "all" plus the levels of the HSK
 *  version the user picked in Settings (new: 1–9, old: 1–6). */
export function browseLevels(version: HskVersion): { key: string; label: string }[] {
  const count = version === "old" ? 6 : 9;
  const out = [{ key: "all", label: "All" }];
  for (let n = 1; n <= count; n++) out.push({ key: `${version}-${n}`, label: `HSK ${n}` });
  return out;
}

/** Same level number in the other HSK version (clamped), or "all". */
export function mapBrowseLevel(level: string, version: HskVersion): string {
  if (level === "all") return "all";
  const n = Number(level.split("-")[1]);
  if (!Number.isFinite(n)) return `${version}-1`;
  const max = version === "old" ? 6 : 9;
  return `${version}-${Math.min(Math.max(n, 1), max)}`;
}

export function browseEmptyText(level: string, query: string): string {
  const q = query.trim();
  const levelName = level === "all" ? null : `HSK ${level.split("-")[1]}`;
  if (q && levelName) return `No words in ${levelName} match “${q}”.`;
  if (q) return `No words match “${q}”.`;
  return levelName ? `No words in ${levelName}.` : "No words found.";
}
