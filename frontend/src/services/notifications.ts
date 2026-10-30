/**
 * Daily-reminder and account-lifecycle local notifications.
 *
 * Android only; every call is a no-op on web. The reminder body uses the
 * due count and streak cached at the last stats refresh, since the API
 * can't be reached reliably from the background. The next 30 days are
 * scheduled up front and rescheduled on app open, which refreshes the
 * count and extends the horizon.
 */

import {
  LocalNotifications,
  type ScheduleOptions,
} from "@capacitor/local-notifications";

import { isNative } from "@/services/native";

const CHANNEL_ID = "qingdu-daily-reminder";
const NOTIFICATION_BASE_ID = 71700;
// Range of an evening at-risk slot that is not scheduled any more;
// cancelExisting() still clears it so a device with slots pending there
// stops firing them.
const AT_RISK_BASE_ID = 71800;
// Lifecycle warnings. Two slots: a 7-day pre-warning and a
// 1-day pre-warning before the server soft-deletes (dormant) the account.
// `+0` = 7-day, `+1` = 1-day. Self-host instances and admin accounts get
// `soft_delete_at = null` from /api/auth/me and we never schedule.
const LIFECYCLE_BASE_ID = 71900;
const LIFECYCLE_CHANNEL_ID = "qingdu-account-lifecycle";
const HORIZON_DAYS = 30;
const CACHE_KEY = "qingdu.notif.lastDueCount";
const STREAK_KEY = "qingdu.notif.lastStreak";

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

/** Cache the streak count alongside the due count so the reminder body
 *  can lead with a live streak. */
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

/** Drop the cached due-count / streak of the signed-in
 *  account, so the next account's reminder doesn't quote someone else's
 *  numbers. Called from resetUserScopedStores on logout / user switch. */
export function forgetUserCaches(): void {
  for (const key of [CACHE_KEY, STREAK_KEY]) {
    try {
      localStorage.removeItem(key);
    } catch {
      // ignore
    }
  }
}

