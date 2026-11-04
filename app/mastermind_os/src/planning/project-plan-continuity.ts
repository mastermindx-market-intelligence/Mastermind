/** Pure decoder for the frozen captured project plan continuity projection.
 * The caller passes the inner captured DTO object plus the selected work ref;
 * wire envelopes, strings, bytes and aliases are refused alike. References
 * inside records are plain data: nothing here reads a repository, fetches a
 * path, performs IO, uses a clock, grants adoption, currency, authenticity or
 * Job admission, or verifies captured bytes. Field spelling and nesting match
 * the frozen producer exactly, output is freshly built and detached from the
 * caller's value, and every malformed input raises the single value-free Error
 * PROJECT_PLAN_CONTINUITY_INVALID.
 */
export const PROJECT_PLAN_CONTINUITY_SCHEMA = "mastermind.project_plan_continuity.v1";
export const PROJECT_PLAN_ADOPTION_SCHEMA = "agentos.project_plan_adoption.v1";
export const PROJECT_PLAN_PROPOSAL_SCHEMA = "agentos.project_plan_proposal.v1";
export const CAPTURED_ASSOCIATIONS_ONLY = "CAPTURED_ASSOCIATIONS_ONLY";
export const PROJECT_PLAN_CONTINUITY_INVALID = "PROJECT_PLAN_CONTINUITY_INVALID";

export interface ProjectPlanSourceRef {
  repository: string;
  path: string;
  commit: string;
  content_sha256: string;
}
export interface ProjectPlanAdoptionMetadata {
  schema: typeof PROJECT_PLAN_ADOPTION_SCHEMA;
  work_ref: string;
  adopted_source: ProjectPlanSourceRef;
  predecessor: string | null;
  proposal_source: ProjectPlanSourceRef | null;
  display_revision: string | null;
}
export interface ProjectPlanDecisionDeclaration {
  decision_ref: string;
  decision_source: ProjectPlanSourceRef;
  adoption: ProjectPlanAdoptionMetadata;
  decided_by: string;
  decided_at: string;
}
export interface ProjectPlanAdoptionAvailable {
  state: "AVAILABLE";
  decision_ref: string;
  decision_source: ProjectPlanSourceRef;
  adoption: ProjectPlanAdoptionMetadata;
  decided_by: string;
  decided_at: string;
  content: string;
}
export type ProjectPlanAdoptionUnavailableReason =
  | "SOURCE_UNAVAILABLE" | "NOT_DECLARED" | "LINEAGE_INVALID" | "PROPOSAL_MISMATCH" | "CONTENT_OVER_BUDGET";
export type ProjectPlanAdoptionUnavailable =
  | { state: "UNAVAILABLE"; reason: "NOT_DECLARED" | "LINEAGE_INVALID" | "CONTENT_OVER_BUDGET" }
  | { state: "UNAVAILABLE"; reason: "SOURCE_UNAVAILABLE" | "PROPOSAL_MISMATCH";
      declared_decision?: ProjectPlanDecisionDeclaration };
export type ProjectPlanAdoptionRead = ProjectPlanAdoptionAvailable | ProjectPlanAdoptionUnavailable;

export interface ProjectPlanComparisonAvailable {
  state: "AVAILABLE";
  base_source: ProjectPlanSourceRef;
  candidate_sha256: string;
  base_text: string;
  candidate_text: string;
  diff: string;
  identical: boolean;
  added_lines: number;
  removed_lines: number;
}
export type ProjectPlanComparisonUnavailableReason =
  | "SOURCE_UNAVAILABLE" | "SOURCE_BYTES_MISMATCH" | "INVALID_CONTENT"
  | "CONTENT_OVER_BUDGET" | "STALE_PREDECESSOR" | "PROPOSAL_MISMATCH";
export type ProjectPlanComparisonRead =
  | ProjectPlanComparisonAvailable
  | { state: "UNAVAILABLE"; reason: ProjectPlanComparisonUnavailableReason };

export type ProjectPlanAdoptionRelation =
  | "CURRENT_DECISION_REFERENCES_PROPOSAL" | "UNASSOCIATED_WITH_CURRENT_DECISION";
