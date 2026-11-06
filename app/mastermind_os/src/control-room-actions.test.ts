import { describe, expect, it } from "vitest";
import {
  CONTROL_ROOM_REQUEST_BYTES,
  CONTROL_ROOM_UNKNOWN_OUTCOME,
  ControlRoomActionTransportError,
  controlRoomActionIsUncertain,
  decodeControlRoomActionJson,
  decodeControlRoomActionPayload,
  decodeControlRoomActionResult,
  type ControlRoomOperation,
} from "./control-room";
import { MAX_RESPONSE_BYTES } from "./public-config";

const result = (operation: ControlRoomOperation = "open", status = 200,
  disposition = "OWNER_RETURNED", outcome: unknown = { ok: true }) => ({
  schema: "mastermind.workspace_control_room_action_result.v1",
  operation, status, disposition, outcome,
});
const encode = (value: unknown) => new TextEncoder().encode(JSON.stringify(value));

describe("Control Room action payloads retain the original owner contract", () => {
  it.each([null, false, [], { malformed: true }].map(owed => [owed]))(
    "retains present owed context %j for the original owner to refuse", owed => {
      const value = decodeControlRoomActionPayload(
        { binding_id: "original", owed_context: owed, target_surface: null }, "open");
      expect(value).toEqual({ binding_id: "original", owed_context: owed, target_surface: null });
      expect(Object.hasOwn(value, "owed_context")).toBe(true);
      expect(Object.isFrozen(value)).toBe(true);
    });
  it("does not fabricate owed context when absent", () => {
    const value = decodeControlRoomActionPayload({ binding_id: "original" }, "open");
    expect(Object.hasOwn(value, "owed_context")).toBe(false);
  });
  it("detaches locator data and leaves semantic provider validation to its owner", () => {
    const input = { work_ref: "", role: "owner-validates", provider: "owner-validates",
      locator: { nested: ["original"] }, seat_ref: null };
    const value = decodeControlRoomActionPayload(input, "bind");
    input.locator.nested[0] = "changed";
    expect(value).toEqual({ ...input, locator: { nested: ["original"] } });
    expect(Object.isFrozen(value.locator)).toBe(true);
    expect(Object.isFrozen(value.locator.nested)).toBe(true);
  });
  it.each([
    ["open", {}], ["open", { binding_id: "" }],
    ["open", { binding_id: "original", extra: true }],
    ["open", { binding_id: "original", target_surface: "browser" }],
    ["unbind", { binding_id: "original", owed_context: null }],
    ["bind", { work_ref: "WS:ONE", role: "worker", provider: "codex", locator: [] }],
    ["bind", { work_ref: "WS:ONE", role: "worker", provider: "codex", locator: {}, seat_ref: 4 }],
    ["refresh-builds", { refresh: true }],
  ])("refuses a malformed %s payload before a caller can invoke transport", (operation, payload) => {
    expect(() => decodeControlRoomActionPayload(payload, operation as ControlRoomOperation)).toThrow();
  });
  it("accepts only the empty refresh payload and exact Unbind selector", () => {
    expect(decodeControlRoomActionPayload({}, "refresh-builds")).toEqual({});
    expect(decodeControlRoomActionPayload({ binding_id: "original" }, "unbind"))
      .toEqual({ binding_id: "original" });
  });
  it.each([undefined, NaN, Infinity, "\ud800"])("refuses lossy JSON %s rather than stripping it", value => {
    expect(() => decodeControlRoomActionPayload(
      { binding_id: "original", owed_context: value }, "open")).toThrow();
  });
  it("refuses getters without executing them, symbols, cycles and sparse arrays", () => {
    let calls = 0;
    const getter = Object.defineProperty({}, "binding_id", { enumerable: true,
      get() { calls++; return "original"; } });
    expect(() => decodeControlRoomActionPayload(getter, "open")).toThrow();
    expect(calls).toBe(0);
    const symbol = { binding_id: "original", [Symbol("hidden")]: true };
    const cycle: Record<string, unknown> = {}; cycle.self = cycle;
    for (const payload of [symbol, { binding_id: "original", owed_context: cycle },
      { binding_id: "original", owed_context: new Array(2) }]) {
      expect(() => decodeControlRoomActionPayload(payload, "open")).toThrow();
    }
  });
  it("bounds encoded input including its line allowance", () => {
    expect(() => decodeControlRoomActionPayload(
      { binding_id: "x".repeat(CONTROL_ROOM_REQUEST_BYTES) }, "open")).toThrow();
  });
});

