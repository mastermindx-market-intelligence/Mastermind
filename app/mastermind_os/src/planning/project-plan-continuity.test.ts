import { describe, expect, it } from "vitest";
import fixture from "../fixtures/project-plan-continuity-owner.json";
import { CAPTURED_ASSOCIATIONS_ONLY, PROJECT_PLAN_CONTINUITY_INVALID,
  PROJECT_PLAN_CONTINUITY_SCHEMA, decodeProjectPlanContinuity,
  type ProjectPlanContinuityRead, type ProjectPlanSourceRef } from "./project-plan-continuity";

const WORK_REF = "WS:PLAN-TEST";
const MACRO = "mastermindx-market-intelligence/macro";
const MASTERMIND = "mastermindx-market-intelligence/Mastermind";
const CASES = (fixture as unknown as { cases: Record<string, unknown> }).cases;

type Mutation = (value: unknown) => void;
const clone = (value: unknown): Record<string, unknown> => structuredClone(value) as Record<string, unknown>;
const caseValue = (name: string): Record<string, unknown> => clone(CASES[name]);
const at = (value: unknown, path: PropertyKey[]): Record<string, unknown> => {
  let current: unknown = value;
  for (const key of path) current = (current as Record<string, unknown>)[key as string];
  return current as Record<string, unknown>;
};
const set = (value: unknown, path: PropertyKey[], replacement: unknown): void => {
  at(value, path.slice(0, -1))[path[path.length - 1] as string] = replacement;
};
const omit = (value: unknown, path: PropertyKey[]): void => {
  delete at(value, path.slice(0, -1))[path[path.length - 1] as string];
};
const extend = (value: unknown, path: PropertyKey[], entry: unknown): void => {
  (at(value, path) as unknown as unknown[]).push(entry);
};
const macroRef = (path: string): ProjectPlanSourceRef => ({
  repository: MACRO, path, commit: "a".repeat(40), content_sha256: "c".repeat(64) });
const readOf = (value: unknown): ProjectPlanContinuityRead => decodeProjectPlanContinuity(value, WORK_REF);
const expectRefused = (run: () => unknown): void => {
  let message: string | null = null;
  try { run(); } catch (error) { message = (error as Error).message; }
  expect(message).toBe(PROJECT_PLAN_CONTINUITY_INVALID);
};
const expectAccepted = (value: unknown): ProjectPlanContinuityRead => {
  const read = readOf(value);
  expect(read.schema).toBe(PROJECT_PLAN_CONTINUITY_SCHEMA);
  expect(read.work_ref).toBe(WORK_REF);
  return read;
};

describe("joined owner relationships", () => {
  it.each([
    ["relation", (v: unknown) => set(v, ["proposals", "items", 0, "adoption_relation"], "CURRENT_DECISION_REFERENCES_PROPOSAL")],
    ["basis", (v: unknown) => set(v, ["proposals", "items", 0, "comparison_basis"], "RECORDED_SOURCE")],
    ["base decision", (v: unknown) => set(v, ["proposals", "items", 0, "base_adoption"], "DEC:FOREIGN-DECISION")],
    ["unpaired source Unicode", (v: unknown) => set(v, ["adoption", "adoption", "adopted_source", "path"], "planning/\ud800.md")],
  ] as const)("refuses %s that disagrees with the captured owner", (_label, mutate) => {
    const value = caseValue("available_pending"); mutate(value);
    expectRefused(() => readOf(value));
  });
  it("preserves a literal revision backslash and a directory sharing only the prefix", () => {
    const value = caseValue("available_pending");
    set(value, ["adoption", "adoption", "display_revision"], "Reviewed\\revision");
    set(value, ["adoption", "adoption", "adopted_source", "path"], "agentos/workstreams-notes/plan.md");
    // Keep the exact owner baseline relationship consistent while varying valid ref data.
    set(value, ["proposals", "items", 0, "base_source", "path"], "agentos/workstreams-notes/plan.md");
    set(value, ["proposals", "items", 0, "comparison", "base_source", "path"], "agentos/workstreams-notes/plan.md");
    expectAccepted(value);
  });
});

