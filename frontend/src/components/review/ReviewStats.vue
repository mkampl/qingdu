<script setup lang="ts">
/**
 * Stats above the start screen: the 7-day sparkline, the counter strip and
 * the daily-target line. A focused session counts only its own words and
 * leaves out the sparkline and the daily target.
 */
import { computed } from "vue";

import WeeklySparkline from "@/components/reader/WeeklySparkline.vue";
import StatTiles from "@/components/review/StatTiles.vue";
import { useReviewStore } from "@/stores/review";

const review = useReviewStore();

const tiles = computed((): Record<string, number> => {
  const info = review.scopeInfo;
  if (review.scope) {
    return {
      "Due now": info?.due_now ?? 0,
      "Due today": info?.due_today ?? 0,
      "In review": info?.total ?? 0,
      Learned: info?.learned ?? 0,
    };
  }
  return {
    "Due now": review.stats.due_now,
    "Due today": review.stats.due_today,
    Learning: review.stats.learning,
    "Reviewed today": review.stats.reviewed_today,
  };
});
</script>

<template>
  <WeeklySparkline v-if="!review.scope" class="mb-4" />

  <StatTiles :tiles="tiles" />

  <!-- Hidden when the target is 0 (auto-enrol off in Settings). -->
  <p
    v-if="review.stats.daily_target > 0 && !review.scope"
    class="-mt-2 mb-6 font-mono text-[10px] uppercase tracking-wider text-fg-subtle"
  >
    New today:
    <span class="text-fg tabular-nums">{{ review.stats.new_today }}</span>
    / {{ review.stats.daily_target }}
    <span v-if="review.stats.new_today >= review.stats.daily_target">
      — today's batch enrolled
    </span>
  </p>
</template>
