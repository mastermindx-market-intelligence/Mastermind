// @vitest-environment jsdom
import React from "react";
import { webcrypto } from "node:crypto";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, act } from "@testing-library/react";
import { ExecutionReturnRead } from "./ExecutionReturnRead";
import type { ResultSelection } from "./result";
import fixture from "../../../integrations/mmos/fixtures/execution_return_read_v1/retained.json";

beforeAll(() => { Object.defineProperty(globalThis, "crypto", { value: webcrypto, configurable: true }); });
afterEach(cleanup);
const wire = fixture.selection;
const selection = { workRef: wire.work_ref, rootJobId: wire.root_job_id, jobId: wire.job_id,
  attemptId: wire.attempt_id, resultEnvelopeDigest: wire.result_envelope_digest };
const props = { selection, authGeneration: 1, hostGeneration: 1, locale: "en" as const };

describe("retained original return consumer", () => {
  it("reads the exact selection once and keeps delivery separate from acceptance", async () => {
    const read = vi.fn(async (_request: ResultSelection & { signal: AbortSignal }) => structuredClone(fixture));
    const view = render(<ExecutionReturnRead {...props} read={read} />);
    await screen.findByText("Selected canonical result");
    expect(read).toHaveBeenCalledTimes(1);
    expect(read.mock.calls[0][0]).toEqual({ ...selection, signal: expect.any(AbortSignal) });
    expect(screen.getByText("Not accepted")).toBeTruthy();
    view.rerender(<ExecutionReturnRead {...props} read={read} locale="zh-CN" />);
    expect(read).toHaveBeenCalledTimes(1);
  });

  it("clears material immediately when authority changes and ignores the late prior read", async () => {
    const releases: ((value: unknown) => void)[] = [];
    const signals: AbortSignal[] = [];
    const read = vi.fn((request: { signal: AbortSignal }) => {
      signals.push(request.signal);
      return new Promise(resolve => releases.push(resolve));
    });
    const view = render(<ExecutionReturnRead {...props} read={read} />);
    view.rerender(<ExecutionReturnRead {...props} authGeneration={2} read={read} />);
    expect(signals[0].aborted).toBe(true);
    await act(async () => { releases[0](structuredClone(fixture)); await Promise.resolve(); });
    expect(screen.queryByText("Selected canonical result")).toBeNull();
    expect(screen.getByText("Reading the original return receipt…")).toBeTruthy();
    await act(async () => { releases[1](structuredClone(fixture)); });
    await screen.findByText("Selected canonical result");
  });

  it("rejects a foreign receipt without showing successful delivery", async () => {
    const changed = structuredClone(fixture);
    changed.delivery_receipt.return_digest = "f".repeat(64);
    render(<ExecutionReturnRead {...props} read={async () => changed} />);
    await screen.findByText("The original return receipt is unavailable.");
    expect(screen.queryByText("Delivered")).toBeNull();
    expect(screen.queryByText("Selected canonical result")).toBeNull();
  });
});
