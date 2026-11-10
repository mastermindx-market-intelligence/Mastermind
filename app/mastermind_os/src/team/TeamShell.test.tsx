// @vitest-environment jsdom
import { useEffect, useState } from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { TeamShell } from "./TeamShell";

afterEach(cleanup);
function Draft({ name, opened }: { name: string; opened(): void }) {
  const [value, setValue] = useState("");
  useEffect(opened, [opened]);
  return <label>{name}<input value={value} onChange={event => setValue(event.target.value)} /></label>;
}

describe("one Team shell retains independently owned consumers", () => {
  it("opens readers only on selection and retains drafts without another mount", () => {
    const company = vi.fn(), native = vi.fn();
    render(<TeamShell locale="en" company={<Draft name="Backlog draft" opened={company} />}
      runtime={<p>Runtime source unavailable</p>} nativeConversations={<Draft name="Native draft" opened={native} />} />);
    expect(company).toHaveBeenCalledTimes(1); expect(native).not.toHaveBeenCalled();
    fireEvent.change(screen.getByRole("textbox", { name: "Backlog draft" }), { target: { value: "Original project" } });
    fireEvent.click(screen.getByRole("tab", { name: "Native conversations" }));
    expect(screen.queryByRole("textbox", { name: "Backlog draft" })).toBeNull();
    fireEvent.change(screen.getByRole("textbox", { name: "Native draft" }), { target: { value: "Original recipient" } });
    fireEvent.click(screen.getByRole("tab", { name: "Runtime profiles" }));
    expect(screen.getByText("Runtime source unavailable")).toBeTruthy();
    fireEvent.click(screen.getByRole("tab", { name: "Native conversations" }));
    expect((screen.getByRole("textbox", { name: "Native draft" }) as HTMLInputElement).value).toBe("Original recipient");
    expect(native).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("tab", { name: "Company" }));
    expect((screen.getByRole("textbox", { name: "Backlog draft" }) as HTMLInputElement).value).toBe("Original project");
    expect(company).toHaveBeenCalledTimes(1);
  });
  it("keeps independent conversations reachable through keyboard navigation", () => {
    render(<TeamShell locale="zh-CN" company={<p>公司来源不可用</p>} runtime={<p>运行来源不可用</p>}
      nativeConversations={<p>选择对话收件人</p>} />);
    const first = screen.getByRole("tab", { name: "公司与工作" }); first.focus();
    fireEvent.keyDown(first, { key: "End" });
    expect(document.activeElement).toBe(screen.getByRole("tab", { name: "原生对话" }));
    expect(screen.getByRole("tabpanel", { name: "原生对话" }).textContent).toBe("选择对话收件人");
    fireEvent.keyDown(document.activeElement!, { key: "ArrowRight" });
    expect(document.activeElement).toBe(first);
  });
  it("does not advertise absent consumers and resets drafts at the outer authorization remount", () => {
    const opened = vi.fn();
    const view = render(<TeamShell key="auth-a" locale="en" company={<Draft name="Scoped draft" opened={opened} />} />);
    expect(screen.queryByRole("tablist")).toBeNull();
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "Previous principal" } });
    view.rerender(<TeamShell key="auth-b" locale="en" company={<Draft name="Scoped draft" opened={opened} />} />);
    expect((screen.getByRole("textbox") as HTMLInputElement).value).toBe("");
    expect(opened).toHaveBeenCalledTimes(2);
  });
});