describe("frozen fixture cases decode with their strict semantic shapes", () => {
  it("decodes the pending available baseline", () => {
    const read = expectAccepted(caseValue("available_pending"));
    expect(read).toEqual(CASES.available_pending);
    const adoption = read.adoption;
    expect(adoption.state).toBe("AVAILABLE");
    if (adoption.state === "AVAILABLE") {
      expect(adoption.decision_ref).toBe("DEC:PLAN-FIRST");
      expect(adoption.decision_source.path).toBe("agentos/decisions/DEC-PLAN-FIRST.md");
      expect(adoption.adoption.schema).toBe("agentos.project_plan_adoption.v1");
      expect(adoption.adoption.predecessor).toBeNull();
      expect(adoption.adoption.proposal_source).toBeNull();
      expect(adoption.decided_by).toBe("fixture-owner");
      expect(adoption.decided_at).toBe("2026-11-04");
      expect(adoption.content).toBe("# Recorded baseline\n");
    }
    expect(read.proposals.state).toBe("AVAILABLE");
    if (read.proposals.state === "AVAILABLE") {
      expect(read.proposals.coverage).toBe(CAPTURED_ASSOCIATIONS_ONLY);
      expect(read.proposals.items).toHaveLength(1);
      const item = read.proposals.items[0];
      expect(item.state).toBe("RECORDED_PROPOSAL");
      if (item.state === "RECORDED_PROPOSAL") {
        expect(item.proposal_id).toBe("PLAN-PROPOSAL");
        expect(item.base_adoption).toBe("DEC:PLAN-FIRST");
        expect(item.adoption_relation).toBe("UNASSOCIATED_WITH_CURRENT_DECISION");
        expect(item.comparison_basis).toBe("ADOPTED_CONTENT");
        expect(item.comparison.state).toBe("AVAILABLE");
        if (item.comparison.state === "AVAILABLE") {
          expect(item.comparison.identical).toBe(false);
          expect(item.comparison.added_lines).toBe(1);
          expect(item.comparison.removed_lines).toBe(1);
          expect(item.comparison.diff).toContain("@@ -1 +1 @@");
        }
      }
    }
  });
  it("decodes a declared decision whose body is unavailable", () => {
    const read = expectAccepted(caseValue("declared_source_unavailable"));
    expect(read).toEqual(CASES.declared_source_unavailable);
    const adoption = read.adoption;
    expect(adoption.state).toBe("UNAVAILABLE");
    if (adoption.state === "UNAVAILABLE" && adoption.reason === "SOURCE_UNAVAILABLE") {
      expect("content" in adoption).toBe(false);
      expect(adoption.declared_decision).toBeDefined();
      if (adoption.declared_decision) {
        expect(Object.keys(adoption.declared_decision).sort()).toEqual(
          ["adoption", "decided_at", "decided_by", "decision_ref", "decision_source"]);
        expect(adoption.declared_decision.decision_ref).toBe("DEC:PLAN-FIRST");
        expect(adoption.declared_decision.decided_by).toBe("fixture-owner");
        expect(adoption.declared_decision.decided_at).toBe("2026-11-04");
      }
    } else {
      expect.unreachable("fixture reason must be SOURCE_UNAVAILABLE");
    }
    expect(read.proposals.state).toBe("AVAILABLE");
    if (read.proposals.state === "AVAILABLE") {
      const item = read.proposals.items[0];
      expect(item.state).toBe("RECORDED_PROPOSAL");
      if (item.state === "RECORDED_PROPOSAL") {
        expect(item.comparison_basis).toBe("DECLARED_ADOPTION_SOURCE");
        expect(item.comparison.state).toBe("UNAVAILABLE");
        if (item.comparison.state === "UNAVAILABLE") expect(item.comparison.reason).toBe("SOURCE_UNAVAILABLE");
      }
    }
  });
  it("decodes an undeclared current plan without a declaration", () => {
    const read = expectAccepted(caseValue("recorded_source_only"));
    expect(read).toEqual(CASES.recorded_source_only);
    const adoption = read.adoption;
    expect(adoption.state).toBe("UNAVAILABLE");
    if (adoption.state === "UNAVAILABLE") {
      expect(adoption.reason).toBe("NOT_DECLARED");
      expect("declared_decision" in adoption).toBe(false);
      expect("content" in adoption).toBe(false);
    }
    expect(read.proposals.state).toBe("AVAILABLE");
    if (read.proposals.state === "AVAILABLE") {
      const item = read.proposals.items[0];
      if (item.state === "RECORDED_PROPOSAL") {
        expect(item.base_adoption).toBeNull();
        expect(item.comparison_basis).toBe("RECORDED_SOURCE");
        expect(item.comparison.state).toBe("AVAILABLE");
      }
    }
  });
  it("decodes a current decision that references its proposal", () => {
    const read = expectAccepted(caseValue("current_references_proposal"));
    expect(read).toEqual(CASES.current_references_proposal);
    const adoption = read.adoption;
    expect(adoption.state).toBe("AVAILABLE");
    if (adoption.state === "AVAILABLE") {
      expect(adoption.decision_ref).toBe("DEC:PLAN-SECOND");
      expect(adoption.adoption.predecessor).toBe("DEC:PLAN-FIRST");
      expect(adoption.adoption.proposal_source?.path).toBe("planning/proposal.md");
      expect(adoption.content).toBe("# Improved candidate\n");
    }
    expect(read.proposals.state).toBe("AVAILABLE");
    if (read.proposals.state === "AVAILABLE") {
      const item = read.proposals.items[0];
      if (item.state === "RECORDED_PROPOSAL") {
        expect(item.adoption_relation).toBe("CURRENT_DECISION_REFERENCES_PROPOSAL");
        expect(item.comparison_basis).toBe("RECORDED_PREDECESSOR");
        expect(item.candidate_sha256)
          .toBe("cf279f760c59148dfadfe65be4a879b17d09d0660e6ff703534dc4e4951d4e18");
      }
    }
  });
  it("decodes invalid lineage without proposals", () => {
    const read = expectAccepted(caseValue("lineage_invalid"));
    expect(read).toEqual(CASES.lineage_invalid);
    expect(read.adoption.state).toBe("UNAVAILABLE");
    if (read.adoption.state === "UNAVAILABLE") expect(read.adoption.reason).toBe("LINEAGE_INVALID");
    expect(read.proposals.state).toBe("UNAVAILABLE");
    if (read.proposals.state === "UNAVAILABLE") {
      expect(read.proposals.reason).toBe("LINEAGE_INVALID");
      expect(read.proposals.coverage).toBe(CAPTURED_ASSOCIATIONS_ONLY);
    }
  });
  it("decodes an available current plan with no captured proposals", () => {
    const read = expectAccepted(caseValue("no_captured_proposal"));
    expect(read).toEqual(CASES.no_captured_proposal);
    expect(read.adoption.state).toBe("AVAILABLE");
    expect(read.proposals.state).toBe("AVAILABLE");
    if (read.proposals.state === "AVAILABLE") expect(read.proposals.items).toHaveLength(0);
  });
  it("never labels an unavailable current plan as adopted", () => {
    for (const name of ["declared_source_unavailable", "recorded_source_only", "lineage_invalid"]) {
      const read = readOf(caseValue(name));
      expect(read.adoption.state).toBe("UNAVAILABLE");
      expect("content" in read.adoption).toBe(false);
      expect((read.adoption as { content?: unknown }).content).toBeUndefined();
    }
  });
  it("keeps declared and undeclared source-unavailable shapes distinct", () => {
    const declared = readOf(caseValue("declared_source_unavailable")).adoption;
    const undeclared = readOf(caseValue("recorded_source_only")).adoption;
    expect(declared).not.toEqual(undeclared);
    expect(undeclared).not.toEqual(declared);
  });
});

