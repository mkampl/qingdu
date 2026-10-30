/**
 * Tiny platform helpers. Browser-only — guard `window`/`navigator` access
 * if you import these into code that could run during SSR.
 */

const ua =
  typeof navigator !== "undefined"
    ? `${navigator.platform ?? ""} ${navigator.userAgent ?? ""}`
    : "";

export const isMac = /Mac|iPhone|iPad|iPod/i.test(ua);

/**
 * Display label for the "submit current form" shortcut. Plain text off
 * macOS: "⌘⏎" renders as tofu boxes on Linux and most Windows browsers,
 * whose system fonts lack U+2318 / U+23CE.
 */
export const submitShortcutLabel = isMac ? "⌘ + Enter" : "Ctrl + Enter";
