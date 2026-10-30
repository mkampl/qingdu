<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import * as api from "@/api/client";
import { ApiError } from "@/api/client";
import type { SavedTextSummary, TextFolder } from "@/api/types";
import FolderNameModal from "@/components/texts/FolderNameModal.vue";
import FolderPickerModal from "@/components/texts/FolderPickerModal.vue";
import SeriesCreateModal from "@/components/texts/SeriesCreateModal.vue";
import { useInlineDelete } from "@/composables/use-inline-delete";
import { useOpenSavedText } from "@/composables/use-open-saved-text";
import { useAuthStore } from "@/stores/auth";
import { useAuthModalsStore } from "@/stores/auth-modals";
import { useCapabilitiesStore } from "@/stores/capabilities";
import { useTextFoldersStore } from "@/stores/text-folders";
import { useToastStore } from "@/stores/toast";

import Button from "@/components/ui/Button.vue";
import Spinner from "@/components/ui/Spinner.vue";
import Tag from "@/components/ui/Tag.vue";
import TextInput from "@/components/ui/TextInput.vue";

import type { LoadState } from "@/utils/load-state";
import {
  formatDate,
  matchesSearch,
  normalizeProgress,
  parseTags,
  previewSnippet,
} from "@/utils/saved-text";
import {
  childFolders,
  folderCounts,
  folderLabel,
  folderPath,
  textsIn,
} from "@/utils/text-folders";

const auth = useAuthStore();
const authModals = useAuthModalsStore();
const folderStore = useTextFoldersStore();
const toasts = useToastStore();
const router = useRouter();
const route = useRoute();
const openSavedText = useOpenSavedText();
const capabilities = useCapabilitiesStore();

const state = ref<LoadState<{ texts: SavedTextSummary[] }>>({ status: "idle" });
const search = ref("");
const openingId = ref<number | null>(null);

async function load() {
  if (!auth.isAuthed) {
    state.value = { status: "idle" };
    return;
  }
  state.value = { status: "loading" };
  try {
    const [texts] = await Promise.all([api.listTexts(), folderStore.load(), loadSeries()]);
    state.value = { status: "ok", texts };
  } catch (e) {
    state.value = {
      status: "error",
      message:
        e instanceof ApiError ? e.message : "Couldn't load your library.",
    };
  }
}

onMounted(load);

// Signing in from the sign-in CTA opens a modal without navigating, so
// load on the auth change.
watch(
  () => auth.isAuthed,
  (isAuthed) => {
    if (isAuthed) void load();
  },
);

const allTexts = computed(() => (state.value.status === "ok" ? state.value.texts : []));
const folders = computed(() => folderStore.folders);

// The open folder lives in the URL (?folder=3) so back/forward and links
// work; the store remembers it so a text saved from the reader lands here.
const folderId = computed<number | null>(() => {
  const raw = Number(route.query.folder);
  return Number.isInteger(raw) && raw > 0 ? raw : null;
});
watch(
  folderId,
  (id) => {
    folderStore.currentFolderId = id;
  },
  { immediate: true },
);
const crumbs = computed(() => folderPath(folders.value, folderId.value));
const currentFolder = computed(() => crumbs.value[crumbs.value.length - 1] ?? null);

function goFolder(id: number | null) {
  search.value = "";
  void router.push({ path: "/texts", query: id === null ? {} : { folder: String(id) } });
}

const searching = computed(() => search.value.trim() !== "");
// Searching looks through every folder.
const filtered = computed(() =>
  searching.value
    ? allTexts.value.filter((t) => matchesSearch(t, search.value))
    : textsIn(allTexts.value, folderId.value),
);
const subfolders = computed(() =>
  searching.value ? [] : childFolders(folders.value, folderId.value),
);
const inFolder = computed(() => !searching.value && folderId.value !== null);

const total = computed(() => allTexts.value.length);

/**
 * Comprehension-band colour for the chip. Matches the "comprehensible
 * input" rule of thumb: <50% is too hard, 50-89% is a stretch, 90-98% is
 * the sweet spot for reading without lookups, 98%+ is review territory.
 */
