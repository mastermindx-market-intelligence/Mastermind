/**
 * Exact Workspace Control Room action framing. The enrolled Workspace owner
 * authorizes individual actions; this pure browser module never grants them.
 * It retains the original owner result or conservative effect uncertainty.
 */
export const CONTROL_ROOM_REQUEST_BYTES = 8192;
export const CONTROL_ROOM_RESPONSE_BYTES = 2_000_000;
export const CONTROL_ROOM_UNKNOWN_OUTCOME = Object.freeze({
  ok: false,
  failure_kind: "effect_unknown",
  detail: "The action may have run. Read current state and reconcile its original target before deciding what to do next.",
  next_action: "read_current_state",
  retryable: false,
});
export type ControlRoomOperation = "open" | "bind" | "unbind" | "refresh-builds";
export type ControlRoomDisposition = "NOT_DISPATCHED" | "OWNER_RETURNED" | "EFFECT_UNKNOWN";
export type ControlRoomActionResult = Readonly<{
  schema: "mastermind.workspace_control_room_action_result.v1";
  operation: ControlRoomOperation;
  status: number;
  disposition: ControlRoomDisposition;
  outcome: Readonly<Record<string, unknown>>;
}>;

const operations = new Set<ControlRoomOperation>(["open", "bind", "unbind", "refresh-builds"]);
const own = (v: object, k: string) => Object.prototype.hasOwnProperty.call(v, k);
const record = (v: unknown): v is Record<string, unknown> =>
  v !== null && typeof v === "object" && !Array.isArray(v);
const unicode = (v: string) => {
  for (let i = 0; i < v.length; i++) {
    const code = v.charCodeAt(i);
    if (code >= 0xd800 && code <= 0xdbff) {
      if (i + 1 >= v.length || v.charCodeAt(i + 1) < 0xdc00 || v.charCodeAt(i + 1) > 0xdfff)
        return false;
      i++;
    } else if (code >= 0xdc00 && code <= 0xdfff) return false;
  }
  return true;
};
function invalid(): never { throw new Error("CONTROL_ROOM_ACTION_INVALID"); }
function strictJsonValue(value: unknown, visited = { count: 0 }, depth = 0): void {
  if (++visited.count > 10000 || depth > 48) invalid();
  if (value === null || typeof value === "boolean") return;
  if (typeof value === "string") { if (!unicode(value)) invalid(); return; }
  if (typeof value === "number") { if (!Number.isFinite(value)) invalid(); return; }
  if (typeof value !== "object") throw new Error("CONTROL_ROOM_ACTION_INVALID");
  if (Array.isArray(value)) {
    if (Reflect.ownKeys(value).length !== value.length + 1
        || Object.keys(value).length !== value.length) invalid();
    for (let i = 0; i < value.length; i++) {
      const desc = Object.getOwnPropertyDescriptor(value, String(i));
      if (!desc || !own(desc, "value")) throw new Error("CONTROL_ROOM_ACTION_INVALID");
      strictJsonValue(desc.value, visited, depth + 1);
    }
    return;
  }
  if (Object.getPrototypeOf(value) !== Object.prototype
      && Object.getPrototypeOf(value) !== null) invalid();
  for (const key of Reflect.ownKeys(value)) {
    if (typeof key !== "string" || !unicode(key)) invalid();
    const desc = Object.getOwnPropertyDescriptor(value, key);
    if (!desc || !own(desc, "value") || !desc.enumerable) invalid();
    strictJsonValue(desc.value, visited, depth + 1);
  }
}
function freezeJson<T>(value: T): T {
  if (value !== null && typeof value === "object") {
    Object.values(value).forEach(freezeJson);
    Object.freeze(value);
  }
  return value;
}
function detached<T>(value: T, ceiling: number): T {
  strictJsonValue(value);
  const wire = JSON.stringify(value);
  if (new TextEncoder().encode(wire).length + 1 > ceiling) invalid();
  return freezeJson(JSON.parse(wire)) as T;
}
function exact(value: Record<string, unknown>, keys: readonly string[]) {
  return Object.keys(value).length === keys.length && keys.every(k => own(value, k));
}
export class ControlRoomActionTransportError extends Error {
  readonly operation: ControlRoomOperation;
  readonly disposition: "NOT_DISPATCHED" | "EFFECT_UNKNOWN";
  constructor(operation: ControlRoomOperation, disposition: "NOT_DISPATCHED" | "EFFECT_UNKNOWN") {
    super("CONTROL_ROOM_ACTION_" + disposition);
    this.name = "ControlRoomActionTransportError";
    this.operation = operation;
    this.disposition = disposition;
    Object.freeze(this);
  }
}
export function decodeControlRoomActionPayload<T extends Record<string, unknown>>(
  value: T, operation: ControlRoomOperation,
): Readonly<T>;
export function decodeControlRoomActionPayload(
  value: unknown, operation: ControlRoomOperation,
): Readonly<Record<string, unknown>>;
export function decodeControlRoomActionPayload(
  value: unknown, operation: ControlRoomOperation,
): Readonly<Record<string, unknown>> {
  if (!operations.has(operation) || !record(value)) invalid();
  // Inspect descriptors before touching any property: a request can contain getters.
  strictJsonValue(value);
  const v = value as Record<string, unknown>, keys = Object.keys(v);
  if (operation === "open" || operation === "unbind") {
    if (typeof v.binding_id !== "string" || !v.binding_id) invalid();
    const allowed = operation === "open" ?
      ["binding_id", "target_surface", "owed_context"] : ["binding_id"];
    if (keys.some(k => !allowed.includes(k))) invalid();
    if (operation === "open" && v.target_surface != null
        && v.target_surface !== "default" && v.target_surface !== "desktop") invalid();
  } else if (operation === "bind") {
    if (!["work_ref", "role", "provider", "locator"].every(k => own(v, k))
        || keys.some(k => !["work_ref", "role", "provider", "locator", "seat_ref"].includes(k))
        || ["work_ref", "role", "provider"].some(k => typeof v[k] !== "string")
        || !record(v.locator) || (v.seat_ref != null && typeof v.seat_ref !== "string")) invalid();
  } else if (keys.length !== 0) invalid();
  return detached(v, CONTROL_ROOM_REQUEST_BYTES);
}
export function decodeControlRoomActionResult(
  value: unknown, operation: ControlRoomOperation, status: number,
): ControlRoomActionResult {
  if (!operations.has(operation) || !record(value)
      || !exact(value, ["schema", "operation", "status", "disposition", "outcome"])
      || value.schema !== "mastermind.workspace_control_room_action_result.v1"
      || value.operation !== operation
      || typeof value.status !== "number" || !Number.isInteger(value.status)
      || value.status !== status || !record(value.outcome)
      || !["NOT_DISPATCHED", "OWNER_RETURNED", "EFFECT_UNKNOWN"].includes(String(value.disposition)))
    invalid();
  const v = value as unknown as ControlRoomActionResult;
  if (v.disposition === "OWNER_RETURNED") {
    if (status !== 200) invalid();
  } else if (v.disposition === "NOT_DISPATCHED") {
    if (![400, 403, 409, 503].includes(status) || v.outcome.failure_kind === "effect_unknown")
      invalid();
  } else if (status !== 503
      || !exact(v.outcome, Object.keys(CONTROL_ROOM_UNKNOWN_OUTCOME))
      || Object.entries(CONTROL_ROOM_UNKNOWN_OUTCOME).some(([key, expected]) => v.outcome[key] !== expected)) {
    invalid();
  }
  return detached(v, CONTROL_ROOM_RESPONSE_BYTES);
}
export function controlRoomActionIsUncertain(value: ControlRoomActionResult): boolean {
  return value.disposition === "EFFECT_UNKNOWN" || value.outcome.failure_kind === "effect_unknown";
}

