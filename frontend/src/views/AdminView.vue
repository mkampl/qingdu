<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";

import * as api from "@/api/client";
import { ApiError } from "@/api/client";
import type { AdminUserSummary } from "@/api/types";
import { useAuthStore } from "@/stores/auth";
import { useAuthModalsStore } from "@/stores/auth-modals";
import { useToastStore } from "@/stores/toast";

import Button from "@/components/ui/Button.vue";
import Modal from "@/components/ui/Modal.vue";
import Spinner from "@/components/ui/Spinner.vue";
import TextInput from "@/components/ui/TextInput.vue";

const auth = useAuthStore();
const authModals = useAuthModalsStore();
const toasts = useToastStore();
const router = useRouter();

type LoadState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "ok"; users: AdminUserSummary[] }
  | { status: "error"; message: string };

const state = ref<LoadState>({ status: "idle" });
const users = computed<AdminUserSummary[]>(() =>
  state.value.status === "ok" ? state.value.users : [],
);

async function load() {
  if (!auth.isAuthed) {
    state.value = { status: "idle" };
    return;
  }
  if (!auth.isAdmin) {
    state.value = { status: "error", message: "Admin access required." };
    return;
  }
  state.value = { status: "loading" };
  try {
    const result = await api.adminListUsers();
    state.value = { status: "ok", users: result };
  } catch (e) {
    state.value = {
      status: "error",
      message: e instanceof ApiError ? e.message : "Couldn't load users.",
    };
  }
}

onMounted(load);

function patchUser(id: number, patch: Partial<AdminUserSummary>) {
  if (state.value.status !== "ok") return;
  state.value = {
    status: "ok",
    users: state.value.users.map((u) => (u.id === id ? { ...u, ...patch } : u)),
  };
}
function removeUser(id: number) {
  if (state.value.status !== "ok") return;
  state.value = {
    status: "ok",
    users: state.value.users.filter((u) => u.id !== id),
  };
}

// --- Create user ---------------------------------------------------------

const createOpen = ref(false);
const createUsername = ref("");
const createPassword = ref("");
const creating = ref(false);
const createError = ref<string | null>(null);

function openCreate() {
  createUsername.value = "";
  createPassword.value = "";
  createError.value = null;
  createOpen.value = true;
}
async function submitCreate(e: Event) {
  e.preventDefault();
  if (creating.value) return;
  if (createPassword.value.length < 8) {
    createError.value = "Temporary password must be at least 8 characters.";
    return;
  }
  creating.value = true;
  createError.value = null;
  try {
    await api.adminCreateUser({
      username: createUsername.value.trim(),
      password: createPassword.value,
    });
    createOpen.value = false;
    toasts.success(`Created “${createUsername.value.trim()}”.`);
    await load();
  } catch (e) {
    createError.value =
      e instanceof ApiError ? e.message : "Couldn't create the user.";
  } finally {
    creating.value = false;
  }
}

// --- Delete user (inline two-step) ---------------------------------------

const pendingDeleteId = ref<number | null>(null);
const deletingId = ref<number | null>(null);

async function confirmDelete(user: AdminUserSummary) {
  if (deletingId.value !== null) return;
  deletingId.value = user.id;
  try {
    await api.adminDeleteUser(user.id);
    removeUser(user.id);
    toasts.success(`Deleted ${user.username}.`);
  } catch (e) {
    toasts.error(
      e instanceof ApiError ? e.message : "Couldn't delete the user.",
    );
  } finally {
    deletingId.value = null;
    pendingDeleteId.value = null;
  }
}

// --- Toggle admin --------------------------------------------------------

const togglingId = ref<number | null>(null);

async function toggleAdmin(user: AdminUserSummary) {
  if (togglingId.value !== null) return;
  // Self-toggle: backend returns a friendly 400, so we don't bother short-
  // circuiting on the client (auth.user doesn't carry the id field anyway).
  togglingId.value = user.id;
  try {
    await api.adminToggleAdmin(user.id);
    patchUser(user.id, { is_admin: !user.is_admin });
    toasts.success(
      user.is_admin
        ? `${user.username} is no longer admin.`
        : `${user.username} is now admin.`,
    );
  } catch (e) {
    toasts.error(
      e instanceof ApiError ? e.message : "Couldn't change admin status.",
    );
  } finally {
    togglingId.value = null;
  }
}

