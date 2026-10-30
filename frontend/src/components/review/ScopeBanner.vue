<script setup lang="ts">
/**
 * Banner over a review session focused on one text's or vocab list's
 * words: what it is, its due and word counts, a way back to the text
 * and a way out to all reviews.
 */
import type { ReviewScope, ReviewScopeInfo } from "@/api/client";

defineProps<{
  scope: ReviewScope;
  info: ReviewScopeInfo | null;
  /** Whether the text can be opened again (saved or library text). */
  canGoBack: boolean;
}>();

const emit = defineEmits<{
  (e: "back"): void;
  (e: "clear"): void;
}>();
</script>

<template>
  <div
    class="mb-4 flex flex-wrap items-center justify-between gap-2 rounded-lg border border-accent/40 bg-accent/5 px-4 py-2.5"
  >
    <p class="text-sm text-fg">
      <span class="font-mono text-[10px] uppercase tracking-wider text-accent">
        {{ scope.listId !== undefined ? "List" : "Text" }}
      </span>
      <span class="ml-2 font-medium">{{ info?.title || "Focused review" }}</span>
      <span v-if="info" class="ml-2 text-xs text-fg-muted">
        {{ info.due }} due · {{ info.total }} words
      </span>
    </p>
    <span class="flex items-center gap-4">
      <button
        v-if="canGoBack"
        type="button"
        class="font-mono text-[10px] uppercase tracking-wider text-accent hover:text-fg"
        @click="emit('back')"
      >
        ← Back to text
      </button>
      <button
        type="button"
        class="font-mono text-[10px] uppercase tracking-wider text-fg-subtle hover:text-fg"
        @click="emit('clear')"
      >
        All reviews
      </button>
    </span>
  </div>
</template>
