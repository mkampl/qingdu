import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "@/api/client";
import type { HskBrowseItem, HskBrowseResponse } from "@/api/client";
import { useAuthStore } from "@/stores/auth";
import { useSettingsStore } from "@/stores/settings";
import { useUserWordsStore } from "@/stores/userWords";
import VocabBrowseView from "@/views/VocabBrowseView.vue";

function item(hanzi: string, user_state: HskBrowseItem["user_state"] = null): HskBrowseItem {
  return {
    hanzi,
    pinyin: "",
    meaning: "",
    meanings: [],
    level_new: "new-1",
    level_old: "old-1",
    frequency: null,
    user_state,
  };
}

function deferred<T>() {
  let resolve!: (v: T) => void;
  const promise = new Promise<T>((r) => (resolve = r));
  return { promise, resolve };
}

describe("VocabBrowseView", () => {
  let calls: Array<{ params: Parameters<typeof api.browseHsk>[0]; d: ReturnType<typeof deferred<HskBrowseResponse>> }>;

  beforeEach(() => {
    setActivePinia(createPinia());
    calls = [];
    vi.spyOn(api, "browseHsk").mockImplementation((params) => {
      const d = deferred<HskBrowseResponse>();
      calls.push({ params, d });
      return d.promise;
    });
  });
  afterEach(() => vi.restoreAllMocks());

  const page = (items: HskBrowseItem[], total: number): HskBrowseResponse => ({
    items,
    total,
    offset: 0,
    limit: 60,
  });

  it("a load-more that a level switch overtook doesn't append old rows", async () => {
    const wrapper = mount(VocabBrowseView);
    calls[0].d.resolve(page([item("一")], 200));
    await flushPromises();

    await wrapper.find("button.w-full").trigger("click"); // Load more
    expect(calls[1].params.level).toBe("new-1");

    const tabs = wrapper.findAll('[role="tab"]');
    await tabs.find((t) => t.text() === "HSK 2")!.trigger("click");
    await flushPromises();
    expect(calls[2].params).toMatchObject({ level: "new-2", offset: 0 });

    calls[2].d.resolve(page([item("二")], 1));
    await flushPromises();
    calls[1].d.resolve(page([item("old row")], 200));
    await flushPromises();

    const rows = wrapper.findAll("li").map((li) => li.text());
    expect(rows).toHaveLength(1);
    expect(rows[0]).toContain("二");
  });

  it("offers old-HSK levels when the setting says old", async () => {
    useSettingsStore().hskVersion = "old";
    const wrapper = mount(VocabBrowseView);
    expect(calls[0].params.level).toBe("old-1");
    const tabs = wrapper.findAll('[role="tab"]').map((t) => t.text());
    expect(tabs).toEqual(["All", "HSK 1", "HSK 2", "HSK 3", "HSK 4", "HSK 5", "HSK 6"]);
  });

  it("disables the state buttons for anonymous users", async () => {
    useAuthStore().hydrated = true;
    const wrapper = mount(VocabBrowseView);
    calls[0].d.resolve(page([item("一")], 1));
    await flushPromises();
    const buttons = wrapper.findAll('li [role="group"] button');
    expect(buttons).toHaveLength(3);
    expect(buttons.every((b) => b.attributes("disabled") !== undefined)).toBe(true);
    expect(wrapper.text()).toContain("Sign in");
  });

  it("un-ignores an ignored word", async () => {
    const auth = useAuthStore();
    auth.user = { username: "alice", is_admin: false } as never;
    auth.hydrated = true;
    const words = useUserWordsStore();
    words.states = { 一: "ignored" };
    words.hydrated = true;
    const clear = vi.spyOn(api, "clearUserWordState").mockResolvedValue({} as never);

    const wrapper = mount(VocabBrowseView);
    calls[0].d.resolve(page([item("一", "ignored")], 1));
    await flushPromises();
    const ignore = wrapper.findAll('li [role="group"] button')[2];
    expect(ignore.attributes("aria-pressed")).toBe("true");
    expect(ignore.text()).toBe("Ignored");
    await ignore.trigger("click");
    await flushPromises();
    expect(clear).toHaveBeenCalledWith("一");
    expect(wrapper.findAll('li [role="group"] button')[2].attributes("aria-pressed")).toBe("false");
  });
});
