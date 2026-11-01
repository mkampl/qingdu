<script setup lang="ts">
/**
 * One vocab list: its heading and list-wide actions, its sections with
 * their words, a row to add a section, and the word, delete and Anki
 * export modals. Loading and every edit live in useVocabList.
 */
import { ref } from "vue";
import { RouterLink, useRouter } from "vue-router";

import type { VocabularyWord } from "@/api/types";
import { useAnkiExport } from "@/composables/use-anki-export";
import { useVocabList } from "@/composables/use-vocab-list";
import { useAuthStore } from "@/stores/auth";
import { useAuthModalsStore } from "@/stores/auth-modals";

import AnkiExportModal from "@/components/vocab-list/AnkiExportModal.vue";
import ListActions from "@/components/vocab-list/ListActions.vue";
import ListTitle from "@/components/vocab-list/ListTitle.vue";
import VocabSection from "@/components/vocab-list/VocabSection.vue";
import WordFormModal from "@/components/vocab-list/WordFormModal.vue";
import Button from "@/components/ui/Button.vue";
import Modal from "@/components/ui/Modal.vue";
import Spinner from "@/components/ui/Spinner.vue";
import TextInput from "@/components/ui/TextInput.vue";

const props = defineProps<{ id: string }>();

const auth = useAuthStore();
const authModals = useAuthModalsStore();
const router = useRouter();

const listId = () => Number(props.id);
const {
  state,
  list,
  counts,
  busy,
  learning,
  learningSection,
  rename,
  toggleGlossary,
  deleteList,
  exportCsv,
  addSection,
  renameSection,
  deleteSection,
  saveWord,
  deleteWord,
  learn,
} = useVocabList(listId);
const {
  phase: ankiPhase,
  progress: ankiProgress,
  error: ankiError,
  run: runAnki,
  close: closeAnki,
} = useAnkiExport();

function exportAnki() {
  if (list.value) void runAnki(list.value.id);
}

const askDeleteList = ref(false);
async function confirmDeleteList() {
  await deleteList();
  askDeleteList.value = false;
}

const newSectionName = ref("");
const addingSection = ref(false);
async function submitSection() {
  const name = newSectionName.value.trim();
  if (!list.value || !name || addingSection.value) return;
  addingSection.value = true;
  try {
    if (await addSection(name)) newSectionName.value = "";
  } finally {
    addingSection.value = false;
  }
}

// One section or word armed for deletion at a time, across sections.
const sectionPendingDelete = ref<string | null>(null);
const wordPendingDelete = ref<{ section: string; hanzi: string } | null>(null);

// Disarmed here, not by the section: a deleted section has unmounted by now.
async function removeSection(name: string) {
  await deleteSection(name);
  sectionPendingDelete.value = null;
}

const wordTarget = ref<{ sectionName: string; word: VocabularyWord | null } | null>(null);
</script>

<template>
  <section class="mx-auto max-w-5xl px-5 py-10 sm:px-8 md:py-14 lg:px-10">
    <!-- Breadcrumb / back -->
    <nav class="mb-3 flex items-center gap-2 text-xs">
      <RouterLink
        to="/vocab"
        class="font-mono uppercase tracking-wider text-fg-subtle hover:text-fg"
      >
        ← Vocabulary
      </RouterLink>
    </nav>

    <!-- Session check still running -->
    <div
      v-if="!auth.hydrated"
      class="flex items-center gap-3 text-fg-muted"
    >
      <Spinner size="sm" />
      <span class="font-display italic">Loading…</span>
    </div>

    <!-- Anonymous CTA -->
    <div
      v-else-if="!auth.isAuthed"
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
          This list doesn't exist or isn't yours.
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
          <ListTitle
            :list="list"
            :counts="counts"
            :busy="busy"
            :rename="rename"
            @toggle-glossary="toggleGlossary"
          />

          <!-- Learn / review / export / delete actions -->
          <ListActions
            :total-words="counts.words"
            :busy="busy"
            :learning="learning"
            :learning-all="learning && learningSection === null"
            :anki-idle="ankiPhase === 'idle'"
            @learn="learn()"
            @review="router.push({ path: '/review', query: { list: String(listId()) } })"
            @csv="exportCsv"
            @anki="exportAnki"
            @delete="askDeleteList = true"
          />
        </header>

        <!-- Sections -->
        <VocabSection
          v-for="section in list.sections"
          :key="section.name"
          :section="section"
          :learning="learning"
          :learning-this="learningSection === section.name"
          :rename="renameSection"
          :remove="() => removeSection(section.name)"
          :remove-word="(hanzi: string) => deleteWord(section.name, hanzi)"
          :pending-delete="sectionPendingDelete === section.name"
          :pending-word="
            wordPendingDelete?.section === section.name ? wordPendingDelete.hanzi : null
          "
          @update:pending-delete="(v) => (sectionPendingDelete = v ? section.name : null)"
          @update:pending-word="
            (h) => (wordPendingDelete = h === null ? null : { section: section.name, hanzi: h })
          "
          @learn="learn(section.name)"
          @add-word="wordTarget = { sectionName: section.name, word: null }"
          @edit-word="(word) => (wordTarget = { sectionName: section.name, word })"
        />

        <!-- Add section row -->
        <form
          class="flex items-center gap-2 rounded-lg border border-dashed border-border bg-bg-elevated p-4"
          @submit.prevent="submitSection"
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

    <WordFormModal :target="wordTarget" :save="saveWord" @close="wordTarget = null" />

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
        “{{ list?.name }}” and its {{ counts.words }}
        {{ counts.words === 1 ? "word" : "words" }} will be permanently removed.
      </p>
      <div class="mt-5 flex items-center justify-end gap-2">
        <Button variant="ghost" size="sm" @click="askDeleteList = false">
          Cancel
        </Button>
        <Button
          variant="danger"
          size="sm"
          :loading="busy"
          @click="confirmDeleteList"
        >
          Delete
        </Button>
      </div>
    </Modal>

    <AnkiExportModal
      :phase="ankiPhase"
      :progress="ankiProgress"
      :error="ankiError"
      @close="closeAnki"
      @retry="exportAnki"
    />
  </section>
</template>
