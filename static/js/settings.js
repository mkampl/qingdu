// Settings Management with localStorage
// Settings are stored per-browser, not per-user

const SETTINGS_KEY = 'qingdu_settings';

// Default settings
const DEFAULT_SETTINGS = {
  pinyin_mode: 'auto', // 'on' | 'off' | 'auto'
  hsk_version: 'new',  // 'new' | 'old' - which HSK version to use for coloring
  show_legend: true,   // true | false - show/hide HSK color legend
  // Future settings can be added here:
  // theme: 'light',
  // font_size: 'medium',
  // show_translations: true,
};

// Settings state
let currentSettings = { ...DEFAULT_SETTINGS };

// Load settings from localStorage
function loadSettings() {
  try {
    const stored = localStorage.getItem(SETTINGS_KEY);
    if (stored) {
      const parsed = JSON.parse(stored);
      currentSettings = { ...DEFAULT_SETTINGS, ...parsed };
    }
  } catch (error) {
    console.error('Failed to load settings:', error);
    currentSettings = { ...DEFAULT_SETTINGS };
  }
  return currentSettings;
}

// Save settings to localStorage
function saveSettings(settings) {
  try {
    currentSettings = { ...currentSettings, ...settings };
    localStorage.setItem(SETTINGS_KEY, JSON.stringify(currentSettings));
    return true;
  } catch (error) {
    console.error('Failed to save settings:', error);
    return false;
  }
}

// Get a specific setting
function getSetting(key) {
  return currentSettings[key] ?? DEFAULT_SETTINGS[key];
}

// Update a specific setting
function updateSetting(key, value) {
  const updated = { [key]: value };
  const success = saveSettings(updated);
  if (success) {
    // Trigger settings change event
    window.dispatchEvent(new CustomEvent('settingsChanged', {
      detail: { key, value, settings: currentSettings }
    }));
  }
  return success;
}

// Reset to defaults
function resetSettings() {
  currentSettings = { ...DEFAULT_SETTINGS };
  try {
    localStorage.setItem(SETTINGS_KEY, JSON.stringify(currentSettings));
    window.dispatchEvent(new CustomEvent('settingsChanged', {
      detail: { settings: currentSettings }
    }));
    return true;
  } catch (error) {
    console.error('Failed to reset settings:', error);
    return false;
  }
}

// Export to window
window.SettingsManager = {
  load: loadSettings,
  save: saveSettings,
  get: getSetting,
  update: updateSetting,
  reset: resetSettings,
  getAll: () => ({ ...currentSettings }),
  DEFAULT_SETTINGS
};

// Load settings on script load
loadSettings();
