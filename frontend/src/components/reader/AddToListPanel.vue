<script setup lang="ts">
/**
 * "Add to vocab list" in the word popover, expanding inline so the
 * popover doesn't grow until asked. The first expand loads the user's
 * lists (cached in the store). The section defaults to the picked list's
 * first section, or 'Main'. Collapses again for each new word.
 */
import { computed, ref, watch } from "vue";

import * as api from "@/api/client";
import { ApiError } from "@/api/client";
import type { WordInfo } from "@/api/types";
import { useToastStore } from "@/stores/toast";
import { useVocabListsStore } from "@/stores/vocab-lists";
import { defaultSectionName, sectionContaining } from "@/utils/vocab-lists";

const props = defineProps<{
  word: WordInfo;
}>();

const vocabLists = useVocabListsStore();
const toasts = useToastStore();

const expanded = ref(false);
const selectedId = ref<number | null>(null);
const section = ref("Main");
// True once the user typed a section name themselves. Until then the field
// follows the picked list (its first section), so switching from list A
// ("Chapter 3") to list B doesn't create a "Chapter 3" section in B.
const sectionDirty = ref(false);
const submitting = ref(false);
const error = ref<string | null>(null);
const notice = ref<string | null>(null);
const added = ref(false);

watch(
  () => props.word,
  () => {
    expanded.value = false;
    selectedId.value = null;
    section.value = "Main";
    sectionDirty.value = false;
    error.value = null;
    notice.value = null;
  },
);

const currentListName = computed(() => {
  const id = selectedId.value;
  if (id === null) return "";
  return vocabLists.lists.find((l) => l.id === id)?.name ?? "";
});

async function expand() {
  expanded.value = true;
  added.value = false;
  error.value = null;
  notice.value = null;
  await vocabLists.ensureLoaded();
  // Pre-select the first list.
  if (selectedId.value === null && vocabLists.lists.length > 0) {
    selectList(vocabLists.lists[0].id);
  }
}

function selectList(id: number) {
  selectedId.value = id;
  notice.value = null;
  error.value = null;
  if (sectionDirty.value) return;
  const list = vocabLists.lists.find((l) => l.id === id);
  section.value = defaultSectionName(list);
}

function onSectionInput(e: Event) {
  section.value = (e.target as HTMLInputElement).value;
  sectionDirty.value = true;
}

async function submit() {
  if (!selectedId.value || submitting.value) return;
  const listId = selectedId.value;
  const hanzi = props.word.text;
  const sectionName = section.value.trim() || "Main";
  submitting.value = true;
  error.value = null;
  notice.value = null;
  try {
    await api.addWordToList(listId, {
      section_name: sectionName,
      hanzi,
      meaning: props.word.meaning ?? "",
    });
    added.value = true;
    toasts.success(`Added 「${hanzi}」 to “${currentListName.value}”.`);
    // Refresh in the background (the cached lists stay on screen) so
    // section defaults and word counts include the new word.
    void vocabLists.invalidate();
    setTimeout(() => {
      expanded.value = false;
      added.value = false;
    }, 700);
  } catch (e) {
    if (e instanceof ApiError && e.status === 409) {
      // Already somewhere in this list — say where instead of "Added".
      const list = vocabLists.lists.find((l) => l.id === listId);
      const where = sectionContaining(list, hanzi);
      notice.value = where ? `Already in “${where}”.` : e.message || "Already in this list.";
    } else {
      error.value = e instanceof ApiError ? e.message : "Couldn't add the word.";
    }
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <div class="mt-4 border-t border-border-subtle pt-3">
    <template v-if="!expanded">
      <button
        type="button"
        class="inline-flex items-center gap-1.5 rounded-md border border-border bg-bg-elevated px-2.5 py-1.5 text-xs font-medium text-fg-muted transition-colors hover:text-fg hover:bg-bg-sunken"
        @click="expand"
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
        <span class="font-mono text-[10px] uppercase tracking-wider text-fg-subtle">
          Add 「{{ word.text }}」 to
        </span>
        <button
          type="button"
          class="text-fg-subtle hover:text-fg"
          aria-label="Cancel"
          @click="expanded = false"
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

      <div v-if="vocabLists.loading" class="flex items-center gap-2 text-xs text-fg-muted">
        <span
          class="inline-block size-3 animate-spin rounded-full border-2 border-current border-t-transparent"
        />
        Loading lists…
      </div>

      <div
        v-else-if="vocabLists.error && vocabLists.isEmpty"
        class="text-xs text-red-700 dark:text-red-300"
      >
        {{ vocabLists.error }}
      </div>

      <div v-else-if="vocabLists.isEmpty" class="text-xs italic text-fg-muted">
        No vocab lists yet —
        <router-link to="/vocab" class="font-medium text-accent hover:underline">
          create one
        </router-link>
        .
      </div>

      <template v-else>
        <!-- List picker — compact scrollable group -->
        <div class="max-h-24 overflow-y-auto rounded-md border border-border-subtle">
          <button
            v-for="vl in vocabLists.lists"
            :key="vl.id"
            type="button"
            class="block w-full px-2.5 py-1.5 text-left text-xs transition-colors hover:bg-bg-sunken"
            :class="selectedId === vl.id ? 'bg-bg-sunken font-medium text-fg' : 'text-fg-muted'"
            :aria-pressed="selectedId === vl.id"
            @click="selectList(vl.id)"
          >
            {{ vl.name }}
            <span class="ml-1 font-mono text-[9px] uppercase tracking-wider text-fg-subtle">
              {{ (vl.sections ?? []).reduce((sum, s) => sum + (s.words?.length ?? 0), 0) }}
              words
            </span>
          </button>
        </div>

        <label class="block">
          <span
            class="mb-1 block font-mono text-[10px] uppercase tracking-wider text-fg-subtle"
          >
            Section
          </span>
          <input
            :value="section"
            type="text"
            class="block w-full rounded-md border border-border bg-bg-elevated px-2 py-1 text-sm text-fg focus:border-accent focus:outline-none"
            autocomplete="off"
            @input="onSectionInput"
            @keydown.enter.prevent="submit"
          />
        </label>

        <p v-if="notice" class="text-xs text-fg-muted" role="status">
          {{ notice }}
        </p>
        <p v-if="error" class="text-xs text-red-700 dark:text-red-300" role="alert">
          {{ error }}
        </p>

        <button
          type="button"
          class="inline-flex w-full items-center justify-center gap-1.5 rounded-md bg-accent px-3 py-1.5 text-xs font-medium text-accent-fg transition-opacity hover:opacity-90 disabled:opacity-50"
          :disabled="selectedId === null || submitting || added"
          @click="submit"
        >
          <span
            v-if="submitting"
            class="inline-block size-3 animate-spin rounded-full border-2 border-current border-t-transparent"
          />
          <svg v-else-if="added" width="11" height="11" viewBox="0 0 11 11" fill="none">
            <path
              d="M2 5.5l2.5 2.5L9 3"
              stroke="currentColor"
              stroke-width="1.5"
              stroke-linecap="round"
              stroke-linejoin="round"
            />
          </svg>
          {{ added ? "Added" : "Add" }}
        </button>
      </template>
    </div>
  </div>
</template>
