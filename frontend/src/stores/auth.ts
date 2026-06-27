import { defineStore } from "pinia";
import { computed, ref } from "vue";

import * as api from "@/api/client";
import type { User } from "@/api/types";
import { useReviewStore } from "@/stores/review";
import { useUserWordsStore } from "@/stores/userWords";

export const useAuthStore = defineStore("auth", () => {
  const user = ref<User | null>(null);
  const loading = ref(false);
  const error = ref<string | null>(null);

  const isAuthed = computed(() => user.value !== null);
  const isAdmin = computed(() => user.value?.is_admin ?? false);

  async function hydrate() {
    if (!api.getToken()) {
      user.value = null;
      return;
    }
    try {
      const me = await api.me();
      user.value = me.authenticated ? me.user : null;
    } catch {
      // Token rejected — clear it.
      api.setToken(null);
      user.value = null;
    }
    if (user.value) {
      // Fire-and-forget; the reader still renders before this resolves.
      useUserWordsStore().hydrate();
      useReviewStore().refreshStats();
    }
  }

  async function login(username: string, password: string) {
    loading.value = true;
    error.value = null;
    try {
      const result = await api.login(username, password);
      api.setToken(result.access_token);
      user.value = result.user;
      useUserWordsStore().hydrate(true);
      useReviewStore().refreshStats();
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
      user.value = result.user;
      useUserWordsStore().hydrate(true);
      useReviewStore().refreshStats();
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
      useUserWordsStore().reset();
      useReviewStore().reset();
    }
  }

  async function changePassword(oldPassword: string, newPassword: string) {
    await api.changePassword(oldPassword, newPassword);
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
      };
    }
    // The review-stats badge depends on daily_target; nudge it so the UI
    // reflects the new value without waiting for the next mount.
    useReviewStore().refreshStats();
  }

  return {
    user,
    loading,
    error,
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
