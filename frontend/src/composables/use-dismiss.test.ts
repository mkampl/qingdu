import { mount } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";
import { defineComponent, h, nextTick, ref } from "vue";

import type { DismissOptions } from "@/composables/use-dismiss";
import { useDismiss } from "@/composables/use-dismiss";
import { _resetOverlays, openOverlay } from "@/utils/modal-stack";

function host(options: DismissOptions = {}) {
  const open = ref(false);
  const dismiss = vi.fn(() => (open.value = false));
  const Host = defineComponent({
    setup() {
      const root = ref<HTMLElement | null>(null);
      useDismiss(open, root, dismiss, options);
      return () =>
        h("div", [
          h("div", { ref: root, id: "inside" }),
          h("span", { id: "outside" }),
          h("span", { id: "word", class: "hsk-wash" }),
        ]);
    },
  });
  const wrapper = mount(Host, { attachTo: document.body });
  const click = (id: string) => document.getElementById(id)!.click();
  return { open, dismiss, wrapper, click };
}

const escape = () => document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));

describe("useDismiss", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    _resetOverlays();
    document.body.innerHTML = "";
  });

  it("listens only while open", async () => {
    const add = vi.spyOn(document, "addEventListener");
    const remove = vi.spyOn(document, "removeEventListener");
    const { open, wrapper } = host();
    expect(add).not.toHaveBeenCalled();
    open.value = true;
    await nextTick();
    expect(add).toHaveBeenCalledWith("click", expect.any(Function));
    expect(add).toHaveBeenCalledWith("keydown", expect.any(Function));
    open.value = false;
    await nextTick();
    expect(remove).toHaveBeenCalledWith("click", expect.any(Function));
    expect(remove).toHaveBeenCalledWith("keydown", expect.any(Function));
    wrapper.unmount();
  });

  it("removes the listeners when unmounted while open", async () => {
    const { open, wrapper } = host({ capture: true });
    open.value = true;
    await nextTick();
    const remove = vi.spyOn(document, "removeEventListener");
    wrapper.unmount();
    expect(remove).toHaveBeenCalledWith("click", expect.any(Function), true);
    expect(remove).toHaveBeenCalledWith("keydown", expect.any(Function));
  });

  it("closes on a click outside, not inside or on an ignored target", async () => {
    const { open, dismiss, click, wrapper } = host({
      ignore: (t) => !!(t as HTMLElement).closest(".hsk-wash"),
    });
    open.value = true;
    await nextTick();
    click("inside");
    click("word");
    expect(dismiss).not.toHaveBeenCalled();
    click("outside");
    expect(dismiss).toHaveBeenCalledTimes(1);
    wrapper.unmount();
  });

  it("closes on Escape unless a dialog is on top and the caller yields", async () => {
    const plain = host();
    plain.open.value = true;
    await nextTick();
    openOverlay();
    escape();
    expect(plain.dismiss).toHaveBeenCalledTimes(1);
    plain.wrapper.unmount();
    _resetOverlays();

    const yielding = host({ yieldToOverlays: true });
    yielding.open.value = true;
    await nextTick();
    openOverlay();
    escape();
    expect(yielding.dismiss).not.toHaveBeenCalled();
    _resetOverlays();
    escape();
    expect(yielding.dismiss).toHaveBeenCalledTimes(1);
    yielding.wrapper.unmount();
  });
});
