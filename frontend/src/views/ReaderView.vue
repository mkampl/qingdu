<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";

import { useAnalysisStore } from "@/stores/analysis";
import { useAuthStore } from "@/stores/auth";
import { useReaderStore } from "@/stores/reader";
import { useToastStore } from "@/stores/toast";
import { ApiError, saveText } from "@/api/client";
import { submitShortcutLabel } from "@/utils/platform";

import ChopMark from "@/components/reader/ChopMark.vue";
import InputPanel from "@/components/reader/InputPanel.vue";
import ReadingProgress from "@/components/reader/ReadingProgress.vue";
import ReadingText from "@/components/reader/ReadingText.vue";
import StatsPanel from "@/components/reader/StatsPanel.vue";
import WordPopover from "@/components/reader/WordPopover.vue";

const analysis = useAnalysisStore();
const reader = useReaderStore();
const auth = useAuthStore();
const toasts = useToastStore();

const localInput = ref<string>(analysis.inputText);
const showEditor = ref<boolean>(!analysis.hasResult);
const articleRef = ref<HTMLElement | null>(null);

const saved = ref(false);
const saving = ref(false);
const justSaved = ref(false); // drives the chop-settle animation

const placeholderSeeded = ref(false);

// Seed with a literary opening line on first mount if there's no input,
// so the empty state is welcoming rather than blank.
const STARTER_TEXT =
  "我今天去学校学习中文。老师教我们很多新的汉字。我觉得中文很有意思,但是也很难。";

onMounted(() => {
  if (!analysis.inputText && !analysis.hasResult) {
    localInput.value = STARTER_TEXT;
    placeholderSeeded.value = true;
  }
});

watch(
  () => analysis.hasResult,
  (hasResult) => {
    if (hasResult) showEditor.value = false;
  },
);