export type ProjectPlanComparisonBasis =
  | "RECORDED_PREDECESSOR" | "DECLARED_ADOPTION_SOURCE" | "ADOPTED_CONTENT" | "RECORDED_SOURCE";
export type ProjectPlanProposalsUnavailableReason =
  | "SOURCE_UNAVAILABLE" | "LINEAGE_INVALID" | "RECORD_INVALID" | "CONTENT_OVER_BUDGET";
export interface ProjectPlanProposalRecord {
  proposal_source: ProjectPlanSourceRef;
  state: "RECORDED_PROPOSAL";
  schema: typeof PROJECT_PLAN_PROPOSAL_SCHEMA;
  proposal_id: string;
  work_ref: string;
  base_adoption: string | null;
  base_source: ProjectPlanSourceRef;
  candidate_sha256: string;
  rationale: string;
  evidence: ProjectPlanSourceRef[];
  adoption_relation: ProjectPlanAdoptionRelation;
  comparison: ProjectPlanComparisonRead;
  comparison_basis: ProjectPlanComparisonBasis;
}
export interface ProjectPlanProposalInvalid {
  proposal_source: ProjectPlanSourceRef;
  state: "UNAVAILABLE";
  reason: "RECORD_INVALID";
}
export type ProjectPlanProposalEntry = ProjectPlanProposalRecord | ProjectPlanProposalInvalid;
export type ProjectPlanProposalsRead =
  | { state: "AVAILABLE"; items: ProjectPlanProposalEntry[]; coverage: typeof CAPTURED_ASSOCIATIONS_ONLY }
  | { state: "UNAVAILABLE"; reason: ProjectPlanProposalsUnavailableReason;
      coverage: typeof CAPTURED_ASSOCIATIONS_ONLY };
export interface ProjectPlanContinuityRead {
  schema: typeof PROJECT_PLAN_CONTINUITY_SCHEMA;
  work_ref: string;
  adoption: ProjectPlanAdoptionRead;
  proposals: ProjectPlanProposalsRead;
}

const MACRO_REPOSITORY = "mastermindx-market-intelligence/macro";
const MASTERMIND_REPOSITORY = "mastermindx-market-intelligence/Mastermind";
const WORKSTREAM_PREFIX = "agentos/workstreams/";
const MAX_RESULT_BYTES = 131072 - 4096;
const MAX_BODY_BYTES = 262144;
const MAX_BASE_TEXT_BYTES = 262144;
const MAX_CANDIDATE_TEXT_BYTES = 131072;
const MAX_COMPARISON_BYTES = 65536;
const MAX_PATH_CODEPOINTS = 512;
const MAX_DECIDED_BY_CODEPOINTS = 256;
const MAX_DISPLAY_REVISION_CODEPOINTS = 128;
const MAX_RATIONALE_CODEPOINTS = 4096;
const MAX_EVIDENCE_REFS = 32;
const MAX_PROPOSAL_ITEMS = 32;
const MIN_KEY_LENGTH = 2;
const MAX_WORK_KEY_LENGTH = 64;
const MAX_DECISION_KEY_LENGTH = 128;

const COMMIT_DIGEST = /^[0-9a-f]{40}$/;
const CONTENT_DIGEST = /^[0-9a-f]{64}$/;
const UPPER_KEBAB = /^[A-Z0-9-]+$/;
const GREGORIAN_DATE = /^([0-9]{4})-([0-9]{2})-([0-9]{2})$/;
const FORBIDDEN_PATH_UNITS = /[\u0000\r\n\\]/;
const MONTH_DAYS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
const textEncoder = new TextEncoder();

const refuse = (): never => { throw new Error(PROJECT_PLAN_CONTINUITY_INVALID); };
const record = (value: unknown): value is Record<string, unknown> => {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return false;
  const prototype = Object.getPrototypeOf(value);
  return prototype === Object.prototype || prototype === null;
};
const keys = (value: Record<string, unknown>, expected: string[]): boolean =>
  Object.keys(value).length === expected.length && expected.every(key => Object.hasOwn(value, key));
