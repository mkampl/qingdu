import { describe, expect, it } from "vitest";
import {
  createRequestSequence,
  mergePage,
  nextBatchSize,
  nextPageOffset,
} from "./paged-list";

describe("createRequestSequence", () => {
  it("only the newest request is current", () => {
    const seq = createRequestSequence();
    const a = seq.next();
    expect(seq.isLatest(a)).toBe(true);
    const b = seq.next();
    expect(seq.isLatest(a)).toBe(false);
    expect(seq.isLatest(b)).toBe(true);
  });

  it("current() does not invalidate the running request", () => {
    const seq = createRequestSequence();
    const a = seq.next();
    const more = seq.current();
    expect(more).toBe(a);
    expect(seq.isLatest(a)).toBe(true);
    // A filter change after the follow-up started makes it stale.
    seq.next();
    expect(seq.isLatest(more)).toBe(false);
  });

  it("drops a slow earlier response that resolves after a newer one", async () => {
    const seq = createRequestSequence();
    let shown = "";
    const run = async (value: string, delay: number) => {
      const id = seq.next();
      await new Promise((r) => setTimeout(r, delay));
      if (seq.isLatest(id)) shown = value;
    };
    await Promise.all([run("old", 20), run("new", 1)]);
    expect(shown).toBe("new");
  });
});

describe("mergePage", () => {
  const key = (r: { w: string }) => r.w;

  it("appends a page in order", () => {
    expect(mergePage([{ w: "a" }], [{ w: "b" }, { w: "c" }], key).map(key)).toEqual([
      "a",
      "b",
      "c",
    ]);
  });

  it("skips rows already shown and keeps the local copy", () => {
    const local = { w: "b", edited: true };
    const merged = mergePage([{ w: "a" }, local], [{ w: "b" }, { w: "c" }], key);
    expect(merged.map(key)).toEqual(["a", "b", "c"]);
    expect(merged[1]).toBe(local);
  });

  it("does not mutate the input array", () => {
    const current = [{ w: "a" }];
    mergePage(current, [{ w: "b" }], key);
    expect(current).toHaveLength(1);
  });

  it("dedupes inside the page too", () => {
    expect(mergePage([], [{ w: "x" }, { w: "x" }], key)).toHaveLength(1);
  });
});

describe("nextPageOffset", () => {
  it("continues where the server left off when nothing changed", () => {
    expect(nextPageOffset(200, 0)).toBe(200);
  });

  it("re-reads one row per local edit", () => {
    expect(nextPageOffset(200, 3)).toBe(197);
  });

  it("never goes below zero", () => {
    expect(nextPageOffset(2, 10)).toBe(0);
    expect(nextPageOffset(5, -4)).toBe(5);
  });
});

describe("nextBatchSize", () => {
  it("is a full page while enough rows remain", () => {
    expect(nextBatchSize(200, 668, 200)).toBe(200);
  });

  it("is the remainder on the last page", () => {
    expect(nextBatchSize(600, 668, 200)).toBe(68);
  });

  it("is zero when everything is shown", () => {
    expect(nextBatchSize(668, 668, 200)).toBe(0);
    expect(nextBatchSize(700, 668, 200)).toBe(0);
  });
});
