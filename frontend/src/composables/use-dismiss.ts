import { getCurrentInstance, onBeforeUnmount, toValue, watch } from "vue";
import type { MaybeRefOrGetter, Ref } from "vue";

import { hasOpenOverlay } from "@/utils/modal-stack";

export interface DismissOptions {
  /** Listen to clicks in the capture phase, before any other handler. */
  capture?: boolean;
  /** Clicks on targets this accepts don't dismiss. */
  ignore?: (target: Node) => boolean;
  /** Leave Escape to a dialog on top (`hasOpenOverlay()`). */
  yieldToOverlays?: boolean;
}

/**
 * Close a menu or popover on a click outside `root` or on Escape. The
 * document listeners exist only while `open` is true; they are removed
 * when it closes and when the component unmounts. A click counts as
 * outside only while `root` is rendered.
 */
export function useDismiss(
  open: MaybeRefOrGetter<boolean>,
  root: Ref<HTMLElement | null>,
  dismiss: () => void,
  options: DismissOptions = {},
) {
  const capture = options.capture === true;

  function onClick(e: MouseEvent) {
    if (!toValue(open)) return;
    const target = e.target as Node;
    if (!root.value || root.value.contains(target)) return;
    if (options.ignore?.(target)) return;
    dismiss();
  }

  function onKey(e: KeyboardEvent) {
    if (e.key !== "Escape" || !toValue(open)) return;
    if (options.yieldToOverlays && hasOpenOverlay()) return;
    dismiss();
  }

  let listening = false;
  function listen() {
    if (listening || typeof document === "undefined") return;
    if (capture) document.addEventListener("click", onClick, true);
    else document.addEventListener("click", onClick);
    document.addEventListener("keydown", onKey);
    listening = true;
  }
  function unlisten() {
    if (!listening) return;
    if (capture) document.removeEventListener("click", onClick, true);
    else document.removeEventListener("click", onClick);
    document.removeEventListener("keydown", onKey);
    listening = false;
  }

  watch(
    () => toValue(open),
    (isOpen) => (isOpen ? listen() : unlisten()),
    { immediate: true },
  );
  if (getCurrentInstance()) onBeforeUnmount(unlisten);
}
