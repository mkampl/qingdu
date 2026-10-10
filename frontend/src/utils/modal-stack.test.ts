import { afterEach, describe, expect, it } from "vitest";

import {
  _resetOverlays,
  closeOverlay,
  hasOpenOverlay,
  isTopOverlay,
  openOverlay,
} from "@/utils/modal-stack";

describe("modal stack", () => {
  afterEach(() => {
    _resetOverlays();
    document.body.style.overflow = "";
  });

  it("locks body scroll until the last overlay closes", () => {
    const a = openOverlay();
    const b = openOverlay();
    expect(document.body.style.overflow).toBe("hidden");
    closeOverlay(b);
    expect(document.body.style.overflow).toBe("hidden");
    closeOverlay(a);
    expect(document.body.style.overflow).toBe("");
    expect(hasOpenOverlay()).toBe(false);
  });

  it("only the newest overlay is on top", () => {
    const a = openOverlay();
    const b = openOverlay();
    expect(isTopOverlay(b)).toBe(true);
    expect(isTopOverlay(a)).toBe(false);
    closeOverlay(b);
    expect(isTopOverlay(a)).toBe(true);
  });

  it("closing out of order keeps the lock and the right top", () => {
    const a = openOverlay();
    const b = openOverlay();
    closeOverlay(a);
    expect(isTopOverlay(b)).toBe(true);
    expect(document.body.style.overflow).toBe("hidden");
  });

  it("restores whatever overflow the body had before", () => {
    document.body.style.overflow = "scroll";
    const a = openOverlay();
    closeOverlay(a);
    expect(document.body.style.overflow).toBe("scroll");
  });

  it("double open / close of one id is harmless", () => {
    const a = openOverlay();
    openOverlay(a);
    const b = openOverlay();
    closeOverlay(a);
    closeOverlay(a);
    expect(hasOpenOverlay()).toBe(true);
    closeOverlay(b);
    expect(hasOpenOverlay()).toBe(false);
  });
});
