import { defineStore } from "pinia";
import { ref } from "vue";

import * as api from "@/api/client";
import type { TranslateResponse, WordInfo } from "@/api/types";

interface AnchorRect {
  top: number;
  left: number;
  bottom: number;
  right: number;
  width: number;
}

type TranslationState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "ok"; data: TranslateResponse }
  | { status: "error"; message: string };

export const useReaderStore = defineStore("reader", () => {
  const selectedWord = ref<WordInfo | null>(null);
  const selectedAnchor = ref<AnchorRect | null>(null);
  /** Sentence containing the selected word — used by the popover to offer
   *  "translate sentence" as a one-tap follow-up. */
  const selectedSentenceKey = ref<string | null>(null);
  const selectedSentenceText = ref<string | null>(null);

  /** Map keyed by sentence text -> translation cache for this session. */
  const sentenceTranslations = ref(new Map<string, TranslationState>());
  /** Track which sentence is currently open (only one at a time). */
  const openSentenceKey = ref<string | null>(null);

  function selectWord(
    word: WordInfo,
    anchorEl?: HTMLElement | null,
    sentence?: { key: string; text: string } | null,
  ) {
    selectedWord.value = word;
    selectedSentenceKey.value = sentence?.key ?? null;
    selectedSentenceText.value = sentence?.text ?? null;
    if (anchorEl) {
      const rect = anchorEl.getBoundingClientRect();
      selectedAnchor.value = {
        top: rect.top,
        left: rect.left,
        bottom: rect.bottom,
        right: rect.right,
        width: rect.width,
      };
    } else {
      selectedAnchor.value = null;
    }
  }

  function clearWord() {
    selectedWord.value = null;
    selectedAnchor.value = null;
    selectedSentenceKey.value = null;
    selectedSentenceText.value = null;
  }

  function toggleSentence(key: string) {
    openSentenceKey.value = openSentenceKey.value === key ? null : key;
  }

  function closeSentence() {
    openSentenceKey.value = null;
  }

  async function translateSentence(text: string): Promise<void> {
    if (!text) return;
    const existing = sentenceTranslations.value.get(text);
    if (existing && (existing.status === "ok" || existing.status === "loading")) {
      return;
    }
    sentenceTranslations.value.set(text, { status: "loading" });
    try {
      const data = await api.translate(text);
      sentenceTranslations.value.set(text, { status: "ok", data });
    } catch (e) {
      sentenceTranslations.value.set(text, {
        status: "error",
        message: e instanceof Error ? e.message : "Translation failed",
      });
    }
  }

  function reset() {
    selectedWord.value = null;
    selectedAnchor.value = null;
    selectedSentenceKey.value = null;
    selectedSentenceText.value = null;
    openSentenceKey.value = null;
    sentenceTranslations.value = new Map();
  }

  return {
    selectedWord,
    selectedAnchor,
    selectedSentenceKey,
    selectedSentenceText,
    sentenceTranslations,
    openSentenceKey,
    selectWord,
    clearWord,
    toggleSentence,
    closeSentence,
    translateSentence,
    reset,
  };
});

export type { TranslationState };
