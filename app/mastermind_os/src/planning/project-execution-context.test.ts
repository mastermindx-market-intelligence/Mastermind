import { describe, expect, it } from "vitest";
import fixture from "../fixtures/project-plan-v2-owner.json";
import { BODY_SCHEMA, type ProjectPlanSelection } from "./project-plan";
import {
  projectExecutionContext,
  sameProjectExecutionContext,
  type ProjectExecutionContext,
  type ProjectExecutionContextAvailable,
} from "./project-execution-context";

type Body = Record<string, any>;

const CASES = (fixture as unknown as { cases: Record<string, unknown> }).cases;
const WORK_REF = "WS:PLAN-TEST";
const SELECTION: ProjectPlanSelection = { work_ref: WORK_REF };
const MACRO = "mastermindx-market-intelligence/macro";
const MASTERMIND = "mastermindx-market-intelligence/Mastermind";
const RECORD_COMMIT = "a".repeat(40);
const RECORD_SHA = "32065f2e9a90424f00d191b68eb3479a38fee45811124611e548c5c1febdd7d3";
const DECISION_SHA = "1e8b858fc52986327beb62ec4632f63d3029a7cea876a9c780df0220e07f28cf";
const ADOPTED_SHA = "c0059c8c00caec3155606af4f273d83ab8d2a3b6a15a1aee73f66449b33908e0";

const clone = (value: unknown): Body => structuredClone(value) as Body;
const caseValue = (name: string): Body => clone(CASES[name]);

/** The legacy v1 body: no continuity, legacy schema, legacy adoption. */
const v1Body = (): Body => {
  const body = caseValue("available_pending");
  delete body.continuity;
  body.schema = BODY_SCHEMA;
  body.plan.adoption = { state: "UNAVAILABLE", reason: "NOT_DECLARED" };
  return body;
};

/** The typed unavailable read: no source, no plan, one closed reason code. */
const unavailableBody = (): Body => ({
  schema: BODY_SCHEMA,
  selection: { work_ref: WORK_REF },
  availability: "UNAVAILABLE",
  source: null,
  plan: null,
  reason_codes: ["SOURCE_UNAVAILABLE"],
});

const available = (context: ProjectExecutionContext): ProjectExecutionContextAvailable => {
  if (context.state !== "AVAILABLE") throw new Error("expected an AVAILABLE execution context");
  return context;
};

/** Asserts the decoder's exact value-free constant, never a fragment. */
const expectInvalid = (run: () => unknown): void => {
  let thrown: unknown;
  try {
    run();
  } catch (error) {
    thrown = error;
  }
  expect(thrown).toBeInstanceOf(Error);
  expect((thrown as Error).message).toBe("PROJECT_PLAN_INVALID");
};

/** The same context values, with every object's keys inserted in another order. */
const reorder = (context: ProjectExecutionContextAvailable): ProjectExecutionContextAvailable => {
  const adopted = context.adoption;
  const decision = context.adoptionDecisionSource;
  return {
    objective: context.objective,
    title: context.title,
    workRef: context.workRef,
    state: context.state,
    recordSource: {
      content_sha256: context.recordSource.content_sha256,
      path: context.recordSource.path,
      commit: context.recordSource.commit,
      repository: context.recordSource.repository,
    },
    adoption: adopted === null
      ? null
      : adopted.state === "AVAILABLE"
        ? {
            state: "AVAILABLE",
            matches_authored_record: adopted.matches_authored_record,
            display_revision: adopted.display_revision,
            adopted_source: {
              content_sha256: adopted.adopted_source.content_sha256,
              commit: adopted.adopted_source.commit,
              path: adopted.adopted_source.path,
              repository: adopted.adopted_source.repository,
            },
            decision_ref: adopted.decision_ref,
          }
        : { state: "UNAVAILABLE", reason: adopted.reason },
    adoptionDecisionSource: decision === null
      ? null
      : {
          content_sha256: decision.content_sha256,
          commit: decision.commit,
          path: decision.path,
          repository: decision.repository,
        },
  };
};

