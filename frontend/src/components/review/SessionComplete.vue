<script setup lang="ts">
/**
 * End of a review session: how many cards were graded, how many are
 * still due, and Continue / Back to text / Done.
 */
defineProps<{
  graded: number;
  due: number;
  /** Whether the focused text can be opened again. */
  canGoBack: boolean;
}>();

const emit = defineEmits<{
  (e: "continue"): void;
  (e: "back"): void;
  (e: "done"): void;
}>();
</script>

<template>
  <div class="rounded-lg border border-border-subtle bg-bg-elevated px-6 py-10 text-center">
    <p class="font-display text-xl font-medium text-fg">Session complete.</p>
    <p class="mt-2 text-sm text-fg-muted">
      {{ graded.toLocaleString() }} card{{ graded === 1 ? "" : "s" }}
      reviewed.
      <template v-if="due > 0">
        {{ due.toLocaleString() }} still due — keep going?
      </template>
      <template v-else>
        Nothing else due right now. Come back later.
      </template>
    </p>
    <div class="mt-6 flex justify-center gap-3">
      <button
        v-if="due > 0"
        type="button"
        class="rounded-full bg-accent px-4 py-1.5 text-sm font-medium text-accent-fg transition-opacity hover:opacity-90"
        @click="emit('continue')"
      >
        Continue ({{ due }})
      </button>
      <button
        v-if="canGoBack"
        type="button"
        class="rounded-full border border-accent px-4 py-1.5 text-sm text-accent transition-colors hover:bg-bg-sunken"
        @click="emit('back')"
      >
        ← Back to text
      </button>
      <button
        type="button"
        class="rounded-full border border-border px-4 py-1.5 text-sm text-fg-muted transition-colors hover:bg-bg-sunken hover:text-fg"
        @click="emit('done')"
      >
        Done
      </button>
    </div>
  </div>
</template>
