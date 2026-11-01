import { computed, onBeforeUnmount, onMounted, ref, watch, type Ref } from "vue";

import { placePopover } from "@/components/reader/utils";
import { useReaderStore } from "@/stores/reader";

/**
 * Where the word popover sits. Below 640 px it is a bottom sheet
 * (`isMobile`); on desktop `desktopPosition` places it at the selected
 * word, using the content's measured height (bind `contentRef`) to flip
 * or cap it. It follows the word while the page scrolls and closes once
 * the word leaves the screen (desktop only).
 */
export function useWordPopoverPlacement(popoverRef: Ref<HTMLElement | null>) {
  const reader = useReaderStore();

  const isMobile = ref(false);
  const contentRef = ref<HTMLElement | null>(null);
  const contentHeight = ref(240);
  const viewport = ref({ width: 1024, height: 800 });
  let contentObserver: ResizeObserver | null = null;

  function measureViewport() {
    viewport.value = { width: window.innerWidth, height: window.innerHeight };
    isMobile.value = window.innerWidth < 640;
  }

  watch(contentRef, (el) => {
    contentObserver?.disconnect();
    contentObserver = null;
    if (!el || typeof ResizeObserver === "undefined") return;
    contentObserver = new ResizeObserver(() => {
      // +1 for the accent rule above the content.
      contentHeight.value = el.offsetHeight + 1;
    });
    contentObserver.observe(el);
  });

  const desktopPosition = computed(() => {
    const anchor = reader.selectedAnchor;
    if (!anchor) return null;
    return placePopover({ anchor, viewport: viewport.value, height: contentHeight.value });
  });

  let scrollFrame = 0;
  function onAnyScroll(e: Event) {
    if (!reader.selectedWord) return;
    if (popoverRef.value && e.target instanceof Node && popoverRef.value.contains(e.target)) {
      return; // scrolling inside the popover itself
    }
    if (scrollFrame) return;
    scrollFrame = requestAnimationFrame(() => {
      scrollFrame = 0;
      const visible = reader.refreshAnchor();
      if (!visible && !isMobile.value) reader.clearWord();
    });
  }
  function onResize() {
    measureViewport();
    if (reader.selectedWord) reader.refreshAnchor();
  }
  onMounted(() => {
    measureViewport();
    window.addEventListener("resize", onResize);
    document.addEventListener("scroll", onAnyScroll, { capture: true, passive: true });
  });
  onBeforeUnmount(() => {
    window.removeEventListener("resize", onResize);
    document.removeEventListener("scroll", onAnyScroll, { capture: true });
    if (scrollFrame) cancelAnimationFrame(scrollFrame);
    contentObserver?.disconnect();
  });

  return { isMobile, contentRef, desktopPosition };
}
