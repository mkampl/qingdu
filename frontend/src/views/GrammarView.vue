<script setup lang="ts">
/**
 * The grammar section: every pattern by HSK level, how often the user met
 * it in texts they read to the end, and whether it is due for practice.
 */
import { computed, onMounted, ref, watch } from "vue";
import { RouterLink } from "vue-router";

import * as api from "@/api/client";
import { useAuthStore } from "@/stores/auth";
import { useAuthModalsStore } from "@/stores/auth-modals";

type Overview = Awaited<ReturnType<typeof api.getGrammar>>;
type Filter = "all" | "met" | "unmet" | "due";

const auth = useAuthStore();
const authModals = useAuthModalsStore();
const data = ref<Overview | null>(null);
const error = ref<string | null>(null);
const filter = ref<Filter>("all");

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
watch(() => auth.isAuthed, (v) => v && void load());

const counts = computed(() => {
  const ps = data.value?.patterns ?? [];
  return {
    all: ps.length,
    met: ps.filter((p) => p.met_texts > 0).length,
    unmet: ps.filter((p) => p.met_texts === 0).length,
    due: ps.filter((p) => p.progress?.due).length,
  };
});

const levels = computed(() => {
  const ps = (data.value?.patterns ?? []).filter((p) => {
    if (filter.value === "met") return p.met_texts > 0;
    if (filter.value === "unmet") return p.met_texts === 0;
    if (filter.value === "due") return !!p.progress?.due;
    return true;
  });
  const by = new Map<number, typeof ps>();
  for (const p of ps) by.set(p.hsk_level, [...(by.get(p.hsk_level) ?? []), p]);
  return [...by.entries()].sort((a, b) => a[0] - b[0]);
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
        The patterns you have met in texts you read to the end, with your own
        sentences to look at and practise.
        <template v-if="data">
          {{ data.read_texts }} text{{ data.read_texts === 1 ? "" : "s" }} read so far.
        </template>
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
      <div class="mb-6 flex flex-wrap gap-2">
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

      <p v-if="!data.read_texts" class="mb-6 rounded-md border border-border-subtle bg-bg-elevated px-4 py-3 text-sm text-fg-muted">
        Finish a text (read to the end, or mark a library text as read) and the
        patterns in it show up here as met. You can already open any pattern:
        it shows sentences from your other texts and the library.
      </p>

      <div v-for="[level, ps] in levels" :key="level" class="mb-8">
        <h2 class="mb-3 font-mono text-[11px] uppercase tracking-[0.2em] text-fg-subtle">
          HSK {{ level }}
        </h2>
        <ul class="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <li v-for="p in ps" :key="p.id">
            <RouterLink
              :to="`/grammar/${p.id}`"
              class="block rounded-lg border border-border bg-bg-elevated px-4 py-3 transition-shadow hover:shadow-md"
            >
              <span class="flex items-baseline justify-between gap-2">
                <span class="text-cn-serif text-lg text-fg">{{ p.title }}</span>
                <span
                  v-if="p.progress?.due"
                  class="rounded-full bg-accent px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider text-accent-fg"
                >
                  due
                </span>
              </span>
              <span class="block text-xs text-fg-muted">{{ p.pinyin }}</span>
              <span class="mt-1 block text-sm text-fg-muted line-clamp-2">{{ p.explanation }}</span>
              <span class="mt-2 block font-mono text-[10px] uppercase tracking-wider text-fg-subtle">
                <template v-if="p.met_texts">
                  met in {{ p.met_texts }} text{{ p.met_texts === 1 ? "" : "s" }} ·
                  {{ p.met_sentences }} sentence{{ p.met_sentences === 1 ? "" : "s" }}
                </template>
                <template v-else>not met yet</template>
                <template v-if="p.progress">
                  · practised {{ p.progress.correct }}/{{ p.progress.total }}
                </template>
              </span>
            </RouterLink>
          </li>
        </ul>
      </div>
      <p v-if="!levels.length" class="font-display italic text-fg-muted">Nothing here with this filter.</p>
    </template>
  </section>
</template>
