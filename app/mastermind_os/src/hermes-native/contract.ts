/** Stable UI port. Native sessions are not Executive Jobs or accepted outcomes. */
import type { NativePendingOperation } from "./pending-pointer";
import { parseTeamRoster, type TeamRoster } from "./team-roster-contract";
export type NativeOperation =
  | { operation: "status" | "list" | "recover" | "team_roster" }
  | { operation: "create"; role: "meta-ceo" | "secretary"; requestId: string }
  | { operation: "read"; sessionId: string }
  | { operation: "send"; sessionId: string; requestId: string; text: string }
  | { operation: "receipt"; sessionId: string; admissionId: string };
export type AdmissionState = "queued" | "started" | "unknown" | "terminal";
export type NativeState = "READY" | "OPENED" | "ADMITTED" | "REFUSED" | "NOT_SENT" | "UNAVAILABLE" | "EFFECT_UNKNOWN";
export interface NativeMessage { role: "user" | "assistant"; text: string }
export interface NativeSession {
  id: string; storedId: string; title: string; requestedModel: string;
  canSend: boolean; toolAccess: "NONE" | "CAPACITY_READ_ONLY" | "ADVISORY_READ_ONLY" | "UNQUALIFIED";
  /** Stored history requires a fresh owner check at the explicit send. */
  sendCheckRequired?: true;
  running: boolean | null; executionGeneration: number; messageCount: number;
  messages: NativeMessage[]; historyTruncated: boolean;
  pending: { id: string; status: AdmissionState }[]; promptsPending: boolean | null;
}
export interface NativeReceipt {
  id: string; sessionId: string; status: AdmissionState; sequence: number;
  outcome: string | null; executionGeneration: number | null;
  /** Present only on a terminal failed receipt: the producer's closed failure
   * classification (bot_failure_reasons vocabulary); never guessed client-side. */
  failureReason?: ContinuationFailureReason;
}
export interface NativeView {
  schema: "mastermind.hermes_native_view.v1"; state: NativeState; authGeneration: number;
  capabilities: string[]; delegation: "NOT_ENABLED"; retryAllowed: false;
  operation?: NativeOperation["operation"]; code?: string;
  requestId?: string; requestSessionId?: string;
  runtime?: { protocol: 1; instanceId: string; authorityEpoch: number; version: string | null; sourceRevision: string | null; localScope?: string };
  /** Produced by the native port from the existing durable pointer store. */
  pendingOperation?: NativePendingOperation | null;
  session?: NativeSession;
  sessions?: { id: string; title: string; running: boolean | null; messageCount: number }[];
  receipt?: NativeReceipt;
  /** Read-only team roster projection (team_roster operation). */
  roster?: TeamRoster;
}
export interface NativeHermesPort { available(): boolean; request(request: NativeOperation): Promise<NativeView> }

const states = new Set(["READY", "OPENED", "ADMITTED", "REFUSED", "NOT_SENT", "UNAVAILABLE", "EFFECT_UNKNOWN"]);
const admissions = new Set(["queued", "started", "unknown", "terminal"]);
const operations = new Set(["status", "list", "create", "read", "send", "receipt", "recover", "team_roster"]);
/** Closed producer-side failure vocabulary (Hermes tools.bot_failure_reasons). */
export type ContinuationFailureReason =
  | "runtime_offline" | "queued_expired" | "delivery_timeout" | "agent_blocked" | "cancelled"
  | "provider_auth_or_access" | "provider_quota_limit" | "provider_rate_limit"
  | "provider_server_error" | "context_overflow" | "missing_config" | "model_unavailable"
  | "target_scope_unresolved" | "unknown";
const failureReasons = new Set<ContinuationFailureReason>(["runtime_offline", "queued_expired",
  "delivery_timeout", "agent_blocked", "cancelled", "provider_auth_or_access", "provider_quota_limit",
  "provider_rate_limit", "provider_server_error", "context_overflow", "missing_config",
  "model_unavailable", "target_scope_unresolved", "unknown"]);
