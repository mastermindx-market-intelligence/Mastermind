/** Execution return contract mirror — mastermind.execution_return/v1 and its
 * delivery receipt.
 *
 * Mirrors control_plane/execution_return_projection.py and
 * integrations/session_bridge/hermes_native_return.py exactly: the closed
 * vocabularies below are asserted equal to the committed fixture
 * integrations/mmos/fixtures/execution_return_v1/vocabularies.json by both
 * test suites, and the committed sample record/receipt prove canonical-JSON
 * and digest parity byte-for-byte. Fail-closed: any drift throws
 * EXECUTION_RETURN_INVALID. No transport, no store, no retry, no UI here;
 * delivery ≠ acceptance — acceptance is closed to "not_accepted" in v1 and
 * this parser refuses any other value. The wire is snake_case because these
 * ARE the contract's field names; UI adaptation happens in views. */

export class ExecutionReturnContractError extends Error {
  constructor(public code: string, public detail: string = "") {
    super(detail ? `${code}: ${detail}` : code);
  }
}
function invalid(code: string, detail = ""): never {
  throw new ExecutionReturnContractError(code, detail);
}

// ── the closed vocabularies (the ONE TypeScript place) ─────────────────────
export const EXECUTION_RETURN_STAGES = [
  "result_only", "branch_pushed", "pr_open", "checks_green", "checks_failed",
  "merged", "installed_unknown",
] as const;
export type ExecutionReturnStage = (typeof EXECUTION_RETURN_STAGES)[number];

/** Closed to exactly "not_accepted" in v1 — no lawful producer of "accepted"
 *  exists in this schema generation; user acceptance is a separate act. */
export const ACCEPTANCE_STATES = ["not_accepted"] as const;
export type AcceptanceState = (typeof ACCEPTANCE_STATES)[number];

export const CHECK_CONCLUSIONS = ["success", "failure", "skipped", "unknown"] as const;
export type CheckConclusion = (typeof CHECK_CONCLUSIONS)[number];

export const CHECKS_STATES = ["green", "failed", "unknown"] as const;
export type ChecksState = (typeof CHECKS_STATES)[number];

export const MERGE_STATES = ["merged", "not_merged", "unknown"] as const;
export type MergeState = (typeof MERGE_STATES)[number];

export const INSTALLATION_STATES = ["none_claimed", "claimed_unproven"] as const;
export type InstallationState = (typeof INSTALLATION_STATES)[number];

/** Receipt states; "unknown" is an ambiguous send — honest terminal marker,
 *  never auto-retried. */
export const DELIVERY_STATES = ["delivered", "unknown", "refused"] as const;
export type DeliveryState = (typeof DELIVERY_STATES)[number];

/** Transport refusal codes are preserved verbatim (never re-cased): the
 *  hermes_native seam emits lowercase guard codes, native refusal reasons
 *  uppercase. */
export const REFUSAL_CODE_PATTERN = "[A-Za-z][A-Za-z0-9_]{0,63}";
const refusalCodePattern = new RegExp(`^(?:${REFUSAL_CODE_PATTERN})$`);

export const RECORD_SCHEMA = "mastermind.execution_return/v1";
export const DELIVERY_SCHEMA = "mastermind.execution_return_delivery/v1";
const hex64 = /^[0-9a-f]{64}$/;
const returnIdPattern = /^execret-[0-9a-f]{32}$/;
const submissionIdPattern = /^execret-[0-9a-f]{32}$/;

