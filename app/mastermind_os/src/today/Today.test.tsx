// @vitest-environment jsdom
import { useState } from "react";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ProgramCard } from "../mission";
import { missionFixture } from "../test-fixtures";
import type { OfficeProjection, ReadSnapshot, SourceState } from "../meta-ceo/projection";
import type { TodayWorkState } from "./Today";
import { Today } from "./Today";

afterEach(cleanup);

const selection = { workRef: "WS:ALPHA", rootJobId: "JOB-ROOT" };

function snapshot<T>(value: T, state: SourceState = "CURRENT"): ReadSnapshot<T> {
  return {
    context: {
      authGeneration: 1, selection, sessionRef: "session-1", bindingGeneration: "binding-1",
      revisions: { mission: "rev:1", programs: "rev:1", result: "rev:1", conversation: "rev:1" },
    },
    source: { owner: "EXECUTIVE_OS", ref: "control:mission", revision: "rev:1", observed_at: "2026-09-20T10:01:00Z", state, coverage: "COMPLETE" },
    value,
  };
}

function projection(overrides: Partial<OfficeProjection> = {}): OfficeProjection {
  const mission = snapshot(missionFixture("WS:ALPHA", "JOB-ROOT"));
  mission.value!.read_state.state = "CURRENT";
  mission.value!.principal.owed_turn = null;
  const empty: OfficeProjection["result"] = {
    source: { owner: "EXECUTIVE_OS", ref: null, revision: null, observed_at: null, state: "UNAVAILABLE", coverage: "NOT_PROJECTED" },
    value: null, reason: "SOURCE_UNAVAILABLE",
  };
  return {
    schema: "mastermind.product_projection.v1",
    context: mission.context,
    mission: { source: mission.source, value: mission.value, reason: null },
    programs: { source: { owner: "AGENT_OS", ref: "control:projects", revision: "rev:1", observed_at: "2026-09-20T10:01:00Z", state: "UNAVAILABLE", coverage: "NOT_PROJECTED" }, value: null, reason: "SOURCE_UNAVAILABLE" },
    result: empty, conversation: empty as unknown as OfficeProjection["conversation"], companyTotal: null,
    receipts: { delivery: null, pickup: null, start: null, effect: null, return: null, review: null, acceptance: null },
    work: { state: "UNAVAILABLE", reason: "WORK_PENDING_CUSTODY" },
    direction: { state: "UNAVAILABLE", reason: "MISSING_PRODUCER" },
    ...overrides,
  };
}

function chairmanOwed(reason = "The owner has requested your attention.", refs?: Array<Partial<{ owner: string; ref: string; observed_at: string; freshness: string }>>) {
  const mission = missionFixture("WS:ALPHA", "JOB-ROOT");
  mission.read_state.state = "CURRENT";
  mission.principal.owed_turn = {
    seat: "chairman", reason,
    source_refs: (refs ?? [{ owner: "executive_inbox", ref: "ATTENTION-1", observed_at: "2026-09-20T10:01:00Z", freshness: "current" }]) as never,
  };
  return mission;
}

function programsRead(cards: ProgramCard[], state: SourceState = "CURRENT"): OfficeProjection["programs"] {
  return {
    source: { owner: "AGENT_OS", ref: "control:projects", revision: "rev:1", observed_at: "2026-09-20T10:01:00Z", state, coverage: "SUPPLIED_SCOPE" },
    value: state === "CURRENT" ? { programs: cards, state: "AVAILABLE", reason: "AVAILABLE" } : null,
    reason: null,
  };
}

const card: ProgramCard = { workRef: "WS:ALPHA", title: "Alpha program", state: "In review", nextAction: "Inspect returned evidence", nextActionWithheld: false, rootJobId: "JOB-ROOT", rootState: "RESOLVED", rootCandidates: ["JOB-ROOT"] };

