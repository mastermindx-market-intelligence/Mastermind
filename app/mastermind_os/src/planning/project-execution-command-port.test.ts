import { describe, expect, it, vi } from "vitest";
import plan from "../fixtures/project-plan-canonical-owner.json";
import { decodeProjectPlan } from "./project-plan";
import { projectExecutionContext, type ProjectExecutionContextAvailable } from "./project-execution-context";
import { ProjectExecutionCommandPort, projectExecutionOperationKey } from "./project-execution-command-port";
import { projectExecutionArguments, type ProjectExecutionPreview, type ProjectExecutionOperation } from "./project-execution-transport";
import { intentIdForOperationKey } from "../orchestration/operation-key";
import { OperationController, type OperationPointer, type OwnerContext, type PendingPointerStore } from "../orchestration/operation-controller";

const context = projectExecutionContext(decodeProjectPlan(plan,{work_ref:"WS:ONE"}),{work_ref:"WS:ONE"}) as ProjectExecutionContextAvailable;
const preview: ProjectExecutionPreview = {
  schema:"mastermind.project_execution_preview.v1",work_ref:"WS:ONE",context_sha256:"c".repeat(64),
  execution_binding_sha256:"d".repeat(64),execution_state:"WORK_CAPABLE",continuation_mode:"DURABLE",
  coordinator:{provider:"codex",model:"installed-model",effort:"high"},
  binding:{workstream:"WS:ONE",priority:0,attemptLimit:1,projects:[{ref:"executive-infrastructure",label:"Project team"}],
    profiles:[{ref:"research_only",label:"Research team"},{ref:"bounded_code_change",label:"Build in declared paths"}]},
};
const form = {workstreamRef:"WS:ONE",projectRef:"executive-infrastructure",profileRef:"research_only",
  goal:"Finish the project",handoffText:"Exact original handoff"};
function response(operation: ProjectExecutionOperation, data: unknown) {
  return {schema:"mastermind.project_execution_private_result.v1",operation,ok:true,data,error:null};
}
function accepted(operation: "submit"|"status", args: Record<string,unknown>, extra={}) {
  return response(operation,{operation_key:args.operation_key,work_ref:args.work_ref,state:"ACCEPTED",receipt:{
    schema:"mastermind.ceo_intent_receipt.v2",intent_id:intentIdForOperationKey(String(args.operation_key)),
    fingerprint:"f".repeat(64),job_id:"JOB-001",status:"QUEUED",accepted:true,duplicate:operation==="status",dispatched:false,
    authority:{requested:["READ","RESEARCH"],policy_sha256:"a".repeat(64),authority_level:"A0"},grounding:{},created_at_ms:0,...extra,
  }});
}
function setup(handler=(operation:ProjectExecutionOperation,args:Record<string,unknown>):unknown =>
  operation==="preview" ? response(operation,preview) : accepted(operation,args)) {
  let owner:OwnerContext|null={principalScope:"a".repeat(64),generation:"1"};
  const request=vi.fn(async(operation:ProjectExecutionOperation,args:Readonly<Record<string,unknown>>) => handler(operation,{...args}));
  const port=new ProjectExecutionCommandPort({request},()=>owner);
  const intent=()=>port.makeLaunchIntent(form,context,preview)!;
  return {port,intent,request,setOwner:(value:OwnerContext|null)=>{owner=value;}};
}

