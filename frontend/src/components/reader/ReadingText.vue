<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue";

import type { AnalysisResponse, WordInfo } from "@/api/types";
import { useReaderStore } from "@/stores/reader";
import { useSettingsStore } from "@/stores/settings";
import { useUserWordsStore } from "@/stores/userWords";

import SentenceTranslation from "./SentenceTranslation.vue";
import {
  detectSections,
  groupIntoSentences,
  hskCssVar,
  levelForVersion,
  shouldShowPinyin,
  type Section,
  type Sentence,
} from "./utils";

const props = defineProps<{ analysis: AnalysisResponse }>();
const emit = defineEmits<{
  /** Fires whenever the section list changes — ReaderView passes it to the TOC. */
  (e: "sections", value: Section[]): void;
}>();

import { useAudioPlayerStore } from "@/stores/audio-player";
import { useAuthStore } from "@/stores/auth";
import { useToastStore } from "@/stores/toast";

const reader = useReaderStore();
const settings = useSettingsStore();
const userWords = useUserWordsStore();
const auth = useAuthStore();
const toasts = useToastStore();
const audioPlayer = useAudioPlayerStore();

/**
 * Per-word state lookup. Prefers the user's live store (so optimistic updates
 * from WordPopover repaint immediately) and falls back to the user_state field
 * stamped onto the analysis payload (so a fresh /api/analyze that landed
 * before the store hydrated still colors correctly on first paint).
 */
function userStateFor(word: WordInfo): string | null {
  return userWords.stateOf(word.text) ?? word.user_state ?? null;
}

/** Per-token grammar-span lookup. True if this absolute token index lives
 *  inside any matched grammar pattern from the analysis response. */
const grammarSpanSet = computed<Set<number>>(() => {
  const set = new Set<number>();
  const matches = props.analysis.grammar?.matches;
  if (!matches) return set;
  for (const m of matches) {
    for (let i = m.start_word_idx; i <= m.end_word_idx; i++) {
      set.add(i);
    }
  }
  return set;
});

/** True if this token is a learnable Chinese word — excludes punctuation,
 *  linebreaks, and other render-only tokens. */
function isLearnableWord(word: WordInfo): boolean {
  if (!word.text || word.text === "\n") return false;
  if (word.translation_source === "linebreak") return false;
  // Must contain at least one CJK character to be worth tracking.
  return /[一-鿿]/.test(word.text);
}

const sentences = computed<Sentence[]>(() =>
  groupIntoSentences(props.analysis.words),
);

const sections = computed<Section[]>(() => detectSections(sentences.value));

watch(
  sections,
  (next) => {
    // Let the TOC pick up section changes (text replaced, re-analysed, etc.).
    emit("sections", next);
    // The DOM-anchor IDs are stable across renders, so we don't need to
    // resync scroll position here — Vue's diff keeps positions intact.
    void nextTick();
  },
  { immediate: true },
);

/** Map from sentence index -> section index, for the "this sentence starts
 *  a new section" lookup in the template. */
const sectionStartAt = computed<Map<number, Section>>(() => {
  const m = new Map<number, Section>();
  for (const s of sections.value) m.set(s.startSentenceIdx, s);
  return m;
});

/** Map from sentence index -> [start, endExclusive] of the section that ends
 *  at that sentence (i.e. the "render the page-complete button after this
 *  sentence" lookup). Empty when there are no sections (short texts). */
const sectionEndAt = computed<Map<number, { start: number; end: number }>>(() => {
  const m = new Map<number, { start: number; end: number }>();
  const total = sentences.value.length;
  for (let i = 0; i < sections.value.length; i++) {
    const start = sections.value[i].startSentenceIdx;
    const end =
      i + 1 < sections.value.length
        ? sections.value[i + 1].startSentenceIdx
        : total;
    // We render the button after the last sentence in the range, i.e. end-1.
    if (end > start) m.set(end - 1, { start, end });
  }
  return m;
});

