<script setup lang="ts">
import type { ServerSwitcher } from "@/components/settings/state";

defineProps<{ server: ServerSwitcher }>();
</script>

<template>
  <fieldset>
    <legend
      class="mb-3 font-mono text-[11px] uppercase tracking-[0.2em] text-fg-subtle"
    >
      Server
    </legend>
    <p class="mb-3 text-xs text-fg-muted leading-relaxed">
      This app currently talks to
      <code class="rounded bg-bg-sunken px-1 py-0.5 font-mono text-[11px] text-fg">{{ server.apiBaseCurrent }}</code>.
      Point it at your own Qingdu instance to keep your data on
      infrastructure you control. Changing server signs you out; the
      new server has its own accounts.
    </p>
    <label class="block">
      <span class="mb-1 block font-mono text-[10px] uppercase tracking-wider text-fg-subtle">
        API URL
      </span>
      <input
        v-model="server.apiBaseInput"
        type="url"
        inputmode="url"
        autocomplete="off"
        spellcheck="false"
        placeholder="https://qingdu.example.com"
        class="w-full rounded-md border border-border-subtle bg-bg px-3 py-2 font-mono text-sm text-fg focus:border-accent focus:outline-none"
      />
    </label>
    <div class="mt-3 flex flex-wrap items-center gap-2">
      <button
        type="button"
        class="inline-flex items-center gap-1.5 rounded-md border border-border bg-bg-elevated px-3 py-1.5 text-xs font-medium text-fg-muted transition-colors hover:bg-bg-sunken hover:text-fg disabled:cursor-not-allowed disabled:opacity-50"
        :disabled="server.apiBaseTesting || !server.apiBaseInput"
        @click="server.testApiBase"
      >
        <span v-if="server.apiBaseTesting" class="inline-flex items-center gap-1.5">
          <span
            class="inline-block size-3 animate-spin rounded-full border-2 border-current border-t-transparent"
          />
          Testing…
        </span>
        <span v-else>Test</span>
      </button>
      <button
        type="button"
        class="inline-flex items-center rounded-md bg-accent px-3 py-1.5 text-xs font-medium text-accent-fg transition-colors hover:bg-accent/90 disabled:cursor-not-allowed disabled:opacity-50"
        :disabled="!server.apiBaseChanged"
        @click="server.saveApiBase"
      >
        Save &amp; reload
      </button>
      <button
        v-if="!server.apiBaseIsDefault"
        type="button"
        class="text-xs text-fg-muted underline-offset-2 hover:text-fg hover:underline"
        @click="server.resetApiBase"
      >
        Use default
      </button>
    </div>
    <p
      v-if="server.apiBaseStatus.kind === 'ok'"
      class="mt-3 text-xs text-emerald-700 dark:text-emerald-300"
    >
      ✓ Connected. Vocab loaded ({{ server.apiBaseStatus.vocabCount.toLocaleString() }} entries).
    </p>
    <p
      v-else-if="server.apiBaseStatus.kind === 'error'"
      class="mt-3 text-xs text-red-700 dark:text-red-300"
    >
      {{ server.apiBaseStatus.message }}
    </p>
  </fieldset>
</template>
