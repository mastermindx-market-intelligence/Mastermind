import type { OfficeProjection, SourceClaim } from "../meta-ceo/projection";
import { observedMissionAssociation } from "../workspace-contract";
import type {
  ConversationListModel, ConversationListProjectRow, ConversationListRecentRow,
  ConversationListSourceState, ConversationProjectLocator, CurrentConversationLocator,
} from "./conversation-list-contract";

/** Already-decoded, already-qualified existing observations. This projection
 * performs no read and issues no capability. The App's actual owner rechecks
 * host/auth/source again before an Open gesture can navigate. */
export interface ConversationListInputs {
  readonly authGeneration: number;
  readonly catalogue: OfficeProjection;
  readonly conversation: OfficeProjection;
  readonly acquisitionAllowed: boolean;
  readonly contentAllowed: boolean;
  /** Owner captures retained by the existing acquisition, not minted while
   * rendering a cached DTO after the host/principal generation changed. */
  readonly catalogueReadCurrent: boolean;
  readonly conversationReadCurrent: boolean;
  readonly programsPending?: boolean;
  readonly windowPending?: boolean;
  readonly hasUnsentDraft: boolean;
}

function currentClaim(source: SourceClaim, revision: string | null): boolean {
  return source.state === "CURRENT" && Boolean(source.ref && source.revision &&
    source.revision === revision && source.observed_at && Number.isFinite(Date.parse(source.observed_at)));
}

function sourceState(source: SourceClaim, revision: string | null): ConversationListSourceState {
  if (source.state !== "CURRENT") return source.state;
  if (source.revision !== revision) return "STALE";
  return currentClaim(source, revision) ? "CURRENT" : "UNKNOWN";
}

/** Current window is one actual conversation, never a full history census.
 * Projects remain a separate population and retain the catalogue's order. */
export function composeConversationsList(input: ConversationListInputs): ConversationListModel {
  const { catalogue, conversation, authGeneration } = input;
  const epochValid = Number.isSafeInteger(authGeneration) && authGeneration >= 0;
  const projectsAllowed = epochValid && input.acquisitionAllowed && input.catalogueReadCurrent &&
    catalogue.context.authGeneration === authGeneration;
  let projectsState: ConversationListSourceState = !projectsAllowed ? "WITHHELD"
    : input.programsPending ? "PENDING"
    : sourceState(catalogue.programs.source, catalogue.context.revisions.programs);
  const projects: ConversationListProjectRow[] = [];
  if (projectsState === "CURRENT") {
    const document = catalogue.programs.value;
    if (!document || document.state !== "AVAILABLE") projectsState = "UNAVAILABLE";
    else if (new Set(document.programs.map(p => p.workRef)).size !== document.programs.length)
      projectsState = "UNASSOCIATED";
    else for (const card of document.programs) {
      const locator = Object.freeze({ kind: "project" as const, workRef: card.workRef,
        sourceRef: catalogue.programs.source.ref!, sourceRevision: catalogue.programs.source.revision!,
        authGeneration });
      projects.push(Object.freeze({ key: `project:${card.workRef}`, locator,
        title: card.title, nextAction: card.nextActionWithheld ? null : card.nextAction }));
    }
  }

  const currentAllowed = epochValid && input.acquisitionAllowed && input.contentAllowed && input.conversationReadCurrent &&
    conversation.context.authGeneration === authGeneration;
  let recentState: ConversationListSourceState = !currentAllowed ? "WITHHELD"
    : input.windowPending ? "PENDING"
    : sourceState(conversation.conversation.source, conversation.context.revisions.conversation);
  const recent: ConversationListRecentRow[] = [];
  if (recentState === "CURRENT") {
    const mission = conversation.mission.value, window = conversation.conversation.value;
    const selection = conversation.context.selection;
    const missionCurrent = currentClaim(conversation.mission.source, conversation.context.revisions.mission);
    const association = missionCurrent && mission?.schema === "mastermind.mission_workspace.v3" &&
      observedMissionAssociation(window, mission, selection);
    if (!window || !selection || !association || !mission ||
        conversation.conversation.source.ref !== window.view.source_ref ||
        conversation.conversation.source.observed_at !== window.view.observed_at)
      recentState = "UNASSOCIATED";
    else {
      const locator = Object.freeze({ kind: "current" as const, workRef: selection.workRef,
        rootJobId: selection.rootJobId, jobId: association.job_id, attemptId: association.attempt_id,
        selectionRef: window.selection_ref, sourceRef: window.view.source_ref,
        sourceRevision: conversation.conversation.source.revision!, epoch: window.view.epoch,
        authGeneration });
      // A declared Mission title can label its associated conversation. Reply
      // text, generated summaries, provider sessions and saved clocks are absent.
      recent.push(Object.freeze({ key: "current:" + JSON.stringify([
        locator.workRef, locator.rootJobId, locator.jobId, locator.attemptId, locator.sourceRef, locator.epoch]),
        locator, title: mission.mission.title,
        projectTitle: mission.program.title ?? projects.find(p => p.locator.workRef === selection.workRef)?.title ?? null,
        observedAt: window.view.observed_at, unsentDraft: input.hasUnsentDraft }));
    }
  }

  const summary = (owner: "CURRENT_WINDOW" | "PROJECT_CATALOGUE", state: ConversationListSourceState,
    source: SourceClaim) => Object.freeze({ owner, state,
    observedAt: state === "WITHHELD" ? null : source.observed_at,
    revision: state === "WITHHELD" ? null : source.revision });
  return Object.freeze({ schema: "mastermind.conversations_list_projection.v1" as const,
    authGeneration, recentState, projectsState, recent: Object.freeze(recent), projects: Object.freeze(projects),
    sources: Object.freeze([summary("CURRENT_WINDOW", recentState, conversation.conversation.source),
      summary("PROJECT_CATALOGUE", projectsState, catalogue.programs.source)]),
    historyCoverage: "NOT_ENUMERATED" as const });
}

const CURRENT_KEYS: readonly (keyof CurrentConversationLocator)[] = [
  "kind", "workRef", "rootJobId", "jobId", "attemptId", "selectionRef",
  "sourceRef", "sourceRevision", "epoch", "authGeneration",
];
const PROJECT_KEYS: readonly (keyof ConversationProjectLocator)[] = [
  "kind", "workRef", "sourceRef", "sourceRevision", "authGeneration",
];

/** Membership/currentness only, never read or send authority. */
export function isListedCurrentConversation(model: ConversationListModel, target: CurrentConversationLocator): boolean {
  return model.recentState === "CURRENT" && target.authGeneration === model.authGeneration &&
    Object.keys(target).length === CURRENT_KEYS.length && model.recent.some(row =>
      CURRENT_KEYS.every(key => row.locator[key] === target[key]));
}

export function isListedConversationProject(model: ConversationListModel, target: ConversationProjectLocator): boolean {
  return model.projectsState === "CURRENT" && target.authGeneration === model.authGeneration &&
    Object.keys(target).length === PROJECT_KEYS.length && model.projects.some(row =>
      PROJECT_KEYS.every(key => row.locator[key] === target[key]));
}
