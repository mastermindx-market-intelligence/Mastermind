import { describe, expect, it } from "vitest";
import { decodeMission, decodeMissionv3, type ChildCard, type MissionDocument } from "../mission";
import fixture from "../fixtures/mission-v2-current-128c46f6.json";
import ownerFixture from "../fixtures/mission-v3-owner-current-operator-harness.json";
import { matchesFilter, MAX_INSPECTED_CHILDREN, missionInteriors } from "./mission-interiors";

const selection = { workRef: "WS:ONE", rootJobId: "JOB-1" };
function child(id: string, overrides: Partial<ChildCard> = {}): ChildCard {
  return { job_id: id, parent_job_id: selection.rootJobId, status: "QUEUED", depth: 1,
    orchestration_role: "work", plan_step_id: null, worker_id: null, attempt_count: 0,
    attempt_limit: 3, current_attempt_id: null, latest_attempt: null, ...overrides };
}
function documentFor(children: ChildCard[]): MissionDocument {
  const raw = structuredClone(fixture) as unknown as MissionDocument;
  raw.children = { state: children.length ? "AVAILABLE" : "EMPTY", coverage: "COMPLETE",
    reason_codes: [], items: children, total_count: children.length, overflow_count: 0,
    unjoined_job_count: 0, unjoined_job_ids: [] };
  return raw;
}
function admitted(children: ChildCard[]): MissionDocument {
  const decoded = decodeMission(documentFor(children), selection);
  expect(decoded, "the canonical decoder must admit this source").not.toBeNull();
  return decoded!;
}
function boundary(parentIndex: number) {
  const children = Array.from({ length: parentIndex + 1 }, (_, i) => child(`JOB-${i + 10}`));
  children[0] = child("JOB-2", { parent_job_id: "JOB-3", depth: 2, status: "RUNNING",
    current_attempt_id: "ATT-2", attempt_count: 1,
    latest_attempt: { attempt_id: "ATT-2", attempt_number: 1, status: "COMPLETED",
      started_at: "2026-10-13T12:00:00Z", finished_at: "2026-10-13T12:01:00Z",
      exit_code: 0, has_result: true, error_present: false, error_class: null } });
  children[parentIndex] = child("JOB-3", { status: "RUNNING" });
  return children;
}

