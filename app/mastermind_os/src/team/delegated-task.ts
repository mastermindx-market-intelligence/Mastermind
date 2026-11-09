/** Delegated-task projection for the card surfaces (TD03 "Coding now", HC05).
 *
 * The identity/admission block mirrors the REAL shared admission contract,
 * `control_plane/child_execution_contracts.py` (`ExecutionBinding` v1/v1.1
 * issued from `ChildExecutionRequest` v1/v1.1): field names and vocabularies
 * below are the Python contract's own, snake_case preserved (same rule as
 * `src/hermes-native/execution-return-contract.ts` — the wire names ARE the
 * contract's names; UI adaptation happens in views).
 *
 * Laws mirrored from the Python owner:
 * - the placement identity triple is `(root_run_ref, immediate_parent_run_ref,
 *   logical_child_key)`; triple fields are bounded printable identifiers
 *   (never a control/`\x1f` separator — the durable command-id join law);
 * - `request_digest` is a 64-char lowercase hex sha256;
 * - `effective_complexity` uses the canonical LONG names; `C0`..`C3` display
 *   shorthand is normalized on input and never persisted;
 * - `runtime_kind` is an OPEN vocabulary (core kinds documented in
 *   `KNOWN_RUNTIME_KINDS`; newer runtimes pass through), strip+lower on input,
 *   empty string = unset;
 * - sparse v1.1: extension fields (`runtime_kind`, `operation_key`,
 *   `caller_namespace`, `lease_ref`) are optional; a binding with none of them
 *   set IS a plain v1 binding and its schema tag normalizes to
 *   `ExecutionBinding.v1`.
 *
 * PENDING the v1.2 requester block (Director C2;
 * `integrations/mmos/LANE_RETURN_PATH_DIRECTOR_F.md` gap #1): the
 * original-requester facts (`teammate_id`, `conversation_id`, `project_id`)
 * are NOT in `ChildExecutionRequest`/`ExecutionBinding` v1.1. They are listed
 * in `PENDING_REQUESTER_FIELDS` and deliberately absent from this type — this
 * projection never invents contract fields the Python side lacks. Until v1.2
 * lands, requester facts on return surfaces come from
 * `mastermind.execution_return/v1`'s `original_requester` block instead.
 *
 * Presentation-only fields (`title`, `summary`, `state*`, `owner`, `route`,
 * `authority`, `lastActivity`) are display observations, not contract fields;
 * they are marked as such and carry their own honest-state rules.
 * `authority: "preview"` mirrors `RoutePreview.v1`'s fixed
 * `PREVIEW_AUTHORITY = "NONE_SOURCE_PREVIEW_ONLY"` — a preview is never a
 * launch grant; only a real admitted handoff can carry dispatch authority,
 * and the UI never mints it.
 */
export type DelegatedTaskState =
  "queued" | "running" | "unknown" | "declined" | "terminal";

/** Canonical task-complexity long names at the shared boundary
 *  (`CANONICAL_TASK_COMPLEXITIES` + the separate `REVIEWER` lane). */
export const TASK_COMPLEXITIES = [
  "C0_MECHANICAL", "C1_ROUTINE_BOUNDED", "C2_COMPLEX_BOUNDED",
  "C3_FRONTIER_JUDGMENT", "REVIEWER",
] as const;
export type TaskComplexity = (typeof TASK_COMPLEXITIES)[number];

/** `KNOWN_RUNTIME_KINDS` — documented core kinds; the vocabulary stays OPEN
 *  (validated non-blank, not membership) exactly like the Python contract. */
export const KNOWN_RUNTIME_KINDS = [
  "hermes-native", "t3-native", "dsh-acp", "opencode-free-cli",
  "fabric-native", "codex-cli", "claude-code", "acp", "api-direct",
] as const;

/** Original-requester fields PENDING the ChildExecutionRequest/ExecutionBinding
 *  v1.2 requester block (Director C2). Documentation of a gap, not a type:
 *  `DelegatedTaskBinding` refuses these keys until the Python contract has
 *  them. */
export const PENDING_REQUESTER_FIELDS = [
  "teammate_id", "conversation_id", "project_id",
] as const;

export const BINDING_SCHEMA_V1 = "ExecutionBinding.v1";
export const BINDING_SCHEMA_V1_1 = "ExecutionBinding.v1.1";

