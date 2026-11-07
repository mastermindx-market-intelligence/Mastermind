// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ActivationReceipt } from "./ActivationReceipt";
import type {
  OperationPointer,
  OperationState,
} from "../orchestration/operation-controller";

beforeEach(() => {
  vi.clearAllMocks();
});
afterEach(() => {
  cleanup();
});

// ---------------------------------------------------------------------------
// Fixtures — exact finite controller states
// ---------------------------------------------------------------------------

const pointer: OperationPointer = {
  operationKey: "op-2026-42",
  kind: "launch",
  targetKey: "ws-main",
};

const idle: OperationState = { status: "idle", pointer: null, reason: "IDLE" };
const submitting: OperationState = {
  status: "submitting",
  pointer,
  reason: "SUBMITTING",
};
const checking: OperationState = {
  status: "checking",
  pointer,
  reason: "CHECKING",
};
const acceptedWithSelection: OperationState = {
  status: "accepted",
  pointer: null,
  reason: "ACCEPTED",
  missionSelection: { workRef: "work-alpha", rootJobId: "job-7" },
};
const acceptedBare: OperationState = {
  status: "accepted",
  pointer: null,
  reason: "ACCEPTED",
};
const refused: OperationState = {
  status: "refused",
  pointer: null,
  reason: "REFUSED",
};
const unknown: OperationState = {
  status: "unknown",
  pointer,
  reason: "UNKNOWN_RECEIPT",
};
const unknownNullTarget: OperationState = {
  status: "unknown",
  pointer: { ...pointer, targetKey: null },
  reason: "UNKNOWN_RECEIPT",
};

// ---------------------------------------------------------------------------
// Current-state receipt
// ---------------------------------------------------------------------------

