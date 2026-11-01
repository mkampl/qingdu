import { ref } from "vue";

import * as api from "@/api/client";
import { ApiError } from "@/api/client";
import { useToastStore } from "@/stores/toast";

export type AnkiExportPhase = "idle" | "checking" | "preparing" | "downloading" | "done" | "error";

export interface AnkiAudioProgress {
  total: number;
  cached: number;
  generated: number;
  failed: number;
  rate_limited: boolean;
}

/**
 * Anki export of a vocab list: check the audio cache, generate the missing
 * audio, then download the deck. `phase` drives the progress modal, which
 * closes itself shortly after a successful download.
 */
export function useAnkiExport() {
  const toasts = useToastStore();
  const phase = ref<AnkiExportPhase>("idle");
  const progress = ref<AnkiAudioProgress | null>(null);
  const error = ref<string | null>(null);

  async function run(listId: number) {
    error.value = null;
    progress.value = null;
    phase.value = "checking";

    try {
      const status = await api.checkAudioStatus(listId);
      if (!status.ready) {
        phase.value = "preparing";
        progress.value = {
          total: status.total,
          cached: status.cached,
          generated: 0,
          failed: 0,
          rate_limited: false,
        };
        const prep = await api.prepareExportAudio(listId);
        progress.value = {
          total: prep.total,
          cached: prep.cached,
          generated: prep.generated,
          failed: prep.failed,
          rate_limited: prep.rate_limited,
        };
      }
      phase.value = "downloading";
      await api.openDownload(`/api/vocabulary-lists/${listId}/export-anki`);
      phase.value = "done";
      if (progress.value?.rate_limited) {
        toasts.info("Anki download started — some cards lack audio (rate limit).");
      } else {
        toasts.success("Anki download started.");
      }
      // Close the modal after a moment, leaving the success message up briefly.
      setTimeout(() => {
        if (phase.value === "done") phase.value = "idle";
      }, 1800);
    } catch (e) {
      error.value = e instanceof ApiError ? e.message : "Anki export failed.";
      phase.value = "error";
    }
  }

  function close() {
    phase.value = "idle";
  }

  return { phase, progress, error, run, close };
}
