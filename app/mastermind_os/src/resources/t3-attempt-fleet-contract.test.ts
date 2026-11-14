import { readFileSync } from "node:fs";
import { expect, it } from "vitest";
import {
  T3_ATTEMPT_FLEET_MAX_BYTES, T3_ATTEMPT_FLEET_REFUSALS, decodeT3AttemptFleet, validT3AttemptId,
} from "./t3-attempt-fleet-contract";

/** The canonical fixture is produced by the Python composition (route output);
 *  both languages assert equality against these exact bytes. */
const FIXTURE_DIR = new URL("../../../../integrations/mmos/fixtures/t3_attempt_fleet_v1/", import.meta.url);
const attemptFixture: unknown = JSON.parse(readFileSync(new URL("attempt.json", FIXTURE_DIR), "utf8"));
const refusalFixture: unknown = JSON.parse(readFileSync(new URL("refusal.json", FIXTURE_DIR), "utf8"));

it("accepts the real Python composition fixture and mirrors its exact fields", () => {
  const read = decodeT3AttemptFleet(attemptFixture);
  if (read.state !== "AVAILABLE" || read.document.kind !== "attempt") throw Error("fixture must qualify");
  const attempt = read.document.attempt;
  expect(attempt.attempt_id).toBe("runs/att-1");
  expect(attempt.invariant).toEqual({ exactly_one_thread: "PROVEN", exactly_one_harness: "PROVEN" });
  expect(attempt.harness_process).toMatchObject({ pid: 100, provider: "claude", model: "glm-5.3" });
  expect(attempt.t3_thread.thread_id).toBe("mcp:launch:" + "1".repeat(64));
  expect(attempt.duplicate_launcher.observed).toBe(false);
  expect(read.document.notes).toEqual([]);
  expect(read.document.evaluated_at_utc).toBe("2026-11-09T12:00:00+00:00");
});

it("accepts the typed refusal fixture as an honest document, not a transport failure", () => {
  expect(decodeT3AttemptFleet(refusalFixture)).toEqual({
    state: "AVAILABLE", document: { kind: "refusal", refusal: "ADAPTER_STATE_SCHEMA_UNKNOWN" },
  });
});

it("keeps the refusal vocabulary closed and the wire bound exact", () => {
  expect(T3_ATTEMPT_FLEET_REFUSALS).toContain("SOURCE_CHANGED");
  expect(T3_ATTEMPT_FLEET_REFUSALS.length).toBeGreaterThanOrEqual(19);
  const body: any = structuredClone(attemptFixture);
  body.refusal = "FOREIGN_CODE"; body.attempts = []; delete body.evaluated_at_utc; delete body.notes;
  expect(decodeT3AttemptFleet(body)).toEqual({ state: "UNAVAILABLE", reason: "INVALID_RESPONSE" });
});

it("refuses a refusal that still carries attempts or a foreign code", () => {
  const bad: any = structuredClone(refusalFixture);
  bad.attempts = [{ attempt_id: "runs/att-1" }];
  expect(decodeT3AttemptFleet(bad).state).toBe("UNAVAILABLE");
  const foreign: any = structuredClone(refusalFixture);
  foreign.refusal = "MADE_UP";
  expect(decodeT3AttemptFleet(foreign).state).toBe("UNAVAILABLE");
});

it.each(["extra_key", "bad_verdict", "thread_unknown_without_reason", "observed_true_no_kinds",
  "duplicate_unknown_without_reason", "pid_zero", "harness_facts_without_pid", "bad_freshness",
  "two_attempts", "newline_evidence", "bad_note", "future_free_stamp", "schema_drift"])("refuses %s", fault => {
  const value: any = structuredClone(attemptFixture);
  const attempt = value.attempts[0];
  if (fault === "extra_key") attempt.spare = 1;
  else if (fault === "bad_verdict") attempt.invariant.exactly_one_harness = "HEALTHY";
  else if (fault === "thread_unknown_without_reason") { attempt.t3_thread.thread_id = null; attempt.t3_thread.run_id = null; attempt.t3_thread.state = null; }
  else if (fault === "observed_true_no_kinds") { attempt.duplicate_launcher.observed = true; }
  else if (fault === "duplicate_unknown_without_reason") { attempt.duplicate_launcher.observed = null; attempt.duplicate_launcher.unknown_reason = null; }
  else if (fault === "pid_zero") attempt.harness_process.pid = 0;
  else if (fault === "harness_facts_without_pid") { attempt.harness_process.pid = null; attempt.harness_process.unknown_reason = null; }
  else if (fault === "bad_freshness") attempt.freshness.census = "old";
  else if (fault === "two_attempts") value.attempts.push(structuredClone(attempt));
  else if (fault === "newline_evidence") attempt.evidence_refs[0] = "adapter_state:read\nx";
  else if (fault === "bad_note") value.notes = ["not-a-token"];
  else if (fault === "future_free_stamp") value.evaluated_at_utc = "2026-11-09T12:00:60+00:00";
  else value.schema = "mastermind.foreign/v1";
  expect(decodeT3AttemptFleet(value)).toEqual({ state: "UNAVAILABLE", reason: "INVALID_RESPONSE" });
});

it("keeps run-id grammar permissive for slash and strict for traversal", () => {
  expect(validT3AttemptId("runs/att-1")).toBe(true);
  expect(validT3AttemptId("runs/run%3Athread%3Ax%3A1")).toBe(true);
  expect(validT3AttemptId("../escape")).toBe(false);
  expect(validT3AttemptId("")).toBe(false);
  expect(validT3AttemptId("runs/" + "x".repeat(200))).toBe(false);
  expect(validT3AttemptId(403)).toBe(false);
});

it("detaches the accepted observation from a mutable transport object", () => {
  const value: any = structuredClone(attemptFixture);
  const read = decodeT3AttemptFleet(value);
  value.attempts[0].invariant.exactly_one_thread = "VIOLATED";
  if (read.state !== "AVAILABLE" || read.document.kind !== "attempt") throw Error("fixture must qualify");
  expect(read.document.attempt.invariant.exactly_one_thread).toBe("PROVEN");
});

it("refuses an oversized body before field checks", () => {
  const value: any = structuredClone(attemptFixture);
  value.pad = "x".repeat(T3_ATTEMPT_FLEET_MAX_BYTES);
  const encoded = JSON.stringify(value);
  if (new TextEncoder().encode(encoded).length < T3_ATTEMPT_FLEET_MAX_BYTES) throw Error("test body must exceed the wire bound");
  expect(decodeT3AttemptFleet(value)).toEqual({ state: "UNAVAILABLE", reason: "INVALID_RESPONSE" });
});
