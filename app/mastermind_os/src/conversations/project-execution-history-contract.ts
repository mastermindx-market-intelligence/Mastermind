/** Project team run history on the incumbent conversation READ channel. */
import {snapshotConversationData} from './fresh-conversation-reference';
import {decodeFreshConversationInitialResult,type FreshConversationPayload} from './new-conversation/fresh-conversation';
import {projectExecutionPreviousRun,type ProjectExecutionPreviousRun} from '../planning/project-execution-transport';

export interface ProjectExecutionReference {
  readonly schema:'mastermind.project_execution_reference.v1';readonly work_ref:string;readonly root_job_id:string;
  readonly root_event_id:number;readonly root_event_sha256:string;readonly project_execution_source_sha256:string;
  readonly principal_scope_sha256:string;
}
export interface ProjectExecutionHistoryCatalogue {
  readonly schema:'mastermind.project_execution_references.v1';readonly work_ref:string;readonly state:'AVAILABLE';
  readonly coverage:{readonly state:'COMPLETE'|'PARTIAL';readonly limit:8;readonly returned:number};
  readonly entries:readonly {readonly kind:'project_execution';readonly reference:ProjectExecutionReference;readonly goal:string;readonly root_state:string}[];
  readonly can_send:false;
}
export interface ProjectExecutionHistoryWindow {
  readonly schema:'mastermind.project_execution_window.v1';readonly kind:'project_execution';
  readonly reference:ProjectExecutionReference;readonly state:string;readonly goal:string;
  readonly continuation_mode:'DURABLE'|'ATTENDED';
  readonly locator:{readonly work_ref:string;readonly root_job_id:string;readonly job_id:string;readonly attempt_id:string|null};
  readonly previous_run:ProjectExecutionPreviousRun|null;
  readonly result:(FreshConversationPayload & {readonly terminal_receipt_sha256:string})|null;
  readonly parent_witness:ProjectExecutionPreviousRun|null;readonly can_send:false;
}
const states=['QUEUED','RUNNING','CHECKPOINTED','RATE_LIMITED','FAILED','LOST','CANCEL_REQUESTED','COMPLETED','CANCELLED'];
function fail():never {throw Error('PROJECT_EXECUTION_HISTORY_UNAVAILABLE');}
function record(value:unknown,keys:readonly string[]):Record<string,unknown>{
  if(!value||typeof value!=='object'||Array.isArray(value))fail();
  const v=value as Record<string,unknown>;
  if(Object.keys(v).length!==keys.length||!keys.every(k=>Object.hasOwn(v,k)))fail();return v;
}
function text(value:unknown,max:number,pattern?:RegExp):string {
  if(typeof value!=='string'||!value.length||value.length>max||pattern&&pattern.exec(value)?.[0]!==value)fail();return value;
}
const hex=(v:unknown)=>text(v,64,/^[0-9a-f]{64}$/);
const work=(v:unknown)=>{const value=text(v,67,/^WS:[A-Z0-9]+(?:-[A-Z0-9]+)*$/);if(value.length<5)fail();return value;};
function goal(value:unknown):string{
  if(typeof value!=='string'||!value.trim()||Array.from(value).length>4000||value.includes('\u0000'))fail();return value;
}
function freeze<T>(value:T):T{
  if(value&&typeof value==='object'){Object.values(value).forEach(freeze);Object.freeze(value);}return value;
}
function bounded<T>(value:T):T{if(new TextEncoder().encode(JSON.stringify(value)).length>32768)fail();return freeze(value);}
export function decodeProjectExecutionReference(raw:unknown,workRef:string):ProjectExecutionReference{
  const v=record(snapshotConversationData(raw),['schema','work_ref','root_job_id','root_event_id','root_event_sha256','project_execution_source_sha256','principal_scope_sha256']);
  if(v.schema!=='mastermind.project_execution_reference.v1'||work(v.work_ref)!==work(workRef)||workRef.length<5||
    !Number.isSafeInteger(v.root_event_id)||Number(v.root_event_id)<1)fail();
  return freeze({schema:'mastermind.project_execution_reference.v1',work_ref:workRef,
    root_job_id:text(v.root_job_id,256,/^JOB-[0-9]+$/),root_event_id:v.root_event_id as number,
    root_event_sha256:hex(v.root_event_sha256),project_execution_source_sha256:hex(v.project_execution_source_sha256),
    principal_scope_sha256:hex(v.principal_scope_sha256)});
}
export function decodeProjectExecutionCatalogue(raw:unknown,workRef:string):ProjectExecutionHistoryCatalogue{
  const v=record(snapshotConversationData(raw),['schema','work_ref','state','coverage','entries','can_send']);
  const c=record(v.coverage,['state','limit','returned']);
  if(v.schema!=='mastermind.project_execution_references.v1'||v.state!=='AVAILABLE'||work(v.work_ref)!==work(workRef)||v.can_send!==false||
    !['COMPLETE','PARTIAL'].includes(String(c.state))||c.limit!==8||!Array.isArray(v.entries)||v.entries.length>8||c.returned!==v.entries.length)fail();
  const entries=v.entries.map(rawRow=>{
    const row=record(rawRow,['kind','reference','goal','root_state']);
    if(row.kind!=='project_execution'||!states.includes(String(row.root_state)))fail();
    return {kind:'project_execution' as const,reference:decodeProjectExecutionReference(row.reference,workRef),
      goal:goal(row.goal),root_state:String(row.root_state)};
  });
  if(new Set(entries.map(row=>row.reference.root_job_id)).size!==entries.length)fail();
  return bounded({schema:'mastermind.project_execution_references.v1',work_ref:workRef,state:'AVAILABLE',
    coverage:{state:c.state as 'COMPLETE'|'PARTIAL',limit:8,returned:entries.length},entries,can_send:false});
}
export function decodeProjectExecutionWindow(raw:unknown,reference:ProjectExecutionReference):ProjectExecutionHistoryWindow{
  const v=record(snapshotConversationData(raw),['schema','kind','reference','state','goal','continuation_mode','locator','previous_run','result','parent_witness','can_send']);
  const expectedSnapshot=snapshotConversationData(reference) as ProjectExecutionReference;
  const expected=decodeProjectExecutionReference(expectedSnapshot,work(expectedSnapshot?.work_ref));
  const ref=decodeProjectExecutionReference(v.reference,expected.work_ref);
  const locator=record(v.locator,['work_ref','root_job_id','job_id','attempt_id']);
  if(v.schema!=='mastermind.project_execution_window.v1'||v.kind!=='project_execution'||JSON.stringify(ref)!==JSON.stringify(expected)||
    v.can_send!==false||!states.includes(String(v.state))||!['DURABLE','ATTENDED'].includes(String(v.continuation_mode))||
    locator.work_ref!==ref.work_ref||locator.root_job_id!==ref.root_job_id||locator.job_id!==ref.root_job_id||
    !(locator.attempt_id===null||typeof locator.attempt_id==='string'&&locator.attempt_id.length>0&&locator.attempt_id.length<=128))fail();
  const previous=v.previous_run===null?null:projectExecutionPreviousRun(v.previous_run);
  const parent=v.parent_witness===null?null:projectExecutionPreviousRun(v.parent_witness);
  let result:ProjectExecutionHistoryWindow['result']=null;
  if(v.result!==null){
    const data=record(v.result,['digest','envelope','terminal_receipt_sha256']);
    const payload=decodeFreshConversationInitialResult({digest:data.digest,envelope:data.envelope},
      {job_id:ref.root_job_id,root_job_id:ref.root_job_id,attempt_id:locator.attempt_id as string|null});
    if(!payload||!payload.envelope||typeof payload.envelope!=='object'||(payload.envelope as Record<string,unknown>).role!=='aggregation')fail();
    const aggregation=(payload.envelope as Record<string,unknown>).role_result as Record<string,unknown>|null;
    if(!aggregation||typeof aggregation!=='object'||Array.isArray(aggregation)||
      !['mastermind.aggregation_result/v1','mastermind.aggregation_result/v2'].includes(String(aggregation.schema_version))||
      aggregation.root_job_id!==ref.root_job_id||
      (aggregation.schema_version==='mastermind.aggregation_result/v2'?aggregation.coordinator_job_id!==ref.root_job_id:
        Object.hasOwn(aggregation,'coordinator_job_id')))fail();
    result={...payload,terminal_receipt_sha256:hex(data.terminal_receipt_sha256)};
  }
  if((v.state==='COMPLETED')!==!!result||(v.state==='COMPLETED')!==!!parent)fail();
  if(parent&&(parent.root_job_id!==ref.root_job_id||parent.root_event_id!==ref.root_event_id||
    parent.root_event_sha256!==ref.root_event_sha256||parent.project_execution_source_sha256!==ref.project_execution_source_sha256||
    parent.attempt_id!==locator.attempt_id||parent.result_envelope_sha256!==result!.digest||
    parent.terminal_receipt_sha256!==result!.terminal_receipt_sha256))fail();
  return bounded({schema:'mastermind.project_execution_window.v1',kind:'project_execution',reference:ref,state:String(v.state),goal:goal(v.goal),
    continuation_mode:v.continuation_mode as 'DURABLE'|'ATTENDED',
    locator:{work_ref:ref.work_ref,root_job_id:ref.root_job_id,job_id:ref.root_job_id,attempt_id:locator.attempt_id as string|null},
    previous_run:previous,result,parent_witness:parent,can_send:false});
}
