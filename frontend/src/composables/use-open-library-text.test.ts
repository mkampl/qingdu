import { createPinia, setActivePinia } from "pinia";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "@/api/client";
import { useAnalysisStore } from "@/stores/analysis";

const push = vi.fn();
vi.mock("vue-router", () => ({ useRouter: () => ({ push }) }));

import { useOpenLibraryText } from "@/composables/use-open-library-text";

describe("useOpenLibraryText", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    push.mockReset();
  });
  afterEach(() => vi.restoreAllMocks());

  it("tells the reader which library text it is, so the quiz shows", async () => {
    vi.spyOn(api, "getLibraryEntry").mockResolvedValue({
      slug: "hsk1_01_x",
      text: "你好",
      analyzed: { words: [] },
      has_quiz: true,
    } as never);
    const analysis = useAnalysisStore();
    const load = vi.spyOn(analysis, "loadSaved");

    const ok = await useOpenLibraryText()("hsk1_01_x");

    expect(ok).toBe(true);
    expect(load).toHaveBeenCalledWith("你好", { words: [] }, null, {
      slug: "hsk1_01_x",
      hasQuiz: true,
    });
    expect(push).toHaveBeenCalledWith("/");
  });

  it("stays put when the text can't be loaded", async () => {
    vi.spyOn(api, "getLibraryEntry").mockRejectedValue(new Error("gone"));
    expect(await useOpenLibraryText()("missing")).toBe(false);
    expect(push).not.toHaveBeenCalled();
  });
});
