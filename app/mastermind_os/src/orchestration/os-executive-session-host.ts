import {
  createExecutiveSessionBinding,
  type ExecutiveSessionBinding,
  type ExecutiveSessionTransport,
} from "./executive-session-command-port";
import type { MissionSelection } from "../mission";
import type {
  FiniteCommandPort,
  PendingPointerStore,
} from "./operation-controller";

/**
 * Session capability/controller lifecycle, composed separately from the
 * Launch host. The mounted binding exists independently of any Launch
 * catalog: it re-qualifies only through the authenticated session context
 * envelope, so absent Executive configuration/auth keeps the capability
 * unavailable and sends no requests. Selection changes are pushed in by the
 * app shell on every transition (including initial, clear, same-value and
 * A→B→A); each push invalidates first, so a stale context reply can never
 * re-qualify an abandoned selection.
 */
/**
 * The session port is the existing FiniteCommandPort plus the host-projected
 * target read the UI presents truthfully. The getter is observation only:
 * it never mints, selects or looks up a target.
 */
/** Read-only original-owner correlation, never a DSH or company-session ID. */
export interface CurrentExecutiveSessionObservation {
  readonly targetRef: string;
  readonly selection: MissionSelection;
  readonly principalScope: string;
  readonly generation: string;
}
export type SessionCommandPort = FiniteCommandPort & {
  readonly currentTargetRef: () => string | null;
  /** Optional for old mounts; absence cannot be treated as a bound session. */
  readonly currentObservation?: () => CurrentExecutiveSessionObservation | null;
};

export type MountedExecutiveSessionBinding = ExecutiveSessionBinding & {
  readonly port: SessionCommandPort;
};

export interface OsExecutiveSessionHost {
  readonly binding: MountedExecutiveSessionBinding;
  readonly ready: Promise<void>;
  /** Push the exact current selection; invalidates before any re-read. */
  refresh(selection: MissionSelection | null): Promise<void>;
  /** Register the explicit synchronous completion-condition provider. */
  setStopCondition(provider: () => unknown): void;
  dispose(): void;
}

export function createOsExecutiveSessionHost(
  transport: ExecutiveSessionTransport,
  store: PendingPointerStore,
): OsExecutiveSessionHost {
  let selection: MissionSelection | null = null;
  let stopCondition: () => unknown = () => undefined;
  const handle = createExecutiveSessionBinding({
    transport,
    store,
    selection: () => selection,
    stopCondition: () => stopCondition(),
  });
  const original = handle.binding.port;
  const binding: MountedExecutiveSessionBinding = {
    ...handle.binding,
    port: {
      context: () => original.context(),
      prepare: (intent) => original.prepare(intent),
      submit: (pointer, intent, signal) => original.submit(pointer, intent, signal),
      readOperation: (pointer, signal) => original.readOperation(pointer, signal),
      currentTargetRef: () => {
        const state = handle.sessionState();
        return state?.capabilities.send ? state.target?.target_ref ?? null : null;
      },
      currentObservation: () => {
        // SessionState is the existing canonical response, decoded against the
        // exact refresh selection and owner epoch. Do not infer association
        // from a target digest or the visible session title alone.
        const state = handle.sessionState();
        const owner = original.context();
        if (!state || state.selectionState !== "RESOLVED" ||
            !state.capabilities.send || !state.target || !owner ||
            state.principalScope !== owner.principalScope) return null;
        return {
          targetRef: state.target.target_ref,
          selection: { ...state.selection },
          principalScope: owner.principalScope,
          generation: owner.generation,
        };
      },
    },
  };
  return {
    binding,
    ready: handle.ready,
    refresh(next) {
      selection = next ? { workRef: next.workRef, rootJobId: next.rootJobId } : null;
      return handle.refresh();
    },
    setStopCondition(provider) {
      stopCondition = provider;
    },
    dispose() {
      handle.dispose();
      stopCondition = () => undefined;
    },
  };
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isFn(value: unknown): value is (...args: never[]) => unknown {
  return typeof value === "function";
}

function nonEmptyString(value: unknown): value is string {
  return typeof value === "string" && value.length > 0;
}

/**
 * Closed shape check for the separately mounted session binding. Mirrors
 * completeOrchestratorCommandBinding and additionally requires the explicit
 * three-argument message entry; bindings that expose store write/clear
 * aliases are refused exactly as the launch check refuses them.
 */
export function completeExecutiveSessionBinding(
  value: unknown,
): MountedExecutiveSessionBinding | null {
  if (!isPlainObject(value)) return null;
  const port = value.port;
  const store = value.store;
  if (!isPlainObject(port) || !isPlainObject(store)) return null;
  if (
    !isFn(port.context) ||
    !isFn(port.prepare) ||
    !isFn(port.submit) ||
    !isFn(port.readOperation) ||
    !isFn((port as Record<string, unknown>).currentTargetRef)
  )
    return null;
  if (
    !isFn(store.read) ||
    !isFn(store.reserve) ||
    !isFn(store.clearIfEqual)
  )
    return null;
  if ("currentObservation" in port && !isFn(port.currentObservation)) return null;
  if (isFn((store as Record<string, unknown>).write)) return null;
  if (isFn((store as Record<string, unknown>).clear)) return null;
  if (
    !isFn(value.getView) ||
    !isFn(value.subscribe) ||
    !isFn(value.makeLaunchIntent) ||
    !isFn(value.makeMessageIntent) ||
    !isFn(value.makeStopIntent) ||
    !isFn(value.makeSessionMessageIntent)
  )
    return null;
  return value as unknown as MountedExecutiveSessionBinding;
}

/** The owner context this binding reports, fenced against throwing ports. */
export function readSessionOwnerContext(
  binding: MountedExecutiveSessionBinding,
): { principalScope: string; generation: string } | null {
  try {
    const ctx = binding.port.context();
    if (!isPlainObject(ctx)) return null;
    if (!nonEmptyString(ctx.principalScope) || !nonEmptyString(ctx.generation)) return null;
    return { principalScope: ctx.principalScope, generation: ctx.generation };
  } catch {
    return null;
  }
}
