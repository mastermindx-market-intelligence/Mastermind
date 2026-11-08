import { decodeCompanyPriorities, type CompanyPrioritiesOwner } from "./meta-ceo/company-priorities";
import { decodeNativeExecutiveObservation, type NativeExecutiveObservation } from "./native-executive-observation";
import {hostObservationHostMethods,hostObservationPublicSelection,type HostObservationRawMethods,type HostObservationHostMethods} from "./resources/host-observation-host";
import {freshConversationArguments, freshConversationNeedsWorkspace, type FreshConversationTransport} from "./orchestration/fresh-conversation-transport";
import { decodeByokRolesRead, type ByokRolesRead } from "./meta-ceo/byok-roles-read";
import { createLazyTerminalSharingHost, type TerminalSharingSource } from "./terminal/terminal-sharing-host";
import { createNativeDraftRecoveryOwner, type NativeDraftRecoveryOwner } from "./auth-recovery/native-draft-owner";
import {projectAccessHostMethods,projectAccessPublicSelection,type ProjectAccessRawMethods,type ProjectAccessHostMethods} from "./access/project-access-host";
import { projectAdmissionHostMethods, projectAdmissionPublicRequest, type ProjectAdmissionRawMethods, type ProjectAdmissionHostMethods } from "./admission/project-admission-host";
import { validArchiveCursor, type ArchiveCursor } from "./projects/archive/project-archive-continuation";
import { decodeProjectArchive, type ProjectArchiveRead } from "./projects/archive/project-archive";
import type { ProjectFileSearchOwner, FileSearchCatalogue, FileSearchSource } from "./discovery/project-file-search";
import { knowledgeReadSelection, validateKnowledgeRead, type KnowledgeReadSelection, type KnowledgeSourceSelection, type KnowledgeReadKind } from "./knowledge/library/knowledge-read-port";
import { decodeSourceOperationContext, validSourceOperationContextSelection, type SourceOperationContext, type SourceOperationContextSelection } from './source-operations/context';
import {createSourceOperationTransport,type SourceOperationTransport} from './source-operations/transport';
import {decodeSourceOperationStatus} from './planning/plan-adoption-status';
import {instructionHostMethods,instructionPublicRequest,type InstructionRawMethods,type InstructionHostMethods} from "./instructions/instruction-host";
import { decodeProjectAssociation, normalizeProjectAssociationSelection, type ProjectAssociationSelection, type ProjectAssociationDocument } from "./conversations/project-association";
import { decodeResourceCapacityRead, validResourceCapacitySelection, type ResourceCapacityReadSelection, type ResourceCapacityRead } from "./resources/resource-capacity-read";
import { decodeModelConfiguration, type ModelConfigurationRead } from "./resources/model-configuration";
import { decodeAutonomyPolicy, isAutonomySelection, type AutonomyRead, type AutonomySelection } from "./supervision/autonomy-policy";
import { decodeProjectJournal, validJournalSelection, type JournalSelection, type ProjectJournalDocument } from "./project-journal";
import { decodeAcceptedDirection, validDirectionSelection, type DirectionSelection, type AcceptedDirectionRead } from "./direction/accepted-direction";
import { decodeProjectPlan, validProjectPlanSelection, type ProjectPlanRead, type ProjectPlanSelection } from "./planning/project-plan";
import { decodeOriginalAcceptanceBody, guardAcceptanceRead, missionV4Selection, type MissionV4Selection, type ProductAcceptanceOwner } from "./product-acceptance/owner-observation";
import { decodeBrowserScopedFabricCatalog, type FabricCatalog } from "./fabric/catalog-contract";
import { attendedSelection, decodeAttendedStatus, type AttendedSelection, type AttendedStatus } from "./fabric/attended-status";
import { decodeAdmittedPlan, validPlanSelection, type PlanRead, type PlanSelection } from "./planning/admitted-plan";
import { decodeRetainedActivity, validActivitySelection, type ActivitySelection, type ActivityRead } from "./planning/retained-activity";
import { createNativeExecutiveTransport } from "./native-executive-transport";
import type { MissionDiagnosticSnapshot } from "./diagnostic-state";
import { createTerminalBriefsNavigationPort, type TerminalBriefsNavigationPort } from "./terminal/terminal-navigation";
import type { ProjectConversationHistoryTransport, ProjectConversationHistoryReaderFactory } from "./conversations/project-conversation-history-owner";
import type { ProjectConversationCatalogueReaderFactory } from './conversations/project-conversation-catalogue-factory';
import type { ProjectPlanningTransport } from "./planning/project-planning-transport";
import type { OsExecutiveTransport } from "./orchestration/os-executive-host";
import {
  decodeMission,
  decodeMissionv3,
  decodeMissionv4,
  normalizeSelection,
  normalizeWorkspaceSelection,
  type MissionDocument,
  type MissionSelection,
  type Missionv3Document,
  type ProgramRead,
} from "./mission";
import {
  decodeProgramsEnvelope,
  decodeWindow,
  type WindowDocument,
} from "./workspace-contract";
import {
  decodeResultEnvelope,
  normalizeResultSelection,
  type ResultEnvelopeDigestShape,
  type ResultSelection,
} from "./result";
import { decodeMissionResult, type MissionResultDocument } from "./mission-result";
import { decodeResultReferencesEnvelope, type ResultReferencesDocument } from "./result-references";
import { decodeWorkDocument, type WorkDocument } from "./work";
import { decodeProgramsObservation, type ProgramsObservation } from "./programs-observation";
import { decodeControlRoomDiscovery, type ControlRoomDiscovery } from "./control-room-navigation";
import {
  completeOrchestratorCommandBinding,
  type OrchestratorCommandBinding,
} from "./orchestration/host-command-bindings";

export type { OrchestratorCommandBinding };

export interface AuthState {
  status: "unconfigured" | "signed_out" | "signing_in" | "signed_in" | "error";
  reason: string | null;
  acquisition: boolean;
  content: boolean;
}
import type { ResearchEvidenceTransport } from "./research/evidence-contract";
import {
  decodeControlRoomRead, type ControlRoomRead,
  decodeControlRoomActionPayload, decodeControlRoomActionResult,
  ControlRoomActionTransportError,
  type ControlRoomOperation, type ControlRoomActionResult,
} from "./control-room";

