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

const oldPassword = ref("");
const newPassword = ref("");
const confirm = ref("");
const submitting = ref(false);
const error = ref<string | null>(null);

watch(
  () => modals.changePasswordOpen,
  (open) => {
    if (open) {
      oldPassword.value = "";
      newPassword.value = "";
      confirm.value = "";
      error.value = null;
    }
  },
);

async function onSubmit(e: Event) {
  e.preventDefault();
  if (submitting.value) return;
  error.value = null;

  if (newPassword.value.length < 8) {
    error.value = "New password must be at least 8 characters.";
    return;
  }
  if (newPassword.value !== confirm.value) {
    error.value = "Passwords don't match.";
    return;
  }

  submitting.value = true;
  try {
    await auth.changePassword(oldPassword.value, newPassword.value);
    toasts.success("Password updated.");
    modals.closeAll();
  } catch (e) {
    error.value =
      e instanceof ApiError ? e.message : "Couldn't change your password.";
  } finally {
    submitting.value = false;
  }
}

// Forced mode (after must_change_password login): hide the close button so the
// user must complete the change. Modal's close-on-backdrop is gated by the
// `close-on-backdrop` prop, which we don't pass when forced.
</script>

<template>
  <Modal
    :open="modals.changePasswordOpen"
    size="sm"
    :close-on-backdrop="!modals.changePasswordForced"
    @close="
      modals.changePasswordForced ? null : modals.closeAll()
    "
  >
    <template #header>
      <div class="flex items-baseline gap-3">
        <h2 class="font-display text-xl font-medium tracking-tight text-fg">
          {{ modals.changePasswordForced ? "Set a new password" : "Change password" }}
        </h2>
        <span
          class="font-mono text-[10px] uppercase tracking-[0.18em] text-fg-subtle"
        >
          {{ modals.changePasswordForced ? "Required" : "Account" }}
        </span>
      </div>
    </template>

    <p
      v-if="modals.changePasswordForced"
      class="mb-4 font-display text-sm italic leading-relaxed text-fg-muted"
    >
      Your account was created with a temporary password — pick something only
      you know before continuing.
    </p>

    <form class="space-y-4" @submit="onSubmit">
      <TextInput
        v-model="oldPassword"
        type="password"
        :label="modals.changePasswordForced ? 'Temporary password' : 'Current password'"
        autocomplete="current-password"
        required
        autofocus
      />
      <TextInput
        v-model="newPassword"
        type="password"
        label="New password"
        hint="At least 8 characters"
        autocomplete="new-password"
        required
      />
      <TextInput
        v-model="confirm"
        type="password"
        label="Confirm new password"
        autocomplete="new-password"
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
        Update password
      </Button>
      <button
        v-if="!modals.changePasswordForced"
        type="button"
        class="block w-full text-center text-xs text-fg-muted hover:text-fg"
        @click="modals.closeAll()"
      >
        Cancel
      </button>
    </form>
  </Modal>
</template>