function comprehensionChipClass(score: number | null): string {
  if (score === null) return "bg-bg-sunken text-fg-subtle";
  if (score < 0.5) {
    return "bg-red-50 text-red-700 dark:bg-red-500/10 dark:text-red-300";
  }
  if (score < 0.9) {
    return "bg-amber-50 text-amber-800 dark:bg-amber-500/15 dark:text-amber-200";
  }
  if (score < 0.98) {
    return "bg-emerald-50 text-emerald-800 dark:bg-emerald-500/15 dark:text-emerald-200";
  }
  return "bg-sky-50 text-sky-800 dark:bg-sky-500/15 dark:text-sky-200";
}

function comprehensionLabel(text: SavedTextSummary): string {
  if (text.comprehension_score === null) return "—";
  const pct = `${Math.floor(text.comprehension_score * 100)}% known`;
  if (text.unlocked) return `${pct} · readable`;
  return text.to_unlock ? `${pct} · ${text.to_unlock} to go` : pct;
}

async function open(text: SavedTextSummary) {
  if (openingId.value !== null) return;
  openingId.value = text.id;
  try {
    await openSavedText(text.id);
  } finally {
    openingId.value = null;
  }
}

// --- Topic series ------------------------------------------------------------

const seriesList = ref<api.TextSeriesInfo[]>([]);
const seriesHere = computed(
  () => seriesList.value.find((x) => x.folder_id === folderId.value) ?? null,
);
const seriesModal = ref(false);
const seriesBusy = ref(false);
let pollTimer: ReturnType<typeof setTimeout> | null = null;

async function loadSeries() {
  try {
    seriesList.value = await api.listSeries();
  } catch {
    seriesList.value = []; // an older server has no series
  }
  schedulePoll();
}

/** While a text is being written, look again every few seconds. */
function schedulePoll() {
  if (pollTimer) clearTimeout(pollTimer);
  const busy = seriesList.value.filter((x) => x.generating);
  if (!busy.length) return;
  pollTimer = setTimeout(async () => {
    const before = new Map(seriesList.value.map((x) => [x.id, x.texts]));
    const fresh = await Promise.all(busy.map((x) => api.getSeries(x.id).catch(() => x)));
    seriesList.value = seriesList.value.map((x) => fresh.find((f) => f.id === x.id) ?? x);
    if (fresh.some((f) => !f.generating || f.texts !== before.get(f.id))) {
      state.value = { status: "ok", texts: await api.listTexts() };
    }
    schedulePoll();
  }, 4000);
}
onBeforeUnmount(() => {
  if (pollTimer) clearTimeout(pollTimer);
});

async function createSeries(input: {
  topic: string;
  level: number;
  new_words: number;
  length: api.SeriesLength;
}) {
  seriesBusy.value = true;
  try {
    const created = await api.createSeries(input);
    seriesModal.value = false;
    await folderStore.load();
    seriesList.value = [...seriesList.value, created];
    goFolder(created.folder_id);
    schedulePoll();
  } catch (e) {
    toasts.error(e instanceof ApiError ? e.message : "Couldn't start the series.");
  } finally {
    seriesBusy.value = false;
  }
}

async function nextInSeries() {
  const here = seriesHere.value;
  if (!here) return;
  try {
    const updated = await api.nextSeriesText(here.id);
    seriesList.value = seriesList.value.map((x) => (x.id === updated.id ? updated : x));
    schedulePoll();
  } catch (e) {
    toasts.error(e instanceof ApiError ? e.message : "Couldn't start the next text.");
  }
}

async function changeSeries(patch: Partial<{ level: number; new_words: number }>) {
  const here = seriesHere.value;
  if (!here) return;
  const updated = await api.updateSeries(here.id, patch);
  seriesList.value = seriesList.value.map((x) => (x.id === updated.id ? updated : x));
}

// --- Folders ---------------------------------------------------------------

const nameModal = ref<{ mode: "new" } | { mode: "rename"; folder: TextFolder } | null>(null);
const nameBusy = ref(false);

async function submitName(name: string) {
  if (!nameModal.value) return;
  nameBusy.value = true;
  try {
    if (nameModal.value.mode === "new") {
      await api.createFolder(name, folderId.value);
    } else {
      await api.renameFolder(nameModal.value.folder.id, name);
    }
    await folderStore.load();
    nameModal.value = null;
  } catch (e) {
    toasts.error(e instanceof ApiError ? e.message : "Couldn't save the folder.");
  } finally {
    nameBusy.value = false;
  }
}

const pendingFolderDelete = ref<number | null>(null);

