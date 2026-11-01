<script setup lang="ts">
/**
 * The popover for the selected word: a card at the word on desktop, a
 * bottom sheet on phones. Meaning, sense in the sentence, word state,
 * radical, foldouts, add to list, and a way to translate the sentence.
 */
import { computed, ref, watch } from "vue";

import * as api from "@/api/client";
import { useReaderStore } from "@/stores/reader";
import { useSettingsStore } from "@/stores/settings";
import { useAuthStore } from "@/stores/auth";
import { useDismiss } from "@/composables/use-dismiss";
import { useTtsPlayer } from "@/composables/use-tts-player";
import { useWordPopoverPlacement } from "@/composables/use-word-popover-placement";
import { useWordStateControl } from "@/composables/use-word-state-control";

import AddToListPanel from "./AddToListPanel.vue";
import WordFoldouts from "./WordFoldouts.vue";
import WordHeading from "./WordHeading.vue";
import WordMeanings from "./WordMeanings.vue";
import WordParts from "./WordParts.vue";
import WordSense from "./WordSense.vue";
import WordStateButtons from "./WordStateButtons.vue";
import { levelForVersion } from "./utils";

const reader = useReaderStore();
const settings = useSettingsStore();
const auth = useAuthStore();

const word = computed(() => reader.selectedWord);

const popoverRef = ref<HTMLElement | null>(null);
// A click outside closes the popover, except on another HSK-wash word:
// the new selection overrides this one (handled by selectWord). A dialog
// on top (share, settings) gets Escape first.
useDismiss(() => !!word.value, popoverRef, () => reader.clearWord(), {
  capture: true,
  ignore: (target) => !!(target as HTMLElement).closest?.(".hsk-wash"),
  yieldToOverlays: true,
});

const { isMobile, contentRef, desktopPosition } = useWordPopoverPlacement(popoverRef);

const { loading: ttsLoading, play: playAudio } = useTtsPlayer();
async function playTts() {
  const text = word.value?.text;
  if (!text) return;
  await playAudio(() => api.tts(text));
}

watch(word, (next) => {
  if (next) ttsLoading.value = false;
});

const { currentState, setWordState, learnPart } = useWordStateControl(word);

function translateSentenceFromWord() {
  const sentenceKey = reader.selectedSentenceKey;
  const sentenceText = reader.selectedSentenceText;
  if (!sentenceKey || !sentenceText) return;
  reader.clearWord();
  // Open the inline annotation under the sentence + fire the translate.
  if (reader.openSentenceKey !== sentenceKey) reader.toggleSentence(sentenceKey);
  void reader.translateSentence(sentenceText);
}

// Tokens that are not dictionary words carry their dictionary parts
// instead of a meaning; they can't be saved as words.
const wordParts = computed(() => word.value?.parts ?? []);

// Source pill in the footer; hsk/linebreak/parts are not worth naming.
const shownSource = computed(() => {
  const src = word.value?.translation_source;
  return src && !["hsk", "linebreak", "parts"].includes(src) ? src : null;
});

const wordLevel = computed(() =>
  word.value ? levelForVersion(word.value, settings.hskVersion) : null,
);

// Stays open from word to word once the user wants it (unlike stroke
// order, it is small).
const detailsOpen = ref(false);
const wordHasCjk = computed(() => !!word.value && /[一-鿿]/.test(word.value.text));
</script>

<template>
  <Teleport to="body">
    <Transition
      enter-active-class="transition duration-150 ease-out"
      enter-from-class="opacity-0 scale-95"
      enter-to-class="opacity-100 scale-100"
      leave-active-class="transition duration-100 ease-in"
      leave-from-class="opacity-100"
      leave-to-class="opacity-0"
    >
      <div
        v-if="word"
        ref="popoverRef"
        role="dialog"
        aria-modal="false"
        class="z-50 w-[min(20rem,calc(100vw-1.5rem))] origin-top overflow-y-auto overscroll-contain bg-bg-elevated text-fg shadow-xl ring-1 ring-border"
        :class="
          isMobile
            ? 'fixed inset-x-3 bottom-3 max-h-[calc(100dvh-1.5rem-env(safe-area-inset-top))] rounded-2xl pb-[env(safe-area-inset-bottom)]'
            : 'fixed rounded-lg'
        "
        :style="
          !isMobile && desktopPosition
            ? {
                top: `${desktopPosition.top}px`,
                left: `${desktopPosition.left}px`,
                maxHeight: `${desktopPosition.maxHeight}px`,
              }
            : undefined
        "
      >
        <!-- Accent rule at the top — letterpress key line. -->
        <div
          class="h-px w-full"
          :style="{ backgroundColor: 'var(--color-accent)' }"
        />

        <div ref="contentRef" class="px-5 pt-4 pb-5">
          <WordHeading
            :word="word"
            :level="wordLevel"
            :tts-loading="ttsLoading"
            @play="playTts"
          />

          <WordMeanings :word="word" />

          <WordSense :word="word" :sentence="reader.selectedSentenceText" />

          <WordParts v-if="wordParts.length" :parts="wordParts" @learn="learnPart" />

          <!-- Word state — LingQ-style progress tracker. Authenticated only;
               anonymous users still get meaning + radical without the gate. -->
          <WordStateButtons
            v-if="auth.isAuthed && word.text && word.text !== '\n' && !wordParts.length"
            :current="currentState"
            @set="setWordState"
          />

          <!-- Radical -->
          <div
            v-if="word.radical"
            class="mt-4 flex items-baseline gap-2 border-t border-border-subtle pt-3 text-xs"
          >
            <span class="font-mono uppercase tracking-wider text-fg-subtle">
              Radical
            </span>
            <span class="font-cn-serif text-base text-fg">
              {{ word.radical }}
            </span>
            <span v-if="word.radical_pinyin" class="text-fg-muted">
              {{ word.radical_pinyin }}
            </span>
          </div>

          <WordFoldouts v-if="wordHasCjk" v-model:details-open="detailsOpen" :word="word" />

          <!-- Signed-in users only. -->
          <AddToListPanel v-if="auth.isAuthed" :word="word" />

          <!-- Footer row: translate-sentence action + source pill. -->
          <div
            v-if="reader.selectedSentenceText || word.translation_source"
            class="mt-4 flex items-center justify-between gap-2 border-t border-border-subtle pt-3"
          >
            <button
              v-if="reader.selectedSentenceText"
              type="button"
              class="inline-flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-wider text-fg-muted transition-colors hover:text-accent"
              @click="translateSentenceFromWord"
            >
              <svg width="11" height="11" viewBox="0 0 11 11" fill="none">
                <path
                  d="M1.5 2.5h5M4 1.5v5M5 5.5h4.5M7.5 4.5v4M2 9l1.5-3 1.5 3M2.7 8h1.6"
                  stroke="currentColor"
                  stroke-width="1.2"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                />
              </svg>
              Translate sentence
            </button>
            <span
              v-if="shownSource"
              class="font-mono text-[9px] uppercase tracking-wider text-fg-subtle"
            >
              via {{ shownSource }}
            </span>
          </div>

          <!-- Close affordance on mobile -->
          <button
            v-if="isMobile"
            type="button"
            class="mt-3 w-full rounded-md border border-border bg-bg-elevated py-2 text-xs font-medium text-fg-muted hover:text-fg hover:bg-bg-sunken"
            @click="reader.clearWord()"
          >
            Close
          </button>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>
