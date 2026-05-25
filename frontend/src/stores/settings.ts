import { defineStore } from "pinia";
import { ref, watch } from "vue";

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
}

function loadFromStorage(): Persisted {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      return { ...defaults(), ...(JSON.parse(raw) as Partial<Persisted>) };
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
  };
}

export const useSettingsStore = defineStore("settings", () => {
  const theme = ref<Theme>("light");
  const pinyinMode = ref<PinyinMode>("auto");
  const hskVersion = ref<HskVersion>("new");
  const showLegend = ref(false);
  const colorMode = ref<ColorMode>("progress");
  const writingShowOutline = ref(false);
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
    };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
  }

  watch(
    [theme, pinyinMode, hskVersion, showLegend, colorMode, writingShowOutline],
    () => {
      if (hydrated) persist();
    },
  );

  watch(theme, applyTheme);

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
    hydrate,
    toggleTheme,
  };
});
