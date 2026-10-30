import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { WordInfo } from "@/api/types";
import WordPopover from "@/components/reader/WordPopover.vue";
import { useReaderStore } from "@/stores/reader";
import { _resetOverlays, hasOpenOverlay, openOverlay } from "@/utils/modal-stack";

const word = (text: string) => ({ text, pinyin: "x", meaning: "m" }) as WordInfo;

// A reading text: two HSK-wash words that select themselves on click,
// as ReadingText does, plus plain page content outside the popover.
function page() {
  const reader = useReaderStore();
  document.body.insertAdjacentHTML(
    "beforeend",
    `<p id="text"><span id="w1" class="hsk-wash">感冒</span>
     <span id="w2" class="hsk-wash">医生</span>
     <span id="plain">。</span></p>`,
  );
  for (const [id, text] of [
    ["w1", "感冒"],
    ["w2", "医生"],
  ] as const) {
    const el = document.getElementById(id)!;
    el.addEventListener("click", (e) => {
      e.stopPropagation();
      reader.selectWord(word(text), el, { key: "s1", text: "句子" });
    });
  }
  const wrapper = mount(WordPopover, { attachTo: document.body });
  return { reader, wrapper };
}

const click = (id: string) => document.getElementById(id)!.click();
const popover = () => document.querySelector('[role="dialog"]');
const escape = () =>
  document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));

describe("WordPopover dismiss", () => {
  beforeEach(() => setActivePinia(createPinia()));
  afterEach(() => {
    vi.restoreAllMocks();
    _resetOverlays();
    document.body.innerHTML = "";
  });

  it("stays open after the click that opens it", async () => {
    const { reader, wrapper } = page();
    click("w1");
    await flushPromises();
    expect(reader.selectedWord?.text).toBe("感冒");
    expect(popover()).toBeTruthy();
    wrapper.unmount();
  });

  it("stays open when opened by a click on a non-word element", async () => {
    // The capture listener only exists once the opening click has passed
    // the document, so it can't see that click.
    const { reader, wrapper } = page();
    const btn = document.createElement("button");
    btn.addEventListener("click", () => reader.selectWord(word("你"), btn));
    document.body.appendChild(btn);
    btn.click();
    await flushPromises();
    expect(reader.selectedWord?.text).toBe("你");
    wrapper.unmount();
  });

  it("switches to another word instead of closing", async () => {
    const { reader, wrapper } = page();
    click("w1");
    await flushPromises();
    click("w2");
    await flushPromises();
    expect(reader.selectedWord?.text).toBe("医生");
    expect(popover()?.textContent).toContain("医生");
    wrapper.unmount();
  });

  it("closes on a click outside, not inside, and reopens", async () => {
    const { reader, wrapper } = page();
    click("w1");
    await flushPromises();
    (popover() as HTMLElement).click();
    await flushPromises();
    expect(reader.selectedWord).not.toBeNull();
    click("plain");
    await flushPromises();
    expect(reader.selectedWord).toBeNull();
    click("w2");
    await flushPromises();
    expect(reader.selectedWord?.text).toBe("医生");
    wrapper.unmount();
  });

  it("leaves Escape to a dialog on top", async () => {
    const { reader, wrapper } = page();
    click("w1");
    await flushPromises();
    openOverlay();
    escape();
    expect(reader.selectedWord).not.toBeNull();
    _resetOverlays();
    escape();
    expect(reader.selectedWord).toBeNull();
    wrapper.unmount();
  });

  it("closes the mobile bottom sheet on a tap outside", async () => {
    window.innerWidth = 400;
    const { reader, wrapper } = page();
    click("w1");
    await flushPromises();
    expect(popover()?.className).toContain("bottom-3");
    click("w2");
    await flushPromises();
    expect(reader.selectedWord?.text).toBe("医生");
    click("plain");
    expect(reader.selectedWord).toBeNull();
    window.innerWidth = 1024;
    wrapper.unmount();
  });

  it("Escape closes the popover before an open sentence", async () => {
    // ReaderView's handler, registered on mount (after WordPopover's).
    // The popover listens only while open, so its handler runs after
    // this one and one Escape closes one layer.
    const { reader, wrapper } = page();
    const onGlobalKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !hasOpenOverlay()) {
        if (!reader.selectedWord && reader.openSentenceKey) reader.closeSentence();
      }
    };
    document.addEventListener("keydown", onGlobalKey);
    reader.openSentenceKey = "s1";
    click("w1");
    await flushPromises();
    escape();
    expect(reader.selectedWord).toBeNull();
    expect(reader.openSentenceKey).toBe("s1");
    escape();
    expect(reader.openSentenceKey).toBeNull();
    document.removeEventListener("keydown", onGlobalKey);
    wrapper.unmount();
  });
});