async function onAnalyze() {
  reader.reset();
  saved.value = false;
  justSaved.value = false;
  try {
    await analysis.analyze(localInput.value);
    showEditor.value = false;
    placeholderSeeded.value = false;
    await nextTick();
    if (articleRef.value) {
      articleRef.value.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  } catch (e) {
    toasts.error(
      e instanceof ApiError
        ? e.message
        : "We couldn't analyse that — please try again.",
    );
  }
}

function onExpand() {
  showEditor.value = true;
  localInput.value = analysis.inputText;
  nextTick(() => {
    window.scrollTo({ top: 0, behavior: "smooth" });
  });
}

function onClear() {
  localInput.value = "";
  analysis.reset();
  reader.reset();
  saved.value = false;
  showEditor.value = true;
  placeholderSeeded.value = false;
}

const onSave = async () => {
  if (!analysis.result) return;
  if (!auth.isAuthed) {
    toasts.info("Log in to save texts to your library.");
    return;
  }
  saving.value = true;
  try {
    await saveText({
      title: derivedTitle.value,
      content: analysis.inputText,
      analysis_data: analysis.result,
    });
    saved.value = true;
    justSaved.value = true;
    toasts.success("Text saved.");
    setTimeout(() => (justSaved.value = false), 1200);
  } catch (e) {
    toasts.error(
      e instanceof ApiError ? e.message : "Couldn't save — please try again.",
    );
  } finally {
    saving.value = false;
  }
};

// Best-effort title from the first sentence (clipped).
const derivedTitle = computed(() => {
  const text = analysis.inputText.trim();
  if (!text) return "Untitled";
  const firstLine = text.split("\n")[0];
  const firstSentence = firstLine.split(/[。！？!?]/)[0] ?? firstLine;
  return firstSentence.length > 40
    ? `${firstSentence.slice(0, 40)}…`
    : firstSentence || firstLine;
});

// Keyboard: ESC closes any open word popover (handled in WordPopover) and
// also closes an open sentence translation when no popover is open.
function onGlobalKey(e: KeyboardEvent) {
  if (e.key === "Escape") {
    if (!reader.selectedWord && reader.openSentenceKey) reader.closeSentence();
  }
}
onMounted(() => document.addEventListener("keydown", onGlobalKey));
onBeforeUnmount(() => document.removeEventListener("keydown", onGlobalKey));
</script>

<template>
  <div class="relative">
    <!-- The reading column + sticky margin panel. Generous outer padding so
         the text breathes; the margin panel sits to the right on ≥ md. -->
    <div
      class="mx-auto grid max-w-6xl grid-cols-1 gap-x-12 gap-y-8 px-5 pt-10 pb-24 sm:px-8 md:grid-cols-[1fr_320px] md:pt-14 lg:px-10"
    >
      <!-- LEFT: reading column. We keep its own max-width tight so line length
           stays in the comfortable 60-72ch range for Chinese reading. -->
      <main
        class="relative min-w-0"
        aria-label="Reading"
      >
        <!-- Vertical progress hairline (≥ md only). Positioned just outside
             the column's left edge — mimics the spine of an open book. -->
        <div
          class="pointer-events-none absolute -left-6 top-0 hidden h-full md:block"
          aria-hidden="true"
        >
          <ReadingProgress :target="articleRef" />
        </div>

        <!-- Header strip: the small kicker + chop. -->
        <header class="mb-6 flex items-center justify-between gap-4">
          <div class="flex items-baseline gap-3">
            <span
              class="font-display text-[11px] font-medium uppercase tracking-[0.22em] text-fg-subtle"
            >
              Reader
            </span>
            <span class="h-px w-12 bg-border-subtle" aria-hidden="true" />
            <span
              v-if="analysis.hasResult"
              class="text-cn-serif truncate max-w-[16rem] text-[12px] italic text-fg-subtle"
              :title="derivedTitle"
            >
              {{ derivedTitle }}
            </span>
          </div>
          <Transition
            enter-active-class="transition duration-300 ease-out"
            enter-from-class="opacity-0 scale-50"
            enter-to-class="opacity-100 scale-100"
          >
            <ChopMark
              v-if="saved"
              :size="26"
              :settled="justSaved"
            />
          </Transition>
        </header>

        <!-- Input / Edit affordance. -->
        <InputPanel
          v-model="localInput"
          :loading="analysis.loading"
          :collapsed="!showEditor"
          :has-result="analysis.hasResult"
          @analyze="onAnalyze"
          @expand="onExpand"
          @clear="onClear"
        />

        <!-- Error banner -->
        <div
          v-if="analysis.error && !analysis.loading"
          class="mb-6 rounded-md border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-800 dark:border-red-900 dark:bg-red-950/40 dark:text-red-200"
        >
          {{ analysis.error }}
        </div>

        <!-- The analysed reading text. -->
        <article ref="articleRef" class="relative">
          <ReadingText
            v-if="analysis.result"
            :analysis="analysis.result"
          />

          <!-- Empty state: a quiet invitation. -->
          <div
            v-else-if="!analysis.loading"
            class="flex flex-col items-start gap-4 border-t border-border-subtle pt-10 text-fg-muted"
          >
            <span
              class="font-display text-[11px] uppercase tracking-[0.2em] text-fg-subtle"
            >
              Ready when you are
            </span>
            <p class="max-w-md font-display text-lg italic leading-relaxed text-fg-muted">
              Paste a paragraph in the editor above and we'll show you the HSK
              composition, pinyin where it'd help, and translations of any
              sentence you select.
            </p>
            <p
              class="text-[12px] text-fg-subtle"
            >
              Press
              <kbd
                class="mx-0.5 rounded border border-border-subtle bg-bg-elevated px-1.5 py-0.5 font-sans text-[10px] font-medium text-fg-muted"
              >{{ submitShortcutLabel }}</kbd>
              to analyse.
            </p>
          </div>
        </article>
      </main>

      <!-- RIGHT: marginalia / stats panel. Sticky on desktop, in-flow on
           mobile (appears below the reading content). -->
      <Transition
        enter-active-class="transition duration-300 ease-out"
        enter-from-class="opacity-0 translate-y-2"
        enter-to-class="opacity-100 translate-y-0"
      >
        <aside
          v-if="analysis.result"
          class="md:sticky md:top-6 md:self-start md:max-h-[calc(100vh-3rem)] md:overflow-y-auto md:pr-1 scrollbar-quiet"
        >
          <StatsPanel
            :statistics="analysis.result.statistics"
            :can-save="auth.isAuthed"
            :saved="saved"
            :saving="saving"
            @save="onSave"
          />
        </aside>
      </Transition>
    </div>

    <!-- Word info popover, mounted at the body root via Teleport. -->
    <WordPopover />
  </div>
</template>
