import { flushPromises, mount, RouterLinkStub } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "@/api/client";
import { useAppModalsStore } from "@/stores/app-modals";
import { useAuthStore } from "@/stores/auth";
import { useSettingsStore } from "@/stores/settings";

import SettingsModal from "./SettingsModal.vue";

async function mountOpen() {
  const w = mount(SettingsModal, {
    global: { stubs: { teleport: true, RouterLink: RouterLinkStub } },
  });
  useAppModalsStore().settingsOpen = true;
  await flushPromises();
  return w;
}

describe("SettingsModal", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    vi.spyOn(api, "listApiTokens").mockResolvedValue({ tokens: [] } as never);
  });
  afterEach(() => {
    vi.restoreAllMocks();
    document.body.innerHTML = "";
  });

  it("a pinyin option writes the settings store", async () => {
    const w = await mountOpen();
    const settings = useSettingsStore();
    expect(settings.pinyinMode).not.toBe("off");
    // "off" exists in both Word coloring and Pinyin display; pick by group.
    const pinyin = w
      .findAll("fieldset")
      .find((f) => f.find("legend").text() === "Pinyin display")!;
    await pinyin.find('input[value="off"]').setValue();
    expect(settings.pinyinMode).toBe("off");
    expect(
      pinyin.find('input[value="off"]').element.closest("label")!.className,
    ).toContain("border-accent");
  });

  it("the legend toggle writes the settings store", async () => {
    const w = await mountOpen();
    const settings = useSettingsStore();
    expect(settings.showLegend).toBe(false);
    const label = w
      .findAll("label")
      .find((l) => l.text().startsWith("Show HSK color legend"))!;
    await label.find('input[type="checkbox"]').setValue(true);
    expect(settings.showLegend).toBe(true);
  });

  it("keeps section state and loaded tokens across close and reopen", async () => {
    useAuthStore().user = { username: "a", daily_new_words: 0 } as never;
    const w = await mountOpen();
    const modals = useAppModalsStore();
    const markButton = () => w.findAll("button").find((b) => b.text() === "Mark as known");
    await markButton()!.trigger("click");
    expect(markButton()).toBeUndefined();
    modals.settingsOpen = false;
    await flushPromises();
    modals.settingsOpen = true;
    await flushPromises();
    expect(markButton()).toBeUndefined();
    expect(w.findAll("button").some((b) => b.text() === "Confirm")).toBe(true);
    expect(api.listApiTokens).toHaveBeenCalledTimes(1);
  });

  it("a review window option saves to the account", async () => {
    const auth = useAuthStore();
    auth.user = { username: "a", review_window: "today" } as never;
    const save = vi.spyOn(auth, "updateSettings").mockResolvedValue(undefined as never);
    const w = await mountOpen();
    const group = w
      .findAll("fieldset")
      .find((f) => f.find("legend").text() === "Review window")!;
    await group.find('input[value="now"]').setValue();
    expect(save).toHaveBeenCalledWith({ review_window: "now" });
  });
});
