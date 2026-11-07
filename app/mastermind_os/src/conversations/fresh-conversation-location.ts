import {validateFreshConversationRequest} from "./new-conversation/fresh-conversation";
import type {ConversationRequestSelection} from "./new-conversation/fresh-conversation-binding";
import {CONVERSATION_CREATE_KEY_PREFIX} from "../orchestration/indexeddb-pending-pointer-store";
const KEYS=["new_conversation","conversation_work_ref","conversation_operation_key"] as const;
/** Lookup DATA only. No text, owner, permission, dispatch or persisted grant. */
export interface FreshConversationLocation {valid:boolean;open:boolean;selection:ConversationRequestSelection|null;}
function selection(value:unknown):ConversationRequestSelection|null{
 const checked=validateFreshConversationRequest(value,"status");
 return checked && checked.operation_key.startsWith(CONVERSATION_CREATE_KEY_PREFIX) &&
  /^[0-9a-f]{40}$/.test(checked.operation_key.slice(CONVERSATION_CREATE_KEY_PREFIX.length))
  ?Object.freeze({work_ref:checked.work_ref,operation_key:checked.operation_key}):null;
}
export function readFreshConversationLocation(input:string):FreshConversationLocation{
 try{
  const url=new URL(input),p=url.searchParams;
  if(KEYS.every(k=>!p.has(k)))return {valid:true,open:false,selection:null};
  if(KEYS.some(k=>p.getAll(k).length>1)||p.has(KEYS[0])&&p.get(KEYS[0])!=="1")throw Error();
  const work=p.get(KEYS[1]),key=p.get(KEYS[2]);
  if(work===null&&key===null)return {valid:true,open:true,selection:null};
  const chosen=selection({work_ref:work,operation_key:key});
  if(!chosen)throw Error();
  return {valid:true,open:true,selection:chosen};
 }catch{return {valid:false,open:false,selection:null};}
}
/** Own safe keys only; discard credentials, legacy roots, private query/hash.
 * The caller commits this synchronously BEFORE any preview/read await. */
export function writeFreshConversationLocation(input:string,original:ConversationRequestSelection|null,open=true):string{
 try{
  const before=new URL(input);
  if(before.username||before.password)throw Error();
  if(!open&&original!==null)throw Error();
  const url=new URL(`${before.protocol}//${before.host}${before.pathname}`);
  if(open)url.searchParams.set(KEYS[0],"1");
  if(original!==null){
   const chosen=selection(original);if(!chosen)throw Error();
   url.searchParams.set(KEYS[1],chosen.work_ref);url.searchParams.set(KEYS[2],chosen.operation_key);
  }
  return url.href;
 }catch{throw Error("FRESH_CONVERSATION_LOCATION_INVALID");}
}
