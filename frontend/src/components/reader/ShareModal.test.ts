import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "@/api/client";
import ShareModal from "@/components/reader/ShareModal.vue";

describe("ShareModal", () => {
  beforeEach(() => setActivePinia(createPinia()));
  afterEach(() => {
    vi.restoreAllMocks();
    document.body.innerHTML = "";
  });

  async function linkFor(apiBase: string) {
    vi.spyOn(api, "getApiBase").mockReturnValue(apiBase);
    const wrapper = mount(ShareModal, {
      props: { open: false, textId: 7, initialToken: "tok123456789" },
      attachTo: document.body,
    });
    await wrapper.setProps({ open: true });
    await flushPromises();
    const input = document.querySelector<HTMLInputElement>("input[readonly]");
    wrapper.unmount();
    return input?.value;
  }

  it("points the link at the configured server (the Android app runs on localhost)", async () => {
    expect(await linkFor("https://qingdu.example.org")).toBe(
      "https://qingdu.example.org/s/tok123456789",
    );
  });

  it("uses the page origin on the web build", async () => {
    expect(await linkFor("")).toBe(`${window.location.origin}/s/tok123456789`);
  });
});
