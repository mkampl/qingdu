import { defineStore } from "pinia";
import { ref } from "vue";

/**
 * Open/close state for non-auth modals — Settings (always available) and My
 * Invitations (only useful when signed in). A store so the header cog and
 * the user menu open the same modal instance.
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
