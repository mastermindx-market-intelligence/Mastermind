import type { LaunchChoice, LaunchForm } from "./ui/LaunchOrchestrator";
import type {
  CommandIntent,
  EffectReceipt,
  FiniteCommandPort,
  OperationPointer,
  OwnerContext,
  PendingPointerStore,
} from "./operation-controller";
import type {
  OrchestratorCommandBinding,
  OrchestratorCommandView,
  OrchestratorSessionPresentation,
} from "./host-command-bindings";
import {
  intentIdForOperationKey,
  operationKeyForLaunch,
} from "./operation-key";

/** Same string as host-command-bindings.COMMAND_ROUTE_UNAVAILABLE; value copied to keep this module free of a runtime import cycle. */
const COMMAND_ROUTE_UNAVAILABLE = "COMMAND_ROUTE_UNAVAILABLE";

const MAX_OBJECTIVE_CHARS = 4000;
const DEPARTMENT_RE = /^[a-z][a-z0-9._-]{1,63}$/;
const WORKSTREAM_RE = /^WS:[A-Z0-9][A-Za-z0-9._-]{1,63}$/;
const JOB_RE = /^JOB-[A-Za-z0-9][A-Za-z0-9._:-]{0,250}$/;
const KEY_RE = /^[a-z0-9][a-z0-9-]{2,95}$/;
const PROFILES = new Set(["research_only", "bounded_code_change"]);
const RECEIPT_SCHEMAS = new Set([
  "mastermind.ceo_intent_receipt.v1",
  "mastermind.ceo_intent_receipt.v2",
]);

export interface ExecutiveToolEnvelope {
  readonly ok: boolean;
  readonly data?: unknown;
  readonly error?: { readonly code: string; readonly message?: string };
}

export interface ExecutiveToolClient {
  callTool(
    name: "submit_ceo_intent" | "ceo_intent_status",
    args: Readonly<Record<string, unknown>>,
    signal: AbortSignal,
  ): Promise<ExecutiveToolEnvelope>;
}

export interface LaunchBindingConfig {
  readonly workstream: string;
  readonly priority: number;
  readonly attemptLimit?: 1 | 2 | 3;
  readonly allowedWritePaths?: readonly string[];
  readonly validation?: {
    readonly pytest_targets?: readonly string[];
    readonly compileall_paths?: readonly string[];
    readonly git_diff_check?: boolean;
  };
  readonly projects: readonly LaunchChoice[];
  readonly profiles: readonly LaunchChoice[];
}

export interface ExecutiveLaunchViewSource {
  context(): OwnerContext | null;
  readonly store: PendingPointerStore;
  getSession(): OrchestratorSessionPresentation | null;
  subscribe(listener: () => void): () => void;
}

export class ExecutiveLaunchCommandPort implements FiniteCommandPort {
  constructor(
    private readonly config: LaunchBindingConfig,
    private readonly client: ExecutiveToolClient,
    private readonly owner: () => OwnerContext | null,
  ) {}

  context(): OwnerContext | null {
    return this.owner();
  }

  makeLaunchIntent(form: LaunchForm): CommandIntent | null {
    const ctx = this.owner();
    if (!ctx) return null;
    const payload = this._payloadFromForm(form, ctx.principalScope);
    if (!payload) return null;
    return { kind: "launch", targetKey: this.config.workstream, payload };
  }

  prepare(intent: CommandIntent): OperationPointer {
    if (intent.kind !== "launch") throw new Error("INVALID_KIND");
    const ctx = this.owner();
    if (!ctx) throw new Error("INVALID_PAYLOAD");
    const form = formFromPayload(intent.payload);
    if (!form) throw new Error("INVALID_PAYLOAD");
    const expected = this._payloadFromForm(form, ctx.principalScope);
    if (!expected || !sameJson(expected, intent.payload)) {
      throw new Error("INVALID_PAYLOAD");
    }
    const workstream = expected.workstream;
    if (typeof workstream !== "string" || !validWorkstream(workstream)) {
      throw new Error("INVALID_PAYLOAD");
    }
    if (intent.targetKey !== workstream) {
      throw new Error("INVALID_PAYLOAD");
    }
    const operationKey = expected.operation_key;
    if (typeof operationKey !== "string" || !KEY_RE.test(operationKey)) {
      throw new Error("INVALID_PAYLOAD");
    }
    return { operationKey, kind: "launch", targetKey: workstream };
  }

