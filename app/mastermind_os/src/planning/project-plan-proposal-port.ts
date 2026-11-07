/** Fixed S19 preparation + incumbent Workspace publication. No new lifecycle. */
import type {
  CommandIntent,
  EffectReceipt,
  FiniteCommandPort,
  OperationPointer,
  OwnerContext,
} from "../orchestration/operation-controller";
import type {
  SourceOperationTransport,
  BasicSourceLookup,
} from "../source-operations/transport";
import type { ProjectPlanningTransport } from "./project-planning-transport";
import { planningArguments } from "./project-planning-transport";
import {
  decodeSourceOperationStatus,
  type SourceOperationStatus,
} from "./plan-adoption-status";
import { canonicalJson } from "../orchestration/operation-key";
import {
  PLAN_PROPOSAL_ACTION as ACTION,
  PLAN_PROPOSAL_KIND as KIND,
  decodePlanProposalOriginal,
  decodePlanProposalPreview,
  freezeProposal,
  parsePlanProposalTarget,
  planProposalPath,
  planProposalRequestSha,
  planProposalTarget,
  proposalHex,
  proposalRecord,
  proposalUnavailable as fail,
  type PlanProposalOriginal,
  type PlanProposalPreview,
  type PlanProposalPointerTarget,
} from "./project-plan-proposal";

export interface PlanProposalOwner {
  context(): OwnerContext | null;
  canInspect(): boolean;
  canPublish(): boolean;
}
interface Witness {
  original_input: {
    schema: "mastermind.terminal_original_input_reference.v1";
    input_ref: string;
    artifact_sha256: string;
    payload_sha256: string;
  };
  recipe_fingerprint_sha256: string;
}
export interface PreparedPlanProposal {
  readonly original: PlanProposalOriginal;
  readonly owner: OwnerContext;
  readonly executive: OwnerContext;
  readonly requestSha256: string;
  readonly fingerprint: string;
  readonly witness: Witness;
  readonly preview: PlanProposalPreview;
}
const issued = new WeakSet<object>();
function same(a: OwnerContext, b: OwnerContext): boolean {
  return a.principalScope === b.principalScope && a.generation === b.generation;
}
function ownerContext(
  owner: PlanProposalOwner,
  write: boolean,
  signal?: AbortSignal,
): OwnerContext {
  const context = owner.context();
  if (
    signal?.aborted ||
    !owner.canInspect() ||
    (write && !owner.canPublish()) ||
    !context ||
    !/^[0-9a-f]{64}$/.test(context.principalScope) ||
    !context.generation
  )
    return fail();
  return { ...context };
}
function fence(
  owner: PlanProposalOwner,
  captured: OwnerContext,
  write: boolean,
  signal?: AbortSignal,
) {
  if (!same(ownerContext(owner, write, signal), captured)) return fail();
}
function previewWitness(value: unknown, fingerprint: string): Witness {
  const w = proposalRecord(value, [
    "original_input",
    "recipe_fingerprint_sha256",
  ]);
  const p = proposalRecord(w.original_input, [
    "schema",
    "input_ref",
    "artifact_sha256",
    "payload_sha256",
  ]);
  if (
    w.recipe_fingerprint_sha256 !== fingerprint ||
    p.schema !== "mastermind.terminal_original_input_reference.v1" ||
    typeof p.input_ref !== "string" ||
    !/^terminal-input:[0-9a-f]{64}$/.test(p.input_ref)
  )
    return fail();
  return {
    original_input: {
      schema: "mastermind.terminal_original_input_reference.v1",
      input_ref: p.input_ref,
      artifact_sha256: proposalHex(p.artifact_sha256),
      payload_sha256: proposalHex(p.payload_sha256),
    },
    recipe_fingerprint_sha256: fingerprint,
  };
}
/** The exact original planning READ/consumption grant and distinct source-WRITE
 * grant are requalified by the fixed server owner. Opaque scopes stay distinct. */
