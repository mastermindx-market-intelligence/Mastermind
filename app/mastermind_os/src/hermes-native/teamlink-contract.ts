/** TeamLink contract mirror — TeamLinkMessage.v1 / ContextPacket.v1.
 *
 * Adopted verbatim (field names, patterns, closed rules) from the v1 design
 * ~/.hermes/profiles/engineering/mmos/TEAMLINK_DESIGN.md (2026-11-09),
 * DESIGN ONLY. Mirrors control_plane/teamlink_contracts.py. No transport, no
 * queue, no broker, no store, no retry loop, no UI (design §6 non-goals):
 * placement stays with the ONE broker, decisions with the ONE Executive
 * decision ledger, and TeamLink is audited BY REFERENCE with the WO-17
 * correlation keys. The wire is snake_case because these ARE the design's
 * field names; UI adaptation happens in views, not in this contract.
 */
export class TeamLinkContractError extends Error {
  constructor(public code: string, public detail: string = "") {
    super(detail ? `${code}: ${detail}` : code);
  }
}
function invalid(code: string, detail = ""): never { throw new TeamLinkContractError(code, detail); }

const messageIdPattern = /^tlm-[0-9a-f]{32}$/;
const packetIdPattern = /^tlp-[0-9a-f]{32}$/;
const operationKeyPattern = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,95}$/;
const requestDigestPattern = /^[0-9a-f]{64}$/;
const isoPattern = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?([+-]\d{2}:?\d{2}|Z)$/;

export type PrincipalSide = "hermes_profile" | "t3_host_thread";
export type MessageKind =
  | "instruction" | "question" | "answer" | "decision_update"
  | "evidence" | "blocker" | "status";
export type MessageIntent = "informational" | "actionable";
export type DeliveryState =
  | "admitted" | "picked_up" | "executed" | "replied" | "consumed" | "unknown";

/** The WO-17 correlation keys, verbatim. TeamLink copies them from an
 * admitted binding/decision; it never mints or re-derives them. Every key
 * is nullable — a status ping before admission has no decision_id yet. */
export interface TeamLinkCorrelation {
  root_run_ref?: string | null;
  immediate_parent_run_ref?: string | null;
  logical_child_key?: string | null;
  preview_id?: string | null;
  decision_id?: string | null;
  attempt_ref?: string | null;
  fence_counter?: number | null;
  request_digest?: string | null;
}
export interface TeamLinkPrincipal {
  side: PrincipalSide; id: string; thread_ref?: string | null;
}
export interface TeamLinkMessage {
  schema: "TeamLinkMessage.v1";
  message_id: string;
  operation_key: string;
  correlation: TeamLinkCorrelation;
  from: TeamLinkPrincipal;
  to: TeamLinkPrincipal;
  kind: MessageKind;
  intent: MessageIntent;
  body: string;
  context_refs: string[];
  reply_to?: string | null;
  hop_count: number;
  max_hops: number;
  delivery_state: DeliveryState;
  expires_at: string;
}

export interface DecisionRef { decision_id: string; summary?: string; ledger_row?: string | null }
export interface Dependency { what: string; owner: string; ref?: string | null }
export interface WorkOwnership { work_ref: string; owner: string; lease_expires_at?: string | null }
export interface UnresolvedEffect { effect_ref: string; state: "EFFECT_UNKNOWN"; rule: string }
export interface PacketDelta { added?: string[]; changed?: string[]; removed?: string[] }
export interface ContextPacket {
  schema: "ContextPacket.v1";
  packet_id: string;
  objective: string;
  accepted_decisions: DecisionRef[];
  outstanding_dependencies: Dependency[];
  source_revision: { branch: string; head: string };
  active_work_ownership: WorkOwnership[];
  unresolved_effects: UnresolvedEffect[];
  next_action: string;
  since_packet_id?: string | null;
  delta?: PacketDelta;
  expires_at: string;
}

// generous caps on fields the design leaves unbounded — hostile-blob defense,
// never a constraint on lawful producers.
const REF_MAX = 1024, PRINCIPAL_ID_MAX = 256, THREAD_REF_MAX = 256;
const BODY_MAX = 4096, CONTEXT_REFS_MAX = 32, MAX_HOPS_CEILING = 8;

