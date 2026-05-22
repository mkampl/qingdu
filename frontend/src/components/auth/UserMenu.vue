<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from "vue";
import { useRouter } from "vue-router";

import { useAuthStore } from "@/stores/auth";
import { useAuthModalsStore } from "@/stores/auth-modals";
import { useToastStore } from "@/stores/toast";

const auth = useAuthStore();
const modals = useAuthModalsStore();
const toasts = useToastStore();
const router = useRouter();

const open = ref(false);
const rootRef = ref<HTMLElement | null>(null);

function toggle() {
  open.value = !open.value;
}
function close() {
  open.value = false;
}

function onDocumentClick(e: MouseEvent) {
  if (!open.value) return;
  const target = e.target as Node;
  if (rootRef.value && !rootRef.value.contains(target)) {
    open.value = false;
  }
}
function onKey(e: KeyboardEvent) {
  if (e.key === "Escape") open.value = false;
}
onMounted(() => {
  document.addEventListener("click", onDocumentClick);
  document.addEventListener("keydown", onKey);
});
onBeforeUnmount(() => {
  document.removeEventListener("click", onDocumentClick);
  document.removeEventListener("keydown", onKey);
});

function openChangePassword() {
  close();
  modals.openChangePassword();
}

function goAdmin() {
  close();
  void router.push("/admin");
}

async function logout() {
  close();
  await auth.logout();
  toasts.info("Signed out.");
}
</script>

<template>
  <div ref="rootRef" class="relative">
    <button
      type="button"
      class="inline-flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-sm text-fg-muted hover:text-fg hover:bg-bg-sunken focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
      :aria-expanded="open"
      aria-haspopup="menu"
      @click="toggle"
    >
      <span class="font-medium text-fg">{{ auth.user?.username }}</span>
      <svg
        width="10"
        height="10"
        viewBox="0 0 10 10"
        fill="none"
        class="text-fg-subtle transition-transform"
        :class="{ 'rotate-180': open }"
      >
        <path
          d="M2 3.5l3 3 3-3"
          stroke="currentColor"
          stroke-width="1.4"
          stroke-linecap="round"
          stroke-linejoin="round"
        />
      </svg>
    </button>

    <Transition
      enter-active-class="transition duration-150 ease-out"
      enter-from-class="opacity-0 -translate-y-1 scale-95"
      enter-to-class="opacity-100 translate-y-0 scale-100"
      leave-active-class="transition duration-100 ease-in"
      leave-from-class="opacity-100"
      leave-to-class="opacity-0"
    >
      <div
        v-if="open"
        role="menu"
        class="absolute right-0 z-40 mt-1.5 w-56 origin-top-right overflow-hidden rounded-md bg-bg-elevated shadow-lg ring-1 ring-border"
      >
        <!-- Identity strip -->
        <div class="border-b border-border-subtle px-4 py-3">
          <p
            class="font-mono text-[10px] uppercase tracking-[0.18em] text-fg-subtle"
          >
            Signed in as
          </p>
          <p class="mt-1 truncate font-display text-base text-fg">
            {{ auth.user?.username }}
          </p>
          <p
            v-if="auth.user?.is_admin"
            class="mt-0.5 font-mono text-[10px] uppercase tracking-wider text-accent"
          >
            Administrator
          </p>
        </div>

        <div class="py-1">
          <button
            type="button"
            role="menuitem"
            class="block w-full px-4 py-2 text-left text-sm text-fg hover:bg-bg-sunken"
            @click="openChangePassword"
          >
            Change password
          </button>
          <button
            v-if="auth.user?.is_admin"
            type="button"
            role="menuitem"
            class="block w-full px-4 py-2 text-left text-sm text-fg hover:bg-bg-sunken"
            @click="goAdmin"
          >
            Admin panel
            <span
              class="ml-1 font-mono text-[9px] uppercase tracking-wider text-fg-subtle"
            >
              soon
            </span>
          </button>
        </div>

        <div class="border-t border-border-subtle py-1">
          <button
            type="button"
            role="menuitem"
            class="block w-full px-4 py-2 text-left text-sm text-fg-muted hover:bg-bg-sunken hover:text-fg"
            @click="logout"
          >
            Sign out
          </button>
        </div>
      </div>
    </Transition>
  </div>
</template>
