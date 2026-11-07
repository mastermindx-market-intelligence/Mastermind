import { attachProjectExecution } from "../planning/project-execution-command-port";
import type { ProjectExecutionTransport } from "../planning/project-execution-transport";
import {
  createExecutiveLaunchBinding,
  type ExecutiveToolEnvelope,
  type LaunchConfiguration,
} from "./executive-launch-command-port";
import type { OwnerContext, PendingPointerStore } from "./operation-controller";
import type { DirectNativeTransport, DirectSelection, DirectTerminalSelection } from "../direct-native-result";
import { DirectNativeCommandPort } from "./direct-native-command-port";
import { closedReadFailurePhase, type DiagnosticPhase, type ExecutiveDiagnosticSnapshot } from "../diagnostic-state";
import type { FreshConversationTransport } from "./fresh-conversation-transport";
import type { ProjectPlanningTransport } from "../planning/project-planning-transport";

/** Implemented inside the existing private web/Rust auth owner. No token getter. */
export interface OsExecutiveTransport {
  authGeneration(): number;
  available(): boolean;
  subscribe(listener: () => void): () => void;
  context(signal: AbortSignal): Promise<unknown>;
  companyPriorities?(signal: AbortSignal): Promise<unknown>;
  submit(arguments_: Readonly<Record<string, unknown>>, signal: AbortSignal): Promise<unknown>;
  status(arguments_: { readonly intent_id: string }, signal: AbortSignal): Promise<unknown>;
  /** Observer-only closed diagnostics; a snapshot read performs no native call. */
  diagnostics?(): ExecutiveDiagnosticSnapshot;
  readonly directNative?: DirectNativeTransport;
  readonly projectPlanning?: ProjectPlanningTransport;
  readonly projectExecution?: ProjectExecutionTransport;
  readonly freshConversation?: FreshConversationTransport;
}

interface VerifiedContext {
  readonly principalScope: string;
  readonly expiresAt: number;
}
const object = (value: unknown): value is Record<string, unknown> =>
  value !== null && typeof value === "object" && !Array.isArray(value);
const exact = (value: Record<string, unknown>, keys: readonly string[]) =>
  Object.keys(value).length === keys.length && keys.every((key) => Object.hasOwn(value, key));

/** Scope is accepted only from the authenticated, closed backend projection. */
export function decodeExecutiveContext(value: unknown, nowMs: number): VerifiedContext | null {
  if (!object(value) || !exact(value, ["schema", "principal_scope", "verified_expiry", "profile"]) ||
      value.schema !== "mastermind.os.executive.owner_context.v1" ||
      typeof value.principal_scope !== "string" || !/^[a-f0-9]{64}$/.test(value.principal_scope) ||
      typeof value.verified_expiry !== "number" || !Number.isSafeInteger(value.verified_expiry) ||
      value.verified_expiry <= nowMs / 1000 || !Number.isSafeInteger(value.verified_expiry * 1000) ||
      !object(value.profile) || !exact(value.profile, ["name", "server_version"]) ||
      value.profile.name !== "web_ceo_v3" ||
      (value.profile.server_version !== "1.4.0" && value.profile.server_version !== "1.5.0")) return null;
  return { principalScope: value.principal_scope, expiresAt: value.verified_expiry * 1000 };
}

/**
 * One mounted auth epoch owns context and receipt visibility. Binding is mounted
 * while signed out too, so later sign-in can qualify it without remounting App.
 * Auth events and expiry invalidate first; async replies can never restore an
 * older principal. Persistence and operation identity remain their existing owners.
 * The legacy Launch catalog is optional; project work and fresh conversations
 * use this same qualified context and pending-operation store without that catalog.
 */
