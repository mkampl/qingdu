<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";

import * as api from "@/api/client";
import { ApiError } from "@/api/client";
import type { SavedTextSummary } from "@/api/types";
import { useAnalysisStore } from "@/stores/analysis";
import { useAuthStore } from "@/stores/auth";
import { useAuthModalsStore } from "@/stores/auth-modals";
import { useReaderStore } from "@/stores/reader";
import { useToastStore } from "@/stores/toast";

import Button from "@/components/ui/Button.vue";
import Spinner from "@/components/ui/Spinner.vue";
import Tag from "@/components/ui/Tag.vue";
import TextInput from "@/components/ui/TextInput.vue";

import {
  formatDate,
  matchesSearch,
  normalizeProgress,
  parseTags,
  previewSnippet,
} from "@/utils/saved-text";

const auth = useAuthStore();
const authModals = useAuthModalsStore();
const analysis = useAnalysisStore();
const reader = useReaderStore();
const toasts = useToastStore();
const router = useRouter();

type LoadState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "ok"; texts: SavedTextSummary[] }
  | { status: "error"; message: string };

const state = ref<LoadState>({ status: "idle" });
const search = ref("");
// Per-row UX state — track which row is in "are you sure?" mode and which
// is currently being deleted, so the page survives a slow network without
// double-firing the request.
const pendingDeleteId = ref<number | null>(null);
const deletingId = ref<number | null>(null);

async function load() {
  if (!auth.isAuthed) {
    state.value = { status: "idle" };
    return;
  }
  state.value = { status: "loading" };
  try {
    const texts = await api.listTexts();
    state.value = { status: "ok", texts };
  } catch (e) {
    state.value = {
      status: "error",
      message: e instanceof ApiError ? e.message : "Couldn't load your library.",
    };
  }
}

onMounted(load);

const filtered = computed(() => {
  if (state.value.status !== "ok") return [];
  return state.value.texts.filter((t) => matchesSearch(t, search.value));
});

const total = computed(() =>
  state.value.status === "ok" ? state.value.texts.length : 0,
);

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
  return `${Math.round(text.comprehension_score * 100)}%`;
}

function open(text: SavedTextSummary) {
  // Hydrate the analysis store with the saved data and jump to the reader so
  // the user sees exactly what they saved — no re-analyse round-trip.
  // Pass id + normalised progress + title + tags so the reader can persist
  // updates, restore scroll position, and let the user rename/retag inline.
  analysis.loadSaved(text.content, text.analysisData, {
    id: text.id,
    progress: normalizeProgress(text.reading_progress),
    title: text.title ?? "",
    tags: parseTags(text.tags),
  });
  reader.reset();
  void router.push("/");
}

function askDelete(id: number) {
  pendingDeleteId.value = id;
}

function cancelDelete() {
  pendingDeleteId.value = null;
}

async function confirmDelete(text: SavedTextSummary) {
  if (deletingId.value !== null) return;
  deletingId.value = text.id;
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
  } finally {
    deletingId.value = null;
    pendingDeleteId.value = null;
  }
}
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
          Saved texts
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
      <!-- Search bar (only useful when there is something to search). -->
      <div
        v-if="state.status === 'ok' && total > 0"
        class="mb-6 max-w-sm"
      >
        <TextInput
          v-model="search"
          placeholder="Search by title or tag…"
          autocomplete="off"
        />
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
        v-else-if="state.status === 'ok' && filtered.length === 0"
        class="text-fg-muted"
      >
        <p class="font-display italic">No texts match “{{ search }}”.</p>
      </div>

      <!-- The grid -->
      <ul
        v-else
        class="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3"
      >
        <li
          v-for="text in filtered"
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
                    : `${text.known_unique.toLocaleString()} of ${text.total_unique.toLocaleString()} unique words known / ignored`
                "
              >
                {{ comprehensionLabel(text) }} known
              </span>
            </div>
          </header>

          <!-- Tags -->
          <div
            v-if="parseTags(text.tags).length"
            class="mb-3 flex flex-wrap gap-1"
          >
            <Tag
              v-for="tag in parseTags(text.tags)"
              :key="tag"
            >
              {{ tag }}
            </Tag>
          </div>

          <!-- Preview -->
          <p
            class="text-cn-serif mb-4 flex-1 text-sm leading-relaxed text-fg-muted line-clamp-3"
            :title="text.content"
          >
            {{ previewSnippet(text.content, 120) }}
          </p>

          <!-- Reading-progress hairline -->
          <div
            class="mb-3 h-px w-full bg-border-subtle"
            aria-hidden="true"
          >
            <div
              class="h-px bg-accent transition-[width]"
              :style="{ width: `${normalizeProgress(text.reading_progress) * 100}%` }"
            />
          </div>

          <!-- Footer actions -->
          <footer class="flex items-center justify-between gap-2">
            <span
              class="font-mono text-[10px] uppercase tracking-wider text-fg-subtle"
            >
              {{ Math.round(normalizeProgress(text.reading_progress) * 100) }}% read
            </span>
            <div class="flex items-center gap-1">
              <template v-if="pendingDeleteId === text.id">
                <button
                  type="button"
                  class="font-mono text-[10px] uppercase tracking-wider text-fg-subtle hover:text-fg"
                  @click="cancelDelete"
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
                <button
                  type="button"
                  class="rounded-md p-1.5 text-fg-subtle transition-colors hover:bg-bg-sunken hover:text-red-700 dark:hover:text-red-300"
                  :title="`Delete ${text.title || 'this text'}`"
                  @click="askDelete(text.id)"
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
  </section>
</template>
