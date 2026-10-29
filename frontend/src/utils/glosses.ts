/**
 * A word can carry several meanings with their provenance: the
 * dictionary's, a package's (Dao De Jing, ...), a vocab list's and the
 * meaning in a text it was pre-learned from.
 * These helpers label them and pick what a card shows.
 */
import type { WordGloss } from "@/api/types";

/** Short label for a gloss's provenance chip. */
export function glossLabel(g: WordGloss): string {
  if (g.source === "package") return g.tag || "Package";
  if (g.source === "list") return g.tag || "List";
  if (g.source === "text") return g.tag || "Text";
  return "Dict";
}

/** Tooltip for the provenance chip. */
export function glossTitle(g: WordGloss): string {
  if (g.source === "package") return g.tag ? `From package ${g.tag}` : "From a package";
  if (g.source === "list") return g.tag ? `From your list ${g.tag}` : "From one of your lists";
  if (g.source === "text") return g.tag ? `Meaning in the text ${g.tag}` : "Meaning in a text";
  return "Dictionary";
}

function same(a: WordGloss, b: WordGloss): boolean {
  return a.source === b.source && (a.tag ?? null) === (b.tag ?? null);
}

const norm = (s: string | null | undefined) => (s ?? "").trim().toLowerCase();

// Which of a word's own meanings leads: a glossary or list (the school's
// or textbook's word), then the meanings in texts, then packages.
const RANK: Record<string, number> = { list: 0, text: 1, package: 2 };
const rank = (g: WordGloss) => RANK[g.source] ?? 3;

/** The meaning a card leads with when no text or list is in focus: the
 *  learner's own before the dictionary's. */
export function leadGloss(glosses: WordGloss[] | null | undefined): WordGloss | null {
  return customGlosses(glosses)[0] ?? null;
}

/** Meanings other than the dictionary's, without the focused one, in
 *  RANK order. A meaning two sources share (a text's glossary and
 *  a list built from the same glossary) is shown once. */
export function customGlosses(
  glosses: WordGloss[] | null | undefined,
  focus: WordGloss | null | undefined = null,
): WordGloss[] {
  const seen = new Set<string>(focus ? [norm(focus.meaning)] : []);
  const ordered = [...(glosses ?? [])].sort((a, b) => rank(a) - rank(b));
  return ordered.filter((g) => {
    if (g.source === "dictionary" || (focus && same(g, focus))) return false;
    const key = norm(g.meaning);
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}
