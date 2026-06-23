/**
 * Daily-reminder local notification wrapper.
 *
 * Only does anything on Android (the Capacitor plugin is a no-op on web).
 * The reminder body is built from a *cached* due-count at app-close time —
 * we can't reliably hit the API from the background, so we settle for "X
 * words wanted you yesterday" rather than missing the slot entirely.
 *
 * Channel-of-one strategy: we schedule the next 30 days at the chosen slot
 * up-front, then reschedule on app open (which refreshes the count + extends
 * the horizon). The user controls everything from SettingsModal.
 */

import { Capacitor } from "@capacitor/core";
import {
  LocalNotifications,
  type ScheduleOptions,
} from "@capacitor/local-notifications";

const CHANNEL_ID = "qingdu-daily-reminder";
const NOTIFICATION_BASE_ID = 71700;
// Phase 1.8 shipped an at-risk evening slot at this ID range; v1.0.39
// reverted. We keep the range constants so cancelExisting() can still
// clear the dangling slots on devices that installed v1.0.36 / v1.0.37
// before this revert lands.
const AT_RISK_BASE_ID = 71800;
const HORIZON_DAYS = 30;
const CACHE_KEY = "qingdu.notif.lastDueCount";
const STREAK_KEY = "qingdu.notif.lastStreak";
const ACTIVE_DATE_KEY = "qingdu.notif.lastActiveDate";

export function isNative(): boolean {
  return Capacitor.isNativePlatform();
}

/** Cache the most recent due-count so the reminder body has something
 *  current-ish to show. Called from the review store after every refresh. */
export function rememberDueCount(n: number): void {
  try {
    localStorage.setItem(CACHE_KEY, String(Math.max(0, Math.floor(n))));
  } catch {
    // ignore
  }
}

function lastDueCount(): number {
  try {
    return Math.max(0, parseInt(localStorage.getItem(CACHE_KEY) ?? "0", 10));
  } catch {
    return 0;
  }
}

/** Phase 1.8 — cache the streak count alongside the due count so the
 *  reminder bodies can speak in streak terms when one is alive. */
export function rememberStreak(n: number): void {
  try {
    localStorage.setItem(STREAK_KEY, String(Math.max(0, Math.floor(n))));
  } catch {
    // ignore
  }
}

function lastStreak(): number {
  try {
    return Math.max(0, parseInt(localStorage.getItem(STREAK_KEY) ?? "0", 10));
  } catch {
    return 0;
  }
}

/** Phase 1.8 — every successful user action (open the app, finish a
 *  review) calls this with today's date. The at-risk evening ping checks
 *  the cache: if today's date already matches, skip — the streak isn't
 *  in danger yet. */
export function rememberActiveToday(): void {
  try {
    const today = new Date().toISOString().slice(0, 10);
    localStorage.setItem(ACTIVE_DATE_KEY, today);
  } catch {
    // ignore
  }
}

function activeToday(): boolean {
  try {
    const stored = localStorage.getItem(ACTIVE_DATE_KEY);
    const today = new Date().toISOString().slice(0, 10);
    return stored === today;
  } catch {
    return false;
  }
}

export async function requestPermission(): Promise<boolean> {
  if (!isNative()) return false;
  try {
    const status = await LocalNotifications.checkPermissions();
    if (status.display === "granted") return true;
    const req = await LocalNotifications.requestPermissions();
    return req.display === "granted";
  } catch {
    return false;
  }
}

async function ensureChannel(): Promise<void> {
  if (!isNative()) return;
  try {
    await LocalNotifications.createChannel({
      id: CHANNEL_ID,
      name: "Daily reminders",
      description: "Time-to-read pings — one tap per slot, dismissible.",
      importance: 3, // IMPORTANCE_DEFAULT — sound on lock screen, no peek
      visibility: 1, // VISIBILITY_PUBLIC
      lights: false,
      vibration: false,
    });
  } catch {
    // Android 7 and below don't support channels — silently ignore.
  }
}

