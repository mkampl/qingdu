import { afterEach, describe, expect, it, vi } from "vitest";

import { createShortcutHandler } from "./use-keyboard-shortcuts";

function setup() {
  const shortcuts = {
    overlayOpen: false,
    toggleOverlay: vi.fn(() => {
      shortcuts.overlayOpen = !shortcuts.overlayOpen;
    }),
  };
  const deps = {
    router: { push: vi.fn(() => Promise.resolve()) },
    analysis: { reset: vi.fn() },
    reader: { reset: vi.fn() },
    shortcuts,
    appModals: { openSettings: vi.fn() },
  };
  const { onKey } = createShortcutHandler(deps);
  return { deps, onKey };
}

function press(onKey: (e: KeyboardEvent) => void, key: string, target: EventTarget) {
  const e = new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true });
  Object.defineProperty(e, "target", { value: target });
  onKey(e);
  return e;
}

function openDialog(): HTMLElement {
  const dialog = document.createElement("div");
  dialog.setAttribute("aria-modal", "true");
  document.body.appendChild(dialog);
  return dialog;
}

describe("keyboard shortcut handler", () => {
  afterEach(() => {
    document.body.innerHTML = "";
  });

  it("lets `?` be typed into an input", () => {
    const { deps, onKey } = setup();
    const input = document.createElement("input");
    document.body.appendChild(input);
    const e = press(onKey, "?", input);
    expect(e.defaultPrevented).toBe(false);
    expect(deps.shortcuts.toggleOverlay).not.toHaveBeenCalled();
  });

  it("opens the overlay on `?` outside inputs", () => {
    const { deps, onKey } = setup();
    const e = press(onKey, "?", document.body);
    expect(e.defaultPrevented).toBe(true);
    expect(deps.shortcuts.toggleOverlay).toHaveBeenCalledOnce();
  });

  it("ignores `n`, `g` chords and `?` while a modal is open", () => {
    const { deps, onKey } = setup();
    const button = document.createElement("button");
    openDialog().appendChild(button);

    press(onKey, "n", button);
    press(onKey, "g", button);
    press(onKey, "t", button);
    press(onKey, "?", button);
    expect(deps.analysis.reset).not.toHaveBeenCalled();
    expect(deps.router.push).not.toHaveBeenCalled();
    expect(deps.shortcuts.toggleOverlay).not.toHaveBeenCalled();
  });

  it("still closes the shortcuts overlay with `?`", () => {
    const { deps, onKey } = setup();
    deps.shortcuts.overlayOpen = true;
    openDialog();
    press(onKey, "?", document.body);
    expect(deps.shortcuts.toggleOverlay).toHaveBeenCalledOnce();
    expect(deps.shortcuts.overlayOpen).toBe(false);
  });

  it("routes `g t` when no modal is open", () => {
    const { deps, onKey } = setup();
    press(onKey, "g", document.body);
    press(onKey, "t", document.body);
    expect(deps.router.push).toHaveBeenCalledWith("/texts");
  });
});
