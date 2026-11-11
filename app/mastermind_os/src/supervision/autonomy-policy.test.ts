import { describe, expect, it } from "vitest";
import producerBody from "./autonomy-policy.producer-fixture.json";
import {
  AUTONOMY_READ_BODY_SCHEMA,
  AUTONOMY_READ_INVALID,
  AUTONOMY_SOURCE_OBSERVATION_SCHEMA,
  AUTONOMY_RUNTIME_RECEIPT_SCHEMA,
  AUTONOMY_UNAVAILABLE_REASONS,
  decodeAutonomyPolicy,
  isAutonomySelection,
} from "./autonomy-policy";

// Inert source DTO fixtures only: fixed hex strings, no crypto, no grants.
const SELECTION={work_ref:"WS:FIXTURE",root_job_id:"JOB-7"};
const IDENTITY="a".repeat(32),DIGEST="b".repeat(64);
const OBSERVATION={
 schema:AUTONOMY_SOURCE_OBSERVATION_SCHEMA,state:"SAME",selection:{...SELECTION},
 runtime:{schema:AUTONOMY_RUNTIME_RECEIPT_SCHEMA,state:"SAME",source_identity:IDENTITY,before:11,after:11},
 control_room:{instance_before:"instance-fixture",instance_after:"instance-fixture",publication_before:4,publication_after:4,
  document_digest:DIGEST,source_validity_digest:DIGEST,cache_currentness_digest:DIGEST},
};
const POLICY={
 scope:"ADMITTED_ROOT",policy_sha:"c".repeat(64),source_sha256:"d".repeat(64),
 plan_digest:"e".repeat(64),reservation_digest:"f".repeat(64),
 limits:{schema_version:1,max_children_total:4,max_fan_out_per_parent:3,max_depth:6,
  max_attempts_per_orchestration_job:2,max_repair_rounds:1,max_review_attempts_per_job:3,
  review_job_attempt_limit:5,allowed_child_cost_classes:["standard","deep_research"]},
};
const available=()=>({schema:AUTONOMY_READ_BODY_SCHEMA,selection:{...SELECTION},availability:"AVAILABLE",
 reason_codes:[],source_observation:structuredClone(OBSERVATION),policy:structuredClone(POLICY)});
const unavailable=()=>({schema:AUTONOMY_READ_BODY_SCHEMA,selection:{...SELECTION},availability:"UNAVAILABLE",
 reason_codes:["SOURCE_CHANGED"],source_observation:null,policy:null});
const invalid=(value:unknown,expected=SELECTION)=>
 expect(()=>decodeAutonomyPolicy(value,expected)).toThrowError(new Error(AUTONOMY_READ_INVALID));
const drift=(mutate:(body:any)=>void)=>{const body=available();mutate(body);invalid(body);};

