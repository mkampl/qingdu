import { defineStore } from "pinia";
import { computed, ref } from "vue";

import * as api from "@/api/client";
import { ApiError } from "@/api/client";
import type { User } from "@/api/types";
import { useReviewStore } from "@/stores/review";
import { useSettingsStore } from "@/stores/settings";
import { resetUserScopedStores } from "@/stores/user-scope";
import { useUserWordsStore } from "@/stores/userWords";
import { browserTimeZone } from "@/utils/timezone";

export const useAuthStore = defineStore("auth", () => {
  const user = ref<User | null>(null);
  const loading = ref(false);
  const error = ref<string | null>(null);
  // False until the boot-time /api/auth/me check has settled (either way).
  // Auth-gated views show a placeholder while false instead of flashing
  // their "Sign in" state for a logged-in user on a hard reload.
  const hydrated = ref(false);
  // Username whose data the reader still holds after a session expiry
  // (resetUserScopedStores({ keepReading: true })). A different account
  // signing in next must not inherit that saved text.
  let readingOwner: string | null = null;

  const isAuthed = computed(() => user.value !== null);
  const isAdmin = computed(() => user.value?.is_admin ?? false);

  // Mid-session token expiry (30-day JWTs do run out). One 401 from any
  // authed endpoint clears the session and brings the login modal back,
  // instead of a trickle of raw "Not authenticated" toasts while
  // optimistic UI keeps accepting edits that roll back one by one.
  api.setUnauthorizedHandler(async () => {
    if (!api.getToken() && user.value === null) return; // already handled
    api.setToken(null);
    readingOwner = user.value?.username ?? readingOwner;
    user.value = null;
    resetUserScopedStores({ keepReading: true });
    // Dynamic imports keep this file free of new static store edges
    // (toast/auth-modals) that could form require cycles.
    const { useToastStore } = await import("@/stores/toast");
    const { useAuthModalsStore } = await import("@/stores/auth-modals");
    useToastStore().info("Your session expired — please sign in again.");
    useAuthModalsStore().openLogin();
  });

  // Every successful sign-in goes through here. A different account than
  // the one whose reading state survived an expiry gets a clean reader.
  function adoptUser(next: User) {
    if (readingOwner !== null && readingOwner !== next.username) {
      resetUserScopedStores();
    }
    readingOwner = null;
    user.value = next;
  }

  async function hydrate() {
    try {
      await hydrateSession();
    } finally {
      hydrated.value = true;
    }
  }

  async function hydrateSession() {
    if (!api.getToken()) {
      user.value = null;
      return;
    }
    try {
      const me = await api.me();
      if (me.authenticated) {
        adoptUser(me.user);
      } else {
        // The server no longer accepts this token (expired, or revoked by
        // a password change elsewhere). Drop it quietly: this is a cold
        // start, not a session dying under the user's hands, so no
        // "session expired" modal — they simply land logged out.
        api.setToken(null);
        user.value = null;
      }
    } catch (e) {
      // Only a server-side rejection means the token is bad. A network
      // failure (offline app start, server blip) must NOT clear it —
      // that logged phone users out every time they opened the app in
      // airplane mode. Stay logged-out for this session but keep the
      // token for the next launch.
      if (e instanceof ApiError && (e.status === 401 || e.status === 403)) {
        api.setToken(null);
      }
      user.value = null;
    }
    if (user.value) {
      // Fire-and-forget; the reader still renders before this resolves.
      useUserWordsStore().hydrate();
      useReviewStore().refreshStats();
      void syncTimezone();
      void syncHskVersion();
    }
  }

  // The server counts "today" in the zone stored on the account. Until
  // one is stored (null), send this device's zone — once; after that the
  // user changes it in Settings. An older server omits the field
  // (undefined) and is left alone.
  async function syncTimezone() {
    if (user.value?.timezone !== null) return;
    const tz = browserTimeZone();
    if (!tz) return;
    try {
      await updateSettings({ timezone: tz });
    } catch {
      // Not critical: the server keeps counting in UTC, and the next app
      // start tries again.
    }
  }

  // The HSK version is picked in Settings and kept on the device; the
  // server needs it too, because daily auto-enrol draws from that list.
  // An older server omits the field and is left alone.
  async function syncHskVersion() {
    const server = user.value?.hsk_focus_version;
    const local = useSettingsStore().hskVersion;
    if (server === undefined || server === local) return;
    try {
      await updateSettings({ hsk_focus_version: local });
    } catch {
      // The next app start tries again.
    }
  }

  // /login and /signup answer with a bare identity; /me carries the
  // settings (timezone among them).
  async function loadProfile() {
    try {
      const me = await api.me();
      if (me.authenticated && me.user.username === user.value?.username) {
        user.value = { ...user.value, ...me.user };
        await syncTimezone();
        await syncHskVersion();
      }
    } catch {
      // The identity from the login response is enough to carry on.
    }
  }

  async function login(username: string, password: string) {
    loading.value = true;
    error.value = null;
    try {
      const result = await api.login(username, password);
      api.setToken(result.access_token);
      adoptUser(result.user);
      useUserWordsStore().hydrate(true);
      useReviewStore().refreshStats();
      void loadProfile();
    } catch (e) {
      error.value = e instanceof Error ? e.message : "Login failed";
      throw e;
    } finally {
      loading.value = false;
    }
  }

  async function signupWithInvite(
    token: string,
    username: string,
    password: string,
  ) {
    loading.value = true;
    error.value = null;
    try {
      const result = await api.signupWithInvite(token, username, password);
      api.setToken(result.access_token);
      adoptUser(result.user);
      useUserWordsStore().hydrate(true);
      useReviewStore().refreshStats();
      void loadProfile();
    } catch (e) {
      error.value = e instanceof Error ? e.message : "Signup failed";
      throw e;
    } finally {
      loading.value = false;
    }
  }

  // Phase 2.9 — public open-registration signup. Returns nothing; the caller
  // catches ApiError to display field-specific errors. The captcha pair is
  // optional from the client's perspective — the server ignores it when the
  // instance has captcha turned off.
  async function openRegister(
    username: string,
    password: string,
    captcha?: { token: string; answer: number | string },
  ) {
    loading.value = true;
    error.value = null;
    try {
      const result = await api.openRegister({
        username,
        password,
        captcha_token: captcha?.token,
        captcha_answer: captcha?.answer,
      });
      api.setToken(result.access_token);
      // Reuse hydrate to pull the full /me payload (lifecycle stamps etc).
      await hydrate();
      useUserWordsStore().hydrate(true);
      useReviewStore().refreshStats();
    } catch (e) {
      error.value = e instanceof Error ? e.message : "Signup failed";
      throw e;
    } finally {
      loading.value = false;
    }
  }

  async function logout() {
    try {
      await api.logout();
    } catch {
      // Server-side logout is a no-op; ignore network errors.
    } finally {
      api.setToken(null);
      user.value = null;
      readingOwner = null;
      resetUserScopedStores();
    }
  }

  async function changePassword(oldPassword: string, newPassword: string) {
    const result = await api.changePassword(oldPassword, newPassword);
    // The change signs out every other session, this one included — the
    // server hands back a fresh token for this device.
    if (result.access_token) api.setToken(result.access_token);
    if (user.value) user.value = { ...user.value, must_change_password: false };
  }

  async function updateSettings(payload: api.UserSettingsPayload) {
    const updated = await api.updateMySettings(payload);
    if (user.value) {
      user.value = {
        ...user.value,
        daily_new_words: updated.daily_new_words,
        hsk_focus_version: updated.hsk_focus_version as "new" | "old",
        display_script: updated.display_script as "auto" | "simp" | "trad",
        review_retention: updated.review_retention,
        review_window: updated.review_window as "now" | "today" | "tomorrow",
        ...(updated.timezone !== undefined ? { timezone: updated.timezone } : {}),
      };
    }
    // The review-stats badge depends on daily_target; nudge it so the UI
    // reflects the new value without waiting for the next mount.
    useReviewStore().refreshStats();
  }

  return {
    syncHskVersion,
    user,
    loading,
    error,
    hydrated,
    isAuthed,
    isAdmin,
    hydrate,
    login,
    signupWithInvite,
    openRegister,
    logout,
    changePassword,
    updateSettings,
  };
});
