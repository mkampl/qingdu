import { defineStore } from "pinia";
import { computed, ref } from "vue";

import * as api from "@/api/client";
import type { Capabilities } from "@/api/client";

/**
 * What the server this app talks to offers beyond the basics (an LLM, the
 * translation providers). Loaded once at start; switching servers reloads
 * the app, so it always describes the current server. Features check
 * `llmFeature(name)` and stay hidden on servers without them.
 */
export const useCapabilitiesStore = defineStore("capabilities", () => {
  const caps = ref<Capabilities | null>(null);

  async function load() {
    try {
      caps.value = await api.getCapabilities();
    } catch {
      // An older server has no /api/capabilities: nothing extra on offer.
      caps.value = null;
    }
  }

  const llm = computed(() => caps.value?.llm ?? null);

  function llmFeature(name: string): boolean {
    return !!llm.value?.available && llm.value.features.includes(name);
  }

  return { caps, llm, load, llmFeature };
});
