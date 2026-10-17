<script setup lang="ts">
/**
 * One grammar pattern: what it does, the sentences that show it (from
 * texts the user read first, then their other texts, then the library),
 * and a practice round of gap and word-order exercises built from them.
 */
import { computed, ref, watch } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";

import * as api from "@/api/client";
import type { GrammarExercise, GrammarSentence } from "@/api/client";
import Button from "@/components/ui/Button.vue";
import { useOpenLibraryText } from "@/composables/use-open-library-text";
import { useOpenSavedText } from "@/composables/use-open-saved-text";
import { useAnalysisStore } from "@/stores/analysis";
import { useCapabilitiesStore } from "@/stores/capabilities";
import { useUserWordsStore } from "@/stores/userWords";

type Detail = Awaited<ReturnType<typeof api.getGrammarPoint>>;

const route = useRoute();
const openSaved = useOpenSavedText();
const openLibrary = useOpenLibraryText();
const userWords = useUserWordsStore();
const analysis = useAnalysisStore();
const capabilities = useCapabilitiesStore();
const router = useRouter();

// --- A practice text written by the LLM -------------------------------------

const textBusy = ref(false);
const textError = ref<string | null>(null);

async function practiceText() {
  if (textBusy.value) return;
  textBusy.value = true;
  textError.value = null;
  try {
    const r = await api.getPracticeText(id.value);
    // Into the reader like a pasted text; Save keeps it.
    analysis.reset();
    analysis.inputText = `${r.title}\n${r.text}`;
    void router.push("/");
    void analysis.analyze(analysis.inputText);
  } catch (e) {
    textError.value = e instanceof Error ? e.message : "Couldn't write a practice text.";
  } finally {
    textBusy.value = false;
  }
}

const detail = ref<Detail | null>(null);
const error = ref<string | null>(null);
const id = computed(() => String(route.params.id));

async function load() {
  error.value = null;
  detail.value = null;
  practice.value = null;
  try {
    detail.value = await api.getGrammarPoint(id.value);
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Couldn't load this pattern.";
  }
}

const GROUPS = [
  { key: "read", label: "From texts you've read" },
  { key: "saved", label: "From your other texts" },
  { key: "library", label: "From the library" },
] as const;
const showAll = ref<Record<string, boolean>>({});

/** The sentence split around the pattern's span, for highlighting. */
function parts(s: GrammarSentence): [string, string, string] {
  const at = s.sentence.indexOf(s.span);
  if (at < 0) return [s.sentence, "", ""];
  return [s.sentence.slice(0, at), s.span, s.sentence.slice(at + s.span.length)];
}

function openSource(s: GrammarSentence) {
  const [kind, ref_] = s.source_key.split(":");
  if (kind === "saved") void openSaved(Number(ref_));
  else if (kind === "library") void openLibrary(ref_);
}

// --- Practice ------------------------------------------------------------------

const practice = ref<{ items: GrammarExercise[]; index: number; correct: number } | null>(null);
const practiceError = ref<string | null>(null);
const picked = ref<number | null>(null);
const built = ref<string[]>([]);
const checked = ref<boolean | null>(null);
const finished = ref<api.GrammarProgress | null>(null);

const item = computed(() => practice.value?.items[practice.value.index] ?? null);

async function startPractice() {
  practiceError.value = null;
  finished.value = null;
  try {
    const r = await api.getGrammarPractice(id.value);
    practice.value = { items: r.items, index: 0, correct: 0 };
    resetItem();
  } catch (e) {
    practiceError.value = e instanceof Error ? e.message : "Nothing to practise yet.";
  }
}

function resetItem() {
  picked.value = null;
  built.value = [];
  checked.value = null;
}

function pickChoice(i: number) {
  if (!practice.value || !item.value || item.value.type !== "cloze" || checked.value !== null) return;
  picked.value = i;
  checked.value = i === item.value.answer;
  if (checked.value) practice.value.correct += 1;
}

const remaining = computed(() => {
  if (!item.value || item.value.type !== "order") return [];
  const used = [...built.value];
  return item.value.pieces.filter((p) => {
    const at = used.indexOf(p);
    if (at >= 0) {
      used.splice(at, 1);
      return false;
    }
    return true;
  });
});

function addPiece(p: string) {
  if (checked.value !== null || !item.value || item.value.type !== "order") return;
  built.value = [...built.value, p];
  if (built.value.length === item.value.answer.length && practice.value) {
    checked.value = built.value.join("") === item.value.answer.join("");
    if (checked.value) practice.value.correct += 1;
  }
}