describe("Control Room action results keep transport and owner facts distinct", () => {
  it.each([true, false])("retains an original owner return with ok=%s", ok => {
    const body = result("open", 200, "OWNER_RETURNED", { ok, detail: "original" });
    const decoded = decodeControlRoomActionResult(body, "open", 200);
    expect(decoded).toEqual(body);
    expect(Object.isFrozen(decoded)).toBe(true);
    expect(Object.isFrozen(decoded.outcome)).toBe(true);
  });
  it("retains qualified 409 and exact unknown responses at their real HTTP status", () => {
    const refused = result("open", 409, "NOT_DISPATCHED",
      { ok: false, failure_kind: "source_precondition_failed", next_action: "read_current_state" });
    expect(decodeControlRoomActionResult(refused, "open", 409)).toEqual(refused);
    const unknown = result("open", 503, "EFFECT_UNKNOWN", CONTROL_ROOM_UNKNOWN_OUTCOME);
    expect(decodeControlRoomActionResult(unknown, "open", 503)).toEqual(unknown);
  });
  it.each([
    result("bind"), { ...result(), status: true },
    { ...result(), extra: true }, { ...result(), schema: "other" },
    result("open", 503, "OWNER_RETURNED"),
    result("open", 200, "NOT_DISPATCHED"),
    result("open", 403, "NOT_DISPATCHED", { failure_kind: "effect_unknown" }),
    result("open", 503, "EFFECT_UNKNOWN", { ...CONTROL_ROOM_UNKNOWN_OUTCOME, retryable: true }),
    result("open", 200, "OWNER_RETURNED", []),
  ])("rejects an invalid or differently named owner result", body => {
    expect(() => decodeControlRoomActionResult(body, "open", body.status as number)).toThrow();
  });
  it("rejects disagreement between HTTP status and body status", () => {
    expect(() => decodeControlRoomActionResult(result(), "open", 503)).toThrow();
  });
  it("does not mistake a provider uncertainty inside OWNER_RETURNED for success", () => {
    const decoded = decodeControlRoomActionResult(result("open", 200, "OWNER_RETURNED",
      { ok: false, failure_kind: "effect_unknown" }), "open", 200);
    expect(controlRoomActionIsUncertain(decoded)).toBe(true);
    expect(controlRoomActionIsUncertain(decodeControlRoomActionResult(result(), "open", 200))).toBe(false);
  });
  it("keeps local transport facts separate from a server receipt", () => {
    const local = new ControlRoomActionTransportError("open", "EFFECT_UNKNOWN");
    expect(local).toBeInstanceOf(Error);
    expect(local).toMatchObject({ operation: "open", disposition: "EFFECT_UNKNOWN" });
    expect(Object.hasOwn(local, "schema")).toBe(false);
    expect(Object.isFrozen(local)).toBe(true);
  });
});

describe("original bounded action response bytes", () => {
  it("accepts strict UTF-8 and valid escaped scalar text", () => {
    const body = result("open", 200, "OWNER_RETURNED", { detail: 'quote " and 😀', ok: true });
    expect(decodeControlRoomActionJson(encode(body), "open", 200)).toEqual(body);
  });
  it.each([
    '{"operation":"bind","operation":"open"}',
    '{"operation":"bind","oper\\u0061tion":"open"}',
    JSON.stringify(result()).replace('"ok":true', '"ok":false,"ok":true'),
    JSON.stringify(result()).replace('"ok":true', '"ok":false,"\\u006fk":true'),
    JSON.stringify(result()).replace('"ok":true', '"number":1e309'),
    JSON.stringify(result()).replace('"ok":true', '"text":"\\ud800"'),
    JSON.stringify(result()).replace('"ok":true', '"\\udfff":true'),
    JSON.stringify(result()) + " trailing",
    "\ufeff" + JSON.stringify(result()),
    "",
  ])("refuses ambiguous or invalid raw JSON without a qualified receipt", text => {
    expect(() => decodeControlRoomActionJson(new TextEncoder().encode(text), "open", 200)).toThrow();
  });
  it("refuses invalid UTF-8 and excessive original bytes", () => {
    expect(() => decodeControlRoomActionJson(new Uint8Array([0xc3, 0x28]), "open", 200)).toThrow();
    expect(() => decodeControlRoomActionJson(new Uint8Array(MAX_RESPONSE_BYTES + 1), "open", 200)).toThrow();
  });
  it("preserves prototype-named properties as ordinary JSON data", () => {
    const body = JSON.stringify(result()).replace('"ok":true', '"__proto__":{"reported":true}');
    const decoded = decodeControlRoomActionJson(new TextEncoder().encode(body), "open", 200);
    expect(Object.hasOwn(decoded.outcome, "__proto__")).toBe(true);
    expect(Object.hasOwn(decoded.outcome, "reported")).toBe(false);
  });
});
