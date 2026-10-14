import { useRouter } from "vue-router";

import * as api from "@/api/client";
import type { AnalysisResponse } from "@/api/types";
import { useAnalysisStore } from "@/stores/analysis";
import { useReaderStore } from "@/stores/reader";
import { useToastStore } from "@/stores/toast";

/**
 * Open a bundled library text in the reader. Every entry point (Library,
 * Discover, the reader's Today panel) goes through here so the reader
 * always knows the slug: that is what shows the quiz and "Mark as read".
 * Resolves to false when the text couldn't be loaded (a toast says why).
 */
export function useOpenLibraryText() {
  const analysis = useAnalysisStore();
  const reader = useReaderStore();
  const toast = useToastStore();
  const router = useRouter();

  return async function openLibraryText(slug: string): Promise<boolean> {
    try {
      const entry = await api.getLibraryEntry(slug);
      analysis.loadSaved(entry.text, entry.analyzed as AnalysisResponse, null, {
        slug,
        hasQuiz: entry.has_quiz === true,
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
