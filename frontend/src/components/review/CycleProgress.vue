<script setup lang="ts">
import { computed } from "vue";

import type { ReviewMode } from "@/api/client";
import { CYCLE_ORDER } from "@/stores/review";

interface Props {
  completed: ReviewMode[];
  current: ReviewMode;
  /** When true (the card has no sample sentence) the cloze step is
   *  displayed as skipped — greyed out, not counted toward the bar. */
  hasSampleSentence?: boolean;
}

const props = withDefaults(defineProps<Props>(), {
  hasSampleSentence: true,
});

const LABELS: Record<ReviewMode, string> = {
  recognition: "Recognition",
  cloze: "Cloze",
  dictation: "Dictation",
  writing: "Writing",
};

interface Stop {
  mode: ReviewMode;
  label: string;
  state: "done" | "active" | "pending" | "skipped";
}

const stops = computed<Stop[]>(() =>
  CYCLE_ORDER.map((mode) => {
    if (mode === "cloze" && !props.hasSampleSentence) {
      return { mode, label: LABELS[mode], state: "skipped" };
    }
    if (props.completed.includes(mode)) {
      return { mode, label: LABELS[mode], state: "done" };
    }
    if (mode === props.current) {
      return { mode, label: LABELS[mode], state: "active" };
    }
    return { mode, label: LABELS[mode], state: "pending" };
  }),
);
</script>

<template>
  <!-- Four-step strip showing where in the mixed-mode cycle the current
       card sits. Each card runs Recognition → Cloze → Dictation → Writing;
       FSRS only advances once all four are graded Good or better. Cloze
       greys out when the card has no sample sentence available. -->
  <div
    class="flex w-full items-center gap-1.5"
    role="progressbar"
    :aria-valuemin="0"
    :aria-valuemax="stops.length"
    :aria-valuenow="stops.filter((s) => s.state === 'done' || s.state === 'skipped').length"
    aria-label="Review cycle progress"
  >
    <template v-for="(stop, i) in stops" :key="stop.mode">
      <!-- Step dot + label -->
      <div class="flex min-w-0 flex-1 items-center gap-1.5">
        <span
          class="inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full border text-[10px] font-mono font-medium tabular-nums transition-colors"
          :class="{
            'border-accent bg-accent text-accent-fg': stop.state === 'done',
            'border-accent bg-bg-elevated text-accent': stop.state === 'active',
            'border-border-subtle bg-bg-elevated text-fg-subtle':
              stop.state === 'pending',
            'border-dashed border-border-subtle bg-bg text-fg-subtle/50':
              stop.state === 'skipped',
          }"
        >
          <template v-if="stop.state === 'done'">
            <svg
              width="9"
              height="9"
              viewBox="0 0 9 9"
              fill="none"
              aria-hidden="true"
            >
              <path
                d="M1.5 4.5l1.8 1.8L7.5 2.4"
                stroke="currentColor"
                stroke-width="1.6"
                stroke-linecap="round"
                stroke-linejoin="round"
              />
            </svg>
          </template>
          <template v-else>{{ i + 1 }}</template>
        </span>
        <span
          class="truncate font-mono text-[10px] uppercase tracking-wider"
          :class="{
            'text-fg': stop.state === 'active',
            'text-fg-muted': stop.state === 'done',
            'text-fg-subtle': stop.state === 'pending',
            'text-fg-subtle/60 line-through': stop.state === 'skipped',
          }"
        >
          {{ stop.label }}
        </span>
      </div>
      <!-- Connector between steps -->
      <span
        v-if="i < stops.length - 1"
        class="h-px w-3 shrink-0"
        :class="
          stop.state === 'done' ? 'bg-accent' : 'bg-border-subtle'
        "
        aria-hidden="true"
      />
    </template>
  </div>
</template>
