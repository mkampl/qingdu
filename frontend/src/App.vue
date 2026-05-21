<script setup lang="ts">
import { RouterLink, RouterView } from "vue-router";
import { onMounted } from "vue";
import { useSettingsStore } from "@/stores/settings";

const settings = useSettingsStore();

onMounted(() => {
  settings.hydrate();
});
</script>

<template>
  <div class="flex h-full flex-col">
    <header class="border-b border-border bg-bg-elevated">
      <div class="mx-auto flex max-w-6xl items-center gap-6 px-6 py-3">
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
        </nav>
        <div class="ml-auto flex items-center gap-2">
          <button
            type="button"
            class="rounded-md px-3 py-1.5 text-sm text-fg-muted hover:text-fg hover:bg-bg-sunken"
            @click="settings.toggleTheme()"
            :title="settings.theme === 'dark' ? 'Switch to light' : 'Switch to dark'"
          >
            {{ settings.theme === "dark" ? "☀" : "☾" }}
          </button>
        </div>
      </div>
    </header>
    <main class="flex-1 overflow-y-auto">
      <RouterView />
    </main>
  </div>
</template>
