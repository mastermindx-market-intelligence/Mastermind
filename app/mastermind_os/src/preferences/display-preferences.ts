/** Versioned display preferences: the only storage key this module owns. */
export type DisplayTheme = "dark" | "light";
export type DisplayLocale = "en" | "zh-CN";

export interface DisplayPreferences {
  theme: DisplayTheme;
  locale: DisplayLocale;
}

export const DISPLAY_PREFERENCES_STORAGE_KEY = "mastermind-os.display-preferences.v1";
export const DISPLAY_PREFERENCES_VERSION = 1;
export const DEFAULT_DISPLAY_PREFERENCES: DisplayPreferences = { theme: "dark", locale: "en" };

/** UI copy for the controls; every visible label and option is translated. */
export interface DisplayPreferenceCopy {
  disclosure: string;
  region: string;
  theme: string;
  language: string;
  dark: string;
  light: string;
  english: string;
  chinese: string;
}

export const DISPLAY_PREFERENCE_STRINGS: Record<DisplayLocale, DisplayPreferenceCopy> = {
  en: {
    disclosure: "Display settings",
    region: "Display preferences",
    theme: "Theme",
    language: "Language",
    dark: "Dark",
    light: "Light",
    english: "English",
    chinese: "Chinese (Simplified)",
  },
  "zh-CN": {
    disclosure: "显示设置",
    region: "显示偏好",
    theme: "主题",
    language: "语言",
    dark: "深色",
    light: "浅色",
    english: "英语",
    chinese: "中文（简体）",
  },
};

export function isDisplayTheme(value: unknown): value is DisplayTheme {
  return value === "dark" || value === "light";
}

export function isDisplayLocale(value: unknown): value is DisplayLocale {
  return value === "en" || value === "zh-CN";
}

/** Null outside a browser or when storage access itself is blocked. */
export function resolveStorageArea(): Storage | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

/** All-or-nothing: malformed, mistyped, or differently versioned data is unusable. */
export function parseStoredDisplayPreferences(raw: string | null): DisplayPreferences | null {
  if (raw === null) return null;
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return null;
  }
  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) return null;
  const record = parsed as Record<string, unknown>;
  if (record.version !== DISPLAY_PREFERENCES_VERSION) return null;
  if (!isDisplayTheme(record.theme) || !isDisplayLocale(record.locale)) return null;
  return { theme: record.theme, locale: record.locale };
}

export function readDisplayPreferences(): DisplayPreferences {
  const storage = resolveStorageArea();
  if (!storage) return DEFAULT_DISPLAY_PREFERENCES;
  try {
    return parseStoredDisplayPreferences(storage.getItem(DISPLAY_PREFERENCES_STORAGE_KEY)) ?? DEFAULT_DISPLAY_PREFERENCES;
  } catch {
    return DEFAULT_DISPLAY_PREFERENCES;
  }
}

export function serializeDisplayPreferences(preferences: DisplayPreferences): string {
  return JSON.stringify({ version: DISPLAY_PREFERENCES_VERSION, theme: preferences.theme, locale: preferences.locale });
}

/** Reports failure instead of throwing; callers keep the in-memory choice. */
export function writeDisplayPreferences(preferences: DisplayPreferences): boolean {
  const storage = resolveStorageArea();
  if (!storage) return false;
  try {
    storage.setItem(DISPLAY_PREFERENCES_STORAGE_KEY, serializeDisplayPreferences(preferences));
    return true;
  } catch {
    return false;
  }
}