function undoPiece() {
  if (checked.value !== null) return;
  built.value = built.value.slice(0, -1);
}

async function next() {
  if (!practice.value) return;
  if (practice.value.index + 1 < practice.value.items.length) {
    practice.value.index += 1;
    resetItem();
    return;
  }
  const { correct, items } = practice.value;
  try {
    finished.value = await api.saveGrammarPractice(id.value, correct, items.length);
    void userWords.refreshStats(); // practice counts for the streak
    if (detail.value) detail.value = { ...detail.value, progress: finished.value };
  } catch {
    finished.value = null;
  }
  practice.value = { ...practice.value, index: items.length };
}

function dueText(iso: string | null): string {
  if (!iso) return "";
  const days = Math.round((new Date(iso).getTime() - Date.now()) / 86_400_000);
  return days <= 0 ? "today" : days === 1 ? "tomorrow" : `in ${days} days`;
}

// Last, so every ref load() touches exists already.
watch(id, load, { immediate: true });
</script>

<template>
  <section class="mx-auto max-w-3xl px-5 py-10 sm:px-8 md:py-14">
    <RouterLink to="/grammar" class="font-mono text-[10px] uppercase tracking-wider text-fg-subtle hover:text-fg">
      ← Grammar
    </RouterLink>

    <p v-if="error" class="mt-4 text-sm text-red-700 dark:text-red-300" role="alert">{{ error }}</p>
    <p v-else-if="!detail" class="mt-4 font-display italic text-fg-muted">Loading…</p>

    <template v-else>
      <header class="mt-2 mb-6">
        <p class="font-mono text-[10px] uppercase tracking-wider text-fg-subtle">
          HSK {{ detail.level }} · {{ detail.group }}
        </p>
        <h1 class="font-display text-2xl font-medium tracking-tight text-fg">{{ detail.title }}</h1>
        <p class="text-cn-serif mt-1 text-lg text-fg">{{ detail.forms }}</p>
        <p class="mt-2 font-mono text-xs text-fg-muted">{{ detail.structure }}</p>
        <p class="mt-3 text-sm leading-relaxed text-fg">{{ detail.explanation }}</p>
        <div
          v-for="x in detail.examples"
          :key="x.zh"
          class="mt-2 rounded-md bg-bg-sunken/60 px-3 py-2"
        >
          <p class="text-cn-serif text-lg text-fg">{{ x.zh }}</p>
          <p class="text-xs italic text-fg-muted">{{ x.en }}</p>
        </div>
      </header>

      <!-- Practice -->
      <div class="mb-8 rounded-lg border border-accent/40 bg-accent/5 px-4 py-4" data-practice>
        <template v-if="!practice">
          <div class="flex flex-wrap items-center justify-between gap-3">
            <p class="text-sm text-fg">
              <template v-if="detail.progress">
                Practised {{ detail.progress.correct }}/{{ detail.progress.total }} right ·
                next {{ dueText(detail.progress.due_at) }}
              </template>
              <template v-else>Fill gaps and put sentences in order, with your own sentences.</template>
            </p>
            <div class="flex flex-wrap gap-2">
              <Button
                v-if="capabilities.llmFeature('practice_text')"
                variant="ghost"
                size="sm"
                :loading="textBusy"
                title="A short text at your level that uses this point several times"
                @click="practiceText"
              >
                Practice text
              </Button>
              <Button variant="primary" size="sm" @click="startPractice">Practise</Button>
            </div>
          </div>
          <p v-if="textBusy" class="mt-2 text-xs text-fg-muted">
            Writing a text with your words… this takes a few seconds.
          </p>
          <p v-if="textError" class="mt-2 text-sm text-red-700 dark:text-red-300">{{ textError }}</p>
          <p v-if="practiceError" class="mt-2 text-sm text-fg-muted">{{ practiceError }}</p>
        </template>

        <div v-else-if="item" class="space-y-4">
          <p class="font-mono text-[10px] uppercase tracking-wider text-fg-subtle">
            {{ practice.index + 1 }} / {{ practice.items.length }} ·
            {{ item.type === "cloze" ? "Fill the gap" : "Put the pieces in order" }}
          </p>

          <template v-if="item.type === 'cloze'">
            <p class="text-cn-serif text-2xl leading-relaxed text-fg">
              {{ item.before }}<span
                class="mx-1 inline-block min-w-[2.5em] border-b-2 border-accent text-center"
                :class="checked === null ? 'text-transparent' : checked ? 'text-emerald-700 dark:text-emerald-300' : 'text-red-700 dark:text-red-300'"
              >{{ checked === null ? "＿" : item.choices[item.answer] }}</span>{{ item.after }}
            </p>
            <div class="flex flex-wrap gap-2">
              <button
                v-for="(c, i) in item.choices"
                :key="c"
                type="button"
                class="text-cn-serif rounded-md border px-4 py-2 text-lg transition-colors"
                :class="
                  checked === null
                    ? 'border-border hover:border-accent'
                    : i === item.answer
                      ? 'border-emerald-500 bg-emerald-500/10'
                      : i === picked
                        ? 'border-red-400 bg-red-500/10'
                        : 'border-border-subtle opacity-50'
                "
                @click="pickChoice(i)"
              >
                {{ c }}
              </button>
            </div>
          </template>

          <template v-else>
            <p class="text-cn-serif min-h-[2.5rem] rounded-md border border-dashed border-border px-3 py-2 text-xl text-fg">
              <span v-for="(p, i) in built" :key="i" class="mr-1">{{ p }}</span>
              <span v-if="!built.length" class="text-sm text-fg-subtle">Tap the pieces in order</span>
            </p>
            <div class="flex flex-wrap gap-2">
              <button
                v-for="(p, i) in remaining"
                :key="`${p}-${i}`"
                type="button"
                class="text-cn-serif rounded-md border border-border px-3 py-1.5 text-lg hover:border-accent"
                @click="addPiece(p)"
              >
                {{ p }}
              </button>
              <button
                v-if="built.length && checked === null"
                type="button"
                class="font-mono text-[10px] uppercase tracking-wider text-fg-subtle hover:text-fg"
                @click="undoPiece"
              >
                Undo
              </button>
            </div>
          </template>

          <div v-if="checked !== null" class="space-y-1">
            <p :class="checked ? 'text-emerald-700 dark:text-emerald-300' : 'text-red-700 dark:text-red-300'" class="text-sm">
              {{ checked ? "Right." : "Not quite:" }}
              <span class="text-cn-serif text-fg">{{ item.sentence }}</span>
            </p>
            <p v-if="item.translation" class="text-xs italic text-fg-muted">{{ item.translation }}</p>
            <p class="text-xs text-fg-subtle">from {{ item.source_title }}</p>
            <div class="flex justify-end">
              <Button variant="primary" size="sm" @click="next">
                {{ practice.index + 1 < practice.items.length ? "Next" : "Finish" }}
              </Button>
            </div>
          </div>
        </div>

        <div v-else class="flex flex-wrap items-center justify-between gap-3">
          <p class="text-sm text-fg">
            {{ practice.correct }} / {{ practice.items.length }} right.
            <template v-if="finished">Next practice {{ dueText(finished.due_at) }}.</template>
          </p>
          <Button variant="ghost" size="sm" @click="startPractice">Another round</Button>
        </div>
      </div>

      <!-- Sentences -->
      <div v-for="g in GROUPS" :key="g.key" class="mb-6">
        <template v-if="detail.sentences[g.key].length">
          <h2 class="mb-2 font-mono text-[11px] uppercase tracking-[0.2em] text-fg-subtle">
            {{ g.label }} · {{ detail.sentences[g.key].length }}
          </h2>
          <ul class="divide-y divide-border-subtle rounded-md border border-border-subtle">
            <li
              v-for="s in showAll[g.key] ? detail.sentences[g.key] : detail.sentences[g.key].slice(0, 8)"
              :key="s.sentence"
              class="px-3 py-2"
            >
              <p class="text-cn-serif text-lg leading-relaxed text-fg">
                {{ parts(s)[0] }}<mark class="rounded bg-accent/20 px-0.5 text-fg">{{ parts(s)[1] }}</mark>{{ parts(s)[2] }}
              </p>
              <p v-if="s.translation" class="text-xs italic text-fg-muted">{{ s.translation }}</p>
              <button
                type="button"
                class="text-cn-serif text-xs text-fg-subtle hover:text-accent"
                @click="openSource(s)"
              >
                {{ s.source_title }} →
              </button>
            </li>
          </ul>
          <button
            v-if="detail.sentences[g.key].length > 8 && !showAll[g.key]"
            type="button"
            class="mt-1 font-mono text-[10px] uppercase tracking-wider text-fg-subtle hover:text-fg"
            @click="showAll = { ...showAll, [g.key]: true }"
          >
            Show all {{ detail.sentences[g.key].length }}
          </button>
        </template>
      </div>
    </template>
  </section>
</template>
