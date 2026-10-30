/**
 * Stack of open overlays (dialogs, the mobile nav drawer). One place owns
 * the body scroll lock, so closing one overlay while another is still open
 * doesn't re-enable background scrolling, and Escape is handled only by the
 * overlay on top.
 *
 * Each overlay calls `openOverlay(id)` when it shows and `closeOverlay(id)`
 * when it hides; keydown handlers check `isTopOverlay(id)`.
 * Anything underneath (word popover, sentence translation) checks
 * `hasOpenOverlay()` before reacting to Escape.
 */

const stack: symbol[] = [];
let savedOverflow: string | null = null;

function lockBody() {
  if (typeof document === "undefined" || savedOverflow !== null) return;
  savedOverflow = document.body.style.overflow;
  document.body.style.overflow = "hidden";
}

function unlockBody() {
  if (typeof document === "undefined" || savedOverflow === null) return;
  document.body.style.overflow = savedOverflow;
  savedOverflow = null;
}

/** Register an overlay as open; returns its id. Idempotent per id. */
export function openOverlay(id: symbol = Symbol("overlay")): symbol {
  if (!stack.includes(id)) stack.push(id);
  lockBody();
  return id;
}

/** Remove an overlay (no-op if it isn't open). */
export function closeOverlay(id: symbol) {
  const i = stack.indexOf(id);
  if (i !== -1) stack.splice(i, 1);
  if (stack.length === 0) unlockBody();
}

export function isTopOverlay(id: symbol): boolean {
  return stack.length > 0 && stack[stack.length - 1] === id;
}

export function hasOpenOverlay(): boolean {
  return stack.length > 0;
}

/** Test helper. */
export function _resetOverlays() {
  stack.length = 0;
  unlockBody();
}
