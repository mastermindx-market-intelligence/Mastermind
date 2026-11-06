/**
 * INERT SOURCE FIXTURE — shared App integration/browser proof adapter.
 * No credentials, authenticated service, provider, paid worker or live effects.
 * Product main never imports this module. The caller supplies the incumbent
 * pending-pointer store; no second persistence mechanism exists here.
 */
import {bindMissionHost,createNativeClient,type AuthState,type MissionHost} from "./host";
import {controlRoomFixture,missionFixture} from "./test-fixtures";
import programs from "./fixtures/programs-available-workspace-service.json";
import plan from "./fixtures/project-plan-canonical-owner.json";
import work from "./fixtures/work-service-available.json";
import historyFixture from "./fixtures/project-execution-history-owner.json";
import {createProjectConversationCatalogueOwner} from "./conversations/project-conversation-catalogue-owner";
import {attachProjectExecution} from "./planning/project-execution-command-port";
import {projectExecutionArguments,type ProjectExecutionOperation} from "./planning/project-execution-transport";
import {intentIdForOperationKey} from "./orchestration/operation-key";
import type {OrchestratorCommandBinding} from "./orchestration/host-command-bindings";
import type {PendingPointerStore} from "./orchestration/operation-controller";

export const PROJECT_EXECUTION_PROOF_WORK = historyFixture.completed_read.reference.work_ref;
export const PROJECT_EXECUTION_PROOF_SCOPE = historyFixture.completed_read.reference.principal_scope_sha256;
export const PROJECT_EXECUTION_PROOF_GOAL = historyFixture.completed_read.goal;
export type ProjectExecutionProofMode = "accepted"|"refused"|"lost_reply";
export type ProjectExecutionProofHistory = "empty"|"queued"|"completed";
const signed:AuthState={status:"signed_in",reason:null,acquisition:true,content:true};
const result=(operation:ProjectExecutionOperation,data:unknown)=>({
  schema:"mastermind.project_execution_private_result.v1",operation,ok:true,data,error:null,
});

