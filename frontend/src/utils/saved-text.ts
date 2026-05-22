/**
 * Helpers for working with `SavedTextSummary` objects returned from
 * /api/texts. The backend stores `tags` as a JSON-encoded string (or null) and
 * `reading_progress` in a range we have to be defensive about — legacy data
 * was 0-100, the Vue reader writes 0-1.
 */

import type { SavedTextSummary } from "@/api/types";

export function parseTags(raw: string | null | undefined): string[] {
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.filter((t) => typeof t === "string") : [];
  } catch {
    return [];
  }
}

/** Returns a 0..1 fraction, regardless of whether the backend gave 0..1 or 0..100. */
export function normalizeProgress(raw: number | null | undefined): number {
  if (!raw || Number.isNaN(raw)) return 0;
  if (raw <= 1) return Math.max(0, raw);
  return Math.min(1, raw / 100);
}

export function previewSnippet(content: string | undefined, len = 80): string {
  if (!content) return "";
  const cleaned = content.replace(/\s+/g, " ").trim();
  if (cleaned.length <= len) return cleaned;
  return `${cleaned.slice(0, len)}…`;
}

export function formatDate(iso: string): string {
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return "";
    const now = new Date();
    const sameYear = d.getFullYear() === now.getFullYear();
    return d.toLocaleDateString(undefined, {
      year: sameYear ? undefined : "numeric",
      month: "short",
      day: "numeric",
    });
  } catch {
    return "";
  }
}

/**
 * Return true if the saved text matches the search term — case-insensitive
 * match against the title and the tag list.
 */
export function matchesSearch(text: SavedTextSummary, query: string): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  if (text.title && text.title.toLowerCase().includes(q)) return true;
  const tags = parseTags(text.tags);
  return tags.some((t) => t.toLowerCase().includes(q));
}
