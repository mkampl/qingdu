import { createPinia, setActivePinia } from "pinia";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "@/api/client";
import { useUserWordsStore } from "@/stores/userWords";

describe("userWords.hydrate", () => {
  beforeEach(() => setActivePinia(createPinia()));
  afterEach(() => vi.restoreAllMocks());

  it("stays unhydrated when a signed-in load fails, so a retry can happen", async () => {
    vi.spyOn(api, "getToken").mockReturnValue("token");
    vi.spyOn(api, "listUserWordStates").mockRejectedValue(new Error("offline"));
    vi.spyOn(api, "getWordStats").mockRejectedValue(new Error("offline"));
    const store = useUserWordsStore();
    await store.hydrate();
    expect(store.hydrated).toBe(false);
  });

  it("counts as hydrated for anonymous visitors", async () => {
    vi.spyOn(api, "getToken").mockReturnValue(null);
    vi.spyOn(api, "listUserWordStates").mockRejectedValue(new Error("401"));
    vi.spyOn(api, "getWordStats").mockRejectedValue(new Error("401"));
    const store = useUserWordsStore();
    await store.hydrate();
    expect(store.hydrated).toBe(true);
  });
});

describe("userWords.bulkMarkKnown", () => {
  beforeEach(() => setActivePinia(createPinia()));
  afterEach(() => vi.restoreAllMocks());

  it("undoes the optimistic state of words the server skipped", async () => {
    vi.spyOn(api, "bulkMarkKnown").mockResolvedValue({
      updated: 1,
      total: 3,
      skipped: ["很多", "我来"],
    });
    const store = useUserWordsStore();
    store.states = { 我来: "learning" };

    await store.bulkMarkKnown(["很多", "衣服", "我来"]);

    expect(store.stateOf("衣服")).toBe("known");
    expect(store.stateOf("很多")).toBeNull();
    expect(store.stateOf("我来")).toBe("learning");
    expect(store.stats.known).toBe(1);
    expect(store.stats.learning).toBe(1);
  });
});
