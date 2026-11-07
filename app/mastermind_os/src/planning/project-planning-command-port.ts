/**
 * ProjectPlanningCommandPort — the accepted S19 projectPlanning transport
 * adapted onto the existing {@link FiniteCommandPort} contract.
 *
 * SCOPE. This module is a pure adapter: no backend, no wire runtime selection,
 * no store, no lifecycle and no admission authority. The injected
 * {@link ProjectPlanningTransport} is the only external boundary, and the
 * caller keeps owning the existing OperationController / PendingPointerStore
 * pairing — this class neither holds nor mints either one, and it mutates no
 * state of its own on construction, prepare or status reads.
 *
 * IDENTITY. `operation_key` is a deterministic canonical SHA-256 over the
 * principal scope plus the exact request identity and bytes (stage, project
 * source digests, publication reference, grounding and the private request
 * text itself, which the source's `request_sha256` also commits to) computed
 * with the incumbent `canonicalJson` / `sha256Hex` pair, so the same qualified
 * request always yields the same key and any edited byte yields a different
 * one. The
 * status identity mirrors the S19 `operation_intent_id` digest over
 * `{operation_key, principal_scope}`; it is derived locally and compared
 * against the receipt, never accepted from the wire as proof of identity.
 *
 * PRIVACY. `CommandIntent.payload` carries the private request text for the
 * one submit call and is never persisted: the pointer embeds only the safe
 * status lookup (`operation_key` + `work_ref` behind an opaque
 * `project-initial-planning.v1:` target prefix), and receipt reasons carry
 * fixed disposition codes only — never producer text and never request text.
 *
 * RECEIPTS. Only the closed S19 direct native ceo receipt
 * (`mastermind.ceo_direct_native_receipt.v1`) with `accepted === true`, a
 * closed key set, an exact `work_ref` and the locally derived `intent_id` may
 * publish an acceptance carrying a mission selection. Anything malformed,
 * foreign or merely uncertain is reported as an unknown receipt. Refusals are
 * never inferred from arbitrary error text or from a non-accepted receipt, and
 * unknown outcomes stay with the incumbent controller, which retains the
 * pointer for a later recover.
 */

import type {
  CommandIntent,
  EffectReceipt,
  FiniteCommandPort,
  OperationPointer,
  OwnerContext,
} from "../orchestration/operation-controller";
import type { MissionSelection } from "../mission";
import {
  planningArguments,
  type ProjectPlanningTransport,
} from "./project-planning-transport";
import { canonicalJson, sha256Hex } from "../orchestration/operation-key";

// ── Closed data types ─────────────────────────────────────────────────────────

/** Exact already-qualified published project request (no `operation_key`). */
export interface PlanningSubmitInput {
  readonly stage: string;
  readonly work_ref: string;
  readonly project_source: Readonly<Record<string, unknown>>;
  readonly publication: Readonly<Record<string, unknown>>;
  readonly grounding: Readonly<Record<string, unknown>>;
  readonly private_request: string;
}

/**
 * Optional closed grounding DATA fixed on the port. It carries no grant: it
 * only restricts which already-qualified inputs this port will compose.
 */
export interface FixedPlanningGrounding {
  readonly mastermind_sha: string;
  readonly macro_sha: string;
}

// ── Fixed identity vocabulary ────────────────────────────────────────────────

const TARGET_PREFIX = "project-initial-planning.v1:";
const KEY_PREFIX = "mmos-project-planning-";
const KEY_HASH_CHARS = 40;
const INTENT_ID_PREFIX = "ceo-project-planning-";
const INTENT_ID_HASH_CHARS = 40;
const DIRECT_RECEIPT_SCHEMA = "mastermind.ceo_direct_native_receipt.v1";

const SUBMIT_INPUT_KEYS = [
  "stage",
  "project_source",
  "publication",
  "grounding",
  "private_request",
  "work_ref",
];
const RECEIPT_KEYS = [
  "schema",
  "intent_id",
  "fingerprint",
  "job_id",
  "status",
  "accepted",
  "duplicate",
  "dispatched",
  "authority",
  "grounding",
  "created_at_ms",
  "work_ref",
];
const AUTHORITY_KEYS = ["requested", "policy_sha256", "authority_level"];
const JOB_STATES = new Set([
  "QUEUED",
  "RUNNING",
  "CHECKPOINTED",
  "RATE_LIMITED",
  "FAILED",
  "LOST",
  "CANCEL_REQUESTED",
  "COMPLETED",
  "CANCELLED",
]);

