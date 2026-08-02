/**
 * The app shell pins html/body/#app to the viewport height (see
 * index.html's h-full chain) and scrolls inside <main id="app-scroll"
 * class="overflow-y-auto"> instead — window itself never scrolls, so
 * window.scrollTo/scrollY/'scroll' listeners are silent no-ops here.
 * Anything that needs the real scroll position (progress tracking,
 * scroll-to-top, restoring saved reading progress) must target this
 * element instead.
 */
export function appScrollEl(): HTMLElement {
  return (
    (document.getElementById("app-scroll") as HTMLElement | null) ??
    (document.scrollingElement as HTMLElement | null) ??
    document.documentElement
  );
}
