import { describe, expect, it } from "vitest";
import fixture from "../fixtures/project-plan-v2-owner.json";
import { planAdoptionRequestFromRead } from "./plan-adoption-from-read";
const selection = {work_ref:"WS:PLAN-TEST"};
const id = "mmos-project-adopt-"+"a".repeat(40);
const prepare = (body:unknown,name="PLAN-PROPOSAL",target=selection,requestId=id) => planAdoptionRequestFromRead(body,target,name,requestId);

describe("real READ -> exact ADOPT request metadata",()=>{
  it("uses actual recorded predecessor/source identities and the owner-supplied original ID",()=>{
    const body=fixture.cases.available_pending;
    const request=prepare(body);
    expect(request.request_id).toBe(id);
    expect(request.expected_commit).toBe(body.source.commit);
    expect(request.expected_adoption).toBe(body.continuity.adoption.decision_ref);
    expect(request.work_ref).toBe(selection.work_ref);
    expect(request).not.toHaveProperty("grant");
    expect(request).not.toHaveProperty("request_sha256");
    expect(request).not.toHaveProperty("accepted");
  });
  it("keeps absence explicit without treating authored source as an adopted baseline",()=>{
    const request=prepare(fixture.cases.recorded_source_only);
    expect(request.expected_adoption).toBeNull();
  });
  it.each(["declared_source_unavailable","current_references_proposal","lineage_invalid","no_captured_proposal"] as const)(
    "refuses %s as a new prepared adoption",name=>{
      expect(()=>prepare(fixture.cases[name])).toThrow("PLAN_ADOPTION_PREPARATION_UNAVAILABLE");
    });
  it("refuses missing selection/proposal and malformed original IDs without leaking raw values",()=>{
    expect(()=>prepare(fixture.cases.available_pending,"MISSING-PROPOSAL")).toThrow("PLAN_ADOPTION_PREPARATION_UNAVAILABLE");
    expect(()=>prepare(fixture.cases.available_pending,"PLAN-PROPOSAL",{work_ref:"WS:FOREIGN"})).toThrow("PLAN_ADOPTION_PREPARATION_UNAVAILABLE");
    expect(()=>prepare(fixture.cases.available_pending,"PLAN-PROPOSAL",selection,"private-synthetic-input")).toThrow("PLAN_ADOPTION_PREPARATION_UNAVAILABLE");
  });
  it("does not turn old v1 authored content into a missing proposal or authority",()=>{
    const body:Record<string,unknown>=structuredClone(fixture.cases.recorded_source_only);
    delete body.continuity;body.schema="mastermind.workspace_project_plan.v1";
    expect(()=>prepare(body)).toThrow("PLAN_ADOPTION_PREPARATION_UNAVAILABLE");
  });
});
