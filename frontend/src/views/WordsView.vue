<script setup lang="ts">
/**
 * /words — personal SRS queue browser. Hybrid list: dense rows with
 * progressive disclosure of per-row actions (Know / Snooze / Review-now /
 * Reset). Reached from the header progress badge.
 *
 * Default sort is "due first" so the user sees what FSRS thinks they should
 * touch next. State + due-zone + HSK filter chips above. Free-text search
 * for jumping to a known word.
 */

import { computed, onMounted, ref, watch } from "vue";
import { RouterLink } from "vue-router";

import * as api from "@/api/client";
import type { WordsQueueItem, WordsQueueParams } from "@/api/client";
import { useAuthStore } from "@/stores/auth";
import { useToastStore } from "@/stores/toast";
import { useUserWordsStore } from "@/stores/userWords";

const auth = useAuthStore();
const toast = useToastStore();
const userWords = useUserWordsStore();

type StateFilter = "all" | "learning" | "known" | "ignored";
type DueFilter = "all" | "today" | "week" | "month";
type SortKey = "due" | "recent" | "hsk";

const items = ref<WordsQueueItem[]>([]);
const total = ref(0);
const loading = ref(false);
const error = ref<string | null>(null);

const stateFilter = ref<StateFilter>("all");
const dueFilter = ref<DueFilter>("all");
const hskFilter = ref<Set<number>>(new Set());
const search = ref("");
const sortKey = ref<SortKey>("due");
const expanded = ref<string | null>(null);

const queryParams = computed<WordsQueueParams>(() => {
  const p: WordsQueueParams = { sort: sortKey.value, limit: 200 };
  if (stateFilter.value !== "all") p.state = stateFilter.value;
  if (dueFilter.value === "today") p.dueWithinDays = 0;
  else if (dueFilter.value === "week") p.dueWithinDays = 7;
  else if (dueFilter.value === "month") p.dueWithinDays = 30;
  if (hskFilter.value.size > 0) p.hskLevels = Array.from(hskFilter.value).join(",");
  if (search.value.trim()) p.search = search.value.trim();
  return p;
});

let searchTimer: number | null = null;
async function refresh() {
  if (!auth.isAuthed) return;
  loading.value = true;
  error.value = null;
  try {
    const r = await api.listWordsQueue(queryParams.value);
    items.value = r.items;
    total.value = r.total;
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Couldn't load your queue";
  } finally {
    loading.value = false;
  }
}

watch([stateFilter, dueFilter, hskFilter, sortKey], () => refresh(), { deep: true });
watch(search, () => {
  if (searchTimer) window.clearTimeout(searchTimer);
  searchTimer = window.setTimeout(() => refresh(), 200);
});
onMounted(() => refresh());

function toggleHsk(n: number) {
  const next = new Set(hskFilter.value);
  if (next.has(n)) next.delete(n);
  else next.add(n);
  hskFilter.value = next;
}

function fmtDue(item: WordsQueueItem): string {
  if (item.due_at === null) return "no schedule";
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
  if (item.due_at === null) return "text-fg-subtle";
  if (sec <= 0) return "text-accent font-medium";
  if (sec < 24 * 3600) return "text-fg";
  return "text-fg-muted";
}

const counts = computed(() => {
  const c = { due_now: 0, due_week: 0, learning: 0, known: 0, ignored: 0 };
  const now = Date.now();
  for (const it of items.value) {
    if (it.state === "learning") c.learning++;
    if (it.state === "known") c.known++;
    if (it.state === "ignored") c.ignored++;
    if (it.due_at) {
      const t = new Date(it.due_at).getTime();
      if (t <= now) c.due_now++;
      else if (t - now < 7 * 86400_000) c.due_week++;
    }
  }
  return c;
});

async function setState(word: string, state: "known" | "learning" | "ignored") {
  try {
    await userWords.setState(word, state);
    items.value = items.value.map((it) =>
      it.word === word ? { ...it, state } : it,
    );
    toast.success(`Marked ${word} as ${state}`);
  } catch (e) {
    toast.error(e instanceof Error ? e.message : "Update failed");
  }
}

async function resetState(word: string) {
  try {
    await userWords.clearState(word);
    items.value = items.value.filter((it) => it.word !== word);
    toast.info(`${word} back to new`);
  } catch (e) {
    toast.error(e instanceof Error ? e.message : "Reset failed");
  }
}

async function snooze(word: string, days: number) {
  try {
    const r = await api.snoozeWord(word, days);
    items.value = items.value.map((it) =>
      it.word === word
        ? { ...it, due_at: r.due_at, seconds_until_due: days * 86400 }
        : it,
    );
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
  <section v-if="!auth.isAuthed" class="mx-auto max-w-prose px-5 py-20 text-center">
    <p class="font-display text-base italic leading-relaxed text-fg-muted">
      Sign in to see the words you're learning.
    </p>
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
          {{ total.toLocaleString() }} word{{ total === 1 ? "" : "s" }} in your collection.
          Open
          <RouterLink to="/review" class="font-medium text-accent hover:underline">
            Review
          </RouterLink>
          to step through them as flashcards, or browse here.
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
    </div>

    <div class="mb-6 flex flex-wrap items-center gap-2">
      <span class="font-mono text-[10px] uppercase tracking-wider text-fg-subtle">
        HSK
      </span>
      <button
        v-for="n in 9"
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
        placeholder="Search a character"
        class="w-40 rounded-md border border-border bg-bg-elevated px-3 py-1.5 text-sm placeholder:text-fg-subtle focus:border-accent focus:outline-none"
      />
      <select
        v-model="sortKey"
        class="rounded-md border border-border bg-bg-elevated px-3 py-1.5 text-sm focus:border-accent focus:outline-none"
      >
        <option value="due">Sort: due first</option>
        <option value="recent">Sort: recently added</option>
        <option value="hsk">Sort: HSK level</option>
      </select>
    </div>

    <!-- Mini stats strip — derived from currently-filtered list. -->
    <div class="mb-4 flex flex-wrap gap-3 text-xs text-fg-muted">
      <span><strong class="text-accent">{{ counts.due_now }}</strong> due now</span>
      <span><strong>{{ counts.due_week }}</strong> within a week</span>
      <span class="text-fg-subtle">·</span>
      <span>{{ counts.learning }} learning · {{ counts.known }} known<span v-if="counts.ignored"> · {{ counts.ignored }} ignored</span></span>
    </div>

    <p v-if="loading" class="py-10 text-center text-sm text-fg-subtle">Loading…</p>
    <p v-else-if="error" class="py-10 text-center text-sm text-rose-600">{{ error }}</p>
    <p
      v-else-if="items.length === 0"
      class="py-10 text-center text-sm text-fg-subtle"
    >
      Nothing matches. Try clearing the filters above.
    </p>
    <ul v-else class="divide-y divide-border-subtle rounded-lg border border-border bg-bg-elevated">
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
                {{ new Date(item.last_reviewed_at).toLocaleDateString() }}
              </span>
              <span v-if="item.stability !== null && item.stability !== undefined">
                · stability {{ item.stability.toFixed(1) }}d
              </span>
            </p>
          </div>
        </Transition>
      </li>
    </ul>
  </section>
</template>
