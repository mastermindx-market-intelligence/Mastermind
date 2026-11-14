// @vitest-environment jsdom
/** HC07 workbench tests. Attempt facts come from a parser-qualified fleet
 *  document (decodeT3AttemptFleet — the contract's own decoder, never
 *  hand-rolled trust); execution returns and receipts come from the committed
 *  Python-produced fixtures parsed through the contract's fail-closed
 *  parsers. Every missing source must render its honest state. */
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import React from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { CodeWorkspace } from "./CodeWorkspace";
import { CodeWorkbench } from "./CodeWorkbench";
import type { T3ProjectionRead, T3ThreadProjection } from "./t3-thread-projection";
import {
  decodeT3AttemptFleet,
  type T3AttemptFleetRead,
} from "../resources/t3-attempt-fleet-contract";
import type { ActivityRead, ActivitySelection } from "../planning/retained-activity";
import {
  parseExecutionReturn,
  parseExecutionReturnDelivery,
  type ExecutionReturnDeliveryReceipt,
  type ExecutionReturnRecord,
} from "../hermes-native/execution-return-contract";

afterEach(cleanup);

const here = path.dirname(fileURLToPath(import.meta.url));
const fixtureDir = path.resolve(here, "../../../../integrations/mmos/fixtures/execution_return_v1");

const ATTEMPT_ID = "runs/att-42";
const THREAD_ID = "th_atlas_7";

/** Parser-minted fleet document: built as a body, then qualified by the
 *  contract decoder so the fixture can never drift from the wire grammar. */