async function removeFolder(folder: TextFolder) {
  try {
    await api.deleteFolder(folder.id);
    await load();
    toasts.success(`Deleted folder "${folder.name}". Its texts moved up one level.`);
  } catch (e) {
    toasts.error(e instanceof ApiError ? e.message : "Couldn't delete the folder.");
  } finally {
    pendingFolderDelete.value = null;
  }
}

// What the folder picker is moving: a text or a folder.
const moving = ref<{ text: SavedTextSummary } | { folder: TextFolder } | null>(null);
const movingCurrent = computed(() => {
  const m = moving.value;
  if (!m) return null;
  return "text" in m ? (m.text.folder_id ?? null) : m.folder.parent_id;
});

async function moveTo(target: number | null) {
  const m = moving.value;
  moving.value = null;
  if (!m) return;
  try {
    if ("text" in m) {
      await api.updateText(m.text.id, { folder_id: target });
    } else {
      await api.moveFolder(m.folder.id, target);
    }
    await load();
    const where = target === null ? "the top level" : folderLabel(folders.value, target);
    toasts.success(`Moved to ${where}.`);
  } catch (e) {
    toasts.error(e instanceof ApiError ? e.message : "Couldn't move it.");
  }
}

/** Move a text one place up or down in its folder. */
async function shift(text: SavedTextSummary, by: -1 | 1) {
  if (folderId.value === null || state.value.status !== "ok") return;
  const ids = filtered.value.map((t) => t.id);
  const i = ids.indexOf(text.id);
  const j = i + by;
  if (i < 0 || j < 0 || j >= ids.length) return;
  [ids[i], ids[j]] = [ids[j], ids[i]];
  // Optimistic: renumber locally, then save.
  const pos = new Map(ids.map((id, k) => [id, k]));
  state.value = {
    status: "ok",
    texts: state.value.texts.map((t) => (pos.has(t.id) ? { ...t, position: pos.get(t.id)! } : t)),
  };
  try {
    await api.orderTexts(folderId.value, ids);
  } catch (e) {
    toasts.error(e instanceof ApiError ? e.message : "Couldn't save the order.");
    void load();
  }
}

// The row asking "are you sure?" and the one being deleted (no double
// request on a slow network).
const {
  pendingId: pendingDeleteId,
  deletingId,
  confirmDelete,
} = useInlineDelete(async (text: SavedTextSummary) => {
  try {
    await api.deleteText(text.id);
    if (state.value.status === "ok") {
      state.value = {
        status: "ok",
        texts: state.value.texts.filter((t) => t.id !== text.id),
      };
    }
    toasts.success(`Deleted "${text.title || "Untitled"}".`);
  } catch (e) {
    toasts.error(
      e instanceof ApiError ? e.message : "Couldn't delete that text.",
    );
  }
});
</script>

