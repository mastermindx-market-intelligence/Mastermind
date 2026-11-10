// @vitest-environment jsdom
import React from "react";
import { readFileSync } from "node:fs";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  CodeSettingsPanel,
  type EnvironmentSummary,
  type ProviderConnection,
} from "./CodeSettingsPanel";

afterEach(cleanup);

/** Read the stylesheet from disk — the vitest CSS pipeline in this app only
 *  processes styles.css?raw, so a ?raw import of code-settings.css is empty.
 *  Vitest runs with cwd at the app root. */
const codeSettingsCss = readFileSync("src/code/code-settings.css", "utf8");

/** Fixtures only — the Paper samples ("DeepSeek Harness", "Ubuntu 2"…) are
 *  forbidden in shipped copy; they never appear in the component. */
const providers: ProviderConnection[] = [
  {
    id: "glm-fabric",
    name: "GLM Fabric",
    ready: true,
    executable: "/opt/fabric/bin/agent",
    args: "--stdio",
    defaultModel: "glm-5.3",
    connectionAuth: "held",
    capabilities: [
      { label: "Runs / streaming", state: "available", note: null },
      {
        label: "Models and session options",
        state: "discovered",
        note: null,
      },
      {
        label: "Native subagent dialogues",
        state: "not-provided",
        note: null,
      },
    ],
  },
];

const environments: EnvironmentSummary[] = [
  { id: "m2studio", label: "M2 Studio" },
  { id: "hermes-shell", label: "Hermes Shell" },
];

const SAMPLES = [
  "Engineering check-in",
  "Ubuntu 2",
  "DeepSeek Harness",
  "20:30",
  "America / Vancouver",
];

