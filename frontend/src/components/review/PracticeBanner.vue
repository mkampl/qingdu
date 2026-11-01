<script setup lang="ts">
/** Practice-mode notice above the card: nothing is graded; End practice leaves. */
const emit = defineEmits<{
  (e: "end"): void;
}>();
</script>

<template>
  <div
    class="mb-6 flex items-start gap-3 rounded-md border border-amber-300/60 bg-amber-50/70 px-4 py-3 text-sm text-amber-800 dark:border-amber-700/50 dark:bg-amber-500/10 dark:text-amber-200"
    role="status"
  >
    <span aria-hidden="true">🎯</span>
    <div class="flex-1 leading-snug">
      <p class="font-medium">Practice mode — nothing is graded.</p>
      <p class="text-xs opacity-80">
        Grading here doesn't change your reviews: due dates, streak and
        stats stay as they are. End practice any time to return to your
        list.
      </p>
    </div>
    <button
      type="button"
      class="rounded-md border border-amber-300/60 bg-amber-50 px-3 py-1 font-mono text-[10px] uppercase tracking-wider text-amber-800 hover:bg-amber-100 dark:border-amber-700/50 dark:bg-amber-500/20 dark:text-amber-100 dark:hover:bg-amber-500/30"
      @click="emit('end')"
    >
      End practice
    </button>
  </div>
</template>
