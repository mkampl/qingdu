<script setup lang="ts">
/**
 * "Pre-learn missing words": the words of the open text the user doesn't
 * know yet, most frequent first. The ones needed to make the text
 * readable are ticked; the user picks as many as they like, and the
 * chosen ones go into review with the sentence from this text and the
 * text's own meaning: a package's or glossary's, else what the LLM says
 * the word means in its sentence (with the book's translation of the
 * sentence, when the text has one). Names and other words not worth
 * learning can be ignored, which also counts them as covered.
 */
import { computed, ref, watch } from "vue";

import * as api from "@/api/client";
import type { ReadabilityResponse, TextGloss } from "@/api/client";
import type { WordInfo } from "@/api/types";
import Button from "@/components/ui/Button.vue";
import Modal from "@/components/ui/Modal.vue";
import { useAnalysisStore } from "@/stores/analysis";
import { useAuthStore } from "@/stores/auth";
import { useCapabilitiesStore } from "@/stores/capabilities";
import { useToastStore } from "@/stores/toast";
import { useUserWordsStore } from "@/stores/userWords";

const props = defineProps<{
  open: boolean;
  data: ReadabilityResponse | null;
  words: WordInfo[];
  textKey: string;
  title: string | null;
  sourceTextId: number | null;
  librarySlug: string | null;
}>();

const emit = defineEmits<{
  (e: "close"): void;
  (e: "done", value: ReadabilityResponse): void;
}>();

const toasts = useToastStore();
const analysis = useAnalysisStore();
const auth = useAuthStore();
const capabilities = useCapabilitiesStore();
const userWords = useUserWordsStore();

const selected = ref<Set<string>>(new Set());
const ignored = ref<Set<string>>(new Set());
const busy = ref(false);

const missing = computed(() =>
  (props.data?.missing ?? []).filter((m) => !ignored.value.has(m.word)),
);

// What the LLM says the missing words mean in this text (no package or
// glossary meaning of their own).
const senses = ref<Record<string, string>>({});
const sensing = ref(false);

/** The sentence a word first stands in, and the book's translation of it
 *  when the text has one. */
function contextOf(word: string): { sentence: string; translation: string | null } | null {
  const translations = analysis.result?.sentence_translations ?? {};
  for (const [zh, en] of Object.entries(translations)) {
    if (zh.includes(word) && zh.length <= 400) return { sentence: zh, translation: en || null };
  }
  let sentence = "";
  for (const w of props.words) {
    if (w.text === "\n") {
      if (sentence.includes(word)) break;
      sentence = "";
      continue;
    }
    sentence += w.text;
    if (/[。！？!?]$/.test(w.text)) {
      if (sentence.includes(word)) break;
      sentence = "";
    }
  }
  sentence = sentence.trim();
  return sentence.includes(word) ? { sentence: sentence.slice(0, 400), translation: null } : null;
}

async function loadSenses() {
  if (!auth.isAuthed || !capabilities.llmFeature("text_sense")) return;
  const items = [];
  for (const m of props.data?.missing ?? []) {
    if (fixedGlosses.value[m.word] || senses.value[m.word]) continue;
    const ctx = contextOf(m.word);
    if (ctx) items.push({ word: m.word, ...ctx });
    if (items.length >= 40) break;
  }
  if (!items.length) return;
  sensing.value = true;
  try {
    const r = await api.getTextSenses(items);
    senses.value = { ...senses.value, ...r.senses };
  } catch {
    /* the dictionary meaning stays */
  } finally {
    sensing.value = false;
  }
}

// The text's own meaning per word: a package's or glossary's, from its
// first occurrence; else the LLM's.
const textGlosses = computed(() => {
  const out: Record<string, TextGloss> = { ...fixedGlosses.value };
  const pinyin = new Map((props.data?.missing ?? []).map((m) => [m.word, m.pinyin]));
  for (const [word, meaning] of Object.entries(senses.value)) {
    if (!out[word]) {
      out[word] = { meaning, pinyin: pinyin.get(word) ?? null, source: "text", tag: null };
    }
  }
  return out;
});

