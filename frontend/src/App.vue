<script setup lang="ts">
import { onMounted, ref, watch } from "vue";
import { RouterLink, RouterView, useRoute } from "vue-router";

import { useAppModalsStore } from "@/stores/app-modals";
import { useAuthStore } from "@/stores/auth";
import { useReviewStore } from "@/stores/review";
import { useSettingsStore } from "@/stores/settings";
import { useShortcutsStore } from "@/stores/shortcuts";
import { useUserWordsStore } from "@/stores/userWords";

import AuthControls from "@/components/auth/AuthControls.vue";
import InvitationsModal from "@/components/InvitationsModal.vue";
import SettingsModal from "@/components/SettingsModal.vue";
import ShortcutsOverlay from "@/components/ShortcutsOverlay.vue";
import Toaster from "@/components/ui/Toaster.vue";

import { useKeyboardShortcuts } from "@/composables/use-keyboard-shortcuts";

const settings = useSettingsStore();
const auth = useAuthStore();
const modals = useAppModalsStore();
const shortcuts = useShortcutsStore();
const userWords = useUserWordsStore();
const review = useReviewStore();
const route = useRoute();

function compactNumber(n: number): string {
  if (n < 1000) return n.toLocaleString();
  if (n < 10_000) return `${(n / 1000).toFixed(1).replace(/\.0$/, "")}k`;
  return `${Math.round(n / 1000)}k`;
}

useKeyboardShortcuts();

// Mobile nav drawer state — visible only via the hamburger on narrow viewports.
const mobileNavOpen = ref(false);

watch(
  () => route.fullPath,
  () => {
    // Close on any navigation so a tap on a drawer link doesn't leave the
    // drawer open over the new view.
    mobileNavOpen.value = false;
  },
);

function onDrawerKeydown(e: KeyboardEvent) {
  if (e.key === "Escape") mobileNavOpen.value = false;
}

watch(mobileNavOpen, (open) => {
  if (typeof document === "undefined") return;
  document.body.style.overflow = open ? "hidden" : "";
  if (open) {
    document.addEventListener("keydown", onDrawerKeydown);
  } else {
    document.removeEventListener("keydown", onDrawerKeydown);
  }
});

onMounted(async () => {
  settings.hydrate();
  await auth.hydrate();
});
</script>

