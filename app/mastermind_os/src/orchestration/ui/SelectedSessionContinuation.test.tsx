// @vitest-environment jsdom
// Focused coverage for the selected-session continuation panel.
import { afterEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import {
  MAX_CONDITION_CODEPOINTS,
  SelectedSessionContinuation,
} from "./SelectedSessionContinuation";
import type { OperationPointer, OperationState } from "../operation-controller";

const POINTER: OperationPointer = {
  operationKey: "session-continue-" + "a".repeat(64),
  kind: "message",
  targetKey: "fabric_attempt:" + "b".repeat(64),
};

function mount(overrides: Partial<Parameters<typeof SelectedSessionContinuation>[0]> = {}) {
  const onContinue = vi.fn(overrides.onContinue);
  const onRecover = vi.fn();
  const props = {
    sessionKey: POINTER.targetKey,
    status: null,
    retainedPointer: null,
    reading: false,
    recovering: false,
    sending: false,
    onRecover,
    ...overrides,
    onContinue,
  };
  const view = render(<SelectedSessionContinuation {...props} />);
  return { ...view, onContinue, onRecover, props };
}

const type = (label: string, value: string) => {
  fireEvent.change(screen.getByLabelText(label), { target: { value } });
};
const submit = () => fireEvent.click(screen.getByRole("button", { name: /^Send$/i }));

afterEach(cleanup);

describe("selected session continuation panel", () => {
  it("recovers the original pointer after its target disappears", () => {
    const { onRecover } = mount({ sessionKey: null, unavailableReason: "SESSION_UNAVAILABLE", retainedPointer: POINTER });
    fireEvent.click(screen.getByRole("button", { name: /check status/i }));
    expect(onRecover).toHaveBeenCalledTimes(1);
    expect(screen.queryByLabelText("What would you like done?")).toBeNull();
  });
  it.each([{ name: "retained pointer", state: { retainedPointer: POINTER } }, { name: "pointer discovery", state: { reading: true } }])("blocks a new continuation during $name", ({ state }) => {
    mount(state);
    type("What would you like done?", "Continue"); type("How will we know it is done?", "done");
    expect((screen.getByRole("button", { name: /^Send$/i }) as HTMLButtonElement).disabled).toBe(true);
  });
  it("shows only the truthful unavailable state and no form when unavailable", () => {
    mount({ sessionKey: null, unavailableReason: "SESSION_UNAVAILABLE" });
    expect(screen.getByText("SESSION_UNAVAILABLE")).toBeTruthy();
    expect(screen.queryByLabelText("What would you like done?")).toBeNull();
    expect(screen.queryByRole("button", { name: /^Send$/i })).toBeNull();
  });

  it("presents the verified target and offers no stop control", () => {
    mount();
    expect(screen.getByText(POINTER.targetKey!)).toBeTruthy();
    expect(screen.getByLabelText("What would you like done?")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /stop|interrupt/i })).toBeNull();
  });

  it.each([
    { name: "empty instruction", field: "What would you like done?", value: "" },
    { name: "blank instruction", field: "What would you like done?", value: "   " },
    { name: "long instruction", field: "What would you like done?", value: "x".repeat(MAX_CONDITION_CODEPOINTS + 1) },
    { name: "empty completion", field: "How will we know it is done?", value: "" },
    { name: "blank completion", field: "How will we know it is done?", value: "   " },
    { name: "long Unicode completion", field: "How will we know it is done?", value: "\u{1D11E}".repeat(MAX_CONDITION_CODEPOINTS + 1) },
  ])("refuses $name", ({ field, value }) => {
    mount();
    // Both fields valid first, then the offending value: only that field may
    // block the dispatch.
    type(field === "What would you like done?" ? "How will we know it is done?" : "What would you like done?", "CI green");
    type(field, value);
    const button = screen.getByRole("button", { name: /^Send$/i }) as HTMLButtonElement;
    expect(button.disabled).toBe(true);
  });

  it("accepts exactly 700 astral code points by code-point counting", () => {
    mount();
    type("What would you like done?", "\u{1D11E}".repeat(MAX_CONDITION_CODEPOINTS));
    type("How will we know it is done?", "CI green");
    const button = screen.getByRole("button", { name: /^Send$/i }) as HTMLButtonElement;
    expect(button.disabled).toBe(false);
  });

  it("dispatches once per submit and never invents a condition re-evaluation", () => {
    const { onContinue } = mount();
    type("What would you like done?", "Continue");
    type("How will we know it is done?", "CI green");
    submit();
    fireEvent.submit(document.querySelector("form")!);
    expect(onContinue).toHaveBeenCalledTimes(1);
    const [instruction, condition] = onContinue.mock.calls[0];
    expect(instruction).toBe("Continue");
    expect(condition).toBe("CI green");
  });

  it("clears the exact submitted pair on accepted; a replayed completion never clears retyped text", () => {
    let complete: (outcome: { status: "accepted" } | { status: "refused" }) => void = () => {};
    const { onContinue } = mount({
      onContinue: (_i, _c, onComplete) => {
        complete = onComplete;
      },
    });
    type("What would you like done?", "Continue");
    type("How will we know it is done?", "CI green");
    submit();
    act(() => complete({ status: "accepted" }));
    expect((screen.getByLabelText("What would you like done?") as HTMLTextAreaElement).value).toBe("");
    expect((screen.getByLabelText("How will we know it is done?") as HTMLTextAreaElement).value).toBe("");
    // The user retypes after the terminal receipt; the settled dispatch's
    // completion is spent and cannot clear the new text.
    type("What would you like done?", "Continue more");
    act(() => complete({ status: "accepted" }));
    expect((screen.getByLabelText("What would you like done?") as HTMLTextAreaElement).value).toBe("Continue more");
    expect(onContinue).toHaveBeenCalledTimes(1);
  });

  it("keeps the text on refused and shows only the closed receipt code", () => {
    let complete: (outcome: { status: "accepted" } | { status: "refused" }) => void = () => {};
    mount({
      onContinue: (_i, _c, onComplete) => {
        complete = onComplete;
      },
    });
    type("What would you like done?", "Continue");
    type("How will we know it is done?", "CI green");
    submit();
    act(() => complete({ status: "refused" }));
    expect((screen.getByLabelText("What would you like done?") as HTMLTextAreaElement).value).toBe("Continue");
    const refused: OperationState = { status: "refused", pointer: null, reason: "REFUSED" };
    mount({ status: refused });
    expect(screen.getByText("REFUSED")).toBeTruthy();
  });

  it("shows the retained original key with status-only recovery and never a send", () => {
    const { onRecover } = mount({ retainedPointer: POINTER, status: null });
    expect(screen.getByText(POINTER.operationKey)).toBeTruthy();
    const check = screen.getByRole("button", { name: /check status/i });
    fireEvent.click(check);
    expect(onRecover).toHaveBeenCalledTimes(1);
    // Status-only: a recovering run keeps the recovery control disabled.
    mount({ retainedPointer: POINTER, recovering: true });
    expect(
      (screen.getByRole("button", { name: /checking/i }) as HTMLButtonElement).disabled,
    ).toBe(true);
  });

  it("a late completion after an owner-epoch remount cannot touch the new panel", () => {
    let complete: (outcome: { status: "accepted" } | { status: "refused" }) => void = () => {};
    const first = render(
      <SelectedSessionContinuation
        sessionKey={POINTER.targetKey}
        status={null}
        retainedPointer={null}
        reading={false}
        recovering={false}
        sending={false}
        onContinue={(_i, _c, onComplete) => {
          complete = onComplete;
        }}
        onRecover={() => {}}
      />,
    );
    fireEvent.change(screen.getByLabelText("What would you like done?"), { target: { value: "First" } });
    fireEvent.change(screen.getByLabelText("How will we know it is done?"), { target: { value: "done" } });
    submit();
    first.unmount();
    const second = render(
      <SelectedSessionContinuation
        key="next-epoch"
        sessionKey={POINTER.targetKey}
        status={null}
        retainedPointer={null}
        reading={false}
        recovering={false}
        sending={false}
        onContinue={vi.fn()}
        onRecover={() => {}}
      />,
    );
    expect(() => complete({ status: "accepted" })).not.toThrow();
    expect((screen.getByLabelText("What would you like done?") as HTMLTextAreaElement).value).toBe("");
    second.unmount();
  });
});


