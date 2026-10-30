<script setup lang="ts">
import { computed } from "vue";

import { useAuthStore } from "@/stores/auth";
import { useSettingsStore } from "@/stores/settings";
import { useToastStore } from "@/stores/toast";

import OptionFieldset from "@/components/settings/OptionFieldset.vue";
import SettingsSection from "@/components/settings/SettingsSection.vue";

const settings = useSettingsStore();
const auth = useAuthStore();
const toasts = useToastStore();

// Device-local settings bind straight to the store through computed setters.
const theme = computed({
  get: () => settings.theme,
  set: (v: "light" | "dark") => (settings.theme = v),
});
const reminderEnabled = computed<boolean>({
  get: () => settings.reminderEnabled,
  set: (v) => (settings.reminderEnabled = v),
});
const reminderTime = computed<string>({
  get: () => settings.reminderTime,
  set: (v) => (settings.reminderTime = v),
});
const hapticsEnabled = computed<boolean>({
  get: () => settings.hapticsEnabled,
  set: (v) => (settings.hapticsEnabled = v),
});

// --- Simplified vs Traditional display ---
const displayScript = computed<"auto" | "simp" | "trad">({
  get: () => auth.user?.display_script ?? "auto",
  set: (v) => {
    void auth.updateSettings({ display_script: v }).catch(() => {
      toasts.error("Couldn't save script preference.");
    });
  },
});

const scriptOptions: {
  value: "auto" | "simp" | "trad";
  label: string;
  hint: string;
}[] = [
  {
    value: "auto",
    label: "Auto",
    hint: "Show Chinese exactly as it appears in the source — no conversion.",
  },
  {
    value: "simp",
    label: "Simplified (简体)",
    hint: "Convert every Chinese surface to Simplified, no matter what was stored.",
  },
  {
    value: "trad",
    label: "Traditional (繁體)",
    hint: "Convert every Chinese surface to Traditional.",
  },
];
</script>

<template>
  <SettingsSection title="Appearance & reminders">
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

    <!-- Daily reminder. Shown on all platforms; on web the toggle saves
         the preference but never schedules anything (the native plugin is
         a no-op outside the Capacitor wrapper). -->
    <fieldset>
      <legend
        class="mb-3 font-mono text-[11px] uppercase tracking-[0.2em] text-fg-subtle"
      >
        Daily reminder
      </legend>
      <label class="flex cursor-pointer items-center gap-3 rounded-md border border-border-subtle px-3 py-2 transition-colors hover:bg-bg-sunken">
        <input
          v-model="reminderEnabled"
          type="checkbox"
          class="mt-0 accent-accent"
        />
        <span class="flex-1">
          <span class="block font-display text-base text-fg">
            Remind me daily
          </span>
          <span class="block text-xs text-fg-muted">
            A notification at a fixed time with your number of due cards
            (as of your last visit).
          </span>
        </span>
      </label>
      <label
        v-if="reminderEnabled"
        class="mt-2 flex items-center gap-3 px-3"
      >
        <span class="font-display text-sm text-fg-muted">Time</span>
        <input
          v-model="reminderTime"
          type="time"
          class="rounded-md border border-border-subtle bg-bg px-2 py-1 font-mono text-sm tabular-nums text-fg focus:border-accent focus:outline-none"
        />
      </label>
    </fieldset>

    <fieldset>
      <legend
        class="mb-3 font-mono text-[11px] uppercase tracking-[0.2em] text-fg-subtle"
      >
        Feedback
      </legend>
      <label class="flex cursor-pointer items-center gap-3 rounded-md border border-border-subtle px-3 py-2 transition-colors hover:bg-bg-sunken">
        <input
          v-model="hapticsEnabled"
          type="checkbox"
          class="mt-0 accent-accent"
        />
        <span class="flex-1">
          <span class="block font-display text-base text-fg">
            Haptic taps
          </span>
          <span class="block text-xs text-fg-muted">
            Subtle vibration on word-tap and review grade. Android only;
            ignored on web.
          </span>
        </span>
      </label>
    </fieldset>

    <!-- Global trad/simp toggle. Auth-gated since
         it lives on the user row server-side; the conversion is applied
         at every endpoint that returns Chinese. -->
    <OptionFieldset v-if="auth.isAuthed"
      v-model="displayScript"
      :options="scriptOptions"
    >
      Script
    </OptionFieldset>
  </SettingsSection>
</template>
