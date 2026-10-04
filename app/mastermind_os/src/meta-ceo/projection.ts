/** Read-only presentation over decoded owner DTOs. No reads, persistence or actions. */
import type { MissionDocument, Missionv3Document, MissionSelection, programsFromControlRoom } from "../mission";
import type { ResultEnvelopeDigestShape } from "../result";
import { observedMissionAssociation, type WindowDocument } from "../workspace-contract";

export type SourceState = "CURRENT" | "STALE" | "UNKNOWN" | "UNAVAILABLE" | "WITHHELD" | "UNASSOCIATED";
export type SourceKey = "mission" | "programs" | "result" | "conversation";
export interface ProjectionContext {
  authGeneration: number;
  selection: MissionSelection | null;
  sessionRef: string | null;
  bindingGeneration: string | number | boolean | null;
  revisions: Record<SourceKey, string | null>;
}
export interface SourceClaim {
  owner: string;
  ref: string | null;
  revision: string | null;
  observed_at: string | null;
  state: SourceState;
  coverage: string;
}
export interface ReadSnapshot<T> { context: ProjectionContext; source: SourceClaim; value: T | null }
export interface ProjectedRead<T> { source: SourceClaim; value: T | null; reason: string | null }
export interface OfficeInput {
  mission: ReadSnapshot<MissionDocument | Missionv3Document> | null;
  programs: ReadSnapshot<ReturnType<typeof programsFromControlRoom>> | null;
  result: ReadSnapshot<ResultEnvelopeDigestShape> | null;
  conversation: ReadSnapshot<WindowDocument> | null;
}
export interface OfficeProjection {
  schema: "mastermind.product_projection.v1";
  context: ProjectionContext;
  mission: ProjectedRead<MissionDocument | Missionv3Document>;
  programs: ProjectedRead<ReturnType<typeof programsFromControlRoom>>;
  result: ProjectedRead<ResultEnvelopeDigestShape>;
  conversation: ProjectedRead<WindowDocument>;
  companyTotal: null;
  receipts: Record<"delivery" | "pickup" | "start" | "effect" | "return" | "review" | "acceptance", string | null>;
  work: { state: "UNAVAILABLE"; reason: "WORK_PENDING_CUSTODY" };
  direction: { state: "UNAVAILABLE"; reason: "MISSING_PRODUCER" };
}
export function sameTarget(a: ProjectionContext, b: ProjectionContext): boolean {
  return a.selection?.workRef === b.selection?.workRef &&
    a.selection?.rootJobId === b.selection?.rootJobId &&
    a.sessionRef === b.sessionRef && a.bindingGeneration === b.bindingGeneration;
}

function unavailable<T>(owner: string): ProjectedRead<T> {
  return { source: { owner, ref: null, revision: null, observed_at: null, state: "UNAVAILABLE", coverage: "NOT_PROJECTED" }, value: null, reason: "SOURCE_UNAVAILABLE" };
}

function clear<T>(read: ProjectedRead<T>, state: SourceState, reason: string): ProjectedRead<T> {
  return { ...read, source: { ...read.source, state }, value: null, reason };
}

function qualify<T>(snapshot: ReadSnapshot<T> | null, context: ProjectionContext, key: SourceKey, owner: string): ProjectedRead<T> {
  if (!snapshot) return unavailable(owner);
  const read: ProjectedRead<T> = { source: structuredClone(snapshot.source), value: structuredClone(snapshot.value), reason: null };
  // The old principal's protected source identity must not survive a new auth epoch.
  if (snapshot.context.authGeneration !== context.authGeneration)
    return { ...unavailable<T>(owner), source: { ...unavailable<T>(owner).source, state: "WITHHELD" }, reason: "AUTH_GENERATION_CHANGED" };
  // Every snapshot is captured by one reader context. A future source-wide Programs
  // epoch must be explicit before a collection can cross that context boundary.
  if (!sameTarget(snapshot.context, context))
    return clear(read, "UNASSOCIATED", "TARGET_CHANGED");
  if (snapshot.source.revision !== context.revisions[key])
    return clear(read, "STALE", "SOURCE_REVISION_CHANGED");
  if (!["CURRENT", "STALE"].includes(read.source.state))
    return clear(read, read.source.state, `SOURCE_${read.source.state}`);
  if (read.value === null) return clear(read, "UNAVAILABLE", "SOURCE_VALUE_MISSING");
  if (read.source.state === "CURRENT" && (!read.source.ref || !read.source.revision || !read.source.observed_at))
    return clear(read, "UNKNOWN", "PROVENANCE_INCOMPLETE");
  return read;
}