<template>
  <div class="flex h-full flex-col">
    <header class="border-b border-border bg-bg-elevated">
      <div class="mx-auto flex max-w-6xl items-center gap-3 px-4 py-3 sm:gap-6 sm:px-6">
        <!-- Hamburger — only visible below sm (where the inline nav is hidden). -->
        <button
          type="button"
          class="-ml-1 inline-flex items-center justify-center rounded-md p-2 text-fg-muted hover:text-fg hover:bg-bg-sunken focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent sm:hidden"
          :aria-expanded="mobileNavOpen"
          aria-label="Open navigation menu"
          aria-controls="mobile-nav-drawer"
          @click="mobileNavOpen = true"
        >
          <svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden="true">
            <path
              d="M3 5h12M3 9h12M3 13h12"
              stroke="currentColor"
              stroke-width="1.6"
              stroke-linecap="round"
            />
          </svg>
        </button>

        <RouterLink
          to="/"
          class="text-cn text-xl font-semibold tracking-tight"
        >
          轻读 <span class="text-fg-muted font-normal">QingDu</span>
        </RouterLink>
        <nav class="hidden gap-1 sm:flex">
          <RouterLink
            to="/"
            class="rounded-md px-3 py-1.5 text-sm text-fg-muted hover:text-fg hover:bg-bg-sunken"
            active-class="text-fg bg-bg-sunken"
          >
            Reader
          </RouterLink>
          <RouterLink
            to="/texts"
            class="rounded-md px-3 py-1.5 text-sm text-fg-muted hover:text-fg hover:bg-bg-sunken"
            active-class="text-fg bg-bg-sunken"
          >
            Saved Texts
          </RouterLink>
          <RouterLink
            to="/vocab"
            class="rounded-md px-3 py-1.5 text-sm text-fg-muted hover:text-fg hover:bg-bg-sunken"
            active-class="text-fg bg-bg-sunken"
          >
            Vocabulary
          </RouterLink>
          <RouterLink
            v-if="auth.isAuthed"
            to="/review"
            class="inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm text-fg-muted hover:text-fg hover:bg-bg-sunken"
            active-class="text-fg bg-bg-sunken"
          >
            Review
            <span
              v-if="review.dueNow > 0"
              class="inline-flex min-w-[1.25rem] items-center justify-center rounded-full bg-accent px-1.5 py-px font-mono text-[10px] font-medium leading-none tracking-tight text-accent-fg tabular-nums"
              :title="`${review.dueNow.toLocaleString()} cards due now`"
            >
              {{ review.dueNow > 99 ? "99+" : review.dueNow }}
            </span>
          </RouterLink>
          <RouterLink
            to="/library"
            class="rounded-md px-3 py-1.5 text-sm text-fg-muted hover:text-fg hover:bg-bg-sunken"
            active-class="text-fg bg-bg-sunken"
          >
            Library
          </RouterLink>
          <RouterLink
            to="/discover"
            class="rounded-md px-3 py-1.5 text-sm text-fg-muted hover:text-fg hover:bg-bg-sunken"
            active-class="text-fg bg-bg-sunken"
          >
            Discover
          </RouterLink>
        </nav>
        <div class="ml-auto flex items-center gap-1">
          <!-- Daily streak badge — flame + day count. Sits before the
               known-words badge so the prosocial habit signal lands first.
               Hidden when streak is 0 to avoid demoralising a new user. -->
          <span
            v-if="auth.isAuthed && userWords.hydrated && userWords.stats.streak > 0"
            class="hidden items-center gap-1 rounded-full border border-amber-300 bg-amber-50 px-2.5 py-1 font-mono text-[10px] uppercase tracking-wider text-amber-800 sm:inline-flex dark:border-amber-700 dark:bg-amber-500/15 dark:text-amber-200"
            :title="`${userWords.stats.streak.toLocaleString()}-day streak — come back tomorrow to keep it going`"
          >
            <svg width="10" height="11" viewBox="0 0 10 11" fill="currentColor" aria-hidden="true">
              <path
                d="M5 0c.5 1.7-.8 2-1 3.5-.2 1.4.7 2 .7 2S4 5 3.5 4c-.4-.9.1-1.6.1-1.6S2 3.6 2 5.7C2 8 3.5 10.5 5 10.5S8 8 8 5.7C8 3 5.5.7 5 0z"
              />
            </svg>
            <span class="tabular-nums">{{ userWords.stats.streak }}</span>
          </span>

          <!-- Known-words badge — at-a-glance progress. Hidden on the very
               narrowest screens to keep the header from wrapping. -->
          <span
            v-if="auth.isAuthed && userWords.hydrated"
            class="hidden items-center gap-1 rounded-full border border-border-subtle bg-bg-sunken/60 px-2.5 py-1 font-mono text-[10px] uppercase tracking-wider text-fg-muted sm:inline-flex"
            :title="`${userWords.stats.known.toLocaleString()} known · ${userWords.stats.learning.toLocaleString()} learning${userWords.stats.ignored ? ` · ${userWords.stats.ignored.toLocaleString()} ignored` : ''}`"
          >
            <svg width="9" height="9" viewBox="0 0 9 9" fill="none" aria-hidden="true">
              <path
                d="M1.5 4.5l1.8 1.8 4.2-4.2"
                stroke="currentColor"
                stroke-width="1.4"
                stroke-linecap="round"
                stroke-linejoin="round"
              />
            </svg>
            <span class="tabular-nums">{{ compactNumber(userWords.stats.known) }}</span>
            <span
              v-if="userWords.stats.learning > 0"
              class="text-accent tabular-nums"
              :title="`${userWords.stats.learning.toLocaleString()} learning`"
            >
              · {{ compactNumber(userWords.stats.learning) }}
            </span>
          </span>
          <button
            type="button"
            class="rounded-md p-2 text-fg-muted hover:text-fg hover:bg-bg-sunken focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
            @click="settings.toggleTheme()"
            :title="settings.theme === 'dark' ? 'Switch to light' : 'Switch to dark'"
            :aria-label="settings.theme === 'dark' ? 'Switch to light' : 'Switch to dark'"
          >
            <svg
              v-if="settings.theme === 'dark'"
              width="16"
              height="16"
              viewBox="0 0 16 16"
              fill="none"
            >
              <circle cx="8" cy="8" r="3" stroke="currentColor" stroke-width="1.4" />
              <path
                d="M8 1v1.5M8 13.5V15M1 8h1.5M13.5 8H15M2.5 2.5l1 1M12.5 12.5l1 1M12.5 3.5l1-1M2.5 13.5l1-1"
                stroke="currentColor"
                stroke-width="1.4"
                stroke-linecap="round"
              />
            </svg>
            <svg
              v-else
              width="16"
              height="16"
              viewBox="0 0 16 16"
              fill="none"
            >
              <path
                d="M13 9.5a5.5 5.5 0 11-6.5-6.5 4.5 4.5 0 006.5 6.5z"
                stroke="currentColor"
                stroke-width="1.4"
                stroke-linejoin="round"
              />
            </svg>
          </button>
          <button
            type="button"
            class="rounded-md p-2 text-fg-muted hover:text-fg hover:bg-bg-sunken focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
            title="Settings"
            aria-label="Settings"
            @click="modals.openSettings()"
          >
            <!-- Sliders icon: three horizontal rails with knobs at different
                 positions. Shares no DNA with the radial sun toggle next door. -->
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <line x1="2" y1="4" x2="14" y2="4" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" />
              <line x1="2" y1="8" x2="14" y2="8" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" />
              <line x1="2" y1="12" x2="14" y2="12" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" />
              <circle cx="10" cy="4" r="1.6" fill="var(--color-bg-elevated)" stroke="currentColor" stroke-width="1.4" />
              <circle cx="5" cy="8" r="1.6" fill="var(--color-bg-elevated)" stroke="currentColor" stroke-width="1.4" />
              <circle cx="11" cy="12" r="1.6" fill="var(--color-bg-elevated)" stroke="currentColor" stroke-width="1.4" />
            </svg>
          </button>
          <AuthControls />
        </div>
      </div>
    </header>
    <main class="flex-1 overflow-y-auto">
      <RouterView />
    </main>
    <!-- Colophon footer — small, restrained, always discoverable. The
         GitHub + Ko-fi links live here rather than in the header so the
         reading content keeps its breathing room. -->
    <footer
      class="border-t border-border-subtle bg-bg-elevated/60 px-6 py-2"
    >
      <div
        class="mx-auto flex max-w-6xl items-center justify-center gap-3 font-mono text-[10px] uppercase tracking-[0.18em] text-fg-subtle"
      >
        <span class="text-cn text-fg-muted normal-case tracking-normal">
          轻读 QingDu
        </span>
        <span aria-hidden="true">·</span>
        <a
          href="https://github.com/mkampl/qingdu"
          target="_blank"
          rel="noopener"
          class="inline-flex items-center gap-1 transition-colors hover:text-accent"
        >
          <svg
            width="11"
            height="11"
            viewBox="0 0 24 24"
            fill="currentColor"
            aria-hidden="true"
          >
            <path
              d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z"
            />
          </svg>
          GitHub
        </a>
        <span aria-hidden="true">·</span>
        <a
          href="https://ko-fi.com/mkampl"
          target="_blank"
          rel="noopener"
          class="inline-flex items-center gap-1 transition-colors hover:text-accent"
        >
          <svg
            width="12"
            height="12"
            viewBox="0 0 24 24"
            fill="currentColor"
            aria-hidden="true"
          >
            <path
              d="M23.881 8.948c-.773-4.085-4.859-4.593-4.859-4.593H.723c-.604 0-.679.798-.679.798s-.082 7.324-.022 11.822c.164 2.424 2.586 2.672 2.586 2.672s8.267-.023 11.966-.049c2.438-.426 2.683-2.566 2.658-3.734 4.352.24 7.422-2.831 6.649-6.916zm-11.062 3.511c-1.246 1.453-4.011 3.976-4.011 3.976s-.121.119-.31.023c-.076-.057-.108-.09-.108-.09-.443-.441-3.368-3.049-4.034-3.954-.709-.965-1.041-2.7-.091-3.71.951-1.01 3.005-1.086 4.363.407 0 0 1.565-1.782 3.468-.963 1.904.82 1.832 3.011.723 4.311zm6.173.478c-.928.116-1.682.028-1.682.028V7.284h1.77s1.971.551 1.971 2.638c0 1.913-.985 2.667-2.059 3.015z"
            />
          </svg>
          Support
        </a>
        <span aria-hidden="true">·</span>
        <button
          type="button"
          class="inline-flex items-center gap-1 transition-colors hover:text-accent"
          @click="shortcuts.openOverlay()"
          title="Show keyboard shortcuts"
        >
          <kbd
            class="rounded border border-border-subtle bg-bg-elevated px-1 font-sans text-[10px] leading-3 text-fg-muted"
          >
            ?
          </kbd>
          Shortcuts
        </button>
      </div>
    </footer>
    <Toaster />
    <SettingsModal />
    <InvitationsModal />
    <ShortcutsOverlay />

    <!-- Mobile navigation drawer. Teleports to body so it overlays everything,
         only meaningful below sm where the inline nav is hidden. -->
    <Teleport to="body">
      <Transition
        enter-active-class="transition-opacity duration-200"
        leave-active-class="transition-opacity duration-150"
        enter-from-class="opacity-0"
        leave-to-class="opacity-0"
      >
        <div
          v-if="mobileNavOpen"
          class="fixed inset-0 z-50 sm:hidden"
          aria-modal="true"
          role="dialog"
          aria-label="Navigation"
        >
          <!-- Backdrop -->
          <div
            class="absolute inset-0 bg-black/40 backdrop-blur-sm"
            @click="mobileNavOpen = false"
            aria-hidden="true"
          />
          <!-- Drawer panel -->
          <Transition
            enter-active-class="transition-transform duration-250 ease-out"
            leave-active-class="transition-transform duration-200 ease-in"
            enter-from-class="-translate-x-full"
            leave-to-class="-translate-x-full"
            appear
          >
            <nav
              v-if="mobileNavOpen"
              id="mobile-nav-drawer"
              class="absolute inset-y-0 left-0 flex w-[min(18rem,80vw)] flex-col bg-bg-elevated shadow-2xl ring-1 ring-border"
            >
              <header
                class="flex items-center justify-between border-b border-border-subtle px-5 py-3"
              >
                <span
                  class="text-cn text-lg font-semibold tracking-tight"
                >
                  轻读 <span class="text-fg-muted font-normal">QingDu</span>
                </span>
                <button
                  type="button"
                  class="rounded-md p-2 text-fg-muted hover:text-fg hover:bg-bg-sunken"
                  aria-label="Close navigation"
                  @click="mobileNavOpen = false"
                >
                  <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                    <path
                      d="M4 4l8 8M12 4l-8 8"
                      stroke="currentColor"
                      stroke-width="1.6"
                      stroke-linecap="round"
                    />
                  </svg>
                </button>
              </header>

              <ul class="flex-1 py-3">
                <li
                  v-for="link in [
                    { to: '/', label: 'Reader', badge: 0 },
                    { to: '/texts', label: 'Saved Texts', badge: 0 },
                    { to: '/vocab', label: 'Vocabulary', badge: 0 },
                    {
                      to: '/review',
                      label: 'Review',
                      badge: auth.isAuthed ? review.dueNow : 0,
                      gated: true,
                    },
                    { to: '/library', label: 'Library', badge: 0 },
                    { to: '/discover', label: 'Discover', badge: 0 },
                  ].filter((l) => !l.gated || auth.isAuthed)"
                  :key="link.to"
                >
                  <RouterLink
                    :to="link.to"
                    class="flex items-center justify-between gap-2 px-5 py-3 font-display text-base text-fg-muted hover:bg-bg-sunken hover:text-fg"
                    active-class="bg-bg-sunken text-fg font-medium"
                  >
                    <span>{{ link.label }}</span>
                    <span
                      v-if="link.badge > 0"
                      class="inline-flex min-w-[1.5rem] items-center justify-center rounded-full bg-accent px-2 py-px font-mono text-[10px] font-medium leading-none text-accent-fg tabular-nums"
                    >
                      {{ link.badge > 99 ? "99+" : link.badge }}
                    </span>
                  </RouterLink>
                </li>
              </ul>

            </nav>
          </Transition>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>
