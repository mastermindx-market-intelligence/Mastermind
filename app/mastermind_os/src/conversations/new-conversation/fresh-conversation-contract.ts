import {decodeFreshConversationResult,validateFreshConversationRequest,type FreshConversationData,type FreshConversationRequest,type FreshConversationOperation} from './fresh-conversation';
import {decodeNativeFreshResult,type NativeFreshData} from './native-fresh-result';
import {validateNativeFreshRequest} from './native-fresh-request';
import type {FreshConversationContract} from '../../orchestration/fresh-conversation-transport';
export type FreshConversationObservedData=FreshConversationData|NativeFreshData;
export const NATIVE_CREATE_PREFIX='mmos-native-create-';
export function conversationContractForKey(value:unknown):FreshConversationContract|null{
 if(typeof value!=='string')return null;
 if(/^mmos-native-create-[0-9a-f]{40}$/.exec(value)?.[0]===value)return 'native-v2';
 if(/^mmos-conversation-create-[0-9a-f]{40}$/.exec(value)?.[0]===value)return 'legacy-v1';
 return null;
}
export function validateConversationRequest(value:unknown,operation:FreshConversationOperation):FreshConversationRequest|null{
 try{
  const descriptor=value&&typeof value==='object'?Object.getOwnPropertyDescriptor(value,'operation_key'):undefined;
  if(!descriptor||!('value'in descriptor))return null;
  const contract=conversationContractForKey(descriptor.value);if(!contract)return null;
  return contract==='native-v2'?validateNativeFreshRequest(value,operation) as FreshConversationRequest:
   validateFreshConversationRequest(value,operation);
 }catch{return null;}
}
export function validConversationDraft(work_ref:string,message:string,contract:FreshConversationContract='legacy-v1'):boolean{
 if(contract!=='native-v2'&&contract!=='legacy-v1')return false;
 const value={work_ref,operation_key:'syntax-check',message};
 try{return contract==='native-v2'?!!validateNativeFreshRequest(value,'preview'):!!validateFreshConversationRequest(value,'preview');}
 catch{return false;}
}
export function decodeConversationResult(raw:unknown,operation:FreshConversationOperation,expected:FreshConversationRequest):
 {readonly ok:true;readonly data:FreshConversationObservedData}|{readonly ok:false;readonly data:null;readonly error:Readonly<{code:string;message:string}>}|null{
 const contract=conversationContractForKey(expected.operation_key);if(!contract)return null;
 if(contract==='native-v2'){
  const value=decodeNativeFreshResult(raw,operation,expected);
  if(value?.ok)return value.data.schema==='mastermind.executive.fresh_conversation_data.v2'?{ok:true,data:value.data}:null;
  return value;
 }
 return decodeFreshConversationResult(raw,operation,expected);
}
export function conversationCreateSettled(data:FreshConversationObservedData):boolean{
 if(data.schema==='mastermind.executive.fresh_conversation_data.v2'&&(data.effect==='UNKNOWN'||
  data.state==='SETTLED'&&(!data.locator||!data.result||!data.head_result)))return false;
 return data.state==='CREATED'||data.state==='SETTLED'||
  data.schema==='mastermind.executive.fresh_conversation_data.v2'&&data.state==='IDLE';
}
