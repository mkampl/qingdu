<script setup lang="ts">
/**
 * Comprehension quiz for a bundled library text. All questions must be
 * answered correctly in one submission to pass — a partial pass just shows
 * which ones were wrong and lets the user retry.
 */
import { computed, ref, watch } from "vue";

import * as api from "@/api/client";
import { ApiError } from "@/api/client";
import type { LibraryProgressEntry, LibraryQuizQuestion } from "@/api/client";

import Button from "@/components/ui/Button.vue";
import Modal from "@/components/ui/Modal.vue";

const props = defineProps<{ open: boolean; slug: string | null; title: string }>();
const emit = defineEmits<{
  (e: "close"): void;
  (e: "passed", progress: LibraryProgressEntry): void;
}>();

const loading = ref(false);
const error = ref<string | null>(null);
const questions = ref<LibraryQuizQuestion[]>([]);
const answers = ref<(number | null)[]>([]);
const submitting = ref(false);
const results = ref<boolean[] | null>(null);
const allCorrect = ref(false);

const allAnswered = computed(() => answers.value.every((a) => a !== null));

watch(
  () => [props.open, props.slug],
  async ([open, slug]) => {
    if (!open || !slug) return;
    loading.value = true;
    error.value = null;
    results.value = null;
    allCorrect.value = false;
    try {
      const r = await api.getLibraryQuiz(slug as string);
      questions.value = r.questions;
      answers.value = r.questions.map(() => null);
    } catch (e) {
      error.value = e instanceof ApiError ? e.message : "Couldn't load the quiz.";
    } finally {
      loading.value = false;
    }
  },
  { immediate: true },
);

async function submit() {
  if (!props.slug || !allAnswered.value || submitting.value) return;
  submitting.value = true;
  error.value = null;
  try {
    const r = await api.submitLibraryQuiz(
      props.slug,
      answers.value as number[],
    );
    results.value = r.results;
    allCorrect.value = r.all_correct;
    if (r.all_correct && r.progress) {
      emit("passed", r.progress);
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
        All correct — marked as done.
      </p>
      <p
        v-else-if="results"
        class="rounded-md bg-rose-500/10 px-3 py-2 text-sm font-medium text-rose-700 dark:text-rose-400"
      >
        {{ results.filter(Boolean).length }} of {{ results.length }} correct — check the ✕
        rows above and try again.
      </p>

      <div class="flex items-center justify-end gap-2">
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