  async submit(
    pointer: OperationPointer,
    intent: CommandIntent,
    signal: AbortSignal,
  ): Promise<EffectReceipt> {
    if (pointer.operationKey !== intent.payload.operation_key) {
      return this._receipt(pointer, "refused", "MALFORMED_POINTER");
    }
    if (!validPointerTargetKey(pointer.targetKey)) {
      return this._receipt(pointer, "unknown", "MALFORMED_POINTER");
    }
    if (signal.aborted) {
      return this._receipt(pointer, "unknown", "TRANSPORT_ERROR");
    }
    let envelope: ExecutiveToolEnvelope;
    try {
      envelope = await this.client.callTool(
        "submit_ceo_intent",
        intent.payload,
        signal,
      );
    } catch {
      return this._receipt(pointer, "unknown", "TRANSPORT_ERROR");
    }
    if (signal.aborted) {
      return this._receipt(pointer, "unknown", "TRANSPORT_ERROR");
    }
    return this._mapEnvelope(pointer, envelope, "submit");
  }

  async readOperation(
    pointer: OperationPointer,
    signal: AbortSignal,
  ): Promise<EffectReceipt> {
    if (!validPointerTargetKey(pointer.targetKey)) {
      return this._receipt(pointer, "unknown", "MALFORMED_POINTER");
    }
    if (signal.aborted) {
      return this._receipt(pointer, "unknown", "TRANSPORT_ERROR");
    }
    const intent_id = intentIdForOperationKey(pointer.operationKey);
    let envelope: ExecutiveToolEnvelope;
    try {
      envelope = await this.client.callTool(
        "ceo_intent_status",
        { intent_id },
        signal,
      );
    } catch {
      return this._receipt(pointer, "unknown", "TRANSPORT_ERROR");
    }
    if (signal.aborted) {
      return this._receipt(pointer, "unknown", "TRANSPORT_ERROR");
    }
    return this._mapEnvelope(pointer, envelope, "status");
  }

  private _payloadFromForm(
    form: LaunchForm,
    principalScope: string,
  ): Record<string, unknown> | null {
    if (!validGoal(form.goal)) return null;
    if (!DEPARTMENT_RE.test(form.projectRef)) return null;
    if (!listedChoice(this.config.projects, form.projectRef)) return null;
    if (!PROFILES.has(form.profileRef)) return null;
    if (!listedChoice(this.config.profiles, form.profileRef)) return null;
    if (!validWorkstream(this.config.workstream)) return null;
    if (!validPriority(this.config.priority)) return null;

    const writePaths = this.config.allowedWritePaths;
    const validation = this.config.validation;
    const writeCount = writePaths?.length ?? 0;
    const validationCount = validationEntries(validation);
    if (form.profileRef === "research_only") {
      if (writeCount > 0 || validationCount > 0) return null;
    } else {
      if (writeCount < 1 || validationCount < 1) return null;
      if (!writePaths || !validWritePaths(writePaths)) return null;
    }

    const payload: Record<string, unknown> = {
      operation_key: operationKeyForLaunch({
        principalScope,
        workstream: this.config.workstream,
        department: form.projectRef,
        execution_profile: form.profileRef,
        objective: form.goal,
        priority: this.config.priority,
        ...(writePaths !== undefined ? { allowed_write_paths: writePaths } : {}),
        ...(validation !== undefined ? { validation } : {}),
        ...(this.config.attemptLimit !== undefined
          ? { attempt_limit: this.config.attemptLimit }
          : {}),
      }),
      objective: form.goal,
      department: form.projectRef,
      priority: this.config.priority,
      execution_profile: form.profileRef,
      workstream: this.config.workstream,
    };
    if (writePaths !== undefined) payload.allowed_write_paths = [...writePaths];
    if (validation !== undefined) payload.validation = copyValidation(validation);
    if (this.config.attemptLimit !== undefined) {
      payload.attempt_limit = this.config.attemptLimit;
    }
    return payload;
  }