function workState(overrides: Partial<{ availability: "AVAILABLE" | "UNAVAILABLE"; observation: "SAME" | "UNKNOWN"; root: string }> = {}): Extract<TodayWorkState, { kind: "DOCUMENT" }> {
  const root = overrides.root ?? "JOB-ROOT";
  const available = overrides.availability ?? "AVAILABLE";
  const observation = overrides.observation ?? "SAME";
  const digest = "a".repeat(64);
  return { kind: "DOCUMENT", document: {
    schema: "mastermind.workspace_work_queue.v1",
    generated_at: "2026-09-20T10:01:00Z",
    availability: available,
    lifecycle_source: available === "AVAILABLE" ? {
      schema: "mastermind.fabric_job_root_list.v2",
      runtime: { root: root, db_present: true, identity: "runtime-1", acquisition: {
        schema: "mastermind.fabric_runtime_acquisition.v1",
        query: { kind: "root_discovery", root_job_id: null },
        owner: "executive_runtime", snapshot_digest: digest,
        budgets: { roots: 64, jobs: 17, attempts_per_job: 20, attempts_total: 340, creation_events_per_job: 1 },
        truncation: { jobs: false, attempt_job_ids: [], roots: false, projection: false },
        provenance: { state: "COMPLETE", unjoined_job_ids: [] },
        generation: { schema: "mastermind.runtime_read_observation.v1", state: "SAME", source_identity: "runtime-1", before: 3, after: 3 },
      } },
      degraded: [],
    } : null,
    effect_exception: { value: "NONE", scope: "RUNTIME_CURRENT_WORKER", observable: false, reason: "no_exception_observed" },
    coverage: { count: available === "AVAILABLE" ? 1 : 0, total: available === "AVAILABLE" ? 1 : 0, truncated: false, completeness: available === "AVAILABLE" ? "COMPLETE" : "PARTIAL" },
    groups: {
      EFFECT_EXCEPTION: [], NEEDS_SOL: [], NEEDS_WORKER: [], WAITING_CAPACITY: [], RUNNING: [], QUEUED: [],
      COMPLETED_NOT_ACCEPTED: available === "AVAILABLE" ? [{
        root_job_id: root,
        lifecycle: { status: "COMPLETED", source: "EXECUTIVE_RUNTIME", orchestration_role: null, depth: 0 },
        next_actor: { value: "UNKNOWN", source: null, reason: "no_producer", evidence_ref: null, observed_at: null },
        capacity: { value: "NOT_APPLICABLE", source: "EXECUTIVE_RUNTIME", reason: "post_start_lifecycle", evidence_ref: null, observed_at: null },
        effect: { value: "NONE", source: "EFFECT_PRODUCER", reason: "evidence_supplied", evidence_ref: "job:effect", observed_at: "2026-09-20T10:01:00Z" },
        acceptance: { state: "NOT_PROJECTED", producer_owner: null, reason: "product acceptance has no producer in this projection" },
        group: "COMPLETED_NOT_ACCEPTED",
      }] : [],
      TERMINAL: [], UNKNOWN: [],
    },
    source_observation: {
      schema: "mastermind.workspace_source_observation.v1",
      state: observation,
      selection: null,
      control_room: available === "AVAILABLE" && observation === "SAME" ? {
        instance_before: "ci-1", instance_after: "ci-1", publication_before: 7, publication_after: 7,
        document_digest: digest, source_validity_digest: digest, cache_currentness_digest: digest,
      } : null,
      runtime: available === "AVAILABLE" && observation === "SAME" ? {
        schema: "mastermind.runtime_read_observation.v1", state: "SAME", source_identity: "runtime-1", before: 3, after: 3, snapshot_digest: digest,
      } : null,
    },
    reason_codes: available === "AVAILABLE" ? [] : ["source_unavailable"],
  } };
}

function renderToday(props: Partial<Parameters<typeof Today>[0]> = {}) {
  const onOpenInbox = vi.fn();
  const onOpenProjects = vi.fn();
  const onOpenMission = vi.fn();
  const composerAction = vi.fn();
  const view = render(<Today
    projection={projection({ programs: programsRead([card]) })}
    work={workState()}
    composer={<button type="button" onClick={composerAction}>Send direction</button>}
    onOpenInbox={onOpenInbox} onOpenProjects={onOpenProjects} onOpenMission={onOpenMission}
    {...props} />);
  return { view, onOpenInbox, onOpenProjects, onOpenMission, composerAction };
}

