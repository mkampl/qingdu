<script setup lang="ts">
withDefaults(
  defineProps<{ size?: "sm" | "md" | "lg"; label?: string }>(),
  { size: "md" },
);
</script>

<template>
  <span
    role="status"
    :aria-label="label ?? 'Loading'"
    class="inline-block animate-spin rounded-full border-current border-t-transparent"
    :class="{
      'size-4 border-2': size === 'sm',
      'size-6 border-2': size === 'md',
      'size-10 border-[3px]': size === 'lg',
    }"
  />
</template>
