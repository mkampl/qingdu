<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { RouterLink, useRouter } from "vue-router";

import * as api from "@/api/client";
import { ApiError } from "@/api/client";
import type {
  VocabularyListSummary,
  VocabularySection,
  VocabularyWord,
} from "@/api/types";
import { useAuthStore } from "@/stores/auth";
import { useAuthModalsStore } from "@/stores/auth-modals";
import { useToastStore } from "@/stores/toast";

import HskChip from "@/components/reader/HskChip.vue";
import Button from "@/components/ui/Button.vue";
import Modal from "@/components/ui/Modal.vue";
import Spinner from "@/components/ui/Spinner.vue";
import TextInput from "@/components/ui/TextInput.vue";

const props = defineProps<{ id: string }>();

const auth = useAuthStore();
const authModals = useAuthModalsStore();
const toasts = useToastStore();
const router = useRouter();

const listId = computed(() => Number(props.id));

type LoadState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "ok"; list: VocabularyListSummary }
  | { status: "notfound" }
  | { status: "error"; message: string };

const state = ref<LoadState>({ status: "idle" });
const busy = ref(false);

async function load() {
  if (!auth.isAuthed) {
    state.value = { status: "idle" };
    return;
  }
  state.value = { status: "loading" };
  try {
    const lists = await api.listVocabularyLists();
    const list = lists.find((l) => l.id === listId.value);
    if (!list) state.value = { status: "notfound" };
    else state.value = { status: "ok", list };
  } catch (e) {
    state.value = {
      status: "error",
      message: e instanceof ApiError ? e.message : "Couldn't load this list.",
    };
  }
}

onMounted(load);

const list = computed(() =>
  state.value.status === "ok" ? state.value.list : null,
);

const totalWords = computed(() => {
  if (!list.value) return 0;
  return list.value.sections.reduce(
    (sum, s) => sum + (s.words?.length ?? 0),
    0,
  );
});

function syncList(mutator: (l: VocabularyListSummary) => VocabularyListSummary) {
  if (state.value.status !== "ok") return;
  state.value = { status: "ok", list: mutator({ ...state.value.list }) };
}

// --- Rename list ----------------------------------------------------------

const renamingTitle = ref(false);
const titleDraft = ref("");

function beginRename() {
  if (!list.value) return;
  titleDraft.value = list.value.name;
  renamingTitle.value = true;
}

async function commitRename() {
  if (!list.value) return;
  const newName = titleDraft.value.trim();
  if (!newName || newName === list.value.name) {
    renamingTitle.value = false;
    return;
  }
  busy.value = true;
  try {
    await api.updateVocabularyList(list.value.id, {
      name: newName,
      sections: list.value.sections,
    });
    syncList((l) => ({ ...l, name: newName }));
    toasts.success("Renamed.");
  } catch (e) {
    toasts.error(
      e instanceof ApiError ? e.message : "Couldn't rename the list.",
    );
  } finally {
    renamingTitle.value = false;
    busy.value = false;
  }
}

// --- Glossary toggle (Phase #99) -----------------------------------------

async function toggleGlossary() {
  if (!list.value) return;
  const next = !list.value.apply_as_glossary;
  busy.value = true;
  try {
    await api.updateVocabularyList(list.value.id, {
      apply_as_glossary: next,
    });
    syncList((l) => ({ ...l, apply_as_glossary: next }));
    toasts.success(
      next
        ? "Now available as a glossary for analysis."
        : "No longer used as a glossary.",
    );
  } catch (e) {
    toasts.error(
      e instanceof ApiError ? e.message : "Couldn't update glossary setting.",
    );
  } finally {
    busy.value = false;
  }
}

// --- Delete list ----------------------------------------------------------

const askDeleteList = ref(false);
async function deleteList() {
  if (!list.value) return;
  busy.value = true;
  try {
    await api.deleteVocabularyList(list.value.id);
    toasts.success(`Deleted “${list.value.name}”.`);
    void router.push("/vocab");
  } catch (e) {
    toasts.error(
      e instanceof ApiError ? e.message : "Couldn't delete the list.",
    );
  } finally {
    busy.value = false;
    askDeleteList.value = false;
  }
}

