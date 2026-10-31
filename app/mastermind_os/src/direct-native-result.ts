/** Closed H2 display DATA; parsing grants no access or consumption. */
import { canonicalJson, sha256Hex } from "./orchestration/operation-key";
export const DIRECT_RESULT_BYTES = 24576;
export type DirectSelection = {
  work_ref: string;
  job_id: string;
  attempt_id: string | null;
};
export type DirectTerminalSelection = DirectSelection & { attempt_id: string };
export type DirectConsumption =
  | { state: "UNCONSUMED"; receipt_digest: null }
  | { state: "CONSUMED"; receipt_digest: string };
export type DirectResult = {
  schema: "mastermind.direct_native_result_response.v1";
  selection: DirectSelection;
  availability: "AVAILABLE" | "UNAVAILABLE";
  reason_codes: string[];
  result: null | {
    result_digest: string;
    summary: string;
    current_state: string;
    completed_steps: string[];
    next_actions: string[];
  };
  consumption: DirectConsumption | null;
};
export interface DirectNativeTransport {
  read(selection: DirectSelection, signal: AbortSignal): Promise<unknown>;
  consume(
    request: DirectTerminalSelection & {
      result_digest: string;
      operation_key: string;
    },
    signal: AbortSignal,
  ): Promise<unknown>;
}
const id = (v: unknown): v is string =>
  typeof v === "string" && /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(v);
const hash = (v: unknown): v is string =>
  typeof v === "string" && /^[0-9a-f]{64}$/.test(v);
const object = (v: unknown): v is Record<string, unknown> =>
  typeof v === "object" &&
  v !== null &&
  (Object.getPrototypeOf(v) === Object.prototype ||
    Object.getPrototypeOf(v) === null);
const exact = (v: Record<string, unknown>, keys: string[]) =>
  Object.keys(v).length === keys.length &&
  keys.every((k) => Object.hasOwn(v, k));
