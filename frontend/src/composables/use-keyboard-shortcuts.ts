import { onBeforeUnmount, onMounted } from "vue";
import { type Router, useRouter } from "vue-router";

import { useAnalysisStore } from "@/stores/analysis";
import { useAppModalsStore } from "@/stores/app-modals";
import { useReaderStore } from "@/stores/reader";
import { useShortcutsStore } from "@/stores/shortcuts";

interface ShortcutDeps {
  router: Pick<Router, "push">;
  analysis: { reset: () => void };
  reader: { reset: () => void };
  shortcuts: { overlayOpen: boolean; toggleOverlay: () => void };
  appModals: { openSettings: () => void };
}

function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return true;
  if (target.isContentEditable) return true;
  return false;
}

// Every open dialog (Modal.vue, the mobile nav drawer) marks itself
// aria-modal. Global shortcuts must not fire behind it — `n` would wipe
// the reader while e.g. Settings has focus on a button.
function isModalOpen(): boolean {
  return document.querySelector('[aria-modal="true"]') !== null;
}

/**
 * The keydown handler behind useKeyboardShortcuts, split out so it can be
 * tested without mounting the app. Order matters: typing targets bail
 * first (so `?`, `n`, `g` can be typed into any field), then open modals.
 */
export function createShortcutHandler(deps: ShortcutDeps) {
  const { router, analysis, reader, shortcuts, appModals } = deps;

  // Two-key chord state for `g <something>` navigation. Cleared automatically
  // by a short timeout so a stray "g" doesn't trap subsequent input.
  let gPending = false;
  let gTimer: ReturnType<typeof setTimeout> | null = null;

  function clearGChord() {
    gPending = false;
    if (gTimer) {
      clearTimeout(gTimer);
      gTimer = null;
    }
  }

  function onKey(e: KeyboardEvent) {
    // In an input? Leave every key to the field.
    if (isTypingTarget(e.target)) {
      clearGChord();
      return;
    }

    const isHelpKey = e.key === "?" && !e.metaKey && !e.ctrlKey && !e.altKey;

    // `?` also closes the shortcuts overlay, which is itself a modal.
    if (isHelpKey && shortcuts.overlayOpen) {
      e.preventDefault();
      shortcuts.toggleOverlay();
      clearGChord();
      return;
    }

    if (isModalOpen()) {
      clearGChord();
      return;
    }

    if (isHelpKey) {
      e.preventDefault();
      shortcuts.toggleOverlay();
      clearGChord();
      return;
    }

    // ⌘/Ctrl + ,  -> Settings (universal "preferences" shortcut on macOS).
    if (e.key === "," && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      appModals.openSettings();
      clearGChord();
      return;
    }

    // Esc closes the chord pending state in case the user changed their mind.
    if (e.key === "Escape") {
      clearGChord();
      return;
    }

    // `g` opens the chord; the next key (r/t/v/a) routes.
    if (gPending) {
      const dest: Record<string, string> = {
        r: "/",
        t: "/texts",
        v: "/vocab",
        a: "/admin",
      };
      const path = dest[e.key];
      if (path) {
        e.preventDefault();
        void router.push(path);
      }
      clearGChord();
      return;
    }

    if (e.key === "g") {
      gPending = true;
      gTimer = setTimeout(clearGChord, 1200);
      return;
    }

    // `n` -> New text. Resets the analysis and reader stores, dropping any
    // currently-loaded saved text.
    if (e.key === "n") {
      e.preventDefault();
      analysis.reset();
      reader.reset();
      void router.push("/");
    }
  }

  return { onKey, clearGChord };
}

/**
 * App-level keyboard shortcuts. Mounted from App.vue so the bindings exist
 * everywhere, not just when ReaderView is active. Deliberately
 * conservative: nothing fires while typing into an input/textarea/
 * contenteditable, or while a modal dialog is open.
 */
export function useKeyboardShortcuts() {
  const { onKey, clearGChord } = createShortcutHandler({
    router: useRouter(),
    analysis: useAnalysisStore(),
    reader: useReaderStore(),
    shortcuts: useShortcutsStore(),
    appModals: useAppModalsStore(),
  });

  onMounted(() => document.addEventListener("keydown", onKey));
  onBeforeUnmount(() => {
    document.removeEventListener("keydown", onKey);
    clearGChord();
  });
}
