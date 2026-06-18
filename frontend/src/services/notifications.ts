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
const HORIZON_DAYS = 30;
const CACHE_KEY = "qingdu.notif.lastDueCount";

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
    const ours = pending.notifications.filter((n) =>
      typeof n.id === "number" && n.id >= NOTIFICATION_BASE_ID &&
      n.id < NOTIFICATION_BASE_ID + HORIZON_DAYS + 5,
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

function body(count: number): string {
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
  const text = body(count);
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