<template>
  <section class="mx-auto max-w-5xl px-5 py-10 sm:px-8 md:py-14 lg:px-10">
    <!-- Header strip mirrors the reader's editorial header style. -->
    <header class="mb-8 flex items-baseline justify-between gap-4">
      <div class="flex items-baseline gap-3">
        <span
          class="font-mono text-[11px] font-medium uppercase tracking-[0.22em] text-fg-subtle"
        >
          Library
        </span>
        <span class="h-px w-12 bg-border-subtle" aria-hidden="true" />
        <h1 class="font-display text-2xl font-medium tracking-tight text-fg">
          <button
            v-if="crumbs.length"
            type="button"
            class="hover:text-accent"
            @click="goFolder(null)"
          >
            Saved texts
          </button>
          <template v-else>Saved texts</template>
        </h1>
      </div>
      <span
        v-if="state.status === 'ok'"
        class="font-mono text-[10px] uppercase tracking-wider text-fg-subtle"
      >
        {{ total }} {{ total === 1 ? "text" : "texts" }}
      </span>
    </header>

    <!-- Anonymous: sign-in CTA. -->
    <div
      v-if="!auth.isAuthed"
      class="rounded-lg border border-border-subtle bg-bg-elevated p-8 text-center"
    >
      <p class="font-display text-lg italic leading-relaxed text-fg-muted">
        Your library appears here once you sign in.
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

    <!-- Authenticated — main content. -->
    <template v-else>
      <!-- Folder path: Saved texts › TaiJiMen › 道德经 -->
      <nav
        v-if="crumbs.length && !searching"
        class="-mt-4 mb-5 flex flex-wrap items-center gap-x-1.5 gap-y-1 text-sm"
        aria-label="Folder path"
      >
        <button type="button" class="text-fg-muted hover:text-accent" @click="goFolder(null)">
          All texts
        </button>
        <template v-for="(f, i) in crumbs" :key="f.id">
          <span class="text-fg-subtle" aria-hidden="true">›</span>
          <button
            v-if="i < crumbs.length - 1"
            type="button"
            class="text-cn-serif text-fg-muted hover:text-accent"
            @click="goFolder(f.id)"
          >
            {{ f.name }}
          </button>
          <span v-else class="text-cn-serif font-medium text-fg">{{ f.name }}</span>
        </template>
        <span v-if="currentFolder" class="ml-2 flex items-center gap-2">
          <button
            type="button"
            class="font-mono text-[10px] uppercase tracking-wider text-fg-subtle hover:text-fg"
            @click="nameModal = { mode: 'rename', folder: currentFolder }"
          >
            Rename
          </button>
          <button
            type="button"
            class="font-mono text-[10px] uppercase tracking-wider text-fg-subtle hover:text-fg"
            @click="moving = { folder: currentFolder }"
          >
            Move
          </button>
        </span>
      </nav>

      <!-- Search + new folder. Search looks through every folder. -->
      <div v-if="state.status === 'ok'" class="mb-6 flex flex-wrap items-center gap-3">
        <div v-if="total > 0 || folders.length > 0" class="w-full max-w-sm">
          <TextInput
            v-model="search"
            placeholder="Search all texts by title or tag…"
            autocomplete="off"
          />
        </div>
        <Button variant="ghost" size="sm" @click="nameModal = { mode: 'new' }">
          + New folder
        </Button>
        <Button
          v-if="capabilities.llmFeature('series')"
          variant="ghost"
          size="sm"
          title="Texts on a topic of your choice, written for your words"
          @click="seriesModal = true"
        >
          + New topic series
        </Button>
      </div>

      <!-- A topic series' folder: write the next text, change its settings. -->
      <div
        v-if="seriesHere && !searching"
        class="mb-6 rounded-lg border border-accent/40 bg-accent/5 px-4 py-3"
      >
        <div class="flex flex-wrap items-center justify-between gap-3">
          <p class="text-sm text-fg">
            <span class="font-mono text-[10px] uppercase tracking-wider text-accent">Topic series</span>
            <span class="ml-2">{{ seriesHere.texts }} text{{ seriesHere.texts === 1 ? "" : "s" }}</span>
          </p>
          <Button
            v-if="capabilities.llmFeature('series')"
            variant="primary"
            size="sm"
            :loading="seriesHere.generating"
            :disabled="seriesHere.generating"
            @click="nextInSeries"
          >
            {{ seriesHere.texts ? "Write the next text" : "Write the first text" }}
          </Button>
        </div>
        <p v-if="seriesHere.generating" class="mt-2 text-xs text-fg-muted">
          Writing a text for your words… about a minute. You can keep reading meanwhile.
        </p>
        <p v-else-if="seriesHere.last_error" class="mt-2 text-xs text-red-700 dark:text-red-300">
          {{ seriesHere.last_error }}
        </p>
        <div class="mt-2 flex flex-wrap items-center gap-3 text-xs text-fg-muted">
          <label>
            Level
            <select
              :value="seriesHere.level"
              class="ml-1 rounded border border-border-subtle bg-bg px-1 py-0.5"
              @change="changeSeries({ level: Number(($event.target as HTMLSelectElement).value) })"
            >
              <option v-for="l in 7" :key="l" :value="l">HSK {{ l === 7 ? "7–9" : l }}</option>
            </select>
          </label>
          <label>
            New words per text
            <select
              :value="seriesHere.new_words"
              class="ml-1 rounded border border-border-subtle bg-bg px-1 py-0.5"
              @change="changeSeries({ new_words: Number(($event.target as HTMLSelectElement).value) })"
            >
              <option v-for="n in [5, 10, 15, 20, 30, 40, 50]" :key="n" :value="n">{{ n }}</option>
            </select>
          </label>
          <span v-if="seriesHere.new_words >= 20">Tip: pre-learn the missing words before reading.</span>
        </div>
      </div>

      <!-- States -->
      <div
        v-if="state.status === 'loading'"
        class="flex items-center gap-3 text-fg-muted"
      >
        <Spinner size="sm" />
        <span class="font-display italic">Fetching your library…</span>
      </div>

      <div
        v-else-if="state.status === 'error'"
        class="rounded-md border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-800 dark:border-red-900 dark:bg-red-950/40 dark:text-red-200"
        role="alert"
      >
        {{ state.message }}
      </div>

      <!-- Empty library -->
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
          Analyse a Chinese text in the reader and use “Save text” to keep it
          here for later.
        </p>
        <Button variant="primary" size="sm" @click="router.push('/')">
          Go to reader
        </Button>
      </div>

      <!-- No search match -->
      <div
        v-else-if="state.status === 'ok' && searching && filtered.length === 0"
        class="text-fg-muted"
      >
        <p class="font-display italic">No texts match “{{ search }}”.</p>
      </div>

      <template v-else-if="state.status === 'ok'">
      <!-- Folders -->
      <ul
        v-if="subfolders.length"
        class="mb-6 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3"
      >
        <li
          v-for="f in subfolders"
          :key="f.id"
          class="flex items-center gap-3 rounded-lg border border-border bg-bg-elevated px-4 py-3 transition-shadow hover:shadow-md"
        >
          <svg width="18" height="18" viewBox="0 0 14 14" fill="none" aria-hidden="true" class="shrink-0 text-accent">
            <path
              d="M1.5 4V11.5h11V5H7L5.5 3h-4z"
              stroke="currentColor"
              stroke-width="1.1"
              stroke-linejoin="round"
            />
          </svg>
          <button type="button" class="min-w-0 flex-1 text-left" @click="goFolder(f.id)">
            <span class="text-cn-serif block truncate font-medium text-fg hover:text-accent">
              {{ f.name }}
            </span>
            <span class="font-mono text-[10px] uppercase tracking-wider text-fg-subtle">
              {{ folderCounts(folders, allTexts, f.id).total }} texts
              <template v-if="folderCounts(folders, allTexts, f.id).total">
                · {{ folderCounts(folders, allTexts, f.id).readable }} readable
              </template>
            </span>
          </button>
          <template v-if="pendingFolderDelete === f.id">
            <button
              type="button"
              class="font-mono text-[10px] uppercase tracking-wider text-fg-subtle hover:text-fg"
              @click="pendingFolderDelete = null"
            >
              Cancel
            </button>
            <Button variant="danger" size="sm" @click="removeFolder(f)">Delete</Button>
          </template>
          <button
            v-else
            type="button"
            class="rounded-md p-1.5 text-fg-subtle transition-colors hover:bg-bg-sunken hover:text-red-700 dark:hover:text-red-300"
            :title="`Delete the folder ${f.name} (its texts move up one level)`"
            @click="pendingFolderDelete = f.id"
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
        </li>
      </ul>

      <p
        v-if="!searching && filtered.length === 0 && subfolders.length === 0"
        class="font-display italic text-fg-muted"
      >
        This folder is empty. Use “Move” on a text to put it here.
      </p>

      <!-- The grid -->
      <ul v-if="filtered.length" class="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <li
          v-for="(text, idx) in filtered"
          :key="text.id"
          class="group flex flex-col rounded-lg border border-border bg-bg-elevated p-5 transition-shadow hover:shadow-md"
        >
          <!-- Title + date -->
          <header class="mb-2 flex items-start justify-between gap-3">
            <button
              type="button"
              class="text-cn-serif flex-1 text-left text-base font-medium leading-snug text-fg hover:text-accent line-clamp-2"
              :title="text.title"
              @click="open(text)"
            >
              {{ text.title || "Untitled" }}
            </button>
            <div class="flex shrink-0 flex-col items-end gap-1">
              <span
                class="font-mono text-[10px] uppercase tracking-wider text-fg-subtle"
              >
                {{ formatDate(text.date) }}
              </span>
              <span
                class="inline-flex items-center gap-1 rounded-full px-2 py-0.5 font-mono text-[10px] font-medium tabular-nums"
                :class="comprehensionChipClass(text.comprehension_score)"
                :title="
                  text.comprehension_score === null
                    ? 'No CJK words in this text yet'
                    : `Share of the running words you know. ${text.known_unique.toLocaleString()} of ${text.total_unique.toLocaleString()} different words known / ignored` +
                      (text.to_unlock ? ` — learn ${text.to_unlock} more to read it comfortably (95%)` : '')
                "
              >
                {{ comprehensionLabel(text) }}
              </span>
            </div>
          </header>

          <!-- Place in the folder, or the folder when searching. -->
          <p
            v-if="inFolder || (searching && text.folder_id)"
            class="mb-2 font-mono text-[10px] uppercase tracking-wider text-fg-subtle"
          >
            <template v-if="inFolder">{{ idx + 1 }} / {{ filtered.length }}</template>
            <span v-else class="text-cn-serif normal-case tracking-normal">
              {{ folderLabel(folders, text.folder_id) }}
            </span>
          </p>

          <!-- Tags -->
          <div
            v-if="parseTags(text.tags).length"
            class="mb-3 flex flex-wrap gap-1"
          >
            <Tag v-for="tag in parseTags(text.tags)" :key="tag">
              {{ tag }}
            </Tag>
          </div>

          <!-- Preview -->
          <p
            class="text-cn-serif mb-4 flex-1 text-sm leading-relaxed text-fg-muted line-clamp-3"
            :title="text.preview"
          >
            {{ previewSnippet(text.preview, 120) }}
          </p>

          <!-- Reading-progress hairline -->
          <div class="mb-3 h-px w-full bg-border-subtle" aria-hidden="true">
            <div
              class="h-px bg-accent transition-[width]"
              :style="{
                width: `${normalizeProgress(text.reading_progress) * 100}%`,
              }"
            />
          </div>

          <!-- Footer actions -->
          <footer class="flex items-center justify-between gap-2">
            <span
              class="font-mono text-[10px] uppercase tracking-wider text-fg-subtle"
            >
              {{ Math.round(normalizeProgress(text.reading_progress) * 100) }}%
              read
            </span>
            <div class="flex items-center gap-1">
              <template v-if="pendingDeleteId === text.id">
                <button
                  type="button"
                  class="font-mono text-[10px] uppercase tracking-wider text-fg-subtle hover:text-fg"
                  @click="pendingDeleteId = null"
                  :disabled="deletingId === text.id"
                >
                  Cancel
                </button>
                <Button
                  variant="danger"
                  size="sm"
                  :loading="deletingId === text.id"
                  @click="confirmDelete(text)"
                >
                  Confirm
                </Button>
              </template>
              <template v-else>
                <template v-if="inFolder">
                  <button
                    type="button"
                    class="rounded-md p-1.5 text-fg-subtle transition-colors hover:bg-bg-sunken hover:text-fg disabled:opacity-30"
                    :disabled="idx === 0"
                    title="Move up"
                    aria-label="Move up"
                    @click="shift(text, -1)"
                  >
                    ↑
                  </button>
                  <button
                    type="button"
                    class="rounded-md p-1.5 text-fg-subtle transition-colors hover:bg-bg-sunken hover:text-fg disabled:opacity-30"
                    :disabled="idx === filtered.length - 1"
                    title="Move down"
                    aria-label="Move down"
                    @click="shift(text, 1)"
                  >
                    ↓
                  </button>
                </template>
                <button
                  type="button"
                  class="rounded-md px-1.5 py-1 font-mono text-[10px] uppercase tracking-wider text-fg-subtle transition-colors hover:bg-bg-sunken hover:text-fg"
                  title="Move to another folder"
                  @click="moving = { text }"
                >
                  Move
                </button>
                <button
                  type="button"
                  class="rounded-md p-1.5 text-fg-subtle transition-colors hover:bg-bg-sunken hover:text-red-700 dark:hover:text-red-300"
                  :title="`Delete ${text.title || 'this text'}`"
                  @click="pendingDeleteId = text.id"

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
                  :loading="openingId === text.id"
                  @click="open(text)"
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
            </div>
          </footer>
        </li>
      </ul>
      </template>
    </template>

    <SeriesCreateModal
      :open="seriesModal"
      :busy="seriesBusy"
      @close="seriesModal = false"
      @create="createSeries"
    />
    <FolderNameModal
      :open="nameModal !== null"
      :title="nameModal?.mode === 'rename' ? 'Rename folder' : 'New folder'"
      :initial="nameModal?.mode === 'rename' ? nameModal.folder.name : ''"
      :busy="nameBusy"
      @close="nameModal = null"
      @submit="submitName"
    />
    <FolderPickerModal
      :open="moving !== null"
      :title="moving && 'folder' in moving ? `Move “${moving.folder.name}” to…` : 'Move text to…'"
      :folders="folders"
      :current-id="movingCurrent"
      :moving-folder-id="moving && 'folder' in moving ? moving.folder.id : null"
      @close="moving = null"
      @pick="moveTo"
    />
  </section>
</template>
