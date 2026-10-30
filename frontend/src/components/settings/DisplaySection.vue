<script setup lang="ts">
import { computed } from "vue";

import { useAuthStore } from "@/stores/auth";
import {
  useSettingsStore,
  type ColorMode,
  type HskVersion,
  type PinyinMode,
} from "@/stores/settings";

import OptionFieldset from "@/components/settings/OptionFieldset.vue";
import SettingsSection from "@/components/settings/SettingsSection.vue";

const settings = useSettingsStore();
const auth = useAuthStore();

// Use computed setters so the radios bind directly to the store.
const pinyinMode = computed<PinyinMode>({
  get: () => settings.pinyinMode,
  set: (v) => (settings.pinyinMode = v),
});
const hskVersion = computed<HskVersion>({
  get: () => settings.hskVersion,
  set: (v) => {
    settings.hskVersion = v;
    // Daily auto-enrol on the server draws from this list.
    if (auth.user) void auth.syncHskVersion();
  },
});
const colorMode = computed<ColorMode>({
  get: () => settings.colorMode,
  set: (v) => (settings.colorMode = v),
});

const colorOptions: { value: ColorMode; label: string; hint: string }[] = [
  {
    value: "progress",
    label: "By progress",
    hint: "Blue = new to you · accent = learning · plain = known/ignored",
  },
  { value: "hsk", label: "By HSK", hint: "Color every word by its HSK level" },
  { value: "off", label: "Off", hint: "Plain text, no highlights" },
];

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
  <SettingsSection title="Display" open>
    <!-- Word color mode -->
    <OptionFieldset
      v-model="colorMode"
      :options="colorOptions"
    >
      Word coloring
    </OptionFieldset>

    <!-- Pinyin -->
    <OptionFieldset
      v-model="pinyinMode"
      :options="pinyinOptions"
    >
      Pinyin display
    </OptionFieldset>

    <!-- HSK version -->
    <OptionFieldset
      v-model="hskVersion"
      :options="hskOptions"
      grid
    >
      HSK version
    </OptionFieldset>
  </SettingsSection>
</template>
