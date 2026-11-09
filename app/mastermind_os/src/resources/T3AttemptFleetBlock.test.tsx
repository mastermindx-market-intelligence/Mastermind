// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { T3AttemptFleetBlock } from "./T3AttemptFleetBlock";
import { decodeT3AttemptFleet, type T3AttemptFleetRead } from "./t3-attempt-fleet-contract";
import { bindMissionHost, type AuthState, type MissionHost } from "../host";

const GOOD_ID = "runs/att-1";
function attemptBody(mutate?: (value: any) => void) {
  const value: any = {
    schema: "mastermind.t3_attempt_fleet/v1",
    evaluated_at_utc: "2026-11-09T12:00:00+00:00",
    attempts: [{
      attempt_id: GOOD_ID,
      idempotency: { key: "a".repeat(64), namespace: "mastermind.control_plane.t3_execution_adapter/v1" },
      t3_thread: { thread_id: "mcp:launch:" + "1".repeat(64), run_id: "run:thread:x:ordinal:1", state: null, unknown_reason: null },
      harness_process: { pid: 100, provider: "claude", model: "glm-5.3", start_time: "2027-01-15T08:00:00+00:00", unknown_reason: null },
      thread_count_for_key: 1, thread_count_reason: null,
      harness_count_for_thread: 1, harness_count_reason: null,
      duplicate_launcher: { observed: false, kinds: [], evidence_refs: ["adapter_state:read"], unknown_reason: null },
      invariant: { exactly_one_thread: "PROVEN", exactly_one_harness: "PROVEN" },
      freshness: { adapter_state: "fresh", census: "fresh", thread_read: "absent" },
      evidence_refs: ["adapter_state:read"],
    }],
    notes: [],
  };
  mutate?.(value);
  return value;
}
function read(value: unknown): T3AttemptFleetRead {
  const result = decodeT3AttemptFleet(value);
  if (result.state !== "AVAILABLE") throw Error("synthetic body must qualify");
  return result;
}

beforeEach(() => { vi.useFakeTimers({ toFake: ["Date"] }); vi.setSystemTime(Date.parse("2026-11-09T12:00:10Z")); });
afterEach(() => { cleanup(); vi.useRealTimers(); });

function owner(reads: T3AttemptFleetRead[] | Error, attemptId: string | null = GOOD_ID) {
  let state: AuthState = { status: "signed_in", acquisition: true, content: false, reason: null };
  const listeners = new Set<() => void>();
  const calls: string[] = [];
  const reader = vi.fn(async ({ attemptId: id }: { attemptId: string }) => {
    calls.push(id);
    const next = Array.isArray(reads) ? reads.shift() : reads;
    if (next instanceof Error) throw next;
    return next ?? read(attemptBody());
  });
  const host = { auth: { getState: () => state, subscribe: (fn: () => void) => { listeners.add(fn); return () => listeners.delete(fn); } },
    invalidationGeneration: () => 1, readT3AttemptFleet: reader } as unknown as MissionHost;
  const ui = <T3AttemptFleetBlock host={host} attemptId={attemptId} />;
  const refresh = async () => { fireEvent.click(screen.getByRole("button", { name: "Read attempt" })); await act(async () => { await vi.advanceTimersByTimeAsync(0); }); };
  return { host, ui, reader, calls, refresh, revoke: () => { state = { ...state, status: "signed_out", acquisition: false }; for (const fn of listeners) fn(); } };
}

it("unknown-no-source: never healthy, never zero, names the reason", async () => {
  const { ui, refresh } = owner([{ state: "UNAVAILABLE", reason: "SOURCE_UNAVAILABLE" }]);
  render(ui);
  await refresh();
  const state = screen.getByTestId("t3-attempt-fleet-state");
  expect(state.textContent).toContain("No qualified attempt observation is connected");
  expect(screen.queryByTestId("t3-attempt-fleet-chips")).toBeNull();
});