const codePoints = (value: string): number => {
  let count = 0;
  for (let index = 0; index < value.length; index++) {
    count += 1;
    if (value.charCodeAt(index) >= 0xd800 && value.charCodeAt(index) <= 0xdbff) {
      const next = index + 1 < value.length ? value.charCodeAt(index + 1) : 0;
      if (next >= 0xdc00 && next <= 0xdfff) index += 1;
    }
  }
  return count;
};
const strictText = (value: unknown): value is string => {
  if (typeof value !== "string") return false;
  for (let index = 0; index < value.length; index++) {
    const unit = value.charCodeAt(index);
    if (unit >= 0xd800 && unit <= 0xdbff) {
      const next = index + 1 < value.length ? value.charCodeAt(index + 1) : 0;
      if (next < 0xdc00 || next > 0xdfff) return false;
      index += 1;
    } else if (unit >= 0xdc00 && unit <= 0xdfff) {
      return false;
    }
  }
  return true;
};
const utf8Bytes = (value: string): number => textEncoder.encode(value).length;
const isUpperKebab = (value: unknown, min: number, max: number): value is string => {
  if (typeof value !== "string" || value.length < min || value.length > max || !UPPER_KEBAB.test(value))
    return false;
  const bounded = (unit: number): boolean => (unit >= 65 && unit <= 90) || (unit >= 48 && unit <= 57);
  return bounded(value.charCodeAt(0)) && bounded(value.charCodeAt(value.length - 1)) && !value.includes("--");
};
const isWorkRef = (value: unknown): value is string =>
  typeof value === "string" && value.startsWith("WS:") &&
  isUpperKebab(value.slice(3), MIN_KEY_LENGTH, MAX_WORK_KEY_LENGTH);
const isDecisionRef = (value: unknown): value is string =>
  typeof value === "string" && value.startsWith("DEC:") &&
  isUpperKebab(value.slice(4), MIN_KEY_LENGTH, MAX_DECISION_KEY_LENGTH);
const isCount = (value: unknown): value is number =>
  typeof value === "number" && Number.isInteger(value) && value >= 0 && value <= Number.MAX_SAFE_INTEGER;
const enumOf = <Type extends string>(value: unknown, allowed: readonly Type[]): Type => {
  if (typeof value === "string" && (allowed as readonly string[]).includes(value)) return value as Type;
  return refuse();
};

/** Compact JSON with the frozen producer's escaping, used only for budgets. */
const jsonEscape = (value: string): string => {
  let out = '"';
  for (let index = 0; index < value.length; index++) {
    const unit = value.charCodeAt(index);
    if (unit === 0x22) out += '\\"';
    else if (unit === 0x5c) out += "\\\\";
    else if (unit === 0x08) out += "\\b";
    else if (unit === 0x09) out += "\\t";
    else if (unit === 0x0a) out += "\\n";
    else if (unit === 0x0c) out += "\\f";
    else if (unit === 0x0d) out += "\\r";
    else if (unit < 0x20) out += `\\u${unit.toString(16).padStart(4, "0")}`;
    else out += value[index];
  }
  return `${out}"`;
};
const compactJson = (value: unknown): string => {
  if (value === null) return "null";
  if (typeof value === "string") return jsonEscape(value);
  if (typeof value === "number") return String(value);
  if (typeof value === "boolean") return value ? "true" : "false";
  if (Array.isArray(value)) return `[${value.map(compactJson).join(",")}]`;
  const members = Object.keys(value as Record<string, unknown>)
    .map(key => `${jsonEscape(key)}:${compactJson((value as Record<string, unknown>)[key])}`);
  return `{${members.join(",")}}`;
};
const compactJsonBytes = (value: unknown): number => utf8Bytes(compactJson(value));

