import { defineStore } from "pinia";
import { ref } from "vue";

/**
 * Open/close state for non-auth modals — Settings (always available) and My
 * Invitations (only useful when signed in). Living in a Pinia store lets the
 * header cog, the user menu, and any future "open settings" affordance all
 * trigger the same modal instance.
 */
export const useAppModalsStore = defineStore("appModals", () => {
  const settingsOpen = ref(false);
  const invitationsOpen = ref(false);

  function openSettings() {
    invitationsOpen.value = false;
    settingsOpen.value = true;
  }

  function openInvitations() {
    settingsOpen.value = false;
    invitationsOpen.value = true;
  }

  function closeAll() {
    settingsOpen.value = false;
    invitationsOpen.value = false;
  }

  return {
    settingsOpen,
    invitationsOpen,
    openSettings,
    openInvitations,
    closeAll,
  };
});
