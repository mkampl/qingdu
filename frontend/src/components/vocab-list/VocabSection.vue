<script setup lang="ts">
/**
 * One section of a vocab list: its name (click to rename inline), word
 * count, Learn / + Word / delete, and its words with edit and a two-step
 * delete. Which section or word is armed for deletion is held by the
 * page (`pendingDelete`, `pendingWord`), so only one is armed at a time.
 */
import { computed, ref } from "vue";

import type { VocabularySection, VocabularyWord } from "@/api/types";
import HskChip from "@/components/reader/HskChip.vue";
import Button from "@/components/ui/Button.vue";
import { createEditGate } from "@/utils/vocab-lists";

const props = defineProps<{
  section: VocabularySection;
  /** A learn request (list or section) is in flight. */
  learning: boolean;
  /** The in-flight learn request is for this section. */
  learningThis: boolean;
  rename: (oldName: string, newName: string) => Promise<void>;
  remove: () => Promise<void>;
  removeWord: (hanzi: string) => Promise<void>;
}>();

const pendingDelete = defineModel<boolean>("pendingDelete", { required: true });
const pendingWord = defineModel<string | null>("pendingWord", { required: true });

const emit = defineEmits<{
  (e: "learn"): void;
  (e: "add-word"): void;
  (e: "edit-word", word: VocabularyWord): void;
}>();

const wordCount = computed(() => props.section.words?.length ?? 0);

const renaming = ref(false);
const draft = ref("");
const gate = createEditGate();

function beginRename() {
  draft.value = props.section.name;
  renaming.value = true;
  gate.begin();
}

function cancelRename() {
  gate.take();
  renaming.value = false;
}

async function commitRename() {
  if (!gate.take()) return;
  const oldName = props.section.name;
  const newName = draft.value.trim();
  if (!newName || newName === oldName) {
    renaming.value = false;
    return;
  }
  try {
    await props.rename(oldName, newName);
  } finally {
    renaming.value = false;
  }
}

const deleting = ref(false);
async function confirmDelete() {
  deleting.value = true;
  try {
    await props.remove();
  } finally {
    deleting.value = false;
  }
}

const deletingWord = ref<string | null>(null);
async function confirmDeleteWord(hanzi: string) {
  deletingWord.value = hanzi;
  try {
    await props.removeWord(hanzi);
  } finally {
    deletingWord.value = null;
    pendingWord.value = null;
  }
}
</script>

<template>
  <section class="mb-8 rounded-lg border border-border bg-bg-elevated">
    <header
      class="flex items-center justify-between gap-3 border-b border-border-subtle px-5 py-3"
    >
      <div class="flex items-center gap-3 min-w-0 flex-1">
        <template v-if="!renaming">
          <button
            type="button"
            class="font-display text-lg font-medium text-fg hover:text-accent truncate"
            @click="beginRename"
            :title="'Click to rename section'"
          >
            {{ section.name }}
          </button>
        </template>
        <input
          v-else
          v-model="draft"
          aria-label="Section name"
          type="text"
          class="rounded-md border border-accent bg-bg-elevated px-2 py-0.5 text-lg font-medium text-fg focus:outline-none"
          autofocus
          @blur="commitRename"
          @keydown.enter.prevent="commitRename"
          @keydown.escape.prevent="cancelRename"
        />
        <span class="font-mono text-[10px] uppercase tracking-wider text-fg-subtle">
          {{ wordCount }}
          {{ wordCount === 1 ? "word" : "words" }}
        </span>
      </div>
      <div class="flex items-center gap-1">
        <Button
          v-if="wordCount > 0"
          variant="ghost"
          size="sm"
          :loading="learningThis"
          :disabled="learning"
          :title="`Take the words of “${section.name}” into review`"
          @click="emit('learn')"
        >
          Learn
        </Button>
        <Button variant="ghost" size="sm" @click="emit('add-word')">
          + Word
        </Button>
        <template v-if="pendingDelete">
          <button
            type="button"
            class="font-mono text-[10px] uppercase tracking-wider text-fg-subtle hover:text-fg"
            @click="pendingDelete = false"
            :disabled="deleting"
          >
            Cancel
          </button>
          <Button variant="danger" size="sm" :loading="deleting" @click="confirmDelete">
            Delete section
          </Button>
        </template>
        <button
          v-else
          type="button"
          class="rounded-md p-1.5 text-fg-subtle transition-colors hover:bg-bg-sunken hover:text-red-700 dark:hover:text-red-300"
          :title="`Delete section ${section.name}`"
          @click="pendingDelete = true"
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

    <ul v-if="section.words?.length" class="divide-y divide-border-subtle">
      <li
        v-for="word in section.words"
        :key="word.hanzi"
        class="group flex items-center gap-4 px-5 py-3"
      >
        <span class="text-cn-serif min-w-[5rem] text-2xl text-fg">
          {{ word.hanzi }}
        </span>
        <span class="hidden min-w-[7rem] font-sans text-sm text-fg-muted sm:inline">
          {{ word.pinyin }}
        </span>
        <span class="flex-1 truncate font-display text-base text-fg">
          {{ word.meaning }}
        </span>
        <HskChip :level="word.level" />
        <div class="flex items-center gap-1 opacity-60 group-hover:opacity-100">
          <template v-if="pendingWord === word.hanzi">
            <button
              type="button"
              class="font-mono text-[10px] uppercase tracking-wider text-fg-subtle hover:text-fg"
              @click="pendingWord = null"
            >
              Cancel
            </button>
            <Button
              variant="danger"
              size="sm"
              :loading="deletingWord === word.hanzi"
              @click="confirmDeleteWord(word.hanzi)"
            >
              Delete
            </Button>
          </template>
          <template v-else>
            <button
              type="button"
              class="rounded-md p-1.5 text-fg-subtle transition-colors hover:bg-bg-sunken hover:text-fg"
              title="Edit word"
              @click="emit('edit-word', word)"
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
              @click="pendingWord = word.hanzi"
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

    <p v-else class="px-5 py-4 text-sm italic text-fg-subtle">
      No words yet — use “+ Word” to add some.
    </p>
  </section>
</template>
