import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import {
  DISPLAY_PREFERENCE_STRINGS,
  DISPLAY_PREFERENCES_STORAGE_KEY,
  isDisplayLocale,
  isDisplayTheme,
  parseStoredDisplayPreferences,
  readDisplayPreferences,
  writeDisplayPreferences,
} from "./display-preferences";
import type { DisplayLocale, DisplayPreferences, DisplayTheme } from "./display-preferences";
import "./display-preferences.css";

/** State-bound handle the root hands to App so any surface can drive preferences. */
export interface DisplayPreferencesControls {
  theme: DisplayTheme;
  locale: DisplayLocale;
  setTheme: (theme: DisplayTheme) => void;
  setLocale: (locale: DisplayLocale) => void;
}

export interface DisplayPreferencesRenderArgs {
  theme: DisplayTheme;
  locale: DisplayLocale;
  control: DisplayPreferencesControls;
}

export interface DisplayPreferencesRootProps {
  children: (args: DisplayPreferencesRenderArgs) => ReactNode;
}

/**
 * Reads persisted preferences lazily during the first render, so children
 * (including App) never see defaults that storage was about to contradict.
 * Storage is only written with validated data under this module's key;
 * read/write failures degrade to the in-memory choice.
 */
export function DisplayPreferencesRoot({ children }: DisplayPreferencesRootProps) {
  const [preferences, setPreferences] = useState<DisplayPreferences>(readDisplayPreferences);
  const latestRef = useRef(preferences);
  latestRef.current = preferences;

  const update = useCallback((patch: Partial<DisplayPreferences>) => {
    const current = latestRef.current;
    const theme = patch.theme !== undefined && isDisplayTheme(patch.theme) ? patch.theme : current.theme;
    const locale = patch.locale !== undefined && isDisplayLocale(patch.locale) ? patch.locale : current.locale;
    if (theme === current.theme && locale === current.locale) return;
    const next = { theme, locale };
    latestRef.current = next;
    setPreferences(next);
    writeDisplayPreferences(next);
  }, []);

  const setTheme = useCallback((theme: DisplayTheme) => update({ theme }), [update]);
  const setLocale = useCallback((locale: DisplayLocale) => update({ locale }), [update]);

  useEffect(() => {
    const onStorage = (event: StorageEvent) => {
      // Other tabs only move this exact key, and only onto validated data.
      // Removals (newValue null) and clear() carry no new data and never reset state.
      if (event.key !== DISPLAY_PREFERENCES_STORAGE_KEY || event.newValue === null) return;
      const next = parseStoredDisplayPreferences(event.newValue);
      if (!next) return;
      latestRef.current = next;
      setPreferences(next);
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  const control = useMemo<DisplayPreferencesControls>(
    () => ({ theme: preferences.theme, locale: preferences.locale, setTheme, setLocale }),
    [preferences, setTheme, setLocale],
  );

  return <>{children({ theme: preferences.theme, locale: preferences.locale, control })}</>;
}

export interface DisplayPreferencesProps {
  control: DisplayPreferencesControls;
  idPrefix?: string;
}

/** Inline disclosure; native selects own labeling and keyboard interaction. */
export function DisplayPreferences({ control, idPrefix = "display-preferences" }: DisplayPreferencesProps) {
  const [open, setOpen] = useState(false);
  const copy = DISPLAY_PREFERENCE_STRINGS[control.locale];
  const panelId = `${idPrefix}-panel`;
  const themeId = `${idPrefix}-theme`;
  const localeId = `${idPrefix}-locale`;
  return (
    <section className="display-preferences">
      <button
        type="button"
        className="display-preferences__toggle"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((value) => !value)}
      >
        {copy.disclosure}
      </button>
      <div id={panelId} role="region" aria-label={copy.region} className="display-preferences__panel" hidden={!open}>
        <div className="display-preferences__field">
          <label className="display-preferences__label" htmlFor={themeId}>{copy.theme}</label>
          <select
            id={themeId}
            className="display-preferences__select"
            value={control.theme}
            onChange={(event) => {
              const value = event.target.value;
              if (isDisplayTheme(value)) control.setTheme(value);
            }}
          >
            <option value="dark">{copy.dark}</option>
            <option value="light">{copy.light}</option>
          </select>
        </div>
        <div className="display-preferences__field">
          <label className="display-preferences__label" htmlFor={localeId}>{copy.language}</label>
          <select
            id={localeId}
            className="display-preferences__select"
            value={control.locale}
            onChange={(event) => {
              const value = event.target.value;
              if (isDisplayLocale(value)) control.setLocale(value);
            }}
          >
            <option value="en">{copy.english}</option>
            <option value="zh-CN">{copy.chinese}</option>
          </select>
        </div>
      </div>
    </section>
  );
}