export function createOsExecutiveHost(
  config: LaunchConfiguration | null,
  transport: OsExecutiveTransport,
  store: PendingPointerStore,
  now: () => number = Date.now,
) {
  let epoch = 0;
  let verified: VerifiedContext | null = null;
  let verifiedAuthGeneration: number | null = null;
  let disposed = false;
  let expiryTimer: ReturnType<typeof setTimeout> | undefined;
  let boundary = new AbortController();
  // Observer-only context diagnostics over existing refresh/expiry activity;
  // a snapshot read never calls context(), subscribes or mutates state.
  let contextPhase: DiagnosticPhase = "not_requested";
  const blockedPhase = (): DiagnosticPhase => {
    try {
      const native = transport.diagnostics?.();
      if (native && native.kind === "native" && native.authAvailable === false) return "auth_unavailable";
      return contextPhase === "not_requested" ? "not_requested" : "unknown";
    } catch { return "unknown"; }
  };
  const listeners = new Set<() => void>();
  const notify = () => { for (const listener of listeners) listener(); };
  const context = (): OwnerContext | null =>
    !disposed && verified && now() < verified.expiresAt && transport.available() &&
    verifiedAuthGeneration === transport.authGeneration()
      ? { principalScope: verified.principalScope, generation: String(epoch) }
      : null;

  function invalidate() {
    epoch++;
    verified = null;
    verifiedAuthGeneration = null;
    boundary.abort();
    boundary = new AbortController();
    clearTimeout(expiryTimer);
    expiryTimer = undefined;
    notify();
  }

  async function refresh() {
    invalidate();
    if (disposed || !transport.available()) {
      contextPhase = disposed ? "unknown" : blockedPhase();
      return;
    }
    const capturedEpoch = epoch;
    const authGeneration = transport.authGeneration();
    contextPhase = "pending"; // observed only at the existing context attempt
    const signal = boundary.signal;
    try {
      const raw = await transport.context(signal);
      if (disposed || signal.aborted || capturedEpoch !== epoch ||
          authGeneration !== transport.authGeneration() || !transport.available()) return;
      const decoded = decodeExecutiveContext(raw, now());
      if (!decoded) { contextPhase = "invalid_response"; return; }
      contextPhase = "ready";
      verified = decoded;
      verifiedAuthGeneration = authGeneration;
      // Very distant or malformed lifetimes cannot overflow a platform timer.
      expiryTimer = setTimeout(() => {
        if (capturedEpoch === epoch) {
          // The existing safety timer may be clamped before the actual expiry.
          contextPhase = now() >= decoded.expiresAt ? "expired" : "unknown";
          invalidate();
        }
      }, Math.min(decoded.expiresAt - now(), 2_147_483_647));
      notify();
    } catch (reason) {
      // No raw auth/transport error is exposed; the command remains unavailable.
      // Only a current, noncancelled rejection yields a phase; unknown stays unknown.
      if (!signal.aborted && !disposed && capturedEpoch === epoch &&
          authGeneration === transport.authGeneration() && transport.available())
        contextPhase = closedReadFailurePhase(reason);
    }
  }

  async function directCall(operation: "read" | "consume" | "correction", args: DirectSelection | Record<string,unknown> | (DirectTerminalSelection & {result_digest:string;operation_key:string}), signal: AbortSignal) {
    const owner=context(), capturedEpoch=epoch, authGeneration=transport.authGeneration();
    if(!owner||signal.aborted||!transport.directNative)throw Error("EXECUTIVE_UNAVAILABLE");
    const request=new AbortController(), boundarySignal=boundary.signal;
    const abort=()=>request.abort();signal.addEventListener("abort",abort,{once:true});boundarySignal.addEventListener("abort",abort,{once:true});
    if(signal.aborted||boundarySignal.aborted)abort();
    try {
      const raw=operation==="correction"?await transport.directNative.correction?.(args as Record<string,unknown>,request.signal):operation==="read"?await transport.directNative.read(args as DirectSelection,request.signal):
        await transport.directNative.consume(args as DirectTerminalSelection & {result_digest:string;operation_key:string},request.signal);
      const current=context();
      if(request.signal.aborted||capturedEpoch!==epoch||authGeneration!==transport.authGeneration()||!current||
        current.principalScope!==owner.principalScope||current.generation!==owner.generation)throw Error("EXECUTIVE_EPOCH_CHANGED");
      return raw;
    }finally{signal.removeEventListener("abort",abort);boundarySignal.removeEventListener("abort",abort);}
  }
  const direct = transport.directNative ? new DirectNativeCommandPort({
    correction:transport.directNative.correction?(args,signal)=>directCall("correction",args,signal):undefined,
    read:(args,signal)=>directCall("read",args,signal),consume:(args,signal)=>directCall("consume",args,signal),
  },context) : null;
  const launchBinding = createExecutiveLaunchBinding(config, {
    async callTool(name, args, signal): Promise<ExecutiveToolEnvelope> {
      const owner = context();
      const capturedEpoch = epoch;
      const authGeneration = transport.authGeneration();
      if (!owner || signal.aborted) throw new Error("EXECUTIVE_UNAVAILABLE");
      const request = new AbortController();
      const boundarySignal = boundary.signal;
      const abort = () => request.abort();
      signal.addEventListener("abort", abort, { once: true });
      boundarySignal.addEventListener("abort", abort, { once: true });
      if (signal.aborted || boundarySignal.aborted) abort();
      try {
        let raw: unknown;
        if (name === "submit_ceo_intent") raw = await transport.submit(args, request.signal);
        else {
          if (!exact(args as Record<string, unknown>, ["intent_id"]) || typeof args.intent_id !== "string")
            throw new Error("EXECUTIVE_ARGUMENTS_INVALID");
          raw = await transport.status({ intent_id: args.intent_id }, request.signal);
        }
        const current = context();
        if (request.signal.aborted || capturedEpoch !== epoch ||
            authGeneration !== transport.authGeneration() || !current ||
            current.principalScope !== owner.principalScope || current.generation !== owner.generation)
          throw new Error("EXECUTIVE_EPOCH_CHANGED");
        if (!object(raw) || typeof raw.ok !== "boolean") throw new Error("EXECUTIVE_RESPONSE_INVALID");
        // The existing launch port owns complete receipt/envelope decoding.
        return raw as unknown as ExecutiveToolEnvelope;
      } finally {
        signal.removeEventListener("abort", abort);
        boundarySignal.removeEventListener("abort", abort);
      }
    },
  }, {
    context,
    store,
    getSession: () => null, // LAUNCH has no SEND/STOP session producer.
    subscribe(listener) { listeners.add(listener); return () => { listeners.delete(listener); }; },
  }, direct ? {port:direct,capability:{read:(selection,signal)=>direct.read(selection,signal),
    inspectCorrection:(selection,signal)=>direct.inspectCorrection(selection,signal),makeCorrectionIntent:(selection,fence)=>direct.makeCorrectionIntent(selection,fence),
    makeConsumeIntent:(selection,digest)=>direct.makeConsumeIntent(selection,digest)}} : undefined);
  const binding = transport.projectExecution ? attachProjectExecution(launchBinding, {
    async request(operation, args, signal) {
      const owner = context(), capturedEpoch = epoch, authGeneration = transport.authGeneration();
      if (!owner || signal.aborted) throw Error("EXECUTIVE_UNAVAILABLE");
      const request = new AbortController(), boundarySignal = boundary.signal;
      const abort = () => request.abort();
      signal.addEventListener("abort", abort, {once:true}); boundarySignal.addEventListener("abort", abort, {once:true});
      if (signal.aborted || boundarySignal.aborted) abort();
      try {
        const raw = await transport.projectExecution!.request(operation,args,request.signal);
        const current = context();
        if (request.signal.aborted || capturedEpoch !== epoch || authGeneration !== transport.authGeneration() ||
            current?.principalScope !== owner.principalScope || current.generation !== owner.generation)
          throw Error("EXECUTIVE_EPOCH_CHANGED");
        return raw;
      } finally {signal.removeEventListener("abort",abort); boundarySignal.removeEventListener("abort",abort);}
    },
  }) : launchBinding;
  const unsubscribe = transport.subscribe(() => { void refresh(); });
  const ready = refresh();
  return {
    binding,
    ready,
    diagnostics: (): { contextPhase: DiagnosticPhase } => {
      try {
        if (disposed) return { contextPhase: "unknown" };
        if (verified && now() >= verified.expiresAt) return { contextPhase: "expired" };
        if (contextPhase === "ready" && !context()) return { contextPhase: blockedPhase() };
        return { contextPhase };
      } catch { return { contextPhase: "unknown" }; }
    },
    dispose() {
      if (disposed) return;
      disposed = true;
      contextPhase = "unknown";
      unsubscribe();
      invalidate();
      listeners.clear();
    },
  };
}
