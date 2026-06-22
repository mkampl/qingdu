<script setup lang="ts">
import { ref } from "vue";

import { setApiBase } from "@/api/client";
import { useToastStore } from "@/stores/toast";

import Modal from "@/components/ui/Modal.vue";

const DEMO_URL = "https://qingdu.itvoodoo.at";

const open = ref(true);
const choice = ref<"demo" | "custom" | null>(null);
const customUrl = ref("");
const testing = ref(false);
const error = ref<string | null>(null);
const toasts = useToastStore();

async function pickDemo() {
  choice.value = "demo";
  setApiBase(DEMO_URL);
  open.value = false;
  setTimeout(() => window.location.reload(), 250);
}

async function pickCustom() {
  const target = customUrl.value.trim().replace(/\/$/, "");
  if (!target) {
    error.value = "Enter a URL like https://qingdu.example.com";
    return;
  }
  testing.value = true;
  error.value = null;
  try {
    const r = await fetch(`${target}/api/health`, { method: "GET" });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    setApiBase(target);
    toasts.success("Connected. Reloading…");
    open.value = false;
    setTimeout(() => window.location.reload(), 400);
  } catch (e) {
    error.value =
      e instanceof Error
        ? `Couldn't reach that URL — ${e.message}`
        : "Couldn't reach that URL";
  } finally {
    testing.value = false;
  }
}
</script>

<template>
  <!-- First-launch chooser for Capacitor builds that ship without a baked-in
       server URL (the F-Droid track). Two paths: hit the maintainer's demo
       server, or paste your own self-hosted URL. Cannot be dismissed without
       a choice — the app needs a backend to be useful, and silent same-origin
       failures from the WebView's https://localhost would be worse UX than
       a forced one-time prompt. -->
  <Modal :open="open" size="md">
    <template #header>
      <div class="flex items-baseline gap-3">
        <h2 class="font-display text-xl font-medium tracking-tight text-fg">
          Choose your server
        </h2>
        <span
          class="font-mono text-[10px] uppercase tracking-[0.18em] text-fg-subtle"
        >
          First launch
        </span>
      </div>
    </template>

    <div class="space-y-5">
      <p class="text-sm text-fg-muted leading-relaxed">
        Qingdu needs a backend to analyse text and store your progress.
        Pick the public demo to try it out without setup, or paste the URL
        of your self-hosted instance.
      </p>

      <!-- Demo option -->
      <button
        type="button"
        class="flex w-full flex-col gap-1 rounded-lg border border-border-subtle bg-bg-elevated px-4 py-3 text-left transition-colors hover:border-accent hover:bg-bg-sunken"
        @click="pickDemo"
      >
        <span class="font-display text-base font-medium text-fg">
          Use the demo server
        </span>
        <span class="font-mono text-xs text-fg-muted">{{ DEMO_URL }}</span>
        <span class="text-xs text-fg-subtle">
          Hosted by the maintainer. No SLA. Best for evaluation; switch
          servers later from Settings if you decide to self-host.
        </span>
      </button>

      <!-- Custom option -->
      <div class="rounded-lg border border-border-subtle bg-bg-elevated px-4 py-3">
        <span class="block font-display text-base font-medium text-fg">
          Use my own server
        </span>
        <p class="mt-1 text-xs text-fg-subtle">
          Self-hosters: enter your instance URL. We'll verify it before
          continuing.
        </p>
        <label class="mt-3 block">
          <span class="mb-1 block font-mono text-[10px] uppercase tracking-wider text-fg-subtle">
            API URL
          </span>
          <input
            v-model="customUrl"
            type="url"
            inputmode="url"
            autocomplete="off"
            spellcheck="false"
            placeholder="https://qingdu.example.com"
            class="w-full rounded-md border border-border-subtle bg-bg px-3 py-2 font-mono text-sm text-fg focus:border-accent focus:outline-none"
            @keydown.enter="pickCustom"
          />
        </label>
        <button
          type="button"
          class="mt-3 inline-flex items-center gap-1.5 rounded-md bg-accent px-3 py-1.5 text-xs font-medium text-accent-fg transition-colors hover:bg-accent/90 disabled:cursor-not-allowed disabled:opacity-50"
          :disabled="testing || !customUrl"
          @click="pickCustom"
        >
          <span v-if="testing" class="inline-flex items-center gap-1.5">
            <span
              class="inline-block size-3 animate-spin rounded-full border-2 border-current border-t-transparent"
            />
            Testing…
          </span>
          <span v-else>Connect</span>
        </button>
        <p
          v-if="error"
          class="mt-2 text-xs text-red-700 dark:text-red-300"
        >
          {{ error }}
        </p>
      </div>
    </div>
  </Modal>
</template>