describe("CodeSettingsPanel (HC11)", () => {
  it("renders the Providers surface from projected data", () => {
    render(
      <CodeSettingsPanel
        providers={providers}
        environments={environments}
        activeEnvironmentId="m2studio"
      />,
    );
    expect(screen.getByText("Code settings / Providers")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Providers" })).toBeTruthy();
    expect(
      screen.getByText("Configure coding agents for this environment."),
    ).toBeTruthy();
    expect(
      screen.getByRole("button", { name: "＋ Add provider" }),
    ).toBeTruthy();
    // Environment select fed by the environments prop.
    const select = screen.getByLabelText(
      "Showing configuration for",
    ) as HTMLSelectElement;
    expect(select.value).toBe("m2studio");
    expect(
      Array.from(select.querySelectorAll("option")).map(
        (option) => option.textContent,
      ),
    ).toEqual(["M2 Studio", "Hermes Shell"]);
    expect(
      screen.getByText("Existing threads stay on their original environment."),
    ).toBeTruthy();
    // Provider card.
    expect(screen.getByText("GLM Fabric")).toBeTruthy();
    expect(screen.getByText("Ready")).toBeTruthy();
    expect(screen.getByText("/opt/fabric/bin/agent")).toBeTruthy();
    expect(screen.getByText("--stdio")).toBeTruthy();
    expect(screen.getByText("glm-5.3")).toBeTruthy();
    expect(screen.getByText("Held by the connection")).toBeTruthy();
    expect(
      screen.getByText("Credentials stay on the execution environment."),
    ).toBeTruthy();
    // Capabilities from this connection.
    expect(
      screen.getByText("Capabilities from this connection"),
    ).toBeTruthy();
    expect(screen.getByText("Available")).toBeTruthy();
    expect(screen.getByText("Discovered from agent")).toBeTruthy();
    expect(screen.getByText("Not provided by ACP")).toBeTruthy();
    expect(screen.getByText(/Linked tasks stay with their conversation/i)).toBeTruthy();
    expect(
      screen.getByRole("button", { name: "More providers →" }),
    ).toBeTruthy();
  });

  it("renders the full four-group settings nav with Providers current", () => {
    render(
      <CodeSettingsPanel
        providers={providers}
        environments={environments}
        activeEnvironmentId="m2studio"
      />,
    );
    for (const item of [
      "General",
      "Appearance",
      "Chat",
      "Keyboard shortcuts",
      "Providers",
      "Threads",
      "Browser",
      "Devices",
      "Scheduled tasks",
      "Projects",
      "Diffs & pull requests",
      "Source control",
      "Worktrees",
      "Environments",
      "Sharing & access",
    ]) {
      expect(screen.getByRole("button", { name: item })).toBeTruthy();
    }
    for (const group of ["INTERFACE", "AGENTS", "CODE", "CONNECTIONS"]) {
      expect(screen.getByText(group)).toBeTruthy();
    }
    expect(
      screen
        .getByRole("button", { name: "Providers" })
        .getAttribute("aria-current"),
    ).toBe("page");
    expect(
      screen
        .getByRole("button", { name: "Appearance" })
        .getAttribute("aria-current"),
    ).toBeNull();
  });

  it("renders null providers as an honest unavailable state", () => {
    render(
      <CodeSettingsPanel
        providers={null}
        environments={environments}
        activeEnvironmentId="m2studio"
      />,
    );
    expect(
      screen.getByText("No provider configuration source is projected in this build"),
    ).toBeTruthy();
    expect(
      screen.getByText(/none is connected here, so nothing is shown or inferred/i),
    ).toBeTruthy();
    expect(screen.queryByText("GLM Fabric")).toBeNull();
    expect(screen.queryByRole("button", { name: "More providers →" })).toBeNull();
  });

  it("renders an empty provider list as a real empty, distinct from unavailable", () => {
    render(
      <CodeSettingsPanel
        providers={[]}
        environments={environments}
        activeEnvironmentId="m2studio"
      />,
    );
    expect(
      screen.getByText("No providers are configured for this environment."),
    ).toBeTruthy();
    expect(
      screen.queryByText(/No provider configuration source is projected/i),
    ).toBeNull();
  });

  it("renders null environments honestly, without a select", () => {
    render(
      <CodeSettingsPanel
        providers={providers}
        environments={null}
        activeEnvironmentId="m2studio"
      />,
    );
    expect(
      screen.getByText(/no environment list is projected in this build/i),
    ).toBeTruthy();
    expect(screen.queryByRole("combobox")).toBeNull();
  });

  it("renders honest not-configured placeholders for every other tab", () => {
    render(
      <CodeSettingsPanel
        providers={providers}
        environments={environments}
        activeEnvironmentId="m2studio"
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Appearance" }));
    expect(
      screen.getByText(/Appearance is not configured in this build/i),
    ).toBeTruthy();
    expect(screen.getByText("Code settings / Appearance")).toBeTruthy();
    expect(
      screen
        .getByRole("button", { name: "Appearance" })
        .getAttribute("aria-current"),
    ).toBe("page");
    expect(
      screen
        .getByRole("button", { name: "Providers" })
        .getAttribute("aria-current"),
    ).toBeNull();
    // The provider surface is gone while the placeholder is shown.
    expect(screen.queryByText("GLM Fabric")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Sharing & access" }));
    expect(
      screen.getByText(/Sharing & access is not configured in this build/i),
    ).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Providers" }));
    expect(screen.getByText("GLM Fabric")).toBeTruthy();
  });

  it("Add provider reports the missing write path instead of faking success", () => {
    render(
      <CodeSettingsPanel
        providers={providers}
        environments={environments}
        activeEnvironmentId="m2studio"
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "＋ Add provider" }));
    expect(
      screen.getByText(/not wired in this build\. No provider write path/i),
    ).toBeTruthy();
    expect(screen.getByText(/nothing was added or saved/i)).toBeTruthy();
    // No fake success and no mutated list.
    expect(screen.queryByText(/provider added/i)).toBeNull();
    expect(screen.getAllByText("GLM Fabric").length).toBe(1);
  });

  it("stays honest when switching to an environment whose configuration is not loaded", () => {
    render(
      <CodeSettingsPanel
        providers={providers}
        environments={environments}
        activeEnvironmentId="m2studio"
      />,
    );
    const select = screen.getByLabelText(
      "Showing configuration for",
    ) as HTMLSelectElement;
    fireEvent.change(select, { target: { value: "hermes-shell" } });
    expect(
      screen.getByText(
        "Provider configuration for Hermes Shell is not projected in this build. Only the active environment's configuration is loaded here.",
      ),
    ).toBeTruthy();
    // The active environment's card never renders under another label.
    expect(screen.queryByText("GLM Fabric")).toBeNull();
    fireEvent.change(select, { target: { value: "m2studio" } });
    expect(screen.getByText("GLM Fabric")).toBeTruthy();
  });

  it("renders unknown provider fields as unknown-with-reason, never invented", () => {
    render(
      <CodeSettingsPanel
        providers={[
          {
            id: "bare",
            name: "Bare Connection",
            ready: null,
            executable: null,
            args: null,
            defaultModel: null,
            connectionAuth: "unknown",
            capabilities: [{ label: "Runs / streaming", state: "unknown", note: null }],
          },
        ]}
        environments={environments}
        activeEnvironmentId="m2studio"
      />,
    );
    expect(screen.getAllByText("Unknown — not provided by the connection").length).toBe(3);
    expect(document.querySelector('.mm-cs-ready[data-ready="unknown"]')?.textContent).toBe(
      "Unknown",
    );
    expect(document.querySelector('.mm-cs-auth[data-auth="unknown"]')?.textContent).toBe(
      "Unknown",
    );
    expect(document.querySelector('.mm-cs-capability[data-state="unknown"]')?.textContent).toBe(
      "Unknown",
    );
  });

  it("More providers and close degrade to disabled-with-reason when unwired", () => {
    const onMoreProviders = vi.fn();
    const onClose = vi.fn();
    const { unmount } = render(
      <CodeSettingsPanel
        providers={providers}
        environments={environments}
        activeEnvironmentId="m2studio"
        onMoreProviders={onMoreProviders}
        onClose={onClose}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "More providers →" }));
    expect(onMoreProviders).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "Close settings" }));
    expect(onClose).toHaveBeenCalledTimes(1);
    unmount();
    render(
      <CodeSettingsPanel
        providers={providers}
        environments={environments}
        activeEnvironmentId="m2studio"
      />,
    );
    const more = screen.getByRole("button", { name: "More providers →" });
    expect(more.hasAttribute("disabled")).toBe(true);
    expect(
      screen.getByText(/provider catalog is not wired in this build/i),
    ).toBeTruthy();
    const close = screen.getByRole("button", { name: "Close settings" });
    expect(close.hasAttribute("disabled")).toBe(true);
    expect(screen.getByText(/no close path is wired/i)).toBeTruthy();
  });

  it("closes on Escape through the provided onClose", () => {
    const onClose = vi.fn();
    render(
      <CodeSettingsPanel
        providers={providers}
        environments={environments}
        activeEnvironmentId="m2studio"
        onClose={onClose}
      />,
    );
    fireEvent.keyDown(document.body, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("keeps focus reachable and visible on interactive controls", () => {
    render(
      <CodeSettingsPanel
        providers={providers}
        environments={environments}
        activeEnvironmentId="m2studio"
        onClose={() => {}}
      />,
    );
    const nav = screen.getByRole("button", { name: "Appearance" });
    nav.focus();
    expect(document.activeElement).toBe(nav);
    const close = screen.getByRole("button", { name: "Close settings" });
    close.focus();
    expect(document.activeElement).toBe(close);
    expect(codeSettingsCss).toContain(".mm-cs :is(button, select):focus-visible");
    expect(codeSettingsCss).toContain("outline: 2px solid var(--noir-champagne)");
  });

  it("renders the zh-CN copy", () => {
    const { unmount } = render(
      <CodeSettingsPanel
        providers={providers}
        environments={environments}
        activeEnvironmentId="m2studio"
        locale="zh-CN"
      />,
    );
    expect(screen.getByText("代码设置 / 提供商")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "提供商" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "＋ 添加提供商" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "键盘快捷键" })).toBeTruthy();
    expect(screen.getByText("界面")).toBeTruthy();
    expect(
      screen.getByRole("button", { name: "关闭设置" }),
    ).toBeTruthy();
    expect(
      screen.getByText("凭据保存在执行环境中。"),
    ).toBeTruthy();
    unmount();
    render(
      <CodeSettingsPanel
        providers={null}
        environments={null}
        activeEnvironmentId={null}
        locale="zh-CN"
      />,
    );
    expect(screen.getByText("此版本未投影提供商配置来源")).toBeTruthy();
    expect(screen.getByText(/不显示也不推断任何内容/)).toBeTruthy();
    expect(screen.getByText(/此版本未投影环境列表/)).toBeTruthy();
  });

  it("ships no Paper sample data in any rendered state", () => {
    const full = render(
      <CodeSettingsPanel
        providers={providers}
        environments={environments}
        activeEnvironmentId="m2studio"
      />,
    );
    for (const sample of SAMPLES) {
      expect(full.container.textContent).not.toContain(sample);
    }
    full.unmount();
    const empty = render(
      <CodeSettingsPanel
        providers={null}
        environments={null}
        activeEnvironmentId={null}
      />,
    );
    for (const sample of SAMPLES) {
      expect(empty.container.textContent).not.toContain(sample);
    }
    expect(empty.container.textContent).not.toContain("GLM Fabric");
  });
});
