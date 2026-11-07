import { describe, expect, it } from "vitest";
import { decodeMissionv3, decodeMissionv4 } from "./mission";
import fixture from "./fixtures/mission-v4-owner-accepted.json";

const selected = { workRef: fixture.product_acceptance.selection.work_ref,
  rootJobId: fixture.product_acceptance.selection.root_job_id };
const key = fixture.product_acceptance.selection.request_message_key;

describe("parent-consumed acceptance read", () => {
  it("decodes the exact real Python Runtime/reducer fixture without changing v3", () => {
    const value = decodeMissionv4(fixture, selected, key);
    expect(value?.product_acceptance.state).toBe("ACCEPTED");
    expect(value?.mission.acceptance.state).toBe("NOT_PROJECTED");
    expect(decodeMissionv3(fixture.mission, selected)).not.toBeNull();
    expect(decodeMissionv3(fixture, selected)).toBeNull();
  });
  it.each(["request", "work", "root"])("refuses foreign %s selection", field => {
    expect(decodeMissionv4(fixture,
      field === "work" ? {...selected, workRef: "WS:FOREIGN"} :
      field === "root" ? {...selected, rootJobId: "JOB-999"} : selected,
      field === "request" ? "asd-mcp-" + "f".repeat(32) : key)).toBeNull();
  });
  it.each(["extra", "parentDigest", "parentAttempt", "subjectDigest", "ruling", "partial", "bareCompleted", "source"])(
    "refuses %s rather than promoting a terminal status", defect => {
      const value: any = structuredClone(fixture);
      const receipt = value.product_acceptance.receipt;
      if (defect === "extra") receipt.secret = "not in this contract";
      if (defect === "parentDigest") receipt.parent_result_envelope_digest = "f".repeat(64);
      if (defect === "parentAttempt") receipt.parent_attempt_id = "ATT-" + "f".repeat(32);
      if (defect === "subjectDigest") receipt.subject_result_envelope_digest = "f".repeat(64);
      if (defect === "ruling") receipt.ruling_message_key = "asd-mcp-" + "f".repeat(32);
      if (defect === "partial") value.mission.read_state.state = "PARTIAL";
      if (defect === "bareCompleted") value.product_acceptance.receipt = {state: "COMPLETED"};
      if (defect === "source") receipt.source_continuity.current_basis_digest = null;
      expect(decodeMissionv4(value, selected, key)).toBeNull();
    });
  it("keeps a typed pending parent unavailable and forbids retained receipt data", () => {
    const value: any = structuredClone(fixture);
    value.product_acceptance.state = "UNAVAILABLE";
    value.product_acceptance.reason_codes = ["PARENT_RETURN_UNVERIFIED"];
    expect(decodeMissionv4(value, selected, key)).toBeNull();
    value.product_acceptance.receipt = null;
    expect(decodeMissionv4(value, selected, key)?.product_acceptance.state).toBe("UNAVAILABLE");
  });
  it.each(["reasonObject", "dispositionArray", "falseUnchanged", "falseChanged"])(
    "refuses malformed or contradictory %s evidence", defect => {
      const value: any = structuredClone(fixture);
      const source = value.product_acceptance.receipt.source_continuity;
      if (defect === "reasonObject") Object.assign(value.product_acceptance,
        {state: "UNAVAILABLE", receipt: null, reason_codes: [{}]});
      if (defect === "dispositionArray") source.disposition = [source.disposition];
      if (defect === "falseUnchanged") Object.assign(source,
        {disposition: "UNCHANGED_SOURCE", current_basis_digest: "f".repeat(64)});
      if (defect === "falseChanged") Object.assign(source,
        {disposition: "SOURCE_OBSERVATION_CHANGED_DECLARATION_UNCHANGED", current_basis_digest: source.issued_basis_digest});
      expect(decodeMissionv4(value, selected, key)).toBeNull();
    });
  it("accepts a changed source observation only with the unchanged-declaration disposition", () => {
    const value: any = structuredClone(fixture);
    Object.assign(value.product_acceptance.receipt.source_continuity,
      {disposition: "SOURCE_OBSERVATION_CHANGED_DECLARATION_UNCHANGED", current_basis_digest: "f".repeat(64)});
    expect(decodeMissionv4(value, selected, key)?.product_acceptance.state).toBe("ACCEPTED");
  });
});
