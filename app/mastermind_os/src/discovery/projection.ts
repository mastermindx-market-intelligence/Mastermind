/** Ephemeral discovery projection over decoded owner inputs.
 * Pure deterministic mapping. No acquisition, catalogue registry, promotion,
 * credential, command or persistence path; ids are ephemeral UI keys. */
import {
  allEvidence,
  normalizeWorkspaceSelection,
  type EvidenceRef,
  type MissionDocument,
  type Missionv3Document,
} from "../mission";
import {
  sameTarget,
  type ProjectedRead,
  type SourceClaim,
  type SourceState,
} from "../meta-ceo/projection";
import { normalizeResultSelection } from "../result";
import { observedMissionAssociation } from "../workspace-contract";
import type {
  DiscoveryCapability,
  DiscoveryInputs,
  DiscoveryItem,
  DiscoveryLimitation,
  DiscoverySource,
  DiscoverySystemObservation,
  DiscoveryView,
} from "./contract";

const MISSION_V2_SCHEMA = "mastermind.mission_workspace.v2" as const;
const MISSION_V3_SCHEMA = "mastermind.mission_workspace.v3";
const SUMMARY_CHARS = 240;

/** CURRENT/STALE projected reads with complete provenance may produce records. */
function isQualifiedClaim(source: SourceClaim): boolean {
  return (
    (source.state === "CURRENT" || source.state === "STALE") &&
    [source.ref, source.revision, source.observed_at].every(value => typeof value === "string" && value.trim().length > 0)
  );
}

/** Exact claim for qualified reads; provenance redacted for every other state. */
function presentedClaim(source: SourceClaim): SourceClaim {
  if (isQualifiedClaim(source)) return { ...source };
  return {
    owner: source.owner,
    ref: null,
    revision: null,
    observed_at: null,
    state: source.state,
    coverage: source.coverage,
  };
}

/** Per-ref freshness reduction over the selected mission citation. */
function evidenceRowState(evidence: EvidenceRef, parentStale: boolean): SourceState {
  if (evidence.freshness_state === "UNAVAILABLE") return "UNAVAILABLE";
  if (evidence.freshness_state === "HISTORICAL" || parentStale) return "STALE";
  if (
    evidence.freshness_state === "PARTIAL" ||
    !evidence.ref ||
    evidence.source_revision === null ||
    evidence.observed_at === null
  ) {
    return "UNKNOWN";
  }
  return "CURRENT";
}

function ownerSourceRow(
  id: string,
  title: string,
  read: ProjectedRead<unknown>,
): DiscoverySource {
  const claim = read.source;
  const qualified = isQualifiedClaim(claim);
  return {
    id,
    title,
    owner: claim.owner,
    state: claim.state,
    reference: qualified ? claim.ref : null,
    revision: qualified ? claim.revision : null,
    observedAt: qualified ? claim.observed_at : null,
    observedKind: qualified ? (claim.observed_at_kind ?? null) : null,
    sourceTime: null,
    coverage: claim.coverage,
    content: qualified && read.value !== null ? "OBSERVED" : "UNAVAILABLE",
    reason: read.reason,
  };
}

/** Citation-only row for one supplied Mission evidence reference. */
function evidenceSourceRow(
  index: number,
  evidence: EvidenceRef,
  parentStale: boolean,
): DiscoverySource {
  const state = evidenceRowState(evidence, parentStale);
  const unavailable = state === "UNAVAILABLE";
  return {
    id: `discovery-source:evidence:${index}`,
    title: `${evidence.owner} ${evidence.field}`,
    owner: evidence.owner,
    state,
    reference: unavailable ? null : evidence.ref,
    revision: unavailable ? null : evidence.source_revision,
    observedAt: unavailable ? null : evidence.observed_at,
    observedKind: null,
    sourceTime: unavailable ? null : evidence.source_time,
    coverage: "REFERENCE_ONLY",
    content: "REFERENCE_ONLY",
    reason: null,
  };
}

