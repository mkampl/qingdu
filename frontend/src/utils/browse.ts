import type { HskVersion } from "@/stores/settings";
import { maxHskLevel } from "@/utils/words-filters";

/** Level chips for /vocab?tab=browse — "all" plus the levels of the HSK
 *  version the user picked in Settings (new: 1–9, old: 1–6). */
export function browseLevels(version: HskVersion): { key: string; label: string }[] {
  const count = maxHskLevel(version);
  const out = [{ key: "all", label: "All" }];
  for (let n = 1; n <= count; n++) out.push({ key: `${version}-${n}`, label: `HSK ${n}` });
  return out;
}

/** Same level number in the other HSK version (clamped), or "all". */
export function mapBrowseLevel(level: string, version: HskVersion): string {
  if (level === "all") return "all";
  const n = Number(level.split("-")[1]);
  if (!Number.isFinite(n)) return `${version}-1`;
  const max = maxHskLevel(version);
  return `${version}-${Math.min(Math.max(n, 1), max)}`;
}

export function browseEmptyText(level: string, query: string, state = "all"): string {
  const q = query.trim();
  const levelName = level === "all" ? null : `HSK ${level.split("-")[1]}`;
  if (state !== "all") {
    const where = levelName ? ` in ${levelName}` : "";
    const match = q ? ` matching “${q}”` : "";
    const what = state === "new" ? "No new words" : `No ${state} words`;
    return `${what}${where}${match}.`;
  }
  if (q && levelName) return `No words in ${levelName} match “${q}”.`;
  if (q) return `No words match “${q}”.`;
  return levelName ? `No words in ${levelName}.` : "No words found.";
}

/** Word-state filter on the Browse tab ("new" = not tracked yet). */
export type BrowseState = "all" | "new" | "learning" | "known" | "ignored";
export type BrowseStateCounts = Record<Exclude<BrowseState, "all">, number>;

export const BROWSE_STATES: { key: BrowseState; label: string }[] = [
  { key: "all", label: "All" },
  { key: "new", label: "New" },
  { key: "learning", label: "Learning" },
  { key: "known", label: "Known" },
  { key: "ignored", label: "Ignored" },
];

export function parseBrowseState(raw: unknown): BrowseState {
  const v = Array.isArray(raw) ? raw[0] : raw;
  return BROWSE_STATES.some((s) => s.key === v) ? (v as BrowseState) : "all";
}

/** Count shown on a state chip; "all" is the sum of the four states. */
export function browseStateCount(
  counts: BrowseStateCounts | null,
  key: BrowseState,
): number | null {
  if (!counts) return null;
  if (key === "all") return counts.new + counts.learning + counts.known + counts.ignored;
  return counts[key];
}

/** Move one word between state counts after the user changes its state. */
export function shiftBrowseCounts(
  counts: BrowseStateCounts,
  from: Exclude<BrowseState, "all">,
  to: Exclude<BrowseState, "all">,
): BrowseStateCounts {
  if (from === to) return counts;
  return { ...counts, [from]: Math.max(0, counts[from] - 1), [to]: counts[to] + 1 };
}
