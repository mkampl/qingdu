<script setup lang="ts">
import { useToastStore } from "@/stores/toast";

const toasts = useToastStore();
</script>

<template>
  <Teleport to="body">
    <!-- top/right offsets compose the visual gutter with the safe-area
         inset so toasts can't hide under Android's status bar (top) or
         the right-edge gesture inset in landscape. env() = 0 in plain
         browsers, so this stays a 1rem gutter on desktop. -->
    <div
      class="toaster-root pointer-events-none fixed z-[60] flex w-full max-w-sm flex-col gap-2"
      aria-live="polite"
    >
      <TransitionGroup
        enter-active-class="transition duration-200 ease-out"
        enter-from-class="translate-y-2 opacity-0"
        enter-to-class="translate-y-0 opacity-100"
        leave-active-class="transition duration-150 ease-in"
        leave-from-class="opacity-100"
        leave-to-class="opacity-0"
      >
        <div
          v-for="toast in toasts.toasts"
          :key="toast.id"
          role="status"
          class="pointer-events-auto flex items-start gap-3 rounded-md border bg-bg-elevated px-4 py-3 shadow-lg"
          :class="{
            'border-border': toast.kind === 'info',
            'border-emerald-300 dark:border-emerald-800':
              toast.kind === 'success',
            'border-red-300 dark:border-red-800': toast.kind === 'error',
          }"
        >
          <span
            class="mt-0.5 inline-flex size-5 shrink-0 items-center justify-center rounded-full text-xs font-bold"
            :class="{
              'bg-bg-sunken text-fg-muted': toast.kind === 'info',
              'bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300':
                toast.kind === 'success',
              'bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300':
                toast.kind === 'error',
            }"
            aria-hidden="true"
          >
            {{
              toast.kind === "success"
                ? "✓"
                : toast.kind === "error"
                  ? "!"
                  : "i"
            }}
          </span>
          <p class="flex-1 text-sm text-fg">{{ toast.message }}</p>
          <button
            type="button"
            class="text-fg-subtle hover:text-fg"
            aria-label="Dismiss"
            @click="toasts.dismiss(toast.id)"
          >
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
              <path
                d="M3.5 3.5l7 7M10.5 3.5l-7 7"
                stroke="currentColor"
                stroke-width="1.5"
                stroke-linecap="round"
              />
            </svg>
          </button>
        </div>
      </TransitionGroup>
    </div>
  </Teleport>
</template>

<style scoped>
.toaster-root {
  top: calc(env(safe-area-inset-top) + 1rem);
  right: calc(env(safe-area-inset-right) + 1rem);
}
</style>
