// @vitest-environment node
import {describe,it,expect} from "vitest";
import owner from "./fixtures/instruction-owner.json";
import {decodeInstructionAdmissionControl as control,decodeInstructionAdmissionResult as result,validInstructionAdmissionSelection as selected} from "./instruction-admission";
const selection={work_ref:"WS:ONE",instruction_ref:"INS:DAILY-ONE"};
describe("parent integration against actual instruction owner bytes",()=>{
 it("consumes actual canonical repository/source, stable pause and removed-row recovery identity",()=>{
  for(const body of [owner.current,owner.paused,owner.removed])expect(control(body,selection)).toEqual(body);
  expect(result(owner.unknown,owner.unknown.selection,"pause")).toEqual(owner.unknown);
  expect(result(owner.status,owner.status.selection,"status")).toEqual(owner.status);
  expect(result(owner.removed_status,owner.removed_status.selection,"status")).toEqual(owner.removed_status);
 });
 it("uses the actual canonical numeric upper-kebab grammar",()=>{
  expect(selected({work_ref:"WS:12",instruction_ref:"INS:34"})).toBe(true);
  for(const ref of ["12--AB","12-","-12","12\n","12_3"]){expect(selected({work_ref:"WS:"+ref,instruction_ref:"INS:34"})).toBe(false);expect(selected({work_ref:"WS:12",instruction_ref:"INS:"+ref})).toBe(false);}
 });
 it.each(["revision","sourceCommit","scope","receiptCommand"])("requires full-string match for %s",field=>{
  const body=structuredClone(owner.paused);
  if(field==="revision")body.instruction_revision+="\n";
  if(field==="sourceCommit")body.source.commit+="\n";
  if(field==="scope")body.owner_context.principal_scope+="\n";
  if(field==="receiptCommand")body.current_receipt.command_id+="\n";
  expect(control(body,selection)).toBeNull();
 });
 it("rejects array element accessors without executing them",()=>{
  let reads=0;const body=structuredClone(owner.removed);body.owner_context=null as never;
  Object.defineProperty(body.reason_codes,"0",{enumerable:true,get(){reads++;return "INSTRUCTION_NOT_SUPPLIED";}});
  expect(control(body,selection)).toBeNull();expect(reads).toBe(0);
 });
 it("rejects known hidden fields and hidden/symbol reason properties",()=>{
  const body=structuredClone(owner.current);Object.defineProperty(body,"state",{value:body.state,enumerable:false});expect(control(body,selection)).toBeNull();
  const removed=structuredClone(owner.removed);Object.defineProperty(removed.reason_codes,Symbol("extra"),{value:true});expect(control(removed,selection)).toBeNull();
 });
 it("allows recovery identity only for the qualified missing-row branch",()=>{
  expect(control(owner.removed,selection)?.owner_context).toEqual(owner.current.owner_context);
  for(const reason of ["ACCESS_DENIED","SOURCE_UNAVAILABLE","SOURCE_CHANGED","OWNER_NOT_READY"]){const body={...owner.removed,reason_codes:[reason]};expect(control(body,selection)).toBeNull();}
 });
 it("rejects an unknown result mode rather than treating it as pause",()=>expect(result(owner.unknown,owner.unknown.selection,"future" as "pause")).toBeNull());
});
