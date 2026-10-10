import { afterEach, describe, expect, it, vi } from "vitest";

import { browserTimeZone, timeZoneOptions } from "@/utils/timezone";

describe("timezone utils", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("reads the device zone", () => {
    vi.spyOn(Intl.DateTimeFormat.prototype, "resolvedOptions").mockReturnValue({
      timeZone: "Asia/Shanghai",
    } as Intl.ResolvedDateTimeFormatOptions);
    expect(browserTimeZone()).toBe("Asia/Shanghai");
  });

  it("returns null when the runtime has no zone", () => {
    vi.spyOn(Intl.DateTimeFormat.prototype, "resolvedOptions").mockReturnValue({
      timeZone: "",
    } as Intl.ResolvedDateTimeFormatOptions);
    expect(browserTimeZone()).toBeNull();
  });

  it("lists sorted zones that include the stored and device zones", () => {
    const zones = timeZoneOptions("Etc/GMT-14", null, "Europe/Vienna");
    expect(zones).toContain("Etc/GMT-14");
    expect(zones).toContain("Europe/Vienna");
    expect(zones).toContain("UTC");
    expect(zones).toEqual([...zones].sort((a, b) => a.localeCompare(b)));
    expect(new Set(zones).size).toBe(zones.length);
  });
});
