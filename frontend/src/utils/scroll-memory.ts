/**
 * Per-history-entry scroll positions for <main id="app-scroll">.
 *
 * Vue Router's scrollBehavior only knows about window, which never scrolls
 * here (see utils/scroll.ts), so App.vue drives this by hand:
 *   - before each navigation, remember where the page being left was;
 *   - after it, scroll to the top for a new page, restore the remembered
 *     position on Back/Forward, and leave query-only changes (tabs,
 *     filters) alone.
 */

export type ScrollAction =
  | { kind: "none" }
  | { kind: "top" }
  | { kind: "restore"; top: number };

export function decideScroll(opts: {
  fromPath: string | null;
  toPath: string;
  isPop: boolean;
  saved: number | undefined;
}): ScrollAction {
  if (opts.isPop && opts.saved !== undefined) {
    return { kind: "restore", top: opts.saved };
  }
  // Same page, different query (/vocab?tab=…, /words filters): keep place.
  if (opts.fromPath === opts.toPath) return { kind: "none" };
  return { kind: "top" };
}

/** Key for the current history entry: Vue Router keeps its index in state. */
export function historyEntryKey(fullPath: string): string {
  const state =
    typeof window !== "undefined"
      ? (window.history.state as { position?: number } | null)
      : null;
  return `${state?.position ?? "?"}|${fullPath}`;
}

export class ScrollMemory {
  private positions = new Map<string, number>();

  constructor(private readonly cap = 50) {}

  save(key: string, top: number) {
    this.positions.delete(key);
    this.positions.set(key, top);
    while (this.positions.size > this.cap) {
      const oldest = this.positions.keys().next().value;
      if (oldest === undefined) break;
      this.positions.delete(oldest);
    }
  }

  get(key: string): number | undefined {
    return this.positions.get(key);
  }
}

/**
 * Scroll `el` to `top` once the page is tall enough — views render their
 * data a moment after the route resolves, so retry for a few frames.
 */
export function restoreScrollTop(el: HTMLElement, top: number, frames = 30) {
  const attempt = (left: number) => {
    el.scrollTop = top;
    if (Math.abs(el.scrollTop - top) <= 1 || left <= 0) return;
    requestAnimationFrame(() => attempt(left - 1));
  };
  attempt(frames);
}
