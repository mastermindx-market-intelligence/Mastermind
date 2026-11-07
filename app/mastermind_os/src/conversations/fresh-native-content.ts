/** Exact original native bytes through the existing authenticated Fresh READ.
 * Decoding grants no Send, resume, tool-execution or Session authority.
 */
import {canonicalJson,sha256Hex} from '../orchestration/operation-key';
import {decodeFreshConversationReadRequest,decodeFreshConversationReference,
  decodeFreshNativeContentSelector,snapshotConversationData,
  type FreshConversationReadRequest} from './fresh-conversation-reference';

type Data=Record<string,unknown>;
function fail():never{throw Error('PROJECT_CONVERSATION_UNAVAILABLE');}
function object(value:unknown):Data {
  if(!value||typeof value!=='object'||Array.isArray(value)||
    ![Object.prototype,null].includes(Object.getPrototypeOf(value)))fail();
  return value as Data;
}
function exact(value:unknown,keys:readonly string[]):Data {
  const data=object(value);
  if(Object.keys(data).length!==keys.length||!keys.every(k=>Object.hasOwn(data,k)))fail();
  return data;
}
function integer(value:unknown,min=0):number {
  if(typeof value!=='number'||!Number.isSafeInteger(value)||value<min||Object.is(value,-0))fail();
  return value;
}
function text(value:unknown,limit:number):string {
  if(typeof value!=='string'||value.length>limit)fail();
  for(const c of value)if(c.length===1&&c.charCodeAt(0)>=0xd800&&c.charCodeAt(0)<=0xdfff)fail();
  return value;
}
function id(value:unknown):string {
  const v=text(value,128);if(!/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(v))fail();return v;
}
function hex(value:unknown):string {
  const v=text(value,64);if(!/^[0-9a-f]{64}$/.test(v))fail();return v;
}
function freeze<T>(value:T):T {
  if(value&&typeof value==='object'){Object.values(value).forEach(freeze);Object.freeze(value);}return value;
}
function claim(raw:unknown) {
  const v=exact(raw,['schema','operationId','requestId','sessionId','messageId','nativeTurn','throughSeq']);
  if(v.schema!=='mastermind.dsh.native_prompt_claim.v1')fail();
  return {schema:v.schema,operationId:id(v.operationId),
    requestId:typeof v.requestId==='number'?integer(v.requestId):id(v.requestId),
    sessionId:id(v.sessionId),messageId:id(v.messageId),nativeTurn:integer(v.nativeTurn),throughSeq:integer(v.throughSeq)};
}
export interface FreshNativeAnswer {
  readonly state:'CONTENT'|'NO_ANSWER';readonly messages:readonly string[];readonly records:readonly unknown[];
}
export function decodeFreshNativeContent(raw:unknown,expected:FreshConversationReadRequest) {
  const requested=decodeFreshConversationReadRequest(expected,expected.work_ref);
  if(!requested.content)fail();
  const v=exact(snapshotConversationData(raw),['schema','reference','content','native_session_id','association_sha256','native']);
  const {content,...reference}=requested;
  if(v.schema!=='mastermind.fresh_conversation_native_content.v1'||
    canonicalJson(decodeFreshConversationReference(v.reference,expected.work_ref))!==canonicalJson(reference)||
    canonicalJson(decodeFreshNativeContentSelector(v.content))!==canonicalJson(content))fail();
  const native=exact(v.native,['kind','state','claim','terminal','turn_start_seq','turn_end_seq',
    'user_message_seq','assistant_message_seqs','content']);
  const original=claim(native.claim);
  if(native.kind!=='result'||!['CONTENT','NO_ANSWER'].includes(native.state as string)||id(v.native_session_id)!==original.sessionId)fail();
  const terminal=exact(native.terminal,['schema','operationId','requestId','claim','throughSeq','observedLastTurn','observedTurnCount']);
  if(terminal.schema!=='mastermind.dsh.native_prompt_terminal.v1'||terminal.operationId!==original.operationId||
    terminal.requestId!==original.requestId||canonicalJson(claim(terminal.claim))!==canonicalJson(original)||
    integer(terminal.throughSeq)<original.throughSeq||integer(terminal.observedLastTurn)<original.nativeTurn||
    integer(terminal.observedTurnCount,1)<1)fail();
  const start=integer(native.turn_start_seq),end=integer(native.turn_end_seq),
    user=native.user_message_seq===null?null:integer(native.user_message_seq);
  if(start>original.throughSeq||end<original.throughSeq||end>Number(terminal.throughSeq)||
    user!==null&&(user<=original.throughSeq||user>=end))fail();
  if(!Array.isArray(native.assistant_message_seqs)||native.assistant_message_seqs.length>4096)fail();
  let previous=start;
  const assistants=native.assistant_message_seqs.map(v=>{
    const seq=integer(v);if(seq<=previous||seq>=end)fail();previous=seq;return seq;
  });
  const state=native.state as FreshNativeAnswer['state'];
  const metadata=freeze({association_sha256:hex(v.association_sha256),native_session_id:original.sessionId,
    claim:original,terminal,turn_start_seq:start,turn_end_seq:end,user_message_seq:user,assistant_message_seqs:assistants,state});
  if(state==='NO_ANSWER'){
    if(assistants.length||native.content!==null||content.offset_bytes!==0||content.expected_sha256!==null)fail();
    return {metadata,part:null};
  }
  if(user===null||!assistants.length||assistants[0]!<=user)fail();
  const part=exact(native.content,['encoding','format','sha256','total_bytes','offset_bytes','next_offset_bytes','data']);
  if(part.encoding!=='base64'||part.format!=='dsh-session-history-records-json')fail();
  const digest=hex(part.sha256),total=integer(part.total_bytes,1),offset=integer(part.offset_bytes);
  if(total>4*1024*1024||offset!==content.offset_bytes||offset>=total||
    content.expected_sha256!==null&&digest!==content.expected_sha256)fail();
  const encoded=text(part.data,5464);
  let binary:string;try{binary=atob(encoded);}catch{fail();}
  if(!binary.length||binary.length>4096||btoa(binary)!==encoded)fail();
  const bytes=Uint8Array.from(binary,c=>c.charCodeAt(0)),endOffset=offset+bytes.length;
  const next=part.next_offset_bytes===null?null:integer(part.next_offset_bytes,1);
  if(endOffset>total||(endOffset===total?next!==null:next!==endOffset))fail();
  return {metadata,part:{sha256:digest,total_bytes:total,offset_bytes:offset,next_offset_bytes:next,bytes}};
}
export type FreshNativeContent=ReturnType<typeof decodeFreshNativeContent>;
/** Full hash and exact original native event cut precede text rendering. */
export function decodeFreshNativeAnswer(bytes:Uint8Array,first:FreshNativeContent):FreshNativeAnswer {
  if(!first.part||first.metadata.state!=='CONTENT')fail();
  let serialized:string;try{serialized=new TextDecoder('utf-8',{fatal:true}).decode(bytes);}catch{fail();}
  if(bytes.length!==first.part.total_bytes||sha256Hex(serialized)!==first.part.sha256)fail();
  let parsed:unknown;try{parsed=JSON.parse(serialized);}catch{fail();}
  const root=exact(parsed,['records']);
  if(!Array.isArray(root.records)||!root.records.length||root.records.length>4096)fail();
  const meta=first.metadata,rows=root.records.map((raw,index)=>{
    const row=object(raw),event=object(row.event),data=object(event.data);
    if(row.type!=='event'||integer(event.seq)!==meta.turn_start_seq+index||typeof event.type!=='string')fail();
    return {raw,event,data};
  });
  const firstRow=rows[0]!,last=rows[rows.length-1]!;
  if(firstRow.event.type!=='turn/start'||firstRow.data.turn!==meta.claim.nativeTurn||
    last.event.type!=='turn/end'||last.data.turn!==meta.claim.nativeTurn||last.event.seq!==meta.turn_end_seq||
    rows.slice(1).some(row=>row.event.type==='turn/start'))fail();
  const users=rows.filter(row=>row.event.type==='user/message');
  const matched=users.filter(row=>row.data.id===meta.claim.messageId);
  if(matched.length!==1||matched[0]!.event.seq!==meta.user_message_seq||
    users.some(row=>row.data.id!==meta.claim.messageId&&object(row.data.source).kind!=='runtime-context'))fail();
  const assistants=rows.filter(row=>row.event.type==='assistant/message');
  if(canonicalJson(assistants.map(row=>row.event.seq))!==canonicalJson(meta.assistant_message_seqs))fail();
  const messages=assistants.map(row=>{
    const message=object(row.data.message);
    if(row.data.turn!==meta.claim.nativeTurn||message.role!=='assistant'||!Array.isArray(message.content))fail();
    return message.content.map(raw=>{
      const block=object(raw);return block.type==='text'?text(block.text,4*1024*1024):'';
    }).join('');
  });
  return freeze({state:'CONTENT',messages,records:root.records});
}