function fleetAttempt(mutate?: (value: any) => void): T3AttemptFleetRead {
  const value: any = {
    schema: "mastermind.t3_attempt_fleet/v1",
    evaluated_at_utc: "2026-11-09T12:00:00+00:00",
    attempts: [{
      attempt_id: ATTEMPT_ID,
      idempotency: { key: "t3-launch-abc123", namespace: "mastermind.control_plane.t3_execution_adapter/v1" },
      t3_thread: { thread_id: THREAD_ID, run_id: "run-77", state: "RUNNING", unknown_reason: null },
      harness_process: { pid: 4242, provider: "claude", model: "glm-5.3", start_time: "2026-11-09T08:00:00+00:00", unknown_reason: null },
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
  const read = decodeT3AttemptFleet(value);
  if (read.state !== "AVAILABLE") throw new Error("synthetic fleet body must qualify");
  return read;
}

function fleetRefusal(): T3AttemptFleetRead {
  const read = decodeT3AttemptFleet({ schema: "mastermind.t3_attempt_fleet/v1", refusal: "ADAPTER_ROW_MALFORMED", attempts: [] });
  if (read.state !== "AVAILABLE") throw new Error("refusal body must qualify");
  return read;
}

function thread(extra: Partial<T3ThreadProjection> = {}): T3ThreadProjection {
  return {
    schema: "mastermind.t3_thread_projection.v1", threadId: THREAD_ID, environment: "m2studio",
    title: "Roster join fix", runState: "running",
    lastActivity: "2026-11-09T00:00:00Z", prLink: "https://github.com/acme/repo/pull/12",
    repository: "acme/repo", companyManaged: true,
    ...extra,
  };
}
const projection = (threads: T3ThreadProjection[]): T3ProjectionRead => ({
  kind: "AVAILABLE", list: { schema: "mastermind.t3_thread_projection_list.v1", threads },
});

const SELECTION: ActivitySelection = {
  work_ref: "WS:MMOS-L2", root_job_id: "JOB-100", job_id: "JOB-101",
  attempt_id: "ATT-" + "a".repeat(32),
};

function workbenchHost({ fleet, activity }: { fleet?: T3AttemptFleetRead; activity?: ActivityRead }) {
  return {
    auth: { getState: () => ({ status: "signed_in", acquisition: true, content: false, reason: null }) },
    invalidationGeneration: () => 3,
    readT3AttemptFleet: vi.fn(async () => fleet ?? fleetAttempt()),
    ...(activity !== undefined
      ? { readRetainedActivity: vi.fn(async () => activity) }
      : {}),
  };
}

describe("CodeWorkbench (HC07) — attempt facts", () => {
  it("renders the attempt's REAL thread facts from the parser-minted fleet document", async () => {
    const host = workbenchHost({});
    render(<CodeWorkbench host={host} attemptId={ATTEMPT_ID} projection={projection([thread()])} />);
    await waitFor(() => expect(screen.getByTestId("mm-code-attempt-facts").textContent).toContain("PROVEN"));
    expect(host.readT3AttemptFleet).toHaveBeenCalledWith(expect.objectContaining({ attemptId: ATTEMPT_ID }));
    const facts = screen.getByTestId("mm-code-attempt-facts");
    expect(facts.textContent).toContain(THREAD_ID);
    expect(facts.textContent).toContain("run-77");
    expect(facts.textContent).toContain("RUNNING");
    expect(facts.textContent).toContain("4242"); // harness pid
    expect(facts.textContent).toContain("claude · glm-5.3");
    expect(facts.textContent).toContain("None observed"); // duplicate launchers
    expect(screen.queryByTestId("mm-code-attempt-refusal")).toBeNull();
  });

  it("renders a typed refusal with the code and NO attempt facts", async () => {
    render(<CodeWorkbench host={workbenchHost({ fleet: fleetRefusal() })} attemptId={ATTEMPT_ID} projection={projection([thread()])} />);
    await waitFor(() => expect(screen.getByTestId("mm-code-attempt-refusal")).toBeTruthy());
    expect(screen.getByTestId("mm-code-attempt-refusal").textContent).toContain("ADAPTER_ROW_MALFORMED");
    expect(screen.queryByTestId("mm-code-attempt-facts")).toBeNull();
    expect(screen.queryByText("PROVEN")).toBeNull();
    expect(screen.queryByText(THREAD_ID)).toBeNull();
  });

  it("renders an unavailable read with its typed reason, never healthy facts", async () => {
    render(<CodeWorkbench host={workbenchHost({ fleet: { state: "UNAVAILABLE", reason: "SOURCE_CHANGED" } })} attemptId={ATTEMPT_ID} />);
    await waitFor(() => expect(screen.getByTestId("mm-code-attempt-facts").textContent).toContain("SOURCE_CHANGED"));
    expect(screen.getByTestId("mm-code-attempt-facts").textContent).toContain("Attempt observation unavailable");
  });

  it("refuses an unreadable attempt id before any fetch", () => {
    const host = workbenchHost({});
    render(<CodeWorkbench host={host} attemptId="../escape" />);
    expect(screen.getByTestId("mm-code-attempt-facts").textContent)
      .toContain("This run id is not a readable attempt id; nothing was fetched.");
    expect(host.readT3AttemptFleet).not.toHaveBeenCalled();
  });
});

describe("CodeWorkbench (HC07) — deep link", () => {
  it("links the exact native thread using the thread id from the attempt read and the projection's environment", async () => {
    render(<CodeWorkbench host={workbenchHost({})} attemptId={ATTEMPT_ID}
      projection={projection([thread({ environment: "chatgpt2" }), thread({ threadId: "other-1", environment: "chatgpt2" })])} />);
    await waitFor(() => screen.getByRole("link", { name: "Open coding session →" }));
    const link = screen.getByRole("link", { name: "Open coding session →" });
    expect(link.getAttribute("href")).toBe("https://app.t3.codes/threads/chatgpt2/th_atlas_7");
    expect(link.getAttribute("target")).toBe("_blank");
  });

  it("hides the deep link when the environment is not known — honest note instead", async () => {
    // The attempt thread is not projected and the projection spans two
    // environments: an exact match resolves it, ambiguity must not.
    render(<CodeWorkbench host={workbenchHost({})} attemptId={ATTEMPT_ID}
      projection={projection([
        thread({ threadId: "a-env1", environment: "m2studio" }),
        thread({ threadId: "b-env2", environment: "chatgpt1" }),
      ])} />);
    await waitFor(() => expect(screen.getByTestId("mm-code-attempt-facts").textContent).toContain("PROVEN"));
    expect(screen.queryByRole("link", { name: "Open coding session →" })).toBeNull();
    expect(screen.getByText(/environment for this thread is not known/i)).toBeTruthy();
  });
});

describe("CodeWorkbench (HC07) — work panels from execution_return/v1", () => {
  let record: ExecutionReturnRecord;
  let receipt: ExecutionReturnDeliveryReceipt;
  beforeAll(async () => {
    record = await parseExecutionReturn(JSON.parse(readFileSync(path.join(fixtureDir, "sample_record.json"), "utf8")));
    receipt = await parseExecutionReturnDelivery(JSON.parse(readFileSync(path.join(fixtureDir, "sample_receipt.json"), "utf8")));
  });

  it("no record → honest missing-source copy naming mastermind.execution_return/v1", async () => {
    render(<CodeWorkbench host={workbenchHost({})} attemptId={ATTEMPT_ID} executionReturn={null} />);
    await waitFor(() => expect(screen.getByTestId("mm-code-changes-missing")).toBeTruthy());
    expect(screen.getByTestId("mm-code-changes").textContent).toContain("Working changes are not projected yet");
    expect(screen.getByTestId("mm-code-changes").textContent).toContain("mastermind.execution_return/v1");
    expect(screen.getByTestId("mm-code-terminal").textContent).toContain("Terminal output is not projected yet");
    expect(screen.getByTestId("mm-code-return-footer").textContent).toContain("Return pending · Engineering receives the result here.");
    expect(screen.getByTestId("mm-code-return-footer").textContent).toContain("Delivered ≠ accepted");
  });

  it("record present → changes, tests and PR rows render real field values", async () => {
    render(<CodeWorkbench host={workbenchHost({})} attemptId={ATTEMPT_ID} executionReturn={record} />);
    const changes = screen.getByTestId("mm-code-changes");
    expect(changes.textContent).toContain("t3/execution-return-path"); // github.branch
    expect(changes.textContent).toContain("control_plane/roster_join.py"); // artifact ref 1
    expect(changes.textContent).toContain("tests/test_roster_join.py"); // artifact ref 2
    const pr = screen.getByRole("link", { name: "https://github.com/Acme/Mastermind/pull/2338" });
    expect(pr.getAttribute("href")).toBe("https://github.com/Acme/Mastermind/pull/2338");
    expect(changes.textContent).toContain("Merged"); // merge_state
    expect(changes.textContent).toContain("Claimed, unproven"); // installation
    // No diff text in the record → honest diff state, prose never masquerades.
    expect(changes.textContent).toContain("Working changes are not projected yet");
    expect(screen.queryByText(/diff --git/)).toBeNull();
    // Terminal tab: the record's own check rows.
    const tabs = screen.getByRole("tablist");
    fireEvent.click(screen.getByRole("tab", { name: "Terminal" }));
    const terminal = screen.getByTestId("mm-code-terminal");
    expect(terminal.textContent).toContain("Green"); // checks_state
    expect(terminal.textContent).toContain("ci-union");
    expect(terminal.textContent).toContain("typecheck");
    expect(terminal.textContent).toContain("lint");
    expect(terminal.querySelector('[data-conclusion="skipped"]')).toBeTruthy();
    expect(tabs).toBeTruthy();
  });

  it("return footer: stage from the record, delivery from the receipt, never acceptance", async () => {
    render(<CodeWorkbench host={workbenchHost({})} attemptId={ATTEMPT_ID} executionReturn={record} deliveryReceipt={receipt} />);
    const footer = screen.getByTestId("mm-code-return-footer");
    expect(footer.textContent).toContain("Stage: Merged — install claim unproven"); // stage installed_unknown
    expect(footer.textContent).toContain("Returned to sess-3f9c2"); // delivered receipt
    expect(footer.textContent).toContain("Transport ref adm-42");
    expect(footer.textContent).toContain("Delivered ≠ accepted");
    // Delivery state is structural, never an acceptance claim.
    expect(footer.querySelector(".mm-code-return-line[data-return]")!.getAttribute("data-return")).toBe("delivered");
  });

  it("return footer: a refused receipt shows its refusal code", async () => {
    const refused = await parseExecutionReturnDelivery({ ...receipt, state: "refused", transport_ref: null, refusal_code: "SESSION_BUSY" });
    render(<CodeWorkbench host={workbenchHost({})} attemptId={ATTEMPT_ID} executionReturn={record} deliveryReceipt={refused} />);
    expect(screen.getByTestId("mm-code-return-footer").textContent).toContain("Refused · SESSION_BUSY");
  });

  it("record without receipt stays honestly return-pending", async () => {
    render(<CodeWorkbench host={workbenchHost({})} attemptId={ATTEMPT_ID} executionReturn={record} deliveryReceipt={null} />);
    expect(screen.getByTestId("mm-code-return-footer").textContent)
      .toContain("No delivery receipt yet — return pending.");
  });
});

describe("CodeWorkbench (HC07) — activity trail", () => {
  it("no selection ids → honest note, never a fake stream", async () => {
    render(<CodeWorkbench host={workbenchHost({})} attemptId={ATTEMPT_ID} activitySelection={null} />);
    await waitFor(() => expect(screen.getByTestId("mm-code-attempt-facts").textContent).toContain("PROVEN"));
    expect(screen.getByTestId("mm-code-activity").textContent)
      .toContain("Activity selection (work, job, attempt) is not projected for this thread.");
  });

  it("read unavailable → activity is not retained for this attempt yet", async () => {
    render(<CodeWorkbench host={workbenchHost({ activity: {
      availability: "UNAVAILABLE", selection: SELECTION, sourceState: "UNKNOWN",
      coverage: null, sourceTruncated: null, omittedInSample: null, rows: [],
      reasons: ["SOURCE_UNAVAILABLE"],
    } })} attemptId={ATTEMPT_ID} activitySelection={SELECTION} />);
    await waitFor(() => expect(screen.getByTestId("mm-code-activity").textContent)
      .toContain("Activity is not retained for this attempt yet."));
  });

  it("retained rows render with their timestamps", async () => {
    render(<CodeWorkbench host={workbenchHost({ activity: {
      availability: "AVAILABLE", selection: SELECTION, sourceState: "SAME",
      coverage: "RETAINED", sourceTruncated: false, omittedInSample: 0,
      rows: [
        { candidate_event_id: 11, turn_id: "turn-abc", ordinal_in_candidate: 0, category: "TURN_ACTIVITY", candidate_recorded_at: "2026-11-09T10:00:00Z" },
        { candidate_event_id: 12, turn_id: "turn-abc", ordinal_in_candidate: 1, category: "TOOL_ACTIVITY", candidate_recorded_at: "2026-11-09T10:01:00Z" },
      ],
    } })} attemptId={ATTEMPT_ID} activitySelection={SELECTION} />);
    const trail = screen.getByTestId("mm-code-activity");
    await waitFor(() => expect(trail.textContent).toContain("Turn activity"));
    expect(trail.textContent).toContain("Tool activity");
    expect(trail.textContent).toContain("2026-11-09T10:00:00Z");
    expect(trail.textContent).toContain("2026-11-09T10:01:00Z");
    expect(trail.textContent).toContain("not a live tool stream");
  });
});

describe("CodeWorkbench (HC07) — rail, tabs, composer, transport limits", () => {
  it("rail groups the attempt thread, projected WORKING threads and a collapsed SETTLED count", async () => {
    render(<CodeWorkbench host={workbenchHost({})} attemptId={ATTEMPT_ID}
      projection={projection([
        thread(),
        thread({ threadId: "idle-9", environment: "m2studio", title: null, runState: "idle", lastActivity: null, prLink: null, repository: null, companyManaged: false }),
      ])} />);
    await waitFor(() => expect(screen.getByTestId("mm-code-attempt-facts").textContent).toContain("PROVEN"));
    const rail = screen.getByTestId("mm-code-rail");
    expect(rail.textContent).toContain("THIS ATTEMPT");
    expect(rail.textContent).toContain("Roster join fix");
    expect(rail.textContent).toContain("WORKING");
    expect(rail.textContent).toContain("SETTLED · 1");
    expect(rail.textContent).toContain("m2studio");
    // New-thread preview is disabled with an honest reason — no launch authority.
    const newThread = screen.getByRole("button", { name: "＋ New thread" }) as HTMLButtonElement;
    expect(newThread.disabled).toBe(true);
    expect(newThread.title).toContain("no launch authority");
  });

  it("tabs are arrow-key navigable and panels follow selection", async () => {
    render(<CodeWorkbench host={workbenchHost({})} attemptId={ATTEMPT_ID} />);
    const changes = screen.getByRole("tab", { name: "Changes" });
    const browser = screen.getByRole("tab", { name: "Browser" });
    const terminal = screen.getByRole("tab", { name: "Terminal" });
    expect(changes.getAttribute("aria-selected")).toBe("true");
    expect(browser.getAttribute("tabIndex")).toBe("-1");
    const tablist = screen.getByRole("tablist");
    fireEvent.keyDown(tablist, { key: "ArrowRight" });
    expect(browser.getAttribute("aria-selected")).toBe("true");
    expect(document.activeElement).toBe(browser);
    // The visible tabpanel follows: the browser panel is honestly not connected.
    expect(screen.getByRole("tabpanel").textContent).toContain("Browser is not connected");
    fireEvent.keyDown(tablist, { key: "ArrowLeft" });
    expect(changes.getAttribute("aria-selected")).toBe("true");
    fireEvent.keyDown(tablist, { key: "End" });
    expect(terminal.getAttribute("aria-selected")).toBe("true");
  });

  it("composer is disabled with the queue note — no send/launch/interrupt anywhere", async () => {
    render(<CodeWorkbench host={workbenchHost({})} attemptId={ATTEMPT_ID} />);
    const composer = screen.getByTestId("mm-code-composer");
    const box = composer.querySelector("textarea") as HTMLTextAreaElement;
    expect(box.disabled).toBe(true);
    expect(composer.textContent).toContain("New direction queues for the next turn. Current work continues.");
    expect(box.placeholder).toContain("Not connected"); // honest not-connected state
    expect(box.placeholder).toContain("never sends to or interrupts");
    const queue = screen.getByRole("button", { name: "Queue direction" }) as HTMLButtonElement;
    expect(queue.disabled).toBe(true);
  });

  it("renders the honest zh-CN workbench copy", async () => {
    render(<CodeWorkbench host={workbenchHost({})} attemptId={ATTEMPT_ID} projection={projection([thread()])} locale="zh-CN" />);
    await waitFor(() => expect(screen.getByRole("link", { name: "打开编码会话 →" })).toBeTruthy());
    expect(screen.getByRole("link", { name: "打开编码会话 →" }).getAttribute("href"))
      .toBe("https://app.t3.codes/threads/m2studio/th_atlas_7");
    const facts = screen.getByTestId("mm-code-attempt-facts");
    expect(facts.textContent).toContain("唯一线程");
    expect(facts.textContent).toContain("已证实");
    expect(screen.getByTestId("mm-code-return-footer").textContent).toContain("返回待定 · 工程团队在此接收结果。");
  });
});

describe("CodeWorkspace switch", () => {
  it("routes a set attempt id to the workbench; null keeps the projected list", async () => {
    const host = workbenchHost({});
    render(<CodeWorkspace host={host} attemptId={ATTEMPT_ID} projection={projection([thread()])} />);
    await waitFor(() => expect(screen.getByTestId("mm-code-workbench")).toBeTruthy());
    expect(screen.queryByRole("list", { name: "T3 coding threads" })).toBeNull();
  });

  it("an invalid attempt id through the workspace switch fetches nothing", () => {
    const host = workbenchHost({});
    render(<CodeWorkspace host={host} attemptId="bad id" />);
    expect(screen.getByTestId("mm-code-attempt-facts").textContent)
      .toContain("not a readable attempt id");
    expect(host.readT3AttemptFleet).not.toHaveBeenCalled();
  });
});