export interface RawClient extends Partial<HostObservationRawMethods>,Partial<ProjectAdmissionRawMethods>,Partial<InstructionRawMethods>,Partial<ProjectAccessRawMethods> {
  /** Explicit fixed local metadata read; never refreshes an authorization owner. */
  readNativeExecutiveDiagnostics?(request: { signal: AbortSignal }): Promise<unknown>;
  /** Native-owned privacy metadata only; never reconstructed from an event. */
  readonly nativeDraftRecovery?: NativeDraftRecoveryOwner;
  /** Independent Terminal session; workspace grants never confer brief access. */
  readonly terminalSharing?: TerminalSharingSource;
  /** Public fixed navigation only; Terminal owns its user's authentication and access. */
  openTerminalBriefs?(): Promise<unknown>;
  readonly sourceOperations?:SourceOperationTransport;
  /** Existing authenticated original-owner acquisition; no caller-supplied request key. */
  readOriginalMissionV4?(request: MissionSelection & { signal: AbortSignal }): Promise<unknown>;
  /** Optional private owner publication; never reconstructed from browser input. */
  readonly productAcceptanceOwner?: ProductAcceptanceOwner;
  readMissionV4?(request: MissionV4Selection & { signal: AbortSignal }): Promise<unknown>;
  /** Optional fixed Research capability; private Auth0 token stays with its owner. */
  readonly research?: ResearchEvidenceTransport;
  readonly executive?: OsExecutiveTransport;
  /** Optional fixed selected-session continuation transport; same private bearer custody. */
  readonly executiveSession?: ProjectConversationHistoryTransport;
  getState(): AuthState;
  /** Existing source epoch, when exposed by the fixed client; never a principal or grant. */
  invalidationGeneration?(): number;
  subscribe(listener: (state: AuthState) => void): () => void;
  signIn(): Promise<unknown>;
  signOut(): Promise<unknown>;
  restore?(): Promise<unknown>;
  /** Optional owner-authorized status-only Fabric port. No default browser/machine credential bridge. */
  readAutonomyPolicy?(request: AutonomySelection & { signal: AbortSignal }): Promise<unknown>;
  readSourceOperationContext?(request: SourceOperationContextSelection & { signal: AbortSignal }): Promise<unknown>;
  readProjectPlan?(request: ProjectPlanSelection & { signal: AbortSignal }): Promise<unknown>;
  readProjectSessionAssociation?(request: ProjectAssociationSelection & { signal: AbortSignal }): Promise<unknown>;
  readProjectJournal?(request: JournalSelection & { signal: AbortSignal }): Promise<unknown>;
  readProjectArchivePage?(request: ArchiveCursor & { signal: AbortSignal }): Promise<unknown>;
  readProjectArchive?(request: { signal: AbortSignal }): Promise<unknown>;
  readProjectDirection?(request: DirectionSelection & { signal: AbortSignal }): Promise<unknown>;
  readProjectKnowledgeCatalogue?(request: KnowledgeReadSelection & { signal: AbortSignal }): Promise<unknown>;
  readProjectKnowledgeMemory?(request: KnowledgeReadSelection & { signal: AbortSignal }): Promise<unknown>;
  readProjectKnowledgeSource?(request: KnowledgeSourceSelection & { signal: AbortSignal }): Promise<unknown>;
  readAdmittedPlan?(request: PlanSelection & { signal: AbortSignal }): Promise<unknown>;
  readResourceCapacity?(request: ResourceCapacityReadSelection & { signal: AbortSignal }): Promise<unknown>;
  readModelConfiguration?(request: { signal: AbortSignal }): Promise<unknown>;
  readRetainedActivity?(request: ActivitySelection & { signal: AbortSignal }): Promise<unknown>;
  readAttendedFabric?(request: AttendedSelection & { signal: AbortSignal }): Promise<unknown>;
  /** Optional authorized recent-run metadata; no source endpoint is implied by this interface. */
  readAttendedFabricCatalog?(request: { signal: AbortSignal }): Promise<unknown>;
  readPrograms(request: { signal: AbortSignal }): Promise<unknown>;
  /** Fixed authenticated one-cache Control Room state; no operator writes. */
  readControlRoomState?(request: { signal: AbortSignal }): Promise<unknown>;
  /** Fixed secret-free role-pair metadata; no enrollment or provider operation. */
  readByokRoles?(request: { signal: AbortSignal }): Promise<unknown>;
  /** Independent read with a separately sealed Discovery grant; never an action grant. */
  readControlRoomDiscovery?(request: { signal: AbortSignal }): Promise<unknown>;
  /** Each original mutation has one fixed, optional host method and one owner. */
  openControlRoomSurface?(request: { payload: Readonly<Record<string, unknown>>; signal: AbortSignal }): Promise<unknown>;
  bindControlRoomSurface?(request: { payload: Readonly<Record<string, unknown>>; signal: AbortSignal }): Promise<unknown>;
  unbindControlRoomSurface?(request: { payload: Readonly<Record<string, unknown>>; signal: AbortSignal }): Promise<unknown>;
  refreshControlRoomBuilds?(request: { signal: AbortSignal }): Promise<unknown>;
  readWork(request: { signal: AbortSignal }): Promise<unknown>;
  readMission(request: {
    work_ref: string;
    root_job_id: string;
    signal: AbortSignal;
  }): Promise<unknown>;
  readMissionV3?(request: {
    workRef: string;
    rootJobId: string;
    signal: AbortSignal;
  }): Promise<unknown>;
  readResult?(request: {
    workRef: string;
    rootJobId: string;
    jobId: string;
    attemptId: string;
    resultEnvelopeDigest: string;
    signal: AbortSignal;
  }): Promise<unknown>;
  /**
   * Optional compound acquisition through the web or fixed native read owner.
   * Signal stays outside the five-field selector.
   */
  readMissionResult?(request: ResultSelection & { signal: AbortSignal }): Promise<unknown>;
  readResultReferences?(request: {
    workRef: string;
    rootJobId: string;
    signal: AbortSignal;
  }): Promise<unknown>;
  readCurrentWindow(request: { signal: AbortSignal }): Promise<unknown>;
}
/**
 * One internally consistent typed read API: every fixed read returns its
 * fully decoded frozen DTO, or throws. Work and Result each preserve their
 * schema-specific typed allowed 503 document with availability "UNAVAILABLE";
 * neither becomes a generic error wrapper or empty success. The exact Result
 * five-selector tuple stays separate from AbortSignal, which is an option,
 * never part of the selector.
 */
export interface MissionResultRead {
  (request: ResultSelection & { signal: AbortSignal }): Promise<unknown>;
}
export interface MissionHost extends Partial<HostObservationHostMethods>,Partial<ProjectAdmissionHostMethods>,Partial<InstructionHostMethods>,Partial<ProjectAccessHostMethods> {
  readNativeExecutiveDiagnostics?(request: { signal: AbortSignal }): Promise<NativeExecutiveObservation>;
  readonly nativeDraftRecovery?: NativeDraftRecoveryOwner;
  /** Independent Terminal session; workspace grants never confer brief access. */
  readonly terminalSharing?: TerminalSharingSource;
  readonly projectPlanning?: ProjectPlanningTransport;
  readonly freshConversation?: FreshConversationTransport;
  /** Optional zero-input navigation; no private content or access receipt. */
  openTerminalBriefs?: TerminalBriefsNavigationPort;
  readonly sourceOperations?:SourceOperationTransport;
  /** Existing authenticated original-owner acquisition; no caller-supplied request key. */
  readOriginalMissionV4?(request: MissionSelection & { signal: AbortSignal }): Promise<unknown>;
  readonly productAcceptanceOwner?: ProductAcceptanceOwner;
  readMissionV4?(request: MissionV4Selection & { signal: AbortSignal }): Promise<unknown>;
  readMission?: (
    request: MissionSelection & { signal: AbortSignal },
  ) => Promise<unknown>;
  readMissionV3?: (
    request: MissionSelection & { signal: AbortSignal },
  ) => Promise<unknown>;
  readAutonomyPolicy?: (request: AutonomySelection & { signal: AbortSignal }) => Promise<AutonomyRead>;
  readSourceOperationContext?: (request: SourceOperationContextSelection & { signal: AbortSignal }) => Promise<SourceOperationContext>;
  readProjectPlan?: (request: ProjectPlanSelection & { signal: AbortSignal }) => Promise<ProjectPlanRead>;
  readProjectSessionAssociation?: (request: ProjectAssociationSelection & { signal: AbortSignal }) => Promise<ProjectAssociationDocument>;
  readProjectJournal?: (request: JournalSelection & { signal: AbortSignal }) => Promise<ProjectJournalDocument>;
  readProjectArchivePage?: (request: ArchiveCursor & { signal: AbortSignal }) => Promise<ProjectArchiveRead>;
  readProjectArchive?: (request: { signal: AbortSignal }) => Promise<ProjectArchiveRead>;
  readProjectDirection?: (request: DirectionSelection & { signal: AbortSignal }) => Promise<AcceptedDirectionRead>;
  readonly projectFilesSearch?: ProjectFileSearchOwner;
  readProjectKnowledgeCatalogue?: (request: KnowledgeReadSelection & { signal: AbortSignal }) => Promise<unknown>;
  readProjectKnowledgeMemory?: (request: KnowledgeReadSelection & { signal: AbortSignal }) => Promise<unknown>;
  readProjectKnowledgeSource?: (request: KnowledgeSourceSelection & { signal: AbortSignal }) => Promise<unknown>;
  readAdmittedPlan?: (request: PlanSelection & { signal: AbortSignal }) => Promise<PlanRead>;
  readResourceCapacity?: (request: ResourceCapacityReadSelection & { signal: AbortSignal }) => Promise<ResourceCapacityRead>;
  readModelConfiguration?: (request: { signal: AbortSignal }) => Promise<ModelConfigurationRead>;
  readRetainedActivity?: (request: ActivitySelection & { signal: AbortSignal }) => Promise<ActivityRead>;
  readAttendedFabric?: (request: AttendedSelection & { signal: AbortSignal }) => Promise<AttendedStatus>;
  readAttendedFabricCatalog?: (request: { signal: AbortSignal }) => Promise<FabricCatalog>;
  readPrograms?: ProgramRead;
  readControlRoomState?: (request: { signal: AbortSignal }) => Promise<ControlRoomRead>;
  readByokRoles?: (request: { signal: AbortSignal }) => Promise<ByokRolesRead>;
  readControlRoomDiscovery?: (request: { signal: AbortSignal }) => Promise<ControlRoomDiscovery>;
  openControlRoomSurface?: (request: { payload: Record<string, unknown>; signal: AbortSignal }) => Promise<ControlRoomActionResult>;
  bindControlRoomSurface?: (request: { payload: Record<string, unknown>; signal: AbortSignal }) => Promise<ControlRoomActionResult>;
  unbindControlRoomSurface?: (request: { payload: Record<string, unknown>; signal: AbortSignal }) => Promise<ControlRoomActionResult>;
  refreshControlRoomBuilds?: (request: { signal: AbortSignal }) => Promise<ControlRoomActionResult>;
  /** Same fixed Programs acquisition, retaining its collection owner receipt. */
  readProgramsObservation?: (request: { signal: AbortSignal }) => Promise<ProgramsObservation>;
  readWork?: (request: { signal: AbortSignal }) => Promise<WorkDocument>;
  readonly companyPriorities?: CompanyPrioritiesOwner;
  readResult?: MissionResultRead;
  /** Mounted only when the raw method and the client invalidation generation both exist. */
  readMissionResult?(request: ResultSelection & { signal: AbortSignal }): Promise<MissionResultDocument>;
  /** Typed retained-result reference index read; same two-field selection grammar. */
  readResultReferences?: (
    request: { workRef: string; rootJobId: string; signal: AbortSignal },
  ) => Promise<ResultReferencesDocument>;
  readCurrentWindow?: (request: {
    signal: AbortSignal;
  }) => Promise<WindowDocument>;
  invalidationGeneration?: () => number;
  selection?: unknown;
  auth?: Pick<RawClient, "getState" | "subscribe" | "signIn" | "signOut">;
  commandBinding?: OrchestratorCommandBinding;
  /** Observer-only composition diagnostics; a zero-effect snapshot, never a grant. */
  diagnostics?: () => MissionDiagnosticSnapshot;
  /** Separately mounted session binding; never the launch route. */
  sessionCommandBinding?: unknown;
  /** Pushes the exact selection on every transition and registers the explicit condition provider. */
  session?: {
    createProjectCatalogueReader?: ProjectConversationCatalogueReaderFactory;
    createProjectHistoryReader?: ProjectConversationHistoryReaderFactory;
    refresh(selection: unknown): Promise<void>;
    setStopCondition(provider: () => unknown): void;
  };
}
export interface SessionHostAttachment {
  readonly createProjectCatalogueReader?: ProjectConversationCatalogueReaderFactory;
  readonly binding: unknown;
  readonly createProjectHistoryReader?: ProjectConversationHistoryReaderFactory;
  refresh(selection: unknown): Promise<void>;
  setStopCondition(provider: () => unknown): void;
}

