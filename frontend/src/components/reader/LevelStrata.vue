<script setup lang="ts">
import { computed } from "vue";

import { buildDistribution, levelNumber } from "./utils";

const props = defineProps<{
  distribution: Record<string, number>;
  totalHskWords: number;
  estimatedLevel: string | null;
}>();

const segments = computed(() =>
  buildDistribution(props.distribution, props.totalHskWords),
);

/** Position (0..1) along the bar where the estimated level marker sits.
 *  We use the cumulative right edge of segments up to and including the level. */
const markerPosition = computed(() => {
  const estNum = levelNumber(props.estimatedLevel);
  if (estNum === null) return null;
  let cumulative = 0;
  for (const seg of segments.value) {
    cumulative += seg.pct;
    if (seg.level === estNum) {
      return cumulative; // right edge of the segment matching estimated level
    }
  }
  return null;
});
</script>

<template>
  <div v-if="segments.length" class="select-none">
    <!-- The bar itself. Hairline border, no fill — just stacked segments. -->
    <div
      class="relative h-3 w-full overflow-hidden rounded-[2px] border border-border-subtle bg-bg-sunken"
    >
      <div class="flex h-full w-full">
        <div
          v-for="(seg, idx) in segments"
          :key="seg.label"
          class="relative h-full transition-[flex-basis]"
          :style="{
            flexBasis: `${seg.pct}%`,
            backgroundColor: `color-mix(in oklch, ${seg.color}, transparent 20%)`,
            boxShadow:
              idx < segments.length - 1
                ? `inset -1px 0 0 0 var(--color-bg-elevated)`
                : undefined,
          }"
          :title="`${seg.label}: ${seg.count} word${seg.count === 1 ? '' : 's'} · ${seg.pct.toFixed(1)}%`"
        />
      </div>
      <!-- "You are here" marker — a vertical hairline + small notch. -->
      <div
        v-if="markerPosition !== null"
        class="pointer-events-none absolute -top-1 bottom-0 z-10 w-px"
        :style="{
          left: `${markerPosition}%`,
          backgroundColor: 'var(--color-accent)',
        }"
        aria-hidden="true"
      >
        <span
          class="absolute -left-1 -top-0.5 size-2 rotate-45 bg-accent"
          :style="{ backgroundColor: 'var(--color-accent)' }"
        />
      </div>
    </div>

    <!-- Tick labels below: HSK1, HSK2, … We only render labels for segments
         that are wide enough to fit (≥ 8%); the rest are revealed on hover via
         the title attribute. -->
    <div class="mt-1.5 flex w-full">
      <div
        v-for="seg in segments"
        :key="`label-${seg.label}`"
        class="relative truncate text-[10px] font-medium uppercase tracking-wide text-fg-subtle"
        :style="{ flexBasis: `${seg.pct}%` }"
      >
        <span
          v-if="seg.pct >= 8"
          class="pr-1"
        >
          {{ seg.level }} · {{ seg.count }}
        </span>
      </div>
    </div>
  </div>

  <div
    v-else
    class="rounded border border-dashed border-border-subtle bg-bg-sunken px-3 py-4 text-center text-xs text-fg-subtle"
  >
    Composition appears after analysis.
  </div>
</template>