/** For the no-sections case (short texts), still expose a "mark all" prompt
 *  at the very end so the user can quickly clear a paragraph too. */
const showTailBulkAction = computed(
  () => sections.value.length === 0 && sentences.value.length > 0,
);

function collectUnknownWordsInRange(start: number, end: number): string[] {
  const out = new Set<string>();
  for (let i = start; i < end; i++) {
    const s = sentences.value[i];
    if (!s) continue;
    for (const w of s.words) {
      if (!isLearnableWord(w)) continue;
      const state = userStateFor(w);
      if (state === "known" || state === "ignored") continue;
      out.add(w.text);
    }
  }
  return Array.from(out);
}

const bulkMarkingRange = ref<string | null>(null);
async function bulkMarkRange(start: number, end: number) {
  const key = `${start}-${end}`;
  if (bulkMarkingRange.value === key) return;
  const words = collectUnknownWordsInRange(start, end);
  if (!words.length) {
    toasts.info("Nothing left to mark — all words here are already known.");
    return;
  }
  bulkMarkingRange.value = key;
  try {
    const result = await userWords.bulkMarkKnown(words);
    toasts.success(
      `Marked ${result.updated.toLocaleString()} word${result.updated === 1 ? "" : "s"} as known.`,
    );
  } catch {
    toasts.error("Couldn't mark these words as known.");
  } finally {
    bulkMarkingRange.value = null;
  }
}

const estimatedLevel = computed(() => {
  if (settings.hskVersion === "old") {
    return (
      props.analysis.statistics.estimated_level_old ??
      props.analysis.statistics.estimated_level
    );
  }
  return (
    props.analysis.statistics.estimated_level_new ??
    props.analysis.statistics.estimated_level
  );
});

function wordHskColor(word: WordInfo): string | null {
  if (!word.is_hsk || word.translation_source === "linebreak") return null;
  return hskCssVar(levelForVersion(word, settings.hskVersion));
}

/**
 * Resolve the wash color for a word given the active colorMode:
 *   - 'off'      → no color, ever.
 *   - 'hsk'      → corpus-level rainbow by HSK band.
 *   - 'progress' → LingQ-style three-state: new=blue, learning=accent
 *                  (warm amber/coral), known/ignored=plain text. The three
 *                  modes must be visually distinguishable at a glance —
 *                  earlier this branch fell back to HSK colors for "new",
 *                  which made progress and hsk look identical until the
 *                  user had marked many words. (Punctuation and other
 *                  non-CJK tokens stay uncolored.)
 */
function washColor(word: WordInfo): string | null {
  if (word.translation_source === "linebreak") return null;
  if (settings.colorMode === "off") return null;
  if (settings.colorMode === "hsk") return wordHskColor(word);

  // progress mode
  if (!isLearnableWord(word)) return null;
  const state = userStateFor(word);
  if (state === "known" || state === "ignored") return null;
  if (state === "learning") return "var(--color-accent)";
  // 'new' (no row in user_words yet): the LingQ blue.
  return "var(--color-progress-new)";
}

function hskStyle(word: WordInfo): Record<string, string> | undefined {
  const color = washColor(word);
  return color ? ({ "--hsk-color": color } as Record<string, string>) : undefined;
}

function wordShowsPinyin(word: WordInfo): boolean {
  if (!word.is_hsk || word.translation_source === "linebreak") return false;
  return shouldShowPinyin(
    settings.pinyinMode,
    word,
    settings.hskVersion,
    estimatedLevel.value,
  );
}

function isPunctOnly(word: WordInfo): boolean {
  // Pure-punctuation tokens that came back as non-HSK — don't wrap them in
  // an HSK wash, render inline plainly.
  return !word.is_hsk && !/[一-鿿]/.test(word.text);
}

