<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";

import * as api from "@/api/client";
import { ApiError } from "@/api/client";
import type { VocabularyListSummary } from "@/api/types";
import { useAuthStore } from "@/stores/auth";
import { useAuthModalsStore } from "@/stores/auth-modals";
import { useToastStore } from "@/stores/toast";

import Button from "@/components/ui/Button.vue";
import Modal from "@/components/ui/Modal.vue";
import Spinner from "@/components/ui/Spinner.vue";
import TextInput from "@/components/ui/TextInput.vue";

const auth = useAuthStore();
const authModals = useAuthModalsStore();
const toasts = useToastStore();
const router = useRouter();

type LoadState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "ok"; lists: VocabularyListSummary[] }
  | { status: "error"; message: string };

const state = ref<LoadState>({ status: "idle" });
const pendingDeleteId = ref<number | null>(null);
const deletingId = ref<number | null>(null);

const createOpen = ref(false);
const createName = ref("");
const creating = ref(false);
const createError = ref<string | null>(null);

async function load() {
  if (!auth.isAuthed) {
    state.value = { status: "idle" };
    return;
  }
  state.value = { status: "loading" };
  try {
    const lists = await api.listVocabularyLists();
    state.value = { status: "ok", lists };
  } catch (e) {
    state.value = {
      status: "error",
      message: e instanceof ApiError ? e.message : "Couldn't load your vocab lists.",
    };
  }
}

onMounted(load);

const total = computed(() =>
  state.value.status === "ok" ? state.value.lists.length : 0,
);
const lists = computed<VocabularyListSummary[]>(() =>
  state.value.status === "ok" ? state.value.lists : [],
);

function wordCount(list: VocabularyListSummary): number {
  return (list.sections ?? []).reduce(
    (sum, s) => sum + (s.words?.length ?? 0),
    0,
  );
}

function sectionCount(list: VocabularyListSummary): number {
  return (list.sections ?? []).filter((s) => s.words?.length).length;
}

function openCreate() {
  createName.value = "";
  createError.value = null;
  createOpen.value = true;
}

async function submitCreate(e: Event) {
  e.preventDefault();
  if (!createName.value.trim() || creating.value) return;
  creating.value = true;
  createError.value = null;
  try {
    const result = await api.createVocabularyList({
      name: createName.value.trim(),
      type: "custom",
      sections: [],
    });
    createOpen.value = false;
    toasts.success(`Created “${createName.value.trim()}”.`);
    await router.push(`/vocab/${result.id}`);
  } catch (e) {
    createError.value =
      e instanceof ApiError ? e.message : "Couldn't create the list.";
  } finally {
    creating.value = false;
  }
}

function askDelete(id: number) {
  pendingDeleteId.value = id;
}
function cancelDelete() {
  pendingDeleteId.value = null;
}
async function confirmDelete(list: VocabularyListSummary) {
  if (deletingId.value !== null) return;
  deletingId.value = list.id;
  try {
    await api.deleteVocabularyList(list.id);
    if (state.value.status === "ok") {
      state.value = {
        status: "ok",
        lists: state.value.lists.filter((l) => l.id !== list.id),
      };
    }
    toasts.success(`Deleted “${list.name}”.`);
  } catch (e) {
    toasts.error(
      e instanceof ApiError ? e.message : "Couldn't delete the list.",
    );
  } finally {
    deletingId.value = null;
    pendingDeleteId.value = null;
  }
}
</script>

