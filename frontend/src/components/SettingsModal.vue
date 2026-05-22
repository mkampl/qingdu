<script setup lang="ts">
import { computed } from "vue";

import { useAppModalsStore } from "@/stores/app-modals";
import { useSettingsStore, type HskVersion, type PinyinMode } from "@/stores/settings";

import Modal from "@/components/ui/Modal.vue";

const modals = useAppModalsStore();
const settings = useSettingsStore();

// Use computed setters so the radios/select bind directly to the store.
const pinyinMode = computed<PinyinMode>({
  get: () => settings.pinyinMode,
  set: (v) => (settings.pinyinMode = v),
});
const hskVersion = computed<HskVersion>({
  get: () => settings.hskVersion,
  set: (v) => (settings.hskVersion = v),
});
const showLegend = computed<boolean>({
  get: () => settings.showLegend,
  set: (v) => (settings.showLegend = v),
});
const theme = computed({
  get: () => settings.theme,
  set: (v: "light" | "dark") => (settings.theme = v),
});

const pinyinOptions: { value: PinyinMode; label: string; hint: string }[] = [
  {
    value: "auto",
    label: "Auto",
    hint: "Show pinyin only for words above your estimated reading level",
  },
  { value: "on", label: "Always", hint: "Show pinyin on every word" },
  { value: "off", label: "Never", hint: "Hide pinyin everywhere" },
];

const hskOptions: { value: HskVersion; label: string; hint: string }[] = [
  { value: "new", label: "New HSK", hint: "2021 standard, 9 levels" },
  { value: "old", label: "Old HSK", hint: "Pre-2021, 6 levels" },
];
</script>

<template>
  <Modal
    :open="modals.settingsOpen"
    size="md"
    close-on-backdrop
    @close="modals.closeAll()"
  >
    <template #header>
      <div class="flex items-baseline gap-3">
        <h2 class="font-display text-xl font-medium tracking-tight text-fg">
          Settings
        </h2>
        <span
          class="font-mono text-[10px] uppercase tracking-[0.18em] text-fg-subtle"
        >
          Saved on this device
        </span>
      </div>
    </template>

    <div class="space-y-7">
      <!-- Pinyin -->
      <fieldset>
        <legend
          class="mb-3 font-mono text-[11px] uppercase tracking-[0.2em] text-fg-subtle"
        >
          Pinyin display
        </legend>
        <div class="space-y-2">
          <label
            v-for="opt in pinyinOptions"
            :key="opt.value"
            class="flex cursor-pointer items-start gap-3 rounded-md border border-border-subtle px-3 py-2 transition-colors hover:bg-bg-sunken"
            :class="{
              'border-accent bg-bg-sunken': pinyinMode === opt.value,
            }"
          >
            <input
              v-model="pinyinMode"
              type="radio"
              :value="opt.value"
              class="mt-1 accent-accent"
            />
            <span class="flex-1">
              <span class="block font-display text-base text-fg">
                {{ opt.label }}
              </span>
              <span class="block text-xs text-fg-muted">{{ opt.hint }}</span>
            </span>
          </label>
        </div>
      </fieldset>

      <!-- HSK version -->
      <fieldset>
        <legend
          class="mb-3 font-mono text-[11px] uppercase tracking-[0.2em] text-fg-subtle"
        >
          HSK version
        </legend>
        <div class="grid grid-cols-2 gap-2">
          <label
            v-for="opt in hskOptions"
            :key="opt.value"
            class="flex cursor-pointer items-start gap-3 rounded-md border border-border-subtle px-3 py-2 transition-colors hover:bg-bg-sunken"
            :class="{
              'border-accent bg-bg-sunken': hskVersion === opt.value,
            }"
          >
            <input
              v-model="hskVersion"
              type="radio"
              :value="opt.value"
              class="mt-1 accent-accent"
            />
            <span class="flex-1">
              <span class="block font-display text-base text-fg">
                {{ opt.label }}
              </span>
              <span class="block text-xs text-fg-muted">{{ opt.hint }}</span>
            </span>
          </label>
        </div>
      </fieldset>

      <!-- Legend -->
      <label
        class="flex cursor-pointer items-start gap-3 rounded-md border border-border-subtle px-3 py-2 transition-colors hover:bg-bg-sunken"
        :class="{ 'border-accent bg-bg-sunken': showLegend }"
      >
        <input
          v-model="showLegend"
          type="checkbox"
          class="mt-1 accent-accent"
        />
        <span class="flex-1">
          <span class="block font-display text-base text-fg">
            Show HSK colour legend
          </span>
          <span class="block text-xs text-fg-muted">
            Adds a small key under the composition stats explaining each
            level's wash colour.
          </span>
        </span>
      </label>

      <!-- Theme — same toggle as the header crescent, included here for
           discoverability. -->
      <fieldset>
        <legend
          class="mb-3 font-mono text-[11px] uppercase tracking-[0.2em] text-fg-subtle"
        >
          Appearance
        </legend>
        <div class="grid grid-cols-2 gap-2">
          <label
            class="flex cursor-pointer items-center gap-2 rounded-md border border-border-subtle px-3 py-2 transition-colors hover:bg-bg-sunken"
            :class="{ 'border-accent bg-bg-sunken': theme === 'light' }"
          >
            <input
              v-model="theme"
              type="radio"
              value="light"
              class="accent-accent"
            />
            <span class="font-display text-base text-fg">Light</span>
          </label>
          <label
            class="flex cursor-pointer items-center gap-2 rounded-md border border-border-subtle px-3 py-2 transition-colors hover:bg-bg-sunken"
            :class="{ 'border-accent bg-bg-sunken': theme === 'dark' }"
          >
            <input
              v-model="theme"
              type="radio"
              value="dark"
              class="accent-accent"
            />
            <span class="font-display text-base text-fg">Dark</span>
          </label>
        </div>
      </fieldset>
    </div>
  </Modal>
</template>
