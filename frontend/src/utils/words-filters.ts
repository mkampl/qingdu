/**
 * /words filter state <-> URL query. The filters live in the query string
 * so they survive a reload and a trip to Practice and back. Defaults are
 * left out of the URL, so a plain /words stays plain.
 *
 * Kept free of Vue / vue-router so it can be unit-tested directly.
 */

import type { WordsQueueParams } from "@/api/client";
import type { HskVersion } from "@/stores/settings";

export type StateFilter = "all" | "learning" | "known" | "ignored";
export type DueFilter = "all" | "today" | "week" | "month";
export type SortKey = "due" | "recent" | "hsk";

export interface WordsFilters {
  state: StateFilter;
  due: DueFilter;
  /** Selected HSK levels, ascending, no duplicates. */
  hsk: number[];
  search: string;
  sort: SortKey;
}

/** Shape of vue-router's LocationQuery, without importing it. */
export type QueryLike = Record<string, string | null | (string | null)[] | undefined>;

export const DEFAULT_FILTERS: Readonly<WordsFilters> = Object.freeze({
  state: "all",
  due: "all",
  hsk: [],
  search: "",
  sort: "due",
});

const STATES: readonly StateFilter[] = ["all", "learning", "known", "ignored"];
const DUES: readonly DueFilter[] = ["all", "today", "week", "month"];
const SORTS: readonly SortKey[] = ["due", "recent", "hsk"];

/** Days ahead for each due chip; the server counts to the end of that day. */
export const DUE_DAYS: Record<Exclude<DueFilter, "all">, number> = {
  today: 0,
  week: 7,
  month: 30,
};

/** Number of HSK level chips for a version (old HSK had six levels). */
export function maxHskLevel(version: HskVersion): number {
  return version === "old" ? 6 : 9;
}

function first(v: QueryLike[string]): string {
  if (Array.isArray(v)) return v.find((x) => typeof x === "string") ?? "";
  return typeof v === "string" ? v : "";
}

function pick<T extends string>(raw: string, allowed: readonly T[], fallback: T): T {
  return (allowed as readonly string[]).includes(raw) ? (raw as T) : fallback;
}

export function normaliseHsk(levels: Iterable<number>, max = 9): number[] {
  const out = new Set<number>();
  for (const n of levels) {
    if (Number.isInteger(n) && n >= 1 && n <= max) out.add(n);
  }
  return Array.from(out).sort((a, b) => a - b);
}

/** Read filters from a route query; unknown or malformed values fall back to defaults. */
export function filtersFromQuery(query: QueryLike): WordsFilters {
  const hskRaw = first(query.hsk);
  return {
    state: pick(first(query.state), STATES, DEFAULT_FILTERS.state),
    due: pick(first(query.due), DUES, DEFAULT_FILTERS.due),
    hsk: normaliseHsk(
      hskRaw
        .split(",")
        .map((s) => s.trim())
        .filter((s) => /^\d+$/.test(s))
        .map((s) => parseInt(s, 10)),
    ),
    search: first(query.q),
    sort: pick(first(query.sort), SORTS, DEFAULT_FILTERS.sort),
  };
}

/** Query for a set of filters, omitting every default. */
export function filtersToQuery(f: WordsFilters): Record<string, string> {
  const q: Record<string, string> = {};
  if (f.state !== DEFAULT_FILTERS.state) q.state = f.state;
  if (f.due !== DEFAULT_FILTERS.due) q.due = f.due;
  const hsk = normaliseHsk(f.hsk);
  if (hsk.length) q.hsk = hsk.join(",");
  const search = f.search.trim();
  if (search) q.q = search;
  if (f.sort !== DEFAULT_FILTERS.sort) q.sort = f.sort;
  return q;
}

/** True when two filter sets give the same query (key order, defaults ignored). */
export function sameFilters(a: WordsFilters, b: WordsFilters): boolean {
  const qa = filtersToQuery(a);
  const qb = filtersToQuery(b);
  const ka = Object.keys(qa);
  return ka.length === Object.keys(qb).length && ka.every((k) => qa[k] === qb[k]);
}

/** Any filter that narrows the list (sort does not). */
export function hasActiveFilters(f: WordsFilters): boolean {
  return f.state !== "all" || f.due !== "all" || f.hsk.length > 0 || f.search.trim() !== "";
}

/** True when nothing differs from the defaults, sort included ("Reset filters" is off). */
export function isDefaultFilters(f: WordsFilters): boolean {
  return sameFilters(f, { ...DEFAULT_FILTERS, hsk: [] });
}

/** /api/words/queue parameters for a set of filters. */
export function filtersToParams(f: WordsFilters, hskVersion: HskVersion): WordsQueueParams {
  const p: WordsQueueParams = { sort: f.sort };
  if (f.state !== "all") p.state = f.state;
  if (f.due !== "all") p.dueWithinDays = DUE_DAYS[f.due];
  const hsk = normaliseHsk(f.hsk, maxHskLevel(hskVersion));
  if (hsk.length) p.hskLevels = hsk.join(",");
  const search = f.search.trim();
  if (search) p.search = search;
  // Only matters for the HSK filter, sort and badge, but always sent so
  // the badge matches the reader's colouring.
  p.hskVersion = hskVersion;
  return p;
}
