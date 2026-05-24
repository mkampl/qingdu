<script setup lang="ts">
/**
 * Compact 7-day activity sparkline. Each day is a stacked bar — reviews
 * on the bottom, newly-marked-known on top — so a single column tells
 * you whether the day was study (reviews) or expansion (new words).
 *
 * Fetches lazily on mount; degrades to a small "no activity yet" hint.
 */
import { computed, onMounted, ref } from "vue";

import * as api from "@/api/client";
import type { WeeklyActivityDay } from "@/api/client";

const days = ref<WeeklyActivityDay[]>([]);
const loading = ref(false);

const max = computed(() => {
  let m = 0;
  for (const d of days.value) {
    const total = d.reviews + d.marked_known;
    if (total > m) m = total;
  }
  return m;
});

const hasActivity = computed(() => max.value > 0);

function dayLabel(iso: string): string {
  // Short weekday letter. Anchored to the user's locale.
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString(undefined, { weekday: "narrow" });
}

function tooltip(day: WeeklyActivityDay): string {
  const date = new Date(day.date + "T00:00:00").toLocaleDateString(undefined, {
    weekday: "long",
    month: "short",
    day: "numeric",
  });
  return `${date} — ${day.reviews} review${day.reviews === 1 ? "" : "s"}, ${day.marked_known} new known`;
}

onMounted(async () => {
  loading.value = true;
  try {
    const r = await api.getWeeklyActivity();
    days.value = r.days;
  } catch {
    /* anonymous request, leave empty */
  } finally {
    loading.value = false;
  }
});
</script>

<template>
  <section
    v-if="!loading"
    class="rounded-lg border border-border-subtle bg-bg-elevated px-4 py-3"
  >
    <header class="mb-2 flex items-baseline justify-between gap-2">
      <h2
        class="font-mono text-[10px] uppercase tracking-[0.2em] text-fg-subtle"
      >
        Last 7 days
      </h2>
      <p
        v-if="hasActivity"
        class="font-mono text-[10px] text-fg-subtle tabular-nums"
      >
        peak {{ max }}
      </p>
    </header>

    <div
      v-if="hasActivity"
      class="grid grid-cols-7 gap-1.5"
      role="img"
      aria-label="7-day activity"
    >
      <div
        v-for="day in days"
        :key="day.date"
        class="flex flex-col items-center gap-1"
        :title="tooltip(day)"
      >
        <div class="flex h-12 w-full items-end overflow-hidden rounded-sm bg-bg-sunken">
          <div class="flex w-full flex-col justify-end">
            <!-- New-known sits on top (orange/amber tone for "new learning"). -->
            <div
              v-if="day.marked_known > 0"
              class="w-full bg-amber-400 dark:bg-amber-500"
              :style="{
                height: `${(day.marked_known / max) * 48}px`,
              }"
            />
            <!-- Reviews on the bottom (accent for "habit maintenance"). -->
            <div
              v-if="day.reviews > 0"
              class="w-full bg-accent"
              :style="{
                height: `${(day.reviews / max) * 48}px`,
              }"
            />
          </div>
        </div>
        <span
          class="font-mono text-[9px] uppercase tracking-wider text-fg-subtle"
        >
          {{ dayLabel(day.date) }}
        </span>
      </div>
    </div>

    <p
      v-else
      class="font-display text-xs italic text-fg-muted"
    >
      No activity yet this week — grade a card or mark a word to start your
      streak.
    </p>
  </section>
</template>
