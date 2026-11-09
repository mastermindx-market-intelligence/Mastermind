// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import {
  ProjectEvidence,
  ProjectJournal,
  ProjectWorkDetail,
} from "./workJourney";
import type {
  EvidenceRef,
  MissionDocument,
  MissionSelection,
} from "./mission";

afterEach(cleanup);

const EN = "en" as const;
const ZH = "zh-CN" as const;

function ref(partial: {
  owner: EvidenceRef["owner"];
  ref: string;
  field: string;
  freshness: EvidenceRef["freshness_state"];
  revision?: string | null;
  sourceTime?: string | null;
  observedAt?: string | null;
}): EvidenceRef {
  return {
    owner: partial.owner,
    ref: partial.ref,
    field: partial.field,
    source_revision: partial.revision === undefined ? null : partial.revision,
    source_time: partial.sourceTime === undefined ? null : partial.sourceTime,
    observed_at: partial.observedAt === undefined ? null : partial.observedAt,
    freshness_state: partial.freshness,
  };
}

interface DocOverrides {
  dispatchState?: MissionDocument["transport"]["dispatch_state"];
  executionState?: MissionDocument["execution"]["state"];
  verdict?: MissionDocument["review"]["verdict"];
  acceptanceState?: MissionDocument["acceptance"]["state"];
  acceptanceRuling?: string | null;
  readState?: MissionDocument["read_state"]["state"];
  programEvidence?: EvidenceRef[];
  missionEvidence?: EvidenceRef[];
  transportEvidence?: EvidenceRef[];
  nextAction?: string | null;
  owedTurn?: MissionDocument["principal"]["owed_turn"];
}

