// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import type { ChildCard, Missionv3Document } from "../mission";
import fixture from "../fixtures/mission-v3-owner-current-operator-harness.json";
import { FabricMissionInspector } from "./FabricMissionInspector";
import { matchesFilter, MAX_INSPECTED_CHILDREN, missionInteriors } from "./mission-interiors";

afterEach(cleanup);
function child(id = "JOB-2", overrides: Partial<ChildCard> = {}): ChildCard {
  return { job_id: id, parent_job_id: "JOB-1", status: "RUNNING", depth: 1, orchestration_role: "work", plan_step_id: "step-1",
    worker_id: "worker-observed-1", attempt_count: 2, attempt_limit: 3, current_attempt_id: "ATT-" + "a".repeat(32),
    latest_attempt: { attempt_id: "ATT-" + "a".repeat(32), attempt_number: 2, status: "RUNNING", started_at: "2026-10-13T12:00:00Z",
      finished_at: null, exit_code: null, has_result: false, error_present: false, error_class: null }, ...overrides };
}
function doc(children = [child()]): Missionv3Document {
  const d = structuredClone(fixture) as unknown as Missionv3Document;
  d.mission.root_job_id = "JOB-1"; d.mission.runtime_root_state = "RESOLVED"; d.mission.root_job_ambiguous = false;
  d.read_state.state = "CURRENT";
  d.children = { state: "AVAILABLE", coverage: "COMPLETE", reason_codes: [], items: children, total_count: children.length,
    overflow_count: 0, unjoined_job_count: 0, unjoined_job_ids: [] };
  d.review.verdict = "NOT_YET"; d.acceptance.state = "NOT_PROJECTED";
  return d;
}
const detail = () => within(screen.getByRole("complementary", { name: "Selected worker" }));
const pick = (id = "JOB-2") => fireEvent.click(screen.getByRole("button", { name: new RegExp(`^${id} `) }));

