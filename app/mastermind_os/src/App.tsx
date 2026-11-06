import { appCopy } from "./app-copy";
import { ProductAcceptancePanel } from "./product-acceptance/ProductAcceptancePanel";
import type { AuthState, MissionHost } from "./host";
import type {
  ObservedMissionAssociation,
  WindowDocument,
} from "./workspace-contract";
import { observedMissionAssociation } from "./workspace-contract";
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import {
  canNavigateForAutomaticSignIn, explicitLogoutRecorded, registerUnsavedNavigationHold,
} from "./auth-navigation-guard";
import { MetaCeoOffice } from "./meta-ceo/MetaCeoOffice";
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
import { ProjectArchiveBrowser } from "./projects/archive/ProjectArchiveBrowser";
import { ProjectWorkspace } from "./projects/ProjectWorkspace";
import { ProjectConversationAssociation } from "./conversations/ProjectConversationAssociation";
import { AcceptedDirectionPanel } from "./direction/AcceptedDirectionPanel";
import { useProjectAdmissionWorkspace } from "./useProjectAdmissionWorkspace";
import { useProjectDetailsControls } from "./projects/useProjectDetailsControls";
import { InboxWorkspace } from "./inbox/InboxWorkspace";
import { Knowledge } from "./knowledge/Knowledge";
import { knowledgeDraftBinding, type KnowledgeDraftPort } from "./knowledge/KnowledgeDraftCompanion";
import type { ProjectSourceDraftPort } from "./knowledge/library/project-source-draft";
import { useProjectKnowledgeWorkspace } from "./knowledge/useProjectKnowledgeWorkspace";
import { ProjectKnowledgeEditor } from "./knowledge/library/ProjectKnowledgeEditor";
import type { ProjectMemoryDocument, KnowledgeLibrarySourceContext } from "./knowledge/library/knowledge-library-contract";
import { ProjectKnowledgeLibrary } from "./knowledge/library/ProjectKnowledgeLibrary";
import type { KnowledgeLibraryProps } from "./knowledge/library/knowledge-library-contract";
import { ProjectSearchWorkspace } from "./discovery/ProjectSearchWorkspace";
import { SavedConversationReader, createSavedConversationNavigation, type SavedConversationNavigation } from "./discovery/SavedConversationReader";
import { DiscoveryWorkspace } from "./discovery/DiscoveryWorkspace";
import { projectDiscovery } from "./discovery/projection";
import { ProjectWorkDetail, ProjectEvidence, ProjectJournal } from "./workJourney";
import { ConversationWindow } from "./conversations/ConversationWindow";
import { HistoricalOriginalAnswers } from "./conversations/HistoricalOriginalAnswers";
import { RetainedResults } from "./RetainedResults";
import { RetainedRootChoice } from "./RetainedRootChoice";
import { normalizeResultReferencesSelection } from "./result-references";
import { parseDirectConsumeTarget } from "./direct-native-result";
import { createAwaitingAnswerPort } from "./conversations/awaiting-answer-port";
import { useQualifiedOriginalAnswer } from "./conversations/useQualifiedOriginalAnswer";
import type { QualifiedSessionAnswer } from "./orchestration/executive-session-command-port";
import { useObservedConversation } from "./conversations/useObservedConversation";
import {
  OperationController,
  type OperationKind,
  type OperationPointer,
  type OperationState,
} from "./orchestration/operation-controller";
import {
  LaunchOrchestrator,
  type LaunchForm,
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
import { selectedCurrentCapacityAttempt } from "./resource-capacity-selection";
import { SupervisionLedger } from "./supervision/SupervisionLedger";
import { SupervisionTrace } from "./supervision/SupervisionTrace";
import { ProjectPlanPanel } from "./planning/ProjectPlanPanel";
import { ProjectJournalReader } from "./ProjectJournalReader";
import { AutonomyPanel } from "./supervision/AutonomyPanel";
import { ActivationReceipt } from "./activation/ActivationReceipt";
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
import { closedReadFailurePhase, closedReadFailureReason, type DiagnosticPhase, type DiagnosticReadReason } from "./diagnostic-state";
export const navigation = [
  "Today",
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
  if (locale === "en") return view;
  const labels: Record<View, string> = { Search: "搜索", Sources: "来源", Tools: "工具", "Session Estate": "会话工作区", Today: "今天", Projects: "项目", Inbox: "收件箱", Conversations: "对话", Knowledge: "知识", "Meta-CEO": "Meta-CEO 办公室", Work: "工作", Programs: "工作流", "Control Room": "控制室", "Fleet & Capacity": "计算资源", "Mission Workspace": "任务工作区", Conversation: "当前对话", Activity: "活动", Connections: "连接", Evidence: "证据" };
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
type ReopenedOperation = {
  binding: OrchestratorCommandBinding;
  principalScope: string;
  generation: string;
  authRevision: number;
  selectionSeq: number;
  pointer: OperationPointer | null;
  reason: "READING" | OperationState["reason"];
};
const display = (v: unknown, f = "Not established") =>
  typeof v === "string" && v ? v : f;
const label = (v: unknown) => display(v, "UNKNOWN").replaceAll("_", " ");
const isDoc = (v: MissionDocument | UnavailableMission): v is MissionDocument =>
  !("kind" in v);
const isDocv3 = (
  v: Missionv3Document | UnavailableMission | null,
): v is Missionv3Document => !!v && !("kind" in v);
function State({ value }: { value: unknown }) {
  return (
    <span className={`state state-${String(value ?? "UNKNOWN").toLowerCase()}`}>
      {label(value)}
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

function ResultCard({ state }: { state: ResultState }) {
  if (state.kind === "IDLE") return null;
  const title =
    state.selection.jobId + " / " + state.selection.attemptId.slice(0, 8) + "…";
  if (state.kind === "PENDING") {
    return (
      <section className="card">
        <div className="section-title">
          <h2>Result detail</h2>
          <State value="SOURCE_READ_PENDING" />
        </div>
        <p className="muted">Reading the exact selected tuple…</p>
        <code>{title}</code>
      </section>
    );
  }
  if (state.kind === "UNAVAILABLE") {
    return (
      <section className="card">
        <div className="section-title">
          <h2>Result detail</h2>
          <State value="UNAVAILABLE" />
        </div>
        <p className="muted">{state.reason}</p>
        <code>{title}</code>
      </section>
    );
  }
  const doc = state.document;
  const result = doc.result;
  if (doc.availability === "UNAVAILABLE" || !result) {
    return (
      <section className="card">
        <div className="section-title">
          <h2>Result detail</h2>
          <State value={doc.availability} />
        </div>
        <p className="muted">
          The bounded result read returned a typed unavailability response:{" "}
          <code>{doc.reason_codes[0] ?? "SOURCE_UNAVAILABLE"}</code>. This is
          not a producer acceptance and adds no result history.
        </p>
        <code>{title}</code>
        <details className="reason-details">
          <summary>Technical details</summary>
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
    <section className="card">
      <div className="section-title">
        <h2>Result detail</h2>
        <State value={doc.availability} />
      </div>
      {doc.availability !== "AVAILABLE" ? (
        <p className="muted">
          <code>{doc.reason_codes.join(" · ")}</code>
        </p>
      ) : null}
      <dl>
        <dt>Role</dt>
        <dd>{label(result.role)}</dd>
        <dt>Execution</dt>
        <dd>{label(result.execution_status)}</dd>
        <dt>Acceptance</dt>
        <dd>
          <State value={result.acceptance} />
        </dd>
        <dt>Review</dt>
        <dd>{review === null ? "Not a review role" : verdictLabel}</dd>
        <dt>Findings</dt>
        <dd>
          {counts === null
            ? "No findings tracked for this role"
            : `Total ${counts.total} · blocking ${counts.blocking} · warning ${counts.warning} · info ${counts.info}`}
        </dd>
        <dt>Next actions</dt>
        <dd>
          {result.counts.next_actions === 0
            ? "None reported"
            : `${result.counts.next_actions} item(s)`}
        </dd>
        <dt>Envelope digest</dt>
        <dd>
          <code>{result.selection.result_envelope_digest}</code>
        </dd>
        {review ? (
          <>
            <dt>Reviewed job and attempt</dt>
            <dd>
              <code>
                {review.reviewed_job_id} · {review.reviewed_attempt_id}
              </code>
            </dd>
            <dt>Reviewed role-result digest</dt>
            <dd>
              <code>{review.reviewed_result_digest}</code>
            </dd>
          </>
        ) : null}
        <dt>Role-result digest</dt>
        <dd>
          <code>{result.role_result_digest}</code>
        </dd>
        <dt>Selection</dt>
        <dd>
          <code>
            {result.selection.root_job_id +
              " · " +
              result.selection.job_id +
              " · " +
              result.selection.attempt_id}
          </code>
        </dd>
        <dt>Omitted</dt>
        <dd>
          {result.omitted.length === 0
            ? "Whole content shown for this role."
            : result.omitted.map((x) => label(x)).join(" · ")}
        </dd>
      </dl>
      {result.content === null ? (
        <Empty>
          Content omitted by owner. Counts and digests remain, but the full role
          result body was not delivered within the bounded response. A full
          result link is not provided.
        </Empty>
      ) : (
        <article className="result-content">
          <h3>Structured role result</h3>
          <pre className="visible-text">
            {JSON.stringify(result.content.role_result, null, 2)}
          </pre>
          <h3>Summary</h3>
          <pre className="visible-text">{result.content.summary}</pre>
          {result.content.next_actions.length > 0 ? (
            <>
              <h3>Next actions</h3>
              <ul className="artifact-list">
                {result.content.next_actions.map((x, i) => (
                  <li key={`na-${i}`}>{x}</li>
                ))}
              </ul>
            </>
          ) : null}
        </article>
      )}
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
function Activity({ d }: { d: MissionDocument }) {
  return (
    <>
      <section className="card activity-summary">
        <div className="section-title">
          <div>
            <h2>Activity</h2>
            <p className="muted">
              The same admitted Mission document, organized by current work
              posture. Opening this view performs no extra read and starts no
              work.
            </p>
          </div>
          <State value={d.execution.state} />
        </div>
        <div className="activity-facts">
          <div>
            <small>EXECUTION</small>
            <State value={d.execution.state} />
          </div>
          <div>
            <small>REVIEW</small>
            <State value={d.review.verdict} />
          </div>
          <div>
            <small>TRANSPORT</small>
            <State value={d.transport.dispatch_state} />
          </div>
          <div>
            <small>ACCEPTANCE</small>
            <State value={d.acceptance.state} />
          </div>
          <div>
            <small>POSTURE</small>
            <State value={d.posture.value} />
          </div>
        </div>
      </section>
      <section className="card">
        <div className="section-title">
          <div>
            <h2>Live work</h2>
            <p className="muted">
              Canonical child facts from this Mission snapshot. Missing joins
              remain missing; a row is never promoted to running from UI state.
            </p>
          </div>
          <State value={d.children.state} />
        </div>
        {d.children.items.length ? (
          <ul className="items activity-items">
            {d.children.items.map((item, index) => (
              <li key={item.job_id ?? `unidentified-activity-${index}`}>
                <code>{display(item.job_id, "Unidentified child")}</code>
                <State value={item.status} />
                <small>
                  {display(item.orchestration_role)} · attempt{" "}
                  {item.latest_attempt?.status ?? "not established"}
                </small>
              </li>
            ))}
          </ul>
        ) : (
          <Empty>
            No bounded child rows are available. This is not evidence of zero
            work.
          </Empty>
        )}
        <p className="muted">
          {d.children.coverage === "INCOMPLETE"
            ? "Coverage is incomplete; known rows are not the complete queue."
            : "The owner reported complete child coverage for this observation."}
        </p>
      </section>
    </>
  );
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
}: {
  active: ProjectTab;
  onChange: (tab: ProjectTab) => void;
  tablistRef?: React.Ref<HTMLDivElement>;
}) {
  return (
    <nav className="card" aria-label="Project sections">
      <div ref={tablistRef} className="segmented" role="tablist" aria-label="Project workspace">
        {projectTabs.map((tab) => (
          <button
            key={tab}
            type="button"
            role="tab"
            aria-selected={active === tab}
            onClick={() => onChange(tab)}
          >
            {tab}
          </button>
        ))}
      </div>
    </nav>
  );
}

function ProjectPlan({ d }: { d: MissionDocument }) {
  return (
    <>
      <section className="card source-gap">
        <div className="section-title">
          <div>
            <h2>Plan</h2>
            <p className="muted">
              Agent OS plan content is not projected through the current
              approved app source.
            </p>
          </div>
          <State value="NOT_PROJECTED" />
        </div>
        <p>
          This project view does not reconstruct a plan from Mission, Work,
          GitHub, or conversation data. The current Mission context below is
          shown only to preserve continuity while the plan owner is absent.
        </p>
      </section>
      <section className="card">
        <div className="section-title">
          <h2>Current project context</h2>
          <State value={d.read_state.state} />
        </div>
        <dl>
          <dt>Project</dt>
          <dd>{d.program.title || d.program.work_ref}</dd>
          <dt>Next source-qualified action</dt>
          <dd>
            {display(
              d.program.next_action,
              "No next action was projected by the Mission source.",
            )}
          </dd>
          <dt>Accountable seat</dt>
          <dd>{display(d.principal.accountable_seat)}</dd>
          <dt>Owed turn</dt>
          <dd>
            {d.principal.owed_turn
              ? `${display(d.principal.owed_turn.seat)} · ${display(d.principal.owed_turn.reason)}`
              : "Not established"}
          </dd>
        </dl>
      </section>
    </>
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
          <h2>Journal</h2>
          <State value="NOT_PROJECTED" />
        </div>
        <p>
          No qualified journal source is installed in this project view. No
          history is inferred.
        </p>
      </section>
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
    initial = useMemo(
      () =>
        initialLocation.hasIdentity
          ? initialLocation.selection
          : normalizeSelection(window.MastermindMissionHost?.selection),
      [initialLocation],
    ),
    [selection, setSelection] = useState<MissionSelection | null>(initial),
    [active, setActive] = useState<View>(initial && new URL(window.location.href).searchParams.get("direct_native_job")===initial.rootJobId ? "Projects" : "Today"),
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
    [catalogueProject, setCatalogueProject] = useState<{workRef: string; authRevision: number; epoch: number} | null>(null),
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
    [officeLaunchHandoff, setOfficeLaunchHandoff] = useState<{
      preview: DirectionPreview;
      workstreamRef: string;
      binding: OrchestratorCommandBinding;
      principalScope: string;
      generation: string;
    } | null>(null),
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
    [retainedComposerDrafts, setRetainedComposerDrafts] = useState({ launch: "", session: "", launchWorkstream: "" }),
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
    programSelection = useRef(selection),
    workRequest = useRef(0),
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
  retainedComposerRef.current = retainedComposerDrafts;
  // The currently authenticated command scope is checked below, after the
  // qualified host identity has been read. Off-view Office text is inspected
  // independently of whether its component is mounted.
  const updateRetainedComposer = (kind: "launch" | "session" | "launchWorkstream", text: string) => {
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
  const liveComposerScope = ownerContext ? JSON.stringify([
    ownerContext.principalScope, ownerContext.generation,
    selection?.workRef, selection?.rootJobId, authRevision,
  ]) : null;
  // The App-level text snapshots are usable only by their originating
  // selection/owner epoch, even when a mounted leaf is later replaced.
  const presentedComposerDrafts = liveComposerScope &&
    retainedComposerScope.current === liveComposerScope
      ? retainedComposerDrafts : { launch: "", session: "", launchWorkstream: "" };
  useEffect(() => {
    if (!signedIn || !liveComposerScope) return;
    if (previousLiveComposerScope.current !== null &&
        previousLiveComposerScope.current !== liveComposerScope) {
      const blank = { launch: "", session: "", launchWorkstream: "" };
      retainedComposerRef.current = blank;
      retainedComposerScope.current = null;
      setRetainedComposerDrafts(blank);
    }
    previousLiveComposerScope.current = liveComposerScope;
  }, [signedIn, liveComposerScope]);
  // The session owner context and host-projected target stay fenced on the
  // live signed-in state; the binding itself is read once per render above.
  const sessionOwner =
    sessionBinding && signedIn ? readSessionOwnerContext(sessionBinding) : null;
  const sessionTargetKey = sessionOwner && sessionBinding
    ? sessionBinding.port.currentTargetRef()
    : null;
  // Read-only exact-session association from the existing Executive owner.
  // Unknown/legacy/DSH/Grok native sessions stay UNBOUND, not guessed.
  const officeSession = qualifyExecutiveOfficeSession(
    signedIn, selection, sessionBinding,
  );
  const office = useOfficeProjection(authRevision, selection, officeSession);
  const byokRoles = useByokRoleObservation({
    active: active === "Meta-CEO",
    acquisition: signedIn && authState?.acquisition === true,
    authRevision,
  });
  // The Office draft is part of the unsent-text signal. It is read after the
  // session-qualified projection exists, never before.
  hasUnsentUserText.current = Boolean(office.draft.text ||
    observedConversation.hasUnsentDraft() ||
    (signedIn ? presentedComposerDrafts.launch || presentedComposerDrafts.session
      : retainedComposerDrafts.launch || retainedComposerDrafts.session));
  const projectConversationActive = active === "Projects" && projectTab === "Conversation" && !catalogueProject &&
    missionSelectionState === "AVAILABLE" && office.projection.programs.source.state === "CURRENT" && !!selection &&
    index.programs.filter(card => card.workRef === selection.workRef).length === 1 &&
    index.programs.some(card => card.workRef === selection.workRef && card.rootState === "RESOLVED" &&
      card.rootJobId === selection.rootJobId && card.rootCandidates.length === 1 &&
      card.rootCandidates[0] === selection.rootJobId);
  const answerView = useQualifiedOriginalAnswer();
  // React may abandon an interrupted render. Only the committed layout
  // publishes a current identity to the private reply acceptance fence.
  useLayoutEffect(() => {
    answerView.setCurrent(sessionBinding && sessionOwner && signedIn ? {
      binding: sessionBinding,
      principalScope: sessionOwner.principalScope,
      generation: sessionOwner.generation,
      selectionSeq: selectionSeq.current,
      authRevision,
      active: active === "Conversations" || projectConversationActive,
    } : null);
  }, [active, projectConversationActive, signedIn, sessionBinding, sessionOwner?.principalScope,
    sessionOwner?.generation, authRevision, selection?.workRef, selection?.rootJobId]);
  const ownsSession = (binding: MountedExecutiveSessionBinding, ctx: { principalScope: string; generation: string }, sequence: number) => {
    const liveBinding = completeExecutiveSessionBinding(window.MastermindMissionHost?.sessionCommandBinding);
    const liveContext = liveBinding ? readSessionOwnerContext(liveBinding) : null;
    return liveBinding === binding && selectionSeq.current === sequence &&
      window.MastermindMissionHost?.auth?.getState().status === "signed_in" &&
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
    const wrapper = createAwaitingAnswerPort<QualifiedSessionAnswer>({
      port: binding.port,
      readAnswer: (pointer, signal) => typeof binding.port.readQualifiedAnswer === "function"
        ? binding.port.readQualifiedAnswer(pointer, signal)
        : Promise.resolve({ receipt: { ...pointer, disposition: "unknown", reason: "UNKNOWN_RECEIPT" }, answer: null }),
      isCurrent: () => ownsSession(binding, ctx, sequence) && answerView.isCurrent(identity),
      onAdmission: () => { if (ownsSession(binding, ctx, sequence)) answerView.invalidate(); },
      onAnswer: (pointer, answer) => answerView.stage(identity, pointer, answer),
    });
    return new OperationController(wrapper, binding.store);
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
    pendingCommand.current !== null || heldKind !== null || recoverInFlight ||
    (passiveExpiryHold.current && hasUnsentUserText.current)
  ), [heldKind, recoverInFlight]);

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
    void sessionControl.refresh(selection);
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
      else if (isRetainedOperation(value)) setReopenedOperation({ ...identity, pointer: value, reason: "PENDING_POINTER" });
      else setReopenedOperation({ ...identity, pointer: null, reason: "MALFORMED_POINTER" });
    }).catch(() => {
      if (ownsDiscovery()) setReopenedOperation({ ...identity, pointer: null, reason: "LOCAL_UNAVAILABLE" });
    });
    return () => { cancelled = true; abort.abort(); };
  }, [commandBinding, ownerContext?.principalScope, ownerContext?.generation,
    authRevision, commandSelectionRevision, selection?.workRef, selection?.rootJobId]);
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
    if (active !== "Conversations" && !projectConversationActive) answerView.leavePresentation();
  }, [active, projectConversationActive]);

  useEffect(() => () => {
    commandSlot.current?.controller.invalidate();
    recoveryFlight.current++;
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
        controlRoomAuthEpoch.current += 1;
        if (passiveLoss && hasUnsentUserText.current)
          passiveExpiryHold.current = true;
        else if (state.status === "signing_in" || state.acquisition ||
                 state.content || state.reason === "USER_SIGNED_OUT" ||
                 explicitLogoutRecorded())
          passiveExpiryHold.current = false;
        if (!passiveLoss) {
          const blank = { launch: "", session: "", launchWorkstream: "" };
          retainedComposerRef.current = blank;
          retainedComposerScope.current = null;
          setRetainedComposerDrafts(blank);
        }
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
    if (!initialLocation.hasIdentity && initial) {
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
  }, [initial, initialLocation.hasIdentity]);
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
          return { raw: observation.controlRoom, observation };
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
      const next = directLocationInput().selection;
      office.clearSelection(next);
      observedConversation.clear();
      selectionSeq.current += 1;
      invalidateSessionPresentation();
      void window.MastermindMissionHost?.session?.refresh(next);
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
    const readV3 = window.MastermindMissionHost?.readMissionV3;
    const read = readV3 ?? window.MastermindMissionHost?.readMission;
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
      .then(() => read({ ...selection, signal: controller.signal }))
      .then((raw) => {
        if (!attached || missionRequest.current !== current) return;
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
          ? "Observed owner window for the exact selected Mission; session identity and send authority remain separate."
          : "Conversation content is shown only from a qualified paired Mission and Current Window observation."
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
          ? "Reading the paired Mission and current permitted window…"
          : observedConversation.projection.conversation.source.state ===
              "CURRENT"
            ? "Observed conversation window for the selected Mission; no recipient or send authority is inferred."
            : "No qualified observed conversation is currently established."
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
              : notice,
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
        void window.MastermindMissionHost?.session?.refresh(next);
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
      // Only this owner-qualified accepted launch releases its Office handoff.
      // A refusal or unknown effect keeps the frozen context and original hold.
      setOfficeLaunchHandoff(null);
      if (sel) open(sel.workRef, sel.rootJobId,bindingAtStart.directNative?.isDirectSelection(sel)===true);
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
    const ctx = binding ? readSessionOwnerContext(binding) : null;
    const liveTarget = binding ? binding.port.currentTargetRef() : null;
    if (!binding || liveAuth?.status !== "signed_in" || !ctx || !liveTarget) {
      onComplete({ status: "refused" });
      return;
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
    const ctx = binding ? readSessionOwnerContext(binding) : null;
    const slot = sessionSlot.current;
    if (!binding || liveAuth?.status !== "signed_in" || !ctx || !slot) return;
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
  const reopenedOperationControl = currentReopened ? (
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
  // Observer-only snapshot for the fallback disclosures. A throwing or
  // absent getter degrades to null, which the fields render as unknown
  // values; reading it triggers no request, refresh or subscription change.
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
    return readLaunchRequestPreview(binding, form);
  }, [commandBinding, ownerContext?.principalScope, ownerContext?.generation, authRevision]);
  // Presentation reuses the incumbent explicit auth action and its guards.
  const authenticationControl = authState ? (
                <button
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
    const alreadyOpen = officeLaunchHandoff !== null &&
      officeLaunchHandoff.preview.draft === preview.draft &&
      previewIsCurrent(officeLaunchHandoff.preview, office.projection.context);
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
    retainedComposerScope.current = liveComposerScope;
    updateRetainedComposer("launch", preview.draft);
    updateRetainedComposer("launchWorkstream", frozenWorkstream!);
    setLaunchDraftDismissed(false);
    setOfficeLaunchHandoff({
      preview,
      workstreamRef: frozenWorkstream!,
      binding: liveBinding!,
      principalScope: liveOwner!.principalScope,
      generation: liveOwner!.generation,
    });
    return outcome;
  };
  const commandPanel =
    !signedIn && passiveExpiryHold.current && retainedComposerDrafts.launch ? (
      <section className="card" aria-label={copy.retainedDraft}>
        <h2>{copy.unsentGoal}</h2>
        <p className="muted">{copy.expiredDraft}</p>
        <label htmlFor="retained-launch-goal">{copy.goal}</label>
        <textarea id="retained-launch-goal" value={retainedComposerDrafts.launch}
          onChange={event => updateRetainedComposer("launch", event.target.value)}
          rows={4} />
        <button type="button" onClick={() => updateRetainedComposer("launch", "")}>
          {copy.discardGoal}
        </button>
      </section>
    ) : canLaunch && commandView && launchDraftDismissed ? (
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
    ) : commandReady && commandView ? (
      <>
        <LaunchOrchestrator
          presentation={active === "Today" ? "composer" : "standard"}
          previewRequest={previewLaunchRequest}
          locale={locale}
          key={JSON.stringify([
            ownerContext?.principalScope,
            ownerContext?.generation,
          ])}
          workstreams={commandView.workstreams}
          defaultWorkstream={commandView.defaultWorkstream}
          workstreamRef={officeLaunchHandoff?.workstreamRef || presentedComposerDrafts.launchWorkstream || undefined}
          lockWorkstream={officeLaunchHandoff !== null}
          onWorkstreamChange={workstream => {
            const liveBinding = completeOrchestratorCommandBinding(window.MastermindMissionHost?.commandBinding);
            const liveOwner = liveBinding ? readOwnerContext(liveBinding.port) : null;
            if (!officeLaunchHandoff && authRevisionRef.current === authRevision &&
                window.MastermindMissionHost?.auth?.getState().status === "signed_in" &&
                liveBinding === commandBinding &&
                liveOwner?.principalScope === ownerContext?.principalScope &&
                liveOwner?.generation === ownerContext?.generation) {
              retainedComposerScope.current = liveComposerScope;
              updateRetainedComposer("launchWorkstream", workstream);
            }
          }}
          projects={commandView.projects}
          profiles={commandView.profiles}
          frontierModels={commandView.frontierModels}
          initialDraft={presentedComposerDrafts.launch}
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
              if (!retainedComposerRef.current.launchWorkstream && commandView.defaultWorkstream)
                updateRetainedComposer("launchWorkstream", commandView.defaultWorkstream);
            }
          }}
          unavailableReason={
            canLaunch
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
            if (officeLaunchHandoff) {
              const liveOwner = readOwnerContext(binding.port);
              const config = readLaunchBindingConfig();
              const enrolled = config ? resolveLaunchBinding(config, officeLaunchHandoff.workstreamRef) : null;
              const workstreamAgrees = officeLaunchWorkstreamAgrees(
                officeLaunchHandoff.preview.context.selection?.workRef ?? null,
                enrolled?.workstream ?? null) && form.workstreamRef === officeLaunchHandoff.workstreamRef;
              if (!previewIsCurrent(officeLaunchHandoff.preview, office.projection.context) ||
                  binding !== officeLaunchHandoff.binding ||
                  liveOwner?.principalScope !== officeLaunchHandoff.principalScope ||
                  liveOwner?.generation !== officeLaunchHandoff.generation ||
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
                    ? "方向交接已不再有效。未准备也未发送任何内容。"
                    : "The direction handoff is no longer current. Nothing was prepared or sent.",
                });
                onComplete({ status: "refused" });
                return;
              }
            }
            const intent = launchIntentFromBinding(binding, form);
            if (officeLaunchHandoff && (!intent ||
                intent.targetKey !== officeLaunchHandoff.workstreamRef ||
                intent.payload.workstream !== officeLaunchHandoff.workstreamRef)) {
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
            setLaunchDraftDismissed(true);
            // The Office handoff closes with its own form. The Office draft
            // itself is never cleared by a cancel.
            setOfficeLaunchHandoff(null);
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
        <p className="muted">{locale === "zh-CN" ? "暂时无法开始工作。" : "Starting work is unavailable right now."}</p>
        <details
          className="reason-details"
          onToggle={(event) => {
            if ((event.currentTarget as HTMLDetailsElement).open) setDiagnosticTick((n) => n + 1);
          }}
        >
          <summary>{copy.technicalDetails}</summary>
          <code>{COMMAND_ROUTE_UNAVAILABLE}</code>
          <TransportDiagnosticFields
            snapshot={missionDiagnostics()}
            programsPhase={programsReadPhase}
            programsReason={programsReadReason}
            locale={locale}
          />
        </details>
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
          <h2>Session Workspace</h2>
        </div>
        <span className="state state-unavailable">UNAVAILABLE</span>
      </div>
      <p className="muted">
        Session is unavailable for the exact selected mission.
      </p>
      <details
        className="reason-details"
        onToggle={(event) => {
          if ((event.currentTarget as HTMLDetailsElement).open) setDiagnosticTick((n) => n + 1);
        }}
      >
        <summary>Technical details</summary>
        <code>{COMMAND_ROUTE_UNAVAILABLE}</code>
        <TransportDiagnosticFields
          snapshot={missionDiagnostics()}
          programsPhase={programsReadPhase}
            programsReason={programsReadReason}
          locale={locale}
        />
      </details>
    </section>
  );
  const sessionLive =
    !!sessionBinding && signedIn && !!sessionOwner && !!sessionTargetKey;
  // A qualified original READ is scoped to the current selected-session
  // owner, even if the old target is now unavailable for NEW sends.
  const presentedSessionAnswer = answerView.visible(
    sessionBinding && sessionOwner && signedIn ? {
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
        void sessionControl.refresh(selection);
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
  const programsRefreshControl = (
    <button
      type="button"
      // Pending reads stay focusable; unavailable acquisition stays natively disabled.
      disabled={!programsReadAvailable}
      aria-disabled={index.state === "PENDING" || !programsReadAvailable}
      onClick={() => {
        if (index.state === "PENDING" || !programsReadAvailable) return;
        setIndex({ programs: [], state: "PENDING", reason: "SOURCE_READ_PENDING" });
        setProgramRevision((revision) => revision + 1);
      }}
    >
      Refresh Projects
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
    undo: observedConversation.undoSource, edit: () => setActive("Conversations")};
  const projectDraftOwner = useRef({host: retainedResultHost, generation: archiveHostGeneration,
    context: observedConversation.projection.context, port: genuineProjectDraft});
  projectDraftOwner.current = {host: retainedResultHost, generation: archiveHostGeneration,
    context: observedConversation.projection.context, port: genuineProjectDraft};
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
      edit: () => { if (readWitness()) projectDraftOwner.current.port.edit?.(); }};
  }, []);
  const projectSourceDraftPort: ProjectSourceDraftPort = {text: genuineProjectDraft.text,
    revision: genuineProjectDraft.revision, insertion: genuineProjectDraft.insertion, ...projectDraftMethods};

  const [knowledgeMode, setKnowledgeMode] = useState<"project" | "retained">("project");
  const [projectSearchSelected, setProjectSearchSelected] = useState(true);
  const [requestedProjectFile, setRequestedProjectFile] = useState<KnowledgeLibraryProps["requestedFile"]>();
  const [savedConversationNavigation, setSavedConversationNavigation] = useState<SavedConversationNavigation | null>(null);
  const projectHistoryOwner = sessionBinding?.port.projectHistory;
  const hasProjectLibrary = Boolean(retainedResultHost?.readProjectKnowledgeCatalogue);
  const hasProjectSearch = Boolean(retainedResultHost?.projectFilesSearch || projectHistoryOwner);
  const catalogueWorkRef = catalogueProject?.authRevision === authRevision &&
    catalogueProject.epoch === programIndexEpoch ? catalogueProject.workRef : null;
  const requestedProjectWorkRef = catalogueProject ? catalogueWorkRef : selection?.workRef ?? null;
  const currentProjectCards = office.projection.programs.source.state === "CURRENT" &&
    index.state === "AVAILABLE" && requestedProjectWorkRef
      ? index.programs.filter(card => card.workRef === requestedProjectWorkRef) : [];
  const projectWorkRef = currentProjectCards.length === 1 ? currentProjectCards[0].workRef : null;
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
  const [knowledgeEditor,setKnowledgeEditor]=useState<{scope:string;mode:"file"|"preference";
    context:KnowledgeLibrarySourceContext;requestId:string;memory:ProjectMemoryDocument|null}|null>(null);
  const currentKnowledgeEditor=knowledgeEditor?.scope===knowledgePublication.scope?knowledgeEditor:null;
  hasUnsentUserText.current ||= !!currentKnowledgeEditor;
  useLayoutEffect(()=>{if(knowledgeEditor && !currentKnowledgeEditor)setKnowledgeEditor(null);},[knowledgeEditor,currentKnowledgeEditor]);
  const knowledgeWriteAvailable=!!(commandBinding?.store && knowledgePorts.readContext && knowledgePorts.transport &&
    projectWorkRef && projectReaders.canRead());
  const openKnowledgeEditor=(mode:"file"|"preference",context:KnowledgeLibrarySourceContext,memory:ProjectMemoryDocument|null)=>{
    if(!knowledgeWriteAvailable || context.workRef!==projectWorkRef ||
      ["submitting","checking","unknown"].includes(knowledgePublication.controller?.getState().status??"idle"))return;
    try {
      knowledgePublication.currentSource(context);
      if(!knowledgePublication.startDraft())return;
      const bytes=new Uint8Array(20);globalThis.crypto.getRandomValues(bytes);
      const suffix=Array.from(bytes,byte=>byte.toString(16).padStart(2,"0")).join("");
      setKnowledgeEditor({scope:knowledgePublication.scope,mode,context:{...context},memory,
        requestId:`mmos-project-${mode==="file"?"file-add":"preference-set"}-${suffix}`});
    } catch { /* No current source or original identifier means no editor action. */ }
  };
  const knowledgePublicationPanel=<>
    {currentKnowledgeEditor && (currentKnowledgeEditor.mode==="file"
      ? <ProjectKnowledgeEditor key={currentKnowledgeEditor.requestId} mode="file"
          sourceContext={currentKnowledgeEditor.context} requestId={currentKnowledgeEditor.requestId}
          authGeneration={authRevision} hostGeneration={archiveHostGeneration} locale={locale}
          current={knowledgePublication.currentSource} phase={knowledgePublication.phase}
          onSubmitFile={knowledgePublication.prepare} onClose={()=>setKnowledgeEditor(null)}
          onCheckOriginal={knowledgePublication.checkOriginal}/>
      : <ProjectKnowledgeEditor key={currentKnowledgeEditor.requestId} mode="preference"
          sourceContext={currentKnowledgeEditor.context} requestId={currentKnowledgeEditor.requestId}
          authGeneration={authRevision} hostGeneration={archiveHostGeneration} locale={locale}
          initialValue={currentKnowledgeEditor.memory?.value??""} expectedPreferenceRevision={currentKnowledgeEditor.memory?.revision??null}
          current={knowledgePublication.currentSource} phase={knowledgePublication.phase}
          onSubmitPreference={knowledgePublication.prepare} onClose={()=>setKnowledgeEditor(null)}
          onCheckOriginal={knowledgePublication.checkOriginal}/>)}
    {currentKnowledgeEditor && knowledgePublication.phase==="prepared" && knowledgePublication.prepared && <section className="card" aria-label={locale==="zh-CN"?"检查准备好的更改":"Review prepared changes"}>
      <h2>{locale==="zh-CN"?"检查你的更改":"Review your changes"}</h2>
      <p>{locale==="zh-CN"?"尚未发布。确认后才会提交这一次更改。":"Nothing has been published. Publish submits this original change once."}</p>
      <pre className="visible-text">{"file" in knowledgePublication.prepared.request
        ? `${knowledgePublication.prepared.request.file.display_name}\n${knowledgePublication.prepared.request.file.content_utf8}`
        : knowledgePublication.prepared.request.value}</pre>
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
        setActive("Conversations");
      }
    } : undefined,
  });
  const recordedDirection = <AcceptedDirectionPanel selection={projectWorkRef ? {work_ref:projectWorkRef} : null}
    read={projectReaders.direction} sourceGeneration={projectReaders.generation} canRead={projectReaders.canRead} locale={locale}
    onChangeDirection={directionConversation ? workRef => {
      if (workRef === projectWorkRef && projectReaders.canRead()) setActive("Conversations");
    } : undefined}/>;
  const projectSessionEvidence = <ProjectConversationAssociation selection={projectAssociationSelection}
    authGeneration={authRevision} hostGeneration={retainedResultHost?.invalidationGeneration?.() ?? null}
    readAssociation={projectReaders.association} locale={locale}/>;
  const recordedProjectJournal = projectWorkRef ? <ProjectJournalReader selection={{workRef: projectWorkRef}}
      read={projectReaders.journal} generation={projectReaders.generation?.() ?? "SOURCE_UNAVAILABLE"}
      authGeneration={authRevision} canRead={projectReaders.canRead} locale={locale}/> : null;
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
        <ResultCard state={{ kind: "READY", selection: selected, document }} />}
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
          <ResultCard state={{ kind: "READY", selection: selected, document }} />
        )}
      />
    ) : null;
  const quietHeader = active === "Inbox" || active === "Today" || active === "Knowledge" || active === "Search" || active === "Sources" || active === "Tools" ||
    active === "Projects" && !directRoute && (!projectTab ||
      Boolean(projectWorkRef && (projectTab === "Conversation" || catalogueWorkRef)));
  const projectReadGeneration = JSON.stringify([authRevision, retainedHostGeneration, selectionSeq.current]);
  const discoveryView = projectDiscovery({projection: office.projection,
    conversation: observedConversation.projection, controlRoom: currentControlRoom});

  const currentConversationPanel = (
      <>
        <ConversationWindow
          locale={locale}
          continuation={active === "Projects" ? undefined : sessionContinuationPanel}
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
          Refresh observed window
        </button>
        {active !== "Projects" && ((!signedIn && retainedComposerDrafts.session) || !sessionBinding)
          ? sessionPanel : null}
      </>
    );
  const changeProjectTab = (tab: ProjectTab) => {
    pendingLegacyTabFocus.current = tab;
    setProjectTab(tab);
  };
  let content: React.ReactNode;
  if (active === "Today")
    content = <Today locale={locale} projection={office.projection} work={workState}
      composer={commandPanel}
      authenticationCue={todayAuthenticationCue}
      retainComposerWithAuth={Boolean(passiveExpiryHold.current && retainedComposerDrafts.launch) || heldKind === "launch"}
      onOpenInbox={() => { setProjectTab(null); setActive("Inbox"); }}
      onOpenProjects={() => { setProjectTab(null); setActive("Projects"); }}
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
          draft={office.draft}
          onDraftChange={office.changeDraft}
          onInspectWorkerResult={workerResultHost?.readResult ? openOfficeWorkerResult : undefined}
          nativeContinuation={
            officeSession.sessionRef !== null &&
            officeSession.sessionRef === sessionTargetKey &&
            office.projection.mission.source.state === "CURRENT"
              ? sessionContinuationPanel
              : null
          }
          onStartNewWork={canLaunch && commandView ? startOfficeLaunch : undefined}
        />
        {/* The one existing launch owner, mounted where the Office mounts it.
            It is the same commandPanel element the other routes use, so only
            one LaunchOrchestrator owner exists at a time. */}
        {officeLaunchHandoff ? commandPanel : null}
        <OperationalNavigation label="Company operations" onNavigate={navigateOperationalView} />
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
  else if (active === "Conversations")
    content = currentConversationPanel;
  else if ((active === "Search" && (!hasProjectSearch || !projectSearchSelected)) || active === "Sources" || active === "Tools")
    content = <DiscoveryWorkspace view={discoveryView} projection={office.projection}
      mode={active} locale={locale} theme={theme}
      sourceProps={{readResultReferences: retainedResultHost?.readResultReferences,
        readResult: retainedResultHost?.readResult,
        hostGeneration: retainedResultHost?.invalidationGeneration?.(),
        draftPort: {projection: observedConversation.projection, text: observedConversation.draft,
          revision: observedConversation.draftRevision, insertion: observedConversation.draftInsertion,
          append: observedConversation.appendSource, undo: observedConversation.undoSource,
          edit: () => setActive("Conversations")}}}
      onModeChange={setActive}
      onOpenProject={office.projection.programs.source.state === "CURRENT" && index.state === "AVAILABLE"
        ? (target, mode) => {
            if (mode !== "current" || office.projection.programs.source.state !== "CURRENT" || index.state !== "AVAILABLE") return;
            const cards = index.programs.filter(card => card.workRef === target.workRef);
            if (cards.length !== 1 || cards[0].rootState !== "RESOLVED" ||
                cards[0].rootJobId !== target.rootJobId || cards[0].rootCandidates.length !== 1 ||
                cards[0].rootCandidates[0] !== target.rootJobId) return;
            open(target.workRef, target.rootJobId);
          } : undefined}
      onOpenConversation={() => setActive("Conversations")}
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
      onReturnToSearch={() => { setRequestedProjectFile(undefined); setActive("Search"); setProjectSearchSelected(true); }}/></>
  else if (active === "Knowledge")
    content = <Knowledge projection={office.projection} locale={locale}
      readResultReferences={retainedResultHost?.readResultReferences}
      readResult={retainedResultHost?.readResult}
      hostGeneration={retainedResultHost?.invalidationGeneration?.()}
      draftPort={{ projection: observedConversation.projection, text: observedConversation.draft,
        revision: observedConversation.draftRevision, insertion: observedConversation.draftInsertion,
        append: observedConversation.appendSource, undo: observedConversation.undoSource,
        edit: () => setActive("Conversations") }} />;
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
        {programsRefreshControl}
        {!directSelected && projectWorkRef && (catalogueWorkRef || projectTab === "Conversation") ? (
          <ProjectPlanPanel {...projectPlanProps} renderWorkspace={({objective, panel}) => <ProjectWorkspace headingLevel={1} headingRef={projectHeading} locale={locale}
            scopeKey={JSON.stringify([authRevision, projectWorkRef,
              projectConversationActive ? selection?.rootJobId : null, sessionTargetKey])}
            title={currentProjectCards[0].title || projectWorkRef} goal={objective}
            conversationPanel={projectConversationActive ? currentConversationPanel
              : <p role="status">{locale === "zh-CN" ? "此项目尚无已确认关联的对话。" : "No qualified conversation is associated with this project here."}</p>}
            composerPanel={projectConversationActive ? sessionContinuationPanel ?? sessionPanel
              : <p>{locale === "zh-CN" ? "尚未提供此项目的对话发送入口。" : "A conversation send route is not supplied for this project."}</p>}
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
            detailsPanel={<>
              {panel}{recordedDirection}{projectAdmissionPanel}
              {projectDetailsControls.instructions}{projectDetailsControls.access}
              <details className="reason-details"><summary>{locale === "zh-CN" ? "项目历史与来源证据" : "Project history and source evidence"}</summary>
                {projectSessionEvidence}{recordedProjectJournal}
              </details>
              {projectConversationActive ? <>
                <AutonomyPanel selection={selection} read={projectReaders.autonomy}
                  canRead={Boolean(projectReaders.generation) && projectReaders.canRead()}
                  sourceGeneration={projectReaders.generation?.() ?? "SOURCE_UNAVAILABLE"} locale={locale}/>
                <details className="reason-details"><summary>{locale === "zh-CN" ? "更多工作详情" : "More work details"}</summary>
                  <ProjectTabs active="Conversation" onChange={changeProjectTab}/>
                </details>
              </> : null}
            </>}/>}/>
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
          {!directSelected ? <ProjectTabs tablistRef={legacyProjectTabs} active={projectTab ?? "Overview"} onChange={changeProjectTab} /> : null}
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
              <ResultCard state={resultState} />
            </>
          ) : projectTab === "Plan" ? (
            <ProjectPlan d={d} />
          ) : projectTab === "Work" ? (
            <>
              <ProjectWorkDetail key={projectReadGeneration} document={d} selection={selection}
                generation={projectReadGeneration} locale={locale}
                resultPanel={<>{resultRefs}<ResultCard state={resultState}/></>}
                activityPanel={<Activity d={d}/>}
                actionPanel={<>{commandPanel}{workRefreshControl}</>}
                onOpenEvidence={() => setProjectTab("Evidence")}
                onOpenJournal={() => setProjectTab("Journal")} />
              <WorkQueue state={workState} rootJobId={selection.rootJobId} />
            </>
          ) : projectTab === "Evidence" ? (
            <><ProjectEvidence key={projectReadGeneration} document={d} selection={selection}
              generation={projectReadGeneration} locale={locale}
              resultPanel={<>{resultRefs}<ResultCard state={resultState}/></>}/>{productAcceptancePanel}</>
          ) : projectTab === "Journal" ? (
            <ProjectJournal key={projectReadGeneration} document={d} selection={selection}
              generation={projectReadGeneration} locale={locale} activityPanel={<Activity d={d}/>} />
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
          programs={office.projection.programs} read={projectReaders.archive} readPage={projectReaders.archivePage}
          sourceGeneration={projectReaders.generation} canRead={projectReaders.canRead}
          onOpenProject={workRef => {
            if (office.projection.programs.source.state !== "CURRENT" || index.state !== "AVAILABLE") return;
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
    content = <><SessionEstate key={"estate:" + authRevision} state={currentControlRoom} locale={locale}
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
    </SessionEstate>
    <SupervisionLedger read={currentControlRoom.state === "AVAILABLE"
      ? currentControlRoom.supervision ?? { state: "UNAVAILABLE", reason: "SOURCE_UNAVAILABLE" }
      : { state: "UNAVAILABLE", reason: "SOURCE_UNAVAILABLE" }} locale={locale} onOpenMission={open}/>
    <SupervisionTrace document={d} selection={selection} locale={locale}/>
    <ActivationReceipt state={currentControllerState} locale={locale} onReadOriginalStatus={checkCommandStatus}/>
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
      <ResourcesSystemsPanel controlRoom={currentControlRoom} work={workState} locale={locale}
        onReviewSources={() => setActive("Sources")}/>
      <ResourceCapacityRead host={retainedResultHost} locale={locale}
        selection={selectedCurrentCapacityAttempt(office.projection, selection,
          resultState.kind === "READY" ? resultState.selection : null, authRevision)}/>
      <AttendedFabricWorkspace
        key={`fleet:${authRevision}`}
        host={window.MastermindMissionHost}
        locale={locale}
      />
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
        <ResultCard state={resultState} />
      </>
    );
  else if (active === "Activity") content = <Activity d={d} />;
  else if (active === "Connections") content = <Connections d={d} />;
  else if (active === "Evidence") content = <><Evidence d={d} />{productAcceptancePanel}</>;
  else content = <Conversation locale={locale} />;
  const privateEntryState = authState && !authState.acquisition && !authState.content &&
    (authState.status === "signed_out" || authState.status === "signing_in" ||
      authState.status === "error" || authState.status === "unconfigured") ? authState.status : null;
  useEffect(() => {
    // Leaving the product shell must release its existing drawer focus owner.
    if (privateEntryState) setNavigationOpen(false);
  }, [privateEntryState]);
  if (privateEntryState) return <AuthEntry state={privateEntryState} locale={locale} theme={theme}
    illustrationSrc={privateEntryArt} authenticationControl={authenticationControl}
    preferencesControl={preferencesControl}
    feedback={authState?.reason && privateEntryState !== "signing_in" && privateEntryState !== "unconfigured" ? <p role="alert">{
      authState.reason === "POPUP_BLOCKED" ? copy.allowPopup :
      authState.reason === "POPUP_CLOSED" ? copy.popupClosed :
      authState.reason.includes("EXPIRED") || authState.reason.includes("TIMEOUT") ? copy.signInTimeout : copy.signInFailed
    }</p> : undefined}
    protectedWork={((passiveExpiryHold.current && (retainedComposerDrafts.launch || retainedComposerDrafts.session || office.draft.text || observedConversation.draft)) || showCheckStatus) ? <>
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
      {passiveExpiryHold.current && retainedComposerDrafts.launch ? commandPanel : null}
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
          <button type="button" className="sidebar-search" aria-current={active === "Search" ? "page" : undefined}
            onClick={() => {setProjectTab(null);setActive("Search");if (navigationOpen) closeNavigation();}}>
            <NavigationIcon view="Search"/>{locale === "zh-CN" ? "搜索" : "Search"}
          </button>
          <div className="nav-section">
            <span className="nav-section-label">{locale === "zh-CN" ? "公司" : "COMPANY"}</span>
            <nav aria-label={locale === "zh-CN" ? "公司导航" : "Company navigation"}>
              {primaryNavigation.map((x) => (
                <button
                  key={x}
                  className={active === x ? "active" : ""}
                  aria-label={navigationLabel(x, locale)}
                  aria-current={active === x ? "page" : undefined}
                  onClick={() => {
                    setProjectTab(null);
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
                    className={active === x ? "active" : ""}
                    aria-label={advancedLabel(x, locale)}
                    aria-current={active === x ? "page" : undefined}
                    onClick={() => {
                      setProjectTab(null);
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
              <small>{copy.authStatus[authState.status]}</small>
              {authState.reason && authState.status !== "unconfigured" ? (
                <p className="muted">
                  {authState.reason === "POPUP_BLOCKED"
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
            </div>
          ) : null}
        </div>
      </aside>
      <main id="content" tabIndex={-1}>
        <header className={quietHeader ? "workspace-header workspace-header-quiet" : "workspace-header"}>
          <div className="workspace-route">
            <button ref={navigationToggle} type="button" className="navigation-toggle" aria-expanded={navigationOpen} aria-controls="workspace-navigation" aria-label={locale === "zh-CN" ? "打开导航" : "Open navigation"} onClick={() => setNavigationOpen(value => !value)}><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><path d="M4 6h16M4 12h16M4 18h16" /></svg></button>
            <span className="eyebrow">{directRoute ? (locale === "zh-CN" ? "单个只读任务" : "One read-only task") : navigationLabel(active, locale)}</span>
            {quietHeader ? <h2 ref={routeHeading} tabIndex={-1}>{navigationLabel(active, locale)}</h2> : <h1 ref={routeHeading} tabIndex={-1}>
              {directRoute ? (locale === "zh-CN" ? "原生任务" : "Native task") : navigationLabel(active, locale)}
            </h1>}
            {!quietHeader && <p>{directRoute ? (locale === "zh-CN" ? "读取当前任务结果，再单独确认接收。" : "Read this task’s result, then acknowledge it separately.") : headerSummary}</p>}
          </div>
          <div className="facts">
            {!directRoute ? quietHeader ? <details className="workspace-qualification"><summary>{active === "Inbox" ? (locale === "zh-CN" ? "工作区来源" : "Workspace source") : (locale === "zh-CN" ? "来源状态" : "Source status")} <State value={headerState} /></summary><p>{headerSummary}</p><p role="status">{visibleNotice}</p><p><b>{copy.statusSources}</b><br />{copy.statusNote}</p></details> : <State value={headerState} /> : null}
          </div>
        </header>
        {!native && authState && authState.status === "signed_out" &&
         passiveExpiryHold.current && hasUnsentUserText.current ? (
          <section className="notice" aria-label={copy.unsentProtected}>
            <p>{copy.expiredUnsent}</p>
            <button type="button" onClick={() => {
              office.changeDraft("");
              observedConversation.discardDraft();
              updateRetainedComposer("launch", "");
              updateRetainedComposer("session", "");
              passiveExpiryHold.current = false;
            }}>{copy.discardAll}</button>
          </section>
        ) : null}
        {active !== "Control Room" && active !== "Today" && !directRoute &&
          !(active === "Inbox" && visibleNotice === "Choose a Program with one resolved mission before opening the workspace.") ? (
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
        {hasProjectSearch && <section hidden={active !== "Search" || !projectSearchSelected || Boolean(savedConversationNavigation)} aria-hidden={active !== "Search" || !projectSearchSelected || Boolean(savedConversationNavigation)}>
          <ProjectSearchWorkspace workRef={projectWorkRef} authGeneration={authRevision}
            hostGeneration={archiveHostGeneration} locale={locale} theme={theme}
            sessionHistory={projectHistoryOwner} projectFiles={retainedResultHost?.projectFilesSearch}
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
        {d && missionNavigation.includes(active) && !conversationActive && (
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