const capabilities = new Set(["native_chat", "native_history", "admission_recovery"]);
const idPattern = /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}$/;
function invalid(): never { throw new Error("NATIVE_RESPONSE_INVALID"); }
function record(value: unknown, allowed: string[], required = allowed): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) return invalid();
  const object = value as Record<string, unknown>;
  if (Object.keys(object).some(key => !allowed.includes(key)) || required.some(key => !(key in object))) return invalid();
  return object;
}
function text(value: unknown, maximum = 32768): string {
  if (typeof value !== "string" || new TextEncoder().encode(value).length > maximum || /[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/.test(value)) return invalid();
  return value;
}
function id(value: unknown): string { const result = text(value, 160); return idPattern.exec(result)?.[0] === result ? result : invalid(); }
function number(value: unknown): number { return typeof value === "number" && Number.isSafeInteger(value) && value >= 0 ? value : invalid(); }
function flag(value: unknown): boolean { return typeof value === "boolean" ? value : invalid(); }
function rows(value: unknown, max: number): unknown[] { return Array.isArray(value) && value.length <= max ? value : invalid(); }
function admission(value: unknown): AdmissionState { return admissions.has(text(value, 20)) ? value as AdmissionState : invalid(); }
function session(value: unknown): NativeSession {
  const required = ["id", "storedId", "title", "requestedModel", "canSend", "toolAccess", "running", "executionGeneration", "messageCount", "messages", "historyTruncated", "pending", "promptsPending"];
  const v = record(value, [...required, "sendCheckRequired"], required);
  const toolAccess = text(v.toolAccess, 32);
  if (!["NONE", "CAPACITY_READ_ONLY", "ADVISORY_READ_ONLY", "UNQUALIFIED"].includes(toolAccess)) return invalid();
  const canSend = flag(v.canSend);
  if (canSend && toolAccess === "UNQUALIFIED") return invalid();
  const sendCheckRequired = v.sendCheckRequired !== undefined;
  if (sendCheckRequired && (v.sendCheckRequired !== true || canSend || toolAccess !== "UNQUALIFIED" || v.running !== null || v.promptsPending !== null)) return invalid();
  const messages = rows(v.messages, 100).map(row => {
    const m = record(row, ["role", "text"]);
    if (m.role !== "user" && m.role !== "assistant") return invalid();
    return { role: m.role, text: text(m.text, 65536) } as NativeMessage;
  });
  const pending = rows(v.pending, 1000).map(row => { const p = record(row, ["id", "status"]); return { id: id(p.id), status: admission(p.status) }; });
  if (new Set(pending.map(item => item.id)).size !== pending.length) return invalid();
  const messageCount = number(v.messageCount);
  if (messageCount < messages.length) return invalid();
  return { id: id(v.id), storedId: id(v.storedId), title: text(v.title, 512), requestedModel: text(v.requestedModel, 160),
    canSend, toolAccess: toolAccess as NativeSession["toolAccess"],
    ...(sendCheckRequired ? { sendCheckRequired: true as const } : {}), running: sendCheckRequired ? null : flag(v.running),
    executionGeneration: number(v.executionGeneration), messageCount, messages,
    historyTruncated: flag(v.historyTruncated), pending, promptsPending: sendCheckRequired ? null : flag(v.promptsPending) };
}

export function parseNativeView(value: unknown): NativeView {
  const v = record(value, ["schema", "state", "authGeneration", "capabilities", "delegation", "retryAllowed", "operation", "requestId", "requestSessionId", "code", "runtime", "session", "sessions", "receipt", "roster"],
    ["schema", "state", "authGeneration", "capabilities", "delegation", "retryAllowed"]);
  if (v.schema !== "mastermind.hermes_native_view.v1" || !states.has(text(v.state, 24)) || v.delegation !== "NOT_ENABLED" || v.retryAllowed !== false) return invalid();
  const caps = rows(v.capabilities, 8).map(value => text(value, 64));
  if (caps.some(value => !capabilities.has(value)) || new Set(caps).size !== caps.length) return invalid();
  const result: NativeView = { schema: "mastermind.hermes_native_view.v1", state: v.state as NativeState,
    authGeneration: number(v.authGeneration), capabilities: caps, delegation: "NOT_ENABLED", retryAllowed: false };
  if (v.operation !== undefined) {
    if (!operations.has(text(v.operation, 20))) return invalid();
    result.operation = v.operation as NativeOperation["operation"];
  }
  if (v.requestId !== undefined) {
    const requestId = text(v.requestId, 32);
    if (/^[a-f0-9]{32}$/.exec(requestId)?.[0] !== requestId) return invalid();
    result.requestId = requestId;
  }
  if (v.requestSessionId !== undefined) result.requestSessionId = id(v.requestSessionId);
  if (v.code !== undefined) {
    const code = text(v.code, 100); if (!/^[A-Za-z][A-Za-z0-9_]*$/.test(code)) return invalid(); result.code = code;
  }
  if (v.runtime !== undefined) {
    const r = record(v.runtime, ["protocol", "instanceId", "authorityEpoch", "version", "sourceRevision", "localScope"],
      ["protocol", "instanceId", "authorityEpoch", "version", "sourceRevision"]);
    if (r.protocol !== 1 || number(r.authorityEpoch) < 1) return invalid();
    const revision = r.sourceRevision === null ? null : text(r.sourceRevision, 40);
    if (revision !== null && !/^[a-f0-9]{40}$/.test(revision)) return invalid();
    result.runtime = { protocol: 1, instanceId: id(r.instanceId), authorityEpoch: number(r.authorityEpoch),
      version: r.version === null ? null : text(r.version, 64), sourceRevision: revision };
    if (r.localScope !== undefined) {
      const scope = text(r.localScope, 64); if (!/^[a-f0-9]{64}$/.test(scope)) return invalid();
      result.runtime.localScope = scope;
    }
  }
  if (v.session !== undefined) result.session = session(v.session);
  if (v.sessions !== undefined) result.sessions = rows(v.sessions, 50).map(row => {
    const s = record(row, ["id", "title", "running", "messageCount"]);
    return { id: id(s.id), title: text(s.title, 512), running: s.running === null ? null : flag(s.running), messageCount: number(s.messageCount) };
  });
  if (v.receipt !== undefined) {
    const r = record(v.receipt, ["id", "sessionId", "status", "sequence", "outcome", "executionGeneration", "failureReason"],
      ["id", "sessionId", "status", "sequence", "outcome", "executionGeneration"]);
    if (number(r.sequence) < 1) return invalid();
    if (r.failureReason !== undefined && r.failureReason !== null
        && (typeof r.failureReason !== "string" || !failureReasons.has(r.failureReason as ContinuationFailureReason))) return invalid();
    if ((r.failureReason !== undefined && r.failureReason !== null)
        && (r.status !== "terminal" || r.outcome !== "failed")) return invalid();
    result.receipt = { id: id(r.id), sessionId: id(r.sessionId), status: admission(r.status), sequence: number(r.sequence),
      outcome: r.outcome === null ? null : text(r.outcome, 240), executionGeneration: r.executionGeneration === null ? null : number(r.executionGeneration),
      ...(r.failureReason ? { failureReason: r.failureReason as ContinuationFailureReason } : {}) };
  }
  if (v.roster !== undefined) {
    if (v.operation !== "team_roster") return invalid();
    result.roster = parseTeamRoster(v.roster);
  }
  if (result.state === "OPENED" && !result.session || result.state === "ADMITTED" && !result.receipt) return invalid();
  if (new TextEncoder().encode(JSON.stringify(result)).length > 1048576) return invalid();
  return result;
}
