<script setup lang="ts">
import { computed } from "vue";

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "sm" | "md" | "lg";

const props = withDefaults(
  defineProps<{
    variant?: Variant;
    size?: Size;
    type?: "button" | "submit" | "reset";
    disabled?: boolean;
    loading?: boolean;
    full?: boolean;
  }>(),
  { variant: "primary", size: "md", type: "button" },
);

const classes = computed(() => {
  const base =
    "inline-flex items-center justify-center gap-1.5 rounded-md font-medium " +
    "transition-colors disabled:opacity-50 disabled:cursor-not-allowed " +
    "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent";

  const variants: Record<Variant, string> = {
    primary: "bg-accent text-accent-fg hover:opacity-90",
    secondary:
      "bg-bg-elevated text-fg border border-border hover:bg-bg-sunken",
    ghost: "text-fg-muted hover:text-fg hover:bg-bg-sunken",
    danger:
      "bg-bg-elevated text-fg border border-border hover:bg-red-50 hover:text-red-700 hover:border-red-200 dark:hover:bg-red-950 dark:hover:text-red-200 dark:hover:border-red-900",
  };

  const sizes: Record<Size, string> = {
    sm: "h-8 px-3 text-sm",
    md: "h-10 px-4 text-sm",
    lg: "h-12 px-6 text-base",
  };

  return [
    base,
    variants[props.variant],
    sizes[props.size],
    props.full ? "w-full" : "",
  ].join(" ");
});
</script>

<template>
  <button
    :type="type"
    :class="classes"
    :disabled="disabled || loading"
    :aria-busy="loading || undefined"
  >
    <span
      v-if="loading"
      class="inline-block size-3.5 animate-spin rounded-full border-2 border-current border-t-transparent"
      aria-hidden="true"
    />
    <slot />
  </button>
</template>