describe("accepts only the inner captured DTO object", () => {
  it.each([
    ["json text", () => JSON.stringify(CASES.available_pending)],
    ["captured bytes", () => new TextEncoder().encode(JSON.stringify(CASES.available_pending))],
    ["null", () => null],
    ["number", () => 42],
    ["boolean", () => true],
    ["undefined", () => undefined],
    ["array wrapper", () => [CASES.available_pending]],
    ["socket envelope", () => ({ envelope: { schema: PROJECT_PLAN_CONTINUITY_SCHEMA, payload: CASES.available_pending } })],
    ["result envelope", () => ({ schema: PROJECT_PLAN_CONTINUITY_SCHEMA, work_ref: WORK_REF, payload: CASES.available_pending })],
    ["job selector wrapper", () => ({ job: { root_job_id: "JOB-1" }, result: CASES.available_pending })],
    ["root selector wrapper", () => ({ root: "ROOT-1", dto: CASES.available_pending })],
    ["grant selector wrapper", () => ({ grant: "*", dto: CASES.available_pending })],
  ] as Array<[string, () => unknown]>)("refuses %s input", (_label, build) => {
    expectRefused(() => readOf(build()));
  });
});

describe("requires the exact selected work ref", () => {
  it.each([
    ["another selected work ref", "WS:OTHER-PLAN"],
    ["lowercase key", "ws:plan-test"],
    ["doubled dash key", "WS:PLAN--TEST"],
    ["trailing dash key", "WS:PLAN-TEST-"],
    ["leading dash key", "WS:-PLAN-TEST"],
    ["one character key", "WS:P"],
    ["oversized key", `WS:${"A".repeat(65)}`],
    ["prefix key that is valid but unequal", "WS:PLAN"],
    ["maximum key that is valid but unequal", `WS:${"A".repeat(64)}`],
    ["missing WS prefix", "PLAN-TEST"],
    ["embedded space", "WS:PLAN-TEST "],
    ["embedded newline", "WS:PLAN-TEST\n"],
    ["empty ref", ""],
  ] as Array<[string, string]>)("refuses expectedWorkRef %s", (label, expectedWorkRef) => {
    void label;
    expectRefused(() => decodeProjectPlanContinuity(caseValue("available_pending"), expectedWorkRef));
  });
  it.each([
    ["other work ref", "WS:OTHER-PLAN"],
    ["lowercase key", "WS:plan-test"],
    ["doubled dash key", "WS:PLAN--TEST"],
    ["null work ref", null],
    ["numeric work ref", 7],
  ] as Array<[string, unknown]>)("refuses a DTO work_ref carrying %s", (_label, workRef) => {
    const value = caseValue("available_pending");
    set(value, ["work_ref"], workRef);
    expectRefused(() => readOf(value));
  });
});

describe("refuses top-level shape mutations", () => {
  it.each([
    ["unknown schema", v => set(v, ["schema"], "mastermind.project_plan_continuity.v2")],
    ["foreign schema family", v => set(v, ["schema"], "mastermind.workspace_admitted_execution_plan.v1")],
    ["non-string schema", v => set(v, ["schema"], 7)],
    ["missing schema", v => omit(v, ["schema"])],
    ["extra grant field", v => set(v, ["grants"], ["*"])],
    ["extra job field", v => set(v, ["job"], {})],
    ["extra root field", v => set(v, ["root"], "ROOT-1")],
    ["extra provenance field", v => set(v, ["provenance"], {})],
    ["missing adoption", v => omit(v, ["adoption"])],
    ["missing proposals", v => omit(v, ["proposals"])],
    ["null adoption", v => set(v, ["adoption"], null)],
    ["null proposals", v => set(v, ["proposals"], null)],
    ["string adoption", v => set(v, ["adoption"], "AVAILABLE")],
    ["array proposals", v => set(v, ["proposals"], [])],
  ] as Array<[string, Mutation]>)("refuses %s", (_label, change) => {
    const value = caseValue("available_pending");
    change(value);
    expectRefused(() => readOf(value));
  });
});