describe("decodeAutonomyPolicy",()=>{
 it("decodes an available admitted-root read into a frozen detached copy",()=>{
  const body=available();
  const decoded=decodeAutonomyPolicy(body,SELECTION);
  expect(decoded.availability).toBe("AVAILABLE");
  expect(decoded.reason_codes).toEqual([]);
  expect(decoded.selection).toEqual(SELECTION);
  if(decoded.availability!=="AVAILABLE")throw new Error("unreachable");
  expect(decoded.policy.limits.max_children_total).toBe(4);
  expect(decoded.policy.limits.allowed_child_cost_classes).toEqual(["standard","deep_research"]);
  expect(decoded.source_observation.state).toBe("SAME");
  expect(decoded.source_observation.runtime).toEqual(
   {schema:AUTONOMY_RUNTIME_RECEIPT_SCHEMA,state:"SAME",source_identity:IDENTITY,before:11,after:11});
  expect(decoded.source_observation.control_room.instance_before).toBe("instance-fixture");
  expect(Object.isFrozen(decoded)).toBe(true);
  expect(Object.isFrozen(decoded.selection)).toBe(true);
  expect(Object.isFrozen(decoded.policy)).toBe(true);
  expect(Object.isFrozen(decoded.policy.limits)).toBe(true);
  expect(Object.isFrozen(decoded.policy.limits.allowed_child_cost_classes)).toBe(true);
  expect(Object.isFrozen(decoded.source_observation.runtime)).toBe(true);
  expect(Object.isFrozen(decoded.source_observation.control_room)).toBe(true);
  // Detached: later mutation of the source DTO must not change the decoded copy.
  body.policy.limits.max_depth=99;
  body.policy.limits.allowed_child_cost_classes.push("mutated");
  body.source_observation.runtime.before=12;
  expect(decoded.policy.limits.max_depth).toBe(6);
  expect(decoded.policy.limits.allowed_child_cost_classes).toEqual(["standard","deep_research"]);
  expect(decoded.source_observation.runtime.before).toBe(11);
  // The frozen copy itself rejects writes.
  expect(()=>{(decoded.policy.limits as {max_depth:number}).max_depth=1;}).toThrow();
 });
 it("accepts the released limit boundaries without inventing values",()=>{
  const ceiling=available() as any;ceiling.policy.limits.max_children_total=1_000_000;
  expect(decodeAutonomyPolicy(ceiling,SELECTION).availability).toBe("AVAILABLE");
  const v2=available() as any;v2.policy.limits.schema_version=2;
  expect(decodeAutonomyPolicy(v2,SELECTION).availability).toBe("AVAILABLE");
  const singleClass=available() as any;singleClass.policy.limits.allowed_child_cost_classes=["standard"];
  expect(decodeAutonomyPolicy(singleClass,SELECTION).availability).toBe("AVAILABLE");
 });
 it("rejects a read for a different selected root or a malformed expected selection",()=>{
  invalid(available(),{work_ref:"WS:FIXTURE",root_job_id:"JOB-9"});
  invalid(available(),{work_ref:"WS:OTHER",root_job_id:"JOB-7"});
  drift((b)=>{b.selection.root_job_id="JOB-9";});
  drift((b)=>{b.selection.work_ref="WS:OTHER";});
  invalid(available(),{work_ref:"ws-fixture",root_job_id:"JOB-7"});
  invalid(available(),{work_ref:"WS:FIXTURE",root_job_id:"JOB-1234567890"});
  invalid(available(),{...SELECTION,extra:1} as any);
  invalid(available(),{work_ref:"WS:FIXTURE"} as any);
 });
 it("rejects proof drift in the source observation receipts",()=>{
  drift((b)=>{b.source_observation.runtime.after=12;});
  drift((b)=>{b.source_observation.runtime.before=-1;});
  drift((b)=>{b.source_observation.runtime.state="STALE";});
  drift((b)=>{b.source_observation.runtime.schema="mastermind.runtime_read_observation.v2";});
  drift((b)=>{b.source_observation.runtime.source_identity="a".repeat(31);});
  drift((b)=>{b.source_observation.state="CHANGED";});
  drift((b)=>{b.source_observation.schema="mastermind.other_observation.v1";});
  drift((b)=>{b.source_observation.selection.root_job_id="JOB-9";});
  drift((b)=>{b.source_observation.control_room.instance_after="instance-next";});
  drift((b)=>{b.source_observation.control_room.publication_after=5;});
  drift((b)=>{b.source_observation.control_room.publication_before=0;});
  drift((b)=>{b.source_observation.control_room.document_digest="b".repeat(63);});
  drift((b)=>{b.source_observation.control_room.cache_currentness_digest=123;});
  drift((b)=>{b.source_observation=null;});
  drift((b)=>{b.source_observation={};});
 });
 it("rejects unknown keys and malformed envelopes whole",()=>{
  invalid(null);invalid(undefined);invalid(42);invalid("read");invalid([]);invalid({});
  const extra=available() as any;extra.extra=1;invalid(extra);
  const missing=available() as any;delete missing.policy;invalid(missing);
  const wrongSchema=available() as any;wrongSchema.schema="mastermind.workspace_autonomy_read_result.v2";invalid(wrongSchema);
  drift((b)=>{b.source_observation.extra=1;});
  drift((b)=>{b.source_observation.runtime.extra=1;});
  drift((b)=>{b.source_observation.control_room.extra=1;});
  const policyExtra=available() as any;policyExtra.policy.extra=1;invalid(policyExtra);
  const limitsExtra=available() as any;limitsExtra.policy.limits.extra=1;invalid(limitsExtra);
  const badScope=available() as any;badScope.policy.scope="ADMITTED_CHILD";invalid(badScope);
  const badDigest=available() as any;badDigest.policy.policy_sha="c".repeat(63);invalid(badDigest);
 });
 it("accepts only the fixed single-reason unavailable shape",()=>{
  const decoded=decodeAutonomyPolicy(unavailable(),SELECTION);
  expect(decoded.availability).toBe("UNAVAILABLE");
  if(decoded.availability!=="UNAVAILABLE")throw new Error("unreachable");
  expect(decoded.reason_codes).toEqual(["SOURCE_CHANGED"]);
  expect(decoded.source_observation).toBeNull();
  expect(decoded.policy).toBeNull();
  expect(Object.isFrozen(decoded)).toBe(true);
  expect(Object.isFrozen(decoded.reason_codes)).toBe(true);
  for(const reason of AUTONOMY_UNAVAILABLE_REASONS){
   const body=unavailable() as any;body.reason_codes=[reason];
   expect(decodeAutonomyPolicy(body,SELECTION).availability).toBe("UNAVAILABLE");
  }
  const two=unavailable() as any;two.reason_codes=["SOURCE_CHANGED","OVER_BUDGET"];invalid(two);
  const none=unavailable() as any;none.reason_codes=[];invalid(none);
  const unknownReason=unavailable() as any;unknownReason.reason_codes=["SOURCE_LOST"];invalid(unknownReason);
  const notCodes=unavailable() as any;notCodes.reason_codes="SOURCE_CHANGED";invalid(notCodes);
  const withObservation=unavailable() as any;withObservation.source_observation=structuredClone(OBSERVATION);invalid(withObservation);
  const withPolicy=unavailable() as any;withPolicy.policy=structuredClone(POLICY);invalid(withPolicy);
  const paused=available() as any;paused.availability="PAUSED";invalid(paused);
 });
 it("rejects out-of-contract policy limits fail-closed",()=>{
  const bad=(mutate:(limits:any)=>void)=>{const body=available() as any;mutate(body.policy.limits);invalid(body);};
  bad((l)=>{l.max_depth=-1;});
  bad((l)=>{l.max_fan_out_per_parent=1_000_001;});
  bad((l)=>{l.max_repair_rounds=1.5;});
  bad((l)=>{l.max_review_attempts_per_job="3";});
  bad((l)=>{l.review_job_attempt_limit=null;});
  bad((l)=>{l.schema_version=3;});
  bad((l)=>{l.schema_version="1";});
  bad((l)=>{l.allowed_child_cost_classes=[];});
  bad((l)=>{l.allowed_child_cost_classes=Array.from({length:17},(_,i)=>`class_${i}`);});
  bad((l)=>{l.allowed_child_cost_classes=["standard","standard"];});
  bad((l)=>{l.allowed_child_cost_classes=["Standard"];});
  bad((l)=>{l.allowed_child_cost_classes=["1standard"];});
  bad((l)=>{l.allowed_child_cost_classes=["deep-research"];});
  bad((l)=>{l.allowed_child_cost_classes="standard";});
 });
 it("keeps the fixed error and never leaks raw exceptions",()=>{
  for(const value of [null,undefined,0,"x",[],{},new Date(),Symbol("x")]){
   expect(()=>decodeAutonomyPolicy(value,SELECTION)).toThrowError(new Error(AUTONOMY_READ_INVALID));
  }
 });
 it("checks the exact selection shape and formats",()=>{
  expect(isAutonomySelection({...SELECTION})).toBe(true);
  expect(isAutonomySelection({...SELECTION,extra:1})).toBe(false);
  expect(isAutonomySelection({work_ref:"WS:FIXTURE"})).toBe(false);
  expect(isAutonomySelection({work_ref:"ws-fixture",root_job_id:"JOB-7"})).toBe(false);
  expect(isAutonomySelection({work_ref:"WS:FIXTURE",root_job_id:"job-7"})).toBe(false);
  expect(isAutonomySelection({work_ref:"WS:FIXTURE",root_job_id:"JOB-1234567890"})).toBe(false);
  expect(isAutonomySelection(null)).toBe(false);
 });
});

