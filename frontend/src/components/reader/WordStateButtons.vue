<script setup lang="ts">
/** Learning / I know this / Ignore for the word in the popover; the active one is pressed. */
import type { UserWordState } from "@/api/client";

defineProps<{
  current: UserWordState | null;
}>();

const emit = defineEmits<{
  (e: "set", state: UserWordState): void;
}>();

const IDLE = "border-border bg-bg-elevated text-fg-muted hover:bg-bg-sunken hover:text-fg";
const BUTTONS: { state: UserWordState; label: string; active: string }[] = [
  {
    state: "learning",
    label: "Learning",
    active:
      "border-amber-500 bg-amber-100 text-amber-900 dark:bg-amber-500/20 dark:text-amber-200",
  },
  {
    state: "known",
    label: "I know this",
    active:
      "border-emerald-500 bg-emerald-100 text-emerald-900 dark:bg-emerald-500/20 dark:text-emerald-200",
  },
  { state: "ignored", label: "Ignore", active: "border-fg-subtle bg-bg-sunken text-fg" },
];
</script>

<template>
  <div class="mt-4 grid grid-cols-3 gap-1.5 border-t border-border-subtle pt-3">
    <button
      v-for="b in BUTTONS"
      :key="b.state"
      type="button"
      :aria-pressed="current === b.state"
      class="rounded-md border px-2 py-1.5 text-[11px] font-medium transition-colors"
      :class="current === b.state ? b.active : IDLE"
      @click="emit('set', b.state)"
    >
      {{ b.label }}
    </button>
  </div>
</template>
