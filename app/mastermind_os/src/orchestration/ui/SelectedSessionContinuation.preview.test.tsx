// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { SelectedSessionContinuation, type SelectedSessionContinuationProps } from "./SelectedSessionContinuation";
afterEach(cleanup);
const base: SelectedSessionContinuationProps = {
  sessionKey: "fabric_attempt:" + "b".repeat(64), status: null, retainedPointer: null,
  reading: false, recovering: false, sending: false, onContinue: vi.fn(), onRecover: vi.fn(),
};
function openPreview(label = "Review your message") {
  const details = screen.getByText(label).closest("details")!;
  details.open = true; fireEvent(details, new Event("toggle"));
}
function fill(instruction = "  Keep original\ntext <script>safe</script>  ", condition = "Return the actual result\nthen stop") {
  fireEvent.change(screen.getByLabelText("What would you like done?"), { target: { value: instruction } });
  fireEvent.change(screen.getByLabelText("How will we know it is done?"), { target: { value: condition } });
}
describe("current selected-session draft preview", () => {
  it("starts closed and opening it preserves exact text without submitting", () => {
    const onContinue = vi.fn(), onRecover = vi.fn();
    render(<SelectedSessionContinuation {...base} onContinue={onContinue} onRecover={onRecover} />);
    fill(); expect(screen.queryByTestId("session-preview-instruction")).toBeNull(); openPreview();
    expect(screen.getByTestId("session-preview-instruction").textContent).toBe("  Keep original\ntext <script>safe</script>  ");
    expect(screen.getByTestId("session-preview-condition").textContent).toBe("Return the actual result\nthen stop");
    expect(document.querySelector("script")).toBeNull();
    expect(onContinue).not.toHaveBeenCalled(); expect(onRecover).not.toHaveBeenCalled();
    expect(screen.getAllByRole("button", { name: /^Send$/ })).toHaveLength(1);
  });
  it("updates both draft fields and selection without an older reviewed snapshot", () => {
    const view = render(<SelectedSessionContinuation {...base} />);
    fill("First", "First condition"); openPreview(); fill("Edited", "Edited condition");
    const target = "fabric_attempt:" + "c".repeat(64);
    view.rerender(<SelectedSessionContinuation {...base} sessionKey={target} />);
    expect(screen.getByTestId("session-preview-instruction").textContent).toBe("Edited");
    expect(screen.getByTestId("session-preview-condition").textContent).toBe("Edited condition");
    expect(screen.queryByText(base.sessionKey!)).toBeNull(); expect(screen.getAllByText(target)).toHaveLength(2);
    expect(screen.queryByText(/reviewed|permission verified/i)).toBeNull();
  });
  it("preserves the unresolved-operation hold without claiming the request is unsent", () => {
    const pointer = { operationKey: "session-continue-" + "a".repeat(64), kind: "message" as const, targetKey: base.sessionKey! };
    render(<SelectedSessionContinuation {...base} retainedPointer={pointer} />); fill(); openPreview();
    expect(screen.getByText(/Its outcome is unresolved here/)).toBeTruthy();
    expect((screen.getByRole("button", { name: /^Send$/ }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.queryByText(/nothing has been sent|unsent/i)).toBeNull();
  });
  it("withholds the previous target when qualification disappears", () => {
    const view = render(<SelectedSessionContinuation {...base} />); fill(); openPreview();
    view.rerender(<SelectedSessionContinuation {...base} sessionKey={null} />);
    expect(screen.queryByText(base.sessionKey!)).toBeNull();
    expect(screen.getByText("No session target is available.")).toBeTruthy();
    expect((screen.getByRole("button", { name: /^Send$/ }) as HTMLButtonElement).disabled).toBe(true);
  });
  it("does not invent content, attachments, permission or observation timestamps", () => {
    render(<SelectedSessionContinuation {...base} />); openPreview();
    expect(screen.getByText("No draft text yet.")).toBeTruthy(); expect(screen.getByText("No completion condition yet.")).toBeTruthy();
    expect(screen.queryByText(/attached sources|observed at|generation|permission unverified/i)).toBeNull();
  });
  it("provides the same local preview in Chinese", () => {
    render(<SelectedSessionContinuation {...base} locale="zh-CN" />); openPreview("查看消息草稿");
    expect(screen.getByText("当前草稿")).toBeTruthy(); expect(screen.getByText("目标会话")).toBeTruthy();
    expect(screen.getByText("发送仍需通过现有会话检查。")).toBeTruthy();
  });
});
