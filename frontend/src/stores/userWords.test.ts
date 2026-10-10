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