describe("projectExecutionContext: the available v2 read", () => {
  it("projects the authored record and its captured provenance", () => {
    const context = available(projectExecutionContext(caseValue("available_pending"), SELECTION));
    expect(context.workRef).toBe("WS:PLAN-TEST");
    expect(context.title).toBe("Authored record");
    expect(context.objective).toBe("Real available objective.");
    expect(context.recordSource).toEqual({
      repository: MACRO,
      commit: RECORD_COMMIT,
      path: "agentos/workstreams/WS-PLAN-TEST.md",
      content_sha256: RECORD_SHA,
    });
    expect(context.adoption).toEqual({
      state: "AVAILABLE",
      decision_ref: "DEC:PLAN-FIRST",
      adopted_source: {
        repository: MACRO,
        path: "planning/base.md",
        commit: "b".repeat(40),
        content_sha256: ADOPTED_SHA,
      },
      display_revision: null,
      matches_authored_record: false,
    });
    expect(context.adoptionDecisionSource).toEqual({
      repository: MACRO,
      path: "agentos/decisions/DEC-PLAN-FIRST.md",
      commit: RECORD_COMMIT,
      content_sha256: DECISION_SHA,
    });
  });

  it("projects the same context when no proposal was captured", () => {
    const withProposal = available(projectExecutionContext(caseValue("available_pending"), SELECTION));
    const withoutProposal = available(projectExecutionContext(caseValue("no_captured_proposal"), SELECTION));
    expect(sameProjectExecutionContext(withProposal, withoutProposal)).toBe(true);
    expect(withoutProposal.adoptionDecisionSource).toEqual(withProposal.adoptionDecisionSource);
  });

  it("carries no readiness, launch authority or wave-derived field", () => {
    const context = available(projectExecutionContext(caseValue("available_pending"), SELECTION));
    expect(Object.keys(context).sort()).toEqual([
      "adoption", "adoptionDecisionSource", "objective", "recordSource", "state", "title", "workRef",
    ]);
    for (const absent of ["status", "owner", "next_action", "waves", "version_history", "launch"]) {
      expect(absent in context).toBe(false);
    }
  });

  it("does not let a mutated input alter the projected context", () => {
    const body = caseValue("available_pending");
    const context = available(projectExecutionContext(body, SELECTION));
    expect(context.adoption).not.toBe(body.plan.adoption);
    expect(context.recordSource).not.toBe(body.source);
    expect(context.adoptionDecisionSource).not.toBe(body.continuity.adoption.decision_source);
    body.plan.title = "Mutated after the read";
    body.source.commit = "f".repeat(40);
    body.continuity.adoption.decision_source.path = "agentos/decisions/DEC-OTHER.md";
    expect(context.title).toBe("Authored record");
    expect(context.recordSource.commit).toBe(RECORD_COMMIT);
    expect(context.adoptionDecisionSource?.path).toBe("agentos/decisions/DEC-PLAN-FIRST.md");
  });

  it("does not let a mutated context alter a later projection", () => {
    const first = available(projectExecutionContext(caseValue("available_pending"), SELECTION));
    first.recordSource.commit = "f".repeat(40);
    const second = available(projectExecutionContext(caseValue("available_pending"), SELECTION));
    expect(second.recordSource.commit).toBe(RECORD_COMMIT);
    expect(sameProjectExecutionContext(first, second)).toBe(false);
  });
});

describe("projectExecutionContext: the legacy v1 read", () => {
  it("keeps the adoption and the decision source null", () => {
    const context = available(projectExecutionContext(v1Body(), SELECTION));
    expect(context.workRef).toBe("WS:PLAN-TEST");
    expect(context.title).toBe("Authored record");
    expect(context.objective).toBe("Real available objective.");
    expect(context.recordSource).toEqual({
      repository: MACRO,
      commit: RECORD_COMMIT,
      path: "agentos/workstreams/WS-PLAN-TEST.md",
      content_sha256: RECORD_SHA,
    });
    expect(context.adoption).toBeNull();
    expect(context.adoptionDecisionSource).toBeNull();
  });

  it("is not the same context as the v2 read of the same record", () => {
    const v1 = available(projectExecutionContext(v1Body(), SELECTION));
    const v2 = available(projectExecutionContext(caseValue("available_pending"), SELECTION));
    expect(sameProjectExecutionContext(v1, v2)).toBe(false);
  });
});