export async function createProjectExecutionProofFixture(store:PendingPointerStore,options:{
  history?:ProjectExecutionProofHistory;multipleRoots?:boolean;mode?:ProjectExecutionProofMode;
}={}){
  let auth=signed,mode=options.mode??"accepted",historyMode=options.history??"completed",readEpoch=0;
  let holdPreview=false;
  let notifyNative!:(event:{payload:unknown})=>void;
  const readListeners=new Set<()=>void>(),controlListeners=new Set<()=>void>();
  const heldPreviews:Array<()=>void>=[];
  const requests:Array<{operation:ProjectExecutionOperation;arguments:Record<string,unknown>}>=[];
  const room=controlRoomFixture();
  const responsibility=structuredClone(room.autonomy.responsibilities[0]);
  room.work=[room.work[0]];room.work[0].work_ref=PROJECT_EXECUTION_PROOF_WORK;
  room.work[0].agent_os.workstream=PROJECT_EXECUTION_PROOF_WORK.slice(3);
  room.work[0].agent_os.title="Project team fixture";
  for(const binding of room.work[0].bindings)binding.work_ref=PROJECT_EXECUTION_PROOF_WORK;
  room.work[0].executive.jobs[0].workstream=PROJECT_EXECUTION_PROOF_WORK;
  room.autonomy.responsibilities=[];
  const publishRoots=(roots:string[])=>{
    if(!roots.length){room.autonomy.responsibilities=[];return;}
    const row=structuredClone(responsibility);
    row.responsibility_ref=PROJECT_EXECUTION_PROOF_WORK;
    row.root_job_id=roots.length===1?roots[0]:null;
    row.root_job_candidates=roots;
    row.root_job_ambiguous=roots.length!==1;
    row.runtime_root_state=roots.length===1?"RESOLVED":"CONFLICT";
    row.dispatch.responsibility_ref=PROJECT_EXECUTION_PROOF_WORK;
    row.dispatch.root_job_id=row.root_job_id;
    row.dispatch.evidence.responsibility_ref=PROJECT_EXECUTION_PROOF_WORK;
    row.dispatch.evidence.root_job_id=row.root_job_id;
    room.work[0].executive.jobs[0].job_id=roots[0];
    room.autonomy.responsibilities=[row];
  };
  if(historyMode!=="empty")publishRoots(options.multipleRoots?["JOB-001","JOB-900"]:["JOB-001"]);
  const sourcePlan=structuredClone(plan);
  sourcePlan.selection.work_ref=PROJECT_EXECUTION_PROOF_WORK;
  sourcePlan.source.path="agentos/workstreams/WS-"+PROJECT_EXECUTION_PROOF_WORK.slice(3)+".md";
  sourcePlan.plan.objective=PROJECT_EXECUTION_PROOF_GOAL;
  const invoke=async(command:string):Promise<unknown>=>{
    if(command==="auth_status")return auth;
    if(command==="auth_sign_out"||command==="auth_sign_in"){
      auth=command==="auth_sign_out"?{status:"signed_out",reason:"USER_SIGNED_OUT",acquisition:false,content:false}:signed;
      notifyNative({payload:auth});return auth;
    }
    if(command==="read_programs")return {...structuredClone(programs),control_room:structuredClone(room)};
    if(command==="read_work")return structuredClone(work);
    if(command==="read_project_plan")return structuredClone(sourcePlan);
    throw Error("INERT_FIXTURE_UNSUPPORTED_READ");
  };
  const client=await createNativeClient(invoke as Parameters<typeof createNativeClient>[0],
    async(_event,listener)=>{notifyNative=listener;return()=>{};});
  if(!client.invalidationGeneration)throw Error("INERT_FIXTURE_GENERATION_UNAVAILABLE");
  const authGeneration=()=>client.invalidationGeneration!();
  let snapshot={mode,historyMode,previewCount:0,submitCount:0,statusCount:0,lastOperationKey:"",heldPreviews:0,readEpoch};
  const changed=()=>{
    snapshot={mode,historyMode,previewCount:requests.filter(x=>x.operation==="preview").length,
      submitCount:requests.filter(x=>x.operation==="submit").length,
      statusCount:requests.filter(x=>x.operation==="status").length,
      lastOperationKey:String(requests.at(-1)?.arguments.operation_key??""),heldPreviews:heldPreviews.length,readEpoch};
    for(const listener of controlListeners)listener();
  };
  const invalidateHistory=()=>{readEpoch++;for(const listener of readListeners)listener();changed();};
  const unavailable=():never=>{throw Error("INERT_FIXTURE_UNSUPPORTED_OPERATION");};
  const base:OrchestratorCommandBinding={store,
    port:{context:()=>client.getState().status==="signed_in"?{
      principalScope:PROJECT_EXECUTION_PROOF_SCOPE,generation:"fixture-"+authGeneration()}:null,
      prepare:unavailable,submit:unavailable,readOperation:unavailable},
    getView:()=>({projects:[],profiles:[],session:null}),subscribe:()=>()=>{},
    makeLaunchIntent:()=>null,makeMessageIntent:()=>null,makeStopIntent:()=>null,
  };
  const request=async(operation:ProjectExecutionOperation,input:Readonly<Record<string,unknown>>,signal:AbortSignal):Promise<unknown>=>{
    const args=projectExecutionArguments(operation,input);
    if(signal.aborted||client.getState().status!=="signed_in")throw Error("INERT_FIXTURE_NOT_CURRENT");
    requests.push({operation,arguments:structuredClone(args)});changed();
    if(operation==="preview"){
      const value=result(operation,{schema:"mastermind.project_execution_preview.v1",work_ref:PROJECT_EXECUTION_PROOF_WORK,
        context_sha256:"c".repeat(64),execution_state:"WORK_CAPABLE",execution_binding_sha256:"d".repeat(64),
        execution_profile_bindings:{research_only:"d".repeat(64),bounded_code_change:"e".repeat(64)},
        continuation_mode:"DURABLE",coordinator:{provider:"inert-fixture",model:"fixture-only-no-provider",effort:"fixture"},
        execution_scope:{repository:"mastermindx-market-intelligence/Mastermind",commit:"e".repeat(40)},
        previous_run:args.previous_run??null,
        binding:{workstream:PROJECT_EXECUTION_PROOF_WORK,priority:0,attemptLimit:1,
          projects:[{ref:"executive-infrastructure",label:"Project team"}],
          profiles:[{ref:"research_only",label:"Research team"},{ref:"bounded_code_change",label:"Build in declared paths"}]}});
      if(holdPreview)return new Promise(resolve=>{heldPreviews.push(()=>resolve(value));changed();});
      return value;
    }
    if(operation==="submit"&&mode==="refused")return {
      schema:"mastermind.project_execution_private_result.v1",operation,ok:false,data:null,
      error:{code:"refused",message:"INERT FIXTURE refusal before execution"}};
    publishRoots(historyMode==="empty"?["JOB-002"]:["JOB-001","JOB-002"]);
    if(operation==="submit"&&mode==="lost_reply")throw Error("INERT FIXTURE lost response");
    return result(operation,{operation_key:args.operation_key,work_ref:PROJECT_EXECUTION_PROOF_WORK,state:"ACCEPTED",
      receipt:{schema:"mastermind.ceo_intent_receipt.v2",intent_id:intentIdForOperationKey(String(args.operation_key)),
        fingerprint:"f".repeat(64),job_id:"JOB-002",status:"QUEUED",accepted:true,dispatched:false,duplicate:operation==="status",
        authority:{requested:["READ","RESEARCH"],policy_sha256:"a".repeat(64),authority_level:"A0"},
        grounding:{},created_at_ms:0}});
  };
  const host:MissionHost={...bindMissionHost(client),commandBinding:attachProjectExecution(base,{request}),
    readMissionV3:undefined,readMission:async({workRef,rootJobId})=>missionFixture(workRef,rootJobId),
    session:{refresh:async()=>{},setStopCondition:()=>{},createProjectCatalogueReader:selection=>{
      const owner=createProjectConversationCatalogueOwner({
        workRef:selection.currentWorkRef,selectionGeneration:selection.selectionGeneration,
        transport:{
          context:()=>client.getState().status==="signed_in"&&selection.currentWorkRef()===PROJECT_EXECUTION_PROOF_WORK
            ?{workRef:PROJECT_EXECUTION_PROOF_WORK,principalScope:PROJECT_EXECUTION_PROOF_SCOPE,generation:"inert-read-"+readEpoch}:null,
          authGeneration:()=>authGeneration(),
          available:()=>client.getState().acquisition&&selection.currentWorkRef()===PROJECT_EXECUTION_PROOF_WORK,
          subscribe:listener=>{readListeners.add(listener);const release=client.subscribe(()=>listener());
            return()=>{readListeners.delete(listener);release();};},
          refreshContext:async()=>{},catalogue:async()=>unavailable(),read:async()=>unavailable(),
          executionReferences:async()=>historyMode==="empty"?{
            ...structuredClone(historyFixture.catalogue),entries:[],coverage:{state:"COMPLETE",limit:8,returned:0},
          }:structuredClone(historyMode==="queued"?historyFixture.pending_catalogue:historyFixture.catalogue),
          readExecutionReference:async()=>structuredClone(historyMode==="queued"?historyFixture.pending_read:historyFixture.completed_read),
        }});
      return {owner,dispose:()=>owner.dispose()};
    }},
  };
  return {host,requests,store,scope:PROJECT_EXECUTION_PROOF_SCOPE,workRef:PROJECT_EXECUTION_PROOF_WORK,
    witness:historyFixture.completed_read.parent_witness,
    getSnapshot:()=>snapshot,subscribe:(listener:()=>void)=>{controlListeners.add(listener);return()=>{controlListeners.delete(listener);};},
    setMode:(next:ProjectExecutionProofMode)=>{mode=next;changed();},
    setHistory:(next:ProjectExecutionProofHistory)=>{historyMode=next;invalidateHistory();},
    invalidateHistory,
    holdPreview:(value:boolean)=>{holdPreview=value;changed();},
    releasePreviews:()=>{const held=heldPreviews.splice(0);for(const release of held)release();changed();},
  };
}