describe("FE-01 outcome-first continuation chrome", () => {
  it("requires explicit Unicode-bounded fields and never sends on textarea Enter or IME", () => {
    const { onContinue } = mount();
    const instruction = screen.getByLabelText("What would you like done?");
    const condition = screen.getByLabelText("How will we know it is done?");
    fireEvent.change(instruction, { target: { value: "🧭".repeat(700) } });
    expect((screen.getByRole("button", { name: "Send" }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(condition, { target: { value: "Explicit original criterion" } });
    fireEvent.keyDown(instruction, { key: "Enter" });
    fireEvent.keyDown(condition, { key: "Enter", isComposing: true, keyCode: 229 });
    expect(onContinue).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(onContinue).toHaveBeenCalledTimes(1);
    expect(onContinue.mock.calls[0].slice(0,2)).toEqual(["🧭".repeat(700), "Explicit original criterion"]);
  });
  it("localizes only static chrome and preserves explicit payload across locale change", () => {
    const onContinue = vi.fn(); const props = { sessionKey: POINTER.targetKey, status: null, retainedPointer: null, reading: false, recovering: false, sending: false, onContinue, onRecover: vi.fn() };
    const { rerender } = render(<SelectedSessionContinuation {...props} />);
    fireEvent.change(screen.getByLabelText("What would you like done?"), { target: { value: "Keep English payload 继续" } });
    expect((screen.getByLabelText("How will we know it is done?") as HTMLTextAreaElement).value).toBe("");
    rerender(<SelectedSessionContinuation {...props} locale="zh-CN" />);
    expect((screen.getByLabelText("你希望完成什么？") as HTMLTextAreaElement).value).toBe("Keep English payload 继续");
    fireEvent.change(screen.getByLabelText("达到什么条件才算完成？"), { target: { value: "Exact DONE criterion" } });
    fireEvent.click(screen.getByRole("button", { name: "发送" }));
    expect(onContinue.mock.calls[0].slice(0,2)).toEqual(["Keep English payload 继续", "Exact DONE criterion"]);
  });
  it("shows committed receipt without success/progress and retains original-key status-only recovery in ZH", () => {
    const committed = mount({ locale: "zh-CN", status: { status: "accepted" } as OperationState });
    expect(screen.getByText("消息已提交。")).toBeTruthy();
    expect(document.body.textContent).not.toMatch(/worker success|working|执行成功/i);
    committed.unmount();
    const onRecover = vi.fn();
    mount({ locale: "zh-CN", retainedPointer: POINTER, onRecover, unavailableReason: "OWNER_REASON_UNCHANGED" });
    expect(screen.getByText(POINTER.operationKey)).toBeTruthy();
    expect(screen.getByText("OWNER_REASON_UNCHANGED")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "查看状态" }));
    expect(onRecover).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("button", { name: "发送" })).toBeNull();
  });
});
