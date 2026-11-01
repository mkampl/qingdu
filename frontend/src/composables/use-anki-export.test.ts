import { createPinia, setActivePinia } from "pinia";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "@/api/client";
import { useToastStore } from "@/stores/toast";
import { useAnkiExport } from "./use-anki-export";

describe("useAnkiExport", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("generates missing audio, downloads, then closes itself", async () => {
    vi.spyOn(api, "checkAudioStatus").mockResolvedValue({
      ready: false,
      total: 4,
      cached: 1,
    } as never);
    const prep = vi.spyOn(api, "prepareExportAudio").mockResolvedValue({
      total: 4,
      cached: 1,
      generated: 2,
      failed: 1,
      rate_limited: true,
    } as never);
    const dl = vi.spyOn(api, "openDownload").mockResolvedValue(undefined as never);
    const info = vi.spyOn(useToastStore(), "info");
    const a = useAnkiExport();
    await a.run(7);
    expect(prep).toHaveBeenCalledWith(7);
    expect(dl).toHaveBeenCalledWith("/api/vocabulary-lists/7/export-anki");
    expect(a.phase.value).toBe("done");
    expect(a.progress.value?.generated).toBe(2);
    expect(info).toHaveBeenCalledOnce();
    vi.advanceTimersByTime(1800);
    expect(a.phase.value).toBe("idle");
  });

  it("skips generation when the cache is ready; a failure stays on error", async () => {
    vi.spyOn(api, "checkAudioStatus").mockResolvedValue({ ready: true } as never);
    const prep = vi.spyOn(api, "prepareExportAudio");
    vi.spyOn(api, "openDownload").mockRejectedValue(new Error("x"));
    const a = useAnkiExport();
    await a.run(7);
    expect(prep).not.toHaveBeenCalled();
    expect(a.phase.value).toBe("error");
    expect(a.error.value).toBe("Anki export failed.");
    vi.advanceTimersByTime(5000);
    expect(a.phase.value).toBe("error");
    a.close();
    expect(a.phase.value).toBe("idle");
  });
});
