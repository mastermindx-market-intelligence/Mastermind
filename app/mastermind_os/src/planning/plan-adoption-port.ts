/** Fixed ADOPT adapter. Transport is supplied by the authenticated source owner.
 * No URL, grant, operation ID, durable store or publication is invented here.
 */
import type {
  CommandIntent,
  EffectReceipt,
  FiniteCommandPort,
  OperationPointer,
  OwnerContext,
} from "../orchestration/operation-controller";
import { canonicalJson, sha256Hex } from "../orchestration/operation-key";
import {
  decodePlanAdoptionRequest,
  type PlanAdoptionRequest,
} from "./plan-adoption-request";
import { decodeSourceOperationStatus } from "./plan-adoption-status";

type Lookup = Readonly<{
  schema: "mastermind.workspace_source_operation_lookup.v1";
  action: "ADOPT_PLAN";
  request_id: string;
  work_ref: string;
}>;
type OriginalInput = Readonly<{
  schema: "mastermind.terminal_original_input_reference.v1";
  input_ref: string;
  artifact_sha256: string;
  payload_sha256: string;
}>;
type Witness = Readonly<{
  original_input: OriginalInput;
  recipe_fingerprint_sha256: string;
}>;
export interface PlanAdoptionTransport {
  prepareSourceOperation(
    input: { action: "ADOPT_PLAN"; request: PlanAdoptionRequest },
    signal: AbortSignal,
  ): Promise<unknown>;
  readSourceOperation(input: Lookup, signal: AbortSignal): Promise<unknown>;
  reconcileSourceOperation?(
    input: Lookup,
    signal: AbortSignal,
  ): Promise<unknown>;
  submitSourceOperation(
    input: {
      action: "ADOPT_PLAN";
      request_id: string;
      work_ref: string;
      preview_witness: Witness;
    },
    signal: AbortSignal,
  ): Promise<unknown>;
  advanceSourceOperation?(
    input: {
      schema: "mastermind.workspace_source_operation_advance.v1";
      action: "ADOPT_PLAN";
      request_id: string;
      work_ref: string;
      phase_receipt_digest: string;
    },
    signal: AbortSignal,
  ): Promise<unknown>;
}
export interface PlanAdoptionOwner {
  /** Actual Workspace scope + monotonic authentication epoch; never a Macro revision. */
  context(): OwnerContext | null;
  canAdopt(): boolean;
  /** Original-scope status capability under the current distinct ADOPT grant.
   * Never generic Workspace READ; independent of Macro source-write readiness.
   */
  canInspect(): boolean;
}

/** Actual fec4 signed context body. Shape validation is not authentication;
 * the fixed authenticated host method supplies it under the current epoch.
 */