// Test-only document helper: fills every field the components access and is
// cast (only here, only in tests) because producer enums are wider than the
// literals a fixture needs.
function makeDoc(overrides: DocOverrides): MissionDocument {
  const base = {
    schema: "mastermind.mission_workspace.v2",
    generated_at: "2026-11-02T10:00:00Z",
    source: {
      control_room_schema: "control_room.v3",
      control_room_generated_at: "2026-11-02T09:55:00Z",
      fabric_view_schema: "fabric_view.v2",
      fabric_view_generated_at: "2026-11-02T09:58:00Z",
      source_generation: {},
      source_coverage: ["program", "transport", "review", "acceptance"],
    },
    read_state: {
      state: overrides.readState ?? "CURRENT",
      reason_codes: [],
      usable_sections: ["program", "transport", "review", "acceptance"],
    },
    program: {
      work_ref: "work-42",
      title: "Work evidence projection",
      state: "IN_PROGRESS",
      next_action:
        overrides.nextAction === undefined
          ? "worker: continue branch feature/work-journey"
          : overrides.nextAction,
      github_prs: [],
      attention_ids: [],
      disagreements: [],
      evidence:
        overrides.programEvidence ??
        [
          ref({
            owner: "GITHUB",
            ref: "repos/mmOS/app/pulls/71",
            field: "merge_state",
            freshness: "CURRENT",
            revision: "pr-71-head",
            sourceTime: "2026-11-02T08:00:00Z",
            observedAt: "2026-11-02T09:00:00Z",
          }),
          ref({
            owner: "LINEAR",
            ref: "issue/MMOS-12",
            field: "state",
            freshness: "PARTIAL",
            observedAt: "2026-11-01T09:00:00Z",
          }),
          ref({
            owner: "SLACK",
            ref: "channels/support/C1",
            field: "latest_message",
            freshness: "HISTORICAL",
            observedAt: "2026-10-20T09:00:00Z",
          }),
        ],
    },
    mission: {
      root_job_id: "job-root-1",
      root_job_candidates: ["job-root-1"],
      root_job_ambiguous: false,
      runtime_root_state: "RESOLVED",
      status: "IN_PROGRESS",
      orchestration_role: "work",
      plan_step_id: "step-3",
      depth: 2,
      title: "Work evidence projection",
      armed: {
        ceo_submit_armed: false,
        coo_autonomy_armed: false,
        ceo_ingress_app_armed: false,
        dialogue_bridge_armed: false,
        terminal_return_armed: false,
        source: "absent",
      },
      submission_availability: "AVAILABLE",
      capability: {
        state: "PROVEN",
        installed: true,
        version: "1.2.0",
        detail: null,
      },
      evidence:
        overrides.missionEvidence ??
        [
          ref({
            owner: "CONTROL_ROOM_CACHE",
            ref: "cache/job-root-1",
            field: "status",
            freshness: "UNAVAILABLE",
          }),
        ],
    },
    principal: {
      accountable_seat: "worker",
      current_worker: {
        worker_id: "worker-alpha",
        attempt_id: "att-9",
        status: "STARTED",
        runtime_binding_id: "rb-1",
        binding_generation: 3,
        continuation_state: "NONE",
        effect_state: "none",
        capacity_state: "available",
        previous_attempt_id: null,
        movement_reason_code: null,
      },
      current_sol_target: null,
      owed_turn:
        overrides.owedTurn === undefined
          ? {
              seat: "worker",
              reason: "worker holds the open turn",
              source_refs: [],
            }
          : overrides.owedTurn,
      evidence: [],
    },
    children: {
      state: "EMPTY",
      coverage: "NOT_APPLICABLE",
      reason_codes: [],
      total_count: 0,
      items: [],
      overflow_count: null,
      unjoined_job_count: 0,
      unjoined_job_ids: [],
    },
    execution: {
      state: overrides.executionState ?? "IN_PROGRESS",
      summary_present: true,
      artifacts: [],
      errors_present: false,
      next_actions: [],
      evidence: [],
    },
    review: {
      required: true,
      reviews_job_id: "job-review-2",
      verdict: overrides.verdict ?? "NOT_YET",
      evidence: [],
    },
    transport: {
      dispatch_state: overrides.dispatchState ?? "STARTED",
      reason: "worker started on admitted budget",
      actionable: true,
      historical: false,
      watch_proven: null,
      carrier: null,
      w3c: null,
      evidence:
        overrides.transportEvidence ??
        [
          ref({
            owner: "AGENT_OS",
            ref: "agent_os/runs/run-77",
            field: "dispatch_state",
            freshness: "CURRENT",
            revision: "run-77",
            sourceTime: "2026-11-02T09:30:00Z",
            observedAt: "2026-11-02T09:31:00Z",
          }),
        ],
    },
    acceptance: {
      state: overrides.acceptanceState ?? "NOT_PROJECTED",
      reason_codes: [],
      owner: null,
      artifact_revision: null,
      ruling:
        overrides.acceptanceRuling === undefined
          ? null
          : overrides.acceptanceRuling,
      evidence: [],
    },
    posture: { value: "READ_ONLY", rule: null, evidence: [] },
    conversation: {
      state: "EMPTY",
      coverage: "NOT_APPLICABLE",
      reason_codes: [],
      total_count: 0,
      items: [],
      overflow_count: null,
    },
    missingness: [],
    degraded: [],
    budget: {},
    feature_gates: {
      conversation: "UNAVAILABLE",
      actions: "READ_ONLY",
      advanced: "AVAILABLE",
    },
  };
  return base as unknown as MissionDocument;
}

const BASE_SELECTION: MissionSelection = {
  workRef: "work-42",
  rootJobId: "job-root-1",
};

const MISMATCH_SELECTION: MissionSelection = {
  workRef: "work-42",
  rootJobId: "some-other-root",
};

function rowButtons(): HTMLElement[] {
  return screen
    .getAllByRole("button")
    .filter((button) => (button.textContent ?? "").includes("field_"));
}

