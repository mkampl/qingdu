<script setup lang="ts">
import { computed } from "vue";

import type { AnalysisResponse, WordInfo } from "@/api/types";
import { useReaderStore } from "@/stores/reader";
import { useSettingsStore } from "@/stores/settings";

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

const reader = useReaderStore();
const settings = useSettingsStore();

const sentences = computed<Sentence[]>(() =>
  groupIntoSentences(props.analysis.words),
);

const sections = computed<Section[]>(() => detectSections(sentences.value));

import { nextTick, watch } from "vue";
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

function hskStyle(word: WordInfo): Record<string, string> | undefined {
  const color = wordHskColor(word);
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
        class="sentence inline px-1 -mx-1 align-baseline"
        :data-open="reader.openSentenceKey === sentence.key || undefined"
        :role="sentence.text ? 'button' : undefined"
        :tabindex="sentence.text ? 0 : -1"
        @click="onSentenceClick(sentence)"
        @keydown.enter.prevent="onSentenceClick(sentence)"
        @keydown.space.prevent="onSentenceClick(sentence)"
      >
        <template v-for="(word, wi) in sentence.words" :key="`${sentence.key}-${wi}`">
          <!-- Plain punctuation: render as raw text. -->
          <span v-if="isPunctOnly(word)" class="text-fg">{{ word.text }}</span>

          <!-- Word with ruby pinyin + HSK wash. Multi-character or HSK words
               always go through the .ruby wrapper so layout stays consistent. -->
          <span
            v-else
            class="ruby ink-settle"
            :data-no-pinyin="!wordShowsPinyin(word) || undefined"
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
    </template>
  </article>
</template>