// --- Add section ----------------------------------------------------------

const newSectionName = ref("");
const addingSection = ref(false);

async function addSection() {
  if (!list.value || !newSectionName.value.trim() || addingSection.value) return;
  addingSection.value = true;
  try {
    await api.addSectionToList(list.value.id, newSectionName.value.trim());
    syncList((l) => ({
      ...l,
      sections: [
        ...l.sections,
        { name: newSectionName.value.trim(), words: [] },
      ],
    }));
    newSectionName.value = "";
  } catch (e) {
    toasts.error(
      e instanceof ApiError ? e.message : "Couldn't add the section.",
    );
  } finally {
    addingSection.value = false;
  }
}

// --- Rename / delete section ---------------------------------------------

const renamingSection = ref<string | null>(null);
const sectionDraft = ref("");
const sectionPendingDelete = ref<string | null>(null);
const sectionDeleting = ref<string | null>(null);

function beginSectionRename(name: string) {
  sectionDraft.value = name;
  renamingSection.value = name;
}

async function commitSectionRename(oldName: string) {
  if (!list.value) return;
  const newName = sectionDraft.value.trim();
  if (!newName || newName === oldName) {
    renamingSection.value = null;
    return;
  }
  try {
    await api.renameSection(list.value.id, { old_name: oldName, new_name: newName });
    syncList((l) => ({
      ...l,
      sections: l.sections.map((s) =>
        s.name === oldName ? { ...s, name: newName } : s,
      ),
    }));
    toasts.success("Section renamed.");
  } catch (e) {
    toasts.error(
      e instanceof ApiError ? e.message : "Couldn't rename the section.",
    );
  } finally {
    renamingSection.value = null;
  }
}

async function confirmDeleteSection(name: string) {
  if (!list.value) return;
  sectionDeleting.value = name;
  try {
    await api.deleteSection(list.value.id, name);
    syncList((l) => ({
      ...l,
      sections: l.sections.filter((s) => s.name !== name),
    }));
    toasts.success(`Section “${name}” deleted.`);
  } catch (e) {
    toasts.error(
      e instanceof ApiError ? e.message : "Couldn't delete the section.",
    );
  } finally {
    sectionDeleting.value = null;
    sectionPendingDelete.value = null;
  }
}

// --- Word modal (add or edit) --------------------------------------------

const wordModal = ref<{
  open: boolean;
  mode: "add" | "edit";
  sectionName: string;
  hanzi: string;
  meaning: string;
  oldHanzi: string;
}>({
  open: false,
  mode: "add",
  sectionName: "",
  hanzi: "",
  meaning: "",
  oldHanzi: "",
});
const wordSubmitting = ref(false);
const wordError = ref<string | null>(null);

function openAddWord(sectionName: string) {
  wordModal.value = {
    open: true,
    mode: "add",
    sectionName,
    hanzi: "",
    meaning: "",
    oldHanzi: "",
  };
  wordError.value = null;
}
function openEditWord(sectionName: string, word: VocabularyWord) {
  wordModal.value = {
    open: true,
    mode: "edit",
    sectionName,
    hanzi: word.hanzi,
    meaning: word.meaning,
    oldHanzi: word.hanzi,
  };
  wordError.value = null;
}
function closeWordModal() {
  wordModal.value.open = false;
}

