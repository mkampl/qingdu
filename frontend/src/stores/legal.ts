import { defineStore } from "pinia";
import { ref } from "vue";

import * as api from "@/api/client";
import type { LegalConfig } from "@/api/client";

// Fetched once and cached — both the footer (link visibility) and the
// Impressum/Privacy views themselves (direct-nav fallback state) read
// from this store instead of each firing their own request.
export const useLegalStore = defineStore("legal", () => {
  const config = ref<LegalConfig | null>(null);
  const loaded = ref(false);

  async function load() {
    if (loaded.value) return;
    try {
      config.value = await api.getLegalConfig();
    } catch {
      // Non-critical — pages fall back to their "not configured" state.
    } finally {
      loaded.value = true;
    }
  }

  return { config, loaded, load };
});