  private _mapEnvelope(
    pointer: OperationPointer,
    envelope: ExecutiveToolEnvelope,
    path: "submit" | "status",
  ): EffectReceipt {
    if (envelope.ok !== true) {
      return this._mapError(pointer, envelope.error?.code, path);
    }
    const data = envelope.data;
    if (!isPlainObject(data)) {
      return this._receipt(pointer, "unknown", "MALFORMED_RECEIPT");
    }
    if (typeof data.intent_id !== "string") {
      return this._receipt(pointer, "unknown", "MALFORMED_RECEIPT");
    }
    if (data.intent_id !== intentIdForOperationKey(pointer.operationKey)) {
      return this._receipt(pointer, "unknown", "RECEIPT_MISMATCH");
    }
    if (!validPointerTargetKey(pointer.targetKey)) {
      return this._receipt(pointer, "unknown", "MALFORMED_POINTER");
    }
    const schemaOk =
      typeof data.schema === "string" && RECEIPT_SCHEMAS.has(data.schema);
    if (!schemaOk || data.accepted !== true || data.dispatched !== false) {
      return this._receipt(pointer, "unknown", "MALFORMED_RECEIPT");
    }
    if (typeof data.job_id !== "string") {
      return this._receipt(pointer, "unknown", "MALFORMED_RECEIPT");
    }
    if (!JOB_RE.test(data.job_id)) {
      return this._receipt(pointer, "unknown", "UNKNOWN_RECEIPT");
    }
    return this._receipt(pointer, "accepted", "ACCEPTED", {
      workRef: pointer.targetKey,
      rootJobId: data.job_id,
    });
  }

  /**
   * Submit-path refused codes fire before the durable Job write:
   * invalid_input — executive_ceo_ingress.py _handle_submit :474-479;
   * authority_refused / backend_refused — adapter.py :996-1040 and ingress
   * _handle_normalized_submit admission_guard :673-685 (zero sink calls);
   * production_write_disabled — adapter.py :898-905;
   * identity_unverified — auth gate before write;
   * grounding_unavailable / grounding_changed — ingress :609 / :647-649
   * ("zero Job").
   * not_found is not a submit-path before-effect code (D1 / §7.2): the
   * installed ingress raises it only from _resolve_status_intent :775-777,
   * so on submit it is unknown/UNKNOWN_RECEIPT. On the status path every
   * non-accepted result is unknown and retains the pointer (§8.3).
   */
  private _mapError(
    pointer: OperationPointer,
    code: string | undefined,
    path: "submit" | "status",
  ): EffectReceipt {
    if (path === "status") {
      switch (code) {
        case "invalid_input":
        case "authority_refused":
        case "identity_unverified":
        case "backend_refused":
        case "production_write_disabled":
        case "grounding_unavailable":
        case "grounding_changed":
        case "not_found":
        case "backend_unavailable":
        case "internal_error":
        case "output_too_large":
          return this._receipt(pointer, "unknown", "UNKNOWN_RECEIPT");
        case "timeout":
        default:
          return this._receipt(pointer, "unknown", "TRANSPORT_ERROR");
      }
    }
    switch (code) {
      case "invalid_input":
        return this._receipt(pointer, "refused", "INVALID_PAYLOAD");
      case "authority_refused":
      case "backend_refused":
      case "production_write_disabled":
      case "identity_unverified":
      case "grounding_unavailable":
      case "grounding_changed":
        return this._receipt(pointer, "refused", "REFUSED");
      case "not_found":
      case "backend_unavailable":
      case "internal_error":
      case "output_too_large":
        return this._receipt(pointer, "unknown", "UNKNOWN_RECEIPT");
      case "timeout":
      default:
        return this._receipt(pointer, "unknown", "TRANSPORT_ERROR");
    }
  }

  private _receipt(
    pointer: OperationPointer,
    disposition: EffectReceipt["disposition"],
    reason: string,
    missionSelection?: { workRef: string; rootJobId: string },
  ): EffectReceipt {
    return {
      operationKey: pointer.operationKey,
      kind: "launch",
      targetKey: pointer.targetKey,
      disposition,
      reason,
      ...(missionSelection ? { missionSelection } : {}),
    };
  }
}

