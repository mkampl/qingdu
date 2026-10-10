// Run these as a learner in New York would: naive UTC strings used to be
// read as local time, which shifted everything by five hours.
process.env.TZ = "America/New_York";

import { describe, expect, it } from "vitest";
import { formatUtcDate, parseUtc, parseUtcMs } from "./time";

describe("parseUtc under TZ=America/New_York", () => {
  it("really runs west of UTC", () => {
    // January: EST, UTC-5.
    expect(new Date(2026, 0, 15, 12).getTimezoneOffset()).toBe(300);
  });

  it("reads Z-suffixed timestamps as UTC", () => {
    expect(parseUtcMs("2026-01-15T23:30:00Z")).toBe(Date.UTC(2026, 0, 15, 23, 30));
  });

  it("reads naive timestamps as UTC, not local time", () => {
    const naive = "2026-01-15T23:30:00";
    expect(parseUtcMs(naive)).toBe(Date.UTC(2026, 0, 15, 23, 30));
    // What the old `new Date(str)` did: five hours late.
    expect(new Date(naive).getTime() - Date.UTC(2026, 0, 15, 23, 30)).toBe(5 * 3600_000);
  });

  it("keeps explicit offsets and microseconds", () => {
    expect(parseUtcMs("2026-01-15T23:30:00+00:00")).toBe(Date.UTC(2026, 0, 15, 23, 30));
    expect(parseUtcMs("2026-01-15T18:30:00-05:00")).toBe(Date.UTC(2026, 0, 15, 23, 30));
    expect(parseUtcMs("2026-01-15T23:30:00.123456Z")).toBe(
      Date.UTC(2026, 0, 15, 23, 30, 0, 123),
    );
  });

  it("returns null for missing or garbage input", () => {
    expect(parseUtc(null)).toBeNull();
    expect(parseUtc(undefined)).toBeNull();
    expect(parseUtc("")).toBeNull();
    expect(parseUtc("not a date")).toBeNull();
  });

  it("formats in the local calendar day", () => {
    // 02:00 UTC on Jan 16 is still Jan 15 in New York.
    expect(parseUtc("2026-01-16T02:00:00")?.getDate()).toBe(15);
    const opts = { month: "numeric", day: "numeric" } as const;
    expect(formatUtcDate("2026-01-16T02:00:00", opts)).toBe(
      new Date(2026, 0, 15, 21).toLocaleDateString(undefined, opts),
    );
    expect(formatUtcDate(null)).toBe("");
  });
});
