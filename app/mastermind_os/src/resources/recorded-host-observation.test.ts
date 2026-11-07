import { describe, expect, it } from "vitest";
import fixture from "./fixtures/recorded-host-observation-owner.json";
import { decodeHostObservationRead } from "./recorded-host-observation";
const clone = () => structuredClone(fixture);
describe("actual retained Darwin capture read", () => {
  it("decodes the actual inert Python owner bytes as recorded physical host only", () => {
    const result = decodeHostObservationRead(fixture, fixture.selection);
    expect(result.state).toBe("AVAILABLE");
    if (result.state !== "AVAILABLE") return;
    expect(result.document.platform).toBe("darwin");
    expect(result.document.observed_host_role).toBe("PHYSICAL_RESOURCE_HOST");
    expect(result.document.can_place_work).toBe(false);
    expect(Object.isFrozen(result.document.snapshot)).toBe(true);
    expect(result.document.snapshot).not.toHaveProperty("namespace_sha256");
  });
  it.each(["platform", "role", "grant", "age", "clock", "source", "scope", "foreign", "receipt", "unknown", "bounds", "unsafe", "missing"])("refuses altered %s facts", fault => {
    const v = clone() as any;
    if (fault === "platform") v.observation.platform = "linux";
    if (fault === "role") v.observation.observed_host_role = "REMOTE_WORKER";
    if (fault === "grant") v.observation.can_place_work = true;
    if (fault === "age") v.observation.age_ms++;
    if (fault === "clock") v.observation.capture_decision_at_ms += 1000;
    if (fault === "source") v.observation.source.commit_sha = "a".repeat(40) + "\n";
    if (fault === "scope") v.observation.snapshot.namespace_sha256 = "a".repeat(64);
    if (fault === "foreign") v.selection.root_job_id = "JOB-foreign";
    if (fault === "receipt") v.source_observation.runtime.after++;
    if (fault === "unknown") v.observation.snapshot.pool_free_bytes = null;
    if (fault === "bounds") v.observation.snapshot.pool_free_bytes = v.observation.snapshot.pool_total_bytes + 1;
    if (fault === "unsafe") v.observation.snapshot.vm_free_pages = 2 ** 53;
    if (fault === "missing") delete v.observation.source.helper_sha256;
    expect(() => decodeHostObservationRead(v, fixture.selection)).toThrow("HOST_OBSERVATION_INVALID");
  });
  it("rejects getters and foreign prototypes without executing display hooks", () => {
    let called = 0;
    const v = clone();
    Object.defineProperty(v.observation, "source", { enumerable: true, get() { called++; return {}; } });
    expect(() => decodeHostObservationRead(v, fixture.selection)).toThrow();
    expect(called).toBe(0);
    const prototype = Object.create({});
    Object.assign(prototype, clone());
    expect(() => decodeHostObservationRead(prototype, fixture.selection)).toThrow();
    expect(() => decodeHostObservationRead(new Proxy({}, { getPrototypeOf() { throw Error("foreign"); } }), fixture.selection)).toThrow("HOST_OBSERVATION_INVALID");
  });
  it("keeps absence unknown with no observation", () => {
    expect(decodeHostObservationRead({ schema: "mastermind.workspace_host_observation_result.v1", selection: fixture.selection, availability: "UNAVAILABLE", reason_codes: ["SOURCE_UNAVAILABLE"], observation: null, source_observation: null }, fixture.selection)).toEqual({ state: "UNAVAILABLE" });
  });
});