const HEX64 = /^[0-9a-f]{64}$/;
const JOB_RE = /^JOB-[A-Za-z0-9][A-Za-z0-9._:-]{0,250}$/;
const WORK_REF_RE = /^WS:[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;
const KEY_RE = /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/;

// ── Small structural helpers ─────────────────────────────────────────────────

function isPlainObject(v: unknown): v is Record<string, unknown> {
  return (
    typeof v === "object" &&
    v !== null &&
    (Object.getPrototypeOf(v) === Object.prototype || Object.getPrototypeOf(v) === null)
  );
}

function hasExactKeys(value: Record<string, unknown>, keys: readonly string[]): boolean {
  return (
    Object.keys(value).length === keys.length &&
    keys.every((key) => Object.prototype.hasOwnProperty.call(value, key))
  );
}

/** Order-insensitive exact comparison of JSON-shaped values. */
function sameCanonical(a: unknown, b: unknown): boolean {
  return canonicalJson(a) === canonicalJson(b);
}

function samePointer(a: OperationPointer, b: OperationPointer): boolean {
  return (
    a.operationKey === b.operationKey &&
    a.kind === b.kind &&
    a.targetKey === b.targetKey
  );
}

// ── Derived identity ─────────────────────────────────────────────────────────

/** Opaque owner target reference; the controller never parses it. */
export function planningTargetKey(workRef: string): string {
  return `${TARGET_PREFIX}${workRef}`;
}

function workRefFromTargetKey(targetKey: string | null): string | null {
  if (typeof targetKey !== "string" || !targetKey.startsWith(TARGET_PREFIX)) return null;
  const workRef = targetKey.slice(TARGET_PREFIX.length);
  return WORK_REF_RE.test(workRef) ? workRef : null;
}

function keyMaterial(
  owner: OwnerContext,
  input: PlanningSubmitInput,
): Record<string, unknown> {
  return {
    v: 1,
    principalScope: owner.principalScope,
    work_ref: input.work_ref,
    stage: input.stage,
    project_source: input.project_source,
    publication: input.publication,
    grounding: input.grounding,
    private_request: input.private_request,
  };
}

/**
 * Deterministic operation key over the principal scope and the exact request
 * identity. ASCII and at most 128 characters (the transport `id()` shape and
 * the admission reference pattern).
 */
export function planningOperationKey(
  owner: OwnerContext,
  input: PlanningSubmitInput,
): string {
  return (
    KEY_PREFIX +
    sha256Hex(canonicalJson(keyMaterial(owner, input))).slice(0, KEY_HASH_CHARS)
  );
}

/**
 * Mirrors S19 `operation_intent_id`:
 * `ceo-project-planning-<40 hex of canonical {principal_scope, operation_key}>`.
 */
export function planningIntentId(operationKey: string, principalScope: string): string {
  return (
    INTENT_ID_PREFIX +
    sha256Hex(
      canonicalJson({ operation_key: operationKey, principal_scope: principalScope }),
    ).slice(0, INTENT_ID_HASH_CHARS)
  );
}

// ── Intent composition ───────────────────────────────────────────────────────

function submitInputFromValue(value: unknown): PlanningSubmitInput | null {
  if (!isPlainObject(value) || !hasExactKeys(value, SUBMIT_INPUT_KEYS)) return null;
  return {
    stage: value.stage,
    work_ref: value.work_ref,
    project_source: value.project_source,
    publication: value.publication,
    grounding: value.grounding,
    private_request: value.private_request,
  } as PlanningSubmitInput;
}

/**
 * Build and validate the exact submit arguments, including the derived
 * `operation_key`. Returns `null` for any out-of-contract input; the private
 * request text never escapes into a pointer, error or reason.
 */
function buildSubmitArguments(
  owner: OwnerContext,
  input: PlanningSubmitInput,
  fixedGrounding: FixedPlanningGrounding | undefined,
): Readonly<Record<string, unknown>> | null {
  if (fixedGrounding !== undefined && !sameCanonical(input.grounding, fixedGrounding)) {
    return null;
  }
  try {
    return planningArguments("submit", {
      operation_key: planningOperationKey(owner, input),
      work_ref: input.work_ref,
      stage: input.stage,
      project_source: input.project_source,
      publication: input.publication,
      private_request: input.private_request,
      grounding: input.grounding,
    });
  } catch {
    return null;
  }
}

/**
 * Compose the launch intent for an EXACT already-qualified published project.
 * Returns `null` instead of throwing for any input that fails the closed
 * transport contract, so a caller can never persist or send an invalid frame.
 */
export function makePlanningIntent(
  owner: OwnerContext | null,
  input: PlanningSubmitInput,
  fixedGrounding?: FixedPlanningGrounding,
): CommandIntent | null {
  if (!owner) return null;
  const source = submitInputFromValue(input);
  if (!source) return null;
  const args = buildSubmitArguments(owner, source, fixedGrounding);
  if (!args) return null;
  return {
    kind: "launch",
    targetKey: planningTargetKey(source.work_ref),
    payload: args,
  };
}

// ── Port ─────────────────────────────────────────────────────────────────────

export class ProjectPlanningCommandPort implements FiniteCommandPort {
  constructor(
    private readonly _transport: ProjectPlanningTransport,
    private readonly _owner: () => OwnerContext | null,
    private readonly _fixedGrounding?: FixedPlanningGrounding,
  ) {}

  context(): OwnerContext | null {
    return this._owner();
  }

  /** Same composition as the standalone helper, bound to the live owner. */
  makePlanningIntent(input: PlanningSubmitInput): CommandIntent | null {
    return makePlanningIntent(this._owner(), input, this._fixedGrounding);
  }

  /**
   * Synchronous and effect-free. Re-derives the whole request from the intent
   * payload, revalidates it against the closed transport contract, and refuses
   * any intent whose key, target or grounding is not exactly what this owner
   * would compose.
   */
  prepare(intent: CommandIntent): OperationPointer {
    if (intent.kind !== "launch") throw new Error("INVALID_KIND");
    const owner = this._owner();
    if (!owner || !isPlainObject(intent.payload)) throw new Error("INVALID_PAYLOAD");
    if (!hasExactKeys(intent.payload, [...SUBMIT_INPUT_KEYS, "operation_key"])) {
      throw new Error("INVALID_PAYLOAD");
    }
    const declaredKey = intent.payload.operation_key;
    if (typeof declaredKey !== "string") throw new Error("INVALID_PAYLOAD");
    const rest: Record<string, unknown> = { ...intent.payload };
    delete rest.operation_key;
    const input = submitInputFromValue(rest);
    if (!input) throw new Error("INVALID_PAYLOAD");
    const args = buildSubmitArguments(owner, input, this._fixedGrounding);
    if (!args || args.operation_key !== declaredKey) throw new Error("INVALID_PAYLOAD");
    if (!sameCanonical(args, intent.payload)) throw new Error("INVALID_PAYLOAD");
    const targetKey = planningTargetKey(input.work_ref);
    if (intent.targetKey !== targetKey) throw new Error("INVALID_TARGET");
    return { operationKey: declaredKey, kind: "launch", targetKey };
  }

  /**
   * One submit call with the exact validated arguments. The pointer, the
   * intent identity and the owner epoch are checked before and after the
   * await; a drifted epoch can never map the response.
   */
  async submit(
    pointer: OperationPointer,
    intent: CommandIntent,
    signal: AbortSignal,
  ): Promise<EffectReceipt> {
    const before = this._owner();
    if (!before) return this._receipt(pointer, "unknown", "OWNER_ABSENT");
    let expected: OperationPointer;
    try {
      expected = this.prepare(intent);
    } catch {
      return this._receipt(pointer, "unknown", "MALFORMED_POINTER");
    }
    if (!samePointer(expected, pointer)) {
      return this._receipt(pointer, "unknown", "RECEIPT_MISMATCH");
    }
    if (signal.aborted) return this._receipt(pointer, "unknown", "TRANSPORT_ERROR");
    let response: unknown;
    try {
      response = await this._transport.request("submit", intent.payload, signal);
    } catch {
      return this._receipt(pointer, "unknown", "TRANSPORT_ERROR");
    }
    if (signal.aborted) return this._receipt(pointer, "unknown", "TRANSPORT_ERROR");
    const after = this._owner();
    if (
      !after ||
      after.principalScope !== before.principalScope ||
      after.generation !== before.generation
    ) {
      return this._receipt(pointer, "unknown", "RECEIPT_MISMATCH");
    }
    return this._mapDirectReceipt(pointer, response, before);
  }

  /**
   * Observation only. The status lookup is rebuilt from the original pointer
   * alone (`operation_key` + `work_ref`); this never resubmits and never
   * guesses a root — the root job comes only from the receipt itself.
   */
  async readOperation(
    pointer: OperationPointer,
    signal: AbortSignal,
  ): Promise<EffectReceipt> {
    const owner = this._owner();
    const workRef = workRefFromTargetKey(pointer.targetKey);
    if (
      !owner ||
      !workRef ||
      pointer.kind !== "launch" ||
      typeof pointer.operationKey !== "string" ||
      !KEY_RE.test(pointer.operationKey)
    ) {
      return this._receipt(pointer, "unknown", "MALFORMED_POINTER");
    }
    if (signal.aborted) return this._receipt(pointer, "unknown", "TRANSPORT_ERROR");
    let args: Readonly<Record<string, unknown>>;
    try {
      args = planningArguments("status", {
        operation_key: pointer.operationKey,
        work_ref: workRef,
      });
    } catch {
      return this._receipt(pointer, "unknown", "MALFORMED_POINTER");
    }
    let response: unknown;
    try {
      response = await this._transport.request("status", args, signal);
    } catch {
      return this._receipt(pointer, "unknown", "TRANSPORT_ERROR");
    }
    if (signal.aborted) return this._receipt(pointer, "unknown", "TRANSPORT_ERROR");
    const current = this._owner();
    if (!current) return this._receipt(pointer, "unknown", "OWNER_ABSENT");
    return this._mapDirectReceipt(pointer, response, current);
  }

  // ── receipt mapping ────────────────────────────────────────────────────────

  /**
   * Map a raw S19 direct native receipt. Data is consumed exactly as the
   * factory produced it — no invented wrapper, no normalized copy. A closed
   * shape with `accepted !== true` is an unknown outcome, never a refusal.
   */
  private _mapDirectReceipt(
    pointer: OperationPointer,
    response: unknown,
    owner: OwnerContext,
  ): EffectReceipt {
    const workRef = workRefFromTargetKey(pointer.targetKey);
    if (!isPlainObject(response) || !hasExactKeys(response, RECEIPT_KEYS) || !workRef) {
      return this._receipt(pointer, "unknown", "MALFORMED_RECEIPT");
    }
    if (response.schema !== DIRECT_RECEIPT_SCHEMA) {
      return this._receipt(pointer, "unknown", "MALFORMED_RECEIPT");
    }
    if (
      typeof response.intent_id !== "string" ||
      typeof response.fingerprint !== "string" ||
      !HEX64.test(response.fingerprint) ||
      typeof response.duplicate !== "boolean" ||
      !Number.isSafeInteger(response.created_at_ms) ||
      (response.created_at_ms as number) < 0 ||
      typeof response.status !== "string" ||
      !JOB_STATES.has(response.status) ||
      !isPlainObject(response.grounding)
    ) {
      return this._receipt(pointer, "unknown", "MALFORMED_RECEIPT");
    }
    const authority = response.authority;
    if (
      !isPlainObject(authority) || !hasExactKeys(authority, AUTHORITY_KEYS) ||
      authority.authority_level !== "A0" ||
      typeof authority.policy_sha256 !== "string" ||
      !HEX64.test(authority.policy_sha256) ||
      !Array.isArray(authority.requested) ||
      (authority.requested as unknown[]).length !== 2 ||
      authority.requested[0] !== "READ" ||
      authority.requested[1] !== "RESEARCH"
    ) {
      return this._receipt(pointer, "unknown", "MALFORMED_RECEIPT");
    }
    if (response.accepted !== true || response.dispatched !== false) {
      // No refusal can be inferred here: the outcome is not known to this
      // client, so the pointer stays for a later recover.
      return this._receipt(pointer, "unknown", "UNKNOWN_RECEIPT");
    }
    if (
      response.intent_id !== planningIntentId(pointer.operationKey, owner.principalScope) ||
      response.work_ref !== workRef
    ) {
      return this._receipt(pointer, "unknown", "RECEIPT_MISMATCH");
    }
    if (typeof response.job_id !== "string" || !JOB_RE.test(response.job_id)) {
      return this._receipt(pointer, "unknown", "UNKNOWN_RECEIPT");
    }
    const missionSelection: MissionSelection = { workRef, rootJobId: response.job_id };
    return this._receipt(pointer, "accepted", "ACCEPTED", missionSelection);
  }

  private _receipt(
    pointer: OperationPointer,
    disposition: EffectReceipt["disposition"],
    reason: string,
    missionSelection?: MissionSelection,
  ): EffectReceipt {
    return {
      operationKey: pointer.operationKey,
      kind: "launch",
      targetKey: pointer.targetKey,
      disposition,
      reason,
      ...(missionSelection ? { missionSelection } : {}),
    };
  }
}