/** Unicode-code-point bound, matching the producer's character accounting. */
const boundedText = (value: unknown, maxCodePoints: number): string => {
  if (!strictText(value) || value.trim().length === 0 || codePoints(value) > maxCodePoints) return refuse();
  return value;
};
/** Strict UTF-8 body text bounded in bytes with no normalization of any kind. */
const bodyText = (value: unknown, maxBytes: number): string => {
  if (!strictText(value)) return refuse();
  const bytes = utf8Bytes(value);
  if (bytes < 1 || bytes > maxBytes) return refuse();
  return value;
};
const displayRevision = (value: unknown): string => {
  if (!strictText(value) || value.trim().length === 0 || /[\u0000\r\n]/.test(value) ||
      codePoints(value) > MAX_DISPLAY_REVISION_CODEPOINTS) return refuse();
  return value;
};
const gregorianDate = (value: unknown): string => {
  if (typeof value !== "string") return refuse();
  const match = GREGORIAN_DATE.exec(value);
  if (match === null) return refuse();
  const year = Number(match[1]), month = Number(match[2]), day = Number(match[3]);
  if (year < 1 || month < 1 || month > 12) return refuse();
  const leap = (year % 4 === 0 && year % 100 !== 0) || year % 400 === 0;
  const monthDays = month === 2 && leap ? 29 : MONTH_DAYS[month - 1];
  if (day < 1 || day > monthDays) return refuse();
  return value;
};
const sourceRef = (value: unknown): ProjectPlanSourceRef => {
  if (!record(value) || !keys(value, ["repository", "path", "commit", "content_sha256"])) return refuse();
  const repository = value.repository, path = value.path,
    commit = value.commit, content_sha256 = value.content_sha256;
  if (typeof repository !== "string" ||
      (repository !== MACRO_REPOSITORY && repository !== MASTERMIND_REPOSITORY)) return refuse();
  if (!strictText(path) || path.length < 1 || codePoints(path) > MAX_PATH_CODEPOINTS ||
      !path.endsWith(".md") || path.startsWith("/") || FORBIDDEN_PATH_UNITS.test(path)) return refuse();
  for (const component of path.split("/")) {
    if (component === "" || component === "." || component === "..") return refuse();
  }
  if (typeof commit !== "string" || !COMMIT_DIGEST.test(commit)) return refuse();
  if (typeof content_sha256 !== "string" || !CONTENT_DIGEST.test(content_sha256)) return refuse();
  return { repository, path, commit, content_sha256 };
};
const sameSourceRef = (left: ProjectPlanSourceRef, right: ProjectPlanSourceRef): boolean =>
  left.repository === right.repository && left.path === right.path &&
  left.commit === right.commit && left.content_sha256 === right.content_sha256;
const workstreamSourceRef = (value: unknown, workRef: string): ProjectPlanSourceRef => {
  const ref = sourceRef(value);
  if (ref.repository === MACRO_REPOSITORY && ref.path.toLowerCase().startsWith(WORKSTREAM_PREFIX) &&
      ref.path !== `agentos/workstreams/WS-${workRef.slice(3)}.md`) refuse();
  return ref;
};
const decisionSourceRef = (value: unknown, decisionRef: string): ProjectPlanSourceRef => {
  const ref = sourceRef(value);
  if (ref.repository !== MACRO_REPOSITORY || ref.path !== `agentos/decisions/DEC-${decisionRef.slice(4)}.md`)
    refuse();
  return ref;
};
const decisionIdentity = (value: Record<string, unknown>): {
  decision_ref: string; decision_source: ProjectPlanSourceRef;
} => {
  const decision_ref = value.decision_ref;
  if (!isDecisionRef(decision_ref)) return refuse();
  return { decision_ref, decision_source: decisionSourceRef(value.decision_source, decision_ref) };
};

const ADOPTION_REASONS = ["SOURCE_UNAVAILABLE", "NOT_DECLARED", "LINEAGE_INVALID",
  "PROPOSAL_MISMATCH", "CONTENT_OVER_BUDGET"] as const;
const DECLARABLE_REASONS = ["SOURCE_UNAVAILABLE", "PROPOSAL_MISMATCH"] as const;
const COMPARISON_REASONS = ["SOURCE_UNAVAILABLE", "SOURCE_BYTES_MISMATCH", "INVALID_CONTENT",
  "CONTENT_OVER_BUDGET", "STALE_PREDECESSOR", "PROPOSAL_MISMATCH"] as const;