describe("ProjectWorkDetail", () => {
  it("hides every supplied panel and shows a localized message when the selected root mismatches", () => {
    render(
      <ProjectWorkDetail
        document={makeDoc({})}
        selection={MISMATCH_SELECTION}
        locale={EN}
        generation={1}
        resultPanel={<div>RESULT_PANEL_MARKER</div>}
        activityPanel={<div>ACTIVITY_PANEL_MARKER</div>}
        actionPanel={<div>ACTION_PANEL_MARKER</div>}
        onOpenEvidence={vi.fn()}
        onOpenJournal={vi.fn()}
      />,
    );
    expect(screen.queryByText("RESULT_PANEL_MARKER")).toBeNull();
    expect(screen.queryByText("ACTIVITY_PANEL_MARKER")).toBeNull();
    expect(screen.queryByText("ACTION_PANEL_MARKER")).toBeNull();
    expect(
      screen.queryByRole("button", { name: "Open evidence" }),
    ).toBeNull();
    expect(
      screen.getByText(
        "Source selection does not match this document; nothing is shown.",
      ),
    ).toBeTruthy();
  });

  it("treats an ambiguous root job as a selection mismatch", () => {
    const doc = makeDoc({});
    doc.mission.root_job_ambiguous = true;
    render(
      <ProjectWorkDetail
        document={doc}
        selection={BASE_SELECTION}
        locale={EN}
        generation={1}
        resultPanel={<div>RESULT_PANEL_MARKER</div>}
      />,
    );
    expect(screen.queryByText("RESULT_PANEL_MARKER")).toBeNull();
    expect(screen.getByText(/Source selection does not match/)).toBeTruthy();
  });

  it("labels the view as Returned work only when dispatch_state is RETURNED", () => {
    const returned = render(
      <ProjectWorkDetail
        document={makeDoc({ dispatchState: "RETURNED" })}
        selection={BASE_SELECTION}
        locale={EN}
        generation={1}
      />,
    );
    expect(
      screen.getByRole("heading", { level: 2, name: "Returned work" }),
    ).toBeTruthy();
    expect(
      screen.getByRole("heading", { level: 3, name: "Return" }),
    ).toBeTruthy();
    returned.unmount();
    render(
      <ProjectWorkDetail
        document={makeDoc({ dispatchState: "PICKUP_ACKNOWLEDGED" })}
        selection={BASE_SELECTION}
        locale={EN}
        generation={1}
      />,
    );
    expect(
      screen.getByRole("heading", { level: 2, name: "Work detail" }),
    ).toBeTruthy();
    expect(
      screen.queryByRole("heading", { level: 3, name: "Return" }),
    ).toBeTruthy();
    expect(screen.getByText("Return not established.")).toBeTruthy();
  });

  it("does not let execution COMPLETED imply return, acceptance or release", () => {
    render(
      <ProjectWorkDetail
        document={makeDoc({
          dispatchState: "PICKUP_ACKNOWLEDGED",
          executionState: "COMPLETED",
        })}
        selection={BASE_SELECTION}
        locale={EN}
        generation={1}
      />,
    );
    expect(
      screen.queryByRole("heading", { level: 3, name: "Return" }),
    ).toBeTruthy();
    expect(screen.getByText("Return not established.")).toBeTruthy();
    const acceptance = screen.getByRole("heading", {
      level: 3,
      name: "Acceptance",
    }).parentElement as HTMLElement;
    expect(within(acceptance).getByText("Acceptance not supplied")).toBeTruthy();
    const release = screen.getByRole("heading", {
      level: 3,
      name: "Release",
    }).parentElement as HTMLElement;
    expect(
      within(release).getByText("Unverified"),
    ).toBeTruthy();
    expect(within(release).queryByText("ACCEPTED")).toBeNull();
  });

  it("keeps a reject verdict and an accepted acceptance as separate facts in separate sections", () => {
    render(
      <ProjectWorkDetail
        document={makeDoc({
          verdict: "reject",
          acceptanceState: "ACCEPTED",
          acceptanceRuling: "Accepted by chairman on revision 7",
        })}
        selection={BASE_SELECTION}
        locale={EN}
        generation={1}
      />,
    );
    const review = screen.getByRole("heading", {
      level: 3,
      name: "Review",
    }).parentElement as HTMLElement;
    const acceptance = screen.getByRole("heading", {
      level: 3,
      name: "Acceptance",
    }).parentElement as HTMLElement;
    expect(within(review).getByText("Changes requested")).toBeTruthy();
    expect(within(review).queryByText("ACCEPTED")).toBeNull();
    expect(within(acceptance).getByText("Accepted")).toBeTruthy();
    expect(
      screen.getByText("Accepted by chairman on revision 7"),
    ).toBeTruthy();
    expect(within(acceptance).queryByText("reject")).toBeNull();
  });

  it("shows owed turn seat/reason and next action verbatim, renders supplied panels and conditional nav buttons", () => {
    const onOpenEvidence = vi.fn();
    const onOpenJournal = vi.fn();
    render(
      <ProjectWorkDetail
        document={makeDoc({})}
        selection={BASE_SELECTION}
        locale={EN}
        generation={1}
        resultPanel={<div>RESULT_PANEL_MARKER</div>}
        activityPanel={<div>ACTIVITY_PANEL_MARKER</div>}
        actionPanel={<div>ACTION_PANEL_MARKER</div>}
        onOpenEvidence={onOpenEvidence}
        onOpenJournal={onOpenJournal}
      />,
    );
    expect(screen.getByText("RESULT_PANEL_MARKER")).toBeTruthy();
    expect(screen.getByText("ACTION_PANEL_MARKER")).toBeTruthy();
    expect(screen.getByText("worker holds the open turn")).toBeTruthy();
    expect(
      screen.getByText("worker: continue branch feature/work-journey"),
    ).toBeTruthy();
    const activity = screen.getByText("Session activity and context")
      .closest("details") as HTMLDetailsElement;
    expect(within(activity).getByText("ACTIVITY_PANEL_MARKER")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Open evidence" }));
    expect(onOpenEvidence).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "Open journal" }));
    expect(onOpenJournal).toHaveBeenCalledTimes(1);
  });

  it("renders no navigation buttons or action panel content when callbacks and panels are absent", () => {
    render(
      <ProjectWorkDetail
        document={makeDoc({})}
        selection={BASE_SELECTION}
        locale={EN}
        generation={1}
      />,
    );
    expect(
      screen.queryByRole("button", { name: "Open evidence" }),
    ).toBeNull();
    expect(
      screen.queryByRole("button", { name: "Open journal" }),
    ).toBeNull();
    expect(screen.getByText("No result panel was supplied.")).toBeTruthy();
  });

  it("surfaces the source read-state caveat when the read is not CURRENT", () => {
    render(
      <ProjectWorkDetail
        document={makeDoc({ readState: "PARTIAL" })}
        selection={BASE_SELECTION}
        locale={EN}
        generation={1}
      />,
    );
    expect(screen.getByText("Some source information is missing or may be out of date.")).toBeTruthy();
  });

  it("localizes work copy to zh-CN", () => {
    render(
      <ProjectWorkDetail
        document={makeDoc({ dispatchState: "RETURNED" })}
        selection={BASE_SELECTION}
        locale={ZH}
        generation={1}
      />,
    );
    expect(
      screen.getByRole("heading", { level: 2, name: "已返回的工作" }),
    ).toBeTruthy();
    expect(
      screen.getByRole("heading", { level: 3, name: "返回" }),
    ).toBeTruthy();
    expect(screen.getByText("未建立；未提供发布证明。")).toBeTruthy();
  });
  it.each([EN,ZH])("keeps raw Work states only in closed source details in %s",locale=>{
    const doc=makeDoc({dispatchState:"UNKNOWN",verdict:"NOT_YET",acceptanceState:"NOT_PROJECTED",readState:"PARTIAL"});
    const before=JSON.stringify(doc);const {container}=render(<ProjectWorkDetail document={doc} selection={BASE_SELECTION} locale={locale} generation={1}/>);
    const primary=container.querySelector("header")!.textContent!+container.querySelector(".mm-work-journey__facts")!.textContent!;
    expect(primary).not.toMatch(/UNKNOWN|NOT_YET|NOT_PROJECTED|PARTIAL/);
    const source=screen.getByText(locale===EN?"Work source details":"工作来源详情").closest("details")!;
    expect(source.open).toBe(false);for(const code of ["UNKNOWN","NOT_YET","NOT_PROJECTED","PARTIAL"])expect(source.textContent).toContain(code);
    expect(JSON.stringify(doc)).toBe(before);
  });

});

