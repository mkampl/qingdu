import { defineStore } from "pinia";
import { computed, ref } from "vue";

import * as api from "@/api/client";
import type { User } from "@/api/types";

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
  }

  async function login(username: string, password: string) {
    loading.value = true;
    error.value = null;
    try {
      const result = await api.login(username, password);
      api.setToken(result.access_token);
      user.value = result.user;
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
    }
  }

  async function changePassword(oldPassword: string, newPassword: string) {
    await api.changePassword(oldPassword, newPassword);
    if (user.value) user.value = { ...user.value, must_change_password: false };
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
    logout,
    changePassword,
  };
});
