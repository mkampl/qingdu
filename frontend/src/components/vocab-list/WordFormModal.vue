<script setup lang="ts">
/**
 * Add or edit one word of a section. `target` opens the modal (null
 * closes it); the form keeps its contents while the modal animates out.
 * Pinyin comes from the server, the level is "Custom".
 */
import { ref, watch } from "vue";

import { ApiError } from "@/api/client";
import type { VocabularyWord } from "@/api/types";
import Button from "@/components/ui/Button.vue";
import Modal from "@/components/ui/Modal.vue";
import TextInput from "@/components/ui/TextInput.vue";
import type { WordForm } from "@/composables/use-vocab-list";

const props = defineProps<{
  target: { sectionName: string; word: VocabularyWord | null } | null;
  /** Saves the word; throws on failure. */
  save: (form: WordForm) => Promise<void>;
}>();

const emit = defineEmits<{
  (e: "close"): void;
}>();

const form = ref<WordForm>({
  mode: "add",
  sectionName: "",
  hanzi: "",
  meaning: "",
  oldHanzi: "",
});
const submitting = ref(false);
const error = ref<string | null>(null);

watch(
  () => props.target,
  (t) => {
    if (!t) return;
    form.value = {
      mode: t.word ? "edit" : "add",
      sectionName: t.sectionName,
      hanzi: t.word?.hanzi ?? "",
      meaning: t.word?.meaning ?? "",
      oldHanzi: t.word?.hanzi ?? "",
    };
    error.value = null;
  },
);

async function submit(e: Event) {
  e.preventDefault();
  if (submitting.value) return;
  if (!form.value.hanzi.trim()) {
    error.value = "Hanzi is required.";
    return;
  }
  submitting.value = true;
  error.value = null;
  try {
    await props.save({ ...form.value });
    emit("close");
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : "Couldn't save the word.";
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <Modal :open="target !== null" size="sm" close-on-backdrop @close="emit('close')">
    <template #header>
      <h2 class="font-display text-xl font-medium tracking-tight text-fg">
        {{ form.mode === "add" ? "Add word" : "Edit word" }}
        <span class="ml-2 font-mono text-[10px] uppercase tracking-wider text-fg-subtle">
          {{ form.sectionName }}
        </span>
      </h2>
    </template>
    <form class="space-y-4" @submit="submit">
      <TextInput v-model="form.hanzi" label="Hanzi" placeholder="你好" autofocus required />
      <TextInput v-model="form.meaning" label="Meaning" placeholder="hello" />
      <p class="font-mono text-[10px] uppercase tracking-wider text-fg-subtle">
        Pinyin is generated automatically — level is set to “Custom”.
      </p>
      <p v-if="error" class="text-sm text-red-700 dark:text-red-300" role="alert">
        {{ error }}
      </p>
      <div class="flex items-center justify-end gap-2">
        <Button variant="ghost" size="sm" type="button" @click="emit('close')">
          Cancel
        </Button>
        <Button
          variant="primary"
          size="sm"
          type="submit"
          :loading="submitting"
          :disabled="!form.hanzi.trim()"
        >
          {{ form.mode === "add" ? "Add" : "Save" }}
        </Button>
      </div>
    </form>
  </Modal>
</template>