describe("refuses nested adoption metadata mutations", () => {
  it.each([
    ["unknown adoption schema", v => set(v, ["adoption", "adoption", "schema"], "agentos.project_plan_adoption.v2")],
    ["foreign adoption work ref", v => set(v, ["adoption", "adoption", "work_ref"], "WS:OTHER-PLAN")],
    ["lowercase adoption work ref", v => set(v, ["adoption", "adoption", "work_ref"], "WS:plan-test")],
    ["extra adoption field", v => set(v, ["adoption", "adoption", "note"], "x")],
    ["missing adopted_source", v => omit(v, ["adoption", "adoption", "adopted_source"])],
    ["wrong-case canonical workstream path", v => set(v, ["adoption", "adoption", "adopted_source", "path"], "agentos/Workstreams/WS-PLAN-TEST.md")],
    ["lowercase canonical workstream path", v => set(v, ["adoption", "adoption", "adopted_source", "path"], "agentos/workstreams/ws-plan-test.md")],
    ["other workstream canonical path", v => set(v, ["adoption", "adoption", "adopted_source", "path"], "agentos/workstreams/WS-OTHER.md")],
    ["absolute source path", v => set(v, ["adoption", "adoption", "adopted_source", "path"], "/planning/base.md")],
    ["dotdot source path", v => set(v, ["adoption", "adoption", "adopted_source", "path"], "planning/../base.md")],
    ["dot source component", v => set(v, ["adoption", "adoption", "adopted_source", "path"], "planning/./base.md")],
    ["empty path component", v => set(v, ["adoption", "adoption", "adopted_source", "path"], "planning//base.md")],
    ["backslash source path", v => set(v, ["adoption", "adoption", "adopted_source", "path"], "planning\\base.md")],
    ["non-markdown source path", v => set(v, ["adoption", "adoption", "adopted_source", "path"], "planning/base.txt")],
    ["newline in source path", v => set(v, ["adoption", "adoption", "adopted_source", "path"], "planning/base\n.md")],
    ["oversized source path", v => set(v, ["adoption", "adoption", "adopted_source", "path"], `planning/${"d".repeat(512)}.md`)],
    ["unknown repository", v => set(v, ["adoption", "adoption", "adopted_source", "repository"], "mastermindx-market-intelligence/other")],
    ["case-mangled repository", v => set(v, ["adoption", "adoption", "adopted_source", "repository"], "mastermindx-market-intelligence/Macro")],
    ["short commit", v => set(v, ["adoption", "adoption", "adopted_source", "commit"], "a".repeat(39))],
    ["long commit", v => set(v, ["adoption", "adoption", "adopted_source", "commit"], "a".repeat(41))],
    ["uppercase commit", v => set(v, ["adoption", "adoption", "adopted_source", "commit"], "A".repeat(40))],
    ["commit trailing newline", v => set(v, ["adoption", "adoption", "adopted_source", "commit"], `${"a".repeat(40)}\n`)],
    ["numeric commit", v => set(v, ["adoption", "adoption", "adopted_source", "commit"], 17)],
    ["missing commit", v => omit(v, ["adoption", "adoption", "adopted_source", "commit"])],
    ["uppercase content digest", v => set(v, ["adoption", "adoption", "adopted_source", "content_sha256"], "C".repeat(64))],
    ["truncated content digest", v => set(v, ["adoption", "adoption", "adopted_source", "content_sha256"], "c".repeat(63))],
    ["extra source field", v => set(v, ["adoption", "adoption", "adopted_source", "note"], "x")],
    ["predecessor without DEC prefix", v => set(v, ["adoption", "adoption", "predecessor"], "PLAN-FIRST")],
    ["lowercase predecessor key", v => set(v, ["adoption", "adoption", "predecessor"], "DEC:plan-first")],
    ["doubled dash predecessor key", v => set(v, ["adoption", "adoption", "predecessor"], "DEC:PLAN--FIRST")],
    ["numeric predecessor", v => set(v, ["adoption", "adoption", "predecessor"], 5)],
    ["proposal_source with wrong-case canonical path", v => set(v, ["adoption", "adoption", "proposal_source"], { repository: MACRO, path: "agentos/Workstreams/WS-PLAN-TEST.md", commit: "a".repeat(40), content_sha256: "c".repeat(64) })],
    ["proposal_source with other workstream path", v => set(v, ["adoption", "adoption", "proposal_source"], { repository: MACRO, path: "agentos/workstreams/WS-OTHER.md", commit: "a".repeat(40), content_sha256: "c".repeat(64) })],
    ["malformed proposal_source", v => set(v, ["adoption", "adoption", "proposal_source"], { repository: MACRO, path: "planning/proposal.md", commit: "a".repeat(40) })],
    ["blank display_revision", v => set(v, ["adoption", "adoption", "display_revision"], "   ")],
    ["display_revision with newline", v => set(v, ["adoption", "adoption", "display_revision"], "REV\n1")],
    ["display_revision with NUL", v => set(v, ["adoption", "adoption", "display_revision"], "REV\u00001")],
    ["oversized display_revision", v => set(v, ["adoption", "adoption", "display_revision"], "R".repeat(129))],
    ["numeric display_revision", v => set(v, ["adoption", "adoption", "display_revision"], 9)],
    ["extra adoption metadata key at the unavailable layer", v => set(v, ["proposals", "coverage_note"], "x")],
  ] as Array<[string, Mutation]>)("refuses %s", (_label, change) => {
    const value = caseValue("available_pending");
    change(value);
    expectRefused(() => readOf(value));
  });
});

describe("refuses decision identity and date mutations", () => {
  it.each([
    ["decision source path mismatch", v => set(v, ["adoption", "decision_source", "path"], "agentos/decisions/DEC-OTHER.md")],
    ["decision source in the Mastermind repository", v => set(v, ["adoption", "decision_source", "repository"], MASTERMIND)],
    ["lowercase decision source path", v => set(v, ["adoption", "decision_source", "path"], "agentos/decisions/dec-plan-first.md")],
    ["lowercase decision ref key", v => set(v, ["adoption", "decision_ref"], "DEC:plan-first")],
    ["decision ref without DEC prefix", v => set(v, ["adoption", "decision_ref"], "PLAN-FIRST")],
    ["doubled dash decision ref key", v => set(v, ["adoption", "decision_ref"], "DEC:PLAN--FIRST")],
    ["oversized decision ref key", v => set(v, ["adoption", "decision_ref"], `DEC:${"A".repeat(129)}`)],
    ["missing decision ref", v => omit(v, ["adoption", "decision_ref"])],
    ["blank decided_by", v => set(v, ["adoption", "decided_by"], "   ")],
    ["oversized decided_by", v => set(v, ["adoption", "decided_by"], "x".repeat(257))],
    ["numeric decided_by", v => set(v, ["adoption", "decided_by"], 12)],
    ["missing decided_by", v => omit(v, ["adoption", "decided_by"])],
    ["day beyond the month", v => set(v, ["adoption", "decided_at"], "2026-02-30")],
    ["month thirteen", v => set(v, ["adoption", "decided_at"], "2026-13-01")],
    ["zero year", v => set(v, ["adoption", "decided_at"], "0000-01-01")],
    ["zero month", v => set(v, ["adoption", "decided_at"], "2026-00-10")],
    ["zero day", v => set(v, ["adoption", "decided_at"], "2026-11-00")],
    ["non-leap february", v => set(v, ["adoption", "decided_at"], "2026-02-29")],
    ["century non-leap february", v => set(v, ["adoption", "decided_at"], "2100-02-29")],
    ["unpadded day", v => set(v, ["adoption", "decided_at"], "2026-11-4")],
    ["slash separator", v => set(v, ["adoption", "decided_at"], "2026/11/04")],
    ["trailing newline", v => set(v, ["adoption", "decided_at"], "2026-11-04\n")],
    ["timestamp instead of date", v => set(v, ["adoption", "decided_at"], "2026-11-04T00:00:00Z")],
    ["numeric date", v => set(v, ["adoption", "decided_at"], 20261104)],
    ["null date", v => set(v, ["adoption", "decided_at"], null)],
    ["missing date", v => omit(v, ["adoption", "decided_at"])],
  ] as Array<[string, Mutation]>)("refuses %s", (_label, change) => {
    const value = caseValue("available_pending");
    change(value);
    expectRefused(() => readOf(value));
  });
});