<template>
  <section class="mx-auto max-w-5xl px-5 py-10 sm:px-8 md:py-14 lg:px-10">
    <header class="mb-8 flex items-baseline justify-between gap-4">
      <div class="flex items-baseline gap-3">
        <span
          class="font-mono text-[11px] font-medium uppercase tracking-[0.22em] text-fg-subtle"
        >
          Library
        </span>
        <span class="h-px w-12 bg-border-subtle" aria-hidden="true" />
        <h1 class="font-display text-2xl font-medium tracking-tight text-fg">
          Vocabulary lists
        </h1>
      </div>
      <div class="flex items-baseline gap-3">
        <span
          v-if="state.status === 'ok'"
          class="font-mono text-[10px] uppercase tracking-wider text-fg-subtle"
        >
          {{ total }} {{ total === 1 ? "list" : "lists" }}
        </span>
        <Button
          v-if="auth.isAuthed"
          variant="primary"
          size="sm"
          @click="openCreate"
        >
          + New list
        </Button>
      </div>
    </header>

    <!-- Anonymous -->
    <div
      v-if="!auth.isAuthed"
      class="rounded-lg border border-border-subtle bg-bg-elevated p-8 text-center"
    >
      <p class="font-display text-lg italic leading-relaxed text-fg-muted">
        Your vocab lists appear here once you sign in.
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

    <!-- States -->
    <template v-else>
      <div
        v-if="state.status === 'loading'"
        class="flex items-center gap-3 text-fg-muted"
      >
        <Spinner size="sm" />
        <span class="font-display italic">Loading your lists…</span>
      </div>

      <div
        v-else-if="state.status === 'error'"
        class="rounded-md border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-800 dark:border-red-900 dark:bg-red-950/40 dark:text-red-200"
        role="alert"
      >
        {{ state.message }}
      </div>

      <div
        v-else-if="state.status === 'ok' && total === 0"
        class="flex flex-col items-start gap-4 rounded-lg border border-dashed border-border bg-bg-elevated p-8"
      >
        <span
          class="font-mono text-[10px] uppercase tracking-[0.2em] text-fg-subtle"
        >
          Nothing here yet
        </span>
        <p
          class="font-display text-lg italic leading-relaxed text-fg-muted max-w-md"
        >
          Vocabulary lists hold words you want to study — group them into
          sections, export to Anki, or download as CSV.
        </p>
        <Button variant="primary" size="sm" @click="openCreate">
          + New list
        </Button>
      </div>

      <ul
        v-else
        class="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3"
      >
        <li
          v-for="list in lists"
          :key="list.id"
          class="group flex flex-col rounded-lg border border-border bg-bg-elevated p-5 transition-shadow hover:shadow-md"
        >
          <header class="mb-3 flex items-start justify-between gap-3">
            <button
              type="button"
              class="text-cn-serif flex-1 text-left text-base font-medium leading-snug text-fg hover:text-accent line-clamp-2"
              :title="list.name"
              @click="router.push(`/vocab/${list.id}`)"
            >
              {{ list.name }}
            </button>
            <span
              v-if="list.type && list.type !== 'custom'"
              class="shrink-0 font-mono text-[9px] uppercase tracking-wider text-fg-subtle"
            >
              {{ list.type }}
            </span>
          </header>

          <p
            class="mb-5 flex flex-1 items-baseline gap-3 text-sm text-fg-muted"
          >
            <span>
              <span class="font-display text-2xl font-medium text-fg">
                {{ wordCount(list) }}
              </span>
              <span class="ml-1 font-mono text-[10px] uppercase tracking-wider text-fg-subtle">
                {{ wordCount(list) === 1 ? "word" : "words" }}
              </span>
            </span>
            <span class="text-fg-subtle/40">·</span>
            <span>
              <span class="font-display text-2xl font-medium text-fg">
                {{ sectionCount(list) }}
              </span>
              <span class="ml-1 font-mono text-[10px] uppercase tracking-wider text-fg-subtle">
                {{ sectionCount(list) === 1 ? "section" : "sections" }}
              </span>
            </span>
          </p>

          <footer class="flex items-center justify-between gap-2">
            <template v-if="pendingDeleteId === list.id">
              <button
                type="button"
                class="font-mono text-[10px] uppercase tracking-wider text-fg-subtle hover:text-fg"
                @click="cancelDelete"
                :disabled="deletingId === list.id"
              >
                Cancel
              </button>
              <Button
                variant="danger"
                size="sm"
                :loading="deletingId === list.id"
                @click="confirmDelete(list)"
              >
                Confirm
              </Button>
            </template>
            <template v-else>
              <button
                type="button"
                class="rounded-md p-1.5 text-fg-subtle transition-colors hover:bg-bg-sunken hover:text-red-700 dark:hover:text-red-300"
                :title="`Delete ${list.name}`"
                @click="askDelete(list.id)"
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
              <Button
                variant="secondary"
                size="sm"
                @click="router.push(`/vocab/${list.id}`)"
              >
                Open
                <svg
                  width="11"
                  height="11"
                  viewBox="0 0 11 11"
                  fill="none"
                  class="ml-0.5"
                >
                  <path
                    d="M2 5.5h7M6 2.5l3 3-3 3"
                    stroke="currentColor"
                    stroke-width="1.4"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                  />
                </svg>
              </Button>
            </template>
          </footer>
        </li>
      </ul>
    </template>

    <!-- New-list modal -->
    <Modal
      :open="createOpen"
      size="sm"
      close-on-backdrop
      @close="createOpen = false"
    >
      <template #header>
        <div class="flex items-baseline gap-3">
          <h2 class="font-display text-xl font-medium tracking-tight text-fg">
            New vocabulary list
          </h2>
        </div>
      </template>
      <form class="space-y-4" @submit="submitCreate">
        <TextInput
          v-model="createName"
          label="List name"
          placeholder="e.g. Chapter 1, Animals, Family…"
          autofocus
          required
        />
        <p
          v-if="createError"
          class="text-sm text-red-700 dark:text-red-300"
          role="alert"
        >
          {{ createError }}
        </p>
        <div class="flex items-center justify-end gap-2">
          <Button
            variant="ghost"
            size="sm"
            type="button"
            @click="createOpen = false"
          >
            Cancel
          </Button>
          <Button
            variant="primary"
            size="sm"
            type="submit"
            :loading="creating"
            :disabled="!createName.trim()"
          >
            Create
          </Button>
        </div>
      </form>
    </Modal>
  </section>
</template>
