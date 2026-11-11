import { describe, expect, it } from "vitest";
import fixtures from "../fixtures/plan-adoption-request-owner.json";
import { decodePlanAdoptionRequest } from "./plan-adoption-request";

describe("actual canonical compiler request integration", () => {
  it.each(fixtures.cases)("decodes actual $name without claiming its fixture fingerprint as authority", row => {
    const value = decodePlanAdoptionRequest(row.request, row.expected_work_ref);
    expect(value).toEqual(row.request);
    expect(value).not.toHaveProperty("request_sha256");
    expect(value).not.toHaveProperty("accepted");
  });
  it("does not return hostile getter error objects even when their message resembles the closed code", () => {
    const raw = structuredClone(fixtures.cases[0].request);
    const hostile = Object.assign(new Error("PLAN_ADOPTION_REQUEST_INVALID"), { attacker_field: "synthetic-private-value" });
    Object.defineProperty(raw, "request_id", { get() { throw hostile; }, enumerable: true });
    let caught: unknown;
    try { decodePlanAdoptionRequest(raw, fixtures.cases[0].expected_work_ref); } catch (error) { caught = error; }
    expect(caught).toBeInstanceOf(Error);
    expect((caught as Error).message).toBe("PLAN_ADOPTION_REQUEST_INVALID");
    expect(caught).not.toBe(hostile);
    expect(Object.keys(caught as object)).toEqual([]);
  });
});
