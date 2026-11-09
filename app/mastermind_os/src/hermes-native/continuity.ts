/** Typed conversation continuity for the #2180 native Hermes path.

Separates WHY a bot conversation is not progressing — viewer disconnected,
gateway busy, model 429/quota, native terminal, or effect-unknown — instead of
collapsing them into one "error". Each state names the exact permitted
continuation, and the rules are closed:

  * an effect-unknown mutation is NEVER re-sent: the only continuation is the
    idempotent `recover` operation, which the port expands with the ORIGINAL
    operation key (requestId + sessionId) from the durable pending pointer;
  * reopen/recover attaches to the SAME native session — a recovery never
    mints a session or a fresh request id;
  * a fresh `send` is legal only from `idle`;
  * stop/steer are not exposed by the native producer (the gateway owns
    prompt.cancel/prompt.steer_queued/session.interrupt; this port wires none
    of them), so no state offers them.
*/
import type { AdmissionState, ContinuationFailureReason, NativeOperation, NativeView } from "./contract";
import type { NativePendingOperation } from "./pending-pointer";

export type GatewayBusyReason = "session_busy" | "prompt_pending" | "port_busy";
export type ViewerDisconnectDetail = "host_interrupted" | "client_unavailable" | "platform_unavailable";
export type ModelLimitedReason = "provider_rate_limit" | "provider_quota_limit";

export type BotContinuity =
  | { kind: "idle"; sessionId: string }
  | { kind: "turn_running"; sessionId: string; admissionId: string; status: AdmissionState }
  | { kind: "native_terminal"; sessionId: string; admissionId: string; outcome: string; failureReason?: ContinuationFailureReason }
  | { kind: "model_limited"; sessionId: string; admissionId: string; failureReason: ModelLimitedReason; retryPolicy: "never_auto" }
  | { kind: "gateway_busy"; sessionId: string | null; reason: GatewayBusyReason }
  | { kind: "viewer_disconnected"; sessionId: string | null; detail: ViewerDisconnectDetail }
  | { kind: "auth_changed" }
  | { kind: "effect_unknown"; pending: NativePendingOperation }
  | { kind: "unclassified"; code: string };

export interface ContinuityInput {
  view?: NativeView | null;
  error?: { message?: string } | null;
  pending?: NativePendingOperation | null;
}

/** Stop/steer honesty: the gateway has these verbs; the native port does not
 * wire them, so no continuity state may offer an intervention. */
export const interventions = {
  stop: "not_exposed_by_native_port",
  steer: "not_exposed_by_native_port",
} as const;

const busyCodes: Record<string, GatewayBusyReason> = {
  NATIVE_SESSION_BUSY: "session_busy",
  NATIVE_PROMPT_PENDING: "prompt_pending",
  NATIVE_BUSY: "port_busy",
};
const viewerCodes: Record<string, ViewerDisconnectDetail> = {
  NATIVE_CLIENT_INTERRUPTED: "host_interrupted",
  NATIVE_CLIENT_UNAVAILABLE: "client_unavailable",
  NATIVE_PIPE_UNAVAILABLE: "client_unavailable",
  NATIVE_PLATFORM_UNAVAILABLE: "platform_unavailable",
};
const modelLimited: ReadonlySet<string> = new Set(["provider_rate_limit", "provider_quota_limit"]);

function fromError(code: string, pending: NativePendingOperation | null | undefined): BotContinuity {
  if (code in busyCodes) return { kind: "gateway_busy", sessionId: null, reason: busyCodes[code] };
  if (code in viewerCodes) return { kind: "viewer_disconnected", sessionId: null, detail: viewerCodes[code] };
  if (code === "AUTHENTICATION_CHANGED" || code === "NATIVE_AUTH_NOT_DISPATCHED") return { kind: "auth_changed" };
  if (pending) return { kind: "effect_unknown", pending };
  return { kind: "unclassified", code };
}

function fromSession(view: NativeView): BotContinuity {
  const session = view.session!;
  if (session.pending.length > 0) {
    const last = session.pending[session.pending.length - 1];
    return { kind: "turn_running", sessionId: session.id, admissionId: last.id, status: last.status };
  }
  if (session.running === true) {
    return { kind: "turn_running", sessionId: session.id, admissionId: "", status: "started" };
  }
  if (session.promptsPending === true) {
    return { kind: "gateway_busy", sessionId: session.id, reason: "prompt_pending" };
  }
  return { kind: "idle", sessionId: session.id };
}