export function bindPlanAdoptionOwner(input: {
  raw: unknown;
  workRef: string;
  generation: string;
  isCurrent: () => boolean;
  sourceReady: () => boolean;
}): PlanAdoptionOwner {
  try {
    const body = record(input.raw, [
      "schema",
      "selection",
      "owner_context",
      "can_inspect",
    ]);
    const selection = record(body.selection, ["action", "work_ref"]);
    const owner = record(body.owner_context, ["principal_scope"]);
    if (
      body.schema !== "mastermind.workspace_source_operation_context.v1" ||
      body.can_inspect !== true ||
      selection.action !== "ADOPT_PLAN" ||
      selection.work_ref !== input.workRef ||
      !WS.test(input.workRef) ||
      input.workRef.slice(3).length < 2 ||
      input.workRef.slice(3).length > 64 ||
      typeof input.generation !== "string" ||
      !input.generation
    )
      fail();
    const scope = hex(owner.principal_scope),
      generation = input.generation;
    const current = () => {
      try {
        return input.isCurrent() === true;
      } catch {
        return false;
      }
    };
    return Object.freeze({
      context: () => (current() ? { principalScope: scope, generation } : null),
      canInspect: current,
      canAdopt: () => current() && input.sourceReady() === true,
    });
  } catch {
    return fail();
  }
}
export interface PreparedPlanAdoption {
  readonly request: PlanAdoptionRequest;
  readonly ownerContext: OwnerContext;
  readonly requestSha256: string;
  readonly recipeFingerprintSha256: string;
  readonly previewWitness: Witness;
  readonly preview: PlanAdoptionPreview;
}
export interface PlanAdoptionPreview {
  readonly schema: "mastermind.project_plan_adoption_preview.v1";
  readonly work_ref: string;
  readonly expected_commit: string;
  readonly expected_adoption: string | null;
  readonly candidate_sha256: string;
  readonly changed_frontmatter_fields: readonly string[];
  readonly record_body_changed: boolean;
}
const issued = new WeakSet<object>();
const HEX = /^[0-9a-f]{64}$/;
const KEY = /^mmos-project-adopt-[0-9a-f]{40}$/;
const WS = /^WS:[A-Z0-9]+(?:-[A-Z0-9]+)*$/;
function fail(): never {
  throw new Error("PLAN_ADOPTION_PORT_UNAVAILABLE");
}
function record(
  value: unknown,
  keys: readonly string[],
): Record<string, unknown> {
  if (value === null || typeof value !== "object" || Array.isArray(value))
    fail();
  const proto = Object.getPrototypeOf(value);
  if (proto !== Object.prototype && proto !== null) fail();
  const names = Reflect.ownKeys(value);
  if (
    names.length !== keys.length ||
    names.some((k) => typeof k !== "string" || !keys.includes(k))
  )
    fail();
  for (const key of keys) {
    const descriptor = Object.getOwnPropertyDescriptor(value, key);
    if (!descriptor || !("value" in descriptor)) fail();
  }
  return value as Record<string, unknown>;
}
function hex(value: unknown): string {
  if (typeof value !== "string" || !HEX.test(value)) fail();
  return value;
}
function context(
  owner: PlanAdoptionOwner,
  action: "read" | "write",
  signal?: AbortSignal,
): OwnerContext {
  if (
    signal?.aborted ||
    !owner.canInspect() ||
    (action === "write" && !owner.canAdopt())
  )
    fail();
  const value = owner.context();
  if (
    !value ||
    !HEX.test(value.principalScope) ||
    typeof value.generation !== "string" ||
    !value.generation
  )
    fail();
  return { principalScope: value.principalScope, generation: value.generation };
}
function fence(
  owner: PlanAdoptionOwner,
  captured: OwnerContext,
  action: "read" | "write",
  signal?: AbortSignal,
): void {
  const now = context(owner, action, signal);
  if (
    now.principalScope !== captured.principalScope ||
    now.generation !== captured.generation
  )
    fail();
}
function freeze<T>(value: T): T {
  if (value && typeof value === "object") {
    Object.values(value).forEach(freeze);
    Object.freeze(value);
  }
  return value;
}
function witness(value: unknown, fingerprint: string): Witness {
  const outer = record(value, ["original_input", "recipe_fingerprint_sha256"]);
  const input = record(outer.original_input, [
    "schema",
    "input_ref",
    "artifact_sha256",
    "payload_sha256",
  ]);
  if (
    outer.recipe_fingerprint_sha256 !== fingerprint ||
    input.schema !== "mastermind.terminal_original_input_reference.v1" ||
    typeof input.input_ref !== "string" ||
    !/^terminal-input:[0-9a-f]{64}$/.test(input.input_ref)
  )
    fail();
  return {
    original_input: {
      schema: "mastermind.terminal_original_input_reference.v1",
      input_ref: input.input_ref,
      artifact_sha256: hex(input.artifact_sha256),
      payload_sha256: hex(input.payload_sha256),
    },
    recipe_fingerprint_sha256: fingerprint,
  };
}
const FIELDS = new Set(
  "schema,key,title,objective,status,program,repos,owner,class,blast_radius,ambiguity,waves,next_action,standing_instructions,project_files,archive,p0,owns_paths,depends_on,blocked_by,decisions,accepted_direction,discoveries,landmines,do_not_redo,artifacts,acceptance_contracts,runtime_ref,claim,needs_ceo,wait".split(
    ",",
  ),
);
function preview(
  value: unknown,
  request: PlanAdoptionRequest,
): PlanAdoptionPreview {
  const p = record(value, [
    "schema",
    "work_ref",
    "expected_commit",
    "expected_adoption",
    "candidate_sha256",
    "changed_frontmatter_fields",
    "record_body_changed",
  ]);
  if (
    p.schema !== "mastermind.project_plan_adoption_preview.v1" ||
    p.work_ref !== request.work_ref ||
    p.expected_commit !== request.expected_commit ||
    p.expected_adoption !== request.expected_adoption ||
    p.candidate_sha256 !== request.candidate_sha256 ||
    typeof p.record_body_changed !== "boolean" ||
    !Array.isArray(p.changed_frontmatter_fields) ||
    p.changed_frontmatter_fields.length > FIELDS.size
  )
    fail();
  const fields = p.changed_frontmatter_fields;
  if (
    Object.getPrototypeOf(fields) !== Array.prototype ||
    Reflect.ownKeys(fields).length !== fields.length + 1
  )
    fail();
  for (let i = 0; i < fields.length; i++) {
    const d = Object.getOwnPropertyDescriptor(fields, String(i));
    if (!d || !("value" in d)) fail();
  }
  if (
    fields.some(
      (field, i) =>
        typeof field !== "string" ||
        !FIELDS.has(field) ||
        (i > 0 && fields[i - 1] >= field),
    )
  )
    fail();
  return {
    schema: "mastermind.project_plan_adoption_preview.v1",
    work_ref: request.work_ref,
    expected_commit: request.expected_commit,
    expected_adoption: request.expected_adoption,
    candidate_sha256: request.candidate_sha256,
    changed_frontmatter_fields: [...fields],
    record_body_changed: p.record_body_changed,
  };
}

