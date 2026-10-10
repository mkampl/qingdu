<script setup lang="ts">
/**
 * /words — personal SRS queue browser. Hybrid list: dense rows with
 * progressive disclosure of per-row actions (Know / Snooze / Review-now /
 * Reset). Reached from the header progress badge.
 *
 * Default sort is "due first" so the user sees what FSRS thinks they should
 * touch next. State + due-zone + HSK filter chips above. Free-text search
 * over hanzi, pinyin and meaning. Filters live in the URL query (see
 * utils/words-filters.ts) so they survive a reload or a trip to Practice.
 */

import { computed, ref, watch } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";

import * as api from "@/api/client";
import type { WordSchedule, WordsQueueItem, WordsQueueParams } from "@/api/client";
import { onAuthReady } from "@/composables/use-auth-ready";
import {
  createRequestSequence,
  mergePage,
  nextBatchSize,
  nextPageOffset,
} from "@/utils/paged-list";
import {
  DEFAULT_FILTERS,
  filtersFromQuery,
  filtersToParams,
  filtersToQuery,
  hasActiveFilters,
  isDefaultFilters,
  maxHskLevel,
  normaliseHsk,
  sameFilters,
  type DueFilter,
  type SortKey,
  type StateFilter,
  type WordsFilters,
} from "@/utils/words-filters";
import { useAuthStore } from "@/stores/auth";
import { formatUtcDate } from "@/utils/time";
import { useAuthModalsStore } from "@/stores/auth-modals";
import { useReviewStore } from "@/stores/review";
import { useSettingsStore } from "@/stores/settings";
import { useToastStore } from "@/stores/toast";
import { useUserWordsStore } from "@/stores/userWords";

import Spinner from "@/components/ui/Spinner.vue";

const auth = useAuthStore();
const authModals = useAuthModalsStore();
const review = useReviewStore();
const settings = useSettingsStore();
const toast = useToastStore();
const userWords = useUserWordsStore();
const route = useRoute();
const router = useRouter();

async function practice(word: string) {
  try {
    await review.startPractice(word, route.fullPath);
    if (review.error) {
      toast.error(review.error);
      return;
    }
    await router.push("/review");
  } catch (e) {
    toast.error(e instanceof Error ? e.message : "Practice failed to start.");
  }
}

const items = ref<WordsQueueItem[]>([]);
const total = ref(0);
const loading = ref(false);
// True after the first successful fetch. Until then the list shows the
// loading state, never "Nothing matches".
const loaded = ref(false);
const error = ref<string | null>(null);

const initial = filtersFromQuery(route.query);
const stateFilter = ref<StateFilter>(initial.state);
const dueFilter = ref<DueFilter>(initial.due);
const hskFilter = ref<Set<number>>(
  new Set(normaliseHsk(initial.hsk, maxHskLevel(settings.hskVersion))),
);
const search = ref(initial.search);
const sortKey = ref<SortKey>(initial.sort);
const expanded = ref<string | null>(null);

// Server page size; "Load more" fetches the next batch of this size.
const PAGE = 200;
// Rows the server has handed out for the current filters (its offset).
const fetched = ref(0);
// Local edits since the last fetch — each can shift the server-side list
// by one row, so the next page re-reads that many (see nextPageOffset).
const drift = ref(0);
const hasMore = ref(false);
const loadingMore = ref(false);
const loadMoreError = ref<string | null>(null);
const requests = createRequestSequence();

const filters = computed<WordsFilters>(() => ({
  state: stateFilter.value,
  due: dueFilter.value,
  hsk: Array.from(hskFilter.value),
  search: search.value,
  sort: sortKey.value,
}));

const queryParams = computed<WordsQueueParams>(() => ({
  ...filtersToParams(filters.value, settings.hskVersion),
  limit: PAGE,
}));

const hasFilters = computed(() => hasActiveFilters(filters.value));
const canReset = computed(() => !isDefaultFilters(filters.value));
const hskChips = computed(() => maxHskLevel(settings.hskVersion));

function applyFilters(f: WordsFilters) {
  stateFilter.value = f.state;
  dueFilter.value = f.due;
  hskFilter.value = new Set(normaliseHsk(f.hsk, maxHskLevel(settings.hskVersion)));
  search.value = f.search;
  sortKey.value = f.sort;
}

