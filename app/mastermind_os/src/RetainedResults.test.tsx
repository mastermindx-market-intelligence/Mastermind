// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { RetainedResults } from "./RetainedResults";
import type { ResultEnvelopeDigestShape, ResultSelection } from "./result";

afterEach(cleanup);

const HEX = (ch: string) => ch.repeat(64);
const LIST_RUNTIME = {
  schema: "mastermind.runtime_read_observation.v1",
  state: "SAME",
  source_identity: "8f2ba172e5e975d5ab0f0965a4df9b53",
  before: 2,
  after: 2,
};
const CONTROL_ROOM = {
  instance_before: "control-room-instance",
  instance_after: "control-room-instance",
  publication_before: 11,
  publication_after: 11,
  document_digest: HEX("a"),
  source_validity_digest: HEX("b"),
  cache_currentness_digest: HEX("c"),
};

// Existing-owner index shape with the fixture's first rows. The first row is
// the click target used by the exact-result tests below.
const INDEX = {
  schema: "mastermind.fabric_result_reference_index.v1",
  root_job_id: "JOB-001",
  snapshot_digest:
    "b025afa54ba7cb8ce68b287edbcd48023982a147252531b2c476b3de1937efeb",
  generation: LIST_RUNTIME,
  availability: "AVAILABLE",
  refs: [
    {
      root_job_id: "JOB-001",
      job_id: "JOB-002",
      attempt_id: "ATT-f762f805f4ab4567ab244aba0d106721",
      result_envelope_digest:
        "52780b9d310fcfe2a95fc3f7f4a21426604eb2ce7fdbef6bc69414bdec85832a",
      orchestration_role: "plan",
      validation: "UNVALIDATED",
    },
    {
      root_job_id: "JOB-001",
      job_id: "JOB-003",
      attempt_id: "ATT-0f7521645e5b462da6c3890da7575125",
      result_envelope_digest:
        "e3f365cc856fd9b205c16485cd148dd795baf794147f370530c384f3a66d3bbb",
      orchestration_role: "work",
      validation: "UNVALIDATED",
    },
    {
      root_job_id: "JOB-001",
      job_id: "JOB-004",
      attempt_id: "ATT-c0ed7b3dea244d18a28e6677f04aefa0",
      result_envelope_digest:
        "867e1551abfcf92b1718b1fdd06ac37eed9f5d2783a8dc2332ec7d4936f9e1d1",
      orchestration_role: "review",
      validation: "UNVALIDATED",
    },
  ],
  absent_job_ids: ["JOB-001"],
  omitted_job_ids: [],
  truncated: false,
};

const availableBody = (workRef = "WS:ONE", indexOverrides: Record<string, unknown> = {}) => ({
  schema: "mastermind.workspace_result_references.v1",
  selection: { work_ref: workRef, root_job_id: "JOB-001" },
  availability: "AVAILABLE",
  reason_codes: [],
  index: { ...INDEX, ...indexOverrides },
  source_observation: {
    schema: "mastermind.workspace_source_observation.v1",
    state: "SAME",
    selection: { work_ref: workRef, root_job_id: "JOB-001" },
    control_room: CONTROL_ROOM,
    runtime: LIST_RUNTIME,
  },
  catalogue: { generated_at: "2026-10-31T15:45:00Z", freshness: "CURRENT" },
});

const unavailableBody = (reason: string) => ({
  schema: "mastermind.workspace_result_references.v1",
  selection: { work_ref: "WS:ONE", root_job_id: "JOB-001" },
  availability: "UNAVAILABLE",
  reason_codes: [reason],
  index: null,
  source_observation: {
    schema: "mastermind.workspace_source_observation.v1",
    state: reason === "SOURCE_CHANGED" ? "CONFLICT" : "UNKNOWN",
    selection: { work_ref: "WS:ONE", root_job_id: "JOB-001" },
    control_room: null,
    runtime: null,
  },
  catalogue: { generated_at: null, freshness: "UNKNOWN" },
});