describe("Atelier Today", () => {
  it("renders the hero, the composer slot and drives no action on mount", () => {
    const { onOpenInbox, onOpenProjects, onOpenMission, composerAction } = renderToday();
    expect(screen.getByRole("heading", { name: "What would you like done?" })).toBeTruthy();
    expect(screen.getByText("Start something new, or continue an existing project.")).toBeTruthy();
    expect(screen.queryByText(/moving projects between owners/i)).toBeNull();
    expect(screen.getByRole("button", { name: "Send direction" })).toBeTruthy();
    expect(composerAction).not.toHaveBeenCalled();
    expect(onOpenInbox).not.toHaveBeenCalled();
    expect(onOpenProjects).not.toHaveBeenCalled();
    expect(onOpenMission).not.toHaveBeenCalled();
    // The slot stays interactive and is the only sender.
    fireEvent.click(screen.getByRole("button", { name: "Send direction" }));
    expect(composerAction).toHaveBeenCalledTimes(1);
    // No fake textarea or send control is invented by Today.
    expect(screen.queryByRole("textbox")).toBeNull();
    expect(screen.queryByRole("button", { name: /^send$/i })).toBeNull();
  });

  it("opens the exact supplied project tuple and keeps attention navigation read-only", () => {
    const mission = chairmanOwed();
    const { onOpenMission, onOpenInbox } = renderToday({
      projection: projection({ mission: { source: { ...snapshot(mission).source, coverage: "SUPPLIED_SCOPE" }, value: mission, reason: null } }),
    });
    expect(screen.getByText("Chairman request · Alpha program")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Open project" }));
    expect(onOpenMission).toHaveBeenCalledExactlyOnceWith({ workRef: "WS:ALPHA", rootJobId: "JOB-ROOT" });
    fireEvent.click(screen.getByRole("button", { name: "Open inbox" }));
    expect(onOpenInbox).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("button", { name: /approve|acknowledge|resend|send direction to team/i })).toBeNull();
  });

  it("never shows an all-clear when attention receipts are not current", () => {
    const receiptCases: Array<Array<Partial<{ owner: string; ref: string; observed_at: string | null; freshness: string }>>> = [
      [{ owner: "executive_inbox", ref: "ATTENTION-1", observed_at: "2026-09-20T10:01:00Z", freshness: "stale" }],
      [{ owner: "executive_inbox", ref: "ATTENTION-1", observed_at: null, freshness: "current" }],
      [{ owner: "", ref: "ATTENTION-1", observed_at: "2026-09-20T10:01:00Z", freshness: "current" }],
      [],
    ];
    for (const refs of receiptCases) {
      const mission = chairmanOwed("Hold delivery", refs as never);
      const rendered = renderToday({ projection: projection({ mission: { source: snapshot(mission).source, value: mission, reason: null } }) });
      expect(screen.getAllByText("Decisions")[0]).toBeTruthy();
      expect(screen.queryByText("Nothing needs your decision")).toBeNull();
      expect(screen.queryByRole("button", { name: "Open project" })).toBeNull();
      expect(screen.getByText("Decision information is unavailable right now.")).toBeTruthy();
      rendered.view.unmount();
    }
  });

  it.each<SourceState>(["STALE", "UNKNOWN", "UNAVAILABLE", "WITHHELD", "UNASSOCIATED"])(
    "shows unavailable attention for %s instead of a false all-clear", state => {
      const mission = chairmanOwed();
      const read = { source: { ...snapshot(mission).source, state }, value: state === "WITHHELD" || state === "UNAVAILABLE" ? null : mission, reason: `SOURCE_${state}` };
      renderToday({ projection: projection({ mission: read }) });
      expect(screen.getAllByText("Decisions")[0]).toBeTruthy();
      expect(screen.queryByText("Nothing needs your decision")).toBeNull();
      expect(screen.queryByText("Chairman request · Alpha program")).toBeNull();
      expect(screen.getByRole("button", { name: "Open inbox" })).toBeTruthy();
    });

  it.each(["UNKNOWN", "SUPPLIED_SCOPE", "NOT_PROJECTED", "INCOMPLETE"])("does not promote %s coverage to an all-clear", coverage => {
    const state = projection();
    state.mission.source.coverage = coverage;
    renderToday({projection:state});
    expect(screen.getAllByText("Decisions")[0]).toBeTruthy();
    expect(screen.queryByText("Nothing needs your decision")).toBeNull();
  });

  it("preserves the composer instance across source, work and locale presentation changes", () => {
    function Composer() {
      const [choice, setChoice] = useState("original");
      return <label>Owner choice<input value={choice} onChange={event=>setChoice(event.target.value)}/></label>;
    }
    const props = {projection:projection(),work:{kind:"PENDING"} as TodayWorkState,
      composer:<Composer/>,onOpenInbox:vi.fn(),onOpenProjects:vi.fn()};
    const view = render(<Today {...props}/>);
    fireEvent.change(screen.getByLabelText("Owner choice"), {target:{value:"user selection"}});
    const original = screen.getByLabelText("Owner choice");
    const next = projection(); next.context.revisions.programs = "rev:2";
    view.rerender(<Today {...props} projection={next} locale="zh-CN" work={{kind:"UNAVAILABLE",reason:"SOURCE_UNAVAILABLE"}}/>);
    expect(screen.getByLabelText("Owner choice")).toBe(original);
    expect((original as HTMLInputElement).value).toBe("user selection");
  });

  it("recognizes a currently receipted team-owned turn without inventing a human decision", () => {
    const mission = chairmanOwed(); mission.principal.owed_turn!.seat = "worker";
    renderToday({projection:projection({mission:{source:snapshot(mission).source,value:mission,reason:null}})});
    expect(screen.getByRole("heading",{name:"Your team owns the next step"})).toBeTruthy();
    expect(screen.getByText("Next turn · worker")).toBeTruthy();
    expect(screen.queryByRole("heading",{name:"Needs your decision"})).toBeNull();
    expect(screen.queryByText("Decision information is unavailable right now.")).toBeNull();
  });

  it("keeps a selected Mission effect-unknown warning visible even with a qualified attention request", () => {
    const mission = chairmanOwed();
    const state = projection({mission:{source:snapshot(mission).source,value:mission,reason:null}});
    state.receipts.effect = "EFFECT_UNKNOWN";
    renderToday({projection:state});
    expect(screen.getByRole("heading",{name:"Needs your decision"})).toBeTruthy();
    expect(screen.getByRole("alert").textContent).toContain("Don’t send it again");
    expect(screen.queryByText("Nothing needs your decision")).toBeNull();
  });

  it("states the bounded all-clear only with current, complete coverage", () => {
    const { onOpenMission } = renderToday();
    expect(screen.getByText("Nothing needs your decision")).toBeTruthy();
    expect(screen.getByText("This applies to this task only. Other project decisions may still be open.")).toBeTruthy();
    expect(onOpenMission).not.toHaveBeenCalled();
  });

  it("clicks a supplied project row with its exact work/root pair", () => {
    const { onOpenMission } = renderToday();
    fireEvent.click(screen.getByRole("button", { name: "Open project Alpha program" }));
    expect(onOpenMission).toHaveBeenCalledExactlyOnceWith({ workRef: "WS:ALPHA", rootJobId: "JOB-ROOT" });
  });

  it.each<ProgramCard>([
    { ...card, rootState: "CONFLICT", rootCandidates: ["JOB-ROOT", "JOB-OTHER"] },
    { ...card, rootState: "UNKNOWN", rootJobId: null, rootCandidates: [] },
    { ...card, rootCandidates: ["JOB-OTHER"] },
    { ...card, workRef: "../escape", rootJobId: "JOB/unsafe", rootCandidates: ["JOB/unsafe"] },
  ])("keeps ambiguous, missing or forged root identity non-actionable: %j", bad => {
    const { onOpenMission } = renderToday({ projection: projection({ programs: programsRead([bad]) }) });
    expect(screen.queryByRole("button", { name: /Open project/ })).toBeNull();
    expect(onOpenMission).not.toHaveBeenCalled();
  });

  it("offers stale programs only as retained facts without current navigation", () => {
    const { onOpenMission } = renderToday({ projection: projection({ programs: programsRead([card], "STALE") }) });
    expect(screen.getByText("Projects are unavailable right now.")).toBeTruthy();
    expect(screen.getByText("STALE")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Open project/ })).toBeNull();
    expect(onOpenMission).not.toHaveBeenCalled();
  });

  it("rejects duplicate supplied work references without choosing a row", () => {
    const { onOpenMission } = renderToday({ projection: projection({ programs: programsRead([card, { ...card, rootJobId: "JOB-ROOT" }]) }) });
    expect(screen.queryByRole("button", { name: /Open project/ })).toBeNull();
    expect(onOpenMission).not.toHaveBeenCalled();
  });

  it("clears prior content on a source-auth or selection rerender", () => {
    const mission = chairmanOwed();
    const first = projection({ mission: { source: snapshot(mission).source, value: mission, reason: null }, programs: programsRead([card]) });
    const { rerender } = render(<Today projection={first} work={workState()}
      composer={<button type="button">Send direction</button>}
      onOpenInbox={vi.fn()} onOpenProjects={vi.fn()} onOpenMission={vi.fn()} />);
    expect(screen.getByText("Chairman request · Alpha program")).toBeTruthy();
    // New auth epoch: the old principal's attention must not survive.
    const withheld = projection({ mission: { ...first.mission, source: { ...first.mission.source, state: "WITHHELD" as SourceState }, value: null, reason: "AUTH_GENERATION_CHANGED" } });
    withheld.context = { ...withheld.context, authGeneration: 2 };
    rerender(<Today projection={withheld} work={workState()}
      composer={<button type="button">Send direction</button>}
      onOpenInbox={vi.fn()} onOpenProjects={vi.fn()} onOpenMission={vi.fn()} />);
    expect(screen.queryByText("Chairman request · Alpha program")).toBeNull();
    expect(screen.queryByRole("button", { name: /Open project/ })).toBeNull();
    expect(screen.getAllByText("Decisions")[0]).toBeTruthy();
    // A different selected mission also clears prior scope markers.
    const moved = projection({ programs: programsRead([card]) });
    moved.context = { ...moved.context, selection: { workRef: "WS:BETA", rootJobId: "JOB-ROOT" } };
    rerender(<Today projection={moved} work={workState()}
      composer={<button type="button">Send direction</button>}
      onOpenInbox={vi.fn()} onOpenProjects={vi.fn()} onOpenMission={vi.fn()} />);
    expect(screen.queryByText("Chairman request · Alpha program")).toBeNull();
    expect(screen.queryByText("Selected project")).toBeNull();
    expect(screen.getByText("Work status is unavailable until a task can be identified.")).toBeTruthy();
  });

  it("summarizes work only from a decoded AVAILABLE document observed SAME, per exact root", () => {
    const { view } = renderToday({ work: workState() });
    expect(screen.getByText("1 work root supplied")).toBeTruthy();
    const rootPanel = screen.getByText("Selected mission root").closest("div")!;
    expect(within(rootPanel).getByText("JOB-ROOT")).toBeTruthy();
    expect(within(rootPanel).getByText("COMPLETED")).toBeTruthy();
    expect(screen.queryByText(/company total:\s*\d+|all \d+ projects/i)).toBeNull();
    // An unrelated root is never promoted into the selected project's lifecycle.
    view.rerender(<Today projection={projection({ programs: programsRead([card]) })} work={workState({ root: "JOB-UNRELATED" })}
      composer={<button type="button">Send direction</button>}
      onOpenInbox={vi.fn()} onOpenProjects={vi.fn()} onOpenMission={vi.fn()} />);
    expect(screen.getByText("The selected mission's root is not present in the supplied work queue.")).toBeTruthy();
    expect(screen.queryByText("COMPLETED")).toBeNull();
  });

  it("does not turn unknown, partial or unavailable work into a zero summary", () => {
    const { rerender } = render(<Today projection={projection({ programs: programsRead([card]) })} work={{ kind: "PENDING" }}
      composer={<button type="button">Send direction</button>}
      onOpenInbox={vi.fn()} onOpenProjects={vi.fn()} onOpenMission={vi.fn()} />);
    expect(screen.getByText("Work details are not available yet.")).toBeTruthy();
    rerender(<Today projection={projection({ programs: programsRead([card]) })} work={{ kind: "UNAVAILABLE", reason: "WORK_PENDING_CUSTODY" }}
      composer={<button type="button">Send direction</button>}
      onOpenInbox={vi.fn()} onOpenProjects={vi.fn()} onOpenMission={vi.fn()} />);
    expect(screen.getByText("Work details are unavailable for this task.")).toBeTruthy();
    rerender(<Today projection={projection({ programs: programsRead([card]) })} work={workState({ availability: "UNAVAILABLE" })}
      composer={<button type="button">Send direction</button>}
      onOpenInbox={vi.fn()} onOpenProjects={vi.fn()} onOpenMission={vi.fn()} />);
    expect(screen.getByText("Work details are unavailable for this task.")).toBeTruthy();
    expect(screen.getByText("source_unavailable")).toBeTruthy();
    rerender(<Today projection={projection({ programs: programsRead([card]) })} work={workState({ observation: "UNKNOWN" })}
      composer={<button type="button">Send direction</button>}
      onOpenInbox={vi.fn()} onOpenProjects={vi.fn()} onOpenMission={vi.fn()} />);
    expect(screen.getByText("Work details are unavailable for this task.")).toBeTruthy();
    expect(screen.queryByText("COMPLETED")).toBeNull();
    expect(screen.queryByText(/0 work roots/)).toBeNull();
  });

  it("keeps runtime details closed and labels its generated clock honestly", () => {
    const {view} = renderToday();
    const details = view.container.querySelector(".today-work-details") as HTMLDetailsElement;
    expect(details.open).toBe(false);
    expect(details.querySelector("h2")?.closest("details")).toBe(details);
    fireEvent.click(screen.getByText("Work and source details"));
    expect(details.open).toBe(true);
    const clock = within(details).getByText("Generated at").closest("dl")!;
    expect(clock.textContent).toContain("Generated at");
    expect(clock.textContent).toContain("2026-09-20T10:01:00Z");
    const observed = within(details).getByText("Observed");
    expect(observed.nextElementSibling?.textContent).toBe("Not supplied");
  });

  it("keeps a qualified work exception visible while runtime details are closed", () => {
    const work = workState(); work.document.effect_exception.value = "EFFECT_UNKNOWN";
    const {view} = renderToday({work});
    const warning = view.container.querySelector(".today-side > [role='alert']");
    expect(warning?.textContent).toContain("Don’t send it again");
    expect(warning?.closest("details")).toBeNull();
    expect((view.container.querySelector(".today-work-details") as HTMLDetailsElement).open).toBe(false);
  });

  it("keeps work-source and selected-row effect enums distinct behind the plain warning", () => {
    const work = workState();
    const row = work.document.groups.COMPLETED_NOT_ACCEPTED.pop()!;
    row.effect.value = "EFFECT_UNKNOWN"; row.group = "EFFECT_EXCEPTION";
    work.document.groups.EFFECT_EXCEPTION.push(row);
    const {view} = renderToday({work});
    const warning = view.container.querySelector(".today-side > [role='alert']");
    expect(warning?.textContent).toContain("Don’t send it again");
    const details = view.container.querySelector(".today-work-details")!;
    expect(within(details as HTMLElement).getByText("Work source exception").nextElementSibling?.textContent).toBe("NONE");
    expect(within(details as HTMLElement).getByText("Selected task effect").nextElementSibling?.textContent).toBe("EFFECT_UNKNOWN");
  });

  it("limits Today to three projects in supplied order without losing View all", () => {
    const cards = Array.from({length:8},(_,i)=>({...card,workRef:`WS:PROJECT-${i}`,title:`Project ${i}`}));
    const {onOpenProjects} = renderToday({projection:projection({programs:programsRead(cards)})});
    const rows = screen.getAllByRole("listitem");
    expect(rows).toHaveLength(3);
    expect(rows.map(row=>row.textContent)).toEqual([expect.stringContaining("Project 0"),expect.stringContaining("Project 1"),expect.stringContaining("Project 2")]);
    expect(screen.getByText("8 projects supplied")).toBeTruthy();
    fireEvent.click(screen.getByRole("button",{name:"View all"}));
    expect(onOpenProjects).toHaveBeenCalledTimes(1);
  });

  it("navigates to Projects from View all and keeps read navigation available", () => {
    const { onOpenProjects } = renderToday({ projection: projection({ programs: programsRead([], "UNAVAILABLE") }) });
    fireEvent.click(screen.getByRole("button", { name: "View all" }));
    expect(onOpenProjects).toHaveBeenCalledTimes(1);
  });

  it("translates labels without losing navigation or truthful states", () => {
    const { onOpenMission } = renderToday({
      locale: "zh-CN",
      projection: projection({
        mission: (() => { const m = chairmanOwed("请审阅返回的证据"); return { source: snapshot(m).source, value: m, reason: null }; })(),
        programs: programsRead([card]),
      }),
    });
    expect(screen.getByRole("heading", { name: "您想完成什么？" })).toBeTruthy();
    expect(screen.getByText("需要您决策")).toBeTruthy();
    expect(screen.getByText("董事长请求 · Alpha program")).toBeTruthy();
    expect(screen.getByRole("button", { name: "打开项目" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "打开收件箱" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "查看全部" })).toBeTruthy();
    expect(screen.getByText("1 个已提供项目")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "打开项目" }));
    expect(onOpenMission).toHaveBeenCalledExactlyOnceWith({ workRef: "WS:ALPHA", rootJobId: "JOB-ROOT" });
    expect(screen.queryByText("Nothing needs your decision")).toBeNull();
    expect(screen.queryByText("Decision information is unavailable right now.")).toBeNull();
  });

  it("keeps receipt semantics visible compactly without inventing new facts", () => {
    renderToday();
    fireEvent.click(screen.getByText("Work and source details"));
    const summary = screen.getByText("Delivery, pickup, start, effect, return, review and acceptance receipts");
    fireEvent.click(summary);
    expect(screen.getAllByText("NOT_PROJECTED")).toHaveLength(7);
    expect(screen.queryByText(/worker assigned|queue healthy|3 projects/i)).toBeNull();
  });
});
