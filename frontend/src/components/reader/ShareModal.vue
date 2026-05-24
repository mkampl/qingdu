<script setup lang="ts">
/**
 * Public-share modal for a saved text. Mints a token via POST
 * /api/texts/:id/share on open (or returns the existing one), shows the
 * shareable URL, lets the user copy or revoke.
 */
import { computed, ref, watch } from "vue";

import * as api from "@/api/client";
import { useToastStore } from "@/stores/toast";

import Button from "@/components/ui/Button.vue";
import Modal from "@/components/ui/Modal.vue";

const props = defineProps<{
  open: boolean;
  textId: number | null;
  /** Initial token if the text already had sharing enabled. */
  initialToken?: string | null;
}>();
const emit = defineEmits<{
  (e: "close"): void;
  /** Lets the parent persist the new state (e.g. update SavedTextSummary). */
  (e: "tokenChange", token: string | null): void;
}>();

const toasts = useToastStore();
const token = ref<string | null>(props.initialToken ?? null);
const loading = ref(false);
const error = ref<string | null>(null);

const shareUrl = computed(() => {
  if (!token.value || typeof window === "undefined") return "";
  return `${window.location.origin}/s/${token.value}`;
});

async function ensureToken() {
  if (!props.textId) return;
  if (token.value) return;
  loading.value = true;
  error.value = null;
  try {
    const r = await api.enableShare(props.textId);
    token.value = r.token;
    emit("tokenChange", r.token);
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Couldn't create share link.";
  } finally {
    loading.value = false;
  }
}

async function revoke() {
  if (!props.textId || !token.value) return;
  loading.value = true;
  try {
    await api.disableShare(props.textId);
    token.value = null;
    emit("tokenChange", null);
    toasts.success("Share link revoked.");
    emit("close");
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Couldn't revoke.";
  } finally {
    loading.value = false;
  }
}

async function copy() {
  if (!shareUrl.value) return;
  try {
    await navigator.clipboard.writeText(shareUrl.value);
    toasts.success("Link copied.");
  } catch {
    toasts.error("Couldn't copy — select and copy manually.");
  }
}

watch(
  () => props.open,
  (open) => {
    if (open) {
      token.value = props.initialToken ?? null;
      error.value = null;
      void ensureToken();
    }
  },
);
</script>

<template>
  <Modal :open="open" size="sm" close-on-backdrop @close="emit('close')">
    <template #header>
      <div class="flex items-baseline gap-3">
        <h2 class="font-display text-xl font-medium tracking-tight text-fg">
          Share text
        </h2>
        <span
          class="font-mono text-[10px] uppercase tracking-[0.18em] text-fg-subtle"
        >
          Public read-only link
        </span>
      </div>
    </template>

    <div class="space-y-4">
      <p class="text-sm leading-relaxed text-fg-muted">
        Anyone with this link can open the analysed text in read-only mode.
        Your tags, progress, and known-word state stay private.
      </p>

      <div v-if="loading" class="flex items-center gap-2 text-sm text-fg-muted">
        <span
          class="inline-block size-4 animate-spin rounded-full border-2 border-current border-t-transparent"
        />
        Preparing link…
      </div>

      <div
        v-else-if="error"
        class="rounded-md border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-800 dark:border-red-900 dark:bg-red-950/40 dark:text-red-200"
      >
        {{ error }}
      </div>

      <template v-else-if="shareUrl">
        <div class="flex items-center gap-2">
          <input
            :value="shareUrl"
            readonly
            class="flex-1 truncate rounded-md border border-border bg-bg-elevated px-3 py-2 font-mono text-xs text-fg focus:border-accent focus:outline-none"
            @focus="($event.target as HTMLInputElement).select()"
          />
          <Button variant="primary" size="sm" type="button" @click="copy">
            Copy
          </Button>
        </div>
        <p class="font-mono text-[10px] uppercase tracking-wider text-fg-subtle">
          Token: {{ token!.slice(0, 8) }}…
        </p>
      </template>

      <div class="flex items-center justify-end gap-2 pt-2">
        <Button
          v-if="token"
          variant="ghost"
          size="sm"
          type="button"
          :disabled="loading"
          @click="revoke"
        >
          Revoke link
        </Button>
        <Button variant="secondary" size="sm" type="button" @click="emit('close')">
          Done
        </Button>
      </div>
    </div>
  </Modal>
</template>
