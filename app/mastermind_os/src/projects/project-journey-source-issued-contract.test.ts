// @vitest-environment jsdom
/** Exact one-run installed owner operands; fixture authority, never live effects.
 * UI options/preview are exercised separately by ProjectPlanningJourney.test.
 * This finite transport/decoder sweep preserves all twenty original envelopes,
 * including the three deliberately unavailable responses; no success splice.
 */
import {expect,it} from "vitest";
import recorded from "../fixtures/project-journey-source-issued-388205.json";
import {createNativeClient,bindMissionHost} from "../host";
import {decodeSourceOperationContext} from "../source-operations/context";
import {decodeSourceOperationStatus} from "../planning/plan-adoption-status";
import {decodeProjectPlan} from "../planning/project-plan";
import {decodeDirectNativeResult,directConsumeIdentity} from "../direct-native-result";
import {ProjectPlanningCommandPort,type PlanningSubmitInput} from "../planning/project-planning-command-port";
import {planningArguments,type PlanningOperation} from "../planning/project-planning-transport";
import {canonicalJson,sha256Hex} from "../orchestration/operation-key";

it("preserves all twenty genuine response/next-request operands through fixed native routes",async()=>{
  // The JSON union is external DATA; runtime decoders below are the authority.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const rows=recorded.samples as any[];
  let selected=rows[0];let last:{command:string,args:unknown}|null=null;
  const signal=new AbortController().signal;
  const client=await createNativeClient(async(command,args)=>{
    if(command==="auth_status")return {status:"signed_in",reason:null,acquisition:true,content:true};
    if(command==="executive_auth_status")return {generation:4,available:true};
    if(command==="terminal_session_status")return {state:"SIGNED_OUT",generation:0,available:false,reason:"FIXTURE_NOT_CONNECTED",principal_scope:null,session_scope:null};
    last={command,args};return structuredClone(selected.response);
  },async()=>()=>{});
  const host=bindMissionHost(client);
  const owner={principalScope:rows[5].response.principal_scope,generation:"fixture-original"};
  // Match the existing Journey's envelope→direct-receipt adapter boundary.
  // The transport retains the raw envelope; the command port accepts its data.
  const planning=new ProjectPlanningCommandPort({request:async(op,args,abort)=>{
    const envelope=await host.projectPlanning!.request(op,args,abort) as {schema:string;operation:string;ok:boolean;error:unknown;data:unknown};
    expect(Object.keys(envelope).sort()).toEqual(["data","error","ok","operation","schema"]);
    expect(envelope.schema).toBe("mastermind.project_initial_planning.private_result.v1");
    expect(envelope.operation).toBe(op);expect(envelope.ok).toBe(true);expect(envelope.error).toBeNull();
    return envelope.data;
  }},()=>owner);
  const intent=planning.makePlanningIntent(recorded.consumer_inputs.planning_input as PlanningSubmitInput)!;
  expect(intent).not.toBeNull();expect(intent.payload).toEqual(rows[6].request.arguments);
  const pointer=planning.prepare(intent);
  const covered:number[]=[];
  for(const row of rows){
    selected=row;const req=row.request;let response:unknown;
    switch(row.sequence){
      case 1:
        response=await host.readSourceOperationContext!({action:req.action,workRef:req.work_ref,signal});
        expect(decodeSourceOperationContext(response,{action:req.action,workRef:req.work_ref})).toEqual(row.response);
        expect(last).toEqual({command:"read_source_operation_context",args:{selection:req}});break;
      case 2:
        response=await host.sourceOperations!.readProjectCreationOptions!(signal);
        expect(last).toEqual({command:"source_operation_options",args:{request:req}});break;
      case 3:
        response=await host.sourceOperations!.prepareSourceOperation(req,signal);
        expect(req.request.profile_sha256).toBe(rows[1].response.profiles.find((p: {id:string})=>p.id===req.request.profile_id).revision);
        expect(row.response.request_sha256).toBe(sha256Hex(canonicalJson(req.request)));
        expect(last).toEqual({command:"source_operation_prepare",args:{request:req}});break;
      case 4:case 15:case 19:
        response=await host.sourceOperations!.submitSourceOperation(req,signal);
        expect(last).toEqual({command:"source_operation_submit",args:{request:req}});
        expect(decodeSourceOperationStatus(response)).toEqual(row.response);break;
      case 5:case 16:
        response=await host.sourceOperations!.reconcileSourceOperation(req,signal);
        expect(last).toEqual({command:"source_operation_reconcile",args:{request:req}});
        expect(decodeSourceOperationStatus(response)).toEqual(row.response);break;
      case 6:
        response=await client.executive!.context(signal);
        expect(last).toEqual({command:"executive_context",args:undefined});break;
      case 7:
        expect((await planning.submit(pointer,intent,signal)).disposition).toBe("accepted");
        response=row.response;
        expect(last).toEqual({command:"executive_project_planning",args:{operation:"submit",arguments:req.arguments}});break;
      case 8:
        expect((await planning.readOperation(pointer,signal)).disposition).toBe("accepted");
        response=row.response;
        expect(last).toEqual({command:"executive_project_planning",args:{operation:"status",arguments:req.arguments}});break;
      case 17:
        response=await host.readProjectPlan!({...req,signal});
        expect(decodeProjectPlan(response,req).availability).toBe("AVAILABLE");
        expect(last).toEqual({command:"read_project_plan",args:{selection:req}});break;
      case 18:
        response=await host.sourceOperations!.readSourceOperation(req,signal);
        expect(last).toEqual({command:"source_operation_read",args:{request:req}});
        expect(decodeSourceOperationStatus(response)).toEqual(row.response);break;
      default:{
        const op=row.operation as PlanningOperation;
        response=await host.projectPlanning!.request(op,planningArguments(op,req.arguments),signal);
        expect(last).toEqual({command:"executive_project_planning",args:{operation:op,arguments:req.arguments}});
        if([10,12,20].includes(row.sequence)){
          expect(row.response.ok).toBe(false);expect(row.response.data).toBeNull();
        }else if(row.sequence===9||row.sequence===11){
          const decoded=decodeDirectNativeResult(row.response.data,{work_ref:req.arguments.work_ref,job_id:rows[7].response.data.job_id,attempt_id:null});
          expect(decoded?.availability).toBe("AVAILABLE");
          expect(decoded?.consumption?.state).toBe(row.sequence===9?"UNCONSUMED":"CONSUMED");
          if(row.sequence===11){
            const identity=directConsumeIdentity(owner.principalScope,decoded!.selection as {work_ref:string;job_id:string;attempt_id:string},decoded!.result!.result_digest);
            expect(req.arguments.consumption_operation_key).toBe(identity.operationKey);
          }
        }else{
          // S24 preview is intentionally raw on this transport; its original
          // private owner qualifies it. No mounted S24 UI decoder is claimed.
          expect([13,14]).toContain(row.sequence);expect(row.response.ok).toBe(true);
          expect(row.response.data.selection.request_id).toBe(req.arguments.proposal_request.request_id);
        }
      }
    }
    expect(response).toEqual(row.response);covered.push(row.sequence);
  }
  expect(covered).toEqual(Array.from({length:20},(_,i)=>i+1));
  expect(rows[14].request.preview_witness).toEqual(rows[12].response.data.preview_witness);
  expect(rows[18].request).toEqual(rows[14].request);
  expect(rows[18].response).toEqual(rows[17].response);
});
