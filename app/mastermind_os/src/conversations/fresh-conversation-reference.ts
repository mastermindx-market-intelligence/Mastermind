/** Closed original fresh-admission READ references. A source-principal digest
 * is original provenance; it is not the current READ ticket or a send grant. */
import {decodeFreshConversationInitialResult,type FreshConversationPayload} from './new-conversation/fresh-conversation';
export interface FreshConversationReference {
  readonly schema:'mastermind.fresh_conversation_reference.v1';
  readonly work_ref:string;readonly root_job_id:string;readonly root_event_id:number;
  readonly root_event_sha256:string;readonly principal_scope_sha256:string;
}
export interface FreshConversationCatalogue {
  readonly schema:'mastermind.fresh_conversation_references.v1';readonly work_ref:string;readonly state:'AVAILABLE';
  readonly coverage:Readonly<{state:'COMPLETE'|'PARTIAL';limit:8;returned:number}>;
  readonly entries:readonly Readonly<{kind:'fresh_native';reference:FreshConversationReference;initial_message:string;root_state:string}>[];
}
export interface FreshConversationWindow {
  readonly schema:'mastermind.fresh_conversation_window.v1';readonly kind:'fresh_native';readonly reference:FreshConversationReference;
  readonly state:'ADMITTED'|'RETAINED'|'SETTLED'|'RECONCILIATION_REQUIRED';
  readonly locator:Readonly<{work_ref:string;root_job_id:string;job_id:string|null;attempt_id:string|null}>;
  readonly epoch:null|Readonly<{attempt_id:string;binding_digest:string;generation_digest:string}>;
  readonly initial_message:string;readonly initial_result:FreshConversationPayload|null;
  readonly initial_consumption:null|Readonly<{state:'CONSUMED';event_id:number;event_sha256:string;initial_digest:string}>;
  readonly turns:readonly Readonly<{turn_key:string;message:string;state:'RECORDED'|'RECONCILIATION_REQUIRED';result:FreshConversationPayload|null;parent_consumed:false}>[];
  readonly can_send:false;readonly parent_consumed:false;
}
function fail():never{throw Error('PROJECT_CONVERSATION_UNAVAILABLE');}
function exact(value:unknown,keys:readonly string[]):Record<string,unknown>{
  if(!value||typeof value!=='object'||Array.isArray(value)||![Object.prototype,null].includes(Object.getPrototypeOf(value)))fail();
  const all=Reflect.ownKeys(value);if(all.length!==keys.length||all.some(key=>typeof key!=='string'||!keys.includes(key)))fail();
  const out:Record<string,unknown>=Object.create(null);
  for(const key of keys){const field=Object.getOwnPropertyDescriptor(value,key);if(!field||!field.enumerable||!('value'in field))fail();out[key]=field.value;}
  return out;
}
function text(value:unknown,max:number,pattern?:RegExp):string{
  if(typeof value!=='string'||!value.length||value.length>max)fail();
  for(const point of value){if(point.length===1&&point.charCodeAt(0)>=0xd800&&point.charCodeAt(0)<=0xdfff)fail();}
  if(pattern&&pattern.exec(value)?.[0]!==value)fail();return value;
}
const work=(value:unknown)=>text(value,72,/^WS:[A-Za-z0-9][A-Za-z0-9._-]{0,68}$/);
const hex=(value:unknown)=>text(value,64,/^[0-9a-f]{64}$/);
function integer(value:unknown,min=0):number{if(typeof value!=='number'||!Number.isSafeInteger(value)||value<min)fail();return value;}
function frozen<T>(value:T):T{if(value&&typeof value==='object'){Object.values(value).forEach(frozen);Object.freeze(value);}return value;}
function budget<T>(value:T):T{if(new TextEncoder().encode(JSON.stringify(value)).length>32768)fail();return frozen(value);}
function list(value:unknown,max:number):unknown[]{
  if(!Array.isArray(value)||Object.getPrototypeOf(value)!==Array.prototype)fail();
  const d=Object.getOwnPropertyDescriptor(value,'length');if(!d||!('value'in d))fail();
  const length=integer(d.value);if(length>max||Reflect.ownKeys(value).length!==length+1)fail();
  const out:unknown[]=[];
  for(let i=0;i<length;i++){const field=Object.getOwnPropertyDescriptor(value,String(i));if(!field||!field.enumerable||!('value'in field))fail();out.push(field.value);}return out;
}
function message(value:unknown):string{
  const result=text(value,1400);
  for(const point of result){const code=point.codePointAt(0)!;if((code<32&&!['\t','\n','\r'].includes(point))||(code>=127&&code<=159))fail();}
  if(!/[^\t\n\r \u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]/u.test(result)||Array.from(result).length>700||new TextEncoder().encode(result).length>2800)fail();
  return result;
}
function sameReference(left:FreshConversationReference,right:FreshConversationReference):boolean{
  return left.work_ref===right.work_ref&&left.root_job_id===right.root_job_id&&left.root_event_id===right.root_event_id&&
    left.root_event_sha256===right.root_event_sha256&&left.principal_scope_sha256===right.principal_scope_sha256;
}
/** Descriptor-only JSON snapshot before entering the reused result decoder.
 * This copies data, not authority, and never calls a raw toJSON or getter. */
