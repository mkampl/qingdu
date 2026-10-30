/**
 * Timestamps from the API are UTC. Most carry a trailing `Z`, but older
 * servers and cached payloads send naive strings like
 * "2026-03-01T23:30:00", which `new Date()` reads as *local* time — west
 * of UTC a card due in one minute would look hours away. Every API
 * timestamp goes through parseUtc().
 */

// A trailing Z or ±HH:MM / ±HHMM offset.
const HAS_OFFSET = /(?:[zZ]|[+-]\d{2}:?\d{2})$/;
// A date-only value ("2026-03-01") is already parsed as UTC by Date.
const DATE_ONLY = /^\d{4}-\d{2}-\d{2}$/;

/** Epoch milliseconds of an API timestamp, or null when missing/invalid. */
export function parseUtcMs(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const s = iso.trim();
  if (!s) return null;
  const normalized = HAS_OFFSET.test(s) || DATE_ONLY.test(s) ? s : `${s}Z`;
  const ms = Date.parse(normalized);
  return Number.isNaN(ms) ? null : ms;
}

/** Date of an API timestamp, or null when missing/invalid. */
export function parseUtc(iso: string | null | undefined): Date | null {
  const ms = parseUtcMs(iso);
  return ms === null ? null : new Date(ms);
}

/** Local date string for an API timestamp ("" when missing/invalid). */
export function formatUtcDate(
  iso: string | null | undefined,
  options?: Intl.DateTimeFormatOptions,
): string {
  const d = parseUtc(iso);
  return d ? d.toLocaleDateString(undefined, options) : "";
}
