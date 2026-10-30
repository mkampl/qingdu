<script setup lang="ts">
/**
 * Comprehension quiz for a bundled library text, or for a saved text
 * (`textId`), whose questions the LLM writes on request. All questions must
 * be answered correctly in one submission to pass — a partial pass just
 * shows which ones were wrong and lets the user retry.
 */
import { computed, ref, watch } from "vue";

import * as api from "@/api/client";
import { ApiError } from "@/api/client";
import type { LibraryProgressEntry, LibraryQuizQuestion } from "@/api/client";
import { useUserWordsStore } from "@/stores/userWords";

import Button from "@/components/ui/Button.vue";
import Modal from "@/components/ui/Modal.vue";

const props = defineProps<{
  open: boolean;
  slug: string | null;
  title: string;
  /** A saved text instead of a library one. */
  textId?: number | null;
}>();
const emit = defineEmits<{
  (e: "close"): void;
  (e: "passed", progress: LibraryProgressEntry): void;
  (e: "text-passed"): void;
}>();

const loading = ref(false);
const error = ref<string | null>(null);
const questions = ref<LibraryQuizQuestion[]>([]);
const answers = ref<(number | null)[]>([]);
const submitting = ref(false);
const results = ref<boolean[] | null>(null);
const allCorrect = ref(false);

const writing = ref(false);

const allAnswered = computed(() => answers.value.every((a) => a !== null));
const textId = computed(() => props.textId ?? null);

function show(qs: LibraryQuizQuestion[]) {
  questions.value = qs;
  answers.value = qs.map(() => null);
  results.value = null;
  allCorrect.value = false;
}

watch(
  () => [props.open, props.slug, textId.value] as const,
  async ([open, slug, id]) => {
    if (!open || (!slug && id === null)) return;
    loading.value = true;
    error.value = null;
    show([]);
    try {
      const r = id !== null ? await api.getTextQuiz(id) : await api.getLibraryQuiz(slug as string);
      show(r.questions);
    } catch (e) {
      error.value = e instanceof ApiError ? e.message : "Couldn't load the quiz.";
    } finally {
      loading.value = false;
    }
  },
  { immediate: true },
);

/** Saved texts: have the LLM write (new) questions. */
async function writeQuestions() {
  if (textId.value === null || writing.value) return;
  writing.value = true;
  error.value = null;
  try {
    show((await api.writeTextQuiz(textId.value)).questions);
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : "Couldn't write questions.";
  } finally {
    writing.value = false;
  }
}

async function submit() {
  if ((!props.slug && textId.value === null) || !allAnswered.value || submitting.value) return;
  submitting.value = true;
  error.value = null;
  try {
    const given = answers.value as number[];
    if (textId.value !== null) {
      const r = await api.submitTextQuiz(textId.value, given);
      results.value = r.results;
      allCorrect.value = r.all_correct;
      if (r.all_correct) {
        emit("text-passed");
        void useUserWordsStore().refreshStats();
      }
      return;
    }
    const r = await api.submitLibraryQuiz(props.slug as string, given);
    results.value = r.results;
    allCorrect.value = r.all_correct;
    if (r.all_correct && r.progress) {
      emit("passed", r.progress);
      // A passed quiz counts for the streak: refresh the header chip.
      void useUserWordsStore().refreshStats();
    }
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : "Couldn't submit the quiz.";
  } finally {
    submitting.value = false;
  }
}

function retry() {
  results.value = null;
  allCorrect.value = false;
}
</script>

<template>
  <Modal :open="open" size="md" close-on-backdrop @close="emit('close')">
    <template #header>
      <div class="flex items-baseline gap-3">
        <h2 class="font-display text-xl font-medium tracking-tight text-fg">
          Quiz
        </h2>
        <span
          class="truncate font-mono text-[10px] uppercase tracking-[0.18em] text-fg-subtle"
        >
          {{ title }}
        </span>
      </div>
    </template>

    <p v-if="loading" class="py-8 text-center text-sm text-fg-subtle">
      Loading…
    </p>
    <p v-else-if="writing" class="py-8 text-center font-display italic text-fg-muted">
      Writing questions about the text…
    </p>
    <div v-else-if="textId !== null && !questions.length" class="space-y-4 py-2">
      <p v-if="error" class="text-sm text-red-700 dark:text-red-300" role="alert">{{ error }}</p>
      <p class="text-sm text-fg-muted">
        A few questions in English on what the text says, to check you
        understood it. All right, and the text counts as read.
      </p>
      <Button variant="primary" size="sm" type="button" @click="writeQuestions">
        Write questions
      </Button>
    </div>
    <p v-else-if="error" class="text-sm text-red-700 dark:text-red-300" role="alert">
      {{ error }}
    </p>
    <div v-else class="space-y-5">
      <fieldset
        v-for="(q, qi) in questions"
        :key="qi"
        class="space-y-2"
        :disabled="submitting"
      >
        <legend class="flex items-start gap-2 text-sm font-medium text-fg">
          <span class="font-mono text-fg-subtle">{{ qi + 1 }}.</span>
          <span class="flex-1">{{ q.prompt }}</span>
          <span
            v-if="results"
            :class="results[qi] ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400'"
            class="shrink-0 font-mono text-[11px]"
          >
            {{ results[qi] ? "✓" : "✕" }}
          </span>
        </legend>
        <label
          v-for="(opt, oi) in q.options"
          :key="oi"
          class="flex cursor-pointer items-center gap-2 rounded-md border px-3 py-1.5 text-sm transition-colors"
          :class="
            answers[qi] === oi
              ? 'border-accent bg-accent/10 text-fg'
              : 'border-border-subtle text-fg-muted hover:border-border hover:text-fg'
          "
        >
          <input
            v-model="answers[qi]"
            type="radio"
            :name="`quiz-q-${qi}`"
            :value="oi"
            class="accent-accent"
          />
          {{ opt }}
        </label>
      </fieldset>

      <p
        v-if="results && allCorrect"
        class="rounded-md bg-emerald-500/10 px-3 py-2 text-sm font-medium text-emerald-700 dark:text-emerald-400"
      >
        All correct — {{ textId !== null ? "the text counts as read." : "marked as done." }}
      </p>
      <p
        v-else-if="results"
        class="rounded-md bg-rose-500/10 px-3 py-2 text-sm font-medium text-rose-700 dark:text-rose-400"
      >
        {{ results.filter(Boolean).length }} of {{ results.length }} correct — check the ✕
        rows above and try again.
      </p>

      <div class="flex items-center justify-end gap-2">
        <button
          v-if="textId !== null"
          type="button"
          class="mr-auto font-mono text-[10px] uppercase tracking-wider text-fg-subtle hover:text-fg"
          @click="writeQuestions"
        >
          New questions
        </button>
        <Button variant="ghost" size="sm" type="button" @click="emit('close')">
          {{ allCorrect ? "Done" : "Cancel" }}
        </Button>
        <Button
          v-if="!allCorrect"
          variant="primary"
          size="sm"
          type="button"
          :loading="submitting"
          :disabled="!allAnswered"
          @click="results ? retry() : submit()"
        >
          {{ results ? "Try again" : "Submit" }}
        </Button>
      </div>
    </div>
  </Modal>
</template>
