import { createPinia, setActivePinia } from "pinia";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { nextTick } from "vue";

import { useSettingsStore } from "@/stores/settings";
import { storageGet, storageSet } from "@/utils/storage";

/** A WebView with storage disabled: every access throws. */
function blockStorage() {
  const boom = () => {
    throw new DOMException("blocked", "SecurityError");
  };
  vi.stubGlobal("localStorage", {
    getItem: boom,
    setItem: boom,
    removeItem: boom,
    clear: boom,
    key: boom,
    length: 0,
  });
}

describe("settings persistence", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    localStorage.clear();
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("persists a toggle", async () => {
    const s = useSettingsStore();
    s.hydrate();
    s.autoLearnOnClick = true;
    await nextTick();
    expect(JSON.parse(localStorage.getItem("qingdu.settings.v2")!).autoLearnOnClick).toBe(true);
  });

  it("a blocked localStorage does not break toggling", async () => {
    const s = useSettingsStore();
    s.hydrate();
    const errors = vi.spyOn(console, "error").mockImplementation(() => undefined);
    const warns = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    blockStorage();
    s.autoLearnOnClick = true;
    await nextTick();
    expect(s.autoLearnOnClick).toBe(true);
    expect(errors).not.toHaveBeenCalled();
    expect(warns).not.toHaveBeenCalled();
  });
});

describe("storage helpers", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("swallow storage exceptions", () => {
    blockStorage();
    expect(storageSet("k", "v")).toBe(false);
    expect(storageGet("k")).toBeNull();
  });
});
