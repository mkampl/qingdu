<script setup lang="ts">
/**
 * Review errors: queue load, grade save, or an empty queue. A failed grade
 * keeps the card on screen; Retry re-sends the same grade.
 */
import { useReviewStore } from "@/stores/review";

const review = useReviewStore();
</script>

<template>
  <div
    :class="[
      'mb-6 flex items-start gap-3 rounded-md border px-4 py-3 text-sm',
      review.errorKind === 'empty'
        ? 'border-border-subtle bg-bg-elevated text-fg-muted'
        : 'border-red-300/60 bg-red-50/70 text-red-800 dark:border-red-800/50 dark:bg-red-500/10 dark:text-red-200',
    ]"
    :role="review.errorKind === 'empty' ? 'status' : 'alert'"
  >
    <p class="flex-1 leading-snug">
      <span v-if="review.errorKind === 'grade'" class="font-medium">
        Couldn't save that grade.
      </span>
      <span v-else-if="review.errorKind === 'queue'" class="font-medium">
        Couldn't load your review queue.
      </span>
      {{ review.error }}
    </p>
    <button
      v-if="review.errorKind === 'grade' || review.errorKind === 'queue'"
      type="button"
      class="shrink-0 rounded-md border border-current/30 px-3 py-1 font-mono text-[10px] uppercase tracking-wider transition-opacity hover:opacity-80 disabled:opacity-50"
      :disabled="review.grading || review.loading"
      @click="review.retry()"
    >
      Retry
    </button>
    <button
      type="button"
      class="shrink-0 px-1 font-mono text-[10px] uppercase tracking-wider opacity-70 transition-opacity hover:opacity-100"
      aria-label="Dismiss"
      @click="review.clearError()"
    >
      ✕
    </button>
  </div>
</template>
