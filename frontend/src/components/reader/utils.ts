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
  /** Absolute index of `words[0]` within the parent analysis.words array.
   *  Used by Phase D grammar matches to address tokens globally. */
  baseIdx: number;
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
  // Absolute index into `words` where the current sentence's first token lives.
  let nextBaseIdx = 0;
  let absoluteIdx = 0;

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
      baseIdx: nextBaseIdx,
    });
    current = [];
    nextBaseIdx = absoluteIdx;
  };

  for (const w of words) {
    if (w.translation_source === "linebreak" || w.text === "\n") {
      // A linebreak after a sentence-ender (e.g. "。\n") used to disappear
      // because the period already flushed the sentence with
      // endsWithLineBreak=false. Promote the just-flushed sentence so
      // section detection sees the paragraph boundary it actually was.
      if (current.length) {
        flush(true);
      } else if (sentences.length) {
        sentences[sentences.length - 1].endsWithLineBreak = true;
      }
      absoluteIdx += 1;
      nextBaseIdx = absoluteIdx;
      continue;
    }
    current.push(w);
    absoluteIdx += 1;
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

/* --- Section detection ----------------------------------------------------
 *
 * Long texts (articles, book chapters, anything imported from /discover)
 * need internal navigation. Two strategies, in order:
 *
 *  1. Numbered-heading mode — texts authored with explicit headings like
 *     "一、…", "二、…", "1.…" land here. We split at every paragraph-start
 *     sentence whose first glyph matches that pattern. The H2 anchor then
 *     carries a real heading instead of a truncated mid-paragraph snippet,
 *     and "Mark remaining as known" buttons land at semantically meaningful
 *     boundaries instead of every ~480 chars.
 *
 *  2. Char-budget mode — fallback for unstructured prose. We walk sentences
 *     and break at paragraph boundaries once we've accumulated
 *     TARGET_SECTION_CHARS. Without this many long articles would render as
 *     a single section with no internal navigation.
 *
 * Both modes only kick in when the text is long enough to warrant a TOC
 * and at least MIN_SECTION_COUNT sections come out — a 2-entry TOC looks
 * broken and gives no navigation value.
 */

export interface Section {
  /** v-for key — index in the sections array, stable across renders. */
  key: string;
  /** Display title — first sentence snippet of this section. */
  title: string;
  /** Index of the first sentence in the parent `sentences` array. */
  startSentenceIdx: number;
}

/** Target chars per section in char-budget mode. Smaller = finer TOC,
 *  more clicks. Only used when no numbered headings exist. */
const TARGET_SECTION_CHARS = 480;
/** Below this total length, we don't bother with sections at all. */
const MIN_TEXT_LENGTH_FOR_TOC = 900;
/** A useful TOC needs at least this many sections; below it we suppress it. */
const MIN_SECTION_COUNT = 3;

/** A paragraph-start sentence that begins with a numbered prefix —
 *  "一、", "二.", "1.", "10、" etc. We treat these as authored headings. */
const HEADING_PREFIX_RE = /^[一二三四五六七八九十百千万0-9]+[、.,．：:]/;

export function detectSections(sentences: Sentence[]): Section[] {
  if (!sentences.length) return [];

  const totalChars = sentences.reduce((sum, s) => sum + s.text.length, 0);
  if (totalChars < MIN_TEXT_LENGTH_FOR_TOC) return [];

  // 1) Try numbered-heading mode. A sentence counts as a heading only when
  // it sits at the start of a paragraph (idx 0 or preceded by a line
  // break) so we don't catch "一、二" embedded inside running prose.
  const headingIdxs: number[] = [];
  for (let i = 0; i < sentences.length; i++) {
    const isParaStart = i === 0 || sentences[i - 1].endsWithLineBreak;
    if (isParaStart && HEADING_PREFIX_RE.test(sentences[i].text.trim())) {
      headingIdxs.push(i);
    }
  }

  if (headingIdxs.length >= MIN_SECTION_COUNT) {
    const sections: Section[] = [];
    // If the first heading isn't at idx 0, the preamble (title page,
    // intro paragraph, etc.) forms its own section so it still gets a
    // bulk-mark action of its own.
    if (headingIdxs[0] > 0) {
      sections.push({
        key: "sec-pre",
        title: snippetTitle(sentences[0].text),
        startSentenceIdx: 0,
      });
    }
    for (let j = 0; j < headingIdxs.length; j++) {
      const startIdx = headingIdxs[j];
      sections.push({
        key: `sec-${j}`,
        title: snippetTitle(sentences[startIdx].text),
        startSentenceIdx: startIdx,
      });
    }
    return sections;
  }

  // 2) Char-budget fallback.
  const sections: Section[] = [];
  let pendingStart = 0;
  let acc = 0;

  function flushAt(idx: number) {
    const first = sentences[pendingStart];
    if (!first) return;
    sections.push({
      key: `sec-${sections.length}`,
      title: snippetTitle(first.text),
      startSentenceIdx: pendingStart,
    });
    pendingStart = idx;
    acc = 0;
  }

  for (let i = 0; i < sentences.length; i++) {
    const sentence = sentences[i];
    acc += sentence.text.length;
    // Only close a section at a paragraph boundary so we don't slice prose
    // mid-thought. The last sentence is implicitly a boundary too.
    const atBoundary = sentence.endsWithLineBreak || i === sentences.length - 1;
    if (atBoundary && acc >= TARGET_SECTION_CHARS) {
      flushAt(i + 1);
    }
  }
  // Tail
  if (pendingStart < sentences.length) flushAt(sentences.length);

  // Suppress trivial TOCs — a 2-section TOC looks broken.
  return sections.length >= MIN_SECTION_COUNT ? sections : [];
}

function snippetTitle(text: string, max = 28): string {
  const clean = text.replace(/\s+/g, " ").trim();
  if (!clean) return "—";
  // Strip leading markdown-ish headers if present (trafilatura sometimes
  // leaves '#' lines in the markdown output).
  const noHeading = clean.replace(/^#+\s*/, "");
  return noHeading.length > max ? `${noHeading.slice(0, max)}…` : noHeading;
}
