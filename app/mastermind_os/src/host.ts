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

export interface AuthState {
  status: "unconfigured" | "signed_out" | "signing_in" | "signed_in" | "error";
  reason: string | null;
  acquisition: boolean;
  content: boolean;
}
export interface RawClient {
  getState(): AuthState;
  subscribe(listener: (state: AuthState) => void): () => void;
  signIn(): Promise<unknown>;
  signOut(): Promise<unknown>;
  readPrograms(request: { signal: AbortSignal }): Promise<unknown>;
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
 * fully decoded frozen DTO, or throws. The typed allowed 503 body is not a
 * separate wrapper kind — it is the validated
 * `mastermind.workspace_role_result.v1` envelope with availability
 * "UNAVAILABLE", preserved whole (reason_codes included) for the consumer
 * render path. The exact five selector fields stay separate from the
 * AbortSignal, which is an option, never part of the selector.
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
  readResult?: MissionResultRead;
  readCurrentWindow?: (request: {
    signal: AbortSignal;
  }) => Promise<WindowDocument>;
  selection?: unknown;
  auth?: Pick<RawClient, "getState" | "subscribe" | "signIn" | "signOut">;
}
export function bindMissionHost(client: RawClient): MissionHost {
  let epoch = 0;
  let previous = JSON.stringify(client.getState());
  client.subscribe((state) => {
    const next = JSON.stringify(state);
    if (next !== previous) {
      epoch++;
      previous = next;
    }
  });
  const check = (signal: AbortSignal, started: number) => {
    if (signal.aborted || started !== epoch) throw new Error("READ_CANCELLED");
  };
  return {
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
  let control = 0;
  const update = (raw: unknown) => {
    current = authState(raw);
    epoch++;
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
      | "read_mission"
      | "read_mission_v3"
      | "read_result"
      | "read_current_window",
    signal: AbortSignal,
    args?: Record<string, unknown>,
  ) {
    const started = epoch;
    if (signal.aborted) throw new Error("READ_CANCELLED");
    const raw = await invoke(command, args);
    if (signal.aborted || started !== epoch) throw new Error("READ_CANCELLED");
    return raw;
  }
  return {
    getState: () => ({ ...current }),
    subscribe(listener) {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    async signIn() {
      epoch++;
      const ticket = ++control;
      const result = await invoke("sign_in");
      if (ticket === control) update(result);
    },
    async signOut() {
      const ticket = ++control;
      update({
        status: "signed_out",
        reason: null,
        acquisition: false,
        content: false,
      });
      const result = await invoke("sign_out");
      if (ticket === control) update(result);
    },
    readPrograms: ({ signal }) => read("read_programs", signal),
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