// Minimal valid exact-result body. Its runtime receipt (aaaa…, 7) differs
// from the list receipt (8f2b…, 2): a list read never binds a click.
const RESULT_RUNTIME = {
  schema: "mastermind.runtime_read_observation.v1",
  state: "SAME",
  source_identity: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  before: 7,
  after: 7,
};

const resultBody = (exact: ResultSelection) => ({
  schema: "mastermind.workspace_role_result.v1",
  selection: {
    work_ref: exact.workRef,
    root_job_id: exact.rootJobId,
    job_id: exact.jobId,
    attempt_id: exact.attemptId,
    result_envelope_digest: exact.resultEnvelopeDigest,
  },
  availability: "AVAILABLE",
  reason_codes: [],
  source_observation: {
    schema: "mastermind.workspace_result_observation.v1",
    state: "SAME",
    selection: {
      work_ref: exact.workRef,
      root_job_id: exact.rootJobId,
      job_id: exact.jobId,
      attempt_id: exact.attemptId,
      result_envelope_digest: exact.resultEnvelopeDigest,
    },
    control_room: {
      instance_before: "control-room-instance",
      instance_after: "control-room-instance",
      publication_before: 3,
      publication_after: 3,
      document_digest: HEX("d"),
      source_validity_digest: HEX("e"),
      cache_currentness_digest: HEX("f"),
    },
    runtime: RESULT_RUNTIME,
  },
  result: {
    schema: "mastermind.fabric_role_result_view.v1",
    selection: {
      root_job_id: exact.rootJobId,
      job_id: exact.jobId,
      attempt_id: exact.attemptId,
      result_envelope_digest: exact.resultEnvelopeDigest,
    },
    role: "work",
    execution_status: "COMPLETED",
    acceptance: "NOT_PROJECTED",
    role_result_digest: HEX("1"),
    generation: RESULT_RUNTIME,
    availability: "AVAILABLE",
    content_complete: true,
    review: null,
    counts: { findings: null, next_actions: 1 },
    content: {
      role_result: { outcome: "retained" },
      summary: "Retained work result.",
      next_actions: ["Inspect the retained result."],
    },
    omitted: [],
  },
});