/** The admission-contract block, exactly as `ExecutionBinding.to_dict()`
 *  spells it (subset the UI consumes; sparse v1.1 semantics preserved). */
export interface DelegatedTaskBinding {
  schema: typeof BINDING_SCHEMA_V1 | typeof BINDING_SCHEMA_V1_1;
  root_run_ref: string;
  immediate_parent_run_ref: string;
  logical_child_key: string;
  request_digest: string;
  effective_complexity: TaskComplexity;
  task_kind: string;
  /** v1.1 extensions; "" = unset (a plain v1 binding). */
  runtime_kind: string;
  operation_key: string;
  caller_namespace: string;
  lease_ref: string;
}

export interface DelegatedTask {
  binding: DelegatedTaskBinding;
  title: string;
  summary: string | null;
  state: DelegatedTaskState;
  /** Honest state reason (why unknown/declined, or terminal outcome). */
  stateReason: string | null;
  owner: string | null;
  route: readonly string[];
  authority: "preview" | "dispatch";
  lastActivity: string | null;
}

// ── shared field validators (mirror the Python contract's own fences) ──────
function invalid(detail: string): never {
  throw new Error(`DELEGATED_TASK_INVALID: ${detail}`);
}

const IDENTIFIER_MAX = 256; // BOUNDED_IDENTIFIER_MAX_LENGTH
const HEX64 = /^[0-9a-f]{64}$/;
const COMPLEXITY_ALIASES: Record<string, TaskComplexity> = {
  c0: "C0_MECHANICAL", c1: "C1_ROUTINE_BOUNDED", c2: "C2_COMPLEX_BOUNDED",
  c3: "C3_FRONTIER_JUDGMENT", reviewer: "REVIEWER",
  c0_mechanical: "C0_MECHANICAL", c1_routine_bounded: "C1_ROUTINE_BOUNDED",
  c2_complex_bounded: "C2_COMPLEX_BOUNDED",
  c3_frontier_judgment: "C3_FRONTIER_JUDGMENT",
};

/** Bounded printable identifier — the idempotency-triple fence: a field that
 *  could carry a control character (notably `\x1f`) would let two distinct
 *  triples hash to one command id. */
function boundedIdentifier(value: unknown, field: string): string {
  if (typeof value !== "string" || value.length === 0) invalid(`${field} must be a non-empty string`);
  if (value.length > IDENTIFIER_MAX) invalid(`${field} exceeds ${IDENTIFIER_MAX} characters`);
  for (const char of value) {
    if (char < " " || char === "\x7f") invalid(`${field} must be printable (no control characters)`);
  }
  return value;
}

function optionalIdentifier(value: unknown, field: string): string {
  return value === "" ? "" : boundedIdentifier(value, field);
}

function canonicalComplexity(value: unknown, field: string): TaskComplexity {
  if (typeof value !== "string" || value.length === 0) invalid(`${field} is required`);
  const alias = COMPLEXITY_ALIASES[value.toLowerCase()];
  if (alias) return alias;
  if ((TASK_COMPLEXITIES as readonly string[]).includes(value)) return value as TaskComplexity;
  invalid(`${field} ${JSON.stringify(value)} is not a canonical class`);
}

function exactKeys(
  value: unknown,
  allowed: readonly string[],
  label: string,
): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) invalid(`${label} must be an object`);
  const object = value as Record<string, unknown>;
  const keys = Object.keys(object);
  if (keys.some((key) => !allowed.includes(key))) invalid(`${label} carries a field the contract does not define`);
  if (allowed.some((key) => !(key in object))) invalid(`${label} is missing a contract field`);
  return object;
}

function text(value: unknown, field: string, maximum: number): string {
  if (typeof value !== "string" || value.length === 0 || value.length > maximum)
    invalid(`${field} must be 1..${maximum} characters`);
  return value;
}

function optionalText(value: unknown, field: string, maximum: number): string | null {
  return value === null ? null : text(value, field, maximum);
}

const STATES: readonly DelegatedTaskState[] = ["queued", "running", "unknown", "declined", "terminal"];

/** Parse the binding block. Fail-closed on anything the Python
 *  `ExecutionBinding` would refuse; the sparse v1.1 schema tag is RE-DERIVED
 *  from the extension content, never trusted from the wire. */
