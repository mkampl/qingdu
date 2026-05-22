<script setup lang="ts">
import { onMounted } from "vue";
import { RouterLink, RouterView } from "vue-router";

import { useAppModalsStore } from "@/stores/app-modals";
import { useAuthStore } from "@/stores/auth";
import { useSettingsStore } from "@/stores/settings";

import AuthControls from "@/components/auth/AuthControls.vue";
import InvitationsModal from "@/components/InvitationsModal.vue";
import SettingsModal from "@/components/SettingsModal.vue";
import Toaster from "@/components/ui/Toaster.vue";

const settings = useSettingsStore();
const auth = useAuthStore();
const modals = useAppModalsStore();

onMounted(async () => {
  settings.hydrate();
  await auth.hydrate();
});
</script>

<template>
  <div class="flex h-full flex-col">
    <header class="border-b border-border bg-bg-elevated">
      <div class="mx-auto flex max-w-6xl items-center gap-6 px-6 py-3">
        <RouterLink
          to="/"
          class="text-cn text-xl font-semibold tracking-tight"
        >
          轻读 <span class="text-fg-muted font-normal">QingDu</span>
        </RouterLink>
        <nav class="hidden gap-1 sm:flex">
          <RouterLink
            to="/"
            class="rounded-md px-3 py-1.5 text-sm text-fg-muted hover:text-fg hover:bg-bg-sunken"
            active-class="text-fg bg-bg-sunken"
          >
            Reader
          </RouterLink>
          <RouterLink
            to="/texts"
            class="rounded-md px-3 py-1.5 text-sm text-fg-muted hover:text-fg hover:bg-bg-sunken"
            active-class="text-fg bg-bg-sunken"
          >
            Saved Texts
          </RouterLink>
          <RouterLink
            to="/vocab"
            class="rounded-md px-3 py-1.5 text-sm text-fg-muted hover:text-fg hover:bg-bg-sunken"
            active-class="text-fg bg-bg-sunken"
          >
            Vocabulary
          </RouterLink>
        </nav>
        <div class="ml-auto flex items-center gap-1">
          <button
            type="button"
            class="rounded-md p-2 text-fg-muted hover:text-fg hover:bg-bg-sunken focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
            @click="settings.toggleTheme()"
            :title="settings.theme === 'dark' ? 'Switch to light' : 'Switch to dark'"
            :aria-label="settings.theme === 'dark' ? 'Switch to light' : 'Switch to dark'"
          >
            <svg
              v-if="settings.theme === 'dark'"
              width="16"
              height="16"
              viewBox="0 0 16 16"
              fill="none"
            >
              <circle cx="8" cy="8" r="3" stroke="currentColor" stroke-width="1.4" />
              <path
                d="M8 1v1.5M8 13.5V15M1 8h1.5M13.5 8H15M2.5 2.5l1 1M12.5 12.5l1 1M12.5 3.5l1-1M2.5 13.5l1-1"
                stroke="currentColor"
                stroke-width="1.4"
                stroke-linecap="round"
              />
            </svg>
            <svg
              v-else
              width="16"
              height="16"
              viewBox="0 0 16 16"
              fill="none"
            >
              <path
                d="M13 9.5a5.5 5.5 0 11-6.5-6.5 4.5 4.5 0 006.5 6.5z"
                stroke="currentColor"
                stroke-width="1.4"
                stroke-linejoin="round"
              />
            </svg>
          </button>
          <button
            type="button"
            class="rounded-md p-2 text-fg-muted hover:text-fg hover:bg-bg-sunken focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
            title="Settings"
            aria-label="Settings"
            @click="modals.openSettings()"
          >
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <circle
                cx="8"
                cy="8"
                r="2"
                stroke="currentColor"
                stroke-width="1.4"
              />
              <path
                d="M8 1.5v1.5M8 13v1.5M14.5 8H13M3 8H1.5M12.6 3.4l-1 1M4.4 11.6l-1 1M12.6 12.6l-1-1M4.4 4.4l-1-1"
                stroke="currentColor"
                stroke-width="1.4"
                stroke-linecap="round"
              />
            </svg>
          </button>
          <AuthControls />
        </div>
      </div>
    </header>
    <main class="flex-1 overflow-y-auto">
      <RouterView />
    </main>
    <Toaster />
    <SettingsModal />
    <InvitationsModal />
  </div>
</template>
