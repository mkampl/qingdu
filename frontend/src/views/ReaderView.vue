<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";

import { useAnalysisStore } from "@/stores/analysis";
import { useAuthStore } from "@/stores/auth";
import { useAuthModalsStore } from "@/stores/auth-modals";
import { useReaderStore } from "@/stores/reader";
import { useToastStore } from "@/stores/toast";
import { useVocabStatsStore } from "@/stores/vocab-stats";
import { ApiError, saveText, updateText } from "@/api/client";
import { submitShortcutLabel } from "@/utils/platform";

import ChopMark from "@/components/reader/ChopMark.vue";
import InputPanel from "@/components/reader/InputPanel.vue";
import ReadingProgress from "@/components/reader/ReadingProgress.vue";
import ReadingText from "@/components/reader/ReadingText.vue";
import StatsPanel from "@/components/reader/StatsPanel.vue";
import WordPopover from "@/components/reader/WordPopover.vue";

const analysis = useAnalysisStore();
const reader = useReaderStore();
const vocabStats = useVocabStatsStore();
const auth = useAuthStore();
const authModals = useAuthModalsStore();
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
  // Cold-start guard: if the backend is still loading HSK vocab, the user's
  // click on Analyze would 503. Kick off a poll so we know when it's ready
  // and can show a friendly banner in the meantime.
  void vocabStats.startPolling();
});
onBeforeUnmount(() => vocabStats.stop());

watch(
  () => analysis.hasResult,
  (hasResult) => {
    if (hasResult) showEditor.value = false;
  },
);