async function requestPermission(): Promise<boolean> {
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

/** Permission check WITHOUT the system dialog. For background schedulers
 *  (lifecycle warnings on login) that must never be the thing that pops
 *  Android 13+'s permission prompt — an unexplained prompt is an instant
 *  deny. Only a user gesture (the reminder toggle) may call
 *  requestPermission(). */
async function hasPermission(): Promise<boolean> {
  if (!isNative()) return false;
  try {
    const status = await LocalNotifications.checkPermissions();
    return status.display === "granted";
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
  // Cancel every ID either range can hold rather than filtering
  // getPending(): unknown IDs are a no-op, and the getPending() path
  // silently dropped at-risk slots on some Android builds, leaving them
  // firing alongside the main reminder. removeAllDelivered then clears
  // copies already shown in the shade.
  const ids: { id: number }[] = [];
  for (let i = 0; i < HORIZON_DAYS + 5; i++) {
    ids.push({ id: NOTIFICATION_BASE_ID + i });
    ids.push({ id: AT_RISK_BASE_ID + i });
  }
  try {
    await LocalNotifications.cancel({ notifications: ids });
  } catch {
    // ignore — the next schedule call will overwrite by id anyway
  }
  try {
    await LocalNotifications.removeAllDeliveredNotifications();
  } catch {
    // older plugin versions don't expose this — fine.
  }
}

/** Cancel any scheduled lifecycle warnings. Called
 *  before every reschedule so old `soft_delete_at` slots don't linger when
 *  the user moves their horizon forward by opening the app. */
async function cancelLifecycleWarnings(): Promise<void> {
  if (!isNative()) return;
  try {
    await LocalNotifications.cancel({
      notifications: [
        { id: LIFECYCLE_BASE_ID },
        { id: LIFECYCLE_BASE_ID + 1 },
      ],
    });
  } catch {
    // ignore
  }
}

async function ensureLifecycleChannel(): Promise<void> {
  if (!isNative()) return;
  try {
    await LocalNotifications.createChannel({
      id: LIFECYCLE_CHANNEL_ID,
      name: "Account lifecycle",
      description: "Heads-up before an unused demo account is paused.",
      importance: 4, // IMPORTANCE_HIGH — wants to be seen, this one really matters
      visibility: 1,
      lights: false,
      vibration: false,
    });
  } catch {
    // Android 7 and below — no channels.
  }
}

function nextSlot(timeHHMM: string, dayOffset: number): Date {
  // Resolve the next firing (today or tomorrow, never past) first, then
  // add the day offset, so slot i is exactly 24 h after slot i-1.
  // Offsetting first and then pushing a past i=0 by a day would land it
  // on the same instant as i=1, and Android shows both (the IDs differ).
  const [hh, mm] = timeHHMM.split(":").map((s) => parseInt(s, 10) || 0);
  const d = new Date();
  d.setHours(hh, mm, 0, 0);
  if (d.getTime() < Date.now()) {
    d.setDate(d.getDate() + 1);
  }
  d.setDate(d.getDate() + dayOffset);
  return d;
}

function body(count: number, streak: number): string {
  // Once a streak is alive, lead with it rather than the queue count.
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

async function scheduleDaily(timeHHMM: string): Promise<boolean> {
  if (!isNative()) return false;
  const ok = await requestPermission();
  if (!ok) return false;
  await ensureChannel();
  await cancelExisting();

  const count = lastDueCount();
  const streak = lastStreak();
  const text = body(count, streak);

  // One slot per day for HORIZON_DAYS.
  const notifications = Array.from({ length: HORIZON_DAYS }, (_, i) => ({
    id: NOTIFICATION_BASE_ID + i,
    title: "QingDu — 轻读",
    body: text,
    schedule: { at: nextSlot(timeHHMM, i) },
    channelId: CHANNEL_ID,
    // Deep-link route, read by App.vue's onNotificationTap handler so a
    // tap opens /review instead of the Reader.
    extra: { route: "/review" },
  }));

  try {
    await LocalNotifications.schedule({ notifications } as ScheduleOptions);
    return true;
  } catch {
    return false;
  }
}

/** Called on app boot + after settings change.
 *
 *  Returns false ONLY when the user asked for reminders and scheduling
 *  failed (permission denied). Callers use that to flip the Settings
 *  toggle back off — a toggle that stays on while nothing is scheduled
 *  is a lie. Web / disabled both return true ("nothing wrong"). */
export async function syncFromSettings(
  enabled: boolean,
  timeHHMM: string,
): Promise<boolean> {
  if (!isNative()) return true;
  if (enabled) {
    return await scheduleDaily(timeHHMM);
  }
  await cancelExisting();
  return true;
}

/**
 * Schedule the two account-lifecycle local notifications
 * from the server's `soft_delete_at` stamp on `/api/auth/me`. Slots:
 *   - 7 days before pause: "QingDu — Your account pauses in 7 days."
 *   - 1 day before pause:  "QingDu — Your account pauses tomorrow."
 *
 * Re-callable: cancels any existing lifecycle slots first, so opening the
 * app (which updates `last_active` server-side and pushes `soft_delete_at`
 * forward) cleanly resets the horizon. Pass `null` to just cancel — used
 * on logout or when the instance has lifecycle cleanup disabled.
 *
 * Web is a no-op. Tapping a fired notification deep-links to `/` so the
 * user's open-the-app action resets `last_active` immediately.
 */
export async function scheduleLifecycleWarnings(
  softDeleteAtIso: string | null,
): Promise<boolean> {
  if (!isNative()) return false;

  await cancelLifecycleWarnings();
  if (!softDeleteAtIso) return false;

  // Check-only: this runs on every demo-server login, which must not be
  // the moment the OS permission dialog appears out of nowhere. If the
  // user has granted notifications (via the reminder toggle), lifecycle
  // warnings ride along; if not, the in-app LifecycleBanner still covers
  // the warning window.
  const ok = await hasPermission();
  if (!ok) return false;
  await ensureLifecycleChannel();

  const target = new Date(softDeleteAtIso);
  if (Number.isNaN(target.getTime())) return false;

  const sevenDay = new Date(target.getTime() - 7 * 24 * 60 * 60 * 1000);
  const oneDay = new Date(target.getTime() - 1 * 24 * 60 * 60 * 1000);
  const now = Date.now();
  const notifications: ScheduleOptions["notifications"] = [];

  if (sevenDay.getTime() > now) {
    notifications.push({
      id: LIFECYCLE_BASE_ID,
      title: "QingDu — 轻读",
      body: "Your account pauses in 7 days. Open the app once to keep it active.",
      schedule: { at: sevenDay },
      channelId: LIFECYCLE_CHANNEL_ID,
      extra: { route: "/" },
    });
  }
  if (oneDay.getTime() > now) {
    notifications.push({
      id: LIFECYCLE_BASE_ID + 1,
      title: "QingDu — 轻读",
      body: "Your account pauses tomorrow. Open the app to keep it active.",
      schedule: { at: oneDay },
      channelId: LIFECYCLE_CHANNEL_ID,
      extra: { route: "/" },
    });
  }

  if (notifications.length === 0) return false;
  try {
    await LocalNotifications.schedule({ notifications } as ScheduleOptions);
    return true;
  } catch {
    return false;
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
