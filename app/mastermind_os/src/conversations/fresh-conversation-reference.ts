/** Closed original fresh-admission READ references. A source-principal digest
 * is original provenance; it is not the current READ ticket or a send grant. */
import {decodeFreshConversationInitialResult,type FreshConversationPayload} from './new-conversation/fresh-conversation';
import {canonicalJson,sha256Hex} from '../orchestration/operation-key';
export interface FreshConversationReference {
  readonly schema:'mastermind.fresh_conversation_reference.v1';
  readonly work_ref:string;readonly root_job_id:string;readonly root_event_id:number;
  readonly root_event_sha256:string;readonly principal_scope_sha256:string;
}
export interface FreshConversationReadRequest extends FreshConversationReference {
  readonly before_event_id?:number;
  readonly fragment?:FreshConversationInputSelector;
  readonly content?:FreshNativeContentSelector;
}
export interface FreshConversationPage {
  readonly kind:'initial'|'history';readonly before_event_id:number|null;readonly next_before_event_id:number|null;
}
export interface FreshConversationCatalogue {
  readonly schema:'mastermind.fresh_conversation_references.v1';readonly work_ref:string;readonly state:'AVAILABLE';
  readonly coverage:Readonly<{state:'COMPLETE'|'PARTIAL';limit:8;returned:number}>;
  readonly entries:readonly Readonly<{kind:'fresh_native';reference:FreshConversationReference;initial_message:string;root_state:string}>[];
}
export interface FreshConversationWindow {
  readonly schema:'mastermind.fresh_conversation_window.v1'|'mastermind.fresh_conversation_window.v2';readonly kind:'fresh_native';readonly reference:FreshConversationReference;
  readonly state:'ADMITTED'|'RETAINED'|'SETTLED'|'RECONCILIATION_REQUIRED';
  readonly locator:Readonly<{work_ref:string;root_job_id:string;job_id:string|null;attempt_id:string|null}>;
  readonly epoch:null|Readonly<{attempt_id:string;binding_digest:string;generation_digest:string}>;
  readonly initial_message:string;readonly initial_result:FreshConversationPayload|null;
  /** v2 distinguishes a history page's omitted envelope from an absent seal. */
  readonly initial_digest?:string|null;readonly page?:FreshConversationPage;
  readonly initial_consumption:null|Readonly<{state:'CONSUMED';event_id:number;event_sha256:string;initial_digest:string}>;
  readonly turns:readonly Readonly<{turn_key:string;message:string;state:'RECORDED'|'RECONCILIATION_REQUIRED';result:FreshConversationPayload|null;parent_consumed:false}>[];
  readonly can_send:false;readonly parent_consumed:false;
}
export interface FreshNativeInput {
  readonly preview:string;readonly sha256:string;readonly utf8_bytes:number;readonly complete:boolean;
  readonly source_event_id:number;readonly source_event_sha256:string;
}
export type FreshConversationInputSelector = Readonly<{
  kind:'initial_input'|'turn_input';turn_key?:string;source_event_id:number;
  source_event_sha256:string;sha256:string;offset_utf8:number;
}>;
export interface FreshNativeResult {
  readonly contract:'mastermind.dsh_native_conversation/v1';readonly digest:string;
  readonly reference:Readonly<{schema_version:'mastermind.dsh_native_conversation_result_ref/v1';
    command_id:string;event_id:number;seal_digest:string;observation_digest:string}>;
}
export type FreshNativeContentSelector=Readonly<{native_ref:FreshNativeResult['reference'];
  offset_bytes:number;expected_sha256:string|null}>;
