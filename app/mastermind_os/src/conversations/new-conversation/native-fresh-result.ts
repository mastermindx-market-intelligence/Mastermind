/** Closed native action receipts. These are observations, never admission grants. */
import {canonicalJson} from '../../orchestration/operation-key';
import {decodeFreshNativeResult,snapshotConversationData,type FreshConversationReference,type FreshNativeResult} from '../fresh-conversation-reference';
import {nativeExact as exact,nativeFreeze as frozen,nativeHex as hex,nativeId as id,nativeInteger as integer,
  nativeInvalid as fail,nativeKey as key,nativeReference,nativeText as text,nativeWork,
  NATIVE_RESPONSE_BYTES,validateNativeFreshRequest,type NativeFreshOperation,type NativeFreshRequest} from './native-fresh-request';

export type NativeFreshEffect='NONE'|'ADMITTED'|'COMMITTED'|'UNKNOWN';
export interface NativeFreshLocator {readonly work_ref:string;readonly root_job_id:string;readonly job_id:string|null;readonly attempt_id:string|null;}
export interface NativeFreshSession {readonly attempt_id:string;readonly session_epoch_id:string;readonly process_generation_id:string;
  readonly provider_session_id:string;readonly binding_digest:string;}
export interface NativeFreshActiveTurn {readonly turn_id:string;readonly begin_operation_id:string;}
export interface NativeFreshConsumption {readonly state:'CONSUMED';readonly event_id:number;readonly event_sha256:string;readonly initial_digest:string;}
export interface NativeFreshPreview {readonly digest:string;readonly profile_digest:string;readonly source_digest:string;
  readonly grounding:Readonly<Record<string,unknown>>;readonly attempt_limit:1;readonly worker_account:'REGISTERED_NOT_SESSION_ATTESTED';}
interface Selected {readonly work_ref:string;readonly operation_key:string|null;readonly reference:FreshConversationReference|null;
  readonly parent_consumed:false;readonly effect:NativeFreshEffect;}
export interface NativeFreshData extends Selected {
  readonly schema:'mastermind.executive.fresh_conversation_data.v2';
  readonly state:'PREVIEW_READY'|'ABSENT'|'ADMITTED'|'ACTIVE'|'CREATED'|'IDLE'|'SETTLED'|'RECONCILIATION_REQUIRED';
  readonly preview:NativeFreshPreview|null;readonly locator:NativeFreshLocator|null;readonly session:NativeFreshSession|null;
  readonly active_turn:NativeFreshActiveTurn|null;readonly result:FreshNativeResult|null;readonly head_result:FreshNativeResult|null;
  readonly can_send:boolean;readonly can_resume:boolean;readonly can_stop:boolean;
}
interface TurnBase extends Selected {readonly turn_key:string|null;readonly locator:NativeFreshLocator;
  readonly initial_consumption:NativeFreshConsumption|null;readonly can_send:boolean;}
export interface NativeFreshTurnData extends TurnBase {
  readonly schema:'mastermind.executive.fresh_conversation_turn_data.v2';
  readonly state:'CONSUMED'|'ABSENT'|'RECONCILIATION_REQUIRED'|'RECORDED';readonly result:FreshNativeResult|null;
}
export interface NativeFreshTurnPreview extends TurnBase {
  readonly schema:'mastermind.executive.fresh_conversation_turn_preview.v2';readonly state:'TURN_READY';readonly preview_digest:string;
}
export interface NativeFreshControlData extends Selected {
  readonly schema:'mastermind.executive.fresh_conversation_control_data.v2';readonly kind:'stop'|'resume';readonly control_key:string;
  readonly state:'RESUME_READY'|'ABSENT'|'INTENT'|'APPLIED'|'EFFECT_UNKNOWN'|'RECONCILIATION_REQUIRED';
  readonly locator:NativeFreshLocator|null;readonly session:NativeFreshSession|null;readonly active_turn:NativeFreshActiveTurn|null;
  readonly operation_id:string|null;readonly receipt:Readonly<{kind:'OPERATOR_OPERATION_INTENT'|'OPERATOR_OPERATION_APPLIED'|'OPERATOR_OPERATION_EFFECT_UNKNOWN';
    command_id:string;event_id:number;event_sha256:string}>|null;
  readonly head_result:FreshNativeResult|null;readonly preview_digest:string|null;
  readonly target:Readonly<{turn_id:string;binding_digest:string}|{expected_result_digest:string;binding_digest:string}>|null;
}
export type NativeFreshSuccessData=NativeFreshData|NativeFreshTurnData|NativeFreshTurnPreview|NativeFreshControlData;
export type NativeFreshResult={readonly ok:true;readonly data:NativeFreshSuccessData}|
  {readonly ok:false;readonly data:null;readonly error:Readonly<{code:string;message:string}>};
