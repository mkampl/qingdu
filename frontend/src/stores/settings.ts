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
    // 'progress' = color by user state (new/learning/known); the LingQ-style
    // default once a learner has a few interactions. 'hsk' keeps the old
    // corpus-level coloring; 'off' is plain text for distraction-free reading.
    colorMode: "progress",
  };
}

export const useSettingsStore = defineStore("settings", () => {
  const theme = ref<Theme>("light");
  const pinyinMode = ref<PinyinMode>("auto");
  const hskVersion = ref<HskVersion>("new");
  const showLegend = ref(false);
  const colorMode = ref<ColorMode>("progress");
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
    };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
  }

  watch([theme, pinyinMode, hskVersion, showLegend, colorMode], () => {
    if (hydrated) persist();
  });

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
    hydrate,
    toggleTheme,
  };
});
