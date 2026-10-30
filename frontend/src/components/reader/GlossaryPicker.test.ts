import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import GlossaryPicker from "@/components/reader/GlossaryPicker.vue";
import { useVocabListsStore } from "@/stores/vocab-lists";

describe("GlossaryPicker", () => {
  beforeEach(() => setActivePinia(createPinia()));
  afterEach(() => vi.restoreAllMocks());

  it("stops listening to the page when it goes away while open", async () => {
    const lists = useVocabListsStore();
    vi.spyOn(lists, "ensureLoaded").mockResolvedValue(undefined as never);
    lists.lists = [{ id: 1, name: "Dao", apply_as_glossary: true } as never];
    const wrapper = mount(GlossaryPicker, { attachTo: document.body });
    await flushPromises();
    await wrapper.get("button").trigger("click");
    const remove = vi.spyOn(document, "removeEventListener");
    wrapper.unmount();
    expect(remove).toHaveBeenCalledWith("click", expect.any(Function));
    expect(remove).toHaveBeenCalledWith("keydown", expect.any(Function));
  });
});