const BASE='mastermind.executive.fresh_conversation_data.v2';
const TURN='mastermind.executive.fresh_conversation_turn_data.v2';
const PREVIEW='mastermind.executive.fresh_conversation_turn_preview.v2';
const CONTROL='mastermind.executive.fresh_conversation_control_data.v2';
function one<T extends string>(value:unknown,options:readonly T[]):T {
  if(typeof value!=='string'||!options.includes(value as T))fail();return value as T;
}
function bool(value:unknown):boolean{if(typeof value!=='boolean')fail();return value;}
function nullable<T>(value:unknown,decode:(raw:unknown)=>T):T|null{return value===null?null:decode(value);}
function selected(value:Record<string,unknown>,request:NativeFreshRequest):Selected {
  if(nativeWork(value.work_ref)!==request.work_ref||value.operation_key!==(request.operation_key??null)||
    value.parent_consumed!==false)fail();
  const reference=nullable(value.reference,v=>nativeReference(v,request.work_ref));
  if(canonicalJson(reference)!==canonicalJson(request.reference??null))fail();
  if(value.operation_key!==null)key(value.operation_key);
  return {work_ref:request.work_ref,operation_key:request.operation_key??null,reference,parent_consumed:false,
    effect:one(value.effect,['NONE','ADMITTED','COMMITTED','UNKNOWN'])};
}
function locator(raw:unknown,request:NativeFreshRequest,child:boolean):NativeFreshLocator {
  const v=exact(raw,['work_ref','root_job_id','job_id','attempt_id']);
  if(nativeWork(v.work_ref)!==request.work_ref||request.reference&&v.root_job_id!==request.reference.root_job_id)fail();
  const result={work_ref:request.work_ref,root_job_id:id(v.root_job_id),job_id:nullable(v.job_id,id),attempt_id:nullable(v.attempt_id,id)};
  if(child&&(result.job_id===null||result.attempt_id===null))fail();return result;
}
function session(raw:unknown,where:NativeFreshLocator|null):NativeFreshSession {
  const v=exact(raw,['attempt_id','session_epoch_id','process_generation_id','provider_session_id','binding_digest']);
  if(!where||where.attempt_id!==v.attempt_id)fail();
  return {attempt_id:id(v.attempt_id),session_epoch_id:id(v.session_epoch_id),process_generation_id:id(v.process_generation_id),
    provider_session_id:id(v.provider_session_id),binding_digest:hex(v.binding_digest)};
}
function active(raw:unknown,owner:NativeFreshSession|null):NativeFreshActiveTurn {
  const v=exact(raw,['turn_id','begin_operation_id']);if(owner===null)fail();
  return {turn_id:id(v.turn_id),begin_operation_id:id(v.begin_operation_id)};
}
function consumption(raw:unknown,request:NativeFreshRequest):NativeFreshConsumption {
  const v=exact(raw,['state','event_id','event_sha256','initial_digest']);
  if(v.state!=='CONSUMED'||request.initial_digest!==undefined&&v.initial_digest!==request.initial_digest)fail();
  return {state:'CONSUMED',event_id:integer(v.event_id,1),event_sha256:hex(v.event_sha256),initial_digest:hex(v.initial_digest)};
}
function decodeBase(raw:unknown,request:NativeFreshRequest):NativeFreshData {
  const v=exact(raw,['schema','work_ref','operation_key','reference','state','effect','parent_consumed',
    'preview','locator','session','active_turn','result','head_result','can_send','can_resume','can_stop']);
  if(v.schema!==BASE)fail();const common=selected(v,request);
  const state=one(v.state,['PREVIEW_READY','ABSENT','ADMITTED','ACTIVE','CREATED','IDLE','SETTLED','RECONCILIATION_REQUIRED']);
  const where=nullable(v.locator,r=>locator(r,request,['ACTIVE','CREATED','IDLE'].includes(state)));
  const owner=nullable(v.session,r=>session(r,where)),turn=nullable(v.active_turn,r=>active(r,owner));
  const result=nullable(v.result,decodeFreshNativeResult),head=nullable(v.head_result,decodeFreshNativeResult);
  const send=bool(v.can_send),resume=bool(v.can_resume),stop=bool(v.can_stop);
  if(['ABSENT','PREVIEW_READY'].includes(state)&&
    ([where,owner,turn,result,head].some(x=>x!==null)||send||resume||stop||common.effect!=='NONE'))fail();
  if(state==='ADMITTED'&&(where===null||[owner,turn,result,head].some(x=>x!==null)||send||resume||stop))fail();
  if(['CREATED','IDLE'].includes(state)&&[where,owner,result,head].some(x=>x===null))fail();
  if(['SETTLED','RECONCILIATION_REQUIRED'].includes(state)&&(send||resume||stop))fail();
  if((turn!==null)!==(state==='ACTIVE')||head!==null&&result===null)fail();
  if(stop&&turn===null||send&&(state!=='CREATED'||owner===null||head===null)||
    resume&&(state!=='IDLE'||owner===null||head===null))fail();
  let preview:NativeFreshPreview|null=null;
  if(state==='PREVIEW_READY'){
    const p=exact(v.preview,['digest','profile_digest','source_digest','grounding','attempt_limit','worker_account']);
    if(p.attempt_limit!==1||p.worker_account!=='REGISTERED_NOT_SESSION_ATTESTED'||!p.grounding||
      typeof p.grounding!=='object'||Array.isArray(p.grounding))fail();
    preview={digest:hex(p.digest),profile_digest:hex(p.profile_digest),source_digest:hex(p.source_digest),
      grounding:p.grounding as Readonly<Record<string,unknown>>,attempt_limit:1,worker_account:'REGISTERED_NOT_SESSION_ATTESTED'};
  }else if(v.preview!==null)fail();
  return {schema:BASE,...common,state,preview,locator:where,session:owner,active_turn:turn,result,head_result:head,
    can_send:send,can_resume:resume,can_stop:stop};
}
function decodeTurn(raw:unknown,request:NativeFreshRequest,preview:boolean):NativeFreshTurnData|NativeFreshTurnPreview {
  const v=exact(raw,['schema','work_ref','operation_key','reference','turn_key','state','effect',
    'initial_consumption','locator','parent_consumed','can_send',preview?'preview_digest':'result']);
  if(v.schema!==(preview?PREVIEW:TURN)||v.turn_key!==(request.turn_key??null))fail();
  const common=selected(v,request);one(common.effect,['NONE','COMMITTED','UNKNOWN']);
  const state=preview?one(v.state,['TURN_READY']):one(v.state,['CONSUMED','ABSENT','RECONCILIATION_REQUIRED','RECORDED']);
  const where=locator(v.locator,request,state!=='ABSENT'),used=nullable(v.initial_consumption,r=>consumption(r,request)),send=bool(v.can_send);
  if(['TURN_READY','CONSUMED','RECORDED'].includes(state)&&used===null||send&&!['TURN_READY','CONSUMED'].includes(state))fail();
  const result={...common,turn_key:request.turn_key??null,locator:where,initial_consumption:used,can_send:send};
  if(preview){
    if(common.effect!=='NONE'||!send)fail();
    return {schema:PREVIEW,...result,state:'TURN_READY',preview_digest:hex(v.preview_digest)};
  }
  const payload=state==='RECORDED'?decodeFreshNativeResult(v.result):null;
  if(state!=='RECORDED'&&v.result!==null)fail();
  return {schema:TURN,...result,state:state as NativeFreshTurnData['state'],result:payload};
}
function decodeControl(raw:unknown,request:NativeFreshRequest):NativeFreshControlData {
  const v=exact(raw,['schema','work_ref','operation_key','reference','kind','control_key','state','effect',
    'locator','session','active_turn','operation_id','receipt','head_result','preview_digest','parent_consumed','target']);
  if(v.schema!==CONTROL)fail();
  const common=selected(v,request);one(common.effect,['NONE','COMMITTED','UNKNOWN']);
  const kind=one(v.kind,['stop','resume']),control=key(v.control_key);
  if(control!==(kind==='stop'?request.stop_key:request.resume_key))fail();
  const state=one(v.state,['RESUME_READY','ABSENT','INTENT','APPLIED','EFFECT_UNKNOWN','RECONCILIATION_REQUIRED']);
  const where=nullable(v.locator,r=>locator(r,request,state!=='ABSENT'));
  const owner=nullable(v.session,r=>session(r,where)),turn=nullable(v.active_turn,r=>active(r,owner));
  const head=nullable(v.head_result,decodeFreshNativeResult),operation=nullable(v.operation_id,id);
  let target:NativeFreshControlData['target']=null;
  if(v.target!==null){
    const field=kind==='stop'?'turn_id':'expected_result_digest',t=exact(v.target,[field,'binding_digest']);
    const binding=hex(t.binding_digest);
    if(request.binding_digest!==undefined&&request.binding_digest!==binding||
      request[field]!==undefined&&request[field]!==t[field])fail();
    target=kind==='stop'?{turn_id:id(t.turn_id),binding_digest:binding}:
      {expected_result_digest:hex(t.expected_result_digest),binding_digest:binding};
  }
  if(['RESUME_READY','INTENT','APPLIED','EFFECT_UNKNOWN'].includes(state)&&target===null)fail();
  let receipt:NativeFreshControlData['receipt']=null;
  if(v.receipt!==null){
    const r=exact(v.receipt,['kind','command_id','event_id','event_sha256']);
    if(operation===null)fail();
    const receiptKind=one(r.kind,['OPERATOR_OPERATION_INTENT','OPERATOR_OPERATION_APPLIED','OPERATOR_OPERATION_EFFECT_UNKNOWN']);
    const suffix=receiptKind==='OPERATOR_OPERATION_APPLIED'?':applied':receiptKind==='OPERATOR_OPERATION_EFFECT_UNKNOWN'?':effect-unknown':'';
    if(suffix&&(!operation.startsWith('ohf-op:')||operation.length>113))fail();
    const command=id(r.command_id);if(command!==operation+suffix)fail();
    if(['INTENT','APPLIED','EFFECT_UNKNOWN'].includes(state)&&receiptKind!=='OPERATOR_OPERATION_'+state)fail();
    receipt={kind:receiptKind,command_id:command,event_id:integer(r.event_id,1),event_sha256:hex(r.event_sha256)};
  }else if(['INTENT','APPLIED','EFFECT_UNKNOWN'].includes(state))fail();
  if(state==='ABSENT'&&(common.effect!=='NONE'||[target,owner,turn,operation,receipt,head,v.preview_digest].some(x=>x!==null)))fail();
  let preview:string|null=null;
  if(state==='RESUME_READY'){
    if(kind!=='resume'||common.effect!=='NONE'||where===null||owner===null||head===null||target===null||
      turn!==null||receipt!==null||operation!==null||head.digest!==request.expected_result_digest||
      target.binding_digest!==owner.binding_digest)fail();
    preview=hex(v.preview_digest);
  }else if(v.preview_digest!==null)fail();
  return {schema:CONTROL,...common,kind,control_key:control,state,locator:where,session:owner,active_turn:turn,
    operation_id:operation,receipt,head_result:head,preview_digest:preview,target};
}
/** Returns null on malformed, foreign, over-budget, or contradictory DATA. */
export function decodeNativeFreshResult(raw:unknown,operation:NativeFreshOperation,expected:unknown):NativeFreshResult|null {
  try{
    const request=validateNativeFreshRequest(expected,operation);
    const snap=snapshotConversationData(raw);
    if(new TextEncoder().encode(JSON.stringify({ok:true,result:snap})+'\n').length>NATIVE_RESPONSE_BYTES)fail();
    const v=exact(snap,['schema','operation','ok','data','error']);
    if(v.schema!=='mastermind.executive.fresh_conversation_result.v2'||v.operation!==operation||typeof v.ok!=='boolean')fail();
    if(!v.ok){
      if(v.data!==null)fail();const error=exact(v.error,['code','message']);
      const code=text(error.code,64,/^[a-z][a-z0-9_]{0,63}$/),message=text(error.message,512);
      if([...message].length>256)fail();
      return frozen({ok:false,data:null,error:{code,message}});
    }
    if(v.error!==null)fail();
    let data:NativeFreshSuccessData;
    if(['preview','create','status','read','recover'].includes(operation))data=decodeBase(v.data,request);
    else if(operation.startsWith('resume')||operation.startsWith('stop'))data=decodeControl(v.data,request);
    else data=decodeTurn(v.data,request,operation==='turn_preview');
    const states:Partial<Record<NativeFreshOperation,readonly string[]>>={
      consume:['CONSUMED'],consume_status:['ABSENT','CONSUMED'],
      turn:['ABSENT','RECONCILIATION_REQUIRED','RECORDED'],turn_status:['ABSENT','RECONCILIATION_REQUIRED','RECORDED'],
      turn_read:['ABSENT','RECONCILIATION_REQUIRED','RECORDED'],turn_recover:['ABSENT','RECONCILIATION_REQUIRED','RECORDED'],turn_preview:['TURN_READY'],resume_preview:['RESUME_READY'],
      resume:['RECONCILIATION_REQUIRED','INTENT','APPLIED','EFFECT_UNKNOWN'],stop:['RECONCILIATION_REQUIRED','INTENT','APPLIED','EFFECT_UNKNOWN'],
      resume_status:['ABSENT','RECONCILIATION_REQUIRED','INTENT','APPLIED','EFFECT_UNKNOWN'],
      stop_status:['ABSENT','RECONCILIATION_REQUIRED','INTENT','APPLIED','EFFECT_UNKNOWN']};
    if(states[operation]&&!states[operation]!.includes(data.state))fail();
    if(['consume_status','turn','turn_status','turn_read','turn_recover'].includes(operation)&&'can_send'in data&&data.can_send)fail();
    if((operation==='preview')!==(data.state==='PREVIEW_READY')||(operation==='turn_preview')!==(data.state==='TURN_READY')||
      (operation==='resume_preview')!==(data.state==='RESUME_READY'))fail();
    if(['status','read','consume_status','turn_status','turn_read','resume_status','stop_status','preview','turn_preview','resume_preview','recover','turn_recover'].includes(operation)&&data.effect!=='NONE')fail();
    if(data.schema===CONTROL&&data.kind!==operation.split('_')[0])fail();
    return frozen({ok:true,data});
  }catch{return null;}
}
