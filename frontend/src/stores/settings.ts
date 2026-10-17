import { defineStore } from "pinia";
import { ref, watch } from "vue";

import { storageSet } from "@/utils/storage";
import {
  DEFAULT_AUTO_GRADE_DELAY,
  normalizeAutoGradeDelay,
  type AutoGradeDelay,
} from "@/utils/review";

export type Theme = "light" | "dark";
export type PinyinMode = "auto" | "on" | "off";
export type HskVersion = "new" | "old";
export type ColorMode = "progress" | "hsk" | "off";

const STORAGE_KEY = "qingdu.settings.v2";

interface Persisted {
  theme: Theme;
  pinyinMode: PinyinMode;
  hskVersion: HskVersion;
  showLegend: boolean;
  colorMode: ColorMode;
  writingShowOutline: boolean;
  // Native-only on Android via @capacitor/local-notifications; ignored on web.
  // `reminderTime` is "HH:MM" 24h. The reminder body shows the cached
  // due-count from the last app session — never an exact live number, but
  // accurate enough to motivate a return visit.
  reminderEnabled: boolean;
  reminderTime: string;
  hapticsEnabled: boolean;
  // When true, the first click on a word auto-promotes its state from
  // 'new' to 'learning' so it enters the SRS queue without an explicit
  // tap on the Learning button. Off by default — the popover already
  // surfaces the Learning/Known/Ignored buttons for explicit enrolment,
  // and the user's usual intent on tap is "what does this mean", not
  // "schedule a review of this word for the next decade".
  autoLearnOnClick: boolean;
  // Phase 1.3 — when true, the review session uses a single modality
  // (the one the user picks from the picker) and advances FSRS on every
  // grade — the pre-Phase-1.3 behaviour. False (default) runs Mixed mode:
  // each card cycles through Recognition → Cloze → Dictation → Writing
  // and FSRS only advances when all four have been graded Good+. Power
  // users who only want to drill one modality can flip this from the
  // Review view's Advanced disclosure; we persist it across sessions.
  reviewSingleMode: boolean;
  // How long the suggested grade waits before firing after a writing
  // quiz (ms). 0 turns auto-grading off; the user then always picks.
  autoGradeDelayMs: AutoGradeDelay;
}

function loadFromStorage(): Persisted {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const merged = { ...defaults(), ...(JSON.parse(raw) as Partial<Persisted>) };
      merged.autoGradeDelayMs = normalizeAutoGradeDelay(merged.autoGradeDelayMs);
      return merged;
    }
  } catch {
    // ignore — fall through to defaults
  }
  return defaults();
}

function defaults(): Persisted {
  const prefersDark =
    typeof window !== "undefined" &&
    window.matchMedia?.("(prefers-color-scheme: dark)").matches;
  return {
    theme: prefersDark ? "dark" : "light",
    pinyinMode: "auto",
    hskVersion: "new",
    showLegend: false,
    // 'hsk' is the default — the rainbow gives an immediate difficulty
    // signal that's useful even before the user has marked any words.
    // 'progress' (LingQ-style blue/accent/plain) and 'off' (plain text)
    // are opt-in from the Settings modal.
    colorMode: "hsk",
    // Anki-style by default: nothing to trace, recall from pinyin + meaning.
    writingShowOutline: false,
    reminderEnabled: false,
    reminderTime: "19:00",
    hapticsEnabled: true,
    autoLearnOnClick: false,
    reviewSingleMode: false,
    autoGradeDelayMs: DEFAULT_AUTO_GRADE_DELAY,
  };
}

/** Preferences kept on the account (users.ui_settings) so every device
 *  shows the same; theme, reminder and haptics stay per device. */
export const SYNCED_KEYS = [
  "pinyinMode",
  "hskVersion",
  "colorMode",
  "showLegend",
  "writingShowOutline",
  "autoLearnOnClick",
  "reviewSingleMode",
  "autoGradeDelayMs",
] as const;
export type SyncedSettings = Pick<Persisted, (typeof SYNCED_KEYS)[number]>;