describe("bounds the adopted body text", () => {
  it.each([
    ["missing content", v => omit(v, ["adoption", "content"])],
    ["numeric content", v => set(v, ["adoption", "content"], 12345)],
    ["null content", v => set(v, ["adoption", "content"], null)],
    ["empty content", v => set(v, ["adoption", "content"], "")],
    ["oversized content", v => set(v, ["adoption", "content"], "a".repeat(262145))],
    ["lone surrogate in content", v => set(v, ["adoption", "content"], "# recorded \uD800 baseline\n")],
  ] as Array<[string, Mutation]>)("refuses %s", (_label, change) => {
    const value = caseValue("available_pending");
    change(value);
    expectRefused(() => readOf(value));
  });
});

describe("keeps the declaration tied to declarable unavailable reasons", () => {
  it.each([
    ["unknown unavailable reason", v => set(v, ["adoption", "reason"], "SOURCE_CHANGED")],
    ["numeric unavailable reason", v => set(v, ["adoption", "reason"], 7)],
    ["missing unavailable reason", v => omit(v, ["adoption", "reason"])],
    ["available label retained on an unavailable record", v => set(v, ["adoption", "state"], "AVAILABLE")],
    ["unknown adoption state", v => set(v, ["adoption", "state"], "PARTIAL")],
    ["content leaked onto an unavailable record", v => set(v, ["adoption", "content"], "# withheld")],
    ["declaration with an extra field", v => set(v, ["adoption", "declared_decision", "note"], "x")],
    ["declaration missing decided_at", v => omit(v, ["adoption", "declared_decision", "decided_at"])],
    ["declaration with a foreign decision ref", v => set(v, ["adoption", "declared_decision", "decision_ref"], "DEC:OTHER-PLAN")],
    ["declaration with a non-canonical decision path", v => set(v, ["adoption", "declared_decision", "decision_source", "path"], "agentos/decisions/dec-plan-first.md")],
    ["declaration adoption with another workstream path", v => set(v, ["adoption", "declared_decision", "adoption", "adopted_source", "path"], "agentos/workstreams/WS-OTHER.md")],
    ["declaration decided_by beyond the bound", v => set(v, ["adoption", "declared_decision", "decided_by"], "x".repeat(257))],
  ] as Array<[string, Mutation]>)("refuses %s", (_label, change) => {
    const value = caseValue("declared_source_unavailable");
    change(value);
    expectRefused(() => readOf(value));
  });
  it("refuses a declaration attached to undeclarable reasons", () => {
    const declaration = clone(at(CASES.declared_source_unavailable, ["adoption", "declared_decision"]));
    const undeclared = caseValue("recorded_source_only");
    set(undeclared, ["adoption", "declared_decision"], declaration);
    expectRefused(() => readOf(undeclared));
    const lineage = caseValue("lineage_invalid");
    set(lineage, ["adoption", "reason"], "CONTENT_OVER_BUDGET");
    set(lineage, ["adoption", "declared_decision"], declaration);
    expectRefused(() => readOf(lineage));
  });
  it("keeps the declaration optional on declarable reasons", () => {
    const value = caseValue("declared_source_unavailable");
    omit(value, ["adoption", "declared_decision"]);
    // A declaration-free result cannot retain declaration-based proposal claims.
    set(value, ["proposals"], { state: "AVAILABLE", items: [], coverage: CAPTURED_ASSOCIATIONS_ONLY });
    const read = expectAccepted(value);
    expect(read.adoption).toEqual({ state: "UNAVAILABLE", reason: "SOURCE_UNAVAILABLE" });
  });
  it("accepts the producer's bare early-return projection shape", () => {
    const value = caseValue("declared_source_unavailable");
    omit(value, ["adoption", "declared_decision"]);
    set(value, ["proposals"], { state: "UNAVAILABLE", reason: "SOURCE_UNAVAILABLE",
      coverage: CAPTURED_ASSOCIATIONS_ONLY });
    const read = expectAccepted(value);
    expect(read.adoption).toEqual({ state: "UNAVAILABLE", reason: "SOURCE_UNAVAILABLE" });
    expect(read.proposals).toEqual({ state: "UNAVAILABLE", reason: "SOURCE_UNAVAILABLE",
      coverage: CAPTURED_ASSOCIATIONS_ONLY });
  });
});

describe("refuses proposals container mutations", () => {
  it.each([
    ["foreign coverage", v => set(v, ["proposals", "coverage"], "FULL_HISTORY")],
    ["missing coverage", v => omit(v, ["proposals", "coverage"])],
    ["numeric coverage", v => set(v, ["proposals", "coverage"], 3)],
    ["unknown proposals state", v => set(v, ["proposals", "state"], "PARTIAL")],
    ["numeric proposals state", v => set(v, ["proposals", "state"], 1)],
    ["items outside an array", v => set(v, ["proposals", "items"], {})],
    ["items as text", v => set(v, ["proposals", "items"], "[]")],
    ["missing items", v => omit(v, ["proposals", "items"])],
    ["oversized items", v => set(v, ["proposals", "items"], Array.from({ length: 33 }, () => clone(at(CASES.available_pending, ["proposals", "items", 0]))))],
  ] as Array<[string, Mutation]>)("refuses %s", (_label, change) => {
    const value = caseValue("no_captured_proposal");
    change(value);
    expectRefused(() => readOf(value));
  });
  it.each([
    ["unknown unavailable reason", v => set(v, ["proposals", "reason"], "SOURCE_CHANGED")],
    ["missing unavailable reason", v => omit(v, ["proposals", "reason"])],
    ["items leaked onto unavailable proposals", v => set(v, ["proposals", "items"], [])],
  ] as Array<[string, Mutation]>)("refuses unavailable proposals with %s", (_label, change) => {
    const value = caseValue("lineage_invalid");
    change(value);
    expectRefused(() => readOf(value));
  });
});

