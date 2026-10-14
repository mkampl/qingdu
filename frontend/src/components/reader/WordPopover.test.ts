import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "@/api/client";
import type { WordInfo } from "@/api/types";
import WordPopover from "@/components/reader/WordPopover.vue";
import { useAnalysisStore } from "@/stores/analysis";
import { useAuthStore } from "@/stores/auth";
import { useReaderStore } from "@/stores/reader";
import { useUserWordsStore } from "@/stores/userWords";

describe("WordPopover", () => {
  beforeEach(() => setActivePinia(createPinia()));
  afterEach(() => {
    vi.restoreAllMocks();
    document.body.innerHTML = "";
  });

  it("sends the sentence the word was clicked in when it is marked", async () => {
    const auth = useAuthStore();
    auth.user = { username: "alice", is_admin: false } as never;
    auth.hydrated = true;
    useUserWordsStore().hydrated = true;
    useAnalysisStore().librarySlug = "hsk3_01_doctor-visit";
    const set = vi
      .spyOn(api, "setUserWordState")
      .mockResolvedValue({ word: "感冒", state: "learning" } as never);

    const wrapper = mount(WordPopover, { attachTo: document.body });
    useReaderStore().selectWord(
      { text: "感冒", pinyin: "gǎn mào", meaning: "to catch cold" } as WordInfo,
      null,
      { key: "s1", text: "上个星期我感冒了。" },
    );
    await flushPromises();

    const learning = [...document.querySelectorAll("button")].find(
      (b) => b.textContent?.trim() === "Learning",
    );
    expect(learning).toBeTruthy();
    learning!.click();
    await flushPromises();

    expect(set).toHaveBeenCalledWith("感冒", "learning", null, null, {
      sentence: "上个星期我感冒了。",
      librarySlug: "hsk3_01_doctor-visit",
    });
    wrapper.unmount();
  });
});