export function bindMissionHost(
  client: RawClient,
  commandBinding?: unknown,
  session?: SessionHostAttachment,
): MissionHost {
  let epoch = 0;
  let previous = JSON.stringify(client.getState());
  let previousClientGeneration = client.invalidationGeneration?.();
  client.subscribe((state) => {
    const next = JSON.stringify(state);
    const generation = client.invalidationGeneration?.();
    // Native identity boundaries may retain the same public display state.
    // Legacy/web clients without an epoch still deduplicate identical updates.
    if (next !== previous || generation !== previousClientGeneration) {
      epoch++;
      previous = next;
      previousClientGeneration = generation;
    }
  });
  const sourceContextReader = client.readSourceOperationContext;
  const sourceGroup = client.sourceOperations;
  const sourceEpochReader = client.invalidationGeneration;
  const sourceMethods = sourceGroup
    ? {
        options: sourceGroup.readProjectCreationOptions,
        prepare: sourceGroup.prepareSourceOperation,
        read: sourceGroup.readSourceOperation,
        submit: sourceGroup.submitSourceOperation,
        reconcile: sourceGroup.reconcileSourceOperation,
        advance: sourceGroup.advanceSourceOperation,
      }
    : null;
  const boundSource =
    sourceGroup &&
    sourceMethods &&
    sourceEpochReader &&
    Object.entries(sourceMethods).every(([key,fn]) => key === "options" || typeof fn === "function")
      ? createSourceOperationTransport(async (method, _path, body, signal) => {
          const started = epoch,
            source = sourceEpochReader.call(client);
          const name = (
            {
              options: "readProjectCreationOptions",
              prepare: "prepareSourceOperation",
              read: "readSourceOperation",
              submit: "submitSourceOperation",
              reconcile: "reconcileSourceOperation",
              advance: "advanceSourceOperation",
            } as const
          )[method];
          const authorized = () => {
            const state = client.getState();
            return (
              !signal.aborted &&
              started === epoch &&
              client.invalidationGeneration === sourceEpochReader &&
              sourceEpochReader.call(client) === source &&
              client.sourceOperations === sourceGroup &&
              sourceGroup[name] === sourceMethods[method] &&
              state.status === "signed_in" &&
              state.acquisition
            );
          };
          if (!authorized()) throw new Error("SOURCE_OPERATION_UNAUTHORIZED");
          const call = sourceMethods[method] as (
            input: unknown,
            signal: AbortSignal,
          ) => Promise<unknown>;
          const result = method === "options" ? await sourceGroup.readProjectCreationOptions!(signal) : await call.call(sourceGroup, body, signal);
          if (!authorized()) throw new Error("READ_CANCELLED");
          if (method === "prepare" || method === "options") return result;
          const decoded = decodeSourceOperationStatus(result);
          if (
            decoded.selection.action !== body.action ||
            decoded.selection.request_id !== body.request_id ||
            (decoded.selection.work_ref !== body.work_ref && !(method === "read" &&
              body.action === "publish_project_proposal" && body.work_ref === null))
          )
            throw new Error("SOURCE_OPERATION_RESPONSE_INVALID");
          return decoded;
        })
      : undefined;
  const check = (signal: AbortSignal, started: number) => {
    if (signal.aborted || started !== epoch) throw new Error("READ_CANCELLED");
  };
  // Capture the actual fixed owner method once. Any replacement before invocation
  // refuses pre-dispatch; a lost result AFTER invoking it is EFFECT_UNKNOWN.
  // Caller cancellation or auth changes after the call cannot erase the owner's return.
  function bindAction(
    operation: ControlRoomOperation,
    method: "openControlRoomSurface" | "bindControlRoomSurface"
      | "unbindControlRoomSurface" | "refreshControlRoomBuilds",
  ) {
    const raw = client[method];
    if (typeof raw !== "function") return null;
    const withPayload = operation !== "refresh-builds";
    return async (request: { payload?: Record<string, unknown>; signal: AbortSignal }): Promise<ControlRoomActionResult> => {
      const admitted = (() => {
        try {
          // Capture authority before request decoding or any state callback can
          // reenter authentication. The final epoch check follows every callback.
          const started = epoch;
          const getState = client.getState;
          const getGeneration = client.invalidationGeneration;
          const source = getGeneration?.call(client);
          const signal = request.signal;
          if (!signal || signal.aborted) throw new Error("PRE_DISPATCH_CANCELLED");
          const payload = decodeControlRoomActionPayload(
            withPayload ? request.payload : {}, operation,
          );
          const state = getState.call(client);
          const authorized = state.status === "signed_in" && state.acquisition;
          const currentSource = getGeneration?.call(client);
          if (!authorized || source !== currentSource
              || client.getState !== getState
              || client.invalidationGeneration !== getGeneration
              || client[method] !== raw || signal.aborted || started !== epoch)
            throw new Error("ACTION_NOT_ADMITTED");
          return { payload, signal };
        } catch {
          throw new ControlRoomActionTransportError(operation, "NOT_DISPATCHED");
        }
      })();
      let result: unknown;
      try {
        result = withPayload
          ? await (raw as NonNullable<RawClient["openControlRoomSurface"]>)
            .call(client, admitted)
          : await (raw as NonNullable<RawClient["refreshControlRoomBuilds"]>)
            .call(client, { signal: admitted.signal });
      } catch (error) {
        // Only this exact delegated owner may establish that its own fetch did
        // not start. No other operation or error phase supplies that evidence.
        let disposition: "NOT_DISPATCHED" | "EFFECT_UNKNOWN" = "EFFECT_UNKNOWN";
        try {
          if (error instanceof ControlRoomActionTransportError
              && error.operation === operation
              && (error.disposition === "NOT_DISPATCHED"
                || error.disposition === "EFFECT_UNKNOWN"))
            disposition = error.disposition;
        } catch { /* An uninspectable dependency error remains uncertain. */ }
        throw new ControlRoomActionTransportError(operation, disposition);
      }
      try {
        const httpStatus = result && typeof result === "object" && !Array.isArray(result)
          ? (result as { status?: number }).status : NaN;
        return decodeControlRoomActionResult(result, operation, httpStatus as number);
      } catch {
        throw new ControlRoomActionTransportError(operation, "EFFECT_UNKNOWN");
      }
    };
  }
  function knowledgeRead(kind: KnowledgeReadKind, raw: ((request: any) => Promise<unknown>) | undefined) {
    if(!raw || !client.invalidationGeneration) return undefined;
    return async (request: (KnowledgeReadSelection|KnowledgeSourceSelection)&{signal:AbortSignal}) => {
      const {signal,...value}=request;
      const selected=knowledgeReadSelection(value,kind);
      if(!selected) throw new Error("PROJECT_KNOWLEDGE_SELECTION_INVALID");
      const started=epoch, generation=client.invalidationGeneration!();
      const method=kind==="catalogue"?"readProjectKnowledgeCatalogue":kind==="memory"?"readProjectKnowledgeMemory":"readProjectKnowledgeSource";
      const current=()=>{const state=client.getState();return !signal.aborted && epoch===started
        && client[method]===raw && client.invalidationGeneration?.()===generation && state.status==="signed_in" && state.acquisition;};
      if(!current()) throw new Error("PROJECT_KNOWLEDGE_READ_UNAUTHORIZED");
      const result=await raw.call(client,{...selected,signal});
      if(!current()) throw new Error("READ_CANCELLED");
      const body=await validateKnowledgeRead(result,selected,kind);
      if(!current()) throw new Error("READ_CANCELLED");
      return body;
    };
  }
  const catalogueRead=knowledgeRead("catalogue",client.readProjectKnowledgeCatalogue);
  const memoryRead=knowledgeRead("memory",client.readProjectKnowledgeMemory);
  const sourceRead=knowledgeRead("source",client.readProjectKnowledgeSource);
  const projectFilesSearch: ProjectFileSearchOwner|undefined = catalogueRead && sourceRead ? Object.freeze({
    context:()=>{
      const state=client.getState(),generation=client.invalidationGeneration?.();
      return state.status==="signed_in" && state.acquisition && Number.isSafeInteger(generation) && generation!>=0
        ? Object.freeze({generation:JSON.stringify([epoch,generation])}) : null;
    },
    authGeneration:()=>epoch,
    readCatalogue:({workRef,signal}:{workRef:string;signal:AbortSignal})=>catalogueRead({work_ref:workRef,signal}) as Promise<FileSearchCatalogue>,
    readSource:({workRef,sourceRef,expectedRevision,signal}:{workRef:string;sourceRef:string;expectedRevision:string;signal:AbortSignal})=>
      sourceRead({work_ref:workRef,source_ref:sourceRef,expected_revision:expectedRevision,signal}) as Promise<FileSearchSource>,
  }):undefined;
  const command = completeOrchestratorCommandBinding(commandBinding);
  const companyTransport=client.executive, companyRead=companyTransport?.companyPriorities;
  const companyGeneration=companyTransport?.authGeneration, companyAvailable=companyTransport?.available;
  const companySubscribe=companyTransport?.subscribe;
  const companyCurrent=()=>!!companyTransport && client.executive===companyTransport &&
    companyTransport.companyPriorities===companyRead && companyTransport.authGeneration===companyGeneration &&
    companyTransport.available===companyAvailable && companyTransport.subscribe===companySubscribe;
  return {
    ...(companyTransport && companyRead && companyGeneration && companyAvailable && companySubscribe ? {companyPriorities: {
      generation: () => companyCurrent() ? companyGeneration.call(companyTransport) : -1,
      available: () => companyCurrent() && companyAvailable.call(companyTransport),
      subscribe: (listener:()=>void) => companySubscribe.call(companyTransport,listener),
      read: async (signal:AbortSignal) => {
        const generation=companyGeneration.call(companyTransport), started=epoch;
        const current=()=>!signal.aborted && epoch===started && companyCurrent() && companyGeneration.call(companyTransport)===generation && companyAvailable.call(companyTransport);
        if(!current())throw new Error("COMPANY_READ_UNAVAILABLE");
        const raw=await companyRead.call(companyTransport,signal);
        if(!current())throw new Error("READ_CANCELLED");
        const value=decodeCompanyPriorities(raw);
        if(!current())throw new Error("READ_CANCELLED");
        return value;
      },
    }} : {}),
    ...(client.nativeDraftRecovery ? { nativeDraftRecovery: client.nativeDraftRecovery } : {}),
    ...(client.terminalSharing ? { terminalSharing: client.terminalSharing } : {}),
    ...(client.openTerminalBriefs ? {
      openTerminalBriefs: createTerminalBriefsNavigationPort(() => client.openTerminalBriefs!()),
    } : {}),
    ...(client.readNativeExecutiveDiagnostics && client.invalidationGeneration ? {
      async readNativeExecutiveDiagnostics({ signal }: { signal: AbortSignal }) {
        const reader = client.readNativeExecutiveDiagnostics!, started = epoch;
        const source = client.invalidationGeneration!();
        const current = () => !signal.aborted && started === epoch &&
          Number.isSafeInteger(source) && source >= 0 && source === client.invalidationGeneration?.() &&
          reader === client.readNativeExecutiveDiagnostics;
        if (!current()) throw new Error("READ_CANCELLED");
        const raw = await reader.call(client, { signal });
        if (!current()) throw new Error("READ_CANCELLED");
        const value = decodeNativeExecutiveObservation(raw);
        if (!value) throw new Error("RESPONSE_INVALID");
        return value;
      },
    } : {}),
    invalidationGeneration: () => epoch,
    ...(catalogueRead ? {readProjectKnowledgeCatalogue: catalogueRead} : {}),
    ...(projectFilesSearch ? {projectFilesSearch} : {}),
    ...(memoryRead ? {readProjectKnowledgeMemory: memoryRead} : {}),
    ...(sourceRead ? {readProjectKnowledgeSource: sourceRead} : {}),
    auth: {
      getState: () => client.getState(),
      subscribe: (listener) => client.subscribe(listener),
      signIn: () => {
        epoch++;
        return client.signIn();
      },
      signOut: () => {
        epoch++;
        return client.signOut();
      },
    },
    ...hostObservationHostMethods(client,()=>epoch),
    ...projectAdmissionHostMethods(client,()=>epoch),
    ...instructionHostMethods(client,()=>epoch),
    ...projectAccessHostMethods(client,()=>epoch),
    ...(client.readAutonomyPolicy && client.invalidationGeneration ? {
      async readAutonomyPolicy(request: AutonomySelection & { signal: AbortSignal }) {
        const { signal, ...selected } = request;
        if (!isAutonomySelection(selected)) throw new Error("AUTONOMY_SELECTION_INVALID");
        const started = epoch, source = client.invalidationGeneration!();
        const authorized = () => {
          const state = client.getState();
          return !signal.aborted && started === epoch && source === client.invalidationGeneration?.() &&
            state.status === "signed_in" && state.acquisition;
        };
        if (!authorized()) throw new Error("AUTONOMY_READ_UNAUTHORIZED");
        const raw = await client.readAutonomyPolicy!({ ...selected, signal });
        if (!authorized()) throw new Error("READ_CANCELLED");
        return decodeAutonomyPolicy(raw, selected);
      },
    } : {}),
    ...(client.executive?.freshConversation ? {freshConversation:{request:async(operation,arguments_,signal)=>{
      const closed=freshConversationArguments(operation,arguments_);
      const transport=client.executive!,group=transport.freshConversation!,method=group.request;
      const getter=client.getState,sourceMethod=client.invalidationGeneration;
      const started=epoch,source=sourceMethod?.call(client),executiveEpoch=transport.authGeneration();
      const current=()=>{
        if(signal.aborted || epoch!==started || client.executive!==transport || transport.freshConversation!==group
          || group.request!==method || client.getState!==getter || client.invalidationGeneration!==sourceMethod
          || sourceMethod?.call(client)!==source || transport.authGeneration()!==executiveEpoch || !transport.available())return false;
        const state=getter.call(client);
        return state.status==='signed_in' && (!freshConversationNeedsWorkspace(operation) || state.acquisition===true);
      };
      if(!current())throw Error('FRESH_CONVERSATION_UNAVAILABLE');
      const result=await method.call(group,operation,closed,signal);
      if(!current())throw Error('FRESH_CONVERSATION_UNAVAILABLE');
      return result;
    }}} : {}),
    ...(client.executive?.projectPlanning ? {projectPlanning:{request: async (operation,arguments_,signal)=>{
      const transport=client.executive!,group=transport.projectPlanning!,method=group.request;
      const started=epoch,source=client.invalidationGeneration?.(),executiveEpoch=transport.authGeneration();
      const current=()=>!signal.aborted && epoch===started && client.executive===transport
        && transport.projectPlanning===group && group.request===method
        && client.invalidationGeneration?.()===source && transport.authGeneration()===executiveEpoch
        && transport.available() && client.getState().status==='signed_in' && client.getState().acquisition;
      if(!current())throw Error('PROJECT_PLANNING_UNAVAILABLE');
      const result=await method.call(group,operation,arguments_,signal);
      if(!current())throw Error('PROJECT_PLANNING_UNAVAILABLE');
      return result;
    }}} : {}),
    ...(boundSource?{sourceOperations:boundSource}:{}),
    ...(sourceContextReader && client.invalidationGeneration ? {
      async readSourceOperationContext(request: SourceOperationContextSelection & { signal: AbortSignal }) {
        const { signal, ...selected } = request;
        if (!validSourceOperationContextSelection(selected)) throw new Error("SOURCE_OPERATION_CONTEXT_SELECTION_INVALID");
        const started = epoch, source = client.invalidationGeneration!();
        const authorized = () => { const state = client.getState();
          return !signal.aborted && started === epoch && source === client.invalidationGeneration?.()
            && client.readSourceOperationContext === sourceContextReader
            && state.status === "signed_in" && state.acquisition;
        };
        if (!authorized()) throw new Error("SOURCE_OPERATION_CONTEXT_UNAUTHORIZED");
        const raw = await sourceContextReader.call(client, { ...selected, signal });
        if (!authorized()) throw new Error("READ_CANCELLED");
        return decodeSourceOperationContext(raw, selected);
      },
    } : {}),
    ...(client.readProjectPlan && client.invalidationGeneration ? {
      async readProjectPlan(request: ProjectPlanSelection & { signal: AbortSignal }) {
        const { signal, ...selected } = request;
        if (!validProjectPlanSelection(selected)) throw new Error("PROJECT_PLAN_SELECTION_INVALID");
        const started = epoch, source = client.invalidationGeneration!();
        const authorized = () => {
          const state = client.getState();
          return !signal.aborted && started === epoch && source === client.invalidationGeneration?.() &&
            state.status === "signed_in" && state.acquisition;
        };
        if (!authorized()) throw new Error("PROJECT_PLAN_READ_UNAUTHORIZED");
        const raw = await client.readProjectPlan!({ ...selected, signal });
        if (!authorized()) throw new Error("READ_CANCELLED");
        return decodeProjectPlan(raw, selected);
      },
    } : {}),
    ...(client.readProjectSessionAssociation && client.invalidationGeneration ? {
      async readProjectSessionAssociation(request: ProjectAssociationSelection & { signal: AbortSignal }) {
        const { signal, ...value } = request;
        const selected = normalizeProjectAssociationSelection(value);
        if (!selected) throw new Error("PROJECT_SESSION_SELECTION_INVALID");
        const started = epoch, source = client.invalidationGeneration!();
        const authorized = () => { const state = client.getState();
          return !signal.aborted && started === epoch && source === client.invalidationGeneration?.() &&
            state.status === "signed_in" && state.acquisition;
        };
        if (!authorized()) throw new Error("PROJECT_SESSION_READ_UNAUTHORIZED");
        const raw = await client.readProjectSessionAssociation!({ ...selected, signal });
        if (!authorized()) throw new Error("READ_CANCELLED");
        const body = decodeProjectAssociation(raw, selected);
        if (!body) throw new Error("PROJECT_SESSION_RESPONSE_INVALID");
        return body;
      },
    } : {}),
    ...(client.readProjectArchivePage && client.invalidationGeneration ? {
      async readProjectArchivePage(request: ArchiveCursor & { signal: AbortSignal }) {
        const { signal, ...cursor } = request;
        if (!validArchiveCursor(cursor)) throw new Error("PROJECT_ARCHIVE_REQUEST_INVALID");
        const started = epoch, source = client.invalidationGeneration!(), reader = client.readProjectArchivePage!;
        const authorized = () => {
          const state = client.getState();
          return !signal.aborted && Number.isSafeInteger(source) && source >= 0 && started === epoch &&
            source === client.invalidationGeneration?.() && reader === client.readProjectArchivePage &&
            state.status === "signed_in" && state.acquisition;
        };
        if (!authorized()) throw new Error("PROJECT_ARCHIVE_READ_UNAUTHORIZED");
        const raw = await reader.call(client, { ...cursor, signal });
        if (!authorized()) throw new Error("READ_CANCELLED");
        const body = decodeProjectArchive(raw);
        if (body.availability === "AVAILABLE" && body.catalogue.document_digest !== cursor.catalogue_digest)
          throw new Error("PROJECT_ARCHIVE_PAGE_CHANGED");
        return body;
      },
    } : {}),
    ...(client.readProjectArchive && client.invalidationGeneration ? {
      async readProjectArchive(request: { signal: AbortSignal }) {
        if (Object.keys(request).length !== 1 || !("signal" in request)) throw new Error("PROJECT_ARCHIVE_REQUEST_INVALID");
        const { signal } = request;
        const started = epoch, source = client.invalidationGeneration!(), reader = client.readProjectArchive!;
        const authorized = () => {
          const state = client.getState();
          return !signal.aborted && Number.isSafeInteger(source) && source >= 0 && started === epoch &&
            source === client.invalidationGeneration?.() && reader === client.readProjectArchive &&
            state.status === "signed_in" && state.acquisition;
        };
        if (!authorized()) throw new Error("PROJECT_ARCHIVE_READ_UNAUTHORIZED");
        const raw = await reader.call(client, { signal });
        if (!authorized()) throw new Error("READ_CANCELLED");
        return decodeProjectArchive(raw);
      },
    } : {}),
    ...(client.readProjectDirection && client.invalidationGeneration ? {
      async readProjectDirection(request: DirectionSelection & { signal: AbortSignal }) {
        const { signal, ...selected } = request;
        if (!validDirectionSelection(selected)) throw new Error("DIRECTION_SELECTION_INVALID");
        const started = epoch, source = client.invalidationGeneration!(), reader = client.readProjectDirection!;
        const authorized = () => {
          const state = client.getState();
          return !signal.aborted && Number.isSafeInteger(source) && source >= 0 && started === epoch &&
            source === client.invalidationGeneration?.() && reader === client.readProjectDirection &&
            state.status === "signed_in" && state.acquisition;
        };
        if (!authorized()) throw new Error("DIRECTION_READ_UNAUTHORIZED");
        const raw = await reader({ ...selected, signal });
        if (!authorized()) throw new Error("READ_CANCELLED");
        return decodeAcceptedDirection(raw, selected);
      },
    } : {}),
    ...(client.readProjectJournal && client.invalidationGeneration ? {
      async readProjectJournal(request: JournalSelection & { signal: AbortSignal }) {
        const { signal, ...selected } = request;
        if (!validJournalSelection(selected)) throw new Error("PROJECT_JOURNAL_SELECTION_INVALID");
        const started = epoch, source = client.invalidationGeneration!();
        const authorized = () => {
          const state = client.getState();
          return !signal.aborted && started === epoch && source === client.invalidationGeneration?.() &&
            state.status === "signed_in" && state.acquisition;
        };
        if (!authorized()) throw new Error("PROJECT_JOURNAL_READ_UNAUTHORIZED");
        const raw = await client.readProjectJournal!({ ...selected, signal });
        if (!authorized()) throw new Error("READ_CANCELLED");
        return decodeProjectJournal(raw, selected.work_ref);
      },
    } : {}),
    ...(client.readAdmittedPlan && client.invalidationGeneration ? {
      async readAdmittedPlan(request: PlanSelection & { signal: AbortSignal }) {
        if (!validPlanSelection({ work_ref: request.work_ref, root_job_id: request.root_job_id })) throw new Error("PLAN_SELECTION_INVALID");
        const selected = { work_ref: request.work_ref, root_job_id: request.root_job_id };
        const started = epoch, source = client.invalidationGeneration!();
        const authorized = () => {
          const state = client.getState();
          return !request.signal.aborted && started === epoch && source === client.invalidationGeneration?.() &&
            state.status === "signed_in" && state.acquisition;
        };
        if (!authorized()) throw new Error("PLAN_READ_UNAUTHORIZED");
        const raw = await client.readAdmittedPlan!({ ...selected, signal: request.signal });
        if (!authorized()) throw new Error("READ_CANCELLED");
        return decodeAdmittedPlan(raw, selected);
      },
    } : {}),
    ...(client.readModelConfiguration && client.invalidationGeneration ? {
      async readModelConfiguration({ signal }: { signal: AbortSignal }) {
        const started = epoch, source = client.invalidationGeneration!(), reader = client.readModelConfiguration!;
        const verify = () => {
          const state = client.getState();
          if (signal.aborted || epoch !== started || !Number.isSafeInteger(source)
            || source !== client.invalidationGeneration?.() || reader !== client.readModelConfiguration)
            throw new Error("READ_CANCELLED");
          if (state.status !== "signed_in" || !state.acquisition) throw new Error("MODEL_CONFIGURATION_UNAUTHORIZED");
        };
        verify();
        const raw = await reader.call(client, { signal });
        verify();
        return decodeModelConfiguration(raw);
      },
    } : {}),
    ...(client.readResourceCapacity && client.invalidationGeneration ? {
      async readResourceCapacity(request: ResourceCapacityReadSelection & { signal: AbortSignal }) {
        const { signal, ...selected } = request;
        if (!validResourceCapacitySelection(selected)) throw new Error("RESOURCE_CAPACITY_SELECTION_INVALID");
        const started = epoch, source = client.invalidationGeneration!(), reader = client.readResourceCapacity!;
        const verify = () => {
          const state = client.getState();
          if (signal.aborted || epoch !== started || !Number.isSafeInteger(source) || source !== client.invalidationGeneration?.() || reader !== client.readResourceCapacity)
            throw new Error("READ_CANCELLED");
          if (state.status !== "signed_in" || !state.acquisition) throw new Error("RESOURCE_CAPACITY_UNAUTHORIZED");
        };
        verify();
        const raw = await reader.call(client, { ...selected, signal });
        verify();
        return decodeResourceCapacityRead(raw, selected);
      },
    } : {}),
    ...(client.readRetainedActivity && client.invalidationGeneration ? {
      async readRetainedActivity(request: ActivitySelection & { signal: AbortSignal }) {
        const { signal, ...selected } = request;
        if (!validActivitySelection(selected)) throw new Error("ACTIVITY_SELECTION_INVALID");
        const started = epoch, source = client.invalidationGeneration!();
        const authorized = () => {
          const state = client.getState();
          return !signal.aborted && epoch === started && source === client.invalidationGeneration?.() &&
            state.status === "signed_in" && state.acquisition;
        };
        if (!authorized()) throw new Error("ACTIVITY_READ_UNAUTHORIZED");
        const raw = await client.readRetainedActivity!({ ...selected, signal });
        if (!authorized()) throw new Error("READ_CANCELLED");
        return decodeRetainedActivity(raw, selected);
      },
    } : {}),
    ...(client.readAttendedFabric && client.invalidationGeneration ? {
      async readAttendedFabric(request: AttendedSelection & { signal: AbortSignal }) {
        const selected = attendedSelection(request);
        if (!selected) throw new Error("FABRIC_SELECTION_INVALID");
        const started = epoch;
        const source = client.invalidationGeneration!();
        const read = client.readAttendedFabric!;
        const verify = () => {
          check(request.signal, started);
          if (!Number.isSafeInteger(source) ||
              source !== client.invalidationGeneration?.() ||
              typeof read !== "function" || read !== client.readAttendedFabric)
            throw new Error("READ_CANCELLED");
          const state = client.getState();
          if (state.status !== "signed_in" || !state.acquisition)
            throw new Error("FABRIC_READ_UNAUTHORIZED");
        };
        verify();
        const raw = await read.call(client, { ...selected, signal: request.signal });
        verify();
        return decodeAttendedStatus(raw, selected);
      },
    } : {}),
    ...(client.readOriginalMissionV4 ? {
      async readOriginalMissionV4(request: MissionSelection & { signal: AbortSignal }) {
        const { signal, ...input } = request;
        const selected = normalizeWorkspaceSelection(input);
        if (!selected) throw new Error("SELECTION_INVALID");
        const started = epoch, sourceGeneration = client.invalidationGeneration?.();
        const read = client.readOriginalMissionV4;
        let invalidated = false;
        const verify = () => {
          const state = client.getState();
          if (invalidated || signal.aborted || started !== epoch || sourceGeneration !== client.invalidationGeneration?.()
            || read !== client.readOriginalMissionV4 || state.status !== "signed_in" || !state.acquisition)
            throw new Error("READ_CANCELLED");
        };
        verify();
        const release = client.subscribe(() => { invalidated = true; });
        try {
          verify();
          const raw = await read!.call(client, { ...selected, signal });
          verify();
          const decoded = decodeOriginalAcceptanceBody(raw, selected);
          if (!decoded) throw new Error("MISSION_V4_RESPONSE_INVALID");
          return decoded;
        } finally { release(); }
      },
    } : {}),
    ...(client.productAcceptanceOwner && client.readMissionV4 ? {
      productAcceptanceOwner: client.productAcceptanceOwner,
      async readMissionV4(request: MissionV4Selection & { signal: AbortSignal }) {
        const { signal, ...input } = request;
        const selected = missionV4Selection(input);
        if (!selected) throw new Error("SELECTION_INVALID");
        const started = epoch, sourceGeneration = client.invalidationGeneration?.(), owner = client.productAcceptanceOwner;
        const authorized = () => {
          const state = client.getState();
          return !signal.aborted && started === epoch && sourceGeneration === client.invalidationGeneration?.()
            && owner === client.productAcceptanceOwner && state.status === "signed_in" && state.acquisition;
        };
        const guard = guardAcceptanceRead(owner, selected, authorized);
        try {
          guard.check();
          const raw = await client.readMissionV4!({ ...selected, signal });
          guard.check();
          const decoded = decodeMissionv4(raw, { workRef: selected.workRef, rootJobId: selected.rootJobId }, selected.requestMessageKey);
          if (!decoded) throw new Error("MISSION_V4_RESPONSE_INVALID");
          return decoded;
        } finally { guard.dispose(); }
      },
    } : {}),
    ...(client.readAttendedFabricCatalog && client.invalidationGeneration ? {
      async readAttendedFabricCatalog({ signal }: { signal: AbortSignal }) {
        const started = epoch;
        const source = client.invalidationGeneration!();
        const read = client.readAttendedFabricCatalog!;
        const verify = () => {
          check(signal, started);
          if (!Number.isSafeInteger(source) ||
              source !== client.invalidationGeneration?.() ||
              typeof read !== "function" || read !== client.readAttendedFabricCatalog)
            throw new Error("READ_CANCELLED");
          const state = client.getState();
          if (state.status !== "signed_in" || !state.acquisition)
            throw new Error("FABRIC_READ_UNAUTHORIZED");
        };
        verify();
        const raw = await read.call(client, { signal });
        verify();
        return decodeBrowserScopedFabricCatalog(raw);
      },
    } : {}),
    async readPrograms({ signal }) {
      const started = epoch;
      check(signal, started);
      const raw = await client.readPrograms({ signal });
      check(signal, started);
      return decodeProgramsEnvelope(raw);
    },
    ...(client.readByokRoles && client.invalidationGeneration ? {
      async readByokRoles({ signal }: { signal: AbortSignal }) {
        const started = epoch;
        const source = client.invalidationGeneration!();
        const read = client.readByokRoles!;
        const generation = client.invalidationGeneration!;
        const verify = () => {
          check(signal, started);
          if (!Number.isSafeInteger(source) || generation !== client.invalidationGeneration ||
              source !== generation.call(client) || read !== client.readByokRoles)
            throw new Error("READ_CANCELLED");
          const state = client.getState();
          if (state.status !== "signed_in" || !state.acquisition)
            throw new Error("BYOK_READ_UNAUTHORIZED");
        };
        verify();
        const raw = await read.call(client, { signal });
        verify();
        const result = decodeByokRolesRead(raw);
        verify();
        return result;
      },
    } : {}),
    ...(client.readControlRoomState ? {
      async readControlRoomState({ signal }: { signal: AbortSignal }) {
        const started = epoch;
        check(signal, started);
        const raw = await client.readControlRoomState!({ signal });
        check(signal, started);
        return decodeControlRoomRead(raw);
      },
    } : {}),
    ...(client.readControlRoomDiscovery ? {
      async readControlRoomDiscovery({ signal }: { signal: AbortSignal }) {
        const started = epoch;
        check(signal, started);
        const state = client.getState();
        if (state.status !== "signed_in" || !state.acquisition)
          throw new Error("DISCOVERY_READ_UNAUTHORIZED");
        const raw = await client.readControlRoomDiscovery!({ signal });
        check(signal, started);
        const decoded = decodeControlRoomDiscovery(raw);
        check(signal, started);
        return decoded;
      },
    } : {}),
    ...(client.openControlRoomSurface ? {
      openControlRoomSurface: bindAction("open", "openControlRoomSurface")!,
    } : {}),
    ...(client.bindControlRoomSurface ? {
      bindControlRoomSurface: bindAction("bind", "bindControlRoomSurface")!,
    } : {}),
    ...(client.unbindControlRoomSurface ? {
      unbindControlRoomSurface: bindAction("unbind", "unbindControlRoomSurface")!,
    } : {}),
    ...(client.refreshControlRoomBuilds ? {
      refreshControlRoomBuilds: bindAction("refresh-builds", "refreshControlRoomBuilds")!,
    } : {}),
    async readProgramsObservation({ signal }) {
      const started = epoch;
      check(signal, started);
      const raw = await client.readPrograms({ signal });
      check(signal, started);
      return decodeProgramsObservation(raw);
    },
    async readWork({ signal }) {
      const started = epoch;
      check(signal, started);
      const raw = await client.readWork({ signal });
      check(signal, started);
      const result = decodeWorkDocument(raw);
      if (!result) throw new Error("WORK_RESPONSE_INVALID");
      return result;
    },
    async readMission({ workRef, rootJobId, signal }) {
      const selection = normalizeSelection({ workRef, rootJobId });
      if (!selection) throw new Error("SELECTION_INVALID");
      const started = epoch;
      check(signal, started);
      const raw = await client.readMission({
        work_ref: workRef,
        root_job_id: rootJobId,
        signal,
      });
      check(signal, started);
      const result = decodeMission(raw, selection);
      // Live acquisition is v2. The App keeps v1 only for historical fixtures.
      if (!result || result.schema !== "mastermind.mission_workspace.v2")
        throw new Error("MISSION_RESPONSE_INVALID");
      return result;
    },
    async readMissionV3({ workRef, rootJobId, signal }) {
      const selection = normalizeWorkspaceSelection({ workRef, rootJobId });
      if (!selection) throw new Error("SELECTION_INVALID");
      const started = epoch;
      check(signal, started);
      if (!client.readMissionV3) throw new Error("MISSION_V3_UNAVAILABLE");
      const raw = await client.readMissionV3({
        workRef,
        rootJobId,
        signal,
      });
      check(signal, started);
      const result = decodeMissionv3(raw, selection);
      if (!result) throw new Error("MISSION_V3_RESPONSE_INVALID");
      return result;
    },
    async readResultReferences({ workRef, rootJobId, signal }) {
      const selection = normalizeWorkspaceSelection({ workRef, rootJobId });
      if (!selection) throw new Error("SELECTION_INVALID");
      const started = epoch;
      check(signal, started);
      if (!client.readResultReferences)
        throw new Error("RESULT_REFERENCES_UNAVAILABLE");
      const raw = await client.readResultReferences({
        workRef: selection.workRef,
        rootJobId: selection.rootJobId,
        signal,
      });
      check(signal, started);
      // The fixed HTTP body (never a private socket frame) is fully decoded
      // by the closed result-references decoder. The typed allowed 503
      // unavailable document is a valid decoded outcome, not an error.
      const decoded = decodeResultReferencesEnvelope(raw, {
        workRef: selection.workRef,
        rootJobId: selection.rootJobId,
      });
      if (!decoded) throw new Error("RESULT_REFERENCES_RESPONSE_INVALID");
      return decoded;
    },
    async readResult({
      workRef,
      rootJobId,
      jobId,
      attemptId,
      resultEnvelopeDigest,
      signal,
    }) {
      // The exact five-key selector is normalized alone; the AbortSignal is
      // an option and never part of the selector.
      const normalized = normalizeResultSelection({
        workRef,
        rootJobId,
        jobId,
        attemptId,
        resultEnvelopeDigest,
      });
      if (!normalized) throw new Error("SELECTION_INVALID");
      const started = epoch;
      check(signal, started);
      if (!client.readResult) throw new Error("RESULT_READ_UNAVAILABLE");
      const raw = await client.readResult({
        workRef: normalized.workRef,
        rootJobId: normalized.rootJobId,
        jobId: normalized.jobId,
        attemptId: normalized.attemptId,
        resultEnvelopeDigest: normalized.resultEnvelopeDigest,
        signal,
      });
      check(signal, started);
      // The typed allowed 503 body is the same frozen envelope with
      // availability "UNAVAILABLE": it survives only through the full
      // decoder below, which validates the complete closed body, its
      // reason vocabulary and its null result/observation joins. There is
      // deliberately no shortcut around that validation.
      const decoded = decodeResultEnvelope(raw, normalized);
      if (!decoded) throw new Error("RESULT_RESPONSE_INVALID");
      return decoded;
    },
    ...(client.readMissionResult && client.invalidationGeneration ? {
      async readMissionResult(request: ResultSelection & { signal: AbortSignal }) {
        const { signal, ...input } = request;
        const selected = normalizeResultSelection(input);
        if (!selected) throw new Error("SELECTION_INVALID");
        const started = epoch;
        const sourceGeneration = client.invalidationGeneration?.();
        const read = client.readMissionResult;
        let invalidated = false;
        const verify = () => {
          const state = client.getState();
          if (invalidated || signal.aborted || started !== epoch
            || sourceGeneration !== client.invalidationGeneration?.()
            || read !== client.readMissionResult
            || state.status !== "signed_in" || !state.acquisition)
            throw new Error("READ_CANCELLED");
        };
        verify();
        const release = client.subscribe(() => { invalidated = true; });
        try {
          verify();
          const raw = await read!.call(client, { ...selected, signal });
          verify();
          const decoded = decodeMissionResult(raw, selected);
          if (!decoded.ok) throw new Error("MISSION_RESULT_RESPONSE_INVALID");
          return decoded.document;
        } finally { release(); }
      },
    } : {}),
    async readCurrentWindow({ signal }) {
      const started = epoch;
      check(signal, started);
      const raw = await client.readCurrentWindow({ signal });
      check(signal, started);
      const result = await decodeWindow(raw);
      check(signal, started);
      if (!result) throw new Error("WINDOW_RESPONSE_INVALID");
      return result;
    },
    ...(command ? { commandBinding: command } : {}),
    ...(session
      ? {
          sessionCommandBinding: session.binding,
          session: {
            ...(session.createProjectHistoryReader ? {createProjectHistoryReader: session.createProjectHistoryReader} : {}),
            ...(session.createProjectCatalogueReader ? {createProjectCatalogueReader: session.createProjectCatalogueReader} : {}),
            refresh: (selection: unknown) => session.refresh(selection),
            setStopCondition: (provider: () => unknown) => session.setStopCondition(provider),
          },
        }
      : {}),
  };
}