function onWordClick(word: WordInfo, event: MouseEvent, sentence: Sentence) {
  // Treat punctuation and whitespace as transparent for word clicks.
  if (!word.is_hsk && !word.meaning) return;
  event.stopPropagation();
  const target = event.currentTarget as HTMLElement;
  reader.selectWord(word, target, { key: sentence.key, text: sentence.text });
}

function onSentenceClick(sentence: Sentence) {
  if (!sentence.text) return;
  if (reader.openSentenceKey === sentence.key) {
    reader.closeSentence();
    return;
  }
  reader.toggleSentence(sentence.key);
  void reader.translateSentence(sentence.text);
}

function selectedWordKey(): string | null {
  return reader.selectedWord?.text ?? null;
}

/** Clicked from the highlighted sentence to jump playback there. */
function onJumpSentence(sentenceKey: string, event: MouseEvent) {
  // Only intercept Alt-click as "jump here" so plain click still opens
  // the translation card (existing behavior).
  if (!event.altKey) return;
  event.preventDefault();
  event.stopPropagation();
  void audioPlayer.jumpTo(sentenceKey);
}

// Auto-scroll the active sentence into view while the player advances.
// We use scrollIntoView with 'center' so the user can see the next line
// before it's read, and 'smooth' so we don't yank attention.
watch(
  () => audioPlayer.currentKey,
  (key) => {
    if (!key || !audioPlayer.playing) return;
    void nextTick(() => {
      const el = document.querySelector(
        `[data-sentence-key="${key}"]`,
      ) as HTMLElement | null;
      if (!el) return;
      const rect = el.getBoundingClientRect();
      const viewportHeight = window.innerHeight;
      // Already comfortably in view? leave it alone.
      if (rect.top > viewportHeight * 0.25 && rect.bottom < viewportHeight * 0.7) {
        return;
      }
      el.scrollIntoView({ behavior: "smooth", block: "center" });
    });
  },
);
</script>

