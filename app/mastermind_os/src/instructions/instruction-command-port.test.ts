// @vitest-environment node
import {afterEach,describe,it,expect,vi} from "vitest";
import type {InstructionStatusRequest} from "./instruction-host";
import {IDBFactory} from "fake-indexeddb";
import owner from "./fixtures/instruction-owner.json";
import {createInstructionAdmissionCommandPort,type InstructionAdmissionSnapshot} from "./instruction-command-port";
import {readInstructionRecoveryTarget} from "./instruction-recovery";
import {serializeInstructionAdmissionTarget} from "../orchestration/instruction-admission-target";
import {createIndexedDbPendingPointerStore} from "../orchestration/indexeddb-pending-pointer-store";
import {OperationController,type CommandIntent} from "../orchestration/operation-controller";
const selection={work_ref:"WS:ONE",instruction_ref:"INS:DAILY-ONE"},target=serializeInstructionAdmissionTarget(selection)!;
const original={kind:"instruction_pause" as const,targetKey:target,operationKey:owner.status.selection.command_id};
const intent=():CommandIntent=>({kind:"instruction_pause",targetKey:target,payload:{selection,expected_revision:owner.current.instruction_revision,expected_source:owner.current.source}});
const snapshot=():InstructionAdmissionSnapshot=>({selection,data:owner.current,dataGeneration:"1",generation:"1",canRead:true});
afterEach(()=>vi.restoreAllMocks());
function deterministicKey(){vi.spyOn(crypto,"getRandomValues").mockImplementation(<T extends ArrayBufferView|null>(array:T):T=>{if(array)new Uint8Array(array.buffer,array.byteOffset,array.byteLength).fill(0x11);return array;});}
describe("instruction pause finite owner port",()=>{
 it("prepares only the exact currently qualified instruction/source revision",()=>{
  const view=snapshot(),pause=vi.fn(),status=vi.fn(),port=createInstructionAdmissionCommandPort(()=>view,{pause,status});
  expect(port.prepare(intent()).kind).toBe("instruction_pause");
  for(const change of [{...intent(),kind:"project_pause" as const},{...intent(),payload:{...intent().payload,expected_revision:"f".repeat(64)}},{...intent(),targetKey:target+"\n"}])expect(()=>port.prepare(change)).toThrow();
  view.data=owner.removed;expect(()=>port.prepare(intent())).toThrow();expect(pause).not.toHaveBeenCalled();expect(status).not.toHaveBeenCalled();
 });
 it("permits same-ID readonly recovery after post-dispatch unknown and unavailable current read",async()=>{
  deterministicKey();const view=snapshot(),pause=vi.fn(async()=>owner.unknown),status=vi.fn(async(_request:InstructionStatusRequest):Promise<unknown>=>owner.status),port=createInstructionAdmissionCommandPort(()=>view,{pause,status});
  const store=createIndexedDbPendingPointerStore(new IDBFactory()),controller=new OperationController(port,store);
  expect((await controller.begin(intent())).status).toBe("unknown");expect(await store.read(owner.current.owner_context.principal_scope)).toEqual(original);
  view.data=null;view.dataGeneration=null;
  expect((await controller.recover()).status).toBe("accepted");expect(pause).toHaveBeenCalledTimes(1);expect(status).toHaveBeenCalledTimes(1);
  expect(status.mock.calls[0][0]).toMatchObject({selection,command_id:original.operationKey});expect(await store.read(owner.current.owner_context.principal_scope)).toBeNull();
 });
 it("discovers original INS from project-only empty content on fresh reopen, requalifies its grant and never resubmits",async()=>{
  deterministicKey();const factory=new IDBFactory(),store=createIndexedDbPendingPointerStore(factory),view=snapshot(),pause=vi.fn(async()=>owner.unknown),status=vi.fn(async(_request:InstructionStatusRequest):Promise<unknown>=>owner.removed_status);
  expect((await new OperationController(createInstructionAdmissionCommandPort(()=>view,{pause,status}),store).begin(intent())).status).toBe("unknown");
  const contentView={selection:{work_ref:"WS:ONE"},data:owner.project_only_empty,dataGeneration:"1",generation:"1",canRead:true};
  const reopenedStore=createIndexedDbPendingPointerStore(factory),found=await readInstructionRecoveryTarget(()=>contentView,reopenedStore,new AbortController().signal);
  expect(found).toEqual({pointer:original,selection});
  const fresh:InstructionAdmissionSnapshot={selection:found!.selection,data:owner.removed,dataGeneration:"1",generation:"1",canRead:true};
  const reopened=new OperationController(createInstructionAdmissionCommandPort(()=>fresh,{pause,status}),reopenedStore);
  expect((await reopened.recover()).status).toBe("accepted");expect(pause).toHaveBeenCalledTimes(1);expect(status).toHaveBeenCalledTimes(1);expect(await reopenedStore.read(owner.current.owner_context.principal_scope)).toBeNull();
 });
 it.each(["auth","generation","selection","principal"])("withholds status after actual %s departure and preserves original",async change=>{
  const view=snapshot(),pause=vi.fn(async()=>owner.unknown),status=vi.fn(async(_request:InstructionStatusRequest):Promise<unknown>=>{
   if(change==="auth")view.canRead=false;
   if(change==="generation")view.generation="2";
   if(change==="selection")view.selection={...selection,instruction_ref:"INS:OTHER"};
   if(change==="principal")view.data={...owner.current,owner_context:{principal_scope:"f".repeat(64)}};
   return owner.status;
  });
  const port=createInstructionAdmissionCommandPort(()=>view,{pause,status}),store=createIndexedDbPendingPointerStore(new IDBFactory());await store.reserve(owner.current.owner_context.principal_scope,original);
  expect((await new OperationController(port,store).recover()).status).toBe("idle");expect(await store.read(owner.current.owner_context.principal_scope)).toEqual(original);expect(pause).not.toHaveBeenCalled();
 });
 it("treats NOT_OBSERVED and foreign receipts as unknown with no clear or retry",async()=>{
  const view=snapshot(),pause=vi.fn(),status=vi.fn(async(_request:InstructionStatusRequest):Promise<unknown>=>({...owner.status,state:"NOT_OBSERVED",receipt:null}));
  const store=createIndexedDbPendingPointerStore(new IDBFactory());await store.reserve(owner.current.owner_context.principal_scope,original);
  const controller=new OperationController(createInstructionAdmissionCommandPort(()=>view,{pause,status}),store);expect((await controller.recover()).status).toBe("unknown");
  status.mockResolvedValue({...owner.status,selection:{...owner.status.selection,instruction_ref:"INS:OTHER"}});
  expect((await controller.recover()).status).toBe("unknown");expect(await store.read(owner.current.owner_context.principal_scope)).toEqual(original);expect(pause).not.toHaveBeenCalled();
 });
});
