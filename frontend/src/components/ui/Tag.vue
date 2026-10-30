<script setup lang="ts">
withDefaults(defineProps<{ tone?: "neutral" | "accent" }>(), { tone: "neutral" });
</script>

<template>
  <span
    class="inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium"
    :class="{
      'bg-bg-sunken text-fg-muted': tone === 'neutral',
      'bg-accent/15 text-accent': tone === 'accent',
    }"
  >
    <slot />
  </span>
</template>
