// @vitest-environment node
import { describe, expect, it, vi } from "vitest";
import { IDBFactory } from "fake-indexeddb";
import { OperationController, type EffectReceipt, type FiniteCommandPort, type OwnerContext, type OperationPointer } from "./operation-controller";
import { createIndexedDbPendingPointerStore } from "./indexeddb-pending-pointer-store";
const scope="a".repeat(64),digest="d".repeat(64);
const pointer:OperationPointer={kind:"project_adopt",operationKey:"mmos-project-adopt-"+"b".repeat(40),targetKey:"WS:ONE"};
function ready():EffectReceipt{return {...pointer,disposition:"unknown",reason:"READY_FOR_ADVANCE",advance:{phase_receipt_digest:digest}};}
async function setup(status:EffectReceipt=ready(),effect:EffectReceipt={...pointer,disposition:"accepted"}) {
 const store=createIndexedDbPendingPointerStore(new IDBFactory());await store.reserve(scope,pointer);
 const context:{value:OwnerContext|null}={value:{principalScope:scope,generation:"1"}};
 const port={context:()=>context.value,prepare:vi.fn<FiniteCommandPort["prepare"]>(()=>{throw new Error("no fresh key");}),submit:vi.fn<FiniteCommandPort["submit"]>(async()=>{throw new Error("no new submission");}),readOperation:vi.fn<FiniteCommandPort["readOperation"]>(async()=>status),advanceOperation:vi.fn<NonNullable<FiniteCommandPort["advanceOperation"]>>(async()=>effect)};
 const clear=vi.spyOn(store,"clearIfEqual"),controller=new OperationController(port,store);
 return {store,context,port,clear,controller};
}
describe("explicit same-original ADOPT advance",()=>{
 it("recover only publishes the closed witness, never advances",async()=>{
  const s=await setup();const state=await s.controller.recover();expect(state).toMatchObject({status:"unknown",reason:"READY_FOR_ADVANCE",advance:{phase_receipt_digest:digest}});
  expect(s.port.advanceOperation).not.toHaveBeenCalled();expect(s.clear).not.toHaveBeenCalled();expect(await s.store.read(scope)).toEqual(pointer);
 });
 it("re-reads original status and pointer, then advances once with exact witness and clears only terminal acceptance",async()=>{
  const s=await setup();expect((await s.controller.advance()).status).toBe("accepted");
  expect(s.port.readOperation).toHaveBeenCalledTimes(1);expect(s.port.advanceOperation.mock.calls[0]?.slice(0,2)).toEqual([pointer,digest]);
  expect(s.port.prepare).not.toHaveBeenCalled();expect(s.port.submit).not.toHaveBeenCalled();expect(await s.store.read(scope)).toBeNull();
 });
 it.each(["refused","throw","unknown"])("retains a partial original when next phase is %s",async change=>{
  const s=await setup(ready(),{...pointer,disposition:change==="refused" ? "refused" : "unknown",reason:"private provider text"});
  if(change==="throw")s.port.advanceOperation.mockRejectedValue(new Error("private"));
  const state=await s.controller.advance();expect(state.status).toBe("unknown");expect(JSON.stringify(state)).not.toContain("private");
  expect(s.clear).not.toHaveBeenCalled();expect(await s.store.read(scope)).toEqual(pointer);expect(s.port.submit).not.toHaveBeenCalled();
 });
 it("holds even a refused status during explicit advance; partial state cannot become a fresh request",async()=>{
  const s=await setup({...pointer,disposition:"refused"});expect((await s.controller.advance()).status).toBe("unknown");expect(s.clear).not.toHaveBeenCalled();expect(s.port.advanceOperation).not.toHaveBeenCalled();expect(await s.store.read(scope)).toEqual(pointer);
 });
 it.each(["absent","bad_digest","extra_witness","wrong_kind","wrong_target","wrong_key","getter"])("does not advance unqualified phase witness %s",async change=>{
  const status:Record<string,unknown>={...ready()};let called=false;
  if(change==="absent")delete status.advance;
  if(change==="bad_digest")status.advance={phase_receipt_digest:"A".repeat(64)};
  if(change==="extra_witness")status.advance={phase_receipt_digest:digest,token:"private"};
  if(change==="wrong_kind")status.kind="project_create";
  if(change==="wrong_target")status.targetKey="WS:OTHER";
  if(change==="wrong_key")status.operationKey="mmos-project-adopt-"+"c".repeat(40);
  if(change==="getter")Object.defineProperty(status,"advance",{get(){called=true;return {phase_receipt_digest:digest};},enumerable:true});
  const s=await setup(status as unknown as EffectReceipt);expect((await s.controller.advance()).status).toBe("unknown");expect(s.port.advanceOperation).not.toHaveBeenCalled();expect(called).toBe(false);expect(s.clear).not.toHaveBeenCalled();expect(await s.store.read(scope)).toEqual(pointer);
 });
 it("masks identity rotation between status and effect and retains original scoped pointer",async()=>{
  const s=await setup();s.port.readOperation.mockImplementation(async()=>{s.context.value={principalScope:scope,generation:"2"};return ready();});
  expect((await s.controller.advance()).status).toBe("idle");expect(s.port.advanceOperation).not.toHaveBeenCalled();expect(s.clear).not.toHaveBeenCalled();expect(await s.store.read(scope)).toEqual(pointer);
 });
 it("retains pointer after effect auth departure without publishing stale terminal fact",async()=>{
  const s=await setup();s.port.advanceOperation.mockImplementation(async()=>{s.context.value=null;return {...pointer,disposition:"accepted"};});
  expect((await s.controller.advance()).status).toBe("idle");expect(s.clear).not.toHaveBeenCalled();expect(await s.store.read(scope)).toEqual(pointer);
 });
 it("does not advance after another controller replaced original pointer during status",async()=>{
  const s=await setup(),replacement={...pointer,operationKey:"mmos-project-adopt-"+"c".repeat(40)};
  s.port.readOperation.mockImplementation(async()=>{await s.store.clearIfEqual(scope,pointer);await s.store.reserve(scope,replacement);return ready();});
  expect((await s.controller.advance()).status).toBe("unknown");expect(s.port.advanceOperation).not.toHaveBeenCalled();expect(await s.store.read(scope)).toEqual(replacement);expect(s.clear).toHaveBeenCalledTimes(1);
 });
 it("joins another explicit advance while the original status is already in flight",async()=>{
  const s=await setup();let release!:(value:EffectReceipt)=>void;let statusStarted!:()=>void;
  const started=new Promise<void>(resolve=>{statusStarted=resolve;});
  s.port.readOperation.mockImplementation(()=>{statusStarted();return new Promise(resolve=>{release=resolve;});});
  const first=s.controller.advance();await started;const second=s.controller.advance();release(ready());await Promise.all([first,second]);
  expect(s.port.readOperation).toHaveBeenCalledTimes(1);expect(s.port.advanceOperation).toHaveBeenCalledTimes(1);expect(s.port.submit).not.toHaveBeenCalled();
 });
 it("clears an already overall accepted operation from observation without another phase effect",async()=>{
  const s=await setup({...pointer,disposition:"accepted"});expect((await s.controller.advance()).status).toBe("accepted");expect(s.port.advanceOperation).not.toHaveBeenCalled();expect(await s.store.read(scope)).toBeNull();
 });
 it("retains original if terminal compare-clear fails",async()=>{
  const s=await setup();s.clear.mockResolvedValue(false);expect((await s.controller.advance()).status).toBe("unknown");expect(await s.store.read(scope)).toEqual(pointer);
 });
});