async function cancelExisting(): Promise<void> {
  if (!isNative()) return;
  try {
    const pending = await LocalNotifications.getPending();
    const ours = pending.notifications.filter(
      (n) =>
        typeof n.id === "number" &&
        ((n.id >= NOTIFICATION_BASE_ID &&
          n.id < NOTIFICATION_BASE_ID + HORIZON_DAYS + 5) ||
          (n.id >= AT_RISK_BASE_ID && n.id < AT_RISK_BASE_ID + HORIZON_DAYS + 5)),
    );
    if (ours.length) {
      await LocalNotifications.cancel({ notifications: ours.map((n) => ({ id: n.id })) });
    }
  } catch {
    // ignore — the next schedule call will overwrite by id anyway
  }
}

function nextSlot(timeHHMM: string, dayOffset: number): Date {
  const [hh, mm] = timeHHMM.split(":").map((s) => parseInt(s, 10) || 0);
  const d = new Date();
  d.setDate(d.getDate() + dayOffset);
  d.setHours(hh, mm, 0, 0);
  // If today's slot has already passed, push to tomorrow.
  if (dayOffset === 0 && d.getTime() < Date.now()) {
    d.setDate(d.getDate() + 1);
  }
  return d;
}

function body(count: number, streak: number): string {
  // Phase 1.8 — streak-aware copy. Once a streak is alive, lead with it;
  // the prosocial signal hits harder than the raw queue count.
  if (streak > 0 && count > 0) {
    return `🔥 ${streak}-day streak · ${count} ${count === 1 ? "word" : "words"} to review`;
  }
  if (streak > 0) {
    return `🔥 ${streak}-day streak — keep it going with a quick review.`;
  }
  if (count <= 0) return "📚 Time to read — your queue is waiting.";
  if (count === 1) return "📚 1 word is due to review.";
  return `📚 ${count} words are due to review.`;
}

export async function scheduleDaily(timeHHMM: string): Promise<boolean> {
  if (!isNative()) return false;
  const ok = await requestPermission();
  if (!ok) return false;
  await ensureChannel();
  await cancelExisting();

  const count = lastDueCount();
  const streak = lastStreak();
  const text = body(count, streak);

  // One slot per day for HORIZON_DAYS. Phase 1.8 added an evening
  // at-risk slot too but user feedback was "two identical reminders" —
  // the body diverged but the cadence felt double-nag. Reverted to a
  // single streak-aware slot; the body alone communicates urgency.
  const notifications = Array.from({ length: HORIZON_DAYS }, (_, i) => ({
    id: NOTIFICATION_BASE_ID + i,
    title: "QingDu — 轻读",
    body: text,
    schedule: { at: nextSlot(timeHHMM, i) },
    channelId: CHANNEL_ID,
    // Phase #118 (#1) — Deep-link route. Read by App.vue's
    // localNotificationActionPerformed listener so a tap from the
    // reminder takes the user straight to /review instead of dumping
    // them onto the Reader.
    extra: { route: "/review" },
  }));

  try {
    await LocalNotifications.schedule({ notifications } as ScheduleOptions);
    return true;
  } catch {
    return false;
  }
}

export async function cancelDaily(): Promise<void> {
  await cancelExisting();
}

/** Called on app boot + after settings change. */
export async function syncFromSettings(
  enabled: boolean,
  timeHHMM: string,
): Promise<void> {
  if (!isNative()) return;
  if (enabled) {
    await scheduleDaily(timeHHMM);
  } else {
    await cancelDaily();
  }
}

/** Register a callback for "user tapped the reminder notification".
 *  Invoked by App.vue on boot so the router can deep-link to the route
 *  carried in the notification's `extra.route` field. Returns an
 *  unsubscribe function. */
export async function onNotificationTap(
  handler: (route: string) => void,
): Promise<() => void> {
  if (!isNative()) return () => {};
  const sub = await LocalNotifications.addListener(
    "localNotificationActionPerformed",
    (event) => {
      const extra = event.notification?.extra as { route?: string } | undefined;
      const route = extra?.route;
      if (typeof route === "string" && route.length) {
        handler(route);
      }
    },
  );
  return () => {
    void sub.remove();
  };
}
