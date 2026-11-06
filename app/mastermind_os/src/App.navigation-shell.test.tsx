// @vitest-environment jsdom
import { act, cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";
import type { MissionHost } from "./host";

beforeEach(() => {
  history.replaceState(null, "", "/os/");
  delete window.MastermindMissionHost;
  delete (window as unknown as { __TAURI_INTERNALS__?: unknown }).__TAURI_INTERNALS__;
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

const advancedDisclosure = () => {
  const details = document.querySelector<HTMLDetailsElement>("details.nav-advanced");
  if (!details) throw new Error("Advanced disclosure is missing");
  const summary = details.querySelector("summary");
  if (!summary) throw new Error("Advanced summary is missing");
  return { details, summary };
};

const activeRoute = () => document.querySelector(".shell")?.getAttribute("data-active-route");

describe("readable workspace shell", () => {
  it("retains the separate Meta-CEO office and all incumbent deep routes", async () => {
    const user = userEvent.setup();
    render(<App />);
    const { details, summary } = advancedDisclosure();
    expect(details.open).toBe(false);
    // The incumbent deep routes live inside the disclosure; open it before
    // querying routes that are hidden while it is closed.
    await user.click(summary);
    expect(details.open).toBe(true);
    const navigation = screen.getByRole("navigation", { name: "Mission navigation" });
    for (const name of ["Meta-CEO", "Work queue", "Programs workspace", "Control Room workspace", "Fleet & Capacity workspace", "Mission Workspace", "Conversation", "Activity", "Connections", "Evidence"])
      expect(within(navigation).getByRole("button", { name })).toBeTruthy();
    expect(screen.getAllByRole("main")).toHaveLength(1);
  });
  it("keeps Search and the five primary destinations outside the closed-by-default Advanced disclosure", () => {
    render(<App />);
    const { details } = advancedDisclosure();
    expect(details.open).toBe(false);
    const pane = document.getElementById("workspace-navigation")!;
    const company = within(pane as HTMLElement).getByRole("navigation", { name: "Company navigation" });
    for (const name of ["Today", "Projects", "Inbox", "Conversations", "Knowledge"])
      expect(within(company).getByRole("button", { name })).toBeTruthy();
    const search = within(pane as HTMLElement).getByRole("button", { name: "Search" });
    expect(search.getAttribute("aria-current")).toBeNull();
    const create = within(pane as HTMLElement).getByRole("button", { name: "New conversation" });
    expect(create.closest('.nav-top')).toBe(pane.querySelector('.nav-top'));
    expect(create.parentElement?.previousElementSibling).toBe(pane.querySelector('.brand'));
    expect(create.parentElement?.nextElementSibling).toBe(search);
    // A sidebar affordance never manufactures an Executive owner/port.
    expect(create.hasAttribute('disabled')).toBe(true);
    // The incumbent advanced nav is wrapped by the disclosure, not duplicated.
    expect(details.querySelector("nav")?.getAttribute("aria-label")).toBe("Mission navigation");
    expect(details.contains(search)).toBe(false);
    expect(pane.querySelectorAll("details").length).toBe(1);
  });
  it.each([['en', 'This connection can’t start a new conversation.'], ['zh-CN', '当前连接无法新建对话。']] as const)("explains a disabled global New conversation in %s", (locale, reason) => {
    render(<App locale={locale}/>);
    const create = within(document.getElementById("workspace-navigation")!).getByRole("button", {name: locale === 'en' ? 'New conversation' : '新建对话'});
    expect(create).toHaveProperty('disabled', true);
    const description = create.getAttribute('aria-describedby');
    expect(description).toBeTruthy();
    expect(document.getElementById(description!)?.textContent).toBe(reason);
  });
  it("reaches every legacy advanced route through the disclosure and keeps it open while active", async () => {
    const user = userEvent.setup();
    render(<App />);
    const { details, summary } = advancedDisclosure();
    await user.click(summary);
    const navigation = screen.getByRole("navigation", { name: "Mission navigation" });
    const routes: readonly (readonly [string, string])[] = [
      ["Sources", "Sources"],
      ["Tools", "Tools"],
      ["Meta-CEO", "Meta-CEO"],
      ["Work queue", "Work"],
      ["Programs workspace", "Programs"],
      ["Control Room workspace", "Control Room"],
      ["Session Estate", "Session Estate"],
      ["Fleet & Capacity workspace", "Fleet & Capacity"],
      ["Mission Workspace", "Mission Workspace"],
      ["Conversation", "Conversation"],
      ["Activity", "Activity"],
      ["Connections", "Connections"],
      ["Evidence", "Evidence"],
    ];
    for (const [name, route] of routes) {
      const button = within(navigation).getByRole("button", { name });
      await user.click(button);
      expect(activeRoute()).toBe(route);
      // The active advanced child never loses its own disclosure state.
      expect(details.open).toBe(true);
      expect(button.getAttribute("aria-current")).toBe("page");
    }
  });
  it("auto-opens the disclosure when the active route becomes an advanced child without navigating", async () => {
    const user = userEvent.setup();
    render(<App />);
    const { details, summary } = advancedDisclosure();
    await user.click(summary);
    const navigation = screen.getByRole("navigation", { name: "Mission navigation" });
    const metaCeo = within(navigation).getByRole("button", { name: "Meta-CEO" });
    await user.click(metaCeo);
    expect(activeRoute()).toBe("Meta-CEO");
    expect(details.open).toBe(true);
    // A manual close stays closed while the advanced route stays active.
    await user.click(summary);
    expect(details.open).toBe(false);
    const company = screen.getByRole("navigation", { name: "Company navigation" });
    await user.click(within(company).getByRole("button", { name: "Today" }));
    expect(details.open).toBe(false);
    // Returning to an advanced route re-opens it; no navigation was implied.
    await user.click(metaCeo);
    expect(activeRoute()).toBe("Meta-CEO");
    expect(details.open).toBe(true);
  });
  it("renders no empty no-work context and no fabricated selection card", () => {
    render(<App />);
    expect(document.querySelector(".mission-context-empty")).toBeNull();
    expect(document.querySelector(".mission-context")).toBeNull();
    expect(screen.queryByText("No work selected")).toBeNull();
    expect(screen.queryByText("尚未选择工作项")).toBeNull();
  });
  it("mounts preferences and the incumbent authenticated account control at the drawer bottom", async () => {
    const user = userEvent.setup();
    const signOut = vi.fn(async () => {});
    window.MastermindMissionHost = {
      auth: {
        getState: () => ({ status: "signed_in", reason: null, acquisition: true, content: true }),
        subscribe: () => () => undefined,
        signIn: vi.fn(async () => {}), signOut,
      },
    } as unknown as MissionHost;
    render(<App preferencesControl={<button>Theme</button>} />);
    const pane = document.getElementById("workspace-navigation")!;
    const bottom = pane.querySelector<HTMLElement>(".nav-bottom")!;
    expect(pane.lastElementChild).toBe(bottom);
    expect(within(bottom).getByRole("button", {name: "Theme"})).toBeTruthy();
    expect(within(bottom).getByText("Signed in")).toBeTruthy();
    expect(screen.getAllByRole("button", {name: "Sign out"})).toHaveLength(1);
    const header = document.querySelector<HTMLElement>(".workspace-header")!;
    expect(within(header).queryByRole("button", {name: "Sign out"})).toBeNull();
    await user.click(within(bottom).getByRole("button", {name: "Sign out"}));
    expect(signOut).toHaveBeenCalledTimes(1);
  });
  it("reopens a manually closed disclosure when a different advanced route becomes active", async () => {
    const user = userEvent.setup();
    render(<App />);
    const {details, summary}=advancedDisclosure();
    await user.click(summary);
    const nav=screen.getByRole("navigation", {name: "Mission navigation"});
    await user.click(within(nav).getByRole("button",{name:"Meta-CEO"}));
    const evidence=within(nav).getByRole("button",{name:"Evidence"});
    await user.click(summary);
    expect(details.open).toBe(false);
    // Exercise the incumbent route callback while the disclosure is closed,
    // as an explicit recovery transition does, without synthesizing a new route.
    act(()=>evidence.click());
    expect(activeRoute()).toBe("Evidence");
    expect(details.open).toBe(true);
  });
  it("cleans the drawer when signing out through its account control before reauthentication", async () => {
    const user=userEvent.setup();
    let state={status:"signed_in",reason:null,acquisition:true,content:true} as import("./host").AuthState;
    const listeners=new Set<(s:import("./host").AuthState)=>void>();
    const update=(next:import("./host").AuthState)=>{state=next;for(const listener of listeners)listener(next);};
    window.MastermindMissionHost={auth:{getState:()=>state,subscribe:listener=>{listeners.add(listener);return()=>{listeners.delete(listener);};},
      signOut:async()=>update({status:"signed_out",reason:null,acquisition:false,content:false}),
      signIn:async()=>update({status:"signed_in",reason:null,acquisition:true,content:true})}};
    vi.stubGlobal("matchMedia",vi.fn(()=>({matches:true,addEventListener:vi.fn(),removeEventListener:vi.fn()})));
    render(<App/>);
    await user.click(screen.getByRole("button",{name:"Open navigation"}));
    expect(screen.getByRole("button",{name:"Open navigation"}).getAttribute("aria-expanded")).toBe("true");
    await user.click(screen.getByRole("button",{name:"Sign out"}));
    expect(screen.getByRole("heading",{name:"Welcome back."})).toBeTruthy();
    await user.click(screen.getByRole("button",{name:"Sign in"}));
    expect(screen.getByRole("button",{name:"Open navigation"}).getAttribute("aria-expanded")).toBe("false");
  });
  it("opens the full navigation drawer and returns focus on Escape", async () => {
    const user = userEvent.setup();
    render(<App />);
    const button = screen.getByRole("button", { name: "Open navigation" });
    await user.click(button);
    expect(button.getAttribute("aria-expanded")).toBe("true");
    expect(document.getElementById("workspace-navigation")?.getAttribute("data-open")).toBe("true");
    const { details, summary } = advancedDisclosure();
    await user.click(summary);
    expect(details.open).toBe(true);
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
  it("releases the mobile focus trap on a desktop resize without focusing the hidden toggle", async () => {
    let mobile = true;
    const listeners = new Set<() => void>();
    vi.stubGlobal("matchMedia", () => ({ get matches() { return mobile; },
      addEventListener: (_type: string, listener: () => void) => listeners.add(listener),
      removeEventListener: (_type: string, listener: () => void) => listeners.delete(listener),
    }));
    const user = userEvent.setup();
    render(<App/>);
    const menu = screen.getByRole("button", {name:"Open navigation"});
    await user.click(menu);
    expect(menu.getAttribute("aria-expanded")).toBe("true");
    act(() => { mobile = false; for (const listener of listeners) listener(); });
    expect(menu.getAttribute("aria-expanded")).toBe("false");
    expect(document.activeElement).toBe(screen.getByRole("main"));
    const event = new KeyboardEvent("keydown", {key:"Tab",bubbles:true,cancelable:true});
    document.dispatchEvent(event);
    expect(event.defaultPrevented).toBe(false);
    expect(listeners.size).toBe(0);
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
    const company = screen.getByRole("navigation", { name: "公司导航" });
    for (const name of ["今天", "项目", "收件箱", "对话", "知识"])
      expect(within(company).getByRole("button", { name })).toBeTruthy();
    expect(document.querySelector(".shell")?.getAttribute("data-active-route")).toBe("Today");
    expect(document.querySelector(".shell")?.getAttribute("data-theme")).toBe("light");
    expect(screen.getByRole("button", { name: "设置" })).toBeTruthy();
  });
});
