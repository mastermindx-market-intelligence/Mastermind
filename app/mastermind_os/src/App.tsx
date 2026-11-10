import {NativeWorkAuthorizationControl} from "./NativeWorkAuthorizationControl";
import {NativePrimaryAccountControl} from "./NativePrimaryAccountControl";
import {NativeAuthorizationContinuationControl} from "./NativeAuthorizationContinuationControl";
import {CompanyPrioritiesRead} from "./meta-ceo/CompanyPrioritiesRead";
import {ProjectDetailsNavigator} from './projects/ProjectDetailsNavigator';
import {RetainedResultContent} from './activity/RetainedResultContent';
import {PlanAdoptionWorkflow} from "./planning/PlanAdoptionWorkflow";
import { appCopy } from "./app-copy";
import { ProductAcceptancePanel } from "./product-acceptance/ProductAcceptancePanel";
import type { AuthState, MissionHost } from "./host";
import type {
  ObservedMissionAssociation,
  WindowDocument,
} from "./workspace-contract";
import { observedMissionAssociation } from "./workspace-contract";
import { lazy, Suspense, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { readFreshConversationLocation } from "./conversations/fresh-conversation-location";
import { useFreshConversationDraftState } from "./conversations/new-conversation/useFreshConversationDraftState";
import { useFreshConversationJourney } from "./conversations/new-conversation/useFreshConversationJourney";
import { createFreshConversationBinding } from "./conversations/new-conversation/fresh-conversation-command-binding";
import { createFreshConversationAttendedBinding, type FreshConversationOriginalRead } from "./conversations/new-conversation/fresh-conversation-attended-binding";
import { FreshConversationContinuation } from "./conversations/new-conversation/FreshConversationContinuation";
import { useFreshConversationTurnDraftState } from "./conversations/new-conversation/useFreshConversationTurnDraftState";
import { sameConversationOwner } from "./conversations/new-conversation/fresh-conversation-binding";
import { decodeFreshConversationResult } from "./conversations/new-conversation/fresh-conversation";
import { freshConversationOriginalSelector, freshConversationTarget, parseFreshConversationTarget } from "./orchestration/fresh-conversation-target";
import {
  canNavigateForAutomaticSignIn, explicitLogoutRecorded, registerUnsavedNavigationHold,
} from "./auth-navigation-guard";
import { MetaCeoOffice } from "./meta-ceo/MetaCeoOffice";
import { captureOfficeReadFrame } from "./meta-ceo/office-read-frame";
import {
  decideOfficeLaunchHandoff, officeLaunchWorkstreamAgrees, previewIsCurrent,
  type DirectionPreview, type OfficeLaunchOutcome,
} from "./meta-ceo/preview";
import { readLaunchBindingConfig } from "./launch-config";
import { resolveLaunchBinding } from "./orchestration/executive-launch-command-port";
import { Today } from "./today/Today";
import { AuthEntry } from "./auth-entry/AuthEntry";
import privateEntryArt from "./auth-entry/private-entry.jpg";
import { AttendedFabricWorkspace } from "./fabric/AttendedFabricWorkspace";
import { qualifyWorkerResultRef } from "./fabric/mission-worker-result";
import { useOfficeProjection } from "./meta-ceo/useOfficeProjection";
import { useByokRoleObservation } from "./meta-ceo/use-byok-role-observation";
import { byokRoleView } from "./meta-ceo/byok-role-view";
import { qualifyExecutiveOfficeSession, SESSION_TARGET_REF } from "./meta-ceo/session-context";
import { Projects } from "./projects/Projects";
import { ProjectPlanningJourney } from "./projects/ProjectPlanningJourney";
import { useProjectJourneyState } from "./projects/useProjectJourneyState";
import {createSessionExecutiveOwnerGetter} from "./auth-recovery/session-executive-owner";
import { useNativeProjectGoalRecovery } from "./auth-recovery/useNativeProjectGoalRecovery";
import { NativeDraftRecoveryNotice } from "./auth-recovery/NativeDraftRecoveryNotice";
import { readProjectJourneyLocation } from "./projects/project-journey-location";
import { ProjectArchiveBrowser } from "./projects/archive/ProjectArchiveBrowser";
import { ProjectWorkspace } from "./projects/ProjectWorkspace";
import { ProjectConversationAssociation } from "./conversations/ProjectConversationAssociation";
import { ProjectExecutionHistory } from "./conversations/ProjectExecutionHistory";
import { AcceptedDirectionPanel } from "./direction/AcceptedDirectionPanel";
import { useProjectAdmissionWorkspace } from "./useProjectAdmissionWorkspace";
import { useProjectDetailsControls } from "./projects/useProjectDetailsControls";
import { InboxWorkspace } from "./inbox/InboxWorkspace";
import { Knowledge } from "./knowledge/Knowledge";
import { knowledgeDraftBinding, type KnowledgeDraftPort } from "./knowledge/KnowledgeDraftCompanion";
import type { ProjectSourceDraftPort } from "./knowledge/library/project-source-draft";
import { useProjectKnowledgeWorkspace } from "./knowledge/useProjectKnowledgeWorkspace";
import { ProjectKnowledgeEditor } from "./knowledge/library/ProjectKnowledgeEditor";
import {ProjectDiscoveryCorrectionEditor,DiscoveryCorrectionReview} from './knowledge/library/ProjectDiscoveryCorrectionEditor';
import type { ProjectMemoryDocument, KnowledgeLibrarySourceContext, ProjectDiscoverySource } from "./knowledge/library/knowledge-library-contract";
import { ProjectKnowledgeLibrary } from "./knowledge/library/ProjectKnowledgeLibrary";
import type { KnowledgeLibraryProps } from "./knowledge/library/knowledge-library-contract";
import { ProjectSearchWorkspace } from "./discovery/ProjectSearchWorkspace";
import { projectReadingPresentation } from "./knowledge/project-reading-presentation";
import { SavedConversationReader, createSavedConversationNavigation, type SavedConversationNavigation } from "./discovery/SavedConversationReader";
import { DiscoveryWorkspace } from "./discovery/DiscoveryWorkspace";
import { projectDiscovery } from "./discovery/projection";
import { ProjectWorkDetail, ProjectEvidence, ProjectJournal } from "./workJourney";
import { ConversationWindow } from "./conversations/ConversationWindow";
import { HistoricalOriginalAnswers } from "./conversations/HistoricalOriginalAnswers";
import { RetainedResults } from "./RetainedResults";
import { RetainedActivityInspector, type RetainedActivityReader } from "./planning/RetainedActivityInspector";
import { validActivitySelection } from "./planning/retained-activity";
import { RetainedRootChoice } from "./RetainedRootChoice";
import { normalizeResultReferencesSelection } from "./result-references";
import { parseDirectConsumeTarget } from "./direct-native-result";
import { createAwaitingAnswerPort } from "./conversations/awaiting-answer-port";
import { useQualifiedOriginalAnswer } from "./conversations/useQualifiedOriginalAnswer";
import type { QualifiedSessionAnswer } from "./orchestration/executive-session-command-port";
import { useObservedConversation } from "./conversations/useObservedConversation";
import { ConversationsList } from "./conversations/ConversationsList";
import { composeConversationsList, isListedCurrentConversation, isListedConversationProject } from "./conversations/conversation-list-source";
import { captureConversationListOwner, conversationListOwnerCurrent, type ConversationListOwnerCapture } from "./conversations/conversation-list-owner";
import { useConversationListNavigation } from "./conversations/useConversationListNavigation";
import { useProjectConversationHistory } from "./conversations/useProjectConversationHistory";
import { useProjectConversations } from "./conversations/useProjectConversations";
import {
  OperationController,
  type OperationKind,
  type OperationPointer,
  type OperationState,
} from "./orchestration/operation-controller";
import {
  LaunchOrchestrator,
  type LaunchForm,
  type LaunchDetailsDraft,
} from "./orchestration/ui/LaunchOrchestrator";
import { SessionWorkspace } from "./orchestration/ui/SessionWorkspace";
import {
  COMMAND_ROUTE_UNAVAILABLE,
  completeOrchestratorCommandBinding,
  launchIntentFromBinding,
  messageIntentFromBinding,
  readCommandView,
  readOwnerContext,
  sessionMatchesSelection,
  stopIntentFromBinding,
  subscribeCommandView,
  type OrchestratorCommandBinding,
} from "./orchestration/host-command-bindings";
import { SelectedSessionContinuation } from "./orchestration/ui/SelectedSessionContinuation";
import { DirectNativeResultPanel } from "./orchestration/ui/DirectNativeResultPanel";
import { directLocationInput } from "./direct-native-location";
import {
  completeExecutiveSessionBinding,
  readSessionOwnerContext,
  type MountedExecutiveSessionBinding,
} from "./orchestration/os-executive-session-host";
import {
  EXECUTIVE_SESSION_TARGET_KINDS,
  type ExecutiveSessionTargetKind,
  type HermesNativePublicResult,
  type QualifiedSessionAnswerValue,
} from "./orchestration/executive-session-command-port";
import {
  allEvidence,
  decodeMission,
  decodeMissionv3,
  normalizeSelection,
  programsFromControlRoom,
  relationshipsForMission,
  unavailableMission,
  type MissionDocument,
  type MissionSelection,
  type Missionv3Document,
  type UnavailableMission,
} from "./mission";
import { controlRoomActionIsUncertain, type ControlRoomState } from "./control-room";
import { ControlRoomPanel } from "./ControlRoomPanel";
import { SessionEstate } from "./session-estate/SessionEstate";
import { ResourcesSystemsPanel } from "./resources/ResourcesSystemsPanel";
import { ResourceCapacityRead } from "./resources/ResourceCapacityRead";
import { ModelConfigurationRead } from "./resources/ModelConfigurationRead";
import { CapacityFabricRead } from "./resources/CapacityFabricRead";
import { selectedCurrentCapacityAttempt } from "./resource-capacity-selection";
import { SupervisionLedger } from "./supervision/SupervisionLedger";
import { SupervisionTrace } from "./supervision/SupervisionTrace";
import { ProjectPlanPanel } from "./planning/ProjectPlanPanel";
import { ProjectStartWork, type ProjectPlanLaunchInspection } from "./planning/ProjectStartWork";
import { projectExecutionContext } from "./planning/project-execution-context";
import type { ProjectExecutionPreview, ProjectExecutionPreviousRun } from "./planning/project-execution-transport";
import { canonicalJson } from "./orchestration/operation-key";
import {
  createProjectLaunchDraft, decideProjectLaunchHandoff, projectLaunchContextIsCurrent,
  type ProjectLaunchDraft, type ProjectLaunchOutcome,
} from "./planning/project-launch-handoff";
import { ProjectJournalReader } from "./ProjectJournalReader";
import { AutonomyPanel } from "./supervision/AutonomyPanel";
import { ActivationReceipt } from "./activation/ActivationReceipt";
import { ActivationFacts } from "./activation/ActivationFacts";
import { activationFacts, type ReceiptRoute } from "./activation/activation-facts";
import type { OriginalOperationObservation } from "./orchestration/operation-controller";
import { WebSessionPreview } from "./activation/WebSessionPreview";
import { readLaunchRequestPreview } from "./activation/LaunchRequestPreview";
import { useControlRoomSurfaceControls } from "./useControlRoomSurfaceControls";
import { ControlRoomSurfaceControls } from "./ControlRoomSurfaceControls";
import {
  decodeResultEnvelope,
  normalizeResultSelection,
  type ResultEnvelopeDigestShape,
  type ResultSelection,
} from "./result";
import {
  decodeWorkDocument,
  WORK_GROUP_ORDER,
  type WorkDocument,
} from "./work";
import { TransportDiagnosticFields } from "./TransportDiagnosticFields";
import { nativeAuthFeedback, nativePartialAuthPresentation } from "./native-partial-auth-presentation";
import { closedReadFailurePhase, closedReadFailureReason, type DiagnosticPhase, type DiagnosticReadReason } from "./diagnostic-state";
const CompanyWorkspace = lazy(() => import("./company/CompanyWorkspace").then(module => ({ default: module.CompanyWorkspace })));

export const navigation = [
  "Today",
  "Team",
  "Projects",
  "Inbox",
  "Conversations",
  "Knowledge",
  "Search",
  "Sources",
  "Tools",
  "Meta-CEO",
  "Work",
  "Programs",
  "Control Room",
  "Session Estate",
  "Fleet & Capacity",
  "Mission Workspace",
  "Conversation",
  "Activity",
  "Connections",
  "Evidence",
] as const;
type View = (typeof navigation)[number];
const primaryNavigation: readonly View[] = [
  "Today",
  "Team",
  "Projects",
  "Inbox",
  "Conversations",
  "Knowledge",
];
type OperationalView = "Work" | "Programs" | "Control Room" | "Fleet & Capacity";
function OperationalNavigation({ label, onNavigate }: {
  label: string;
  onNavigate: (view: OperationalView) => void;
}) {
  return (
    <nav className="card" aria-label={label}>
      <div className="segmented">
        <button type="button" onClick={() => onNavigate("Work")}>Work</button>
        <button type="button" onClick={() => onNavigate("Programs")}>Open Programs</button>
        <button type="button" onClick={() => onNavigate("Control Room")}>Control Room</button>
        <button type="button" onClick={() => onNavigate("Fleet & Capacity")}>Fleet &amp; Capacity</button>
      </div>
    </nav>
  );
}
const missionNavigation: readonly View[] = [
  "Mission Workspace",
  "Conversation",
  "Activity",
  "Connections",
  "Evidence",
];
const advancedNavigation: readonly View[] = ["Sources", "Tools", "Meta-CEO", "Work", "Programs", "Control Room", "Session Estate", "Fleet & Capacity", ...missionNavigation];
const advancedLabel = (view: View, locale: "en" | "zh-CN") => locale === "zh-CN" ? navigationLabel(view, locale) :
  view === "Work" ? "Work queue" : view === "Programs" ? "Programs workspace" :
  view === "Control Room" ? "Control Room workspace" : view === "Fleet & Capacity" ? "Fleet & Capacity workspace" : view;
const projectTabs = ["Conversation", "Overview", "Plan", "Work", "Evidence", "Journal", "More"] as const;
type ProjectTab = (typeof projectTabs)[number];
const navigationPaths: Record<View, string> = {
  Search: "M10 3a7 7 0 1 0 0 14 7 7 0 0 0 0-14M15 15l6 6",
  Sources: "M5 3h10l4 4v14H5zM14 3v5h5M8 12h8M8 16h5",
  Tools: "M8 3h8v5H8zM4 12h5v8H4zM15 12h5v8h-5M12 8v3M6 11h12",

  "Session Estate": "M4 4h16v12H4zM8 20h8M12 16v4",
  Today: "M3 10 12 3l9 7v11H3zM9 21v-7h6v7",
  Team: "M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M16 3a4 4 0 0 1 0 8M22 21v-2a4 4 0 0 0-3-3.87M13 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0",
  Projects: "M3 6h6l2 2h10v12H3z", Inbox: "M3 5h18v15H3zM3 14h5l2 3h4l2-3h5",
  Conversations: "M4 4h16v12H9l-5 4z", Knowledge: "M4 3h7v17H4zM14 3h6v17h-6z",
  "Meta-CEO": "M12 3 3 8l9 5 9-5zM3 12l9 5 9-5M3 16l9 5 9-5",
  Work: "M6 4h15v17H6zM2 8h8M2 13h8M2 18h8", Programs: "M3 4h18v16H3zM8 4v16M3 9h18",
  "Control Room": "M4 5h16v14H4zM8 9h2M14 9h2M8 14h8", "Fleet & Capacity": "M3 4h18v6H3zM3 14h18v6H3zM7 7h.01M7 17h.01",
  "Mission Workspace": "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18M12 8v8M8 12h8",
  Conversation: "M4 4h16v12H9l-5 4z", Activity: "M2 12h5l3-8 4 16 3-8h5",
  Connections: "M9 8 5 12l4 4M15 8l4 4-4 4M10 12h4", Evidence: "M5 3h10l4 4v14H5zM14 3v5h5M8 12h8M8 16h6",
};
function NavigationIcon({ view }: { view: View }) {
  return <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={navigationPaths[view]} /></svg>;
}
function navigationLabel(view: View, locale: "en" | "zh-CN"): string {
  if (locale === "en") return view === "Fleet & Capacity" ? "Resources & systems" : view;
  const labels: Record<View, string> = { Search: "搜索", Sources: "来源", Tools: "工具", "Session Estate": "会话工作区", Today: "今天", Team: "团队", Projects: "项目", Inbox: "收件箱", Conversations: "对话", Knowledge: "知识", "Meta-CEO": "Meta-CEO 办公室", Work: "工作", Programs: "工作流", "Control Room": "控制室", "Fleet & Capacity": "资源与系统", "Mission Workspace": "任务工作区", Conversation: "当前对话", Activity: "活动", Connections: "连接", Evidence: "证据" };
  return labels[view];
}

interface BuildReceipt {
  version: string;
  source_revision: string;
  build_identity: string;
  transport: string;
  state: string;
  native_client_ref?: string | null;
}
declare global {
  interface Window {
    MastermindMissionHost?: MissionHost;
  }
}
type ProgramIndex =
  | ReturnType<typeof programsFromControlRoom>
  | { programs: []; state: "PENDING"; reason: "SOURCE_READ_PENDING" };
type WorkState =
  | { kind: "PENDING" }
  | { kind: "DOCUMENT"; document: WorkDocument }
  | { kind: "UNAVAILABLE"; reason: string };
// Only a pointer is restored; drafts, callbacks and authority are never inferred
// from durable storage. Recovery still goes through the controller's decoder.
function isRetainedOperation(value: unknown): value is OperationPointer {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const pointer = value as Record<string, unknown>;
  if (pointer.kind === "consume") {
    return Object.keys(pointer).length === 3 &&
      Object.keys(pointer).every(key => ["operationKey", "kind", "targetKey"].includes(key)) &&
      typeof pointer.operationKey === "string" && /^mmos-consume-[0-9a-f]{40}$/.test(pointer.operationKey) &&
      typeof pointer.targetKey === "string" && parseDirectConsumeTarget(pointer.targetKey) !== null;
  }
  return Object.keys(pointer).every(key => ["operationKey", "kind", "targetKey"].includes(key)) &&
    typeof pointer.operationKey === "string" && pointer.operationKey.length > 0 &&
    typeof pointer.kind === "string" && ["launch", "message", "stop"].includes(pointer.kind) &&
    (pointer.targetKey === null || typeof pointer.targetKey === "string");
}
// These closed pointers belong to the existing Fresh owner, never to generic
// command recovery. Classification is local DATA; malformed hints stay held.
function isFreshRetainedOperation(value: unknown): value is OperationPointer {
  try {
    if (!value || typeof value !== "object" || ![Object.prototype, null].includes(Object.getPrototypeOf(value))) return false;
    const fields = Object.getOwnPropertyDescriptors(value), keys = Reflect.ownKeys(fields);
    if (keys.length !== 3 || keys.some(key => !["operationKey", "kind", "targetKey"].includes(String(key))) ||
        Object.values(fields).some(field => !("value" in field))) return false;
    const kind = fields.kind.value, operationKey = fields.operationKey.value, targetKey = fields.targetKey.value;
    if (kind === "conversation_create")
      return freshConversationOriginalSelector({work_ref: targetKey, operation_key: operationKey}) !== null;
    if (kind !== "conversation_consume" && kind !== "conversation_turn") return false;
    const pattern = kind === "conversation_consume" ? /^mmos-conversation-consume-[0-9a-f]{40}$/ : /^mmos-conversation-turn-[0-9a-f]{40}$/;
    return typeof operationKey === "string" && pattern.exec(operationKey)?.[0] === operationKey && parseFreshConversationTarget(targetKey) !== null;
  } catch { return false; }
}
const SESSION_OPERATION_KEY = /^session-continue-[0-9a-f]{64}$/;
// SESSION_TARGET_REF belongs to the same closed native-session proof adapter.
// Only a session message pointer is restored from the session-exclusive
// namespace; launch pointers live in their own store and are never adopted.
function sessionStoreHold(state: OperationState): boolean {
  return (state.status === "unknown" && !state.pointer) ||
    (state.status === "idle" && ["LOCAL_UNAVAILABLE", "MALFORMED_POINTER", "STORE_WRITE_FAILED"].includes(state.reason));
}

function isRetainedSessionOperation(value: unknown): value is OperationPointer {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const pointer = value as Record<string, unknown>;
  return Object.keys(pointer).every(key => ["operationKey", "kind", "targetKey"].includes(key)) &&
    typeof pointer.operationKey === "string" && SESSION_OPERATION_KEY.test(pointer.operationKey) &&
    pointer.kind === "message" &&
    typeof pointer.targetKey === "string" && SESSION_TARGET_REF.test(pointer.targetKey);
}
/**
 * The ordinary URL parameter that carries the closed session target kind.
 * There is no new persistence owner: the parameter is the whole retention.
 */
const SESSION_TARGET_KIND_PARAM = "session_target_kind";
function readSessionTargetKind(search = window.location.search): ExecutiveSessionTargetKind {
  try {
    const raw = search.startsWith("?") ? search.slice(1) : search;
    for (const pair of raw.split("&")) {
      const at = pair.indexOf("=");
      if (at === -1) continue;
      if (decodeURIComponent(pair.slice(0, at)) !== SESSION_TARGET_KIND_PARAM) continue;
      const value = decodeURIComponent(pair.slice(at + 1));
      return EXECUTIVE_SESSION_TARGET_KINDS.includes(value as ExecutiveSessionTargetKind)
        ? (value as ExecutiveSessionTargetKind)
        : "fabric_attempt";
    }
  } catch {
    return "fabric_attempt";
  }
  return "fabric_attempt";
}
function writeSessionTargetKind(kind: ExecutiveSessionTargetKind): void {
  try {
    const url = new URL(window.location.href);
    if (kind === "fabric_attempt") url.searchParams.delete(SESSION_TARGET_KIND_PARAM);
    else url.searchParams.set(SESSION_TARGET_KIND_PARAM, kind);
    window.history.replaceState(window.history.state, "", url.toString());
  } catch {
    /* The ordinary URL parameter is best-effort; the choice still applies. */
  }
}
type ReopenedOperation = {
  binding: OrchestratorCommandBinding;
  principalScope: string;
  generation: string;
  authRevision: number;
  selectionSeq: number;
  pointer: OperationPointer | null;
  reason: "READING" | "CONVERSATION_OWNER_UNAVAILABLE" | OperationState["reason"];
};
const display = (v: unknown, f = "Not established") =>
  typeof v === "string" && v ? v : f;
const label = (v: unknown) => display(v, "UNKNOWN").replaceAll("_", " ");
const isDoc = (v: MissionDocument | UnavailableMission): v is MissionDocument =>
  !("kind" in v);
const isDocv3 = (
  v: Missionv3Document | UnavailableMission | null,
): v is Missionv3Document => !!v && !("kind" in v);
function State({ value, text }: { value: unknown; text?: string }) {
  return (
    <span className={`state state-${String(value ?? "UNKNOWN").toLowerCase()}`}>
      {text ?? label(value)}
    </span>
  );
}
function Empty({ children }: { children: React.ReactNode }) {
  return <p className="empty">{children}</p>;
}

function WorkQueue({
  state,
  rootJobId = null,
}: {
  state: WorkState;
  rootJobId?: string | null;
}) {
  if (state.kind === "PENDING")
    return (
      <section className="card">
        <div className="section-title">
          <div>
            <h2>Work</h2>
            <p className="muted">
              Company-wide lifecycle and next-action ownership from the bounded
              Executive projection.
            </p>
          </div>
          <State value="SOURCE_READ_PENDING" />
        </div>
        <Empty>Reading the bounded Work projection…</Empty>
      </section>
    );
  if (state.kind === "UNAVAILABLE")
    return (
      <section className="card source-gap">
        <div className="section-title">
          <div>
            <h2>Work</h2>
            <p className="muted">
              The fixed Work read did not return a qualified document.
            </p>
          </div>
          <State value="UNAVAILABLE" />
        </div>
        <p>Work source unavailable. This is not evidence of zero work.</p>
        <details className="reason-details">
          <summary>Technical details</summary>
          <code>{state.reason}</code>
        </details>
      </section>
    );

  const doc = state.document;
  if (doc.availability === "UNAVAILABLE")
    return (
      <section className="card source-gap">
        <div className="section-title">
          <div>
            <h2>Work</h2>
            <p className="muted">
              The canonical Work owner returned a typed refusal document.
            </p>
          </div>
          <State value="UNAVAILABLE" />
        </div>
        <p>
          Work is unavailable in this observation. This is not evidence of zero
          work.
        </p>
        <p className="muted">
          Coverage is partial by contract; no empty queue or ownership all-clear
          is inferred.
        </p>
        <details className="reason-details" open>
          <summary>Technical details</summary>
          <code>{doc.reason_codes.join(", ") || "source_unavailable"}</code>
        </details>
      </section>
    );

  return (
    <div className="today-view">
      <section className="card">
        <div className="section-title">
          <div>
            <h2>Work</h2>
            <p className="muted">
              Read-only company work projection. Lifecycle, ownership, capacity,
              effects and acceptance stay separate.
            </p>
          </div>
          <State value={doc.availability} />
        </div>
        <p className="muted">
          {rootJobId
            ? `Exact project root ${rootJobId}; other roots remain outside this project view.`
            : `${doc.coverage.count} of ${doc.coverage.total ?? "unknown"} roots observed · ${label(doc.coverage.completeness)}${doc.coverage.truncated ? " · truncated" : ""}`}
        </p>
        <p className="muted">
          Queue effect <b>{label(doc.effect_exception.value)}</b> ·{" "}
          {label(doc.effect_exception.reason)}
        </p>
      </section>
      <div className="today-grid">
        {WORK_GROUP_ORDER.map((group) => {
          const rows = rootJobId
            ? doc.groups[group].filter((row) => row.root_job_id === rootJobId)
            : doc.groups[group];
          return (
            <section className="card" key={group}>
              <div className="section-title">
                <div>
                  <h2>{label(group)}</h2>
                  <p className="muted">
                    {rows.length} roots in this qualified group
                  </p>
                </div>
              </div>
              {rows.length === 0 ? (
                <Empty>No roots were projected into this group.</Empty>
              ) : (
                <ul className="items">
                  {rows.map((row) => (
                    <li key={row.root_job_id}>
                      <div>
                        <code>{row.root_job_id}</code>
                        <State value={row.lifecycle.status} />
                      </div>
                      <span>
                        Next actor <b>{label(row.next_actor.value)}</b> ·
                        Capacity <b>{label(row.capacity.value)}</b>
                      </span>
                      <small>
                        Effect {label(row.effect.value)} · Acceptance{" "}
                        {label(row.acceptance.state)}
                      </small>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          );
        })}
      </div>
    </div>
  );
}

function ResultRefs({
  d,
  onPick,
  selectedKey,
  disabled,
}: {
  d: Missionv3Document;
  onPick: (selection: ResultSelection) => void;
  selectedKey: string | null;
  disabled: boolean;
}) {
  const index = d.result_refs;
  return (
    <section className="card">
      <div className="section-title">
        <div>
          <h2>Result navigation</h2>
          <p className="muted">
            Unvalidated navigation from the bounded Mission v3 reference index.
            Each row identifies exactly one tuple; this view never constructs a
            URL or command outside the fixed selection.
          </p>
        </div>
        <State value={index.availability} />
      </div>
      <p className="muted index-summary">
        <span>{index.refs.length} result refs</span>
        <span>{index.absent_job_ids.length} absent</span>
        <span>{index.omitted_job_ids.length} omitted</span>
      </p>
      {index.availability === "UNAVAILABLE" ? (
        <Empty>
          No result index was published for this Mission v3 selection.
        </Empty>
      ) : index.refs.length === 0 && index.absent_job_ids.length === 0 ? (
        <Empty>
          No qualifying result references were returned by the bounded
          same-snapshot index. No result history is implied.
        </Empty>
      ) : (
        <ul className="items">
          {index.refs.map((ref) => {
            const key = `${ref.job_id}|${ref.attempt_id}|${ref.result_envelope_digest}`;
            const sel: ResultSelection = {
              workRef: d.program.work_ref,
              rootJobId: ref.root_job_id,
              jobId: ref.job_id,
              attemptId: ref.attempt_id,
              resultEnvelopeDigest: ref.result_envelope_digest,
            };
            return (
              <li key={key}>
                <button
                  className={key === selectedKey ? "selected" : ""}
                  onClick={() => onPick(sel)}
                  disabled={disabled}
                >
                  <code>{ref.job_id}</code>
                  <span>{label(ref.orchestration_role)}</span>
                  <small>attempt {ref.attempt_id}</small>
                  <small>
                    digest {ref.result_envelope_digest.slice(0, 12)}…
                  </small>
                </button>
              </li>
            );
          })}
          {index.absent_job_ids.map((jobId) => (
            <li key={`absent-${jobId}`}>
              <code>{jobId}</code>
              <span>absent</span>
              <small>No result was emitted for this job in the snapshot.</small>
            </li>
          ))}
        </ul>
      )}
      {(index.omitted_job_ids.length > 0 || index.truncated) && (
        <p className="muted">
          Omitted IDs:{" "}
          {index.omitted_job_ids.length > 0
            ? index.omitted_job_ids.map(label).join(", ")
            : "none reported"}
          {index.truncated ? " · owner snapshot was truncated" : ""}
        </p>
      )}
    </section>
  );
}

type ResultState =
  | { kind: "IDLE" }
  | { kind: "PENDING"; selection: ResultSelection }
  | {
      kind: "READY";
      selection: ResultSelection;
      document: ResultEnvelopeDigestShape;
    }
  | { kind: "UNAVAILABLE"; selection: ResultSelection; reason: string };

function ResultCard({ state, locale = "en" }: { state: ResultState; locale?: "en" | "zh-CN" }) {
  const t = (en: string, zh: string) => locale === "zh-CN" ? zh : en;
  if (state.kind === "IDLE") return null;
  const title =
    state.selection.jobId + " / " + state.selection.attemptId.slice(0, 8) + "…";
  if (state.kind === "PENDING") {
    return (
      <section className="card" lang={locale}>
        <div className="section-title">
          <h2>{t("Result detail", "结果详情")}</h2>

        </div>
        <p className="muted">{t("Reading the selected result…", "正在读取所选结果…")}</p>
        <code>{title}</code>
      </section>
    );
  }
  if (state.kind === "UNAVAILABLE") {
    return (
      <section className="card" lang={locale}>
        <div className="section-title">
          <h2>{t("Result detail", "结果详情")}</h2>

        </div>
        <p className="muted">{t("This result could not be read.", "无法读取此结果。")}</p><details className="reason-details"><summary>{t("Source details", "来源详情")}</summary><code>{state.reason}</code></details>
        <code>{title}</code>
      </section>
    );
  }
  const doc = state.document;
  const result = doc.result;
  if (doc.availability === "UNAVAILABLE" || !result) {
    return (
      <section className="card" lang={locale}>
        <div className="section-title">
          <h2>{t("Result detail", "结果详情")}</h2>

        </div>
        <p className="muted">
          {t("This result is unavailable. Reading it does not change acceptance or release.", "此结果不可用。读取结果不会改变验收或发布状态。") }
        </p>
        <code>{title}</code>
        <details className="reason-details">
          <summary>{t("Source details", "来源详情")}</summary>
          <code>
            {(doc.reason_codes[0] ?? "SOURCE_UNAVAILABLE") +
              " · selection " +
              doc.selection.work_ref +
              " / " +
              doc.selection.root_job_id +
              " / " +
              doc.selection.job_id +
              " / " +
              doc.selection.attempt_id +
              " / " +
              doc.selection.result_envelope_digest}
          </code>
        </details>
      </section>
    );
  }
  const counts = result.counts.findings;
  const review = result.review;
  const verdictLabel =
    review === null
      ? "Not a review role"
      : "Review verdict: " +
        label(review.verdict) +
        " · latest revision UNPROVEN";
  return (
    <section className="card" lang={locale}>
      <div className="section-title">
        <h2>{t("Result detail", "结果详情")}</h2>

      </div>
      {doc.availability !== "AVAILABLE" ? <p className="muted">{t("Only part of this result was supplied.", "此结果只提供了部分内容。")}</p> : null}
      <p className="muted">{t("This is a recorded return. Review, acceptance and release remain separate.", "这是已保留的工作结果。审阅、验收和发布状态分别确认。")}</p>
      {result.content === null ? <Empty>{t("The source did not supply the result text. Counts and source references remain available below.", "来源未提供结果正文。下方仍保留统计与来源引用。")}</Empty> :
        <RetainedResultContent locale={locale} summary={result.content.summary} roleResult={result.content.role_result} nextActions={result.content.next_actions}/>}
      <details className="reason-details"><summary>{t("Source and review details", "来源与审阅详情")}</summary>
      <dl><dt>{t("Result source", "结果来源")}</dt><dd><State value={doc.availability}/><code>{doc.reason_codes.join(" · ")}</code></dd>
        <dt>{t("Role", "角色")}</dt>
        <dd>{label(result.role)}</dd>
        <dt>{t("Execution", "执行")}</dt>
        <dd>{label(result.execution_status)}</dd>
        <dt>{t("Acceptance", "验收")}</dt>
        <dd>
          <State value={result.acceptance} />
        </dd>
        <dt>{t("Review", "审阅")}</dt>
        <dd>{review === null ? "Not a review role" : verdictLabel}</dd>
        <dt>{t("Findings", "发现")}</dt>
        <dd>
          {counts === null
            ? "No findings tracked for this role"
            : `Total ${counts.total} · blocking ${counts.blocking} · warning ${counts.warning} · info ${counts.info}`}
        </dd>
        <dt>{t("Next actions", "下一步")}</dt>
        <dd>
          {result.counts.next_actions === 0
            ? "None reported"
            : `${result.counts.next_actions} item(s)`}
        </dd>
        <dt>{t("Envelope digest", "结果信封摘要")}</dt>
        <dd>
          <code>{result.selection.result_envelope_digest}</code>
        </dd>
        {review ? (
          <>
            <dt>{t("Reviewed job and attempt", "审阅的任务与尝试")}</dt>
            <dd>
              <code>
                {review.reviewed_job_id} · {review.reviewed_attempt_id}
              </code>
            </dd>
            <dt>{t("Reviewed role-result digest", "审阅的角色结果摘要")}</dt>
            <dd>
              <code>{review.reviewed_result_digest}</code>
            </dd>
          </>
        ) : null}
        <dt>{t("Role-result digest", "角色结果摘要")}</dt>
        <dd>
          <code>{result.role_result_digest}</code>
        </dd>
        <dt>{t("Selection", "所选记录")}</dt>
        <dd>
          <code>
            {result.selection.root_job_id +
              " · " +
              result.selection.job_id +
              " · " +
              result.selection.attempt_id}
          </code>
        </dd>
        <dt>{t("Omitted", "省略内容")}</dt>
        <dd>
          {result.omitted.length === 0
            ? "Whole content shown for this role."
            : result.omitted.map((x) => label(x)).join(" · ")}
        </dd>
      </dl>
      </details>
    </section>
  );
}
function Mission({ d }: { d: MissionDocument }) {
  return (
    <>
      <section className="hero">
        <div>
          <span className="eyebrow">PROGRAM</span>
          <h2>{d.program.title || d.program.work_ref}</h2>
          <p>
            {display(
              d.program.next_action,
              "No next action was projected by the source.",
            )}
          </p>
        </div>
        <div className="facts">
          <div>
            <small>MISSION ROOT</small>
            <code>
              {display(
                d.mission.root_job_id,
                d.mission.runtime_root_state === "CONFLICT"
                  ? "Conflict; no root selected"
                  : "Unknown; no root selected",
              )}
            </code>
          </div>
          <div>
            <small>RUNTIME ROOT STATE</small>
            <State value={d.mission.runtime_root_state} />
          </div>
          <div>
            <small>EXECUTION</small>
            <State value={d.execution.state} />
          </div>
        </div>
      </section>
      <div className="grid">
        <section className="card">
          <div className="section-title">
            <h2>Mission</h2>
            <State value={d.mission.status} />
          </div>
          <dl>
            <dt>Role</dt>
            <dd>{display(d.mission.orchestration_role)}</dd>
            <dt>Capability</dt>
            <dd>
              <State value={d.mission.capability.state} />
            </dd>
            <dt>Submission</dt>
            <dd>
              <State value={d.mission.submission_availability} />
            </dd>
          </dl>
        </section>
        <section className="card">
          <div className="section-title">
            <h2>Principal</h2>
            <State value={d.transport.dispatch_state} />
          </div>
          <dl>
            <dt>Accountable seat</dt>
            <dd>{display(d.principal.accountable_seat)}</dd>
            <dt>Current worker</dt>
            <dd>
              {display(
                d.principal.current_worker?.worker_id ??
                  d.principal.current_worker?.attempt_id,
              )}
            </dd>
            <dt>Owed turn</dt>
            <dd>
              {d.principal.owed_turn
                ? `${display(d.principal.owed_turn.seat)} · ${display(
                    d.principal.owed_turn.reason,
                  )}`
                : "Not established"}
            </dd>
            <dt>Transport</dt>
            <dd>{display(d.transport.reason)}</dd>
          </dl>
        </section>
        <section className="card">
          <div className="section-title">
            <h2>Review and acceptance</h2>
            <State value={d.acceptance.state} />
          </div>
          <dl>
            <dt>Execution</dt>
            <dd>
              <State value={d.execution.state} />
            </dd>
            <dt>Review</dt>
            <dd>
              <State value={d.review.verdict} />
            </dd>
            <dt>Transport</dt>
            <dd>
              <State value={d.transport.dispatch_state} />
            </dd>
            <dt>Acceptance</dt>
            <dd>
              <State value={d.acceptance.state} />
            </dd>
            <dt>Posture</dt>
            <dd>
              <State value={d.posture.value} />
            </dd>
            <dt>Rule</dt>
            <dd>{display(d.posture.rule)}</dd>
          </dl>
        </section>
      </div>
      <section className="card">
        <div className="section-title">
          <h2>Mission tree</h2>
          <State value={d.children.state} />
        </div>
        <p className="muted">
          {d.children.coverage === "INCOMPLETE"
            ? "Known-subset evidence; the complete tree is not established."
            : d.children.reason_codes.join(" · ") ||
              "Complete source coverage."}
        </p>
        <div className="unjoined" aria-label="Unjoined jobs">
          <b>Unjoined jobs</b>
          <span>
            {d.children.unjoined_job_count === null
              ? "Count unknown"
              : `${d.children.unjoined_job_count} reported`}
          </span>
          {d.children.unjoined_job_ids.length ? (
            <ul>
              {d.children.unjoined_job_ids.map((id) => (
                <li key={id}>
                  <code>{id}</code>
                </li>
              ))}
            </ul>
          ) : d.children.unjoined_job_count === 0 ? (
            <small>No unjoined job IDs were reported.</small>
          ) : (
            <small>No bounded unjoined identities were projected.</small>
          )}
        </div>
        {d.children.items.length ? (
          <ul className="items">
            {d.children.items.map((x, index) => (
              <li key={x.job_id ?? `unidentified-child-${index}`}>
                <code>{display(x.job_id, "Unidentified child")}</code>
                <span>{label(x.status)}</span>
                <small>
                  {display(x.orchestration_role)} · parent{" "}
                  {display(x.parent_job_id)} · attempt{" "}
                  {x.latest_attempt?.status ?? "not established"}
                </small>
              </li>
            ))}
          </ul>
        ) : (
          <Empty>
            No items are rendered. This is not evidence of zero work.
          </Empty>
        )}
      </section>
    </>
  );
}
function Activity({ d, selection, readActivity, sourceGeneration, canRead, locale = "en" }: {
  d: MissionDocument;
  selection?: {workRef: string; rootJobId: string} | null;
  readActivity?: RetainedActivityReader;
  sourceGeneration?: () => number;
  canRead?: () => boolean;
  locale?: "en" | "zh-CN";
}) {
  const exact = selection?.workRef === d.program.work_ref &&
    selection?.rootJobId === d.mission.root_job_id && d.mission.root_job_ambiguous === false;
  const t = (en: string, zh: string) => locale === "zh-CN" ? zh : en;
  const status = (value: string | null | undefined) => ({RUNNING:t("Running", "运行中"),COMPLETED:t("Completed", "已完成"),QUEUED:t("Queued", "排队中"),PENDING:t("Pending", "待处理"),FAILED:t("Failed", "失败"),CANCELLED:t("Cancelled", "已取消"),CHECKPOINTED:t("Checkpoint saved", "检查点已保存"),RATE_LIMITED:t("Rate limited", "受到速率限制"),LOST:t("Lost", "已失联"),CANCEL_REQUESTED:t("Cancellation requested", "已请求取消"),CLAIMED:t("Claimed", "已认领")}[value ?? ""] ?? t("Status not established", "状态尚未确认"));
  const role = (value: string | null | undefined) => ({plan:t("Planning", "规划"),work:t("Work", "执行工作"),review:t("Review", "审阅"),repair:t("Repair", "修复"),aggregation:t("Coordination", "协调")}[value ?? ""] ?? t("Work item", "工作项"));
  return <section className="card mm-project-activity" lang={locale}>
    <div className="section-title"><div><h2>{t("Recorded work", "工作记录")}</h2>
      <p className="muted">{t("Inspect recorded activity for an item. These records are not a live stream.", "查看工作项的已记录活动。这些记录不是实时信息流。")}</p>
    </div></div>
    {d.children.items.length ? <ul className="items activity-items">{d.children.items.map((item,index)=><li key={item.job_id ?? `unidentified-activity-${index}`}>
      <b>{role(item.orchestration_role)}</b><span>{status(item.status)}</span>
      <small><code>{display(item.job_id, t("Unidentified item", "未标识工作项"))}</code> · {t("Attempt", "尝试")}: {status(item.latest_attempt?.status)}</small>
                {exact && index < 8 && validActivitySelection({work_ref: d.program.work_ref,
                  root_job_id: d.mission.root_job_id, job_id: item.job_id, attempt_id: item.current_attempt_id}) &&
                  <RetainedActivityInspector selection={{work_ref: d.program.work_ref,
                    root_job_id: d.mission.root_job_id!, job_id: item.job_id,
                    attempt_id: item.current_attempt_id!}} read={readActivity}
                    sourceGeneration={sourceGeneration} canRead={canRead} locale={locale} />}
    </li>)}</ul> : <Empty>{t("No work records were supplied. This does not establish that there is no work.", "尚未提供工作记录，这不表示没有工作。")}</Empty>}
    <p className="muted">{d.children.coverage === "INCOMPLETE" ? t("Only part of the work is shown; this is not the full queue.", "此处只显示部分工作，并非完整队列。") : t("All child records reported for this observation are shown.", "已显示此次观测中报告的全部子任务记录。")}</p>
    <details className="reason-details"><summary>{t("Work status details", "工作状态详情")}</summary>
      <dl><dt>{t("Execution", "执行")}</dt><dd><State value={d.execution.state}/></dd>
      <dt>{t("Review", "审阅")}</dt><dd><State value={d.review.verdict}/></dd>
      <dt>{t("Transport", "传输")}</dt><dd><State value={d.transport.dispatch_state}/></dd>
      <dt>{t("Acceptance", "验收")}</dt><dd><State value={d.acceptance.state}/></dd>
      <dt>{t("Work posture", "工作状态")}</dt><dd><State value={d.posture.value}/></dd>
      <dt>{t("Child source", "子任务来源")}</dt><dd><State value={d.children.state}/></dd></dl>
    </details>
  </section>;
}

function Connections({ d }: { d: MissionDocument }) {
  const rs = useMemo(() => relationshipsForMission(d), [d]),
    [mode, setMode] = useState<"graph" | "list">("graph"),
    [selected, setSelected] = useState(rs[0]?.id ?? null),
    focus = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (selected && !rs.some((x) => x.id === selected))
      setSelected(rs[0]?.id ?? null);
  }, [rs, selected]);
  useEffect(() => {
    if (selected) focus.current?.focus();
  }, [mode, selected]);
  const button = (rel: (typeof rs)[number]) => (
    <button
      ref={rel.id === selected ? focus : undefined}
      className={rel.id === selected ? "selected" : ""}
      onClick={() => setSelected(rel.id)}
    >
      <code>{rel.from}</code>
      <span>contains</span>
      <code>{rel.to}</code>
      <small>{rel.kind}</small>
    </button>
  );
  return (
    <section className="card connections">
      <div className="section-title">
        <div>
          <h2>Connections</h2>
          <p className="muted">
            One source-derived model. It adds no graph authority.
          </p>
        </div>
        <div
          className="segmented"
          role="group"
          aria-label="Connection presentation"
        >
          <button
            onClick={() => setMode("graph")}
            aria-pressed={mode === "graph"}
          >
            Graph
          </button>
          <button
            onClick={() => setMode("list")}
            aria-pressed={mode === "list"}
          >
            List
          </button>
        </div>
      </div>
      {rs.length === 0 ? (
        <Empty>
          No joined relationships are available. Missing joins remain gaps.
        </Empty>
      ) : mode === "graph" ? (
        <div className="relation-graph" role="list">
          {rs.map((rel) => (
            <div role="listitem" key={rel.id}>
              {button(rel)}
            </div>
          ))}
        </div>
      ) : (
        <ul className="relationship-list">
          {rs.map((rel) => (
            <li key={rel.id}>{button(rel)}</li>
          ))}
        </ul>
      )}
      <p className="selection-note" aria-live="polite">
        {selected
          ? `Selected relationship: ${selected}`
          : "No relationship selected."}
      </p>
    </section>
  );
}
function Evidence({ d }: { d: MissionDocument }) {
  const refs = allEvidence(d);
  return (
    <>
      <section className="card">
        <div className="section-title">
          <h2>Evidence</h2>
          <State value={d.read_state.state} />
        </div>
        <dl>
          <dt>Projection created</dt>
          <dd>
            {d.generated_at ? (
              <time dateTime={d.generated_at}>{d.generated_at}</time>
            ) : (
              "Unavailable"
            )}
          </dd>
          <dt>Control Room source</dt>
          <dd>{display(d.source.control_room_generated_at)}</dd>
          <dt>Fabric source</dt>
          <dd>{display(d.source.fabric_view_generated_at)}</dd>
        </dl>
        <div className="generation">
          <h3>Source generations</h3>
          {Object.entries(d.source.source_generation).length ? (
            <ul>
              {Object.entries(d.source.source_generation).map(([k, v]) => (
                <li key={k}>
                  <code>{k}</code>
                  <span>{String(v)}</span>
                </li>
              ))}
            </ul>
          ) : (
            <Empty>No generation receipt was projected.</Empty>
          )}
        </div>
      </section>
      <section className="card">
        <h2>Qualified evidence references</h2>
        {refs.length ? (
          <ul className="evidence-list">
            {refs.map(({ facet, evidence }, i) => (
              <li key={`${facet}-${evidence.ref}-${i}`}>
                <div>
                  <b>{facet}</b>
                  <State value={evidence.freshness_state} />
                </div>
                <code>
                  {evidence.owner} · {evidence.ref} · {evidence.field}
                </code>
                <small>
                  Source time: {display(evidence.source_time)} · observed:{" "}
                  {display(evidence.observed_at)} · revision:{" "}
                  {display(evidence.source_revision)}
                </small>
              </li>
            ))}
          </ul>
        ) : (
          <Empty>No qualified evidence tuples were projected.</Empty>
        )}
      </section>
      <section className="card">
        <h2>Artifacts and next actions</h2>
        {d.execution.artifacts.length ? (
          <ul className="artifact-list">
            {d.execution.artifacts.map((x, i) => (
              <li key={i}>{x}</li>
            ))}
          </ul>
        ) : (
          <Empty>No allowlisted artifact reference was projected.</Empty>
        )}
        {d.execution.next_actions.length ? (
          <ul className="artifact-list">
            {d.execution.next_actions.map((x, i) => (
              <li key={i}>{x}</li>
            ))}
          </ul>
        ) : null}
      </section>
    </>
  );
}

function ProjectTabs({
  active,
  onChange,
  tablistRef,
  locale = "en",
}: {
  active: ProjectTab;
  locale?: "en" | "zh-CN";
  onChange: (tab: ProjectTab) => void;
  tablistRef?: React.Ref<HTMLDivElement>;
}) {
  return (
    <nav className="card" aria-label={locale === "zh-CN" ? "项目分区" : "Project sections"}>
      <div ref={tablistRef} className="segmented" role="tablist" aria-label={locale === "zh-CN" ? "项目工作区" : "Project workspace"}>
        {projectTabs.map((tab) => (
          <button
            key={locale === "zh-CN" ? {Conversation:"对话",Overview:"概览",Plan:"规划",Work:"工作",Evidence:"证据",Journal:"日志",More:"更多"}[tab] : tab}
            type="button"
            role="tab"
            aria-selected={active === tab}
            onClick={() => onChange(tab)}
          >
            {locale === "zh-CN" ? {Conversation:"对话",Overview:"概览",Plan:"规划",Work:"工作",Evidence:"证据",Journal:"日志",More:"更多"}[tab] : tab}
          </button>
        ))}
      </div>
    </nav>
  );
}

function ProjectMore({
  d,
  sessionPanel,
  onNavigate,
}: {
  d: MissionDocument;
  sessionPanel: React.ReactNode;
  onNavigate: (view: OperationalView) => void;
}) {
  return (
    <>
      <section className="card">
        <div className="section-title">
          <div>
            <h2>More</h2>
            <p className="muted">
              Sessions, journal, resources and systems stay views over their
              existing owners.
            </p>
          </div>
          <State value={d.read_state.state} />
        </div>
      </section>
      {sessionPanel}
      <OperationalNavigation label="Project operations" onNavigate={onNavigate} />
      <Connections d={d} />
      <section className="card source-gap">
        <div className="section-title">
          <h2>Resources &amp; systems</h2>
          <State value="NOT_PROJECTED" />
        </div>
        <p>
          Capacity and system health require their canonical owners; project
          selection does not grant access or authority.
        </p>
      </section>
    </>
  );
}
function Conversation({
  document,
  pending,
  refresh,
  selection,
  association,
  contentAvailable,
  locale = "en",
}: {
  document?: WindowDocument | null;
  pending?: boolean;
  refresh?: () => void;
  selection?: MissionSelection | null;
  association?: ObservedMissionAssociation | null;
  contentAvailable?: boolean;
  locale?: "en" | "zh-CN";
}) {
  const refreshControl = (
    <button onClick={refresh} disabled={!!pending || !contentAvailable}>
      Refresh window
    </button>
  );
  if (document)
    return (
      <section className="card">
        <div className="section-title">
          <h2>
            {association
              ? "Observed window for this Mission"
              : "Unbound current window"}
          </h2>
          <State
            value={association ? "OBSERVED_MISSION_ASSOCIATION" : "UNBOUND"}
          />
        </div>
        {association ? (
          <div className="unjoined" role="note">
            <b>Observed window for this Mission</b>
            <p>
              Job {association.job_id} · Attempt {association.attempt_id}. The
              content owner observed this Job/Attempt and the separately
              authorized Mission owner placed that same current Job/Attempt
              under this selected root. Independent owner observations. This
              display does not prove shared identity, later liveness, complete
              history, terminal acceptance, review approval, or action/result
              correspondence.
            </p>
            <p>
              Window observed at {association.window_observed_at}. Mission
              document generated at{" "}
              {association.mission_generated_at ?? "unavailable"}.
            </p>
          </div>
        ) : (
          <div className="unjoined" role="note">
            <b>NOT_LINKED_TO_SELECTED_MISSION</b>
            <p>
              {selection
                ? `No relationship is proven between this current window and ${selection.workRef} / ${selection.rootJobId}.`
                : "No relationship is proven between this current window and any Mission selection."}
            </p>
          </div>
        )}
        <p className="muted">
          {association
            ? `Coverage ${label(document.view.coverage)}. This window does not establish full history, Mission evidence, action or result correlation, review, or product acceptance.`
            : `Global current permitted turn · observed ${document.view.observed_at} · coverage ${label(document.view.coverage)}. This window does not establish full history, Mission evidence, action or result correlation, review, or product acceptance.`}
        </p>
        {document.view.items.map((item) => (
          <article key={item.id}>
            <State value={item.state} />
            {item.kind === "withheld" ? (
              <Empty>Content withheld by its owner.</Empty>
            ) : (
              <pre className="visible-text">{item.text}</pre>
            )}
          </article>
        ))}
        {document.view.items.length === 0 ? (
          <Empty>
            No visible response was returned in this observed window.
          </Empty>
        ) : null}
        {document.view.gaps.length ? (
          <p className="muted">The source reported gaps in this window.</p>
        ) : null}
        {refreshControl}
      </section>
    );
  return (
    <section className="card">
      <div className="section-title">
        <h2>Conversation</h2>
        <State value={pending ? "SOURCE_READ_PENDING" : "UNAVAILABLE"} />
      </div>
      <p className="muted">
        {window.MastermindMissionHost?.readCurrentWindow
          ? "The current permitted conversation window is unavailable."
          : "This app has no connected conversation source yet."}
      </p>
      <Empty>
        {window.MastermindMissionHost?.readCurrentWindow
          ? contentAvailable
            ? locale === "zh-CN"
              ? "对话来源暂不可用。服务或来源恢复后，请刷新。"
              : "The conversation source is unavailable. Refresh after the service or source becomes available."
            : "Sign in with permitted conversation access, then open this view again."
          : "No conversation content is shown until a connected source is installed. Existing owner and effect boundaries remain unchanged."}
      </Empty>
      <details className="reason-details">
        <summary>Technical details</summary>
        <code>CONVERSATION_TRANSPORT_UNAVAILABLE</code>
      </details>
      {refreshControl}
    </section>
  );
}

export interface AppProps {
  /** Explicit render inputs only; never inferred from auth, storage or OS preferences. */
  locale?: "en" | "zh-CN";
  theme?: "dark" | "light";
  preferencesControl?: React.ReactNode;
}
export function App({ locale = "en", theme = "dark", preferencesControl }: AppProps = {}) {
  const copy = appCopy(locale);
  const [navigationOpen, setNavigationOpen] = useState(false);
  const navigationPane = useRef<HTMLElement>(null);
  const preferencesPane = useRef<HTMLDivElement>(null);
  const [hasPreferencesNavigation, setHasPreferencesNavigation] = useState(false);
  useLayoutEffect(() => {
    setHasPreferencesNavigation(Boolean(preferencesPane.current?.querySelector("button.display-preferences__toggle")));
  }, [preferencesControl]);
  const openDisplayPreferences = () => {
    if (window.matchMedia?.("(max-width: 959px)").matches) setNavigationOpen(true);
    const open = () => {
      const toggle = preferencesPane.current?.querySelector<HTMLButtonElement>("button.display-preferences__toggle");
      if (!toggle) return;
      if (toggle.getAttribute("aria-expanded") !== "true") toggle.click();
      toggle.focus();
    };
    if (typeof window.requestAnimationFrame === "function") window.requestAnimationFrame(open);
    else queueMicrotask(open);
  };
  const navigationToggle = useRef<HTMLButtonElement>(null);
  const closeNavigation = () => { setNavigationOpen(false); navigationToggle.current?.focus(); };
  const advancedDisclosure = useRef<HTMLDetailsElement>(null);
  useEffect(() => {
    if (!navigationOpen) return;
    const drawerMedia = window.matchMedia?.("(max-width: 959px)");
    const leaveDrawerForDesktop = () => {
      if (drawerMedia?.matches) return;
      setNavigationOpen(false);
      // The mobile toggle/close controls are hidden in the desktop layout.
      document.getElementById("content")?.focus();
    };
    if (drawerMedia && !drawerMedia.matches) { leaveDrawerForDesktop(); return; }
    drawerMedia?.addEventListener("change", leaveDrawerForDesktop);
    const pane = navigationPane.current;
    pane?.querySelector<HTMLButtonElement>("button")?.focus();
    const handle = (event: KeyboardEvent) => {
      if (event.key === "Escape") { event.preventDefault(); closeNavigation(); }
      if (event.key !== "Tab" || !pane) return;
      const items = Array.from(pane.querySelectorAll<HTMLElement>("button:not(:disabled), summary, a[href], input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex=\"0\"]"));
      const visible = items.filter(element => {
        const style = window.getComputedStyle(element);
        return element.getClientRects().length > 0 && style.visibility !== "hidden" && style.display !== "none";
      });
      const first = visible[0], last = visible.at(-1);
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    };
    document.addEventListener("keydown", handle);
    return () => {
      document.removeEventListener("keydown", handle);
      drawerMedia?.removeEventListener("change", leaveDrawerForDesktop);
    };
  }, [navigationOpen]);
  const native = "__TAURI_INTERNALS__" in window,
    initialLocation = useMemo(() => directLocationInput(), []),
    initialProjectJourney = useMemo(() => readProjectJourneyLocation(window.location.href), []),
    initialFreshConversation = useMemo(() => readFreshConversationLocation(window.location.href), []),
    initial = useMemo(
      () =>
        initialLocation.hasIdentity
          ? initialLocation.selection
          : normalizeSelection(window.MastermindMissionHost?.selection),
      [initialLocation],
    ),
    [selection, setSelection] = useState<MissionSelection | null>(initial),
    [active, setActive] = useState<View>(initialFreshConversation.open || !initialFreshConversation.valid ? "Conversations" : initialProjectJourney.open || !initialProjectJourney.valid ? "Projects" : initial && new URL(window.location.href).searchParams.get("direct_native_job")===initial.rootJobId ? "Projects" : "Today"),
    [projectTab, setProjectTab] = useState<ProjectTab | null>(initial && new URL(window.location.href).searchParams.get("direct_native_job")===initial.rootJobId ? "Overview" : null),
    [index, setIndex] = useState<ProgramIndex>({
      programs: [],
      state: "PENDING",
      reason: "SOURCE_READ_PENDING",
    }),
    [programRevision, setProgramRevision] = useState(0),
    [programIndexEpoch, setProgramIndexEpoch] = useState(0),
    // Observer-only Programs read phase for the diagnostic disclosures. It
    // never gates a read and no read effect depends on it.
    [programsReadPhase, setProgramsReadPhase] = useState<DiagnosticPhase>("unknown"),
    [programsReadReason, setProgramsReadReason] = useState<DiagnosticReadReason>("UNKNOWN"),
    // Pure disclosure tick: one re-render when a Technical details disclosure
    // opens, so the observer snapshot is fresh. It starts no read.
    [, setDiagnosticTick] = useState(0),
    [catalogueProject, setCatalogueProjectState] = useState<{workRef: string; authRevision: number; epoch: number} | null>(null),
    [retainedRoot, setRetainedRoot] = useState<{
      pair: MissionSelection;
      index: ProgramIndex;
      epoch: number;
      authRevision: number;
      host: MissionHost | undefined;
      hostGeneration: string | number;
      missionWorkRef: string | null;
      candidates: string;
    } | null>(null),
    [controlRoom, setControlRoom] = useState<ControlRoomState>({
      state: "UNAVAILABLE", reason: "NOT_READ", ownerRevision: -1,
    }),
    [controlRoomRevision, setControlRoomRevision] = useState(0),
    controlRoomAuthEpoch = useRef(0),
    [workState, setWorkState] = useState<WorkState>({ kind: "PENDING" }),
    [workRevision, setWorkRevision] = useState(0),
    [missionReadRevision, setMissionReadRevision] = useState(0),
    [mission, setMission] = useState<MissionDocument | UnavailableMission>(() =>
      unavailableMission(
        initial,
        initial ? "SOURCE_NOT_READ" : "EXACT_SELECTION_REQUIRED",
      ),
    ),
    [notice, setNotice] = useState("A qualified source has not been read."),
    [build, setBuild] = useState<BuildReceipt | null>(null),
    [authState, setAuthState] = useState<AuthState | null>(
      () => window.MastermindMissionHost?.auth?.getState() ?? null,
    ),
    [authRevision, setAuthRevision] = useState(0),
    [windowDocument, setWindowDocument] = useState<WindowDocument | null>(null),
    [windowPending, setWindowPending] = useState(false),
    [windowRevision, setWindowRevision] = useState(0),
    [association, setAssociation] = useState<ObservedMissionAssociation | null>(
      null,
    ),
    invalidation = useRef(0),
    pairAbort = useRef<AbortController | null>(null),
    selectionSeq = useRef(0),
    commandSlot = useRef<{
      controller: OperationController;
      /** Binding object this controller was created from; identity matters. */
      binding: OrchestratorCommandBinding;
      principalScope: string;
      generation: string;
    } | null>(null),
    activationOriginal = useRef<{observation: OriginalOperationObservation;
      binding: OrchestratorCommandBinding; frame: () => {principalScope: string; generation: string} | null;
      selectionSeq: number} | null>(null),
    [activationWorkReturn, setActivationWorkReturn] = useState<string | null>(null),
    pendingCommand = useRef<{
      generation: string;
      principalScope: string;
      /** Binding this pending was dispatched under; identity matters. */
      binding: OrchestratorCommandBinding;
      kind: OperationKind;
      selectionSeq: number;
      sessionKey: string | null;
      presentationSeq: number;
      complete: (
        outcome: { status: "accepted" } | { status: "refused" },
      ) => void;
    } | null>(null),
    [viewTick, setViewTick] = useState(0),
    [commandStatus, setCommandStatus] = useState<OperationState | null>(null),
    [commandRefusal, setCommandRefusal] = useState<{
      binding: OrchestratorCommandBinding;
      principalScope: string;
      generation: string;
      kind: OperationKind;
      selectionSeq: number;
      sessionKey: string | null;
      presentationSeq: number;
      reason: string;
    } | null>(null),
    [heldKind, setHeldKind] = useState<OperationKind | null>(null),
    [launchDraftDismissed, setLaunchDraftDismissed] = useState(false),
    // The Office → existing launch owner handoff. It holds the exact frozen
    // preview and the owner identity it was opened under, so the same
    // captured context can be revalidated before a submission. It never
    // carries a sessionRef and never owns a command.
    [launchHandoff, setLaunchHandoff] = useState<({
      workstreamRef: string;
      binding: OrchestratorCommandBinding;
      principalScope: string;
      generation: string;
    } & (
      | { kind: "office"; preview: DirectionPreview }
      | { kind: "project"; draft: ProjectLaunchDraft; inspection: ProjectPlanLaunchInspection; executionPreview: ProjectExecutionPreview; continuationCurrent?: () => boolean }
    )) | null>(null),
    // True only while a Check-status recover() is actually in flight. A
    // static checking/PENDING_POINTER hold (a persisted pointer with no
    // recovery promise) is NOT busy — its recovery control stays usable.
    [recoverInFlight, setRecoverInFlight] = useState(false),
    recoveryFlight = useRef(0),
    [reopenedOperation, setReopenedOperation] = useState<ReopenedOperation | null>(null),
    previousAuth = useRef<string | null>(
      authState ? JSON.stringify(authState) : null,
    ),
    previousAuthState = useRef<AuthState | null>(authState),
    passiveExpiryHold = useRef(false),
    // App already owns presentation state. These text-only snapshots survive
    // an unmount during passive expiry, never a new principal or sign-out.
    [retainedComposerDrafts, setRetainedComposerDrafts] = useState({ launch: "", session: "", launchWorkstream: "", launchDetails: null as LaunchDetailsDraft | null }),
    retainedComposerRef = useRef(retainedComposerDrafts),
    retainedComposerScope = useRef<string | null>(null),
    previousLiveComposerScope = useRef<string | null>(null),
    hasUnsentUserText = useRef(false),
    authRevisionRef = useRef(authRevision),
    previousHostGeneration = useRef(
      window.MastermindMissionHost?.invalidationGeneration?.() ?? 0,
    ),
    bumpInvalidation = () => {
      invalidation.current += 1;
      pairAbort.current?.abort();
    },
    [missionV3, setMissionV3] = useState<
      Missionv3Document | UnavailableMission | null
    >(null),
    [resultState, setResultState] = useState<ResultState>({ kind: "IDLE" }),
    resultRequest = useRef(0),
    compoundTicket = useRef(0),
    compoundRetention = useRef<{
      mission: Missionv3Document;
      selection: MissionSelection | null;
      authRevision: number;
    } | null>(null),
    missionRequest = useRef(0),
    programRequest = useRef(0),
    // One explicit navigation gesture waits for the incumbent Programs read.
    // It carries no command, grant, draft payload or persistent operation.
    createdProjectOpen = useRef<{
      workRef: string; createRequestId: string; host: MissionHost;
      authRevision: number; selectionSequence: number; catalogueSequence: number;
      afterEpoch: number; current: () => boolean; complete: (opened: boolean) => void;
    } | null>(null),
    programSelection = useRef(selection),
    workRequest = useRef(0),
    officeWorkFrame = useRef<ReturnType<typeof captureOfficeReadFrame> | null>(null),
    missionSelectionState =
      native &&
      !window.MastermindMissionHost?.readPrograms &&
      !window.MastermindMissionHost?.readProgramsObservation
        ? "NATIVE"
        : selection?.workRef !== programSelection.current?.workRef ||
            selection?.rootJobId !== programSelection.current?.rootJobId
          ? "PENDING"
          : index.state,
    selectionRefused =
      index.state === "AVAILABLE" &&
      !!selection &&
      !index.programs.some(
        (program) =>
          program.workRef === selection.workRef &&
          program.rootState === "RESOLVED" &&
          program.rootJobId === selection.rootJobId,
      );
  // Track the actual project-selection event, including A→B→A before render.
  const cataloguePresentationSequence = useRef(0);
  const setCatalogueProject = (next: typeof catalogueProject) => {
    cataloguePresentationSequence.current += 1;
    setCatalogueProjectState(next);
  };
  // Auto-open the Advanced disclosure only while an actual advanced route is
  // active. This never navigates and never closes the disclosure itself; the
  // incumbent summary click keeps ownership of manual toggling.
  const advancedRoute = advancedNavigation.includes(active);
  useEffect(() => {
    if (advancedRoute && advancedDisclosure.current && !advancedDisclosure.current.open)
      advancedDisclosure.current.open = true;
  }, [active, advancedRoute]);
  const controlRoomSurfaceControls = useControlRoomSurfaceControls({
    selection, selectionSeq, authEpoch: controlRoomAuthEpoch, authRevision,
    active: active === "Control Room" || active === "Session Estate",
  });
  const observedConversation = useObservedConversation(
    authRevision,
    selection,
    authState?.content,
  );
  authRevisionRef.current = authRevision;
  const projectJourney = useProjectJourneyState({host: window.MastermindMissionHost ?? null,
    authRevision, currentAuthRevision: () => authRevisionRef.current});
  const nativeGoal = useNativeProjectGoalRecovery({native,
    owner: window.MastermindMissionHost?.nativeDraftRecovery,
    journey: projectJourney, authGeneration: authRevision});
  const nativeGoalRef = useRef(nativeGoal);
  nativeGoalRef.current = nativeGoal;
  const projectJourneyRef = useRef(projectJourney);
  projectJourneyRef.current = projectJourney;
  const openProjectJourney = () => {
    if (!projectJourney.open()) return;
    setCatalogueProject(null);setProjectTab(null);setActive("Projects");
  };
  const catalogueListOwner = useRef<ConversationListOwnerCapture | null>(null);
  const windowListOwner = useRef<ConversationListOwnerCapture | null>(null);
  const captureListReadOwner = (host: MissionHost | undefined) => captureConversationListOwner({
    host, authGeneration: authRevision, selectionSequence: selectionSeq.current,
    currentHost: () => window.MastermindMissionHost,
    currentAuthGeneration: () => authRevisionRef.current,
    currentSelectionSequence: () => selectionSeq.current,
  });
  const conversationNavigation = useConversationListNavigation({host: window.MastermindMissionHost,
    authGeneration: authRevision,
    hostGeneration: (() => { try { return window.MastermindMissionHost?.invalidationGeneration?.() ?? null; } catch { return null; } })()});
  const showCurrentConversation = () => {
    freshDraftRef.current.hide();
    conversationNavigation.showCurrentDetail();
    setActive("Conversations");
  };
  retainedComposerRef.current = retainedComposerDrafts;
  // The currently authenticated command scope is checked below, after the
  // qualified host identity has been read. Off-view Office text is inspected
  // independently of whether its component is mounted.
  const updateRetainedComposer = <K extends keyof typeof retainedComposerDrafts>(
    kind: K, text: (typeof retainedComposerDrafts)[K],
  ) => {
    const next = { ...retainedComposerRef.current, [kind]: text };
    retainedComposerRef.current = next;
    setRetainedComposerDrafts(next);
  };
  // Separately mounted session capability: never the launch route, never
  // multiplexed through whichever screen happens to be current.
  const sessionBinding = completeExecutiveSessionBinding(
    window.MastermindMissionHost?.sessionCommandBinding,
  );
  const sessionControl = window.MastermindMissionHost?.session ?? null;
  const sessionSlot = useRef<{
    controller: OperationController;
    binding: MountedExecutiveSessionBinding;
    principalScope: string;
    generation: string;
  } | null>(null);
  const sessionPending = useRef<{
    binding: MountedExecutiveSessionBinding;
    principalScope: string;
    generation: string;
    selectionSeq: number;
    complete: (
      outcome: { status: "accepted" } | { status: "refused" },
    ) => void;
  } | null>(null);
  const [sessionStatus, setSessionStatus] = useState<OperationState | null>(null);
  // The explicit session target kind. It is an ordinary URL parameter and an
  // ordinary local choice; it is never inferred from a title, a provider or a
  // capability advertisement.
  const [sessionTargetKind, setSessionTargetKind] = useState<ExecutiveSessionTargetKind>(
    () => readSessionTargetKind(),
  );
  // Ephemeral presentation state for one validated native public result. It
  // is fenced by the existing owner, auth and selection identity and is never
  // a durable answer, a pointer or a consumption record.
  const [sessionNative, setSessionNative] = useState<{
    binding: MountedExecutiveSessionBinding;
    principalScope: string;
    generation: string;
    selectionSeq: number;
    targetKind: ExecutiveSessionTargetKind;
    result: HermesNativePublicResult;
  } | null>(null);
  // The session selection the host is asked to qualify. The closed target
  // kind travels with it; a kind change is a different selection.
  const sessionSelection = useMemo(
    () => (selection
      ? {
        workRef: selection.workRef,
        rootJobId: selection.rootJobId,
        targetKind: sessionTargetKind,
      }
      : null),
    [selection, sessionTargetKind],
  );
  const [sessionRefusal, setSessionRefusal] = useState<{
    binding: MountedExecutiveSessionBinding;
    principalScope: string;
    generation: string;
    reason: string;
  } | null>(null);
  const [sessionPointer, setSessionPointer] = useState<OperationPointer | null>(null);
  const [sessionReading, setSessionReading] = useState(true);
  const [sessionPointerError, setSessionPointerError] = useState(false);
  const [sessionRecovering, setSessionRecovering] = useState(false);
  const [sessionTick, setSessionTick] = useState(0);
  void sessionTick;
  const sessionRecoveryFlight = useRef(0);
  // Initial qualification belongs to the committed mount. Subsequent
  // selection transitions still invalidate synchronously at their owners.
  const sessionMounted = useRef<MountedExecutiveSessionBinding | null>(null);
  const resultContext = useMemo(
    () => ({ selection, authRevision, missionV3 }),
    [selection, authRevision, missionV3],
  );
  const commandBinding = completeOrchestratorCommandBinding(
    window.MastermindMissionHost?.commandBinding,
  );
  const commandView = commandBinding ? readCommandView(commandBinding) : null;
  void viewTick;
  const signedIn = authState?.status === "signed_in";
  const ownerContext =
    signedIn && commandBinding ? readOwnerContext(commandBinding.port) : null;
  // One Executive owner seam, stable across locale and ordinary renders. Its
  // captured methods and actual host/auth epoch are re-proved on every call;
  // a new render never grants old cached Workspace observations currency.
  const freshHost = window.MastermindMissionHost;
  const freshHostGeneration = (() => {try {return freshHost?.invalidationGeneration?.() ?? null;} catch {return null;}})();
  const freshAuthRevision = useMemo(() => () => authRevisionRef.current, []);
  // The incumbent ledger belongs to this Host/binding issuance. Ordinary
  // rerenders, Back, or auth refresh cannot bless an unannounced store swap.
  // This is identity only: Workspace READ does not acquire an Executive grant.
  const projectJourneyStoreOwner = useMemo(() => {
    const host=freshHost,binding=commandBinding,store=binding?.store;
    if(!host||!binding||!store)return null;
    const read=store.read,reserve=store.reserve,clear=store.clearIfEqual;
    return {store,current:()=>window.MastermindMissionHost===host&&host.commandBinding===binding&&
      binding.store===store&&store.read===read&&store.reserve===reserve&&store.clearIfEqual===clear};
  },[freshHost,commandBinding]);

  const freshExecutiveOwner = useMemo(() => {
    const host = freshHost, revision = authRevision, generation = freshHostGeneration;
    const binding = commandBinding, auth = host?.auth, getState = auth?.getState;
    const context = binding?.port.context, source = host?.invalidationGeneration;
    return () => {
      try {
        if (!host || !binding || !auth || !getState || !context || generation === null ||
            window.MastermindMissionHost !== host || authRevisionRef.current !== revision ||
            host.auth !== auth || auth.getState !== getState || host.invalidationGeneration !== source ||
            source?.call(host) !== generation || host.commandBinding !== binding ||
            binding.port.context !== context || getState.call(auth).status !== "signed_in") return null;
        return readOwnerContext(binding.port);
      } catch {return null;}
    };
  }, [freshHost, freshHostGeneration, authRevision, commandBinding,
    ownerContext?.principalScope, ownerContext?.generation]);
  const freshDraft = useFreshConversationDraftState({host: freshHost ?? null, authRevision,
    currentAuthRevision: freshAuthRevision, getExecutiveOwner: freshExecutiveOwner});
  const freshTurnDraft = useFreshConversationTurnDraftState({host: freshHost ?? null, authRevision,
    currentAuthRevision: freshAuthRevision, getExecutiveOwner: freshExecutiveOwner});
  const freshTurnDraftRef = useRef(freshTurnDraft);
  freshTurnDraftRef.current = freshTurnDraft;
  const freshDraftRef = useRef(freshDraft);
  freshDraftRef.current = freshDraft;
  const freshOriginalHeld = useRef(false);
  const refreshFreshPendingHint = useRef<(() => Promise<boolean>) | null>(null);
  const onFreshOriginalSettled = useMemo(() => () => {
    void refreshFreshPendingHint.current?.().catch(() => {});
  }, []);

  const freshBinding = useMemo(() => {
    const host = freshHost, transport = host?.freshConversation, request = transport?.request;
    if (!host || !transport || !request || !commandBinding?.store) return null;
    const current = () => !!freshExecutiveOwner() && host.freshConversation === transport && transport.request === request;
    const send = (operation: "preview" | "create" | "status" | "read", arguments_: unknown, signal: AbortSignal) => {
      if (!current()) return Promise.reject(new Error("FRESH_CONVERSATION_UNAVAILABLE"));
      return request.call(transport, operation, arguments_, signal);
    };
    return createFreshConversationBinding({owner: () => current() ? freshExecutiveOwner() : null,
      canPreviewCreate: () => current() && host.auth?.getState().acquisition === true,
      store: commandBinding.store,
      transport: {preview: (args, signal) => send("preview", args, signal),
        create: (args, signal) => send("create", args, signal),
        status: (args, signal) => send("status", args, signal),
        read: (args, signal) => send("read", args, signal)}});
  }, [freshHost, freshExecutiveOwner, commandBinding?.store, freshDraft.navigationEpoch]);
  const freshReferenceReadFrame = useMemo(() => ({}), [freshHost, freshExecutiveOwner]);
  const freshReferenceRead = useRef<{frame: object; read: FreshConversationOriginalRead;
    owner: NonNullable<ReturnType<typeof freshExecutiveOwner>>} | null>(null);
  const reportFreshReferenceRead = useMemo(() => {
    const frame = freshReferenceReadFrame;
    return (read: FreshConversationOriginalRead | null) => {
      const owner = freshExecutiveOwner();
      if (owner && read?.current() === true)
        freshReferenceRead.current = {frame, read, owner: {...owner}};
      else if (freshReferenceRead.current?.frame === frame) freshReferenceRead.current = null;
    };
  }, [freshReferenceReadFrame, freshExecutiveOwner]);
  const attendedReadSequence = useRef(0);
  const freshAttendedBinding = useMemo(() => {
    const host = freshHost, transport = host?.freshConversation, request = transport?.request;
    if (!host || !transport || !request || !freshBinding || !commandBinding?.store) return null;
    const store = commandBinding.store;
    const current = () => !!freshExecutiveOwner() && window.MastermindMissionHost === host &&
      host.commandBinding === commandBinding && commandBinding.store === store &&
      host.freshConversation === transport && transport.request === request;
    const send = (operation: "consume" | "consume_status" | "turn_preview" | "turn" | "turn_status" | "turn_read",
      args: unknown, signal: AbortSignal) => current()
        ? request.call(transport, operation, args, signal)
        : Promise.reject(new Error("FRESH_CONVERSATION_UNAVAILABLE"));
    return createFreshConversationAttendedBinding({owner: () => current() ? freshExecutiveOwner() : null,
      canModify: () => current() && host.auth?.getState().acquisition === true,
      store,
      transport: {consume: (args, signal) => send("consume", args, signal),
        consumeStatus: (args, signal) => send("consume_status", args, signal),
        turnPreview: (args, signal) => send("turn_preview", args, signal),
        turn: (args, signal) => send("turn", args, signal),
        turnStatus: (args, signal) => send("turn_status", args, signal),
        turnRead: (args, signal) => send("turn_read", args, signal)},
      readInitial: async (value, signal): Promise<FreshConversationOriginalRead | null> => {
        const selected = freshConversationOriginalSelector(value), owner = freshExecutiveOwner();
        const sequence = ++attendedReadSequence.current;
        const live = () => current() && sequence === attendedReadSequence.current &&
          sameConversationOwner(owner, freshExecutiveOwner());
        if (!selected || !owner || !live() || signal.aborted) return null;
        if ("operation_key" in selected) {
          const raw = await freshBinding.readOriginal(selected, signal);
          if (!live() || signal.aborted) return null;
          const decoded = decodeFreshConversationResult(raw, "read", selected);
          const data = decoded?.ok ? decoded.data : null, locator = data?.locator;
          if (!data?.result || !locator?.job_id || !locator.attempt_id) return null;
          return {selection: selected, result: data.result, locator,
            current: live};
        }
        // Reuse the actual still-current issued reference body, never a hint.
        // A hidden owner.readFresh would retire the UI's current witness. The
        // independent status/preflight endpoint reauthorizes every request.
        const issued = freshReferenceRead.current;
        if (!issued || issued.frame !== freshReferenceReadFrame || !sameConversationOwner(issued.owner, owner) ||
            freshConversationTarget(issued.read.selection) !== freshConversationTarget(selected) ||
            issued.read.current() !== true) return null;
        return {selection: selected, result: issued.read.result, locator: issued.read.locator,
          current: () => live() && freshReferenceRead.current === issued && issued.read.current() === true};
      }});
  }, [freshHost, freshExecutiveOwner, freshBinding, commandBinding?.store, freshReferenceReadFrame]);
  const freshAttendedRef = useRef(freshAttendedBinding);
  freshAttendedRef.current = freshAttendedBinding;
  const freshAttendedViewHeld = useRef({binding: freshAttendedBinding, held: false});
  const reportFreshAttendedOriginal = useMemo(() => {
    const binding = freshAttendedBinding;
    return (held: boolean) => {
      if (freshAttendedRef.current === binding) freshAttendedViewHeld.current = {binding, held};
    };
  }, [freshAttendedBinding]);
  const hasFreshAttendedOriginal = useMemo(() => () => {
    const binding = freshAttendedRef.current;
    if (!binding) return false;
    const state = binding.controller.getState();
    return !!state.pointer ||
      freshAttendedViewHeld.current.binding === binding && freshAttendedViewHeld.current.held;
  }, []);
  const initialFreshRestored = useRef(false);
  useEffect(() => {
    // Initial URL is lookup DATA only. Delay its owner association until the
    // genuine Executive context arrives; this performs no source request.
    if (!initialFreshRestored.current && (initialFreshConversation.open || !initialFreshConversation.valid) && freshExecutiveOwner()) {
      initialFreshRestored.current = true;
      freshDraftRef.current.restoreLocation();
    }
  }, [freshExecutiveOwner, initialFreshConversation]);
  const liveComposerScope = ownerContext ? JSON.stringify([
    ownerContext.principalScope, ownerContext.generation,
    selection?.workRef, selection?.rootJobId, authRevision,
  ]) : null;
  // The App-level text snapshots are usable only by their originating
  // selection/owner epoch, even when a mounted leaf is later replaced.
  const presentedComposerDrafts = liveComposerScope &&
    retainedComposerScope.current === liveComposerScope
      ? retainedComposerDrafts : { launch: "", session: "", launchWorkstream: "", launchDetails: null };
  useEffect(() => {
    if (!signedIn || !liveComposerScope) return;
    if (previousLiveComposerScope.current !== null &&
        previousLiveComposerScope.current !== liveComposerScope) {
      const blank = { launch: "", session: "", launchWorkstream: "", launchDetails: null };
      retainedComposerRef.current = blank;
      retainedComposerScope.current = null;
      setRetainedComposerDrafts(blank);
    }
    previousLiveComposerScope.current = liveComposerScope;
  }, [signedIn, liveComposerScope]);
  // The session owner context and host-projected target stay fenced on the
  // current resource owner; the binding itself is read once per render above.
  const sessionExecutiveOwner=useMemo(()=>createSessionExecutiveOwnerGetter({host:freshHost??null,native,
    authRevision,currentAuthRevision:freshAuthRevision}),[freshHost,freshHostGeneration,native,authRevision,sessionBinding,sessionBinding?.port.context]);
  const sessionOwner = native?sessionExecutiveOwner():sessionBinding&&signedIn?readSessionOwnerContext(sessionBinding):null;
  const sessionTargetKey = sessionOwner && sessionBinding
    ? sessionBinding.port.currentTargetRef()
    : null;
  // Read-only exact-session association from the existing Executive owner.
  // Unknown/legacy/DSH/Grok native sessions stay UNBOUND, not guessed.
  const officeSession = qualifyExecutiveOfficeSession(
    native?!!sessionOwner:signedIn, selection, sessionBinding,
  );
  const office = useOfficeProjection(authRevision, selection, officeSession);
  const byokRoles = useByokRoleObservation({
    active: active === "Meta-CEO",
    acquisition: signedIn && authState?.acquisition === true,
    authRevision,
  });
  // The Office draft is part of the unsent-text signal. It is read after the
  // session-qualified projection exists, never before.
  hasUnsentUserText.current = Boolean(freshDraft.hasUnsentDraft() || freshTurnDraft.hasUnsentDraft() || hasFreshAttendedOriginal() || projectJourney.hasUnsentDraft() || office.draft.text ||
    observedConversation.hasUnsentDraft() ||
    (signedIn ? presentedComposerDrafts.launch || presentedComposerDrafts.launchDetails || presentedComposerDrafts.session
      : retainedComposerDrafts.launch || retainedComposerDrafts.launchDetails || retainedComposerDrafts.session));
  const projectConversationActive = active === "Projects" && projectTab === "Conversation" && !catalogueProject &&
    missionSelectionState === "AVAILABLE" && office.projection.programs.source.state === "CURRENT" && !!selection &&
    index.programs.filter(card => card.workRef === selection.workRef).length === 1 &&
    index.programs.some(card => card.workRef === selection.workRef && card.rootState === "RESOLVED" &&
      card.rootJobId === selection.rootJobId && card.rootCandidates.length === 1 &&
      card.rootCandidates[0] === selection.rootJobId);
  const officeSessionPresentation=active==='Meta-CEO'&&officeSession.sessionRef!==null&&
    officeSession.sessionRef===sessionTargetKey&&office.projection.mission.source.state==='CURRENT';
  const nativeSessionPresentation=native&&!signedIn&&!!sessionOwner&&conversationNavigation.view==='detail';
  const answerView = useQualifiedOriginalAnswer();
  // React may abandon an interrupted render. Only the committed layout
  // publishes a current identity to the private reply acceptance fence.
  useLayoutEffect(() => {
    answerView.setCurrent(sessionBinding && sessionOwner && (native||signedIn) ? {
      binding: sessionBinding,
      principalScope: sessionOwner.principalScope,
      generation: sessionOwner.generation,
      selectionSeq: selectionSeq.current,
      authRevision,
      active: active === "Conversations" || projectConversationActive || officeSessionPresentation || nativeSessionPresentation,
    } : null);
  }, [active, projectConversationActive,officeSessionPresentation,nativeSessionPresentation, signedIn, sessionBinding, sessionOwner?.principalScope,
    sessionOwner?.generation, authRevision, selection?.workRef, selection?.rootJobId]);
  const ownsSession = (binding: MountedExecutiveSessionBinding, ctx: { principalScope: string; generation: string }, sequence: number) => {
    const liveBinding = completeExecutiveSessionBinding(window.MastermindMissionHost?.sessionCommandBinding);
    const liveContext = liveBinding ? readSessionOwnerContext(liveBinding) : null;
    return liveBinding === binding && selectionSeq.current === sequence &&
      (native?!!sessionExecutiveOwner():window.MastermindMissionHost?.auth?.getState().status === "signed_in") &&
      liveContext?.principalScope === ctx.principalScope && liveContext.generation === ctx.generation;
  };
  const makeSessionController = (
    binding: MountedExecutiveSessionBinding,
    ctx: { principalScope: string; generation: string },
    sequence: number,
  ): OperationController => {
    const identity = { binding, principalScope: ctx.principalScope, generation: ctx.generation,
      selectionSeq: sequence, authRevision };
    // The real mounted host supplies the existing native qualified reader.
    // An older unqualified fixture is fail-dark: it cannot clear an original
    // hint by promoting a receipt without a validated answer.
    // The validated native public result is captured as ephemeral presentation
    // state under the existing owner, auth and selection fences. It is never
    // a durable answer, a pointer or a consumption record.
    const captureNative = (result: HermesNativePublicResult | null) => {
      if (!result || !ownsSession(binding, ctx, sequence) ||
          !answerView.isCurrent(identity)) return;
      // A late phase belongs only to the controller that requested it.
      // Replacing the live host must not retag an old result to its new owner.
      setSessionNative({
        binding, principalScope: ctx.principalScope,
        generation: ctx.generation, selectionSeq: sequence,
        targetKind: sessionTargetKind, result,
      });
    };
    const wrapper = createAwaitingAnswerPort<QualifiedSessionAnswerValue>({
      // The same single SEND. The qualified entry only adds the validated
      // native public result of that one send; it never sends twice.
      port: {
        context: () => binding.port.context(),
        prepare: (intent) => binding.port.prepare(intent),
        submit: async (pointer, intent, signal) => {
          const qualified = binding.port.submitQualified;
          if (!qualified) return binding.port.submit(pointer, intent, signal);
          const dispatch = await qualified(pointer, intent, signal);
          captureNative(dispatch.nativeResult);
          return dispatch.receipt;
        },
        readOperation: (pointer, signal) => binding.port.readOperation(pointer, signal),
      },
      readAnswer: async (pointer, signal) => {
        const read = typeof binding.port.readQualifiedAnswer === "function"
          ? await binding.port.readQualifiedAnswer(pointer, signal)
          : {
            receipt: {
              ...pointer, disposition: "unknown" as const, reason: "UNKNOWN_RECEIPT",
            },
            answer: null,
            nativeResult: null,
          };
        captureNative(read.nativeResult ?? null);
        return read;
      },
      isCurrent: () => ownsSession(binding, ctx, sequence) && answerView.isCurrent(identity),
      onAdmission: () => { if (ownsSession(binding, ctx, sequence)) answerView.invalidate(); },
      onAnswer: (pointer, answer) => answerView.stage(identity, pointer, answer),
    });
    return new OperationController(wrapper, binding.store);
  };
  // An explicit kind change re-qualifies the host before any capability
  // evidence is used.  The kind is never inferred from a title, a provider
  // or a capability advertisement, and it may not change underneath an
  // unresolved original operation.
  const changeSessionTargetKind = (kind: ExecutiveSessionTargetKind) => {
    if (!EXECUTIVE_SESSION_TARGET_KINDS.includes(kind)) return;
    if (kind === sessionTargetKind) return;
    if (sessionPending.current !== null || sessionPointer !== null ||
        sessionPointerError || sessionRecovering) return;
    writeSessionTargetKind(kind);
    setSessionTargetKind(kind);
    invalidateSessionPresentation();
    void sessionControl?.refresh(
      selection
        ? { workRef: selection.workRef, rootJobId: selection.rootJobId, targetKind: kind }
        : null,
    );
  };
  const invalidateSessionPresentation = () => {
    answerView.invalidate();
    sessionSlot.current?.controller.invalidate();
    sessionSlot.current = null;
    const held = sessionPending.current;
    sessionPending.current = null;
    held?.complete({ status: "refused" });
    sessionRecoveryFlight.current++;
    setSessionStatus(null); setSessionPointer(null); setSessionRefusal(null);
    setSessionPointerError(false); setSessionReading(true); setSessionRecovering(false);
    // The native phase is presentation state of one qualified result; a
    // route, selection, auth or kind transition withdraws it.
    setSessionNative(null);
  };
  const commandReady = !!commandBinding && signedIn && !!ownerContext;
  const commandSelectionRevision = selectionSeq.current;
  const currentReopened = reopenedOperation && commandReady &&
    reopenedOperation.binding === commandBinding &&
    reopenedOperation.principalScope === ownerContext?.principalScope &&
    reopenedOperation.generation === ownerContext?.generation &&
    reopenedOperation.authRevision === authRevision &&
    reopenedOperation.selectionSeq === selectionSeq.current
      ? reopenedOperation : null;
  const canLaunch =
    commandReady &&
    !!commandView &&
    commandView.projects.length > 0 &&
    commandView.profiles.length > 0;
  const sessionExact =
    commandReady &&
    sessionMatchesSelection(commandView?.session ?? null, selection);
  const presentationKey = JSON.stringify([ownerContext?.principalScope,
    ownerContext?.generation, commandView?.session?.sessionKey,
    selectionSeq.current, authRevision]);
  const commandPresentation = useRef({ binding: commandBinding, key: presentationKey, seq: 0 });
  if (commandPresentation.current.binding !== commandBinding ||
      commandPresentation.current.key !== presentationKey) {
    commandPresentation.current = {
      binding: commandBinding, key: presentationKey,
      seq: commandPresentation.current.seq + 1,
    };
  }
  // A terminal receipt clears its pointer and held kind. Keep only its safe
  // local reason with the original presentation identity; never attribute it
  // to a new session, owner epoch, binding, selection, or command kind.
  const currentRefusal = commandRefusal &&
    signedIn && commandRefusal.binding === commandBinding &&
    commandRefusal.principalScope === ownerContext?.principalScope &&
    commandRefusal.generation === ownerContext?.generation &&
    commandRefusal.selectionSeq === selectionSeq.current &&
    commandRefusal.presentationSeq === commandPresentation.current.seq &&
    (commandRefusal.kind === "launch" ||
      (sessionExact && commandRefusal.sessionKey === commandView?.session?.sessionKey))
    ? commandRefusal : null;
  // A retained command pointer is an effect-reconciliation obligation.
  // Automatic OAuth navigation must not tear down an unresolved UI owner.
  useEffect(() => registerUnsavedNavigationHold(() =>
    freshDraftRef.current.hasUnsentDraft() || freshTurnDraftRef.current.hasUnsentDraft() || hasFreshAttendedOriginal() || freshOriginalHeld.current ||
    projectJourney.hasUnsentDraft() || !!currentReopened || pendingCommand.current !== null || heldKind !== null || recoverInFlight ||
    (passiveExpiryHold.current && hasUnsentUserText.current)
  ), [heldKind, recoverInFlight, currentReopened]);

  useEffect(() => {
    setCommandRefusal(null);
  }, [commandBinding, ownerContext?.principalScope, ownerContext?.generation,
    commandView?.session?.sessionKey, selection?.workRef, selection?.rootJobId]);
  useEffect(() => {
    if (!commandBinding) return;
    return subscribeCommandView(commandBinding, () =>
      setViewTick((n) => n + 1),
    );
  }, [commandBinding]);
  useEffect(() => {
    if (!sessionBinding) return;
    return subscribeCommandView(sessionBinding, () => {
      const cur = sessionSlot.current;
      const ctx = readSessionOwnerContext(sessionBinding);
      if (cur && (cur.binding !== sessionBinding || !ctx ||
          cur.principalScope !== ctx.principalScope || cur.generation !== ctx.generation)) {
        invalidateSessionPresentation();
      }
      setSessionTick((n) => n + 1);
    });
  }, [sessionBinding]);
  useEffect(() => {
    if (!sessionBinding || !sessionControl || sessionMounted.current === sessionBinding) return;
    sessionMounted.current = sessionBinding;
    sessionControl.setStopCondition(() => undefined);
    void sessionControl.refresh(sessionSelection);
  }, [sessionBinding, sessionControl]);
  useEffect(() => {
    if (!commandBinding || !ownerContext) {
      if (commandSlot.current) {
        commandSlot.current.controller.invalidate();
        commandSlot.current = null;
      }
      return;
    }
    const cur = commandSlot.current;
    // One controller per owner epoch AND per binding object: a replaced
    // binding supersedes the route it carried even when the owner context it
    // reports is unchanged, so view churn on the same binding keeps this
    // controller while a swap invalidates it before the next dispatch.
    if (
      cur &&
      cur.principalScope === ownerContext.principalScope &&
      cur.generation === ownerContext.generation &&
      cur.binding === commandBinding
    )
      return;
    if (cur) cur.controller.invalidate();
    commandSlot.current = {
      controller: new OperationController(
        commandBinding.port,
        commandBinding.store,
      ),
      binding: commandBinding,
      principalScope: ownerContext.principalScope,
      generation: ownerContext.generation,
    };
  }, [commandBinding, ownerContext?.principalScope, ownerContext?.generation]);
  useEffect(() => {
    if (!sessionBinding || !sessionOwner) {
      if (sessionSlot.current) {
        sessionSlot.current.controller.invalidate();
        sessionSlot.current = null;
      }
      return;
    }
    const cur = sessionSlot.current;
    if (
      cur &&
      cur.principalScope === sessionOwner.principalScope &&
      cur.generation === sessionOwner.generation &&
      cur.binding === sessionBinding
    )
      return;
    if (cur) cur.controller.invalidate();
    sessionSlot.current = {
      controller: makeSessionController(sessionBinding, sessionOwner, selectionSeq.current),
      binding: sessionBinding,
      principalScope: sessionOwner.principalScope,
      generation: sessionOwner.generation,
    };
  }, [sessionBinding, sessionOwner?.principalScope, sessionOwner?.generation, authRevision]);
  useEffect(() => {
    // Discover the retained hint without invoking prepare, submit or even a
    // status request. This is available before any launch catalog is loaded.
    recoveryFlight.current++;
    setRecoverInFlight(false);
    setReopenedOperation(null);
    if (!commandBinding || !ownerContext) return;
    const binding = commandBinding;
    const ctx = ownerContext;
    const sequence = commandSelectionRevision;
    const revision = recoveryFlight.current;
    const slot = commandSlot.current;
    // An in-memory action already owns its callback and recovery surface.
    // Discovery must not create a second hold for that same route.
    if (pendingCommand.current?.binding === binding) return;
    const abort = new AbortController();
    let cancelled = false;
    const ownsDiscovery = () => {
      const liveBinding = completeOrchestratorCommandBinding(window.MastermindMissionHost?.commandBinding);
      const liveContext = liveBinding ? readOwnerContext(liveBinding.port) : null;
      return !cancelled && recoveryFlight.current === revision && selectionSeq.current === sequence &&
        window.MastermindMissionHost?.auth?.getState().status === "signed_in" &&
        liveBinding === binding && liveContext?.principalScope === ctx.principalScope &&
        liveContext.generation === ctx.generation && commandSlot.current === slot &&
        (!pendingCommand.current || pendingCommand.current.binding !== binding) &&
        slot?.controller.getState().status === "idle";
    };
    const identity = { binding, ...ctx, authRevision, selectionSeq: sequence };
    setReopenedOperation({ ...identity, pointer: null, reason: "READING" });
    void Promise.resolve().then(() => binding.store.read(ctx.principalScope, abort.signal)).then(value => {
      if (!ownsDiscovery()) return;
      if (value === null) setReopenedOperation(null);
      else if (isFreshRetainedOperation(value)) {
        const owner = value.kind === "conversation_create" ? freshBinding : freshAttendedBinding;
        if (owner?.store === binding.store && sameConversationOwner(ctx, owner.context()))
          setReopenedOperation(null);
        else setReopenedOperation({...identity, pointer: value, reason: "CONVERSATION_OWNER_UNAVAILABLE"});
      }
      else if (isRetainedOperation(value)) setReopenedOperation({ ...identity, pointer: value, reason: "PENDING_POINTER" });
      else setReopenedOperation({ ...identity, pointer: null, reason: "MALFORMED_POINTER" });
    }).catch(() => {
      if (ownsDiscovery()) setReopenedOperation({ ...identity, pointer: null, reason: "LOCAL_UNAVAILABLE" });
    });
    return () => { cancelled = true; abort.abort(); };
  }, [commandBinding, ownerContext?.principalScope, ownerContext?.generation,
    authRevision, commandSelectionRevision, selection?.workRef, selection?.rootJobId, freshBinding, freshAttendedBinding]);
  useEffect(() => {
    const revision = ++sessionRecoveryFlight.current;
    setSessionReading(false); setSessionPointer(null); setSessionPointerError(false);
    setSessionRecovering(false);
    if (!sessionBinding || !sessionOwner) return;
    if (sessionPending.current?.binding === sessionBinding) return;
    const binding = sessionBinding, ctx = sessionOwner, sequence = selectionSeq.current;
    const slot = sessionSlot.current;
    const abort = new AbortController();
    let cancelled = false;
    const current = () => !cancelled && sessionRecoveryFlight.current === revision &&
      ownsSession(binding, ctx, sequence) && sessionSlot.current === slot && !sessionPending.current;
    setSessionReading(true);
    void Promise.resolve().then(() => {
      if (!current()) return undefined;
      return binding.store.read(ctx.principalScope, abort.signal);
    }).then((value) => {
      if (!current()) return;
      if (value === null) setSessionPointer(null);
      else if (isRetainedSessionOperation(value)) setSessionPointer(value);
      else setSessionPointerError(true);
    }).catch(() => {
      if (current()) setSessionPointerError(true);
    }).finally(() => { if (current()) setSessionReading(false); });
    return () => { cancelled = true; abort.abort(); };
  }, [sessionBinding, sessionOwner?.principalScope, sessionOwner?.generation,
    authRevision, commandSelectionRevision]);
  useEffect(() => {
    setSessionRefusal(null);
  }, [sessionBinding, sessionOwner?.principalScope, sessionOwner?.generation,
    selection?.workRef, selection?.rootJobId]);
  useEffect(() => {
    if (active !== "Conversations" && !projectConversationActive && !officeSessionPresentation && !nativeSessionPresentation) answerView.leavePresentation();
  }, [active, projectConversationActive,officeSessionPresentation,nativeSessionPresentation]);

  useEffect(() => () => {
    commandSlot.current?.controller.invalidate();
    recoveryFlight.current++;
    const opening = createdProjectOpen.current;
    createdProjectOpen.current = null;
    opening?.complete(false);
    sessionSlot.current?.controller.invalidate();
    sessionSlot.current = null;
    sessionPending.current = null;
    sessionRecoveryFlight.current++;
  }, []);
  const currentResultContext = useRef(resultContext);
  currentResultContext.current = resultContext;
  const liveSelection = useRef(selection);
  const liveAuthRevision = useRef(authRevision);
  liveSelection.current = selection;
  liveAuthRevision.current = authRevision;
  const resultController = useRef<AbortController | null>(null);
  const compoundRetained = compoundRetention.current;
  const compoundContextHeld = !!compoundRetained
    && compoundRetained.mission === missionV3
    && compoundRetained.selection === selection
    && compoundRetained.authRevision === authRevision;
  useEffect(() => {
    // A compound commit updates missionV3 inside the same pair. That update
    // must not abort or clear the Result it just accepted. Every other
    // context change still fences the standalone Result ticket.
    if (compoundContextHeld) return;
    resultRequest.current++;
    resultController.current?.abort();
    setResultState({ kind: "IDLE" });
    return () => {
      resultRequest.current++;
      resultController.current?.abort();
    };
  }, [resultContext, compoundContextHeld]);
  useEffect(() => () => {
    compoundTicket.current += 1;
    resultController.current?.abort();
  }, []);
  const projectHeading = useRef<HTMLHeadingElement>(null);
  const resourcesView = useRef<HTMLDivElement>(null), resourcesWorkView = useRef<HTMLElement>(null);
  const pendingResourcesFocus = useRef<{kind:"work"|"resources";root:string;auth:number;host:typeof window.MastermindMissionHost;epoch:number|undefined}|null>(null);
  useLayoutEffect(() => {
    const intent = pendingResourcesFocus.current;
    if (!intent) return;
    pendingResourcesFocus.current = null;
    if (intent.auth !== authRevisionRef.current || intent.host !== window.MastermindMissionHost ||
        intent.epoch !== intent.host?.invalidationGeneration?.() || selection?.rootJobId !== intent.root) return;
    const row = Array.from(resourcesView.current?.querySelectorAll<HTMLElement>("[data-root-job-id]") ?? [])
      .find(node => node.dataset.rootJobId === intent.root);
    const target = intent.kind === "work" ? resourcesWorkView.current :
      row?.querySelector<HTMLButtonElement>("button") ?? resourcesView.current?.querySelector<HTMLHeadingElement>("h1");
    target?.focus(); target?.scrollIntoView?.({block:"start"});
  });
  const [resourcesWorkOrigin, setResourcesWorkOrigin] = useState<{auth:number;workRef:string;rootJobId:string} | null>(null);
  const legacyProjectTabs = useRef<HTMLDivElement>(null);
  const pendingLegacyTabFocus = useRef<ProjectTab | null>(null);
  const pendingProjectHeadingFocus = useRef<HTMLElement | null>(null);
  const routeHeading = useRef<HTMLHeadingElement>(null),
    // Project tabs and data refreshes retain focus. Collection/detail and exact
    // project identity changes can remove the content action that held it.
    viewIdentity = JSON.stringify([
      active,
      active === "Projects" && catalogueProject ? ["catalogue", catalogueProject.workRef] :
      active === "Projects" && projectTab && selection
        ? [selection.workRef, selection.rootJobId]
        : null,
    ]),
    previousView = useRef(viewIdentity);
  useLayoutEffect(() => {
    if (previousView.current === viewIdentity) return;
    previousView.current = viewIdentity;
    // A removed content action leaves focus on body. Preserve connected
    // controls (including navigation), and never move focus for data refreshes.
    pendingProjectHeadingFocus.current = null;
    if (!document.activeElement || document.activeElement === document.body) {
      const target = projectHeading.current ?? routeHeading.current;
      target?.focus();
      if (active === "Projects" && projectTab === "Conversation" && !projectHeading.current)
        pendingProjectHeadingFocus.current = target;
    }
  }, [viewIdentity]);
  useLayoutEffect(() => {
    const pending = pendingProjectHeadingFocus.current;
    if (!pending) return;
    if (active !== "Projects" || ![pending, document.body].includes(document.activeElement as HTMLElement)) {
      pendingProjectHeadingFocus.current = null;
      return;
    }
    // Complete only the navigation handoff we initiated. A later source read
    // must never move focus away from a control the user subsequently chose.
    if (projectHeading.current) {
      pendingProjectHeadingFocus.current = null;
      projectHeading.current.focus();
    }
  });
  useLayoutEffect(() => {
    if (!pendingLegacyTabFocus.current) return;
    pendingLegacyTabFocus.current = null;
    if (document.activeElement === document.body) {
      const selected = legacyProjectTabs.current?.querySelector<HTMLButtonElement>('[role="tab"][aria-selected="true"]');
      (selected ?? projectHeading.current)?.focus();
    }
  });
  useEffect(
    () =>
      window.MastermindMissionHost?.auth?.subscribe((state) => {
        const serialized = JSON.stringify(state);
        const generation =
          window.MastermindMissionHost?.invalidationGeneration?.() ?? 0;
        if (
          serialized === previousAuth.current &&
          generation === previousHostGeneration.current
        )
          return;
        const before = previousAuthState.current;
        // Losing a token without acquiring another credential is passive
        // expiry only on the browser client (never infer this for native).
        // An explicit/cross-tab logout always clears, even with a dirty draft.
        const passiveLoss = !native && before !== null &&
          ((before.acquisition && !state.acquisition) ||
           (before.content && !state.content)) &&
          (!state.acquisition || before.acquisition) &&
          (!state.content || before.content) &&
          state.reason !== "USER_SIGNED_OUT" &&
          !explicitLogoutRecorded() &&
          (!canNavigateForAutomaticSignIn() || hasUnsentUserText.current);
        previousAuth.current = serialized;
        previousAuthState.current = state;
        previousHostGeneration.current = generation;
        // Invalidate old surface presentation at notification time while the
        // App-owned pending/unknown action continues to retain its own result.
        // Quarantine the incumbent native goal before withdrawing its old actor.
        const nativeGoalHeld = nativeGoalRef.current.onAuthChange(
          explicitLogoutRecorded() || state.reason === "USER_SIGNED_OUT");
        controlRoomAuthEpoch.current += 1;
        if (passiveLoss && hasUnsentUserText.current)
          passiveExpiryHold.current = true;
        else if (state.status === "signing_in" || state.acquisition ||
                 state.content || state.reason === "USER_SIGNED_OUT" ||
                 explicitLogoutRecorded())
          passiveExpiryHold.current = false;
        if (!passiveLoss) {
          const blank = { launch: "", session: "", launchWorkstream: "", launchDetails: null };
          retainedComposerRef.current = blank;
          retainedComposerScope.current = null;
          setRetainedComposerDrafts(blank);
        }
        freshDraftRef.current.invalidateAuth(passiveLoss);
        freshTurnDraftRef.current.invalidateAuth(passiveLoss);
        freshAttendedRef.current?.controller.invalidate();
        projectJourneyRef.current.invalidateFilesAuth(passiveLoss);
        if (!native || !nativeGoalHeld) projectJourneyRef.current.invalidateAuth(passiveLoss);
        office.invalidateAuth(passiveLoss);
        observedConversation.invalidateAuth(passiveLoss);
        commandSlot.current?.controller.invalidate();
        const pending = pendingCommand.current;
        if (pending) {
          pending.complete({ status: "refused" });
          pendingCommand.current = null;
        }
        setHeldKind(null);
        setCommandRefusal(null);
        setLaunchHandoff(current => current?.kind === "project" ? null : current);
        setReopenedOperation(null);
        recoveryFlight.current++;
        setRecoverInFlight(false);
        answerView.invalidate();
        sessionSlot.current?.controller.invalidate();
        const heldSession = sessionPending.current;
        if (heldSession) {
          heldSession.complete({ status: "refused" });
          sessionPending.current = null;
        }
        setSessionStatus(null);
        setSessionRefusal(null);
        setSessionPointer(null);
        sessionRecoveryFlight.current++;
        bumpInvalidation();
        // Invalidate rendered and in-flight source data at the notification,
        // not after replacement reads resolve or a passive effect runs.
        programRequest.current++;
        workRequest.current++;
        missionRequest.current++;
        resultRequest.current++;
        compoundTicket.current += 1;
        compoundRetention.current = null;
        resultController.current?.abort();
        setIndex({
          programs: [],
          state: "PENDING",
          reason: "SOURCE_READ_PENDING",
        });
        setWorkState(
          state.acquisition
            ? { kind: "PENDING" }
            : { kind: "UNAVAILABLE", reason: "AUTHENTICATION_REQUIRED" },
        );
        setMission(
          unavailableMission(
            null,
            state.acquisition
              ? "SOURCE_READ_PENDING"
              : "AUTHENTICATION_REQUIRED",
          ),
        );
        setAuthState(state);
        setAuthRevision((n) => n + 1);
        setWindowDocument(null);
        setAssociation(null);
        setMissionV3(null);
        // Diagnostic side-state resets with the same source epoch; the
        // Programs effect refines it on its immediate re-run.
        setProgramsReadPhase("not_requested");
        setProgramsReadReason("NONE");
        setResultState({ kind: "IDLE" });
      }),
    [],
  );
  useEffect(() => {
    // Selection change clears result detail. The bounded read for the new
    // tuple must be reissued; we never carry stale detail across a click.
    if (compoundRetention.current?.selection === selection) return;
    compoundTicket.current += 1;
    compoundRetention.current = null;
    resultController.current?.abort();
    setResultState({ kind: "IDLE" });
  }, [selection]);
  useEffect(() => {
    // New result_refs revision (root/work_ref pair changed under the hood)
    // also clears any in-flight detail even if the user kept their click.
    // The compound pair's own Mission commit is the same observation and stays.
    if (compoundRetention.current?.mission === missionV3) return;
    setResultState({ kind: "IDLE" });
  }, [missionV3]);
  useEffect(() => {
    if (resultState.kind !== "READY") return;
    if (authState && !authState.acquisition) {
      setResultState({ kind: "IDLE" });
    }
  }, [authState?.acquisition, resultState]);
  useEffect(() => {
    bumpInvalidation();
    const controller = new AbortController();
    pairAbort.current = controller;
    const started = invalidation.current;
    const hostGeneration =
      window.MastermindMissionHost?.invalidationGeneration?.() ?? 0;
    let attached = true;
    setWindowDocument(null);
    setAssociation(null);
    setWindowPending(false);
    const host = window.MastermindMissionHost;
    const listReadOwner = captureListReadOwner(host);
    windowListOwner.current = null;
    const readWindow = host?.readCurrentWindow;
    const readV3 = host?.readMissionV3;
    const stillCurrent = () =>
      attached &&
      !controller.signal.aborted &&
      started === invalidation.current &&
      hostGeneration === (host?.invalidationGeneration?.() ?? 0);
    if (active !== "Conversation" && active !== "Conversations" && !projectConversationActive)
      return () => {
        attached = false;
        controller.abort();
      };
    const run = async () => {
      const conversationRead = observedConversation.begin();
      setWindowPending(true);
      let pairMission: Missionv3Document | null = null;
      if (authState?.acquisition && selection && readV3) {
        try {
          const raw = await readV3({ ...selection, signal: controller.signal });
          if (!stillCurrent()) return;
          // Same full decoder as the main Mission path: a fresh response that
          // fails the closed contract can never establish an association, so
          // the window stays UNBOUND rather than trusting an unknown shape.
          pairMission = decodeMissionv3(raw, selection);
        } catch {
          if (!stillCurrent()) return;
          pairMission = null;
        }
      }
      if (!stillCurrent()) return;
      if (!authState?.content || !readWindow) {
        observedConversation.accept(conversationRead, pairMission, null);
        setWindowPending(false);
        return;
      }
      try {
        const value = await readWindow({ signal: controller.signal });
        if (!stillCurrent()) return;
        setWindowDocument(value);
        setAssociation(
          observedMissionAssociation(value, pairMission, selection),
        );
        windowListOwner.current = conversationListOwnerCurrent(listReadOwner, true) ? listReadOwner : null;
        observedConversation.accept(conversationRead, pairMission, value);
      } catch {
        if (!stillCurrent()) return;
        setWindowDocument(null);
        setAssociation(null);
        observedConversation.accept(conversationRead, pairMission, null);
      } finally {
        if (stillCurrent()) setWindowPending(false);
      }
    };
    void run();
    return () => {
      attached = false;
      controller.abort();
    };
  }, [
    active,
    projectConversationActive,
    selection,
    authRevision,
    windowRevision,
    authState?.content,
    authState?.acquisition,
  ]);
  useEffect(() => {
    if (!initialProjectJourney.open && initialProjectJourney.valid && !initialLocation.hasIdentity && initial) {
      const location = new URL(window.location.href);
      location.search = new URLSearchParams({
        work_ref: initial.workRef,
        root_job_id: initial.rootJobId,
      }).toString();
      window.history.replaceState(
        window.history.state,
        "",
        `${location.pathname}${location.search}${location.hash}`,
      );
    }
  }, [initial, initialLocation.hasIdentity, initialProjectJourney]);
  useEffect(() => {
    let attached = true;
    if (!native)
      return () => {
        attached = false;
      };
    import("@tauri-apps/api/core")
      .then(({ invoke }) => invoke<BuildReceipt>("readiness"))
      .then((r) => {
        if (attached) setBuild(r);
      })
      .catch(() => {
        if (attached)
          setNotice(
            "Native readiness receipt unavailable. No source request was attempted.",
          );
      });
    return () => {
      attached = false;
    };
  }, [native]);
  useEffect(() => {
    let attached = true;
    const current = ++programRequest.current,
      controller = new AbortController();
    // A changed selection must wait for its own collection read before the
    // Mission effect can use the preceding selection's AVAILABLE index.
    programSelection.current = selection;
    const officeRead = office.beginPrograms();
    const listReadOwner = captureListReadOwner(window.MastermindMissionHost);
    catalogueListOwner.current = null;
    if (
      native &&
      !window.MastermindMissionHost?.readPrograms &&
      !window.MastermindMissionHost?.readProgramsObservation
    ) {
      setProgramsReadPhase("not_requested");
      setProgramsReadReason("NONE");
      setIndex({
        programs: [],
        state: "UNAVAILABLE",
        reason: "NATIVE_TRANSPORT_UNCONFIGURED",
      });
      return () => {
        attached = false;
        controller.abort();
      };
    }
    // A refused owner read emits auth state. Re-reading on that notification
    // without acquisition authority creates a feedback loop while signed out.
    if (authState && !authState.acquisition) {
      setProgramsReadPhase("auth_unavailable");
      setProgramsReadReason("AUTHENTICATION_REQUIRED");
      setIndex({
        programs: [],
        state: "UNAVAILABLE",
        reason: "AUTHENTICATION_REQUIRED",
      });
      return () => {
        attached = false;
        controller.abort();
      };
    }
    const read = window.MastermindMissionHost?.readPrograms;
    const readObservation =
      window.MastermindMissionHost?.readProgramsObservation;
    if (typeof read !== "function" && typeof readObservation !== "function") {
      setProgramsReadPhase("not_requested");
      setProgramsReadReason("NONE");
      setIndex({
        programs: [],
        state: "UNAVAILABLE",
        reason: "QUALIFIED_PROGRAM_READ_UNAVAILABLE",
      });
      return () => {
        attached = false;
        controller.abort();
      };
    }
    setIndex({
      programs: [],
      state: "PENDING",
      reason: "SOURCE_READ_PENDING",
    });
    setProgramsReadPhase("pending");
    setProgramsReadReason("UNKNOWN");
    Promise.resolve()
      .then(async () => {
        if (readObservation) {
          const observation = await readObservation({
            signal: controller.signal,
          });
          return { raw: observation.programsInput ?? observation.controlRoom, observation };
        }
        return {
          raw: await read!({ signal: controller.signal }),
          observation: null,
        };
      })
      .then(({ raw, observation }) => {
        if (
          attached &&
          programRequest.current === current &&
          !controller.signal.aborted
        ) {
          setIndex(programsFromControlRoom(raw));
          setProgramIndexEpoch(current);
          setProgramsReadPhase("ready");
          setProgramsReadReason("NONE");
          catalogueListOwner.current = observation && conversationListOwnerCurrent(listReadOwner, false) ? listReadOwner : null;
          office.acceptPrograms(officeRead, observation);
        }
      })
      .catch((error: unknown) => {
        if (
          attached &&
          programRequest.current === current &&
          !controller.signal.aborted
        ) {
          // The rendered reason stays SOURCE_UNAVAILABLE; the closed
          // diagnostic phase records the failure class only.
          setProgramsReadPhase(closedReadFailurePhase(error));
          setProgramsReadReason(closedReadFailureReason(error));
          setIndex({
            programs: [],
            state: "UNAVAILABLE",
            reason: "SOURCE_UNAVAILABLE",
          });
        }
      });
    return () => {
      attached = false;
      controller.abort();
    };
  }, [
    native,
    authRevision,
    programRevision,
    authState?.acquisition,
    selection?.workRef,
    selection?.rootJobId,
    officeSession.sessionRef,
    officeSession.bindingGeneration,
  ]);
  useEffect(() => {
    if (active !== "Control Room" && active !== "Session Estate" && active !== "Fleet & Capacity" && active !== "Sources" && active !== "Tools") return;
    const host = window.MastermindMissionHost;
    const read = host?.readControlRoomState;
    const ownerRevision = authRevision;
    if (!authState?.acquisition || typeof read !== "function") {
      setControlRoom({
        state: "UNAVAILABLE", ownerRevision,
        reason: !authState?.acquisition ? "AUTHENTICATION_REQUIRED" : "SIGNED_CONTROL_ROOM_READ_UNAVAILABLE",
      });
      return;
    }
    let attached = true;
    const controller = new AbortController();
    setControlRoom({ state: "PENDING", ownerRevision });
    Promise.resolve()
      .then(() => read({ signal: controller.signal }))
      .then((value) => {
        if (attached && !controller.signal.aborted)
          setControlRoom({ ...value, ownerRevision });
      })
      .catch(() => {
        if (attached && !controller.signal.aborted)
          setControlRoom({ state: "UNAVAILABLE", ownerRevision, reason: "SOURCE_UNAVAILABLE" });
      });
    return () => { attached = false; controller.abort(); };
  }, [active, authRevision, authState?.acquisition, controlRoomRevision]);
  // An old auth epoch's Control Room data may remain in state while another
  // view is mounted, but must never render for the next signed-in account.
  const currentControlRoom: ControlRoomState =
    authState?.acquisition && controlRoom.ownerRevision === authRevision
      ? controlRoom
      : { state: "UNAVAILABLE", reason: "AUTHENTICATION_REQUIRED", ownerRevision: authRevision };
  useEffect(() => {
    let attached = true;
    const current = ++workRequest.current;
    const controller = new AbortController();
    const host = window.MastermindMissionHost;
    const read = host?.readWork;
    // The Office consumes this existing acquisition, not a second queue read.
    // Its view stays bound to the exact acquisition-start Host/READ epoch.
    officeWorkFrame.current = captureOfficeReadFrame(host, authRevision, freshAuthRevision, "readWork");
    if (native && !read) {
      setWorkState({
        kind: "UNAVAILABLE",
        reason: "NATIVE_TRANSPORT_UNCONFIGURED",
      });
      return () => {
        attached = false;
        controller.abort();
      };
    }
    if (authState && !authState.acquisition) {
      setWorkState({ kind: "UNAVAILABLE", reason: "AUTHENTICATION_REQUIRED" });
      return () => {
        attached = false;
        controller.abort();
      };
    }
    if (typeof read !== "function") {
      setWorkState({
        kind: "UNAVAILABLE",
        reason: "QUALIFIED_WORK_READ_UNAVAILABLE",
      });
      return () => {
        attached = false;
        controller.abort();
      };
    }
    setWorkState({ kind: "PENDING" });
    Promise.resolve()
      .then(() => read({ signal: controller.signal }))
      .then((raw) => {
        if (
          !attached ||
          workRequest.current !== current ||
          controller.signal.aborted
        )
          return;
        const document = decodeWorkDocument(raw);
        if (!document) throw new Error("WORK_RESPONSE_INVALID");
        setWorkState({ kind: "DOCUMENT", document });
      })
      .catch(() => {
        if (
          attached &&
          workRequest.current === current &&
          !controller.signal.aborted
        )
          setWorkState({ kind: "UNAVAILABLE", reason: "SOURCE_UNAVAILABLE" });
      });
    return () => {
      attached = false;
      controller.abort();
    };
  }, [native, authRevision, authState?.acquisition, workRevision]);
  useEffect(() => {
    const restoreSelection = () => {
      const fresh = readFreshConversationLocation(window.location.href);
      freshDraftRef.current.restoreLocation();
      if (fresh.open || !fresh.valid) {setActive("Conversations"); return;}
      const journey = readProjectJourneyLocation(window.location.href);
      projectJourneyRef.current.restoreLocation();
      if (journey.open || !journey.valid) {
        setCatalogueProject(null);setProjectTab(null);setActive("Projects");
        return;
      }
      const next = directLocationInput().selection;
      const nextKind = readSessionTargetKind();
      office.clearSelection(next);
      observedConversation.clear();
      selectionSeq.current += 1;
      invalidateSessionPresentation();
      setSessionTargetKind(nextKind);
      void window.MastermindMissionHost?.session?.refresh(
        next ? { workRef: next.workRef, rootJobId: next.rootJobId, targetKind: nextKind } : null,
      );
      commandSlot.current?.controller.invalidate();
      bumpInvalidation();
      setWindowDocument(null);
      setAssociation(null);
      setWindowPending(false);
      setMissionV3(null);
      setResultState({ kind: "IDLE" });
      setMission(
        unavailableMission(
          next,
          next ? "PROGRAM_SELECTION_PENDING" : "EXACT_SELECTION_REQUIRED",
        ),
      );
      setSelection(next);
      setProjectTab(next ? "Conversation" : null);
      setActive("Projects");
    };
    window.addEventListener("popstate", restoreSelection);
    return () => window.removeEventListener("popstate", restoreSelection);
  }, []);
  useEffect(() => {
    let attached = true;
    const current = ++missionRequest.current,
      controller = new AbortController();
    // An independent Mission refresh supersedes both the standalone Mission
    // ticket and any compound pair. A late compound accept cannot republish.
    compoundTicket.current += 1;
    compoundRetention.current = null;
    resultController.current?.abort();
    office.supersedePair();
    const officeRead = office.beginMission();
    if (
      native &&
      !window.MastermindMissionHost?.readMissionV3 &&
      !window.MastermindMissionHost?.readMission
    ) {
      setMission(
        unavailableMission(selection, "NATIVE_TRANSPORT_UNCONFIGURED"),
      );
      setNotice("Workspace connection unavailable. Current work was not read.");
      return () => {
        attached = false;
        controller.abort();
      };
    }
    if (!selection) {
      setMission(unavailableMission(null, "EXACT_SELECTION_REQUIRED"));
      setNotice(
        "Choose a Program with one resolved mission before opening the workspace.",
      );
      return () => {
        attached = false;
        controller.abort();
      };
    }
    if (missionSelectionState === "PENDING") {
      setMission(unavailableMission(selection, "PROGRAM_SELECTION_PENDING"));
      setNotice("Reading Programs before resolving the exact mission pair…");
      return () => {
        attached = false;
        controller.abort();
      };
    }
    if (missionSelectionState === "UNAVAILABLE") {
      setMission(unavailableMission(selection, "PROGRAM_SOURCE_UNAVAILABLE"));
      setNotice("Program source unavailable. No mission pair was guessed.");
      return () => {
        attached = false;
        controller.abort();
      };
    }
    if (selectionRefused) {
      setMission(unavailableMission(selection, "EXACT_SELECTION_UNRESOLVED"));
      setNotice(
        "The Program source did not resolve one exact mission pair. No mission was read.",
      );
      return () => {
        attached = false;
        controller.abort();
      };
    }
    if (authState && !authState.acquisition) {
      setMissionV3(null);
      setMission(unavailableMission(selection, "AUTHENTICATION_REQUIRED"));
      setNotice("Workspace connection unavailable. Current work was not read.");
      return () => {
        attached = false;
        controller.abort();
      };
    }
    const missionHost = window.MastermindMissionHost;
    const readV3 = missionHost?.readMissionV3;
    const read = readV3 ?? missionHost?.readMission;
    const missionHostGeneration = missionHost?.invalidationGeneration?.();
    const readIsCurrent = () => window.MastermindMissionHost === missionHost &&
      authRevisionRef.current === authRevision &&
      missionHost?.invalidationGeneration?.() === missionHostGeneration &&
      (missionHost?.readMissionV3 ?? missionHost?.readMission) === read;
    setMissionV3(null);
    if (typeof read !== "function") {
      setMission(
        unavailableMission(selection, "QUALIFIED_HOST_READ_UNAVAILABLE"),
      );
      setNotice("Workspace connection unavailable. Current work was not read.");
      return () => {
        attached = false;
        controller.abort();
      };
    }
    setMission(unavailableMission(selection, "SOURCE_READ_PENDING"));
    setNotice("Reading the exact selected mission pair…");
    Promise.resolve()
      .then(() => {
        if (!readIsCurrent()) throw new Error("MISSION_READ_OWNER_CHANGED");
        return read({ ...selection, signal: controller.signal });
      })
      .then((raw) => {
        if (!attached || missionRequest.current !== current || !readIsCurrent()) return;
        const v3 = readV3 ? decodeMissionv3(raw, selection) : null;
        const decoded = readV3 ? v3 : decodeMission(raw, selection);
        office.acceptMission(officeRead, decoded);
        if (decoded) {
          if (v3) {
            // Existing presentation components consume the same observation's
            // v2 fields; there is no second acquisition or fallback read.
            const { result_refs: _refs, ...body } = v3;
            setMission({ ...body, schema: "mastermind.mission_workspace.v2" });
            setMissionV3(v3);
          } else {
            setMission(decoded as MissionDocument);
          }
          setNotice(
            "Source and observation clocks are displayed as projected; this render did not refresh them.",
          );
        } else {
          setMission(
            unavailableMission(selection, "SELECTION_OR_SCHEMA_MISMATCH"),
          );
          setNotice(
            "The response failed the closed contract or exact pair check.",
          );
        }
      })
      .catch(() => {
        if (
          attached &&
          missionRequest.current === current &&
          !controller.signal.aborted
        ) {
          setMission(unavailableMission(selection, "SOURCE_UNAVAILABLE"));
          setNotice(
            "Mission source unavailable. No mission, relationship, or content was fabricated.",
          );
        }
      });
    return () => {
      attached = false;
      controller.abort();
    };
  }, [
    selection,
    native,
    missionSelectionState,
    selectionRefused,
    authRevision,
    authState?.acquisition,
    officeSession.sessionRef,
    officeSession.bindingGeneration,
    missionReadRevision,
  ]);
  const candidate = isDoc(mission) ? mission : null,
    d =
      candidate &&
      (!authState || authState.acquisition) &&
      selection &&
      candidate.program.work_ref === selection.workRef &&
      (candidate.mission.root_job_id === null ||
        candidate.mission.root_job_id === selection.rootJobId)
        ? candidate
        : null,
    conversationActive =
      active === "Conversation" || active === "Conversations" || projectConversationActive,
    legacyConversationState = windowPending
      ? "SOURCE_READ_PENDING"
      : association
        ? "OBSERVED_MISSION_ASSOCIATION"
        : windowDocument && authState?.content
          ? "UNBOUND"
          : "UNAVAILABLE",
    conversationState =
      active === "Conversations"
        ? observedConversation.projection.conversation.source.state
        : legacyConversationState,
    directSelected = !!selection && new URL(window.location.href).searchParams.get("direct_native_job")===selection.rootJobId,
    directRoute = active === "Projects" && directSelected,
    headerState = conversationActive
      ? conversationState
      : active === "Inbox" || active === "Knowledge"
        ? office.projection.mission.source.state
        : active === "Projects"
          ? office.projection.programs.source.state
          : active === "Today" || active === "Programs"
            ? index.state === "PENDING"
              ? "SOURCE_READ_PENDING"
              : index.state
            : active === "Work"
              ? workState.kind === "PENDING"
                ? "SOURCE_READ_PENDING"
                : workState.kind === "DOCUMENT"
                  ? workState.document.availability
                  : "UNAVAILABLE"
              : active === "Control Room" || active === "Session Estate"
                ? currentControlRoom.state === "PENDING" ? "SOURCE_READ_PENDING" : currentControlRoom.state
              : active === "Fleet & Capacity"
                ? "NOT_PROJECTED"
                : (d?.read_state.state ?? "UNAVAILABLE"),
    headerSummary =
      active === "Conversations"
        ? observedConversation.projection.conversation.source.state ===
          "CURRENT"
          ? (locale === "zh-CN" ? "查看所选工作的回复，并保留未发送的笔记。" : "Read replies from the selected work and keep unsent notes.")
          : (locale === "zh-CN" ? "暂时无法获取所选工作的回复。" : "Replies for the selected work are unavailable right now.")
        : active === "Conversation"
          ? association
            ? "Observed window for this Mission from separately authorized owner observations."
            : windowDocument && authState?.content
              ? "A global current permitted window. No relationship to the selected Mission is proven."
              : "No Mission-linked conversation is currently established."
          : active === "Inbox"
            ? locale === "zh-CN"
              ? "Terminal 请求与任务负责人上下文分别跟随各自来源；全公司覆盖尚未建立。"
              : "Terminal requests and Mission owner context follow their own sources. Company-wide coverage is not established."
            : active === "Knowledge"
              ? "Supplied Mission references retain exact provenance; canonical record content is not reconstructed."
              : active === "Projects"
                ? "Exact Project identities from the supplied owner collection; company-wide coverage is not established."
                : active === "Programs"
                  ? index.state === "PENDING"
                    ? "Reading the bounded Programs projection; no company-wide queue is inferred."
                    : index.state === "AVAILABLE"
                      ? `${index.programs.length} Programs from the bounded source observation.`
                      : "Program source unavailable; current company movement is not inferred."
                : active === "Today"
                  ? d && d.read_state.state !== "CURRENT"
                    ? `Selected mission projection is ${label(d.read_state.state)}; source qualification is not current.`
                    : index.state === "PENDING"
                      ? "Reading the bounded Programs projection; no company-wide queue is inferred."
                      : index.state === "AVAILABLE"
                        ? `${index.programs.length} Programs from the bounded source observation.`
                        : "Program source unavailable; current company movement is not inferred."
                  : active === "Work"
                    ? workState.kind === "PENDING"
                      ? "Reading the bounded Work projection; no queue is inferred yet."
                      : workState.kind === "DOCUMENT"
                        ? workState.document.availability === "AVAILABLE"
                          ? `${workState.document.coverage.count} Work roots from the bounded Executive observation.`
                          : "Work owner returned a typed unavailable observation; no empty queue is inferred."
                        : "Work source unavailable; no empty queue is inferred."
                    : active === "Session Estate"
                      ? (locale === "zh-CN" ? "查看已保存的工作区绑定及其来源状态。保存的绑定不代表会话正在运行。" : "Review saved workspace bindings and their source status. Saved bindings do not prove running sessions.")
                    : active === "Control Room"
                      ? currentControlRoom.state === "AVAILABLE"
                        ? `${currentControlRoom.programs.length} programmes observed. Review the next step and its source.`
                        : currentControlRoom.state === "PENDING"
                          ? "Reading one authenticated incumbent Control Room cache."
                          : "Authenticated Control Room source unavailable; no current operation is inferred."
                    : active === "Fleet & Capacity"
                      ? "Fleet health and placement require their canonical Capacity source."
                      : d
                        ? d.mission.root_job_id &&
                          d.read_state.state === "CURRENT"
                          ? "A bounded source-qualified mission, current as of its owner observation."
                          : d.mission.root_job_id
                            ? `This mission projection is ${label(d.read_state.state)}; source qualification is not current.`
                            : "A qualified reconciliation state; no mission root is established."
                        : "No producer document is currently admitted.",
    visibleNotice =
      active === "Conversations"
        ? windowPending
          ? (locale === "zh-CN" ? "正在读取所选工作的回复…" : "Reading replies from the selected work…")
          : observedConversation.projection.conversation.source.state ===
              "CURRENT"
            ? (locale === "zh-CN" ? "显示此处已提供的回复，可能不包含完整对话。" : "Showing the supplied replies. This may not include the full conversation.")
            : (locale === "zh-CN" ? "暂时无法显示所选工作的回复。" : "Replies for the selected work cannot be shown right now.")
        : active === "Conversation"
          ? association
            ? "Observed window for this Mission. Independent owner observations."
            : windowDocument && authState?.content
              ? "This current permitted window is not linked to the selected Mission."
              : windowPending
                ? "Reading the current permitted window…"
                : "No Mission-linked conversation is currently established."
          : active === "Work"
            ? workState.kind === "PENDING"
              ? "Reading the source-qualified Work queue…"
              : workState.kind === "DOCUMENT"
                ? workState.document.availability === "AVAILABLE"
                  ? "Work queue is source-qualified; ownership, capacity, effects, and acceptance remain evidence-bound."
                  : "Work projection unavailable; zero work is not inferred."
                : "Work source unavailable; zero work is not inferred."
            : active === "Fleet & Capacity"
              ? "Capacity source not connected. No host readiness was inferred."
              : notice === "Source and observation clocks are displayed as projected; this render did not refresh them."
              ? copy.sourceClocksNotice : notice,
    open = (w: string, r: string | null, direct = false) => {
      setCatalogueProject(null);
      if (r) {
        office.clearSelection({ workRef: w, rootJobId: r });
        observedConversation.clear();
        selectionSeq.current += 1;
        invalidateSessionPresentation();
        commandSlot.current?.controller.invalidate();
        bumpInvalidation();
        setWindowDocument(null);
        setAssociation(null);
        setWindowPending(false);
        const next = { workRef: w, rootJobId: r },
          location = new URL(window.location.href);
        location.search = new URLSearchParams({
          work_ref: next.workRef,
          root_job_id: next.rootJobId,
        }).toString();
        // The ordinary session target kind parameter is retained across a
        // mission change; it is the whole retention of that choice.
        if (sessionTargetKind !== "fabric_attempt") {
          location.searchParams.set(SESSION_TARGET_KIND_PARAM, sessionTargetKind);
        }
        // Read-selection hint only; the authenticated direct endpoint still
        // proves the Job, original principal, receiver and terminal identity.
        if(direct)location.searchParams.set("direct_native_job",r);
        window.history.pushState(
          null,
          "",
          `${location.pathname}${location.search}${location.hash}`,
        );
        setMission(unavailableMission(next, "SOURCE_READ_PENDING"));
        setNotice("Reading the exact selected mission pair…");
        setSelection(next);
        void window.MastermindMissionHost?.session?.refresh(
          { workRef: next.workRef, rootJobId: next.rootJobId, targetKind: sessionTargetKind },
        );
        setProjectTab(direct ? "Overview" : "Conversation");
        setActive("Projects");
      }
    };
  const settleCommand = (
    state: OperationState,
    bindingAtStart: OrchestratorCommandBinding,
  ) => {
    const pending = pendingCommand.current;
    // Adjudicate against the live route, not the captured one: a binding
    // object that was replaced — even by one carrying the same owner scope
    // and generation — supersedes the dispatch it received. Its receipt may
    // not navigate, may not complete a newer action, and may not publish a
    // terminal admission over the route the user now sees.
    const liveBinding = completeOrchestratorCommandBinding(
      window.MastermindMissionHost?.commandBinding,
    );
    if (liveBinding !== bindingAtStart) {
      // A superseded route's receipt may release only the pending it
      // dispatched. A newer pending started under the replacement binding
      // belongs to its own route's receipt: publish nothing and release
      // nothing here.
      if (pending && pending.binding === bindingAtStart) {
        pending.complete({ status: "refused" });
        pendingCommand.current = null;
        setHeldKind(null);
      }
      return;
    }
    setCommandStatus(state);
    if (!pending) return;
    const liveAuth = window.MastermindMissionHost?.auth?.getState();
    const ctx = readOwnerContext(bindingAtStart.port);
    if (liveAuth?.status !== "signed_in" || !ctx) return;
    if (
      ctx.generation !== pending.generation ||
      ctx.principalScope !== pending.principalScope
    ) {
      pending.complete({ status: "refused" });
      pendingCommand.current = null;
      setHeldKind(null);
      return;
    }
    if (state.status !== "accepted" && state.status !== "refused") {
      setHeldKind(pending.kind);
      return;
    }
    const liveSession = readCommandView(bindingAtStart)?.session;
    if (state.status === "refused" &&
        pending.selectionSeq === selectionSeq.current &&
        pending.presentationSeq === commandPresentation.current.seq &&
        (pending.kind === "launch" ||
          (sessionMatchesSelection(liveSession ?? null, selection) &&
            liveSession?.sessionKey === pending.sessionKey))) {
      setCommandRefusal({
        binding: pending.binding,
        principalScope: pending.principalScope,
        generation: pending.generation,
        kind: pending.kind,
        selectionSeq: pending.selectionSeq,
        sessionKey: pending.sessionKey,
        presentationSeq: pending.presentationSeq,
        reason: state.reason,
      });
    }
    if (state.status === "accepted" && pending.kind === "launch") {
      if (pending.selectionSeq !== selectionSeq.current) {
        pending.complete({ status: "refused" });
        pendingCommand.current = null;
        setHeldKind(null);
        return;
      }
      const sel = state.missionSelection
        ? normalizeSelection(state.missionSelection)
        : null;
      const original = commandSlot.current?.binding === bindingAtStart
        ? commandSlot.current.controller.observeOriginalOperation() : null;
      // Only this owner-qualified accepted launch releases its Office handoff.
      // A refusal or unknown effect keeps the frozen context and original hold.
      setLaunchHandoff(null);
      if (sel) open(sel.workRef, sel.rootJobId,bindingAtStart.directNative?.isDirectSelection(sel)===true);
      // Navigation invalidates the command controller. Retain only its already
      // validated public original receipt, with the exact caller and selection
      // lifetime; this is neither a pending store nor a lifecycle projection.
      if (original?.status === "accepted" && sel && original.missionSelection?.workRef === sel.workRef
          && original.missionSelection.rootJobId === sel.rootJobId && freshExecutiveOwner())
        activationOriginal.current = {observation: original, binding: bindingAtStart,
          frame: freshExecutiveOwner, selectionSeq: selectionSeq.current};
    }
    pending.complete({ status: state.status });
    pendingCommand.current = null;
    setHeldKind(null);
  };
  const beginCommand = (
    kind: OperationKind,
    intent: ReturnType<typeof launchIntentFromBinding>,
    onComplete: (
      outcome: { status: "accepted" } | { status: "refused" },
    ) => void,
  ) => {
    setCommandRefusal(null);
    const binding = completeOrchestratorCommandBinding(
      window.MastermindMissionHost?.commandBinding,
    );
    const liveAuth = window.MastermindMissionHost?.auth?.getState();
    const ctx = binding ? readOwnerContext(binding.port) : null;
    if (!binding || liveAuth?.status !== "signed_in" || !ctx || !intent) {
      onComplete({ status: "refused" });
      return;
    }
    if (currentReopened) {
      // An unreadable store is not evidence of absence. Only a successful
      // empty read admits an ordinary new command.
      onComplete({ status: "refused" });
      return;
    }
    if (pendingCommand.current) {
      // Another action is already held for this composition: refuse the NEW
      // callback exactly once so its own guard releases immediately. The
      // original held callback, pointer, and guard are never replaced or
      // released here — only its own receipt may settle them.
      onComplete({ status: "refused" });
      return;
    }
    let controller = commandSlot.current?.controller ?? null;
    if (
      !commandSlot.current ||
      commandSlot.current.binding !== binding ||
      commandSlot.current.principalScope !== ctx.principalScope ||
      commandSlot.current.generation !== ctx.generation
    ) {
      commandSlot.current?.controller.invalidate();
      controller = new OperationController(binding.port, binding.store);
      commandSlot.current = {
        controller,
        binding,
        principalScope: ctx.principalScope,
        generation: ctx.generation,
      };
    }
    if (!controller) {
      onComplete({ status: "refused" });
      return;
    }
    pendingCommand.current = {
      generation: ctx.generation,
      principalScope: ctx.principalScope,
      binding,
      kind,
      selectionSeq: selectionSeq.current,
      sessionKey: kind === "launch" ? null : readCommandView(binding)?.session?.sessionKey ?? null,
      presentationSeq: commandPresentation.current.seq,
      complete: onComplete,
    };
    activationOriginal.current = null;
    setActivationWorkReturn(null);
    setReopenedOperation(null);
    setHeldKind(kind);
    void Promise.resolve()
      .then(() => controller.begin(intent))
      .then((state) => settleCommand(state, binding))
      .catch(() => {
        const current = controller.getState();
        if (current.status === "unknown") settleCommand(current, binding);
        else setHeldKind(kind);
      });
  };
  const checkCommandStatus = () => {
    if (recoverInFlight) return;
    const binding = completeOrchestratorCommandBinding(
      window.MastermindMissionHost?.commandBinding,
    );
    const liveAuth = window.MastermindMissionHost?.auth?.getState();
    const ctx = binding ? readOwnerContext(binding.port) : null;
    const slot = commandSlot.current;
    if (!binding || liveAuth?.status !== "signed_in" || !ctx || !slot) return;
    if (
      slot.generation !== ctx.generation ||
      slot.principalScope !== ctx.principalScope ||
      slot.binding !== binding
    )
      return;
    // Read-only recovery: recover() resolves through readOperation only and
    // never prepares or submits. The control is disabled exactly while this
    // asynchronous recovery is in flight — not for a static held pointer.
    setRecoverInFlight(true);
    const flight = ++recoveryFlight.current;
    const restored = currentReopened;
    const sequence = selectionSeq.current;
    const ownsRecovery = () => {
      const liveBinding = completeOrchestratorCommandBinding(window.MastermindMissionHost?.commandBinding);
      const liveContext = liveBinding ? readOwnerContext(liveBinding.port) : null;
      return recoveryFlight.current === flight &&
        selectionSeq.current === sequence && commandSlot.current === slot &&
        liveBinding === binding && window.MastermindMissionHost?.auth?.getState().status === "signed_in" &&
        liveContext?.principalScope === ctx.principalScope && liveContext.generation === ctx.generation;
    };
    void Promise.resolve()
      .then(() => ownsRecovery() ? slot.controller.recover() : null)
      .then((state) => {
        if (!state || !ownsRecovery()) return;
        if (!restored || pendingCommand.current?.binding === binding) { settleCommand(state, binding); return; }
        if (state.status === "accepted" || (state.status === "refused" && state.reason === "REFUSED") ||
            (state.status === "idle" && state.reason === "RECOVER_NO_POINTER")) {
          setReopenedOperation(null);
          // Only the controller-qualified accepted launch can carry a
          // mission selection, including when initial discovery had failed.
          if (state.status === "accepted") {
            const next = state.missionSelection ? normalizeSelection(state.missionSelection) : null;
            if (next) open(next.workRef, next.rootJobId,binding.directNative?.isDirectSelection(next)===true);
          }
        } else {
          setReopenedOperation({ ...restored, pointer: state.pointer ?? restored.pointer, reason: state.reason });
        }
      })
      .catch(() => {})
      .finally(() => { if (recoveryFlight.current === flight) setRecoverInFlight(false); });
  };
  const settleSessionCommand = (
    state: OperationState,
    pending: NonNullable<typeof sessionPending.current>,
  ) => {
    if (sessionPending.current !== pending) return;
    if (!ownsSession(pending.binding, pending, pending.selectionSeq)) {
      sessionPending.current = null;
      pending.complete({ status: "refused" });
      return;
    }
    setSessionStatus(state); setSessionPointer(state.pointer);
    setSessionPointerError(sessionStoreHold(state));
    sessionPending.current = null;
    pending.complete({ status: state.status === "accepted" ? "accepted" : "refused" });
    if (state.status === "refused" || state.status === "idle") setSessionRefusal({
      binding: pending.binding, principalScope: pending.principalScope,
      generation: pending.generation, reason: state.reason,
    });
  };
  const beginSessionCommand = (
    instruction: string,
    stopCondition: string,
    onComplete: (outcome: { status: "accepted" } | { status: "refused" }) => void,
  ) => {
    setSessionRefusal(null);
    const binding = completeExecutiveSessionBinding(
      window.MastermindMissionHost?.sessionCommandBinding,
    );
    const liveAuth = window.MastermindMissionHost?.auth?.getState();
    const ctx = native?sessionExecutiveOwner():binding?readSessionOwnerContext(binding):null;
    const liveTarget = binding ? binding.port.currentTargetRef() : null;
    if (!binding || (!native&&liveAuth?.status !== "signed_in") || !ctx || !liveTarget) {
      onComplete({ status: "refused" });
      return;
    }
    // Native caller binds the user's rendered selected-session frame, not
    // merely whichever valid E target happens to be current at click time.
    if(native&&(binding!==sessionBinding||ctx.principalScope!==sessionOwner?.principalScope||
        ctx.generation!==sessionOwner?.generation||liveTarget!==sessionTargetKey||
        selectionSeq.current!==commandSelectionRevision)){
      onComplete({status:"refused"});return;
    }
    if (sessionPending.current) {
      // One session dispatch at a time: the newer callback is refused exactly
      // once and the original held completion is never replaced.
      onComplete({ status: "refused" });
      return;
    }
    // Explicit synchronous capture: the user-entered instruction and
    // completion condition are captured once into the immutable intent here.
    // No condition re-evaluation, no Stop authority, no unsolicited action.
    const control = window.MastermindMissionHost?.session;
    if (!control || control !== sessionControl) { onComplete({ status: "refused" }); return; }
    control.setStopCondition(() => stopCondition);
    const intent = binding.makeMessageIntent(liveTarget, instruction);
    if (!intent) {
      onComplete({ status: "refused" });
      return;
    }
    let controller = sessionSlot.current?.controller ?? null;
    if (
      !sessionSlot.current ||
      sessionSlot.current.binding !== binding ||
      sessionSlot.current.principalScope !== ctx.principalScope ||
      sessionSlot.current.generation !== ctx.generation
    ) {
      sessionSlot.current?.controller.invalidate();
      controller = makeSessionController(binding, ctx, selectionSeq.current);
      sessionSlot.current = {
        controller,
        binding,
        principalScope: ctx.principalScope,
        generation: ctx.generation,
      };
    }
    if (!controller) {
      onComplete({ status: "refused" });
      return;
    }
    sessionPending.current = {
      binding,
      principalScope: ctx.principalScope,
      generation: ctx.generation,
      selectionSeq: selectionSeq.current,
      complete: onComplete,
    };
    const pending = sessionPending.current;
    const activeController = controller;
    setSessionStatus(null);
    void Promise.resolve()
      .then(() => activeController.begin(intent))
      .then((state) => settleSessionCommand(state, pending))
      .catch(() => {
        const current = activeController.getState();
        settleSessionCommand(current, pending);
      });
  };
  const checkSessionStatus = () => {
    if (sessionRecovering) return;
    const binding = completeExecutiveSessionBinding(
      window.MastermindMissionHost?.sessionCommandBinding,
    );
    const liveAuth = window.MastermindMissionHost?.auth?.getState();
    const ctx = native?sessionExecutiveOwner():binding?readSessionOwnerContext(binding):null;
    const slot = sessionSlot.current;
    if (!binding || (!native&&liveAuth?.status !== "signed_in") || !ctx || !slot) return;
    if (
      slot.generation !== ctx.generation ||
      slot.principalScope !== ctx.principalScope ||
      slot.binding !== binding
    )
      return;
    // Status-only recovery through readOperation: the exact original
    // operation key, no send, no target lookup, no second dispatch.
    setSessionRecovering(true);
    setSessionRefusal(null);
    const flight = ++sessionRecoveryFlight.current;
    const sequence = selectionSeq.current;
    const current = () => sessionRecoveryFlight.current === flight &&
      ownsSession(binding, ctx, sequence) && sessionSlot.current === slot;
    void Promise.resolve()
      .then(() => current() ? slot.controller.recover() : null)
      .then((state) => {
        if (!current() || !state) return;
        setSessionPointerError(sessionStoreHold(state));
        setSessionStatus(state);
        setSessionPointer(state.pointer);
        if (state.status === "idle" && state.reason !== "RECOVER_NO_POINTER") setSessionRefusal({
          binding, principalScope: ctx.principalScope, generation: ctx.generation, reason: state.reason,
        });
      })
      .catch(() => {})
      .finally(() => {
        if (current()) { setSessionRecovering(false); setSessionReading(false); }
      });
  };
  const reopenedOperationControl = currentReopened?.reason === "CONVERSATION_OWNER_UNAVAILABLE" ? (
    <section className="card" aria-label={locale === "zh-CN" ? "待核实的对话请求" : "Pending conversation request"}>
      <h2>{locale === "zh-CN" ? "对话请求待核实" : "Conversation request pending"}</h2>
      <p>{locale === "zh-CN" ? "请恢复原对话连接后查看该请求的状态。" : "Restore the original conversation connection to check this request."}</p>
    </section>
  ) : currentReopened ? (
    <section className="card" aria-label="Retained operation">
      <h2>{currentReopened.pointer ? "Retained operation" : "Operation recovery"}</h2>
      {currentReopened.pointer ? (
        <p>Original {currentReopened.pointer.kind} reference: <code>{currentReopened.pointer.operationKey}</code></p>
      ) : <p>{currentReopened.reason === "READING" ? "Checking for a retained operation…" : "The retained operation could not be read. Check status before starting a new command."}</p>}
      {currentReopened.reason !== "READING" ? (
        <div className="form-actions">
          <code>{currentReopened.reason}</code>
          <button type="button" onClick={checkCommandStatus} disabled={recoverInFlight}>Check status</button>
        </div>
      ) : null}
    </section>
  ) : null;
  const commandBusy =
    commandStatus?.status === "submitting" ||
    commandStatus?.status === "checking";
  const showCheckStatus =
    !!heldKind &&
    commandStatus?.status !== "accepted" &&
    commandStatus?.status !== "refused" &&
    commandStatus?.status !== "submitting";
  const checkStatusControl = showCheckStatus ? (
    <div className="form-actions">
      {commandStatus?.reason ? <code>{commandStatus.reason}</code> : null}
      <button
        type="button"
        onClick={checkCommandStatus}
        disabled={recoverInFlight}
      >
        {copy.checkStatus}
      </button>
    </div>
  ) : null;
  // Read only the current controller instance, never the last settled view
  // from an earlier binding/auth epoch. Selection changes invalidate this same
  // controller; recovery remains the existing guarded owner callback.
  const currentControllerState = signedIn && authState?.acquisition && ownerContext &&
    commandSlot.current?.binding === commandBinding &&
    commandSlot.current.principalScope === ownerContext.principalScope &&
    commandSlot.current.generation === ownerContext.generation
      ? commandSlot.current.controller.getState() : null;
  const readActivationOriginal = (): OriginalOperationObservation | null => {
    try {
      const ctx = freshExecutiveOwner(), liveAuth = window.MastermindMissionHost?.auth?.getState();
      if (!ctx || !liveAuth?.acquisition || !commandBinding) return null;
      const slot = commandSlot.current;
      const live = slot?.binding === commandBinding ? slot.controller.observeOriginalOperation() : null;
      if (live) return live;
      const prior = activationOriginal.current, sel = prior?.observation.missionSelection;
      return prior?.binding === commandBinding && prior.frame === freshExecutiveOwner
        && prior.selectionSeq === selectionSeq.current && prior.observation.owner.principalScope === ctx.principalScope
        && prior.observation.owner.generation === ctx.generation && sel?.workRef === selection?.workRef
        && sel?.rootJobId === selection?.rootJobId ? prior.observation : null;
    } catch {return null;}
  };
  const activationModel = activationFacts(readActivationOriginal(), d);
  const navigateActivation = (route: ReceiptRoute) => {
    const current = activationFacts(readActivationOriginal(), d);
    if (!current || current.operationKey !== activationModel?.operationKey || current.kind !== activationModel.kind
        || current.targetKey !== activationModel.targetKey || !current.routes.includes(route)) return;
    if (route === "original_status") {checkCommandStatus(); return;}
    if (route === "work") {setActivationWorkReturn(current.operationKey); setActive("Work"); return;}
    document.getElementById("activation-session-owner")?.focus();
  };
  // Observer-only snapshot for the fallback disclosures. A throwing or
  // absent getter degrades to null, which the fields render as unknown
  // values; reading it triggers no request, refresh or subscription change.
  // Explicit local observation only: no transport update, auth notification or
  // context/Programs refresh. Keep the reader stable within this owner epoch.
  const nativeDiagnosticHost = window.MastermindMissionHost;
  const nativeDiagnosticGeneration = nativeDiagnosticHost?.invalidationGeneration?.();
  const refreshNativeDiagnostics = useMemo(() => {
    const host = nativeDiagnosticHost, reader = host?.readNativeExecutiveDiagnostics;
    const revision = authRevision, generation = nativeDiagnosticGeneration;
    if (!host || !reader) return undefined;
    return async ({ signal }: { signal: AbortSignal }) => {
      const current = () => !signal.aborted && window.MastermindMissionHost === host &&
        authRevisionRef.current === revision && host.readNativeExecutiveDiagnostics === reader &&
        host.invalidationGeneration?.() === generation;
      if (!current()) throw new Error("READ_CANCELLED");
      const value = await reader.call(host, { signal });
      if (!current()) throw new Error("READ_CANCELLED");
      return value;
    };
  }, [nativeDiagnosticHost, nativeDiagnosticGeneration, authRevision]);
  const missionDiagnostics = (): unknown => {
    try {
      return window.MastermindMissionHost?.diagnostics?.() ?? null;
    } catch {
      return null;
    }
  };
  const previewLaunchRequest = useMemo(() => (form: LaunchForm) => {
    const binding = completeOrchestratorCommandBinding(window.MastermindMissionHost?.commandBinding);
    const auth = window.MastermindMissionHost?.auth?.getState();
    const owner = binding ? readOwnerContext(binding.port) : null;
    if (authRevisionRef.current !== authRevision || auth?.status !== "signed_in" || !auth.acquisition ||
        binding !== commandBinding || !owner || owner.principalScope !== ownerContext?.principalScope ||
        owner.generation !== ownerContext?.generation) return {state: "UNAVAILABLE" as const};
    if (launchHandoff?.kind === "project") {
      if (!launchHandoff.inspection.isCurrent() ||
          launchHandoff.executionPreview.previous_run && launchHandoff.continuationCurrent?.() !== true)
        return {state: "UNAVAILABLE" as const};
      const intent = binding?.projectExecution?.makeLaunchIntent(form, launchHandoff.draft.context, launchHandoff.executionPreview);
      return intent ? {state: "PREPARED" as const, goal: form.goal, projectRef: form.projectRef,
        profileRef: form.profileRef, frontierModelAlias: form.frontierModelAlias ?? null, targetKey: intent.targetKey}
        : {state: "UNAVAILABLE" as const};
    }
    return readLaunchRequestPreview(binding, form);
  }, [commandBinding, ownerContext?.principalScope, ownerContext?.generation, authRevision, launchHandoff]);
  const partialNativeAuth = native && authState
    ? nativePartialAuthPresentation(authState, locale) : null;
  // Presentation reuses the incumbent explicit auth action and its guards.
  const authenticationButtonRef = useRef<HTMLButtonElement>(null);
  const existingAuthenticationControl = authState ? (
                <button ref={authenticationButtonRef}
                  disabled={authState.status === "unconfigured"}
                  onClick={() => {
                    const auth = window.MastermindMissionHost?.auth;
                    if (!auth) return;
                    const signingOut =
                      authState.acquisition ||
                      authState.content ||
                      authState.status === "signing_in";
                    if (signingOut) {
                      setWindowDocument(null);
                      setMission(
                        unavailableMission(
                          selection,
                          "AUTHENTICATION_REQUIRED",
                        ),
                      );
                    }
                    if (native) nativeGoalRef.current.onAuthChange(signingOut);
                    try {
                      const request = signingOut
                        ? auth.signOut()
                        : auth.signIn();
                      request.catch(() =>
                        setNotice(
                          "Sign-in could not complete. Please try again.",
                        ),
                      );
                    } catch {
                      setNotice(
                        "Sign-in could not complete. Please try again.",
                      );
                    }
                  }}
                >
                  {authState.status === "signing_in"
                    ? copy.cancelSignIn
                    : authState.acquisition || authState.content
                      ? copy.signOut
                      : copy.signIn}
                </button>
  ) : null;
  const authenticationControl = authState && native && !authState.acquisition && !authState.content ? (
    <NativePrimaryAccountControl host={window.MastermindMissionHost} state={authState} locale={locale}
      pendingControl={existingAuthenticationControl} pendingControlRef={authenticationButtonRef}
      beforeSignIn={() => nativeGoalRef.current.onAuthChange(false)} />
  ) : existingAuthenticationControl;
  const todayNeedsAuthentication = !!authState && !authState.acquisition &&
    ["signed_out", "error", "signing_in", "unconfigured"].includes(authState.status);
  const todayAuthenticationCue = todayNeedsAuthentication ? <section className="card" aria-label={locale === "zh-CN" ? "工作区登录" : "Workspace sign-in"}>
    <h2>{authState?.status === "signing_in" ? (locale === "zh-CN" ? "正在登录…" : "Signing in…")
      : authState?.status === "unconfigured" ? (locale === "zh-CN" ? "此处暂时无法登录。" : "Sign-in is unavailable here.")
      : (locale === "zh-CN" ? "登录以继续" : "Sign in to continue")}</h2>
    {authState?.status !== "signing_in" && authState?.status !== "unconfigured" &&
      <p>{locale === "zh-CN" ? "登录以访问工作区。" : "Sign in to access your workspace."}</p>}
    {authenticationControl}
    {authState?.reason && <details><summary>{copy.technicalDetails}</summary><code>{authState.reason}</code></details>}
  </section> : null;
  // The Office → existing launch owner handoff. It re-reads the live host,
  // binding and owner epoch at the moment of the request, refuses rather than
  // replacing an existing unsent goal or a held original command, and only
  // then hands the exact frozen text to the existing launch draft. It never
  // prepares, submits, or carries a session reference.
  const startOfficeLaunch = (preview: DirectionPreview): OfficeLaunchOutcome => {
    const liveBinding = completeOrchestratorCommandBinding(
      window.MastermindMissionHost?.commandBinding);
    const liveAuth = window.MastermindMissionHost?.auth?.getState();
    const liveOwner = liveBinding ? readOwnerContext(liveBinding.port) : null;
    const frozenWorkstream = preview.context.selection?.workRef;
    const config = readLaunchBindingConfig();
    const enrolled = config && frozenWorkstream ? resolveLaunchBinding(config, frozenWorkstream) : null;
    const launchAvailable = canLaunch && !!commandView && !!enrolled &&
      liveBinding === commandBinding &&
      liveAuth?.status === "signed_in" && !!liveOwner &&
      liveOwner.principalScope === ownerContext?.principalScope &&
      liveOwner.generation === ownerContext?.generation;
    // Revisiting an open handoff is idempotent: the same frozen direction never
    // places a second launch owner and never replaces its own goal.
    const alreadyOpen = launchHandoff?.kind === "office" &&
      launchHandoff.preview.draft === preview.draft &&
      previewIsCurrent(launchHandoff.preview, office.projection.context);
    const outcome = decideOfficeLaunchHandoff(preview, office.projection.context, {
      configuredWorkstream: enrolled?.workstream ?? null,
      selectedWorkstream: office.projection.context.selection?.workRef ?? null,
      launchAvailable,
      retainedGoal: retainedComposerDrafts.launch,
      commandHeld: pendingCommand.current?.kind === "launch" || heldKind === "launch",
      handoffAlreadyOpen: alreadyOpen,
    });
    if (outcome.status !== "OPENED") return outcome;
    if (alreadyOpen) return outcome;
    if (retainedComposerRef.current.launchDetails)
      return { status: "REFUSED", reason: "LAUNCH_GOAL_PRESERVED" };
    retainedComposerScope.current = liveComposerScope;
    updateRetainedComposer("launch", preview.draft);
    updateRetainedComposer("launchWorkstream", frozenWorkstream!);
    setLaunchDraftDismissed(false);
    setLaunchHandoff({
      kind: "office", preview,
      workstreamRef: frozenWorkstream!,
      binding: liveBinding!,
      principalScope: liveOwner!.principalScope,
      generation: liveOwner!.generation,
    });
    return outcome;
  };
  const startProjectLaunch = async (
    draft: ProjectLaunchDraft, inspection: ProjectPlanLaunchInspection,
    previousRun?: ProjectExecutionPreviousRun, previousRunCurrent?: () => boolean,
  ): Promise<ProjectLaunchOutcome> => {
    const liveBinding = completeOrchestratorCommandBinding(window.MastermindMissionHost?.commandBinding);
    const liveOwner = liveBinding ? readOwnerContext(liveBinding.port) : null;
    const workRef = draft.context.workRef;
    const inspect = (): ProjectLaunchOutcome => {
      const currentBinding = completeOrchestratorCommandBinding(window.MastermindMissionHost?.commandBinding);
      const currentOwner = currentBinding ? readOwnerContext(currentBinding.port) : null;
      const decision = decideProjectLaunchHandoff(draft, {
        current: projectExecutionContext(inspection.read, inspection.selection),
        sourceIsCurrent: inspection.isCurrent() && projectWorkRef === workRef &&
          (!previousRun || previousRunCurrent?.() === true),
        owner: {
          configuredWorkstream: workRef, selectedWorkstream: projectWorkRef,
          launchAvailable: commandReady && !!liveBinding?.projectExecution &&
            currentBinding === liveBinding && liveBinding === commandBinding &&
            window.MastermindMissionHost?.auth?.getState().status === "signed_in" && !!liveOwner &&
            currentOwner?.principalScope === liveOwner.principalScope && currentOwner?.generation === liveOwner.generation &&
            liveOwner.principalScope === ownerContext?.principalScope && liveOwner.generation === ownerContext?.generation,
          retainedGoal: retainedComposerRef.current.launch,
          commandHeld: pendingCommand.current?.kind === "launch" || heldKind === "launch" || !!currentReopened,
        },
        openedDraft: launchHandoff?.kind === "project" &&
          canonicalJson(launchHandoff.executionPreview.previous_run ?? null) === canonicalJson(previousRun ?? null)
          ? launchHandoff.draft : null,
      });
      return decision.status === "OPENED" && !decision.reuseExisting && retainedComposerRef.current.launchDetails
        ? { status: "REFUSED", reason: "LAUNCH_GOAL_PRESERVED" } : decision;
    };
    try {
      const initial = inspect();
      if (initial.status !== "OPENED") return initial;
      if (initial.reuseExisting && launchHandoff?.kind === "project" &&
          launchHandoff.binding === liveBinding && launchHandoff.principalScope === liveOwner?.principalScope &&
          launchHandoff.generation === liveOwner?.generation && launchHandoff.inspection.isCurrent() &&
          (!previousRun || launchHandoff.continuationCurrent?.() === true)) return initial;
      const executionPreview = await liveBinding!.projectExecution!.preview(draft.context, new AbortController().signal, previousRun);
      const current = inspect();
      if (current.status !== "OPENED") return current;
      if (executionPreview.execution_state !== "WORK_CAPABLE" || executionPreview.work_ref !== workRef)
        return {status: "REFUSED", reason: "LAUNCH_OWNER_UNAVAILABLE"};
      // A newly acquired source may requalify this same draft after a view
      // unmount. Retain the user’s edited text and scope in that case.
      if (!current.reuseExisting) {
        retainedComposerScope.current = liveComposerScope;
        updateRetainedComposer("launch", draft.goal);
        updateRetainedComposer("launchWorkstream", workRef);
      }
      setLaunchDraftDismissed(false);
      setLaunchHandoff({ kind: "project", draft, inspection, executionPreview, workstreamRef: workRef,
        binding: liveBinding!, principalScope: liveOwner!.principalScope, generation: liveOwner!.generation,
        ...(previousRun ? { continuationCurrent: previousRunCurrent } : {}) });
      return current;
    } catch {
      return { status: "REFUSED", reason: inspection.isCurrent() ? "LAUNCH_OWNER_UNAVAILABLE" : "PROJECT_CONTEXT_NOT_CURRENT" };
    }
  };
  const launchView = launchHandoff?.kind === "project" ? {
    projects: launchHandoff.executionPreview.binding.projects,
    profiles: launchHandoff.executionPreview.binding.profiles,
    frontierModels: undefined,
    defaultWorkstream: launchHandoff.workstreamRef,
    workstreams: [{ref: launchHandoff.workstreamRef, label: launchHandoff.workstreamRef,
      projects: launchHandoff.executionPreview.binding.projects,
      profiles: launchHandoff.executionPreview.binding.profiles}],
  } : commandView;
  // Dynamic project choices are qualified by the authenticated preview. The
  // legacy static enrollment remains the Office/Today launch source only.
  const currentLaunchAvailable = commandReady && !!launchView &&
    launchView.projects.length > 0 && launchView.profiles.length > 0;
  const retainedLaunchDetails = retainedComposerDrafts.launchDetails;
  const changeHeldLaunchDetails = (change: Partial<LaunchDetailsDraft>) => {
    const held = retainedComposerRef.current.launchDetails;
    if (!signedIn && passiveExpiryHold.current && held) {
      const next = { ...held, ...change };
      const hasDetails = next.acceptanceCriteria || next.handoffText || next.writePathsText ||
        next.testTargetsText || !next.diffCheck || next.projectRef || next.profileRef;
      updateRetainedComposer("launchDetails", hasDetails ? next : null);
    }
  };
  const commandPanel =
    !signedIn && passiveExpiryHold.current && (retainedComposerDrafts.launch || retainedComposerDrafts.launchDetails) ? (
      <section className="card" aria-label={copy.retainedDraft}>
        <h2>{copy.unsentGoal}</h2>
        <p className="muted">{copy.expiredDraft}</p>
        <label htmlFor="retained-launch-goal">{copy.goal}</label>
        <textarea id="retained-launch-goal" value={retainedComposerDrafts.launch}
          onChange={event => updateRetainedComposer("launch", event.target.value)}
          rows={4} />
        {retainedLaunchDetails?.acceptanceCriteria ? <div className="form-field">
          <label htmlFor="retained-launch-criteria">{locale === "zh-CN" ? "验收条件（可选，每行一项）" : "Acceptance criteria (optional, one per line)"}</label>
          <textarea id="retained-launch-criteria" value={retainedLaunchDetails.acceptanceCriteria} rows={3}
            onChange={event => changeHeldLaunchDetails({ acceptanceCriteria: event.target.value })}/>
        </div> : null}
        {retainedLaunchDetails && (launchHandoff?.kind === "project" || retainedLaunchDetails.handoffText ||
          retainedLaunchDetails.writePathsText || retainedLaunchDetails.testTargetsText || retainedLaunchDetails.profileRef) ? <fieldset className="project-execution-scope">
          <legend>{locale === "zh-CN" ? "未发送的交接与范围" : "Unsent handoff and scope"}</legend>
          <div className="form-field">
            <label htmlFor="retained-launch-handoff">{locale === "zh-CN" ? "交接说明（可选）" : "Handoff (optional)"}</label>
            <textarea id="retained-launch-handoff" value={retainedLaunchDetails.handoffText} rows={5}
              onChange={event => changeHeldLaunchDetails({ handoffText: event.target.value })}/>
          </div>
          {retainedLaunchDetails.profileRef === "bounded_code_change" || retainedLaunchDetails.writePathsText || retainedLaunchDetails.testTargetsText ? <>
            <div className="form-field">
              <label htmlFor="retained-launch-paths">{locale === "zh-CN" ? "可修改的路径" : "Paths to change"}</label>
              <textarea id="retained-launch-paths" value={retainedLaunchDetails.writePathsText} rows={3}
                onChange={event => changeHeldLaunchDetails({ writePathsText: event.target.value })}/>
            </div>
            <div className="form-field">
              <label htmlFor="retained-launch-tests">{locale === "zh-CN" ? "Pytest 测试目标（可选）" : "Pytest targets (optional)"}</label>
              <textarea id="retained-launch-tests" value={retainedLaunchDetails.testTargetsText} rows={2}
                onChange={event => changeHeldLaunchDetails({ testTargetsText: event.target.value })}/>
            </div>
            <label><input type="checkbox" checked={retainedLaunchDetails.diffCheck}
              onChange={event => changeHeldLaunchDetails({ diffCheck: event.target.checked })}/>
              {locale === "zh-CN" ? "检查 diff 中的空白错误" : "Check the diff for whitespace errors"}</label>
          </> : null}
        </fieldset> : null}
        <button type="button" onClick={() => {
          updateRetainedComposer("launch", "");
          updateRetainedComposer("launchDetails", null);
        }}>
          {copy.discardGoal}
        </button>
      </section>
    ) : commandReady && launchView && launchDraftDismissed ? (
      <section className="card">
        <div className="section-title">
          <h2>{copy.startWork}</h2>
        </div>
        <p className="muted">{copy.draftDismissed}</p>
        <button
          type="button"
          onClick={() => {
            setLaunchDraftDismissed(false);
            routeHeading.current?.focus();
          }}
        >
          {copy.newGoal}
        </button>
      </section>
    ) : commandReady && launchView ? (
      <>
        <LaunchOrchestrator
          presentation={active === "Today" ? "composer" : "standard"}
          previewRequest={previewLaunchRequest}
          locale={locale}
          key={JSON.stringify([
            ownerContext?.principalScope,
            ownerContext?.generation,
          ])}
          workstreams={launchView.workstreams}
          defaultWorkstream={launchView.defaultWorkstream}
          projectExecution={launchHandoff?.kind === "project"}
          projectFollowUp={launchHandoff?.kind === "project" && !!launchHandoff.executionPreview.previous_run}
          continuationMode={launchHandoff?.kind === "project" ? launchHandoff.executionPreview.continuation_mode : undefined}
          coordinatorModel={launchHandoff?.kind === "project" ? launchHandoff.executionPreview.coordinator?.model : undefined}
          executionScope={launchHandoff?.kind === "project" ? launchHandoff.executionPreview.execution_scope : undefined}
          workstreamRef={launchHandoff?.workstreamRef || presentedComposerDrafts.launchWorkstream || undefined}
          lockWorkstream={launchHandoff !== null}
          onWorkstreamChange={workstream => {
            const liveBinding = completeOrchestratorCommandBinding(window.MastermindMissionHost?.commandBinding);
            const liveOwner = liveBinding ? readOwnerContext(liveBinding.port) : null;
            if (!launchHandoff && authRevisionRef.current === authRevision &&
                window.MastermindMissionHost?.auth?.getState().status === "signed_in" &&
                liveBinding === commandBinding &&
                liveOwner?.principalScope === ownerContext?.principalScope &&
                liveOwner?.generation === ownerContext?.generation) {
              retainedComposerScope.current = liveComposerScope;
              updateRetainedComposer("launchWorkstream", workstream);
            }
          }}
          projects={launchView.projects}
          profiles={launchView.profiles}
          frontierModels={launchView.frontierModels}
          initialDraft={presentedComposerDrafts.launch}
          initialDetails={presentedComposerDrafts.launchDetails}
          onDetailsChange={details => {
            const liveBinding = completeOrchestratorCommandBinding(window.MastermindMissionHost?.commandBinding);
            const liveOwner = liveBinding ? readOwnerContext(liveBinding.port) : null;
            if (authRevisionRef.current === authRevision &&
                window.MastermindMissionHost?.auth?.getState().status === "signed_in" &&
                liveBinding === commandBinding &&
                liveOwner?.principalScope === ownerContext?.principalScope &&
                liveOwner?.generation === ownerContext?.generation) {
              retainedComposerScope.current = liveComposerScope;
              updateRetainedComposer("launchDetails", details);
              if (details && !retainedComposerRef.current.launchWorkstream && launchView.defaultWorkstream)
                updateRetainedComposer("launchWorkstream", launchView.defaultWorkstream);
            }
          }}
          onDraftChange={text => {
            const liveBinding = completeOrchestratorCommandBinding(
              window.MastermindMissionHost?.commandBinding);
            const liveOwner = liveBinding ? readOwnerContext(liveBinding.port) : null;
            if (authRevisionRef.current === authRevision &&
                window.MastermindMissionHost?.auth?.getState().status === "signed_in" &&
                liveBinding === commandBinding &&
                liveOwner?.principalScope === ownerContext?.principalScope &&
                liveOwner?.generation === ownerContext?.generation)
            {
              retainedComposerScope.current = liveComposerScope;
              updateRetainedComposer("launch", text);
              if (!retainedComposerRef.current.launchWorkstream && launchView.defaultWorkstream)
                updateRetainedComposer("launchWorkstream", launchView.defaultWorkstream);
            }
          }}
          unavailableReason={
            currentLaunchAvailable
              ? undefined
              : copy.choicesUnavailable
          }
          submitting={heldKind === "launch" && commandBusy}
          blocked={!!currentReopened || heldKind === "consume"}
          error={
            currentRefusal?.kind === "launch"
              ? currentRefusal.reason
              : undefined
          }
          onSubmit={(form: LaunchForm, onComplete) => {
            const binding = completeOrchestratorCommandBinding(
              window.MastermindMissionHost?.commandBinding,
            );
            const liveAuth = window.MastermindMissionHost?.auth?.getState();
            const ctx = binding ? readOwnerContext(binding.port) : null;
            if (!binding || liveAuth?.status !== "signed_in" || !ctx) {
              onComplete({ status: "refused" });
              return;
            }
            // A handoff carries the exact frozen preview it was opened from.
            // Revalidate it against the live owner before anything is
            // prepared: a stale, changed or mismatched source refuses here
            // and leaves the Office draft and the launch goal untouched.
            if (launchHandoff) {
              const liveOwner = readOwnerContext(binding.port);
              const config = readLaunchBindingConfig();
              const enrolled = launchHandoff.kind === "project" ? launchHandoff.executionPreview.binding
                : config ? resolveLaunchBinding(config, launchHandoff.workstreamRef) : null;
              const capturedWorkRef = launchHandoff.kind === "office"
                ? launchHandoff.preview.context.selection?.workRef ?? null : launchHandoff.draft.context.workRef;
              const workstreamAgrees = officeLaunchWorkstreamAgrees(capturedWorkRef,
                enrolled?.workstream ?? null) && form.workstreamRef === launchHandoff.workstreamRef;
              let sourceCurrent = false;
              try {
                sourceCurrent = launchHandoff.kind === "office"
                  ? previewIsCurrent(launchHandoff.preview, office.projection.context)
                  : projectWorkRef === launchHandoff.workstreamRef && projectLaunchContextIsCurrent(
                    launchHandoff.draft,
                    projectExecutionContext(launchHandoff.inspection.read, launchHandoff.inspection.selection),
                    launchHandoff.inspection.isCurrent() && (!launchHandoff.executionPreview.previous_run ||
                      launchHandoff.continuationCurrent?.() === true));
              } catch { /* Malformed or stale captured data never reaches preparation. */ }
              if (!sourceCurrent ||
                  binding !== launchHandoff.binding ||
                  liveOwner?.principalScope !== launchHandoff.principalScope ||
                  liveOwner?.generation !== launchHandoff.generation ||
                  !workstreamAgrees) {
                setCommandRefusal({
                  // The refusal is published against the live owner identity,
                  // so it stays visible under exactly the route that would
                  // have dispatched it.
                  binding,
                  principalScope: ctx.principalScope,
                  generation: ctx.generation,
                  kind: "launch", selectionSeq: selectionSeq.current, sessionKey: null,
                  presentationSeq: commandPresentation.current.seq,
                  reason: locale === "zh-CN"
                    ? launchHandoff.kind === "office"
                      ? "方向交接已不再有效。未准备也未发送任何内容。"
                      : "项目计划已更改。请刷新项目并重新检查，尚未开始工作。"
                    : launchHandoff.kind === "office"
                      ? "The direction handoff is no longer current. Nothing was prepared or sent."
                      : "The project plan is no longer current. Refresh the project and review it before starting work.",
                });
                onComplete({ status: "refused" });
                return;
              }
            }
            const intent = launchHandoff?.kind === "project"
              ? binding.projectExecution?.makeLaunchIntent(form, launchHandoff.draft.context, launchHandoff.executionPreview) ?? null
              : launchIntentFromBinding(binding, form);
            if (launchHandoff && (!intent ||
                intent.targetKey !== launchHandoff.workstreamRef ||
                (launchHandoff.kind === "project" ? intent.payload.work_ref : intent.payload.workstream) !== launchHandoff.workstreamRef)) {
              onComplete({ status: "refused" });
              return;
            }
            beginCommand("launch", intent, onComplete);
          }}
          onCancel={() => {
            // Dismiss an unsent draft only. A held command keeps its original
            // completion handle and durable pointer until owner reconciliation.
            if (
              pendingCommand.current?.kind === "launch" ||
              heldKind === "launch"
            ) return;
            updateRetainedComposer("launch", "");
            updateRetainedComposer("launchDetails", null);
            setLaunchDraftDismissed(true);
            // The Office handoff closes with its own form. The Office draft
            // itself is never cleared by a cancel.
            setLaunchHandoff(null);
            routeHeading.current?.focus();
          }}
        />
        {heldKind === "launch" ? checkStatusControl : null}
      </>
    ) : (
      <section className="card">
        <div className="section-title">
          <div>
            <h2>{copy.startWork}</h2>
          </div>
          <span className="state state-unavailable">{copy.unavailable}</span>
        </div>
        {native && authState?.acquisition && authState.content ? <TransportDiagnosticFields
          connectionDetails
          onConnectionDetailsOpen={() => setDiagnosticTick((n) => n + 1)}
          refreshNativeDiagnostics={refreshNativeDiagnostics}
          snapshot={missionDiagnostics()}
          programsPhase={programsReadPhase}
          programsReason={programsReadReason}
          locale={locale}
        ><code>{COMMAND_ROUTE_UNAVAILABLE}</code></TransportDiagnosticFields> : <><p className="muted">{locale === "zh-CN" ? "暂时无法开始工作。" : "Starting work is unavailable right now."}</p>
        <details
          className="reason-details"
          onToggle={(event) => {
            if ((event.currentTarget as HTMLDetailsElement).open) setDiagnosticTick((n) => n + 1);
          }}
        >
          <summary>{copy.technicalDetails}</summary>
          <code>{COMMAND_ROUTE_UNAVAILABLE}</code>
          <TransportDiagnosticFields
            refreshNativeDiagnostics={refreshNativeDiagnostics}
            snapshot={missionDiagnostics()}
            programsPhase={programsReadPhase}
            programsReason={programsReadReason}
            locale={locale}
          />
        </details></>}
        {heldKind === "launch" ? checkStatusControl : null}
      </section>
    );
  const productAcceptancePanel = (
    <ProductAcceptancePanel
      host={window.MastermindMissionHost}
      currentHost={() => window.MastermindMissionHost}
      selection={selection}
      selectionGeneration={selectionSeq.current}
      currentSelectionGeneration={() => selectionSeq.current}
      authRevision={authRevision}
      enabled={!!d && !selectionRefused && missionSelectionState !== "PENDING" && missionSelectionState !== "UNAVAILABLE"}
      locale={locale}
    />
  );
  const sessionUnavailableCard = (
    <section className="card">
      <div className="section-title">
        <div>
          <h2>{locale === "zh-CN" ? "会话操作" : "Session controls"}</h2>
        </div>
        <span className="state state-unavailable">{locale === "zh-CN" ? "不可用" : "Unavailable"}</span>
      </div>
      <p className="muted">
        {locale === "zh-CN" ? "此处暂时无法向会话发送消息。" : "Sending to a session is unavailable here."}
      </p>
      <details
        className="reason-details"
        onToggle={(event) => {
          if ((event.currentTarget as HTMLDetailsElement).open) setDiagnosticTick((n) => n + 1);
        }}
      >
        <summary>{locale === "zh-CN" ? "技术详情" : "Technical details"}</summary>
        <code>{COMMAND_ROUTE_UNAVAILABLE}</code>
        <TransportDiagnosticFields
          refreshNativeDiagnostics={refreshNativeDiagnostics}
          snapshot={missionDiagnostics()}
          programsPhase={programsReadPhase}
            programsReason={programsReadReason}
          locale={locale}
        />
      </details>
    </section>
  );
  const sessionLive =
    !!sessionBinding && (native||signedIn) && !!sessionOwner && !!sessionTargetKey;
  // A qualified original READ is scoped to the current selected-session
  // owner, even if the old target is now unavailable for NEW sends.
  const presentedSessionAnswer = answerView.visible(
    sessionBinding && sessionOwner && (native||signedIn) ? {
      binding: sessionBinding,
      principalScope: sessionOwner.principalScope,
      generation: sessionOwner.generation,
      selectionSeq: selectionSeq.current,
      authRevision,
    } : null,
  );
  const sessionContinuationUnavailable =
    sessionBinding && !sessionLive ? "SESSION_UNAVAILABLE" : undefined;
  const sessionContinuationPanel = sessionBinding ? (
    <SelectedSessionContinuation
      locale={locale}
      key={JSON.stringify([sessionOwner?.principalScope, sessionOwner?.generation])}
      sessionKey={sessionTargetKey}
      unavailableReason={sessionContinuationUnavailable}
      targetKind={sessionTargetKind}
      onTargetKindChange={changeSessionTargetKind}
      targetKindLocked={
        sessionPending.current !== null || sessionPointer !== null ||
        sessionPointerError || sessionRecovering
      }
      nativeResult={sessionNative && sessionNative.binding === sessionBinding &&
        sessionNative.principalScope === sessionOwner?.principalScope &&
        sessionNative.generation === sessionOwner?.generation &&
        sessionNative.selectionSeq === selectionSeq.current &&
        sessionNative.targetKind === sessionTargetKind
        ? sessionNative.result
        : null}
      status={sessionStatus}
      retainedPointer={sessionPointer}
      reading={!!sessionOwner && sessionReading}
      recoveryRequired={!!sessionOwner && sessionPointerError}
      recovering={sessionRecovering}
      sending={!!sessionPending.current}
      refusalReason={
        sessionRefusal &&
        sessionRefusal.binding === sessionBinding &&
        sessionRefusal.principalScope === sessionOwner?.principalScope &&
        sessionRefusal.generation === sessionOwner?.generation
          ? sessionRefusal.reason
          : undefined
      }
      onContinue={beginSessionCommand}
      onRecover={checkSessionStatus}
      onRequalify={signedIn && !sessionOwner && sessionControl ? () => {
        invalidateSessionPresentation();
        void sessionControl.refresh(sessionSelection);
      } : undefined}
    />
  ) : null;
  const sessionPanel = !signedIn && passiveExpiryHold.current &&
    retainedComposerDrafts.session ? (
    <section className="card" aria-label="Retained Session draft">
      <h2>Unsent session message</h2>
      <p className="muted">Authentication expired. Copy or discard this local draft; sending is disabled until sign-in.</p>
      <label htmlFor="retained-session-message">Message</label>
      <textarea id="retained-session-message" value={retainedComposerDrafts.session}
        onChange={event => updateRetainedComposer("session", event.target.value)}
        rows={4} />
      <button type="button" onClick={() => updateRetainedComposer("session", "")}>
        Discard session message
      </button>
    </section>
  ) : sessionBinding ? (
    sessionContinuationPanel
  ) : commandBinding ? (
    sessionExact && commandView?.session ? (
      <>
        <SessionWorkspace
          sessionKey={commandView.session.sessionKey}
          title={commandView.session.title}
          messages={commandView.session.messages}
          observedAt={commandView.session.observedAt}
          connection={commandView.session.connection}
          coverage={commandView.session.coverage}
          turnBusy={commandView.session.turnBusy}
          sending={heldKind === "message" && commandBusy}
          initialDraft={presentedComposerDrafts.session}
          onDraftChange={text => {
            const liveBinding = completeOrchestratorCommandBinding(
              window.MastermindMissionHost?.commandBinding);
            const liveView = liveBinding ? readCommandView(liveBinding) : null;
            if (authRevisionRef.current === authRevision &&
                window.MastermindMissionHost?.auth?.getState().status === "signed_in" &&
                liveBinding === commandBinding &&
                liveView?.session?.sessionKey === commandView.session?.sessionKey)
            {
              retainedComposerScope.current = liveComposerScope;
              updateRetainedComposer("session", text);
            }
          }}
          unavailableReason={commandView.session.unavailableReason}
          error={currentRefusal && currentRefusal.kind !== "launch"
            ? currentRefusal.reason : commandView.session.error}
          stopLabel={commandView.session.stopLabel}
          stopping={heldKind === "stop" && commandBusy}
          onSend={(text, onComplete) => {
            const presented = commandView.session;
            const binding = completeOrchestratorCommandBinding(
              window.MastermindMissionHost?.commandBinding,
            );
            const liveAuth = window.MastermindMissionHost?.auth?.getState();
            const ctx = binding ? readOwnerContext(binding.port) : null;
            const view = binding ? readCommandView(binding) : null;
            const current = selection;
            if (
              !presented ||
              !binding ||
              liveAuth?.status !== "signed_in" ||
              !ctx ||
              !sessionMatchesSelection(view?.session ?? null, current) ||
              view?.session?.sessionKey !== presented.sessionKey
            ) {
              onComplete({ status: "refused" });
              return;
            }
            const intent = messageIntentFromBinding(
              binding,
              presented.sessionKey,
              text,
            );
            beginCommand("message", intent, onComplete);
          }}
          onStop={
            commandView.session.stopLabel
              ? (onComplete) => {
                  const presented = commandView.session;
                  const binding = completeOrchestratorCommandBinding(
                    window.MastermindMissionHost?.commandBinding,
                  );
                  const liveAuth =
                    window.MastermindMissionHost?.auth?.getState();
                  const ctx = binding ? readOwnerContext(binding.port) : null;
                  const view = binding ? readCommandView(binding) : null;
                  if (
                    !presented ||
                    !binding ||
                    liveAuth?.status !== "signed_in" ||
                    !ctx ||
                    !sessionMatchesSelection(
                      view?.session ?? null,
                      selection,
                    ) ||
                    view?.session?.sessionKey !== presented.sessionKey
                  ) {
                    onComplete({ status: "refused" });
                    return;
                  }
                  const intent = stopIntentFromBinding(
                    binding,
                    presented.sessionKey,
                  );
                  beginCommand("stop", intent, onComplete);
                }
              : undefined
          }
        />
        {heldKind === "message" || heldKind === "stop"
          ? checkStatusControl
          : null}
      </>
    ) : (
      <>
        {sessionUnavailableCard}
        {heldKind === "message" || heldKind === "stop"
          ? checkStatusControl
          : null}
      </>
    )
  ) : (
    // No command route is installed at all: Conversation shows the same fixed
    // unavailable code as Work, with no fabricated session or dispatch state.
    sessionUnavailableCard
  );
  const directResultPanel = directSelected && selection ? <DirectNativeResultPanel
    key={JSON.stringify([ownerContext?.principalScope,ownerContext?.generation,selection.workRef,selection.rootJobId,commandSelectionRevision])}
    locale={locale} selection={{work_ref:selection.workRef,job_id:selection.rootJobId,attempt_id:null}}
    read={commandReady ? commandBinding?.directNative?.read : undefined}
    inspectCorrection={commandReady ? commandBinding?.directNative?.inspectCorrection : undefined}
    onCorrect={(selected,fence,complete)=>{
      const live=completeOrchestratorCommandBinding(window.MastermindMissionHost?.commandBinding);
      const ctx=live ? readOwnerContext(live.port) : null;
      if(commandSelectionRevision!==selectionSeq.current||!live||live!==commandBinding||!ctx||
        ctx.principalScope!==ownerContext?.principalScope||ctx.generation!==ownerContext?.generation){complete({status:'refused'});return;}
      beginCommand('stop',live.directNative?.makeCorrectionIntent?.(selected,fence)??null,complete);
    }}
    held={heldKind==="consume" || heldKind==="stop" || currentReopened?.pointer?.kind==="consume" || currentReopened?.pointer?.kind==="stop"}
    recovery={heldKind==="consume" || heldKind==="stop" ? checkStatusControl : null}
    onConsume={(selected,digest,complete)=>{
      const live=completeOrchestratorCommandBinding(window.MastermindMissionHost?.commandBinding);
      const ctx=live ? readOwnerContext(live.port) : null;
      if(commandSelectionRevision!==selectionSeq.current||!live||live!==commandBinding||!ctx||
        ctx.principalScope!==ownerContext?.principalScope||ctx.generation!==ownerContext?.generation){complete({status:"refused"});return;}
      const intent=live.directNative?.makeConsumeIntent(selected,digest)??null;
      beginCommand("consume",intent,complete);
    }} /> : null;
  const pickResult = (sel: ResultSelection) => {
    const valid = normalizeResultSelection(sel);
    if (!valid) return;
    const compoundRead = window.MastermindMissionHost?.readMissionResult;
    if (compoundRead) {
      resultController.current?.abort();
      const ticket = ++compoundTicket.current;
      missionRequest.current += 1;
      resultRequest.current += 1;
      const held = office.beginMissionResult();
      const host = window.MastermindMissionHost;
      const hostGeneration = host?.invalidationGeneration?.();
      const selectionAtStart = liveSelection.current;
      const authAtStart = liveAuthRevision.current;
      setResultState({ kind: "PENDING", selection: valid });
      const controller = new AbortController();
      resultController.current = controller;
      // A newer ticket, selection, or auth epoch owns the screen. Its
      // callback must never clear the replacement ticket or Office pair.
      const newerOwner = () => compoundTicket.current !== ticket
        || liveSelection.current !== selectionAtStart
        || liveAuthRevision.current !== authAtStart;
      // Host identity/generation can drift without notifying the original
      // subscription. That is still this ticket's cancellation, not a
      // reason to strand its card in PENDING.
      const hostChanged = () => window.MastermindMissionHost !== host
        || host?.invalidationGeneration?.() !== hostGeneration;
      const superseded = () => newerOwner() || hostChanged();
      // The mounted typed method can be replaced without changing the raw
      // client or the host object. Raw identity checks do not cover that.
      const typedHeld = () => window.MastermindMissionHost?.readMissionResult === compoundRead;
      const withholdOwned = (reason: string) => {
        if (newerOwner()) return;
        office.supersedePair();
        compoundRetention.current = null;
        setResultState({ kind: "UNAVAILABLE", selection: valid, reason });
      };
      Promise.resolve()
        .then(() => {
          if (superseded()) {
            withholdOwned("READ_CANCELLED");
            return undefined;
          }
          if (controller.signal.aborted || !typedHeld()) {
            withholdOwned("READ_CANCELLED");
            return undefined;
          }
          return compoundRead({ ...valid, signal: controller.signal });
        })
        .then((decoded) => {
          if (decoded === undefined) return;
          if (superseded()) {
            withholdOwned("READ_CANCELLED");
            return;
          }
          if (!typedHeld()) {
            withholdOwned("READ_CANCELLED");
            return;
          }
          // The host decoder already checks all five selection fields, but
          // App must fail closed if a replaced typed host returns an otherwise
          // well-formed pair belonging to a different selected Job/Attempt.
          if (!decoded.selection
            || decoded.selection.workRef !== valid.workRef
            || decoded.selection.rootJobId !== valid.rootJobId
            || decoded.selection.jobId !== valid.jobId
            || decoded.selection.attemptId !== valid.attemptId
            || decoded.selection.resultEnvelopeDigest !== valid.resultEnvelopeDigest) {
            withholdOwned("MISSION_RESULT_RESPONSE_INVALID");
            return;
          }
          if (decoded.availability !== "AVAILABLE" || !decoded.mission || !decoded.roleResult) {
            withholdOwned(decoded.reasonCodes.join(", ") || "SOURCE_UNAVAILABLE");
            return;
          }
          // The nested Result and its source observation each carry their own
          // five-field selector. A substituted typed method could forge a
          // matching compound selection around a sibling Job's actual Result.
          const sameWireSelection = (
            wire: ResultEnvelopeDigestShape["selection"] | null | undefined,
          ) => !!wire
            && wire.work_ref === valid.workRef
            && wire.root_job_id === valid.rootJobId
            && wire.job_id === valid.jobId
            && wire.attempt_id === valid.attemptId
            && wire.result_envelope_digest === valid.resultEnvelopeDigest;
          const roleView = decoded.roleResult.result;
          if (!sameWireSelection(decoded.roleResult.selection)
            || !sameWireSelection(decoded.roleResult.source_observation?.selection)
            || (roleView !== null && (!roleView?.selection
              || roleView.selection.root_job_id !== valid.rootJobId
              || roleView.selection.job_id !== valid.jobId
              || roleView.selection.attempt_id !== valid.attemptId
              || roleView.selection.result_envelope_digest !== valid.resultEnvelopeDigest))) {
            withholdOwned("MISSION_RESULT_RESPONSE_INVALID");
            return;
          }
          // No async boundary between these fences and the synchronous
          // Office accept. Post-accept fences could leave a published pair.
          const accepted = office.acceptMissionResult(
            held, decoded.mission, decoded.roleResult, new Date().toISOString(),
          );
          if (accepted.kind !== "observed") {
            withholdOwned(accepted.reason);
            return;
          }
          compoundRetention.current = {
            mission: decoded.mission,
            selection: liveSelection.current,
            authRevision: liveAuthRevision.current,
          };
          const { result_refs: _refs, ...body } = decoded.mission;
          setMission({ ...body, schema: "mastermind.mission_workspace.v2" });
          setMissionV3(decoded.mission);
          setResultState({ kind: "READY", selection: valid, document: decoded.roleResult });
        })
        .catch((err: Error) => {
          if (superseded()) {
            withholdOwned("READ_CANCELLED");
            return;
          }
          withholdOwned(
            err?.message === "MISSION_RESULT_RESPONSE_INVALID"
              ? "MISSION_RESULT_RESPONSE_INVALID"
              : err?.message === "READ_CANCELLED"
                ? "READ_CANCELLED"
                : "RESULT_SOURCE_UNAVAILABLE",
          );
        });
      return;
    }
    if (!window.MastermindMissionHost?.readResult) {
      setResultState({
        kind: "UNAVAILABLE",
        selection: valid,
        reason: "QUALIFIED_RESULT_READ_UNAVAILABLE",
      });
      return;
    }
    resultController.current?.abort();
    const context = resultContext;
    setResultState({ kind: "PENDING", selection: valid });
    const current = ++resultRequest.current;
    const controller = new AbortController();
    resultController.current = controller;
    let raceAborted = false;
    Promise.resolve()
      .then(() =>
        window.MastermindMissionHost!.readResult!({
          workRef: valid.workRef,
          rootJobId: valid.rootJobId,
          jobId: valid.jobId,
          attemptId: valid.attemptId,
          resultEnvelopeDigest: valid.resultEnvelopeDigest,
          signal: controller.signal,
        }),
      )
      .then((raw) => {
        if (
          resultRequest.current !== current ||
          raceAborted ||
          currentResultContext.current !== context ||
          controller.signal.aborted
        )
          return;
        const decoded = decodeResultEnvelope(raw, valid);
        if (!decoded) {
          setResultState({
            kind: "UNAVAILABLE",
            selection: valid,
            reason: "RESULT_RESPONSE_INVALID",
          });
          return;
        }
        setResultState({ kind: "READY", selection: valid, document: decoded });
      })
      .catch((err: Error) => {
        if (
          resultRequest.current !== current ||
          raceAborted ||
          currentResultContext.current !== context ||
          controller.signal.aborted
        )
          return;
        if (err?.message === "READ_CANCELLED") {
          raceAborted = true;
          return;
        }
        setResultState({
          kind: "UNAVAILABLE",
          selection: valid,
          reason: "RESULT_SOURCE_UNAVAILABLE",
        });
      });
  };
  // Open exactly the indexed worker return through the *existing* Result
  // owner, never by manufacturing a URL, another read path or permission.
  const workerResultHost = window.MastermindMissionHost;
  const workerResultEpoch = workerResultHost?.invalidationGeneration?.();
  const openOfficeWorkerResult = (input: ResultSelection) => {
    const valid = normalizeResultSelection(input);
    const host = window.MastermindMissionHost;
    const user = host?.auth?.getState();
    const source = office.projection.mission;
    const indexed = missionV3 && isDocv3(missionV3) ? missionV3 : null;
    if (!valid || !host?.readResult || host !== workerResultHost ||
        workerResultEpoch === undefined ||
        host.invalidationGeneration?.() !== workerResultEpoch ||
        user?.status !== "signed_in" || !user.acquisition ||
        authState?.status !== "signed_in" || !authState.acquisition ||
        source.source.state !== "CURRENT" ||
        source.value?.schema !== "mastermind.mission_workspace.v3" ||
        !indexed || !selection ||
        valid.workRef !== selection.workRef || valid.rootJobId !== selection.rootJobId ||
        source.value.program.work_ref !== selection.workRef ||
        source.value.mission.root_job_id !== selection.rootJobId ||
        indexed.result_refs.snapshot_digest !== source.value.result_refs.snapshot_digest ||
        JSON.stringify(indexed.result_refs.generation) !== JSON.stringify(source.value.result_refs.generation))
      return;
    const c = source.value.children.items.find(row =>
      row.job_id === valid.jobId && row.latest_attempt?.attempt_id === valid.attemptId);
    const exact = c ? qualifyWorkerResultRef(source.value, c) : null;
    const stillIndexed = indexed.result_refs.refs.some(ref =>
      ref.root_job_id === valid.rootJobId && ref.job_id === valid.jobId &&
      ref.attempt_id === valid.attemptId && ref.result_envelope_digest === valid.resultEnvelopeDigest);
    if (!exact || !stillIndexed ||
        exact.resultEnvelopeDigest !== valid.resultEnvelopeDigest) return;
    // This user interaction is the explicit permitted read. The Result owner
    // rechecks identity, source and exact digest during the bounded acquisition.
    setActive("Projects");
    setProjectTab("Overview");
    pickResult(exact);
  };
  const resultRefs =
    d && missionV3 && isDocv3(missionV3) ? (
      <ResultRefs
        d={missionV3}
        onPick={pickResult}
        selectedKey={
          resultState.kind === "READY" || resultState.kind === "PENDING"
            ? `${resultState.selection.jobId}|${resultState.selection.attemptId}|${resultState.selection.resultEnvelopeDigest}`
            : null
        }
        disabled={!authState?.acquisition}
      />
    ) : null;
  const navigateOperationalView = (view: OperationalView) => {
    setProjectTab(null);
    setActive(view);
  };
  const programsReadAvailable =
    (typeof window.MastermindMissionHost?.readProgramsObservation === "function" ||
      typeof window.MastermindMissionHost?.readPrograms === "function") &&
    (!authState || authState.acquisition);
  const refreshProjects = () => {
    setIndex({ programs: [], state: "PENDING", reason: "SOURCE_READ_PENDING" });
    setProgramRevision((revision) => revision + 1);
  };
  const programsRefreshControl = (
    <button
      type="button"
      // Pending reads stay focusable; unavailable acquisition stays natively disabled.
      disabled={!programsReadAvailable}
      aria-disabled={index.state === "PENDING" || !programsReadAvailable}
      onClick={() => {
        if (index.state === "PENDING" || !programsReadAvailable) return;
        refreshProjects();
      }}
    >
      {locale === "zh-CN" ? "刷新项目" : "Refresh Projects"}
    </button>
  );
  const workReadAvailable =
    typeof window.MastermindMissionHost?.readWork === "function" &&
    (!authState || authState.acquisition);
  const workRefreshControl = (
    <button
      type="button"
      // Native disabled blurs the focused button in Chrome. Guard pending reads below.
      disabled={!workReadAvailable}
      aria-disabled={workState.kind === "PENDING" || !workReadAvailable}
      onClick={() => {
        if (workState.kind === "PENDING" || !workReadAvailable) return;
        setWorkState({ kind: "PENDING" });
        setWorkRevision((revision) => revision + 1);
      }}
    >
      Refresh Work
    </button>
  );
  const retainedResultHost = window.MastermindMissionHost;
  const retainedHostGeneration = retainedResultHost?.invalidationGeneration?.() ?? 0;
  // Stable fixed READ ports. Each consumer also fences source/auth changes;
  // callbacks recheck the actual currently installed host at acquisition time.
  const projectReaders = useMemo(() => {
    const host = retainedResultHost;
    return {
      canRead: () => {
        const auth = host?.auth?.getState();
        return window.MastermindMissionHost === host && authRevisionRef.current === authRevision &&
          auth?.status === "signed_in" && Boolean(auth.acquisition);
      },
      generation: host?.invalidationGeneration ? () => host.invalidationGeneration!() : undefined,
      activity: host?.readRetainedActivity ? (request: Parameters<NonNullable<MissionHost["readRetainedActivity"]>>[0]) => host.readRetainedActivity!(request) : undefined,
      plan: host?.readProjectPlan ? (request: Parameters<NonNullable<MissionHost["readProjectPlan"]>>[0]) => host.readProjectPlan!(request) : undefined,
      journal: host?.readProjectJournal ? ({workRef, signal}: {workRef: string; signal: AbortSignal}) => host.readProjectJournal!({work_ref: workRef, signal}) : undefined,
      archive: host?.readProjectArchive ? (request: Parameters<NonNullable<MissionHost["readProjectArchive"]>>[0]) => host.readProjectArchive!(request) : undefined,
      archivePage: host?.readProjectArchivePage ? (request: Parameters<NonNullable<MissionHost["readProjectArchivePage"]>>[0]) => host.readProjectArchivePage!(request) : undefined,
      direction: host?.readProjectDirection ? (request: Parameters<NonNullable<MissionHost["readProjectDirection"]>>[0]) => host.readProjectDirection!(request) : undefined,
      association: host?.readProjectSessionAssociation ? (request: Parameters<NonNullable<MissionHost["readProjectSessionAssociation"]>>[0]) => host.readProjectSessionAssociation!(request) : undefined,
      autonomy: host?.readAutonomyPolicy ? (request: Parameters<NonNullable<MissionHost["readAutonomyPolicy"]>>[0]) => host.readAutonomyPolicy!(request) : undefined,
    };
  }, [retainedResultHost, authRevision]);
  let archiveHostGeneration: number | null = null;
  try {
    const value = projectReaders.generation?.();
    if (typeof value === "number" && Number.isSafeInteger(value) && value >= 0) archiveHostGeneration = value;
  } catch { /* Missing current owner cannot qualify an archive read. */ }
  const archiveScopeKey = JSON.stringify([authRevision, archiveHostGeneration]);
  const genuineProjectDraft: KnowledgeDraftPort = {projection: observedConversation.projection,
    text: observedConversation.draft, revision: observedConversation.draftRevision,
    insertion: observedConversation.draftInsertion, append: observedConversation.appendSource,
    undo: observedConversation.undoSource, edit: () => showCurrentConversation()};
  const projectDraftOwner = useRef({host: retainedResultHost, generation: archiveHostGeneration,
    context: observedConversation.projection.context, port: genuineProjectDraft});
  projectDraftOwner.current = {host: retainedResultHost, generation: archiveHostGeneration,
    context: observedConversation.projection.context, port: genuineProjectDraft};
  // An explicit guarded source return may focus the existing notes owner once.
  const projectDraftReturnFocus = useRef<{
    witness: NonNullable<ReturnType<ProjectSourceDraftPort["readWitness"]>>;
    host: typeof retainedResultHost;
    authRevision: number;
  } | null>(null);
  const projectDraftMethods = useMemo(() => {
    const readWitness: ProjectSourceDraftPort["readWitness"] = () => {
      const owner = projectDraftOwner.current, host = owner.host, auth = host?.auth;
      const getState = auth?.getState, getGeneration = host?.invalidationGeneration;
      try {
        if (!host || !auth || !getState || !getGeneration || owner.generation === null ||
            window.MastermindMissionHost !== host) return null;
        const state = getState.call(auth), generation = getGeneration.call(host);
        if (state.status !== "signed_in" || state.content !== true || generation !== owner.generation ||
            owner.context.authGeneration !== authRevisionRef.current || projectDraftOwner.current !== owner ||
            window.MastermindMissionHost !== host || host.auth !== auth || auth.getState !== getState ||
            host.invalidationGeneration !== getGeneration) return null;
        const binding = knowledgeDraftBinding(owner.context, owner.port);
        return binding && owner.context.selection ? {workRef: owner.context.selection.workRef,
          binding, revision: owner.port.revision} : null;
      } catch { return null; }
    };
    return {readWitness,
      append: ((source, revision) => {
        const owner = projectDraftOwner.current, witness = readWitness();
        return !!witness && witness.revision === revision && projectDraftOwner.current === owner &&
          owner.port.append(source, revision);
      }) as ProjectSourceDraftPort["append"],
      undo: ((identity, revision) => {
        const owner = projectDraftOwner.current, witness = readWitness();
        return !!witness && witness.revision === revision && projectDraftOwner.current === owner &&
          owner.port.undo(identity, revision);
      }) as ProjectSourceDraftPort["undo"],
      edit: () => {
        const witness = readWitness();
        if (!witness) return;
        projectDraftReturnFocus.current = {witness, host: projectDraftOwner.current.host,
          authRevision: authRevisionRef.current};
        projectDraftOwner.current.port.edit?.();
      }};
  }, []);
  const projectSourceDraftPort: ProjectSourceDraftPort = {text: genuineProjectDraft.text,
    revision: genuineProjectDraft.revision, insertion: genuineProjectDraft.insertion, ...projectDraftMethods};

  useLayoutEffect(() => {
    const intent = projectDraftReturnFocus.current;
    if (!intent) return;
    // A passive render cannot create or revive a consumed gesture.
    projectDraftReturnFocus.current = null;
    const current = projectDraftMethods.readWitness();
    if (active !== "Conversations" || intent.host !== projectDraftOwner.current.host ||
        intent.authRevision !== authRevisionRef.current || !current ||
        current.workRef !== intent.witness.workRef || current.binding !== intent.witness.binding ||
        current.revision !== intent.witness.revision) return;
    // Scope the unique mounted window without adding a layout wrapper.
    const windows = document.getElementById("content")?.querySelectorAll<HTMLElement>(".conversation-window");
    if (!windows || windows.length !== 1) return;
    const region = windows[0];
    const target = region.querySelector<HTMLElement>(".conversation-notes textarea") ??
      region.querySelector<HTMLElement>(".conversation-notes-trigger");
    target?.focus();
    target?.scrollIntoView?.({block: "center"});
  });

  const [knowledgeMode, setKnowledgeMode] = useState<"project" | "retained">("project");
  const [projectSearchSelected, setProjectSearchSelected] = useState(true);
  const [requestedProjectFile, setRequestedProjectFile] = useState<KnowledgeLibraryProps["requestedFile"]>();
  const [savedConversationNavigation, setSavedConversationNavigation] = useState<SavedConversationNavigation | null>(null);
  const legacyProjectHistoryOwner = sessionBinding?.port.projectHistory;
  const hasProjectLibrary = Boolean(retainedResultHost?.readProjectKnowledgeCatalogue);
  const hasProjectSearch = Boolean(retainedResultHost?.projectFilesSearch || retainedResultHost?.session?.createProjectHistoryReader || legacyProjectHistoryOwner);
  const catalogueWorkRef = catalogueProject?.authRevision === authRevision &&
    catalogueProject.epoch === programIndexEpoch ? catalogueProject.workRef : null;
  const requestedProjectWorkRef = catalogueProject ? catalogueWorkRef : selection?.workRef ?? null;
  const currentProjectCards = office.projection.programs.source.state === "CURRENT" &&
    index.state === "AVAILABLE" && requestedProjectWorkRef
      ? index.programs.filter(card => card.workRef === requestedProjectWorkRef) : [];
  const projectWorkRef = currentProjectCards.length === 1 ? currentProjectCards[0].workRef : null;
  const projectSearchRegion = useRef<HTMLElement>(null);
  const sourceSearchReturn = useRef<{host: typeof retainedResultHost; auth: number; generation: number | null; work: string | null; epoch: number} | null>(null);
  useLayoutEffect(() => {
    const intent = sourceSearchReturn.current;
    if (!intent) return;
    sourceSearchReturn.current = null;
    if (active !== "Search" || intent.host !== window.MastermindMissionHost || intent.host !== retainedResultHost ||
        intent.auth !== authRevision || intent.generation !== archiveHostGeneration ||
        intent.work !== projectWorkRef || intent.epoch !== programIndexEpoch) return;
    projectSearchRegion.current?.querySelector<HTMLInputElement>('.project-search__input')?.focus();
  });
  const historyReadState = useRef({host: retainedResultHost, authRevision, workRef: projectWorkRef,
    owner: catalogueListOwner.current, index, programs: office.projection.programs,
    selectionEpoch: cataloguePresentationSequence.current});
  historyReadState.current = {host: retainedResultHost, authRevision, workRef: projectWorkRef,
    owner: catalogueListOwner.current, index, programs: office.projection.programs,
    selectionEpoch: cataloguePresentationSequence.current};
  const projectConversationReadScope = {host: retainedResultHost,
    workRef: projectWorkRef, authGeneration: authRevision, hostGeneration: retainedHostGeneration,
    selectionGeneration: JSON.stringify([programIndexEpoch, selectionSeq.current,
      cataloguePresentationSequence.current, office.projection.context.revisions.programs]),
    canReadCurrentProject: () => {
      const current = historyReadState.current;
      return !!current.workRef && current.host === window.MastermindMissionHost &&
        current.authRevision === authRevisionRef.current &&
        current.selectionEpoch === cataloguePresentationSequence.current &&
        current.owner === catalogueListOwner.current && conversationListOwnerCurrent(current.owner, false) &&
        current.programs.source.state === "CURRENT" && current.index.state === "AVAILABLE" &&
        current.index.programs.filter(card => card.workRef === current.workRef).length === 1;
    }, locale, theme};
  const projectConversationHistory = useProjectConversationHistory(projectConversationReadScope);
  // A project READ has no current native-session target requirement. Older
  // hosts keep their existing selected-session source only when this factory
  // is absent; a denied/unqualified new owner never falls back to it.
  const projectHistoryOwner = retainedResultHost?.session?.createProjectHistoryReader
    ? projectConversationHistory.history?.owner : legacyProjectHistoryOwner;
  const projectConversations = useProjectConversations({...projectConversationReadScope,
    renderFreshContinuation: source => <FreshConversationContinuation locale={locale}
      active={active === "Projects"} binding={freshAttendedBinding} host={freshHost} authGeneration={authRevision}
      entry={{kind: "reference", window: source.window, current: source.current}}
      turnDraft={freshTurnDraft} onUnresolvedChange={reportFreshAttendedOriginal}
      onReadCurrent={reportFreshReferenceRead} onOriginalSettled={onFreshOriginalSettled}/>});
  const [knowledgeRefresh, setKnowledgeRefresh] = useState(0);
  const knowledgePorts = useMemo(() => {
    const host=retainedResultHost;
    return {readContext:host?.readSourceOperationContext
      ? (request:Parameters<NonNullable<MissionHost["readSourceOperationContext"]>>[0])=>host.readSourceOperationContext!(request):undefined,
      transport:host?.sourceOperations};
  },[retainedResultHost,authRevision]);
  const knowledgePublication=useProjectKnowledgeWorkspace({workRef:projectWorkRef,
    authGeneration:authRevision,hostGeneration:archiveHostGeneration,canRead:projectReaders.canRead,
    readContext:knowledgePorts.readContext,transport:knowledgePorts.transport,store:commandBinding?.store,
    onSourceObserved:()=>setKnowledgeRefresh(value=>value+1)});
  const [knowledgeEditor,setKnowledgeEditor]=useState<{scope:string;mode:"file"|"preference"|"correction";
    context:KnowledgeLibrarySourceContext;requestId:string;memory:ProjectMemoryDocument|null;discovery:ProjectDiscoverySource|null}|null>(null);
  const currentKnowledgeEditor=knowledgeEditor?.scope===knowledgePublication.scope?knowledgeEditor:null;
  hasUnsentUserText.current ||= !!currentKnowledgeEditor;
  useLayoutEffect(()=>{if(knowledgeEditor && !currentKnowledgeEditor)setKnowledgeEditor(null);},[knowledgeEditor,currentKnowledgeEditor]);
  const knowledgeWriteAvailable=!!(commandBinding?.store && knowledgePorts.readContext && knowledgePorts.transport &&
    projectWorkRef && projectReaders.canRead());
  const openKnowledgeEditor=(mode:"file"|"preference"|"correction",context:KnowledgeLibrarySourceContext,memory:ProjectMemoryDocument|null,discovery:ProjectDiscoverySource|null=null)=>{
    if(!knowledgeWriteAvailable || context.workRef!==projectWorkRef ||
      ["submitting","checking","unknown"].includes(knowledgePublication.controller?.getState().status??"idle"))return;
    try {
      knowledgePublication.currentSource(context);
      if(mode==='correction'&&(!discovery||!knowledgePublication.currentDiscovery(discovery)))return;
      if(!knowledgePublication.startDraft())return;
      const bytes=new Uint8Array(20);globalThis.crypto.getRandomValues(bytes);
      const suffix=Array.from(bytes,byte=>byte.toString(16).padStart(2,"0")).join("");
      setKnowledgeEditor({scope:knowledgePublication.scope,mode,context:{...context},memory,discovery,
        requestId:`mmos-project-${mode==="file"?"file-add":mode==='correction'?'discovery-correct':"preference-set"}-${suffix}`});
    } catch { /* No current source or original identifier means no editor action. */ }
  };
  const knowledgePublicationPanel=<>
    {currentKnowledgeEditor && (currentKnowledgeEditor.mode==='correction'
      ? currentKnowledgeEditor.discovery&&<ProjectDiscoveryCorrectionEditor key={currentKnowledgeEditor.requestId}
          source={currentKnowledgeEditor.discovery} requestId={currentKnowledgeEditor.requestId} locale={locale}
          phase={knowledgePublication.phase} current={knowledgePublication.currentDiscovery}
          onPrepare={knowledgePublication.prepareCorrection} onClose={()=>setKnowledgeEditor(null)} onCheckOriginal={knowledgePublication.checkOriginal}
          onInspectOriginal={knowledgePublication.inspectOriginal}/>
      :currentKnowledgeEditor.mode==="file"
      ? <ProjectKnowledgeEditor key={currentKnowledgeEditor.requestId} mode="file"
          sourceContext={currentKnowledgeEditor.context} requestId={currentKnowledgeEditor.requestId}
          authGeneration={authRevision} hostGeneration={archiveHostGeneration} locale={locale}
          current={knowledgePublication.currentSource} phase={knowledgePublication.phase}
          onSubmitFile={knowledgePublication.prepare} onClose={()=>setKnowledgeEditor(null)}
          onCheckOriginal={knowledgePublication.checkOriginal}/>
      : <ProjectKnowledgeEditor key={currentKnowledgeEditor.requestId} mode="preference"
          sourceContext={currentKnowledgeEditor.context} requestId={currentKnowledgeEditor.requestId}
          authGeneration={authRevision} hostGeneration={archiveHostGeneration} locale={locale}
          initialValue={currentKnowledgeEditor.memory?.value??""} expectedPreferenceRevision={currentKnowledgeEditor.memory?.source.contentSha256??null}
          current={knowledgePublication.currentSource} phase={knowledgePublication.phase}
          onSubmitPreference={knowledgePublication.prepare} onClose={()=>setKnowledgeEditor(null)}
          onCheckOriginal={knowledgePublication.checkOriginal}/>)}
    {currentKnowledgeEditor && knowledgePublication.phase==="prepared" && knowledgePublication.prepared && <section className="card" aria-label={locale==="zh-CN"?"检查准备好的更改":"Review prepared changes"}>
      <h2>{locale==="zh-CN"?"检查你的更改":"Review your changes"}</h2>
      <p>{locale==="zh-CN"?"尚未发布。确认后才会提交这一次更改。":"Nothing has been published. Publish submits this original change once."}</p>
      {knowledgePublication.prepared.request.schema==='mastermind.project_discovery_correct_request.v1'
        ? currentKnowledgeEditor.discovery&&<><DiscoveryCorrectionReview request={knowledgePublication.prepared.request} source={currentKnowledgeEditor.discovery} locale={locale}/>
          <details><summary>{locale==='zh-CN'?'更改的来源记录':'Changed source records'}</summary><ul>{knowledgePublication.prepared.response.preview.postimages.map(image=><li key={image.path}>{image.path}</li>)}</ul></details></>
        :<pre className="visible-text">{"file" in knowledgePublication.prepared.request
        ? `${knowledgePublication.prepared.request.file.display_name}\n${knowledgePublication.prepared.request.file.content_utf8}`
        : knowledgePublication.prepared.request.value}</pre>}
      <button type="button" disabled={!knowledgePublication.canPublish} onClick={knowledgePublication.publish}>{locale==="zh-CN"?"发布更改":"Publish changes"}</button>
    </section>}
    {knowledgeWriteAvailable && <section className="card" aria-label={locale==="zh-CN"?"原始发布状态":"Original publication status"}>
      {knowledgePublication.phase==="proposal-published" || knowledgePublication.phase==="unknown"
        ? <p>{locale==="zh-CN"?"项目源尚未确认保存。请检查原始发布，不要重复提交。":"The project source has not confirmed this save. Check the original publication; do not submit it again."}</p>:null}
      {knowledgePublication.phase==="publication-held"?<p>{locale==="zh-CN"?"之前的项目操作尚未确定。请使用它的原始控件检查；这些更改尚未提交。":"A previous project action is unresolved. Use its original controls; these changes have not been submitted."}</p>:null}
      {knowledgePublication.phase==="source-published"?<p>{locale==="zh-CN"?"已保存到项目源。":"Saved to the project source."}</p>:null}
      <button type="button" onClick={knowledgePublication.checkOriginal}>{locale==="zh-CN"?"检查发布状态":"Check publication status"}</button>
    </section>}
  </>;
  // Admission gates address the canonical programme, not an inferred Runtime
  // root. The owner independently brackets its exact Agent OS source and grant.
  const admissionPorts = useMemo(() => {
    const host=retainedResultHost;
    return {
      read: host?.readProjectAdmissionControl ? (request: Parameters<NonNullable<MissionHost["readProjectAdmissionControl"]>>[0]) => host.readProjectAdmissionControl!(request) : undefined,
      transport: host?.pauseProjectAdmission && host.resumeProjectAdmission && host.readProjectAdmissionOperation ? {
        pause: (request: Parameters<NonNullable<MissionHost["pauseProjectAdmission"]>>[0]) => host.pauseProjectAdmission!(request),
        resume: (request: Parameters<NonNullable<MissionHost["resumeProjectAdmission"]>>[0]) => host.resumeProjectAdmission!(request),
        status: (request: Parameters<NonNullable<MissionHost["readProjectAdmissionOperation"]>>[0]) => host.readProjectAdmissionOperation!(request),
      } : undefined,
    };
  }, [retainedResultHost,authRevision,projectWorkRef,selectionSeq.current]);
  const projectAdmissionPanel=useProjectAdmissionWorkspace({
    selection:projectWorkRef ? {work_ref:projectWorkRef} : null,
    authGeneration:authRevision,sourceGeneration:projectReaders.generation,canRead:projectReaders.canRead,
    readCurrent:admissionPorts.read,transport:admissionPorts.transport,store:commandBinding?.store,locale,
  });
  // Observational association reads use the canonical catalogue pair, independently
  // of the Mission/conversation-send selection. No association grants a send target.
  const projectCard = currentProjectCards.length === 1 ? currentProjectCards[0] : null;
  const projectAssociationSelection = projectWorkRef && projectReaders.canRead() &&
    projectCard?.rootState === "RESOLVED" && projectCard.rootJobId &&
    projectCard.rootCandidates.length === 1 && projectCard.rootCandidates[0] === projectCard.rootJobId
      ? {workRef: projectWorkRef, rootJobId: projectCard.rootJobId} : null;
  const directionConversation = projectConversationActive && projectWorkRef && selection?.workRef === projectWorkRef &&
    observedConversation.projection.conversation.source.state === "CURRENT" &&
    observedConversation.projection.context.selection?.workRef === projectWorkRef &&
    observedConversation.projection.context.selection?.rootJobId === selection.rootJobId;
  const instructionConversationCurrent = !!(projectWorkRef && selection?.workRef === projectWorkRef &&
    authState?.content === true && projectReaders.canRead() &&
    observedConversation.projection.conversation.source.state === "CURRENT" &&
    observedConversation.projection.context.selection?.workRef === projectWorkRef &&
    observedConversation.projection.context.selection?.rootJobId === selection.rootJobId);
  const instructionDraftOwner = projectDraftOwner.current;
  const instructionDraftWitness = instructionConversationCurrent ? projectDraftMethods.readWitness() : null;
  const projectDetailsControls = useProjectDetailsControls({
    selection: projectWorkRef ? {work_ref: projectWorkRef} : null,
    host: retainedResultHost ?? null, authGeneration: authRevision,
    sourceGeneration: projectReaders.generation, canRead: projectReaders.canRead,
    store: commandBinding?.store, locale,
    onChangeInConversation: instructionDraftWitness ? source => {
      const current = projectDraftMethods.readWitness();
      if (projectDraftOwner.current === instructionDraftOwner && current &&
          current.workRef === projectWorkRef && current.workRef === instructionDraftWitness.workRef &&
          current.binding === instructionDraftWitness.binding && current.revision === instructionDraftWitness.revision &&
          projectDraftMethods.append(source, instructionDraftWitness.revision)) {
        showCurrentConversation();
      }
    } : undefined,
  });
  const recordedDirection = <AcceptedDirectionPanel selection={projectWorkRef ? {work_ref:projectWorkRef} : null}
    read={projectReaders.direction} sourceGeneration={projectReaders.generation} canRead={projectReaders.canRead} locale={locale}
    onChangeDirection={directionConversation ? workRef => {
      if (workRef === projectWorkRef && projectReaders.canRead()) showCurrentConversation();
    } : undefined}/>;
  const projectSessionEvidence = <ProjectConversationAssociation selection={projectAssociationSelection}
    authGeneration={authRevision} hostGeneration={retainedResultHost?.invalidationGeneration?.() ?? null}
    readAssociation={projectReaders.association} locale={locale}/>;
  const recordedProjectJournal = projectWorkRef ? <ProjectJournalReader selection={{workRef: projectWorkRef}}
      read={projectReaders.journal} generation={projectReaders.generation?.() ?? "SOURCE_UNAVAILABLE"}
      authGeneration={authRevision} canRead={projectReaders.canRead} locale={locale}/> : null;
  const officeJournalFrame = useMemo(() => captureOfficeReadFrame(retainedResultHost,
    authRevision, freshAuthRevision, "readProjectJournal"), [retainedResultHost, retainedHostGeneration, authRevision, freshAuthRevision]);
  const officeProjectJournal = projectWorkRef ? <ProjectJournalReader selection={{workRef:projectWorkRef}}
    read={projectReaders.journal} generation={retainedHostGeneration} authGeneration={authRevision}
    canRead={officeJournalFrame.current} locale={locale}/> : null;
  const officeWorkRead: WorkState = officeWorkFrame.current?.current() ? workState
    : {kind:"UNAVAILABLE",reason:"SOURCE_OWNER_NOT_CURRENT"};
  const planAdoptionHostCurrent = useMemo(() => {
    const host=retainedResultHost,revision=authRevision;
    return () => !!host && window.MastermindMissionHost===host && authRevisionRef.current===revision;
  },[retainedResultHost,authRevision]);
  const projectPlanProps = {selection: projectWorkRef ? {work_ref: projectWorkRef} : null,
    read: projectReaders.plan, sourceGeneration: projectReaders.generation,
    canRead: projectReaders.canRead, locale};
  const recordedProjectDetails = <><ProjectPlanPanel {...projectPlanProps}/>{recordedProjectJournal}</>;

  const retainedProgram = retainedRoot && index.state === "AVAILABLE"
    ? index.programs.filter(p => p.workRef === retainedRoot.pair.workRef)
    : [];
  // This is a separate read-only choice, never the Mission/action selection.
  // Every new Programs read invalidates it, including A-B-A source changes.
  const currentRetainedRoot = retainedRoot &&
    retainedRoot.index === index && retainedRoot.epoch === programIndexEpoch &&
    retainedRoot.epoch === programRequest.current &&
    retainedRoot.authRevision === authRevision &&
    retainedRoot.host === retainedResultHost &&
    retainedRoot.hostGeneration === retainedHostGeneration &&
    retainedRoot.missionWorkRef === (selection?.workRef ?? null) &&
    (!authState || authState.acquisition) && retainedProgram.length === 1 &&
    retainedProgram[0].rootState === "CONFLICT" &&
    retainedProgram[0].rootCandidates.length > 1 &&
    retainedRoot.candidates === JSON.stringify(retainedProgram[0].rootCandidates) &&
    retainedProgram[0].rootCandidates.includes(retainedRoot.pair.rootJobId)
      ? retainedRoot : null;
  useLayoutEffect(() => {
    if (retainedRoot && !currentRetainedRoot) setRetainedRoot(null);
  }, [retainedRoot, currentRetainedRoot]);
  const chooseRetainedRoot = (pair: MissionSelection) => {
    const normalized = normalizeResultReferencesSelection(pair);
    if (!normalized || index.state !== "AVAILABLE" ||
        programIndexEpoch !== programRequest.current ||
        (authState && !authState.acquisition)) return;
    const programmes = index.programs.filter(p => p.workRef === normalized.workRef);
    if (programmes.length !== 1 || programmes[0].rootState !== "CONFLICT" ||
        programmes[0].rootCandidates.length < 2 ||
        !programmes[0].rootCandidates.includes(normalized.rootJobId)) return;
    setRetainedRoot({ pair: normalized, index, epoch: programIndexEpoch,
      authRevision, host: retainedResultHost, hostGeneration: retainedHostGeneration,
      missionWorkRef: selection?.workRef ?? null,
      candidates: JSON.stringify(programmes[0].rootCandidates) });
  };
  const selectedHistoryPanel = currentRetainedRoot && retainedResultHost?.readResultReferences &&
    retainedResultHost.readResult ? <RetainedResults
      key={JSON.stringify([authRevision, programIndexEpoch, retainedHostGeneration,
        currentRetainedRoot.pair])}
      selection={currentRetainedRoot.pair} authGeneration={authRevision}
      hostGeneration={retainedHostGeneration} locale={locale}
      missionState="UNAVAILABLE"
      readReferences={retainedResultHost.readResultReferences}
      readResult={retainedResultHost.readResult}
      renderResult={(selected, document) =>
        <ResultCard locale={locale} state={{ kind: "READY", selection: selected, document }} />}
    /> : null;
  const retainedResultsPanel = selection && !directSelected &&
    retainedResultHost?.readResultReferences && retainedResultHost.readResult &&
    (!authState || authState.acquisition) ? (
      <RetainedResults
        key={JSON.stringify([authRevision, selectionSeq.current, selection,
          retainedResultHost.invalidationGeneration?.() ?? 0])}
        selection={selection}
        authGeneration={authRevision}
        hostGeneration={retainedResultHost.invalidationGeneration?.() ?? 0}
        locale={locale}
        missionState={d?.read_state.state ?? "UNAVAILABLE"}
        readReferences={retainedResultHost.readResultReferences}
        readResult={retainedResultHost.readResult}
        renderResult={(selected, document) => (
          <ResultCard locale={locale} state={{ kind: "READY", selection: selected, document }} />
        )}
      />
    ) : null;
  const newProjectRoute = active === "Projects" && (projectJourney.shown || projectJourney.invalidLink);
  const quietHeader = active === "Team" || active === "Meta-CEO" || active === "Fleet & Capacity" || active === "Conversations" || active === "Inbox" || active === "Today" || active === "Knowledge" || active === "Search" || active === "Sources" || active === "Tools" ||
    active === "Projects" && !directRoute && (!projectTab ||
      Boolean(projectWorkRef && (projectTab === "Conversation" || catalogueWorkRef)));
  const independentProjectRead =
    (active === "Knowledge" && hasProjectLibrary && knowledgeMode === "project") ||
    (active === "Search" && hasProjectSearch && projectSearchSelected);
  const reading = projectReadingPresentation({
    active, locale, independentProjectRead, notice: visibleNotice,
  });
  const projectReadGeneration = JSON.stringify([authRevision, retainedHostGeneration, selectionSeq.current]);
  const discoveryView = projectDiscovery({projection: office.projection,
    conversation: observedConversation.projection, controlRoom: currentControlRoom});

  const conversationListModel = composeConversationsList({authGeneration: authRevision,
    catalogue: office.projection, conversation: observedConversation.projection,
    acquisitionAllowed: authState?.acquisition === true, contentAllowed: authState?.content === true,
    catalogueReadCurrent: conversationListOwnerCurrent(catalogueListOwner.current, false),
    conversationReadCurrent: conversationListOwnerCurrent(windowListOwner.current, true),
    programsPending: programsReadPhase === "pending", windowPending,
    hasUnsentDraft: !!observedConversation.draft.trim()});
  const conversationListSnapshot = useRef({model: conversationListModel,
    catalogueOwner: catalogueListOwner.current, windowOwner: windowListOwner.current,
    index, epoch: programIndexEpoch});
  conversationListSnapshot.current = {model: conversationListModel,
    catalogueOwner: catalogueListOwner.current, windowOwner: windowListOwner.current,
    index, epoch: programIndexEpoch};
  const currentProgramsRead = () => {
    const latest = conversationListSnapshot.current;
    return latest.index === index && latest.epoch === programIndexEpoch && latest.epoch === programRequest.current &&
      latest.catalogueOwner === catalogueListOwner.current && conversationListOwnerCurrent(latest.catalogueOwner, false) &&
      latest.index.state === "AVAILABLE";
  };
  const todayCatalogueFrame = useRef({active, index, epoch: programIndexEpoch});
  todayCatalogueFrame.current = {active, index, epoch: programIndexEpoch};
  const currentTodayCatalogue = () => todayCatalogueFrame.current.active === "Today" &&
    todayCatalogueFrame.current.index === index && todayCatalogueFrame.current.epoch === programIndexEpoch &&
    currentProgramsRead();
  const openCreatedProject = (workRef: string, current: () => boolean): Promise<boolean> => {
    const host = window.MastermindMissionHost, selected = projectJourney.selection;
    try {
      if (!host || createdProjectOpen.current || active !== "Projects" || !projectJourney.shown ||
          !selected || selected.workRef !== workRef || !projectJourney.isHostCurrent() ||
          !programsReadAvailable || !current()) return Promise.resolve(false);
    } catch { return Promise.resolve(false); }
    return new Promise<boolean>(complete => {
      createdProjectOpen.current = {workRef, createRequestId: selected!.createRequestId, host: host!,
        authRevision, selectionSequence: selectionSeq.current,
        catalogueSequence: cataloguePresentationSequence.current,
        afterEpoch: programRequest.current, current, complete};
      refreshProjects();
    });
  };
  // Completion belongs to this one explicit Open gesture and its fresh read.
  // SOURCE_OBSERVED supplies a hint; only the acquired catalogue supplies membership.
  useLayoutEffect(() => {
    const opening = createdProjectOpen.current;
    if (!opening) return;
    const finish = (opened: boolean) => {
      createdProjectOpen.current = null;
      opening.complete(opened);
    };
    let current = false;
    try {
      current = active === "Projects" && projectJourney.shown &&
        projectJourney.selection?.createRequestId === opening.createRequestId &&
        projectJourney.selection?.workRef === opening.workRef &&
        window.MastermindMissionHost === opening.host && authRevision === opening.authRevision &&
        authRevisionRef.current === opening.authRevision && selectionSeq.current === opening.selectionSequence &&
        cataloguePresentationSequence.current === opening.catalogueSequence &&
        projectJourney.isHostCurrent() && opening.current();
    } catch { /* An unavailable original witness cannot select a project. */ }
    if (!current) { finish(false); return; }
    if (programRequest.current <= opening.afterEpoch) return;
    if (programRequest.current !== opening.afterEpoch + 1) { finish(false); return; }
    if (index.state === "PENDING") return;
    if (!currentProgramsRead() || programIndexEpoch <= opening.afterEpoch ||
        index.programs.filter(row => row.workRef === opening.workRef).length !== 1) {
      finish(false); return;
    }
    projectJourney.hide();
    setCatalogueProject({workRef: opening.workRef, authRevision, epoch: programIndexEpoch});
    setProjectTab("More"); setActive("Projects");
    finish(true);
  });
  // Presentation-only navigation. Existing read owners still qualify all data;
  // no selection/Attempt, draft, operation or admission is created or changed.
  const resourcesHost = window.MastermindMissionHost;
  const resourcesOwnerCurrent = () => window.MastermindMissionHost === resourcesHost &&
    authRevisionRef.current === authRevision && office.projection.programs.source.state === "CURRENT" &&
    conversationListSnapshot.current.index === index && conversationListSnapshot.current.epoch === programIndexEpoch;
  const resourcesCanOpenWork = (root: string) => resourcesOwnerCurrent() && projectReaders.canRead() &&
    Boolean(selection && projectWorkRef === selection.workRef && selection.rootJobId === root &&
      d?.mission.root_job_id === root && d.mission.root_job_ambiguous === false &&
      currentProjectCards[0]?.rootState === "RESOLVED" && currentProjectCards[0]?.rootCandidates.length === 1 &&
      currentProjectCards[0]?.rootJobId === root);
  const resourcesWorkReturn = resourcesWorkOrigin?.auth === authRevision &&
    resourcesWorkOrigin.workRef === selection?.workRef && resourcesWorkOrigin.rootJobId === selection?.rootJobId;
  // Fresh choices consume the SAME acquired index, including qualified N.
  // Global saved-conversation locators remain owned by the C projection.
  const freshIndexCurrent = currentProgramsRead();
  const freshProjects = freshIndexCurrent
    ? index.programs.map(row => ({workRef: row.workRef, title: row.title})) : [];
  const freshJourney = useFreshConversationJourney({locale, active: active === "Conversations" && freshDraft.shown,
    binding: freshBinding, authGeneration: authRevision, host: freshHost,
    projects: freshProjects,
    projectsState: freshIndexCurrent ? "available" : programsReadPhase === "pending" ? "reading" : "unavailable",
    projectReadIdentity: index,
    isProjectCurrent: workRef => {
      const latest = conversationListSnapshot.current;
      return latest.catalogueOwner === catalogueListOwner.current &&
        conversationListOwnerCurrent(latest.catalogueOwner, false) && latest.index.state === "AVAILABLE" &&
        latest.epoch === programRequest.current && latest.index.programs.filter(row => row.workRef === workRef).length === 1;
    },
    workRef: freshDraft.workRef, message: freshDraft.message, draftOwner: freshDraft.draftOwner,
    onWorkRefChange: freshDraft.onWorkRefChange, onMessageChange: freshDraft.onMessageChange,
    onOriginalKeySelected: freshDraft.onOriginalKeySelected, originalLookup: freshDraft.originalLookup,
    renderContinuation: read => <FreshConversationContinuation locale={locale}
      active={active === "Conversations" && freshDraft.shown} binding={freshAttendedBinding}
      host={freshHost} authGeneration={authRevision} entry={{kind: "initial", read}}
      turnDraft={freshTurnDraft} onUnresolvedChange={reportFreshAttendedOriginal}
      onOriginalSettled={onFreshOriginalSettled}/>,
    onBack: () => {freshDraftRef.current.hide();conversationNavigation.backFromNewConversation();setActive("Conversations");}});
  refreshFreshPendingHint.current = freshJourney.refreshPendingOriginal;
  freshOriginalHeld.current = freshJourney.hasUnresolvedOriginal;
  const openFreshConversation = () => {
    if (!freshDraft.open(freshJourney.hasUnresolvedOriginal || hasFreshAttendedOriginal() ? "resume" : "new")) return;
    // Close the mobile drawer before the Journey captures this explicit
    // gesture's focus origin. Its owned field/outcome focus can then proceed.
    if (navigationOpen) closeNavigation();
    freshJourney.start();setActive("Conversations");
  };
  const freshEntryUnavailableReason = !freshHost?.freshConversation
    ? (locale === "zh-CN" ? "当前连接无法新建对话。" : "This connection can’t start a new conversation.")
    : !freshExecutiveOwner()
      ? (locale === "zh-CN" ? "暂时无法确认新建对话的访问权限。" : "Conversation access couldn’t be confirmed.") : null;
  // The existing Executive Session source is independent of Workspace Content.
  // A user gesture opens its existing reader; no window locator/body is minted.
  const sessionEntryHost = window.MastermindMissionHost;
  const sessionEntryAuth = sessionEntryHost?.auth, sessionEntryAuthRead = sessionEntryAuth?.getState;
  const sessionEntryContext = sessionBinding?.port.context;
  const sessionEntryGeneration = sessionEntryHost?.invalidationGeneration;
  const sessionEntrySequence = selectionSeq.current;
  const openSessionRequests = sessionBinding && sessionOwner && (native||signedIn) ? () => {
    try {
      if (!sessionEntryHost || window.MastermindMissionHost !== sessionEntryHost ||
          sessionEntryHost.auth !== sessionEntryAuth || sessionEntryAuth?.getState !== sessionEntryAuthRead ||
          !sessionEntryAuthRead || (!native&&sessionEntryAuthRead.call(sessionEntryAuth).status !== "signed_in") ||
          sessionEntryHost.sessionCommandBinding !== sessionBinding || sessionBinding.port.context !== sessionEntryContext ||
          sessionEntryHost.invalidationGeneration !== sessionEntryGeneration ||
          (sessionEntryGeneration?.call(sessionEntryHost) ?? null) !== freshHostGeneration ||
          !ownsSession(sessionBinding, sessionOwner, sessionEntrySequence)) return false;
      conversationNavigation.showCurrentDetail("selected-session");
      return true;
    } catch { return false; }
  } : undefined;
  const conversationListPanel = <ConversationsList model={conversationListModel} locale={locale} theme={theme}
    onNewConversation={freshHost?.freshConversation ? openFreshConversation : undefined}
    onOpenSessionRequests={openSessionRequests}
    query={conversationNavigation.query} onQueryChange={conversationNavigation.changeQuery}
    showAllProjects={conversationNavigation.showAllProjects} onShowAllProjects={conversationNavigation.showAll}
    restoreFocus={conversationNavigation.restoreFocus}
    onOpenCurrent={locator => {
      const latest = conversationListSnapshot.current;
      if (latest.windowOwner !== windowListOwner.current || !conversationListOwnerCurrent(latest.windowOwner, true) ||
          !isListedCurrentConversation(latest.model, locator)) return false;
      const row = latest.model.recent.find(item => item.locator === locator ||
        JSON.stringify(item.locator) === JSON.stringify(locator));
      if (!row) return false;
      conversationNavigation.showCurrentDetail(row.key); return true;
    }}
    onOpenProject={locator => {
      const latest = conversationListSnapshot.current;
      if (latest.catalogueOwner !== catalogueListOwner.current || !conversationListOwnerCurrent(latest.catalogueOwner, false) ||
          !isListedConversationProject(latest.model, locator) || latest.index.state !== "AVAILABLE" ||
          latest.index.programs.filter(card => card.workRef === locator.workRef).length !== 1) return false;
      const row = latest.model.projects.find(item => item.locator.workRef === locator.workRef);
      if (!row) return false;
      conversationNavigation.rememberProject(locator.workRef, row.key);
      setCatalogueProject({workRef: locator.workRef, authRevision, epoch: latest.epoch});
      setProjectTab("More"); setActive("Projects"); return true;
    }}
    onOpenMetaCeo={() => setActive("Meta-CEO")} onSourcesAndAccess={() => setActive("Sources")}
    onRefresh={() => {
      const owner = captureListReadOwner(retainedResultHost);
      if (!owner || owner.hostGeneration !== retainedHostGeneration || !conversationListOwnerCurrent(owner, false)) return;
      setProgramRevision(n => n + 1);setWindowRevision(n => n + 1);
    }} />;
  const currentConversationPanel = (
      <>
        <ConversationWindow
          headingLevel={active === "Conversations" ? 1 : 2}
          locale={locale}
          continuation={active === "Projects" && !(native&&!signedIn) ? undefined : sessionContinuationPanel}
          historicalAnswers={<HistoricalOriginalAnswers
            binding={sessionBinding}
            selection={selection}
            principalScope={sessionOwner?.principalScope ?? null}
            generation={sessionOwner?.generation ?? null}
            authRevision={authRevision}
            selectionSeq={selectionSeq.current}
            activeReadRef={presentedSessionAnswer?.answer.readRef}
          />}
          qualifiedAnswer={presentedSessionAnswer}
          onQualifiedAnswerCommitted={answerView.acknowledgeRender}
          notesPresentation="collapsed"
          retainUnsentOnExpiry={passiveExpiryHold.current && authState?.content === false}
          projection={observedConversation.projection}
          draft={observedConversation.draft}
          onDraftChange={observedConversation.changeDraft}
          readResult={window.MastermindMissionHost?.readResult}
          draftRevision={observedConversation.draftRevision}
          draftInsertion={observedConversation.draftInsertion}
          onAppendSource={observedConversation.appendSource}
          onUndoSource={observedConversation.undoSource}
        />
        <button
          type="button"
          disabled={windowPending || !authState?.content}
          onClick={() => {
            bumpInvalidation();
            setWindowRevision((n) => n + 1);
          }}
        >
          {locale === "zh-CN" ? "刷新回复" : "Refresh replies"}
        </button>
        {active !== "Projects" && ((!signedIn && retainedComposerDrafts.session) || !sessionBinding)
          ? sessionPanel : null}
      </>
    );
  const changeProjectTab = (tab: ProjectTab) => {
    pendingLegacyTabFocus.current = tab;
    setProjectTab(tab);
  };
  const nativeGoalQuarantined = nativeGoal.quarantine ||
    (native && projectJourney.retainedGoal?.passivelyHeld === true);
  const nativeGoalNotice = nativeGoalQuarantined ? <NativeDraftRecoveryNotice locale={locale}
    checking={nativeGoal.phase === "CHECKING"} canRecover={nativeGoal.canRecover}
    onRecover={() => {
      if (!projectJourney.isHostCurrent()) return;
      void nativeGoal.recover().then(restored => {
      if (restored && projectJourney.isHostCurrent()) {
        setCatalogueProject(null);setProjectTab(null);setActive("Projects");
      }
    }); }} onDiscard={nativeGoal.discard}/> : null;
  const retainedProjectGoal = !nativeGoalQuarantined && projectJourney.retainedGoal &&
    (!projectJourney.retainedGoal.passivelyHeld || passiveExpiryHold.current) ?
    <section className="card" aria-label={locale === "zh-CN" ? "保留的项目目标" : "Retained project goal"}>
      <h2>{locale === "zh-CN" ? "未发送的项目目标" : "Unsent project goal"}</h2>
      <label htmlFor="retained-project-goal">{locale === "zh-CN" ? "原项目目标" : "Original project goal"}</label>
      <textarea id="retained-project-goal" value={projectJourney.retainedGoal.text}
        onChange={event => projectJourney.editRetainedGoal(event.target.value)} rows={4}/>
      {!projectJourney.retainedGoal.passivelyHeld ? <button type="button" onClick={() => {
        if (projectJourney.returnToRetainedGoal()) {setCatalogueProject(null);setProjectTab(null);setActive("Projects");}
      }}>{locale === "zh-CN" ? "返回原项目设置" : "Return to original project setup"}</button> : null}
      <button type="button" onClick={projectJourney.discardRetainedGoal}>{locale === "zh-CN" ? "丢弃项目目标" : "Discard project goal"}</button>
    </section> : null;
  const nativeSessionReturn=native&&!signedIn&&sessionOwner?<>
    {conversationNavigation.view==='detail'?<>
      <button type="button" onClick={conversationNavigation.backToList}>{locale==='zh-CN'?'返回对话':'Back to conversations'}</button>
      {currentConversationPanel}
    </>:openSessionRequests?<button type="button" onClick={()=>openSessionRequests()}>{locale==='zh-CN'?'查看会话请求':'Open session requests'}</button>:null}
  </>:null;
  const retainedFreshMessage = freshDraft.retainedDraft &&
    (!freshDraft.retainedDraft.passivelyHeld || passiveExpiryHold.current) ?
    <section className="card" aria-label={locale === "zh-CN" ? "保留的第一条消息" : "Retained first message"}>
      <h2>{locale === "zh-CN" ? "未发送的第一条消息" : "Unsent first message"}</h2>
      <label htmlFor="retained-fresh-message">{locale === "zh-CN" ? "原消息" : "Original message"}</label>
      <textarea id="retained-fresh-message" value={freshDraft.retainedDraft.text}
        onChange={event => freshDraft.editRetainedDraft(event.target.value)} rows={4}/>
      {!freshDraft.retainedDraft.passivelyHeld ? <button type="button" onClick={() => {
        if (freshDraft.returnToRetainedDraft()) setActive("Conversations");
      }}>{locale === "zh-CN" ? "返回原草稿" : "Return to original draft"}</button> : null}
      <button type="button" onClick={freshDraft.discardRetainedDraft}>{locale === "zh-CN" ? "丢弃第一条消息" : "Discard first message"}</button>
    </section> : null;
  let content: React.ReactNode;
  if (active === "Projects" && (projectJourney.shown || projectJourney.invalidLink))
    content = <>
      <button type="button" onClick={() => {
        if (!projectJourney.isHostCurrent()) return;
        projectJourney.hide();setProjectTab(null);
      }}>{locale === "zh-CN" ? "返回项目" : "Back to projects"}</button>
      {projectJourney.invalidLink ? <section className="card"><h1>{locale === "zh-CN" ? "项目设置链接不可用" : "Project setup link unavailable"}</h1>
        <p>{locale === "zh-CN" ? "请使用原始项目设置链接，或明确打开项目设置。" : "Use the original project setup link, or explicitly open project setup."}</p>
        <button type="button" onClick={openProjectJourney}>{locale === "zh-CN" ? "打开项目设置" : "Open project setup"}</button></section>
      : nativeGoalQuarantined ? null : commandBinding && projectJourneyStoreOwner ? <><ProjectPlanningJourney key={`project-journey:${authRevision}`} locale={locale}
        host={window.MastermindMissionHost ?? null} store={projectJourneyStoreOwner.store}
        executiveOwner={() => {
          if (!projectJourney.isHostCurrent() || !projectJourneyStoreOwner.current() || window.MastermindMissionHost?.commandBinding !== commandBinding) return null;
          const live = readOwnerContext(commandBinding.port);
          return live && live.principalScope === ownerContext?.principalScope && live.generation === ownerContext?.generation ? live : null;
        }}
        isHostCurrent={() => projectJourney.isHostCurrent() && projectJourneyStoreOwner.current()} selection={projectJourney.selection}
        onSelection={value => {projectJourney.onSelection(value);void nativeGoal.beforeEdit();}}
        onOpenProject={openCreatedProject}
        goal={projectJourney.goal} goalReadOnly={native && !nativeGoal.canEdit}
        onGoalFocus={() => {void nativeGoal.beforeEdit();}}
        onGoalChange={text => {if (nativeGoal.canEdit) projectJourney.onGoalChange(text);}}
        draftFiles={projectJourney.draftFiles} onDraftFilesChange={projectJourney.onDraftFilesChange}
        originalFileLookup={projectJourney.originalFileLookup} onOriginalFileLookupChange={projectJourney.onOriginalFileLookupChange}
        proposalOriginal={projectJourney.proposalOriginal} currentProposalOriginal={projectJourney.currentProposalOriginal} onProposalOriginalChange={projectJourney.onProposalOriginalChange}/>
      {projectJourney.filesHeld && <section className="card" aria-label={locale==='zh-CN'?'保留的文件草稿':'Held file draft'}>
        <p>{locale==='zh-CN'?'文件草稿已为原始项目及登录身份保留。':'The file draft is held for its original project and signed-in identity.'}</p>
        <button type="button" onClick={()=>void projectJourney.checkRetainedFileDraft()}>{locale==='zh-CN'?'查询文件草稿访问状态':'Check file draft access'}</button>
        <button type="button" onClick={projectJourney.discardRetainedFiles}>{locale==='zh-CN'?'丢弃文件草稿':'Discard file draft'}</button>
      </section>}</>
      : <section className="card"><h1>{locale === "zh-CN" ? "项目设置暂不可用" : "Project setup unavailable"}</h1>
        <p>{locale === "zh-CN" ? "当前来源未提供项目操作接口。" : "The current source has not supplied the project operation interface."}</p></section>}
      {retainedProjectGoal}
    </>;
  else if (active === "Team")
    content = <Suspense fallback={<p role="status">{locale === "zh-CN" ? "正在加载团队工作区…" : "Loading the team workspace…"}</p>}><CompanyWorkspace key={authRevision} transport={window.MastermindMissionHost?.company}
      authGeneration={authRevision} canRead={Boolean(authState?.status === "signed_in" && authState.acquisition)} locale={locale}
      onNavigate={destination => { setProjectTab(null); setActive(destination); }}
      onOpenProject={workRef => {
        if (!currentTodayCatalogue() || index.state !== "AVAILABLE") return false;
        const matches = index.programs.filter(card => card.workRef === workRef);
        if (matches.length !== 1) return false;
        const card = matches[0];
        if (card.rootState === "RESOLVED" && card.rootJobId && card.rootCandidates.length === 1 && card.rootCandidates[0] === card.rootJobId) {
          open(card.workRef, card.rootJobId); return true;
        }
        setCatalogueProject({ workRef, authRevision, epoch: programIndexEpoch });
        setProjectTab("More"); setActive("Projects"); return true;
      }}/></Suspense>;
  else if (active === "Today")
    content = <Today locale={locale} projection={office.projection} work={workState}
      currentCatalogue={{value: index, current: currentTodayCatalogue}}
      onOpenProject={workRef => {
        if (!currentTodayCatalogue() || index.state !== "AVAILABLE") return;
        const cards = index.programs.filter(card => card.workRef === workRef);
        if (cards.length !== 1) return;
        const card = cards[0];
        // Reuse current-catalogue navigation; only its actual singleton root
        // may enter Mission. A rootless card opens project details instead.
        if (card.rootState === "RESOLVED" && card.rootJobId && card.rootCandidates.length === 1 && card.rootCandidates[0] === card.rootJobId) {
          open(card.workRef, card.rootJobId); return;
        }
        setCatalogueProject({workRef, authRevision, epoch: programIndexEpoch});
        setProjectTab("More"); setActive("Projects");
      }}
      composer={commandPanel}
      authenticationCue={todayAuthenticationCue}
      retainComposerWithAuth={Boolean(passiveExpiryHold.current && (retainedComposerDrafts.launch || retainedComposerDrafts.launchDetails)) || heldKind === "launch"}
      onOpenInbox={() => { setProjectTab(null); setActive("Inbox"); }}
      onOpenProjects={() => { setProjectTab(null); setCatalogueProject(null); setActive("Projects"); }}
      onOpenMission={(!authState || authState.acquisition) ? target => open(target.workRef, target.rootJobId) : undefined}
    />;
  else if (active === "Meta-CEO")
    content = (
      <>
        <MetaCeoOffice
          key={JSON.stringify([authRevision, selection, officeSession.sessionRef, officeSession.bindingGeneration])}
          locale={locale}
          projection={office.projection}
          byokObservation={byokRoleView(byokRoles)}
          canRefreshByok={byokRoles.canRefresh}
          onRefreshByok={byokRoles.refresh}
          programmeDirection={{selection: projectWorkRef ? {work_ref: projectWorkRef} : null,
            read: projectReaders.plan, sourceGeneration: projectReaders.generation, canRead: projectReaders.canRead}}
          acceptedDirection={recordedDirection}
          workRead={officeWorkRead}
          onInspectWork={() => {if (officeWorkFrame.current?.current()) setActive("Work");}}
          projectJournal={officeProjectJournal}
          companyPriorities={<CompanyPrioritiesRead host={window.MastermindMissionHost} locale={locale}/>}
          onOpenProjects={() => { setProjectTab(null); setActive("Projects"); }}
          selectedProject={projectWorkRef && currentProjectCards.length === 1 ? {
            title: currentProjectCards[0].title || projectWorkRef,
            nextAction: currentProjectCards[0].nextAction,
            onOpen: () => { if (projectReaders.canRead()) { setProjectTab("Conversation"); setActive("Projects"); } },
          } : null}
          draft={office.draft}
          onDraftChange={office.changeDraft}
          onInspectWorkerResult={workerResultHost?.readResult ? openOfficeWorkerResult : undefined}
          nativeContinuation={
            officeSession.sessionRef !== null &&
            officeSession.sessionRef === sessionTargetKey &&
            office.projection.mission.source.state === "CURRENT"
              ? currentConversationPanel
              : null
          }
          onStartNewWork={canLaunch && commandView ? startOfficeLaunch : undefined}
        />
        {/* The one existing launch owner, mounted where the Office mounts it.
            It is the same commandPanel element the other routes use, so only
            one LaunchOrchestrator owner exists at a time. */}
        {launchHandoff?.kind === "office" ? commandPanel : null}
        <details className="office-operations"><summary>{locale === "zh-CN" ? "公司工具" : "Company tools"}</summary>
          <OperationalNavigation label="Company operations" onNavigate={navigateOperationalView} />
        </details>
      </>
    );
  else if (active === "Inbox")
    content = (
      <InboxWorkspace
        locale={locale}
        terminalHost={window.MastermindMissionHost?.terminalSharing}
        projection={office.projection}
        onNavigateMission={
          office.projection.mission.source.state === "CURRENT"
            ? (target, mode) => {
                if (mode === "current") open(target.workRef, target.rootJobId);
              }
            : undefined
        }
      />
    );
  else if (active === "Conversations" && (freshDraft.shown || freshDraft.invalidLink))
    content = <>{freshDraft.invalidLink ? <section className="card"><h1>{locale === "zh-CN" ? "对话链接不可用" : "Conversation link unavailable"}</h1>
      <p>{locale === "zh-CN" ? "使用原对话链接，或明确开始新对话。" : "Use the original conversation link, or explicitly start a new conversation."}</p>
      <button type="button" onClick={openFreshConversation}>{locale === "zh-CN" ? "新建对话" : "New conversation"}</button></section> : freshJourney.panel}{retainedFreshMessage}</>;
  else if (active === "Conversations")
    content = <>{conversationNavigation.view === "list" ? conversationListPanel : <>
      <button type="button" onClick={conversationNavigation.backToList}>{locale === "zh-CN" ? "返回对话" : "Back to conversations"}</button>
      {currentConversationPanel}</>}{retainedFreshMessage}</>;
  else if ((active === "Search" && (!hasProjectSearch || !projectSearchSelected)) || active === "Sources" || active === "Tools")
    content = <DiscoveryWorkspace view={discoveryView} projection={office.projection}
      mode={active} locale={locale} theme={theme}
      sourceProps={{readResultReferences: retainedResultHost?.readResultReferences,
        readResult: retainedResultHost?.readResult,
        hostGeneration: retainedResultHost?.invalidationGeneration?.(),
        draftPort: {projection: observedConversation.projection, text: observedConversation.draft,
          revision: observedConversation.draftRevision, insertion: observedConversation.draftInsertion,
          append: observedConversation.appendSource, undo: observedConversation.undoSource,
          edit: () => showCurrentConversation()}}}
      onModeChange={setActive}
      onReturnToSearch={() => {
        if (window.MastermindMissionHost !== retainedResultHost || authRevisionRef.current !== authRevision) return;
        sourceSearchReturn.current = {host: retainedResultHost, auth: authRevision, generation: archiveHostGeneration,
          work: projectWorkRef, epoch: programIndexEpoch};
        setSavedConversationNavigation(null); setActive("Search");
      }}
      onOpenProject={office.projection.programs.source.state === "CURRENT" && index.state === "AVAILABLE"
        ? (target, mode) => {
            if (mode !== "current" || office.projection.programs.source.state !== "CURRENT" || index.state !== "AVAILABLE") return;
            const cards = index.programs.filter(card => card.workRef === target.workRef);
            if (cards.length !== 1 || cards[0].rootState !== "RESOLVED" ||
                cards[0].rootJobId !== target.rootJobId || cards[0].rootCandidates.length !== 1 ||
                cards[0].rootCandidates[0] !== target.rootJobId) return;
            open(target.workRef, target.rootJobId);
          } : undefined}
      onOpenConversation={() => showCurrentConversation()}
      onOpenMetaCeo={() => setActive("Meta-CEO")}
      onOpenKnowledge={() => setActive("Knowledge")}
      onOpenPreferences={hasPreferencesNavigation ? openDisplayPreferences : undefined}
      onRefreshSources={authState?.acquisition && typeof retainedResultHost?.readControlRoomState === "function"
        ? () => setControlRoomRevision(revision => revision + 1) : undefined}/>
  else if (active === "Search")
    content = savedConversationNavigation ? <SavedConversationReader
      selection={savedConversationNavigation} workRef={projectWorkRef} authGeneration={authRevision}
      hostGeneration={archiveHostGeneration} owner={projectHistoryOwner} locale={locale} theme={theme} draftPort={projectSourceDraftPort}
      onBack={() => setSavedConversationNavigation(null)}/> : null;
  else if (active === "Knowledge" && hasProjectLibrary && knowledgeMode === "project")
    content = <>{knowledgePublicationPanel}<ProjectKnowledgeLibrary host={retainedResultHost} workRef={projectWorkRef}
      authGeneration={authRevision} hostGeneration={archiveHostGeneration} locale={locale} theme={theme}
      requestedFile={requestedProjectFile} draftPort={projectSourceDraftPort} refreshKey={knowledgeRefresh}
      onCurrentSourceOwner={knowledgePublication.registerSourceOwner}
      readActions={knowledgeWriteAvailable?knowledgePublication.readActions:undefined}
      onAddFiles={knowledgeWriteAvailable?context=>openKnowledgeEditor("file",context,null):undefined}
      onEditPreference={knowledgeWriteAvailable?(context,memory)=>openKnowledgeEditor("preference",context,memory):undefined}
      onCorrectDiscovery={knowledgeWriteAvailable?source=>openKnowledgeEditor('correction',source.sourceContext,null,source):undefined}
      onReturnToSearch={() => { setRequestedProjectFile(undefined); setActive("Search"); setProjectSearchSelected(true); }}/></>
  else if (active === "Knowledge")
    content = <Knowledge projection={office.projection} locale={locale}
      readResultReferences={retainedResultHost?.readResultReferences}
      readResult={retainedResultHost?.readResult}
      hostGeneration={retainedResultHost?.invalidationGeneration?.()}
      draftPort={{ projection: observedConversation.projection, text: observedConversation.draft,
        revision: observedConversation.draftRevision, insertion: observedConversation.draftInsertion,
        append: observedConversation.appendSource, undo: observedConversation.undoSource,
        edit: () => showCurrentConversation() }} />;
  else if (directRoute)
    content = <>
      {directResultPanel}
      <details className="reason-details">
        <summary>{locale === "zh-CN" ? "任务范围与项目来源" : "Task scope and project source"}</summary>
        <dl>
          <dt>{locale === "zh-CN" ? "工作流" : "Workstream"}</dt><dd><code>{selection?.workRef}</code></dd>
          <dt>Job</dt><dd><code>{selection?.rootJobId}</code></dd>
          <dt>{locale === "zh-CN" ? "项目来源" : "Project source"}</dt><dd><State value={office.projection.programs.source.state} /></dd>
        </dl>
        <p>{visibleNotice}</p>
        {programsRefreshControl}
      </details>
    </>;
  else if (active === "Projects")
    content = (
      <>
        <button type="button" onClick={openProjectJourney} disabled={!projectJourney.isHostCurrent()}>{locale === "zh-CN" ? projectJourney.selection ? "继续项目设置" : "新建项目" : projectJourney.selection ? "Continue project setup" : "New project"}</button>
        {retainedProjectGoal}
        {programsRefreshControl}
        {!directSelected && projectWorkRef && (catalogueWorkRef || projectTab === "Conversation") ? (
          <ProjectPlanPanel {...projectPlanProps} renderWorkspace={({objective, panel, inspection, launchInspection}) => <ProjectWorkspace headingLevel={1} headingRef={projectHeading} locale={locale}
            scopeKey={JSON.stringify([authRevision, projectWorkRef,
              projectConversationActive ? selection?.rootJobId : null, sessionTargetKey])}
            title={currentProjectCards[0].title || projectWorkRef} goal={objective}
            startWorkControl={<ProjectStartWork inspection={launchInspection} locale={locale}
              disabled={!signedIn} operationHold={currentReopened
                ? currentReopened.reason === "READING" ? "checking" : "pending"
                : pendingCommand.current?.kind === "launch" || heldKind === "launch" ? "pending" : null}
              onStart={startProjectLaunch}/>}
            launchPanel={launchHandoff?.kind === "project" && launchHandoff.workstreamRef === projectWorkRef
              ? commandPanel : undefined}
            conversationPanel={<>
              <ProjectExecutionHistory workRef={projectWorkRef} owner={projectConversations.history?.owner}
                locale={locale} theme={theme} onContinue={async (witness, current) => {
                  const refresh = locale === "zh-CN" ? "请重新读取项目计划与执行结果后再继续。"
                    : "Read the current project plan and run again before continuing.";
                  try {
                    if (!launchInspection || !launchInspection.isCurrent() || !current()) return refresh;
                    const context = projectExecutionContext(launchInspection.read, launchInspection.selection);
                    if (context.state !== "AVAILABLE") return refresh;
                    // The previous result is immutable input. The user writes a
                    // new message; a separate current preview qualifies its run.
                    const outcome = await startProjectLaunch(createProjectLaunchDraft(context, ""),
                      launchInspection, witness, current);
                    if (outcome.status === "OPENED") return;
                    if (outcome.reason === "LAUNCH_GOAL_PRESERVED") return locale === "zh-CN"
                      ? "已保留现有工作草稿，请先完成或取消该草稿。"
                      : "Your existing work draft is preserved. Finish or cancel that draft first.";
                    if (outcome.reason === "LAUNCH_COMMAND_HELD") return locale === "zh-CN"
                      ? "已有启动请求待确认，请查看原始请求的状态。"
                      : "A launch is already pending. Check its original status.";
                    if (outcome.reason === "LAUNCH_OWNER_UNAVAILABLE") return locale === "zh-CN"
                      ? "此项目暂时无法开始后续工作。"
                      : "Follow-up work is unavailable for this project right now.";
                    return refresh;
                  } catch { return refresh; }
                }}/>
              {projectConversationActive ? currentConversationPanel : null}
            </>}
            composerPanel={projectConversationActive ? sessionContinuationPanel ?? sessionPanel : undefined}
            filesPanel={projectConversationActive ? retainedResultsPanel : undefined}
            statusPanel={!catalogueProject && selection?.workRef === projectWorkRef ? <>
              <div><small>{locale === "zh-CN" ? "任务来源" : "Mission source"}</small>
                <State value={d?.read_state.state ?? ("reason" in mission &&
                  (mission.reason === "SOURCE_READ_PENDING" || mission.reason === "PROGRAM_SELECTION_PENDING")
                    ? "SOURCE_READ_PENDING" : "UNAVAILABLE")}/></div>
              {projectConversationActive && d ? <div>
                <small>{locale === "zh-CN" ? "执行观测" : "Execution observation"}</small>
                <State value={d.execution.state}/>
              </div> : null}
              <details className="reason-details"><summary>{locale === "zh-CN" ? "任务范围与来源详情" : "Mission scope and source details"}</summary>
                <dl><dt>{locale === "zh-CN" ? "所选根任务" : "Selected Mission root"}</dt><dd><code>{selection.rootJobId}</code></dd></dl>
                {"reason" in mission ? <code>{mission.reason}</code> : null}
              </details>
            </> : undefined}
            detailsPanel={<ProjectDetailsNavigator
              scopeKey={JSON.stringify([authRevision, projectWorkRef])}
              locale={locale} title={currentProjectCards[0].title || projectWorkRef} goal={objective}
              sections={[
                {id:"direction", content:recordedDirection},
                {id:"plan", content:<>{panel}{retainedResultHost ? <PlanAdoptionWorkflow workRef={projectWorkRef} inspection={inspection}
                  host={retainedResultHost} isHostCurrent={planAdoptionHostCurrent} locale={locale}/> : null}</>},
                {id:"work", content:<><button type="button" onClick={() => {
                  if (!resourcesOwnerCurrent()) return;
                  setProjectTab(null); setActive("Fleet & Capacity");
                }}>{locale === "zh-CN" ? "查看资源与系统" : "Inspect resources & systems"}</button>{projectAdmissionPanel}
                  {projectConversationActive ? <>
                    <AutonomyPanel selection={selection} read={projectReaders.autonomy}
                      canRead={Boolean(projectReaders.generation) && projectReaders.canRead()}
                      sourceGeneration={projectReaders.generation?.() ?? "SOURCE_UNAVAILABLE"} locale={locale}/>
                    <details className="reason-details"><summary>{locale === "zh-CN" ? "更多工作详情" : "More work details"}</summary>
                      <ProjectTabs locale={locale} active="Conversation" onChange={changeProjectTab}/>
                    </details>
                  </> : null}</>},
                {id:"instructions", content:projectDetailsControls.instructions},
                {id:"permissions", content:projectDetailsControls.access},
                {id:"history", content:<details className="reason-details"><summary>{locale === "zh-CN" ? "项目历史与来源证据" : "Project history and source evidence"}</summary>
                  {projectConversations.panel}{projectConversationHistory.panel}{projectSessionEvidence}{recordedProjectJournal}
                </details>},
              ]}/>}/>}/>
        ) : !catalogueProject && (projectTab || directSelected) && selection ? (
        <>
          <section className="hero">
            <div>
              <span className="eyebrow">PROJECT</span>
              <h2>{d?.program.title || selection.workRef}</h2>
              <p>Exact project context · {selection.rootJobId}</p>
            </div>
            <div className="facts">
              <div>
                <small>PROJECT IDENTITY</small>
                <code>{selection.workRef}</code>
              </div>
              <div>
                <small>MISSION ROOT</small>
                <code>{selection.rootJobId}</code>
              </div>
              <div>
                <small>OWNER STATE</small>
                <State
                  value={
                    d?.read_state.state ??
                    ("reason" in mission &&
                    (mission.reason === "SOURCE_READ_PENDING" ||
                      mission.reason === "PROGRAM_SELECTION_PENDING")
                      ? "SOURCE_READ_PENDING"
                      : "UNAVAILABLE")
                  }
                />
              </div>
            </div>
          </section>
          {!directSelected ? <ProjectTabs locale={locale} tablistRef={legacyProjectTabs} active={projectTab ?? "Overview"} onChange={changeProjectTab} /> : null}
          {retainedResultsPanel}
          {directSelected ? directResultPanel : !d ? (
            <section className="card empty-panel">
              <h2>{projectTab}</h2>
              <State value="UNAVAILABLE" />
              <Empty>
                The exact project Mission is not currently admitted. No project
                facts are borrowed from another selection.
              </Empty>
              <details className="reason-details">
                <summary>Technical details</summary>
                <code>
                  {"reason" in mission ? mission.reason : "SOURCE_UNAVAILABLE"}
                </code>
              </details>
            </section>
          ) : projectTab === "Conversation" ? (
            <section className="card empty-panel">
              <h2>{locale === "zh-CN" ? "项目对话" : "Project conversation"}</h2>
              <p>{locale === "zh-CN" ? "当前来源尚未确认此项目与任务的关联，无法显示项目对话。" : "The current catalogue has not qualified this project’s Mission association. Its conversation is unavailable here."}</p>
            </section>
          ) : projectTab === "Overview" ? (
            <>
              <Mission d={d} />
              {resultRefs}
              <ResultCard locale={locale} state={resultState} />
            </>
          ) : projectTab === "Plan" ? (
            <ProjectPlanPanel {...projectPlanProps} />
          ) : projectTab === "Work" ? (
            <>
              <section ref={resourcesWorkView} tabIndex={-1} aria-label={locale === "zh-CN" ? "所选工作详情" : "Selected work inspection"}>
              {resourcesWorkReturn ? <button type="button" onClick={() => {
                pendingResourcesFocus.current={kind:"resources",root:selection.rootJobId,auth:authRevision,host:resourcesHost,epoch:resourcesHost?.invalidationGeneration?.()};
                setProjectTab(null);setActive("Fleet & Capacity");}}>{locale === "zh-CN" ? "返回资源与系统" : "Back to resources & systems"}</button> : null}
              <ProjectWorkDetail key={projectReadGeneration} document={d} selection={selection}
                generation={projectReadGeneration} locale={locale}
                resultPanel={<>{resultRefs}<ResultCard locale={locale} state={resultState}/></>}
                activityPanel={<Activity d={d} selection={selection} readActivity={projectReaders.activity} sourceGeneration={projectReaders.generation} canRead={projectReaders.canRead} locale={locale}/>}
                actionPanel={<>{commandPanel}{workRefreshControl}</>}
                onOpenEvidence={() => setProjectTab("Evidence")}
                onOpenJournal={() => setProjectTab("Journal")} /></section>
              <details className="mm-work-journey__details"><summary>{locale === "zh-CN" ? "相关工作状态" : "Related work status"}</summary><WorkQueue state={workState} rootJobId={selection.rootJobId} /></details>
            </>
          ) : projectTab === "Evidence" ? (
            <><ProjectEvidence key={projectReadGeneration} document={d} selection={selection}
              generation={projectReadGeneration} locale={locale}
              resultPanel={<>{resultRefs}<ResultCard locale={locale} state={resultState}/></>}/>{productAcceptancePanel}</>
          ) : projectTab === "Journal" ? (
            <ProjectJournal key={projectReadGeneration} document={d} selection={selection}
              generation={projectReadGeneration} locale={locale} activityPanel={<Activity d={d} selection={selection} readActivity={projectReaders.activity} sourceGeneration={projectReaders.generation} canRead={projectReaders.canRead} locale={locale}/>} />
          ) : (
            <><ProjectMore d={d} sessionPanel={sessionPanel} onNavigate={navigateOperationalView} />
              {recordedProjectDetails}
              <AutonomyPanel selection={selection} read={projectReaders.autonomy}
                canRead={Boolean(projectReaders.generation) && projectReaders.canRead()}
                sourceGeneration={projectReaders.generation?.() ?? "SOURCE_UNAVAILABLE"} locale={locale}/>
            </>
          )}
        </>
      ) : (
        projectReaders.archive && projectReaders.archivePage && projectReaders.generation ?
        <ProjectArchiveBrowser locale={locale} scopeKey={archiveScopeKey}
          programs={office.projection.programs}
          currentCatalogue={{value: index, current: currentProgramsRead}}
          read={projectReaders.archive} readPage={projectReaders.archivePage}
          sourceGeneration={projectReaders.generation} canRead={projectReaders.canRead}
          onOpenProject={workRef => {
            if (!currentProgramsRead() || index.state !== "AVAILABLE") return;
            const cards = index.programs.filter(card => card.workRef === workRef);
            if (cards.length !== 1) return;
            const card = cards[0];
            // Current catalogue navigation preserves the existing conversation
            // path only for its exact singleton root. Archived Open never calls
            // this callback and remains the archive component's read-only view.
            if (card.rootState === "RESOLVED" && card.rootJobId && card.rootCandidates.length === 1 && card.rootCandidates[0] === card.rootJobId) {
              open(card.workRef, card.rootJobId); return;
            }
            setCatalogueProject({workRef, authRevision, epoch: programIndexEpoch});
            setProjectTab("More");
          }} /> :
        <Projects locale={locale}
          programs={office.projection.programs}
          selectedProject={selection}
          onOpenProject={workRef => {
            if (office.projection.programs.source.state !== "CURRENT" || index.state !== "AVAILABLE" ||
                index.programs.filter(card => card.workRef === workRef).length !== 1) return;
            setCatalogueProject({workRef, authRevision, epoch: programIndexEpoch});
            setProjectTab("More");
          }}
          onNavigateMission={
            office.projection.programs.source.state === "CURRENT"
              ? (target, mode) => {
                  if (mode === "current")
                    open(target.workRef, target.rootJobId);
                }
              : undefined
          }
        />
        )}
      </>
    );
  else if (active === "Programs")
    content = (
      <section className="card">
        <div className="section-title">
          <h2>Programs</h2>
          {programsRefreshControl}
          <State
            value={
              index.state === "PENDING" ? "SOURCE_READ_PENDING" : index.state
            }
          />
        </div>
        {index.state === "PENDING" ? (
          <Empty>Reading the bounded Control Room projection…</Empty>
        ) : index.programs.length ? (
          <div className="programs">
            {index.programs.map((p) => (
              <div key={p.workRef}>
              <button
                disabled={!p.rootJobId}
                onClick={() => open(p.workRef, p.rootJobId)}
              >
                <b>{p.title || p.workRef}</b>
                <span>
                  {label(p.state)} ·{" "}
                  {p.nextActionWithheld ? "Next action withheld" : display(p.nextAction, "No next action projected")}
                </span>
                <small>
                  {p.rootJobId
                    ? `Mission ${p.rootJobId}`
                    : p.rootState === "CONFLICT"
                      ? (locale === "zh-CN" ? "任务根存在冲突：当前任务仍未确定。" : "Root conflict: the current Mission stays unresolved.")
                      : "Root unknown; no mission was guessed"}
                </small>
              </button>
              {p.rootState === "CONFLICT" && p.rootCandidates.length > 1 ? <RetainedRootChoice workRef={p.workRef} rootCandidates={p.rootCandidates}
                rootState={p.rootState} locale={locale}
                selectedRootJobId={currentRetainedRoot?.pair.workRef === p.workRef
                  ? currentRetainedRoot.pair.rootJobId : null}
                onChooseRoot={chooseRetainedRoot} /> : null}
              {currentRetainedRoot?.pair.workRef === p.workRef ? selectedHistoryPanel : null}
              </div>
            ))}
          </div>
        ) : index.state === "AVAILABLE" ? (
          <Empty>
            No Programs were projected. This is not evidence of zero work.
          </Empty>
        ) : (
          <Empty>
            Workspace connection unavailable. Programs will appear when an
            approved source is available.
          </Empty>
        )}
        {index.state === "UNAVAILABLE" ? (
          <details className="reason-details">
            <summary>Technical details</summary>
            <code>{index.reason}</code>
          </details>
        ) : null}
      </section>
    );
  else if (active === "Session Estate")
    content = <><div id="activation-session-owner" tabIndex={-1}><SessionEstate key={"estate:" + authRevision} state={currentControlRoom} locale={locale}
      controlsHeld={controlRoomSurfaceControls.held}
      canOpenSurface={controlRoomSurfaceControls.canAct && !controlRoomSurfaceControls.held
        && controlRoomSurfaceControls.action.state !== "PENDING"
        && !(controlRoomSurfaceControls.action.state === "WITHHELD" && controlRoomSurfaceControls.action.held)
        && !(controlRoomSurfaceControls.action.state === "FAILURE" && controlRoomSurfaceControls.action.disposition === "EFFECT_UNKNOWN")
        && !(controlRoomSurfaceControls.action.state === "RESULT" && controlRoomActionIsUncertain(controlRoomSurfaceControls.action.result))}
      onOpenSurface={controlRoomSurfaceControls.onOpenSurface}
      canRefresh={Boolean(authState?.acquisition) && typeof window.MastermindMissionHost?.readControlRoomState === "function"}
      onRefresh={() => setControlRoomRevision(revision => revision + 1)} onOpenMission={open}>
      <ControlRoomSurfaceControls key={"estate-controls:" + authRevision}
        navigation={currentControlRoom.state === "AVAILABLE" ? currentControlRoom.navigation : null}
        locale={locale} {...controlRoomSurfaceControls}/>
    </SessionEstate></div>
    <SupervisionLedger read={currentControlRoom.state === "AVAILABLE"
      ? currentControlRoom.supervision ?? { state: "UNAVAILABLE", reason: "SOURCE_UNAVAILABLE" }
      : { state: "UNAVAILABLE", reason: "SOURCE_UNAVAILABLE" }} locale={locale} onOpenMission={open}/>
    <SupervisionTrace document={d} selection={selection} locale={locale}
      onReadCurrent={authState?.acquisition && selection && !selectionRefused &&
        missionSelectionState === "AVAILABLE" &&
        typeof (window.MastermindMissionHost?.readMissionV3 ?? window.MastermindMissionHost?.readMission) === "function"
        ? (() => {
          const host = window.MastermindMissionHost;
          const read = host?.readMissionV3 ?? host?.readMission;
          const generation = host?.invalidationGeneration?.();
          const revision = authRevision;
          return () => {
            if (window.MastermindMissionHost !== host || authRevisionRef.current !== revision ||
                (host?.readMissionV3 ?? host?.readMission) !== read ||
                host?.invalidationGeneration?.() !== generation || !host?.auth?.getState().acquisition) return;
            setMissionReadRevision(value => value + 1);
          };
        })() : undefined}/>
    <ActivationFacts model={activationModel} locale={locale} onNavigate={navigateActivation}/>
    <details className="reason-details"><summary>{locale === "zh-CN" ? "原始请求状态" : "Original request status"}</summary>
      <ActivationReceipt state={currentControllerState} locale={locale} onReadOriginalStatus={() => navigateActivation("original_status")}/>
    </details>
    <WebSessionPreview key={authRevision} document={d} selection={selection} locale={locale}/></>;
  else if (active === "Control Room")
    content = (
      <>
        <ControlRoomPanel key={authRevision} state={currentControlRoom}
          canRefresh={Boolean(authState?.acquisition) &&
            typeof window.MastermindMissionHost?.readControlRoomState === "function"}
          onRefresh={() => setControlRoomRevision(revision => revision + 1)}
          onOpen={open} />
        <ControlRoomSurfaceControls key={"surface-controls:" + authRevision}
          navigation={currentControlRoom.state === "AVAILABLE"
            ? currentControlRoom.navigation : null}
          locale={locale}
          {...controlRoomSurfaceControls} />
      </>
    );
  else if (active === "Work")
    content = (
      <>
        {commandPanel}
        {workRefreshControl}
        <WorkQueue state={workState} />
      </>
    );
  else if (active === "Fleet & Capacity")
    content = (
      <>
      {projectWorkRef && resourcesOwnerCurrent() ? <div className="resources-project-context">
        <p className="muted">{locale === "zh-CN" ? "所选项目" : "Selected project"} · {currentProjectCards[0].title || projectWorkRef}</p>
        <button type="button" onClick={() => {if (!resourcesOwnerCurrent()) return;setProjectTab("Conversation");setActive("Projects");}}>{locale === "zh-CN" ? "返回项目" : "Back to project"}</button>
      </div> : null}
      <div ref={resourcesView}>
      <h1 tabIndex={-1}>{locale === "zh-CN" ? "资源与系统" : "Resources & systems"}</h1>
      <CapacityFabricRead key={`capacity:${authRevision}`} host={window.MastermindMissionHost} locale={locale}/>
      <details className="reason-details" open={Boolean(projectWorkRef && resourcesOwnerCurrent())}><summary>{locale === "zh-CN" ? "系统与工作量证据" : "Systems & workload evidence"}</summary>
      <ResourcesSystemsPanel controlRoom={currentControlRoom} work={workState} locale={locale} headingLevel={2}
        onOpenWork={root => {if (!resourcesCanOpenWork(root) || !selection) return;
          pendingResourcesFocus.current={kind:"work",root:selection.rootJobId,auth:authRevision,host:resourcesHost,epoch:resourcesHost?.invalidationGeneration?.()};
          setResourcesWorkOrigin({auth:authRevision,workRef:selection.workRef,rootJobId:selection.rootJobId});
          setProjectTab("Work");setActive("Projects");}}
        canOpenWork={resourcesCanOpenWork}
        onReviewSources={() => setActive("Sources")}/></details></div>
      <details className="reason-details"><summary>{locale === "zh-CN" ? "模型与路由配置" : "Models & routing configuration"}</summary>
      <ModelConfigurationRead key={`models:${authRevision}`} host={window.MastermindMissionHost} locale={locale}/></details>
      <details className="reason-details"><summary>{locale === "zh-CN" ? "原始容量凭据与运行记录" : "Original capacity receipts and run records"}</summary>
      <ResourceCapacityRead host={retainedResultHost} locale={locale}
        selection={selectedCurrentCapacityAttempt(office.projection, selection,
          resultState.kind === "READY" ? resultState.selection : null, authRevision)}/>
      <AttendedFabricWorkspace
        key={`fleet:${authRevision}`}
        host={window.MastermindMissionHost}
        locale={locale}
      />
      </details>
      </>
    );
  else if (active === "Conversation")
    content = (
      <>
        {sessionPanel}
        <Conversation
          document={authState?.content ? windowDocument : null}
          pending={windowPending}
          refresh={() => {
            bumpInvalidation();
            setWindowRevision((n) => n + 1);
          }}
          selection={selection}
          association={association}
          contentAvailable={!!authState?.content}
          locale={locale}
        />
      </>
    );
  else if (!d)
    content = (
      <section className="card empty-panel">
        <h2>{active}</h2>
        <State value="UNAVAILABLE" />
        <Empty>
          The workspace is not connected. Mission content will appear when an
          approved source is available.
        </Empty>
        <details className="reason-details">
          <summary>Technical details</summary>
          <code>
            {"reason" in mission ? mission.reason : "SOURCE_UNAVAILABLE"}
          </code>
        </details>
      </section>
    );
  else if (active === "Mission Workspace")
    content = (
      <>
        {directResultPanel}
        <Mission d={d} />
        {retainedResultsPanel}
        {missionV3 && isDocv3(missionV3) ? (
          <ResultRefs
            d={missionV3}
            onPick={pickResult}
            selectedKey={
              resultState.kind === "READY" || resultState.kind === "PENDING"
                ? `${resultState.selection.jobId}|${resultState.selection.attemptId}|${resultState.selection.resultEnvelopeDigest}`
                : null
            }
            disabled={!authState?.acquisition}
          />
        ) : null}
        <ResultCard locale={locale} state={resultState} />
      </>
    );
  else if (active === "Activity") content = <Activity d={d} selection={selection} readActivity={projectReaders.activity} sourceGeneration={projectReaders.generation} canRead={projectReaders.canRead} locale={locale}/>;
  else if (active === "Connections") content = <Connections d={d} />;
  else if (active === "Evidence") content = <><Evidence d={d} />{productAcceptancePanel}</>;
  else content = <Conversation locale={locale} />;
  if (active === "Work" && activationWorkReturn && activationModel?.operationKey === activationWorkReturn)
    content = <><button type="button" onClick={() => {
      const original = readActivationOriginal();
      if (original?.pointer.operationKey !== activationWorkReturn) return;
      setActive("Session Estate"); setActivationWorkReturn(null);
    }}>{locale === "zh-CN" ? "返回激活回执" : "Back to activation receipts"}</button>{content}</>;
  if (active === "Projects" && conversationNavigation.projectReturn !== null &&
      !projectJourney.shown && !projectJourney.invalidLink &&
      conversationNavigation.projectReturn === projectWorkRef)
    content = <><button type="button" onClick={() => {conversationNavigation.backToList();setActive("Conversations");}}>{locale === "zh-CN" ? "返回对话" : "Back to conversations"}</button>{content}</>;
  const privateEntryState = authState && !authState.acquisition && !authState.content &&
    (authState.status === "signed_out" || authState.status === "signing_in" ||
      authState.status === "error" || authState.status === "unconfigured") ? authState.status : null;
  const successfulSignOut = privateEntryState === "signed_out" && authState?.reason === "USER_SIGNED_OUT";
  useEffect(() => {
    // Leaving the product shell must release its existing drawer focus owner.
    if (privateEntryState) setNavigationOpen(false);
  }, [privateEntryState]);
  if (privateEntryState) return <AuthEntry state={privateEntryState} locale={locale} theme={theme}
    illustrationSrc={privateEntryArt} authenticationControl={authenticationControl}
    preferencesControl={preferencesControl}
    feedback={authState?.reason && !successfulSignOut && privateEntryState !== "signing_in" && privateEntryState !== "unconfigured" ? <p role="alert">{
      native ? nativeAuthFeedback(authState, locale) ?? copy.signInFailed :
      authState.reason === "POPUP_BLOCKED" ? copy.allowPopup :
      authState.reason === "POPUP_CLOSED" ? copy.popupClosed :
      authState.reason.includes("EXPIRED") || authState.reason.includes("TIMEOUT") ? copy.signInTimeout : copy.signInFailed
    }</p> : undefined}
    protectedWork={(nativeGoalQuarantined || nativeSessionReturn || (passiveExpiryHold.current && (retainedComposerDrafts.launch || retainedComposerDrafts.launchDetails || retainedComposerDrafts.session || office.draft.text || observedConversation.draft || projectJourney.retainedGoal?.text || freshDraft.retainedDraft?.text)) || showCheckStatus) ? <>
      {nativeGoalNotice}{nativeSessionReturn}
      {passiveExpiryHold.current ? retainedProjectGoal : null}
      {passiveExpiryHold.current ? retainedFreshMessage : null}
      {passiveExpiryHold.current && office.draft.text ? <section className="card">
        <h2>{locale === "zh-CN" ? "未发送的指示" : "Unsent direction"}</h2>
        <p>{copy.expiredUnsent}</p>
        <label htmlFor="entry-office-draft">{locale === "zh-CN" ? "给 Meta-CEO 的指示" : "Direction to Meta-CEO"}</label>
        <textarea id="entry-office-draft" value={office.draft.text} onChange={event => office.changeDraft(event.target.value)} rows={4}/>
        <button type="button" onClick={() => office.changeDraft("")}>{locale === "zh-CN" ? "丢弃指示" : "Discard direction"}</button>
      </section> : null}
      {passiveExpiryHold.current && observedConversation.draft ? <section className="card">
        <h2>{locale === "zh-CN" ? "未发送的对话草稿" : "Unsent conversation draft"}</h2>
        <p>{copy.expiredUnsent}</p>
        <label htmlFor="entry-conversation-draft">{locale === "zh-CN" ? "消息" : "Message"}</label>
        <textarea id="entry-conversation-draft" value={observedConversation.draft} onChange={event => observedConversation.changeDraft(event.target.value)} rows={4}/>
        <button type="button" onClick={observedConversation.discardDraft}>{locale === "zh-CN" ? "丢弃消息" : "Discard message"}</button>
      </section> : null}
      {passiveExpiryHold.current && (retainedComposerDrafts.launch || retainedComposerDrafts.launchDetails) ? commandPanel : null}
      {passiveExpiryHold.current && retainedComposerDrafts.session ? sessionPanel : null}
      {showCheckStatus ? <section className="card">
        <h2>{locale === "zh-CN" ? "先前请求" : "Previous request"}</h2>
        <p>{locale === "zh-CN" ? "请检查原请求，不要重新发送。" : "Check the original request. Do not send it again."}</p>
        {checkStatusControl}
      </section> : null}
    </> : undefined} />;
  return (
    <div className="shell" data-theme={theme} data-active-route={active} lang={locale}>
      <a className="skip" href="#content" onClick={event => {
        event.preventDefault();
        document.getElementById("content")?.focus();
      }}>
        {locale === "zh-CN" ? "跳至工作区" : "Skip to workspace"}
      </a>
      {navigationOpen && <button className="navigation-backdrop" aria-label={locale === "zh-CN" ? "关闭导航" : "Close navigation"} tabIndex={-1} onClick={closeNavigation} />}
      <aside id="workspace-navigation" ref={navigationPane} data-open={navigationOpen ? "true" : "false"}>
        <button type="button" className="navigation-close" onClick={closeNavigation}>{locale === "zh-CN" ? "关闭导航" : "Close navigation"}</button>
        <div className="nav-top">
          <div className="brand">
            <span className="brand-mark" aria-hidden="true">
              M
            </span>
            <span className="brand-copy">
              mastermind<small>EXECUTIVE OS</small>
            </span>
          </div>
          <div className="sidebar-new-entry">
          <button type="button" className="sidebar-search sidebar-new-conversation"
            aria-describedby={freshEntryUnavailableReason ? "new-conversation-unavailable" : undefined}
            disabled={!freshHost?.freshConversation || !freshExecutiveOwner()} onClick={openFreshConversation}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><path d="M12 5v14M5 12h14"/></svg>
            {locale === "zh-CN" ? "新建对话" : "New conversation"}
          </button>
          {freshEntryUnavailableReason ? <p id="new-conversation-unavailable" className="sidebar-new-entry-hint">{freshEntryUnavailableReason}</p> : null}
          </div>
          <button type="button" className="sidebar-search" data-agent-route="Search" aria-current={active === "Search" ? "page" : undefined}
            onClick={() => {setProjectTab(null);setActive("Search");if (navigationOpen) closeNavigation();}}>
            <NavigationIcon view="Search"/>{locale === "zh-CN" ? "搜索" : "Search"}
          </button>
          <div className="nav-section">
            <span className="nav-section-label">{locale === "zh-CN" ? "公司" : "COMPANY"}</span>
            <nav aria-label={locale === "zh-CN" ? "公司导航" : "Company navigation"}>
              {primaryNavigation.map((x) => (
                <button
                  key={x}
                  data-agent-route={x}
                  className={active === x ? "active" : ""}
                  aria-label={navigationLabel(x, locale)}
                  aria-current={active === x ? "page" : undefined}
                  onClick={() => {
                    setProjectTab(null);
                    if (x === "Projects") setCatalogueProject(null);
                    if (x === "Conversations") {freshDraftRef.current.hide();conversationNavigation.showList();}
                    setActive(x);
                    if (navigationOpen) closeNavigation();
                  }}
                >
                  <span className="nav-glyph" aria-hidden="true">
                    <NavigationIcon view={x} />
                  </span>
                  <span className="nav-label">{navigationLabel(x, locale)}</span>
                </button>
              ))}
            </nav>
          </div>
        </div>
        <div className="nav-scroll">
          <div className="nav-section mission-nav">
            <span className="nav-section-label">{locale === "zh-CN" ? "工作与上下文" : "WORK & CONTEXT"}</span>
            {selection && d && d.read_state.state === "CURRENT" &&
             d.mission.root_job_id === selection.rootJobId ? (
              <div className="mission-context">
                <b>{d.program.title || selection.workRef}</b>
                <small>{copy.selectedWork}</small>
              </div>
            ) : null}
            <details className="nav-advanced" ref={advancedDisclosure}>
              <summary>{locale === "zh-CN" ? "高级工具" : "Advanced"}</summary>
              <nav aria-label={copy.missionNavigation}>
                {advancedNavigation.map((x) => (
                  <button
                    key={x}
                    data-agent-route={x}
                    className={active === x ? "active" : ""}
                    aria-label={advancedLabel(x, locale)}
                    aria-current={active === x ? "page" : undefined}
                    onClick={() => {
                      setProjectTab(null);
                      if (x === "Conversations") {freshDraftRef.current.hide();conversationNavigation.showList();}
                      setActive(x);
                      if (navigationOpen) closeNavigation();
                    }}
                  >
                    <span className="nav-glyph" aria-hidden="true">
                      <NavigationIcon view={x} />
                    </span>
                    <span className="nav-label">{navigationLabel(x, locale)}</span>
                  </button>
                ))}
              </nav>
            </details>
          </div>
        </div>
        <div className="nav-bottom">
          <div ref={preferencesPane}>{preferencesControl}</div>
          {authState ? (
            <div className="nav-account">
              <small>{partialNativeAuth?.label ?? copy.authStatus[authState.status]}</small>
              {partialNativeAuth ? <p className="muted">{partialNativeAuth.description}</p>
                : authState.reason && authState.status !== "unconfigured" ? (
                <p className="muted">
                  {native ? nativeAuthFeedback(authState, locale) ??
                    (authState.acquisition ? copy.conversationUnavailable : copy.signInFailed)
                    : authState.reason === "POPUP_BLOCKED"
                    ? copy.allowPopup
                    : authState.reason === "POPUP_CLOSED"
                      ? copy.popupClosed
                      : authState.reason.includes("EXPIRED") ||
                          authState.reason.includes("TIMEOUT")
                        ? copy.signInTimeout
                        : authState.acquisition
                          ? copy.conversationUnavailable
                          : copy.signInFailed}
                </p>
              ) : null}
              {active === "Today" && todayNeedsAuthentication ? null : authenticationControl}
              {native && <NativeAuthorizationContinuationControl host={window.MastermindMissionHost} state={authState} revision={authRevision} locale={locale}/>}
              {native && <NativeWorkAuthorizationControl host={window.MastermindMissionHost} state={authState} revision={authRevision} locale={locale} beforeSignIn={() => nativeGoalRef.current.onAuthChange(false)}/>}
            </div>
          ) : null}
        </div>
      </aside>
      <main id="content" tabIndex={-1}>
        <header className={quietHeader ? "workspace-header workspace-header-quiet" : "workspace-header"}>
          <div className="workspace-route">
            <button ref={navigationToggle} type="button" className="navigation-toggle" aria-expanded={navigationOpen} aria-controls="workspace-navigation" aria-label={locale === "zh-CN" ? "打开导航" : "Open navigation"} onClick={() => setNavigationOpen(value => !value)}><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><path d="M4 6h16M4 12h16M4 18h16" /></svg></button>
            {active !== "Activity" && <span className="eyebrow">{directRoute ? (locale === "zh-CN" ? "单个只读任务" : "One read-only task") : newProjectRoute ? (locale === "zh-CN" ? "新建项目" : "New project") : navigationLabel(active, locale)}</span>}
            {quietHeader ? <h2 ref={routeHeading} tabIndex={-1}>{newProjectRoute ? (locale === "zh-CN" ? "新建项目" : "New project") : navigationLabel(active, locale)}</h2> : <h1 ref={routeHeading} tabIndex={-1}>
              {directRoute ? (locale === "zh-CN" ? "原生任务" : "Native task") : navigationLabel(active, locale)}
            </h1>}
            {!quietHeader && <p>{directRoute ? (locale === "zh-CN" ? "读取当前任务结果，再单独确认接收。" : "Read this task’s result, then acknowledge it separately.") : active === "Activity" ? (locale === "zh-CN" ? "此项目已记录的工作与结果。来源信息可能不完整。" : "Recorded work and results for this project. Source information may be incomplete.") : headerSummary}</p>}
          </div>
          <div className="facts">
            {active === "Team" ? null : active === "Tools" || active === "Sources" ? <details className="workspace-qualification"><summary>{active === "Tools" ? (locale === "zh-CN" ? "工具上下文" : "Tool context") : (locale === "zh-CN" ? "来源与范围" : "Sources and scope")}</summary><State value={headerState}/><p>{headerSummary}</p><p>{visibleNotice}</p><p>{copy.statusNote}</p></details> : active === "Activity" ? <details className="workspace-qualification mm-activity-source-status"><summary>{locale === "zh-CN" ? "来源与范围" : "Sources and scope"}</summary><State value={headerState}/><p>{headerSummary}</p><p>{visibleNotice}</p><p>{copy.statusNote}</p></details> : !directRoute ? quietHeader ? <details className="workspace-qualification"><summary>{active === "Conversations" || active === "Meta-CEO" || active === "Fleet & Capacity" || newProjectRoute ? (locale === "zh-CN" ? "来源与访问" : "Sources and access") : reading.qualificationLabel} {active !== "Conversations" && active !== "Meta-CEO" && active !== "Fleet & Capacity" && !newProjectRoute ? <State value={headerState} /> : null}</summary>{newProjectRoute ? <p>{locale === "zh-CN" ? "工作区项目列表与现有任务" : "Workspace project list and existing tasks"}</p> : null}{active === "Conversations" || active === "Meta-CEO" || active === "Fleet & Capacity" || newProjectRoute ? <State value={headerState} /> : null}<p>{headerSummary}</p>{reading.readinessDiagnostic ? <><p role="status">{reading.statusNotice}</p><p><code>{reading.readinessDiagnostic}</code></p></> : <p role="status">{visibleNotice}</p>}<p><b>{copy.statusSources}</b><br />{copy.statusNote}</p></details> : <State value={headerState} text={active === "Session Estate" && headerState === "UNAVAILABLE" ? copy.unavailable : undefined} /> : null}
          </div>
        </header>
        {nativeGoalNotice}
        {!native && authState && authState.status === "signed_out" &&
         passiveExpiryHold.current && hasUnsentUserText.current ? (
          <section className="notice" aria-label={copy.unsentProtected}>
            <p>{copy.expiredUnsent}</p>
            <button type="button" onClick={() => {
              freshDraftRef.current.invalidateAuth(false);
              freshTurnDraftRef.current.invalidateAuth(false);
              freshAttendedRef.current?.controller.invalidate();
              projectJourney.invalidateAuth(false);
              office.changeDraft("");
              observedConversation.discardDraft();
              updateRetainedComposer("launch", "");
              updateRetainedComposer("launchDetails", null);
              updateRetainedComposer("session", "");
              passiveExpiryHold.current = false;
            }}>{copy.discardAll}</button>
          </section>
        ) : null}
        {active !== "Team" && active !== "Control Room" && active !== "Fleet & Capacity" && active !== "Today" && active !== "Conversations" && active !== "Activity" && active !== "Tools" && active !== "Sources" && !directRoute &&
          !((active === "Meta-CEO" || active === "Inbox" || active === "Projects" && (projectJourney.shown || projectJourney.invalidLink)) && visibleNotice === "Choose a Program with one resolved mission before opening the workspace.") &&
          !reading.suppressBodyNotice &&
          !(active === "Projects" && (projectJourney.shown || projectJourney.invalidLink) && reading.readinessDiagnostic !== null) ? (
          <div className="notice" role="status">{visibleNotice === "Choose a Program with one resolved mission before opening the workspace."
            ? locale === "zh-CN" ? "选择一个项目，查看其工作。" : "Choose a project to view its work."
            : visibleNotice}</div>
        ) : null}
        {build ? (
          <details className="build-details">
            <summary>{copy.buildDetails}</summary>
            <dl>
              <dt>{copy.version}</dt>
              <dd>{build.version}</dd>
              <dt>{copy.sourceRevision}</dt>
              <dd>
                <code>{build.source_revision}</code>
              </dd>
              <dt>{copy.buildIdentity}</dt>
              <dd>
                <code>{build.build_identity}</code>
              </dd>
              {build.native_client_ref ? (
                <>
                  <dt>{copy.nativeClient}</dt>
                  <dd>
                    <code>{build.native_client_ref}</code>
                  </dd>
                </>
              ) : null}
              <dt>{copy.transport}</dt>
              <dd>{`${build.transport} / ${build.state}`}</dd>
            </dl>
          </details>
        ) : null}
        {reopenedOperationControl}
        {active === "Search" && hasProjectSearch && !savedConversationNavigation && <div role="group" aria-label={locale === "zh-CN" ? "搜索范围" : "Search scope"}>
          <button type="button" aria-pressed={projectSearchSelected} onClick={() => setProjectSearchSelected(true)}>{locale === "zh-CN" ? "项目来源" : "Project sources"}</button>
          <button type="button" aria-pressed={!projectSearchSelected} onClick={() => setProjectSearchSelected(false)}>{locale === "zh-CN" ? "公司引用" : "Company references"}</button>
        </div>}
        {active === "Knowledge" && hasProjectLibrary && <div role="group" aria-label={locale === "zh-CN" ? "知识来源" : "Knowledge sources"}>
          <button type="button" aria-pressed={knowledgeMode === "project"} onClick={() => { setRequestedProjectFile(undefined); setKnowledgeMode("project"); }}>{locale === "zh-CN" ? "项目资料库" : "Project library"}</button>
          <button type="button" aria-pressed={knowledgeMode === "retained"} onClick={() => setKnowledgeMode("retained")}>{locale === "zh-CN" ? "已保留的任务来源" : "Retained task sources"}</button>
        </div>}
        {hasProjectSearch && <section ref={projectSearchRegion} hidden={active !== "Search" || !projectSearchSelected || Boolean(savedConversationNavigation)} aria-hidden={active !== "Search" || !projectSearchSelected || Boolean(savedConversationNavigation)}>
          <ProjectSearchWorkspace workRef={projectWorkRef} authGeneration={authRevision}
            hostGeneration={archiveHostGeneration} locale={locale} theme={theme}
            sessionHistory={projectHistoryOwner} savedHistory={projectConversationHistory.history}
            projectFiles={retainedResultHost?.projectFilesSearch}
            onOpenFile={match => {
              if (!projectWorkRef || archiveHostGeneration === null || !projectReaders.canRead()) return;
              setRequestedProjectFile(Object.freeze({match, workRef: projectWorkRef, authGeneration: authRevision, hostGeneration: archiveHostGeneration}));
              setKnowledgeMode("project"); setActive("Knowledge");
            }}
            onOpenSaved={(match, page) => {
              if (!projectWorkRef || archiveHostGeneration === null) return;
              const navigation = createSavedConversationNavigation({workRef: projectWorkRef, authGeneration: authRevision,
                hostGeneration: archiveHostGeneration, match, ...page}, projectHistoryOwner);
              if (navigation) setSavedConversationNavigation(navigation);
            }}/>
        </section>}
        {content}
        {d && active === "Activity" ? <details className="reason-details mm-activity-source-gaps"><summary>{locale === "zh-CN" ? "来源缺失详情" : "Source gaps"}</summary>            {d.missingness.length ? (
              <ul className="missing">
                {d.missingness.map((x, i) => (
                  <li key={i}>
                    <State value={x.missingness_class} />{" "}
                    <code>{x.target_field}</code> — {x.reason}
                  </li>
                ))}
              </ul>
            ) : (
              <Empty>
                No missingness facts were projected. This adds no freshness
                claim.
              </Empty>
            )}</details> : d && missionNavigation.includes(active) && !conversationActive && (
          <section className="card">
            <h2>Missingness and source state</h2>
            {d.missingness.length ? (
              <ul className="missing">
                {d.missingness.map((x, i) => (
                  <li key={i}>
                    <State value={x.missingness_class} />{" "}
                    <code>{x.target_field}</code> — {x.reason}
                  </li>
                ))}
              </ul>
            ) : (
              <Empty>
                No missingness facts were projected. This adds no freshness
                claim.
              </Empty>
            )}
          </section>
        )}
      </main>
    </div>
  );
}