describe("Fabric lineage across the display boundary", () => {

  it("preserves every visible lineage at the admitted 500-child source limit", () => {
    const leaves = Array.from({ length: 256 }, (_, i) => child(`JOB-${i + 10}`, {
      parent_job_id: "JOB-7000", depth: 245, status: "RUNNING" }));
    const ancestors = Array.from({ length: 244 }, (_, i) => child(`JOB-${i + 7000}`, {
      parent_job_id: i === 243 ? "JOB-1" : `JOB-${i + 7001}`, depth: 244 - i }));
    const model = missionInteriors(admitted([...leaves, ...ancestors]));
    expect(model.rows).toHaveLength(256); expect(model.running).toBe(256);
    expect(model.locallyOmitted).toBe(244); expect(model.unassociated).toBe(0);
    for (const row of model.rows) {
      expect(row.lineage).toHaveLength(246);
      expect(row.lineage[0]).toBe("JOB-1"); expect(row.lineage[1]).toBe("JOB-7243");
      expect(row.lineage.at(-2)).toBe("JOB-7000"); expect(row.lineage.at(-1)).toBe(row.child.job_id);
    }
  });
  it("qualifies the same cutoff case through the live v3 owner-observation decoder", () => {
    const raw = structuredClone(ownerFixture);
    raw.children = { ...documentFor(boundary(256)).children,
      items: boundary(256).map(row => ({ ...row, parent_job_id: row.parent_job_id === "JOB-1" ? "JOB-001" : row.parent_job_id })) } as typeof raw.children;
    raw.result_refs = { ...raw.result_refs, availability: "PARTIAL", refs: [],
      absent_job_ids: ["JOB-001"], omitted_job_ids: [], truncated: true };
    const decoded = decodeMissionv3(raw, { workRef: "WS:ONE", rootJobId: "JOB-001" });
    expect(decoded).not.toBeNull();
    const model = missionInteriors(decoded);
    expect(model.rows).toHaveLength(256); expect(model.locallyOmitted).toBe(1);
    expect(model.rows[0].lineage).toEqual(["JOB-001", "JOB-3", "JOB-2"]);
    expect(model.running).toBe(1); expect(model.results).toBe(1);
  });
  it.each([255, 256, 499])("uses a decoded parent at source index %i without extending the rendered list", parentIndex => {
    const doc = admitted(boundary(parentIndex));
    const before = JSON.stringify(doc);
    const model = missionInteriors(doc);
    expect(model.rows).toHaveLength(Math.min(parentIndex + 1, MAX_INSPECTED_CHILDREN));
    expect(model.rows[0].lineage).toEqual(["JOB-1", "JOB-3", "JOB-2"]);
    expect(model.rows[0].association).toBe("ASSOCIATED");
    expect(model.rows[0].problem).toBeNull();
    expect(model.running).toBe(parentIndex < MAX_INSPECTED_CHILDREN ? 2 : 1);
    expect(model.results).toBe(1);
    expect(model.problems).toBe(0);
    expect(model.locallyOmitted).toBe(Math.max(0, parentIndex + 1 - MAX_INSPECTED_CHILDREN));
    expect(matchesFilter(model.rows[0], "running")).toBe(true);
    expect(matchesFilter(model.rows[0], "results")).toBe(true);
    expect(matchesFilter(model.rows[0], "problems")).toBe(false);
    expect(JSON.stringify(doc)).toBe(before);
  });
  it("follows several supplied ancestors beyond the visible slice", () => {
    const children = boundary(258);
    children[0].depth = 4;
    children[258].parent_job_id = "JOB-4"; children[258].depth = 3;
    children[257] = child("JOB-4", { parent_job_id: "JOB-5", depth: 2 });
    children[256] = child("JOB-5");
    const model = missionInteriors(admitted(children));
    expect(model.rows[0].lineage).toEqual(["JOB-1", "JOB-5", "JOB-4", "JOB-3", "JOB-2"]);
    expect(model.rows[0].association).toBe("ASSOCIATED");
    expect(model.running).toBe(1); expect(model.locallyOmitted).toBe(3);
  });
  it("keeps displayed-worker counts independent of hidden workers and their output", () => {
    const children = boundary(499);
    children[499].latest_attempt = { ...children[0].latest_attempt!, attempt_id: "ATT-3" };
    children[499].current_attempt_id = "ATT-3"; children[499].attempt_count = 1;
    const model = missionInteriors(admitted(children));
    expect(model.rows).toHaveLength(256); expect(model.running).toBe(1); expect(model.results).toBe(1);
    expect(model.rows.some(row => row.child.job_id === "JOB-3")).toBe(false);
  });
  it("retains the decoder's 500-child limit and refuses 501 children", () => {
    expect(decodeMission(documentFor(boundary(499)), selection)).not.toBeNull();
    expect(decodeMission(documentFor(boundary(500)), selection)).toBeNull();
  });
  it.each(["missing", "duplicate", "cycle", "depth"])("keeps the canonical decoder's %s-parent rejection", kind => {
    const children = boundary(257);
    if (kind === "missing") children[257].parent_job_id = "JOB-999999";
    if (kind === "duplicate") children[256] = { ...children[257] };
    if (kind === "cycle") children[257].parent_job_id = "JOB-2";
    if (kind === "depth") children[257].depth = 8;
    expect(decodeMission(documentFor(children), selection)).toBeNull();
  });
  it("keeps actually absent parents unassociated in defensive direct input", () => {
    const doc = documentFor(boundary(256)); doc.children.items.pop();
    const model = missionInteriors(doc);
    expect(model.rows[0].problem).toBe("PARENT_NOT_OBSERVED"); expect(model.running).toBe(0);
    expect(model.results).toBe(0); expect(matchesFilter(model.rows[0], "problems")).toBe(true);
  });
  it("quarantines a duplicate parent outside the display slice and its visible descendant", () => {
    const children = boundary(257); children[256] = { ...children[257] };
    const model = missionInteriors(documentFor(children));
    expect(model.rows[0].problem).toBe("IDENTITY_CONFLICT");
    expect(model.rows[0].association).toBe("UNASSOCIATED"); expect(model.running).toBe(0);
  });
  it("terminates cycles involving an omitted parent", () => {
    const children = boundary(256); children[256].parent_job_id = "JOB-2";
    const model = missionInteriors(documentFor(children));
    expect(model.rows[0].problem).toBe("PARENT_CYCLE"); expect(model.running).toBe(0);
  });
  it.each(["mission-unavailable", "children-unavailable", "root-conflict", "root-unknown"])("does not restore lineage through %s", kind => {
    const doc = documentFor(boundary(256));
    if (kind === "mission-unavailable") doc.read_state.state = "UNAVAILABLE";
    if (kind === "children-unavailable") doc.children.state = "UNAVAILABLE";
    if (kind === "root-conflict") doc.mission.root_job_ambiguous = true;
    if (kind === "root-unknown") doc.mission.runtime_root_state = "UNKNOWN";
    const model = missionInteriors(doc);
    expect(model.rows[0].problem).toBe("ROOT_NOT_QUALIFIED"); expect(model.running).toBe(0);
    expect(model.results).toBe(0); expect(model.rows[0].lineage).toEqual([]);
  });
  it("does not attach a conflicting root identity to itself", () => {
    const children = boundary(256); children[256].job_id = "JOB-1"; children[0].parent_job_id = "JOB-1";
    const model = missionInteriors(documentFor(children));
    // The root comes from the qualified Mission, not a duplicate child record.
    expect(model.rows[0].lineage).toEqual(["JOB-1", "JOB-2"]);
    const rootChild = missionInteriors(documentFor([child("JOB-1")]));
    expect(rootChild.rows[0].problem).toBe("IDENTITY_CONFLICT");
  });
});
