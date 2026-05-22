<script setup lang="ts">
withDefaults(
  defineProps<{
    removable?: boolean;
    tone?: "neutral" | "accent";
  }>(),
  { tone: "neutral" },
);
defineEmits<{ (e: "remove"): void }>();
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
    <button
      v-if="removable"
      type="button"
      class="ml-0.5 text-fg-subtle hover:text-fg"
      aria-label="Remove tag"
      @click="$emit('remove')"
    >
      <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
        <path
          d="M2.5 2.5l5 5M7.5 2.5l-5 5"
          stroke="currentColor"
          stroke-width="1.5"
          stroke-linecap="round"
        />
      </svg>
    </button>
  </span>
</template>