describe("ProjectEvidence", () => {
  it("hides the supplied result panel on selection mismatch", () => {
    render(
      <ProjectEvidence
        document={makeDoc({})}
        selection={MISMATCH_SELECTION}
        locale={EN}
        generation={1}
        resultPanel={<div>RESULT_PANEL_MARKER</div>}
      />,
    );
    expect(screen.queryByText("RESULT_PANEL_MARKER")).toBeNull();
    expect(screen.getByText(/Source selection does not match/)).toBeTruthy();
  });

  it("filters observed evidence by freshness bucket with per-bucket counts over observed refs only", () => {
    render(
      <ProjectEvidence
        document={makeDoc({})}
        selection={BASE_SELECTION}
        locale={EN}
        generation={1}
      />,
    );
    expect(screen.getByText("5 observed references")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /Partial \(/ }));
    expect(screen.getByText("1 observed references")).toBeTruthy();
    expect(screen.queryByText(/GITHUB · merge_state/)).toBeNull();
    expect(screen.queryByText(/SLACK · latest_message/)).toBeNull();
    expect(screen.getByText(/LINEAR · state/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /Unavailable \(/ }));
    expect(screen.queryByText(/LINEAR · state/)).toBeNull();
    expect(screen.getByText(/CONTROL_ROOM_CACHE · status/)).toBeTruthy();
  });

  it("shows the exact source tuple of the selected row", () => {
    render(
      <ProjectEvidence
        document={makeDoc({})}
        selection={BASE_SELECTION}
        locale={EN}
        generation={1}
      />,
    );
    expect(
      screen.getByText(/Select an evidence row to inspect/),
    ).toBeTruthy();
    fireEvent.click(screen.getByText(/GITHUB · merge_state/));
    const detail = screen.getByRole("heading", {
      level: 3,
      name: "Selected source detail",
    }).parentElement as HTMLElement;
    expect(within(detail).getByText("Program")).toBeTruthy();
    expect(within(detail).getByText("GITHUB")).toBeTruthy();
    expect(within(detail).getByText("repos/mmOS/app/pulls/71")).toBeTruthy();
    expect(within(detail).getByText("merge_state")).toBeTruthy();
    expect(within(detail).getByText("pr-71-head")).toBeTruthy();
    expect(within(detail).getByText("2026-11-02T08:00:00Z")).toBeTruthy();
    expect(within(detail).getByText("2026-11-02T09:00:00Z")).toBeTruthy();
    expect(within(detail).getByText("CURRENT")).toBeTruthy();
  });

  it("caps the list at 8 rows and exposes a named see-all toggle", () => {
    const freshnings: EvidenceRef["freshness_state"][] = [
      "CURRENT",
      "PARTIAL",
      "HISTORICAL",
      "CURRENT",
      "CURRENT",
      "PARTIAL",
      "CURRENT",
      "HISTORICAL",
      "CURRENT",
      "PARTIAL",
      "CURRENT",
    ];
    const programEvidence = freshnings.map((freshness, index) =>
      ref({
        owner: "GITHUB",
        ref: `repos/mmOS/app/commits/${index}`,
        field: `field_${index}`,
        freshness,
      }),
    );
    render(
      <ProjectEvidence
        document={makeDoc({ programEvidence })}
        selection={BASE_SELECTION}
        locale={EN}
        generation={1}
      />,
    );
    expect(rowButtons()).toHaveLength(8);
    fireEvent.click(screen.getByRole("button", { name: "See all 13" }));
    expect(rowButtons()).toHaveLength(11);
    fireEvent.click(screen.getByRole("button", { name: "Show fewer" }));
    expect(rowButtons()).toHaveLength(8);
  });

  it("resets filter and selected source synchronously when generation changes", () => {
    const view = render(
      <ProjectEvidence
        document={makeDoc({})}
        selection={BASE_SELECTION}
        locale={EN}
        generation="gen-1"
      />,
    );
    fireEvent.click(screen.getByText(/LINEAR · state/));
    expect(
      screen.queryByText(/Select an evidence row to inspect/),
    ).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /Historical \(/ }));
    expect(screen.queryByText(/GITHUB · merge_state/)).toBeNull();
    view.rerender(
      <ProjectEvidence
        document={makeDoc({})}
        selection={BASE_SELECTION}
        locale={EN}
        generation="gen-2"
      />,
    );
    expect(screen.getByText(/GITHUB · merge_state/)).toBeTruthy();
    expect(
      screen.getByText(/Select an evidence row to inspect/),
    ).toBeTruthy();
    expect(screen.getByText("5 observed references")).toBeTruthy();
  });

  it("resets the selected source when the document object changes with the same generation", () => {
    const view = render(
      <ProjectEvidence
        document={makeDoc({})}
        selection={BASE_SELECTION}
        locale={EN}
        generation="gen-1"
      />,
    );
    fireEvent.click(screen.getByText(/GITHUB · merge_state/));
    expect(
      screen.queryByText(/Select an evidence row to inspect/),
    ).toBeNull();
    view.rerender(
      <ProjectEvidence
        document={makeDoc({})}
        selection={BASE_SELECTION}
        locale={EN}
        generation="gen-1"
      />,
    );
    expect(
      screen.getByText(/Select an evidence row to inspect/),
    ).toBeTruthy();
  });

  it("resets the selected source when the selection changes", () => {
    const view = render(
      <ProjectEvidence
        document={makeDoc({})}
        selection={BASE_SELECTION}
        locale={EN}
        generation="gen-1"
      />,
    );
    fireEvent.click(screen.getByText(/GITHUB · merge_state/));
    expect(
      screen.queryByText(/Select an evidence row to inspect/),
    ).toBeNull();
    view.rerender(
      <ProjectEvidence
        document={makeDoc({})}
        selection={{ workRef: "work-42", rootJobId: "job-root-1" }}
        locale={EN}
        generation="gen-1"
      />,
    );
    expect(
      screen.getByText(/Select an evidence row to inspect/),
    ).toBeTruthy();
  });

  it("localizes evidence copy to zh-CN", () => {
    render(
      <ProjectEvidence
        document={makeDoc({})}
        selection={BASE_SELECTION}
        locale={ZH}
        generation={1}
      />,
    );
    expect(screen.getByRole("heading", { level: 2, name: "证据" })).toBeTruthy();
    expect(screen.getByText("已观察引用 5 条")).toBeTruthy();
    fireEvent.click(screen.getByText(/GITHUB · merge_state/));
    expect(
      screen.getByRole("heading", { level: 3, name: "所选来源详情" }),
    ).toBeTruthy();
    expect(screen.getByText("引用")).toBeTruthy();
    expect(screen.getByRole("button", { name: /部分 \(/ })).toBeTruthy();
  });
});

