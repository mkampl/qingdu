/**
 * Small native-API adapters. On web, every call is a graceful no-op so
 * components don't need to know whether they run in a Capacitor wrapper.
 */

import { Capacitor } from "@capacitor/core";
import { Haptics, ImpactStyle } from "@capacitor/haptics";
import { Share } from "@capacitor/share";
import { SplashScreen } from "@capacitor/splash-screen";
import { StatusBar, Style } from "@capacitor/status-bar";

export const isNative = (): boolean => Capacitor.isNativePlatform();

// ----- Status bar -----------------------------------------------------------

/** Tint the status bar to match the SPA theme. Called on boot + on every
 *  theme toggle so the OS chrome doesn't fight the WebView. */
export async function syncStatusBar(theme: "light" | "dark"): Promise<void> {
  if (!isNative()) return;
  try {
    await StatusBar.setStyle({
      style: theme === "dark" ? Style.Dark : Style.Light,
    });
    // Background color matches the SPA bg so the status bar feels welded
    // to the app shell, not stuck on top of it.
    await StatusBar.setBackgroundColor({
      color: theme === "dark" ? "#0E0E0E" : "#FFFFFF",
    });
  } catch {
    // Plugin missing or platform unsupported — silent.
  }
}

// ----- Haptics --------------------------------------------------------------

/** Light tap, used on word-click and grade-button-press. */
export async function tap(enabled = true): Promise<void> {
  if (!enabled || !isNative()) return;
  try {
    await Haptics.impact({ style: ImpactStyle.Light });
  } catch {
    // ignore
  }
}

/** Medium impact for success states (grade Easy / page-complete). */
export async function success(enabled = true): Promise<void> {
  if (!enabled || !isNative()) return;
  try {
    await Haptics.impact({ style: ImpactStyle.Medium });
  } catch {
    // ignore
  }
}

// ----- Share ----------------------------------------------------------------

export interface ShareTarget {
  title: string;
  text: string;
  url?: string;
}

/** Native share sheet on Android, navigator.share where available on web,
 *  clipboard copy as the universal fallback. Returns true if it landed
 *  somewhere meaningful so the caller can show a toast. */
export async function share(target: ShareTarget): Promise<"native" | "web" | "clipboard" | "failed"> {
  if (isNative()) {
    try {
      await Share.share(target);
      return "native";
    } catch {
      // user cancelled or plugin failed — fall through
    }
  }
  if (typeof navigator !== "undefined" && "share" in navigator) {
    try {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      await (navigator as any).share(target);
      return "web";
    } catch {
      // dismissed
    }
  }
  // Last resort: clipboard
  const payload = [target.title, target.text, target.url].filter(Boolean).join("\n\n");
  try {
    await navigator.clipboard.writeText(payload);
    return "clipboard";
  } catch {
    return "failed";
  }
}

// ----- Splash --------------------------------------------------------------

export async function hideSplash(): Promise<void> {
  if (!isNative()) return;
  try {
    await SplashScreen.hide({ fadeOutDuration: 200 });
  } catch {
    // ignore
  }
}
