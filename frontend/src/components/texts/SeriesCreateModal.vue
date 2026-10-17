<script setup lang="ts">
/** Start a topic series: topic, level, new words per text, length. */
import { ref, watch } from "vue";

import type { SeriesLength } from "@/api/client";
import Button from "@/components/ui/Button.vue";
import Modal from "@/components/ui/Modal.vue";
import TextInput from "@/components/ui/TextInput.vue";

const props = defineProps<{ open: boolean; busy?: boolean; defaultLevel?: number }>();
const emit = defineEmits<{
  (e: "close"): void;
  (e: "create", value: { topic: string; level: number; new_words: number; length: SeriesLength }): void;
}>();

const topic = ref("");
const level = ref(3);
const newWords = ref(10);
const length = ref<SeriesLength>("medium");

watch(
  () => props.open,
  (open) => {
    if (open) {
      topic.value = "";
      level.value = props.defaultLevel ?? 3;
      newWords.value = 10;
      length.value = "medium";
    }
  },
);

function submit() {
  const t = topic.value.trim();
  if (t) emit("create", { topic: t, level: level.value, new_words: newWords.value, length: length.value });
}
</script>

<template>
  <Modal :open="open" title="New topic series" size="md" close-on-backdrop @close="emit('close')">
    <form class="space-y-4" @submit.prevent="submit">
      <p class="text-sm text-fg-muted">
        Texts on one topic, written one after another for your words: each
        builds on the last, uses its new words again and brings new ones.
      </p>
      <TextInput v-model="topic" label="Topic" placeholder="Cooking, a trip to Xi'an, Daoist breathing…" autofocus />
      <label class="block text-sm text-fg">
        Level
        <select
          v-model.number="level"
          class="mt-1 block rounded-md border border-border-subtle bg-bg px-2 py-1.5 text-sm"
        >
          <option v-for="l in 7" :key="l" :value="l">HSK {{ l === 7 ? "7–9" : l }}</option>
        </select>
      </label>
      <label class="block text-sm text-fg">
        New words per text: <span class="font-medium">{{ newWords }}</span>
        <input v-model.number="newWords" type="range" min="5" max="50" step="1" class="mt-1 block w-full accent-accent" />
        <span v-if="newWords >= 20" class="mt-1 block text-xs text-fg-muted">
          That many new words make a text hard to read cold. Use “Pre-learn
          missing words” before reading, and they come back in the next texts.
        </span>
      </label>
      <fieldset class="text-sm text-fg">
        <legend class="mb-1">Length</legend>
        <div class="flex gap-2">
          <button
            v-for="[k, label] in [['short', 'Short (~300)'], ['medium', 'Medium (~600)'], ['long', 'Long (~900)']]"
            :key="k"
            type="button"
            class="rounded-full border px-3 py-1 text-xs"
            :class="length === k ? 'border-accent bg-accent/10 text-accent' : 'border-border text-fg-muted'"
            @click="length = k as SeriesLength"
          >
            {{ label }}
          </button>
        </div>
      </fieldset>
    </form>
    <template #footer>
      <div class="flex justify-end gap-2">
        <Button variant="ghost" size="sm" @click="emit('close')">Cancel</Button>
        <Button variant="primary" size="sm" :loading="busy" :disabled="!topic.trim()" @click="submit">
          Write the first text
        </Button>
      </div>
    </template>
  </Modal>
</template>
