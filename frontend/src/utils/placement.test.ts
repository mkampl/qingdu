import { describe, expect, it } from "vitest";

import { afterRound, start } from "./placement";

function run(startLevel: number, rounds: number[]) {
  let s = start(startLevel);
  let step = null as ReturnType<typeof afterRound>["step"] | null;
  for (const c of rounds) {
    const r = afterRound(s, c);
    s = r.state;
    step = r.step;
    if (step.done) break;
  }
  return step;
}

describe("placement", () => {
  it("climbs while rounds go well and stops at a poor one", () => {
    expect(run(2, [6, 5, 2])).toEqual({ done: true, level: 3 });
  });

  it("goes down once when the first level fails", () => {
    expect(run(3, [1, 6, 1])).toEqual({ done: true, level: 2 });
    expect(run(2, [2, 2])).toEqual({ done: true, level: 0 });
  });

  it("asks a second round when undecided", () => {
    expect(run(1, [4, 4, 1])).toEqual({ done: true, level: 1 });
    expect(run(1, [4, 3])).toEqual({ done: true, level: 0 });
  });

  it("ends at the top", () => {
    expect(run(6, [6, 6])).toEqual({ done: true, level: 7 });
  });
});
