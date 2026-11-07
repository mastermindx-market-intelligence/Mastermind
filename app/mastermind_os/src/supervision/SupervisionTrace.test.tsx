// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { SupervisionTrace } from "./SupervisionTrace";
import { decodeMission, type EvidenceRef, type MissionDocument, type MissionSelection } from "../mission";
import ownerFixture from "../fixtures/mission-v2-current-128c46f6.json";

afterEach(() => cleanup());

it("consumes the existing canonical Mission decoder and labels its generation clock correctly", () => {
  const selected = {workRef:"WS:ONE",rootJobId:"JOB-1"};
  const observed = decodeMission(ownerFixture, selected);
  expect(observed).not.toBeNull();
  render(<SupervisionTrace document={observed} selection={selected} />);
  expect(screen.getByText(/Generated at/)).toBeTruthy();
  expect(screen.queryByText(/Source observed/)).toBeNull();
  expect(screen.getAllByText("WS:ONE").length).toBeGreaterThan(0);
});

// Inert local typed fixture builder; no live reads, no real owner data.
const WORK_REF = "WS:SUPERVISION-TRACE-FIXTURE";
const ROOT_JOB_ID = "JOB-bf9540a3";
const DIGEST = "c".repeat(64);
const selection: MissionSelection = { workRef: WORK_REF, rootJobId: ROOT_JOB_ID };

function evidenceItem(n: number): EvidenceRef {
  return {
    owner: "GITHUB",
    ref: `refs/heads/evidence-${n}`,
    field: "transport.dispatch_state",
    source_revision: `rev-${n}`,
    source_time: "2026-11-02T10:00:00Z",
    observed_at: "2026-11-02T11:00:00Z",
    freshness_state: n % 2 === 0 ? "CURRENT" : "PARTIAL",
  };
}

function fixture(): MissionDocument {
  return {
    schema: "mastermind.mission_workspace.v2",
    generated_at: "2026-11-03T00:00:00Z",
    source: {
      control_room_schema: "control-room.v9",
      control_room_generated_at: "2026-11-02T23:00:00Z",
      fabric_view_schema: "fabric-view.v4",
      fabric_view_generated_at: "2026-11-02T23:30:00Z",
      source_generation: { control_room: 7 },
      source_coverage: ["transport", "principal", "execution"],
    },
    read_state: {
      state: "CURRENT",
      reason_codes: [],
      usable_sections: ["transport", "principal", "execution", "review", "acceptance"],
    },
    program: {
      work_ref: WORK_REF,
      title: "Supervision trace fixture",
      state: "in_review",
      next_action: "Wait for the acceptance ruling",
      github_prs: [],
      attention_ids: [],
      disagreements: [],
      evidence: [],
    },
    mission: {
      root_job_id: ROOT_JOB_ID,
      root_job_candidates: [ROOT_JOB_ID],
      root_job_ambiguous: false,
      runtime_root_state: "RESOLVED",
      status: "open",
      orchestration_role: "work",
      plan_step_id: "step-1",
      depth: 1,
      title: "Fixture mission",
      armed: {
        ceo_submit_armed: null,
        coo_autonomy_armed: null,
        ceo_ingress_app_armed: null,
        dialogue_bridge_armed: null,
        terminal_return_armed: null,
        source: "absent",
      },
      submission_availability: "AVAILABLE",
      capability: { state: "PROVEN", installed: true, version: "1.0", detail: null },
      evidence: [],
    },
    principal: {
      accountable_seat: "coo",
      current_worker: {
        worker_id: "worker-fixture-1",
        attempt_id: "ATT-fixture-1",
        status: "COMPLETED",
        runtime_binding_id: "rb-fixture-1",
        binding_generation: 3,
        continuation_state: "NONE",
        effect_state: "applied",
        capacity_state: "available",
        previous_attempt_id: null,
        movement_reason_code: null,
      },
      current_sol_target: null,
      owed_turn: {
        seat: "worker",
        reason: "Terminal return awaited",
        source_refs: [
          {
            owner: "EXECUTIVE_OS",
            ref: "exec/os/turn-1",
            observed_at: "2026-11-02T09:00:00Z",
            freshness: "SOURCE_EVIDENCE_TIME",
          },
        ],
      },
      evidence: [],
    },
    children: {
      state: "AVAILABLE",
      coverage: "COMPLETE",
      reason_codes: [],
      total_count: 0,
      items: [],
      overflow_count: null,
      unjoined_job_count: 0,
      unjoined_job_ids: [],
    },
    execution: {
      state: "COMPLETED",
      summary_present: true,
      artifacts: [],
      errors_present: false,
      next_actions: [],
      evidence: [],
    },
    review: { required: true, reviews_job_id: "JOB-review-1", verdict: "approve", evidence: [] },
    transport: {
      dispatch_state: "RETURNED",
      reason: "Returned by receiver",
      actionable: false,
      historical: false,
      watch_proven: true,
      carrier: { state: "RESOLVED", reason: "carrier held", historical: false, actionable: true },
      w3c: {
        state: "RESOLVED",
        reason: null,
        terminal_state: "COMPLETED",
        wake_state: "WOKEN",
        terminal_applied: true,
        source_receipt: {
          observed_at: "2026-11-02T12:00:00Z",
          freshness: "SOURCE_EVIDENCE_TIME",
          snapshot_digest: DIGEST,
          terminal_source_owner: "executive_terminal_return",
          wake_source_owner: "wake_ledger",
        },
      },
      evidence: [],
    },
    acceptance: {
      state: "ACCEPTED",
      reason_codes: [],
      owner: "executive_terminal_return",
      artifact_revision: "rev-fixture-1",
      ruling: null,
      evidence: [],
    },
    posture: { value: "READ_ONLY", rule: null, evidence: [] },
    conversation: {
      state: "UNAVAILABLE",
      coverage: "NOT_PROJECTED",
      reason_codes: [],
      total_count: 0,
      items: [],
      overflow_count: null,
    },
    missingness: [],
    degraded: [],
    budget: { bytes: 4096 },
    feature_gates: { conversation: "UNAVAILABLE", actions: "READ_ONLY", advanced: "AVAILABLE" },
  };
}

