<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";

const props = defineProps<{
  /** Length in characters of the text being analysed. Drives the time estimate. */
  textLength: number;
}>();

/**
 * Estimated analyse time, in seconds. Calibrated against typical Wikipedia-
 * imported articles after the concurrent-lookup speedup: roughly 50 chars/sec
 * for short cached texts, slower for long ones with many novel terms. We
 * don't need to be precise — the goal is "looks like progress, not a hang".
 */
const estimatedSeconds = computed(() => {
  const len = Math.max(props.textLength, 1);
  // Floor: 1.5s for anything > 0 chars (rough cold-start overhead).
  // Slope: ~1s per 250 chars after that.
  return Math.max(1.5, 1.5 + len / 250);
});

const elapsed = ref(0);
let timer: ReturnType<typeof setInterval> | null = null;
const startedAt = ref<number | null>(null);

function reset() {
  elapsed.value = 0;
  startedAt.value = performance.now();
}

watch(
  () => props.textLength,
  () => reset(),
  { immediate: true },
);

timer = setInterval(() => {
  if (startedAt.value === null) return;
  elapsed.value = (performance.now() - startedAt.value) / 1000;
}, 80);

onBeforeUnmount(() => {
  if (timer) clearInterval(timer);
});

/**
 * Bar fills smoothly to ~90% over the estimated duration, then creeps the
 * remaining 10% slowly so we never reach 100% before the actual response
 * arrives (avoids the "stuck at 100% for 5 seconds" frustration).
 */
const fillPct = computed(() => {
  const est = estimatedSeconds.value;
  const t = elapsed.value;
  if (t < est * 0.9) {
    // Linear up to 90% across the estimated duration.
    return Math.min(90, (t / est) * 100);
  }
  // Beyond 0.9 * est, asymptote to 95% — the response is "late" but we
  // still want forward motion.
  const overshoot = t - est * 0.9;
  return Math.min(95, 90 + Math.log10(1 + overshoot) * 4);
});

const elapsedDisplay = computed(() => {
  if (elapsed.value < 10) return `${elapsed.value.toFixed(1)}s`;
  return `${Math.round(elapsed.value)}s`;
});
</script>

<template>
  <div
    class="mt-4 rounded-lg border border-border-subtle bg-bg-elevated px-5 py-5"
    role="status"
    aria-live="polite"
  >
    <div class="mb-3 flex items-baseline justify-between gap-3">
      <p class="font-display text-base italic text-fg">
        Analyzing {{ textLength.toLocaleString() }} characters…
      </p>
      <span
        class="font-mono text-[10px] uppercase tracking-wider text-fg-subtle tabular-nums"
      >
        {{ elapsedDisplay }}
      </span>
    </div>

    <!-- Time-estimated progress bar. The estimate is rough; the bar
         deliberately never hits 100% before the API returns, to avoid the
         "stuck" failure mode of fake progress bars. -->
    <div
      class="h-[3px] w-full overflow-hidden rounded-full bg-bg-sunken"
      :aria-valuenow="Math.round(fillPct)"
      aria-valuemin="0"
      aria-valuemax="100"
      role="progressbar"
    >
      <div
        class="h-full rounded-full bg-accent transition-[width] duration-150 ease-out"
        :style="{ width: `${fillPct}%` }"
      />
    </div>

    <p class="mt-3 text-xs leading-relaxed text-fg-muted">
      Long articles take longer because every word that isn't already in HSK
      gets a fresh translation lookup. After the first analysis those words
      are cached, so re-analysing this text will be near-instant.
    </p>
  </div>
</template>
