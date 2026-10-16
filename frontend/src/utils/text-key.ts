/**
 * The key that names a text for its pre-learned words: a saved text by
 * id, a library text by slug, anything else (fresh or imported reading)
 * by a hash of its content, so coming back to the same text finds its
 * progress again.
 */
export function textKeyFor(opts: {
  savedTextId: number | null;
  librarySlug: string | null;
  content: string;
}): string {
  if (opts.savedTextId !== null) return `saved:${opts.savedTextId}`;
  if (opts.librarySlug) return `library:${opts.librarySlug}`;
  return `text:${contentHash(opts.content.trim())}`;
}

/** 32-bit FNV-1a over the UTF-16 code units, plus the length. */
export function contentHash(s: string): string {
  let h = 0x811c9dc5;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
  }
  return `${(h >>> 0).toString(16).padStart(8, "0")}-${s.length}`;
}