export async function preparePlanProposal(
  input: {
    original: PlanProposalOriginal;
    planning: ProjectPlanningTransport;
    owner: PlanProposalOwner;
    executiveOwner: () => OwnerContext | null;
    isCurrent: () => boolean;
  },
  signal: AbortSignal,
): Promise<PreparedPlanProposal> {
  try {
    const original = decodePlanProposalOriginal(input.original);
    const owner = ownerContext(input.owner, true, signal),
      executive = input.executiveOwner();
    if (!executive || !input.isCurrent()) return fail();
    const capturedExecutive = { ...executive };
    const envelope = proposalRecord(
      await input.planning.request(
        "prepare_proposal",
        planningArguments("prepare_proposal", original),
        signal,
      ),
      ["schema", "operation", "ok", "data", "error"],
    );
    fence(input.owner, owner, true, signal);
    const nowExecutive = input.executiveOwner();
    if (
      !nowExecutive ||
      !same(capturedExecutive, nowExecutive) ||
      !input.isCurrent() ||
      envelope.schema !==
        "mastermind.project_initial_planning.private_result.v1" ||
      envelope.operation !== "prepare_proposal" ||
      envelope.ok !== true ||
      envelope.error !== null
    )
      return fail();
    const value = proposalRecord(envelope.data, [
      "schema",
      "selection",
      "owner_context",
      "request_sha256",
      "recipe_fingerprint_sha256",
      "preview_witness",
      "preview",
    ]);
    const selected = proposalRecord(value.selection, [
      "action",
      "request_id",
      "work_ref",
    ]);
    const scoped = proposalRecord(value.owner_context, ["principal_scope"]);
    const request = original.proposal_request,
      requestSha256 = planProposalRequestSha(original);
    if (
      value.schema !== "mastermind.workspace_source_operation_preview.v1" ||
      selected.action !== ACTION ||
      selected.request_id !== request.request_id ||
      selected.work_ref !== request.work_ref ||
      scoped.principal_scope !== owner.principalScope ||
      value.request_sha256 !== requestSha256
    )
      return fail();
    const fingerprint = proposalHex(value.recipe_fingerprint_sha256);
    if (fingerprint === requestSha256) return fail();
    const prepared = freezeProposal({
      original,
      owner,
      executive: capturedExecutive,
      requestSha256,
      fingerprint,
      witness: previewWitness(value.preview_witness, fingerprint),
      preview: decodePlanProposalPreview(value.preview, request),
    });
    issued.add(prepared);
    return prepared;
  } catch {
    return fail();
  }
}
export function proposalPointer(
  prepared: PreparedPlanProposal,
): OperationPointer {
  if (!issued.has(prepared)) return fail();
  return {
    kind: KIND,
    operationKey: prepared.original.proposal_request.request_id,
    targetKey: planProposalTarget({
      schema: "mastermind.project_plan_publication_lookup.v1",
      action: ACTION,
      request_id: prepared.original.proposal_request.request_id,
      work_ref: prepared.original.work_ref,
      principal_scope: prepared.owner.principalScope,
      request_sha256: prepared.requestSha256,
      recipe_fingerprint_sha256: prepared.fingerprint,
    }),
  };
}
/** Qualifies a status under the actual current Workspace owner. This works
 * after PLAN makes the old S19 source stale; it never re-authorizes execution. */