/** Qualifies the actual closed owner preview, never an opaque ReactNode/body. */
export async function preparePlanAdoption(
  input: {
    workRef: string;
    request: unknown;
    transport: PlanAdoptionTransport;
    owner: PlanAdoptionOwner;
    isCurrent: () => boolean;
  },
  signal: AbortSignal,
): Promise<PreparedPlanAdoption> {
  try {
    const request = freeze(
      decodePlanAdoptionRequest(input.request, input.workRef),
    );
    // Preview qualification precedes source-write readiness. The actual server
    // prepares the exact private recipe under the distinct ADOPT grant; no Git
    // publication occurs. Submit/advance still require canAdopt separately.
    const captured = context(input.owner, "read", signal);
    if (!input.isCurrent()) fail();
    const response = record(
      await input.transport.prepareSourceOperation(
        { action: "ADOPT_PLAN", request },
        signal,
      ),
      [
        "schema",
        "selection",
        "owner_context",
        "request_sha256",
        "recipe_fingerprint_sha256",
        "preview_witness",
        "preview",
      ],
    );
    fence(input.owner, captured, "read", signal);
    if (!input.isCurrent()) fail();
    const selection = record(response.selection, [
      "action",
      "request_id",
      "work_ref",
    ]);
    const owner = record(response.owner_context, ["principal_scope"]);
    const requestSha256 = sha256Hex(canonicalJson(request));
    if (
      response.schema !== "mastermind.workspace_source_operation_preview.v1" ||
      selection.action !== "ADOPT_PLAN" ||
      selection.request_id !== request.request_id ||
      selection.work_ref !== request.work_ref ||
      owner.principal_scope !== captured.principalScope ||
      response.request_sha256 !== requestSha256
    )
      fail();
    const fingerprint = hex(response.recipe_fingerprint_sha256);
    if (fingerprint === requestSha256) fail();
    const prepared = freeze({
      request,
      ownerContext: captured,
      requestSha256,
      recipeFingerprintSha256: fingerprint,
      previewWitness: witness(response.preview_witness, fingerprint),
      preview: preview(response.preview, request),
    });
    issued.add(prepared);
    return prepared;
  } catch {
    return fail();
  }
}

