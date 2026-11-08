import {freshConversationArguments} from "./orchestration/fresh-conversation-transport";
import {projectConversationArguments} from './conversations/project-conversation-transport';
import { projectHistoryArguments } from "./orchestration/project-history-arguments";
import type { OsExecutiveTransport } from "./orchestration/os-executive-host";
import {
  normalizeExecutiveSessionSelection,
  sessionSelectionWire,
} from "./orchestration/executive-session-command-port";
import {sessionSendArguments} from "./orchestration/session-send-arguments";
import type { ProjectConversationHistoryTransport } from "./conversations/project-conversation-history-owner";
import { projectHistorySelection } from "./conversations/project-history-selection";
import { normalizeDirectSelection, type DirectNativeTransport } from "./direct-native-result";
import { closedReadFailureReason, type DiagnosticReadReason, type DiagnosticPhase, type ExecutiveDiagnosticSnapshot } from "./diagnostic-state";
import { planningArguments } from "./planning/project-planning-transport";
import { projectExecutionArguments } from "./planning/project-execution-transport";

type Invoke = <T>(command: string, args?: Record<string, unknown>) => Promise<T>;
type Listen = (event: string, listener: (event: { payload: unknown }) => void) => Promise<() => void>;
function status(raw: unknown): { generation: number; available: boolean } | null {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null;
  const value = raw as Record<string, unknown>;
  return Object.keys(value).sort().join(",") === "available,generation" &&
    Number.isSafeInteger(value.generation) && Number(value.generation) >= 0 && typeof value.available === "boolean"
    ? { generation: Number(value.generation), available: value.available } : null;
}

