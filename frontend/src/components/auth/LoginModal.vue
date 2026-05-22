<script setup lang="ts">
import { ref, watch } from "vue";

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

watch(
  () => modals.loginOpen,
  (open) => {
    if (open) {
      username.value = "";
      password.value = "";
      error.value = null;
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
      <p class="text-center text-xs text-fg-muted">
        Have an invitation?
        <button
          type="button"
          class="ml-1 font-medium text-accent hover:underline"
          @click="switchToSignup"
        >
          Create account
        </button>
      </p>
    </form>
  </Modal>
</template>
