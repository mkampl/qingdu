<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";

import * as api from "@/api/client";
import { ApiError } from "@/api/client";
import type { UserWordState, WordSnapshot } from "@/api/client";
import { useAnalysisStore } from "@/stores/analysis";
import { useAuthStore } from "@/stores/auth";
import { useReaderStore } from "@/stores/reader";
import { useSettingsStore } from "@/stores/settings";
import { useToastStore } from "@/stores/toast";
import { useUserWordsStore } from "@/stores/userWords";
import { useVocabListsStore } from "@/stores/vocab-lists";

import HskChip from "./HskChip.vue";
import StrokeOrder from "./StrokeOrder.vue";
import { levelForVersion } from "./utils";

const reader = useReaderStore();
const analysis = useAnalysisStore();
const settings = useSettingsStore();
const auth = useAuthStore();
const userWords = useUserWordsStore();
const vocabLists = useVocabListsStore();
const toasts = useToastStore();

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
  const viewportWidth =
    typeof window !== "undefined" ? window.innerWidth : 1024;
  const viewportHeight =
    typeof window !== "undefined" ? window.innerHeight : 800;

  // Try to centre the popover under the anchor; clamp to viewport.
  let left = anchor.value.left + anchor.value.width / 2 - popoverWidth / 2;
  left = Math.max(
    margin,
    Math.min(left, viewportWidth - popoverWidth - margin),
  );

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
  if (next) {
    ttsLoading.value = false;
    addToListExpanded.value = false;
    addToListSelectedId.value = null;
    addToListSection.value = "Main";
    addToListError.value = null;
  }
});

// --- Add-to-vocab-list ----------------------------------------------------
//
// Inline expanding panel inside the popover. First click loads the user's
// vocab lists (cached in the store), shows them as a picker. Section field
// defaults to 'Main' but uses the first existing section if the picked list
// already has one.

const addToListExpanded = ref(false);
const addToListSelectedId = ref<number | null>(null);
const addToListSection = ref("Main");
const addToListSubmitting = ref(false);
const addToListError = ref<string | null>(null);
const addToListAdded = ref(false);

async function expandAddToList() {
  addToListExpanded.value = true;
  addToListAdded.value = false;
  addToListError.value = null;
  await vocabLists.ensureLoaded();
  // Pre-select a sensible default: the only list, or the first one.
  if (addToListSelectedId.value === null && vocabLists.lists.length > 0) {
    selectList(vocabLists.lists[0].id);
  }
}

function selectList(id: number) {
  addToListSelectedId.value = id;
  const list = vocabLists.lists.find((l) => l.id === id);
  const firstSection = list?.sections?.[0]?.name;
  // Stick with the user's draft if they've already changed it; otherwise
  // fall back to the first existing section name or 'Main'.
  if (addToListSection.value === "Main" && firstSection) {
    addToListSection.value = firstSection;
  }
}

async function submitAddToList() {
  if (!word.value || !addToListSelectedId.value || addToListSubmitting.value)
    return;
  const sectionName = addToListSection.value.trim() || "Main";
  addToListSubmitting.value = true;
  addToListError.value = null;
  try {
    await api.addWordToList(addToListSelectedId.value, {
      section_name: sectionName,
      hanzi: word.value.text,
      meaning: word.value.meaning ?? "",
    });
    addToListAdded.value = true;
    toasts.success(
      `Added 「${word.value.text}」 to “${currentListName.value}”.`,
    );
    // Invalidate so the next open picks up the new word (e.g. for section
    // defaults on the same list).
    vocabLists.invalidate();
    setTimeout(() => {
      addToListExpanded.value = false;
      addToListAdded.value = false;
    }, 700);
  } catch (e) {
    addToListError.value =
      e instanceof ApiError ? e.message : "Couldn't add the word.";
  } finally {
    addToListSubmitting.value = false;
  }
}

const currentListName = computed(() => {
  const id = addToListSelectedId.value;
  if (id === null) return "";
  return vocabLists.lists.find((l) => l.id === id)?.name ?? "";
});

