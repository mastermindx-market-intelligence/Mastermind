// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { DEFAULT_DISPLAY_PREFERENCES, DISPLAY_PREFERENCES_STORAGE_KEY } from "./display-preferences";
import type { DisplayPreferences as StoredDisplayPreferences } from "./display-preferences";
import { DisplayPreferences, DisplayPreferencesRoot } from "./DisplayPreferences";
import type { DisplayPreferencesControls } from "./DisplayPreferences";

const KEY = DISPLAY_PREFERENCES_STORAGE_KEY;
// Unrelated neighboring keys: this module must ignore both.
const AUTH_KEY = "mastermind-os.auth.session";
const SHELL_THEME_KEY = "theme";

const stored = (preferences: Partial<StoredDisplayPreferences>) =>
  JSON.stringify({ version: 1, theme: "dark", locale: "en", ...preferences });

const storageEvent = (key: string | null, newValue: string | null) => new StorageEvent("storage", { key, newValue });

interface Probe {
  seen: StoredDisplayPreferences[];
  control: DisplayPreferencesControls | null;
}

function renderRoot() {
  const probe: Probe = { seen: [], control: null };
  const view = render(
    <DisplayPreferencesRoot>
      {({ theme, locale, control }) => {
        probe.seen.push({ theme, locale });
        probe.control = control;
        return (
          <div>
            <span data-testid="theme">{theme}</span>
            <span data-testid="locale">{locale}</span>
            <DisplayPreferences control={control} />
          </div>
        );
      }}
    </DisplayPreferencesRoot>,
  );
  return { probe, ...view };
}

function openSettings() {
  fireEvent.click(screen.getByRole("button", { name: "Display settings" }));
}

const themeSelect = () => screen.getByLabelText("Theme") as HTMLSelectElement;
const localeSelect = () => screen.getByLabelText("Language") as HTMLSelectElement;

// jsdom backs localStorage with a proxy, so storage mocks must target the prototype.
beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("defaults and hydration", () => {
  it("defaults to dark/en on empty storage and writes nothing on mount", () => {
    const setItem = vi.spyOn(Storage.prototype, "setItem");
    const { probe } = renderRoot();
    expect(probe.seen[0]).toEqual(DEFAULT_DISPLAY_PREFERENCES);
    expect(screen.getByTestId("theme").textContent).toBe("dark");
    expect(screen.getByTestId("locale").textContent).toBe("en");
    expect(localStorage.getItem(KEY)).toBeNull();
    expect(setItem).not.toHaveBeenCalled();
  });

  it.each([
    ["malformed JSON", "{oops"],
    ["non-object JSON", "42"],
    ["unknown version", '{"version":2,"theme":"light","locale":"zh-CN"}'],
    ["unknown theme", '{"version":1,"theme":"navy","locale":"en"}'],
    ["unknown locale", '{"version":1,"theme":"light","locale":"zh"}'],
    ["missing version", '{"theme":"light","locale":"en"}'],
  ])("ignores %s and keeps defaults", (_name, raw) => {
    localStorage.setItem(KEY, raw);
    const { probe } = renderRoot();
    expect(probe.seen[0]).toEqual(DEFAULT_DISPLAY_PREFERENCES);
    expect(screen.getByTestId("theme").textContent).toBe("dark");
    expect(screen.getByTestId("locale").textContent).toBe("en");
  });

  it("hydrates a valid record before the first child render", () => {
    localStorage.setItem(KEY, stored({ theme: "light", locale: "zh-CN" }));
    const { probe } = renderRoot();
    expect(probe.seen[0]).toEqual({ theme: "light", locale: "zh-CN" });
    expect(screen.getByTestId("theme").textContent).toBe("light");
    expect(screen.getByTestId("locale").textContent).toBe("zh-CN");
    expect(probe.seen).toHaveLength(1);
  });
});

describe("user changes", () => {
  it("theme changes update children and persist only this key with version 1", () => {
    localStorage.setItem(AUTH_KEY, "ticket-1");
    localStorage.setItem(SHELL_THEME_KEY, "light");
    const setItem = vi.spyOn(Storage.prototype, "setItem");
    renderRoot();
    openSettings();
    fireEvent.change(themeSelect(), { target: { value: "light" } });
    expect(screen.getByTestId("theme").textContent).toBe("light");
    expect(localStorage.getItem(KEY)).toBe('{"version":1,"theme":"light","locale":"en"}');
    expect(setItem.mock.calls.every((call: string[]) => call[0] === KEY)).toBe(true);
    expect(localStorage.getItem(AUTH_KEY)).toBe("ticket-1");
    expect(localStorage.getItem(SHELL_THEME_KEY)).toBe("light");
  });

  it("language changes retranslate labels and options and persist", () => {
    renderRoot();
    openSettings();
    const language = localeSelect();
    const theme = themeSelect();
    fireEvent.change(language, { target: { value: "zh-CN" } });
    expect(screen.getByTestId("locale").textContent).toBe("zh-CN");
    expect(screen.getByLabelText("主题")).toBe(theme);
    expect(screen.getByLabelText("语言")).toBe(language);
    expect(Array.from(theme.options, (option) => option.textContent)).toEqual(["深色", "浅色"]);
    expect(Array.from(language.options, (option) => option.textContent)).toEqual(["英语", "中文（简体）"]);
    expect(localStorage.getItem(KEY)).toBe('{"version":1,"theme":"dark","locale":"zh-CN"}');
  });

  it("control methods drive the same state and persistence", () => {
    const { probe } = renderRoot();
    act(() => probe.control!.setTheme("light"));
    act(() => probe.control!.setLocale("zh-CN"));
    expect(screen.getByTestId("theme").textContent).toBe("light");
    expect(screen.getByTestId("locale").textContent).toBe("zh-CN");
    expect(localStorage.getItem(KEY)).toBe('{"version":1,"theme":"light","locale":"zh-CN"}');
  });
});