describe("SupervisionTrace", () => {
  it("withholds every source detail when the document does not match the selection", () => {
    const doc = fixture();
    doc.mission.root_job_candidates = [ROOT_JOB_ID, "JOB-second"];
    render(<SupervisionTrace document={doc} selection={selection} />);
    expect(screen.getByText(/does not exactly match/i)).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "Orchestration trace" })).toBeNull();
    expect(screen.queryByText("worker-fixture-1")).toBeNull();
    expect(screen.queryByRole("button")).toBeNull();
    expect(screen.queryByText("c".repeat(64))).toBeNull();
  });

  it("withholds source details on a work reference mismatch", () => {
    render(
      <SupervisionTrace
        document={fixture()}
        selection={{ workRef: "WS:OTHER", rootJobId: ROOT_JOB_ID }}
      />,
    );
    expect(screen.getByText(/does not exactly match/i)).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "Return and acceptance" })).toBeNull();
    expect(screen.queryByText("worker-fixture-1")).toBeNull();
  });

  it("shows unavailable without source details when no document is provided", () => {
    const read = vi.fn();
    render(<SupervisionTrace document={null} selection={selection} onReadCurrent={read} />);
    expect(screen.getByText(/No mission observation is available/i)).toBeTruthy();
    expect(read).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", {name:"Read current mission"}));
    expect(read).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("heading", { name: "Orchestration trace" })).toBeNull();
  });
  it("permits a selected-source refresh while foreign fields remain withheld", () => {
    const read = vi.fn();
    const view = render(<SupervisionTrace document={fixture()}
      selection={{workRef:"WS:OTHER",rootJobId:ROOT_JOB_ID}} onReadCurrent={read} />);
    expect(screen.queryByText("worker-fixture-1")).toBeNull();
    expect(read).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", {name:"Read current mission"}));
    expect(read).toHaveBeenCalledTimes(1);
    view.rerender(<SupervisionTrace document={null}
      selection={{workRef:"WS:OTHER",rootJobId:"latest"}} onReadCurrent={read} />);
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("keeps the held headline when dispatch reports EFFECT_UNKNOWN even with completed and accepted fields", () => {
    const doc = fixture();
    doc.transport.dispatch_state = "EFFECT_UNKNOWN";
    render(<SupervisionTrace document={doc} selection={selection} />);
    expect(screen.getByText(/original operation held/i)).toBeTruthy();
    expect(screen.getByText("Transport dispatch state")).toBeTruthy();
    expect(screen.getAllByText("completed").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("accepted").length).toBeGreaterThanOrEqual(1);
  });

  it("keeps the held headline when the current worker reports effect_unknown", () => {
    const doc = fixture();
    if (doc.principal.current_worker === null) throw new Error("fixture worker");
    doc.principal.current_worker.effect_state = "effect_unknown";
    render(<SupervisionTrace document={doc} selection={selection} />);
    expect(screen.getByText(/original operation held/i)).toBeTruthy();
    expect(screen.getAllByText("Current worker effect state").length).toBeGreaterThanOrEqual(1);
  });

  it("keeps the held headline when the current Sol target reports effect_unknown", () => {
    const doc = fixture();
    doc.principal.current_sol_target = {
      worker_id: "worker-fixture-2",
      attempt_id: "ATT-fixture-2",
      status: "RUNNING",
      runtime_binding_id: null,
      binding_generation: null,
      continuation_state: "PREPARED",
      effect_state: "effect_unknown",
      capacity_state: "degraded",
      previous_attempt_id: null,
      movement_reason_code: null,
    };
    render(<SupervisionTrace document={doc} selection={selection} />);
    expect(screen.getByText(/original operation held/i)).toBeTruthy();
    expect(screen.getByText("Current Sol target effect state")).toBeTruthy();
    expect(screen.getByText("worker-fixture-2")).toBeTruthy();
  });

  it("keeps the held headline when the W3C transport reports EFFECT_UNKNOWN", () => {
    const doc = fixture();
    if (doc.transport.w3c === null) throw new Error("fixture w3c");
    doc.transport.w3c.state = "EFFECT_UNKNOWN";
    render(<SupervisionTrace document={doc} selection={selection} />);
    expect(screen.getByText(/original operation held/i)).toBeTruthy();
    expect(screen.getAllByText("W3C transport state").length).toBeGreaterThanOrEqual(1);
  });

  it("states the historical caveat and never claims a live or ready state", () => {
    const doc = fixture();
    doc.read_state.state = "HISTORICAL";
    doc.transport.historical = true;
    render(<SupervisionTrace document={doc} selection={selection} />);
    expect(screen.getByText(/^This observation is marked historical/)).toBeTruthy();
    expect(screen.getByText(/may describe a previous attempt/i)).toBeTruthy();
    const text = document.body.textContent ?? "";
    expect(text).not.toMatch(/\bready\b/i);
    expect(text).not.toMatch(/\blive\b/i);
  });

  it("states the partial caveat without inferring completion", () => {
    const doc = fixture();
    doc.read_state.state = "PARTIAL";
    render(<SupervisionTrace document={doc} selection={selection} />);
    expect(screen.getByText(/This observation is partial/i)).toBeTruthy();
    expect(document.body.textContent ?? "").not.toMatch(/\bready\b/i);
    expect(screen.getByText("partial")).toBeTruthy();
  });

  it("keeps execution completion distinct from NOT_PROJECTED acceptance", () => {
    const doc = fixture();
    doc.acceptance.state = "NOT_PROJECTED";
    doc.acceptance.owner = null;
    render(<SupervisionTrace document={doc} selection={selection} />);
    expect(screen.getByText("not projected")).toBeTruthy();
    expect(screen.getAllByText("completed").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/does not imply acceptance/i)).toBeTruthy();
    expect(screen.getAllByText("Unknown").length).toBeGreaterThanOrEqual(1);
  });

  it("keeps null facts explicitly unknown or unreported instead of inventing values", () => {
    const doc = fixture();
    doc.principal.accountable_seat = null;
    doc.principal.owed_turn = null;
    doc.program.next_action = null;
    if (doc.transport.w3c === null) throw new Error("fixture w3c");
    doc.transport.w3c.terminal_state = null;
    doc.transport.watch_proven = null;
    render(<SupervisionTrace document={doc} selection={selection} />);
    expect(screen.getAllByText("Unknown").length).toBeGreaterThanOrEqual(3);
    expect(screen.getByText(/Not provided by the source/i)).toBeTruthy();
    expect(screen.getAllByText("Not reported").length).toBeGreaterThanOrEqual(6);
  });

  it("invokes the host read exactly once per activation and never on mount or rerender", () => {
    const onReadCurrent = vi.fn();
    const doc = fixture();
    const { rerender } = render(
      <SupervisionTrace document={doc} selection={selection} onReadCurrent={onReadCurrent} />,
    );
    expect(onReadCurrent).not.toHaveBeenCalled();
    rerender(
      <SupervisionTrace document={doc} selection={selection} onReadCurrent={onReadCurrent} />,
    );
    expect(onReadCurrent).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Read current mission" }));
    expect(onReadCurrent).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "Read current mission" }));
    expect(onReadCurrent).toHaveBeenCalledTimes(2);
  });

  it("offers no read button when no host read was provided", () => {
    render(<SupervisionTrace document={fixture()} selection={selection} />);
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("renders zh-CN labels at parity and forwards one host read activation", () => {
    const onReadCurrent = vi.fn();
    render(
      <SupervisionTrace
        document={fixture()}
        selection={selection}
        locale="zh-CN"
        onReadCurrent={onReadCurrent}
      />,
    );
    expect(screen.getByRole("heading", { name: "监督与追踪", level: 2 })).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "Supervision & trace" })).toBeNull();
    expect(screen.getByRole("heading", { name: "编排追踪", level: 3 })).toBeTruthy();
    expect(screen.getByText("分发状态")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "读取当前任务" }));
    expect(onReadCurrent).toHaveBeenCalledTimes(1);
  });

  it("reports armed flags as separate observations and never offers a command", () => {
    const doc = fixture();
    doc.mission.armed.ceo_submit_armed = true;
    doc.mission.armed.source = "control.json";
    render(<SupervisionTrace document={doc} selection={selection} />);
    expect(screen.getByText("Reported armed")).toBeTruthy();
    expect(screen.getByText(/never combines into a readiness claim/i)).toBeTruthy();
    expect(screen.queryAllByRole("button")).toHaveLength(0);
  });

  it("keeps unreported armed flags separate instead of an all-green readiness row", () => {
    render(<SupervisionTrace document={fixture()} selection={selection} />);
    expect(screen.getAllByText("Not reported").length).toBeGreaterThanOrEqual(5);
    expect(screen.queryByText("Reported armed")).toBeNull();
  });

  it("shows the exact observed worker, attempt and receipt facts with one h2 and no hyperlinks", () => {
    const { container } = render(<SupervisionTrace document={fixture()} selection={selection} />);
    expect(screen.getByText("worker-fixture-1")).toBeTruthy();
    expect(screen.getByText("ATT-fixture-1")).toBeTruthy();
    expect(screen.getByText("2026-11-02T12:00:00Z")).toBeTruthy();
    expect(screen.getByText(DIGEST)).toBeTruthy();
    expect(screen.getByText("exec/os/turn-1")).toBeTruthy();
    expect(container.querySelectorAll("h2")).toHaveLength(1);
    expect(container.querySelectorAll("h1")).toHaveLength(0);
    expect(container.querySelectorAll("a")).toHaveLength(0);
  });

  it("bounds source evidence to the first 8 with an explicit counted expansion", () => {
    const doc = fixture();
    doc.transport.evidence = Array.from({ length: 10 }, (_, i) => evidenceItem(i + 1));
    render(<SupervisionTrace document={doc} selection={selection} />);
    expect(screen.getByText(/Showing the first 8 of 10 source evidence items/)).toBeTruthy();
    expect(screen.getByText("refs/heads/evidence-8")).toBeTruthy();
    const withheld = screen.getByText("refs/heads/evidence-9").closest("details");
    expect(withheld?.hasAttribute("open")).toBe(false);
    fireEvent.click(screen.getByText(/Show the remaining 2 source evidence items/));
    expect(screen.getByText("refs/heads/evidence-9").closest("details")?.hasAttribute("open")).toBe(
      true,
    );
    expect(screen.getByText("refs/heads/evidence-10")).toBeTruthy();
  });

  it("keeps reported missingness visible without claiming all producers are connected", () => {
    const doc = fixture();
    doc.missingness = [
      {
        missingness_class: "MISSING_PRODUCER",
        target_field: "principal.owed_turn",
        producer_owner: null,
        reason: "No producer reported this field in this observation.",
      },
    ];
    render(<SupervisionTrace document={doc} selection={selection} />);
    expect(screen.getByText("principal.owed_turn")).toBeTruthy();
    expect(screen.getByText("missing producer")).toBeTruthy();
    expect(screen.getByText(/does not claim that every producer is connected/i)).toBeTruthy();
  });
});
