<script setup lang="ts">
/**
 * The grammar section: every point of the HSK 3.0 grammar syllabus by
 * level and kind, how often the user met it in texts they read to the
 * end, and whether it is due for practice.
 */
import { computed, onMounted, ref, watch } from "vue";
import { RouterLink } from "vue-router";

import * as api from "@/api/client";
import { useAuthStore } from "@/stores/auth";
import { useAuthModalsStore } from "@/stores/auth-modals";
import { storageGet, storageSet } from "@/utils/storage";

type Overview = Awaited<ReturnType<typeof api.getGrammar>>;
type Filter = "all" | "met" | "unmet" | "due";

const LEVELS = ["1", "2", "3", "4", "5", "6", "7-9"];
// The syllabus' kinds of points, in English.
const GROUPS: Record<string, string> = {
  动作的态: "Aspect",
  固定格式: "Fixed patterns",
  句子的类型: "Sentence types",
  强调的方法: "Emphasis",
  提问的方法: "Asking questions",
  口语格式: "Spoken patterns",
  特殊表达法: "Special expressions",
  词类: "Word classes",
  短语: "Phrases",
  句子成分: "Sentence parts",
  句群: "Linking sentences",
  语素: "Word parts",
};
const GROUP_ORDER = Object.keys(GROUPS);
const LEVEL_KEY = "qingdu.grammar.level";

const auth = useAuthStore();
const authModals = useAuthModalsStore();
const data = ref<Overview | null>(null);
const error = ref<string | null>(null);
const filter = ref<Filter>("all");
const level = ref<string>(storageGet(LEVEL_KEY) || "1");
const query = ref("");

watch(level, (v) => storageSet(LEVEL_KEY, v));

async function load() {
  if (!auth.isAuthed) return;
  error.value = null;
  try {
    data.value = await api.getGrammar();
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Couldn't load the grammar.";
  }
}
onMounted(load);
watch(
  () => auth.isAuthed,
  (v) => v && void load(),
);

function passes(p: Overview["points"][number]): boolean {
  if (filter.value === "met" && p.met_texts === 0) return false;
  if (filter.value === "unmet" && p.met_texts > 0) return false;
  if (filter.value === "due" && !p.progress?.due) return false;
  const q = query.value.trim().toLowerCase();
  return !q || p.title.toLowerCase().includes(q) || p.forms.includes(q);
}

const searching = computed(() => query.value.trim() !== "");
const visible = computed(() =>
  (data.value?.points ?? []).filter(
    (p) => passes(p) && (searching.value || p.level === level.value),
  ),
);

const levelCounts = computed(() => {
  const out: Record<string, { all: number; met: number; due: number }> = {};
  for (const l of LEVELS) out[l] = { all: 0, met: 0, due: 0 };
  for (const p of data.value?.points ?? []) {
    const c = out[p.level];
    if (!c) continue;
    c.all += 1;
    if (p.met_texts) c.met += 1;
    if (p.progress?.due) c.due += 1;
  }
  return out;
});

const counts = computed(() => {
  const ps = data.value?.points ?? [];
  return {
    all: ps.length,
    met: ps.filter((p) => p.met_texts > 0).length,
    unmet: ps.filter((p) => p.met_texts === 0).length,
    due: ps.filter((p) => p.progress?.due).length,
  };
});

const grouped = computed(() => {
  const by = new Map<string, typeof visible.value>();
  for (const p of visible.value) by.set(p.group, [...(by.get(p.group) ?? []), p]);
  return [...by.entries()].sort(
    (a, b) => GROUP_ORDER.indexOf(a[0]) - GROUP_ORDER.indexOf(b[0]),
  );
});

const FILTERS: { id: Filter; label: string }[] = [
  { id: "all", label: "All" },
  { id: "met", label: "Met in my reading" },
  { id: "unmet", label: "Not met yet" },
  { id: "due", label: "Due" },
];
</script>