// --- Update invite quota -------------------------------------------------

const editingQuotaId = ref<number | null>(null);
const quotaDraft = ref<number>(0);
const savingQuotaId = ref<number | null>(null);

function beginEditQuota(user: AdminUserSummary) {
  editingQuotaId.value = user.id;
  quotaDraft.value = user.invite_quota;
}
async function commitQuota(user: AdminUserSummary) {
  if (savingQuotaId.value !== null) return;
  const target = Number(quotaDraft.value);
  if (Number.isNaN(target) || target < -1) {
    toasts.error("Quota must be -1 (unlimited) or any non-negative number.");
    return;
  }
  if (target === user.invite_quota) {
    editingQuotaId.value = null;
    return;
  }
  savingQuotaId.value = user.id;
  try {
    const result = await api.adminUpdateInviteQuota(user.id, target);
    patchUser(user.id, { invite_quota: result.invite_quota });
    toasts.success(`Quota for ${user.username} set to ${result.invite_quota}.`);
  } catch (e) {
    toasts.error(
      e instanceof ApiError ? e.message : "Couldn't update the quota.",
    );
  } finally {
    savingQuotaId.value = null;
    editingQuotaId.value = null;
  }
}

// --- Reset password ------------------------------------------------------

const resetOpen = ref(false);
const resetTarget = ref<AdminUserSummary | null>(null);
const resetPassword = ref("");
const resetting = ref(false);
const resetError = ref<string | null>(null);

function openReset(user: AdminUserSummary) {
  resetTarget.value = user;
  resetPassword.value = "";
  resetError.value = null;
  resetOpen.value = true;
}
async function submitReset(e: Event) {
  e.preventDefault();
  if (!resetTarget.value || resetting.value) return;
  if (resetPassword.value.length < 8) {
    resetError.value = "New password must be at least 8 characters.";
    return;
  }
  resetting.value = true;
  resetError.value = null;
  try {
    await api.adminResetPassword(resetTarget.value.id, resetPassword.value);
    toasts.success(`Password reset for ${resetTarget.value.username}.`);
    resetOpen.value = false;
  } catch (e) {
    resetError.value =
      e instanceof ApiError ? e.message : "Couldn't reset the password.";
  } finally {
    resetting.value = false;
  }
}

// --- Date helper ---------------------------------------------------------

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  } catch {
    return iso;
  }
}

// --- Phase 2.7 — Registration + lifecycle settings ------------------------

interface RegSettingsForm {
  registration_open: boolean;
  registration_per_ip_24h: number;
  registration_daily_cap: number;
  registration_captcha: boolean;
  lifecycle_soft_delete_days: number;
  lifecycle_hard_delete_days: number;
}

const regForm = ref<RegSettingsForm | null>(null);
const regLoading = ref(false);
const regSaving = ref(false);
const regError = ref<string | null>(null);
const lifecycleRunning = ref(false);

async function loadRegistrationSettings() {
  if (!auth.isAdmin) return;
  regLoading.value = true;
  regError.value = null;
  try {
    const s = await api.adminGetRegistrationSettings();
    regForm.value = {
      registration_open: s["registration.open"],
      registration_per_ip_24h: s["registration.per_ip_24h"],
      registration_daily_cap: s["registration.daily_cap"],
      registration_captcha: s["registration.captcha"],
      lifecycle_soft_delete_days: s["lifecycle.soft_delete_days"],
      lifecycle_hard_delete_days: s["lifecycle.hard_delete_days"],
    };
  } catch (e) {
    regError.value = e instanceof ApiError ? e.message : "Couldn't load settings.";
  } finally {
    regLoading.value = false;
  }
}