function text(v: unknown, limit: number, content = false): v is string {
  return (
    typeof v === "string" &&
    [...v].length <= limit &&
    (content || (v.length > 0 && v.trim() === v)) &&
    ![...v].some((c) => {
      const n = c.codePointAt(0)!;
      return (
        (n < 32 && !(content && (c === "\n" || c === "\t"))) ||
        n === 127 ||
        (n >= 0xd800 && n <= 0xdfff)
      );
    })
  );
}
export function normalizeDirectSelection(v: unknown): DirectSelection | null {
  if (
    !object(v) ||
    !exact(v, ["work_ref", "job_id", "attempt_id"]) ||
    !text(v.work_ref, 512) ||
    !id(v.job_id) ||
    (v.attempt_id !== null && !id(v.attempt_id))
  )
    return null;
  return {
    work_ref: v.work_ref,
    job_id: v.job_id,
    attempt_id: v.attempt_id as string | null,
  };
}
const REASONS = new Set([
  "INVALID_SELECTION",
  "AUTHORITY_UNAVAILABLE",
  "SOURCE_UNAVAILABLE",
  "NOT_TERMINAL",
  "CONTENT_OVER_BUDGET",
  "CONSUMPTION_CONFLICT",
  "EFFECT_UNKNOWN",
]);
export function decodeDirectNativeResult(
  value: unknown,
  expected?: DirectSelection,
): DirectResult | null {
  try {
    if (
      !object(value) ||
      !exact(value, [
        "schema",
        "selection",
        "availability",
        "reason_codes",
        "result",
        "consumption",
      ]) ||
      value.schema !== "mastermind.direct_native_result_response.v1"
    )
      return null;
    const selection = normalizeDirectSelection(value.selection);
    if (
      !selection ||
      (expected &&
        (selection.work_ref !== expected.work_ref ||
          selection.job_id !== expected.job_id ||
          (expected.attempt_id !== null &&
            selection.attempt_id !== expected.attempt_id))) ||
      !Array.isArray(value.reason_codes)
    )
      return null;
    if (value.availability === "AVAILABLE") {
      const r = value.result,
        c = value.consumption;
      if (
        selection.attempt_id === null ||
        value.reason_codes.length ||
        !object(r) ||
        !exact(r, [
          "result_digest",
          "summary",
          "current_state",
          "completed_steps",
          "next_actions",
        ]) ||
        !hash(r.result_digest) ||
        !text(r.summary, 4096, true) ||
        !text(r.current_state, 4096, true) ||
        ![r.completed_steps, r.next_actions].every(
          (v) =>
            Array.isArray(v) &&
            v.length <= 32 &&
            v.every((s) => text(s, 256, true)),
        ) ||
        !object(c) ||
        !exact(c, ["state", "receipt_digest"]) ||
        !(
          (c.state === "UNCONSUMED" && c.receipt_digest === null) ||
          (c.state === "CONSUMED" && hash(c.receipt_digest))
        )
      )
        return null;
    } else if (value.availability === "UNAVAILABLE") {
      const r = value.reason_codes;
      if (
        !r.length ||
        r.length > REASONS.size ||
        new Set(r).size !== r.length ||
        !r.every((x) => typeof x === "string" && REASONS.has(x)) ||
        value.result !== null ||
        value.consumption !== null
      )
        return null;
    } else return null;
    const raw = canonicalJson(value);
    if (new TextEncoder().encode(raw).byteLength > DIRECT_RESULT_BYTES)
      return null;
    return JSON.parse(raw) as DirectResult;
  } catch {
    return null;
  }
}
/** Duplicate-key-aware finite parser for new direct routes only. */
export function parseDirectNativeJson(raw: string): unknown {
  if (new TextEncoder().encode(raw).byteLength > DIRECT_RESULT_BYTES)
    throw Error("DIRECT_RESULT_INVALID");
  let at = 0;
  const fail = (): never => {
    throw Error("DIRECT_RESULT_INVALID");
  };
  const space = () => {
    while (at < raw.length && /[ \t\n\r]/.test(raw[at])) at++;
  };
  function string(): string {
    const start = at++;
    while (at < raw.length) {
      const c = raw[at++];
      if (c === '"') return JSON.parse(raw.slice(start, at));
      if (c === "\\") at++;
    }
    return fail();
  }
  function value(depth: number): unknown {
    if (depth > 32) return fail();
    space();
    const c = raw[at];
    if (c === '"') return string();
    if (c === "{") {
      at++;
      space();
      const out: Record<string, unknown> = Object.create(null);
      if (raw[at] === "}") {
        at++;
        return out;
      }
      while (at < raw.length) {
        space();
        if (raw[at] !== '"') return fail();
        const k = string();
        if (Object.hasOwn(out, k)) return fail();
        space();
        if (raw[at++] !== ":") return fail();
        out[k] = value(depth + 1);
        space();
        const end = raw[at++];
        if (end === "}") return out;
        if (end !== ",") return fail();
      }
      return fail();
    }
    if (c === "[") {
      at++;
      space();
      const out: unknown[] = [];
      if (raw[at] === "]") {
        at++;
        return out;
      }
      while (at < raw.length) {
        out.push(value(depth + 1));
        space();
        const end = raw[at++];
        if (end === "]") return out;
        if (end !== ",") return fail();
      }
      return fail();
    }
    for (const [literal, v] of [
      ["true", true],
      ["false", false],
      ["null", null],
    ] as const) {
      if (raw.startsWith(literal, at)) {
        at += literal.length;
        return v;
      }
    }
    const n = raw
      .slice(at)
      .match(/^-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?/);
    if (!n) return fail();
    at += n[0].length;
    const number = Number(n[0]);
    if (!Number.isFinite(number)) return fail();
    return number;
  }
  const result = value(0);
  space();
  if (at !== raw.length) return fail();
  return result;
}
export function directConsumeIdentity(
  scope: string,
  selection: DirectTerminalSelection,
  digest: string,
) {
  if (
    !hash(scope) ||
    !normalizeDirectSelection(selection) ||
    !id(selection.attempt_id) ||
    !hash(digest)
  )
    throw Error("DIRECT_SELECTION_INVALID");
  return {
    operationKey: `mmos-consume-${sha256Hex(canonicalJson({ schema: "mastermind.direct_native_consume_pointer.v1", principal_scope: scope, ...selection, result_digest: digest })).slice(0, 40)}`,
    kind: "consume" as const,
    targetKey: canonicalJson({ ...selection, result_digest: digest }),
  };
}
export function parseDirectConsumeTarget(
  raw: unknown,
): (DirectTerminalSelection & { result_digest: string }) | null {
  try {
    if (
      typeof raw !== "string" ||
      new TextEncoder().encode(raw).byteLength > 4096
    )
      return null;
    const v = parseDirectNativeJson(raw);
    if (
      !object(v) ||
      !exact(v, ["work_ref", "job_id", "attempt_id", "result_digest"]) ||
      !hash(v.result_digest)
    )
      return null;
    const s = normalizeDirectSelection({
      work_ref: v.work_ref,
      job_id: v.job_id,
      attempt_id: v.attempt_id,
    });
    if (!s || s.attempt_id === null || canonicalJson(v) !== raw) return null;
    return { ...s, attempt_id: s.attempt_id, result_digest: v.result_digest };
  } catch {
    return null;
  }
}