export function createPlanAdoptionPort(input: {
  workRef: string;
  transport: PlanAdoptionTransport;
  owner: PlanAdoptionOwner;
  prepared: () => PreparedPlanAdoption | null;
  isPreparedCurrent: (prepared: PreparedPlanAdoption) => boolean;
}): FiniteCommandPort & {
  reconcileOperation?: (
    pointer: OperationPointer,
    signal: AbortSignal,
  ) => Promise<EffectReceipt>;
} {
  if (
    !WS.test(input.workRef) ||
    input.workRef.slice(3).length < 2 ||
    input.workRef.slice(3).length > 64
  )
    fail();
  function lookup(pointer: OperationPointer): Lookup {
    if (
      pointer.kind !== "project_adopt" ||
      pointer.targetKey !== input.workRef ||
      !KEY.test(pointer.operationKey)
    )
      fail();
    return {
      schema: "mastermind.workspace_source_operation_lookup.v1",
      action: "ADOPT_PLAN",
      request_id: pointer.operationKey,
      work_ref: input.workRef,
    };
  }
  function preparedFor(intent: CommandIntent): PreparedPlanAdoption {
    const candidate = input.prepared();
    if (
      !candidate ||
      !issued.has(candidate) ||
      !input.isPreparedCurrent(candidate) ||
      intent.kind !== "project_adopt" ||
      intent.targetKey !== input.workRef
    )
      fail();
    const payload = record(intent.payload, ["action", "request"]);
    if (
      payload.action !== "ADOPT_PLAN" ||
      canonicalJson(
        decodePlanAdoptionRequest(payload.request, input.workRef),
      ) !== canonicalJson(candidate.request) ||
      candidate.request.work_ref !== input.workRef
    )
      fail();
    fence(input.owner, candidate.ownerContext, "write");
    return candidate;
  }
  async function operation(
    pointer: OperationPointer,
    signal: AbortSignal,
    action: "read" | "write",
    call: (lookup: Lookup) => Promise<unknown>,
    anchor?: PreparedPlanAdoption,
  ): Promise<EffectReceipt> {
    try {
      const target = lookup(pointer),
        captured = context(input.owner, action, signal);
      const status = decodeSourceOperationStatus(await call(target));
      fence(input.owner, captured, action, signal);
      if (
        status.selection.action !== "ADOPT_PLAN" ||
        status.selection.request_id !== target.request_id ||
        status.selection.work_ref !== target.work_ref ||
        status.owner_context.principal_scope !== captured.principalScope
      )
        fail();
      if (
        anchor &&
        status.receipt !== null &&
        (status.request_sha256 !== anchor.requestSha256 ||
          status.recipe_fingerprint_sha256 !== anchor.recipeFingerprintSha256)
      )
        fail();
      return {
        operationKey: pointer.operationKey,
        kind: "project_adopt",
        targetKey: input.workRef,
        disposition: status.disposition,
        ...(status.reason !== null ? { reason: status.reason } : {}),
        ...(status.advance !== null
          ? {
              advance: {
                phase_receipt_digest: status.advance.phase_receipt_digest,
              },
            }
          : {}),
      };
    } catch {
      return fail();
    }
  }
  return {
    context: () => {
      try {
        return context(input.owner, "read");
      } catch {
        return null;
      }
    },
    prepare(intent) {
      try {
        const p = preparedFor(intent);
        return {
          operationKey: p.request.request_id,
          kind: "project_adopt",
          targetKey: input.workRef,
        };
      } catch {
        return fail();
      }
    },
    async submit(pointer, intent, signal) {
      try {
        const p = preparedFor(intent);
        if (lookup(pointer).request_id !== p.request.request_id) fail();
        return await operation(
          pointer,
          signal,
          "write",
          () =>
            input.transport.submitSourceOperation(
              {
                action: "ADOPT_PLAN",
                request_id: p.request.request_id,
                work_ref: input.workRef,
                preview_witness: p.previewWitness,
              },
              signal,
            ),
          p,
        );
      } catch {
        return fail();
      }
    },
    readOperation: (pointer, signal) =>
      operation(pointer, signal, "read", (target) =>
        input.transport.readSourceOperation(target, signal),
      ),
    ...(input.transport.reconcileSourceOperation
      ? {
          reconcileOperation: (
            pointer: OperationPointer,
            signal: AbortSignal,
          ) =>
            operation(pointer, signal, "read", (target) =>
              input.transport.reconcileSourceOperation!(target, signal),
            ),
        }
      : {}),
    ...(input.transport.advanceSourceOperation
      ? {
          advanceOperation: async (
            pointer: OperationPointer,
            digest: string,
            signal: AbortSignal,
          ) => {
            try {
              hex(digest);
              return await operation(pointer, signal, "write", (target) =>
                input.transport.advanceSourceOperation!(
                  {
                    schema: "mastermind.workspace_source_operation_advance.v1",
                    action: "ADOPT_PLAN",
                    request_id: target.request_id,
                    work_ref: target.work_ref,
                    phase_receipt_digest: digest,
                  },
                  signal,
                ),
              );
            } catch {
              return fail();
            }
          },
        }
      : {}),
  };
}
