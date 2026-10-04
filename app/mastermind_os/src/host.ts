import {
  decodeMission,
  decodeMissionv3,
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
export interface RawClient {
  getState(): AuthState;
  /** Existing source epoch, when exposed by the fixed client; never a principal or grant. */
  invalidationGeneration?(): number;
  subscribe(listener: (state: AuthState) => void): () => void;
  signIn(): Promise<unknown>;
  signOut(): Promise<unknown>;
  readPrograms(request: { signal: AbortSignal }): Promise<unknown>;
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
  readMission?: (
    request: MissionSelection & { signal: AbortSignal },
  ) => Promise<unknown>;
  readMissionV3?: (
    request: MissionSelection & { signal: AbortSignal },
  ) => Promise<unknown>;
  readPrograms?: ProgramRead;
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
}
export function bindMissionHost(
  client: RawClient,
  commandBinding?: unknown,
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
    async readPrograms({ signal }) {
      const started = epoch;
      check(signal, started);
      const raw = await client.readPrograms({ signal });
      check(signal, started);
      return decodeProgramsEnvelope(raw);
    },
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
    getState: () => ({ ...current }),
    invalidationGeneration: () => epoch,
    subscribe(listener) {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    async signIn() {
      invalidateReads();
      const ticket = ++control;
      const started = epoch;
      const result = await invoke("sign_in");
      if (ticket === control && started === epoch) update(result);
    },
    async signOut() {
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
