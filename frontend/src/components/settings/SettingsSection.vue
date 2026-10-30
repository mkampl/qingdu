<script setup lang="ts">
// One collapsible Settings section. Native <details> handles keyboard and a11y.
defineProps<{ title: string; open?: boolean }>();
</script>

<template>
  <details class="group rounded-md" :open="open">
    <summary class="flex cursor-pointer list-none items-center justify-between rounded-md border border-border-subtle bg-bg-elevated px-3 py-2 hover:bg-bg-sunken">
      <span class="font-mono text-[11px] uppercase tracking-[0.2em] text-fg-subtle">{{ title }}</span>
      <svg class="size-3 text-fg-subtle transition-transform group-open:rotate-90" viewBox="0 0 12 12" fill="none"><path d="M4 2l4 4-4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
    </summary>
    <div class="mt-4 space-y-7 pl-1">
      <slot />
    </div>
  </details>
</template>