export function qualifyPlanProposalStatus(
  raw: unknown,
  original: PlanProposalOriginal,
  scope: string,
  fingerprint?: string,
): SourceOperationStatus {
  const status = decodeSourceOperationStatus(raw),
    request = original.proposal_request;
  if (
    status.selection.action !== ACTION ||
    status.selection.request_id !== request.request_id ||
    status.selection.work_ref !== request.work_ref ||
    status.owner_context.principal_scope !== scope ||
    (status.phase !== null && status.phase !== "PUBLICATION")
  )
    return fail();
  if (
    status.receipt !== null &&
    (status.request_sha256 !== planProposalRequestSha(original) ||
      (fingerprint !== undefined &&
        status.recipe_fingerprint_sha256 !== fingerprint))
  )
    return fail();
  if (status.disposition === "accepted") {
    if (status.receipt?.kind !== "SOURCE_OBSERVED") return fail();
    const paths = [
      planProposalPath(request),
      `agentos/workstreams/WS-${request.work_ref.slice(3)}.md`,
    ];
    const sources = status.receipt.sources;
    if (
      sources.length !== 2 ||
      !paths.every(
        (path) =>
          sources.filter((s) => s.repository === "macro" && s.path === path)
            .length === 1,
      ) ||
      sources[0].commit !== sources[1].commit
    )
      return fail();
  }
  return status;
}
export function createPlanProposalPort(input: {
  workRef: string;
  source: SourceOperationTransport;
  owner: PlanProposalOwner;
  original: () => PlanProposalOriginal | null;
  prepared: () => PreparedPlanProposal | null;
  isPreparedCurrent: (prepared: PreparedPlanProposal) => boolean;
  onStatus?: (status: SourceOperationStatus) => void;
}): FiniteCommandPort {
  function selected(pointer: OperationPointer): {
    target: PlanProposalPointerTarget;
    lookup: BasicSourceLookup;
    original: PlanProposalOriginal;
  } {
    const t = parsePlanProposalTarget(pointer.targetKey),
      original = input.original();
    if (
      !t ||
      !original ||
      pointer.kind !== KIND ||
      pointer.operationKey !== t.request_id ||
      t.work_ref !== input.workRef ||
      original.work_ref !== input.workRef ||
      original.proposal_request.request_id !== t.request_id ||
      planProposalRequestSha(original) !== t.request_sha256 ||
      input.owner.context()?.principalScope !== t.principal_scope
    )
      return fail();
    return {
      target: t,
      original,
      lookup: {
        schema: "mastermind.workspace_source_operation_lookup.v1",
        action: ACTION,
        request_id: t.request_id,
        work_ref: t.work_ref,
      },
    };
  }
  function preparedFor(intent: CommandIntent): PreparedPlanProposal {
    const p = input.prepared();
    if (
      !p ||
      !issued.has(p) ||
      !input.isPreparedCurrent(p) ||
      intent.kind !== KIND
    )
      return fail();
    const payload = proposalRecord(intent.payload, ["action", "original"]);
    if (
      payload.action !== ACTION ||
      canonicalJson(decodePlanProposalOriginal(payload.original)) !==
        canonicalJson(p.original) ||
      intent.targetKey !== proposalPointer(p).targetKey
    )
      return fail();
    fence(input.owner, p.owner, true);
    return p;
  }
  async function observe(
    pointer: OperationPointer,
    signal: AbortSignal,
    write: boolean,
    call: (lookup: BasicSourceLookup) => Promise<unknown>,
  ): Promise<EffectReceipt> {
    const { target, lookup, original } = selected(pointer),
      owner = ownerContext(input.owner, write, signal);
    const status = qualifyPlanProposalStatus(
      await call(lookup),
      original,
      owner.principalScope,
      target.recipe_fingerprint_sha256,
    );
    fence(input.owner, owner, write, signal);
    selected(pointer);
    input.onStatus?.(status);
    return {
      operationKey: pointer.operationKey,
      kind: KIND,
      targetKey: pointer.targetKey,
      disposition: status.disposition,
    };
  }
  return {
    context: () => {
      try {
        return ownerContext(input.owner, false);
      } catch {
        return null;
      }
    },
    prepare(intent) {
      const p = preparedFor(intent);
      return proposalPointer(p);
    },
    async submit(pointer, intent, signal) {
      const p = preparedFor(intent);
      selected(pointer);
      if (canonicalJson(pointer) !== canonicalJson(proposalPointer(p)))
        return fail();
      return observe(pointer, signal, true, () =>
        input.source.submitSourceOperation(
          {
            action: ACTION,
            request_id: p.original.proposal_request.request_id,
            work_ref: p.original.work_ref,
            preview_witness: p.witness,
          },
          signal,
        ),
      );
    },
    readOperation: (pointer, signal) =>
      observe(pointer, signal, false, (lookup) =>
        input.source.readSourceOperation(lookup, signal),
      ),
    reconcileOperation: (pointer, signal) =>
      observe(pointer, signal, false, (lookup) =>
        input.source.reconcileSourceOperation(lookup, signal),
      ),
  };
}
