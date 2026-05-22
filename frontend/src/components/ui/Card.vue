<script setup lang="ts">
withDefaults(
  defineProps<{ padding?: "none" | "sm" | "md" | "lg"; as?: string }>(),
  { padding: "md", as: "div" },
);
</script>

<template>
  <component
    :is="as"
    class="rounded-lg border border-border bg-bg-elevated"
    :class="{
      'p-0': padding === 'none',
      'p-3': padding === 'sm',
      'p-5': padding === 'md',
      'p-8': padding === 'lg',
    }"
  >
    <slot />
  </component>
</template>
