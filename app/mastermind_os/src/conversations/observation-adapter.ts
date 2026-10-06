import type { Missionv3Document } from "../mission";
import { observedMissionAssociation, type WindowDocument } from "../workspace-contract";
import { captureMissionOfficeRead, completeMissionOfficeRead, type PendingMissionOfficeRead } from "../meta-ceo/mission-adapter";
import { projectOffice, type OfficeInput, type ProjectionContext, type SourceClaim } from "../meta-ceo/projection";

export const captureObservedConversation = captureMissionOfficeRead;
export interface ObservedConversationSnapshot { input: OfficeInput; context: ProjectionContext }
export type ConversationCompletion =
  | ({ kind: "observed" } & ObservedConversationSnapshot)
  | { kind: "discarded"; reason: string };

/** Presentation only over the App's existing paired Mission/Window observations.
 * The pair has its own read context: a separate Office read cannot qualify it. */
export function completeObservedConversation(
  pending: PendingMissionOfficeRead,
  current: ProjectionContext,
  mission: Missionv3Document | null,
  window: WindowDocument | null,
  localAcquiredAt: string,
): ConversationCompletion {
  if (pending.context.revisions.conversation !== current.revisions.conversation)
    return { kind: "discarded", reason: "WINDOW_READ_SUPERSEDED" };
  const accepted = completeMissionOfficeRead(pending, current, mission, localAcquiredAt);
  if (accepted.kind === "discarded") return accepted;
  const context = structuredClone(accepted.context);
  const input: OfficeInput = { mission: accepted.snapshot, programs: null, result: null, conversation: null };
  const qualifiedMission = projectOffice(input, context).mission;
  const associated = qualifiedMission.source.state === "CURRENT" &&
    observedMissionAssociation(window, qualifiedMission.value, context.selection);
  // This is an explicitly tagged presentation identity made from owner-supplied
  // epoch/publication facts. It is not a session identity or an authority token.
  // Include visibility hashes: filtered content can change within one epoch.
  const revision = associated && window ? "window-owner-observation:v1:" + JSON.stringify([
    window.schema, window.selection_ref, window.view.epoch,
    window.schema === "mastermind.workspace.window_read_candidate.v2" ? window.observation_binding : null,
    window.view.terminal, window.view.coverage,
    window.view.items.map(item => [item.id, item.source_sequence, item.publication_sequence,
      item.state, item.kind, item.representation, item.display_sha256]),
    window.view.gaps,
  ]) : null;
  const source: SourceClaim = {
    owner: "CURRENT_WINDOW", ref: associated ? window!.view.source_ref : null,
    revision, observed_at: associated ? window!.view.observed_at : null,
    state: !window ? "UNAVAILABLE" : associated ? "CURRENT" : "UNASSOCIATED",
    coverage: associated ? window!.view.coverage : "NOT_PROJECTED",
  };
  context.revisions.conversation = revision;
  input.conversation = { context: structuredClone(context), source, value: associated ? structuredClone(window) : null };
  return { kind: "observed", context, input };
}