export interface FreshNativeCatalogueEntry {
  readonly kind:'fresh_native';readonly reference:FreshConversationReference;readonly root_state:string;
  readonly result_contract:'mastermind.dsh_native_conversation/v1';readonly initial_input:FreshNativeInput;
}
export interface FreshConversationHistoryCatalogue extends Omit<FreshConversationCatalogue,'schema'|'entries'> {
  readonly schema:'mastermind.fresh_conversation_references.v1'|'mastermind.fresh_conversation_references.v2';
  readonly entries:readonly (FreshConversationCatalogue['entries'][number]|FreshNativeCatalogueEntry)[];
}
export interface FreshNativeConversationWindow extends Omit<FreshConversationWindow,
  'schema'|'initial_message'|'initial_result'|'turns'|'initial_digest'|'page'> {
  readonly schema:'mastermind.fresh_conversation_window.v3';readonly initial_input:FreshNativeInput;
  readonly initial_result:FreshNativeResult|null;readonly head_result:FreshNativeResult|null;
  readonly initial_digest:string|null;readonly page:FreshConversationPage;
  readonly turns:readonly Readonly<{turn_key:string;input:FreshNativeInput;
    state:'RECORDED'|'RECONCILIATION_REQUIRED';result:FreshNativeResult|null;parent_consumed:false}>[];
}
export type FreshConversationHistoryWindow=FreshConversationWindow|FreshNativeConversationWindow;
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
      if(typeof key!=='string')fail();for(const point of key){const code=point.codePointAt(0)!;if(code>=0xd800&&code<=0xdfff)fail();}const field=Object.getOwnPropertyDescriptor(value,key);
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
export function decodeFreshConversationReadRequest(raw:unknown,expectedWorkRef:string):FreshConversationReadRequest{
  const cursor=raw&&typeof raw==='object'?Object.getOwnPropertyDescriptor(raw,'before_event_id'):undefined;
  const fragment=raw&&typeof raw==='object'?Object.getOwnPropertyDescriptor(raw,'fragment'):undefined;
  const content=raw&&typeof raw==='object'?Object.getOwnPropertyDescriptor(raw,'content'):undefined;
  if([cursor,fragment,content].filter(Boolean).length>1)fail();
  const keys=['schema','work_ref','root_job_id','root_event_id','root_event_sha256','principal_scope_sha256'];
  const value=exact(raw,content?[...keys,'content']:fragment?[...keys,'fragment']:cursor?[...keys,'before_event_id']:keys);
  const base=Object.fromEntries(keys.map(key=>[key,value[key]]));
  const reference=decodeFreshConversationReference(base,expectedWorkRef);
  return frozen({...reference,...(cursor?{before_event_id:integer(value.before_event_id,1)}:{}),
    ...(fragment?{fragment:decodeFreshConversationInputSelector(value.fragment)}:{}),
    ...(content?{content:decodeFreshNativeContentSelector(value.content)}:{})});
}
export function freshConversationInitialDigest(window:FreshConversationHistoryWindow):string|null{
  return window.schema!=='mastermind.fresh_conversation_window.v1'?window.initial_digest??null:window.initial_result?.digest??null;
}
export function freshConversationNextPage(window:FreshConversationHistoryWindow):number|null{
  return window.schema!=='mastermind.fresh_conversation_window.v1'?window.page?.next_before_event_id??null:null;
}
export function decodeFreshConversationWindow(raw:unknown,expected:unknown):FreshConversationWindow{
  const expectedWork=expected&&typeof expected==='object'?Object.getOwnPropertyDescriptor(expected,'work_ref')?.value:undefined;
  const requested=decodeFreshConversationReadRequest(expected,work(expectedWork));
  if(requested.fragment)fail();
  const {before_event_id:before,...wanted}=requested;
  const rawSchema=raw&&typeof raw==='object'?Object.getOwnPropertyDescriptor(raw,'schema')?.value:undefined;
  const v2=rawSchema==='mastermind.fresh_conversation_window.v2';
  const keys=['schema','kind','reference','state','locator','epoch','initial_message','initial_result','initial_consumption','turns','can_send','parent_consumed'];
  const value=exact(raw,v2?[...keys,'initial_digest','page']:keys);
  if(!['mastermind.fresh_conversation_window.v1','mastermind.fresh_conversation_window.v2'].includes(value.schema as string)||
    value.kind!=='fresh_native'||value.can_send!==false||value.parent_consumed!==false||
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
  const initial=value.initial_result===null?null:decodeFreshConversationInitialResult(jsonData(value.initial_result),locator);
  if(value.initial_result!==null&&!initial)fail();
  let initialDigest=initial?.digest??null;
  let page:FreshConversationPage|undefined;
  if(v2){
    const item=exact(value.page,['kind','before_event_id','next_before_event_id']);
    if(item.kind!==(before===undefined?'initial':'history')||item.before_event_id!==(before??null))fail();
    const next=item.next_before_event_id===null?null:integer(item.next_before_event_id,1);
    if(before!==undefined&&(initial!==null||next!==null&&next>=before))fail();
    const digest=value.initial_digest===null?null:hex(value.initial_digest);
    if(before===undefined&&digest!==initialDigest)fail();
    initialDigest=digest;page={kind:item.kind as FreshConversationPage['kind'],before_event_id:before??null,next_before_event_id:next};
  }else if(before!==undefined)fail();
  let consumed:FreshConversationWindow['initial_consumption']=null;
  if(value.initial_consumption!==null){const item=exact(value.initial_consumption,['state','event_id','event_sha256','initial_digest']);
    if(item.state!=='CONSUMED'||!initialDigest||hex(item.initial_digest)!==initialDigest)fail();
    consumed={state:'CONSUMED',event_id:integer(item.event_id,1),event_sha256:hex(item.event_sha256),initial_digest:initialDigest};}
  const turns=list(value.turns,v2?8:1).map(rawTurn=>{
    const turn=exact(rawTurn,['turn_key','message','state','result','parent_consumed']);
    if(turn.parent_consumed!==false||!['RECORDED','RECONCILIATION_REQUIRED'].includes(turn.state as string)||!initialDigest||!consumed)fail();
    const result=turn.result===null?null:decodeFreshConversationInitialResult(jsonData(turn.result),locator);
    if((turn.state==='RECORDED')!==(result!==null)||turn.result!==null&&!result)fail();
    return {turn_key:identifier(turn.turn_key),message:message(turn.message),state:turn.state as 'RECORDED'|'RECONCILIATION_REQUIRED',result,parent_consumed:false as const};
  });
  if(new Set(turns.map(turn=>turn.turn_key)).size!==turns.length)fail();
  if(page?.kind==='history'&&!turns.length&&page.next_before_event_id!==null)fail();
  if(value.state==='SETTLED'&&!initialDigest)fail();
  return budget({schema:value.schema as FreshConversationWindow['schema'],kind:'fresh_native',reference,
    state:value.state as FreshConversationWindow['state'],locator,epoch,initial_message:message(value.initial_message),initial_result:initial,
    ...(v2?{initial_digest:initialDigest,page}:{}),initial_consumption:consumed,turns,can_send:false,parent_consumed:false});
}

/** Reused descriptor-only bounded JSON data snapshot; no source authority. */
export const snapshotConversationData = (value: unknown): unknown => jsonData(value);

function ownSchema(raw:unknown):unknown {
  return raw&&typeof raw==='object'?Object.getOwnPropertyDescriptor(raw,'schema')?.value:undefined;
}
function nativeText(raw:unknown,bytes:number):string {
  const value=text(raw,bytes);
  for(const point of value){const code=point.codePointAt(0)!;
    if((code<32&&!['\t','\n','\r'].includes(point))||(code>=127&&code<=159))fail();}
  if(new TextEncoder().encode(value).length>bytes)fail();return value;
}
export function decodeFreshNativeInput(raw:unknown):FreshNativeInput {
  const value=exact(raw,['preview','sha256','utf8_bytes','complete','source_event_id','source_event_sha256']);
  const preview=nativeText(value.preview,256),length=integer(value.utf8_bytes,1),digest=hex(value.sha256);
  const bytes=new TextEncoder().encode(preview).length;
  if(length>131072||bytes>length||typeof value.complete!=='boolean'||value.complete!==(bytes===length)||
    value.complete&&sha256Hex(preview)!==digest)fail();
  return frozen({preview,sha256:digest,utf8_bytes:length,complete:value.complete,
    source_event_id:integer(value.source_event_id,1),source_event_sha256:hex(value.source_event_sha256)});
}
export function decodeFreshNativeResult(raw:unknown):FreshNativeResult {
  const value=exact(raw,['contract','digest','reference']);
  const ref=exact(value.reference,['schema_version','command_id','event_id','seal_digest','observation_digest']);
  const command=text(ref.command_id,128,/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/),prefix='ohf-native-result:';
  if(value.contract!=='mastermind.dsh_native_conversation/v1'||
    ref.schema_version!=='mastermind.dsh_native_conversation_result_ref/v1'||!command.startsWith(prefix))fail();
  text(command.slice(prefix.length),128,/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/);
  const digest=hex(value.digest);if(hex(ref.seal_digest)!==digest)fail();
  return frozen({contract:'mastermind.dsh_native_conversation/v1',digest,
    reference:{schema_version:'mastermind.dsh_native_conversation_result_ref/v1',command_id:command,
      event_id:integer(ref.event_id,1),seal_digest:digest,observation_digest:hex(ref.observation_digest)}});
}
export function decodeFreshNativeContentSelector(raw:unknown):FreshNativeContentSelector {
  const value=exact(raw,['native_ref','offset_bytes','expected_sha256']);
  const ref=exact(value.native_ref,['schema_version','command_id','event_id','seal_digest','observation_digest']);
  const native=decodeFreshNativeResult({contract:'mastermind.dsh_native_conversation/v1',
    digest:ref.seal_digest,reference:ref}).reference;
  const offset=integer(value.offset_bytes),digest=value.expected_sha256===null?null:hex(value.expected_sha256);
  if(offset>=4*1024*1024||offset>0&&digest===null)fail();
  return frozen({native_ref:native,offset_bytes:offset,expected_sha256:digest});
}
export function decodeFreshConversationInputSelector(raw:unknown):FreshConversationInputSelector {
  const kind=raw&&typeof raw==='object'?Object.getOwnPropertyDescriptor(raw,'kind')?.value:undefined;
  if(kind!=='initial_input'&&kind!=='turn_input')fail();
  const keys=['kind','source_event_id','source_event_sha256','sha256','offset_utf8'];
  const value=exact(raw,kind==='turn_input'?[...keys,'turn_key']:keys);
  const offset=integer(value.offset_utf8);if(offset>=131072)fail();
  return frozen({kind,source_event_id:integer(value.source_event_id,1),
    source_event_sha256:hex(value.source_event_sha256),sha256:hex(value.sha256),offset_utf8:offset,
    ...(kind==='turn_input'?{turn_key:text(value.turn_key,96,/^[A-Za-z0-9][A-Za-z0-9._:-]{0,95}$/)}:{})});
}
export function decodeFreshConversationInputFragment(raw:unknown,expected:FreshConversationReadRequest):Readonly<{
  text:string;utf8_bytes:number;next_offset_utf8:number|null
}> {
  const requested=decodeFreshConversationReadRequest(expected,expected.work_ref);
  if(!requested.fragment)fail();
  const value=exact(raw,['schema','reference','fragment','text','utf8_bytes','next_offset_utf8']);
  const {fragment,...reference}=requested;
  if(value.schema!=='mastermind.fresh_conversation_input_fragment.v1'||
    !sameReference(decodeFreshConversationReference(value.reference,requested.work_ref),reference)||
    canonicalJson(decodeFreshConversationInputSelector(value.fragment))!==canonicalJson(fragment))fail();
  const part=nativeText(value.text,4096),length=integer(value.utf8_bytes,1);
  const end=fragment.offset_utf8+new TextEncoder().encode(part).length;
  const next=value.next_offset_utf8===null?null:integer(value.next_offset_utf8,1);
  if(length>131072||end>length||(end===length?next!==null:next!==end))fail();
  budget(value);return frozen({text:part,utf8_bytes:length,next_offset_utf8:next});
}
export function decodeFreshConversationHistoryCatalogue(raw:unknown,expectedWorkRef:string):FreshConversationHistoryCatalogue {
  if(ownSchema(raw)==='mastermind.fresh_conversation_references.v1')return decodeFreshConversationCatalogue(raw,expectedWorkRef);
  const value=exact(raw,['schema','work_ref','state','coverage','entries']);
  if(value.schema!=='mastermind.fresh_conversation_references.v2'||value.state!=='AVAILABLE'||work(value.work_ref)!==work(expectedWorkRef))fail();
  const coverage=exact(value.coverage,['state','limit','returned']);
  if(!['COMPLETE','PARTIAL'].includes(coverage.state as string)||coverage.limit!==8)fail();
  const entries=list(value.entries,8).map(rawEntry=>{
    if(rawEntry&&typeof rawEntry==='object'&&Object.getOwnPropertyDescriptor(rawEntry,'initial_input')){
      const row=exact(rawEntry,['kind','reference','root_state','result_contract','initial_input']);
      if(row.kind!=='fresh_native'||row.result_contract!=='mastermind.dsh_native_conversation/v1'||
        !['QUEUED','RUNNING','CHECKPOINTED','RATE_LIMITED','FAILED','LOST','CANCEL_REQUESTED','COMPLETED','CANCELLED'].includes(row.root_state as string))fail();
      const reference=decodeFreshConversationReference(row.reference,expectedWorkRef),input=decodeFreshNativeInput(row.initial_input);
      if(input.source_event_id!==reference.root_event_id||input.source_event_sha256!==reference.root_event_sha256)fail();
      return {kind:'fresh_native' as const,reference,root_state:row.root_state as string,
        result_contract:'mastermind.dsh_native_conversation/v1' as const,initial_input:input};
    }
    return decodeFreshConversationCatalogue({schema:'mastermind.fresh_conversation_references.v1',work_ref:expectedWorkRef,
      state:'AVAILABLE',coverage:{state:'COMPLETE',limit:8,returned:1},entries:[rawEntry]},expectedWorkRef).entries[0]!;
  });
  if(integer(coverage.returned)!==entries.length||new Set(entries.map(row=>row.reference.root_job_id)).size!==entries.length||
    !entries.some(row=>'initial_input' in row))fail();
  return budget({schema:'mastermind.fresh_conversation_references.v2',work_ref:expectedWorkRef,state:'AVAILABLE',
    coverage:{state:coverage.state as 'COMPLETE'|'PARTIAL',limit:8,returned:entries.length},entries});
}
export function freshConversationInput(value:FreshConversationHistoryWindow|FreshConversationHistoryCatalogue['entries'][number]):string|FreshNativeInput {
  return 'initial_input' in value?value.initial_input:value.initial_message;
}
export function sameFreshConversationInput(left:FreshConversationHistoryWindow|FreshConversationHistoryCatalogue['entries'][number],
  right:FreshConversationHistoryWindow|FreshConversationHistoryCatalogue['entries'][number]):boolean {
  return canonicalJson(freshConversationInput(left))===canonicalJson(freshConversationInput(right));
}
export function decodeFreshConversationHistoryWindow(raw:unknown,expected:unknown):FreshConversationHistoryWindow {
  if(ownSchema(raw)!=='mastermind.fresh_conversation_window.v3')return decodeFreshConversationWindow(raw,expected);
  const expectedWork=expected&&typeof expected==='object'?Object.getOwnPropertyDescriptor(expected,'work_ref')?.value:undefined;
  const requested=decodeFreshConversationReadRequest(expected,work(expectedWork));if(requested.fragment||requested.content)fail();
  const {before_event_id:before,...wanted}=requested;
  const value=exact(raw,['schema','kind','reference','state','locator','epoch','initial_input','initial_result','head_result',
    'initial_digest','initial_consumption','turns','page','can_send','parent_consumed']);
  if(value.kind!=='fresh_native'||value.can_send!==false||value.parent_consumed!==false||
    !['ADMITTED','RETAINED','SETTLED','RECONCILIATION_REQUIRED'].includes(value.state as string))fail();
  const reference=decodeFreshConversationReference(value.reference,wanted.work_ref);if(!sameReference(reference,wanted))fail();
  const input=decodeFreshNativeInput(value.initial_input);
  if(input.source_event_id!==reference.root_event_id||input.source_event_sha256!==reference.root_event_sha256)fail();
  const loc=exact(value.locator,['work_ref','root_job_id','job_id','attempt_id']);
  if(loc.work_ref!==reference.work_ref||loc.root_job_id!==reference.root_job_id)fail();
  const id=(v:unknown)=>text(v,128,/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/);
  const locator={work_ref:reference.work_ref,root_job_id:reference.root_job_id,
    job_id:loc.job_id===null?null:id(loc.job_id),attempt_id:loc.attempt_id===null?null:id(loc.attempt_id)};
  if(locator.attempt_id!==null&&locator.job_id===null)fail();
  let epoch:FreshConversationWindow['epoch']=null;
  if(value.epoch!==null){const item=exact(value.epoch,['attempt_id','binding_digest','generation_digest']);
    if(item.attempt_id!==locator.attempt_id||locator.attempt_id===null)fail();
    epoch={attempt_id:locator.attempt_id,binding_digest:hex(item.binding_digest),generation_digest:hex(item.generation_digest)};}
  if((value.state==='RETAINED')!==(epoch!==null))fail();
  const initial=value.initial_result===null?null:decodeFreshNativeResult(value.initial_result);
  const head=value.head_result===null?null:decodeFreshNativeResult(value.head_result);
  const digest=value.initial_digest===null?null:hex(value.initial_digest);
  if(digest!==(initial?.digest??null)||(initial===null)!==(head===null)||initial&&
    (!locator.attempt_id||initial.reference.event_id<=reference.root_event_id||head!.reference.event_id<initial.reference.event_id))fail();
  const p=exact(value.page,['kind','before_event_id','next_before_event_id']);
  const next=p.next_before_event_id===null?null:integer(p.next_before_event_id,1);
  if(p.kind!==(before===undefined?'initial':'history')||p.before_event_id!==(before??null)||before!==undefined&&next!==null&&next>=before)fail();
  const page:FreshConversationPage={kind:p.kind as FreshConversationPage['kind'],before_event_id:before??null,next_before_event_id:next};
  let consumed:FreshConversationWindow['initial_consumption']=null;
  if(value.initial_consumption!==null){const item=exact(value.initial_consumption,['state','event_id','event_sha256','initial_digest']);
    if(item.state!=='CONSUMED'||!digest||hex(item.initial_digest)!==digest)fail();
    consumed={state:'CONSUMED',event_id:integer(item.event_id,1),event_sha256:hex(item.event_sha256),initial_digest:digest};}
  let previous=reference.root_event_id;
  const turns=list(value.turns,8).map(rawTurn=>{
    const turn=exact(rawTurn,['turn_key','input','state','result','parent_consumed']);
    if(turn.parent_consumed!==false||!['RECORDED','RECONCILIATION_REQUIRED'].includes(turn.state as string)||!initial||!consumed)fail();
    const input=decodeFreshNativeInput(turn.input),result=turn.result===null?null:decodeFreshNativeResult(turn.result);
    if(input.source_event_id<=previous||before!==undefined&&input.source_event_id>=before||
      (turn.state==='RECORDED')!==(result!==null)||result&&result.reference.event_id<=input.source_event_id)fail();
    previous=input.source_event_id;
    return {turn_key:text(turn.turn_key,96,/^[A-Za-z0-9][A-Za-z0-9._:-]{0,95}$/),input,
      state:turn.state as 'RECORDED'|'RECONCILIATION_REQUIRED',result,parent_consumed:false as const};
  });
  if(new Set(turns.map(t=>t.turn_key)).size!==turns.length||page.kind==='history'&&!turns.length&&next!==null||
    value.state==='SETTLED'&&!initial)fail();
  return budget({schema:'mastermind.fresh_conversation_window.v3',kind:'fresh_native',reference,
    state:value.state as FreshConversationWindow['state'],locator,epoch,initial_input:input,initial_result:initial,
    head_result:head,initial_digest:digest,initial_consumption:consumed,turns,page,can_send:false,parent_consumed:false});
}
