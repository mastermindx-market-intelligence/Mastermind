// @vitest-environment jsdom
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";

beforeEach(() => {
  history.replaceState(null, "", "/os/");
  delete window.MastermindMissionHost;
  delete (window as unknown as { __TAURI_INTERNALS__?: unknown }).__TAURI_INTERNALS__;
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe("readable workspace shell", () => {
  it("retains the separate Meta-CEO office and all incumbent deep routes", () => {
    render(<App />);
    const navigation = screen.getByRole("navigation", { name: "Mission navigation" });
    for (const name of ["Meta-CEO", "Work queue", "Programs workspace", "Control Room workspace", "Fleet & Capacity workspace", "Mission Workspace", "Conversation", "Activity", "Connections", "Evidence"])
      expect(within(navigation).getByRole("button", { name })).toBeTruthy();
    expect(screen.getAllByRole("main")).toHaveLength(1);
  });
  it("opens the full navigation drawer and returns focus on Escape", async () => {
    const user = userEvent.setup();
    render(<App />);
    const button = screen.getByRole("button", { name: "Open navigation" });
    await user.click(button);
    expect(button.getAttribute("aria-expanded")).toBe("true");
    expect(document.getElementById("workspace-navigation")?.getAttribute("data-open")).toBe("true");
    await user.keyboard("{Escape}");
    expect(button.getAttribute("aria-expanded")).toBe("false");
    expect(document.activeElement).toBe(button);
  });
  it("returns focus to the menu after choosing a route in the mobile drawer", async () => {
    const user = userEvent.setup();
    render(<App/>);
    const menu = screen.getByRole("button", {name:"Open navigation"});
    await user.click(menu);
    const company = screen.getByRole("navigation", {name:"Company navigation"});
    await user.click(within(company).getByRole("button", {name:"Knowledge"}));
    expect(menu.getAttribute("aria-expanded")).toBe("false");
    expect(document.activeElement).toBe(menu);
  });
  it("cycles focus through visible drawer controls without entering closed Settings", async () => {
    vi.spyOn(HTMLElement.prototype, "getClientRects").mockImplementation(function (this: HTMLElement) {
      const closed = this.closest("details:not([open])");
      return (closed && this.tagName !== "SUMMARY" ? [] : [new DOMRect(0, 0, 44, 44)]) as unknown as DOMRectList;
    });
    const user = userEvent.setup();
    render(<App preferencesControl={<details><summary>Settings</summary><label>Theme<select><option>Dark</option></select></label></details>} />);
    await user.click(screen.getByRole("button", { name: "Open navigation" }));
    const pane = document.getElementById("workspace-navigation")!;
    const summary = within(pane).getByText("Settings");
    summary.focus();
    await user.keyboard("{Tab}");
    expect(document.activeElement).toBe(within(pane).getByRole("button", { name: "Close navigation" }));
    await user.keyboard("{Shift>}{Tab}{/Shift}");
    expect(document.activeElement).toBe(summary);
  });
  it("uses translated primary labels and supplied display controls without changing route IDs", () => {
    render(<App locale="zh-CN" theme="light" preferencesControl={<button>设置</button>} />);
    const company = screen.getByRole("navigation", { name: "Company navigation" });
    for (const name of ["今天", "项目", "收件箱", "对话", "知识"])
      expect(within(company).getByRole("button", { name })).toBeTruthy();
    expect(document.querySelector(".shell")?.getAttribute("data-active-route")).toBe("Today");
    expect(document.querySelector(".shell")?.getAttribute("data-theme")).toBe("light");
    expect(screen.getByRole("button", { name: "设置" })).toBeTruthy();
  });
});