function jsonData(value:unknown,seen=new Set<object>(),depth=0,nodes={count:0}):unknown{
  if(depth>32||++nodes.count>32768)fail();
  if(value===null||typeof value==='boolean')return value;
  if(typeof value==='number'){if(!Number.isFinite(value))fail();return value;}
  if(typeof value==='string'){
    if(value.length>32768)fail();for(const point of value){if(point.length===1&&point.charCodeAt(0)>=0xd800&&point.charCodeAt(0)<=0xdfff)fail();}return value;
  }
  if(!value||typeof value!=='object'||seen.has(value))fail();seen.add(value);
  let result:unknown;
  if(Array.isArray(value))result=list(value,32768).map(item=>jsonData(item,seen,depth+1,nodes));
  else{
    if(![Object.prototype,null].includes(Object.getPrototypeOf(value)))fail();
    const out:Record<string,unknown>=Object.create(null);
    for(const key of Reflect.ownKeys(value)){
      if(typeof key!=='string')fail();const field=Object.getOwnPropertyDescriptor(value,key);
      if(!field||!field.enumerable||!('value'in field))fail();out[key]=jsonData(field.value,seen,depth+1,nodes);
    }result=out;
  }
  seen.delete(value);return result;
}
export function decodeFreshConversationReference(raw:unknown,expectedWorkRef:string):FreshConversationReference{
  const value=exact(raw,['schema','work_ref','root_job_id','root_event_id','root_event_sha256','principal_scope_sha256']);
  if(value.schema!=='mastermind.fresh_conversation_reference.v1'||work(value.work_ref)!==work(expectedWorkRef))fail();
  return frozen({schema:'mastermind.fresh_conversation_reference.v1',work_ref:expectedWorkRef,
    root_job_id:text(value.root_job_id,256,/^JOB-[0-9]+$/),root_event_id:integer(value.root_event_id,1),
    root_event_sha256:hex(value.root_event_sha256),principal_scope_sha256:hex(value.principal_scope_sha256)});
}
export function decodeFreshConversationCatalogue(raw:unknown,expectedWorkRef:string):FreshConversationCatalogue{
  const value=exact(raw,['schema','work_ref','state','coverage','entries']);
  if(value.schema!=='mastermind.fresh_conversation_references.v1'||value.state!=='AVAILABLE'||work(value.work_ref)!==work(expectedWorkRef))fail();
  const coverage=exact(value.coverage,['state','limit','returned']);
  if(!['COMPLETE','PARTIAL'].includes(coverage.state as string)||coverage.limit!==8)fail();
  const entries=list(value.entries,8).map(rawEntry=>{
    const row=exact(rawEntry,['kind','reference','initial_message','root_state']);
    if(row.kind!=='fresh_native'||!['QUEUED','RUNNING','CHECKPOINTED','RATE_LIMITED','FAILED','LOST','CANCEL_REQUESTED','COMPLETED','CANCELLED'].includes(row.root_state as string))fail();
    return {kind:'fresh_native' as const,reference:decodeFreshConversationReference(row.reference,expectedWorkRef),initial_message:message(row.initial_message),root_state:row.root_state as string};
  });
  if(integer(coverage.returned)!==entries.length||new Set(entries.map(row=>row.reference.root_job_id)).size!==entries.length)fail();
  return budget({schema:'mastermind.fresh_conversation_references.v1',work_ref:expectedWorkRef,state:'AVAILABLE',
    coverage:{state:coverage.state as 'COMPLETE'|'PARTIAL',limit:8,returned:entries.length},entries});
}

