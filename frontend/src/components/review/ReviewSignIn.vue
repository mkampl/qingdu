<script setup lang="ts">
/** The review page for a signed-out visitor: what review draws from, and Sign in. */
import { useAuthModalsStore } from "@/stores/auth-modals";

const authModals = useAuthModalsStore();
</script>

<template>
  <div class="rounded-lg border border-border-subtle bg-bg-elevated px-6 py-10 text-center">
    <p class="font-display text-lg text-fg">Sign in to review your words.</p>
    <p class="mt-2 text-sm text-fg-muted">
      Review draws from the words you track in the reader —
      <span class="font-medium">Learning</span> words often,
      <span class="font-medium">Known</span> words now and then.
    </p>
    <button
      type="button"
      class="mt-4 inline-flex items-center rounded-full bg-accent px-4 py-1.5 text-sm font-medium text-accent-fg transition-opacity hover:opacity-90"
      @click="authModals.openLogin()"
    >
      Sign in
    </button>
  </div>
</template>
