/**
 * Helpers for showing a word's headline gloss next to its other senses.
 *
 * The API sends `meaning` (the headline, already stripped of register
 * tags like "(bound form)" and long editorial notes) and `meanings` (every
 * sense, full text). The headline is not always `meanings[0]`: the
 * dictionary picks the learner-facing sense from anywhere in the list.
 * So the "other meanings" list must drop the sense the headline came
 * from, not blindly the first entry. Mirrors `is_same_sense` in
 * app/services/cedict_loader.py.
 */

// Register tags / editorial notes the backend strips off the headline.
// Kept loose on purpose: comparing is about recognising the same sense,
// not about reproducing the backend's display rules exactly.
const LEADING_PAREN_RE = /^\([^()]*\)\s*/;
const TRAILING_PAREN_RE = /\s*\([^()]*\)$/;
const HAS_WORD_RE = /[A-Za-z]{2,}/;

function stripParens(text: string): string {
  let s = text.trim();
  for (;;) {
    const m = LEADING_PAREN_RE.exec(s);
    if (!m) break;
    const rest = s.slice(m[0].length);
    if (!HAS_WORD_RE.test(rest)) break;
    s = rest;
  }
  // A sense cut off mid-note leaves an unclosed "(" tail.
  if ((s.match(/\(/g) ?? []).length > (s.match(/\)/g) ?? []).length) {
    s = s.slice(0, s.lastIndexOf("("));
  }
  const t = TRAILING_PAREN_RE.exec(s);
  if (t && HAS_WORD_RE.test(s.slice(0, t.index))) {
    s = s.slice(0, t.index);
  }
  return s;
}

function senseKey(text: string): string {
  return stripParens(text)
    .replace(/[\s…]+/g, " ")
    .replace(/^[\s;,]+|[\s;,]+$/g, "")
    .toLowerCase();
}

/** True when `sense` is the sense `headline` was derived from. */
export function isSameSense(headline: string, sense: string): boolean {
  const a = senseKey(headline);
  const b = senseKey(sense);
  if (!a || !b) return false;
  if (a === b) return true;
  const aCut = headline.trimEnd().endsWith("…");
  const bCut = sense.trimEnd().endsWith("…");
  return (aCut && b.startsWith(a)) || (bCut && a.startsWith(b));
}

/**
 * The senses to list under the headline: every entry of `meanings` that
 * isn't the headline's own sense, in order, de-duplicated, optionally
 * capped at `max`.
 */
export function otherMeanings(
  meaning: string | null | undefined,
  meanings: readonly string[] | null | undefined,
  max?: number,
): string[] {
  const head = (meaning ?? "").trim();
  const out: string[] = [];
  const seen = new Set<string>();
  for (const m of meanings ?? []) {
    const text = (m ?? "").trim();
    if (!text) continue;
    if (head && isSameSense(head, text)) continue;
    const key = senseKey(text) || text;
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(text);
    if (max !== undefined && out.length >= max) break;
  }
  return out;
}
