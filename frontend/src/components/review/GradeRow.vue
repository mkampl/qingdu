<script setup lang="ts">
/**
 * The grade row, Again to Easy; each button's grade is its 1-4 key. The
 * button of a pending auto-grade carries a ring and a countdown bar. On a
 * phone the row sticks to the bottom of the screen, so a long sentence
 * above can't push it out of view.
 */
import type { ReviewGrade } from "@/api/client";
import { formatInterval } from "@/utils/review";

const props = defineProps<{
  /** Seconds until the next review after each grade ("1".."4"). */
  intervals?: Record<string, number>;
  practice: boolean;
  disabled: boolean;
  pending: ReviewGrade | null;
  delayMs: number;
}>();

const emit = defineEmits<{
  (e: "grade", g: ReviewGrade): void;
}>();

// Under each grade button: when the card comes back after that grade
// (practice grades change nothing, so it keeps the words).
const GRADE_WORDS = ["", "< 10m", "sooner", "on schedule", "later"];
function gradeCaption(g: ReviewGrade): string {
  const s = props.intervals?.[g];
  return s == null || props.practice ? GRADE_WORDS[g] : formatInterval(s);
}

const GRADE_BUTTONS: {
  grade: ReviewGrade;
  label: string;
  hover: string;
  darkHover: string;
  ring: string;
  bar: string;
  text: string;
}[] = [
  {
    grade: 1,
    label: "Again",
    hover: "hover:border-red-500 hover:bg-red-50",
    darkHover: "dark:hover:bg-red-500/10",
    ring: "ring-2 ring-red-400/60",
    bar: "bg-red-500",
    text: "text-red-700 dark:text-red-300",
  },
  {
    grade: 2,
    label: "Hard",
    hover: "hover:border-amber-500 hover:bg-amber-50",
    darkHover: "dark:hover:bg-amber-500/10",
    ring: "ring-2 ring-amber-400/60",
    bar: "bg-amber-500",
    text: "text-amber-700 dark:text-amber-300",
  },
  {
    grade: 3,
    label: "Good",
    hover: "hover:border-emerald-500 hover:bg-emerald-50",
    darkHover: "dark:hover:bg-emerald-500/10",
    ring: "ring-2 ring-emerald-400/60",
    bar: "bg-emerald-500",
    text: "text-emerald-700 dark:text-emerald-300",
  },
  {
    grade: 4,
    label: "Easy",
    hover: "hover:border-sky-500 hover:bg-sky-50",
    darkHover: "dark:hover:bg-sky-500/10",
    ring: "ring-2 ring-sky-400/60",
    bar: "bg-sky-500",
    text: "text-sky-700 dark:text-sky-300",
  },
];
</script>

<template>
  <div
    class="sticky bottom-0 z-10 -mx-3 grid grid-cols-4 gap-2 bg-bg/95 px-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] pt-2 backdrop-blur sm:static sm:mx-0 sm:bg-transparent sm:p-0 sm:backdrop-blur-none"
  >
    <button
      v-for="b in GRADE_BUTTONS"
      :key="b.grade"
      type="button"
      :disabled="disabled"
      :class="[
        'relative overflow-hidden rounded-lg border border-border bg-bg-elevated px-3 py-3 transition-colors',
        b.hover,
        'disabled:opacity-50',
        b.darkHover,
        pending === b.grade ? b.ring : '',
      ]"
      @click="emit('grade', b.grade)"
    >
      <span
        v-if="pending === b.grade"
        :style="{ animationDuration: `${delayMs}ms` }"
        :class="['qd-auto-grade-progress absolute inset-x-0 bottom-0 h-0.5', b.bar]"
      />

      <p :class="['font-display text-base font-medium', b.text]">
        {{ b.label }}
      </p>
      <p class="mt-0.5 font-mono text-[9px] uppercase tracking-wider text-fg-subtle">
        {{ gradeCaption(b.grade) }}
      </p>
    </button>
  </div>
</template>

<style scoped>
/* Countdown bar along the bottom of the pending button. The inline
 * animation-duration matches the auto-grade timeout. */

.qd-auto-grade-progress {
  transform-origin: left;
  animation: qd-auto-grade-fill 2000ms linear forwards;
}

@keyframes qd-auto-grade-fill {
  from {
    transform: scaleX(0);
  }
  to {
    transform: scaleX(1);
  }
}
</style>