const deferred = () => {
  let resolve!: (value: unknown) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<unknown>((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
};

const flush = async () => {
  for (let n = 0; n < 12; n++) await Promise.resolve();
};

const show = async () => {
  fireEvent.click(screen.getByRole("button", { name: "Show retained results" }));
  await screen.findByRole("button", { name: /JOB-002/ });
};

function setup() {
  const signals: AbortSignal[] = [];
  const readReferences = vi.fn(async (request: {
    workRef: string;
    rootJobId: string;
    signal: AbortSignal;
  }): Promise<unknown> => {
    signals.push(request.signal);
    return availableBody(request.workRef);
  });
  const readResult = vi.fn(
    async (request: ResultSelection & { signal: AbortSignal }): Promise<unknown> =>
      resultBody(request),
  );
  const renderResult = vi.fn(
    (selection: ResultSelection, decoded: ResultEnvelopeDigestShape) => (
      <div>EXACT_RESULT_CARD:{decoded.result?.role}:{selection.jobId}</div>
    ),
  );
  const props = {
    selection: { workRef: "WS:ONE", rootJobId: "JOB-001" },
    authGeneration: 1 as string | number,
    hostGeneration: 1 as string | number,
    locale: "en" as "en" | "zh-CN",
    missionState: "CURRENT",
    readReferences,
    readResult,
    renderResult,
  };
  const view = render(<RetainedResults {...props} />);
  const rerender = (overrides: Partial<typeof props> = {}) =>
    view.rerender(<RetainedResults {...props} {...overrides} />);
  return { readReferences, readResult, renderResult, signals, view, rerender };
}

describe("explicit disclosure and list rendering", () => {
  it("reads the list only after explicit disclosure", async () => {
    const { readReferences } = setup();
    expect(readReferences).not.toHaveBeenCalled();
    await show();
    expect(readReferences).toHaveBeenCalledTimes(1);
    const request = readReferences.mock.calls[0][0];
    expect(request.workRef).toBe("WS:ONE");
    expect(request.rootJobId).toBe("JOB-001");
    expect(request.signal).toBeInstanceOf(AbortSignal);
    expect(screen.getByText(/Mission state: Current/)).toBeTruthy();
    expect(
      screen.getAllByText(/Retained as of 2026-10-31T15:45:00Z/).length,
    ).toBeGreaterThan(0);
    expect(screen.getAllByText(/Catalogue freshness: Within source age limit/).length).toBeGreaterThan(0);
  });

  it("refreshes only on the explicit refresh control and aborts the prior read", async () => {
    const { readReferences, signals, rerender } = setup();
    await show();
    fireEvent.click(screen.getByRole("button", { name: "Refresh retained results" }));
    await waitFor(() => expect(readReferences).toHaveBeenCalledTimes(2));
    expect(readReferences.mock.calls[0][0].signal.aborted).toBe(true);
    expect(signals[1].aborted).toBe(false);
    expect(screen.getByRole("button", { name: /JOB-002/ })).toBeTruthy();
  });

  it("never reads on mount, mission-state change or epoch change alone", async () => {
    const { readReferences, rerender } = setup();
    rerender({ missionState: "HISTORICAL" });
    rerender({ authGeneration: 2 });
    rerender({ hostGeneration: 3 });
    await flush();
    expect(readReferences).not.toHaveBeenCalled();
    expect(screen.queryByText(/JOB-002/)).toBeNull();
  });

  it("keeps reading on a historical mission", async () => {
    const { rerender } = setup();
    rerender({ missionState: "HISTORICAL" });
    await show();
    expect(screen.getByText(/Mission state: Historical/)).toBeTruthy();
    expect(screen.getByRole("button", { name: /JOB-004/ })).toBeTruthy();
  });

  it("renders localized copy", async () => {
    const { rerender } = setup();
    rerender({ locale: "zh-CN" });
    fireEvent.click(screen.getByRole("button", { name: "显示保留的结果" }));
    await screen.findByText(/JOB-002/);
    expect(screen.getByText(/任务状态: 当前/)).toBeTruthy();
  });
});

describe("unavailable, invalid, empty and partial lists", () => {
  it.each([
    ["SOURCE_UNAVAILABLE", "The result source is unavailable."],
    ["SOURCE_CHANGED", "The result source changed while reading."],
    ["OVER_BUDGET", "The retained list is over its display budget."],
    ["REFERENCE_INDEX_UNAVAILABLE", "The reference index is unavailable."],
  ])("shows the typed state for %s", async (reason, expected) => {
    const { readReferences } = setup();
    readReferences.mockResolvedValueOnce(unavailableBody(reason));
    fireEvent.click(screen.getByRole("button", { name: "Show retained results" }));
    await screen.findByText(expected);
    expect(screen.queryByText(/Open retained result/)).toBeNull();
  });

  it("shows an explicit invalid state and fabricates nothing", async () => {
    const { readReferences } = setup();
    readReferences.mockResolvedValueOnce({ hacked: true });
    fireEvent.click(screen.getByRole("button", { name: "Show retained results" }));
    await screen.findByText("The retained list response was invalid.");
    expect(screen.queryByText(/JOB-002/)).toBeNull();
    expect(screen.queryByText(/Open retained result/)).toBeNull();
  });

  it("shows an explicit read-failure state", async () => {
    const { readReferences } = setup();
    readReferences.mockRejectedValueOnce(new Error("READ_CANCELLED"));
    fireEvent.click(screen.getByRole("button", { name: "Show retained results" }));
    await screen.findByText("The retained list could not be read.");
    expect(screen.queryByText(/JOB-002/)).toBeNull();
  });

  it("renders an empty list without inventing rows", async () => {
    const { readReferences } = setup();
    readReferences.mockResolvedValueOnce(
      availableBody("WS:ONE", { refs: [], absent_job_ids: ["JOB-001", "JOB-002"] }),
    );
    fireEvent.click(screen.getByRole("button", { name: "Show retained results" }));
    await screen.findByText("No retained results are listed for this workspace.");
    expect(screen.queryByText(/Open retained result/)).toBeNull();
  });

  it("renders the source-noted partial and truncated orientation", async () => {
    const { readReferences } = setup();
    readReferences.mockResolvedValueOnce(
      availableBody("WS:ONE", { availability: "PARTIAL", truncated: true }),
    );
    fireEvent.click(screen.getByRole("button", { name: "Show retained results" }));
    await screen.findByText("The source notes this list is partial.");
    expect(screen.getByRole("button", { name: /JOB-002/ })).toBeTruthy();
  });
});

describe("exact result read through the existing renderer", () => {
  it("reads a returned reference and renders only the parent renderer", async () => {
    const { readResult, renderResult } = setup();
    await show();
    fireEvent.click(screen.getByRole("button", { name: "Open retained result — JOB-002" }));
    await screen.findByText("EXACT_RESULT_CARD:work:JOB-002");
    expect(readResult).toHaveBeenCalledTimes(1);
    const request = readResult.mock.calls[0][0];
    expect(request).toMatchObject({
      workRef: "WS:ONE",
      rootJobId: "JOB-001",
      jobId: "JOB-002",
      attemptId: "ATT-f762f805f4ab4567ab244aba0d106721",
      resultEnvelopeDigest:
        "52780b9d310fcfe2a95fc3f7f4a21426604eb2ce7fdbef6bc69414bdec85832a",
    });
    expect(request.signal).toBeInstanceOf(AbortSignal);
    expect(renderResult).toHaveBeenCalledTimes(1);
    const [selection, decoded] = renderResult.mock.calls[0];
    expect(selection.jobId).toBe("JOB-002");
    expect(decoded.result?.role).toBe("work");
    // The list receipt (8f2b…, 2) and this result receipt (aaaa…, 7) differ;
    // the click still succeeded through the existing exact decoder.
    expect(RESULT_RUNTIME.source_identity).not.toBe(LIST_RUNTIME.source_identity);
    expect(RESULT_RUNTIME.before).not.toBe(LIST_RUNTIME.before);
  });

  it("shows an explicit failure when the exact read decodes to nothing", async () => {
    const { readResult } = setup();
    readResult.mockResolvedValueOnce({ not: "a result" });
    await show();
    fireEvent.click(screen.getByRole("button", { name: "Open retained result — JOB-002" }));
    await screen.findByText("This exact result could not be read.");
    expect(screen.queryByText(/EXACT_RESULT_CARD/)).toBeNull();
  });

  it("shows an explicit failure when the exact read rejects", async () => {
    const { readResult } = setup();
    readResult.mockRejectedValueOnce(new Error("READ_CANCELLED"));
    await show();
    fireEvent.click(screen.getByRole("button", { name: "Open retained result — JOB-002" }));
    await screen.findByText("This exact result could not be read.");
  });

  it("returns to the list from the back control", async () => {
    setup();
    await show();
    fireEvent.click(screen.getByRole("button", { name: "Open retained result — JOB-002" }));
    await screen.findByText("EXACT_RESULT_CARD:work:JOB-002");
    fireEvent.click(screen.getByRole("button", { name: "Back to retained results" }));
    expect(screen.queryByText(/EXACT_RESULT_CARD/)).toBeNull();
    expect(screen.getByRole("button", { name: /JOB-002/ })).toBeTruthy();
    expect((document.activeElement as HTMLElement).tagName).toBe("H3");
  });

  it("returns from the detail with Escape and restores focus", async () => {
    setup();
    await show();
    fireEvent.click(screen.getByRole("button", { name: "Open retained result — JOB-002" }));
    await screen.findByText("EXACT_RESULT_CARD:work:JOB-002");
    expect((document.activeElement as HTMLElement).textContent).toBe(
      "Back to retained results",
    );
    const region = screen.getByRole("region", { name: "Retained results" });
    fireEvent.keyDown(region, { key: "Escape" });
    expect(screen.queryByText(/EXACT_RESULT_CARD/)).toBeNull();
    expect((document.activeElement as HTMLElement).tagName).toBe("H3");
  });
});

describe("epoch races, including A-B-A", () => {
  it("denies a list reply that arrives after an auth-generation change", async () => {
    const hold = deferred();
    const { readReferences, rerender } = setup();
    readReferences.mockImplementationOnce(() => hold.promise);
    fireEvent.click(screen.getByRole("button", { name: "Show retained results" }));
    rerender({ authGeneration: 2 });
    expect(screen.getByRole("button", { name: "Show retained results" })).toBeTruthy();
    hold.resolve(availableBody());
    await flush();
    expect(screen.queryByText(/JOB-002/)).toBeNull();
    expect(readReferences).toHaveBeenCalledTimes(1);
  });

  it("denies the first reply across an A-B-A auth round-trip", async () => {
    const hold = deferred();
    const { readReferences, signals, rerender } = setup();
    readReferences.mockImplementationOnce(() => hold.promise);
    fireEvent.click(screen.getByRole("button", { name: "Show retained results" }));
    rerender({ authGeneration: 2 });
    rerender({ authGeneration: 1 });
    expect(readReferences.mock.calls[0][0].signal.aborted).toBe(true);
    hold.resolve(availableBody());
    await flush();
    expect(screen.queryByText(/JOB-002/)).toBeNull();
    // A fresh explicit disclosure still reads normally.
    await show();
    expect(readReferences).toHaveBeenCalledTimes(2);
    expect(screen.getByRole("button", { name: /JOB-002/ })).toBeTruthy();
  });

  it("denies a list reply after the selection changed", async () => {
    const hold = deferred();
    const { readReferences, rerender } = setup();
    readReferences.mockImplementationOnce(() => hold.promise);
    fireEvent.click(screen.getByRole("button", { name: "Show retained results" }));
    rerender({ selection: { workRef: "WS:TWO", rootJobId: "JOB-001" } });
    hold.resolve(availableBody("WS:ONE"));
    await flush();
    expect(screen.queryByText(/JOB-002/)).toBeNull();
    // The new selection reads only on its own explicit disclosure.
    fireEvent.click(screen.getByRole("button", { name: "Show retained results" }));
    await waitFor(() => expect(readReferences).toHaveBeenCalledTimes(2));
    expect(readReferences.mock.calls[1][0].workRef).toBe("WS:TWO");
    await screen.findByRole("button", { name: /JOB-002/ });
  });

  it("clears an open list when the host generation changes", async () => {
    const { readReferences, rerender } = setup();
    await show();
    expect(screen.getByRole("button", { name: /JOB-002/ })).toBeTruthy();
    rerender({ hostGeneration: 4 });
    expect(screen.queryByText(/JOB-002/)).toBeNull();
    expect(screen.getByRole("button", { name: "Show retained results" })).toBeTruthy();
    expect(readReferences).toHaveBeenCalledTimes(1);
  });

  it("denies a late exact-result reply after another reference was opened", async () => {
    const hold = deferred();
    const { readResult, renderResult } = setup();
    const resultSignals: AbortSignal[] = [];
    readResult.mockImplementation(
      (request: ResultSelection & { signal: AbortSignal }) => {
        resultSignals.push(request.signal);
        if (request.jobId === "JOB-002") return hold.promise;
        return Promise.resolve(resultBody(request));
      },
    );
    await show();
    fireEvent.click(screen.getByRole("button", { name: "Open retained result — JOB-002" }));
    fireEvent.click(screen.getByRole("button", { name: "Open retained result — JOB-003" }));
    await screen.findByText("EXACT_RESULT_CARD:work:JOB-003");
    expect(resultSignals[0].aborted).toBe(true);
    expect(resultSignals[1].aborted).toBe(false);
    hold.resolve(resultBody({
      workRef: "WS:ONE",
      rootJobId: "JOB-001",
      jobId: "JOB-002",
      attemptId: "ATT-f762f805f4ab4567ab244aba0d106721",
      resultEnvelopeDigest:
        "52780b9d310fcfe2a95fc3f7f4a21426604eb2ce7fdbef6bc69414bdec85832a",
    }));
    await flush();
    expect(renderResult).toHaveBeenCalledTimes(1);
    expect(renderResult.mock.calls[0][0].jobId).toBe("JOB-003");
    expect(screen.queryByText(/EXACT_RESULT_CARD:work:JOB-002/)).toBeNull();
  });

  it("closing the disclosure stops the display read", async () => {
    const hold = deferred();
    const { readReferences, signals, rerender } = setup();
    readReferences.mockImplementationOnce(() => hold.promise);
    fireEvent.click(screen.getByRole("button", { name: "Show retained results" }));
    fireEvent.click(screen.getByRole("button", { name: "Hide retained results" }));
    expect(readReferences.mock.calls[0][0].signal.aborted).toBe(true);
    hold.resolve(availableBody());
    await flush();
    expect(screen.queryByText(/JOB-002/)).toBeNull();
    expect(screen.queryByText(/EXACT_RESULT_CARD/)).toBeNull();
    expect(readReferences).toHaveBeenCalledTimes(1);
  });

  it("issues read requests only; no mutation or command shapes exist", async () => {
    const { readReferences, readResult } = setup();
    await show();
    fireEvent.click(screen.getByRole("button", { name: "Open retained result — JOB-002" }));
    await screen.findByText("EXACT_RESULT_CARD:work:JOB-002");
    expect(Object.keys(readReferences.mock.calls[0][0]).sort()).toEqual([
      "rootJobId",
      "signal",
      "workRef",
    ]);
    expect(Object.keys(readResult.mock.calls[0][0]).sort()).toEqual([
      "attemptId",
      "jobId",
      "resultEnvelopeDigest",
      "rootJobId",
      "signal",
      "workRef",
    ]);
  });
});


it("keeps the first eight returned rows visible and exposes all remaining rows by counted disclosure", async () => {
  const {readReferences} = setup();
  const refs = Array.from({length: 17}, (_, i) => ({...INDEX.refs[0],
    job_id: `JOB-${String(i+1).padStart(3, "0")}`}));
  readReferences.mockResolvedValueOnce(availableBody("WS:ONE", {refs, absent_job_ids: []}));
  fireEvent.click(screen.getByRole("button", {name: "Show retained results"}));
  await screen.findByText("More retained results (9)");
  expect(screen.getAllByRole("list")[0].children).toHaveLength(8);
  const disclosure = screen.getByText("More retained results (9)").closest("details")!;
  expect(disclosure.open).toBe(false);
  expect(disclosure.querySelectorAll("li")).toHaveLength(9);
  fireEvent.click(screen.getByText("More retained results (9)"));
  disclosure.open = true; // jsdom does not implement native summary toggling.
  expect(screen.getAllByRole("button", {name: /Open retained result/})).toHaveLength(17);
});

it("opens a retained result when the catalogue as-of is known but source freshness is unknown", async () => {
  const {readReferences, readResult, renderResult} = setup();
  const body = availableBody();
  body.catalogue.freshness = "UNKNOWN";
  readReferences.mockResolvedValueOnce(body);
  fireEvent.click(screen.getByRole("button", {name: "Show retained results"}));
  const button = await screen.findByRole("button", {name: "Open retained result — JOB-002"});
  expect(screen.getByText(/2026-10-31T15:45:00Z/)).toBeTruthy();
  expect(screen.getByText(/Source age not known/)).toBeTruthy();
  fireEvent.click(button);
  await screen.findByText("EXACT_RESULT_CARD:work:JOB-002");
  expect(readResult).toHaveBeenCalledTimes(1);
  expect(renderResult).toHaveBeenCalledTimes(1);
});