export function createExecutiveLaunchBinding(
  config: LaunchBindingConfig,
  client: ExecutiveToolClient,
  viewSource: ExecutiveLaunchViewSource,
): OrchestratorCommandBinding {
  const port = new ExecutiveLaunchCommandPort(config, client, () =>
    viewSource.context(),
  );
  return {
    port,
    store: viewSource.store,
    getView(): OrchestratorCommandView {
      const session = viewSource.getSession();
      return {
        projects: config.projects,
        profiles: config.profiles,
        session: session ? presentSession(session) : null,
      };
    },
    subscribe: (listener) => viewSource.subscribe(listener),
    makeLaunchIntent: (form) => port.makeLaunchIntent(form),
    makeMessageIntent: () => null,
    makeStopIntent: () => null,
  };
}

function presentSession(
  session: OrchestratorSessionPresentation,
): OrchestratorSessionPresentation {
  return {
    sessionKey: session.sessionKey,
    title: session.title,
    messages: session.messages,
    observedAt: session.observedAt,
    connection: session.connection,
    coverage: session.coverage,
    turnBusy: false,
    unavailableReason: COMMAND_ROUTE_UNAVAILABLE,
    selection: session.selection,
    ...(typeof session.error === "string" ? { error: session.error } : {}),
  };
}

function formFromPayload(payload: Readonly<Record<string, unknown>>): LaunchForm | null {
  if (typeof payload.objective !== "string") return null;
  if (typeof payload.department !== "string") return null;
  if (typeof payload.execution_profile !== "string") return null;
  return {
    goal: payload.objective,
    projectRef: payload.department,
    profileRef: payload.execution_profile,
  };
}

function listedChoice(choices: readonly LaunchChoice[], ref: string): boolean {
  return choices.some((choice) => choice.ref === ref && !choice.unavailableReason);
}

function validGoal(goal: unknown): goal is string {
  return typeof goal === "string" && goal.length > 0 && goal.length <= MAX_OBJECTIVE_CHARS;
}

function validWorkstream(value: string): boolean {
  return value.length <= 72 && WORKSTREAM_RE.test(value);
}

function validPointerTargetKey(value: string | null): value is string {
  return (
    typeof value === "string" &&
    value.length > 0 &&
    value.length <= 72 &&
    WORKSTREAM_RE.test(value)
  );
}

function validPriority(value: number): boolean {
  return Number.isInteger(value) && value >= -100 && value <= 100;
}

function validationEntries(
  validation: LaunchBindingConfig["validation"] | undefined,
): number {
  if (!validation) return 0;
  let count = 0;
  if (validation.pytest_targets && validation.pytest_targets.length > 0) count += 1;
  if (validation.compileall_paths && validation.compileall_paths.length > 0) count += 1;
  if (validation.git_diff_check === true) count += 1;
  return count;
}

function validWritePaths(paths: readonly string[]): boolean {
  if (paths.length > 16) return false;
  for (const path of paths) {
    if (typeof path !== "string" || path.length === 0 || path.length > 256) return false;
    if (path.startsWith("/") || path.includes("\\")) return false;
    const segments = path.split("/").filter((segment) => segment !== "" && segment !== ".");
    if (segments.length === 0) return false;
    for (const segment of segments) {
      if (segment === ".." || segment === ".git") return false;
    }
  }
  return true;
}

function copyValidation(
  validation: NonNullable<LaunchBindingConfig["validation"]>,
): Record<string, unknown> {
  const copied: Record<string, unknown> = {};
  if (validation.pytest_targets !== undefined) {
    copied.pytest_targets = [...validation.pytest_targets];
  }
  if (validation.compileall_paths !== undefined) {
    copied.compileall_paths = [...validation.compileall_paths];
  }
  if (validation.git_diff_check !== undefined) {
    copied.git_diff_check = validation.git_diff_check;
  }
  return copied;
}

function isPlainObject(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

function sameJson(a: unknown, b: unknown): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}
