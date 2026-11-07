import { describe, expect, it } from "vitest";
import { closedReadFailurePhase, closedReadFailureReason, decodeMissionDiagnostics } from "./diagnostic-state";

const mission = {
  hostKind: "native",
  launchConfigured: true,
  frontendResourceConfigured: true,
  nativeResourceConfigured: null,
  acquisitionAvailable: true,
  contentAvailable: false,
  executiveAvailable: true,
  executiveContextPhase: "ready",
};
const opaque = (): object => new (class Hidden { constructor() { (this as { id?: number }).id = 1; } })();

describe("closed mission diagnostics codec", () => {
  it("accepts exactly the frozen plain snapshot shape", () => {
    expect(decodeMissionDiagnostics(mission)).toEqual(mission);
    expect(decodeMissionDiagnostics({
      ...mission, hostKind: "web", executiveContextPhase: "unknown",
      launchConfigured: null, frontendResourceConfigured: null,
      nativeResourceConfigured: null, acquisitionAvailable: null,
      contentAvailable: null, executiveAvailable: null,
    })).toEqual({
      hostKind: "web", launchConfigured: null, frontendResourceConfigured: null,
      nativeResourceConfigured: null, acquisitionAvailable: null, contentAvailable: null,
      executiveAvailable: null, executiveContextPhase: "unknown",
    });
    expect(decodeMissionDiagnostics({
      ...mission, executiveContextPhase: "not_requested",
    })?.executiveContextPhase).toBe("not_requested");
  });
  it("rejects non-plain, extra, missing and mistyped payloads", () => {
    for (const invalid of [
      null, undefined, 0, 7, true, "native", "",
      [], [mission],
      { ...mission, extra: 1 },
      (() => { const { launchConfigured: _dropped, ...rest } = mission; return rest; })(),
      { ...mission, hostKind: "firmware" },
      { ...mission, hostKind: undefined },
      { ...mission, executiveContextPhase: "queued" },
      { ...mission, executiveContextPhase: null },
      { ...mission, executiveAvailable: "true" },
      { ...mission, nativeResourceConfigured: 0 },
      { ...mission, launchConfigured: undefined },
      { ...mission, contentAvailable: 1 },
      Object.assign(opaque(), mission),
      Object.assign(Object.create({ inherited: true }), mission),
    ])
      expect(decodeMissionDiagnostics(invalid)).toBeNull();
  });
  it("rejects own enumerable masquerading keys instead of reading prototype members", () => {
    const reordered: Record<string, unknown> = { ...mission };
    delete reordered.hostKind; reordered.hostKind = "native";
    expect(decodeMissionDiagnostics(reordered)).toEqual(mission);
    for (const key of ["constructor", "toString", "__proto__"]) {
      const forged: Record<string, unknown> = { ...mission };
      delete forged.executiveAvailable;
      Object.defineProperty(forged, key, { value: mission.executiveAvailable, enumerable: true, configurable: true });
      expect(forged.executiveAvailable).toBeUndefined();
      expect(decodeMissionDiagnostics(forged)).toBeNull();
    }
  });
});

describe("closed read failure phase", () => {
  it("maps only exact native closed codes", () => {
    expect(closedReadFailurePhase("AUTHENTICATION_REQUIRED")).toBe("auth_unavailable");
    expect(closedReadFailurePhase("SOURCE_UNAVAILABLE")).toBe("transport_failure");
    expect(closedReadFailurePhase("ACCESS_REFUSED")).toBe("transport_failure");
    expect(closedReadFailurePhase("SELECTION_UNAVAILABLE")).toBe("transport_failure");
    expect(closedReadFailurePhase("RESPONSE_INVALID")).toBe("invalid_response");
    expect(closedReadFailurePhase("RESPONSE_BOUND")).toBe("invalid_response");
    expect(closedReadFailurePhase("AUTHENTICATION_CHANGED")).toBe("unknown");
    expect(closedReadFailurePhase("READ_CANCELLED")).toBe("unknown");
  });
  it("maps only exact local sentinel messages and keeps private text unknown", () => {
    expect(closedReadFailurePhase(new Error("EXECUTIVE_TRANSPORT_UNAVAILABLE"))).toBe("transport_failure");
    expect(closedReadFailurePhase(new Error("EXECUTIVE_AUTH_CHANGED"))).toBe("unknown");
    expect(closedReadFailurePhase(new Error("EXECUTIVE_UNAVAILABLE"))).toBe("unknown");
    expect(closedReadFailurePhase(new Error("AUTHENTICATION_REQUIRED"))).toBe("auth_unavailable");
    expect(closedReadFailurePhase(Object.assign(new Error("private refusal"), { name: "PrivateError" })))
      .toBe("unknown");
    for (const privateReason of [
      new Error("native missing"), new Error(""), new Error("AUTHENTICATION_REQUIRED "),
      new Error("authentication_required"), "authentication_required", "AUTHENTICATION_REQUIRED\n",
      { message: "AUTHENTICATION_REQUIRED" }, { code: "ACCESS_REFUSED" },
      { }, 7, null, undefined, ["SOURCE_UNAVAILABLE"],
    ])
      expect(closedReadFailurePhase(privateReason)).toBe("unknown");
  });
});


describe("native status phase stays separate from owner-context phase", () => {
  it("accepts only an optional closed auth-status phase and rejects private values", () => {
    expect(decodeMissionDiagnostics({ ...mission, executiveTransportPhase: "transport_failure" }))
      .toEqual({ ...mission, executiveTransportPhase: "transport_failure" });
    expect(decodeMissionDiagnostics({ ...mission, executiveTransportPhase: "PRIVATE account URL" })).toBeNull();
    expect(decodeMissionDiagnostics({ ...mission, executiveTransportPhase: false })).toBeNull();
  });
});


it("retains only known read reason codes and rejects private diagnostic reason fields", () => {
  expect(closedReadFailureReason("ACCESS_REFUSED")).toBe("ACCESS_REFUSED");
  expect(closedReadFailureReason(new Error("PROGRAM_RESPONSE_INVALID"))).toBe("PROGRAM_RESPONSE_INVALID");
  expect(closedReadFailureReason(new Error("PRIVATE account credential"))).toBe("UNKNOWN");
  expect(decodeMissionDiagnostics({ ...mission, executiveReadReason: "ACCESS_REFUSED" })?.executiveReadReason).toBe("ACCESS_REFUSED");
  expect(decodeMissionDiagnostics({ ...mission, executiveReadReason: "PRIVATE account credential" })).toBeNull();
});