async function saveRegistrationSettings() {
  if (!regForm.value) return;
  regSaving.value = true;
  regError.value = null;
  try {
    const s = await api.adminPatchRegistrationSettings({ ...regForm.value });
    regForm.value = {
      registration_open: s["registration.open"],
      registration_per_ip_24h: s["registration.per_ip_24h"],
      registration_daily_cap: s["registration.daily_cap"],
      registration_captcha: s["registration.captcha"],
      lifecycle_soft_delete_days: s["lifecycle.soft_delete_days"],
      lifecycle_hard_delete_days: s["lifecycle.hard_delete_days"],
    };
    toasts.success("Settings saved.");
  } catch (e) {
    regError.value = e instanceof ApiError ? e.message : "Couldn't save settings.";
  } finally {
    regSaving.value = false;
  }
}

async function runLifecycleNow() {
  lifecycleRunning.value = true;
  try {
    const stats = await api.adminRunLifecycleNow();
    toasts.success(
      `Lifecycle pass: ${stats.soft_marked} marked dormant, ` +
        `${stats.hard_deleted} hard-deleted, ${stats.attempts_pruned} attempts pruned.`,
    );
    void load();
  } catch (e) {
    toasts.error(
      e instanceof ApiError ? e.message : "Lifecycle pass failed.",
    );
  } finally {
    lifecycleRunning.value = false;
  }
}

onMounted(() => {
  void loadRegistrationSettings();
});
</script>