const WORK = /^WS:[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;
const ROOT = /^JOB-[A-Za-z0-9][A-Za-z0-9._:-]{0,250}$/;
const OPERATION = /^session-continue-[0-9a-f]{64}$/;
const CURSOR = /^[A-Za-z0-9_=-]{1,2048}$/;
/** Private native auth epoch; no token/claims enter the webview, no arbitrary native command. */
export async function createNativeExecutiveTransport(invoke: Invoke, listen: Listen) {
  let nativeGeneration = -1, epoch = 0, available = false;
  let contextReadReason: DiagnosticReadReason = "UNKNOWN";
  let generationAbort = new AbortController();
  const listeners = new Set<() => void>();
  const invalidate = (nextAvailable = false) => {
    epoch++; available = nextAvailable;
    contextReadReason = "UNKNOWN";
    const previous = generationAbort; generationAbort = new AbortController(); previous.abort();
    for (const listener of listeners) listener();
  };
  // A locally requested sign-in/out requires a later native auth generation.
  let minimumNativeGeneration = 0;
  // Observer-only diagnostics over the *existing* auth_status/listen outcomes.
  // No snapshot read invokes, subscribes, retries or notifies; unknown stays
  // unknown and a stale reply never resurrects an older observation.
  let observedAuth: boolean | null = null;
  let phase: DiagnosticPhase = "not_requested";
  const diagnostics = (): ExecutiveDiagnosticSnapshot =>
    ({ kind: "native", authAvailable: observedAuth, phase, contextReadReason });
  const update = (raw: unknown) => {
    const next = status(raw);
    if (!next) { phase = "invalid_response"; observedAuth = null; invalidate(); minimumNativeGeneration = nativeGeneration + 1; return; }
    if (next.generation < Math.max(nativeGeneration, minimumNativeGeneration)) return;
    // A duplicate authoritative reply still settles the diagnostic attempt;
    // it must not notify or change the original auth generation.
    phase = next.available ? "ready" : "auth_unavailable";
    observedAuth = next.available;
    if (next.generation === nativeGeneration && next.available === available) return;
    nativeGeneration = next.generation;
    invalidate(next.available);
  };
  let listening = false;
  try {
    await listen("mastermind-executive-auth-state", (event) => update(event.payload));
    listening = true;
  } catch {
    /* The read-only workspace remains usable without this optional capability. */
    phase = "transport_failure"; observedAuth = null;
  }
  const ready = (async () => {
    if (!listening) return;
    const started = epoch;
    try {
      phase = "pending"; // observed only at the existing executive_auth_status invocation
      const initial = await invoke("executive_auth_status");
      if (started === epoch) update(initial);
    } catch {
      /* Missing command remains unavailable. */
      if (started === epoch) { phase = "transport_failure"; observedAuth = null; }
    }
  })();

  function call(command: "read_company_priorities" | "executive_context" | "executive_submit" | "executive_status" |
    "executive_session_context" | "executive_session_send" | "executive_session_reply" | "executive_session_references" |
    "executive_project_session_references" |
    "executive_project_history_context" | "executive_fresh_conversation" | "executive_project_conversations_read" |
    "executive_direct_native_result" | "executive_direct_native_consume" | "executive_direct_correction" | "executive_project_planning" | "executive_project_execution",
    signal: AbortSignal, args?: Record<string, unknown>): Promise<unknown> {
    const started = epoch, boundary = generationAbort.signal;
    if (!available || signal.aborted) return Promise.reject(new Error("EXECUTIVE_UNAVAILABLE"));
    if (command === "executive_context") contextReadReason = "UNKNOWN";
    const observeContextFailure = (reason: unknown) => {
      // Observe only this existing READ, never mutation/status outcomes. Its
      // public rejection contract and authority checks stay unchanged.
      if (command === "executive_context" && started === epoch && !signal.aborted && !boundary.aborted)
        contextReadReason = closedReadFailureReason(reason);
    };
    return new Promise((resolve, reject) => {
      let settled = false;
      const finish = (failed: boolean, value: unknown) => {
        if (settled) return;
        settled = true; signal.removeEventListener("abort", abort); boundary.removeEventListener("abort", abort);
        failed ? reject(value) : resolve(value);
      };
      const abort = () => finish(true, new Error("EXECUTIVE_AUTH_CHANGED"));
      signal.addEventListener("abort", abort, { once: true }); boundary.addEventListener("abort", abort, { once: true });
      if (signal.aborted || boundary.aborted) { abort(); return; }
      try {
        Promise.resolve(invoke(command, args)).then((value) => {
          if (started !== epoch || !available || signal.aborted) abort(); else {
            if (command === "executive_context") contextReadReason = "NONE";
            finish(false, value);
          }
        }, (reason: unknown) => { observeContextFailure(reason); finish(true, new Error("EXECUTIVE_TRANSPORT_UNAVAILABLE")); });
      } catch (reason) { observeContextFailure(reason); finish(true, new Error("EXECUTIVE_TRANSPORT_UNAVAILABLE")); }
    });
  }
  const transport: OsExecutiveTransport & { directNative: DirectNativeTransport & {
    correction(request: Record<string, unknown>, signal: AbortSignal): Promise<unknown>;
  } } = {
    authGeneration: () => epoch, available: () => available,
    subscribe(listener) { listeners.add(listener); return () => { listeners.delete(listener); }; },
    diagnostics,
    context: (signal) => call("executive_context", signal),
    companyPriorities: (signal) => call("read_company_priorities", signal),
    submit: (arguments_, signal) => call("executive_submit", signal, { arguments: arguments_ }),
    status: (arguments_, signal) => call("executive_status", signal, { intentId: arguments_.intent_id }),
    projectPlanning: {request:(operation,arguments_,signal)=>call("executive_project_planning",signal,
      {operation,arguments:planningArguments(operation,arguments_)})},
    projectExecution: {request:(operation,arguments_,signal)=>call("executive_project_execution",signal,
      {operation,arguments:projectExecutionArguments(operation,arguments_)})},
    freshConversation: {request:(operation,arguments_,signal,contract)=>call("executive_fresh_conversation",signal,
      {operation,arguments:freshConversationArguments(operation,arguments_,contract),...(contract?{contract}:{})})},
    directNative: {
      read: (selection, signal) => {
        const normalized = normalizeDirectSelection(selection);
        if (!normalized) return Promise.reject(new Error("DIRECT_SELECTION_INVALID"));
        return call("executive_direct_native_result", signal, { arguments: normalized });
      },
      consume: (request, signal) => {
        if (!request || typeof request !== "object" || Array.isArray(request) ||
            ![Object.prototype, null].includes(Object.getPrototypeOf(request)) ||
            Object.keys(request).sort().join(",") !== "attempt_id,job_id,operation_key,result_digest,work_ref")
          return Promise.reject(new Error("DIRECT_SELECTION_INVALID"));
        const { result_digest, operation_key, ...selection } = request;
        const normalized = normalizeDirectSelection(selection);
        if (!normalized || normalized.attempt_id === null ||
            typeof result_digest !== "string" || !/^[a-f0-9]{64}$/.test(result_digest) ||
            typeof operation_key !== "string" || !/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(operation_key))
          return Promise.reject(new Error("DIRECT_SELECTION_INVALID"));
        return call("executive_direct_native_consume", signal, {
          arguments: { ...normalized, result_digest, operation_key },
        });
      },
      correction: (request, signal) => {
        if (!request || typeof request !== "object" || Array.isArray(request) ||
            ![Object.prototype, null].includes(Object.getPrototypeOf(request)))
          return Promise.reject(new Error("DIRECT_SELECTION_INVALID"));
        const mutation = request.operation === "request";
        const keys = mutation ? "attempt_id,fence_generation,job_id,operation,operation_key,work_ref"
          : "attempt_id,job_id,operation,work_ref";
        if ((!mutation && request.operation !== "inspect") || Object.keys(request).sort().join(",") !== keys)
          return Promise.reject(new Error("DIRECT_SELECTION_INVALID"));
        const selected = normalizeDirectSelection({ work_ref: request.work_ref,
          job_id: request.job_id, attempt_id: request.attempt_id });
        if (!selected || (mutation && (selected.attempt_id === null ||
            !Number.isSafeInteger(request.fence_generation) || Number(request.fence_generation) < 1 ||
            typeof request.operation_key !== "string" || !/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(request.operation_key))))
          return Promise.reject(new Error("DIRECT_SELECTION_INVALID"));
        return call("executive_direct_correction", signal, {
          arguments: { ...selected, operation: request.operation,
            ...(mutation ? { fence_generation: request.fence_generation, operation_key: request.operation_key } : {}) },
        });
      },
    },
  };
  // History and qualified Fabric/Secretary continuations reuse the same
  // native bearer owner, fixed SEND command and auth epoch.
  // The independent executive_submit F2 review remains unchanged.
  const sessionTransport: ProjectConversationHistoryTransport = {
    projectConversations: {request: (operation,arguments_,signal) => {
      const closed=projectConversationArguments(operation,arguments_);
      return closed ? call('executive_project_conversations_read',signal,{operation,arguments:closed})
        : Promise.reject(new Error('PROJECT_CONVERSATION_SELECTION_INVALID'));
    }},
    authGeneration: () => epoch, available: () => available,
    subscribe(listener) { listeners.add(listener); return () => { listeners.delete(listener); }; },
    historyContext: (selection, signal) => {
      const closed = projectHistorySelection(selection);
      return closed ? call("executive_project_history_context", signal, {workRef: closed.workRef})
        : Promise.reject(new Error("SESSION_HISTORY_SELECTION_INVALID"));
    },
    context: async (selection, signal) => {
      const normalized = normalizeExecutiveSessionSelection(selection);
      if (!normalized) throw new Error("SESSION_SELECTION_INVALID");
      // The Session owner validates the returned target and capability.
      return call("executive_session_context", signal, {
        selection: sessionSelectionWire(normalized),
      });
    },
    reply: (args, signal) => OPERATION.test(args.operation_key)
      ? call("executive_session_reply", signal, { operationKey: args.operation_key })
      : Promise.reject(new Error("SESSION_OPERATION_INVALID")),
    projectReferences: (args, signal) => {
      const closed = projectHistoryArguments(args);
      if (!closed) return Promise.reject(new Error("SESSION_REFERENCES_INVALID"));
      return call("executive_project_session_references", signal, {
        workRef: closed.work_ref, ...(closed.cursor !== undefined ? { cursor: closed.cursor } : {}),
      });
    },
    references: (args, signal) => {
      if (!WORK.test(args.work_ref) || !ROOT.test(args.root_job_id) ||
          (args.page_size !== undefined && (!Number.isSafeInteger(args.page_size) ||
            args.page_size < 1 || args.page_size > 32)) ||
          (args.cursor !== undefined && !CURSOR.test(args.cursor)))
        return Promise.reject(new Error("SESSION_REFERENCES_INVALID"));
      return call("executive_session_references", signal, {
        selection: { work_ref: args.work_ref, root_job_id: args.root_job_id },
        pageSize: args.page_size ?? 16,
        ...(args.cursor ? { cursor: args.cursor } : {}),
      });
    },
    send: (arguments_,signal) => {
      const closed=sessionSendArguments(arguments_);
      return closed?call("executive_session_send",signal,{arguments:closed})
        :Promise.reject(new Error("SESSION_SEND_INVALID"));
    },
  };
  return { transport, sessionTransport, ready,
    invalidate() {
      // A locally requested sign-in/out resets diagnostics to unknown without
      // changing availability or epoch semantics.
      minimumNativeGeneration = nativeGeneration + 1;
      phase = "not_requested"; observedAuth = null;
      invalidate();
    } };
}