/** The source owns complete Role validation and immutable native Events.
 * Display uses the existing qualified sealed-result digest/locator helper;
 * this reader never creates an old operation-key DTO or a send capability. */
export function decodeFreshConversationWindow(raw:unknown,expected:unknown):FreshConversationWindow{
  const expectedData=exact(expected,['schema','work_ref','root_job_id','root_event_id','root_event_sha256','principal_scope_sha256']);
  const wanted=decodeFreshConversationReference(expectedData,work(expectedData.work_ref));
  const value=exact(raw,['schema','kind','reference','state','locator','epoch','initial_message','initial_result','initial_consumption','turns','can_send','parent_consumed']);
  if(value.schema!=='mastermind.fresh_conversation_window.v1'||value.kind!=='fresh_native'||value.can_send!==false||value.parent_consumed!==false||
    !['ADMITTED','RETAINED','SETTLED','RECONCILIATION_REQUIRED'].includes(value.state as string))fail();
  const reference=decodeFreshConversationReference(value.reference,wanted.work_ref);if(!sameReference(reference,wanted))fail();
  const rawLocator=exact(value.locator,['work_ref','root_job_id','job_id','attempt_id']);
  if(rawLocator.work_ref!==reference.work_ref||rawLocator.root_job_id!==reference.root_job_id)fail();
  const identifier=(v:unknown)=>text(v,128,/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/);
  const locator={work_ref:reference.work_ref,root_job_id:reference.root_job_id,
    job_id:rawLocator.job_id===null?null:identifier(rawLocator.job_id),attempt_id:rawLocator.attempt_id===null?null:identifier(rawLocator.attempt_id)};
  if(locator.attempt_id!==null&&locator.job_id===null)fail();
  let epoch:FreshConversationWindow['epoch']=null;
  if(value.epoch!==null){const item=exact(value.epoch,['attempt_id','binding_digest','generation_digest']);
    if(item.attempt_id!==locator.attempt_id||locator.attempt_id===null)fail();epoch={attempt_id:locator.attempt_id,binding_digest:hex(item.binding_digest),generation_digest:hex(item.generation_digest)};}
  if((value.state==='RETAINED')!==(epoch!==null))fail();
  // Helper safely detaches the bounded canonical JSON before computing SHA.
  const initial=value.initial_result===null?null:decodeFreshConversationInitialResult(jsonData(value.initial_result),locator);
  if(value.initial_result!==null&&!initial)fail();
  let consumed:FreshConversationWindow['initial_consumption']=null;
  if(value.initial_consumption!==null){const item=exact(value.initial_consumption,['state','event_id','event_sha256','initial_digest']);
    if(item.state!=='CONSUMED'||!initial||hex(item.initial_digest)!==initial.digest)fail();
    consumed={state:'CONSUMED',event_id:integer(item.event_id,1),event_sha256:hex(item.event_sha256),initial_digest:initial.digest};}
  const turns=list(value.turns,1).map(rawTurn=>{
    const turn=exact(rawTurn,['turn_key','message','state','result','parent_consumed']);
    if(turn.parent_consumed!==false||!['RECORDED','RECONCILIATION_REQUIRED'].includes(turn.state as string)||!initial||!consumed)fail();
    const result=turn.result===null?null:decodeFreshConversationInitialResult(jsonData(turn.result),locator);
    if((turn.state==='RECORDED')!==(result!==null)||turn.result!==null&&!result)fail();
    return {turn_key:identifier(turn.turn_key),message:message(turn.message),state:turn.state as 'RECORDED'|'RECONCILIATION_REQUIRED',result,parent_consumed:false as const};
  });
  if(value.state==='SETTLED'&&!initial)fail();
  return budget({schema:'mastermind.fresh_conversation_window.v1',kind:'fresh_native',reference,
    state:value.state as FreshConversationWindow['state'],locator,epoch,initial_message:message(value.initial_message),initial_result:initial,
    initial_consumption:consumed,turns,can_send:false,parent_consumed:false});
}

/** Reused descriptor-only bounded JSON data snapshot; no source authority. */
export const snapshotConversationData = (value: unknown): unknown => jsonData(value);
