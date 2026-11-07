import {
  normalizeSelection,
  type MissionDocument,
  type MissionSelection,
  type EvidenceRef,
} from "../mission";
import type { OriginalOperationObservation } from "../orchestration/operation-controller";

export const PHASES = [
  "request",
  "pickup",
  "start",
  "effect",
  "return",
  "acceptance",
] as const;
export type Phase = (typeof PHASES)[number];
export type ReceiptRoute = "work" | "sessions" | "original_status";
export interface Fact {
  readonly phase: Phase;
  readonly state: "reported" | "unavailable" | "held";
  readonly value: string | null;
  readonly evidence: readonly {
    owner: string;
    field: string;
    revision: string | null;
    time: string | null;
  }[];
}
export interface ActivationFactsModel {
  readonly operationKey: string;
  readonly kind: string;
  readonly targetKey: string | null;
  readonly selection: Readonly<MissionSelection> | null;
  readonly runtime: Readonly<{
    jobId: string;
    workerId: string;
    attemptId: string;
    bindingId: string | null;
    bindingGeneration: string | number | boolean | null;
  }> | null;
  readonly facts: readonly Fact[];
  readonly routes: readonly ReceiptRoute[];
}
const currentEvidence = (items: readonly EvidenceRef[]) =>
  items.filter((x) => x.freshness_state === "CURRENT");
const evidence = (items: readonly EvidenceRef[]) =>
  items.map((x) => ({
    owner: x.owner,
    field: x.field,
    revision: x.source_revision,
    time: x.source_time ?? x.observed_at,
  }));

/** Already-decoded owner inputs only. No read, store, clock, command or grant.
 * Never join an arbitrary selected Mission: only the verified original launch
 * receipt's exact selection may establish its root association. */
export function activationFacts(
  original: OriginalOperationObservation | null,
  document: MissionDocument | null,
): ActivationFactsModel | null {
  if (!original) return null;
  const rows: Fact[] = PHASES.map((phase) => ({
    phase,
    state: "unavailable",
    value: null,
    evidence: [],
  }));
  rows[0] = {
    phase: "request",
    state: original.status === "unknown" ? "held" : "reported",
    value: original.status,
    evidence: [
      {
        owner: "ORIGINAL_COMMAND_OWNER",
        field: "validated_original_receipt",
        revision: null,
        time: null,
      },
    ],
  };
  const selection =
    original.pointer.kind === "launch" && original.status === "accepted"
      ? normalizeSelection(original.missionSelection)
      : null;
  const d = document;
  let runtime: ActivationFactsModel["runtime"] = null;
  const observation = d?.source.owner_observation;
  const matched =
    !!selection &&
    !!d &&
    d.program.work_ref === selection.workRef &&
    d.mission.root_job_id === selection.rootJobId &&
    !d.mission.root_job_ambiguous &&
    d.mission.runtime_root_state === "RESOLVED" &&
    d.mission.root_job_candidates.length === 1 &&
    d.mission.root_job_candidates[0] === selection.rootJobId &&
    d.read_state.state === "CURRENT" &&
    observation?.state === "SAME" &&
    observation.selection?.work_ref === selection.workRef &&
    observation.selection.root_job_id === selection.rootJobId &&
    observation.runtime?.state === "SAME";
  if (matched && d) {
    const transport = currentEvidence(d.transport.evidence);
    if (
      !d.transport.historical &&
      d.transport.dispatch_state === "PICKUP_ACKNOWLEDGED" &&
      transport.length
    )
      rows[1] = {
        phase: "pickup",
        state: "reported",
        value: "PICKUP_ACKNOWLEDGED",
        evidence: evidence(transport),
      };
    const worker = d.principal.current_worker;
    const child =
      worker &&
      d.children.items.find(
        (x) =>
          x.parent_job_id === selection!.rootJobId &&
          x.worker_id === worker.worker_id &&
          !!worker.attempt_id &&
          x.current_attempt_id === worker.attempt_id &&
          x.latest_attempt?.attempt_id === worker.attempt_id &&
          x.latest_attempt.status === worker.status,
      );
    if (child && worker?.worker_id && worker.attempt_id)
      runtime = Object.freeze({
        jobId: child.job_id,
        workerId: worker.worker_id,
        attemptId: worker.attempt_id,
        bindingId: worker.runtime_binding_id,
        bindingGeneration: worker.binding_generation,
      });
    const runtimeEvidence = [
      {
        owner: "EXECUTIVE_OS",
        field: child
          ? `attempt:${child.latest_attempt!.attempt_id}`
          : "runtime",
        revision: observation!.runtime!.snapshot_digest,
        time: child?.latest_attempt?.started_at ?? null,
      },
    ];
    if (child?.latest_attempt?.started_at)
      rows[2] = {
        phase: "start",
        state: "reported",
        value: child.latest_attempt.status,
        evidence: runtimeEvidence,
      };
    if (child && worker?.effect_state === "applied")
      rows[3] = {
        phase: "effect",
        state: "reported",
        value: "applied",
        evidence: runtimeEvidence,
      };
    if (
      d.transport.dispatch_state === "EFFECT_UNKNOWN" ||
      worker?.effect_state === "effect_unknown" ||
      d.principal.current_sol_target?.effect_state === "effect_unknown" ||
      d.transport.w3c?.state === "EFFECT_UNKNOWN"
    ) {
      rows[3] = {
        phase: "effect",
        state: "held",
        value: "EFFECT_UNKNOWN",
        evidence: evidence(transport),
      };
    }
    const returned = d.transport.w3c?.source_receipt;
    if (
      !d.transport.historical &&
      d.transport.dispatch_state === "RETURNED" &&
      (transport.length ||
        (returned?.terminal_source_owner === "executive_terminal_return" &&
          returned.snapshot_digest))
    )
      rows[4] = {
        phase: "return",
        state: "reported",
        value: "RETURNED",
        evidence: transport.length
          ? evidence(transport)
          : [
              {
                owner: "executive_terminal_return",
                field: "transport.dispatch_state",
                revision: returned!.snapshot_digest,
                time: returned!.observed_at,
              },
            ],
      };
    // The current v2/v3 Mission decoder explicitly excludes product acceptance.
    // A separately selected v4 acceptance read needs its own exact request
    // association; an arbitrary selected ruling cannot supply this phase.

  }
  // Navigation inspects the existing owner surface; it never claims usable
  // session/provider binding, which these Mission fields do not establish.
  // Runtime uncertainty is not an unsettled command receipt. Its owner can
  // be inspected in Work/Sessions; never pretend the cleared command hint
  // can reconcile a separate Runtime effect.
  const routes: ReceiptRoute[] =
    original.status === "unknown"
      ? ["original_status"]
      : selection
        ? ["work", "sessions"]
        : [];
  return Object.freeze({
    operationKey: original.pointer.operationKey,
    kind: original.pointer.kind,
    targetKey: original.pointer.targetKey,
    selection: selection ? Object.freeze({ ...selection }) : null,
    runtime,
    facts: Object.freeze(
      rows.map((row) =>
        Object.freeze({
          ...row,
          evidence: Object.freeze(
            row.evidence.map((x) => Object.freeze({ ...x })),
          ),
        }),
      ),
    ),
    routes: Object.freeze(routes),
  });
}
