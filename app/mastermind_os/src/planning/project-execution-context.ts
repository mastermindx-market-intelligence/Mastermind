/** Pure, detached execution context over ONE decoded project-plan read.
 *
 * The context names the authored record and the captured provenance of that
 * record so a caller can tell whether the record it is about to work on is
 * still the record it read. It derives NOTHING from the authored ``status``,
 * ``waves`` or ``next_action``: those are producer-owned record state, never
 * task readiness, never launch authority and never a binding between a run
 * and a plan. A context is not a plan, a schedule, an approval or a receipt.
 *
 * Like the decoders it reuses, this module is PURE: no I/O, no clock, no
 * network, no store, no lifecycle, no side effect. The public body is read
 * through ``decodeProjectPlan`` alone -- no second parser, no second
 * validation, no alternate input shape -- so malformed or mismatched input
 * fails closed with that decoder's own value-free ``PROJECT_PLAN_INVALID``.
 *
 * The context never aliases the decoded read: every nested value is rebuilt,
 * so a caller cannot reach the read and a later mutation of the read cannot
 * reach the context.
 */

import { BODY_SCHEMA_V2, decodeProjectPlan, type ProjectPlanAdoptionSummary,
  type ProjectPlanSelection, type ProjectPlanSourceIdentity } from "./project-plan";
import type { ProjectPlanSourceRef } from "./project-plan-continuity";

/** The detached context of one qualified, available project-plan read. */
export interface ProjectExecutionContextAvailable {
  readonly state: "AVAILABLE";
  /** The selected work reference this context was read for. */
  readonly workRef: string;
  readonly title: string;
  readonly objective: string;
  /** The pinned identity of the authored record that was read. */
  readonly recordSource: ProjectPlanSourceIdentity;
  /** The captured adoption summary, or null on a v1 read that carries none. */
  readonly adoption: ProjectPlanAdoptionSummary | null;
  /** The captured decision record, or null unless the decision is AVAILABLE. */
  readonly adoptionDecisionSource: ProjectPlanSourceRef | null;
}

/** The qualified read exists but reports the plan as unavailable. */
export interface ProjectExecutionContextUnavailable {
  readonly state: "UNAVAILABLE";
}

export type ProjectExecutionContext =
  | ProjectExecutionContextAvailable
  | ProjectExecutionContextUnavailable;

const copySourceIdentity = (source: ProjectPlanSourceIdentity): ProjectPlanSourceIdentity => ({
  repository: source.repository,
  commit: source.commit,
  path: source.path,
  content_sha256: source.content_sha256,
});

const copySourceRef = (source: ProjectPlanSourceRef): ProjectPlanSourceRef => ({
  repository: source.repository,
  path: source.path,
  commit: source.commit,
  content_sha256: source.content_sha256,
});

const copyAdoption = (adoption: ProjectPlanAdoptionSummary): ProjectPlanAdoptionSummary =>
  adoption.state === "AVAILABLE"
    ? {
        state: "AVAILABLE",
        decision_ref: adoption.decision_ref,
        adopted_source: copySourceRef(adoption.adopted_source),
        display_revision: adoption.display_revision,
        matches_authored_record: adoption.matches_authored_record,
      }
    : { state: "UNAVAILABLE", reason: adoption.reason };

/**
 * Project the execution context of one project-plan read.
 *
 * The public body is decoded once through the existing strict decoder, which
 * validates it and reconstructs a detached read. A qualified but unavailable
 * read yields the unavailable state; an available v1 read carries no adoption
 * at all (null), while an available v2 read keeps the exact captured adoption
 * summary and, only when the captured decision itself is AVAILABLE, the
 * decision record that carries it.
 */
export function projectExecutionContext(
  value: unknown,
  selection: ProjectPlanSelection,
): ProjectExecutionContext {
  const read = decodeProjectPlan(value, selection);
  if (read.availability !== "AVAILABLE") return { state: "UNAVAILABLE" };
  if (read.schema === BODY_SCHEMA_V2) {
    const decision = read.continuity.adoption;
    return {
      state: "AVAILABLE",
      workRef: read.selection.work_ref,
      title: read.plan.title,
      objective: read.plan.objective,
      recordSource: copySourceIdentity(read.source),
      adoption: copyAdoption(read.plan.adoption),
      adoptionDecisionSource:
        decision.state === "AVAILABLE" ? copySourceRef(decision.decision_source) : null,
    };
  }
  return {
    state: "AVAILABLE",
    workRef: read.selection.work_ref,
    title: read.plan.title,
    objective: read.plan.objective,
    recordSource: copySourceIdentity(read.source),
    // A v1 read declares no adoption at all: it is not an unavailable
    // adoption, it is no adoption.
    adoption: null,
    adoptionDecisionSource: null,
  };
}

const sameSourceIdentity = (
  left: ProjectPlanSourceIdentity,
  right: ProjectPlanSourceIdentity,
): boolean =>
  left.repository === right.repository &&
  left.commit === right.commit &&
  left.path === right.path &&
  left.content_sha256 === right.content_sha256;

const sameSourceRef = (
  left: ProjectPlanSourceRef | null,
  right: ProjectPlanSourceRef | null,
): boolean => {
  if (left === null || right === null) return left === right;
  return left.repository === right.repository &&
    left.path === right.path &&
    left.commit === right.commit &&
    left.content_sha256 === right.content_sha256;
};

const sameAdoption = (
  left: ProjectPlanAdoptionSummary | null,
  right: ProjectPlanAdoptionSummary | null,
): boolean => {
  if (left === null || right === null) return left === right;
  if (left.state === "UNAVAILABLE") {
    return right.state === "UNAVAILABLE" && left.reason === right.reason;
  }
  if (right.state === "UNAVAILABLE") return false;
  return left.decision_ref === right.decision_ref &&
    sameSourceRef(left.adopted_source, right.adopted_source) &&
    left.display_revision === right.display_revision &&
    left.matches_authored_record === right.matches_authored_record;
};

/**
 * Exact structural comparison of two execution contexts.
 *
 * Every context field is compared by value, so the result does not depend on
 * the order in which any object's keys were inserted, and no serialized form
 * is involved. Two unavailable reads are the same context; an unavailable read
 * is never the same context as an available one.
 */
export function sameProjectExecutionContext(
  frozen: ProjectExecutionContext,
  current: ProjectExecutionContext,
): boolean {
  if (frozen.state === "UNAVAILABLE") return current.state === "UNAVAILABLE";
  if (current.state === "UNAVAILABLE") return false;
  return frozen.workRef === current.workRef &&
    frozen.title === current.title &&
    frozen.objective === current.objective &&
    sameSourceIdentity(frozen.recordSource, current.recordSource) &&
    sameAdoption(frozen.adoption, current.adoption) &&
    sameSourceRef(frozen.adoptionDecisionSource, current.adoptionDecisionSource);
}
