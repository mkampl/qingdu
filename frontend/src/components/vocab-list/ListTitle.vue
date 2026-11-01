<script setup lang="ts">
/**
 * The list's heading: the name (click to rename inline), word and section
 * counts, and the "Offer as glossary" toggle.
 */
import { ref } from "vue";

import type { VocabularyListSummary } from "@/api/types";
import { createEditGate } from "@/utils/vocab-lists";

const props = defineProps<{
  list: VocabularyListSummary;
  counts: { sections: number; words: number };
  busy: boolean;
  /** Saves a new, changed name; the input stays open until it settles. */
  rename: (name: string) => Promise<void>;
}>();

const emit = defineEmits<{
  (e: "toggle-glossary"): void;
}>();

const renaming = ref(false);
const draft = ref("");
const gate = createEditGate();

function begin() {
  draft.value = props.list.name;
  renaming.value = true;
  gate.begin();
}

function cancel() {
  gate.take();
  renaming.value = false;
}

async function commit() {
  if (!gate.take()) return;
  const name = draft.value.trim();
  if (!name || name === props.list.name) {
    renaming.value = false;
    return;
  }
  try {
    await props.rename(name);
  } finally {
    renaming.value = false;
  }
}
</script>

<template>
  <div class="min-w-0 flex-1">
    <div class="mb-2 flex items-baseline gap-3">
      <span class="font-mono text-[11px] uppercase tracking-[0.22em] text-fg-subtle">
        Vocab list
      </span>
      <span class="h-px w-12 bg-border-subtle" aria-hidden="true" />
    </div>
    <h1 class="text-cn-serif text-3xl font-medium tracking-tight text-fg sm:text-4xl">
      <template v-if="!renaming">
        <button
          type="button"
          class="text-left hover:text-accent"
          :title="'Click to rename'"
          @click="begin"
        >
          {{ list.name }}
        </button>
      </template>
      <input
        v-else
        v-model="draft"
        aria-label="List name"
        type="text"
        class="text-cn-serif w-full max-w-xl rounded-md border border-accent bg-bg-elevated px-2 py-0.5 text-3xl font-medium text-fg focus:outline-none sm:text-4xl"
        autofocus
        @blur="commit"
        @keydown.enter.prevent="commit"
        @keydown.escape.prevent="cancel"
      />
    </h1>
    <p class="mt-1 font-mono text-[11px] uppercase tracking-wider text-fg-subtle">
      {{ counts.words }} {{ counts.words === 1 ? "word" : "words" }}
      ·
      {{ counts.sections }}
      {{ counts.sections === 1 ? "section" : "sections" }}
      <span
        v-if="list.apply_as_glossary"
        class="ml-2 inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] tracking-wider"
        :style="{
          backgroundColor: 'color-mix(in oklch, var(--color-glossary), transparent 80%)',
          color: 'var(--color-glossary)',
        }"
      >
        · Glossary
      </span>
    </p>

    <!-- Glossary toggle — surfaces the apply_as_glossary flag. -->
    <label
      class="mt-3 flex cursor-pointer items-start gap-3 rounded-md border border-border-subtle bg-bg-elevated px-3 py-2 transition-colors hover:bg-bg-sunken"
      :class="{
        'border-[color:var(--color-glossary)]': list.apply_as_glossary,
      }"
    >
      <input
        type="checkbox"
        :checked="list.apply_as_glossary"
        :disabled="busy"
        class="mt-1 accent-accent"
        @change="emit('toggle-glossary')"
      />
      <span class="min-w-0 flex-1">
        <span class="block font-display text-sm font-medium text-fg">
          Offer as glossary
        </span>
        <!-- Short hint on mobile; full explanation only shows
             above sm so the row doesn't dominate a phone column. -->
        <span class="block text-xs text-fg-muted leading-relaxed">
          <span class="sm:hidden">Pick it per text in the reader's Glossaries.</span>
          <span class="hidden sm:inline">
            Lets you pick this list for a text in the reader's
            <em>Glossaries</em>; for that text its meanings replace the
            dictionary's, and translations keep its terms. Useful for
            specialised texts (Daoist, Buddhist, business jargon); other
            texts are not touched.
          </span>
        </span>
      </span>
    </label>
  </div>
</template>
