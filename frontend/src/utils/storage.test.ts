import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@capacitor/local-notifications", () => ({ LocalNotifications: {} }));

import { forgetUserCaches, rememberDueCount, rememberStreak } from "@/services/notifications";
import { storageGet, storageRemove, storageSet } from "@/utils/storage";

function throwingStorage() {
  const fail = () => {
    throw new Error("SecurityError");
  };
  vi.stubGlobal("localStorage", { getItem: fail, setItem: fail, removeItem: fail });
}

describe("storage helpers", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    localStorage.clear();
  });

  it("read, write and remove a key", () => {
    expect(storageSet("k", "v")).toBe(true);
    expect(storageGet("k")).toBe("v");
    storageRemove("k");
    expect(storageGet("k")).toBeNull();
  });

  it("never throw when localStorage does", () => {
    throwingStorage();
    expect(storageGet("k")).toBeNull();
    expect(storageSet("k", "v")).toBe(false);
    expect(() => storageRemove("k")).not.toThrow();
  });

  it("keep the reminder caches under their keys", () => {
    rememberDueCount(4.7);
    rememberStreak(-2);
    expect(localStorage.getItem("qingdu.notif.lastDueCount")).toBe("4");
    expect(localStorage.getItem("qingdu.notif.lastStreak")).toBe("0");
    forgetUserCaches();
    expect(localStorage.getItem("qingdu.notif.lastDueCount")).toBeNull();
    expect(localStorage.getItem("qingdu.notif.lastStreak")).toBeNull();
  });

  it("let the reminder caches fail quietly", () => {
    throwingStorage();
    expect(() => rememberDueCount(3)).not.toThrow();
    expect(() => rememberStreak(3)).not.toThrow();
    expect(() => forgetUserCaches()).not.toThrow();
  });
});
