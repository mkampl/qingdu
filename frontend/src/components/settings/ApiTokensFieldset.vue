<script setup lang="ts">
import * as api from "@/api/client";
import { formatUtcDate } from "@/utils/time";

import type { ApiTokens } from "@/components/settings/state";

defineProps<{ tokens: ApiTokens }>();
</script>

<template>
  <fieldset>
    <legend
      class="mb-3 font-mono text-[11px] uppercase tracking-[0.2em] text-fg-subtle"
    >
      API tokens
    </legend>
    <p class="mb-3 text-xs text-fg-muted leading-relaxed">
      Let another app of yours read your known/learning words or report
      new ones it taught you — without sharing your password. Create a
      token scoped to just what it needs; revoke it any time.
    </p>

    <ul v-if="tokens.apiTokens.length" class="mb-3 space-y-1.5">
      <li
        v-for="t in tokens.apiTokens"
        :key="t.id"
        class="flex items-center justify-between gap-2 rounded-md border border-border-subtle bg-bg-elevated px-3 py-2 text-xs"
      >
        <span class="min-w-0">
          <span class="block truncate font-medium text-fg">{{ t.name }}</span>
          <span class="block font-mono text-[10px] text-fg-subtle">
            {{ t.token_prefix }}… · {{ t.scopes.join(", ") }}
            <template v-if="t.last_used_at"> · last used {{ formatUtcDate(t.last_used_at) }}</template>
            <template v-else> · never used</template>
          </span>
        </span>
        <button
          type="button"
          class="shrink-0 rounded-md border border-red-300 px-2 py-1 text-[11px] font-medium text-red-700 transition-colors hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-red-800 dark:text-red-300 dark:hover:bg-red-950/40"
          :disabled="tokens.revokingTokenId === t.id"
          @click="tokens.revokeToken(t.id)"
        >
          {{ tokens.revokingTokenId === t.id ? "Revoking…" : "Revoke" }}
        </button>
      </li>
    </ul>
    <p v-else-if="tokens.apiTokensLoaded" class="mb-3 text-xs text-fg-subtle">
      No tokens yet.
    </p>

    <div
      v-if="tokens.revealedToken"
      class="mb-3 rounded-md border border-accent/40 bg-bg-sunken p-3"
    >
      <p class="mb-2 text-xs text-fg-muted">
        Copy this now — it won't be shown again.
      </p>
      <div class="flex items-center gap-2">
        <code
          class="min-w-0 flex-1 truncate rounded bg-bg px-2 py-1.5 font-mono text-[11px] text-fg"
          >{{ tokens.revealedToken.token }}</code
        >
        <button
          type="button"
          class="shrink-0 rounded-md border border-border bg-bg-elevated px-2 py-1.5 text-[11px] font-medium text-fg-muted transition-colors hover:bg-bg-sunken hover:text-fg"
          @click="tokens.copyRevealedToken"
        >
          Copy
        </button>
      </div>
      <button
        type="button"
        class="mt-2 text-[11px] text-fg-muted underline-offset-2 hover:text-fg hover:underline"
        @click="tokens.revealedToken = null"
      >
        Done
      </button>
    </div>

    <div class="space-y-2">
      <label class="block">
        <span class="mb-1 block font-mono text-[10px] uppercase tracking-wider text-fg-subtle">
          Name
        </span>
        <input
          v-model="tokens.newTokenName"
          type="text"
          placeholder="e.g. speaking companion"
          class="w-full max-w-xs rounded-md border border-border-subtle bg-bg px-3 py-2 text-sm text-fg focus:border-accent focus:outline-none"
        />
      </label>
      <div class="flex flex-wrap gap-3">
        <label
          v-for="scope in api.API_TOKEN_SCOPES"
          :key="scope"
          class="flex items-center gap-1.5 text-xs text-fg-muted"
        >
          <input
            v-model="tokens.newTokenScopes"
            type="checkbox"
            :value="scope"
            class="accent-accent"
          />
          {{ scope }}
        </label>
      </div>
      <button
        type="button"
        class="rounded-md bg-accent px-3 py-1.5 text-xs font-medium text-accent-fg transition-colors hover:bg-accent/90 disabled:cursor-not-allowed disabled:opacity-50"
        :disabled="!tokens.newTokenName.trim() || tokens.newTokenScopes.length === 0 || tokens.creatingToken"
        @click="tokens.createToken"
      >
        {{ tokens.creatingToken ? "Creating…" : "Create token" }}
      </button>
    </div>
  </fieldset>
</template>
