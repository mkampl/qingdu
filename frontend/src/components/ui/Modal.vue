<script setup lang="ts">
import { onBeforeUnmount, watch } from "vue";

const props = defineProps<{
  open: boolean;
  title?: string;
  closeOnBackdrop?: boolean;
  size?: "sm" | "md" | "lg";
}>();

const emit = defineEmits<{ (e: "close"): void }>();

function handleKeydown(e: KeyboardEvent) {
  if (e.key === "Escape" && props.open) emit("close");
}

watch(
  () => props.open,
  (open) => {
    if (typeof document === "undefined") return;
    if (open) {
      document.addEventListener("keydown", handleKeydown);
      document.body.style.overflow = "hidden";
    } else {
      document.removeEventListener("keydown", handleKeydown);
      document.body.style.overflow = "";
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
      <div
        v-if="open"
        class="fixed inset-0 z-50 flex items-end justify-center p-0 sm:items-center sm:p-6"
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
             sheet — the same cap works there too. -->
        <div
          role="dialog"
          aria-modal="true"
          :aria-label="title"
          class="relative flex w-full max-h-[calc(100dvh-1rem)] flex-col rounded-t-2xl bg-bg-elevated shadow-2xl ring-1 ring-border sm:max-h-[calc(100dvh-3rem)] sm:rounded-2xl"
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
