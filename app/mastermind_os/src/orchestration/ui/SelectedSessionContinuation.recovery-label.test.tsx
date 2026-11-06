// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { SelectedSessionContinuation } from "./SelectedSessionContinuation";
import type { SelectedSessionContinuationProps, SessionContinuationOutcome } from "./SelectedSessionContinuation";
import type { OperationPointer } from "../operation-controller";

const POINTER: OperationPointer = {
  operationKey: "session-continue-" + "a".repeat(64),
  kind: "message",
  targetKey: "fabric_attempt:" + "b".repeat(64),
};
const locales = [
  { locale: "en" as const, send: "Send", sending: "Sending…", check: "Check status", checking: "Checking…" },
  { locale: "zh-CN" as const, send: "发送", sending: "正在发送…", check: "查看状态", checking: "正在查询…" },
];
function props(overrides: Partial<SelectedSessionContinuationProps> = {}): SelectedSessionContinuationProps {
  return { sessionKey: POINTER.targetKey, status: null, retainedPointer: null,
    reading: false, recovering: false, sending: false, onContinue: vi.fn(), onRecover: vi.fn(), ...overrides };
}
function enterDraft() {
  const fields = screen.getAllByRole<HTMLTextAreaElement>("textbox");
  fireEvent.change(fields[0], { target: { value: "Preserve my instruction" } });
  fireEvent.change(fields[1], { target: { value: "Keep the original completion condition" } });
  return fields;
}
afterEach(cleanup);

describe.each(locales)("$locale continuation progress labels", labels => {
  it.each(["retained pointer", "pointer read unavailable"])("does not claim a send during repeated recovery of %s", held => {
    const onContinue = vi.fn(), onRecover = vi.fn();
    let current = props({ locale: labels.locale, onContinue, onRecover,
      ...(held === "retained pointer" ? { retainedPointer: POINTER } : { recoveryRequired: true }) });
    const view = render(<SelectedSessionContinuation {...current} />);
    const fields = enterDraft();
    const send = () => screen.getByRole<HTMLButtonElement>("button", { name: labels.send });
    expect(send().disabled).toBe(true);
    for (let attempt = 1; attempt <= 2; attempt++) {
      fireEvent.click(screen.getByRole("button", { name: labels.check }));
      expect(onRecover).toHaveBeenCalledTimes(attempt);
      current = { ...current, recovering: true };
      view.rerender(<SelectedSessionContinuation {...current} />);
      const checking = screen.getByRole<HTMLButtonElement>("button", { name: labels.checking });
      expect(checking.disabled).toBe(true);
      expect(send().disabled).toBe(true);
      expect(screen.queryByRole("button", { name: labels.sending })).toBeNull();
      fireEvent.click(checking);
      fireEvent.submit(document.querySelector("form")!);
      expect(onRecover).toHaveBeenCalledTimes(attempt);
      expect(onContinue).not.toHaveBeenCalled();
      expect(fields.map(field => field.value)).toEqual(["Preserve my instruction", "Keep the original completion condition"]);
      expect(fields.every(field => field.disabled)).toBe(true);
      current = { ...current, recovering: false };
      view.rerender(<SelectedSessionContinuation {...current} />);
    }
    expect(send().disabled).toBe(true);
    if (held === "retained pointer") expect(screen.getByText(POINTER.operationKey)).toBeTruthy();
  });

  it("does not relabel an accepted receipt Sending while recovery settles", () => {
    render(<SelectedSessionContinuation {...props({ locale: labels.locale,
      recovering: true, status: { status: "accepted", pointer: null, reason: "ACCEPTED" } })} />);
    expect(screen.getByRole<HTMLButtonElement>("button", { name: labels.send }).disabled).toBe(true);
    expect(screen.queryByRole("button", { name: labels.sending })).toBeNull();
  });

  it.each([false, true])("retains Sending for an actual owner dispatch with recovering=%s", recovering => {
    render(<SelectedSessionContinuation {...props({ locale: labels.locale, sending: true, recovering })} />);
    expect(screen.getByRole<HTMLButtonElement>("button", { name: labels.sending }).disabled).toBe(true);
  });

  it("tracks a local send separately from status recovery and retains the refused draft", () => {
    let complete: (outcome: SessionContinuationOutcome) => void = () => {};
    const onContinue = vi.fn((_instruction: string, _condition: string, done: typeof complete) => { complete = done; });
    let current = props({ locale: labels.locale, onContinue });
    const view = render(<SelectedSessionContinuation {...current} />);
    const fields = enterDraft();
    fireEvent.click(screen.getByRole("button", { name: labels.send }));
    expect(onContinue).toHaveBeenCalledTimes(1);
    expect(screen.getByRole<HTMLButtonElement>("button", { name: labels.sending }).disabled).toBe(true);
    current = { ...current, recovering: true };
    view.rerender(<SelectedSessionContinuation {...current} />);
    expect(screen.getByRole("button", { name: labels.sending })).toBeTruthy();
    act(() => complete({ status: "refused" }));
    expect(screen.getByRole<HTMLButtonElement>("button", { name: labels.send }).disabled).toBe(true);
    expect(screen.queryByRole("button", { name: labels.sending })).toBeNull();
    current = { ...current, recovering: false, status: { status: "refused", pointer: null, reason: "REFUSED" } };
    view.rerender(<SelectedSessionContinuation {...current} />);
    expect(screen.getByRole<HTMLButtonElement>("button", { name: labels.send }).disabled).toBe(false);
    expect(fields.map(field => field.value)).toEqual(["Preserve my instruction", "Keep the original completion condition"]);
    expect(onContinue).toHaveBeenCalledTimes(1);
  });

  it("leaves idle, pointer discovery and unavailable presentation unchanged", () => {
    const current = props({ locale: labels.locale });
    const view = render(<SelectedSessionContinuation {...current} />);
    expect(screen.getByRole<HTMLButtonElement>("button", { name: labels.send }).disabled).toBe(true);
    view.rerender(<SelectedSessionContinuation {...current} reading />);
    expect(screen.getByRole<HTMLButtonElement>("button", { name: labels.send }).disabled).toBe(true);
    expect(screen.queryByRole("button", { name: labels.sending })).toBeNull();
    view.rerender(<SelectedSessionContinuation {...current} sessionKey={null} unavailableReason="SESSION_UNAVAILABLE"
      retainedPointer={POINTER} recovering />);
    expect(screen.queryByRole("button", { name: labels.send })).toBeNull();
    expect(screen.queryByRole("button", { name: labels.sending })).toBeNull();
  });
});