function resetFilters() {
  applyFilters({ ...DEFAULT_FILTERS, hsk: [] });
}

// Mirror the filters into the URL. replace(), not push(): flipping chips
// shouldn't fill the back button with one entry per click.
function syncUrl() {
  if (route.path !== "/words") return;
  if (sameFilters(filtersFromQuery(route.query), filters.value)) return;
  void router.replace({ query: filtersToQuery(filters.value) });
}

let searchTimer: number | null = null;
// Load the first page for the current filters, dropping whatever was shown.
// Responses from requests started before a newer one are ignored, so a slow
// search for "学" can't overwrite the results for "学生".
async function refresh() {
  if (searchTimer) {
    window.clearTimeout(searchTimer);
    searchTimer = null;
  }
  syncUrl();
  if (!auth.isAuthed) return;
  const id = requests.next();
  items.value = [];
  fetched.value = 0;
  drift.value = 0;
  hasMore.value = false;
  loadingMore.value = false;
  loadMoreError.value = null;
  loading.value = true;
  error.value = null;
  try {
    const r = await api.listWordsQueue({ ...queryParams.value, offset: 0 });
    if (!requests.isLatest(id)) return;
    items.value = r.items;
    total.value = r.total;
    fetched.value = r.items.length;
    hasMore.value = r.has_more;
    loaded.value = true;
    // Pull the same numbers the header badge shows, so the user can't see
    // "38 due" in the nav and "28 due" here at the same time.
    review.refreshStats();
    userWords.refreshStats();
  } catch (e) {
    if (!requests.isLatest(id)) return;
    error.value = e instanceof Error ? e.message : "Couldn't load your queue";
  } finally {
    if (requests.isLatest(id)) loading.value = false;
  }
}

async function loadMore() {
  if (loading.value || loadingMore.value || !hasMore.value) return;
  // Not a new sequence number: a filter change while this is in flight
  // calls refresh(), which bumps the sequence and makes this response stale.
  const id = requests.current();
  const offset = nextPageOffset(fetched.value, drift.value);
  loadingMore.value = true;
  loadMoreError.value = null;
  try {
    const r = await api.listWordsQueue({ ...queryParams.value, offset });
    if (!requests.isLatest(id)) return;
    items.value = mergePage(items.value, r.items, (it) => it.word);
    total.value = r.total;
    fetched.value = offset + r.items.length;
    drift.value = 0;
    hasMore.value = r.has_more;
  } catch (e) {
    if (!requests.isLatest(id)) return;
    loadMoreError.value = e instanceof Error ? e.message : "Couldn't load more words";
  } finally {
    if (requests.isLatest(id)) loadingMore.value = false;
  }
}

const nextBatch = computed(() => nextBatchSize(items.value.length, total.value, PAGE));


watch([stateFilter, dueFilter, hskFilter, sortKey], () => refresh(), { deep: true });
watch(search, () => {
  if (searchTimer) window.clearTimeout(searchTimer);
  searchTimer = window.setTimeout(() => refresh(), 200);
});
// Back/forward between filter states, or the nav link to a plain /words.
watch(
  () => route.query,
  (q) => {
    if (route.path !== "/words") return;
    const next = filtersFromQuery(q);
    if (!sameFilters(next, filters.value)) applyFilters(next);
  },
);
// Switching between old and new HSK in Settings changes what a level means.
watch(
  () => settings.hskVersion,
  (v) => {
    const kept = normaliseHsk(hskFilter.value, maxHskLevel(v));
    if (kept.length !== hskFilter.value.size) hskFilter.value = new Set(kept);
    else refresh();
  },
);
// Fetch once the boot-time session check settles (or after a login on
// this page); drop the previous account's words on logout.
onAuthReady(refresh, () => {
  items.value = [];
  total.value = 0;
  loaded.value = false;
});

function toggleHsk(n: number) {
  const next = new Set(hskFilter.value);
  if (next.has(n)) next.delete(n);
  else next.add(n);
  hskFilter.value = next;
}

