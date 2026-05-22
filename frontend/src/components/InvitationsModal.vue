<script setup lang="ts">
import { ref, watch } from "vue";

import * as api from "@/api/client";
import { ApiError } from "@/api/client";
import type { InvitationSummary } from "@/api/types";
import { useAppModalsStore } from "@/stores/app-modals";
import { useAuthStore } from "@/stores/auth";
import { useToastStore } from "@/stores/toast";

import Button from "@/components/ui/Button.vue";
import Modal from "@/components/ui/Modal.vue";
import Spinner from "@/components/ui/Spinner.vue";

const auth = useAuthStore();
const modals = useAppModalsStore();
const toasts = useToastStore();

type LoadState =
  | { status: "idle" }
  | { status: "loading" }
  | {
      status: "ok";
      invitations: InvitationSummary[];
      quota: { total: number; used: number; remaining: number };
    }
  | { status: "error"; message: string };

const state = ref<LoadState>({ status: "idle" });
const generating = ref(false);

async function load() {
  state.value = { status: "loading" };
  try {
    const data = await api.myInvitations();
    state.value = {
      status: "ok",
      invitations: data.invitations,
      quota: data.quota,
    };
  } catch (e) {
    state.value = {
      status: "error",
      message: e instanceof ApiError ? e.message : "Couldn't load invitations.",
    };
  }
}

// Lazy-load when the modal opens.
watch(
  () => modals.invitationsOpen,
  (open) => {
    if (open && auth.isAuthed) void load();
  },
);

async function generateInvite() {
  if (generating.value) return;
  generating.value = true;
  try {
    await api.generateInvitation();
    toasts.success("Invitation created.");
    await load();
  } catch (e) {
    toasts.error(
      e instanceof ApiError ? e.message : "Couldn't create an invitation.",
    );
  } finally {
    generating.value = false;
  }
}

async function copyInviteUrl(invitation: InvitationSummary) {
  // The SPA picks up the `invite` query param via AuthControls regardless of
  // path; keep the URL on the root so it stays clean. (Legacy /v2/?invite=…
  // links still resolve thanks to the backend's 301 redirect.)
  const origin = window.location.origin;
  const url = `${origin}/?invite=${invitation.full_token}`;
  try {
    await navigator.clipboard.writeText(url);
    toasts.success("Invite link copied.");
  } catch {
    toasts.error("Couldn't copy — your browser blocked clipboard access.");
  }
}

const statusColor = (status: InvitationSummary["status"]) => {
  switch (status) {
    case "claimed":
      return "text-emerald-700 dark:text-emerald-300";
    case "expired":
      return "text-fg-subtle";
    default:
      return "text-accent";
  }
};

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

const quotaLabel = (state: LoadState) => {
  if (state.status !== "ok") return "";
  const { total, used, remaining } = state.quota;
  if (total === -1) return `${used} sent · unlimited`;
  return `${used} of ${total} used · ${remaining} remaining`;
};

const canGenerate = (state: LoadState) => {
  if (state.status !== "ok") return false;
  return state.quota.total === -1 || state.quota.remaining > 0;
};
</script>

<template>
  <Modal
    :open="modals.invitationsOpen"
    size="lg"
    close-on-backdrop
    @close="modals.closeAll()"
  >
    <template #header>
      <div class="flex items-baseline gap-3">
        <h2 class="font-display text-xl font-medium tracking-tight text-fg">
          My invitations
        </h2>
        <span
          v-if="state.status === 'ok'"
          class="font-mono text-[10px] uppercase tracking-[0.18em] text-fg-subtle"
        >
          {{ quotaLabel(state) }}
        </span>
      </div>
    </template>

    <div class="space-y-5">
      <!-- Generate row -->
      <div
        class="flex items-center justify-between gap-3 rounded-md border border-border-subtle bg-bg-sunken px-4 py-3"
      >
        <div class="flex-1">
          <p class="font-display text-base text-fg">
            Send someone an invite link.
          </p>
          <p class="text-xs text-fg-muted">
            Links expire after 30 days. Each invitation can be used once.
          </p>
        </div>
        <Button
          variant="primary"
          size="sm"
          :loading="generating"
          :disabled="!canGenerate(state)"
          @click="generateInvite"
        >
          + New invite
        </Button>
      </div>

      <!-- Body -->
      <div
        v-if="state.status === 'loading'"
        class="flex items-center gap-3 py-4 text-fg-muted"
      >
        <Spinner size="sm" />
        <span class="font-display italic">Loading invitations…</span>
      </div>

      <div
        v-else-if="state.status === 'error'"
        class="rounded-md border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-800 dark:border-red-900 dark:bg-red-950/40 dark:text-red-200"
        role="alert"
      >
        {{ state.message }}
      </div>

      <div
        v-else-if="state.status === 'ok' && state.invitations.length === 0"
        class="rounded-md border border-dashed border-border bg-bg-elevated px-4 py-6 text-center text-sm italic text-fg-muted"
      >
        No invitations yet. Generate one to share with someone.
      </div>

      <ul
        v-else-if="state.status === 'ok'"
        class="divide-y divide-border-subtle overflow-hidden rounded-md border border-border-subtle"
      >
        <li
          v-for="inv in state.invitations"
          :key="inv.id"
          class="flex items-center gap-3 bg-bg-elevated px-4 py-3 text-sm"
        >
          <div class="min-w-0 flex-1">
            <p class="flex items-center gap-2">
              <span
                class="font-mono text-[10px] uppercase tracking-wider"
                :class="statusColor(inv.status)"
              >
                {{ inv.status }}
              </span>
              <span class="text-fg-subtle">·</span>
              <span class="font-mono text-xs text-fg">
                {{ inv.token }}
              </span>
            </p>
            <p class="mt-0.5 text-xs text-fg-muted">
              <template v-if="inv.status === 'claimed'">
                Claimed by
                <span class="text-fg">{{ inv.claimed_by ?? "?" }}</span>
                on {{ inv.claimed_at ? formatDate(inv.claimed_at) : "?" }}
              </template>
              <template v-else-if="inv.status === 'expired'">
                Expired {{ formatDate(inv.expires_at) }}
              </template>
              <template v-else>
                Expires {{ formatDate(inv.expires_at) }}
              </template>
            </p>
          </div>
          <Button
            v-if="inv.status === 'pending'"
            variant="secondary"
            size="sm"
            @click="copyInviteUrl(inv)"
          >
            Copy link
          </Button>
        </li>
      </ul>
    </div>
  </Modal>
</template>
