<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";

import * as api from "@/api/client";
import { useReaderStore } from "@/stores/reader";
import { useSettingsStore } from "@/stores/settings";
import HskChip from "./HskChip.vue";
import { levelForVersion } from "./utils";

const reader = useReaderStore();
const settings = useSettingsStore();

const word = computed(() => reader.selectedWord);
const anchor = computed(() => reader.selectedAnchor);

const isMobile = ref(false);
function checkMobile() {
  isMobile.value = window.innerWidth < 640;
}
onMounted(() => {
  checkMobile();
  window.addEventListener("resize", checkMobile);
  document.addEventListener("keydown", onKey);
  document.addEventListener("click", onDocumentClick, true);
});
onBeforeUnmount(() => {
  window.removeEventListener("resize", checkMobile);
  document.removeEventListener("keydown", onKey);
  document.removeEventListener("click", onDocumentClick, true);
});

function onKey(e: KeyboardEvent) {
  if (e.key === "Escape" && word.value) reader.clearWord();
}
const popoverRef = ref<HTMLElement | null>(null);
function onDocumentClick(e: MouseEvent) {
  if (!word.value) return;
  const target = e.target as Node;
  // Don't close when clicking another HSK-wash word — the new selection
  // overrides this one (handled by selectWord).
  const inPopover = popoverRef.value?.contains(target);
  const inWord = (target as HTMLElement)?.closest?.(".hsk-wash");
  if (!inPopover && !inWord) reader.clearWord();
}

const desktopPosition = computed(() => {
  if (!anchor.value) return null;
  const margin = 12;
  const popoverWidth = 320;
  const viewportWidth = typeof window !== "undefined" ? window.innerWidth : 1024;
  const viewportHeight = typeof window !== "undefined" ? window.innerHeight : 800;

  // Try to centre the popover under the anchor; clamp to viewport.
  let left = anchor.value.left + anchor.value.width / 2 - popoverWidth / 2;
  left = Math.max(margin, Math.min(left, viewportWidth - popoverWidth - margin));

  // Default below the word, flip above if it would overflow the viewport.
  let top = anchor.value.bottom + 8;
  const estimatedPopoverHeight = 240;
  if (top + estimatedPopoverHeight > viewportHeight - margin) {
    top = anchor.value.top - estimatedPopoverHeight - 8;
    if (top < margin) top = margin;
  }
  return { top, left };
});

const ttsLoading = ref(false);
async function playTts() {
  if (!word.value?.text) return;
  ttsLoading.value = true;
  try {
    const response = await api.tts(word.value.text);
    if (!response.ok) throw new Error("TTS failed");
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const audio = new Audio(url);
    audio.addEventListener("ended", () => URL.revokeObjectURL(url));
    await audio.play();
  } catch {
    /* ignore — keep button responsive */
  } finally {
    ttsLoading.value = false;
  }
}

watch(word, (next) => {
  if (next) ttsLoading.value = false;
});

function translateSentenceFromWord() {
  const sentenceKey = reader.selectedSentenceKey;
  const sentenceText = reader.selectedSentenceText;
  if (!sentenceKey || !sentenceText) return;
  reader.clearWord();
  // Open the inline annotation under the sentence + fire the translate.
  if (reader.openSentenceKey !== sentenceKey) reader.toggleSentence(sentenceKey);
  void reader.translateSentence(sentenceText);
}

const wordLevel = computed(() =>
  word.value ? levelForVersion(word.value, settings.hskVersion) : null,
);
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
        class="z-50 w-[min(20rem,calc(100vw-1.5rem))] origin-top bg-bg-elevated text-fg shadow-xl ring-1 ring-border"
        :class="
          isMobile
            ? 'fixed inset-x-3 bottom-3 rounded-2xl pb-[env(safe-area-inset-bottom)]'
            : 'fixed rounded-lg'
        "
        :style="
          !isMobile && desktopPosition
            ? {
                top: `${desktopPosition.top}px`,
                left: `${desktopPosition.left}px`,
              }
            : undefined
        "
      >
        <!-- Accent rule at the top — letterpress key line. -->
        <div
          class="h-px w-full"
          :style="{ backgroundColor: 'var(--color-accent)' }"
        />

        <div class="px-5 pt-4 pb-5">
          <div class="flex items-start justify-between gap-3">
            <div>
              <div class="font-cn-serif text-3xl leading-none text-fg">
                {{ word.text }}
              </div>
              <div
                v-if="word.pinyin"
                class="mt-1.5 font-sans text-sm text-fg-muted"
              >
                {{ word.pinyin }}
              </div>
            </div>
            <div class="flex flex-col items-end gap-2">
              <button
                type="button"
                class="inline-flex items-center justify-center rounded-md border border-border bg-bg-elevated p-2 text-fg-muted transition-colors hover:text-fg hover:bg-bg-sunken disabled:opacity-50"
                aria-label="Play pronunciation"
                :disabled="ttsLoading"
                @click="playTts"
              >
                <span
                  v-if="ttsLoading"
                  class="inline-block size-4 animate-spin rounded-full border-2 border-current border-t-transparent"
                />
                <svg
                  v-else
                  width="16"
                  height="16"
                  viewBox="0 0 16 16"
                  fill="none"
                >
                  <path
                    d="M3.5 5h2L8 3v10L5.5 11h-2V5z"
                    fill="currentColor"
                  />
                  <path
                    d="M10.5 5.5C11.5 6.3 12 7.1 12 8s-.5 1.7-1.5 2.5M12.5 4C14 5 14.5 6.5 14.5 8s-.5 3-2 4"
                    stroke="currentColor"
                    stroke-width="1.2"
                    stroke-linecap="round"
                  />
                </svg>
              </button>
              <HskChip :level="wordLevel" />
            </div>
          </div>

          <!-- Meaning(s) -->
          <div v-if="word.meaning || word.meanings?.length" class="mt-4">
            <p class="font-display text-[15px] leading-snug text-fg">
              {{ word.meaning }}
            </p>
            <ul
              v-if="word.meanings && word.meanings.length > 1"
              class="mt-1 list-inside space-y-0.5 text-xs text-fg-muted"
            >
              <li v-for="(m, i) in word.meanings.slice(1)" :key="i">
                {{ m }}
              </li>
            </ul>
          </div>

          <!-- Radical -->
          <div
            v-if="word.radical"
            class="mt-4 flex items-baseline gap-2 border-t border-border-subtle pt-3 text-xs"
          >
            <span
              class="font-mono uppercase tracking-wider text-fg-subtle"
            >
              Radical
            </span>
            <span class="font-cn-serif text-base text-fg">
              {{ word.radical }}
            </span>
            <span v-if="word.radical_pinyin" class="text-fg-muted">
              {{ word.radical_pinyin }}
            </span>
          </div>

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
              v-else-if="
                word.translation_source &&
                !['hsk', 'linebreak'].includes(word.translation_source)
              "
              class="font-mono text-[9px] uppercase tracking-wider text-fg-subtle"
            >
              via {{ word.translation_source }}
            </span>
            <span
              v-if="
                reader.selectedSentenceText &&
                word.translation_source &&
                !['hsk', 'linebreak'].includes(word.translation_source)
              "
              class="font-mono text-[9px] uppercase tracking-wider text-fg-subtle"
            >
              via {{ word.translation_source }}
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