function fmtDue(item: WordsQueueItem): string {
  // Never scheduled: a new card the review queue serves first (ignored
  // words never come up for review).
  if (item.due_at === null) return item.state === "ignored" ? "—" : "new";
  const sec = item.seconds_until_due ?? 0;
  if (sec <= 0) return "due now";
  const m = Math.round(sec / 60);
  if (m < 60) return `in ${m}m`;
  const h = Math.round(m / 60);
  if (h < 24) return `in ${h}h`;
  const d = Math.round(h / 24);
  if (d < 30) return `in ${d}d`;
  const mo = Math.round(d / 30);
  if (mo < 12) return `in ${mo}mo`;
  return `in ${Math.round(mo / 12)}y`;
}

function dueTone(item: WordsQueueItem): string {
  const sec = item.seconds_until_due ?? Infinity;
  if (item.due_at === null) {
    return item.state === "ignored" ? "text-fg-subtle" : "text-accent font-medium";
  }
  if (sec <= 0) return "text-accent font-medium";
  if (sec < 24 * 3600) return "text-fg";
  return "text-fg-muted";
}

// Patch one row with what the server reports (state and FSRS schedule), so
// e.g. a word just marked known shows "in 3mo", not "due now".
function patchRow(word: string, patch: Partial<WordsQueueItem> & WordSchedule) {
  items.value = items.value.map((it) => (it.word === word ? { ...it, ...patch } : it));
}

// Global counters (strip + nav badge) after a row changed.
function refreshCounters() {
  review.refreshStats();
  userWords.refreshStats();
}

async function setState(word: string, state: "known" | "learning" | "ignored") {
  try {
    const r = await userWords.setState(word, state);
    patchRow(word, {
      state,
      due_at: r.due_at,
      seconds_until_due: r.seconds_until_due,
      stability: r.stability,
      difficulty: r.difficulty,
      last_reviewed_at: r.last_reviewed_at,
    });
    drift.value++;
    refreshCounters();
    toast.success(`Marked ${word} as ${state}`);
  } catch (e) {
    toast.error(e instanceof Error ? e.message : "Update failed");
  }
}

async function resetState(word: string) {
  try {
    await userWords.clearState(word);
    const before = items.value.length;
    items.value = items.value.filter((it) => it.word !== word);
    if (items.value.length < before) {
      total.value = Math.max(0, total.value - 1);
      drift.value++;
    }
    refreshCounters();
    toast.info(`${word} back to new`);
  } catch (e) {
    toast.error(e instanceof Error ? e.message : "Reset failed");
  }
}

async function snooze(word: string, days: number) {
  try {
    const r = await api.snoozeWord(word, days);
    patchRow(word, {
      due_at: r.due_at,
      seconds_until_due: r.seconds_until_due,
      stability: r.stability,
      difficulty: r.difficulty,
      last_reviewed_at: r.last_reviewed_at,
    });
    drift.value++;
    refreshCounters();
    toast.success(`Snoozed ${word} for ${days} day${days === 1 ? "" : "s"}`);
  } catch (e) {
    toast.error(e instanceof Error ? e.message : "Snooze failed");
  }
}

async function makeDue(word: string) {
  try {
    const r = await api.reviewNow(word);
    items.value = items.value.map((it) =>
      it.word === word
        ? { ...it, due_at: r.due_at, seconds_until_due: 0 }
        : it,
    );
    drift.value++;
    refreshCounters();
    toast.success(`${word} queued for review`);
  } catch (e) {
    toast.error(e instanceof Error ? e.message : "Couldn't queue");
  }
}

function toggleExpanded(word: string) {
  expanded.value = expanded.value === word ? null : word;
}
</script>