<template>
  <article
    class="font-cn-serif"
    :style="{ fontSize: '20px' }"
    aria-label="Analysed text"
  >
    <template v-for="(sentence, idx) in sentences" :key="sentence.key">
      <!-- Section anchor + heading. We render a real heading element so it's
           reachable by screen readers and the URL hash navigation, and so
           IntersectionObserver in TocSidebar can pin the "current" entry. -->
      <h2
        v-if="sectionStartAt.get(idx)"
        :id="sectionStartAt.get(idx)!.key"
        class="reader-section-anchor mb-2 mt-8 scroll-mt-24 font-display text-[11px] font-medium uppercase tracking-[0.22em] text-fg-subtle first:mt-0"
        :data-section-key="sectionStartAt.get(idx)!.key"
      >
        <span class="text-fg-muted">{{ sectionStartAt.get(idx)!.title }}</span>
      </h2>

    <p
      class="mb-2.5 leading-[2.4]"
      :class="{ 'mt-4': sentence.endsWithLineBreak && idx > 0 }"
    >
      <span
        class="sentence inline px-1 -mx-1 align-baseline transition-colors"
        :class="{
          'bg-accent/15 rounded-md':
            audioPlayer.currentKey === sentence.key && audioPlayer.playing,
        }"
        :data-open="reader.openSentenceKey === sentence.key || undefined"
        :data-sentence-key="sentence.key"
        :role="sentence.text ? 'button' : undefined"
        :tabindex="sentence.text ? 0 : -1"
        :title="
          audioPlayer.hasQueue && sentence.text
            ? 'Click to translate · Alt-click to play from here'
            : undefined
        "
        @click="
          $event.altKey
            ? onJumpSentence(sentence.key, $event)
            : onSentenceClick(sentence)
        "
        @keydown.enter.prevent="onSentenceClick(sentence)"
        @keydown.space.prevent="onSentenceClick(sentence)"
      >
        <template v-for="(word, wi) in sentence.words" :key="`${sentence.key}-${wi}`">
          <!-- Plain punctuation: render as raw text. -->
          <span
            v-if="isPunctOnly(word)"
            class="text-fg"
            :data-word-idx="sentence.baseIdx + wi"
            :data-grammar="grammarSpanSet.has(sentence.baseIdx + wi) || undefined"
          >{{ word.text }}</span>

          <!-- Word with ruby pinyin + HSK wash. Multi-character or HSK words
               always go through the .ruby wrapper so layout stays consistent. -->
          <span
            v-else
            class="ruby ink-settle"
            :data-no-pinyin="!wordShowsPinyin(word) || undefined"
            :data-word-idx="sentence.baseIdx + wi"
            :data-grammar="grammarSpanSet.has(sentence.baseIdx + wi) || undefined"
            :style="{ animationDelay: `${Math.min(wi, 30) * 8}ms` }"
            @click.stop="onWordClick(word, $event, sentence)"
          >
            <span class="pinyin">{{ word.pinyin ?? '' }}</span>
            <span
              class="hanzi hsk-wash"
              :data-selected="
                (selectedWordKey() === word.text &&
                  reader.selectedWord === word) || undefined
              "
              :style="hskStyle(word)"
            >
              {{ word.text }}
            </span>
          </span>
        </template>
      </span>

      <!-- Inline translation card unfurls below the sentence -->
      <Transition
        enter-active-class="transition duration-200 ease-out"
        enter-from-class="opacity-0 -translate-y-1"
        enter-to-class="opacity-100 translate-y-0"
        leave-active-class="transition duration-150 ease-in"
        leave-from-class="opacity-100"
        leave-to-class="opacity-0"
      >
        <SentenceTranslation
          v-if="reader.openSentenceKey === sentence.key && sentence.text"
          :text="sentence.text"
        />
      </Transition>
    </p>

    <!-- Section-complete bulk action. Renders after the last sentence of each
         detected section (LingQ-style "page-complete"). Auth-only. -->
    <div
      v-if="auth.isAuthed && sectionEndAt.has(idx)"
      class="mb-6 mt-2 flex justify-end"
    >
      <button
        type="button"
        class="inline-flex items-center gap-1.5 rounded-full border border-border-subtle bg-bg-elevated px-3 py-1.5 font-mono text-[10px] uppercase tracking-wider text-fg-muted transition-colors hover:bg-bg-sunken hover:text-fg disabled:cursor-not-allowed disabled:opacity-50"
        :disabled="bulkMarkingRange !== null"
        @click="
          bulkMarkRange(
            sectionEndAt.get(idx)!.start,
            sectionEndAt.get(idx)!.end,
          )
        "
      >
        <svg width="11" height="11" viewBox="0 0 11 11" fill="none" aria-hidden="true">
          <path
            d="M2 5.5l2.5 2.5L9 3"
            stroke="currentColor"
            stroke-width="1.5"
            stroke-linecap="round"
            stroke-linejoin="round"
          />
        </svg>
        Mark remaining as known
      </button>
    </div>
    </template>

    <!-- Tail bulk action — only when the text is too short to have sections. -->
    <div
      v-if="auth.isAuthed && showTailBulkAction"
      class="mt-4 flex justify-end"
    >
      <button
        type="button"
        class="inline-flex items-center gap-1.5 rounded-full border border-border-subtle bg-bg-elevated px-3 py-1.5 font-mono text-[10px] uppercase tracking-wider text-fg-muted transition-colors hover:bg-bg-sunken hover:text-fg disabled:cursor-not-allowed disabled:opacity-50"
        :disabled="bulkMarkingRange !== null"
        @click="bulkMarkRange(0, sentences.length)"
      >
        <svg width="11" height="11" viewBox="0 0 11 11" fill="none" aria-hidden="true">
          <path
            d="M2 5.5l2.5 2.5L9 3"
            stroke="currentColor"
            stroke-width="1.5"
            stroke-linecap="round"
            stroke-linejoin="round"
          />
        </svg>
        Mark remaining as known
      </button>
    </div>
  </article>
</template>