async function submitWord(e: Event) {
  e.preventDefault();
  if (!list.value || wordSubmitting.value) return;
  const { sectionName, hanzi, meaning, oldHanzi, mode } = wordModal.value;
  if (!hanzi.trim()) {
    wordError.value = "Hanzi is required.";
    return;
  }
  wordSubmitting.value = true;
  wordError.value = null;
  try {
    if (mode === "add") {
      const result = await api.addWordToList(list.value.id, {
        section_name: sectionName,
        hanzi: hanzi.trim(),
        meaning: meaning.trim(),
      });
      const pinyin = result.pinyin ?? "";
      syncList((l) => ({
        ...l,
        sections: l.sections.map((s) =>
          s.name === sectionName
            ? {
                ...s,
                words: s.words.some((w) => w.hanzi === hanzi.trim())
                  ? s.words
                  : [
                      ...s.words,
                      { hanzi: hanzi.trim(), pinyin, meaning: meaning.trim(), level: "Custom" },
                    ],
              }
            : s,
        ),
      }));
    } else {
      const result = await api.updateWordInList(list.value.id, {
        section_name: sectionName,
        old_hanzi: oldHanzi,
        word: { hanzi: hanzi.trim(), meaning: meaning.trim() },
      });
      const pinyin = result.pinyin ?? "";
      syncList((l) => ({
        ...l,
        sections: l.sections.map((s) =>
          s.name === sectionName
            ? {
                ...s,
                words: s.words.map((w) =>
                  w.hanzi === oldHanzi
                    ? {
                        hanzi: hanzi.trim(),
                        pinyin,
                        meaning: meaning.trim(),
                        level: "Custom",
                      }
                    : w,
                ),
              }
            : s,
        ),
      }));
    }
    closeWordModal();
  } catch (e) {
    wordError.value =
      e instanceof ApiError ? e.message : "Couldn't save the word.";
  } finally {
    wordSubmitting.value = false;
  }
}

// --- Delete word (inline) ------------------------------------------------

const wordPendingDelete = ref<{ section: string; hanzi: string } | null>(null);
const wordDeleting = ref<{ section: string; hanzi: string } | null>(null);

async function confirmDeleteWord(sectionName: string, hanzi: string) {
  if (!list.value) return;
  wordDeleting.value = { section: sectionName, hanzi };
  try {
    await api.deleteWordFromList(list.value.id, {
      section_name: sectionName,
      hanzi,
    });
    syncList((l) => ({
      ...l,
      sections: l.sections.map((s) =>
        s.name === sectionName
          ? { ...s, words: s.words.filter((w) => w.hanzi !== hanzi) }
          : s,
      ),
    }));
  } catch (e) {
    toasts.error(
      e instanceof ApiError ? e.message : "Couldn't delete the word.",
    );
  } finally {
    wordDeleting.value = null;
    wordPendingDelete.value = null;
  }
}

// --- Export flows --------------------------------------------------------

type ExportPhase =
  | "idle"
  | "checking"
  | "preparing"
  | "downloading"
  | "done"
  | "error";
const exportPhase = ref<ExportPhase>("idle");
const exportProgress = ref<{
  total: number;
  cached: number;
  generated: number;
  failed: number;
  rate_limited: boolean;
} | null>(null);
const exportError = ref<string | null>(null);

function triggerDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  // Slight delay so the browser has time to start the download before we
  // revoke the URL.
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

async function exportCsv() {
  if (!list.value) return;
  busy.value = true;
  try {
    const { blob, filename } = await api.exportVocabularyListCsv(list.value.id);
    triggerDownload(blob, filename || `${list.value.name}.csv`);
    toasts.success("CSV downloaded.");
  } catch (e) {
    toasts.error(
      e instanceof ApiError ? e.message : "CSV export failed.",
    );
  } finally {
    busy.value = false;
  }
}

async function exportAnki() {
  if (!list.value) return;
  exportError.value = null;
  exportProgress.value = null;
  exportPhase.value = "checking";

  try {
    const status = await api.checkAudioStatus(list.value.id);
    if (!status.ready) {
      exportPhase.value = "preparing";
      exportProgress.value = {
        total: status.total,
        cached: status.cached,
        generated: 0,
        failed: 0,
        rate_limited: false,
      };
      const prep = await api.prepareExportAudio(list.value.id);
      exportProgress.value = {
        total: prep.total,
        cached: prep.cached,
        generated: prep.generated,
        failed: prep.failed,
        rate_limited: prep.rate_limited,
      };
    }
    exportPhase.value = "downloading";
    const { blob, filename, rateLimited } = await api.exportVocabularyListAnki(
      list.value.id,
    );
    triggerDownload(blob, filename || `${list.value.name}.apkg`);
    exportPhase.value = "done";
    if (rateLimited) {
      toasts.info("Anki package downloaded — some cards lack audio (rate limit).");
    } else {
      toasts.success("Anki package downloaded.");
    }
    // Auto-close the modal after a beat so the success message lingers
    setTimeout(() => {
      if (exportPhase.value === "done") exportPhase.value = "idle";
    }, 1800);
  } catch (e) {
    exportError.value =
      e instanceof ApiError ? e.message : "Anki export failed.";
    exportPhase.value = "error";
  }
}

