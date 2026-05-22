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
 * Display label for the "submit current form" shortcut.
 *
 * Why this exists: we used to render "⌘⏎" universally, which falls back to
 * tofu boxes on Linux + most Windows browsers because the system fonts don't
 * carry U+2318 / U+23CE. Plain text ("Ctrl + Enter") renders everywhere.
 */
export const submitShortcutLabel = isMac ? "⌘ + Enter" : "Ctrl + Enter";
