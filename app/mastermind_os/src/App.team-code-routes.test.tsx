// @vitest-environment jsdom
import React from "react";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { App } from "./App";

beforeEach(() => {
  history.replaceState(null, "", "/os/");
  delete window.MastermindMissionHost;
  delete (window as unknown as { __TAURI_INTERNALS__?: unknown })
    .__TAURI_INTERNALS__;
});
afterEach(cleanup);

const companyNav = (locale: "en" | "zh-CN" = "en") => {
  const pane = document.getElementById("workspace-navigation")!;
  return within(pane as HTMLElement).getByRole("navigation", {
    name: locale === "zh-CN" ? "公司导航" : "Company navigation",
  });
};
const activeRoute = () =>
  document.querySelector(".shell")?.getAttribute("data-active-route");

describe("Team and Code company routes", () => {
  it("registers Team and Code beside the incumbent Company destinations", () => {
    render(<App />);
    const company = companyNav();
    for (const name of [
      "Today",
      "Team",
      "Projects",
      "Code",
      "Inbox",
      "Conversations",
      "Knowledge",
    ])
      expect(within(company).getByRole("button", { name })).toBeTruthy();
  });

  it("shows the honest unverified roster while no team source is connected (TS01)", () => {
    render(<App />);
    fireEvent.click(within(companyNav()).getByRole("button", { name: "Team" }));
    expect(activeRoute()).toBe("Team");
    expect(screen.getByRole("heading", { name: "Team roster" })).toBeTruthy();
    expect(screen.getByText("Team needs a connection")).toBeTruthy();
    expect(screen.getByText("Roster not verified")).toBeTruthy();
    expect(screen.getByText("Current team size")).toBeTruthy();
    expect(screen.getByText("Not verified")).toBeTruthy();
    expect(screen.getByText("Presence")).toBeTruthy();
    expect(screen.getByText("Not observed")).toBeTruthy();
    expect(
      screen.getByText(
        /An unavailable source is never shown as an empty company/i,
      ),
    ).toBeTruthy();
    expect(screen.queryByRole("table")).toBeNull();
    // The escape hatch reuses the existing Conversations surface, not a new transport.
    fireEvent.click(
      screen.getByRole("button", { name: "Open recent conversations" }),
    );
    expect(activeRoute()).toBe("Conversations");
  });

  it("shows the honest not-projected T3 threads while no projection source is connected (TD04)", () => {
    render(<App />);
    fireEvent.click(within(companyNav()).getByRole("button", { name: "Code" }));
    expect(activeRoute()).toBe("Code");
    expect(screen.getByRole("heading", { name: "T3 Code" })).toBeTruthy();
    expect(screen.getByText("Code threads are not projected yet")).toBeTruthy();
    expect(
      screen.getByText(/no thread state is shown or inferred/i),
    ).toBeTruthy();
    expect(screen.getByText("T3_PROJECTION_SOURCE_NOT_CONNECTED")).toBeTruthy();
    expect(screen.getByText(/No provider keys live in this app/i)).toBeTruthy();
    expect(
      screen.queryByRole("link", { name: "Open in T3 Code ↗" }),
    ).toBeNull();
  });

  it("keeps the zh-CN route labels and honest states", () => {
    render(<App locale="zh-CN" />);
    const company = companyNav("zh-CN");
    fireEvent.click(within(company).getByRole("button", { name: "团队" }));
    expect(activeRoute()).toBe("Team");
    expect(screen.getByRole("heading", { name: "团队名册" })).toBeTruthy();
    expect(screen.getByText("团队需要连接")).toBeTruthy();
    expect(screen.getByText("名册未验证")).toBeTruthy();
    expect(screen.getByText(/来源不可用时，绝不显示为空公司。/)).toBeTruthy();
    fireEvent.click(within(company).getByRole("button", { name: "代码" }));
    expect(activeRoute()).toBe("Code");
    expect(screen.getByText("编码线程尚未投影")).toBeTruthy();
    expect(screen.getByText("T3_PROJECTION_SOURCE_NOT_CONNECTED")).toBeTruthy();
    expect(screen.getByText(/此应用不保存任何提供商密钥/i)).toBeTruthy();
  });
});
