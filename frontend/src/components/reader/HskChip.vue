<script setup lang="ts">
import { computed } from "vue";

import type { HskLevel } from "@/api/types";
import { hskCssVar, levelDisplayName } from "./utils";

const props = withDefaults(
  defineProps<{
    level: HskLevel | null | undefined;
    size?: "xs" | "sm";
  }>(),
  { size: "sm" },
);

const color = computed(() => hskCssVar(props.level));
const label = computed(() => levelDisplayName(props.level));
</script>

<template>
  <span
    class="inline-flex items-center gap-1 rounded-full px-1.5 leading-none"
    :class="{
      'h-4 text-[10px] font-medium': size === 'xs',
      'h-5 text-[11px] font-medium': size === 'sm',
    }"
    :style="{
      backgroundColor: `color-mix(in oklch, ${color}, transparent 75%)`,
      color: 'var(--color-fg)',
      boxShadow: `inset 0 0 0 1px color-mix(in oklch, ${color}, transparent 50%)`,
    }"
  >
    <span
      class="inline-block size-1.5 rounded-full"
      :style="{ backgroundColor: color }"
      aria-hidden="true"
    />
    {{ label }}
  </span>
</template>