// When a saved text is loaded, mirror that into the local "saved" flag so
// the Save button doesn't initially say "Save text" for an already-stored
// record. Reset to false when the loaded record changes / is cleared.
watch(
  () => analysis.savedTextId,
  (id) => {
    saved.value = id !== null;
    justSaved.value = false;
  },
  { immediate: true },
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

// Best-effort title from the first sentence (clipped). Used for FRESH saves;
// loaded saved texts use their stored title (analysis.savedTextTitle).
const derivedTitle = computed(() => {
  const text = analysis.inputText.trim();
  if (!text) return "Untitled";
  const firstLine = text.split("\n")[0];
  const firstSentence = firstLine.split(/[。！？!?]/)[0] ?? firstLine;
  return firstSentence.length > 40
    ? `${firstSentence.slice(0, 40)}…`
    : firstSentence || firstLine;
});

/** Title shown in the reader header — stored value if loaded, derived otherwise. */
const displayTitle = computed(
  () => analysis.savedTextTitle ?? derivedTitle.value,
);

const onSave = async () => {
  if (!analysis.result) return;
  if (!auth.isAuthed) {
    toasts.info("Sign in to save texts to your library.");
    authModals.openLogin();
    return;
  }
  saving.value = true;
  try {
    if (analysis.savedTextId !== null) {
      // Update the existing record (re-analysed / edited).
      await updateText(analysis.savedTextId, {
        title: analysis.savedTextTitle ?? derivedTitle.value,
        content: analysis.inputText,
        analysis_data: analysis.result,
        tags: analysis.savedTextTags,
      });
      analysis.markSynced();
      toasts.success("Text updated.");
    } else {
      const result = await saveText({
        title: derivedTitle.value,
        content: analysis.inputText,
        analysis_data: analysis.result,
      });
      analysis.adoptSavedId(result.id, derivedTitle.value, []);
      toasts.success("Text saved.");
    }
    saved.value = true;
    justSaved.value = true;
    setTimeout(() => (justSaved.value = false), 1200);
  } catch (e) {
    toasts.error(
      e instanceof ApiError ? e.message : "Couldn't save — please try again.",
    );
  } finally {
    saving.value = false;
  }
};

// --- Inline title rename --------------------------------------------------

const renamingTitle = ref(false);
const titleDraft = ref("");

function beginRenameTitle() {
  if (analysis.savedTextId === null) return; // only saved texts can be renamed
  titleDraft.value = displayTitle.value;
  renamingTitle.value = true;
}

async function commitRenameTitle() {
  if (analysis.savedTextId === null) return;
  const next = titleDraft.value.trim();
  if (!next || next === analysis.savedTextTitle) {
    renamingTitle.value = false;
    return;
  }
  try {
    await updateText(analysis.savedTextId, { title: next });
    analysis.updateSavedTitle(next);
    toasts.success("Title updated.");
  } catch (e) {
    toasts.error(
      e instanceof ApiError ? e.message : "Couldn't rename.",
    );
  } finally {
    renamingTitle.value = false;
  }
}

// --- Tag editor -----------------------------------------------------------

const newTagDraft = ref("");
const tagSaving = ref(false);

async function syncTags(next: string[]) {
  if (analysis.savedTextId === null) return;
  tagSaving.value = true;
  try {
    await updateText(analysis.savedTextId, { tags: next });
    analysis.updateSavedTags(next);
  } catch (e) {
    toasts.error(
      e instanceof ApiError ? e.message : "Couldn't update tags.",
    );
  } finally {
    tagSaving.value = false;
  }
}

async function addTag() {
  const tag = newTagDraft.value.trim();
  if (!tag || analysis.savedTextTags.includes(tag)) {
    newTagDraft.value = "";
    return;
  }
  await syncTags([...analysis.savedTextTags, tag]);
  newTagDraft.value = "";
}

async function removeTag(tag: string) {
  await syncTags(analysis.savedTextTags.filter((t) => t !== tag));
}

// Keyboard: ESC closes any open word popover (handled in WordPopover) and
// also closes an open sentence translation when no popover is open.
function onGlobalKey(e: KeyboardEvent) {
  if (e.key === "Escape") {
    if (!reader.selectedWord && reader.openSentenceKey) reader.closeSentence();
  }
}
onMounted(() => document.addEventListener("keydown", onGlobalKey));
onBeforeUnmount(() => document.removeEventListener("keydown", onGlobalKey));

// --- Reading-progress persistence ---------------------------------------
//
// When the user opens a saved text, the analysis store carries its id +
// last-known progress. We:
//   1. Restore scroll to roughly that position once the article element is
//      laid out (next-tick after ReadingText renders).
//   2. Debounce-PATCH /api/texts/:id with the current scroll fraction so
//      Saved Texts cards reflect real progress instead of always 0%.
//   3. Cancel any pending PATCH if the user navigates away.

const liveProgress = ref(0);
let progressFlushTimer: ReturnType<typeof setTimeout> | null = null;
let lastPersistedProgress: number | null = null;

function schedulePersist(value: number) {
  if (!analysis.savedTextId) return;
  // Skip noise: only persist when the value moves by ≥ 1%, plus the natural
  // 100% milestone, so we don't hammer the API on micro-scrolls.
  if (
    lastPersistedProgress !== null &&
    Math.abs(value - lastPersistedProgress) < 0.01 &&
    !(value >= 0.99 && lastPersistedProgress < 0.99)
  ) {
    return;
  }
  if (progressFlushTimer) clearTimeout(progressFlushTimer);
  progressFlushTimer = setTimeout(() => {
    void persistProgress(value);
  }, 1500);
}

async function persistProgress(value: number) {
  const id = analysis.savedTextId;
  if (!id) return;
  try {
    await updateText(id, { reading_progress: value });
    lastPersistedProgress = value;
  } catch {
    // Silent — the next scroll will retry on the same debounce window.
  }
}

function onProgress(value: number) {
  liveProgress.value = value;
  schedulePersist(value);
}

// Restore scroll position after the article renders. We can't jump to a
// pixel offset deterministically (the article height isn't known until
// after layout), so we restore by setting window.scrollTo to a multiple
// of the article's bounding height, matching what ReadingProgress.compute
// would compute.
function restoreScroll() {
  const target = analysis.initialProgress;
  if (target <= 0 || !articleRef.value) return;
  // Defer to next paint so the article has its final layout height.
  requestAnimationFrame(() => {
    const el = articleRef.value;
    if (!el) return;
    const viewportH = window.innerHeight;
    const total = el.getBoundingClientRect().height;
    if (total <= viewportH) return;
    const maxScroll = total - viewportH;
    const top = el.offsetTop + Math.round(target * maxScroll);
    window.scrollTo({ top, behavior: "instant" as ScrollBehavior });
  });
}

// When a saved text is loaded (id changes), restore its progress.
watch(
  () => analysis.savedTextId,
  (id) => {
    if (id !== null) {
      lastPersistedProgress = analysis.initialProgress;
      // Wait one tick for ReadingText to render before measuring layout.
      nextTick(restoreScroll);
    } else {
      lastPersistedProgress = null;
    }
  },
);

onBeforeUnmount(() => {
  // Best-effort flush so closing the tab on unsaved progress still persists.
  if (progressFlushTimer) {
    clearTimeout(progressFlushTimer);
    if (analysis.savedTextId !== null) {
      void persistProgress(liveProgress.value);
    }
  }
});
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
          <ReadingProgress :target="articleRef" @progress="onProgress" />
        </div>

        <!-- Header strip: kicker · title · edited pill · chop. -->
        <header class="mb-3 flex items-center justify-between gap-4">
          <div class="flex min-w-0 flex-1 items-baseline gap-3">
            <span
              class="font-display text-[11px] font-medium uppercase tracking-[0.22em] text-fg-subtle"
            >
              Reader
            </span>
            <span class="h-px w-12 shrink-0 bg-border-subtle" aria-hidden="true" />

            <!-- Title — inline-editable for saved texts. -->
            <template v-if="analysis.hasResult">
              <input
                v-if="renamingTitle"
                v-model="titleDraft"
                type="text"
                class="text-cn-serif w-full max-w-md rounded-sm border-b border-accent bg-transparent text-[13px] italic text-fg focus:outline-none"
                autofocus
                @blur="commitRenameTitle"
                @keydown.enter.prevent="commitRenameTitle"
                @keydown.escape.prevent="renamingTitle = false"
              />
              <button
                v-else-if="analysis.savedTextId !== null"
                type="button"
                class="text-cn-serif truncate text-left text-[13px] italic text-fg-muted transition-colors hover:text-accent"
                :title="`${displayTitle} — click to rename`"
                @click="beginRenameTitle"
              >
                {{ displayTitle }}
              </button>
              <span
                v-else
                class="text-cn-serif truncate text-[12px] italic text-fg-subtle"
                :title="displayTitle"
              >
                {{ displayTitle }}
              </span>

              <!-- Edited pill — only when the loaded saved text has drifted. -->
              <span
                v-if="analysis.isEdited"
                class="shrink-0 rounded-full bg-accent/15 px-2 py-0.5 font-mono text-[9px] uppercase tracking-wider text-accent"
                title="The text has been edited since you saved it — click Save to update."
              >
                edited
              </span>
            </template>
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

        <!-- Tag row — only when viewing a saved text. -->
        <div
          v-if="analysis.hasResult && analysis.savedTextId !== null"
          class="mb-5 flex flex-wrap items-center gap-1.5"
        >
          <span
            v-for="tag in analysis.savedTextTags"
            :key="tag"
            class="inline-flex items-center gap-1 rounded-full bg-bg-sunken px-2.5 py-0.5 text-xs font-medium text-fg-muted"
          >
            {{ tag }}
            <button
              type="button"
              class="text-fg-subtle hover:text-fg disabled:opacity-50"
              :aria-label="`Remove ${tag}`"
              :disabled="tagSaving"
              @click="removeTag(tag)"
            >
              <svg width="9" height="9" viewBox="0 0 9 9" fill="none">
                <path
                  d="M2 2l5 5M7 2l-5 5"
                  stroke="currentColor"
                  stroke-width="1.4"
                  stroke-linecap="round"
                />
              </svg>
            </button>
          </span>
          <input
            v-model="newTagDraft"
            type="text"
            placeholder="+ Add tag"
            class="min-w-[6rem] max-w-[10rem] rounded-full border border-border-subtle bg-transparent px-2.5 py-0.5 text-xs text-fg placeholder:text-fg-subtle focus:border-accent focus:outline-none"
            :disabled="tagSaving"
            @keydown.enter.prevent="addTag"
            @keydown.escape.prevent="newTagDraft = ''"
            @blur="addTag"
          />
        </div>

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

        <!-- Cold-start banner: HSK vocab still loading on the backend. -->
        <div
          v-if="!vocabStats.ready"
          class="mb-6 flex items-center gap-3 rounded-md border border-border-subtle bg-bg-elevated px-4 py-3 text-sm text-fg-muted"
          role="status"
        >
          <span
            class="inline-block size-4 animate-spin rounded-full border-2 border-current border-t-transparent"
            aria-hidden="true"
          />
          <span class="font-display italic">
            Loading HSK vocabulary on the server — analysis will work in a few seconds.
          </span>
        </div>

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
            :is-update="analysis.savedTextId !== null"
            :is-edited="analysis.isEdited"
            @save="onSave"
          />
        </aside>
      </Transition>
    </div>

    <!-- Word info popover, mounted at the body root via Teleport. -->
    <WordPopover />
  </div>
</template>