function parseBinding(value: unknown): DelegatedTaskBinding {
  const raw = { ...(value as Record<string, unknown>) };
  const schema = raw.schema;
  delete raw.schema;
  if (schema !== undefined && schema !== BINDING_SCHEMA_V1 && schema !== BINDING_SCHEMA_V1_1)
    invalid("binding.schema must be ExecutionBinding.v1 or ExecutionBinding.v1.1");
  const v = exactKeys(raw, [
    "root_run_ref", "immediate_parent_run_ref", "logical_child_key",
    "request_digest", "effective_complexity", "task_kind", "runtime_kind",
    "operation_key", "caller_namespace", "lease_ref",
  ], "binding");
  // strip+lower exactly like the Python owner; whitespace-only reads as unset
  const runtimeKind = v.runtime_kind === "" || v.runtime_kind === undefined
    ? "" : String(v.runtime_kind).trim().toLowerCase();
  const binding: DelegatedTaskBinding = {
    schema: BINDING_SCHEMA_V1,
    root_run_ref: boundedIdentifier(v.root_run_ref, "binding.root_run_ref"),
    immediate_parent_run_ref: boundedIdentifier(v.immediate_parent_run_ref, "binding.immediate_parent_run_ref"),
    logical_child_key: boundedIdentifier(v.logical_child_key, "binding.logical_child_key"),
    request_digest: typeof v.request_digest === "string" && HEX64.test(v.request_digest)
      ? v.request_digest : invalid("binding.request_digest must be 64-char lowercase hex"),
    effective_complexity: canonicalComplexity(v.effective_complexity, "binding.effective_complexity"),
    task_kind: v.task_kind === "" || v.task_kind === undefined ? "" : optionalIdentifier(v.task_kind, "binding.task_kind"),
    runtime_kind: runtimeKind,
    operation_key: v.operation_key === "" || v.operation_key === undefined ? "" : optionalIdentifier(v.operation_key, "binding.operation_key"),
    caller_namespace: v.caller_namespace === "" || v.caller_namespace === undefined ? "" : optionalIdentifier(v.caller_namespace, "binding.caller_namespace"),
    lease_ref: v.lease_ref === "" || v.lease_ref === undefined ? "" : optionalIdentifier(v.lease_ref, "binding.lease_ref"),
  };
  // Sparse v1.1: only extension CONTENT upgrades the schema tag; a wire
  // record labelled v1.1 with no extensions normalizes to a plain v1.
  const hasExtensions = Boolean(
    binding.runtime_kind || binding.operation_key ||
    binding.caller_namespace || binding.lease_ref);
  binding.schema = hasExtensions ? BINDING_SCHEMA_V1_1 : BINDING_SCHEMA_V1;
  return binding;
}

/** Fail-closed parser for a delegated-task projection: the admission binding
 *  must satisfy the shared contract's own fences, and the honest-state rules
 *  hold at the presentation layer. Throws DELEGATED_TASK_INVALID on any
 *  defect; never returns a partial record. */
export function parseDelegatedTask(value: unknown): DelegatedTask {
  const v = exactKeys(value, [
    "binding", "title", "summary", "state", "stateReason", "owner",
    "route", "authority", "lastActivity",
  ], "task");
  if (!STATES.includes(v.state as DelegatedTaskState)) invalid("task.state is not a known state");
  const state = v.state as DelegatedTaskState;
  const stateReason = optionalText(v.stateReason, "task.stateReason", 480);
  if ((state === "unknown" || state === "declined") && stateReason === null)
    invalid(`task.stateReason is required when state is ${state}`);
  if (!Array.isArray(v.route) || v.route.length > 6)
    invalid("task.route must be an array of at most 6 chips");
  const route = v.route.map((chip) => text(chip, "task.route", 64));
  if (v.authority !== "preview" && v.authority !== "dispatch")
    invalid("task.authority must be preview or dispatch");
  return {
    binding: parseBinding(v.binding),
    title: text(v.title, "task.title", 240),
    summary: optionalText(v.summary, "task.summary", 480),
    state,
    stateReason,
    owner: optionalText(v.owner, "task.owner", 240),
    route,
    authority: v.authority,
    lastActivity: optionalText(v.lastActivity, "task.lastActivity", 40),
  };
}
