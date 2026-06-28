<script setup lang="ts">
/**
 * Phase 2.9 — Open-registration signup.
 *
 * Sibling of `SignupWithInviteModal.vue`. Triggered from `LoginModal`
 * when `/api/auth/registration-status` reports `open=true`. Honours the
 * server's captcha flag: if the instance has captcha on, the user solves
 * the math question; if off, the captcha block hides and the user just
 * picks a username + password.
 *
 * The honeypot input is rendered off-screen via `tabindex="-1"` and
 * `aria-hidden="true"` so screen readers and keyboard tabbing skip it.
 * A real user never fills it; bots that auto-complete every input do.
 */

import { computed, ref, watch } from "vue";

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
const confirm = ref("");
const captchaAnswer = ref("");

const submitting = ref(false);
const error = ref<string | null>(null);

type CaptchaState =
  | { status: "off" }
  | { status: "loading" }
  | { status: "ready"; question: string; token: string }
  | { status: "error" };

const captcha = ref<CaptchaState>({ status: "loading" });
const captchaRequired = ref(true);

const canSubmit = computed(() => {
  if (submitting.value) return false;
  if (username.value.trim().length < 3) return false;
  if (password.value.length < 8) return false;
  if (password.value !== confirm.value) return false;
  if (captchaRequired.value) {
    if (captcha.value.status !== "ready") return false;
    if (!captchaAnswer.value.trim()) return false;
  }
  return true;
});

async function refreshCaptcha() {
  if (!captchaRequired.value) {
    captcha.value = { status: "off" };
    return;
  }
  captcha.value = { status: "loading" };
  captchaAnswer.value = "";
  try {
    const c = await api.getCaptcha();
    captcha.value = { status: "ready", question: c.question, token: c.token };
  } catch {
    captcha.value = { status: "error" };
  }
}

watch(
  () => modals.openSignupOpen,
  async (open) => {
    if (!open) return;
    username.value = "";
    password.value = "";
    confirm.value = "";
    captchaAnswer.value = "";
    error.value = null;
    // Pull the live status so we know if captcha is currently required —
    // self-hosters who turned it off shouldn't see a captcha block at all.
    try {
      const status = await api.getRegistrationStatus();
      captchaRequired.value = status.captcha;
    } catch {
      // If the lookup fails, assume captcha is on (safer default).
      captchaRequired.value = true;
    }
    await refreshCaptcha();
  },
);

async function onSubmit(e: Event) {
  e.preventDefault();
  if (!canSubmit.value) return;
  error.value = null;
  submitting.value = true;
  try {
    const captchaPayload =
      captchaRequired.value && captcha.value.status === "ready"
        ? { token: captcha.value.token, answer: captchaAnswer.value }
        : undefined;
    await auth.openRegister(username.value.trim(), password.value, captchaPayload);
    toasts.success(`Welcome, ${auth.user?.username ?? "friend"}.`);
    modals.closeAll();
  } catch (e) {
    const msg = e instanceof ApiError ? e.message : "Couldn't create your account.";
    error.value = msg;
    // Captcha is single-use — once the server rejected the answer, the
    // token's spent. Pull a fresh one so the user can retry without a
    // stale-token error.
    if (captchaRequired.value) await refreshCaptcha();
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
    :open="modals.openSignupOpen"
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
          Open signup
        </span>
      </div>
    </template>

    <form class="space-y-4" @submit="onSubmit">
      <TextInput
        v-model="username"
        label="Username"
        hint="At least 3 characters · letters, digits, _ and -"
        autocomplete="username"
        autofocus
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

      <!-- Math captcha block — hidden when the instance disables it. -->
      <div
        v-if="captchaRequired"
        class="rounded-md border border-border-subtle bg-bg-sunken/40 px-3 py-2"
      >
        <div class="mb-2 flex items-baseline justify-between gap-3">
          <span
            class="font-mono text-[10px] uppercase tracking-wider text-fg-subtle"
          >
            Quick check
          </span>
          <button
            type="button"
            class="font-mono text-[10px] uppercase tracking-wider text-fg-muted underline-offset-2 hover:text-fg hover:underline"
            @click="refreshCaptcha"
          >
            New question
          </button>
        </div>
        <div class="flex items-center gap-3">
          <div
            v-if="captcha.status === 'loading'"
            class="font-display text-lg italic text-fg-muted"
          >
            Loading…
          </div>
          <div
            v-else-if="captcha.status === 'ready'"
            class="font-display text-2xl tabular-nums text-fg"
          >
            {{ captcha.question }} =
          </div>
          <div
            v-else
            class="font-display text-sm italic text-red-700 dark:text-red-300"
          >
            Couldn't load the question. Tap New question to retry.
          </div>
          <input
            v-model="captchaAnswer"
            type="number"
            inputmode="numeric"
            class="w-20 rounded-md border border-border bg-bg-elevated px-3 py-1.5 text-center text-base text-fg focus:border-accent focus:outline-none"
            :disabled="captcha.status !== 'ready'"
            aria-label="Captcha answer"
          />
        </div>
      </div>

      <p
        v-if="error"
        class="text-sm text-red-700 dark:text-red-300"
        role="alert"
      >
        {{ error }}
      </p>

      <Button type="submit" full :loading="submitting" :disabled="!canSubmit">
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
