<script setup lang="ts">
import * as api from "@/api/client";
import { useAuthStore } from "@/stores/auth";
import { useCapabilitiesStore } from "@/stores/capabilities";
import { useToastStore } from "@/stores/toast";

import ApiTokensFieldset from "@/components/settings/ApiTokensFieldset.vue";
import DownloadIcon from "@/components/settings/DownloadIcon.vue";
import ServerFieldset from "@/components/settings/ServerFieldset.vue";
import SettingsSection from "@/components/settings/SettingsSection.vue";
import type {
  AccountDeletion,
  ApiTokens,
  ServerSwitcher,
} from "@/components/settings/state";

defineProps<{
  tokens: ApiTokens;
  server: ServerSwitcher;
  deletion: AccountDeletion;
}>();

const auth = useAuthStore();
const toasts = useToastStore();
const capabilities = useCapabilitiesStore();

async function download(path: string) {
  try {
    await api.openDownload(path);
  } catch (e) {
    toasts.error(e instanceof Error ? e.message : "Couldn't start the download");
  }
}
</script>

<template>
  <SettingsSection title="Data & account">
    <!-- What the server this app talks to offers (GET /api/capabilities). -->
    <p v-if="capabilities.caps" class="text-xs text-fg-muted">
      <span class="font-mono text-[10px] uppercase tracking-wider text-fg-subtle">This server</span>
      ·
      <template v-if="capabilities.llm?.available">
        AI help available ({{ capabilities.llm.model }})
      </template>
      <template v-else-if="capabilities.llm?.configured">
        AI help configured but not reachable right now
      </template>
      <template v-else>No AI help configured</template>
      · translation via {{ capabilities.caps.translation.join(", ") }}
    </p>
    <!-- Data export. Each button opens the download as a
         plain link with a short-lived ticket (api.openDownload), so the
         browser handles the file natively and no session token lands in
         a URL. -->
    <fieldset v-if="auth.isAuthed">
      <legend
        class="mb-3 font-mono text-[11px] uppercase tracking-[0.2em] text-fg-subtle"
      >
        Export
      </legend>
      <p class="mb-3 text-xs text-fg-muted leading-relaxed">
        Take your data with you. Everything is the complete account —
        texts, word states with scheduling, lists, and review history —
        as one JSON file. CSV and Anki cover just your words.
      </p>
      <div class="flex flex-wrap gap-2">
        <button
          type="button"
          @click="download(api.FULL_EXPORT_PATH)"
          class="inline-flex items-center gap-1.5 rounded-md border border-accent/40 bg-bg-elevated px-3 py-1.5 text-xs font-medium text-fg transition-colors hover:bg-bg-sunken"
        >
          <DownloadIcon />
          everything.json
        </button>
        <button
          type="button"
          @click="download(api.WORDS_CSV_PATH)"
          class="inline-flex items-center gap-1.5 rounded-md border border-border bg-bg-elevated px-3 py-1.5 text-xs font-medium text-fg-muted transition-colors hover:bg-bg-sunken hover:text-fg"
        >
          <DownloadIcon />
          words.csv
        </button>
        <button
          type="button"
          @click="download(api.WORDS_ANKI_PATH)"
          class="inline-flex items-center gap-1.5 rounded-md border border-border bg-bg-elevated px-3 py-1.5 text-xs font-medium text-fg-muted transition-colors hover:bg-bg-sunken hover:text-fg"
        >
          <DownloadIcon />
          words.apkg
        </button>
      </div>
    </fieldset>

    <!-- Personal API tokens for external integrations,
         e.g. a speaking-companion app that wants to read which words
         you already know and report newly-encountered ones back. -->
    <ApiTokensFieldset v-if="auth.isAuthed" :tokens="tokens" />

    <!-- Server switcher for self-hosters. Shown on every
         native build (F-Droid ships no baked-in default — the first-
         launch ServerPicker promises "switch later in Settings") and on
         web builds that carry a default URL. Hidden only on same-origin
         web builds, where the user already knows what server they hit. -->
    <ServerFieldset v-if="server.serverSectionVisible" :server="server" />

    <!-- Self-service account deletion. Inline two-step
         confirm + password re-entry; there is no email, so there is no
         undo path once this runs. -->
    <fieldset v-if="auth.isAuthed && !auth.isAdmin">
      <legend
        class="mb-3 font-mono text-[11px] uppercase tracking-[0.2em] text-fg-subtle"
      >
        Delete account
      </legend>
      <p class="mb-3 text-xs text-fg-muted leading-relaxed">
        Removes your account and everything in it — texts, words, lists,
        review history — immediately and permanently. Download your data
        first if you might want it back.
      </p>
      <button
        v-if="!deletion.deleteArmed"
        type="button"
        class="rounded-md border border-red-300 px-3 py-1.5 text-xs font-medium text-red-700 transition-colors hover:bg-red-50 dark:border-red-800 dark:text-red-300 dark:hover:bg-red-950/40"
        @click="deletion.deleteArmed = true"
      >
        Delete my account…
      </button>
      <div v-else class="space-y-2">
        <label class="block">
          <span class="mb-1 block font-mono text-[10px] uppercase tracking-wider text-fg-subtle">
            Confirm with your password
          </span>
          <input
            v-model="deletion.deletePassword"
            type="password"
            autocomplete="current-password"
            class="w-full max-w-xs rounded-md border border-border-subtle bg-bg px-3 py-2 text-sm text-fg focus:border-accent focus:outline-none"
          />
        </label>
        <div class="flex items-center gap-2">
          <button
            type="button"
            class="rounded-md bg-red-600 px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-red-700 disabled:cursor-not-allowed disabled:opacity-50"
            :disabled="!deletion.deletePassword || deletion.deleteBusy"
            @click="deletion.confirmDeleteAccount"
          >
            {{ deletion.deleteBusy ? "Deleting…" : "Yes, delete everything" }}
          </button>
          <button
            type="button"
            class="text-xs text-fg-muted underline-offset-2 hover:text-fg hover:underline"
            @click="deletion.deleteArmed = false; deletion.deletePassword = ''"
          >
            Cancel
          </button>
        </div>
      </div>
    </fieldset>
  </SettingsSection>
</template>
