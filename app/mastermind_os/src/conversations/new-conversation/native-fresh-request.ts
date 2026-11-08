/** Native-v2 data syntax on the existing fresh-conversation carrier. */
import type {FreshConversationReference} from '../fresh-conversation-reference';
export const NATIVE_FRESH_OPERATIONS = ['preview','create','status','read','consume','consume_status',
  'turn_preview','turn','turn_status','turn_read','turn_recover','recover','resume_preview','resume','resume_status','stop','stop_status'] as const;
export type NativeFreshOperation = typeof NATIVE_FRESH_OPERATIONS[number];
export type NativeFreshSelector = Readonly<{work_ref:string;operation_key:string;reference?:never} |
  {work_ref:string;reference:FreshConversationReference;operation_key?:never}>;
export type NativeFreshRequest = NativeFreshSelector & Readonly<{
  message?:string;initial_digest?:string;turn_key?:string;preview_digest?:string;
  resume_key?:string;expected_result_digest?:string;stop_key?:string;turn_id?:string;binding_digest?:string;
}>;
export const NATIVE_MESSAGE_BYTES=131072;
export const NATIVE_REQUEST_BYTES=524288;
export const NATIVE_RESPONSE_BYTES=32768;
export function nativeInvalid():never {throw Error('FRESH_CONVERSATION_REQUEST_INVALID');}
export function nativeExact(value:unknown,keys:readonly string[]):Record<string,unknown>{
  if(!value||typeof value!=='object'||Array.isArray(value)||
    ![Object.prototype,null].includes(Object.getPrototypeOf(value)))nativeInvalid();
  const own=Reflect.ownKeys(value);
  if(own.length!==keys.length||own.some(k=>typeof k!=='string'||!keys.includes(k)))nativeInvalid();
  const out:Record<string,unknown>=Object.create(null);
  for(const key of keys){const descriptor=Object.getOwnPropertyDescriptor(value,key);
    if(!descriptor?.enumerable||!('value'in descriptor))nativeInvalid();out[key]=descriptor.value;}
  return out;
}
export function nativeText(value:unknown,max:number,pattern?:RegExp):string{
  if(typeof value!=='string'||value.length===0||value.length>max)nativeInvalid();
  for(const point of value){const code=point.codePointAt(0)!;if(code>=0xd800&&code<=0xdfff)nativeInvalid();}
  if(pattern&&pattern.exec(value)?.[0]!==value)nativeInvalid();
  return value;
}
export const nativeWork=(value:unknown)=>nativeText(value,72,/^WS:[A-Za-z0-9][A-Za-z0-9._-]{0,68}$/);
export const nativeKey=(value:unknown)=>nativeText(value,96,/^[A-Za-z0-9][A-Za-z0-9._:-]{0,95}$/);
export const nativeId=(value:unknown)=>nativeText(value,128,/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/);
export const nativeHex=(value:unknown)=>nativeText(value,64,/^[0-9a-f]{64}$/);
export function nativeInteger(value:unknown,min=0):number{
  if(typeof value!=='number'||!Number.isSafeInteger(value)||value<min)nativeInvalid();return value;
}
export function nativeFreeze<T>(value:T):T{
  if(value&&typeof value==='object'){Object.values(value).forEach(nativeFreeze);Object.freeze(value);}return value;
}
export function nativeMessage(value:unknown):string{
  const message=nativeText(value,NATIVE_MESSAGE_BYTES);
  // Python str.strip whitespace, without JS's additional U+FEFF trimming.
  if(/^[\u0009-\u000d\u001c-\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]*$/.test(message)||
    /[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f-\u009f]/.test(message)||
    new TextEncoder().encode(message).length>NATIVE_MESSAGE_BYTES)nativeInvalid();
  return message;
}
export function nativeReference(value:unknown,work:string):FreshConversationReference{
  const ref=nativeExact(value,['schema','work_ref','root_job_id','root_event_id','root_event_sha256','principal_scope_sha256']);
  if(ref.schema!=='mastermind.fresh_conversation_reference.v1'||nativeWork(ref.work_ref)!==work)nativeInvalid();
  return nativeFreeze({schema:'mastermind.fresh_conversation_reference.v1',work_ref:work,
    root_job_id:nativeId(ref.root_job_id),root_event_id:nativeInteger(ref.root_event_id,1),
    root_event_sha256:nativeHex(ref.root_event_sha256),principal_scope_sha256:nativeHex(ref.principal_scope_sha256)});
}
export function validateNativeFreshRequest(value:unknown,operation:NativeFreshOperation):NativeFreshRequest{
  if(!NATIVE_FRESH_OPERATIONS.includes(operation))nativeInvalid();
  const referenceMode=!!value&&typeof value==='object'&&Object.prototype.hasOwnProperty.call(value,'reference');
  if(referenceMode&&(operation==='preview'||operation==='create'))nativeInvalid();
  const keys=['work_ref',referenceMode?'reference':'operation_key'];
  if(['preview','create','turn_preview','turn'].includes(operation))keys.push('message');
  if(['consume','consume_status','turn_preview','turn'].includes(operation))keys.push('initial_digest');
  if(['turn_preview','turn','turn_status','turn_read','turn_recover'].includes(operation))keys.push('turn_key');
  if(['resume_preview','resume','resume_status'].includes(operation))keys.push('resume_key');
  if(['stop','stop_status'].includes(operation))keys.push('stop_key');
  if(['create','turn','resume'].includes(operation))keys.push('preview_digest');
  if(['resume_preview','resume'].includes(operation))keys.push('expected_result_digest');
  if(operation==='stop')keys.push('turn_id','binding_digest');
  const raw=nativeExact(value,keys),out:Record<string,unknown>={work_ref:nativeWork(raw.work_ref)};
  if(referenceMode)out.reference=nativeReference(raw.reference,out.work_ref as string);
  else out.operation_key=nativeKey(raw.operation_key);
  for(const key of ['turn_key','resume_key','stop_key'])if(keys.includes(key))out[key]=nativeKey(raw[key]);
  for(const key of ['preview_digest','initial_digest','expected_result_digest','binding_digest'])
    if(keys.includes(key))out[key]=nativeHex(raw[key]);
  if(keys.includes('turn_id'))out.turn_id=nativeId(raw.turn_id);
  if(keys.includes('message'))out.message=nativeMessage(raw.message);
  if(new TextEncoder().encode(JSON.stringify({arguments:out})).length>NATIVE_REQUEST_BYTES)nativeInvalid();
  return nativeFreeze(out as NativeFreshRequest);
}