describe("owner-backed Fabric interiors", () => {
  it("uses actual parent IDs rather than asserted depth", () => {
    const m = missionInteriors(doc([child(), child("JOB-3", { parent_job_id: "JOB-2", depth: 99 })]));
    expect(m.rows[1].lineage).toEqual(["JOB-1", "JOB-2", "JOB-3"]);
    expect(m.running).toBe(2);
  });
  it("does not make a missing parent a root child", () => {
    const m = missionInteriors(doc([child("JOB-2", { parent_job_id: "JOB-90" })]));
    expect(m.rows[0].problem).toBe("PARENT_NOT_OBSERVED"); expect(m.running).toBe(0);
    expect(matchesFilter(m.rows[0], "problems")).toBe(true);
  });
  it("detects cycles without hanging", () => {
    const m = missionInteriors(doc([child("JOB-2", { parent_job_id: "JOB-3" }), child("JOB-3", { parent_job_id: "JOB-2" })]));
    expect(m.unassociated).toBe(2); expect(m.rows[0].problem).toBe("PARENT_CYCLE");
  });
  it("quarantines duplicate identities and their descendants", () => {
    const m = missionInteriors(doc([child(), child(), child("JOB-3", { parent_job_id: "JOB-2" })]));
    expect(m.unassociated).toBe(3); expect(m.running).toBe(0);
  });
  it("does not count queued or completed work as running", () => {
    const m = missionInteriors(doc([child("JOB-2", { status: "QUEUED" }), child("JOB-3", { status: "COMPLETED" })]));
    expect(m.running).toBe(0); expect(m.results).toBe(0);
  });
  it("refuses inferred root membership on root conflict", () => {
    const d = doc(); d.mission.root_job_ambiguous = true;
    expect(missionInteriors(d).rows[0].problem).toBe("ROOT_NOT_QUALIFIED");
  });
  it("does not report zero active workers when a supplied root is conflicted", () => {
    const d = doc(); d.mission.runtime_root_state = "CONFLICT";
    render(<FabricMissionInspector mission={d} />);
    expect(screen.getByText("Observed running").querySelector("strong")?.textContent).toBe("Unknown");
    expect(screen.getAllByText("With results").map(el => el.querySelector("strong")?.textContent).find(Boolean)).toBe("Unknown");
    expect(screen.getByText(/Current activity counts are unknown/)).toBeTruthy();
  });
  it("reports totals only when source time, coverage and parent chains are qualified", () => {
    const d = doc();
    const view = render(<FabricMissionInspector mission={d} />);
    expect(screen.getByText("Observed running").querySelector("strong")?.textContent).toBe("1");
    const orphan = doc([child("JOB-2", { parent_job_id: "JOB-99" })]);
    view.rerender(<FabricMissionInspector mission={orphan} />);
    expect(screen.getByText("Observed running").querySelector("strong")?.textContent).toBe("Unknown");
    const historical = doc(); historical.read_state.state = "HISTORICAL";
    view.rerender(<FabricMissionInspector mission={historical} />);
    expect(screen.getByText("Observed running").querySelector("strong")?.textContent).toBe("Unknown");
    const partial = doc(); partial.children.coverage = "INCOMPLETE";
    view.rerender(<FabricMissionInspector mission={partial} />);
    expect(screen.getByText("Observed running").querySelector("strong")?.textContent).toBe("Unknown");
  });
  it("bounds visible rows and exposes local truncation", () => {
    const d = doc(Array.from({ length: 270 }, (_, i) => child(`JOB-${i+2}`)));
    const m = missionInteriors(d); expect(m.rows).toHaveLength(MAX_INSPECTED_CHILDREN); expect(m.locallyOmitted).toBe(14);
  });
  it("does not translate unavailable source to a zero-worker claim", () => {
    render(<FabricMissionInspector mission={null} />);
    expect(screen.getByRole("status").textContent).toContain("not a zero-worker");
    expect(screen.queryByText("Observed running")).toBeNull();
  });
  it("shows typed unavailable child source without exposing worker buttons", () => {
    const d = doc(); d.children.state = "UNAVAILABLE";
    render(<FabricMissionInspector mission={d} />);
    expect(screen.getByText("Worker list unavailable.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /^JOB-2 / })).toBeNull();
  });
  it("discloses historical/partial coverage and unknown denominators", () => {
    const d = doc(); d.read_state.state = "HISTORICAL"; d.children.coverage = "INCOMPLETE";
    d.children.total_count = null; d.children.overflow_count = 6; d.children.unjoined_job_count = null;
    render(<FabricMissionInspector mission={d} />);
    expect(screen.getByText("Source · HISTORICAL")).toBeTruthy();
    expect(screen.getByText(/Owner total Unknown/)).toBeTruthy();
    expect(screen.getByText("Omitted by owner 6")).toBeTruthy();
    expect(screen.getByText(/Direct M2 Fabric workers/)).toBeTruthy();
  });
  it("opens the exact attempt and preserves selection when rows reorder", () => {
    const d = doc([child(), child("JOB-3", { worker_id: "another-worker" })]);
    const view = render(<FabricMissionInspector mission={d} />); pick();
    expect(detail().getByText("worker-observed-1")).toBeTruthy();
    d.children.items.reverse(); view.rerender(<FabricMissionInspector mission={d} />);
    expect(detail().getByText("worker-observed-1")).toBeTruthy();
    expect(detail().getByText("2026-10-13T12:00:00Z")).toBeTruthy();
  });
  it("drops selected details immediately on root change and disappearance", () => {
    const d = doc(); const view = render(<FabricMissionInspector mission={d} />); pick();
    const next = doc(); next.mission.root_job_id = "JOB-9";
    view.rerender(<FabricMissionInspector mission={next} />);
    expect(detail().queryByText("worker-observed-1")).toBeNull();
    view.rerender(<FabricMissionInspector mission={doc([])} />);
    expect(detail().queryByText("worker-observed-1")).toBeNull();
  });
  it("filters without issuing effects and hides an out-of-filter detail", () => {
    render(<FabricMissionInspector mission={doc([child(), child("JOB-3", { status: "FAILED" })])} />); pick();
    fireEvent.click(screen.getByRole("button", { name: "Problems" }));
    expect(screen.queryByRole("button", { name: /^JOB-2 / })).toBeNull();
    expect(screen.getByRole("button", { name: /^JOB-3 / })).toBeTruthy();
    expect(detail().queryByText("2026-10-13T12:00:00Z")).toBeNull();
  });
  it("does not attribute latest-attempt results to a different current attempt", () => {
    const c = child(); c.latest_attempt!.attempt_id = "ATT-" + "b".repeat(32); c.latest_attempt!.has_result = true;
    const d = doc([c]); d.execution.state = "COMPLETED";
    render(<FabricMissionInspector mission={d} />); pick();
    expect(detail().getByText(/Latest attempt is not the current attempt/)).toBeTruthy();
    expect(screen.getByText("NOT_PROJECTED")).toBeTruthy();
    expect(screen.getByText(/not acceptance of each child/)).toBeTruthy();
  });
  it("navigates source-qualified immediate parent and children inside the supplied mission only", () => {
    const rootChild = child("JOB-2", { worker_id: "worker-parent" });
    const grandChild = child("JOB-3", { parent_job_id: "JOB-2", worker_id: "worker-leaf" });
    render(<FabricMissionInspector mission={doc([grandChild, rootChild])} />);
    pick("JOB-2");
    expect(detail().getByRole("button", { name: "View observed child: JOB-3" })).toBeTruthy();
    fireEvent.click(detail().getByRole("button", { name: "View observed child: JOB-3" }));
    expect(detail().getByText("worker-leaf")).toBeTruthy();
    expect(detail().getByText("JOB-1 → JOB-2 → JOB-3")).toBeTruthy();
    fireEvent.click(detail().getByRole("button", { name: "View observed parent: JOB-2" }));
    expect(detail().getByText("worker-parent")).toBeTruthy();
    expect(detail().queryByRole("button", { name: "View observed parent: JOB-1" })).toBeNull();
  });
  it("resets a restrictive worker filter to reach a verified relative but does not dispatch", () => {
    const one = child("JOB-2", { status: "FAILED" });
    const two = child("JOB-3", { parent_job_id: "JOB-2", status: "RUNNING" });
    render(<FabricMissionInspector mission={doc([one, two])} />);
    fireEvent.click(screen.getByRole("button", { name: "Problems" }));
    pick("JOB-2");
    fireEvent.click(detail().getByRole("button", { name: "View observed child: JOB-3" }));
    expect(screen.getByRole("button", { name: "All" }).getAttribute("aria-pressed")).toBe("true");
    expect(detail().getByText("JOB-1 → JOB-2 → JOB-3")).toBeTruthy();
  });
  it("does not navigate through unavailable or conflicted lineage", () => {
    const d = doc([child("JOB-2", { parent_job_id: "JOB-3" }), child("JOB-3", { parent_job_id: "JOB-2" })]);
    const view = render(<FabricMissionInspector mission={d} />);
    pick("JOB-2");
    expect(detail().queryByRole("button", { name: /^View observed (parent|child)/ })).toBeNull();
    const conflict = doc([child("JOB-2"), child("JOB-3", { parent_job_id: "JOB-2" })]);
    conflict.mission.root_job_ambiguous = true;
    view.rerender(<FabricMissionInspector mission={conflict} />);
    pick("JOB-2");
    expect(detail().queryByRole("button", { name: /^View observed (parent|child)/ })).toBeNull();
  });
  it("clears previously selected worker and filter on a different mission root", () => {
    const rootOne = doc([child("JOB-2", { status: "FAILED" })]);
    const view = render(<FabricMissionInspector mission={rootOne} />);
    fireEvent.click(screen.getByRole("button", { name: "Problems" }));
    pick("JOB-2");
    const rootTwo = doc([child("JOB-8", { parent_job_id: "JOB-9", status: "RUNNING" })]);
    rootTwo.mission.root_job_id = "JOB-9";
    view.rerender(<FabricMissionInspector mission={rootTwo} />);
    expect(detail().queryByText("worker-observed-1")).toBeNull();
    expect(screen.getByRole("button", { name: "All" }).getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByRole("button", { name: /^JOB-8 / })).toBeTruthy();
  });
  it("does not treat a validated parent after the display cap as a displayed navigation target", () => {
    const members = Array.from({length:270},(_,index)=>child("JOB-"+(index+2)));
    members[0].parent_job_id = "JOB-260";
    const d=doc(members);
    const view=render(<FabricMissionInspector mission={d} />);
    pick("JOB-2");
    // The companion #1435 decoder repair may prove ancestry using the full
    // supplied source. It must not produce an invisible/off-cap action.
    expect(detail().queryByRole("button",{name:"View observed parent: JOB-260"})).toBeNull();
  });
  it("opens only the exact indexed, unvalidated result from the selected current Mission worker", () => {
    const sample = doc();
    const ref = sample.result_refs.refs[0];
    const c = child(ref.job_id, { parent_job_id: ref.root_job_id, status: "COMPLETED",
      orchestration_role: ref.orchestration_role, current_attempt_id: ref.attempt_id,
      latest_attempt: { ...child().latest_attempt!, attempt_id: ref.attempt_id,
        has_result: true, status: "COMPLETED", finished_at: "2026-10-15T17:00:00Z" } });
    sample.mission.root_job_id = ref.root_job_id; sample.children.items = [c];
    const opened = vi.fn();
    render(<FabricMissionInspector mission={sample} onInspectResult={opened} />);
    pick(ref.job_id);
    fireEvent.click(detail().getByRole("button", { name: "Inspect indexed result" }));
    expect(opened).toHaveBeenCalledTimes(1);
    expect(opened).toHaveBeenCalledWith({
      workRef: sample.program.work_ref, rootJobId: ref.root_job_id,
      jobId: ref.job_id, attemptId: ref.attempt_id, resultEnvelopeDigest: ref.result_envelope_digest,
    });
    expect(detail().getByText(/UNVALIDATED/)).toBeTruthy();
  });
  it("distinguishes an exact reference from a missing authorized reader", () => {
    const sample = doc(), ref = sample.result_refs.refs[0];
    sample.mission.root_job_id = ref.root_job_id;
    sample.children.items = [child(ref.job_id, {
      parent_job_id: ref.root_job_id, status: "COMPLETED",
      orchestration_role: ref.orchestration_role,
      current_attempt_id: ref.attempt_id,
      latest_attempt: { ...child().latest_attempt!, attempt_id: ref.attempt_id,
        status: "COMPLETED", has_result: true },
    })];
    render(<FabricMissionInspector mission={sample} />);
    pick(ref.job_id);
    expect(detail().queryByRole("button", { name: "Inspect indexed result" })).toBeNull();
    expect(detail().getByText(/exact result reference exists, but no authorized result reader/)).toBeTruthy();
  });
  it("hides the result read when its apparent worker result lacks exact source-index evidence", () => {
    const sample = doc();
    const ref = sample.result_refs.refs[0];
    sample.mission.root_job_id = ref.root_job_id;
    const c = child(ref.job_id, { parent_job_id: ref.root_job_id, status: "COMPLETED",
      current_attempt_id: "ATT-" + "a".repeat(32),
      latest_attempt: { ...child().latest_attempt!, has_result: true,
        attempt_id: "ATT-" + "a".repeat(32), status: "COMPLETED" } });
    sample.children.items = [c];
    const opened = vi.fn(); const view = render(<FabricMissionInspector mission={sample} onInspectResult={opened} />);
    pick(ref.job_id);
    expect(detail().queryByRole("button", { name: "Inspect indexed result" })).toBeNull();
    expect(detail().getByText(/No exact result reference is available/)).toBeTruthy();
    sample.result_refs.generation.state = "CONFLICT";
    view.rerender(<FabricMissionInspector mission={sample} onInspectResult={opened} />);
    expect(detail().queryByRole("button", { name: "Inspect indexed result" })).toBeNull();
    expect(opened).not.toHaveBeenCalled();
  });
  it("keeps the latest returned attempt distinct from the current attempt when inspecting its indexed result", () => {
    const sample = doc(); const ref = sample.result_refs.refs[0];
    sample.mission.root_job_id = ref.root_job_id;
    const c = child(ref.job_id, { parent_job_id: ref.root_job_id, orchestration_role: ref.orchestration_role,
      current_attempt_id: "ATT-" + "f".repeat(32),
      latest_attempt: { ...child().latest_attempt!, attempt_id: ref.attempt_id,
        status: "COMPLETED", has_result: true } });
    sample.children.items = [c];
    const opened = vi.fn();
    render(<FabricMissionInspector mission={sample} onInspectResult={opened} />);
    pick(ref.job_id);
    expect(detail().getByText(/Latest attempt is not the current attempt/)).toBeTruthy();
    fireEvent.click(detail().getByRole("button", { name: "Inspect indexed result" }));
    expect(opened.mock.calls[0][0].attemptId).toBe(ref.attempt_id);
    expect(opened.mock.calls[0][0].attemptId).not.toBe(c.current_attempt_id);
  });
  it("keeps unknown attempt fields unknown and supports the current app locale", () => {
    const c = child(); c.latest_attempt = null;
    render(<FabricMissionInspector mission={doc([c])} locale="zh-CN" />); pick();
    expect(screen.getByRole("heading", { name: "任务内部状态" })).toBeTruthy();
    expect(screen.getAllByText("未知").length).toBeGreaterThan(2);
  });
});
