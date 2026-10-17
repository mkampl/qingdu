/**
 * The placement test's way through the levels (HSK 1-6, 7 = 7-9).
 *
 * A round asks ROUND_SIZE words of one level. 5+ right: the level is
 * passed, go up. 3 or fewer: stop (going down once when the very first
 * level failed). 4: one more round at the same level, passed with 8 of 12.
 */
export const ROUND_SIZE = 6;
export const TOP_LEVEL = 7;

export interface PlacementState {
  level: number;
  /** Highest level passed so far (0 = none). */
  passed: number;
  /** Right answers of the current level so far, and how many asked. */
  correct: number;
  asked: number;
  /** Levels already decided (passed or failed). */
  decided: number[];
}

export type Step = { done: false; level: number } | { done: true; level: number };

export function start(level: number): PlacementState {
  return { level, passed: 0, correct: 0, asked: 0, decided: [] };
}

/** Record a finished round and say where to go next. */
export function afterRound(s: PlacementState, correct: number): { state: PlacementState; step: Step } {
  const c = s.correct + correct;
  const asked = s.asked + ROUND_SIZE;
  const second = asked > ROUND_SIZE;
  const pass = second ? c >= 8 : correct >= 5;
  const fail = second ? c < 8 : correct <= 3;
  if (!pass && !fail) {
    // Undecided: one more round at this level.
    return { state: { ...s, correct: c, asked }, step: { done: false, level: s.level } };
  }
  const decided = [...s.decided, s.level];
  if (pass) {
    const passed = Math.max(s.passed, s.level);
    const next = s.level + 1;
    if (next > TOP_LEVEL || decided.includes(next)) {
      return { state: { ...s, passed, decided }, step: { done: true, level: passed } };
    }
    return {
      state: { level: next, passed, correct: 0, asked: 0, decided },
      step: { done: false, level: next },
    };
  }
  // Failed: below the first level tried, check the one under it once.
  const below = s.level - 1;
  if (s.passed === 0 && below >= 1 && !decided.includes(below)) {
    return {
      state: { level: below, passed: 0, correct: 0, asked: 0, decided },
      step: { done: false, level: below },
    };
  }
  return { state: { ...s, decided }, step: { done: true, level: s.passed } };
}

export function levelLabel(level: number): string {
  return level >= TOP_LEVEL ? "HSK 7–9" : `HSK ${level}`;
}
