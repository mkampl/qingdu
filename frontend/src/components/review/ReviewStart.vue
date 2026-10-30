<script setup lang="ts">
/**
 * Review start screen. Mixed mode is the default button; the four single
 * modes sit behind an Advanced disclosure, which stays open while single
 * mode is the user's choice. Below: tone practice and why nothing is due.
 */
import type { ReviewMode } from "@/api/client";

defineProps<{
  /** Cards Start would serve (the review window's or the focused scope's). */
  dueCount: number;
  /** A session focused on one text or list: no single modes, no tone practice. */
  scoped: boolean;
  singleMode: boolean;
  inRotation: number;
  /** The Advanced disclosure's open state, kept by the view across sessions. */
  advancedOpen: boolean;
}>();

const emit = defineEmits<{
  (e: "start-mixed"): void;
  (e: "start-single", mode: ReviewMode): void;
  (e: "switch-to-mixed"): void;
  (e: "update:advancedOpen", open: boolean): void;
}>();

const modes: { id: ReviewMode; label: string; hint: string }[] = [
  {
    id: "recognition",
    label: "Recognition",
    hint: "See the character, recall the meaning",
  },
  {
    id: "dictation",
    label: "Dictation",
    hint: "Listen, type what you hear",
  },
  {
    id: "writing",
    label: "Writing",
    hint: "Draw the character stroke by stroke",
  },
  {
    id: "cloze",
    label: "Cloze",
    hint: "Fill the blank in a real sentence from your saved texts",
  },
];
</script>

<template>
  <div class="space-y-4">
    <p class="font-mono text-[11px] uppercase tracking-[0.2em] text-fg-subtle">
      {{ singleMode ? "Pick a mode to begin" : "Ready to review" }}
    </p>

    <!-- Mixed-mode Start. -->
    <button
      v-if="!singleMode"
      type="button"
      :disabled="dueCount === 0"
      class="group flex w-full items-center justify-between rounded-lg border border-accent/40 bg-accent/5 px-5 py-3.5 text-left transition-colors hover:bg-accent/10 disabled:cursor-not-allowed disabled:opacity-50"
      @click="emit('start-mixed')"
    >
      <span class="font-display text-lg font-medium text-fg">
        <template v-if="scoped">
          Start these {{ dueCount }}
        </template>
        <template v-else>Start review</template>
      </span>
      <span class="font-mono text-[10px] uppercase tracking-wider text-fg-muted group-hover:text-fg">
        →
      </span>
    </button>

    <!-- Advanced disclosure — single-mode picks. Open while single mode
         is the user's choice, so they can continue or switch back. -->
    <details
      v-if="!scoped"
      :open="singleMode || advancedOpen"
      class="group rounded-lg border border-border-subtle bg-bg-elevated"
      @toggle="emit('update:advancedOpen', ($event.target as HTMLDetailsElement).open)"
    >
      <summary class="flex cursor-pointer items-center justify-between px-4 py-2.5 font-mono text-[10px] uppercase tracking-wider text-fg-muted hover:text-fg">
        {{ singleMode ? "Single-mode picker" : "Advanced — drill one modality" }}
        <span class="text-fg-subtle">⌃</span>
      </summary>
      <div class="border-t border-border-subtle px-4 py-3">
        <button
          v-if="singleMode"
          type="button"
          class="mb-3 w-full rounded-md border border-accent/40 bg-accent/5 px-3 py-2 text-left text-xs font-medium text-accent transition-colors hover:bg-accent/10"
          @click="emit('switch-to-mixed')"
        >
          ← Use Mixed mode (recommended)
        </button>
        <div class="grid gap-2 sm:grid-cols-2 sm:gap-3">
          <button
            v-for="m in modes"
            :key="m.id"
            type="button"
            :disabled="dueCount === 0"
            class="rounded-md border border-border-subtle bg-bg px-3 py-2.5 text-left transition-colors hover:border-accent hover:bg-bg-sunken disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:border-border-subtle disabled:hover:bg-bg"
            @click="emit('start-single', m.id)"
          >
            <span class="block font-display text-sm font-medium text-fg">
              {{ m.label }}
            </span>
            <span class="block text-xs text-fg-muted">{{ m.hint }}</span>
          </button>
        </div>
      </div>
    </details>

    <!-- Tone practice: hear a word, pick its tones (no grading). -->
    <RouterLink
      v-if="!scoped"
      to="/tones"
      class="flex items-center justify-between rounded-lg border border-border-subtle bg-bg-elevated px-4 py-2.5 transition-colors hover:border-accent"
    >
      <span>
        <span class="block font-display text-sm font-medium text-fg">Tone practice</span>
        <span class="block text-xs text-fg-muted">Hear a word, pick its tones (mǎi or mài?)</span>
      </span>
      <span class="font-mono text-[10px] uppercase tracking-wider text-fg-muted">→</span>
    </RouterLink>

    <div
      v-if="dueCount === 0 && inRotation > 0"
      class="mt-2 rounded-lg border border-border-subtle bg-bg-elevated px-5 py-4 text-center text-sm text-fg-muted"
    >
      Nothing's due right now — come back later. Your
      {{ inRotation.toLocaleString() }} Learning and Known
      words come back on their own schedule.
    </div>
    <div
      v-else-if="inRotation === 0"
      class="mt-2 rounded-lg border border-border-subtle bg-bg-elevated px-5 py-4 text-center text-sm text-fg-muted"
    >
      Nothing to review yet. Click any word in the reader and choose
      "Learning" (or "Known") from the popover — both join your review
      rotation.
    </div>
  </div>
</template>
