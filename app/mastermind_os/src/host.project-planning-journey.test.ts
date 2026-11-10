import {expect,it,vi} from "vitest";
import {bindMissionHost,createNativeClient} from "./host";

// Native invoke/listen is the unavoidable external edge. Everything from the
// public Host through actual native clients, fixed encoders and auth epochs is
// real source. No app launch, credential, socket, Runtime or worker is implied.
const workspaceScope="a".repeat(64);
const requestId="mmos-project-create-"+"b".repeat(40);
const signed={status:"signed_in",reason:null,acquisition:true,content:false};
const context={schema:"mastermind.workspace_source_operation_context.v1",selection:{action:"publish_project_proposal",work_ref:null},owner_context:{principal_scope:workspaceScope},can_inspect:true};
const status={schema:"mastermind.workspace_source_operation_status.v1",selection:{action:"publish_project_proposal",request_id:requestId,work_ref:"WS:CREATED"},owner_context:{principal_scope:workspaceScope},disposition:"unknown",reason:"ORIGINAL_OPERATION_NOT_OBSERVED",request_sha256:null,recipe_fingerprint_sha256:null,phase:null,receipt:null,advance:null};
async function setup() {
 const events=new Map<string,(event:{payload:unknown})=>void>();
 let boundary:(command:string,args?:Record<string,unknown>)=>Promise<unknown>=async command=>{
  if(command==="read_source_operation_context")return context;
  if(command==="source_operation_read")return status;
  if(command==="source_operation_options")return {fixture:"options-data"};
  if(command==="executive_project_planning")return {fixture:"planning-data"};
  throw Error("unexpected fixture effect");
 };
 const invoke=vi.fn(async(command:string,args?:Record<string,unknown>)=>command==="auth_status"?signed:
  command==="executive_auth_status"?{generation:1,available:true}:boundary(command,args));
 const raw=await createNativeClient(invoke as never,async(name,callback)=>{events.set(name,callback);return()=>{};});
 const host=bindMissionHost(raw);
 return {raw,host,invoke,events,setBoundary:(fn:typeof boundary)=>{boundary=fn;}};
}
it("joins CREATE context/options/null-original lookup to the fixed native owner without a guessed workspace",async()=>{
 const e=await setup(),signal=new AbortController().signal;
 expect(await e.host.readSourceOperationContext!({action:"publish_project_proposal",workRef:null,signal})).toEqual(context);
 await e.host.sourceOperations!.readProjectCreationOptions!(signal);
 expect(await e.host.sourceOperations!.readSourceOperation({schema:"mastermind.workspace_source_operation_lookup.v1",action:"publish_project_proposal",request_id:requestId,work_ref:null},signal)).toEqual(status);
 expect(e.invoke.mock.calls.filter(([command])=>command.startsWith("source_operation_")||command==="read_source_operation_context")).toEqual([
  ["read_source_operation_context",{selection:{action:"publish_project_proposal",work_ref:null}}],
  ["source_operation_options",{request:{action:"publish_project_proposal"}}],
  ["source_operation_read",{request:{schema:"mastermind.workspace_source_operation_lookup.v1",action:"publish_project_proposal",request_id:requestId,work_ref:null}}],
 ]);
});
it("preserves original planning and separate consumption keys through Host and actual native encoder",async()=>{
 const e=await setup(),signal=new AbortController().signal,base={operation_key:"original-planning",work_ref:"WS:CREATED"};
 await e.host.projectPlanning!.request("status",base,signal);
 await e.host.projectPlanning!.request("result",base,signal);
 const consume={...base,attempt_id:"ATT-1",result_digest:"c".repeat(64),consumption_operation_key:"original-result-ack"};
 await e.host.projectPlanning!.request("consume",consume,signal);
 expect(e.invoke.mock.calls.filter(([command])=>command==="executive_project_planning")).toEqual([
  ["executive_project_planning",{operation:"status",arguments:base}],
  ["executive_project_planning",{operation:"result",arguments:base}],
  ["executive_project_planning",{operation:"consume",arguments:consume}],
 ]);
 expect(e.invoke.mock.calls.some(([command])=>command==="executive_submit"||command==="source_operation_submit")).toBe(false);
});
it("drops an in-flight original result on actual executive epoch invalidation without a second invocation",async()=>{
 const e=await setup();let resolve!:(v:unknown)=>void;
 e.setBoundary(()=>new Promise(yes=>{resolve=yes;}));
 const read=e.host.projectPlanning!.request("result",{operation_key:"original-planning",work_ref:"WS:CREATED"},new AbortController().signal);
 const refused=expect(read).rejects.toThrow();
 e.events.get("mastermind-executive-auth-state")!({payload:{generation:2,available:false}});
 resolve({fixture:"late-private-result"});await refused;
 expect(e.invoke.mock.calls.filter(([command])=>command==="executive_project_planning")).toHaveLength(1);
});
