import { defineStore } from "pinia";
import { computed, ref } from "vue";

import * as api from "@/api/client";
import type { AnalysisResponse } from "@/api/types";

export const useAnalysisStore = defineStore("analysis", () => {
  const inputText = ref("");
  const result = ref<AnalysisResponse | null>(null);
  const loading = ref(false);
  const error = ref<string | null>(null);
  /**
   * Backend id of the saved-text record this analysis represents. Set when
   * `loadSaved()` is called from the library; null when the user is reading
   * a fresh analysis they haven't saved yet (so we don't try to PATCH).
   */
  const savedTextId = ref<number | null>(null);
  /** Title of the loaded saved text — editable in the reader header. */
  const savedTextTitle = ref<string | null>(null);
  /** Tags array of the loaded saved text — editable in the reader header. */
  const savedTextTags = ref<string[]>([]);
  /** Original content snapshot — drives the "edited" pill when inputText drifts. */
  const savedTextOriginalContent = ref<string | null>(null);
  /**
   * 0..1 fraction — last-known reading progress for the loaded saved text.
   * Used by ReaderView to restore scroll position after the article renders.
   */
  const initialProgress = ref<number>(0);
  /**
   * Slug of the bundled library text currently loaded, or null when the
   * user is reading a saved/fresh analysis. Set by LibraryView.open() so
   * ReaderView can show the mark-as-read / take-quiz control.
   */
  const librarySlug = ref<string | null>(null);
  /** Whether the loaded library text has a comprehension quiz authored. */
  const libraryHasQuiz = ref(false);
  /**
   * Phase #99 — per-text glossary picker selection.
   * null  = use all glossary-flagged lists (the default for fresh analyses)
   * []    = explicitly use no glossary
   * [3,5] = use only those lists
   * Persisted on the saved_text record via /save and /update.
   */
  const glossaryListIds = ref<number[] | null>(null);
  let activeRequest: AbortController | null = null;

  const hasResult = computed(() => result.value !== null);
  /**
   * True when the user is reading a saved text but has edited its content
   * (so the in-DB snapshot is stale relative to the analysis they see now).
   * The reader shows an "edited" pill — Save updates the existing record.
   */
  const isEdited = computed(
    () =>
      savedTextId.value !== null &&
      savedTextOriginalContent.value !== null &&
      inputText.value !== savedTextOriginalContent.value,
  );

  async function analyze(text: string) {
    inputText.value = text;
    error.value = null;
    if (!text.trim()) {
      result.value = null;
      return;
    }

    // Cancel any in-flight analysis so the UI never shows stale results.
    if (activeRequest) activeRequest.abort();
    activeRequest = new AbortController();

    loading.value = true;
    try {
      result.value = await api.analyze(text, {
        glossary_list_ids: glossaryListIds.value,
        signal: activeRequest.signal,
      });
      // NOTE: savedTextId is intentionally preserved across re-analyse so the
      // user can edit a saved text + re-analyse + Save (which updates the
      // same record). Use reset() to fully decouple from a saved record.
    } catch (e) {
      if (e instanceof DOMException && e.name === "AbortError") return;
      error.value = e instanceof Error ? e.message : "Analysis failed";
      throw e;
    } finally {
      loading.value = false;
    }
  }

  function reset() {
    inputText.value = "";
    result.value = null;
    error.value = null;
    savedTextId.value = null;
    savedTextTitle.value = null;
    savedTextTags.value = [];
    savedTextOriginalContent.value = null;
    initialProgress.value = 0;
    glossaryListIds.value = null;
    librarySlug.value = null;
    libraryHasQuiz.value = false;
  }

  /**
   * Hydrate the store from a previously-saved text without re-hitting
   * /api/analyze. Used when opening a saved text from the library so the
   * reader matches what the user actually saved.
   */
  function loadSaved(
    text: string,
    data: AnalysisResponse,
    options: {
      id: number;
      progress?: number;
      title?: string;
      tags?: string[];
      glossaryListIds?: number[] | null;
    } | null = null,
    libraryEntry: { slug: string; hasQuiz: boolean } | null = null,
  ) {
    if (activeRequest) activeRequest.abort();
    inputText.value = text;
    result.value = data;
    error.value = null;
    loading.value = false;
    savedTextId.value = options?.id ?? null;
    savedTextTitle.value = options?.title ?? null;
    savedTextTags.value = options?.tags ?? [];
    savedTextOriginalContent.value = text;
    initialProgress.value = Math.max(0, Math.min(1, options?.progress ?? 0));
    glossaryListIds.value =
      options?.glossaryListIds === undefined ? null : options.glossaryListIds;
    librarySlug.value = libraryEntry?.slug ?? null;
    libraryHasQuiz.value = libraryEntry?.hasQuiz ?? false;
  }

  /**
   * Mark the current analysis as saved (called by ReaderView after POST /save).
   * Snapshots the current input as the "original" so the edited-pill behaves
   * right immediately after a fresh save.
   */
  function adoptSavedId(id: number, title: string, tags: string[]) {
    savedTextId.value = id;
    savedTextTitle.value = title;
    savedTextTags.value = tags;
    savedTextOriginalContent.value = inputText.value;
  }

  function updateSavedTitle(title: string) {
    savedTextTitle.value = title;
  }
  function updateSavedTags(tags: string[]) {
    savedTextTags.value = tags;
  }
  /** Called after a successful Save-update to refresh the "original" snapshot. */
  function markSynced() {
    savedTextOriginalContent.value = inputText.value;
  }

  return {
    inputText,
    result,
    loading,
    error,
    savedTextId,
    savedTextTitle,
    savedTextTags,
    savedTextOriginalContent,
    initialProgress,
    glossaryListIds,
    librarySlug,
    libraryHasQuiz,
    hasResult,
    isEdited,
    analyze,
    reset,
    loadSaved,
    adoptSavedId,
    updateSavedTitle,
    updateSavedTags,
    markSynced,
  };
});
