import { describe, expect, it, vi } from "vitest";
import { canonicalJson, sha256Hex } from "../orchestration/operation-key";
import {
  decodeProjectExecutionCatalogue, decodeProjectExecutionReference, decodeProjectExecutionWindow,
  type ProjectExecutionReference,
} from "./project-execution-history-contract";
import { executionFixture as fixture, executionReference as reference, executionWork as work } from "./project-execution-history.test-support";

describe("actual Runtime project execution history DTOs", () => {
  it("preserves pending and completed results, immutable reference and verified continuation witness", () => {
    expect(fixture.provenance.installed_runtime_evidence).toBe(false);
    expect(decodeProjectExecutionCatalogue(fixture.catalogue, work)).toEqual(fixture.catalogue);
    const pending = decodeProjectExecutionWindow(fixture.pending_read, decodeProjectExecutionReference(reference, work));
    const completed = decodeProjectExecutionWindow(fixture.completed_read, decodeProjectExecutionReference(reference, work));
    expect(pending.state).toBe("QUEUED");
    expect(pending.result).toBeNull(); expect(pending.parent_witness).toBeNull();
    expect(completed).toEqual(fixture.completed_read);
    expect(completed.result!.digest).toBe(completed.parent_witness!.result_envelope_sha256);
    expect(completed.can_send).toBe(false);
    expect(Object.isFrozen(completed)).toBe(true);
    expect(Object.isFrozen(completed.result!.envelope)).toBe(true);
    expect(completed.reference).not.toBe(reference);
  });
  it.each(["source", "root", "locator", "attempt", "digest", "receipt", "state", "parent", "capability", "extra"])(
    "withholds a mismatched completed %s coordinate", fault => {
      const value = structuredClone(fixture.completed_read);
      if (fault === "source") value.reference.project_execution_source_sha256 = "f".repeat(64);
      if (fault === "root") value.reference.root_job_id = "JOB-999";
      if (fault === "locator") value.locator.root_job_id = "JOB-999";
      if (fault === "attempt") value.locator.attempt_id = "ATT-foreign";
      if (fault === "digest") value.result.digest = "f".repeat(64);
      if (fault === "receipt") value.result.terminal_receipt_sha256 = "f".repeat(64);
      if (fault === "state") value.state = "RUNNING";
      if (fault === "parent") value.parent_witness.root_event_id += 1;
      if (fault === "capability") value.can_send = true;
      if (fault === "extra") Object.assign(value, { operation_key: "forged-send" });
      expect(() => decodeProjectExecutionWindow(value, reference as ProjectExecutionReference)).toThrow();
    });
  it("refuses a rehashed result belonging to another root or coordinator", () => {
    for (const field of ["job_id", "root_job_id", "coordinator_job_id"]) {
      const value = structuredClone(fixture.completed_read);
      if (field === "job_id") value.result.envelope.job_id = "JOB-999";
      else (value.result.envelope.role_result as Record<string, unknown>)[field] = "JOB-999";
      value.result.digest = sha256Hex(canonicalJson(value.result.envelope));
      value.parent_witness.result_envelope_sha256 = value.result.digest;
      expect(() => decodeProjectExecutionWindow(value, reference as ProjectExecutionReference)).toThrow();
    }
  });
  it("does not evaluate a getter in raw content or the expected immutable read reference", () => {
    const value = structuredClone(fixture.completed_read), getter = vi.fn(() => "must-not-execute");
    Object.defineProperty(value.result.envelope, "summary", { enumerable: true, get: getter });
    expect(() => decodeProjectExecutionWindow(value, reference as ProjectExecutionReference)).toThrow();
    expect(getter).not.toHaveBeenCalled();
    const workGetter = vi.fn(() => work);
    const expected = Object.defineProperty({ ...reference }, "work_ref", { enumerable: true, get: workGetter });
    expect(() => decodeProjectExecutionWindow(fixture.completed_read, expected as ProjectExecutionReference)).toThrow();
    expect(workGetter).not.toHaveBeenCalled();
  });
  it("rejects surrogate text, sparse arrays and hidden extra fields before decoding result bodies", () => {
    const value = structuredClone(fixture.completed_read);
    value.goal = "bad\uD800";
    expect(() => decodeProjectExecutionWindow(value, reference as ProjectExecutionReference)).toThrow();
    const catalogue = structuredClone(fixture.catalogue);
    delete (catalogue.entries as unknown[])[0];
    expect(() => decodeProjectExecutionCatalogue(catalogue, work)).toThrow();
    const hidden = structuredClone(fixture.completed_read);
    Object.defineProperty(hidden, "hidden_authority", { value: true, enumerable: false });
    expect(() => decodeProjectExecutionWindow(hidden, reference as ProjectExecutionReference)).toThrow();
  });
  it("keeps empty and partial coverage explicit but rejects invalid project grammar", () => {
    const empty = { ...fixture.catalogue, entries: [], coverage: { state: "PARTIAL", limit: 8, returned: 0 } };
    expect(decodeProjectExecutionCatalogue(empty, work).coverage).toEqual(empty.coverage);
    expect(() => decodeProjectExecutionCatalogue({ ...empty, work_ref: "WS:A" }, "WS:A")).toThrow();
    expect(() => decodeProjectExecutionCatalogue({ ...empty, can_send: true }, work)).toThrow();
    expect(() => decodeProjectExecutionCatalogue({ ...empty, coverage: { ...empty.coverage, returned: 1 } }, work)).toThrow();
  });
  it("enforces the source response budget without truncating an oversized result into apparent success", () => {
    const entries = Array.from({ length: 8 }, (_, n) => ({
      ...fixture.catalogue.entries[0], goal: "界".repeat(4000),
      reference: { ...reference, root_job_id: "JOB-" + (n + 1) },
    }));
    expect(() => decodeProjectExecutionCatalogue({ ...fixture.catalogue, entries,
      coverage: { state: "PARTIAL", limit: 8, returned: 8 } }, work)).toThrow();
  });
});

it("preserves exact multiline goals at the source Unicode limit without accepting blank or NUL text", () => {
  const goal = "😀".repeat(3994) + "\nPlan\t";
  const window = { ...fixture.completed_read, goal };
  const catalogue = { ...fixture.catalogue, entries: [{ ...fixture.catalogue.entries[0], goal }] };
  expect(decodeProjectExecutionWindow(window, reference as ProjectExecutionReference).goal).toBe(goal);
  expect(decodeProjectExecutionCatalogue(catalogue, work).entries[0]!.goal).toBe(goal);
  for (const invalid of [goal + "😀", " \t\r\n", "goal\u0000suffix"]) {
    expect(() => decodeProjectExecutionWindow({ ...window, goal: invalid }, reference as ProjectExecutionReference)).toThrow();
    expect(() => decodeProjectExecutionCatalogue({ ...catalogue, entries: [{ ...catalogue.entries[0], goal: invalid }] }, work)).toThrow();
  }
});
