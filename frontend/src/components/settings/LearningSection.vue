<script setup lang="ts">
import { computed } from "vue";

import { useAppModalsStore } from "@/stores/app-modals";
import { useAuthStore } from "@/stores/auth";
import { useToastStore } from "@/stores/toast";

import SettingsSection from "@/components/settings/SettingsSection.vue";
import type { HskImport } from "@/components/settings/state";

defineProps<{ hskImport: HskImport }>();

const modals = useAppModalsStore();
const auth = useAuthStore();
const toasts = useToastStore();

// --- Daily auto-enrol target ---
// Bound to auth.user so the UI shows the server's value; 0 means
// auto-enrol is off.
const dailyNewWords = computed<number>({
  get: () => auth.user?.daily_new_words ?? 0,
  set: (v) => {
    void auth.updateSettings({ daily_new_words: clampDaily(v) }).catch(() => {
      toasts.error("Couldn't save daily target.");
    });
  },
});

const dailyEnabled = computed<boolean>({
  get: () => dailyNewWords.value > 0,
  // On sets the recommended default of 5; off sets 0.
  set: (v) => {
    dailyNewWords.value = v ? 5 : 0;
  },
});

function clampDaily(v: number): number {
  if (!Number.isFinite(v)) return 0;
  return Math.max(0, Math.min(30, Math.round(v)));
}
</script>

<template>
  <SettingsSection title="Learning">
    <!-- Daily auto-enrol target. Off by default; the checkbox flips the
         target between 0 and 5, with a numeric input revealed when on. -->
    <fieldset>
      <legend
        class="mb-3 font-mono text-[11px] uppercase tracking-[0.2em] text-fg-subtle"
      >
        Daily learning
      </legend>
      <label
        class="flex cursor-pointer items-start gap-3 rounded-md border border-border-subtle px-3 py-2 transition-colors hover:bg-bg-sunken"
      >
        <input
          v-model="dailyEnabled"
          type="checkbox"
          class="mt-1 accent-accent"
        />
        <span class="flex-1">
          <span class="block font-display text-base text-fg">
            Auto-enrol new HSK words
          </span>
          <span class="block text-xs text-fg-muted">
            Adds the next N HSK words to your queue daily.
          </span>
        </span>
      </label>
      <label v-if="dailyEnabled" class="mt-3 flex items-center gap-3 pl-6">
        <span
          class="font-mono text-[10px] uppercase tracking-wider text-fg-subtle"
        >
          New words / day
        </span>
        <input
          v-model.number="dailyNewWords"
          type="number"
          min="1"
          max="30"
          class="w-20 rounded-md border border-border bg-bg-elevated px-3 py-1.5 text-sm text-fg focus:border-accent focus:outline-none"
        />
        <span class="font-mono text-[10px] text-fg-subtle">1–30</span>
      </label>
    </fieldset>

    <!-- Onboarding shortcut: one batch mark-as-known pass so intermediate
         learners skip the cold start. -->
    <fieldset>
      <legend
        class="mb-3 font-mono text-[11px] uppercase tracking-[0.2em] text-fg-subtle"
      >
        Onboarding shortcuts
      </legend>
      <p class="mb-3 text-xs text-fg-muted">
        Bulk-mark every word up to a level as known — or
        <RouterLink to="/welcome" class="text-accent hover:underline" @click="modals.settingsOpen = false">
          take the placement test
        </RouterLink>
        to find your level.
      </p>
      <div class="flex flex-wrap items-end gap-3">
        <label class="flex flex-col gap-1">
          <span
            class="font-mono text-[10px] uppercase tracking-wider text-fg-subtle"
          >
            Up to HSK
          </span>
          <select
            v-model.number="hskImport.importLevel"
            :disabled="hskImport.importing"
            class="rounded-md border border-border bg-bg-elevated px-2 py-1.5 text-sm text-fg focus:border-accent focus:outline-none"
          >
            <option v-for="n in hskImport.importMaxLevel" :key="n" :value="n">
              HSK {{ n }}
            </option>
          </select>
        </label>
        <div class="flex flex-col gap-1">
          <span
            class="font-mono text-[10px] uppercase tracking-wider text-fg-subtle"
          >
            About
          </span>
          <span class="font-display text-base text-fg tabular-nums">
            ~{{ hskImport.roughTotal.toLocaleString() }} words
          </span>
        </div>
        <div class="ml-auto flex items-center gap-2">
          <template v-if="!hskImport.pendingConfirm">
            <button
              type="button"
              class="rounded-md bg-accent px-3 py-1.5 text-xs font-medium text-accent-fg transition-opacity hover:opacity-90 disabled:opacity-50"
              :disabled="hskImport.importing"
              @click="hskImport.pendingConfirm = true"
            >
              Mark as known
            </button>
          </template>
          <template v-else>
            <button
              type="button"
              class="font-mono text-[10px] uppercase tracking-wider text-fg-subtle transition-colors hover:text-fg"
              :disabled="hskImport.importing"
              @click="hskImport.pendingConfirm = false"
            >
              Cancel
            </button>
            <button
              type="button"
              class="rounded-md bg-accent px-3 py-1.5 text-xs font-medium text-accent-fg transition-opacity hover:opacity-90 disabled:opacity-50"
              :disabled="hskImport.importing"
              @click="hskImport.runImport"
            >
              <span v-if="hskImport.importing" class="inline-flex items-center gap-1.5">
                <span
                  class="inline-block size-3 animate-spin rounded-full border-2 border-current border-t-transparent"
                />
                Marking…
              </span>
              <span v-else>Confirm</span>
            </button>
          </template>
        </div>
      </div>
      <p
        v-if="hskImport.lastResult"
        class="mt-3 font-mono text-[10px] uppercase tracking-wider text-fg-subtle"
      >
        {{ hskImport.lastResult.inserted.toLocaleString() }} added ·
        {{ hskImport.lastResult.skipped.toLocaleString() }} already tracked ·
        {{ hskImport.lastResult.total_eligible.toLocaleString() }} eligible
      </p>
    </fieldset>
  </SettingsSection>
</template>
