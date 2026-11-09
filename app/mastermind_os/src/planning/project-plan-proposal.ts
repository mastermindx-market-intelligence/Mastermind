/** Closed proposal metadata. None of these caller-held values is source authority. */
import { planningArguments } from "./project-planning-transport";
import { decodeProjectPlan } from "./project-plan";
import { canonicalJson, sha256Hex } from "../orchestration/operation-key";

export const PLAN_PROPOSAL_ACTION = "publish_project_plan_proposal" as const;
export const PLAN_PROPOSAL_KIND = "project_source_write" as const;
export const PLAN_PROPOSAL_KEY = /^mmos-project-plan-proposal-[0-9a-f]{40}$/;
export const PLAN_PROPOSAL_TARGET = "project-plan-publication.v1:";
export interface PlanProposalRequest {
  schema: "mastermind.project_plan_proposal_request.v1";
  request_id: string;
  work_ref: string;
  expected_commit: string;
  expected_adoption: string | null;
  base_source: {
    repository: string;
    commit: string;
    path: string;
    content_sha256: string;
  };
  selection: { work_ref: string; job_id: string; attempt_id: string };
  result_digest: string;
}
/** Safe original lookup/request metadata only: no plan body, prompt or witness. */
export interface PlanProposalOriginal {
  operation_key: string;
  work_ref: string;
  proposal_request: PlanProposalRequest;
}
export interface PlanProposalPointerTarget {
  schema: "mastermind.project_plan_publication_lookup.v1";
  action: typeof PLAN_PROPOSAL_ACTION;
  request_id: string;
  work_ref: string;
  principal_scope: string;
  request_sha256: string;
  recipe_fingerprint_sha256: string;
}
export interface PlanProposalPreview {
  schema: "mastermind.project_plan_proposal_preview.v1";
  work_ref: string;
  status: "DRAFT_ONLY";
  expected_commit: string;
  expected_adoption: string | null;
  proposal_id: string;
  proposal_path: string;
  candidate_sha256: string;
  base_source: PlanProposalRequest["base_source"];
  result_digest: string;
  edited_paths: string[];
}
export function proposalUnavailable(): never {
  throw Error("PLAN_PROPOSAL_UNAVAILABLE");
}
export function proposalRecord(
  value: unknown,
  keys: readonly string[],
): Record<string, unknown> {
  if (
    value === null ||
    typeof value !== "object" ||
    Array.isArray(value) ||
    ![Object.prototype, null].includes(Object.getPrototypeOf(value))
  )
    return proposalUnavailable();
  const descriptors = Object.getOwnPropertyDescriptors(value),
    names = Reflect.ownKeys(descriptors);
  if (
    names.length !== keys.length ||
    names.some((k) => typeof k !== "string" || !keys.includes(k))
  )
    return proposalUnavailable();
  for (const key of keys)
    if (!descriptors[key] || !("value" in descriptors[key]))
      return proposalUnavailable();
  return value as Record<string, unknown>;
}
export function proposalHex(value: unknown): string {
  if (typeof value !== "string" || /^[0-9a-f]{64}$/.exec(value)?.[0] !== value)
    return proposalUnavailable();
  return value;
}
export function proposalWork(value: unknown): value is string {
  return (
    typeof value === "string" &&
    value.length >= 5 &&
    value.length <= 67 &&
    /^WS:[A-Z0-9]+(?:-[A-Z0-9]+)*$/.exec(value)?.[0] === value
  );
}
export function freezeProposal<T>(value: T): T {
  if (value && typeof value === "object") {
    Object.values(value).forEach(freezeProposal);
    Object.freeze(value);
  }
  return value;
}
export function decodePlanProposalOriginal(
  value: unknown,
  workRef?: string,
): PlanProposalOriginal {
  try {
    const v = proposalRecord(value, [
      "operation_key",
      "work_ref",
      "proposal_request",
    ]);
    if (
      !proposalWork(v.work_ref) ||
      (workRef !== undefined && v.work_ref !== workRef) ||
      typeof v.operation_key !== "string" ||
      /^mmos-project-planning-[0-9a-f]{40}$/.exec(v.operation_key)?.[0] !==
        v.operation_key
    )
      return proposalUnavailable();
    const p = proposalRecord(v.proposal_request, [
      "schema",
      "request_id",
      "work_ref",
      "expected_commit",
      "expected_adoption",
      "base_source",
      "selection",
      "result_digest",
    ]);
    proposalRecord(p.base_source, [
      "repository",
      "commit",
      "path",
      "content_sha256",
    ]);
    proposalRecord(p.selection, ["work_ref", "job_id", "attempt_id"]);
    const checked = planningArguments("prepare_proposal", v);
    // Persist only exact closed identifiers: JS end anchors alone also match
    // before a final line break, which is never an issued owner identifier.
    const p2 = checked.proposal_request as PlanProposalRequest;
    if (
      PLAN_PROPOSAL_KEY.exec(p2.request_id)?.[0] !== p2.request_id ||
      ![p2.expected_commit, p2.base_source.commit].every(
        (x) => /^[a-f0-9]{40}$/.exec(x)?.[0] === x,
      ) ||
      ![p2.result_digest, p2.base_source.content_sha256].every(
        (x) => /^[a-f0-9]{64}$/.exec(x)?.[0] === x,
      ) ||
      ![p2.selection.job_id, p2.selection.attempt_id].every(
        (x) => /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/.exec(x)?.[0] === x,
      ) ||
      (p2.expected_adoption !== null &&
        /^DEC:[A-Z0-9]+(?:-[A-Z0-9]+)*$/.exec(p2.expected_adoption)?.[0] !==
          p2.expected_adoption) ||
      /[\r\n]/.test(p2.base_source.path)
    )
      return proposalUnavailable();
    if (new TextEncoder().encode(canonicalJson(checked)).length > 4096)
      return proposalUnavailable();
    return freezeProposal(checked as unknown as PlanProposalOriginal);
  } catch {
    return proposalUnavailable();
  }
}
export function serializePlanProposalOriginal(
  value: PlanProposalOriginal,
): string {
  return canonicalJson(decodePlanProposalOriginal(value));
}
export function parsePlanProposalOriginal(
  value: string,
  workRef: string,
): PlanProposalOriginal {
  try {
    if (typeof value !== "string" || value.length > 4096)
      return proposalUnavailable();
    const result = decodePlanProposalOriginal(JSON.parse(value), workRef);
    if (canonicalJson(result) !== value) return proposalUnavailable();
    return result;
  } catch {
    return proposalUnavailable();
  }
}
export function planProposalOriginalFromRead(input: {
  read: unknown;
  workRef: string;
  planningOperationKey: string;
  requestId: string;
  jobId: string;
  attemptId: string;
  resultDigest: string;
}): PlanProposalOriginal {
  try {
    const read = decodeProjectPlan(input.read, { work_ref: input.workRef });
    if (
      read.schema !== "mastermind.workspace_project_plan.v2" ||
      read.availability !== "AVAILABLE"
    )
      return proposalUnavailable();
    const adopted = read.continuity.adoption;
    const expected =
      adopted.state === "AVAILABLE"
        ? adopted.decision_ref
        : adopted.reason === "NOT_DECLARED"
          ? null
          : undefined;
    if (expected === undefined) return proposalUnavailable();
    const base =
      adopted.state === "AVAILABLE"
        ? adopted.adoption.adopted_source
        : read.source;
    return decodePlanProposalOriginal(
      {
        operation_key: input.planningOperationKey,
        work_ref: input.workRef,
        proposal_request: {
          schema: "mastermind.project_plan_proposal_request.v1",
          request_id: input.requestId,
          work_ref: input.workRef,
          expected_commit: read.source.commit,
          expected_adoption: expected,
          base_source: base,
          selection: {
            work_ref: input.workRef,
            job_id: input.jobId,
            attempt_id: input.attemptId,
          },
          result_digest: input.resultDigest,
        },
      },
      input.workRef,
    );
  } catch {
    return proposalUnavailable();
  }
}
export function planProposalRequestSha(original: PlanProposalOriginal): string {
  return sha256Hex(
    canonicalJson(decodePlanProposalOriginal(original).proposal_request),
  );
}
export function planProposalPath(request: PlanProposalRequest): string {
  return `research/project-plans/PLAN-${request.work_ref.slice(3)}-${request.request_id.slice(-40)}.md`;
}
export function decodePlanProposalPreview(
  value: unknown,
  request: PlanProposalRequest,
): PlanProposalPreview {
  const v = proposalRecord(value, [
    "schema",
    "work_ref",
    "status",
    "expected_commit",
    "expected_adoption",
    "proposal_id",
    "proposal_path",
    "candidate_sha256",
    "base_source",
    "result_digest",
    "edited_paths",
  ]);
  const base = proposalRecord(v.base_source, [
    "repository",
    "commit",
    "path",
    "content_sha256",
  ]);
  const paths = v.edited_paths;
  if (
    !Array.isArray(paths) ||
    Object.getPrototypeOf(paths) !== Array.prototype ||
    paths.length !== 2 ||
    Reflect.ownKeys(paths).length !== 3
  )
    return proposalUnavailable();
  const expectedPaths = [
    planProposalPath(request),
    `agentos/workstreams/WS-${request.work_ref.slice(3)}.md`,
  ];
  for (let i = 0; i < 2; i++) {
    const d = Object.getOwnPropertyDescriptor(paths, String(i));
    if (!d || !("value" in d) || d.value !== expectedPaths[i])
      return proposalUnavailable();
  }
  if (
    v.schema !== "mastermind.project_plan_proposal_preview.v1" ||
    v.status !== "DRAFT_ONLY" ||
    v.work_ref !== request.work_ref ||
    v.expected_commit !== request.expected_commit ||
    v.expected_adoption !== request.expected_adoption ||
    v.proposal_id !== `PLAN-${request.request_id.slice(-40)}` ||
    v.proposal_path !== planProposalPath(request) ||
    v.result_digest !== request.result_digest ||
    !Object.keys(base).every(
      (k) =>
        base[k] === request.base_source[k as keyof typeof request.base_source],
    )
  )
    return proposalUnavailable();
  proposalHex(v.candidate_sha256);
  return freezeProposal(JSON.parse(JSON.stringify(v)) as PlanProposalPreview);
}
export function parsePlanProposalTarget(
  value: unknown,
): PlanProposalPointerTarget | null {
  try {
    if (
      typeof value !== "string" ||
      value.length > 2048 ||
      !value.startsWith(PLAN_PROPOSAL_TARGET)
    )
      return null;
    const text = value.slice(PLAN_PROPOSAL_TARGET.length),
      parsed = JSON.parse(text);
    const t = proposalRecord(parsed, [
      "schema",
      "action",
      "request_id",
      "work_ref",
      "principal_scope",
      "request_sha256",
      "recipe_fingerprint_sha256",
    ]);
    if (
      t.schema !== "mastermind.project_plan_publication_lookup.v1" ||
      t.action !== PLAN_PROPOSAL_ACTION ||
      typeof t.request_id !== "string" ||
      PLAN_PROPOSAL_KEY.exec(t.request_id)?.[0] !== t.request_id ||
      !proposalWork(t.work_ref) ||
      canonicalJson(t) !== text
    )
      return null;
    proposalHex(t.principal_scope);
    proposalHex(t.request_sha256);
    proposalHex(t.recipe_fingerprint_sha256);
    return freezeProposal(t as unknown as PlanProposalPointerTarget);
  } catch {
    return null;
  }
}
export function planProposalTarget(target: PlanProposalPointerTarget): string {
  const encoded = PLAN_PROPOSAL_TARGET + canonicalJson(target);
  if (!parsePlanProposalTarget(encoded)) return proposalUnavailable();
  return encoded;
}
