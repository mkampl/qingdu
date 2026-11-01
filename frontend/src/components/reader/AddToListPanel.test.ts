import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "@/api/client";
import { ApiError } from "@/api/client";
import type { VocabularyListSummary, WordInfo } from "@/api/types";
import AddToListPanel from "@/components/reader/AddToListPanel.vue";
import { useVocabListsStore } from "@/stores/vocab-lists";

const LISTS = [
  { id: 1, name: "Trip", sections: [{ name: "Day 1", words: [{ hanzi: "茶" }] }] },
  { id: 2, name: "Work", sections: [] },
] as unknown as VocabularyListSummary[];

function word(text: string): WordInfo {
  return { text, meaning: "tea" } as WordInfo;
}

function button(w: ReturnType<typeof mount>, text: string) {
  return w.findAll("button").find((b) => b.text().startsWith(text))!;
}

describe("AddToListPanel", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    const store = useVocabListsStore();
    store.lists = LISTS;
    vi.spyOn(store, "ensureLoaded").mockResolvedValue();
    vi.spyOn(store, "invalidate").mockResolvedValue();
  });
  afterEach(() => vi.restoreAllMocks());

  it("pre-selects the first list and its first section; follows the pick until typed", async () => {
    const w = mount(AddToListPanel, { props: { word: word("茶") }, global: { stubs: { RouterLink: true } } });
    await button(w, "Add to vocab list").trigger("click");
    await flushPromises();
    const input = w.find("input");
    expect((input.element as HTMLInputElement).value).toBe("Day 1");
    await button(w, "Work").trigger("click");
    expect((input.element as HTMLInputElement).value).toBe("Main");
    await input.setValue("Mine");
    await button(w, "Trip").trigger("click");
    expect((input.element as HTMLInputElement).value).toBe("Mine");
  });

  it("says where the word already is on a 409", async () => {
    vi.spyOn(api, "addWordToList").mockRejectedValue(new ApiError(409, null, "dup"));
    const w = mount(AddToListPanel, { props: { word: word("茶") }, global: { stubs: { RouterLink: true } } });
    await button(w, "Add to vocab list").trigger("click");
    await flushPromises();
    await button(w, "Add").trigger("click");
    await flushPromises();
    expect(api.addWordToList).toHaveBeenCalledWith(1, {
      section_name: "Day 1",
      hanzi: "茶",
      meaning: "tea",
    });
    expect(w.find('[role="status"]').text()).toBe("Already in “Day 1”.");
  });

  it("collapses for a new word", async () => {
    const w = mount(AddToListPanel, { props: { word: word("茶") }, global: { stubs: { RouterLink: true } } });
    await button(w, "Add to vocab list").trigger("click");
    await flushPromises();
    await w.setProps({ word: word("水") });
    expect(w.text()).toContain("Add to vocab list");
  });
});