/** Project the supplied decoded owners into the detached discovery view. */
export function projectDiscovery(inputs: DiscoveryInputs): DiscoveryView {
  const projection = inputs.projection;
  const context = projection.context;

  const items: DiscoveryItem[] = [];
  const sources: DiscoverySource[] = [];
  const systems: DiscoverySystemObservation[] = [];

  const missionRead = projection.mission;
  const missionValue = missionRead.value;
  const missionQualified = isQualifiedClaim(missionRead.source) && missionValue !== null;
  const parentStale = missionRead.source.state === "STALE";
  const missionV3 =
    missionQualified && missionValue !== null && missionValue.schema === MISSION_V3_SCHEMA
      ? (missionValue as Missionv3Document)
      : null;

  // Programs -> project items, in supplied owner order.
  const programsRead = projection.programs;
  const programsValue = programsRead.value;
  if (
    isQualifiedClaim(programsRead.source) &&
    programsValue !== null &&
    programsValue.state === "AVAILABLE"
  ) {
    const claim = presentedClaim(programsRead.source);
    programsValue.programs.forEach((card, index) => {
      const resolvedRoot =
        card.rootState === "RESOLVED" &&
        card.rootCandidates.length === 1 &&
        card.rootCandidates[0] === card.rootJobId;
      const selection =
        resolvedRoot && card.rootJobId !== null
          ? normalizeWorkspaceSelection({ workRef: card.workRef, rootJobId: card.rootJobId })
          : null;
      const title = card.title ?? card.workRef;
      const summary =
        card.nextActionWithheld || card.nextAction === null ? null : card.nextAction;
      items.push({
        id: `discovery:project:${card.workRef}:${index}`,
        kind: "project",
        title,
        summary,
        searchText: summary === null ? title : `${title} ${summary}`,
        source: claim,
        target: { kind: "project", selection, mode: "current" },
      });
    });
  }
  sources.push(ownerSourceRow("discovery-source:programs", "Programs", programsRead));
  sources.push(ownerSourceRow("discovery-source:mission", "Mission", missionRead));

  // Separately paired current-window owner; never inferred from Office.
  const conversationProjection = inputs.conversation ?? null;
  const windowRead = conversationProjection === null ? null : conversationProjection.conversation;
  const windowValue = windowRead === null ? null : windowRead.value;
  if (conversationProjection !== null && windowRead !== null) {
    const paired = conversationProjection.context.authGeneration === context.authGeneration &&
      sameTarget(context, conversationProjection.context);
    sources.push(ownerSourceRow("discovery-source:window", "Observed window", paired ? windowRead : {
      source: { owner: windowRead.source.owner, ref: null, revision: null, observed_at: null,
        state: "WITHHELD", coverage: "NOT_PROJECTED" }, value: null, reason: "OWNER_CONTEXT_MISMATCH" }));
    const windowQualified = isQualifiedClaim(windowRead.source) && windowValue !== null;
    const authMatched = conversationProjection.context.authGeneration === context.authGeneration;
    const association =
      windowQualified &&
      authMatched &&
      sameTarget(context, conversationProjection.context) &&
      observedMissionAssociation(windowValue, missionV3, context.selection);
    if (windowValue !== null && association) {
      const claim = presentedClaim(windowRead.source);
      windowValue.view.items.forEach((entry, index) => {
        if (entry.kind !== "visible-response") return;
        if (entry.representation === "WITHHELD") return;
        if (entry.text === null) return;
        items.push({
          id: `discovery:conversation:${entry.id}:${index}`,
          kind: "conversation",
          title: "Observed response",
          summary: entry.text.slice(0, SUMMARY_CHARS),
          searchText: entry.text,
          source: claim,
          target: { kind: "conversation", reference: windowValue.view.source_ref },
        });
      });
    }
  }

  // Result refs only from the selected qualified v3 mission with SAME generation.
  let reviewRefSupplied = false;
  if (missionV3 !== null) {
    const refs = missionV3.result_refs;
    const rootMatch =
      refs.root_job_id === missionV3.mission.root_job_id &&
      context.selection !== null &&
      refs.root_job_id === context.selection.rootJobId;
    if (
      (refs.availability === "AVAILABLE" || refs.availability === "PARTIAL") &&
      refs.generation.state === "SAME" &&
      rootMatch
    ) {
      const claim = presentedClaim(missionRead.source);
      refs.refs.forEach((ref, index) => {
        const selection = normalizeResultSelection({
          workRef: context.selection === null ? "" : context.selection.workRef,
          rootJobId: ref.root_job_id,
          jobId: ref.job_id,
          attemptId: ref.attempt_id,
          resultEnvelopeDigest: ref.result_envelope_digest,
        });
        if (selection === null) return;
        const role = ref.orchestration_role;
        if (role === "review") reviewRefSupplied = true;
        items.push({
          id: `discovery:result:${ref.job_id}:${ref.attempt_id}:${index}`,
          kind: "result",
          title: `${role} result ${ref.job_id}`,
          summary: null,
          searchText: `${role} ${ref.job_id} ${ref.attempt_id} ${ref.result_envelope_digest}`,
          source: claim,
          target: { kind: "result", selection, role },
        });
      });
    }
  }

  const resultRead = projection.result;
  if (isQualifiedClaim(resultRead.source) || resultRead.value !== null) {
    sources.push(ownerSourceRow("discovery-source:result", "Result", resultRead));
  }

  // Evidence citations from the selected qualified mission; content REFERENCE_ONLY.
  if (missionQualified && missionValue !== null) {
    const v2Mission = { ...missionValue, schema: MISSION_V2_SCHEMA } as MissionDocument;
    allEvidence(v2Mission).forEach(({ evidence, facet }, index) => {
      items.push({
        id: `discovery:evidence:${evidence.owner}:${index}`,
        kind: "evidence",
        title: `${evidence.owner} ${evidence.field}`,
        summary: null,
        searchText: `${evidence.owner} ${evidence.field}`,
        source: { owner: evidence.owner, ref: evidence.ref || null,
          revision: evidence.source_revision, observed_at: evidence.observed_at,
          state: evidenceRowState(evidence, parentStale), coverage: "REFERENCE_ONLY" },
        target: { kind: "evidence", evidence: { ...evidence }, facet },
      });
      sources.push(evidenceSourceRow(index, evidence, parentStale));
    });
  }

  // Detached Control Room cache: only with ownerRevision === current auth generation.
  const controlRoom = inputs.controlRoom ?? null;
  const controlRoomQualified =
    controlRoom !== null &&
    controlRoom.state === "AVAILABLE" &&
    controlRoom.ownerRevision === context.authGeneration;
  if (controlRoomQualified && controlRoom !== null) {
    sources.push({
      id: "discovery-source:control-room",
      title: "Control Room cache",
      owner: "CONTROL_ROOM_CACHE",
      state: "UNKNOWN",
      reference: null,
      revision: String(controlRoom.ownerRevision),
      observedAt: controlRoom.observedAt,
      observedKind: null,
      sourceTime: null,
      coverage: "OWNER_QUALIFIED_CACHE",
      content: "OBSERVED",
      reason: null,
    });
    if (controlRoom.navigation.state === "AVAILABLE") {
      for (const [provider, capability] of Object.entries(controlRoom.navigation.capabilities)) {
        if (!capability) continue;
        const observation: DiscoverySystemObservation = {
          provider,
          installed: capability.installed,
          state: capability.state,
          version: capability.version,
          detail: capability.detail,
          observedAt: controlRoom.observedAt,
        };
        systems.push(observation);
      }
    }
  }

  // Capabilities are local view hints only, never provider grants.
  const missionCurrentQualified = missionQualified && missionRead.source.state === "CURRENT";
  const anyRecords = items.length > 0;
  const capabilities: DiscoveryCapability[] = [
    {
      id: "direction_preview",
      state: missionCurrentQualified ? "PREVIEW_ONLY" : "UNAVAILABLE",
      target: missionCurrentQualified ? "meta_ceo" : null,
    },
    {
      id: "search",
      state: anyRecords ? "READ_ONLY" : "UNAVAILABLE",
      target: anyRecords ? "search" : null,
    },
    {
      id: "return_review",
      state: reviewRefSupplied ? "READ_ONLY" : "UNAVAILABLE",
      target: reviewRefSupplied ? "knowledge" : null,
    },
    { id: "source_context", state: "READ_ONLY", target: "sources" },
    { id: "placement", state: "UNAVAILABLE", target: null },
    { id: "release", state: "UNAVAILABLE", target: null },
  ];

  const limitations: DiscoveryLimitation[] = [
    "BOUNDED_SCOPE",
    "NO_PEOPLE_INDEX",
    "NO_GLOBAL_HISTORY",
    "NO_GENERIC_SOURCE_READER",
  ];
  if (!controlRoomQualified) limitations.push("CONTROL_ROOM_NOT_SUPPLIED");

  return { context: { ...context, selection: context.selection ? { ...context.selection } : null,
    revisions: { ...context.revisions } }, scope: "SUPPLIED_WORKSPACE", items, sources, capabilities, systems, limitations };
}