describe("projectExecutionContext: an unavailable captured adoption", () => {
  it("keeps the unavailable adoption summary and no decision source", () => {
    const context = available(projectExecutionContext(caseValue("declared_source_unavailable"), SELECTION));
    expect(context.adoption).toEqual({ state: "UNAVAILABLE", reason: "SOURCE_UNAVAILABLE" });
    expect(context.adoptionDecisionSource).toBeNull();
  });

  it("keeps a not-declared adoption summary and no decision source", () => {
    const context = available(projectExecutionContext(caseValue("recorded_source_only"), SELECTION));
    expect(context.adoption).toEqual({ state: "UNAVAILABLE", reason: "NOT_DECLARED" });
    expect(context.adoptionDecisionSource).toBeNull();
  });
});

describe("projectExecutionContext: the unavailable read", () => {
  it("returns the unavailable state and no context field", () => {
    const context = projectExecutionContext(unavailableBody(), SELECTION);
    expect(context).toEqual({ state: "UNAVAILABLE" });
    expect(Object.keys(context)).toEqual(["state"]);
  });

  it("treats two unavailable reads as the same context", () => {
    expect(sameProjectExecutionContext(
      projectExecutionContext(unavailableBody(), SELECTION),
      projectExecutionContext(unavailableBody(), SELECTION),
    )).toBe(true);
  });

  it("never treats an unavailable read as an available context", () => {
    expect(sameProjectExecutionContext(
      projectExecutionContext(unavailableBody(), SELECTION),
      available(projectExecutionContext(caseValue("available_pending"), SELECTION)),
    )).toBe(false);
  });
});

describe("projectExecutionContext: fail closed", () => {
  it("fails closed for a mismatched selection", () => {
    expectInvalid(() => projectExecutionContext(caseValue("available_pending"), { work_ref: "WS:OTHER" }));
    expectInvalid(() => projectExecutionContext(caseValue("available_pending"), { work_ref: "WS:reader" }));
    expectInvalid(() => projectExecutionContext(v1Body(), { work_ref: "WS:OTHER" }));
  });

  it("fails closed for a malformed body", () => {
    const missingTitle = caseValue("available_pending");
    delete missingTitle.plan.title;
    expectInvalid(() => projectExecutionContext(missingTitle, SELECTION));
    const extraKey = caseValue("available_pending");
    extraKey.launch_authority = "GRANTED";
    expectInvalid(() => projectExecutionContext(extraKey, SELECTION));
    const wrongSchema = caseValue("available_pending");
    wrongSchema.schema = "mastermind.workspace_project_plan.v3";
    expectInvalid(() => projectExecutionContext(wrongSchema, SELECTION));
    expectInvalid(() => projectExecutionContext(JSON.stringify(caseValue("available_pending")), SELECTION));
    expectInvalid(() => projectExecutionContext(null, SELECTION));
  });
});

