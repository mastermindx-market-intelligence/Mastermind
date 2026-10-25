import { decodeOriginalAcceptanceBody, guardAcceptanceRead, missionV4Selection, type MissionV4Selection, type ProductAcceptanceOwner } from "./product-acceptance/owner-observation";
import { attendedSelection, decodeAttendedStatus, type AttendedSelection, type AttendedStatus } from "./fabric/attended-status";
import { decodeAdmittedPlan, validPlanSelection, type PlanRead, type PlanSelection } from "./planning/admitted-plan";
import { decodeRetainedActivity, validActivitySelection, type ActivitySelection, type ActivityRead } from "./planning/retained-activity";
import { createNativeExecutiveTransport } from "./native-executive-transport";
import type { ExecutiveSessionTransport } from "./orchestration/executive-session-command-port";
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

export interface RawClient {
  /** Existing authenticated original-owner acquisition; no caller-supplied request key. */
  readOriginalMissionV4?(request: MissionSelection & { signal: AbortSignal }): Promise<unknown>;
  /** Optional private owner publication; never reconstructed from browser input. */
  readonly productAcceptanceOwner?: ProductAcceptanceOwner;
  readMissionV4?(request: MissionV4Selection & { signal: AbortSignal }): Promise<unknown>;
  /** Optional fixed Research capability; private Auth0 token stays with its owner. */
  readonly research?: ResearchEvidenceTransport;
  readonly executive?: OsExecutiveTransport;
  /** Optional fixed selected-session continuation transport; same private bearer custody. */
  readonly executiveSession?: ExecutiveSessionTransport;
  getState(): AuthState;
  /** Existing source epoch, when exposed by the fixed client; never a principal or grant. */
  invalidationGeneration?(): number;
  subscribe(listener: (state: AuthState) => void): () => void;
  signIn(): Promise<unknown>;
  signOut(): Promise<unknown>;
  /** Optional owner-authorized status-only Fabric port. No default browser/machine credential bridge. */
  readAdmittedPlan?(request: PlanSelection & { signal: AbortSignal }): Promise<unknown>;
  readRetainedActivity?(request: ActivitySelection & { signal: AbortSignal }): Promise<unknown>;
  readAttendedFabric?(request: AttendedSelection & { signal: AbortSignal }): Promise<unknown>;
  readPrograms(request: { signal: AbortSignal }): Promise<unknown>;
  /** Fixed authenticated one-cache Control Room state; no operator writes. */
  readControlRoomState?(request: { signal: AbortSignal }): Promise<unknown>;
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
export interface MissionHost {
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
  readAdmittedPlan?: (request: PlanSelection & { signal: AbortSignal }) => Promise<PlanRead>;
  readRetainedActivity?: (request: ActivitySelection & { signal: AbortSignal }) => Promise<ActivityRead>;
  readAttendedFabric?: (request: AttendedSelection & { signal: AbortSignal }) => Promise<AttendedStatus>;
  readPrograms?: ProgramRead;
  readControlRoomState?: (request: { signal: AbortSignal }) => Promise<ControlRoomRead>;
  readControlRoomDiscovery?: (request: { signal: AbortSignal }) => Promise<ControlRoomDiscovery>;
  openControlRoomSurface?: (request: { payload: Record<string, unknown>; signal: AbortSignal }) => Promise<ControlRoomActionResult>;
  bindControlRoomSurface?: (request: { payload: Record<string, unknown>; signal: AbortSignal }) => Promise<ControlRoomActionResult>;
  unbindControlRoomSurface?: (request: { payload: Record<string, unknown>; signal: AbortSignal }) => Promise<ControlRoomActionResult>;
  refreshControlRoomBuilds?: (request: { signal: AbortSignal }) => Promise<ControlRoomActionResult>;
  /** Same fixed Programs acquisition, retaining its collection owner receipt. */
  readProgramsObservation?: (request: { signal: AbortSignal }) => Promise<ProgramsObservation>;
  readWork?: (request: { signal: AbortSignal }) => Promise<WorkDocument>;
  readResult?: MissionResultRead;
  readCurrentWindow?: (request: {
    signal: AbortSignal;
  }) => Promise<WindowDocument>;
  invalidationGeneration?: () => number;
  selection?: unknown;
  auth?: Pick<RawClient, "getState" | "subscribe" | "signIn" | "signOut">;
  commandBinding?: OrchestratorCommandBinding;
  /** Separately mounted session binding; never the launch route. */
  sessionCommandBinding?: unknown;
  /** Pushes the exact selection on every transition and registers the explicit condition provider. */
  session?: {
    refresh(selection: unknown): Promise<void>;
    setStopCondition(provider: () => unknown): void;
  };
}
export interface SessionHostAttachment {
  readonly binding: unknown;
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
  const command = completeOrchestratorCommandBinding(commandBinding);
  return {
    invalidationGeneration: () => epoch,
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
        check(request.signal, started);
        const state = client.getState();
        if (state.status !== "signed_in" || !state.acquisition) throw new Error("FABRIC_READ_UNAUTHORIZED");
        const raw = await client.readAttendedFabric!({ ...selected, signal: request.signal });
        check(request.signal, started);
        const current = client.getState();
        if (current.status !== "signed_in" || !current.acquisition) throw new Error("FABRIC_READ_UNAUTHORIZED");
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
    async readPrograms({ signal }) {
      const started = epoch;
      check(signal, started);
      const raw = await client.readPrograms({ signal });
      check(signal, started);
      return decodeProgramsEnvelope(raw);
    },
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
  let current: AuthState = {
    status: "unconfigured",
    reason: "NATIVE_HOST_UNAVAILABLE",
    acquisition: false,
    content: false,
  };
  const listeners = new Set<(state: AuthState) => void>();
  let epoch = 0;
  let readGeneration = new AbortController();
  const invalidateReads = () => {
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
      | "read_programs"
      | "read_work"
      | "read_mission"
      | "read_mission_v3"
      | "read_admitted_plan"
      | "read_retained_activity"
      | "read_result"
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
    executive: executive.transport,
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
      executive.invalidate();
      const ticket = ++control;
      update({
        status: "signed_out",
        reason: null,
        acquisition: false,
        content: false,
      });
      const started = epoch;
      const result = await invoke("sign_out");
      if (ticket === control && started === epoch) update(result);
    },
    readPrograms: ({ signal }) => read("read_programs", signal),
    readWork: ({ signal }) => read("read_work", signal),
    readMission: ({ work_ref, root_job_id, signal }) => {
      if (!normalizeSelection({ workRef: work_ref, rootJobId: root_job_id }))
        return Promise.reject(new Error("SELECTION_INVALID"));
      return read("read_mission", signal, {
        selection: { work_ref, root_job_id },
      });
    },
    readAdmittedPlan: ({ work_ref, root_job_id, signal }) => {
      if (!validPlanSelection({ work_ref, root_job_id }))
        return Promise.reject(new Error("PLAN_SELECTION_INVALID"));
      return read("read_admitted_plan", signal, { selection: { work_ref, root_job_id } });
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
    readCurrentWindow: ({ signal }) => read("read_current_window", signal),
  };
}
