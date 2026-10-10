import type { VocabularyListSummary } from "@/api/types";

/** Section the add-to-list field starts with for a list: its first one, else "Main". */
export function defaultSectionName(
  list: Pick<VocabularyListSummary, "sections"> | null | undefined,
): string {
  return list?.sections?.find((s) => s.name)?.name ?? "Main";
}

/** Name of the section that already holds `hanzi`, or null. */
export function sectionContaining(
  list: Pick<VocabularyListSummary, "sections"> | null | undefined,
  hanzi: string,
): string | null {
  for (const s of list?.sections ?? []) {
    if (s.words?.some((w) => w.hanzi === hanzi || w.traditional === hanzi)) {
      return s.name;
    }
  }
  return null;
}

/**
 * One-shot gate for inline rename inputs. Enter, Escape and blur can all
 * fire for the same edit (the input unmounts after Enter/Escape and some
 * browsers then blur it), so the first one to `take()` wins: Escape
 * really cancels and Enter + blur don't PUT twice.
 */
export function createEditGate() {
  let open = false;
  return {
    begin() {
      open = true;
    },
    take(): boolean {
      if (!open) return false;
      open = false;
      return true;
    },
  };
}

/**
 * Counts shown for a list. The card on /vocab and the detail page both use
 * this, so they agree — empty sections count as sections.
 */
export function listCounts(list: Pick<VocabularyListSummary, "sections">): {
  sections: number;
  words: number;
} {
  const sections = list.sections ?? [];
  return {
    sections: sections.length,
    words: sections.reduce((n, s) => n + (s.words?.length ?? 0), 0),
  };
}
