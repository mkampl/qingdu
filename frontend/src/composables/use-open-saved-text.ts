import { useRouter } from "vue-router";

import * as api from "@/api/client";
import { useAnalysisStore } from "@/stores/analysis";
import { useReaderStore } from "@/stores/reader";
import { useToastStore } from "@/stores/toast";
import { normalizeProgress, parseTags } from "@/utils/saved-text";

/**
 * Open one of the user's saved texts in the reader: fetch the full text,
 * hydrate the analysis store with the saved analysis (no re-analyse) and
 * go to the reader. Every entry point (Texts, the Today panel, previous /
 * next in a folder) goes through here so the reader always knows the
 * text's id and its place in its folder. Resolves to false when the text
 * couldn't be loaded (a toast says why).
 */
export function useOpenSavedText() {
  const analysis = useAnalysisStore();
  const reader = useReaderStore();
  const toast = useToastStore();
  const router = useRouter();

  return async function openSavedText(id: number): Promise<boolean> {
    try {
      const full = await api.getText(id);
      analysis.loadSaved(full.content, full.analysisData, {
        id: full.id,
        progress: normalizeProgress(full.reading_progress),
        title: full.title ?? "",
        tags: parseTags(full.tags),
        glossaryListIds: full.glossary_list_ids,
        series: full.series ?? null,
      });
      reader.reset();
      void router.push("/");
      return true;
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Couldn't open that text");
      return false;
    }
  };
}