<template>
  <section
    v-if="!auth.hydrated"
    class="mx-auto flex max-w-prose items-center justify-center gap-3 px-5 py-20 text-fg-muted"
  >
    <Spinner size="sm" />
    <span class="font-display italic">Loading…</span>
  </section>

  <section v-else-if="!auth.isAuthed" class="mx-auto max-w-prose px-5 py-20 text-center">
    <p class="font-display text-base italic leading-relaxed text-fg-muted">
      Sign in to see the words you're learning.
    </p>
    <button
      type="button"
      class="mt-4 inline-flex items-center rounded-full bg-accent px-4 py-1.5 text-sm font-medium text-accent-fg transition-opacity hover:opacity-90"
      @click="authModals.openLogin()"
    >
      Sign in
    </button>
  </section>

  <section
    v-else
    class="mx-auto max-w-5xl px-5 py-10 sm:px-8 md:py-14 lg:px-10"
  >
    <header class="mb-8 flex items-end justify-between gap-4">
      <div>
        <div class="mb-2 flex items-baseline gap-3">
          <span
            class="font-mono text-[11px] font-medium uppercase tracking-[0.22em] text-fg-subtle"
          >
            Words
          </span>
          <span class="h-px w-12 bg-border-subtle" aria-hidden="true" />
        </div>
        <h1
          class="font-display text-2xl font-medium tracking-tight text-fg sm:text-3xl"
        >
          Your review queue
        </h1>
        <p class="mt-2 max-w-prose text-sm text-fg-muted">
          {{ total.toLocaleString() }} word{{ total === 1 ? "" : "s" }} in this view.
          Open
          <RouterLink to="/review" class="font-medium text-accent hover:underline">
            Review
          </RouterLink>
          to step through them as flashcards.
        </p>
      </div>
    </header>

    <!-- Filter bar -->
    <div class="mb-6 flex flex-wrap items-center gap-2">
      <button
        type="button"
        :class="[
          'rounded-full border px-3 py-1 font-mono text-[11px] uppercase tracking-wider transition-colors',
          stateFilter === 'all'
            ? 'border-accent bg-accent/10 text-accent'
            : 'border-border bg-bg-elevated text-fg-muted hover:text-fg',
        ]"
        @click="stateFilter = 'all'"
      >
        All
      </button>
      <button
        v-for="s in ['learning', 'known', 'ignored'] as const"
        :key="s"
        type="button"
        :class="[
          'rounded-full border px-3 py-1 font-mono text-[11px] uppercase tracking-wider transition-colors',
          stateFilter === s
            ? 'border-accent bg-accent/10 text-accent'
            : 'border-border bg-bg-elevated text-fg-muted hover:text-fg',
        ]"
        @click="stateFilter = s"
      >
        {{ s }}
      </button>
      <span class="mx-1 text-fg-subtle">|</span>
      <button
        v-for="d in [
          { key: 'today' as DueFilter, label: 'Due today' },
          { key: 'week' as DueFilter, label: 'This week' },
          { key: 'month' as DueFilter, label: 'This month' },
        ]"
        :key="d.key"
        type="button"
        :class="[
          'rounded-full border px-3 py-1 font-mono text-[11px] uppercase tracking-wider transition-colors',
          dueFilter === d.key
            ? 'border-accent bg-accent/10 text-accent'
            : 'border-border bg-bg-elevated text-fg-muted hover:text-fg',
        ]"
        @click="dueFilter = dueFilter === d.key ? 'all' : d.key"
      >
        {{ d.label }}
      </button>
      <button
        v-if="canReset"
        type="button"
        class="ml-auto rounded-full px-3 py-1 font-mono text-[11px] uppercase tracking-wider text-fg-muted underline-offset-2 hover:text-fg hover:underline"
        @click="resetFilters"
      >
        Reset filters
      </button>
    </div>

    <div class="mb-6 flex flex-wrap items-center gap-2">
      <span
        class="font-mono text-[10px] uppercase tracking-wider text-fg-subtle"
        :title="settings.hskVersion === 'old' ? 'Old HSK (2.0) levels — change in Settings' : 'New HSK (3.0) levels — change in Settings'"
      >
        {{ settings.hskVersion === "old" ? "HSK 2.0" : "HSK" }}
      </span>
      <button
        v-for="n in hskChips"
        :key="n"
        type="button"
        :class="[
          'rounded-full border px-2.5 py-0.5 font-mono text-[10px] uppercase tracking-wider transition-colors',
          hskFilter.has(n)
            ? 'border-accent bg-accent/10 text-accent'
            : 'border-border bg-bg-elevated text-fg-muted hover:text-fg',
        ]"
        @click="toggleHsk(n)"
      >
        {{ n }}
      </button>
      <div class="flex-1" />
      <input
        v-model="search"
        type="search"
        placeholder="Hanzi, pinyin or meaning"
        aria-label="Search your words by hanzi, pinyin or meaning"
        class="w-48 rounded-md border border-border bg-bg-elevated px-3 py-1.5 text-sm placeholder:text-fg-subtle focus:border-accent focus:outline-none"
      />
      <select
        v-model="sortKey"
        aria-label="Sort"
        class="rounded-md border border-border bg-bg-elevated px-3 py-1.5 text-sm focus:border-accent focus:outline-none"
      >
        <option value="due">Sort: due first</option>
        <option value="recent">Sort: recently added</option>
        <option value="hsk">Sort: HSK level</option>
      </select>
    </div>

    <!-- Mini stats strip — global totals only: due counts from
         /api/review/stats (the nav badge), state totals from
         /api/words/stats. The list below is filtered; these counts are not. -->
    <div class="mb-4 flex flex-wrap gap-3 text-xs text-fg-muted">
      <span><strong class="text-accent">{{ review.stats.due_now }}</strong> due now</span>
      <span><strong>{{ review.stats.due_today }}</strong> due today</span>
      <span class="text-fg-subtle">·</span>
      <span>{{ userWords.stats.learning.toLocaleString() }} learning · {{ userWords.stats.known.toLocaleString() }} known<span v-if="userWords.stats.ignored"> · {{ userWords.stats.ignored.toLocaleString() }} ignored</span></span>
    </div>

    <p v-if="error" class="py-10 text-center text-sm text-rose-600">{{ error }}</p>
    <p v-else-if="loading || !loaded" class="py-10 text-center text-sm text-fg-subtle">Loading…</p>
    <p
      v-else-if="items.length === 0 && total === 0 && hasFilters"
      class="py-10 text-center text-sm text-fg-subtle"
    >
      None of your words match these filters.
      <button
        type="button"
        class="ml-1 font-medium text-accent hover:underline"
        @click="resetFilters"
      >
        Reset filters
      </button>
    </p>
    <p
      v-else-if="items.length === 0 && total === 0"
      class="py-10 text-center text-sm text-fg-subtle"
    >
      You aren't tracking any words yet. Words you click while reading show up here.
    </p>
    <p
      v-if="!error && loaded && !loading && items.length > 0 && items.length < total"
      class="mb-2 font-mono text-[10px] uppercase tracking-wider text-fg-subtle"
    >
      Showing {{ items.length.toLocaleString() }} of {{ total.toLocaleString() }}
    </p>
    <ul
      v-if="!error && loaded && !loading && items.length > 0"
      class="divide-y divide-border-subtle rounded-lg border border-border bg-bg-elevated"
    >
      <li
        v-for="item in items"
        :key="item.word"
        class="group"
      >
        <button
          type="button"
          class="flex w-full items-center gap-3 px-3 py-2 text-left hover:bg-bg-sunken/60 sm:px-4 sm:py-2.5"
          @click="toggleExpanded(item.word)"
          :aria-expanded="expanded === item.word"
        >
          <span class="font-cn-serif w-14 shrink-0 truncate text-base text-fg sm:text-lg">
            {{ item.word }}
          </span>
          <span class="hidden w-20 shrink-0 truncate text-xs text-fg-muted sm:inline">
            {{ item.pinyin || "—" }}
          </span>
          <span class="flex-1 truncate text-xs text-fg-muted">
            {{ item.meaning || "no gloss" }}
          </span>
          <span :class="['shrink-0 font-mono text-[10px] uppercase tracking-wider', dueTone(item)]">
            {{ fmtDue(item) }}
          </span>
          <span
            v-if="item.hsk_level"
            class="hidden shrink-0 rounded-full bg-bg-sunken px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-wider text-fg-muted sm:inline"
          >
            HSK {{ item.hsk_level }}
          </span>
          <span
            :class="[
              'shrink-0 rounded-full px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-wider',
              item.state === 'learning'
                ? 'bg-accent/15 text-accent'
                : item.state === 'known'
                  ? 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-300'
                  : 'bg-fg-subtle/15 text-fg-subtle',
            ]"
          >
            {{ item.state }}
          </span>
        </button>

        <Transition
          enter-active-class="transition-[max-height,opacity] duration-200 ease-out overflow-hidden"
          enter-from-class="max-h-0 opacity-0"
          enter-to-class="max-h-[200px] opacity-100"
          leave-active-class="transition-[max-height,opacity] duration-150 ease-in overflow-hidden"
          leave-from-class="max-h-[200px] opacity-100"
          leave-to-class="max-h-0 opacity-0"
        >
          <div
            v-if="expanded === item.word"
            class="border-t border-border-subtle bg-bg-sunken/30 px-3 py-2 sm:px-4"
          >
            <div class="flex flex-wrap items-center gap-1.5">
              <button
                v-if="item.state !== 'known'"
                type="button"
                class="rounded-md border border-emerald-500/40 bg-emerald-500/10 px-2.5 py-1 font-mono text-[10px] uppercase tracking-wider text-emerald-700 hover:bg-emerald-500/20 dark:text-emerald-300"
                @click.stop="setState(item.word, 'known')"
              >
                ✓ Know
              </button>
              <button
                v-if="item.state === 'known'"
                type="button"
                class="rounded-md border border-accent/40 bg-accent/10 px-2.5 py-1 font-mono text-[10px] uppercase tracking-wider text-accent hover:bg-accent/20"
                @click.stop="setState(item.word, 'learning')"
              >
                Back to learning
              </button>
              <button
                type="button"
                class="rounded-md border border-border bg-bg-elevated px-2.5 py-1 font-mono text-[10px] uppercase tracking-wider text-fg-muted hover:text-fg"
                @click.stop="snooze(item.word, 3)"
              >
                ⏸ Snooze 3d
              </button>
              <button
                type="button"
                class="rounded-md border border-border bg-bg-elevated px-2.5 py-1 font-mono text-[10px] uppercase tracking-wider text-fg-muted hover:text-fg"
                @click.stop="snooze(item.word, 7)"
              >
                ⏸ Snooze 7d
              </button>
              <button
                type="button"
                class="rounded-md border border-border bg-bg-elevated px-2.5 py-1 font-mono text-[10px] uppercase tracking-wider text-fg-muted hover:text-fg"
                @click.stop="makeDue(item.word)"
              >
                ⚡ Review now
              </button>
              <!-- Practice — a no-consequences session for this one word.
                   No FSRS advance, no streak update, no due-date shuffle.
                   Handy for eyeballing how a card will look next time, or
                   for extra writing practice out of turn. See the review
                   store's startPractice() for the wiring. -->
              <button
                type="button"
                class="rounded-md border border-border bg-bg-elevated px-2.5 py-1 font-mono text-[10px] uppercase tracking-wider text-fg-muted hover:text-fg"
                @click.stop="practice(item.word)"
              >
                🎯 Practice
              </button>
              <button
                v-if="item.state !== 'ignored'"
                type="button"
                class="rounded-md border border-border bg-bg-elevated px-2.5 py-1 font-mono text-[10px] uppercase tracking-wider text-fg-muted hover:text-fg"
                @click.stop="setState(item.word, 'ignored')"
              >
                ◯ Ignore
              </button>
              <button
                type="button"
                class="rounded-md border border-border bg-bg-elevated px-2.5 py-1 font-mono text-[10px] uppercase tracking-wider text-fg-muted hover:text-rose-600 hover:border-rose-300"
                @click.stop="resetState(item.word)"
              >
                ✕ Reset to new
              </button>
            </div>
            <p
              v-if="item.last_reviewed_at || item.seen_count"
              class="mt-2 font-mono text-[10px] text-fg-subtle"
            >
              <span v-if="item.seen_count">seen {{ item.seen_count }}×</span>
              <span v-if="item.last_reviewed_at">
                · last reviewed
                {{ formatUtcDate(item.last_reviewed_at) }}
              </span>
              <span v-if="item.stability !== null && item.stability !== undefined">
                · stability {{ item.stability.toFixed(1) }}d
              </span>
            </p>
          </div>
        </Transition>
      </li>
    </ul>

    <!-- Pager -->
    <template v-if="!error && loaded && !loading">
      <p v-if="loadMoreError" class="mt-3 text-center text-xs text-rose-600">
        {{ loadMoreError }}
      </p>
      <div v-if="loadingMore" class="py-4 text-center text-xs text-fg-subtle">Loading…</div>
      <button
        v-else-if="hasMore"
        type="button"
        class="mt-3 w-full rounded-md border border-border-subtle bg-bg-elevated px-3 py-2 text-xs font-medium text-fg-muted transition-colors hover:bg-bg-sunken hover:text-fg"
        @click="loadMore"
      >
        Load {{ nextBatch > 0 ? `${nextBatch} ` : "" }}more · {{ items.length.toLocaleString() }} /
        {{ total.toLocaleString() }}
      </button>
    </template>
  </section>
</template>