<template>
  <section class="mx-auto max-w-5xl px-5 py-10 sm:px-8 md:py-14 lg:px-10">
    <header class="mb-8 flex items-baseline justify-between gap-4">
      <div class="flex items-baseline gap-3">
        <span
          class="font-mono text-[11px] font-medium uppercase tracking-[0.22em] text-accent"
        >
          Admin
        </span>
        <span class="h-px w-12 bg-border-subtle" aria-hidden="true" />
        <h1 class="font-display text-2xl font-medium tracking-tight text-fg">
          Users
        </h1>
      </div>
      <div class="flex items-baseline gap-3">
        <span
          v-if="state.status === 'ok'"
          class="font-mono text-[10px] uppercase tracking-wider text-fg-subtle"
        >
          {{ users.length }} {{ users.length === 1 ? "account" : "accounts" }}
        </span>
        <Button
          v-if="auth.isAdmin"
          variant="primary"
          size="sm"
          @click="openCreate"
        >
          + New user
        </Button>
      </div>
    </header>

    <!-- Anonymous / non-admin gating -->
    <div
      v-if="!auth.isAuthed"
      class="rounded-lg border border-border-subtle bg-bg-elevated p-8 text-center"
    >
      <p class="font-display text-lg italic leading-relaxed text-fg-muted">
        Sign in to access the admin panel.
      </p>
      <Button
        variant="primary"
        size="sm"
        class="mt-4"
        @click="authModals.openLogin()"
      >
        Sign in
      </Button>
    </div>

    <div
      v-else-if="!auth.isAdmin"
      class="rounded-lg border border-border-subtle bg-bg-elevated p-8"
    >
      <p class="font-display text-lg italic leading-relaxed text-fg-muted">
        This area is for administrators only.
      </p>
      <Button
        variant="secondary"
        size="sm"
        class="mt-4"
        @click="router.push('/')"
      >
        Back to reader
      </Button>
    </div>

    <!-- Loading / error -->
    <div
      v-else-if="state.status === 'loading'"
      class="flex items-center gap-3 text-fg-muted"
    >
      <Spinner size="sm" />
      <span class="font-display italic">Loading users…</span>
    </div>

    <div
      v-else-if="state.status === 'error'"
      class="rounded-md border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-800 dark:border-red-900 dark:bg-red-950/40 dark:text-red-200"
      role="alert"
    >
      {{ state.message }}
    </div>

    <!-- User table -->
    <div
      v-else-if="state.status === 'ok'"
      class="overflow-x-auto rounded-lg border border-border-subtle bg-bg-elevated"
    >
      <table class="min-w-full divide-y divide-border-subtle">
        <thead>
          <tr
            class="bg-bg-sunken text-left font-mono text-[10px] uppercase tracking-wider text-fg-subtle"
          >
            <th class="px-5 py-2.5">User</th>
            <th class="px-5 py-2.5">Role</th>
            <th class="px-5 py-2.5">Invite quota</th>
            <th class="hidden px-5 py-2.5 lg:table-cell">Last active</th>
            <th class="hidden px-5 py-2.5 sm:table-cell">Joined</th>
            <th class="px-5 py-2.5 text-right">Actions</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-border-subtle">
          <tr v-for="user in users" :key="user.id">
            <td class="px-5 py-3">
              <span class="font-display text-base text-fg">
                {{ user.username }}
              </span>
              <span
                v-if="user.username === auth.user?.username"
                class="ml-1.5 font-mono text-[9px] uppercase tracking-wider text-fg-subtle"
              >
                you
              </span>
            </td>
            <td class="px-5 py-3">
              <span
                v-if="user.is_admin"
                class="inline-flex items-center gap-1 rounded-full bg-accent/15 px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider text-accent"
              >
                Admin
              </span>
              <span
                v-else
                class="font-mono text-[10px] uppercase tracking-wider text-fg-subtle"
              >
                User
              </span>
            </td>
            <td class="px-5 py-3">
              <template v-if="editingQuotaId === user.id">
                <div class="flex items-center gap-1">
                  <input
                    v-model.number="quotaDraft"
                    type="number"
                    min="-1"
                    class="w-20 rounded border border-border-subtle bg-bg-elevated px-2 py-0.5 text-sm text-fg focus:border-accent focus:outline-none"
                    @keydown.enter.prevent="commitQuota(user)"
                    @keydown.escape.prevent="editingQuotaId = null"
                  />
                  <Button
                    variant="primary"
                    size="sm"
                    :loading="savingQuotaId === user.id"
                    @click="commitQuota(user)"
                  >
                    Save
                  </Button>
                </div>
              </template>
              <button
                v-else
                type="button"
                class="font-mono text-xs text-fg hover:text-accent"
                @click="beginEditQuota(user)"
                :title="'Click to edit'"
              >
                {{ user.invite_quota === -1 ? "∞ unlimited" : user.invite_quota }}
              </button>
            </td>
            <td class="hidden px-5 py-3 text-sm text-fg-muted lg:table-cell">
              {{ formatDate(user.last_active) }}
            </td>
            <td class="hidden px-5 py-3 text-sm text-fg-muted sm:table-cell">
              {{ formatDate(user.created_at) }}
            </td>
            <td class="px-5 py-3 text-right">
              <div class="inline-flex items-center gap-1">
                <Button
                  variant="ghost"
                  size="sm"
                  @click="openReset(user)"
                  :title="'Reset password'"
                >
                  Reset
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  :loading="togglingId === user.id"
                  @click="toggleAdmin(user)"
                  :title="user.is_admin ? 'Remove admin' : 'Make admin'"
                >
                  {{ user.is_admin ? "Demote" : "Promote" }}
                </Button>
                <template v-if="pendingDeleteId === user.id">
                  <button
                    type="button"
                    class="font-mono text-[10px] uppercase tracking-wider text-fg-subtle hover:text-fg"
                    @click="pendingDeleteId = null"
                    :disabled="deletingId === user.id"
                  >
                    Cancel
                  </button>
                  <Button
                    variant="danger"
                    size="sm"
                    :loading="deletingId === user.id"
                    @click="confirmDelete(user)"
                  >
                    Delete
                  </Button>
                </template>
                <Button
                  v-else
                  variant="danger"
                  size="sm"
                  :disabled="user.is_admin"
                  :title="user.is_admin ? 'Demote first to delete' : 'Delete user'"
                  @click="pendingDeleteId = user.id"
                >
                  Delete
                </Button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Phase 2.7 — Registration & lifecycle. Sits below the user table
         because the controls are instance-wide; the toggles drive behaviour
         in the open signup flow + the soft/hard delete scheduler. Only
         rendered for admins, gated on the same auth checks as the table. -->
    <div
      v-if="auth.isAdmin"
      class="mt-12 rounded-lg border border-border-subtle bg-bg-elevated p-6"
    >
      <div class="mb-5 flex items-baseline justify-between gap-3">
        <div class="flex items-baseline gap-3">
          <span
            class="font-mono text-[11px] uppercase tracking-[0.22em] text-accent"
          >
            Instance
          </span>
          <span class="h-px w-12 bg-border-subtle" aria-hidden="true" />
          <h2 class="font-display text-xl font-medium tracking-tight text-fg">
            Registration &amp; lifecycle
          </h2>
        </div>
        <Button
          variant="ghost"
          size="sm"
          :loading="lifecycleRunning"
          :disabled="
            !regForm ||
            (regForm.lifecycle_soft_delete_days === 0 &&
              regForm.lifecycle_hard_delete_days === 0)
          "
          @click="runLifecycleNow"
        >
          Run sweep now
        </Button>
      </div>

      <div v-if="regLoading" class="flex items-center gap-3 text-fg-muted">
        <Spinner size="sm" />
        <span class="font-display italic">Loading settings…</span>
      </div>

      <div
        v-else-if="regError"
        class="rounded-md border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-800 dark:border-red-900 dark:bg-red-950/40 dark:text-red-200"
        role="alert"
      >
        {{ regError }}
      </div>

      <form
        v-else-if="regForm"
        class="grid gap-5 sm:grid-cols-2"
        @submit.prevent="saveRegistrationSettings"
      >
        <!-- Registration master toggle. The four follow-on inputs are
             still editable when off (defensible: the admin may be staging
             a config), just visually de-emphasised. -->
        <label class="flex cursor-pointer items-start gap-3 rounded-md border border-border-subtle px-3 py-3 transition-colors hover:bg-bg-sunken sm:col-span-2">
          <input
            v-model="regForm.registration_open"
            type="checkbox"
            class="mt-1 accent-accent"
          />
          <span class="flex-1">
            <span class="block font-display text-base text-fg">
              Open registration
            </span>
            <span class="block text-xs text-fg-muted">
              Lets anyone create an account on this instance. Off by default;
              the maintainer's demo at qingdu.itvoodoo.at runs it on.
            </span>
          </span>
        </label>

        <label class="flex flex-col gap-1">
          <span class="font-mono text-[10px] uppercase tracking-wider text-fg-subtle">
            Per-IP limit / 24 h
          </span>
          <input
            v-model.number="regForm.registration_per_ip_24h"
            type="number"
            min="0"
            max="100"
            :disabled="!regForm.registration_open"
            class="w-32 rounded-md border border-border bg-bg-elevated px-3 py-1.5 text-sm text-fg focus:border-accent focus:outline-none disabled:opacity-50"
          />
          <span class="text-xs text-fg-muted">
            0 = unlimited. Failed attempts count toward the cap.
          </span>
        </label>

        <label class="flex flex-col gap-1">
          <span class="font-mono text-[10px] uppercase tracking-wider text-fg-subtle">
            Global daily cap
          </span>
          <input
            v-model.number="regForm.registration_daily_cap"
            type="number"
            min="0"
            max="10000"
            :disabled="!regForm.registration_open"
            class="w-32 rounded-md border border-border bg-bg-elevated px-3 py-1.5 text-sm text-fg focus:border-accent focus:outline-none disabled:opacity-50"
          />
          <span class="text-xs text-fg-muted">
            Successful signups per 24 h. 0 = unlimited.
          </span>
        </label>

        <label class="flex cursor-pointer items-start gap-3 rounded-md border border-border-subtle px-3 py-2 transition-colors hover:bg-bg-sunken sm:col-span-2">
          <input
            v-model="regForm.registration_captcha"
            type="checkbox"
            :disabled="!regForm.registration_open"
            class="mt-1 accent-accent disabled:opacity-50"
          />
          <span class="flex-1">
            <span class="block font-display text-base text-fg">
              Math captcha on signup
            </span>
            <span class="block text-xs text-fg-muted">
              Server-issued, no external script. Blocks the casual spam-bot
              wave without leaking anything to a third party.
            </span>
          </span>
        </label>

        <!-- Lifecycle thresholds. These are separate from registration —
             a self-hoster can run open registration without any cleanup
             (storage is cheap) or run invite-only with a cleanup pass
             for old test accounts. -->
        <div class="sm:col-span-2 border-t border-border-subtle pt-4">
          <span class="font-mono text-[10px] uppercase tracking-wider text-fg-subtle">
            Lifecycle cleanup
          </span>
          <p class="mt-1 text-xs text-fg-muted">
            Inactivity is measured against the last authenticated request
            (every app open touches it). Admins are never auto-deleted.
            Set both to 0 to disable the sweep entirely.
          </p>
        </div>

        <label class="flex flex-col gap-1">
          <span class="font-mono text-[10px] uppercase tracking-wider text-fg-subtle">
            Soft-delete after (days)
          </span>
          <input
            v-model.number="regForm.lifecycle_soft_delete_days"
            type="number"
            min="0"
            max="3650"
            class="w-32 rounded-md border border-border bg-bg-elevated px-3 py-1.5 text-sm text-fg focus:border-accent focus:outline-none"
          />
          <span class="text-xs text-fg-muted">
            Marks the account dormant. 0 = disabled.
          </span>
        </label>

        <label class="flex flex-col gap-1">
          <span class="font-mono text-[10px] uppercase tracking-wider text-fg-subtle">
            Hard-delete after (days)
          </span>
          <input
            v-model.number="regForm.lifecycle_hard_delete_days"
            type="number"
            min="0"
            max="3650"
            class="w-32 rounded-md border border-border bg-bg-elevated px-3 py-1.5 text-sm text-fg focus:border-accent focus:outline-none"
          />
          <span class="text-xs text-fg-muted">
            Deletes the account + all data. 0 = disabled. Must be ≥ soft.
          </span>
        </label>

        <div class="sm:col-span-2 flex items-center justify-end gap-3">
          <Button
            variant="primary"
            size="sm"
            type="submit"
            :loading="regSaving"
          >
            Save settings
          </Button>
        </div>
      </form>
    </div>

    <!-- Create user modal -->
    <Modal
      :open="createOpen"
      size="sm"
      close-on-backdrop
      @close="createOpen = false"
    >
      <template #header>
        <h2 class="font-display text-xl font-medium tracking-tight text-fg">
          New user
        </h2>
      </template>
      <form class="space-y-4" @submit="submitCreate">
        <TextInput
          v-model="createUsername"
          label="Username"
          autocomplete="off"
          autofocus
          required
        />
        <TextInput
          v-model="createPassword"
          type="password"
          label="Temporary password"
          hint="The user must change this on first sign-in"
          autocomplete="new-password"
          required
        />
        <p
          v-if="createError"
          class="text-sm text-red-700 dark:text-red-300"
          role="alert"
        >
          {{ createError }}
        </p>
        <div class="flex items-center justify-end gap-2">
          <Button
            variant="ghost"
            size="sm"
            type="button"
            @click="createOpen = false"
          >
            Cancel
          </Button>
          <Button
            variant="primary"
            size="sm"
            type="submit"
            :loading="creating"
            :disabled="!createUsername.trim() || !createPassword"
          >
            Create user
          </Button>
        </div>
      </form>
    </Modal>

    <!-- Reset password modal -->
    <Modal
      :open="resetOpen"
      size="sm"
      close-on-backdrop
      @close="resetOpen = false"
    >
      <template #header>
        <h2 class="font-display text-xl font-medium tracking-tight text-fg">
          Reset password
          <span
            class="ml-2 font-mono text-[10px] uppercase tracking-wider text-fg-subtle"
          >
            {{ resetTarget?.username }}
          </span>
        </h2>
      </template>
      <form class="space-y-4" @submit="submitReset">
        <TextInput
          v-model="resetPassword"
          type="password"
          label="New temporary password"
          hint="At least 8 characters. The user will be required to change it on next sign-in."
          autocomplete="new-password"
          autofocus
          required
        />
        <p
          v-if="resetError"
          class="text-sm text-red-700 dark:text-red-300"
          role="alert"
        >
          {{ resetError }}
        </p>
        <div class="flex items-center justify-end gap-2">
          <Button
            variant="ghost"
            size="sm"
            type="button"
            @click="resetOpen = false"
          >
            Cancel
          </Button>
          <Button
            variant="primary"
            size="sm"
            type="submit"
            :loading="resetting"
            :disabled="!resetPassword"
          >
            Reset password
          </Button>
        </div>
      </form>
    </Modal>
  </section>
</template>
