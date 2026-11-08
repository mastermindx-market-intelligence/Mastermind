/** Closed contract joins for the existing attended owner. No state or effects. */
import {decodeFreshConversationTurnResult,decodeFreshConversationTurnPreviewResult,validateFreshConversationTurnRequest,
 type FreshConversationTurnRequest,type FreshConversationTurnOperation,type FreshConversationTurnData} from './fresh-conversation-turn';
import {decodeNativeFreshResult,type NativeFreshTurnData} from './native-fresh-result';
import {validateNativeFreshRequest} from './native-fresh-request';
import type {FreshConversationContract} from '../../orchestration/fresh-conversation-transport';
export type FreshAttendedData=FreshConversationTurnData|NativeFreshTurnData;
export function attendedContractForKey(key:unknown):FreshConversationContract|null{
 if(typeof key!=='string')return null;
 if(/^mmos-native-(?:consume|turn|resume|stop)-[0-9a-f]{40}$/.exec(key)?.[0]===key)return 'native-v2';
 if(/^mmos-conversation-(?:consume|turn)-[0-9a-f]{40}$/.exec(key)?.[0]===key)return 'legacy-v1';
 return null;
}
export function validateAttendedRequest(raw:unknown,operation:FreshConversationTurnOperation,contract:FreshConversationContract):FreshConversationTurnRequest|null{
 try{
  if(contract==='native-v2')return validateNativeFreshRequest(raw,operation) as FreshConversationTurnRequest;
  return contract==='legacy-v1'?validateFreshConversationTurnRequest(raw,operation):null;
 }catch{return null;}
}
export function decodeAttendedResult(raw:unknown,operation:Exclude<FreshConversationTurnOperation,'turn_preview'>,request:FreshConversationTurnRequest,contract:FreshConversationContract){
 if(contract==='native-v2'){
  const decoded=decodeNativeFreshResult(raw,operation,request);
  if(decoded?.ok)return decoded.data.schema==='mastermind.executive.fresh_conversation_turn_data.v2'?{ok:true as const,data:decoded.data}:null;
  return decoded;
 }
 return contract==='legacy-v1'?decodeFreshConversationTurnResult(raw,operation,request):null;
}
export function decodeAttendedPreview(raw:unknown,request:FreshConversationTurnRequest,contract:FreshConversationContract){
 if(contract==='native-v2'){
  const decoded=decodeNativeFreshResult(raw,'turn_preview',request);
  if(decoded?.ok)return decoded.data.schema==='mastermind.executive.fresh_conversation_turn_preview.v2'?{ok:true as const,data:decoded.data}:null;
  return decoded;
 }
 return contract==='legacy-v1'?decodeFreshConversationTurnPreviewResult(raw,request):null;
}
/** Passive native receipts use NONE; the exact sealed/consumed proof settles. */
export function attendedReadSettled(data:FreshAttendedData):boolean{
 const proven=data.state==='RECORDED'&&data.result!==null||data.state==='CONSUMED'&&data.initial_consumption!==null;
 return proven&&(data.schema==='mastermind.executive.fresh_conversation_turn_data.v2'?data.effect==='NONE':data.effect==='COMMITTED');
}
