/** TEST ONLY: one whole actual source recording; all unrecorded effects refuse.
 * Native auth/continuity/launch configuration are explicitly inert authority
 * premises. Real NativeClient/Host/ports/controllers/IndexedDB are not replaced. */
import fixture from '../fixtures/project-draft-files-source-issued.json';
import {canonicalJson} from '../orchestration/operation-key';
import {createNativeClient} from '../host';
import {composeMissionHost} from '../compose-mission-host';
import {decodeLaunchBindingConfig} from '../launch-config';
type Rec=Record<string,unknown>;
type Row={sequence:number;operation:string;request:Rec;response:Rec;edge:string};
export {fixture};
export async function createFileConsumerFixture(factory:IDBFactory,negative?:{wrongOrigin?:boolean}){
 const rows=fixture.samples as unknown as Row[],calls:{command:string;args:unknown;sequence:number|null}[]=[],events=new Map<string,(event:{payload:unknown})=>void>();
 let landed=false,loss:string|null=null;
 const same=(a:unknown,b:unknown)=>canonicalJson(a)===canonicalJson(b);
 const pick=(operation:string,request:unknown,filter:(r:Row)=>boolean=()=>true)=>{
  const row=rows.find(r=>r.operation===operation&&filter(r)&&same(r.request,request));
  if(!row)throw Error('INERT_UNRECORDED_OPERAND');calls[calls.length-1].sequence=row.sequence;return structuredClone(row.response);
 };
 const invoke=async(command:string,args?:Rec):Promise<unknown>=>{
  calls.push({command,args,sequence:null});
  if(command==='auth_status')return {status:'signed_in',reason:null,acquisition:true,content:true};
  if(command==='executive_auth_status')return {generation:4,available:true};
  if(command==='terminal_session_status')return {state:'SIGNED_OUT',generation:0,available:false,reason:'FIXTURE_NOT_CONNECTED',principal_scope:null,session_scope:null};
  if(command==='read_native_draft_continuity')return {schema:'mastermind.native_draft_continuity.v1',owner_instance:'1'.repeat(32),privacy_epoch:1,phase:'QUALIFIED',cause:'OWNER_QUALIFIED',principal_scope:fixture.identities.workspace_scope,valid_until_ms:fixture.recorded_at_ms+15000};
  const request=args?.request??args,selection=args?.selection??request;
  if(command==='read_source_operation_context')return pick('context',selection,r=>r.edge==='ACTUAL_WORKSPACE_CONTEXT');
  if(command==='executive_context')return pick('context',{},r=>r.edge==='SIGNED_EXECUTIVE_HTTP');
  if(command==='read_project_knowledge_catalogue'){
   const value=pick('catalogue',selection,r=>(r.response.data_observation as Rec).canonical_data_commit===(landed?fixture.assertions.current_file_commit:fixture.assertions.historical_create_commit));
   if(landed&&negative?.wrongOrigin){
    // Explicit adversarial transport DATA only; never a positive recording.
    const files=(value.project as Rec).files as Rec[];
    for(const file of files)(file.origin as Rec).request_sha256=((value.data_observation as Rec).source_operation as Rec).request_sha256;
   }return value;
  }
  if(command.startsWith('source_operation_')){
   const operation=command.slice('source_operation_'.length);
   const value=pick(operation,request,r=>operation!=='read'||(r.request.action!=='add_project_file'||((r.response.receipt as Rec).kind===(landed?'SOURCE_OBSERVED':'PROPOSAL_OBSERVED'))));
   if(operation==='reconcile'&&(request as Rec).action==='add_project_file')landed=true;
   if(loss===command){loss=null;throw Error('INERT_LOST_RESPONSE_AFTER_RECORDED_OWNER');}
   return value;
  }
  if(command==='executive_project_planning'){
   const operation=String(args?.operation);const value=pick(operation,{arguments:args?.arguments},r=>r.edge==='SIGNED_EXECUTIVE_HTTP');
   if(loss==='planning'){loss=null;throw Error('INERT_LOST_RESPONSE_AFTER_RECORDED_OWNER');}return value;
  }
  throw Error('INERT_UNRECORDED_COMMAND');
 };
 const listen:Parameters<typeof createNativeClient>[1]=async(name,handler)=>{events.set(name,handler);return()=>{events.delete(name);};};
 const client=await createNativeClient(invoke as never,listen);
 const config=decodeLaunchBindingConfig(JSON.stringify({v:1,workstream:'WS:JOURNEY-INTEG',priority:0,attemptLimit:1,projects:[{ref:'executive-infrastructure',label:'Infrastructure'}],profiles:[{ref:'research_only',label:'Research'},{ref:'native_research_only',label:'Native research'}]}))!;
 const composed=composeMissionHost(client,config,factory);await composed.ready;window.MastermindMissionHost=composed.host;
 return {...composed,calls,events,lose:(name:string)=>{loss=name;},expire:()=>events.get('mastermind-auth-state')?.({payload:{status:'signed_out',reason:'SESSION_EXPIRED',acquisition:false,content:false}})};
}
