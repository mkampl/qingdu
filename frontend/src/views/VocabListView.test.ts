import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "@/api/client";
import type { VocabularyListSummary } from "@/api/types";
import { useAuthStore } from "@/stores/auth";
import { useVocabListsStore } from "@/stores/vocab-lists";

vi.mock("vue-router", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  RouterLink: { props: ["to"], template: "<a><slot /></a>" },
}));

import VocabListView from "./VocabListView.vue";

const LIST = {
  id: 3,
  name: "Trip",
  apply_as_glossary: false,
  sections: [
    { name: "A", words: [{ hanzi: "一", pinyin: "yī", meaning: "one", level: "Custom" }] },
    { name: "B", words: [{ hanzi: "二", pinyin: "èr", meaning: "two", level: "Custom" }] },
  ],
} as unknown as VocabularyListSummary;

function buttons(w: VueWrapper, title: string) {
  return w.findAll(`button[title="${title}"]`);
}

describe("VocabListView", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    const auth = useAuthStore();
    auth.user = { username: "a" } as never;
    auth.hydrated = true;
    vi.spyOn(useVocabListsStore(), "invalidate").mockResolvedValue(undefined as never);
    vi.spyOn(api, "getVocabularyList").mockResolvedValue(structuredClone(LIST));
  });
  afterEach(() => {
    vi.restoreAllMocks();
    document.body.innerHTML = "";
  });

  it("renders the list with counts and its sections", async () => {
    const w = mount(VocabListView, { props: { id: "3" } });
    await flushPromises();
    expect(w.text()).toContain("Trip");
    expect(w.text()).toContain("2 words · 2 sections");
    expect(w.text()).toContain("一");
    expect(w.text()).toContain("二");
  });

  it("arms one word delete at a time, across sections, and deletes it", async () => {
    const del = vi.spyOn(api, "deleteWordFromList").mockResolvedValue(undefined as never);
    const w = mount(VocabListView, { props: { id: "3" } });
    await flushPromises();
    await buttons(w, "Delete word")[0].trigger("click");
    expect(buttons(w, "Delete word")).toHaveLength(1);
    await buttons(w, "Delete word")[0].trigger("click");
    expect(buttons(w, "Delete word")).toHaveLength(1);
    await w.findAll("button").find((b) => b.text() === "Delete")!.trigger("click");
    await flushPromises();
    expect(del).toHaveBeenCalledExactlyOnceWith(3, { section_name: "B", hanzi: "二" });
    expect(w.text()).not.toContain("二");
    expect(buttons(w, "Delete word")).toHaveLength(1);
  });

  it("a deleted section's name is not left armed", async () => {
    vi.spyOn(api, "deleteSection").mockResolvedValue(undefined as never);
    vi.spyOn(api, "addSectionToList").mockResolvedValue(undefined as never);
    const w = mount(VocabListView, { props: { id: "3" } });
    await flushPromises();
    await buttons(w, "Delete section B")[0].trigger("click");
    await w.findAll("button").find((b) => b.text() === "Delete section")!.trigger("click");
    await flushPromises();
    expect(w.text()).not.toContain("二");
    await w.find('input[placeholder="New section name"]').setValue("B");
    await w.find("form").trigger("submit");
    await flushPromises();
    expect(buttons(w, "Delete section B")).toHaveLength(1);
  });

  it("adds a word to a section through the modal", async () => {
    const add = vi.spyOn(api, "addWordToList").mockResolvedValue({ pinyin: "sān" } as never);
    const w = mount(VocabListView, { props: { id: "3" }, attachTo: document.body });
    await flushPromises();
    await w.findAll("button").filter((b) => b.text() === "+ Word")[1].trigger("click");
    await flushPromises();
    const input = document.body.querySelector<HTMLInputElement>('input[placeholder="你好"]')!;
    input.value = " 三 ";
    input.dispatchEvent(new Event("input"));
    await flushPromises();
    document.body.querySelector<HTMLFormElement>("form.space-y-4")!.requestSubmit();
    await flushPromises();
    expect(add).toHaveBeenCalledExactlyOnceWith(3, { section_name: "B", hanzi: "三", meaning: "" });
    expect(w.text()).toContain("sān");
    w.unmount();
  });
});
