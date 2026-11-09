// @vitest-environment node
import {describe,it,expect,vi} from "vitest";
import {IDBFactory} from "fake-indexeddb";
import owner from "./fixtures/instruction-owner.json";
import {decodeStandingInstructions} from "./standing-instructions";
import {instructionRecoveryContext,readInstructionRecoveryTarget,type InstructionRecoverySnapshot} from "./instruction-recovery";
import {createIndexedDbPendingPointerStore} from "../orchestration/indexeddb-pending-pointer-store";
import {serializeInstructionAdmissionTarget} from "../orchestration/instruction-admission-target";
const selection={work_ref:"WS:ONE"},ins={...selection,instruction_ref:"INS:DAILY-ONE"};
const original={kind:"instruction_pause" as const,operationKey:owner.status.selection.command_id,targetKey:serializeInstructionAdmissionTarget(ins)!};
const snapshot=():InstructionRecoverySnapshot=>({selection,data:owner.project_only_empty,dataGeneration:"1",generation:"1",canRead:true});
describe("qualified project-only recovery identity",()=>{
 it("decodes current empty content and discovers the original INS lookup in the same durable namespace",async()=>{
  const view=snapshot();const body=decodeStandingInstructions(view.data,selection);expect(body).toEqual(owner.project_only_empty);
  const scope=instructionRecoveryContext(view)!.principalScope;expect(scope).toBe(owner.current.owner_context.principal_scope);
  const factory=new IDBFactory(),store=createIndexedDbPendingPointerStore(factory);await store.reserve(scope,original);
  const clear=vi.spyOn(store,"clearIfEqual"),reserve=vi.spyOn(store,"reserve");
  expect(await readInstructionRecoveryTarget(()=>view,store,new AbortController().signal)).toEqual({pointer:original,selection:ins});
  expect(clear).not.toHaveBeenCalled();expect(reserve).not.toHaveBeenCalled();expect(await createIndexedDbPendingPointerStore(factory).read(scope)).toEqual(original);
 });
 it.each(["legacy","unavailable","wrongProject","wrongIdentity","expiredRead","generation"])("does not publish another owner's pointer under %s",async change=>{
  const view=snapshot(),factory=new IDBFactory(),store=createIndexedDbPendingPointerStore(factory),scope=instructionRecoveryContext(view)!.principalScope;await store.reserve(scope,original);
  if(change==="legacy"){const body={...owner.project_only_empty,schema:"mastermind.workspace_project_instructions.v1"};delete (body as Record<string,unknown>).recovery_identity;view.data=body;}
  if(change==="unavailable")view.data={schema:"mastermind.workspace_project_instructions.v2",selection,availability:"UNAVAILABLE",source:null,declaration:null,instructions:null,reason_codes:["SOURCE_UNAVAILABLE"],recovery_identity:null};
  if(change==="wrongProject")view.selection={work_ref:"WS:OTHER"};
  if(change==="wrongIdentity")view.data={...owner.project_only_empty,recovery_identity:{principal_scope:"f".repeat(64)}};
  if(change==="expiredRead")view.canRead=false;
  if(change==="generation")view.generation="2";
  expect(await readInstructionRecoveryTarget(()=>view,store,new AbortController().signal)).toBeNull();expect(await store.read(scope)).toEqual(original);
 });
 it("withholds a lookup after identity departure during the asynchronous store read",async()=>{
  const view=snapshot(),store=createIndexedDbPendingPointerStore(new IDBFactory()),scope=instructionRecoveryContext(view)!.principalScope;await store.reserve(scope,original);
  const read=store.read.bind(store);vi.spyOn(store,"read").mockImplementation(async(...args)=>{const pointer=await read(...args);view.generation="2";return pointer;});
  expect(await readInstructionRecoveryTarget(()=>view,store,new AbortController().signal)).toBeNull();expect(await read(scope)).toEqual(original);
 });
 it("rejects recovery identity in an unavailable or legacy content body",()=>{
  const identity=owner.current.owner_context;
  expect(decodeStandingInstructions({...owner.project_only_empty,schema:"mastermind.workspace_project_instructions.v1"},selection)).toBeNull();
  expect(decodeStandingInstructions({schema:"mastermind.workspace_project_instructions.v2",selection,availability:"UNAVAILABLE",source:null,declaration:null,instructions:null,reason_codes:["ACCESS_DENIED"],recovery_identity:identity},selection)).toBeNull();
  expect(decodeStandingInstructions({...owner.project_only_empty,recovery_identity:{...identity,permission:true}},selection)).toBeNull();
 });
});
