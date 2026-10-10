import { describe, expect, it } from "vitest";
import {
  DEFAULT_FILTERS,
  filtersFromQuery,
  filtersToParams,
  filtersToQuery,
  hasActiveFilters,
  isDefaultFilters,
  sameFilters,
  type WordsFilters,
} from "./words-filters";

const defaults = (): WordsFilters => ({ ...DEFAULT_FILTERS, hsk: [] });

describe("filtersToQuery", () => {
  it("leaves defaults out of the URL", () => {
    expect(filtersToQuery(defaults())).toEqual({});
  });

  it("writes every non-default filter", () => {
    expect(
      filtersToQuery({ state: "known", due: "week", hsk: [3, 1, 3], search: "  hao ", sort: "hsk" }),
    ).toEqual({ state: "known", due: "week", hsk: "1,3", q: "hao", sort: "hsk" });
  });
});

describe("filtersFromQuery", () => {
  it("reads an empty query as the defaults", () => {
    expect(filtersFromQuery({})).toEqual(defaults());
  });

  it("round-trips through the query", () => {
    const f: WordsFilters = { state: "learning", due: "today", hsk: [2, 5], search: "學生", sort: "recent" };
    expect(filtersFromQuery(filtersToQuery(f))).toEqual(f);
  });

  it("falls back to defaults for unknown values", () => {
    expect(
      filtersFromQuery({ state: "new", due: "year", sort: "random", hsk: "x,0,4,12,4" }),
    ).toEqual({ ...defaults(), hsk: [4] });
  });

  it("takes the first value of repeated keys", () => {
    expect(filtersFromQuery({ state: ["known", "ignored"], q: [null, "hao"] })).toMatchObject({
      state: "known",
      search: "hao",
    });
  });
});

describe("filter predicates", () => {
  it("sort alone is not an active filter but is not the default either", () => {
    const f = { ...defaults(), sort: "hsk" as const };
    expect(hasActiveFilters(f)).toBe(false);
    expect(isDefaultFilters(f)).toBe(false);
    expect(isDefaultFilters(defaults())).toBe(true);
  });

  it("whitespace-only search counts as empty", () => {
    expect(hasActiveFilters({ ...defaults(), search: "   " })).toBe(false);
    expect(sameFilters({ ...defaults(), search: " " }, defaults())).toBe(true);
  });
});

describe("filtersToParams", () => {
  it("maps due chips to end-of-day day counts", () => {
    expect(filtersToParams({ ...defaults(), due: "today" }, "new").dueWithinDays).toBe(0);
    expect(filtersToParams({ ...defaults(), due: "week" }, "new").dueWithinDays).toBe(7);
    expect(filtersToParams({ ...defaults(), due: "month" }, "new").dueWithinDays).toBe(30);
    expect(filtersToParams(defaults(), "new").dueWithinDays).toBeUndefined();
  });

  it("passes the HSK version and drops levels the old list does not have", () => {
    const p = filtersToParams({ ...defaults(), hsk: [1, 6, 7, 9] }, "old");
    expect(p.hskVersion).toBe("old");
    expect(p.hskLevels).toBe("1,6");
    expect(filtersToParams({ ...defaults(), hsk: [1, 6, 7, 9] }, "new").hskLevels).toBe("1,6,7,9");
  });

  it("sends state, search and sort", () => {
    expect(
      filtersToParams({ state: "ignored", due: "all", hsk: [], search: " hao ", sort: "recent" }, "new"),
    ).toEqual({ state: "ignored", search: "hao", sort: "recent", hskVersion: "new" });
  });
});
