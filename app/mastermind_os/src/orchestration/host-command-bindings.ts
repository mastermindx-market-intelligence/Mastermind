import { normalizeSelection, type MissionSelection } from "../mission";
import type {
  CommandIntent,
  FiniteCommandPort,
  OperationKind,
  OwnerContext,
  PendingPointerStore,
} from "./operation-controller";
import type { LaunchChoice, LaunchForm } from "./ui/LaunchOrchestrator";
import type {
  SessionMessage,
  SessionWorkspaceProps,
} from "./ui/SessionWorkspace";

/** Fixed local reason when the injected command route is absent or unusable. */
export const COMMAND_ROUTE_UNAVAILABLE = "COMMAND_ROUTE_UNAVAILABLE";

const CONNECTION = new Set(["connected", "disconnected", "unknown"]);
const STOP_LABELS = new Set(["Interrupt turn", "Request stop"]);
const MESSAGE_ROLES = new Set(["user", "assistant", "activity"]);

export interface OrchestratorSessionPresentation {
  readonly sessionKey: string;
  readonly title: string;
  readonly messages: readonly SessionMessage[];
  readonly observedAt: string | null;
  readonly connection: SessionWorkspaceProps["connection"];
  readonly coverage: string;
  readonly turnBusy: boolean;
  readonly unavailableReason?: string;
  readonly error?: string;
  readonly stopLabel?: SessionWorkspaceProps["stopLabel"];
  readonly selection: MissionSelection;
}

export interface OrchestratorCommandView {
  readonly projects: readonly LaunchChoice[];
  readonly profiles: readonly LaunchChoice[];
  readonly session: OrchestratorSessionPresentation | null;
}

/**
 * Owner-injected command capability. Completeness is a closed shape check:
 * there are no catalog, provider, or programs-derived defaults.
 */
export interface OrchestratorCommandBinding {
  readonly port: FiniteCommandPort;
  readonly store: PendingPointerStore;
  getView(): OrchestratorCommandView;
  subscribe(listener: () => void): () => void;
  makeLaunchIntent(form: LaunchForm): CommandIntent | null;
  makeMessageIntent(sessionKey: string, text: string): CommandIntent | null;
  makeStopIntent(sessionKey: string): CommandIntent | null;
}

