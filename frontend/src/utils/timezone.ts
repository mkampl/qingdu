/**
 * The learner's timezone. The server rolls "today" (streak, due today,
 * daily new words, the weekly chart) over at local midnight in the zone
 * stored on the account; the SPA sends the browser's zone once, and the
 * Settings modal lets the user pick another.
 */

// Shown when the runtime can't list its zones (older WebViews).
const COMMON_ZONES = [
  "UTC",
  "Europe/London",
  "Europe/Berlin",
  "Europe/Vienna",
  "Europe/Paris",
  "Europe/Moscow",
  "Asia/Dubai",
  "Asia/Kolkata",
  "Asia/Bangkok",
  "Asia/Shanghai",
  "Asia/Hong_Kong",
  "Asia/Taipei",
  "Asia/Singapore",
  "Asia/Tokyo",
  "Asia/Seoul",
  "Australia/Sydney",
  "Pacific/Auckland",
  "America/Sao_Paulo",
  "America/New_York",
  "America/Chicago",
  "America/Denver",
  "America/Los_Angeles",
  "America/Vancouver",
  "Pacific/Honolulu",
];

/** IANA zone of this device, or null when the runtime doesn't say. */
export function browserTimeZone(): string | null {
  try {
    const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
    return tz ? tz : null;
  } catch {
    return null;
  }
}

/** Zones for the Settings select: the full list when available, always
 *  including the stored zone and this device's zone. Sorted. */
export function timeZoneOptions(...include: Array<string | null | undefined>): string[] {
  let all: string[] = COMMON_ZONES;
  const intl = Intl as unknown as {
    supportedValuesOf?: (key: "timeZone") => string[];
  };
  try {
    if (typeof intl.supportedValuesOf === "function") {
      all = intl.supportedValuesOf("timeZone");
    }
  } catch {
    // Keep the short list.
  }
  const set = new Set(all);
  set.add("UTC");
  for (const tz of include) if (tz) set.add(tz);
  return [...set].sort((a, b) => a.localeCompare(b));
}
