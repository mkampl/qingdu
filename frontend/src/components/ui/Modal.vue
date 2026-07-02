<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref, watch } from "vue";

const props = defineProps<{
  open: boolean;
  title?: string;
  closeOnBackdrop?: boolean;
  size?: "sm" | "md" | "lg";
}>();

const emit = defineEmits<{ (e: "close"): void }>();

const shell = ref<HTMLElement | null>(null);
// The element that opened the dialog — focus returns to it on close so
// keyboard users don't get dumped at the top of the document.
let opener: HTMLElement | null = null;

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

function handleKeydown(e: KeyboardEvent) {
  if (!props.open) return;
  if (e.key === "Escape") {
    emit("close");
    return;
  }
  // Focus trap. aria-modal alone doesn't stop Tab from walking the
  // obscured page behind the backdrop; every one of the app's ~12 modals
  // inherits this single trap.
  if (e.key === "Tab" && shell.value) {
    const focusables = Array.from(
      shell.value.querySelectorAll<HTMLElement>(FOCUSABLE),
    ).filter((el) => el.offsetParent !== null);
    if (focusables.length === 0) {
      e.preventDefault();
      return;
    }
    const first = focusables[0];
    const last = focusables[focusables.length - 1];
    const active = document.activeElement as HTMLElement | null;
    if (e.shiftKey && (active === first || !shell.value.contains(active))) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && (active === last || !shell.value.contains(active))) {
      e.preventDefault();
      first.focus();
    }
  }
}

watch(
  () => props.open,
  (open) => {
    if (typeof document === "undefined") return;
    if (open) {
      opener = document.activeElement as HTMLElement | null;
      document.addEventListener("keydown", handleKeydown);
      document.body.style.overflow = "hidden";
      // Move focus into the dialog once it has rendered. Prefer an
      // autofocus-marked control; else the first focusable; else the
      // shell itself (tabindex=-1) so Escape works immediately.
      void nextTick(() => {
        if (!shell.value) return;
        const target =
          shell.value.querySelector<HTMLElement>("[autofocus]") ??
          shell.value.querySelector<HTMLElement>(FOCUSABLE) ??
          shell.value;
        target.focus();
      });
    } else {
      document.removeEventListener("keydown", handleKeydown);
      document.body.style.overflow = "";
      opener?.focus?.();
      opener = null;
    }
  },
  { immediate: true },
);

onBeforeUnmount(() => {
  if (typeof document === "undefined") return;
  document.removeEventListener("keydown", handleKeydown);
  document.body.style.overflow = "";
});

const sizeClasses = {
  sm: "max-w-sm",
  md: "max-w-md",
  lg: "max-w-2xl",
};
</script>

<template>
  <Teleport to="body">
    <Transition
      enter-active-class="transition-opacity"
      leave-active-class="transition-opacity"
      enter-from-class="opacity-0"
      leave-to-class="opacity-0"
    >
      <!-- modal-overlay carries safe-area padding via scoped <style> below.
           Needed because the dialog is Teleport'd to body and uses
           position:fixed, which bypasses body's own safe-area padding.
           Without it the bottom-sheet footer (e.g. package Import button)
           sits under Android's gesture nav bar. -->
      <div
        v-if="open"
        class="modal-overlay fixed inset-0 z-50 flex items-end justify-center p-0 sm:items-center sm:p-6"
      >
        <div
          class="absolute inset-0 bg-black/40 backdrop-blur-sm"
          @click="closeOnBackdrop ? emit('close') : null"
          aria-hidden="true"
        />
        <!-- Cap the dialog to the viewport so tall content scrolls *inside*
             the modal instead of pushing past the screen edge. The flex
             column keeps the header / footer pinned while only the body
             slot scrolls. On mobile the modal sits at the bottom as a
             sheet — the same cap works there too.

             The mobile max-h subtracts both safe-area insets so the
             dialog can't grow taller than the visible area between
             status bar and gesture nav bar. Without this the bottom-
             anchored sheet pushes its header above the status bar and
             the close button becomes unreachable. -->
        <div
          ref="shell"
          role="dialog"
          aria-modal="true"
          :aria-label="title"
          tabindex="-1"
          class="dialog-shell relative flex w-full flex-col rounded-t-2xl bg-bg-elevated shadow-2xl outline-none ring-1 ring-border sm:max-h-[calc(100dvh-3rem)] sm:rounded-2xl"
          :class="sizeClasses[size ?? 'md']"
        >
          <header
            v-if="title || $slots.header"
            class="flex shrink-0 items-center justify-between border-b border-border px-6 py-4"
          >
            <slot name="header">
              <h2 class="text-lg font-semibold text-fg">{{ title }}</h2>
            </slot>
            <button
              type="button"
              class="rounded-md p-1 text-fg-muted hover:bg-bg-sunken hover:text-fg"
              aria-label="Close"
              @click="emit('close')"
            >
              <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                <path
                  d="M5 5l10 10M15 5L5 15"
                  stroke="currentColor"
                  stroke-width="1.5"
                  stroke-linecap="round"
                />
              </svg>
            </button>
          </header>
          <div class="min-h-0 flex-1 overflow-y-auto px-6 py-5">
            <slot />
          </div>
          <footer
            v-if="$slots.footer"
            class="flex shrink-0 items-center justify-end gap-2 border-t border-border px-6 py-4"
          >
            <slot name="footer" />
          </footer>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
/* Capacitor Android draws the WebView behind the status + nav bars
   (Android 15 edge-to-edge). Indent the overlay by the inset so the
   bottom-anchored mobile sheet keeps its footer above the nav bar and
   the top-anchored close button stays under the status bar.

   Desktop / mobile-web: env() returns 0 → no visual change. We only
   apply this below the sm: breakpoint; on sm+ the existing sm:p-6
   provides the visual gutter and the safe-area insets are 0 anyway. */
@media (max-width: 639px) {
  .modal-overlay {
    padding-top: env(safe-area-inset-top);
    padding-bottom: env(safe-area-inset-bottom);
    padding-left: env(safe-area-inset-left);
    padding-right: env(safe-area-inset-right);
  }
  /* The mobile cap subtracts the same insets the overlay adds so the
     dialog can't grow past the visible area. Without this the bottom
     anchor pushes the header off-screen and its close button becomes
     unreachable when the body content overflows. */
  .dialog-shell {
    max-height: calc(
      100dvh - 1rem - env(safe-area-inset-top) - env(safe-area-inset-bottom)
    );
  }
}
</style>