describe("refuses proposal item mutations", () => {
  it.each([
    ["unknown item state", v => set(v, ["proposals", "items", 0, "state"], "PROPOSED")],
    ["unavailable label retaining record fields", v => set(v, ["proposals", "items", 0, "state"], "UNAVAILABLE")],
    ["foreign proposal schema", v => set(v, ["proposals", "items", 0, "schema"], "agentos.project_plan_proposal.v2")],
    ["missing proposal schema", v => omit(v, ["proposals", "items", 0, "schema"])],
    ["lowercase proposal id", v => set(v, ["proposals", "items", 0, "proposal_id"], "plan-proposal")],
    ["doubled dash proposal id", v => set(v, ["proposals", "items", 0, "proposal_id"], "PLAN--PROPOSAL")],
    ["trailing dash proposal id", v => set(v, ["proposals", "items", 0, "proposal_id"], "PLAN-PROPOSAL-")],
    ["one character proposal id", v => set(v, ["proposals", "items", 0, "proposal_id"], "P")],
    ["oversized proposal id", v => set(v, ["proposals", "items", 0, "proposal_id"], "P".repeat(129))],
    ["numeric proposal id", v => set(v, ["proposals", "items", 0, "proposal_id"], 11)],
    ["missing proposal id", v => omit(v, ["proposals", "items", 0, "proposal_id"])],
    ["foreign item work ref", v => set(v, ["proposals", "items", 0, "work_ref"], "WS:OTHER-PLAN")],
    ["missing item work ref", v => omit(v, ["proposals", "items", 0, "work_ref"])],
    ["absolute proposal source path", v => set(v, ["proposals", "items", 0, "proposal_source", "path"], "/planning/proposal.md")],
    ["malformed proposal source digest", v => set(v, ["proposals", "items", 0, "proposal_source", "content_sha256"], "6e7f")],
    ["unknown proposal source repository", v => set(v, ["proposals", "items", 0, "proposal_source", "repository"], "mastermindx-market-intelligence/other")],
    ["base adoption without DEC prefix", v => set(v, ["proposals", "items", 0, "base_adoption"], "PLAN-FIRST")],
    ["numeric base adoption", v => set(v, ["proposals", "items", 0, "base_adoption"], 4)],
    ["base source with wrong-case canonical path", v => set(v, ["proposals", "items", 0, "base_source", "path"], "agentos/Workstreams/WS-PLAN-TEST.md")],
    ["base source with another workstream path", v => set(v, ["proposals", "items", 0, "base_source", "path"], "agentos/workstreams/WS-OTHER.md")],
    ["missing base source", v => omit(v, ["proposals", "items", 0, "base_source"])],
    ["uppercase candidate digest", v => set(v, ["proposals", "items", 0, "candidate_sha256"], "C".repeat(64))],
    ["candidate digest unanchored to the comparison", v => set(v, ["proposals", "items", 0, "candidate_sha256"], "b".repeat(64))],
    ["missing candidate digest", v => omit(v, ["proposals", "items", 0, "candidate_sha256"])],
    ["blank rationale", v => set(v, ["proposals", "items", 0, "rationale"], "   ")],
    ["numeric rationale", v => set(v, ["proposals", "items", 0, "rationale"], 5)],
    ["oversized rationale", v => set(v, ["proposals", "items", 0, "rationale"], "r".repeat(4097))],
    ["lone surrogate in rationale", v => set(v, ["proposals", "items", 0, "rationale"], "proposed \uD800 change")],
    ["evidence outside an array", v => set(v, ["proposals", "items", 0, "evidence"], {})],
    ["oversized evidence", v => set(v, ["proposals", "items", 0, "evidence"], Array.from({ length: 33 }, () => clone(at(CASES.available_pending, ["proposals", "items", 0, "base_source"]))))],
    ["malformed evidence entry", v => extend(v, ["proposals", "items", 0, "evidence"], { repository: "other", path: "x.md", commit: "a".repeat(40), content_sha256: "c".repeat(64) })],
    ["missing evidence", v => omit(v, ["proposals", "items", 0, "evidence"])],
    ["unknown adoption relation", v => set(v, ["proposals", "items", 0, "adoption_relation"], "ADOPTED")],
    ["boolean adoption relation", v => set(v, ["proposals", "items", 0, "adoption_relation"], true)],
    ["unknown comparison basis", v => set(v, ["proposals", "items", 0, "comparison_basis"], "GIT_STATUS")],
    ["numeric comparison basis", v => set(v, ["proposals", "items", 0, "comparison_basis"], 2)],
    ["missing comparison", v => omit(v, ["proposals", "items", 0, "comparison"])],
    ["extra comparison field", v => set(v, ["proposals", "items", 0, "comparison", "engine"], "difflib")],
    ["extra item field", v => set(v, ["proposals", "items", 0, "lifecycle"], "ADOPTED")],
  ] as Array<[string, Mutation]>)("refuses %s", (_label, change) => {
    const value = caseValue("available_pending");
    change(value);
    expectRefused(() => readOf(value));
  });
  it("refuses duplicate proposal identifiers across valid items", () => {
    const value = caseValue("available_pending");
    const entry = clone(at(value, ["proposals", "items", 0]));
    set(value, ["proposals", "items"], [entry, clone(entry)]);
    expectRefused(() => readOf(value));
  });
  it.each([
    ["reason outside the single invalid code", v => set(v, ["proposals", "items", 0], { proposal_source: clone(at(v, ["proposals", "items", 0, "proposal_source"])), state: "UNAVAILABLE", reason: "SOURCE_UNAVAILABLE" })],
    ["extra field on the invalid item", v => set(v, ["proposals", "items", 0], { proposal_source: clone(at(v, ["proposals", "items", 0, "proposal_source"])), state: "UNAVAILABLE", reason: "RECORD_INVALID", comparison: { state: "UNAVAILABLE", reason: "SOURCE_UNAVAILABLE" } })],
    ["missing proposal source", v => set(v, ["proposals", "items", 0], { state: "UNAVAILABLE", reason: "RECORD_INVALID" })],
    ["malformed invalid item source", v => set(v, ["proposals", "items", 0], { proposal_source: { repository: MACRO, path: "planning/proposal", commit: "a".repeat(40), content_sha256: "c".repeat(64) }, state: "UNAVAILABLE", reason: "RECORD_INVALID" })],
    ["unknown state on the invalid item", v => set(v, ["proposals", "items", 0], { proposal_source: clone(at(v, ["proposals", "items", 0, "proposal_source"])), state: "PARTIAL", reason: "RECORD_INVALID" })],
  ] as Array<[string, Mutation]>)("refuses an unavailable proposal item with %s", (_label, change) => {
    const value = caseValue("available_pending");
    change(value);
    expectRefused(() => readOf(value));
  });
  it("accepts the exact three-field unavailable proposal item", () => {
    const value = caseValue("available_pending");
    const proposalSource = clone(at(value, ["proposals", "items", 0, "proposal_source"]));
    set(value, ["proposals", "items"], [{ proposal_source: proposalSource, state: "UNAVAILABLE", reason: "RECORD_INVALID" }]);
    const read = expectAccepted(value);
    if (read.proposals.state === "AVAILABLE") {
      expect(read.proposals.items[0]).toEqual({ proposal_source: proposalSource, state: "UNAVAILABLE", reason: "RECORD_INVALID" });
    } else {
      expect.unreachable("proposals must stay available");
    }
  });
});

