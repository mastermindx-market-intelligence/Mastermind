// @vitest-environment jsdom
import { StrictMode } from "react";
import {
  cleanup,
  render,
  screen,
  fireEvent,
  waitFor,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, it, expect, vi } from "vitest";
import {
  DirectNativeResultPanel,
  type DirectNativeResultPanelProps,
} from "./DirectNativeResultPanel";
const selection = {
  work_ref: "WS:H2-FIXTURE",
  job_id: "JOB-123",
  attempt_id: null,
};
function result(consumed = false) {
  return {
    schema: "mastermind.direct_native_result_response.v1",
    selection: { ...selection, attempt_id: "ATT-456" },
    availability: "AVAILABLE",
    reason_codes: [],
    result: {
      result_digest: "d".repeat(64),
      summary: "Retained analysis",
      current_state: "Complete",
      completed_steps: [],
      next_actions: [],
    },
    consumption: consumed
      ? { state: "CONSUMED", receipt_digest: "c".repeat(64) }
      : { state: "UNCONSUMED", receipt_digest: null },
  };
}
afterEach(cleanup);
describe("direct native result interaction", () => {
  it("keeps keyboard focus on the pending and settled outcome of explicit actions", async () => {
    let complete!: (outcome: { status: "accepted" | "refused" }) => void;
    const read = vi
      .fn()
      .mockResolvedValueOnce(result())
      .mockResolvedValueOnce(result(true));
    render(
      <DirectNativeResultPanel
        selection={selection}
        read={read}
        held={false}
        onConsume={(_selection, _digest, callback) => {
          complete = callback;
        }}
      />,
    );
    const user = userEvent.setup();
    await user.click(
      screen.getByRole("button", { name: "Read current result" }),
    );
    expect(await screen.findByText("Retained analysis")).toBeTruthy();
    expect(document.activeElement).toBe(screen.getByRole("status"));
    await user.click(
      screen.getByRole("button", { name: "Acknowledge this result" }),
    );
    expect(document.activeElement).toBe(screen.getByRole("status"));
    complete({ status: "accepted" });
    await waitFor(() =>
      expect(screen.getByRole("status").textContent).toContain(
        "original commissioning parent acknowledged",
      ),
    );
    expect(document.activeElement).toBe(screen.getByRole("status"));
  });
  it.each([
    ["en", "dark"],
    ["en", "light"],
    ["zh-CN", "dark"],
    ["zh-CN", "light"],
  ] as const)(
    "keeps read separate from acknowledgment in %s/%s",
    async (locale, theme) => {
      const read = vi.fn().mockResolvedValue(result()),
        consume = vi.fn();
      render(
        <StrictMode>
          <div data-theme={theme}>
            <DirectNativeResultPanel
              selection={selection}
              locale={locale}
              read={read}
              held={false}
              onConsume={consume}
            />
          </div>
        </StrictMode>,
      );
      const user = userEvent.setup();
      await user.tab();
      expect(document.activeElement?.tagName).toBe("BUTTON");
      await user.keyboard("{Enter}");
      expect(await screen.findByText("Retained analysis")).toBeTruthy();
      expect(read).toHaveBeenCalledTimes(1);
      expect(consume).not.toHaveBeenCalled();
      const ack = screen.getByRole("button", {
        name: locale === "en" ? "Acknowledge this result" : "确认接收此结果",
      });
      await user.click(ack);
      await user.click(ack);
      expect(consume).toHaveBeenCalledTimes(1);
      expect(consume.mock.calls[0].slice(0, 2)).toEqual([
        { ...selection, attempt_id: "ATT-456" },
        "d".repeat(64),
      ]);
      expect(ack.hasAttribute("disabled")).toBe(true);
    },
  );
  it("does not show a delayed result after selection changes", async () => {
    let resolve!: (v: unknown) => void;
    const read = vi.fn<NonNullable<DirectNativeResultPanelProps["read"]>>(
      () => new Promise((r) => (resolve = r)),
    );
    const page = render(
      <DirectNativeResultPanel
        selection={selection}
        read={read}
        held={false}
        onConsume={vi.fn()}
      />,
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Read current result" }),
    );
    page.rerender(
      <DirectNativeResultPanel
        selection={{ ...selection, job_id: "JOB-other" }}
        read={read}
        held={false}
        onConsume={vi.fn()}
      />,
    );
    resolve(result());
    await waitFor(() =>
      expect(screen.queryByText("Retained analysis")).toBeNull(),
    );
    expect(read.mock.calls[0][1].aborted).toBe(true);
  });
  it("does not render unavailable result as unconsumed or expose raw transport errors", async () => {
    const read = vi.fn().mockRejectedValue(new Error("PRIVATE_ERROR_SENTINEL"));
    render(
      <DirectNativeResultPanel
        selection={selection}
        read={read}
        held={true}
        recovery={<button>Check status</button>}
        onConsume={vi.fn()}
      />,
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Read current result" }),
    );
    expect(await screen.findByText(/The result is unavailable/)).toBeTruthy();
    expect(screen.queryByText("PRIVATE_ERROR_SENTINEL")).toBeNull();
    expect(
      screen.queryByRole("button", { name: "Acknowledge this result" }),
    ).toBeNull();
    expect(screen.getByRole("button", { name: "Check status" })).toBeTruthy();
  });
});
