<script setup lang="ts">
import { useAppModalsStore } from "@/stores/app-modals";
import { useAuthStore } from "@/stores/auth";

import Modal from "@/components/ui/Modal.vue";
import AccountSection from "@/components/settings/AccountSection.vue";
import AppearanceSection from "@/components/settings/AppearanceSection.vue";
import DisplaySection from "@/components/settings/DisplaySection.vue";
import LearningSection from "@/components/settings/LearningSection.vue";
import ReviewSection from "@/components/settings/ReviewSection.vue";
import {
  useAccountDeletion,
  useApiTokens,
  useHskImport,
  useServerSwitcher,
} from "@/components/settings/state";

const modals = useAppModalsStore();
const auth = useAuthStore();

// Section state lives here, not in the sections, so it outlasts the
// modal closing (see settings/state.ts).
const hskImport = useHskImport();
const tokens = useApiTokens();
const server = useServerSwitcher();
const deletion = useAccountDeletion();
</script>

<template>
  <Modal
    :open="modals.settingsOpen"
    size="md"
    close-on-backdrop
    @close="modals.closeAll()"
  >
    <template #header>
      <div class="flex items-baseline gap-3">
        <h2 class="font-display text-xl font-medium tracking-tight text-fg">
          Settings
        </h2>
        <span
          class="font-mono text-[10px] uppercase tracking-[0.18em] text-fg-subtle"
          :title="
            auth.isAuthed
              ? 'Reading and review settings follow your account to every device; theme, reminders and vibration stay on this device.'
              : undefined
          "
        >
          {{ auth.isAuthed ? "Saved to your account" : "Saved on this device" }}
        </span>
      </div>
    </template>

    <div class="space-y-3">
      <!-- Five collapsible sections; the two most used (Display, Review)
           open by default. Native <details> handles keyboard and a11y. -->
      <DisplaySection />

      <ReviewSection />

      <AppearanceSection />

      <LearningSection v-if="auth.isAuthed" :hsk-import="hskImport" />

      <!-- Everything inside is auth-gated or server-related; logged-out on
           a same-origin web build the section would expand to nothing. -->
      <AccountSection
        v-if="auth.isAuthed || server.serverSectionVisible"
        :tokens="tokens"
        :server="server"
        :deletion="deletion"
      />
    </div>
  </Modal>
</template>