/** Scan each actual JSON object key before JSON.parse can collapse duplicates. */
function uniqueJson(raw: string): unknown {
  let i = 0, count = 0;
  const ws = () => { while (i < raw.length && /[\x20\t\r\n]/.test(raw[i]!)) i++; };
  const quoted = (): string => {
    if (raw[i] !== '"') invalid();
    const begin = i++;
    while (i < raw.length) {
      const char = raw[i++]!;
      if (char === '"') return JSON.parse(raw.slice(begin, i)) as string;
      if (char === "\\") {
        if (i >= raw.length) invalid();
        const esc = raw[i++]!;
        if (esc === "u") {
          if (!/^[0-9a-fA-F]{4}$/.test(raw.slice(i, i + 4))) invalid();
          i += 4;
        } else if (!'"\\/bfnrt'.includes(esc)) invalid();
      } else if (char.charCodeAt(0) < 32) invalid();
    }
    return invalid();
  };
  const parseValue = (depth: number): void => {
    if (depth > 48 || ++count > 10000) invalid();
    ws();
    if (raw[i] === "{") {
      i++; ws();
      const seen = new Set<string>();
      if (raw[i] === "}") { i++; return; }
      while (true) {
        ws();
        const key = quoted();
        if (!unicode(key) || seen.has(key)) invalid();
        seen.add(key);
        ws(); if (raw[i++] !== ":") invalid();
        parseValue(depth + 1);
        ws();
        const end = raw[i++];
        if (end === "}") break;
        if (end !== ",") invalid();
      }
      return;
    }
    if (raw[i] === "[") {
      i++; ws();
      if (raw[i] === "]") { i++; return; }
      while (true) {
        parseValue(depth + 1);
        ws();
        const end = raw[i++];
        if (end === "]") break;
        if (end !== ",") invalid();
      }
      return;
    }
    if (raw[i] === '"') { quoted(); return; }
    const remainder = raw.slice(i);
    const word = /^(?:true|false|null)/.exec(remainder);
    if (word) { i += word[0].length; return; }
    const number = /^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?/.exec(remainder);
    if (!number || !Number.isFinite(Number(number[0]))) throw new Error("CONTROL_ROOM_ACTION_INVALID");
    i += number[0].length;
  };
  parseValue(0);
  ws(); if (i !== raw.length) invalid();
  const parsed = JSON.parse(raw) as unknown;
  strictJsonValue(parsed);
  return parsed;
}
export function decodeControlRoomActionJson(
  raw: Uint8Array, operation: ControlRoomOperation, status: number,
): ControlRoomActionResult {
  try {
    if (!(raw instanceof Uint8Array) || raw.length === 0
        || raw.length > CONTROL_ROOM_RESPONSE_BYTES) invalid();
    const text = new TextDecoder("utf-8", { fatal: true, ignoreBOM: true }).decode(raw);
    return decodeControlRoomActionResult(uniqueJson(text), operation, status);
  } catch {
    throw new Error("CONTROL_ROOM_ACTION_RESPONSE_INVALID");
  }
}
