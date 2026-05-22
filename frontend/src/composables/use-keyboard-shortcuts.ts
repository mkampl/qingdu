import { onBeforeUnmount, onMounted } from "vue";
import { useRouter } from "vue-router";

import { useAnalysisStore } from "@/stores/analysis";
import { useAppModalsStore } from "@/stores/app-modals";
import { useReaderStore } from "@/stores/reader";
import { useShortcutsStore } from "@/stores/shortcuts";

/**
 * App-level keyboard shortcuts. Mounted from App.vue so the bindings exist
 * everywhere, not just when ReaderView is active. We're deliberately
 * conservative about what triggers the handler — if the user is typing into
 * an input/textarea/contenteditable, the only key we still consume is `?`
 * (which is gated to require Shift, not arrive from the IME).
 */
export function useKeyboardShortcuts() {
  const router = useRouter();
  const analysis = useAnalysisStore();
  const reader = useReaderStore();
  const shortcuts = useShortcutsStore();
  const appModals = useAppModalsStore();

  // Two-key chord state for `g <something>` navigation. Cleared automatically
  // by a short timeout so a stray "g" doesn't trap subsequent input.
  let gPending = false;
  let gTimer: ReturnType<typeof setTimeout> | null = null;

  function isTypingTarget(target: EventTarget | null): boolean {
    if (!(target instanceof HTMLElement)) return false;
    const tag = target.tagName;
    if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return true;
    if (target.isContentEditable) return true;
    return false;
  }

  function clearGChord() {
    gPending = false;
    if (gTimer) {
      clearTimeout(gTimer);
      gTimer = null;
    }
  }

  function onKey(e: KeyboardEvent) {
    // Always: ? opens the shortcuts overlay, even in inputs (it requires
    // Shift+/, which won't be typed accidentally).
    if (e.key === "?" && !e.metaKey && !e.ctrlKey && !e.altKey) {
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

    // In an input? Don't consume normal letter keys.
    if (isTypingTarget(e.target)) {
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

  onMounted(() => document.addEventListener("keydown", onKey));
  onBeforeUnmount(() => {
    document.removeEventListener("keydown", onKey);
    clearGChord();
  });
}
