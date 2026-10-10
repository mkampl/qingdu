import { createPinia, setActivePinia } from "pinia";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "@/api/client";
import type { VocabularyListSummary } from "@/api/types";
import { useAuthStore } from "@/stores/auth";
import { useVocabListsStore } from "@/stores/vocab-lists";

function list(id: number, name = `List ${id}`): VocabularyListSummary {
  return { id, name, type: "custom", sections: [], apply_as_glossary: false };
}

function deferred<T>() {
  let resolve!: (v: T) => void;
  const promise = new Promise<T>((r) => (resolve = r));
  return { promise, resolve };
}

describe("vocab-lists store", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    useAuthStore().user = { username: "alice", is_admin: false } as never;
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("skips the request for anonymous users", async () => {
    useAuthStore().user = null;
    const spy = vi.spyOn(api, "listVocabularyLists");
    await useVocabListsStore().ensureLoaded();
    expect(spy).not.toHaveBeenCalled();
  });

  it("returns the in-flight promise to concurrent callers", async () => {
    const d = deferred<VocabularyListSummary[]>();
    const spy = vi.spyOn(api, "listVocabularyLists").mockReturnValue(d.promise);
    const store = useVocabListsStore();
    const first = store.ensureLoaded();
    const second = store.ensureLoaded();
    expect(spy).toHaveBeenCalledTimes(1);
    d.resolve([list(1)]);
    await second;
    // The second caller must see the data, not return early with nothing.
    expect(store.lists.map((l) => l.id)).toEqual([1]);
    await first;
  });

  it("keeps showing the old lists while revalidating", async () => {
    const spy = vi.spyOn(api, "listVocabularyLists").mockResolvedValue([list(1)]);
    const store = useVocabListsStore();
    await store.ensureLoaded();
    const d = deferred<VocabularyListSummary[]>();
    spy.mockReturnValue(d.promise);
    const refreshed = store.invalidate();
    expect(store.lists.map((l) => l.id)).toEqual([1]);
    expect(store.loading).toBe(false);
    expect(store.isEmpty).toBe(false);
    d.resolve([list(1), list(2)]);
    await refreshed;
    expect(store.lists.map((l) => l.id)).toEqual([1, 2]);
  });

  it("drops a response that an invalidate overtook", async () => {
    const stale = deferred<VocabularyListSummary[]>();
    const fresh = deferred<VocabularyListSummary[]>();
    vi.spyOn(api, "listVocabularyLists")
      .mockReturnValueOnce(stale.promise)
      .mockReturnValueOnce(fresh.promise);
    const store = useVocabListsStore();
    const first = store.ensureLoaded();
    const second = store.invalidate();
    fresh.resolve([list(1, "after edit")]);
    await second;
    stale.resolve([list(1, "before edit")]);
    await first;
    expect(store.lists[0].name).toBe("after edit");
  });

  it("clear() empties the cache and ignores late responses", async () => {
    const d = deferred<VocabularyListSummary[]>();
    vi.spyOn(api, "listVocabularyLists").mockReturnValue(d.promise);
    const store = useVocabListsStore();
    const pending = store.ensureLoaded();
    store.clear();
    d.resolve([list(9)]);
    await pending;
    expect(store.lists).toEqual([]);
    expect(store.loadedAt).toBeNull();
  });
});