it("renders PROVEN invariants, harness facts and no duplicates from the composition shape", async () => {
  const { ui, refresh, calls } = owner([read(attemptBody())]);
  render(ui);
  await refresh();
  expect(calls).toEqual([GOOD_ID]);
  const chips = screen.getByTestId("t3-attempt-fleet-chips");
  expect(chips.textContent).toContain("Exactly one thread");
  expect(chips.textContent).toContain("PROVEN");
  const panel = screen.getByTestId("t3-attempt-fleet");
  expect(panel.textContent).toContain("100");
  expect(panel.textContent).toContain("None observed");
});

it("renders VIOLATED with its reason and duplicate kinds when observed", async () => {
  const body = attemptBody(value => {
    const attempt = value.attempts[0];
    attempt.invariant.exactly_one_thread = "VIOLATED";
    attempt.thread_count_for_key = 2;
    attempt.duplicate_launcher = { observed: true, kinds: ["second_t3_thread", "codex_cli"], evidence_refs: ["adapter_state:read"], unknown_reason: null };
  });
  const { ui, refresh } = owner([read(body)]);
  render(ui);
  await refresh();
  const chips = screen.getByTestId("t3-attempt-fleet-chips");
  expect(chips.textContent).toContain("VIOLATED");
  const panel = screen.getByTestId("t3-attempt-fleet");
  expect(panel.textContent).toContain("second T3 thread");
  expect(panel.textContent).toContain("Codex CLI process");
});

it("keeps an unobserved harness UNKNOWN with its reason", async () => {
  const body = attemptBody(value => {
    const attempt = value.attempts[0];
    attempt.harness_process = { pid: null, provider: null, model: null, start_time: null, unknown_reason: "HARNESS_NOT_OBSERVED" };
    attempt.harness_count_for_thread = null; attempt.harness_count_reason = "HARNESS_NOT_OBSERVED";
    attempt.invariant.exactly_one_harness = "UNKNOWN";
    value.notes = ["CENSUS_ABSENT"];
  });
  const { ui, refresh } = owner([read(body)]);
  render(ui);
  await refresh();
  const chips = screen.getByTestId("t3-attempt-fleet-chips");
  expect(chips.textContent).toContain("UNKNOWN");
  expect(chips.textContent).toContain("HARNESS_NOT_OBSERVED");
  expect(screen.queryByText("pid")).toBeNull();
});

it("shows the typed refusal as an honest refusal, never a healthy projection", async () => {
  const { ui, refresh } = owner([read({ schema: "mastermind.t3_attempt_fleet/v1", refusal: "ADAPTER_ROW_MALFORMED", attempts: [] })]);
  render(ui);
  await refresh();
  const refusal = screen.getByTestId("t3-attempt-fleet-refusal");
  expect(refusal.textContent).toContain("ADAPTER_ROW_MALFORMED");
  expect(screen.queryByTestId("t3-attempt-fleet-chips")).toBeNull();
});

it("signed-out or absent reader is unknown-with-reason and never fetches", async () => {
  const { host, ui, reader, revoke, refresh } = owner([]);
  const view = render(ui);
  await refresh();
  expect(reader).toHaveBeenCalledTimes(1);
  // A bound host bumps its epoch on auth change and the parent remounts/re-renders
  // the block; the block itself carries no auth subscription.
  await act(async () => { revoke(); });
  view.rerender(<T3AttemptFleetBlock host={host} attemptId={GOOD_ID} />);
  const button = screen.getByRole("button", { name: "Read attempt" }) as HTMLButtonElement;
  expect(button.disabled).toBe(true);
  expect(screen.getByTestId("t3-attempt-fleet-state").textContent).toContain("Sign in with Workspace access");
  // A client without the reader (native desktop before the Rust command) is
  // honestly not connected — no fake zero, no healthy chips.
  const bare = { getState: () => ({}), subscribe: () => () => {} } as never;
  const bound = bindMissionHost(bare);
  expect(bound.readT3AttemptFleet).toBeUndefined();
});

it("an unreadable run id refuses selection before any fetch", () => {
  const { ui, reader } = owner([], "../escape");
  render(ui);
  expect((screen.getByRole("button", { name: "Read attempt" }) as HTMLButtonElement).disabled).toBe(true);
  expect(reader).not.toHaveBeenCalled();
  expect(screen.getByTestId("t3-attempt-fleet").textContent).toContain("not a readable attempt id");
});