function obj(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) invalid("INVALID_OBJECT");
  return value as Record<string, unknown>;
}
function exactKeys(value: unknown, required: string[], allowed: string[], label: string): Record<string, unknown> {
  const v = obj(value);
  const keys = Object.keys(v);
  if (keys.some(key => !allowed.includes(key))) invalid(`INVALID_${label}_FIELDS`);
  const missing = required.filter(key => !(key in v));
  if (missing.length > 0) invalid(`MISSING_${label}_FIELD`, missing.join(","));
  return v;
}
function text(value: unknown, label: string, maximum: number, minimum = 0): string {
  if (typeof value !== "string" || value.length < minimum || value.length > maximum) invalid(`INVALID_${label}`);
  return value;
}
function nullableText(value: unknown, label: string, maximum: number): string | null {
  return value === undefined || value === null ? null : text(value, label, maximum);
}
function integer(value: unknown, label: string, minimum: number, maximum?: number): number {
  if (typeof value !== "number" || !Number.isSafeInteger(value)
      || value < minimum || (maximum !== undefined && value > maximum)) invalid(`INVALID_${label}`);
  return value;
}
function iso(value: unknown, label: string): string {
  const s = text(value, label, 64, 1);
  if (!validIso(s)) invalid(`INVALID_${label}`);
  return s;
}

// Date.parse normalizes impossible calendar days on some engines. Match the
// Python contract before parsing so an invalid deadline cannot gain lifetime.
function validIso(value: string): boolean {
  if (value.length > 64 || !isoPattern.test(value)) return false;
  const year = Number(value.slice(0, 4)), month = Number(value.slice(5, 7));
  const day = Number(value.slice(8, 10));
  const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
  const days = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  if (year < 1 || month < 1 || month > 12 || day < 1 || day > days[month - 1]!
      || Number(value.slice(11, 13)) > 23 || Number(value.slice(14, 16)) > 59
      || Number(value.slice(17, 19)) > 59) return false;
  const offset = value.match(/([+-])(\d{2}):?(\d{2})$/);
  if (offset && (Number(offset[2]) > 23 || Number(offset[3]) > 59)) return false;
  return Number.isFinite(Date.parse(value));
}

const principalSides = new Set(["hermes_profile", "t3_host_thread"]);
const messageKinds = new Set(["instruction", "question", "answer", "decision_update", "evidence", "blocker", "status"]);
const messageIntents = new Set(["informational", "actionable"]);
const deliveryStates = new Set(["admitted", "picked_up", "executed", "replied", "consumed", "unknown"]);
/** Monotonic chain; "unknown" is deliberately OUTSIDE it. */
export const DELIVERY_CHAIN = ["admitted", "picked_up", "executed", "replied", "consumed"] as const;

function principal(value: unknown, label: string): TeamLinkPrincipal {
  const v = exactKeys(value, ["side", "id"], ["side", "id", "thread_ref"], `${label}_PRINCIPAL`);
  if (!principalSides.has(v.side as string)) invalid(`INVALID_${label}_PRINCIPAL_SIDE`);
  text(v.id, `${label}_PRINCIPAL_ID`, PRINCIPAL_ID_MAX, 1);
  if ("thread_ref" in v && v.thread_ref !== null) {
    if (text(v.thread_ref, `${label}_THREAD_REF`, THREAD_REF_MAX).length === 0) invalid(`INVALID_${label}_THREAD_REF`);
  }
  return { side: v.side as PrincipalSide, id: v.id as string,
    ...("thread_ref" in v ? { thread_ref: (v.thread_ref as string | null) ?? null } : {}) };
}
function correlation(value: unknown): TeamLinkCorrelation {
  const v = exactKeys(value, [],
    ["root_run_ref", "immediate_parent_run_ref", "logical_child_key", "preview_id",
     "decision_id", "attempt_ref", "fence_counter", "request_digest"], "CORRELATION");
  const out: TeamLinkCorrelation = {};
  for (const key of ["root_run_ref", "immediate_parent_run_ref", "logical_child_key",
                     "preview_id", "decision_id", "attempt_ref"]) {
    if (key in v) out[key as keyof TeamLinkCorrelation] = nullableText(v[key], `INVALID_${key.toUpperCase()}`, REF_MAX) as never;
  }
  if ("fence_counter" in v && v.fence_counter !== null) {
    out.fence_counter = integer(v.fence_counter, "FENCE_COUNTER", 0);
  }
  if ("request_digest" in v) {
    const digest = nullableText(v.request_digest, "REQUEST_DIGEST", 64);
    if (digest !== null && !requestDigestPattern.test(digest)) invalid("INVALID_REQUEST_DIGEST");
    out.request_digest = digest;
  }
  return out;
}

