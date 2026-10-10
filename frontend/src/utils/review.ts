/**
 * Pure helpers behind the review session (stores/review.ts and
 * ReviewView.vue), split out so they can be unit-tested.
 */
import type { ReviewGrade, ReviewStatsResponse } from "@/api/client";
import { parseUtcMs } from "@/utils/time";

export type ReviewWindow = "now" | "today" | "tomorrow";

/** Anki-style learning steps: a card FSRS schedules within this many
 *  minutes goes back on the end of the current session's queue. */
export const REINSERT_WINDOW_MS = 20 * 60_000;

/** True when a just-graded card is due again soon enough to see it this
 *  session. `dueAt` is the API timestamp (UTC). */
export function shouldReinsert(
  dueAt: string | null | undefined,
  nowMs: number = Date.now(),
): boolean {
  const ms = parseUtcMs(dueAt);
  return ms !== null && ms <= nowMs + REINSERT_WINDOW_MS;
}

/**
 * How many cards a session would open with right now. The server counts
 * this with the same window definition the queue uses (`due_in_window`);
 * the fallback covers servers that predate that field.
 */
export function dueCountForWindow(
  stats: Pick<ReviewStatsResponse, "due_now" | "due_today"> & { due_in_window?: number },
  window: string | null | undefined,
): number {
  if (typeof stats.due_in_window === "number") return stats.due_in_window;
  return window === "now" ? stats.due_now : stats.due_today;
}

/** "new-3" → "HSK 3", "old-4" → "HSK 4 (old)", "new-7-9" → "HSK 7–9". */
export function formatHskLevel(level: string | number | null | undefined): string {
  if (level === null || level === undefined || level === "") return "";
  if (typeof level === "number") return `HSK ${level}`;
  const m = /^(new|old)-(\d+)(?:-(\d+))?(\+)?$/.exec(level);
  if (!m) return level;
  const [, version, from, to, plus] = m;
  const range = to ? `${from}–${to}` : `${from}${plus ?? ""}`;
  return version === "old" ? `HSK ${range} (old)` : `HSK ${range}`;
}

/**
 * Suggested FSRS grade from a writing quiz. Ratio-based instead of
 * hardcoded thresholds — 3 mistakes on 一 (1 stroke) is catastrophic, on
 * 鬱 (29 strokes) it's solid. Falls back to absolute thresholds if
 * strokes is 0 (stroke data failed to load).
 */
export function suggestedGradeForMistakes(mistakes: number, strokes: number): ReviewGrade {
  if (strokes <= 0) {
    if (mistakes === 0) return 4;
    if (mistakes <= 2) return 3;
    if (mistakes <= 5) return 2;
    return 1;
  }
  if (mistakes === 0) return 4;
  const ratio = mistakes / strokes;
  if (ratio <= 0.1) return 3; // Good — at most 1 mistake per 10 strokes
  if (ratio <= 0.25) return 2; // Hard — up to 1 in 4
  return 1; // Again — more than 1 in 4
}

export type AutoGradeDelay = 0 | 1000 | 2000 | 3000;
export const AUTO_GRADE_DELAYS: readonly AutoGradeDelay[] = [0, 1000, 2000, 3000];
export const DEFAULT_AUTO_GRADE_DELAY: AutoGradeDelay = 2000;

export function normalizeAutoGradeDelay(value: unknown): AutoGradeDelay {
  return AUTO_GRADE_DELAYS.includes(value as AutoGradeDelay)
    ? (value as AutoGradeDelay)
    : DEFAULT_AUTO_GRADE_DELAY;
}

// Elements that act on Space themselves; the review shortcut must not
// steal it from them.
const SPACE_OWNERS = "button, a[href], summary, select, [role='button'], [role='checkbox'], [role='radio']";

/**
 * Whether the review page should ignore this keydown: typing in a field,
 * a dialog open on top (every open modal marks itself aria-modal), or —
 * for Space only — a focused control that Space would activate.
 */
export function reviewShortcutBlocked(e: KeyboardEvent, doc: Document = document): boolean {
  const el = e.target instanceof HTMLElement ? e.target : null;
  if (el) {
    const tag = el.tagName;
    if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || el.isContentEditable) {
      return true;
    }
  }
  if (e.ctrlKey || e.metaKey || e.altKey) return true;
  if (doc.querySelector('[aria-modal="true"]') !== null) return true;
  if (e.key === " " && el && el.closest(SPACE_OWNERS)) return true;
  return false;
}