function closeExportModal() {
  exportPhase.value = "idle";
}

// --- Helpers --------------------------------------------------------------

function sectionWordCount(section: VocabularySection): number {
  return section.words?.length ?? 0;
}
</script>

<template>
  <section class="mx-auto max-w-5xl px-5 py-10 sm:px-8 md:py-14 lg:px-10">
    <!-- Breadcrumb / back -->
    <nav class="mb-3 flex items-center gap-2 text-xs">
      <RouterLink
        to="/vocab"
        class="font-mono uppercase tracking-wider text-fg-subtle hover:text-fg"
      >
        ← Library
      </RouterLink>
    </nav>

    <!-- Anonymous CTA -->
    <div
      v-if="!auth.isAuthed"
      class="rounded-lg border border-border-subtle bg-bg-elevated p-8 text-center"
    >
      <p class="font-display text-lg italic leading-relaxed text-fg-muted">
        Sign in to manage vocab lists.
      </p>
      <Button
        variant="primary"
        size="sm"
        class="mt-4"
        @click="authModals.openLogin()"
      >
        Sign in
      </Button>
    </div>

    <template v-else>
      <!-- Loading -->
      <div
        v-if="state.status === 'loading'"
        class="flex items-center gap-3 text-fg-muted"
      >
        <Spinner size="sm" />
        <span class="font-display italic">Loading…</span>
      </div>

      <!-- Error -->
      <div
        v-else-if="state.status === 'error'"
        class="rounded-md border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-800 dark:border-red-900 dark:bg-red-950/40 dark:text-red-200"
        role="alert"
      >
        {{ state.message }}
      </div>

      <!-- Not found -->
      <div
        v-else-if="state.status === 'notfound'"
        class="rounded-lg border border-border-subtle bg-bg-elevated p-8"
      >
        <p class="font-display text-lg italic leading-relaxed text-fg-muted">
          We couldn't find that vocab list.
        </p>
        <Button
          variant="primary"
          size="sm"
          class="mt-4"
          @click="router.push('/vocab')"
        >
          Back to your lists
        </Button>
      </div>

      <!-- The list itself -->
      <template v-else-if="list">
        <header
          class="mb-8 flex flex-wrap items-end justify-between gap-y-4"
        >
          <div class="min-w-0 flex-1">
            <div class="mb-2 flex items-baseline gap-3">
              <span
                class="font-mono text-[11px] uppercase tracking-[0.22em] text-fg-subtle"
              >
                Vocab list
              </span>
              <span
                class="h-px w-12 bg-border-subtle"
                aria-hidden="true"
              />
            </div>
            <h1 class="text-cn-serif text-3xl font-medium tracking-tight text-fg sm:text-4xl">
              <template v-if="!renamingTitle">
                <button
                  type="button"
                  class="text-left hover:text-accent"
                  :title="'Click to rename'"
                  @click="beginRename"
                >
                  {{ list.name }}
                </button>
              </template>
              <input
                v-else
                v-model="titleDraft"
                type="text"
                class="text-cn-serif w-full max-w-xl rounded-md border border-accent bg-bg-elevated px-2 py-0.5 text-3xl font-medium text-fg focus:outline-none sm:text-4xl"
                autofocus
                @blur="commitRename"
                @keydown.enter.prevent="commitRename"
                @keydown.escape.prevent="renamingTitle = false"
              />
            </h1>
            <p class="mt-1 font-mono text-[11px] uppercase tracking-wider text-fg-subtle">
              {{ totalWords }} {{ totalWords === 1 ? "word" : "words" }}
              ·
              {{ list.sections.length }}
              {{ list.sections.length === 1 ? "section" : "sections" }}
              <span
                v-if="list.apply_as_glossary"
                class="ml-2 inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] tracking-wider"
                :style="{
                  backgroundColor: 'color-mix(in oklch, var(--color-glossary), transparent 80%)',
                  color: 'var(--color-glossary)',
                }"
              >
                · Active glossary
              </span>
            </p>

            <!-- Glossary toggle — surfaces the apply_as_glossary flag. -->
            <label
              class="mt-3 flex cursor-pointer items-start gap-3 rounded-md border border-border-subtle bg-bg-elevated px-3 py-2 transition-colors hover:bg-bg-sunken"
              :class="{
                'border-[color:var(--color-glossary)]': list.apply_as_glossary,
              }"
            >
              <input
                type="checkbox"
                :checked="list.apply_as_glossary"
                :disabled="busy"
                class="mt-1 accent-accent"
                @change="toggleGlossary"
              />
              <span class="min-w-0 flex-1">
                <span class="block font-display text-sm font-medium text-fg">
                  Use as glossary
                </span>
                <!-- Short hint on mobile; full explanation only shows
                     above sm so the row doesn't dominate a phone column. -->
                <span class="block text-xs text-fg-muted leading-relaxed">
                  <span class="sm:hidden">Overrides HSK meanings during analysis.</span>
                  <span class="hidden sm:inline">
                    Words in this list will override HSK meanings when analysing
                    text. Useful for specialised corpora (Daoist, Buddhist,
                    business jargon) where the default glosses don't fit.
                    Toggle per-text from the reader's <em>Glossaries</em> picker.
                  </span>
                </span>
              </span>
            </label>
          </div>

          <!-- Export / delete actions -->
          <div class="flex items-center gap-2">
            <Button
              variant="secondary"
              size="sm"
              :disabled="totalWords === 0 || busy"
              :loading="busy && exportPhase === 'idle'"
              @click="exportCsv"
            >
              ↓ CSV
            </Button>
            <Button
              variant="secondary"
              size="sm"
              :disabled="totalWords === 0 || exportPhase !== 'idle'"
              @click="exportAnki"
            >
              ↓ Anki
            </Button>
            <Button
              variant="danger"
              size="sm"
              :disabled="busy"
              @click="askDeleteList = true"
            >
              Delete list
            </Button>
          </div>
        </header>

        <!-- Sections -->
        <section
          v-for="section in list.sections"
          :key="section.name"
          class="mb-8 rounded-lg border border-border bg-bg-elevated"
        >
          <header
            class="flex items-center justify-between gap-3 border-b border-border-subtle px-5 py-3"
          >
            <div class="flex items-center gap-3 min-w-0 flex-1">
              <template v-if="renamingSection !== section.name">
                <button
                  type="button"
                  class="font-display text-lg font-medium text-fg hover:text-accent truncate"
                  @click="beginSectionRename(section.name)"
                  :title="'Click to rename section'"
                >
                  {{ section.name }}
                </button>
              </template>
              <input
                v-else
                v-model="sectionDraft"
                type="text"
                class="rounded-md border border-accent bg-bg-elevated px-2 py-0.5 text-lg font-medium text-fg focus:outline-none"
                autofocus
                @blur="commitSectionRename(section.name)"
                @keydown.enter.prevent="commitSectionRename(section.name)"
                @keydown.escape.prevent="renamingSection = null"
              />
              <span
                class="font-mono text-[10px] uppercase tracking-wider text-fg-subtle"
              >
                {{ sectionWordCount(section) }}
                {{ sectionWordCount(section) === 1 ? "word" : "words" }}
              </span>
            </div>
            <div class="flex items-center gap-1">
              <Button
                variant="ghost"
                size="sm"
                @click="openAddWord(section.name)"
              >
                + Word
              </Button>
              <template v-if="sectionPendingDelete === section.name">
                <button
                  type="button"
                  class="font-mono text-[10px] uppercase tracking-wider text-fg-subtle hover:text-fg"
                  @click="sectionPendingDelete = null"
                  :disabled="sectionDeleting === section.name"
                >
                  Cancel
                </button>
                <Button
                  variant="danger"
                  size="sm"
                  :loading="sectionDeleting === section.name"
                  @click="confirmDeleteSection(section.name)"
                >
                  Delete section
                </Button>
              </template>
              <button
                v-else
                type="button"
                class="rounded-md p-1.5 text-fg-subtle transition-colors hover:bg-bg-sunken hover:text-red-700 dark:hover:text-red-300"
                :title="`Delete section ${section.name}`"
                @click="sectionPendingDelete = section.name"
              >
                <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                  <path
                    d="M3 4h8M5 4V2.5h4V4M5 6.5v4M9 6.5v4M4 4l.5 8.5h5L10 4"
                    stroke="currentColor"
                    stroke-width="1.2"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                  />
                </svg>
              </button>
            </div>
          </header>

          <!-- Words -->
          <ul
            v-if="section.words?.length"
            class="divide-y divide-border-subtle"
          >
            <li
              v-for="word in section.words"
              :key="word.hanzi"
              class="group flex items-center gap-4 px-5 py-3"
            >
              <span class="text-cn-serif min-w-[5rem] text-2xl text-fg">
                {{ word.hanzi }}
              </span>
              <span
                class="hidden min-w-[7rem] font-sans text-sm text-fg-muted sm:inline"
              >
                {{ word.pinyin }}
              </span>
              <span class="flex-1 truncate font-display text-base text-fg">
                {{ word.meaning }}
              </span>
              <HskChip :level="word.level" />
              <div class="flex items-center gap-1 opacity-60 group-hover:opacity-100">
                <template
                  v-if="
                    wordPendingDelete &&
                    wordPendingDelete.section === section.name &&
                    wordPendingDelete.hanzi === word.hanzi
                  "
                >
                  <button
                    type="button"
                    class="font-mono text-[10px] uppercase tracking-wider text-fg-subtle hover:text-fg"
                    @click="wordPendingDelete = null"
                  >
                    Cancel
                  </button>
                  <Button
                    variant="danger"
                    size="sm"
                    :loading="
                      wordDeleting?.section === section.name &&
                      wordDeleting?.hanzi === word.hanzi
                    "
                    @click="confirmDeleteWord(section.name, word.hanzi)"
                  >
                    Delete
                  </Button>
                </template>
                <template v-else>
                  <button
                    type="button"
                    class="rounded-md p-1.5 text-fg-subtle transition-colors hover:bg-bg-sunken hover:text-fg"
                    title="Edit word"
                    @click="openEditWord(section.name, word)"
                  >
                    <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                      <path
                        d="M2 12l2.5-.5L11 5l-2-2L2.5 9.5 2 12zM9 4l2 2"
                        stroke="currentColor"
                        stroke-width="1.2"
                        stroke-linecap="round"
                        stroke-linejoin="round"
                      />
                    </svg>
                  </button>
                  <button
                    type="button"
                    class="rounded-md p-1.5 text-fg-subtle transition-colors hover:bg-bg-sunken hover:text-red-700 dark:hover:text-red-300"
                    title="Delete word"
                    @click="
                      wordPendingDelete = { section: section.name, hanzi: word.hanzi }
                    "
                  >
                    <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                      <path
                        d="M3 4h8M5 4V2.5h4V4M5 6.5v4M9 6.5v4M4 4l.5 8.5h5L10 4"
                        stroke="currentColor"
                        stroke-width="1.2"
                        stroke-linecap="round"
                        stroke-linejoin="round"
                      />
                    </svg>
                  </button>
                </template>
              </div>
            </li>
          </ul>

          <p
            v-else
            class="px-5 py-4 text-sm italic text-fg-subtle"
          >
            No words yet — use “+ Word” to add some.
          </p>
        </section>

        <!-- Add section row -->
        <form
          class="flex items-center gap-2 rounded-lg border border-dashed border-border bg-bg-elevated p-4"
          @submit.prevent="addSection"
        >
          <TextInput
            v-model="newSectionName"
            placeholder="New section name"
            autocomplete="off"
          />
          <Button
            variant="primary"
            size="sm"
            type="submit"
            :loading="addingSection"
            :disabled="!newSectionName.trim()"
          >
            Add section
          </Button>
        </form>
      </template>
    </template>

    <!-- Word add/edit modal -->
    <Modal
      :open="wordModal.open"
      size="sm"
      close-on-backdrop
      @close="closeWordModal"
    >
      <template #header>
        <h2 class="font-display text-xl font-medium tracking-tight text-fg">
          {{ wordModal.mode === "add" ? "Add word" : "Edit word" }}
          <span
            class="ml-2 font-mono text-[10px] uppercase tracking-wider text-fg-subtle"
          >
            {{ wordModal.sectionName }}
          </span>
        </h2>
      </template>
      <form class="space-y-4" @submit="submitWord">
        <TextInput
          v-model="wordModal.hanzi"
          label="Hanzi"
          placeholder="你好"
          autofocus
          required
        />
        <TextInput
          v-model="wordModal.meaning"
          label="Meaning"
          placeholder="hello"
        />
        <p
          class="font-mono text-[10px] uppercase tracking-wider text-fg-subtle"
        >
          Pinyin is generated automatically — level is set to “Custom”.
        </p>
        <p
          v-if="wordError"
          class="text-sm text-red-700 dark:text-red-300"
          role="alert"
        >
          {{ wordError }}
        </p>
        <div class="flex items-center justify-end gap-2">
          <Button
            variant="ghost"
            size="sm"
            type="button"
            @click="closeWordModal"
          >
            Cancel
          </Button>
          <Button
            variant="primary"
            size="sm"
            type="submit"
            :loading="wordSubmitting"
            :disabled="!wordModal.hanzi.trim()"
          >
            {{ wordModal.mode === "add" ? "Add" : "Save" }}
          </Button>
        </div>
      </form>
    </Modal>

    <!-- Delete list confirmation -->
    <Modal
      :open="askDeleteList"
      size="sm"
      close-on-backdrop
      @close="askDeleteList = false"
    >
      <template #header>
        <h2 class="font-display text-xl font-medium tracking-tight text-fg">
          Delete this list?
        </h2>
      </template>
      <p class="text-sm text-fg-muted">
        “{{ list?.name }}” and its {{ totalWords }}
        {{ totalWords === 1 ? "word" : "words" }} will be permanently removed.
      </p>
      <div class="mt-5 flex items-center justify-end gap-2">
        <Button variant="ghost" size="sm" @click="askDeleteList = false">
          Cancel
        </Button>
        <Button
          variant="danger"
          size="sm"
          :loading="busy"
          @click="deleteList"
        >
          Delete
        </Button>
      </div>
    </Modal>

    <!-- Anki export progress modal -->
    <Modal
      :open="exportPhase !== 'idle'"
      size="sm"
      :close-on-backdrop="exportPhase === 'done' || exportPhase === 'error'"
      @close="closeExportModal"
    >
      <template #header>
        <h2 class="font-display text-xl font-medium tracking-tight text-fg">
          Anki export
        </h2>
      </template>

      <div class="space-y-4">
        <p
          v-if="exportPhase === 'checking'"
          class="flex items-center gap-2 font-display italic text-fg-muted"
        >
          <Spinner size="sm" /> Checking audio cache…
        </p>

        <template v-else-if="exportPhase === 'preparing'">
          <p class="flex items-center gap-2 font-display italic text-fg-muted">
            <Spinner size="sm" /> Generating audio (this can take a minute)…
          </p>
          <p
            v-if="exportProgress"
            class="font-mono text-[11px] uppercase tracking-wider text-fg-subtle"
          >
            {{ exportProgress.cached + exportProgress.generated }} /
            {{ exportProgress.total }} ready
          </p>
        </template>

        <p
          v-else-if="exportPhase === 'downloading'"
          class="flex items-center gap-2 font-display italic text-fg-muted"
        >
          <Spinner size="sm" /> Packaging…
        </p>

        <template v-else-if="exportPhase === 'done'">
          <p class="font-display text-base text-fg">
            Downloaded.
          </p>
          <p
            v-if="exportProgress?.rate_limited"
            class="text-sm text-fg-muted"
          >
            A few cards came through without audio because Google's TTS hit
            its rate limit. Try the export again later to fill those in.
          </p>
        </template>

        <template v-else-if="exportPhase === 'error'">
          <p class="text-sm text-red-700 dark:text-red-300" role="alert">
            {{ exportError }}
          </p>
          <div class="flex items-center justify-end gap-2">
            <Button variant="ghost" size="sm" @click="closeExportModal">
              Close
            </Button>
            <Button variant="primary" size="sm" @click="exportAnki">
              Try again
            </Button>
          </div>
        </template>
      </div>
    </Modal>
  </section>
</template>
