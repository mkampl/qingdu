<script setup lang="ts">
/** The review counter strip: one tile per label → count; smaller numbers on mobile. */
defineProps<{
  tiles: Record<string, number>;
}>();
</script>

<template>
  <div class="mb-6 grid grid-cols-2 gap-2 sm:grid-cols-4 sm:gap-3">
    <div
      v-for="(stat, key) in tiles"
      :key="key"
      class="rounded-lg border border-border-subtle bg-bg-elevated px-3 py-2 sm:px-4 sm:py-3"
    >
      <p class="font-mono text-[10px] uppercase tracking-wider text-fg-subtle">
        {{ key }}
      </p>
      <p class="mt-0.5 font-display text-xl tabular-nums text-fg sm:mt-1 sm:text-2xl">
        {{ stat.toLocaleString() }}
      </p>
    </div>
  </div>
</template>