// ── the wire types ─────────────────────────────────────────────────────────
export interface ExecutionReturnAttempt {
  attempt_id: string; root_id: string; idempotency_key: string;
  authenticated_namespace: string; t3_thread_id: string | null;
  t3_run_id: string | null; seal_digest: string;
}
export interface ExecutionReturnResult { text: string | null; artifact_refs: string[] }
export interface ExecutionReturnCheck { name: string; conclusion: CheckConclusion }
export interface ExecutionReturnGithub {
  branch: string | null; pr_number: number | null; pr_url: string | null;
  checks: ExecutionReturnCheck[] | null; checks_state: ChecksState;
  merge_state: MergeState; installation: InstallationState;
}
export interface ExecutionReturnRequester {
  teammate_id: string; conversation_id: string; project_id: string;
  authenticated_namespace: string;
}
export interface ExecutionReturnRecord {
  schema: typeof RECORD_SCHEMA; return_id: string; digest: string;
  stage: ExecutionReturnStage; acceptance: AcceptanceState;
  acceptance_claim_refused: boolean;
  attempt: ExecutionReturnAttempt; result: ExecutionReturnResult;
  github: ExecutionReturnGithub; original_requester: ExecutionReturnRequester;
}
export interface ExecutionReturnDeliveryReceipt {
  schema: typeof DELIVERY_SCHEMA; return_id: string; return_digest: string;
  conversation_id: string; submission_id: string; state: DeliveryState;
  transport_ref: string | null; refusal_code: string | null;
}

// ── canonical JSON + digests (byte-parity with the Python owner) ──────────
export function canonicalJson(value: unknown): string {
  if (value === null || typeof value !== "object") return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  const entries = Object.entries(value as Record<string, unknown>)
    .filter(([, v]) => v !== undefined)
    .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0));
  return `{${entries.map(([k, v]) => `${JSON.stringify(k)}:${canonicalJson(v)}`).join(",")}}`;
}

async function sha256Hex(text: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, "0")).join("");
}

function recordDigestMaterial(value: Record<string, unknown>): string {
  const material: Record<string, unknown> = {};
  for (const [key, item] of Object.entries(value)) {
    if (key !== "digest" && key !== "return_id") material[key] = item;
  }
  return canonicalJson(material);
}

export async function recordDigest(value: unknown): Promise<string> {
  return sha256Hex(recordDigestMaterial(value as Record<string, unknown>));
}

/** Deterministic native submission id for (return digest, conversation):
 *  same pair ⇒ same id, so a replayed delivery is the SAME native
 *  submission (mirrors the Python mint byte-for-byte). */
export async function mintSubmissionId(returnDigest: string, conversationId: string): Promise<string> {
  const canonical = JSON.stringify({
    conversation_id: conversationId, return_digest: returnDigest,
  });
  const digest = await sha256Hex(canonical);
  return "execret-" + digest.slice(0, 32);
}

// ── shared field validators ────────────────────────────────────────────────
function obj(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) invalid("INVALID_OBJECT");
  return value as Record<string, unknown>;
}
function exactKeys(value: unknown, allowed: string[], label: string): Record<string, unknown> {
  const v = obj(value);
  const keys = Object.keys(v);
  if (keys.some(key => !allowed.includes(key)) || allowed.some(key => !(key in v))) {
    invalid("INVALID_FIELDS", label);
  }
  return v;
}
function text(value: unknown, label: string, maximum: number): string {
  if (typeof value !== "string" || value.length === 0 || value.length > maximum) invalid("INVALID_TEXT", label);
  return value;
}
function nullableText(value: unknown, label: string, maximum: number): string | null {
  return value === null ? null : text(value, label, maximum);
}
function identifier(value: unknown, label: string): string {
  const item = text(value, label, 256);
  if (/[\u0000-\u001f\u007f]/.test(item)) invalid("INVALID_IDENTIFIER", label);
  return item;
}
function nullableIdentifier(value: unknown, label: string): string | null {
  return value === null ? null : identifier(value, label);
}
function positiveInt(value: unknown, label: string): number {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= 1
    ? value : invalid("INVALID_NUMBER", label);
}
function flag(value: unknown, label: string): boolean {
  return typeof value === "boolean" ? value : invalid("INVALID_FLAG", label);
}
function vocabulary<T extends string>(value: unknown, members: readonly T[], label: string): T {
  return members.includes(value as T) ? value as T : invalid("INVALID_VOCABULARY", label);
}