describe("sameProjectExecutionContext", () => {
  const context = (): ProjectExecutionContextAvailable =>
    available(projectExecutionContext(caseValue("available_pending"), SELECTION));

  it("accepts identical contexts whose keys are inserted in another order", () => {
    const frozen = context();
    const current = reorder(frozen);
    expect(Object.keys(current)).not.toEqual(Object.keys(frozen));
    expect(sameProjectExecutionContext(frozen, current)).toBe(true);
    expect(sameProjectExecutionContext(current, frozen)).toBe(true);
  });

  it("detects a changed record source in every property", () => {
    const frozen = context();
    const changed = [
      { ...frozen.recordSource, repository: MASTERMIND },
      { ...frozen.recordSource, commit: "f".repeat(40) },
      { ...frozen.recordSource, path: "agentos/workstreams/WS-PLAN-OTHER.md" },
      { ...frozen.recordSource, content_sha256: "0".repeat(64) },
    ];
    for (const recordSource of changed) {
      expect(sameProjectExecutionContext(frozen, { ...frozen, recordSource })).toBe(false);
    }
  });

  it("detects a changed decision source in every property", () => {
    const frozen = context();
    const decision = frozen.adoptionDecisionSource;
    if (decision === null) throw new Error("expected a captured decision source");
    const changed = [
      { ...decision, repository: MASTERMIND },
      { ...decision, path: "agentos/decisions/DEC-OTHER.md" },
      { ...decision, commit: "f".repeat(40) },
      { ...decision, content_sha256: "0".repeat(64) },
    ];
    for (const adoptionDecisionSource of changed) {
      expect(sameProjectExecutionContext(frozen, { ...frozen, adoptionDecisionSource })).toBe(false);
    }
  });

  it("detects every changed adoption fact", () => {
    const frozen = context();
    const adopted = frozen.adoption;
    if (adopted === null || adopted.state !== "AVAILABLE") throw new Error("expected an available adoption");
    const changed = [
      { ...adopted, decision_ref: "DEC:PLAN-SECOND" },
      { ...adopted, adopted_source: { ...adopted.adopted_source, path: "planning/other.md" } },
      { ...adopted, adopted_source: { ...adopted.adopted_source, content_sha256: "0".repeat(64) } },
      { ...adopted, display_revision: "reviewed-1" },
      { ...adopted, matches_authored_record: !adopted.matches_authored_record },
    ];
    for (const adoption of changed) {
      expect(sameProjectExecutionContext(frozen, { ...frozen, adoption })).toBe(false);
    }
  });

  it("detects a changed unavailable adoption reason between two captured reads", () => {
    const notDeclared = available(projectExecutionContext(caseValue("recorded_source_only"), SELECTION));
    const sameRead = available(projectExecutionContext(caseValue("recorded_source_only"), SELECTION));
    const lineageInvalid = available(projectExecutionContext(caseValue("lineage_invalid"), SELECTION));
    expect(sameProjectExecutionContext(notDeclared, sameRead)).toBe(true);
    expect(sameProjectExecutionContext(notDeclared, lineageInvalid)).toBe(false);
  });

  it("detects a changed unavailable adoption reason and a dropped adoption", () => {
    const frozen: ProjectExecutionContextAvailable = {
      state: "AVAILABLE",
      workRef: WORK_REF,
      title: "Authored record",
      objective: "Real available objective.",
      recordSource: {
        repository: MACRO,
        commit: RECORD_COMMIT,
        path: "agentos/workstreams/WS-PLAN-TEST.md",
        content_sha256: RECORD_SHA,
      },
      adoption: { state: "UNAVAILABLE", reason: "NOT_DECLARED" },
      adoptionDecisionSource: null,
    };
    expect(sameProjectExecutionContext(frozen, { ...frozen })).toBe(true);
    expect(sameProjectExecutionContext(
      frozen,
      { ...frozen, adoption: { state: "UNAVAILABLE", reason: "LINEAGE_INVALID" } },
    )).toBe(false);
    expect(sameProjectExecutionContext(frozen, { ...frozen, adoption: null })).toBe(false);
    expect(sameProjectExecutionContext(
      frozen,
      { ...frozen, adoptionDecisionSource: { ...frozen.recordSource } },
    )).toBe(false);
  });

  it("detects a changed title, objective or work reference", () => {
    const frozen = context();
    expect(sameProjectExecutionContext(frozen, { ...frozen, title: "Other record" })).toBe(false);
    expect(sameProjectExecutionContext(frozen, { ...frozen, objective: "Other objective." })).toBe(false);
    expect(sameProjectExecutionContext(frozen, { ...frozen, workRef: "WS:OTHER" })).toBe(false);
  });
});