function translateSentenceFromWord() {
  const sentenceKey = reader.selectedSentenceKey;
  const sentenceText = reader.selectedSentenceText;
  if (!sentenceKey || !sentenceText) return;
  reader.clearWord();
  // Open the inline annotation under the sentence + fire the translate.
  if (reader.openSentenceKey !== sentenceKey)
    reader.toggleSentence(sentenceKey);
  void reader.translateSentence(sentenceText);
}

const wordLevel = computed(() =>
  word.value ? levelForVersion(word.value, settings.hskVersion) : null,
);

const strokeOrderOpen = ref(false);
const wordHasCjk = computed(
  () => !!word.value && /[一-鿿]/.test(word.value.text),
);
watch(word, () => {
  // Collapse the accordion when the user moves to a new word so the
  // popover stays compact on first open.
  strokeOrderOpen.value = false;
});

// --- Word-state control ----------------------------------------------------
//
// LingQ-style: opening the popover for a 'new' word implicitly promotes it
// to 'learning' so the next time it appears the reader can color it as
// known-in-progress. Explicit known/ignored choices come from the buttons.

const currentState = computed<UserWordState | null>(() => {
  return word.value ? userWords.stateOf(word.value.text) : null;
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

watch(word, async (next) => {
  if (!next || !auth.isAuthed) return;
  // Skip linebreaks and other non-CJK tokens — we keep state for words only.
  if (!next.text || next.text === "\n") return;
  // Opt-in: by default a click is just "what does this mean", not "schedule
  // this for review". The user can still flip it to learning via the
  // explicit Learning/Known/Ignored buttons in the popover footer, or turn
  // the auto-promote back on in Settings → Reader.
  if (!settings.autoLearnOnClick) return;
  if (currentState.value === null) {
    try {
      await userWords.setState(
        next.text,
        "learning",
        analysis.savedTextId ?? null,
        buildSnapshot(),
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
    );
  } catch {
    toasts.error("Couldn't update word state");
  }
}
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
              <div class="flex items-center gap-1.5">
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
              </div>
              <HskChip v-if="wordLevel" :level="wordLevel" />
            </div>
          </div>

          <!-- Glossary-source pill — when the meaning was overridden by
               one of the user's personal glossaries, surface it so the
               user knows it's their gloss, not the dictionary's. -->
          <div
            v-if="word.glossary_source"
            class="mt-3 inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 font-mono text-[10px] uppercase tracking-wider"
            :style="{
              backgroundColor:
                'color-mix(in oklch, var(--color-glossary), transparent 80%)',
              color: 'var(--color-glossary)',
            }"
            :title="`From your glossary list “${word.glossary_source}”`"
          >
            <svg
              width="9"
              height="9"
              viewBox="0 0 9 9"
              fill="none"
              aria-hidden="true"
            >
              <path
                d="M1.5 1.5h6M1.5 4h6M1.5 6.5h4"
                stroke="currentColor"
                stroke-width="1.4"
                stroke-linecap="round"
              />
            </svg>
            {{ word.glossary_source }}
          </div>

          <!-- Meaning(s). Phase #120: when the user has any tagged
               glosses (= they've clicked this word in a package context),
               show every gloss with its provenance chip so dictionary
               and package meanings sit side-by-side. Falls back to the
               flat meaning + meanings list for words the user hasn't
               touched yet. -->
          <div
            v-if="word.user_glosses && word.user_glosses.length"
            class="mt-4 space-y-2"
          >
            <div
              v-for="(g, i) in word.user_glosses"
              :key="i"
              class="flex items-start gap-2"
            >
              <span
                :class="[
                  'mt-0.5 shrink-0 rounded-full px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-wider',
                  g.source === 'package'
                    ? 'bg-accent/15 text-accent'
                    : 'bg-bg-sunken text-fg-subtle',
                ]"
                :title="
                  g.source === 'package' && g.tag
                    ? `From package ${g.tag}`
                    : 'Dictionary'
                "
              >
                {{ g.source === 'package' ? g.tag || 'Package' : 'Dict' }}
              </span>
              <p class="font-display text-[14px] leading-snug text-fg">
                {{ g.meaning }}
              </p>
            </div>
          </div>
          <div
            v-else-if="word.meaning || word.meanings?.length"
            class="mt-4"
          >
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

          <!-- Word state — LingQ-style progress tracker. Authenticated only;
               anonymous users still get meaning + radical without the gate. -->
          <div
            v-if="auth.isAuthed && word.text && word.text !== '\n'"
            class="mt-4 grid grid-cols-3 gap-1.5 border-t border-border-subtle pt-3"
          >
            <button
              type="button"
              :aria-pressed="currentState === 'learning'"
              class="rounded-md border px-2 py-1.5 text-[11px] font-medium transition-colors"
              :class="
                currentState === 'learning'
                  ? 'border-amber-500 bg-amber-100 text-amber-900 dark:bg-amber-500/20 dark:text-amber-200'
                  : 'border-border bg-bg-elevated text-fg-muted hover:bg-bg-sunken hover:text-fg'
              "
              @click="setWordState('learning')"
            >
              Learning
            </button>
            <button
              type="button"
              :aria-pressed="currentState === 'known'"
              class="rounded-md border px-2 py-1.5 text-[11px] font-medium transition-colors"
              :class="
                currentState === 'known'
                  ? 'border-emerald-500 bg-emerald-100 text-emerald-900 dark:bg-emerald-500/20 dark:text-emerald-200'
                  : 'border-border bg-bg-elevated text-fg-muted hover:bg-bg-sunken hover:text-fg'
              "
              @click="setWordState('known')"
            >
              I know this
            </button>
            <button
              type="button"
              :aria-pressed="currentState === 'ignored'"
              class="rounded-md border px-2 py-1.5 text-[11px] font-medium transition-colors"
              :class="
                currentState === 'ignored'
                  ? 'border-fg-subtle bg-bg-sunken text-fg'
                  : 'border-border bg-bg-elevated text-fg-muted hover:bg-bg-sunken hover:text-fg'
              "
              @click="setWordState('ignored')"
            >
              Ignore
            </button>
          </div>

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

          <!-- Stroke order — collapsed by default to keep the popover small;
               the hanzi-writer chunk + per-char data only loads on expand. -->
          <div
            v-if="wordHasCjk"
            class="mt-4 border-t border-border-subtle pt-3"
          >
            <button
              type="button"
              class="flex w-full items-center justify-between text-fg-muted transition-colors hover:text-fg"
              :aria-expanded="strokeOrderOpen"
              @click="strokeOrderOpen = !strokeOrderOpen"
            >
              <span class="font-mono text-[10px] uppercase tracking-wider">
                Stroke order
              </span>
              <svg
                width="10"
                height="10"
                viewBox="0 0 10 10"
                fill="none"
                class="transition-transform"
                :class="{ 'rotate-90': strokeOrderOpen }"
                aria-hidden="true"
              >
                <path
                  d="M3.5 2l3 3-3 3"
                  stroke="currentColor"
                  stroke-width="1.4"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                />
              </svg>
            </button>
            <div v-if="strokeOrderOpen" class="mt-3">
              <StrokeOrder :chars="word.text" />
            </div>
          </div>

          <!-- Add to vocab list — signed-in users only. Expands inline so the
               popover doesn't grow until the user asks for it. -->
          <div
            v-if="auth.isAuthed"
            class="mt-4 border-t border-border-subtle pt-3"
          >
            <template v-if="!addToListExpanded">
              <button
                type="button"
                class="inline-flex items-center gap-1.5 rounded-md border border-border bg-bg-elevated px-2.5 py-1.5 text-xs font-medium text-fg-muted transition-colors hover:text-fg hover:bg-bg-sunken"
                @click="expandAddToList"
              >
                <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
                  <path
                    d="M5 1.5v7M1.5 5h7"
                    stroke="currentColor"
                    stroke-width="1.4"
                    stroke-linecap="round"
                  />
                </svg>
                Add to vocab list
              </button>
            </template>

            <div v-else class="space-y-2.5">
              <div class="flex items-center justify-between">
                <span
                  class="font-mono text-[10px] uppercase tracking-wider text-fg-subtle"
                >
                  Add 「{{ word.text }}」 to
                </span>
                <button
                  type="button"
                  class="text-fg-subtle hover:text-fg"
                  aria-label="Cancel"
                  @click="addToListExpanded = false"
                >
                  <svg width="11" height="11" viewBox="0 0 11 11" fill="none">
                    <path
                      d="M2.5 2.5l6 6M8.5 2.5l-6 6"
                      stroke="currentColor"
                      stroke-width="1.4"
                      stroke-linecap="round"
                    />
                  </svg>
                </button>
              </div>

              <div
                v-if="vocabLists.loading"
                class="flex items-center gap-2 text-xs text-fg-muted"
              >
                <span
                  class="inline-block size-3 animate-spin rounded-full border-2 border-current border-t-transparent"
                />
                Loading lists…
              </div>

              <div
                v-else-if="vocabLists.error"
                class="text-xs text-red-700 dark:text-red-300"
              >
                {{ vocabLists.error }}
              </div>

              <div
                v-else-if="vocabLists.isEmpty"
                class="text-xs italic text-fg-muted"
              >
                No vocab lists yet —
                <router-link
                  to="/vocab"
                  class="font-medium text-accent hover:underline"
                >
                  create one
                </router-link>
                .
              </div>

              <template v-else>
                <!-- List picker — compact scrollable group -->
                <div
                  class="max-h-24 overflow-y-auto rounded-md border border-border-subtle"
                >
                  <button
                    v-for="vl in vocabLists.lists"
                    :key="vl.id"
                    type="button"
                    class="block w-full px-2.5 py-1.5 text-left text-xs transition-colors hover:bg-bg-sunken"
                    :class="
                      addToListSelectedId === vl.id
                        ? 'bg-bg-sunken font-medium text-fg'
                        : 'text-fg-muted'
                    "
                    @click="selectList(vl.id)"
                  >
                    {{ vl.name }}
                    <span
                      class="ml-1 font-mono text-[9px] uppercase tracking-wider text-fg-subtle"
                    >
                      {{
                        (vl.sections ?? []).reduce(
                          (sum, s) => sum + (s.words?.length ?? 0),
                          0,
                        )
                      }}
                      words
                    </span>
                  </button>
                </div>

                <!-- Section input -->
                <label class="block">
                  <span
                    class="mb-1 block font-mono text-[10px] uppercase tracking-wider text-fg-subtle"
                  >
                    Section
                  </span>
                  <input
                    v-model="addToListSection"
                    type="text"
                    class="block w-full rounded-md border border-border bg-bg-elevated px-2 py-1 text-sm text-fg focus:border-accent focus:outline-none"
                    autocomplete="off"
                    @keydown.enter.prevent="submitAddToList"
                  />
                </label>

                <p
                  v-if="addToListError"
                  class="text-xs text-red-700 dark:text-red-300"
                >
                  {{ addToListError }}
                </p>

                <button
                  type="button"
                  class="inline-flex w-full items-center justify-center gap-1.5 rounded-md bg-accent px-3 py-1.5 text-xs font-medium text-accent-fg transition-opacity hover:opacity-90 disabled:opacity-50"
                  :disabled="
                    addToListSelectedId === null ||
                    addToListSubmitting ||
                    addToListAdded
                  "
                  @click="submitAddToList"
                >
                  <span
                    v-if="addToListSubmitting"
                    class="inline-block size-3 animate-spin rounded-full border-2 border-current border-t-transparent"
                  />
                  <svg
                    v-else-if="addToListAdded"
                    width="11"
                    height="11"
                    viewBox="0 0 11 11"
                    fill="none"
                  >
                    <path
                      d="M2 5.5l2.5 2.5L9 3"
                      stroke="currentColor"
                      stroke-width="1.5"
                      stroke-linecap="round"
                      stroke-linejoin="round"
                    />
                  </svg>
                  {{ addToListAdded ? "Added" : "Add" }}
                </button>
              </template>
            </div>
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
