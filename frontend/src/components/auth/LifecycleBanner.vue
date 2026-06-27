<script setup lang="ts">
/**
 * Phase 2.10 — Account lifecycle banner.
 *
 * Renders a soft warning at the top of the app when the current user is
 * close to the instance's soft-delete threshold. The server populates
 * `soft_delete_at` on `/api/auth/me` (returns null when the instance has
 * inactivity cleanup disabled, so this whole banner stays hidden).
 *
 * Visible 7 days before soft-delete fires. The countdown updates live
 * (one tick per minute is plenty — it's a vague "in 5 days" not a
 * stopwatch). User dismissal is per-session (sessionStorage) so the
 * banner reappears next time but doesn't nag during a single session.
 */

import { computed, onMounted, onUnmounted, ref } from "vue";

import { useAuthStore } from "@/stores/auth";

const auth = useAuthStore();

const WARNING_WINDOW_DAYS = 7;
const DISMISS_KEY = "qingdu.lifecycle.dismissedFor";

const dismissed = ref(false);
const now = ref(new Date());

let tick: number | null = null;
onMounted(() => {
  // Restore per-soft_delete dismiss state — the same value of
  // soft_delete_at remembers a single dismiss; once the user opens the
  // app and the timestamp shifts later (their last_active stamp moved),
  // a new banner shows for the new horizon.
  try {
    const stored = sessionStorage.getItem(DISMISS_KEY);
    if (stored && stored === auth.user?.soft_delete_at) {
      dismissed.value = true;
    }
  } catch {
    // ignore — privacy modes block sessionStorage
  }
  tick = window.setInterval(() => {
    now.value = new Date();
  }, 60_000);
});

onUnmounted(() => {
  if (tick !== null) window.clearInterval(tick);
});

const daysUntilSoftDelete = computed<number | null>(() => {
  const iso = auth.user?.soft_delete_at;
  if (!iso) return null;
  const target = new Date(iso).getTime();
  if (Number.isNaN(target)) return null;
  const diffMs = target - now.value.getTime();
  if (diffMs <= 0) return 0;
  return Math.ceil(diffMs / (24 * 60 * 60 * 1000));
});

const show = computed(
  () =>
    auth.isAuthed &&
    !dismissed.value &&
    daysUntilSoftDelete.value !== null &&
    daysUntilSoftDelete.value <= WARNING_WINDOW_DAYS,
);

const days = computed(() => daysUntilSoftDelete.value ?? 0);

function dismiss() {
  dismissed.value = true;
  try {
    if (auth.user?.soft_delete_at) {
      sessionStorage.setItem(DISMISS_KEY, auth.user.soft_delete_at);
    }
  } catch {
    // ignore
  }
}
</script>

<template>
  <div
    v-if="show"
    role="status"
    class="border-b border-amber-300/60 bg-amber-50/70 px-4 py-2 dark:border-amber-700/50 dark:bg-amber-500/10"
  >
    <div class="mx-auto flex max-w-6xl items-center gap-3 text-xs">
      <svg
        width="14"
        height="14"
        viewBox="0 0 14 14"
        fill="none"
        aria-hidden="true"
        class="shrink-0 text-amber-700 dark:text-amber-300"
      >
        <path
          d="M7 1.5l5.5 10h-11L7 1.5zM7 5.5v2.5M7 9.7v.6"
          stroke="currentColor"
          stroke-width="1.4"
          stroke-linecap="round"
          stroke-linejoin="round"
        />
      </svg>
      <span class="font-medium text-amber-800 dark:text-amber-200">
        <template v-if="days <= 0">
          Your account is paused for inactivity. Sign in again to reactivate.
        </template>
        <template v-else-if="days === 1">
          Your account will pause tomorrow if you don't open the app.
        </template>
        <template v-else>
          Your account will pause in
          <span class="tabular-nums">{{ days }}</span>
          days if you don't open the app.
        </template>
      </span>
      <span
        class="hidden text-amber-700/70 dark:text-amber-300/70 sm:inline"
      >
        Self-host your own backend for unlimited retention.
      </span>
      <button
        type="button"
        class="ml-auto rounded p-1 text-amber-700 hover:bg-amber-100 hover:text-amber-900 dark:text-amber-300 dark:hover:bg-amber-500/20 dark:hover:text-amber-100"
        aria-label="Dismiss banner"
        @click="dismiss"
      >
        <svg width="12" height="12" viewBox="0 0 12 12" fill="none" aria-hidden="true">
          <path
            d="M2 2l8 8M10 2l-8 8"
            stroke="currentColor"
            stroke-width="1.5"
            stroke-linecap="round"
          />
        </svg>
      </button>
    </div>
  </div>
</template>
