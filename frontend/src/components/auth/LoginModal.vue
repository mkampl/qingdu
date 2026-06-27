<script setup lang="ts">
import { ref, watch } from "vue";

import * as api from "@/api/client";
import { ApiError } from "@/api/client";
import { useAuthStore } from "@/stores/auth";
import { useAuthModalsStore } from "@/stores/auth-modals";
import { useToastStore } from "@/stores/toast";

import Button from "@/components/ui/Button.vue";
import Modal from "@/components/ui/Modal.vue";
import TextInput from "@/components/ui/TextInput.vue";

const auth = useAuthStore();
const modals = useAuthModalsStore();
const toasts = useToastStore();

const username = ref("");
const password = ref("");
const submitting = ref(false);
const error = ref<string | null>(null);
// Phase 2.9 — whether the instance accepts open signups. Drives the "Create
// account" link below the form. Refreshed every time the login modal opens
// so the admin toggling it shows up immediately on the next open.
const openRegistrationAvailable = ref(false);

watch(
  () => modals.loginOpen,
  async (open) => {
    if (open) {
      username.value = "";
      password.value = "";
      error.value = null;
      try {
        const status = await api.getRegistrationStatus();
        openRegistrationAvailable.value = status.open;
      } catch {
        openRegistrationAvailable.value = false;
      }
    }
  },
);

async function onSubmit(e: Event) {
  e.preventDefault();
  if (!username.value || !password.value) return;
  submitting.value = true;
  error.value = null;
  try {
    await auth.login(username.value, password.value);
    toasts.success(`Welcome back, ${auth.user?.username}.`);
    modals.closeAll();
    if (auth.user?.must_change_password) {
      modals.openChangePassword(true);
    }
  } catch (e) {
    error.value =
      e instanceof ApiError ? e.message : "Couldn't sign you in.";
  } finally {
    submitting.value = false;
  }
}

function switchToSignup() {
  modals.closeAll();
  modals.openSignup();
}

function switchToOpenSignup() {
  modals.closeAll();
  modals.openOpenSignup();
}
</script>

<template>
  <Modal
    :open="modals.loginOpen"
    size="sm"
    close-on-backdrop
    @close="modals.closeAll()"
  >
    <template #header>
      <div class="flex items-baseline gap-3">
        <h2 class="font-display text-xl font-medium tracking-tight text-fg">
          Welcome back
        </h2>
        <span
          class="font-mono text-[10px] uppercase tracking-[0.18em] text-fg-subtle"
        >
          Sign in
        </span>
      </div>
    </template>

    <form class="space-y-4" @submit="onSubmit">
      <TextInput
        v-model="username"
        label="Username"
        autocomplete="username"
        required
        autofocus
      />
      <TextInput
        v-model="password"
        type="password"
        label="Password"
        autocomplete="current-password"
        required
      />
      <p
        v-if="error"
        class="text-sm text-red-700 dark:text-red-300"
        role="alert"
      >
        {{ error }}
      </p>
      <Button type="submit" full :loading="submitting">
        Sign in
      </Button>

      <!-- Phase 2.9 — public signup link, only when the instance allows it.
           The invite-token flow stays accessible underneath as the
           "Have an invitation?" line so existing invite users keep their
           shortcut. -->
      <p
        v-if="openRegistrationAvailable"
        class="text-center text-xs text-fg-muted"
      >
        New here?
        <button
          type="button"
          class="ml-1 font-medium text-accent hover:underline"
          @click="switchToOpenSignup"
        >
          Create an account
        </button>
      </p>
      <p class="text-center text-xs text-fg-muted">
        Have an invitation?
        <button
          type="button"
          class="ml-1 font-medium text-accent hover:underline"
          @click="switchToSignup"
        >
          Use invite token
        </button>
      </p>
    </form>
  </Modal>
</template>