describe("refuses comparison mutations", () => {
  it.each([
    ["unknown comparison state", v => set(v, ["proposals", "items", 0, "comparison", "state"], "PARTIAL")],
    ["cross-source base path", v => set(v, ["proposals", "items", 0, "comparison", "base_source", "path"], "planning/other-base.md")],
    ["cross-source repository", v => set(v, ["proposals", "items", 0, "comparison", "base_source", "repository"], MASTERMIND)],
    ["base commit mismatch", v => set(v, ["proposals", "items", 0, "comparison", "base_source", "commit"], "d".repeat(40))],
    ["base digest mismatch", v => set(v, ["proposals", "items", 0, "comparison", "base_source", "content_sha256"], "d".repeat(64))],
    ["candidate digest mismatch", v => set(v, ["proposals", "items", 0, "comparison", "candidate_sha256"], "b".repeat(64))],
    ["missing base text", v => omit(v, ["proposals", "items", 0, "comparison", "base_text"])],
    ["numeric base text", v => set(v, ["proposals", "items", 0, "comparison", "base_text"], 9)],
    ["empty base text", v => set(v, ["proposals", "items", 0, "comparison", "base_text"], "")],
    ["numeric diff", v => set(v, ["proposals", "items", 0, "comparison", "diff"], 9)],
    ["null diff", v => set(v, ["proposals", "items", 0, "comparison", "diff"], null)],
    ["text identical label", v => set(v, ["proposals", "items", 0, "comparison", "identical"], "yes")],
    ["identical label over differing texts", v => set(v, ["proposals", "items", 0, "comparison", "identical"], true)],
    ["identical label with a residual diff", v => {
      set(v, ["proposals", "items", 0, "comparison", "candidate_text"],
        at(v, ["proposals", "items", 0, "comparison", "base_text"]));
      set(v, ["proposals", "items", 0, "comparison", "identical"], true);
    }],
    ["equal texts labeled different", v => set(v, ["proposals", "items", 0, "comparison", "candidate_text"],
      at(v, ["proposals", "items", 0, "comparison", "base_text"]))],
    ["boolean added lines", v => set(v, ["proposals", "items", 0, "comparison", "added_lines"], true)],
    ["float removed lines", v => set(v, ["proposals", "items", 0, "comparison", "removed_lines"], 1.5)],
    ["negative added lines", v => set(v, ["proposals", "items", 0, "comparison", "added_lines"], -1)],
    ["unsafe added lines", v => set(v, ["proposals", "items", 0, "comparison", "added_lines"], 2 ** 53)],
    ["missing removed lines", v => omit(v, ["proposals", "items", 0, "comparison", "removed_lines"])],
  ] as Array<[string, Mutation]>)("refuses %s", (_label, change) => {
    const value = caseValue("available_pending");
    change(value);
    expectRefused(() => readOf(value));
  });
  it.each([
    ["unknown unavailable reason", v => set(v, ["proposals", "items", 0, "comparison", "reason"], "BYTES_CHANGED")],
    ["body text leaked onto an unavailable comparison", v => set(v, ["proposals", "items", 0, "comparison", "base_text"], "# leaked")],
    ["missing unavailable reason", v => omit(v, ["proposals", "items", 0, "comparison", "reason"])],
  ] as Array<[string, Mutation]>)("refuses an unavailable comparison with %s", (_label, change) => {
    const value = caseValue("declared_source_unavailable");
    change(value);
    expectRefused(() => readOf(value));
  });
});

describe("enforces the frozen byte budgets", () => {
  it.each([
    ["oversized base text", v => set(v, ["proposals", "items", 0, "comparison", "base_text"], "b".repeat(262145))],
    ["oversized candidate text", v => set(v, ["proposals", "items", 0, "comparison", "candidate_text"], "c".repeat(131073))],
    ["a comparison over the 65536-byte serialization budget", v => set(v, ["proposals", "items", 0, "comparison", "base_text"], "b".repeat(65540))],
    ["a whole result over the 126976-byte serialization budget", v => {
      set(v, ["adoption", "content"], "a".repeat(70000));
      set(v, ["proposals", "items", 0, "comparison", "base_text"], "b".repeat(30000));
      set(v, ["proposals", "items", 0, "comparison", "candidate_text"], "c".repeat(30000));
    }],
  ] as Array<[string, Mutation]>)("refuses %s", (_label, change) => {
    const value = caseValue("available_pending");
    change(value);
    expectRefused(() => readOf(value));
  });
});

