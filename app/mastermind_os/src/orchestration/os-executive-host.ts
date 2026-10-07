import {
  createExecutiveLaunchBinding,
  type ExecutiveToolEnvelope,
  type LaunchBindingConfig,
} from "./executive-launch-command-port";
import type { OwnerContext, PendingPointerStore } from "./operation-controller";

/** Implemented inside the existing private web/Rust auth owner. No token getter. */
export interface OsExecutiveTransport {
  authGeneration(): number;
  available(): boolean;
  subscribe(listener: () => void): () => void;
  context(signal: AbortSignal): Promise<unknown>;
  submit(arguments_: Readonly<Record<string, unknown>>, signal: AbortSignal): Promise<unknown>;
  status(arguments_: { readonly intent_id: string }, signal: AbortSignal): Promise<unknown>;
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
 */
export function createOsExecutiveHost(
  config: LaunchBindingConfig,
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
    if (disposed || !transport.available()) return;
    const capturedEpoch = epoch;
    const authGeneration = transport.authGeneration();
    const signal = boundary.signal;
    try {
      const raw = await transport.context(signal);
      if (disposed || signal.aborted || capturedEpoch !== epoch ||
          authGeneration !== transport.authGeneration() || !transport.available()) return;
      const decoded = decodeExecutiveContext(raw, now());
      if (!decoded) return;
      verified = decoded;
      verifiedAuthGeneration = authGeneration;
      // Very distant or malformed lifetimes cannot overflow a platform timer.
      expiryTimer = setTimeout(() => {
        if (capturedEpoch === epoch) invalidate();
      }, Math.min(decoded.expiresAt - now(), 2_147_483_647));
      notify();
    } catch {
      // No raw auth/transport error is exposed; the command remains unavailable.
    }
  }

  const binding = createExecutiveLaunchBinding(config, {
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
  });
  const unsubscribe = transport.subscribe(() => { void refresh(); });
  const ready = refresh();
  return {
    binding,
    ready,
    dispose() {
      if (disposed) return;
      disposed = true;
      unsubscribe();
      invalidate();
      listeners.clear();
    },
  };
}
