import {
  createExecutiveSessionBinding,
  type ExecutiveSessionBinding,
  type ExecutiveSessionTransport,
  type QualifiedSessionAnswerRead,
} from "./executive-session-command-port";
import type { MissionSelection } from "../mission";
import type {
  FiniteCommandPort,
  PendingPointerStore,
  OperationPointer,
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
export type SessionCommandPort = FiniteCommandPort & {
  readonly currentTargetRef: () => string | null;
  readonly readOriginalReferences?: (selection: MissionSelection, signal: AbortSignal,
                                     cursor?: string) => Promise<unknown>;
  /** Existing native READ operation; optional only for older injected hosts. */
  readonly readQualifiedAnswer?: (pointer: OperationPointer, signal: AbortSignal) =>
    Promise<QualifiedSessionAnswerRead>;
};

export type MountedExecutiveSessionBinding = Omit<ExecutiveSessionBinding, "port"> & {
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
      readQualifiedAnswer: (pointer, signal) => original.readQualifiedAnswer(pointer, signal),
      readOriginalReferences: transport.references ? (selected, signal, cursor) => {
        const normalized = selected;
        const args = { work_ref: normalized.workRef, root_job_id: normalized.rootJobId,
                       page_size: 16, ...(cursor ? { cursor } : {}) };
        return transport.references!(args, signal);
      } : undefined,
      currentTargetRef: () => {
        const state = handle.sessionState();
        return state?.capabilities.send ? state.target?.target_ref ?? null : null;
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
  if (port.readQualifiedAnswer !== undefined && !isFn(port.readQualifiedAnswer)) return null;
  if (port.readOriginalReferences !== undefined && !isFn(port.readOriginalReferences)) return null;
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
