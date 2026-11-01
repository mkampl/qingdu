import { computed, watch, type Ref } from "vue";

import { ApiError } from "@/api/client";
import type { UserWordState, WordContext, WordSnapshot } from "@/api/client";
import type { WordInfo } from "@/api/types";
import { effectiveWordState } from "@/components/reader/utils";
import { useAnalysisStore } from "@/stores/analysis";
import { useAuthStore } from "@/stores/auth";
import { useReaderStore } from "@/stores/reader";
import { useSettingsStore } from "@/stores/settings";
import { useToastStore } from "@/stores/toast";
import { useUserWordsStore } from "@/stores/userWords";

/**
 * Learning state of the word open in the popover. Explicit choices come
 * from the state buttons (clicking the active state clears it). With
 * autoLearnOnClick on, opening a 'new' word promotes it to 'learning'.
 */
export function useWordStateControl(word: Ref<WordInfo | null>) {
  const analysis = useAnalysisStore();
  const auth = useAuthStore();
  const reader = useReaderStore();
  const settings = useSettingsStore();
  const toasts = useToastStore();
  const userWords = useUserWordsStore();

  // Before the user-words store hydrates, the analysis token's own state is
  // the best we have — without it a known word looks new and auto-learn would
  // demote it to learning.
  const currentState = computed<UserWordState | null>(() => {
    if (!word.value) return null;
    return effectiveWordState(
      userWords.stateOf(word.value.text),
      userWords.hydrated,
      word.value.user_state,
    );
  });

  /**
   * Build the optional package-snapshot for the API call. Only populated
   * when the clicked word was glossed by a pre-analyzed JSON package — we
   * deliberately do NOT ship dictionary-sourced fields, so the backend
   * falls through to its normal lookup_pinyin_meaning() chain. Without
   * this, package-curated meanings (e.g. the bundled Dao De Jing's
   * Daoist-context glosses) get clobbered by CC-CEDICT on the first click.
   */
  function buildSnapshot(): WordSnapshot | null {
    const w = word.value;
    if (!w || w.translation_source !== "package") return null;
    return {
      meaning: w.meaning ?? null,
      pinyin: w.pinyin ?? null,
      translation_source: "package",
      package_source: w.package_source ?? null,
    };
  }

  /** The sentence the word was clicked in, kept as its review context. */
  function wordContext(): WordContext {
    return { sentence: reader.selectedSentenceText, librarySlug: analysis.librarySlug };
  }

  watch(word, async (next) => {
    if (!next || !auth.isAuthed) return;
    // Skip linebreaks and other non-CJK tokens — we keep state for words only.
    if (!next.text || next.text === "\n") return;
    // Opt-in (Settings → Review): by default a click only shows the meaning.
    if (!settings.autoLearnOnClick) return;
    if (next.parts?.length) return;
    if (currentState.value === null) {
      try {
        await userWords.setState(
          next.text,
          "learning",
          analysis.savedTextId ?? null,
          buildSnapshot(),
          wordContext(),
        );
      } catch {
        /* network error shouldn't block the popover */
      }
    }
  });

  async function setWordState(state: UserWordState) {
    if (!word.value) return;
    // Toggle off if the user clicks the currently active state.
    if (currentState.value === state) {
      try {
        await userWords.clearState(word.value.text);
      } catch {
        /* ignore */
      }
      return;
    }
    try {
      await userWords.setState(
        word.value.text,
        state,
        analysis.savedTextId ?? null,
        buildSnapshot(),
        wordContext(),
      );
    } catch (e) {
      toasts.error(
        e instanceof ApiError && e.status === 422 ? e.message : "Couldn't update word state",
      );
    }
  }

  /** Marks one part of a non-dictionary token as learning. */
  async function learnPart(part: string) {
    if (userWords.stateOf(part)) return;
    try {
      await userWords.setState(part, "learning", analysis.savedTextId ?? null, null, wordContext());
    } catch {
      toasts.error("Couldn't update word state");
    }
  }

  return { currentState, setWordState, learnPart };
}
