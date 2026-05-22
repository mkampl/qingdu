<script setup lang="ts">
import { useShortcutsStore } from "@/stores/shortcuts";
import Modal from "@/components/ui/Modal.vue";
import { submitShortcutLabel, isMac } from "@/utils/platform";

const shortcuts = useShortcutsStore();

const groups: { title: string; items: { keys: string[]; label: string }[] }[] = [
  {
    title: "Reader",
    items: [
      { keys: [submitShortcutLabel], label: "Analyze the current text" },
      { keys: ["n"], label: "Start a new text" },
      { keys: ["Esc"], label: "Close popover / sentence translation" },
    ],
  },
  {
    title: "Navigation",
    items: [
      { keys: ["g", "r"], label: "Reader" },
      { keys: ["g", "t"], label: "Saved Texts" },
      { keys: ["g", "v"], label: "Vocabulary" },
      { keys: ["g", "a"], label: "Admin panel (if admin)" },
    ],
  },
  {
    title: "Everywhere",
    items: [
      { keys: ["?"], label: "Show this shortcuts overlay" },
      { keys: [isMac ? "⌘" : "Ctrl", ","], label: "Open settings" },
    ],
  },
];
</script>

<template>
  <Modal
    :open="shortcuts.overlayOpen"
    size="md"
    close-on-backdrop
    @close="shortcuts.closeOverlay()"
  >
    <template #header>
      <div class="flex items-baseline gap-3">
        <h2 class="font-display text-xl font-medium tracking-tight text-fg">
          Keyboard shortcuts
        </h2>
        <span
          class="font-mono text-[10px] uppercase tracking-[0.18em] text-fg-subtle"
        >
          Press ? anywhere
        </span>
      </div>
    </template>

    <div class="space-y-6">
      <section v-for="group in groups" :key="group.title">
        <p
          class="mb-2 font-mono text-[10px] uppercase tracking-[0.2em] text-fg-subtle"
        >
          {{ group.title }}
        </p>
        <ul class="space-y-1.5">
          <li
            v-for="item in group.items"
            :key="item.label"
            class="flex items-center justify-between gap-3 text-sm"
          >
            <span class="text-fg-muted">{{ item.label }}</span>
            <span class="flex shrink-0 items-center gap-1">
              <template v-for="(key, idx) in item.keys" :key="idx">
                <kbd
                  class="inline-flex h-5 min-w-[1.25rem] items-center justify-center rounded border border-border-subtle bg-bg-elevated px-1.5 font-sans text-[10px] font-medium text-fg-muted"
                >
                  {{ key }}
                </kbd>
                <span
                  v-if="idx < item.keys.length - 1"
                  class="font-mono text-[10px] text-fg-subtle"
                  aria-hidden="true"
                >
                  then
                </span>
              </template>
            </span>
          </li>
        </ul>
      </section>
    </div>
  </Modal>
</template>