export function parseTeamLinkMessage(value: unknown): TeamLinkMessage {
  const v = exactKeys(value,
    ["schema", "message_id", "operation_key", "correlation", "from", "to", "kind",
     "intent", "body", "context_refs", "hop_count", "max_hops", "delivery_state", "expires_at"],
    ["schema", "message_id", "operation_key", "correlation", "from", "to", "kind",
     "intent", "body", "context_refs", "reply_to", "hop_count", "max_hops",
     "delivery_state", "expires_at"], "MESSAGE");
  if (v.schema !== "TeamLinkMessage.v1") invalid("INVALID_MESSAGE_SCHEMA");
  if (!messageIdPattern.test(text(v.message_id, "MESSAGE_ID", 36, 1))) invalid("INVALID_MESSAGE_ID");
  if (!operationKeyPattern.test(text(v.operation_key, "OPERATION_KEY", 96, 1))) invalid("INVALID_OPERATION_KEY");
  if (!messageKinds.has(v.kind as string)) invalid("INVALID_KIND");
  if (!messageIntents.has(v.intent as string)) invalid("INVALID_INTENT");
  text(v.body, "BODY", BODY_MAX, 1);
  const refs = v.context_refs;
  if (!Array.isArray(refs) || refs.length > CONTEXT_REFS_MAX) invalid("INVALID_CONTEXT_REFS");
  refs.forEach(ref => text(ref, "CONTEXT_REF", REF_MAX, 1));
  let reply_to: string | null | undefined;
  if ("reply_to" in v) {
    reply_to = nullableText(v.reply_to, "REPLY_TO", 36);
    if (reply_to !== null && !messageIdPattern.test(reply_to)) invalid("INVALID_REPLY_TO");
  }
  integer(v.hop_count, "HOP_COUNT", 0);
  integer(v.max_hops, "MAX_HOPS", 0, MAX_HOPS_CEILING);
  if (!deliveryStates.has(v.delivery_state as string)) invalid("INVALID_DELIVERY_STATE");
  iso(v.expires_at, "EXPIRES_AT");
  return { schema: "TeamLinkMessage.v1", message_id: v.message_id as string,
    operation_key: v.operation_key as string, correlation: correlation(v.correlation),
    from: principal(v.from, "FROM"), to: principal(v.to, "TO"),
    kind: v.kind as MessageKind, intent: v.intent as MessageIntent,
    body: v.body as string, context_refs: refs as string[],
    ...("reply_to" in v ? { reply_to } : {}),
    hop_count: v.hop_count as number, max_hops: v.max_hops as number,
    delivery_state: v.delivery_state as DeliveryState, expires_at: v.expires_at as string };
}

function rows<T>(value: unknown, limit: number, label: string,
                 required: string[], allowed: string[], check: (row: Record<string, unknown>) => T): T[] {
  if (!Array.isArray(value) || value.length > limit) invalid(`INVALID_${label}`);
  return value.map(row => check(exactKeys(row, required, allowed, label)));
}