type Invoke = <T>(
  command: string,
  args?: Record<string, unknown>,
) => Promise<T>;
type Listen = (
  event: string,
  listener: (event: { payload: unknown }) => void,
) => Promise<() => void>;
function authState(raw: unknown): AuthState {
  if (typeof raw !== "object" || raw === null || Array.isArray(raw))
    throw new Error("AUTH_STATE_INVALID");
  const r = raw as Record<string, unknown>;
  if (
    Object.keys(r).sort().join(",") !== "acquisition,content,reason,status" ||
    ![
      "unconfigured",
      "signed_out",
      "signing_in",
      "signed_in",
      "error",
    ].includes(String(r.status)) ||
    !(
      r.reason === null ||
      (typeof r.reason === "string" && /^[A-Z_]{1,128}$/.test(r.reason))
    ) ||
    typeof r.acquisition !== "boolean" ||
    typeof r.content !== "boolean"
  )
    throw new Error("AUTH_STATE_INVALID");
  return { ...r } as unknown as AuthState;
}

/** Injectable fixed command functions permit ordinary fixture tests without a native app launch. */
export async function createNativeClient(
  invoke: Invoke,
  listen: Listen,
): Promise<RawClient> {
  const executive = await createNativeExecutiveTransport(invoke, listen);
  const terminalSharing = createLazyTerminalSharingHost(invoke,
    (event, handler) => listen(event, message => handler(message.payload)));
  let current: AuthState = {
    status: "unconfigured",
    reason: "NATIVE_HOST_UNAVAILABLE",
    acquisition: false,
    content: false,
  };
  const listeners = new Set<(state: AuthState) => void>();
  let epoch = 0;
  const nativeDraftRecovery = createNativeDraftRecoveryOwner({
    inspect: () => invoke("read_native_draft_continuity"),
    sourceGeneration: () => epoch,
    signedIn: () => current.status === "signed_in" && current.acquisition,
  });
  let readGeneration = new AbortController();
  const invalidateReads = () => {
    nativeDraftRecovery.invalidate();
    epoch++;
    const previous = readGeneration;
    readGeneration = new AbortController();
    previous.abort();
  };
  let control = 0;
  const update = (raw: unknown) => {
    current = authState(raw);
    invalidateReads();
    for (const listener of listeners) listener({ ...current });
  };
  await listen("mastermind-auth-state", (event) => {
    try {
      update(event.payload);
    } catch {
      /* refuse malformed state */
    }
  });
  const initial = epoch;
  const status = await invoke("auth_status");
  if (initial === epoch) update(status);
  async function read(
    command:
      | "executive_auth_status"
      | "read_programs"
      | "read_byok_roles"
      | "read_control_room_state"
      | "read_work"
      | "read_mission"
      | "read_mission_v3"
      | "read_project_admission_control"
      | "pause_project_admission"
      | "resume_project_admission"
      | "read_project_admission_operation"
      | "read_project_instructions"
      | "read_project_access"
      | "read_instruction_admission_control"
      | "pause_instruction_admission"
      | "read_instruction_admission_operation"
      | "read_autonomy_policy"
      | "read_project_plan"
      | "read_project_journal"
      | "read_project_knowledge_catalogue"
      | "read_project_knowledge_memory"
      | "read_project_knowledge_source"
      | "read_project_session"
      | "read_project_direction"
      | "read_project_archive"
      | "read_project_archive_page"
      | "read_source_operation_context"
      | "source_operation_options"
      | "source_operation_prepare"
      | "source_operation_read"
      | "source_operation_submit"
      | "source_operation_reconcile"
      | "source_operation_advance"
      | "read_admitted_plan"
      | "read_retained_activity"
      | "read_resource_capacity"
      | "read_model_configuration"
      | "read_host_observation"
      | "read_fabric_catalog"
      | "read_fabric_status"
      | "read_result"
      | "read_mission_result"
      | "read_result_references"
      | "read_current_window",
    signal: AbortSignal,
    args?: Record<string, unknown>,
  ) {
    const started = epoch;
    const generation = readGeneration.signal;
    if (signal.aborted || generation.aborted) throw new Error("READ_CANCELLED");
    // Tauri invoke has no AbortSignal parameter. Settle this read locally on
    // cancellation without claiming the native request stopped or issuing any
    // second native command. Both late outcomes remain observed below.
    return new Promise<unknown>((resolve, reject) => {
      let settled = false;
      const finish = (failed: boolean, value: unknown) => {
        if (settled) return;
        settled = true;
        signal.removeEventListener("abort", onAbort);
        generation.removeEventListener("abort", onAbort);
        if (failed) reject(value);
        else resolve(value);
      };
      const onAbort = () => finish(true, new Error("READ_CANCELLED"));
      const onFailure = (error: unknown) => {
        if (signal.aborted || started !== epoch) onAbort();
        else finish(true, error);
      };
      signal.addEventListener("abort", onAbort, { once: true });
      generation.addEventListener("abort", onAbort, { once: true });
      if (signal.aborted || generation.aborted) {
        onAbort();
        return;
      }
      try {
        Promise.resolve(invoke(command, args)).then((raw) => {
          if (signal.aborted || started !== epoch) onAbort();
          else finish(false, raw);
        }, onFailure);
      } catch (error) {
        onFailure(error);
      }
    });
  }
  return {
    readNativeExecutiveDiagnostics: ({ signal }) => read("executive_auth_status", signal, { diagnostics: true }),
    nativeDraftRecovery,
    terminalSharing,
    executive: executive.transport,
    executiveSession: executive.sessionTransport,
    openTerminalBriefs: createTerminalBriefsNavigationPort((command) => invoke(command)),
    getState: () => ({ ...current }),
    invalidationGeneration: () => epoch,
    subscribe(listener) {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    async signIn() {
      executive.invalidate();
      invalidateReads();
      const ticket = ++control;
      const started = epoch;
      const result = await invoke("sign_in");
      if (ticket === control && started === epoch) update(result);
    },
    async signOut() {
      nativeDraftRecovery.clear();
      executive.invalidate();
      const ticket = ++control;
      update({
        status: "signed_out",
        reason: "USER_SIGNED_OUT",
        acquisition: false,
        content: false,
      });
      const started = epoch;
      const result = await invoke("sign_out");
      if (ticket === control && started === epoch) update(result);
    },
  sourceOperations: createSourceOperationTransport(
    (method, _path, body, signal) => {
      if (current.status !== "signed_in" || !current.acquisition)
        return Promise.reject(new Error("SOURCE_OPERATION_UNAUTHORIZED"));
      return read(
        (
          {
            options: "source_operation_options",
            prepare: "source_operation_prepare",
            read: "source_operation_read",
            submit: "source_operation_submit",
            reconcile: "source_operation_reconcile",
            advance: "source_operation_advance",
          } as const
        )[method],
        signal,
        { request: body },
      );
    },
  ),
    readPrograms: ({ signal }) => read("read_programs", signal),
    readByokRoles: ({ signal }) => read("read_byok_roles", signal),
    readControlRoomState: ({ signal }) => {
      if (current.status !== "signed_in" || !current.acquisition)
        return Promise.reject(new Error("CONTROL_ROOM_READ_UNAUTHORIZED"));
      return read("read_control_room_state", signal);
    },
    readWork: ({ signal }) => read("read_work", signal),
    readAttendedFabricCatalog: ({ signal }) => read("read_fabric_catalog", signal),
    readAttendedFabric: ({ rootId, runId, signal }) => {
      const selected = attendedSelection({ rootId, runId });
      if (!selected) return Promise.reject(new Error("FABRIC_SELECTION_INVALID"));
      return read("read_fabric_status", signal, { selection: {
        root_id: selected.rootId, run_id: selected.runId,
      } });
    },
    readMission: ({ work_ref, root_job_id, signal }) => {
      if (!normalizeSelection({ workRef: work_ref, rootJobId: root_job_id }))
        return Promise.reject(new Error("SELECTION_INVALID"));
      return read("read_mission", signal, {
        selection: { work_ref, root_job_id },
      });
    },
    readProjectAdmissionControl: (request) => {
      const input=projectAdmissionPublicRequest("current",request);
      if(!input)return Promise.reject(new Error("PROJECT_ADMISSION_REQUEST_INVALID"));
      return read("read_project_admission_control",request.signal,{selection:input.selection});
    },
    readProjectAccess: request => {
      const selection=projectAccessPublicSelection(request);
      if(!selection)return Promise.reject(Error("PROJECT_ACCESS_REQUEST_INVALID"));
      return read("read_project_access",request.signal,{selection});
    },
    readProjectInstructions: request => {
      const input=instructionPublicRequest("content",request);
      if(!input)return Promise.reject(Error("INSTRUCTION_REQUEST_INVALID"));
      return read("read_project_instructions",request.signal,{selection:input.selection});
    },
    readInstructionAdmissionControl: request => {
      const input=instructionPublicRequest("current",request);
      if(!input)return Promise.reject(Error("INSTRUCTION_REQUEST_INVALID"));
      return read("read_instruction_admission_control",request.signal,{selection:input.selection});
    },
    pauseInstructionAdmission: request => {
      const input=instructionPublicRequest("pause",request);
      if(!input)return Promise.reject(Error("INSTRUCTION_REQUEST_INVALID"));
      return read("pause_instruction_admission",request.signal,{request:input});
    },
    readInstructionAdmissionOperation: request => {
      const input=instructionPublicRequest("status",request);
      if(!input)return Promise.reject(Error("INSTRUCTION_REQUEST_INVALID"));
      return read("read_instruction_admission_operation",request.signal,{request:input});
    },
    pauseProjectAdmission: (request) => {
      const input=projectAdmissionPublicRequest("pause",request);
      if(!input)return Promise.reject(new Error("PROJECT_ADMISSION_REQUEST_INVALID"));
      return read("pause_project_admission",request.signal,{request:input});
    },
    resumeProjectAdmission: (request) => {
      const input=projectAdmissionPublicRequest("resume",request);
      if(!input)return Promise.reject(new Error("PROJECT_ADMISSION_REQUEST_INVALID"));
      return read("resume_project_admission",request.signal,{request:input});
    },
    readProjectAdmissionOperation: (request) => {
      const input=projectAdmissionPublicRequest("status",request);
      if(!input)return Promise.reject(new Error("PROJECT_ADMISSION_REQUEST_INVALID"));
      return read("read_project_admission_operation",request.signal,{request:input});
    },
    readAutonomyPolicy: (request) => {
      const { signal, ...selected } = request;
      if (!isAutonomySelection(selected))
        return Promise.reject(new Error("AUTONOMY_SELECTION_INVALID"));
      return read("read_autonomy_policy", signal, { selection: selected });
    },
    readSourceOperationContext: (request) => {
      const { signal, ...selected } = request;
      if (!validSourceOperationContextSelection(selected)) return Promise.reject(new Error("SOURCE_OPERATION_CONTEXT_SELECTION_INVALID"));
      return read("read_source_operation_context", signal, { selection: { action: selected.action, work_ref: selected.workRef } });
    },
    readProjectPlan: (request) => {
      const { signal, ...selected } = request;
      if (!validProjectPlanSelection(selected))
        return Promise.reject(new Error("PROJECT_PLAN_SELECTION_INVALID"));
      return read("read_project_plan", signal, { selection: selected });
    },
    readProjectSessionAssociation: (request) => {
      const { signal, ...value } = request;
      const selected = normalizeProjectAssociationSelection(value);
      if (!selected) return Promise.reject(new Error("PROJECT_SESSION_SELECTION_INVALID"));
      return read("read_project_session", signal, { selection: { work_ref: selected.workRef, root_job_id: selected.rootJobId } });
    },
    readProjectArchivePage: (request) => {
      const { signal, ...cursor } = request;
      if (!validArchiveCursor(cursor)) return Promise.reject(new Error("PROJECT_ARCHIVE_REQUEST_INVALID"));
      return read("read_project_archive_page", signal, { cursor });
    },
    readProjectArchive: ({ signal }) => read("read_project_archive", signal),
    readProjectDirection: (request) => {
      const { signal, ...selected } = request;
      if (!validDirectionSelection(selected))
        return Promise.reject(new Error("DIRECTION_SELECTION_INVALID"));
      return read("read_project_direction", signal, { selection: selected });
    },
    readProjectKnowledgeCatalogue: (request) => {
      const {signal,...value}=request, selected=knowledgeReadSelection(value,"catalogue");
      if(!selected) return Promise.reject(new Error("PROJECT_KNOWLEDGE_SELECTION_INVALID"));
      return read("read_project_knowledge_catalogue",signal,{selection:selected});
    },
    readProjectKnowledgeMemory: (request) => {
      const {signal,...value}=request, selected=knowledgeReadSelection(value,"memory");
      if(!selected) return Promise.reject(new Error("PROJECT_KNOWLEDGE_SELECTION_INVALID"));
      return read("read_project_knowledge_memory",signal,{selection:selected});
    },
    readProjectKnowledgeSource: (request) => {
      const {signal,...value}=request, selected=knowledgeReadSelection(value,"source");
      if(!selected) return Promise.reject(new Error("PROJECT_KNOWLEDGE_SELECTION_INVALID"));
      return read("read_project_knowledge_source",signal,{selection:selected});
    },
    readProjectJournal: (request) => {
      const { signal, ...selected } = request;
      if (!validJournalSelection(selected))
        return Promise.reject(new Error("PROJECT_JOURNAL_SELECTION_INVALID"));
      return read("read_project_journal", signal, { selection: selected });
    },
    readAdmittedPlan: ({ work_ref, root_job_id, signal }) => {
      if (!validPlanSelection({ work_ref, root_job_id }))
        return Promise.reject(new Error("PLAN_SELECTION_INVALID"));
      return read("read_admitted_plan", signal, { selection: { work_ref, root_job_id } });
    },
    readModelConfiguration: ({ signal }) => read("read_model_configuration", signal),
    readHostObservation: request => {
      const selection=hostObservationPublicSelection(request);
      return selection ? read("read_host_observation",request.signal,{selection})
        : Promise.reject(Error("HOST_OBSERVATION_REQUEST_INVALID"));
    },
    readResourceCapacity: ({ work_ref, root_job_id, job_id, attempt_id, signal }) => {
      const selection = { work_ref, root_job_id, job_id, attempt_id };
      if (!validResourceCapacitySelection(selection))
        return Promise.reject(new Error("RESOURCE_CAPACITY_SELECTION_INVALID"));
      return read("read_resource_capacity", signal, { selection });
    },
    readRetainedActivity: ({ work_ref, root_job_id, job_id, attempt_id, signal }) => {
      const selection = { work_ref, root_job_id, job_id, attempt_id };
      if (!validActivitySelection(selection))
        return Promise.reject(new Error("ACTIVITY_SELECTION_INVALID"));
      return read("read_retained_activity", signal, { selection });
    },
    readMissionV3: ({ workRef, rootJobId, signal }) => {
      if (!normalizeWorkspaceSelection({ workRef, rootJobId }))
        return Promise.reject(new Error("SELECTION_INVALID"));
      return read("read_mission_v3", signal, {
        selection: { work_ref: workRef, root_job_id: rootJobId },
      });
    },
    readResult: ({
      workRef,
      rootJobId,
      jobId,
      attemptId,
      resultEnvelopeDigest,
      signal,
    }) => {
      const normalized = normalizeResultSelection({
        workRef,
        rootJobId,
        jobId,
        attemptId,
        resultEnvelopeDigest,
      });
      if (!normalized) return Promise.reject(new Error("SELECTION_INVALID"));
      return read("read_result", signal, {
        selection: {
          work_ref: workRef,
          root_job_id: rootJobId,
          job_id: jobId,
          attempt_id: attemptId,
          result_envelope_digest: resultEnvelopeDigest,
        },
      });
    },
    readMissionResult: ({
      workRef, rootJobId, jobId, attemptId, resultEnvelopeDigest, signal,
    }) => {
      const selected = normalizeResultSelection({
        workRef, rootJobId, jobId, attemptId, resultEnvelopeDigest,
      });
      if (!selected) return Promise.reject(new Error("SELECTION_INVALID"));
      return read("read_mission_result", signal, {
        selection: {
          work_ref: selected.workRef,
          root_job_id: selected.rootJobId,
          job_id: selected.jobId,
          attempt_id: selected.attemptId,
          result_envelope_digest: selected.resultEnvelopeDigest,
        },
      });
    },
    readResultReferences: ({ workRef, rootJobId, signal }) => {
      if (!normalizeWorkspaceSelection({ workRef, rootJobId }))
        return Promise.reject(new Error("SELECTION_INVALID"));
      return read("read_result_references", signal, {
        selection: { work_ref: workRef, root_job_id: rootJobId },
      });
    },
    readCurrentWindow: ({ signal }) => read("read_current_window", signal),
  };
}