export function classifyContinuity(input: ContinuityInput): BotContinuity {
  const pending = input.pending ?? input.view?.pendingOperation ?? null;
  const code = input.error?.message ?? null;
  if (code !== null) return fromError(code, pending);
  const view = input.view ?? null;
  if (view === null) {
    if (pending) return { kind: "effect_unknown", pending };
    return { kind: "unclassified", code: "NO_OBSERVATION" };
  }
  if (view.state === "EFFECT_UNKNOWN") {
    return pending ? { kind: "effect_unknown", pending }
      : { kind: "unclassified", code: view.code ?? "EFFECT_UNKNOWN_WITHOUT_POINTER" };
  }
  if (view.state === "REFUSED") {
    if (view.code && view.code in busyCodes) {
      return { kind: "gateway_busy", sessionId: view.session?.id ?? null, reason: busyCodes[view.code] };
    }
    return { kind: "unclassified", code: view.code ?? "REFUSED" };
  }
  if (view.state === "ADMITTED" && view.receipt) {
    const receipt = view.receipt;
    if (receipt.status === "terminal") {
      if (receipt.outcome === "failed" && receipt.failureReason
          && modelLimited.has(receipt.failureReason)) {
        return { kind: "model_limited", sessionId: receipt.sessionId, admissionId: receipt.id,
          failureReason: receipt.failureReason as ModelLimitedReason, retryPolicy: "never_auto" };
      }
      return { kind: "native_terminal", sessionId: receipt.sessionId, admissionId: receipt.id,
        outcome: receipt.outcome ?? "", ...(receipt.failureReason ? { failureReason: receipt.failureReason } : {}) };
    }
    return { kind: "turn_running", sessionId: receipt.sessionId, admissionId: receipt.id, status: receipt.status };
  }
  if (view.state === "NOT_SENT" || view.state === "UNAVAILABLE") {
    const detail = view.code === "NATIVE_CLIENT_INTERRUPTED" ? "host_interrupted" : "client_unavailable";
    return { kind: "viewer_disconnected", sessionId: view.session?.id ?? null, detail };
  }
  if ((view.state === "OPENED" || view.state === "READY") && view.session) return fromSession(view);
  return { kind: "unclassified", code: view.code ?? view.state };
}

export interface Continuation { operation: NativeOperation; why: string }

export function permittedContinuations(state: BotContinuity): Continuation[] {
  switch (state.kind) {
    case "effect_unknown":
      // The port expands `recover` with the ORIGINAL request id and session id
      // from the durable pointer: the idempotent replay of the original send,
      // never a second submission and never a new session.
      return [{ operation: { operation: "recover" },
        why: "idempotent recovery of the original request by its operation key" }];
    case "model_limited":
      return [{ operation: { operation: "read", sessionId: state.sessionId },
        why: "quota/rate limit: wait for the reset window; never an automatic retry or account switch" }];
    case "gateway_busy":
      return state.sessionId
        ? [{ operation: { operation: "read", sessionId: state.sessionId },
            why: "the gateway owns the turn; re-read when it clears instead of queueing another" }]
        : [{ operation: { operation: "status" }, why: "the port is busy; re-observe before any mutation" }];
    case "viewer_disconnected":
      return state.sessionId
        ? [{ operation: { operation: "read", sessionId: state.sessionId },
            why: "only the viewer attachment was lost; the native session is unchanged" }]
        : [{ operation: { operation: "status" }, why: "re-observe the native runtime" }];
    case "native_terminal":
      return [{ operation: { operation: "read", sessionId: state.sessionId },
        why: "the turn finished; read retained history on the same session" }];
    case "turn_running":
      return [{ operation: { operation: "read", sessionId: state.sessionId },
        why: "the turn is running on the same admission; no stop or steer is exposed by this port" }];
    case "idle":
      // A fresh send is legal here (see freshSendAllowed); the UI mints the
      // new request id at send time, so this list carries only the safe read.
      return [{ operation: { operation: "read", sessionId: state.sessionId },
        why: "the session is idle; a fresh send needs a newly minted request id" }];
    case "auth_changed":
    case "unclassified":
      return [];
  }
}

/** The only state in which the UI may offer a fresh send. */
export function freshSendAllowed(state: BotContinuity): boolean {
  return state.kind === "idle";
}