export function parseContextPacket(value: unknown): ContextPacket {
  const v = exactKeys(value,
    ["schema", "packet_id", "objective", "accepted_decisions", "outstanding_dependencies",
     "source_revision", "active_work_ownership", "unresolved_effects", "next_action", "expires_at"],
    ["schema", "packet_id", "objective", "accepted_decisions", "outstanding_dependencies",
     "source_revision", "active_work_ownership", "unresolved_effects", "next_action",
     "since_packet_id", "delta", "expires_at"], "PACKET");
  if (v.schema !== "ContextPacket.v1") invalid("INVALID_PACKET_SCHEMA");
  if (!packetIdPattern.test(text(v.packet_id, "PACKET_ID", 36, 1))) invalid("INVALID_PACKET_ID");
  text(v.objective, "OBJECTIVE", 2048);
  const accepted = rows(v.accepted_decisions, 64, "ACCEPTED_DECISIONS",
    ["decision_id"], ["decision_id", "summary", "ledger_row"], row => {
      text(row.decision_id, "DECISION_ID", REF_MAX, 1);
      if ("summary" in row) text(row.summary, "DECISION_SUMMARY", 512);
      if ("ledger_row" in row) nullableText(row.ledger_row, "LEDGER_ROW", REF_MAX);
      return { decision_id: row.decision_id as string,
        ...("summary" in row ? { summary: row.summary as string } : {}),
        ...("ledger_row" in row ? { ledger_row: row.ledger_row as string | null } : {}) };
    });
  const dependencies = rows(v.outstanding_dependencies, 64, "OUTSTANDING_DEPENDENCIES",
    ["what", "owner"], ["what", "owner", "ref"], row => {
      text(row.what, "DEPENDENCY_WHAT", 512, 1);
      text(row.owner, "DEPENDENCY_OWNER", PRINCIPAL_ID_MAX, 1);
      if ("ref" in row) nullableText(row.ref, "DEPENDENCY_REF", REF_MAX);
      return { what: row.what as string, owner: row.owner as string,
        ...("ref" in row ? { ref: row.ref as string | null } : {}) };
    });
  const revisionRow = exactKeys(v.source_revision, ["branch", "head"], ["branch", "head"], "SOURCE_REVISION");
  const source_revision = {
    branch: text(revisionRow.branch, "SOURCE_BRANCH", REF_MAX, 1),
    head: text(revisionRow.head, "SOURCE_HEAD", REF_MAX, 1),
  };
  const ownership = rows(v.active_work_ownership, 32, "ACTIVE_WORK_OWNERSHIP",
    ["work_ref", "owner"], ["work_ref", "owner", "lease_expires_at"], row => {
      text(row.work_ref, "WORK_REF", REF_MAX, 1);
      text(row.owner, "WORK_OWNER", PRINCIPAL_ID_MAX, 1);
      if ("lease_expires_at" in row && row.lease_expires_at !== null) {
        iso(row.lease_expires_at, "LEASE_EXPIRES_AT");
      }
      return { work_ref: row.work_ref as string, owner: row.owner as string,
        ...("lease_expires_at" in row ? { lease_expires_at: (row.lease_expires_at as string | null) } : {}) };
    });
  const unresolved = rows(v.unresolved_effects, 64, "UNRESOLVED_EFFECTS",
    ["effect_ref", "state", "rule"], ["effect_ref", "state", "rule"], row => {
      text(row.effect_ref, "EFFECT_REF", REF_MAX, 1);
      if (row.state !== "EFFECT_UNKNOWN") invalid("INVALID_EFFECT_STATE");
      text(row.rule, "EFFECT_RULE", 1024, 1);
      return { effect_ref: row.effect_ref as string, state: "EFFECT_UNKNOWN" as const, rule: row.rule as string };
    });
  text(v.next_action, "NEXT_ACTION", 1024);
  let since_packet_id: string | null | undefined;
  if ("since_packet_id" in v) {
    since_packet_id = nullableText(v.since_packet_id, "SINCE_PACKET_ID", 36);
    if (since_packet_id !== null && !packetIdPattern.test(since_packet_id)) invalid("INVALID_SINCE_PACKET_ID");
  }
  let delta: PacketDelta | undefined;
  if ("delta" in v) {
    const d = exactKeys(v.delta, [], ["added", "changed", "removed"], "PACKET_DELTA");
    delta = {};
    for (const key of ["added", "changed", "removed"] as const) {
      if (key in d) {
        const items = d[key];
        if (!Array.isArray(items)) invalid("INVALID_PACKET_DELTA");
        items.forEach(item => text(item, "PACKET_DELTA_ITEM", REF_MAX, 1));
        delta[key] = items as string[];
      }
    }
  }
  iso(v.expires_at, "PACKET_EXPIRES_AT");
  return { schema: "ContextPacket.v1", packet_id: v.packet_id as string,
    objective: v.objective as string, accepted_decisions: accepted,
    outstanding_dependencies: dependencies, source_revision,
    active_work_ownership: ownership, unresolved_effects: unresolved,
    next_action: v.next_action as string,
    ...("since_packet_id" in v ? { since_packet_id } : {}),
    ...("delta" in v ? { delta } : {}),
    expires_at: v.expires_at as string };
}

/** Deterministic message id (design §1.2): same sender + operation_key +
 * content ⇒ same id, so a duplicate delivery is the SAME message, never new
 * work. Canonical JSON keys are emitted in sorted order to match the Python
 * mint byte-for-byte (see the fixed parity vectors in both test suites).
 * Async because the web platform only exposes SHA-256 via crypto.subtle. */
export async function mintMessageId(senderId: string, operationKey: string,
                                    body: string, contextRefs: string[] = []): Promise<string> {
  const canonical = JSON.stringify({
    body, context_refs: contextRefs, operation_key: operationKey, sender: senderId,
  });
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(canonical));
  const hex = Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, "0")).join("");
  return "tlm-" + hex.slice(0, 32);
}

// Stable property order and optional/null normalization match Python's
// immutable-envelope equality. Existing v1 message IDs stay unchanged: they
// are content labels, not authentication or proof of destination authority.
function principalIdentity(value: TeamLinkPrincipal): TeamLinkPrincipal {
  return { side: value.side, id: value.id, thread_ref: value.thread_ref ?? null };
}