const ADOPTION_RELATIONS = ["CURRENT_DECISION_REFERENCES_PROPOSAL",
  "UNASSOCIATED_WITH_CURRENT_DECISION"] as const;
const COMPARISON_BASES = ["RECORDED_PREDECESSOR", "DECLARED_ADOPTION_SOURCE",
  "ADOPTED_CONTENT", "RECORDED_SOURCE"] as const;
const PROPOSALS_REASONS = ["SOURCE_UNAVAILABLE", "LINEAGE_INVALID", "RECORD_INVALID",
  "CONTENT_OVER_BUDGET"] as const;

const adoptionMetadata = (value: unknown, workRef: string): ProjectPlanAdoptionMetadata => {
  if (!record(value) ||
      !keys(value, ["schema", "work_ref", "adopted_source", "predecessor", "proposal_source", "display_revision"]) ||
      value.schema !== PROJECT_PLAN_ADOPTION_SCHEMA || value.work_ref !== workRef) return refuse();
  const adopted_source = workstreamSourceRef(value.adopted_source, workRef);
  const predecessorValue = value.predecessor;
  const predecessor = predecessorValue === null ? null
    : isDecisionRef(predecessorValue) ? predecessorValue : refuse();
  const proposalValue = value.proposal_source;
  const proposal_source = proposalValue === null ? null : workstreamSourceRef(proposalValue, workRef);
  const displayValue = value.display_revision;
  const display_revision = displayValue === null ? null : displayRevision(displayValue);
  return { schema: PROJECT_PLAN_ADOPTION_SCHEMA, work_ref: workRef, adopted_source,
    predecessor, proposal_source, display_revision };
};
const decisionDeclaration = (value: unknown, workRef: string): ProjectPlanDecisionDeclaration => {
  if (!record(value) ||
      !keys(value, ["decision_ref", "decision_source", "adoption", "decided_by", "decided_at"])) return refuse();
  const { decision_ref, decision_source } = decisionIdentity(value);
  return { decision_ref, decision_source, adoption: adoptionMetadata(value.adoption, workRef),
    decided_by: boundedText(value.decided_by, MAX_DECIDED_BY_CODEPOINTS),
    decided_at: gregorianDate(value.decided_at) };
};
const adoptionRead = (value: unknown, workRef: string): ProjectPlanAdoptionRead => {
  if (!record(value)) return refuse();
  if (value.state === "AVAILABLE") {
    if (!keys(value, ["state", "decision_ref", "decision_source", "adoption",
        "decided_by", "decided_at", "content"])) return refuse();
    const { decision_ref, decision_source } = decisionIdentity(value);
    return { state: "AVAILABLE", decision_ref, decision_source,
      adoption: adoptionMetadata(value.adoption, workRef),
      decided_by: boundedText(value.decided_by, MAX_DECIDED_BY_CODEPOINTS),
      decided_at: gregorianDate(value.decided_at),
      content: bodyText(value.content, MAX_BODY_BYTES) };
  }
  if (value.state !== "UNAVAILABLE") return refuse();
  const reason = enumOf(value.reason, ADOPTION_REASONS);
  const declarable = (DECLARABLE_REASONS as readonly string[]).includes(reason);
  if (Object.hasOwn(value, "declared_decision")) {
    if (!keys(value, ["state", "reason", "declared_decision"]) || !declarable) return refuse();
    return { state: "UNAVAILABLE", reason: reason as "SOURCE_UNAVAILABLE" | "PROPOSAL_MISMATCH",
      declared_decision: decisionDeclaration(value.declared_decision, workRef) };
  }
  if (!keys(value, ["state", "reason"])) return refuse();
  return declarable
    ? { state: "UNAVAILABLE", reason: reason as "SOURCE_UNAVAILABLE" | "PROPOSAL_MISMATCH" }
    : { state: "UNAVAILABLE", reason: reason as "NOT_DECLARED" | "LINEAGE_INVALID" | "CONTENT_OVER_BUDGET" };
};
const comparisonRead = (value: unknown,
    base_source: ProjectPlanSourceRef, candidate_sha256: string): ProjectPlanComparisonRead => {
  if (!record(value)) return refuse();
  if (value.state === "UNAVAILABLE") {
    if (!keys(value, ["state", "reason"])) return refuse();
    return { state: "UNAVAILABLE", reason: enumOf(value.reason, COMPARISON_REASONS) };
  }
  if (value.state !== "AVAILABLE" || !keys(value, ["state", "base_source", "candidate_sha256",
      "base_text", "candidate_text", "diff", "identical", "added_lines", "removed_lines"])) return refuse();
  const recordedBase = sourceRef(value.base_source);
  if (!sameSourceRef(recordedBase, base_source)) return refuse();
  const recordedSha = value.candidate_sha256;
  if (typeof recordedSha !== "string" || !CONTENT_DIGEST.test(recordedSha) ||
      recordedSha !== candidate_sha256) return refuse();
  const base_text = bodyText(value.base_text, MAX_BASE_TEXT_BYTES);
  const candidate_text = bodyText(value.candidate_text, MAX_CANDIDATE_TEXT_BYTES);
  if (!strictText(value.diff)) return refuse();
  if (typeof value.identical !== "boolean" || value.identical !== (base_text === candidate_text)) return refuse();
  if (!isCount(value.added_lines) || !isCount(value.removed_lines)) return refuse();
  if (value.identical && (value.diff !== "" || value.added_lines !== 0 || value.removed_lines !== 0))
    return refuse();
  const comparison: ProjectPlanComparisonAvailable = {
    state: "AVAILABLE", base_source: recordedBase, candidate_sha256: recordedSha,
    base_text, candidate_text, diff: value.diff, identical: value.identical,
    added_lines: value.added_lines, removed_lines: value.removed_lines };
  if (compactJsonBytes(comparison) > MAX_COMPARISON_BYTES) return refuse();
  return comparison;
};
const proposalEntry = (value: unknown, workRef: string): ProjectPlanProposalEntry => {
  if (!record(value)) return refuse();
  if (value.state === "UNAVAILABLE") {
    if (!keys(value, ["proposal_source", "state", "reason"]) || value.reason !== "RECORD_INVALID")
      return refuse();
    return { proposal_source: sourceRef(value.proposal_source), state: "UNAVAILABLE", reason: "RECORD_INVALID" };
  }
  const proposalId = value.proposal_id;
  if (value.state !== "RECORDED_PROPOSAL" || !keys(value, ["proposal_source", "state", "schema",
      "proposal_id", "work_ref", "base_adoption", "base_source", "candidate_sha256", "rationale",
      "evidence", "adoption_relation", "comparison", "comparison_basis"]) ||
      value.schema !== PROJECT_PLAN_PROPOSAL_SCHEMA || value.work_ref !== workRef ||
      !isUpperKebab(proposalId, MIN_KEY_LENGTH, MAX_DECISION_KEY_LENGTH)) return refuse();
  const proposal_source = sourceRef(value.proposal_source);
  const baseAdoptionValue = value.base_adoption;
  const base_adoption = baseAdoptionValue === null ? null
    : isDecisionRef(baseAdoptionValue) ? baseAdoptionValue : refuse();
  const base_source = workstreamSourceRef(value.base_source, workRef);
  const candidateValue = value.candidate_sha256;
  if (typeof candidateValue !== "string" || !CONTENT_DIGEST.test(candidateValue)) return refuse();
  const rationale = boundedText(value.rationale, MAX_RATIONALE_CODEPOINTS);
  const evidenceValue = value.evidence;
  if (!Array.isArray(evidenceValue) || evidenceValue.length > MAX_EVIDENCE_REFS) return refuse();
  const evidence = evidenceValue.map((entry: unknown) => sourceRef(entry));
  return { proposal_source, state: "RECORDED_PROPOSAL", schema: PROJECT_PLAN_PROPOSAL_SCHEMA,
    proposal_id: proposalId, work_ref: workRef, base_adoption, base_source,
    candidate_sha256: candidateValue, rationale, evidence,
    adoption_relation: enumOf(value.adoption_relation, ADOPTION_RELATIONS),
    comparison: comparisonRead(value.comparison, base_source, candidateValue),
    comparison_basis: enumOf(value.comparison_basis, COMPARISON_BASES) };
};
const proposalsRead = (value: unknown, workRef: string): ProjectPlanProposalsRead => {
  if (!record(value)) return refuse();
  if (value.state === "UNAVAILABLE") {
    if (!keys(value, ["state", "reason", "coverage"]) || value.coverage !== CAPTURED_ASSOCIATIONS_ONLY)
      return refuse();
    return { state: "UNAVAILABLE", reason: enumOf(value.reason, PROPOSALS_REASONS),
      coverage: CAPTURED_ASSOCIATIONS_ONLY };
  }
  const itemsValue = value.items;
  if (value.state !== "AVAILABLE" || !keys(value, ["state", "items", "coverage"]) ||
      value.coverage !== CAPTURED_ASSOCIATIONS_ONLY || !Array.isArray(itemsValue) ||
      itemsValue.length > MAX_PROPOSAL_ITEMS) return refuse();
  const seen = new Set<string>();
  const items = itemsValue.map((entry: unknown) => {
    const item = proposalEntry(entry, workRef);
    if (item.state === "RECORDED_PROPOSAL") {
      if (seen.has(item.proposal_id)) return refuse();
      seen.add(item.proposal_id);
    }
    return item;
  });
  return { state: "AVAILABLE", items, coverage: CAPTURED_ASSOCIATIONS_ONLY };
};