// ── the stage ladder (mirror of the Python derivation) ────────────────────
export function deriveStage(github: Pick<ExecutionReturnGithub,
    "checks" | "checks_state" | "pr_number" | "pr_url" | "branch"
    | "merge_state" | "installation">): ExecutionReturnStage {
  if (github.merge_state === "merged") {
    return github.installation === "claimed_unproven" ? "installed_unknown" : "merged";
  }
  if (github.checks_state === "failed") return "checks_failed";
  if (github.checks_state === "green") return "checks_green";
  if (github.pr_number !== null || github.pr_url !== null) return "pr_open";
  if (github.branch !== null) return "branch_pushed";
  return "result_only";
}

// ── the record parser ──────────────────────────────────────────────────────
export async function parseExecutionReturn(value: unknown): Promise<ExecutionReturnRecord> {
  const v = exactKeys(value, ["schema", "return_id", "digest", "stage", "acceptance",
    "acceptance_claim_refused", "attempt", "result", "github", "original_requester"],
    "record");
  if (v.schema !== RECORD_SCHEMA) invalid("INVALID_SCHEMA", "record");
  const stage = vocabulary(v.stage, EXECUTION_RETURN_STAGES, "stage");
  if (v.acceptance !== "not_accepted") invalid("INVALID_ACCEPTANCE", "acceptance is closed to not_accepted in v1");
  const acceptanceClaimRefused = flag(v.acceptance_claim_refused, "acceptance_claim_refused");

  const a = exactKeys(v.attempt, ["attempt_id", "root_id", "idempotency_key",
    "authenticated_namespace", "t3_thread_id", "t3_run_id", "seal_digest"], "attempt");
  const attempt: ExecutionReturnAttempt = {
    attempt_id: identifier(a.attempt_id, "attempt.attempt_id"),
    root_id: identifier(a.root_id, "attempt.root_id"),
    idempotency_key: identifier(a.idempotency_key, "attempt.idempotency_key"),
    authenticated_namespace: identifier(a.authenticated_namespace, "attempt.authenticated_namespace"),
    t3_thread_id: nullableIdentifier(a.t3_thread_id, "attempt.t3_thread_id"),
    t3_run_id: nullableIdentifier(a.t3_run_id, "attempt.t3_run_id"),
    seal_digest: hex64.test(text(a.seal_digest, "attempt.seal_digest", 64)) ? a.seal_digest as string
      : invalid("INVALID_DIGEST", "attempt.seal_digest"),
  };

  const r = exactKeys(v.result, ["text", "artifact_refs"], "result");
  const result: ExecutionReturnResult = {
    text: r.text === null ? null : text(r.text, "result.text", 8192),
    artifact_refs: Array.isArray(r.artifact_refs) && r.artifact_refs.length <= 16
      ? r.artifact_refs.map(ref => text(ref, "result.artifact_refs", 512))
      : invalid("INVALID_REFS", "result.artifact_refs"),
  };

  const g = exactKeys(v.github, ["branch", "pr_number", "pr_url", "checks",
    "checks_state", "merge_state", "installation"], "github");
  const checks = g.checks === null ? null
    : Array.isArray(g.checks) && g.checks.length <= 64
      ? g.checks.map(row => {
          const c = exactKeys(row, ["name", "conclusion"], "github.checks");
          return { name: text(c.name, "github.checks.name", 256),
                   conclusion: vocabulary(c.conclusion, CHECK_CONCLUSIONS, "github.checks.conclusion") };
        })
      : invalid("INVALID_CHECKS", "github.checks");
  const github: ExecutionReturnGithub = {
    branch: nullableText(g.branch, "github.branch", 256),
    pr_number: g.pr_number === null ? null : positiveInt(g.pr_number, "github.pr_number"),
    pr_url: nullableText(g.pr_url, "github.pr_url", 512),
    checks,
    checks_state: vocabulary(g.checks_state, CHECKS_STATES, "github.checks_state"),
    merge_state: vocabulary(g.merge_state, MERGE_STATES, "github.merge_state"),
    installation: vocabulary(g.installation, INSTALLATION_STATES, "github.installation"),
  };

  const q = exactKeys(v.original_requester, ["teammate_id", "conversation_id",
    "project_id", "authenticated_namespace"], "original_requester");
  const original_requester: ExecutionReturnRequester = {
    teammate_id: identifier(q.teammate_id, "original_requester.teammate_id"),
    conversation_id: identifier(q.conversation_id, "original_requester.conversation_id"),
    project_id: identifier(q.project_id, "original_requester.project_id"),
    authenticated_namespace: identifier(q.authenticated_namespace, "original_requester.authenticated_namespace"),
  };

  const digest = hex64.test(text(v.digest, "digest", 64)) ? v.digest as string
    : invalid("INVALID_DIGEST", "digest");
  // Content-before-derivation: the digest must bind the actual content
  // before the derived identity fields are cross-checked.
  if (await recordDigest(v) !== digest) invalid("DIGEST_MISMATCH", "digest does not match the record content");
  const returnId = text(v.return_id, "return_id", 64);
  if (returnId !== "execret-" + digest.slice(0, 32)) invalid("INVALID_RETURN_ID", "return_id does not derive from the digest");
  if (deriveStage(github) !== stage) invalid("STAGE_EXCEEDS_EVIDENCE", "stage exceeds what the record's own evidence proves");

  return { schema: RECORD_SCHEMA, return_id: returnId, digest, stage,
    acceptance: "not_accepted", acceptance_claim_refused: acceptanceClaimRefused,
    attempt, result, github, original_requester };
}