function immutableEnvelope(value: TeamLinkMessage) {
  const msg = parseTeamLinkMessage(value);
  return {
    schema: msg.schema, message_id: msg.message_id, operation_key: msg.operation_key,
    from: principalIdentity(msg.from), to: principalIdentity(msg.to),
    correlation: {
      root_run_ref: msg.correlation.root_run_ref ?? null,
      immediate_parent_run_ref: msg.correlation.immediate_parent_run_ref ?? null,
      logical_child_key: msg.correlation.logical_child_key ?? null,
      preview_id: msg.correlation.preview_id ?? null,
      decision_id: msg.correlation.decision_id ?? null,
      attempt_ref: msg.correlation.attempt_ref ?? null,
      fence_counter: msg.correlation.fence_counter ?? null,
      request_digest: msg.correlation.request_digest ?? null,
    },
    kind: msg.kind, intent: msg.intent, body: msg.body, context_refs: msg.context_refs,
    reply_to: msg.reply_to ?? null, max_hops: msg.max_hops, expires_at: msg.expires_at,
  };
}

/** Compare complete immutable envelopes, even if the supplied ID is copied.
 * Only hop_count/delivery_state are mutable observations. Equal identity does
 * not authorize resetting those owner observations or replaying an effect. */
export function verifyDuplicate(original: TeamLinkMessage, repeat: TeamLinkMessage):
    "same_message" | "refused_content_changed" | "different_operation_key" {
  const first = immutableEnvelope(original), second = immutableEnvelope(repeat);
  if (second.operation_key !== first.operation_key) return "different_operation_key";
  return JSON.stringify(first) === JSON.stringify(second) ? "same_message" : "refused_content_changed";
}

const deliveryRank = new Map(DELIVERY_CHAIN.map((state, index) => [state as string, index]));

/** Monotonic delivery transition (design §1.12, §4.1): same state is a no-op;
 * `unknown` may be entered from anywhere (honest terminal marker, never an
 * auto-retry) and left only for a chain state observed on the original
 * operation during reconciliation; chain→chain must move strictly forward —
 * a regression throws instead of applying. */
export function advanceDelivery(current: string, target: string): string {
  if (!deliveryStates.has(current) || !deliveryStates.has(target)) {
    invalid("INVALID_DELIVERY_STATE", `${current}->${target}`);
  }
  if (current === target) return current;
  if (target === "unknown") return target;
  if (current === "unknown") return target;
  if ((deliveryRank.get(target) ?? -1) <= (deliveryRank.get(current) ?? -1)) {
    invalid("DELIVERY_REGRESSION", `${current}->${target}`);
  }
  return target;
}

/** True when expires_at has passed (message dead / packet must be re-fetched,
 * never acted on). An unreadable expiry provides no protection ⇒ expired. */
export function isExpired(record: { expires_at?: unknown }, now: Date = new Date()): boolean {
  if (!(now instanceof Date) || !Number.isFinite(now.getTime())) return true;
  if (typeof record.expires_at !== "string" || !validIso(record.expires_at)) return true;
  const moment = Date.parse(record.expires_at);
  return Number.isNaN(moment) ? true : moment <= now.getTime();
}

/** Hop math (design §5.2, §5.6): forwarding increments hop_count; a forward
 * whose hop_count would reach max_hops is refused (hop_breach). An expired
 * message is dead even below max_hops. */
export function mayForward(message: TeamLinkMessage, now?: Date): [boolean, "hop_breach" | "expired" | ""] {
  if (isExpired(message, now)) return [false, "expired"];
  parseTeamLinkMessage(message);
  return message.hop_count + 1 >= message.max_hops ? [false, "hop_breach"] : [true, ""];
}

/** The wake gate (design §5.1): only actionable may cause a model turn;
 * informational delivery NEVER wakes either side. */
export function requiresModelTurn(message: TeamLinkMessage): boolean {
  return message.intent === "actionable";
}

/** Exact semantic mirror with both full principals reversed. Independent
 * operations, threads or content are not echoes. The sender-dependent ID and
 * mutable transport observations are excluded; hop limits bound other loops. */
export function isPingPongEcho(sent: TeamLinkMessage, received: TeamLinkMessage): boolean {
  const { message_id: _sentId, ...first } = immutableEnvelope(sent);
  const { message_id: _receivedId, ...second } = immutableEnvelope(received);
  [first.from, first.to] = [first.to, first.from];
  return JSON.stringify(first) === JSON.stringify(second);
}

/** Answers settle (design §5.4): after question → answer the subject is
 * closed; a follow-up on the same subject is lawful only under a NEW
 * operation_key. Returns true when the follow-up reuses the settled key. */
export function followupRequiresNewKey(settledQuestion: TeamLinkMessage, followUp: TeamLinkMessage): boolean {
  return followUp.operation_key === settledQuestion.operation_key;
}
