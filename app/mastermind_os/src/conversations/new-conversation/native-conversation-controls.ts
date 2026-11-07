/** Stateless native Stop/resume/recovery methods on incumbent command ports. */
import {conversationCreateSettled} from './fresh-conversation-contract';
import type {CommandIntent,EffectReceipt,OperationPointer,OwnerContext} from '../../orchestration/operation-controller';
import {freshConversationTarget,parseFreshConversationTarget,mintFreshConversationCommandKey,type FreshConversationOriginalSelector} from '../../orchestration/fresh-conversation-target';
import {decodeNativeFreshResult,type NativeFreshData,type NativeFreshControlData} from './native-fresh-result';
import {validateNativeFreshRequest,type NativeFreshRequest,type NativeFreshOperation} from './native-fresh-request';
export interface NativeConversationObservation {
 readonly selection:FreshConversationOriginalSelector;readonly data:NativeFreshData;current():boolean;
}
export interface NativeControlTransport {request(operation:NativeFreshOperation,request:NativeFreshRequest,signal:AbortSignal):Promise<unknown>;}
export interface NativeControlOptions {readonly owner:()=>OwnerContext|null;readonly canModify:()=>boolean;readonly transport:NativeControlTransport;}
export interface PreparedNativeResume {
 readonly request:NativeFreshRequest;readonly preview:NativeFreshControlData;readonly owner:OwnerContext;readonly witness:NativeConversationObservation;
}
export interface NativeControlBinding {
 readCurrent(selection:FreshConversationOriginalSelector,signal:AbortSignal):Promise<NativeFreshData|null>;
 makeStopIntent(observation:NativeConversationObservation):CommandIntent|null;
 makeResumeRequest(observation:NativeConversationObservation):NativeFreshRequest|null;
 previewResume(observation:NativeConversationObservation,request:NativeFreshRequest,signal:AbortSignal):Promise<PreparedNativeResume|null>;
 makeResumeIntent(prepared:PreparedNativeResume):CommandIntent|null;
 readOriginalControl(kind:'stop'|'resume',selection:FreshConversationOriginalSelector,key:string,signal:AbortSignal):Promise<NativeFreshControlData|null>;
}
const closed=()=>Error('NATIVE_CONVERSATION_CONTROL_UNAVAILABLE');
const same=(a:OwnerContext|null,b:OwnerContext|null)=>!!a&&!!b&&a.principalScope===b.principalScope&&a.generation===b.generation;
const ownerCopy=(owner:OwnerContext)=>Object.freeze({principalScope:owner.principalScope,generation:owner.generation});
const nativeKey=(key:unknown,kind:'stop'|'resume')=>typeof key==='string'&&new RegExp('^mmos-native-'+kind+'-[0-9a-f]{40}$').exec(key)?.[0]===key;
const result=(p:OperationPointer,accepted=false):EffectReceipt=>({...p,disposition:accepted?'accepted':'unknown',reason:accepted?'ACCEPTED':'UNKNOWN_RECEIPT'});
function nativeSelector(value:FreshConversationOriginalSelector):FreshConversationOriginalSelector|null {
 const selected=parseFreshConversationTarget(freshConversationTarget(value));
 return selected&&('reference'in selected||/^mmos-native-create-[0-9a-f]{40}$/.test(selected.operation_key))?selected:null;
}
function selector(request:NativeFreshRequest):FreshConversationOriginalSelector|null {
 return nativeSelector(request.reference?{work_ref:request.work_ref,reference:request.reference}:
  {work_ref:request.work_ref,operation_key:request.operation_key!});
}
function observed(value:NativeConversationObservation):NativeFreshData|null {
 try{
  if(typeof value.current!=='function'||value.current()!==true||!nativeSelector(value.selection))return null;
  const data=decodeNativeFreshResult({schema:'mastermind.executive.fresh_conversation_result.v2',operation:'read',ok:true,data:value.data,error:null},'read',value.selection);
  return data?.ok&&data.data.schema==='mastermind.executive.fresh_conversation_data.v2'?data.data:null;
 }catch{return null;}
}
function targetMatches(data:NativeFreshData,request:NativeFreshRequest,kind:'stop'|'resume'):boolean {
 if(!data.session)return false;
 return kind==='stop'?request.binding_digest===data.session.binding_digest&&data.state==='ACTIVE'&&data.can_stop&&!!data.active_turn&&request.turn_id===data.active_turn.turn_id:
  data.state==='IDLE'&&data.can_resume&&!!data.head_result&&request.expected_result_digest===data.head_result.digest;
}
type Payload={request:NativeFreshRequest;owner:OwnerContext;witness:NativeConversationObservation};
function payload(intent:CommandIntent):Payload|null{
 try{
  if(intent.kind!=='conversation_stop'&&intent.kind!=='conversation_resume')return null;
  const value=intent.payload as Payload;
  if(!value||typeof value!=='object'||Object.keys(value).sort().join(',')!=='owner,request,witness')return null;
  const kind=intent.kind==='conversation_stop'?'stop':'resume',request=validateNativeFreshRequest(value.request,kind);
  const key=kind==='stop'?request.stop_key:request.resume_key;
  if(!nativeKey(key,kind)||!same(value.owner,value.owner)||Object.keys(value.owner).length!==2)return null;
  const selected=selector(request),data=observed(value.witness);
  if(!selected||freshConversationTarget(selected)!==intent.targetKey||
    freshConversationTarget(value.witness.selection)!==intent.targetKey||!data||!targetMatches(data,request,kind))return null;
  return {request,owner:ownerCopy(value.owner),witness:value.witness};
 }catch{return null;}
}
function keyOf(request:NativeFreshRequest,kind:'stop'|'resume'){return (kind==='stop'?request.stop_key:request.resume_key)!;}
function parentMatches(parent:OperationPointer,control:OperationPointer):boolean{
 const selected=parent.kind==='conversation_create'&&/^mmos-native-create-[0-9a-f]{40}$/.test(parent.operationKey)
  ?{work_ref:parent.targetKey,operation_key:parent.operationKey}
  :parent.kind==='conversation_turn'&&/^mmos-native-turn-[0-9a-f]{40}$/.test(parent.operationKey)?parseFreshConversationTarget(parent.targetKey):null;
 return !!selected&&control.kind==='conversation_stop'&&nativeKey(control.operationKey,'stop')&&freshConversationTarget(selected)===control.targetKey;
}
export function createNativeControlAdapter(options:NativeControlOptions){
 async function request(operation:NativeFreshOperation,args:NativeFreshRequest,signal:AbortSignal,modify=false){
  const before=options.owner(),transport=options.transport,call=transport.request;
  if(!before||signal.aborted||modify&&options.canModify()!==true)throw closed();
  const checked=validateNativeFreshRequest(args,operation);
  const raw=await call.call(transport,operation,checked,signal);
  if(signal.aborted||!same(before,options.owner())||options.transport!==transport||transport.request!==call||
    modify&&options.canModify()!==true)throw closed();
  return raw;
 }
 async function readCurrent(selection:FreshConversationOriginalSelector,signal:AbortSignal){
  if(!nativeSelector(selection))throw closed();
  const args=validateNativeFreshRequest(selection,'read'),raw=await request('read',args,signal);
  const decoded=decodeNativeFreshResult(raw,'read',args);
  return decoded?.ok&&decoded.data.schema==='mastermind.executive.fresh_conversation_data.v2'?decoded.data:null;
 }
 function makeStopIntent(witness:NativeConversationObservation):CommandIntent|null{
  try{
   const data=observed(witness),owner=options.owner();
   if(!data?.can_stop||!data.active_turn||!data.session||!owner||options.canModify()!==true)return null;
   const key=mintFreshConversationCommandKey('conversation_stop','native-v2');if(!key)return null;
   const request=validateNativeFreshRequest({...witness.selection,stop_key:key,turn_id:data.active_turn.turn_id,binding_digest:data.session.binding_digest},'stop');
   return {kind:'conversation_stop',targetKey:freshConversationTarget(witness.selection),payload:{request,owner:ownerCopy(owner),witness}};
  }catch{return null;}
 }
 function makeResumeRequest(witness:NativeConversationObservation):NativeFreshRequest|null{
  try{
   const data=observed(witness);
   if(!data?.can_resume||!data.session||!data.head_result||!options.owner()||options.canModify()!==true)return null;
   const key=mintFreshConversationCommandKey('conversation_resume','native-v2');if(!key)return null;
   return validateNativeFreshRequest({...witness.selection,resume_key:key,expected_result_digest:data.head_result.digest},'resume_preview');
  }catch{return null;}
 }
 async function previewResume(witness:NativeConversationObservation,args:NativeFreshRequest,signal:AbortSignal):Promise<PreparedNativeResume|null>{
  try{
   const data=observed(witness),owner=options.owner(),checked=validateNativeFreshRequest(args,'resume_preview');
   if(!data||!owner||!nativeKey(checked.resume_key,'resume')||!targetMatches(data,checked,'resume')||
     freshConversationTarget(selector(checked))!==freshConversationTarget(witness.selection))return null;
   const raw=await request('resume_preview',checked,signal,true);
   if(!same(owner,options.owner())||!observed(witness))return null;
   const decoded=decodeNativeFreshResult(raw,'resume_preview',checked);
   return decoded?.ok&&decoded.data.schema==='mastermind.executive.fresh_conversation_control_data.v2'&&decoded.data.state==='RESUME_READY'&&
    decoded.data.target?.binding_digest===data.session?.binding_digest
    ?{request:checked,preview:decoded.data,owner:ownerCopy(owner),witness}:null;
  }catch{return null;}
 }
 function makeResumeIntent(prepared:PreparedNativeResume):CommandIntent|null{
  try{
   if(!same(prepared.owner,options.owner())||options.canModify()!==true)return null;
   const decoded=decodeNativeFreshResult({schema:'mastermind.executive.fresh_conversation_result.v2',operation:'resume_preview',ok:true,data:prepared.preview,error:null},'resume_preview',prepared.request);
   if(!decoded?.ok||decoded.data.schema!=='mastermind.executive.fresh_conversation_control_data.v2'||decoded.data.state!=='RESUME_READY'||
    decoded.data.target?.binding_digest!==observed(prepared.witness)?.session?.binding_digest)return null;
   const request=validateNativeFreshRequest({...prepared.request,preview_digest:decoded.data.preview_digest},'resume');
   const intent:CommandIntent={kind:'conversation_resume',targetKey:freshConversationTarget(prepared.witness.selection),
    payload:{request,owner:ownerCopy(prepared.owner),witness:prepared.witness}};
   return payload(intent)?intent:null;
  }catch{return null;}
 }
 async function readOriginalControl(kind:'stop'|'resume',selection:FreshConversationOriginalSelector,key:string,signal:AbortSignal){
  if(!nativeKey(key,kind)||!nativeSelector(selection))throw closed();
  const operation=kind==='stop'?'stop_status':'resume_status';
  const args=validateNativeFreshRequest({...selection,[kind+'_key']:key},operation),raw=await request(operation,args,signal);
  const decoded=decodeNativeFreshResult(raw,operation,args);
  return decoded?.ok&&decoded.data.schema==='mastermind.executive.fresh_conversation_control_data.v2'?decoded.data:null;
 }
 function prepare(intent:CommandIntent):OperationPointer{
  const value=payload(intent);
  if(!value||!same(value.owner,options.owner())||options.canModify()!==true)throw closed();
  return {kind:intent.kind,operationKey:keyOf(value.request,intent.kind==='conversation_stop'?'stop':'resume'),targetKey:intent.targetKey};
 }
 async function submit(pointer:OperationPointer,intent:CommandIntent,signal:AbortSignal):Promise<EffectReceipt>{
  try{
   const value=payload(intent),kind=intent.kind==='conversation_stop'?'stop':'resume';
   if(!value||pointer.kind!==intent.kind||pointer.operationKey!==keyOf(value.request,kind)||pointer.targetKey!==intent.targetKey||
    !same(value.owner,options.owner())||options.canModify()!==true||signal.aborted)return result(pointer);
   const raw=await request(kind,value.request,signal,true);
   if(!same(value.owner,options.owner())||value.witness.current()!==true)return result(pointer);
   const decoded=decodeNativeFreshResult(raw,kind,value.request);
   return result(pointer,!!decoded?.ok&&decoded.data.schema==='mastermind.executive.fresh_conversation_control_data.v2'&&
    decoded.data.state==='APPLIED'&&decoded.data.effect!=='UNKNOWN'&&decoded.data.receipt?.kind==='OPERATOR_OPERATION_APPLIED');
  }catch{return result(pointer);}
 }
 async function readOperation(pointer:OperationPointer,signal:AbortSignal):Promise<EffectReceipt>{
  try{
   const selection=parseFreshConversationTarget(pointer.targetKey);
   if(!selection||pointer.kind!=='conversation_stop'&&pointer.kind!=='conversation_resume')return result(pointer);
   const data=await readOriginalControl(pointer.kind==='conversation_stop'?'stop':'resume',selection,pointer.operationKey,signal);
   return result(pointer,!!data&&data.state==='APPLIED'&&data.receipt?.kind==='OPERATOR_OPERATION_APPLIED');
  }catch{return result(pointer);}
 }

 async function reconcileNativeOperation(pointer:OperationPointer,signal:AbortSignal):Promise<EffectReceipt>{
  try{
   const create=pointer.kind==='conversation_create'&&/^mmos-native-create-[0-9a-f]{40}$/.exec(pointer.operationKey)?.[0]===pointer.operationKey;
   const turn=pointer.kind==='conversation_turn'&&/^mmos-native-turn-[0-9a-f]{40}$/.exec(pointer.operationKey)?.[0]===pointer.operationKey;
   if(!create&&!turn)return result(pointer);
   const selection=create?{work_ref:pointer.targetKey??'',operation_key:pointer.operationKey}:parseFreshConversationTarget(pointer.targetKey);
   if(!selection||!nativeSelector(selection))return result(pointer);
   const operation=create?'recover':'turn_recover';
   const args=validateNativeFreshRequest({...selection,...(turn?{turn_key:pointer.operationKey}:{})},operation);
   const owner=options.owner();if(!owner)return result(pointer);
   const captured=ownerCopy(owner);
   // This observes an existing effect. New-draft eligibility is not recovery authority.
   const raw=await request(operation,args,signal);
   if(!same(captured,options.owner()))return result(pointer);
   const decoded=decodeNativeFreshResult(raw,operation,args);
   const accepted=!!decoded?.ok&&(create?
    decoded.data.schema==='mastermind.executive.fresh_conversation_data.v2'&&conversationCreateSettled(decoded.data):
    decoded.data.schema==='mastermind.executive.fresh_conversation_turn_data.v2'&&decoded.data.state==='RECORDED'&&
      decoded.data.effect!=='UNKNOWN'&&!!decoded.data.initial_consumption&&!!decoded.data.result);
   return result(pointer,accepted);
  }catch{return result(pointer);}
 }
 const binding:NativeControlBinding={readCurrent,makeStopIntent,makeResumeRequest,previewResume,makeResumeIntent,readOriginalControl};
 return {binding,prepare,submit,readOperation,reconcileNativeOperation,
  prepareControl(parent:OperationPointer,intent:CommandIntent){const child=prepare(intent);if(!parentMatches(parent,child))throw closed();return child;},
  submitControl(parent:OperationPointer,child:OperationPointer,intent:CommandIntent,signal:AbortSignal){
   return parentMatches(parent,child)?submit(child,intent,signal):Promise.resolve(result(child));},
  readControlOperation(parent:OperationPointer,child:OperationPointer,signal:AbortSignal){
   return parentMatches(parent,child)?readOperation(child,signal):Promise.resolve(result(child));}};
}
export type NativeControlAdapter=ReturnType<typeof createNativeControlAdapter>;