/** All inputs are decoded at MissionHost. Qualifiers can reduce, never promote owner truth. */
export function projectOffice(input: OfficeInput, context: ProjectionContext): OfficeProjection {
  let mission = qualify(input.mission, context, "mission", "EXECUTIVE_OS");
  let programs = qualify(input.programs, context, "programs", "AGENT_OS");
  let result = qualify(input.result, context, "result", "EXECUTIVE_OS");
  let conversation = qualify(input.conversation, context, "conversation", "CURRENT_WINDOW");
  const m = mission.value;
  if (m) {
    if (!context.selection || m.program.work_ref !== context.selection.workRef ||
        m.mission.root_job_id !== context.selection.rootJobId ||
        m.mission.root_job_ambiguous || m.mission.runtime_root_state !== "RESOLVED")
      mission = clear(mission, "UNASSOCIATED", "MISSION_IDENTITY_UNQUALIFIED");
    else if (m.read_state.state === "UNAVAILABLE")
      mission = clear(mission, "UNAVAILABLE", "MISSION_SOURCE_UNAVAILABLE");
    else if (m.read_state.state === "HISTORICAL")
      mission.source.state = "STALE";
    else if (m.source.owner_observation && m.source.owner_observation.state !== "SAME")
      mission = clear(mission, "UNKNOWN", "OWNER_OBSERVATION_UNQUALIFIED");
    else if (m.read_state.state === "PARTIAL") {
      // Partial owner sections remain useful, with their own coverage and missingness intact.
      if (mission.source.state === "CURRENT") mission.source.state = "UNKNOWN";
      mission.source.coverage = "INCOMPLETE";
      mission.reason = "PARTIAL_OWNER_READ";
    }
  }
  if (programs.value?.state === "UNAVAILABLE") programs = clear(programs, "UNAVAILABLE", programs.value.reason);

  if (result.value) {
    const r = result.value, selected = context.selection;
    const index = mission.value?.schema === "mastermind.mission_workspace.v3" ? mission.value.result_refs : null;
    const missionControl = mission.value?.source.owner_observation?.control_room;
    const resultControl = r.source_observation.control_room;
    const sameControl = missionControl && resultControl &&
      (Object.keys(missionControl) as Array<keyof typeof missionControl>)
        .every(key => missionControl[key] === resultControl[key]);
    const exactRef = index?.refs.some(ref => ref.root_job_id === r.selection.root_job_id &&
      ref.job_id === r.selection.job_id && ref.attempt_id === r.selection.attempt_id &&
      ref.result_envelope_digest === r.selection.result_envelope_digest);
    if (!selected || r.selection.work_ref !== selected.workRef || r.selection.root_job_id !== selected.rootJobId || !exactRef)
      result = clear(result, "UNASSOCIATED", "RESULT_TUPLE_NOT_ASSOCIATED");
    else if (r.availability === "UNAVAILABLE") result = clear(result, "UNAVAILABLE", r.reason_codes.join(" · "));
    else if (!sameControl || mission.source.state !== "CURRENT" || r.source_observation.state !== "SAME" || index?.generation.state !== "SAME" ||
      index.generation.source_identity !== r.source_observation.runtime?.source_identity ||
      index.generation.before !== r.source_observation.runtime?.before || index.generation.after !== r.source_observation.runtime?.after)
      result = clear(result, "UNKNOWN", "RESULT_OBSERVATION_UNQUALIFIED");
    else if (r.availability === "CONTENT_OVER_BUDGET") {
      result.source.coverage = "INCOMPLETE";
      result.reason = "CONTENT_OVER_BUDGET";
    }
  }
  if (conversation.value && (mission.source.state !== "CURRENT" ||
      !observedMissionAssociation(conversation.value, mission.value, context.selection)))
    conversation = clear(conversation, "UNASSOCIATED", "EXACT_WINDOW_ASSOCIATION_MISSING");

  const d = mission.value;
  const dispatch = d?.transport.dispatch_state;
  const effects = [d?.principal.current_worker?.effect_state, d?.principal.current_sol_target?.effect_state].filter(v => v != null);
  const effectUnknown = dispatch === "EFFECT_UNKNOWN" || effects.includes("effect_unknown");
  const uniqueEffects = [...new Set(effects)];
  return {
    schema: "mastermind.product_projection.v1", context: structuredClone(context),
    mission, programs, result, conversation, companyTotal: null,
    receipts: {
      delivery: dispatch === "DELIVERY_SENT" || dispatch === "DELIVERY_UNCONSUMED" ? dispatch : null,
      pickup: dispatch === "PICKUP_ACKNOWLEDGED" ? dispatch : null,
      start: dispatch === "STARTED" ? dispatch : null,
      effect: effectUnknown ? "EFFECT_UNKNOWN" : uniqueEffects.length === 1 ? uniqueEffects[0]!.toUpperCase() : uniqueEffects.length > 1 ? "UNKNOWN" : null,
      return: dispatch === "RETURNED" ? "RETURNED" : null,
      review: d?.review.verdict ?? null,
      acceptance: d?.acceptance.state ?? null,
    },
    work: { state: "UNAVAILABLE", reason: "WORK_PENDING_CUSTODY" },
    direction: { state: "UNAVAILABLE", reason: "MISSING_PRODUCER" },
  };
}