describe("project execution through the existing command owner",()=>{
  it("previews without preparing an effect and launches the dynamic project",async()=>{
    const f=setup();
    expect(await f.port.preview(context,new AbortController().signal)).toEqual(preview);
    expect(f.request.mock.calls.map(c=>c[0])).toEqual(["preview"]);
    const intent=f.intent(),pointer=f.port.prepare(intent);
    expect(intent.payload.handoff_text).toBe(form.handoffText);
    expect(intent.payload.continuation_mode).toBe("DURABLE");
    expect(pointer.operationKey).toBe(projectExecutionOperationKey("a".repeat(64),intent.payload));
    expect(await f.port.submit(pointer,intent,new AbortController().signal)).toMatchObject({
      disposition:"accepted",missionSelection:{workRef:"WS:ONE",rootJobId:"JOB-001"}});
  });
  it("binds changed handoff, paths, checks and continuation mode into the operation identity",()=>{
    const f=setup(),base=f.intent().payload;
    for(const changed of [
      {...base,handoff_text:"Changed handoff"},
      {...base,continuation_mode:"ATTENDED"},
      {...base,execution_profile:"bounded_code_change",allowed_write_paths:["app/example"],validation:{git_diff_check:true}},
    ]) expect(projectExecutionOperationKey("a".repeat(64),changed)).not.toBe(base.operation_key);
    expect(f.port.makeLaunchIntent({...form,frontierModelAlias:"native-alias"},context,preview)).toBeNull();
    expect(f.port.makeLaunchIntent({...form,profileRef:"bounded_code_change"},context,preview)).toBeNull();
    const build=f.port.makeLaunchIntent({...form,profileRef:"bounded_code_change",allowedWritePaths:["app/example"],
      validation:{git_diff_check:true}},context,preview)!;
    expect(build.payload.allowed_write_paths).toEqual(["app/example"]);
  });
  it("retains only the pointer after a lost reply and recovers the same root without resubmit",async()=>{
    const f=setup((operation,args)=>{
      if(operation==="submit") throw Error("lost response");
      return accepted("status",args);
    });
    let saved:OperationPointer|null=null;
    const store:PendingPointerStore={
      read:()=>saved,
      reserve:(_scope,pointer)=>saved ? {reserved:false,pointer:saved} : (saved=pointer,{reserved:true}),
      clearIfEqual:(_scope,pointer)=>saved?.operationKey===pointer.operationKey ? (saved=null,true) : false,
    };
    const controller=new OperationController(f.port,store);
    await controller.begin(f.intent());
    expect(saved).toEqual(f.port.prepare(f.intent()));
    expect(Object.keys(saved!)).toEqual(["kind","targetKey","operationKey"]);
    const reopened=new OperationController(f.port,store);
    const recovered=await reopened.recover();
    expect(JSON.stringify(recovered)).toContain("JOB-001");
    expect(saved).toBeNull();
    expect(f.request.mock.calls.map(c=>c[0])).toEqual(["submit","status"]);
    expect(f.request.mock.calls[1][1]).toEqual({operation_key:f.intent().payload.operation_key,work_ref:"WS:ONE"});
  });
  it.each(["operation_conflict","effect_unknown","refused"])("keeps ambiguous effects distinct from pre-effect %s",async code=>{
    const f=setup(operation=>({schema:"mastermind.project_execution_private_result.v1",operation,ok:false,data:null,
      error:{code,message:"Opaque private failure"}}));
    const intent=f.intent(),pointer=f.port.prepare(intent);
    expect((await f.port.submit(pointer,intent,new AbortController().signal)).disposition).toBe(code==="refused"?"refused":"unknown");
    expect((await f.port.readOperation(pointer,new AbortController().signal)).disposition).toBe("unknown");
  });
  it("rejects a foreign accepted root receipt and a foreign outer operation",async()=>{
    const f=setup((operation,args)=>accepted(operation as "submit",args,{intent_id:"auto-foreign"}));
    const intent=f.intent(),pointer=f.port.prepare(intent);
    expect((await f.port.submit(pointer,intent,new AbortController().signal)).disposition).toBe("unknown");
    const other=setup((_operation,args)=>accepted("status",args));
    expect((await other.port.submit(pointer,intent,new AbortController().signal)).disposition).toBe("unknown");
  });
  it("rejects stale owner completion and malformed source/scope before transport",async()=>{
    let finish!:(value:unknown)=>void;
    const f=setup(()=>new Promise(resolve=>{finish=resolve;}));
    const pending=f.port.preview(context,new AbortController().signal);
    f.setOwner({principalScope:"a".repeat(64),generation:"2"});finish(response("preview",preview));
    await expect(pending).rejects.toThrow("CONTEXT_CHANGED");
    const args=setup().intent().payload;
    expect(()=>projectExecutionArguments("submit",{...args,allowed_write_paths:["../escape"]})).toThrow();
    expect(()=>projectExecutionArguments("submit",{...args,endpoint:"https://foreign"})).toThrow();
  });
});