function isPlainObject(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

function isFn(v: unknown): v is (...args: never[]) => unknown {
  return typeof v === "function";
}

function nonEmptyString(v: unknown): v is string {
  return typeof v === "string" && v.length > 0;
}

/** Shape-only. Does not call port/store/view/mappers. */
export function completeOrchestratorCommandBinding(
  value: unknown,
): OrchestratorCommandBinding | null {
  if (!isPlainObject(value)) return null;
  const port = value.port;
  const store = value.store;
  if (!isPlainObject(port) || !isPlainObject(store)) return null;
  if (
    !isFn(port.context) ||
    !isFn(port.prepare) ||
    !isFn(port.submit) ||
    !isFn(port.readOperation)
  )
    return null;
  if (!isFn(store.read) || !isFn(store.write) || !isFn(store.clear))
    return null;
  if (
    !isFn(value.getView) ||
    !isFn(value.subscribe) ||
    !isFn(value.makeLaunchIntent) ||
    !isFn(value.makeMessageIntent) ||
    !isFn(value.makeStopIntent)
  )
    return null;
  return value as unknown as OrchestratorCommandBinding;
}

export function readOwnerContext(port: unknown): OwnerContext | null {
  try {
    if (!isPlainObject(port) || !isFn(port.context)) return null;
    const ctx = port.context();
    if (!isPlainObject(ctx)) return null;
    if (!nonEmptyString(ctx.principalScope) || !nonEmptyString(ctx.generation))
      return null;
    return {
      principalScope: ctx.principalScope,
      generation: ctx.generation,
    };
  } catch {
    return null;
  }
}

function asChoice(v: unknown): LaunchChoice | null {
  if (!isPlainObject(v) || !nonEmptyString(v.ref) || typeof v.label !== "string")
    return null;
  const choice: LaunchChoice = { ref: v.ref, label: v.label };
  if (v.unavailableReason !== undefined) {
    if (typeof v.unavailableReason !== "string") return null;
    choice.unavailableReason = v.unavailableReason;
  }
  return choice;
}

function asMessage(v: unknown): SessionMessage | null {
  if (!isPlainObject(v)) return null;
  if (!nonEmptyString(v.id) || typeof v.text !== "string") return null;
  if (typeof v.role !== "string" || !MESSAGE_ROLES.has(v.role)) return null;
  return { id: v.id, role: v.role as SessionMessage["role"], text: v.text };
}

function asSession(v: unknown): OrchestratorSessionPresentation | null {
  if (!isPlainObject(v)) return null;
  if (!nonEmptyString(v.sessionKey) || typeof v.title !== "string") return null;
  if (typeof v.coverage !== "string") return null;
  if (typeof v.turnBusy !== "boolean") return null;
  if (typeof v.connection !== "string" || !CONNECTION.has(v.connection))
    return null;
  if (v.observedAt !== null && typeof v.observedAt !== "string") return null;
  if (!Array.isArray(v.messages)) return null;
  const selection = normalizeSelection(v.selection);
  if (!selection) return null;
  const messages: SessionMessage[] = [];
  for (const item of v.messages) {
    const message = asMessage(item);
    if (!message) return null;
    messages.push(message);
  }
  if (v.unavailableReason !== undefined && typeof v.unavailableReason !== "string")
    return null;
  if (v.error !== undefined && typeof v.error !== "string") return null;
  if (
    v.stopLabel !== undefined &&
    (typeof v.stopLabel !== "string" || !STOP_LABELS.has(v.stopLabel))
  )
    return null;
  return {
    sessionKey: v.sessionKey,
    title: v.title,
    messages,
    observedAt: v.observedAt,
    connection: v.connection as SessionWorkspaceProps["connection"],
    coverage: v.coverage,
    turnBusy: v.turnBusy,
    selection,
    ...(typeof v.unavailableReason === "string"
      ? { unavailableReason: v.unavailableReason }
      : {}),
    ...(typeof v.error === "string" ? { error: v.error } : {}),
    ...(typeof v.stopLabel === "string"
      ? { stopLabel: v.stopLabel as SessionWorkspaceProps["stopLabel"] }
      : {}),
  };
}

const EMPTY_VIEW: OrchestratorCommandView = {
  projects: [],
  profiles: [],
  session: null,
};

export function readCommandView(
  binding: OrchestratorCommandBinding,
): OrchestratorCommandView {
  try {
    const raw = binding.getView();
    if (!isPlainObject(raw) || !Array.isArray(raw.projects) || !Array.isArray(raw.profiles))
      return EMPTY_VIEW;
    const projects: LaunchChoice[] = [];
    for (const item of raw.projects) {
      const choice = asChoice(item);
      if (!choice) return EMPTY_VIEW;
      projects.push(choice);
    }
    const profiles: LaunchChoice[] = [];
    for (const item of raw.profiles) {
      const choice = asChoice(item);
      if (!choice) return EMPTY_VIEW;
      profiles.push(choice);
    }
    const session =
      raw.session === null || raw.session === undefined
        ? null
        : asSession(raw.session);
    if (raw.session != null && session === null) return EMPTY_VIEW;
    return { projects, profiles, session };
  } catch {
    return EMPTY_VIEW;
  }
}

export function sessionMatchesSelection(
  session: OrchestratorSessionPresentation | null,
  selection: MissionSelection | null,
): boolean {
  if (!session || !selection) return false;
  const current = normalizeSelection(selection);
  if (!current) return false;
  return (
    session.selection.workRef === current.workRef &&
    session.selection.rootJobId === current.rootJobId
  );
}

export function intentMatchingKind(
  intent: unknown,
  kind: OperationKind,
): CommandIntent | null {
  if (!isPlainObject(intent)) return null;
  if (intent.kind !== kind) return null;
  if (!isPlainObject(intent.payload)) return null;
  if (intent.targetKey !== null && typeof intent.targetKey !== "string")
    return null;
  if (intent.targetKey !== null && intent.targetKey.length === 0) return null;
  return {
    kind,
    payload: intent.payload,
    targetKey: intent.targetKey === null ? null : intent.targetKey,
  };
}

export function launchIntentFromBinding(
  binding: OrchestratorCommandBinding,
  form: LaunchForm,
): CommandIntent | null {
  try {
    return intentMatchingKind(binding.makeLaunchIntent(form), "launch");
  } catch {
    return null;
  }
}

export function messageIntentFromBinding(
  binding: OrchestratorCommandBinding,
  sessionKey: string,
  text: string,
): CommandIntent | null {
  try {
    return intentMatchingKind(
      binding.makeMessageIntent(sessionKey, text),
      "message",
    );
  } catch {
    return null;
  }
}

export function stopIntentFromBinding(
  binding: OrchestratorCommandBinding,
  sessionKey: string,
): CommandIntent | null {
  try {
    return intentMatchingKind(binding.makeStopIntent(sessionKey), "stop");
  } catch {
    return null;
  }
}

export function subscribeCommandView(
  binding: OrchestratorCommandBinding,
  listener: () => void,
): () => void {
  try {
    const unsubscribe = binding.subscribe(listener);
    return typeof unsubscribe === "function" ? unsubscribe : () => {};
  } catch {
    return () => {};
  }
}
