<script setup lang="ts">
/** The list-wide actions: learn, review, CSV and Anki export, delete. */
import Button from "@/components/ui/Button.vue";

defineProps<{
  totalWords: number;
  busy: boolean;
  /** A learn request (list or section) is in flight. */
  learning: boolean;
  /** The in-flight learn request is for the whole list. */
  learningAll: boolean;
  /** No Anki export is running. */
  ankiIdle: boolean;
}>();

const emit = defineEmits<{
  (e: "learn"): void;
  (e: "review"): void;
  (e: "csv"): void;
  (e: "anki"): void;
  (e: "delete"): void;
}>();
</script>

<template>
  <div class="flex flex-wrap items-center gap-2">
    <Button
      variant="primary"
      size="sm"
      :disabled="totalWords === 0 || learning"
      :loading="learningAll"
      title="Take every word of this list into review, with the list's own meanings"
      @click="emit('learn')"
    >
      Learn this list
    </Button>
    <Button
      variant="secondary"
      size="sm"
      :disabled="totalWords === 0"
      title="Review only the words of this list"
      @click="emit('review')"
    >
      Review this list
    </Button>
    <Button
      variant="secondary"
      size="sm"
      :disabled="totalWords === 0 || busy"
      :loading="busy && ankiIdle"
      @click="emit('csv')"
    >
      ↓ CSV
    </Button>
    <Button
      variant="secondary"
      size="sm"
      :disabled="totalWords === 0 || !ankiIdle"
      @click="emit('anki')"
    >
      ↓ Anki
    </Button>
    <Button variant="danger" size="sm" :disabled="busy" @click="emit('delete')">
      Delete list
    </Button>
  </div>
</template>