export const useSettingsStore = defineStore("settings", () => {
  const theme = ref<Theme>("light");
  const pinyinMode = ref<PinyinMode>("auto");
  const hskVersion = ref<HskVersion>("new");
  const showLegend = ref(false);
  // Must match defaults().colorMode — any read before hydrate() (or a
  // storage failure) otherwise shows a different mode than a fresh user
  // actually gets.
  const colorMode = ref<ColorMode>("hsk");
  const writingShowOutline = ref(false);
  const reminderEnabled = ref(false);
  const reminderTime = ref("19:00");
  const hapticsEnabled = ref(true);
  const autoLearnOnClick = ref(false);
  const reviewSingleMode = ref(false);
  const autoGradeDelayMs = ref<AutoGradeDelay>(DEFAULT_AUTO_GRADE_DELAY);
  let hydrated = false;

  function applyTheme(value: Theme) {
    if (typeof document === "undefined") return;
    document.documentElement.classList.toggle("dark", value === "dark");
  }

  function hydrate() {
    if (hydrated) return;
    const persisted = loadFromStorage();
    theme.value = persisted.theme;
    pinyinMode.value = persisted.pinyinMode;
    hskVersion.value = persisted.hskVersion;
    showLegend.value = persisted.showLegend;
    colorMode.value = persisted.colorMode;
    writingShowOutline.value = persisted.writingShowOutline;
    reminderEnabled.value = persisted.reminderEnabled;
    reminderTime.value = persisted.reminderTime;
    hapticsEnabled.value = persisted.hapticsEnabled;
    autoLearnOnClick.value = persisted.autoLearnOnClick;
    reviewSingleMode.value = persisted.reviewSingleMode;
    autoGradeDelayMs.value = persisted.autoGradeDelayMs;
    applyTheme(theme.value);
    hydrated = true;
  }

  function persist() {
    if (typeof localStorage === "undefined") return;
    const payload: Persisted = {
      theme: theme.value,
      pinyinMode: pinyinMode.value,
      hskVersion: hskVersion.value,
      showLegend: showLegend.value,
      colorMode: colorMode.value,
      writingShowOutline: writingShowOutline.value,
      reminderEnabled: reminderEnabled.value,
      reminderTime: reminderTime.value,
      hapticsEnabled: hapticsEnabled.value,
      autoLearnOnClick: autoLearnOnClick.value,
      reviewSingleMode: reviewSingleMode.value,
      autoGradeDelayMs: autoGradeDelayMs.value,
    };
    storageSet(STORAGE_KEY, JSON.stringify(payload));
  }

  watch(
    [theme, pinyinMode, hskVersion, showLegend, colorMode, writingShowOutline,
     reminderEnabled, reminderTime, hapticsEnabled, autoLearnOnClick,
     reviewSingleMode, autoGradeDelayMs],
    () => {
      if (hydrated) persist();
    },
  );

  watch(theme, applyTheme);

  /** The account-wide preferences as they are now. */
  function syncedSnapshot(): SyncedSettings {
    return {
      pinyinMode: pinyinMode.value,
      hskVersion: hskVersion.value,
      colorMode: colorMode.value,
      showLegend: showLegend.value,
      writingShowOutline: writingShowOutline.value,
      autoLearnOnClick: autoLearnOnClick.value,
      reviewSingleMode: reviewSingleMode.value,
      autoGradeDelayMs: autoGradeDelayMs.value,
    };
  }

  /** Take the account's preferences (the server checked every value). */
  function applySynced(remote: Partial<SyncedSettings>) {
    if (remote.pinyinMode !== undefined) pinyinMode.value = remote.pinyinMode;
    if (remote.hskVersion !== undefined) hskVersion.value = remote.hskVersion;
    if (remote.colorMode !== undefined) colorMode.value = remote.colorMode;
    if (remote.showLegend !== undefined) showLegend.value = remote.showLegend;
    if (remote.writingShowOutline !== undefined) {
      writingShowOutline.value = remote.writingShowOutline;
    }
    if (remote.autoLearnOnClick !== undefined) autoLearnOnClick.value = remote.autoLearnOnClick;
    if (remote.reviewSingleMode !== undefined) reviewSingleMode.value = remote.reviewSingleMode;
    if (remote.autoGradeDelayMs !== undefined) {
      autoGradeDelayMs.value = normalizeAutoGradeDelay(remote.autoGradeDelayMs);
    }
  }

  function toggleTheme() {
    theme.value = theme.value === "dark" ? "light" : "dark";
  }

  return {
    theme,
    pinyinMode,
    hskVersion,
    showLegend,
    colorMode,
    writingShowOutline,
    reminderEnabled,
    reminderTime,
    hapticsEnabled,
    autoLearnOnClick,
    reviewSingleMode,
    autoGradeDelayMs,
    hydrate,
    toggleTheme,
    syncedSnapshot,
    applySynced,
  };
});