describe("ActivationReceipt", () => {
  it("renders unavailable for a null state and fabricates nothing", () => {
    const { container } = render(<ActivationReceipt state={null} />);
    expect(screen.getByText("Request status unavailable")).toBeTruthy();
    expect(container.querySelector("button")).toBeNull();
    expect(container.querySelector("dl")).toBeNull();
    expect(container.querySelector("details")).toBeNull();
  });

  it("renders the idle owner outcome", () => {
    render(<ActivationReceipt state={idle} />);
    expect(screen.getByText("No current request receipt")).toBeTruthy();
  });

  it("renders submitting as awaiting the original result", () => {
    render(<ActivationReceipt state={submitting} />);
    expect(
      screen.getByText("Awaiting the original request result."),
    ).toBeTruthy();
  });

  it("renders checking as checking the original result", () => {
    render(<ActivationReceipt state={checking} />);
    expect(screen.getByText("Checking the original result.")).toBeTruthy();
  });

  it("renders the refused owner outcome with no retry action", () => {
    const { container } = render(<ActivationReceipt state={refused} />);
    expect(screen.getByText("Request declined")).toBeTruthy();
    expect(container.querySelector("button")).toBeNull();
  });

  it("keeps the finite controller reason inside details only", () => {
    const { container } = render(<ActivationReceipt state={refused} />);
    const reason = screen.getByText("REFUSED");
    expect(reason.closest("details")).not.toBeNull();
    // The reason code is not the receipt headline and not a loose paragraph.
    expect(container.querySelector("p[role='status']")?.textContent).toBe(
      "Request declined",
    );
  });

  it("renders the unknown outcome with the exact original pointer", () => {
    render(<ActivationReceipt state={unknown} />);
    expect(screen.getByText("Request outcome unknown")).toBeTruthy();
    expect(screen.getByText("op-2026-42")).toBeTruthy();
    expect(screen.getByText("launch")).toBeTruthy();
    expect(screen.getByText("ws-main")).toBeTruthy();
    expect(
      screen.getByText(
        "This request is unresolved. Do not send it again, choose another destination, or create a replacement.",
      ),
    ).toBeTruthy();
  });

  it("reports a null original target as not reported, never zero or no-effect", () => {
    render(<ActivationReceipt state={unknownNullTarget} />);
    expect(screen.getByText("Not reported")).toBeTruthy();
    expect(screen.queryByText("0")).toBeNull();
    expect(screen.queryByText(/no effect/i)).toBeNull();
    expect(screen.getByText("op-2026-42")).toBeTruthy();
  });

  it("offers the original-status read only explicitly, once per click", () => {
    const onReadOriginalStatus = vi.fn();
    const { container, rerender } = render(<ActivationReceipt state={unknown} />);
    // No callback supplied: no button at all.
    expect(container.querySelector("button")).toBeNull();

    rerender(
      <ActivationReceipt
        state={unknown}
        onReadOriginalStatus={onReadOriginalStatus}
      />,
    );
    const button = screen.getByRole("button", { name: "Read original status" });
    // No mount effect and no automatic action: the callback is untouched so far.
    expect(onReadOriginalStatus).not.toHaveBeenCalled();
    fireEvent.click(button);
    expect(onReadOriginalStatus).toHaveBeenCalledTimes(1);
    fireEvent.click(button);
    expect(onReadOriginalStatus).toHaveBeenCalledTimes(2);

    // The read is offered for the unknown state only.
    rerender(
      <ActivationReceipt
        state={acceptedWithSelection}
        onReadOriginalStatus={onReadOriginalStatus}
      />,
    );
    expect(container.querySelector("button")).toBeNull();
  });

  it("never offers the original-status read outside an unknown state", () => {
    const onReadOriginalStatus = vi.fn();
    for (const state of [idle, submitting, checking, acceptedWithSelection, refused]) {
      const { container } = render(
        <ActivationReceipt
          state={state}
          onReadOriginalStatus={onReadOriginalStatus}
        />,
      );
      expect(container.querySelector("button")).toBeNull();
      cleanup();
    }
    expect(onReadOriginalStatus).not.toHaveBeenCalled();
  });

  it("renders the accepted owner receipt with the actual mission selection only", () => {
    const { container } = render(<ActivationReceipt state={acceptedWithSelection} />);
    expect(screen.getByText("Request accepted")).toBeTruthy();
    expect(screen.getByText("work-alpha")).toBeTruthy();
    expect(screen.getByText("job-7")).toBeTruthy();
    expect(
      screen.getByText(
        "This receipt does not confirm that work started, a result returned, or the result was accepted.",
      ),
    ).toBeTruthy();
    // Terminal pointer is null: no operation ID may be invented, and the
    // accepted launch is not labelled as a completed activation.
    expect(container.textContent).not.toContain("op-2026-42");
    expect(screen.queryByText(/activation complete/i)).toBeNull();
    expect(screen.queryByText(/complete/i)).toBeNull();
    // Current receipt only: no history list is fabricated.
    expect(container.querySelector("ul")).toBeNull();
    expect(container.querySelector("ol")).toBeNull();
  });

  it("fabricates nothing for an accepted receipt without a mission selection", () => {
    const { container } = render(<ActivationReceipt state={acceptedBare} />);
    expect(screen.getByText("Request accepted")).toBeTruthy();
    expect(
      screen.getByText(
        "This receipt does not confirm that work started, a result returned, or the result was accepted.",
      ),
    ).toBeTruthy();
    expect(container.querySelector("dl")).toBeNull();
    expect(container.querySelector("button")).toBeNull();
  });

  it("renders zh-CN wording for the current receipt states", () => {
    const { rerender } = render(
      <ActivationReceipt state={unknown} locale="zh-CN" onReadOriginalStatus={vi.fn()} />,
    );
    expect(screen.getByText("请求状态")).toBeTruthy();
    expect(screen.getByText("请求结果未知")).toBeTruthy();
    expect(screen.getByText("op-2026-42")).toBeTruthy();
    expect(screen.getByText("读取原始状态")).toBeTruthy();
    rerender(<ActivationReceipt state={idle} locale="zh-CN" />);
    expect(screen.getByText("当前没有请求回执")).toBeTruthy();
    rerender(<ActivationReceipt state={refused} locale="zh-CN" />);
    expect(screen.getByText("请求已拒绝")).toBeTruthy();
    rerender(<ActivationReceipt state={acceptedWithSelection} locale="zh-CN" />);
    expect(screen.getByText("请求已接受")).toBeTruthy();
    expect(screen.getByText("work-alpha")).toBeTruthy();
    expect(screen.getByText(
      "此回执不能确认工作已开始、结果已返回或结果已被接受。",
    )).toBeTruthy();
  });

  it("reports 未报告 for a null zh-CN original target", () => {
    render(<ActivationReceipt state={unknownNullTarget} locale="zh-CN" />);
    expect(screen.getByText("未报告")).toBeTruthy();
  });

  it("renders zh-CN unavailable for a null state", () => {
    render(<ActivationReceipt state={null} locale="zh-CN" />);
    expect(screen.getByText("请求状态不可用")).toBeTruthy();
  });
});
