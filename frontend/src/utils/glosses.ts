/**
 * A word can carry several meanings with their provenance: the
 * dictionary's, a package's (Dao De Jing, ...) and a vocab list's.
 * These helpers label them and pick what a card shows.
 */
import type { WordGloss } from "@/api/types";

/** Short label for a gloss's provenance chip. */
export function glossLabel(g: WordGloss): string {
  if (g.source === "package") return g.tag || "Package";
  if (g.source === "list") return g.tag || "List";
  return "Dict";
}

/** Tooltip for the provenance chip. */
export function glossTitle(g: WordGloss): string {
  if (g.source === "package") return g.tag ? `From package ${g.tag}` : "From a package";
  if (g.source === "list") return g.tag ? `From your list ${g.tag}` : "From one of your lists";
  return "Dictionary";
}

function same(a: WordGloss, b: WordGloss): boolean {
  return a.source === b.source && (a.tag ?? null) === (b.tag ?? null);
}

/** Meanings other than the dictionary's, without the focused one. */
export function customGlosses(
  glosses: WordGloss[] | null | undefined,
  focus: WordGloss | null | undefined = null,
): WordGloss[] {
  return (glosses ?? []).filter(
    (g) => g.source !== "dictionary" && !(focus && same(g, focus)),
  );
}