<template>
  <section class="mx-auto max-w-4xl px-5 py-10 sm:px-8 md:py-14">
    <header class="mb-6">
      <h1 class="font-display text-2xl font-medium tracking-tight text-fg">Grammar</h1>
      <p class="mt-1 max-w-2xl text-sm text-fg-muted">
        The HSK 3.0 grammar points, with the ones you met in texts you read
        to the end and your own sentences to look at and practice.
        <template v-if="data">
          {{ data.read_texts }} text{{ data.read_texts === 1 ? "" : "s" }} read so far.
        </template>
      </p>
      <p v-if="data && data.analysing > 0" class="mt-2 text-xs text-fg-subtle">
        Looking for grammar in {{ data.analysing.toLocaleString() }} more sentences of your
        reading in the background; come back later for more matches.
      </p>
    </header>

    <div v-if="!auth.isAuthed" class="rounded-lg border border-border-subtle bg-bg-elevated p-8 text-center">
      <p class="font-display italic text-fg-muted">Sign in to see the grammar of what you read.</p>
      <button
        type="button"
        class="mt-4 rounded-md bg-accent px-3 py-1.5 text-sm text-accent-fg"
        @click="authModals.openLogin()"
      >
        Sign in
      </button>
    </div>

    <p v-else-if="error" class="text-sm text-red-700 dark:text-red-300" role="alert">{{ error }}</p>
    <p v-else-if="!data" class="font-display italic text-fg-muted">Looking through your reading…</p>

    <template v-else>
      <div class="mb-4 flex flex-wrap items-center gap-2">
        <input
          v-model="query"
          type="search"
          placeholder="Search all levels (把, comparison …)"
          class="w-full max-w-xs rounded-md border border-border-subtle bg-bg px-3 py-1.5 text-sm text-fg focus:border-accent focus:outline-none"
        />
        <button
          v-for="f in FILTERS"
          :key="f.id"
          type="button"
          class="rounded-full border px-3 py-1 text-xs transition-colors"
          :class="filter === f.id ? 'border-accent bg-accent/10 text-accent' : 'border-border text-fg-muted hover:text-fg'"
          @click="filter = f.id"
        >
          {{ f.label }} · {{ counts[f.id] }}
        </button>
      </div>

      <nav v-if="!searching" class="mb-6 flex flex-wrap gap-1" aria-label="HSK level">
        <button
          v-for="l in LEVELS"
          :key="l"
          type="button"
          class="rounded-md px-3 py-1.5 text-sm transition-colors"
          :class="level === l ? 'bg-bg-sunken font-medium text-fg' : 'text-fg-muted hover:text-fg'"
          @click="level = l"
        >
          HSK {{ l }}
          <span class="ml-1 font-mono text-[10px] text-fg-subtle">
            {{ levelCounts[l].met }}/{{ levelCounts[l].all }}
          </span>
          <span
            v-if="levelCounts[l].due"
            class="ml-1 rounded-full bg-accent px-1.5 font-mono text-[10px] text-accent-fg"
          >
            {{ levelCounts[l].due }}
          </span>
        </button>
      </nav>

      <p v-if="!data.read_texts" class="mb-6 rounded-md border border-border-subtle bg-bg-elevated px-4 py-3 text-sm text-fg-muted">
        Finish a text (read to the end, or mark a library text as read) and the
        points in it show up here as met. Every point already has examples and
        sentences from the library.
      </p>

      <div v-for="[group, ps] in grouped" :key="group" class="mb-8">
        <h2 class="mb-3 font-mono text-[11px] uppercase tracking-[0.2em] text-fg-subtle">
          {{ GROUPS[group] ?? group }}
          <span class="normal-case tracking-normal">· {{ group }}</span>
        </h2>
        <ul class="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <li v-for="p in ps" :key="p.id">
            <RouterLink
              :to="`/grammar/${p.id}`"
              class="block rounded-lg border border-border bg-bg-elevated px-4 py-3 transition-shadow hover:shadow-md"
            >
              <span class="flex items-baseline justify-between gap-2">
                <span class="text-sm font-medium text-fg">{{ p.title }}</span>
                <span
                  v-if="p.progress?.due"
                  class="shrink-0 rounded-full bg-accent px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider text-accent-fg"
                >
                  due
                </span>
              </span>
              <span class="text-cn-serif mt-0.5 block text-sm text-fg-muted line-clamp-1">{{ p.forms }}</span>
              <span class="mt-2 block font-mono text-[10px] uppercase tracking-wider text-fg-subtle">
                <template v-if="searching">HSK {{ p.level }} · </template>
                <template v-if="p.met_texts">
                  met in {{ p.met_texts }} text{{ p.met_texts === 1 ? "" : "s" }} ·
                  {{ p.met_sentences }} sentence{{ p.met_sentences === 1 ? "" : "s" }}
                </template>
                <template v-else>not met yet</template>
                <template v-if="p.progress">
                  · practiced {{ p.progress.correct }}/{{ p.progress.total }}
                </template>
              </span>
            </RouterLink>
          </li>
        </ul>
      </div>
      <p v-if="!grouped.length" class="font-display italic text-fg-muted">Nothing here with this filter.</p>
    </template>
  </section>
</template>