const fixedGlosses = computed(() => {
  const out: Record<string, TextGloss> = {};
  for (const w of props.words) {
    if (out[w.text] || !w.meaning) continue;
    if (w.translation_source === "package") {
      out[w.text] = {
        meaning: w.meaning,
        pinyin: w.pinyin,
        source: "package",
        tag: w.package_source ?? null,
      };
    } else if (w.translation_source === "glossary") {
      out[w.text] = {
        meaning: w.meaning,
        pinyin: w.pinyin,
        source: "glossary",
        tag: w.glossary_source ?? null,
      };
    }
  }
  return out;
});

function selectFirst(n: number) {
  selected.value = new Set(missing.value.slice(0, n).map((m) => m.word));
}

watch(
  () => props.open,
  (open) => {
    if (!open) return;
    ignored.value = new Set();
    selectFirst(props.data?.to_unlock ?? 0);
    void loadSenses();
  },
);

function toggle(word: string) {
  const next = new Set(selected.value);
  if (next.has(word)) next.delete(word);
  else next.add(word);
  selected.value = next;
}

async function ignore(word: string) {
  try {
    await userWords.setState(word, "ignored");
    ignored.value = new Set(ignored.value).add(word);
    const next = new Set(selected.value);
    next.delete(word);
    selected.value = next;
  } catch {
    toasts.error("Couldn't ignore that word");
  }
}

const chosen = computed(() =>
  missing.value.filter((m) => selected.value.has(m.word)).map((m) => m.word),
);