describe("ProjectJournal", () => {
  it("states the journal is unavailable and never fabricates a chronological event stream", () => {
    const doc = makeDoc({});
    const { container } = render(
      <ProjectJournal
        document={doc}
        selection={BASE_SELECTION}
        locale={EN}
        generation={1}
        activityPanel={<div>ACTIVITY_PANEL_MARKER</div>}
      />,
    );
    expect(
      screen.getByText("Journal unavailable — no event stream was supplied."),
    ).toBeTruthy();
    expect(container.querySelector("ol")).toBeNull();
    expect(container.querySelector("time")).toBeNull();
    expect(container.querySelector("textarea")).toBeNull();
    expect(container.querySelector("input")).toBeNull();
    // Non-AGENT_OS observation timestamps are never rendered as journal events.
    expect(screen.queryByText("2026-11-02T08:00:00Z")).toBeNull();
    expect(screen.queryByText("2026-10-20T09:00:00Z")).toBeNull();
    const activity = screen.getByText("Activity").closest(
      "details",
    ) as HTMLDetailsElement;
    expect(within(activity).getByText("ACTIVITY_PANEL_MARKER")).toBeTruthy();
    const continuity = screen.getByRole("heading", {
      level: 3,
      name: "Continuity sources",
    }).parentElement as HTMLElement;
    expect(
      within(continuity).getByText(/AGENT_OS · dispatch_state/),
    ).toBeTruthy();
    expect(within(continuity).queryByText(/GITHUB/)).toBeNull();
    expect(within(continuity).queryByText(/LINEAR/)).toBeNull();
    expect(within(continuity).queryByText(/SLACK/)).toBeNull();
    const context = screen.getByRole("heading", {
      level: 3,
      name: "Supplied context",
    }).parentElement as HTMLElement;
    expect(within(context).getByText("worker")).toBeTruthy();
    expect(within(context).getByText("worker holds the open turn")).toBeTruthy();
    expect(within(context).getByText("worker-alpha")).toBeTruthy();
  });

  it("shows an explicit empty state when no AGENT_OS evidence refs were supplied", () => {
    render(
      <ProjectJournal
        document={makeDoc({
          transportEvidence: [
            ref({
              owner: "GITHUB",
              ref: "repos/mmOS/app/pulls/71",
              field: "merge_state",
              freshness: "CURRENT",
            }),
          ],
        })}
        selection={BASE_SELECTION}
        locale={EN}
        generation={1}
      />,
    );
    expect(
      screen.getByText("No AGENT_OS evidence references were supplied."),
    ).toBeTruthy();
  });

  it("hides the activity panel on selection mismatch", () => {
    render(
      <ProjectJournal
        document={makeDoc({})}
        selection={MISMATCH_SELECTION}
        locale={EN}
        generation={1}
        activityPanel={<div>ACTIVITY_PANEL_MARKER</div>}
      />,
    );
    expect(screen.queryByText("ACTIVITY_PANEL_MARKER")).toBeNull();
    expect(screen.getByText(/Source selection does not match/)).toBeTruthy();
  });

  it("localizes journal copy to zh-CN", () => {
    render(
      <ProjectJournal
        document={makeDoc({})}
        selection={BASE_SELECTION}
        locale={ZH}
        generation={1}
      />,
    );
    expect(screen.getByText("日志不可用 — 未提供事件流。")).toBeTruthy();
    expect(
      screen.getByRole("heading", { level: 2, name: "项目日志" }),
    ).toBeTruthy();
    expect(
      screen.getByRole("heading", { level: 3, name: "已提供的上下文" }),
    ).toBeTruthy();
    expect(
      screen.getByRole("heading", { level: 3, name: "延续来源" }),
    ).toBeTruthy();
    expect(screen.getByText("活动")).toBeTruthy();
  });
});

it("keeps four status facts together and rejects an unresolved Mission binding", () => {
  const doc = makeDoc({});
  const view = render(<ProjectWorkDetail document={doc} selection={BASE_SELECTION} locale="en" generation={1} resultPanel={<span>bound-result</span>} />);
  const strip = screen.getByRole("region", {name: "Status ladder"});
  expect(within(strip).getAllByRole("heading", {level: 3}).map(node=>node.textContent)).toEqual(["Return","Review","Acceptance","Release"]);
  const conflicted = structuredClone(doc); conflicted.mission.runtime_root_state="CONFLICT";
  view.rerender(<ProjectWorkDetail document={conflicted} selection={BASE_SELECTION} locale="en" generation={2} resultPanel={<span>bound-result</span>} />);
  expect(screen.queryByText("bound-result")).toBeNull();
  expect(screen.getByText(/Source selection does not match/)).toBeTruthy();
});
