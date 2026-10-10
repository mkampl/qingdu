import { mount } from "@vue/test-utils";
import { afterEach, describe, expect, it } from "vitest";
import { defineComponent, h, nextTick, ref } from "vue";

import Modal from "@/components/ui/Modal.vue";
import { _resetOverlays } from "@/utils/modal-stack";

function escape() {
  document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
}

describe("Modal stacking", () => {
  afterEach(() => {
    _resetOverlays();
    document.body.innerHTML = "";
  });

  it("Escape closes only the top modal and the scroll lock holds", async () => {
    const outer = ref(true);
    const inner = ref(false);
    const closed: string[] = [];
    const Host = defineComponent({
      setup: () => () => [
        h(
          Modal,
          {
            open: outer.value,
            title: "Outer",
            onClose: () => {
              closed.push("outer");
              outer.value = false;
            },
          },
          () => h("button", "outer"),
        ),
        h(
          Modal,
          {
            open: inner.value,
            title: "Inner",
            onClose: () => {
              closed.push("inner");
              inner.value = false;
            },
          },
          () => h("button", "inner"),
        ),
      ],
    });
    const wrapper = mount(Host, { attachTo: document.body });
    await nextTick();
    expect(document.body.style.overflow).toBe("hidden");

    inner.value = true;
    await nextTick();

    escape();
    await nextTick();
    expect(closed).toEqual(["inner"]);
    // Outer is still open: the background must stay locked.
    expect(document.body.style.overflow).toBe("hidden");

    escape();
    await nextTick();
    expect(closed).toEqual(["inner", "outer"]);
    expect(document.body.style.overflow).toBe("");
    wrapper.unmount();
  });
});
