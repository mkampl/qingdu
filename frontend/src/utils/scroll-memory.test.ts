import { describe, expect, it } from "vitest";

import { decideScroll, ScrollMemory } from "@/utils/scroll-memory";

describe("decideScroll", () => {
  it("goes to the top on a new page", () => {
    expect(
      decideScroll({ fromPath: "/words", toPath: "/review", isPop: false, saved: undefined }),
    ).toEqual({ kind: "top" });
  });

  it("keeps the position on a query-only change", () => {
    expect(
      decideScroll({ fromPath: "/vocab", toPath: "/vocab", isPop: false, saved: undefined }),
    ).toEqual({ kind: "none" });
  });

  it("restores the remembered position on Back", () => {
    expect(
      decideScroll({ fromPath: "/vocab/3", toPath: "/vocab", isPop: true, saved: 840 }),
    ).toEqual({ kind: "restore", top: 840 });
  });

  it("falls back to the top on Back without a remembered position", () => {
    expect(
      decideScroll({ fromPath: "/vocab/3", toPath: "/vocab", isPop: true, saved: undefined }),
    ).toEqual({ kind: "top" });
  });
});

describe("ScrollMemory", () => {
  it("evicts the oldest entries past its cap", () => {
    const m = new ScrollMemory(2);
    m.save("a", 1);
    m.save("b", 2);
    m.save("a", 3); // refresh a
    m.save("c", 4);
    expect(m.get("b")).toBeUndefined();
    expect(m.get("a")).toBe(3);
    expect(m.get("c")).toBe(4);
  });
});
