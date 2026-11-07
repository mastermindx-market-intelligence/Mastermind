// @vitest-environment jsdom
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ByokRolesPanel, type ByokObservation } from "./ByokRolesPanel";

afterEach(cleanup);

const OBSERVED: ByokObservation = {
  state: "OBSERVED",
  roles: [
    {
      role: "mmmeta",
      state: "CONFIGURATION_OBSERVED",
      requestedProvider: "provider-a",
      requestedModel: "model-a",
    },
    { role: "mmsecretary", state: "ABSENT" },
  ],
};

/** The value rendered in the drawer row that carries this exact label. */
function drawerRow(dialog: HTMLElement, label: string): string | undefined {
  const term = within(dialog).getByText(label);
  return term.parentElement?.querySelector("dd")?.textContent ?? undefined;
}

describe("BYOK role setup boundary", () => {
  it("defaults to an unbound source without claiming setup, absence or readiness", () => {
    const { container } = render(<ByokRolesPanel />);
    expect(screen.getAllByText("Source not connected")).toHaveLength(2);
    expect(screen.queryByText("Needs setup")).toBeNull();
    expect(screen.queryByText("Configuration not installed")).toBeNull();
    expect(screen.queryByText("Configuration observed")).toBeNull();
    expect(screen.getAllByText("Unverified")).toHaveLength(2);
    expect(screen.getAllByText("Not proven")).toHaveLength(2);
    expect(screen.getAllByText("Unavailable")).toHaveLength(2);
    expect(container.querySelector("input, textarea, form")).toBeNull();
    expect(screen.queryByText(/ready to run|healthy|credentials? present|served model is/i)).toBeNull();
  });

  it("keeps an unbound source, an absent configuration and an unreadable source distinct", () => {
    const { rerender } = render(<ByokRolesPanel observation={{ state: "UNAVAILABLE" }} />);
    expect(screen.getAllByText("Source unavailable")).toHaveLength(2);
    expect(screen.queryByText("Source not connected")).toBeNull();

    rerender(<ByokRolesPanel observation={{
      state: "OBSERVED",
      roles: [
        { role: "mmmeta", state: "ABSENT" },
        { role: "mmsecretary", state: "UNAVAILABLE" },
      ],
    }} />);
    expect(screen.getByText("Configuration not installed")).toBeTruthy();
    expect(screen.getByText("Configuration unavailable")).toBeTruthy();
    expect(screen.queryByText("Source unavailable")).toBeNull();
  });

  it("separates the planning candidate from the observed requested configuration", async () => {
    const user = userEvent.setup();
    render(<ByokRolesPanel observation={OBSERVED} />);
    await user.click(screen.getByRole("button", { name: "Review connection · Meta-CEO" }));
    const dialog = screen.getByRole("dialog");
    expect(drawerRow(dialog, "Source status")).toBe("Source read");
    expect(drawerRow(dialog, "Configuration status")).toBe("Configuration observed");
    expect(drawerRow(dialog, "Model candidate")).toBe("GLM 5.3");
    expect(drawerRow(dialog, "Requested provider")).toBe("provider-a");
    expect(drawerRow(dialog, "Requested model")).toBe("model-a");
    expect(drawerRow(dialog, "Enrollment")).toBe("Unverified");
    expect(drawerRow(dialog, "Service and model connection")).toBe("Not verified");
    expect(drawerRow(dialog, "Last turn")).toBe("Not proven");
    expect(drawerRow(dialog, "Usage")).toBe("Unavailable");
    expect(screen.queryByText(/ready to run|healthy|credentials? present|served model is/i)).toBeNull();
  });

  it("reports an absent configuration as not installed and not as a missing credential", async () => {
    const user = userEvent.setup();
    render(<ByokRolesPanel observation={OBSERVED} />);
    await user.click(screen.getByRole("button", { name: "Review connection · Secretary" }));
    const dialog = screen.getByRole("dialog");
    expect(drawerRow(dialog, "Configuration status")).toBe("Configuration not installed");
    expect(drawerRow(dialog, "Requested provider")).toBe("Not observed");
    expect(drawerRow(dialog, "Requested model")).toBe("Not observed");
    expect(drawerRow(dialog, "Enrollment")).toBe("Unverified");
    expect(drawerRow(dialog, "Service and model connection")).toBe("Not verified");
    expect(screen.queryByText(/missing credential|credential absent/i)).toBeNull();
  });

  it("opens and closes the review from the keyboard and restores the trigger focus", async () => {
    const user = userEvent.setup();
    render(<ByokRolesPanel />);
    const trigger = screen.getByRole("button", { name: "Review connection · Meta-CEO" });
    trigger.focus();
    await user.keyboard("{Enter}");
    expect(screen.getByRole("dialog")).toBeTruthy();
    expect(document.activeElement).toBe(screen.getByRole("dialog"));
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(trigger);
  });

  it("closes the review from its own close control and returns focus to the trigger", async () => {
    const user = userEvent.setup();
    render(<ByokRolesPanel />);
    const trigger = screen.getByRole("button", { name: "Review connection · Secretary" });
    await user.click(trigger);
    await user.click(screen.getByRole("button", { name: "Close" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(trigger);
  });

  it("keeps keyboard focus inside the review and releases the trap once it closes", async () => {
    const user = userEvent.setup();
    render(<ByokRolesPanel />);
    await user.click(screen.getByRole("button", { name: "Review connection · Secretary" }));
    const close = screen.getByRole("button", { name: "Close" });
    close.focus();
    await user.keyboard("{Tab}");
    expect(document.activeElement).toBe(close);
    await user.keyboard("{Shift>}{Tab}{/Shift}");
    expect(document.activeElement).toBe(close);
    await user.click(close);
    expect(screen.queryByRole("dialog")).toBeNull();
    const event = new KeyboardEvent("keydown", { key: "Tab", bubbles: true, cancelable: true });
    document.dispatchEvent(event);
    expect(event.defaultPrevented).toBe(false);
  });

  it("shows only the reviewed role and switches roles without leaking the previous review", async () => {
    const user = userEvent.setup();
    render(<ByokRolesPanel observation={OBSERVED} />);
    await user.click(screen.getByRole("button", { name: "Review connection · Meta-CEO" }));
    let dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText("Meta-CEO")).toBeTruthy();
    expect(within(dialog).queryByText("Secretary")).toBeNull();
    await user.keyboard("{Escape}");
    await user.click(screen.getByRole("button", { name: "Review connection · Secretary" }));
    dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText("Secretary")).toBeTruthy();
    expect(within(dialog).queryByText("Meta-CEO")).toBeNull();
    expect(drawerRow(dialog, "Model candidate")).toBe("Qualified Flash route");
    expect(drawerRow(dialog, "Configuration status")).toBe("Configuration not installed");
    expect(drawerRow(dialog, "Requested provider")).toBe("Not observed");
  });

  it("hands the reviewed role to an external setup owner without changing any enrollment claim", async () => {
    const user = userEvent.setup();
    const review = vi.fn();
    render(<ByokRolesPanel onReviewConnection={review} />);
    expect(review).not.toHaveBeenCalled();
    expect(screen.getAllByText("Unverified")).toHaveLength(2);
    await user.click(screen.getByRole("button", { name: "Review connection · Secretary" }));
    expect(review).toHaveBeenCalledExactlyOnceWith("secretary");
    const dialog = screen.getByRole("dialog");
    expect(drawerRow(dialog, "Enrollment")).toBe("Unverified");
    expect(drawerRow(dialog, "Service and model connection")).toBe("Not verified");
    expect(drawerRow(dialog, "Last turn")).toBe("Not proven");
    expect(drawerRow(dialog, "Usage")).toBe("Unavailable");
    expect(screen.queryByText(/enrolled|verified enrollment/i)).toBeNull();
  });

  it("never collects a credential or offers a connect action in the review", async () => {
    const user = userEvent.setup();
    const { container } = render(<ByokRolesPanel onReviewConnection={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: "Review connection · Meta-CEO" }));
    expect(container.querySelector("input, textarea, select, form")).toBeNull();
    expect(screen.queryByRole("textbox")).toBeNull();
    expect(screen.queryByRole("button", { name: /^(connect|enroll|save|apply|retry)\b/i })).toBeNull();
  });

  it("bounds an observed request and never renders it as markup", async () => {
    const user = userEvent.setup();
    const long = "p".repeat(400);
    render(<ByokRolesPanel observation={{
      state: "OBSERVED",
      roles: [{
        role: "mmmeta",
        state: "CONFIGURATION_OBSERVED",
        requestedProvider: "<b>bold</b>" + long,
        requestedModel: "model" + String.fromCharCode(0) + "x",
      }],
    }} />);
    await user.click(screen.getByRole("button", { name: "Review connection · Meta-CEO" }));
    const dialog = screen.getByRole("dialog");
    expect(dialog.querySelector("b")).toBeNull();
    const provider = drawerRow(dialog, "Requested provider") ?? "";
    expect(provider.startsWith("<b>bold</b>")).toBe(true);
    expect(provider.length).toBeLessThanOrEqual(120);
    expect(drawerRow(dialog, "Requested model")).toBe("model x");
  });

  it("renders a complete translated review in zh-CN", async () => {
    const user = userEvent.setup();
    render(<ByokRolesPanel locale="zh-CN" observation={OBSERVED} />);
    expect(screen.getByRole("button", { name: "查看连接 · 秘书" })).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "查看连接 · Meta-CEO" }));
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText("连接审阅")).toBeTruthy();
    expect(within(dialog).getByText("来源与配置")).toBeTruthy();
    expect(within(dialog).getByText("证明状态")).toBeTruthy();
    expect(within(dialog).getByText("后续已授权步骤")).toBeTruthy();
    expect(drawerRow(dialog, "来源状态")).toBe("已读取来源");
    expect(drawerRow(dialog, "配置状态")).toBe("已观察到配置");
    expect(drawerRow(dialog, "请求的提供方")).toBe("provider-a");
    expect(drawerRow(dialog, "请求的模型")).toBe("model-a");
    expect(drawerRow(dialog, "接入登记")).toBe("尚未验证");
    expect(drawerRow(dialog, "服务与模型连接")).toBe("未经验证");
    expect(drawerRow(dialog, "最近一次交互")).toBe("尚未确认");
    expect(drawerRow(dialog, "用量")).toBe("不可用");
    expect(within(dialog).getByRole("button", { name: "关闭" })).toBeTruthy();
  });
});
