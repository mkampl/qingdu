import { computed, ref } from "vue";
import { useRouter } from "vue-router";

import * as api from "@/api/client";
import { ApiError } from "@/api/client";
import type { VocabularyListSummary } from "@/api/types";
import { onAuthReady } from "@/composables/use-auth-ready";
import { useToastStore } from "@/stores/toast";
import { useUserWordsStore } from "@/stores/userWords";
import { useVocabListsStore } from "@/stores/vocab-lists";
import type { LoadState } from "@/utils/load-state";
import { listCounts } from "@/utils/vocab-lists";

export interface WordForm {
  mode: "add" | "edit";
  sectionName: string;
  hanzi: string;
  meaning: string;
  oldHanzi: string;
}

function errorText(e: unknown, fallback: string): string {
  return e instanceof ApiError ? e.message : fallback;
}

/**
 * One vocab list, loaded once the session check settles, and every edit
 * to it: each is sent to the server, applied to the local copy and
 * reported in a toast. `busy` covers the list-wide actions (rename,
 * glossary, delete, CSV).
 */
export function useVocabList(listId: () => number) {
  const toasts = useToastStore();
  const userWords = useUserWordsStore();
  // The reader's WordPopover / GlossaryPicker read the cached vocab-lists
  // store, not this local state — invalidate it after any mutation so the
  // pickers don't serve stale lists until a full page reload.
  const vocabListsCache = useVocabListsStore();
  const router = useRouter();

  const state = ref<LoadState<{ list: VocabularyListSummary }, { status: "notfound" }>>({
    status: "idle",
  });
  const busy = ref(false);

  async function load() {
    const id = listId();
    if (!Number.isInteger(id) || id <= 0) {
      state.value = { status: "notfound" };
      return;
    }
    state.value = { status: "loading" };
    try {
      const list = await api.getVocabularyList(id);
      state.value = { status: "ok", list };
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) {
        state.value = { status: "notfound" };
        return;
      }
      state.value = { status: "error", message: errorText(e, "Couldn't load this list.") };
    }
  }

  // Waits for the boot-time session check, so a hard reload of this page
  // doesn't flash the Sign-in state for a logged-in user.
  onAuthReady(load, () => {
    state.value = { status: "idle" };
  });

  const list = computed(() => (state.value.status === "ok" ? state.value.list : null));

  // Same counting as the card on /vocab (empty sections count).
  const counts = computed(() =>
    list.value ? listCounts(list.value) : { sections: 0, words: 0 },
  );

  /** Apply a local edit and refresh the shared cache the reader's popover
   *  and glossary picker read (in the background — nothing blanks). */
  function syncList(mutator: (l: VocabularyListSummary) => VocabularyListSummary) {
    if (state.value.status !== "ok") return;
    state.value = { status: "ok", list: mutator({ ...state.value.list }) };
    void vocabListsCache.invalidate();
  }

  async function rename(newName: string) {
    if (!list.value) return;
    busy.value = true;
    try {
      // Name only: re-sending the sections we got from GET would write back
      // their display-script conversion (traditional users' hanzi).
      await api.updateVocabularyList(list.value.id, { name: newName });
      syncList((l) => ({ ...l, name: newName }));
      toasts.success("Renamed.");
    } catch (e) {
      toasts.error(errorText(e, "Couldn't rename the list."));
    } finally {
      busy.value = false;
    }
  }

  async function toggleGlossary() {
    if (!list.value) return;
    const next = !list.value.apply_as_glossary;
    busy.value = true;
    try {
      await api.updateVocabularyList(list.value.id, { apply_as_glossary: next });
      syncList((l) => ({ ...l, apply_as_glossary: next }));
      toasts.success(
        next
          ? "Offered as a glossary: pick it per text in the reader."
          : "No longer offered as a glossary (texts using it keep it).",
      );
    } catch (e) {
      toasts.error(errorText(e, "Couldn't update glossary setting."));
    } finally {
      busy.value = false;
    }
  }

  async function deleteList() {
    if (!list.value) return;
    busy.value = true;
    try {
      await api.deleteVocabularyList(list.value.id);
      vocabListsCache.invalidate();
      toasts.success(`Deleted “${list.value.name}”.`);
      void router.push("/vocab");
    } catch (e) {
      toasts.error(errorText(e, "Couldn't delete the list."));
    } finally {
      busy.value = false;
    }
  }

  async function exportCsv() {
    if (!list.value) return;
    busy.value = true;
    try {
      await api.openDownload(`/api/vocabulary-lists/${list.value.id}/export`);
      toasts.success("Download started.");
    } catch (e) {
      toasts.error(errorText(e, "CSV export failed."));
    } finally {
      busy.value = false;
    }
  }

  /** Adds an empty section; false when the request failed. */
  async function addSection(name: string): Promise<boolean> {
    if (!list.value) return false;
    try {
      await api.addSectionToList(list.value.id, name);
      syncList((l) => ({ ...l, sections: [...l.sections, { name, words: [] }] }));
      return true;
    } catch (e) {
      toasts.error(errorText(e, "Couldn't add the section."));
      return false;
    }
  }

  async function renameSection(oldName: string, newName: string) {
    if (!list.value) return;
    try {
      await api.renameSection(list.value.id, { old_name: oldName, new_name: newName });
      syncList((l) => ({
        ...l,
        sections: l.sections.map((s) => (s.name === oldName ? { ...s, name: newName } : s)),
      }));
      toasts.success("Section renamed.");
    } catch (e) {
      toasts.error(errorText(e, "Couldn't rename the section."));
    }
  }

  async function deleteSection(name: string) {
    if (!list.value) return;
    try {
      await api.deleteSection(list.value.id, name);
      syncList((l) => ({ ...l, sections: l.sections.filter((s) => s.name !== name) }));
      toasts.success(`Section “${name}” deleted.`);
    } catch (e) {
      toasts.error(errorText(e, "Couldn't delete the section."));
    }
  }

  /** Adds or edits a word (level "Custom", pinyin from the server). Throws
   *  on failure, for the form to show. */
  async function saveWord(form: WordForm) {
    if (!list.value) return;
    const { sectionName, oldHanzi, mode } = form;
    const hanzi = form.hanzi.trim();
    const meaning = form.meaning.trim();
    if (mode === "add") {
      const result = await api.addWordToList(list.value.id, {
        section_name: sectionName,
        hanzi,
        meaning,
      });
      const pinyin = result.pinyin ?? "";
      syncList((l) => ({
        ...l,
        sections: l.sections.map((s) =>
          s.name === sectionName
            ? {
                ...s,
                words: s.words.some((w) => w.hanzi === hanzi)
                  ? s.words
                  : [...s.words, { hanzi, pinyin, meaning, level: "Custom" }],
              }
            : s,
        ),
      }));
    } else {
      const result = await api.updateWordInList(list.value.id, {
        section_name: sectionName,
        old_hanzi: oldHanzi,
        word: { hanzi, meaning },
      });
      const pinyin = result.pinyin ?? "";
      syncList((l) => ({
        ...l,
        sections: l.sections.map((s) =>
          s.name === sectionName
            ? {
                ...s,
                words: s.words.map((w) =>
                  w.hanzi === oldHanzi ? { hanzi, pinyin, meaning, level: "Custom" } : w,
                ),
              }
            : s,
        ),
      }));
    }
  }

  async function deleteWord(sectionName: string, hanzi: string) {
    if (!list.value) return;
    try {
      await api.deleteWordFromList(list.value.id, { section_name: sectionName, hanzi });
      syncList((l) => ({
        ...l,
        sections: l.sections.map((s) =>
          s.name === sectionName ? { ...s, words: s.words.filter((w) => w.hanzi !== hanzi) } : s,
        ),
      }));
    } catch (e) {
      toasts.error(errorText(e, "Couldn't delete the word."));
    }
  }

  const learning = ref(false);
  // Name of the section being taken into review, if one is.
  const learningSection = ref<string | null>(null);

  /** Take the whole list, or one section of it, into review. */
  async function learn(sectionName: string | null = null) {
    if (learning.value) return;
    learning.value = true;
    learningSection.value = sectionName;
    try {
      const r = await api.learnVocabularyList(listId(), sectionName);
      if (r.added.length) {
        const next = { ...userWords.states };
        for (const w of r.added) next[w] = "learning";
        userWords.states = next;
      }
      const n = r.added.length;
      toasts.success(
        n
          ? `Added ${n} word${n === 1 ? "" : "s"} to your review` +
              (r.already_tracked ? ` (${r.already_tracked} already there).` : ".")
          : "Every word of this list is already in your review.",
      );
    } catch (e) {
      toasts.error(e instanceof Error ? e.message : "Couldn't add the list");
    } finally {
      learning.value = false;
      learningSection.value = null;
    }
  }

  return {
    state,
    list,
    counts,
    busy,
    learning,
    learningSection,
    rename,
    toggleGlossary,
    deleteList,
    exportCsv,
    addSection,
    renameSection,
    deleteSection,
    saveWord,
    deleteWord,
    learn,
  };
}
