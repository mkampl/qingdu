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
// Phase 2.10 — lifecycle warnings. Two slots: a 7-day pre-warning and a
// 1-day pre-warning before the server soft-deletes (dormant) the account.
// `+0` = 7-day, `+1` = 1-day. Self-host instances and admin accounts get
// `soft_delete_at = null` from /api/auth/me and we never schedule.
const LIFECYCLE_BASE_ID = 71900;
const LIFECYCLE_CHANNEL_ID = "qingdu-account-lifecycle";
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

/** Permission check WITHOUT the system dialog. For background schedulers
 *  (lifecycle warnings on login) that must never be the thing that pops
 *  Android 13+'s permission prompt — an unexplained prompt is an instant
 *  deny. Only a user gesture (the reminder toggle) may call
 *  requestPermission(). */
export async function hasPermission(): Promise<boolean> {
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
  // Defensive cancel: enumerate every ID we've ever scheduled across all
  // app versions and pass the lot to LocalNotifications.cancel. Passing
  // unknown IDs is a no-op, so this is safe; it's also more reliable
  // than filtering getPending() — that path silently dropped at-risk
  // slots on some Android builds and left them firing alongside the
  // main reminder (a user reported 'two identical' notifications after
  // the Phase 1.8 → 1.9 transition). A second guard `removeAllDelivered`
  // clears any already-shown copies sitting in the shade.
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

/** Phase 2.10 — cancel any previously-scheduled lifecycle warnings. Called
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
  // Resolve the "first firing" first, then add the day offset. The naïve
  // approach (offset first, then push i=0 by a day if past) collides i=0
  // with i=1 whenever the user opens the app *after* the reminder time:
  // pushed i=0 lands on tomorrow's slot at the same instant as
  // (unshifted) i=1. Android treats them as separate notifications since
  // the IDs differ — the user sees two identical reminders in the tray.
  // The fix: compute the next absolute firing (today or tomorrow, never
  // past), then add dayOffset days to that, so every i strictly leads
  // i-1 by exactly 24 h.
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
  await cancelDaily();
  return true;
}

/**
 * Phase 2.10 — schedule the two account-lifecycle local notifications
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
