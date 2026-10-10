import { createPinia, setActivePinia } from "pinia";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "@/api/client";
import type { AnalysisResponse } from "@/api/types";
import { useAnalysisStore } from "@/stores/analysis";

function fakeResult(tag: string): AnalysisResponse {
  return { tag } as unknown as AnalysisResponse;
}

/** api.analyze stand-in that settles on demand and honours the abort signal. */
function controllableAnalyze() {
  const pending: Array<{
    resolve: (r: AnalysisResponse) => void;
    signal?: AbortSignal;
  }> = [];
  vi.spyOn(api, "analyze").mockImplementation(
    (_text, opts) =>
      new Promise<AnalysisResponse>((resolve, reject) => {
        opts?.signal?.addEventListener("abort", () =>
          // Settle on a later tick, like a real fetch does.
          setTimeout(() => reject(new DOMException("aborted", "AbortError")), 0),
        );
        pending.push({ resolve, signal: opts?.signal });
      }),
  );
  return pending;
}

describe("analysis store", () => {
  beforeEach(() => setActivePinia(createPinia()));
  afterEach(() => vi.restoreAllMocks());

  it("an aborted request finishing late does not clear loading", async () => {
    const pending = controllableAnalyze();
    const store = useAnalysisStore();
    const first = store.analyze("一");
    const second = store.analyze("二");
    await first; // the aborted one settles
    expect(store.loading).toBe(true);
    pending[1].resolve(fakeResult("二"));
    await second;
    expect(store.loading).toBe(false);
    expect((store.result as unknown as { tag: string }).tag).toBe("二");
  });

  it("a stale response never replaces a newer one", async () => {
    const pending = controllableAnalyze();
    const store = useAnalysisStore();
    const first = store.analyze("一");
    const second = store.analyze("二");
    pending[1].resolve(fakeResult("二"));
    await second;
    pending[0].resolve(fakeResult("一"));
    await first;
    expect((store.result as unknown as { tag: string }).tag).toBe("二");
  });

  it("clearing the text cancels the request in flight", async () => {
    const pending = controllableAnalyze();
    const store = useAnalysisStore();
    const first = store.analyze("一");
    await store.analyze("   ");
    expect(store.loading).toBe(false);
    pending[0].resolve(fakeResult("一"));
    await first;
    expect(store.result).toBeNull();
  });

  it("stash/restore round-trips the reader's own analysis", () => {
    const store = useAnalysisStore();
    store.loadSaved("我的", fakeResult("mine"), {
      id: 7,
      title: "Mine",
      tags: ["a"],
      progress: 0.4,
    });
    const saved = store.stash();
    store.loadSaved("别人的", fakeResult("theirs"));
    expect(store.savedTextId).toBeNull();
    store.restore(saved);
    expect(store.inputText).toBe("我的");
    expect(store.savedTextId).toBe(7);
    expect(store.savedTextTitle).toBe("Mine");
    expect(store.initialProgress).toBeCloseTo(0.4);
    expect((store.result as unknown as { tag: string }).tag).toBe("mine");
  });
});
