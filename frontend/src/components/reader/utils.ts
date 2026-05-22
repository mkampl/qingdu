/**
 * Pure helpers for the reader components — sentence grouping, HSK colour
 * mapping, pinyin display decisions. Kept TS-only so they can be unit-tested.
 */

import type { HskLevel, WordInfo } from "@/api/types";
import type { HskVersion, PinyinMode } from "@/stores/settings";

export interface Sentence {
  /** Stable key for v-for. */
  key: string;
  /** Words in reading order. Includes terminating punctuation and line breaks. */
  words: WordInfo[];
  /** The plain Chinese text — what we send to the translate API. */
  text: string;
  /** Sentences derived from a soft line break are rendered on their own line. */
  endsWithLineBreak: boolean;
}

const SENTENCE_END = /[。！？!?…\n]/;

/**
 * Group the flat words[] response from /api/analyze into sentences. We split
 * on any sentence-ending punctuation glyph and on explicit line-break tokens
 * (the API marks line breaks with translation_source === "linebreak").
 */
export function groupIntoSentences(words: WordInfo[]): Sentence[] {
  const sentences: Sentence[] = [];
  let current: WordInfo[] = [];
  let id = 0;

  const flush = (endsWithLineBreak: boolean) => {
    if (!current.length) return;
    sentences.push({
      key: `s-${id++}`,
      words: current,
      text: current
        .filter((w) => w.translation_source !== "linebreak")
        .map((w) => w.text)
        .join("")
        .trim(),
      endsWithLineBreak,
    });
    current = [];
  };

  for (const w of words) {
    if (w.translation_source === "linebreak" || w.text === "\n") {
      flush(true);
      continue;
    }
    current.push(w);
    if (SENTENCE_END.test(w.text)) {
      flush(false);
    }
  }
  flush(false);

  return sentences;
}

/**
 * Choose which level field to drive the colouring with, based on the user's
 * HSK-version preference. Falls back to whichever field exists.
 */
export function levelForVersion(
  word: WordInfo,
  version: HskVersion,
): HskLevel | null | undefined {
  if (version === "old") return word.level_old ?? word.level_new;
  return word.level_new ?? word.level_old;
}

/**
 * Return the matching `--color-hsk-N` CSS variable for a level string like
 * "new-3", "old-2", "Custom", or null.
 */
export function hskCssVar(level: HskLevel | null | undefined): string {
  if (!level || level === "unknown") return "var(--color-hsk-unknown)";
  if (level === "Custom") return "var(--color-accent)";
  const match = /([0-9]+)/.exec(String(level));
  if (!match) return "var(--color-hsk-unknown)";
  const num = Math.min(Math.max(parseInt(match[1], 10), 1), 9);
  return `var(--color-hsk-${num})`;
}

/**
 * Extract the numeric portion of a level (e.g. "new-3" -> 3, "HSK 5" -> 5).
 * Returns null for unrecognised inputs.
 */
export function levelNumber(level: string | null | undefined): number | null {
  if (!level) return null;
  const match = /([0-9]+)/.exec(level);
  return match ? parseInt(match[1], 10) : null;
}

/**
 * Decide whether to render pinyin above a given word, per the user's mode.
 * In auto mode, we show pinyin only for words above their estimated level.
 */
export function shouldShowPinyin(
  mode: PinyinMode,
  word: WordInfo,
  version: HskVersion,
  estimatedLevel: string | null,
): boolean {
  if (mode === "off") return false;
  if (mode === "on") return Boolean(word.pinyin);
  if (!word.pinyin) return false;

  const wordLevel = levelForVersion(word, version);
  const wordNum = levelNumber(wordLevel);
  const estNum = levelNumber(estimatedLevel);

  // Unknown or above-estimate -> show. Within-estimate -> hide.
  if (wordNum === null) return true;
  if (estNum === null) return true;
  return wordNum > estNum;
}

/**
 * Build the HSK distribution data for the strata bar. Returns ordered entries
 * with computed percentages — segments below a minimum threshold are merged
 * into "Other" so the bar stays readable.
 */
export interface DistributionSegment {
  /** "HSK1".."HSK9" or "Other" / "Unknown" */
  label: string;
  /** Numeric level (1-9) or null for special segments. */
  level: number | null;
  /** Count of words in this bucket. */
  count: number;
  /** Percentage of the total HSK-tagged words. */
  pct: number;
  /** CSS background colour for the segment. */
  color: string;
}

export function buildDistribution(
  distribution: Record<string, number>,
  total: number,
): DistributionSegment[] {
  if (total <= 0) return [];
  const entries: DistributionSegment[] = [];
  for (let i = 1; i <= 9; i++) {
    const count = distribution[`hsk${i}`] ?? 0;
    if (count === 0) continue;
    entries.push({
      label: `HSK ${i}`,
      level: i,
      count,
      pct: (count / total) * 100,
      color: `var(--color-hsk-${i})`,
    });
  }
  return entries;
}

/** Format a level token like "new-3" -> "HSK 3", "Custom" -> "Custom". */
export function levelDisplayName(level: HskLevel | null | undefined): string {
  if (!level || level === "unknown") return "Unknown";
  if (level === "Custom") return "Custom";
  const n = levelNumber(level);
  return n === null ? String(level) : `HSK ${n}`;
}
