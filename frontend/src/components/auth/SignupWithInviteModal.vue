<script setup lang="ts">
import { computed, ref, watch } from "vue";
// `computed` is used by reasonLabel below — keep the import.

import { ApiError, apiUrl } from "@/api/client";
import { useAuthStore } from "@/stores/auth";
import { useAuthModalsStore } from "@/stores/auth-modals";
import { useToastStore } from "@/stores/toast";

import Button from "@/components/ui/Button.vue";
import Modal from "@/components/ui/Modal.vue";
import TextInput from "@/components/ui/TextInput.vue";

const auth = useAuthStore();
const modals = useAuthModalsStore();
const toasts = useToastStore();

const token = ref("");
const username = ref("");
const password = ref("");
const confirm = ref("");
const submitting = ref(false);
const error = ref<string | null>(null);

type InviteState =
  | { status: "idle" }
  | { status: "checking" }
  | { status: "valid"; invitedBy: string; expiresAt: string }
  | { status: "invalid"; reason: string };

const inviteState = ref<InviteState>({ status: "idle" });

watch(
  () => modals.signupOpen,
  (open) => {
    if (open) {
      token.value = modals.signupInviteToken ?? "";
      username.value = "";
      password.value = "";
      confirm.value = "";
      error.value = null;
      inviteState.value = { status: "idle" };
      if (token.value) void validateInvite(token.value);
    }
  },
);

let validateAbort: AbortController | null = null;
async function validateInvite(t: string) {
  if (!t) {
    inviteState.value = { status: "idle" };
    return;
  }
  if (validateAbort) validateAbort.abort();
  validateAbort = new AbortController();
  inviteState.value = { status: "checking" };
  try {
    // Tiny inline call rather than expanding the client.ts surface area —
    // this endpoint is only useful from this one modal.
    const response = await fetch(
      apiUrl(`/api/invitations/validate/${encodeURIComponent(t)}`),
      { signal: validateAbort.signal },
    );
    if (!response.ok) {
      inviteState.value = { status: "invalid", reason: "not_found" };
      return;
    }
    const data = await response.json();
    if (data.valid) {
      inviteState.value = {
        status: "valid",
        invitedBy: data.invited_by,
        expiresAt: data.expires_at,
      };
    } else {
      inviteState.value = {
        status: "invalid",
        reason: data.reason ?? "invalid",
      };
    }
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") return;
    inviteState.value = { status: "invalid", reason: "network" };
  }
}

function onTokenInput(v: string) {
  token.value = v;
  void validateInvite(v.trim());
}

const reasonLabel = computed(() => {
  if (inviteState.value.status !== "invalid") return "";
  switch (inviteState.value.reason) {
    case "not_found":
      return "We couldn't find that invitation.";
    case "already_used":
      return "This invitation has already been claimed.";
    case "expired":
      return "This invitation has expired.";
    case "network":
      return "Couldn't reach the server to verify the invite.";
    default:
      return "This invitation isn't valid.";
  }
});

async function onSubmit(e: Event) {
  e.preventDefault();
  if (submitting.value) return;
  error.value = null;

  if (!token.value.trim()) {
    error.value = "Paste your invitation token first.";
    return;
  }
  if (inviteState.value.status === "invalid") {
    error.value = reasonLabel.value;
    return;
  }
  if (password.value.length < 8) {
    error.value = "Password must be at least 8 characters.";
    return;
  }
  if (password.value !== confirm.value) {
    error.value = "Passwords don't match.";
    return;
  }

  submitting.value = true;
  try {
    await auth.signupWithInvite(
      token.value.trim(),
      username.value,
      password.value,
    );
    toasts.success("Welcome aboard.");
    modals.closeAll();
  } catch (e) {
    error.value =
      e instanceof ApiError ? e.message : "Couldn't create your account.";
  } finally {
    submitting.value = false;
  }
}

function switchToLogin() {
  modals.closeAll();
  modals.openLogin();
}
</script>

<template>
  <Modal
    :open="modals.signupOpen"
    size="sm"
    close-on-backdrop
    @close="modals.closeAll()"
  >
    <template #header>
      <div class="flex items-baseline gap-3">
        <h2 class="font-display text-xl font-medium tracking-tight text-fg">
          Create your account
        </h2>
        <span
          class="font-mono text-[10px] uppercase tracking-[0.18em] text-fg-subtle"
        >
          Invite-only
        </span>
      </div>
    </template>

    <form class="space-y-4" @submit="onSubmit">
      <div>
        <TextInput
          :model-value="token"
          label="Invitation token"
          :hint="
            inviteState.status === 'valid'
              ? `Invited by ${inviteState.invitedBy}`
              : 'Paste the token from your invite link'
          "
          :error="inviteState.status === 'invalid' ? reasonLabel : null"
          :required="true"
          autocomplete="off"
          @update:model-value="onTokenInput"
        />
        <p
          v-if="inviteState.status === 'checking'"
          class="mt-1 font-mono text-[10px] uppercase tracking-wider text-fg-subtle"
        >
          Verifying…
        </p>
      </div>

      <TextInput
        v-model="username"
        label="Username"
        hint="At least 3 characters"
        autocomplete="username"
        required
      />
      <TextInput
        v-model="password"
        type="password"
        label="Password"
        hint="At least 8 characters"
        autocomplete="new-password"
        required
      />
      <TextInput
        v-model="confirm"
        type="password"
        label="Confirm password"
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

      <Button
        type="submit"
        full
        :loading="submitting"
        :disabled="inviteState.status !== 'valid'"
      >
        Create account
      </Button>

      <p class="text-center text-xs text-fg-muted">
        Already have an account?
        <button
          type="button"
          class="ml-1 font-medium text-accent hover:underline"
          @click="switchToLogin"
        >
          Sign in
        </button>
      </p>
    </form>
  </Modal>
</template>
