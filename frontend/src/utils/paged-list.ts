/**
 * Small helpers for "Load more"-style lists backed by offset paging.
 * Kept free of Vue so they can be unit-tested directly.
 */

/**
 * Hands out increasing request ids so a view can drop responses that
 * arrive after a newer request was started (filter changed mid-flight,
 * fast typing in a search box, ...).
 */
export function createRequestSequence() {
  let latest = 0;
  return {
    /** Start a new request; every older id becomes stale. */
    next(): number {
      latest += 1;
      return latest;
    },
    /** Id of the newest request, for follow-ups that must not invalidate it. */
    current(): number {
      return latest;
    },
    isLatest(id: number): boolean {
      return id === latest;
    },
  };
}

/**
 * Append a fetched page to the rows already shown, skipping rows whose
 * key is already present. Pages can overlap when rows were edited locally
 * between two fetches (see nextPageOffset).
 */
export function mergePage<T>(current: T[], page: T[], key: (row: T) => string): T[] {
  const seen = new Set(current.map(key));
  const merged = current.slice();
  for (const row of page) {
    const k = key(row);
    if (seen.has(k)) continue;
    seen.add(k);
    merged.push(row);
  }
  return merged;
}

/**
 * Server offset for the next page. `fetched` is how many rows the server
 * has handed out so far; `drift` counts local edits since then (each can
 * drop a row out of the server-side result or move it, shifting later rows
 * up by at most one). Re-reading that many rows is cheap and mergePage
 * drops the duplicates, so nothing at the page boundary gets skipped.
 */
export function nextPageOffset(fetched: number, drift: number): number {
  return Math.max(0, fetched - Math.max(0, drift));
}

/** Size of the next "Load N more" batch. */
export function nextBatchSize(shown: number, total: number, pageSize: number): number {
  return Math.max(0, Math.min(pageSize, total - shown));
}