// ── the delivery receipt parser ───────────────────────────────────────────
export async function parseExecutionReturnDelivery(value: unknown): Promise<ExecutionReturnDeliveryReceipt> {
  const v = exactKeys(value, ["schema", "return_id", "return_digest", "conversation_id",
    "submission_id", "state", "transport_ref", "refusal_code"], "receipt");
  if (v.schema !== DELIVERY_SCHEMA) invalid("INVALID_SCHEMA", "receipt");
  const state = vocabulary(v.state, DELIVERY_STATES, "receipt.state");
  const returnId = text(v.return_id, "receipt.return_id", 256);
  const conversationId = identifier(v.conversation_id, "receipt.conversation_id");
  const returnDigest = hex64.test(text(v.return_digest, "receipt.return_digest", 64))
    ? v.return_digest as string : invalid("INVALID_DIGEST", "receipt.return_digest");
  const submissionId = text(v.submission_id, "receipt.submission_id", 64);
  if (!submissionIdPattern.test(submissionId)) invalid("INVALID_SUBMISSION_ID", "receipt.submission_id");
  if (submissionId !== await mintSubmissionId(returnDigest, conversationId)) {
    invalid("SUBMISSION_ID_MISMATCH", "submission_id does not derive from (digest, conversation)");
  }
  const transportRef = v.transport_ref === null ? null : text(v.transport_ref, "receipt.transport_ref", 256);
  const refusalCode = v.refusal_code === null ? null : text(v.refusal_code, "receipt.refusal_code", 64);
  if (refusalCode !== null && !refusalCodePattern.test(refusalCode)) invalid("INVALID_REFUSAL_CODE", "receipt.refusal_code");
  if (state === "delivered" && transportRef === null) invalid("DELIVERED_WITHOUT_REF", "a delivered receipt carries a transport ref");
  if (state === "unknown" && transportRef !== null) invalid("UNKNOWN_WITH_REF", "an ambiguous receipt cannot carry a transport ref");
  if (state !== "refused" && refusalCode !== null) invalid("CODE_WITHOUT_REFUSAL", "only a refused receipt carries a refusal code");
  if (state === "refused" && refusalCode === null) invalid("REFUSAL_WITHOUT_CODE", "a refused receipt carries a refusal code");
  return { schema: DELIVERY_SCHEMA, return_id: returnId, return_digest: returnDigest,
    conversation_id: conversationId, submission_id: submissionId, state,
    transport_ref: transportRef, refusal_code: refusalCode };
}