describe("refuses lone surrogates in strict UTF-8 text", () => {
  it.each([
    ["candidate text", v => set(v, ["proposals", "items", 0, "comparison", "candidate_text"], "# improved \uDFFF candidate\n")],
    ["diff text", v => set(v, ["proposals", "items", 0, "comparison", "diff"], "--- recorded-base\n+\uD800")],
    ["content", v => set(v, ["adoption", "content"], "# recorded \uDC80\n")],
    ["decided_by", v => set(v, ["adoption", "decided_by"], "owner \uD800")],
  ] as Array<[string, Mutation]>)("refuses a lone surrogate in %s", (_label, change) => {
    const value = caseValue("available_pending");
    change(value);
    expectRefused(() => readOf(value));
  });
});

describe("accepts documented boundary values", () => {
  it("accepts an explicit display revision", () => {
    const value = caseValue("available_pending");
    set(value, ["adoption", "adoption", "display_revision"], "REV-1");
    const read = expectAccepted(value);
    expect(read.adoption.state).toBe("AVAILABLE");
    if (read.adoption.state === "AVAILABLE") {
      expect(read.adoption.adoption.display_revision).toBe("REV-1");
    }
  });
  it("accepts a genuine leap day and preserves it verbatim", () => {
    const value = caseValue("available_pending");
    set(value, ["adoption", "decided_at"], "2000-02-29");
    const read = expectAccepted(value);
    expect(read.adoption.state).toBe("AVAILABLE");
    if (read.adoption.state === "AVAILABLE") expect(read.adoption.decided_at).toBe("2000-02-29");
  });
  it("accepts a comparison whose identical label matches equal texts", () => {
    const value = caseValue("available_pending");
    const comparison = at(value, ["proposals", "items", 0, "comparison"]);
    comparison.candidate_text = comparison.base_text;
    comparison.diff = "";
    comparison.added_lines = 0;
    comparison.removed_lines = 0;
    comparison.identical = true;
    const read = expectAccepted(value);
    if (read.proposals.state === "AVAILABLE" && read.proposals.items[0].state === "RECORDED_PROPOSAL" &&
        read.proposals.items[0].comparison.state === "AVAILABLE") {
      expect(read.proposals.items[0].comparison.identical).toBe(true);
      expect(read.proposals.items[0].comparison.diff).toBe("");
    } else {
      expect.unreachable("comparison must stay available");
    }
  });
  it("accounts line separators the way the frozen producer serializes them", () => {
    const value = caseValue("available_pending");
    // 64900 ASCII bytes + 20 three-byte line separators serialize to 65518
    // comparison bytes, inside the 65536 budget; a serializer that escapes
    // U+2028 would measure 65618 and wrongly refuse this recorded body.
    set(value, ["proposals", "items", 0, "comparison", "base_text"],
      `${"x".repeat(64900)}${"\u2028".repeat(20)}`);
    const read = expectAccepted(value);
    expect(read.proposals.state).toBe("AVAILABLE");
  });
  it("applies the canonical workstream rule to Macro refs only", () => {
    const value = caseValue("available_pending");
    set(value, ["adoption", "adoption", "adopted_source", "repository"], MASTERMIND);
    set(value, ["proposals", "items", 0, "base_source", "repository"], MASTERMIND);
    set(value, ["proposals", "items", 0, "comparison", "base_source", "repository"], MASTERMIND);
    const read = expectAccepted(value);
    expect(read.adoption.state).toBe("AVAILABLE");
  });
  it("preserves evidence references verbatim", () => {
    const value = caseValue("available_pending");
    const evidence = clone(at(value, ["proposals", "items", 0, "base_source"]));
    extend(value, ["proposals", "items", 0, "evidence"], evidence);
    const read = expectAccepted(value);
    if (read.proposals.state === "AVAILABLE" && read.proposals.items[0].state === "RECORDED_PROPOSAL") {
      expect(read.proposals.items[0].evidence).toHaveLength(1);
      expect(read.proposals.items[0].evidence[0]).toEqual(evidence);
    } else {
      expect.unreachable("proposals must stay available");
    }
  });
  it("preserves astral, CRLF and BOM bodies without normalization", () => {
    const value = caseValue("available_pending");
    const body = "\uFEFF# Recorded\r\n\u{1F30D}\n";
    set(value, ["adoption", "content"], body);
    const read = expectAccepted(value);
    expect(read.adoption.state).toBe("AVAILABLE");
    if (read.adoption.state === "AVAILABLE") {
      expect(read.adoption.content).toBe(body);
      expect(read.adoption.content.length).toBe(body.length);
    }
  });
});

describe("returns detached output", () => {
  it("never aliases the caller value", () => {
    const input = caseValue("available_pending");
    const read = expectAccepted(input);
    expect(read).toEqual(CASES.available_pending);
    set(input, ["adoption", "decided_by"], "tampered");
    set(input, ["proposals", "items", 0, "proposal_id"], "OTHER");
    expect(read).toEqual(CASES.available_pending);
  });
  it("never aliases an earlier read", () => {
    const read = expectAccepted(caseValue("available_pending"));
    if (read.adoption.state === "AVAILABLE") read.adoption.content = "tampered";
    if (read.proposals.state === "AVAILABLE") read.proposals.items.push({ proposal_source: macroRef("planning/x.md"), state: "UNAVAILABLE", reason: "RECORD_INVALID" });
    expect(expectAccepted(caseValue("available_pending"))).toEqual(CASES.available_pending);
  });
  it("never reuses nested containers across decodes", () => {
    const first = expectAccepted(caseValue("available_pending"));
    const second = expectAccepted(caseValue("available_pending"));
    expect(first).not.toBe(second);
    expect(first).toEqual(second);
    if (first.adoption.state === "AVAILABLE" && second.adoption.state === "AVAILABLE") {
      expect(first.adoption.decision_source).not.toBe(second.adoption.decision_source);
      expect(first.adoption.adoption).not.toBe(second.adoption.adoption);
    }
    if (first.proposals.state === "AVAILABLE" && second.proposals.state === "AVAILABLE") {
      expect(first.proposals.items).not.toBe(second.proposals.items);
    }
  });
});