async function addToReview() {
  if (!chosen.value.length || busy.value) return;
  busy.value = true;
  const glosses: Record<string, TextGloss> = {};
  for (const w of chosen.value) {
    const g = textGlosses.value[w];
    if (g) glosses[w] = g;
  }
  try {
    const r = await api.prelearnWords({
      tokens: props.words.map((w) => w.text),
      extra: Object.keys(fixedGlosses.value),
      words: chosen.value,
      text_key: props.textKey,
      title: props.title,
      source_text_id: props.sourceTextId,
      library_slug: props.librarySlug,
      glosses,
    });
    // The reader colours words by state; show the new ones as learning.
    if (r.added.length) {
      const next = { ...userWords.states };
      for (const w of r.added) next[w] = "learning";
      userWords.states = next;
    }
    const n = r.added.length;
    toasts.success(
      n
        ? `Added ${n} word${n === 1 ? "" : "s"} to your review.`
        : "Those words are already in your review.",
    );
    emit("done", r);
    emit("close");
  } catch (e) {
    toasts.error(e instanceof Error ? e.message : "Couldn't add the words");
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <Modal :open="open" size="lg" close-on-backdrop title="Pre-learn words" @close="emit('close')">
    <template #header>
      <div>
        <h2 class="font-display text-xl font-medium tracking-tight text-fg">
          Pre-learn words for this text
        </h2>
        <p v-if="data" class="mt-0.5 text-xs text-fg-muted">
          {{ data.missing_count }} word{{ data.missing_count === 1 ? "" : "s" }} you don't know yet,
          most frequent first.
          <template v-if="data.to_unlock">
            The first {{ data.to_unlock }} make it readable.
          </template>
        </p>
      </div>
    </template>

    <div class="space-y-3">
      <div class="flex flex-wrap gap-2 text-xs">
        <button
          v-if="data && data.to_unlock"
          type="button"
          class="rounded-full border border-accent px-2.5 py-1 text-accent hover:bg-accent/10"
          @click="selectFirst(data.to_unlock)"
        >
          Enough to read it ({{ data.to_unlock }})
        </button>
        <button
          type="button"
          class="rounded-full border border-border px-2.5 py-1 text-fg-muted hover:border-accent hover:text-accent"
          @click="selectFirst(10)"
        >
          First 10
        </button>
        <button
          type="button"
          class="rounded-full border border-border px-2.5 py-1 text-fg-muted hover:border-accent hover:text-accent"
          @click="selectFirst(missing.length)"
        >
          All ({{ missing.length }})
        </button>
        <button
          type="button"
          class="rounded-full border border-border px-2.5 py-1 text-fg-muted hover:border-accent hover:text-accent"
          @click="selectFirst(0)"
        >
          None
        </button>
      </div>

      <p v-if="sensing" class="text-xs italic text-fg-muted">
        Looking up what the words mean in this text…
      </p>
      <p v-if="!missing.length" class="py-6 text-center text-sm italic text-fg-muted">
        Nothing missing — every word of this text is known or in review.
      </p>

      <ul
        v-else
        class="divide-y divide-border-subtle overflow-hidden rounded-md border border-border-subtle"
      >
        <li
          v-for="m in missing"
          :key="m.word"
          class="flex items-start gap-3 px-3 py-2"
        >
          <input
            :id="`prelearn-${m.word}`"
            type="checkbox"
            class="mt-1.5 accent-accent"
            :checked="selected.has(m.word)"
            @change="toggle(m.word)"
          />
          <label :for="`prelearn-${m.word}`" class="min-w-0 flex-1 cursor-pointer">
            <span class="flex flex-wrap items-baseline gap-x-2">
              <span class="font-cn-serif text-xl text-fg">{{ m.word }}</span>
              <span class="text-sm text-fg-muted">
                {{ textGlosses[m.word]?.pinyin || m.pinyin }}
              </span>
              <span
                v-if="m.count > 1"
                class="font-mono text-[10px] text-fg-subtle"
                :title="`${m.count} times in this text`"
              >
                ×{{ m.count }}
              </span>
              <span
                v-if="m.hsk_level"
                class="font-mono text-[10px] uppercase tracking-wider text-fg-subtle"
              >
                HSK {{ m.hsk_level }}
              </span>
            </span>
            <span v-if="textGlosses[m.word]" class="block text-sm text-fg">
              <span
                class="mr-1 inline-block max-w-[14rem] truncate rounded-full bg-accent/15 px-1.5 py-0.5 align-middle font-mono text-[9px] uppercase tracking-wider text-accent"
                :title="textGlosses[m.word].tag || undefined"
              >
                {{ textGlosses[m.word].tag || "in this text" }}
              </span>
              {{ textGlosses[m.word].meaning }}
            </span>
            <span
              v-if="m.meaning && m.meaning !== textGlosses[m.word]?.meaning"
              :class="[
                'block',
                textGlosses[m.word] ? 'text-xs text-fg-subtle' : 'text-sm text-fg',
              ]"
            >
              <template v-if="textGlosses[m.word]">Also: </template>{{ m.meaning }}
            </span>
          </label>
          <button
            type="button"
            class="mt-1 shrink-0 font-mono text-[10px] uppercase tracking-wider text-fg-subtle hover:text-fg"
            title="Not worth learning (a name, for example) — counts as covered"
            @click="ignore(m.word)"
          >
            Ignore
          </button>
        </li>
      </ul>
      <p
        v-if="data && data.missing_count > (data.missing?.length ?? 0)"
        class="text-xs text-fg-subtle"
      >
        Showing the {{ data.missing.length }} most frequent.
      </p>
    </div>

    <template #footer>
      <p v-if="chosen.length > 20" class="mb-2 text-xs text-fg-muted">
        That's a lot of new words for one day. You can add some now and come
        back for the rest — this text remembers what you've added.
      </p>
      <div class="flex items-center justify-end gap-2">
        <Button variant="ghost" size="sm" @click="emit('close')">Cancel</Button>
        <Button
          variant="primary"
          size="sm"
          :loading="busy"
          :disabled="!chosen.length"
          @click="addToReview"
        >
          Add {{ chosen.length }} to review
        </Button>
      </div>
    </template>
  </Modal>
</template>
