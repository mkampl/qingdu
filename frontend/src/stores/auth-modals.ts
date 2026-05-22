import { defineStore } from "pinia";
import { ref } from "vue";

/**
 * Shared open/close state for the auth modals. Lives in a tiny Pinia store
 * (rather than local refs in AuthControls) so any view can request "open the
 * login dialog" without prop-drilling — useful when the Save Text button
 * wants to nudge an anonymous user to authenticate.
 */
export const useAuthModalsStore = defineStore("authModals", () => {
  const loginOpen = ref(false);
  const signupOpen = ref(false);
  const signupInviteToken = ref<string | null>(null);
  const changePasswordOpen = ref(false);
  const changePasswordForced = ref(false);

  function openLogin() {
    closeAll();
    loginOpen.value = true;
  }

  function openSignup(token?: string | null) {
    closeAll();
    signupInviteToken.value = token ?? null;
    signupOpen.value = true;
  }

  function openChangePassword(forced = false) {
    closeAll();
    changePasswordForced.value = forced;
    changePasswordOpen.value = true;
  }

  function closeAll() {
    loginOpen.value = false;
    signupOpen.value = false;
    changePasswordOpen.value = false;
    changePasswordForced.value = false;
  }

  return {
    loginOpen,
    signupOpen,
    signupInviteToken,
    changePasswordOpen,
    changePasswordForced,
    openLogin,
    openSignup,
    openChangePassword,
    closeAll,
  };
});
