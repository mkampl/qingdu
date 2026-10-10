/**
 * Per-character bookkeeping for the hanzi-writer quiz (WritingQuiz.vue).
 *
 * Each character's stroke count is recorded once, when its stroke data
 * first loads — re-creating the writer (outline toggle, theme change,
 * word change) must not add it again, or the mistake ratio halves and
 * the suggested grade turns lenient. Mistakes are per character too, so
 * a skipped or "shown" character is scored on the same ratio scale the
 * grade uses instead of a flat penalty.
 */

export interface CharScore {
  /** Stroke count from hanzi-writer's data; null until it has loaded. */
  strokes: number | null;
  /** Mistakes on this character; null while it is still being drawn. */
  mistakes: number | null;
}

export function emptyScores(count: number): CharScore[] {
  return Array.from({ length: count }, () => ({ strokes: null, mistakes: null }));
}

/** Stroke count for a character whose data never loaded. */
const UNKNOWN_STROKES = 1;

/** Skipped: every stroke counts as a mistake (ratio 1 for this char). */
export function skippedScore(strokes: number | null): CharScore {
  const n = strokes ?? UNKNOWN_STROKES;
  return { strokes: n, mistakes: n };
}

/** "Show me": worse than a skip — twice the strokes as mistakes. */
export function shownScore(strokes: number | null): CharScore {
  const n = strokes ?? UNKNOWN_STROKES;
  return { strokes: n, mistakes: n * 2 };
}

export function scoreTotals(scores: CharScore[]): { strokes: number; mistakes: number } {
  let strokes = 0;
  let mistakes = 0;
  for (const s of scores) {
    strokes += s.strokes ?? 0;
    mistakes += s.mistakes ?? 0;
  }
  return { strokes, mistakes };
}