describe("storage failures", () => {
  it("a throwing read falls back to defaults", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("storage blocked");
    });
    const { probe } = renderRoot();
    expect(probe.seen[0]).toEqual(DEFAULT_DISPLAY_PREFERENCES);
    expect(screen.getByTestId("theme").textContent).toBe("dark");
    expect(screen.getByTestId("locale").textContent).toBe("en");
  });

  it("a throwing write keeps the in-memory choice and recovers later", () => {
    const setItem = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("quota exceeded");
    });
    const { probe } = renderRoot();
    openSettings();
    fireEvent.change(themeSelect(), { target: { value: "light" } });
    expect(screen.getByTestId("theme").textContent).toBe("light");
    expect(setItem).toHaveBeenCalledTimes(1);
    expect(localStorage.getItem(KEY)).toBeNull();
    setItem.mockRestore();
    fireEvent.change(localeSelect(), { target: { value: "zh-CN" } });
    expect(screen.getByTestId("locale").textContent).toBe("zh-CN");
    expect(probe.control?.theme).toBe("light");
    expect(localStorage.getItem(KEY)).toBe('{"version":1,"theme":"light","locale":"zh-CN"}');
  });
});

describe("cross-tab storage events", () => {
  it("applies a valid update from another tab", () => {
    const { probe } = renderRoot();
    act(() => {
      window.dispatchEvent(storageEvent(KEY, stored({ theme: "light", locale: "zh-CN" })));
    });
    expect(screen.getByTestId("theme").textContent).toBe("light");
    expect(screen.getByTestId("locale").textContent).toBe("zh-CN");
    expect(probe.seen.at(-1)).toEqual({ theme: "light", locale: "zh-CN" });
  });

  it("ignores unrelated keys, malformed payloads, and removals", () => {
    localStorage.setItem(KEY, stored({ theme: "light", locale: "zh-CN" }));
    const { probe } = renderRoot();
    const setItem = vi.spyOn(Storage.prototype, "setItem");
    act(() => {
      window.dispatchEvent(storageEvent(SHELL_THEME_KEY, "dark"));
      window.dispatchEvent(storageEvent(AUTH_KEY, "ticket-2"));
      window.dispatchEvent(storageEvent(KEY, "{oops"));
      window.dispatchEvent(storageEvent(KEY, '{"version":1,"theme":"navy","locale":"en"}'));
      window.dispatchEvent(storageEvent(KEY, null));
      window.dispatchEvent(storageEvent(null, null));
    });
    expect(screen.getByTestId("theme").textContent).toBe("light");
    expect(screen.getByTestId("locale").textContent).toBe("zh-CN");
    expect(probe.seen).toHaveLength(1);
    expect(setItem).not.toHaveBeenCalled();
    expect(localStorage.getItem(KEY)).toBe(stored({ theme: "light", locale: "zh-CN" }));
  });

  it("ignores storage events after unmount without crashing", () => {
    const { probe, unmount } = renderRoot();
    unmount();
    expect(() =>
      act(() => {
        window.dispatchEvent(storageEvent(KEY, stored({ theme: "light", locale: "zh-CN" })));
      }),
    ).not.toThrow();
    expect(probe.seen).toHaveLength(1);
  });
});

describe("accessible disclosure and native selects", () => {
  it("exposes a disclosure button with labeled native selects", () => {
    renderRoot();
    const toggle = screen.getByRole("button", { name: "Display settings" }) as HTMLButtonElement;
    expect(toggle.tagName).toBe("BUTTON");
    expect(toggle.type).toBe("button");
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    expect(screen.queryByRole("region", { name: "Display preferences" })).toBeNull();
    openSettings();
    expect(toggle.getAttribute("aria-expanded")).toBe("true");
    const panel = screen.getByRole("region", { name: "Display preferences" });
    expect(toggle.getAttribute("aria-controls")).toBe(panel.id);
    expect(panel.getAttribute("hidden")).toBeNull();
    const theme = themeSelect();
    const locale = localeSelect();
    expect(theme.tagName).toBe("SELECT");
    expect(locale.tagName).toBe("SELECT");
    expect(Array.from(theme.options, (option) => option.value)).toEqual(["dark", "light"]);
    expect(Array.from(locale.options, (option) => option.value)).toEqual(["en", "zh-CN"]);
    theme.focus();
    expect(document.activeElement).toBe(theme);
    locale.focus();
    expect(document.activeElement).toBe(locale);
  });
});