/** Decode the frozen captured continuity DTO for one exact selected work ref. */
export function decodeProjectPlanContinuity(value: unknown, expectedWorkRef: string): ProjectPlanContinuityRead {
  if (!isWorkRef(expectedWorkRef) || !record(value) ||
      !keys(value, ["schema", "work_ref", "adoption", "proposals"]) ||
      value.schema !== PROJECT_PLAN_CONTINUITY_SCHEMA || value.work_ref !== expectedWorkRef) return refuse();
  const read: ProjectPlanContinuityRead = {
    schema: PROJECT_PLAN_CONTINUITY_SCHEMA,
    work_ref: expectedWorkRef,
    adoption: adoptionRead(value.adoption, expectedWorkRef),
    proposals: proposalsRead(value.proposals, expectedWorkRef),
  };
  const declaration = read.adoption.state === "AVAILABLE" ? read.adoption
    : "declared_decision" in read.adoption ? read.adoption.declared_decision : undefined;
  if (declaration?.adoption.predecessor === declaration?.decision_ref && declaration !== undefined) refuse();
  if (read.proposals.state === "AVAILABLE") for (const item of read.proposals.items) {
    if (item.state !== "RECORDED_PROPOSAL") continue;
    const pointer = declaration?.adoption.proposal_source;
    const referenced = pointer != null && sameSourceRef(pointer, item.proposal_source);
    const relation = referenced ? "CURRENT_DECISION_REFERENCES_PROPOSAL" : "UNASSOCIATED_WITH_CURRENT_DECISION";
    const basis = referenced ? "RECORDED_PREDECESSOR" : declaration !== undefined
      ? read.adoption.state === "AVAILABLE" ? "ADOPTED_CONTENT" : "DECLARED_ADOPTION_SOURCE" : "RECORDED_SOURCE";
    if (item.adoption_relation !== relation || item.comparison_basis !== basis) refuse();
    if (item.comparison.state === "AVAILABLE") {
      if (declaration !== undefined && read.adoption.state !== "AVAILABLE") refuse();
      if (referenced && item.base_adoption !== declaration?.adoption.predecessor) refuse();
      if (!referenced && declaration !== undefined && (item.base_adoption !== declaration.decision_ref ||
          !sameSourceRef(item.base_source, declaration.adoption.adopted_source))) refuse();
      if (declaration === undefined && item.base_adoption !== null) refuse();
    }
  }
  if (compactJsonBytes(read) > MAX_RESULT_BYTES) return refuse();
  return read;
}
