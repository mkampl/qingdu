<script setup lang="ts">
/** Above the card: surface and position in the queue, the way out, and a progress bar. */
import { computed } from "vue";

import type { ReviewSurface } from "@/utils/review";

const props = defineProps<{
  surface: ReviewSurface;
  cursor: number;
  total: number;
  practice: boolean;
}>();

const emit = defineEmits<{
  (e: "end"): void;
}>();

const idx = computed(() => Math.min(props.cursor + 1, props.total));
</script>

<template>
  <div class="flex items-center justify-between">
    <p class="font-mono text-[11px] uppercase tracking-[0.2em] text-fg-subtle">
      {{ surface }} · card {{ idx }} / {{ total }}
    </p>
    <button
      type="button"
      class="font-mono text-[10px] uppercase tracking-wider text-fg-subtle transition-colors hover:text-fg"
      @click="emit('end')"
    >
      {{ practice ? "End practice" : "End session" }}
    </button>
  </div>

  <div class="h-[3px] w-full overflow-hidden rounded-full bg-bg-sunken">
    <div
      class="h-full rounded-full bg-accent transition-[width] duration-200"
      :style="{
        width: total > 0 ? `${(cursor / total) * 100}%` : '0%',
      }"
    />
  </div>
</template>