// Generated through compose_autonomy_policy_read + validate_body using the
// backend's inert admitted-plan fixture and actual CooCyclePolicy source.
describe("actual producer compatibility", () => {
 it("decodes the source-owner validated body without retyping literals", () => {
  const decoded = decodeAutonomyPolicy(producerBody, producerBody.selection);
  expect(decoded).toEqual(producerBody);
 });
 it("rejects the abbreviated observation schema and noncanonical work ref", () => {
  const body = structuredClone(producerBody);
  body.source_observation.schema = "mastermind.plan_observation.v1";
  expect(() => decodeAutonomyPolicy(body, body.selection)).toThrow(AUTONOMY_READ_INVALID);
  expect(isAutonomySelection({work_ref: "WS-ONE", root_job_id: "JOB-1"})).toBe(false);
 });
});

describe("closed inert body bounds", () => {
 it("rejects accessors and symbol fields without reading accessor values", () => {
  const body = available();
  let read = false;
  Object.defineProperty(body.policy, "policy_sha", {enumerable: true, get() { read = true; return "a".repeat(64); }});
  invalid(body); expect(read).toBe(false);
  const extra = available();
  Object.defineProperty(extra, Symbol("extra"), {value: "hidden"});
  invalid(extra);
 });
 it("retains the fixed public response byte cap", () => {
  const body = available();
  body.source_observation.control_room.instance_before = "x".repeat(32768);
  body.source_observation.control_room.instance_after = body.source_observation.control_room.instance_before;
  invalid(body);
 });
});
