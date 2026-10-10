import { describe, expect, it } from "vitest";

import { localDateKey } from "@/services/notifications";

describe("localDateKey", () => {
  it("uses the device's calendar day, not the UTC one", () => {
    expect(localDateKey(new Date(2026, 9, 10, 23, 59))).toBe("2026-10-10");
    expect(localDateKey(new Date(2026, 9, 11, 0, 1))).toBe("2026-10-11");
    expect(localDateKey(new Date(2026, 0, 5, 12, 0))).toBe("2026-01-05");
  });
});
