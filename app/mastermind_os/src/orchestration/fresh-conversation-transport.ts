import {validateFreshConversationRequest, type FreshConversationOperation, type FreshConversationRequest} from "../conversations/new-conversation/fresh-conversation";
import {validateFreshConversationTurnRequest,type FreshConversationTurnOperation,type FreshConversationTurnRequest} from '../conversations/new-conversation/fresh-conversation-turn';
import {validateNativeFreshRequest,type NativeFreshOperation,type NativeFreshRequest} from '../conversations/new-conversation/native-fresh-request';
export type FreshConversationFixedOperation=FreshConversationOperation|FreshConversationTurnOperation;
export type FreshConversationTransportOperation=FreshConversationFixedOperation|NativeFreshOperation;
export type FreshConversationContract='legacy-v1'|'native-v2';
export const FRESH_CONVERSATION_PATHS=Object.freeze({preview:'conversation/preview',create:'conversation/create',
  status:'conversation/status',read:'conversation/read',consume:'conversation/consume',turn:'conversation/turn',
  turn_status:'conversation/turn/status',turn_read:'conversation/turn/read',
  consume_status:'conversation/consume/status',turn_preview:'conversation/turn/preview'} as const);
export const NATIVE_FRESH_PATHS=Object.freeze({preview:'conversation/v2/preview',create:'conversation/v2/create',
  status:'conversation/v2/status',read:'conversation/v2/read',consume:'conversation/v2/consume',
  consume_status:'conversation/v2/consume/status',turn_preview:'conversation/v2/turn/preview',turn:'conversation/v2/turn',
  turn_status:'conversation/v2/turn/status',turn_read:'conversation/v2/turn/read',
  resume_preview:'conversation/v2/resume/preview',resume:'conversation/v2/resume',resume_status:'conversation/v2/resume/status',
  stop:'conversation/v2/stop',stop_status:'conversation/v2/stop/status',recover:'conversation/v2/recover',turn_recover:'conversation/v2/turn/recover'} as const);

/** Version selects closed syntax and routes; it confers no admission. */
export interface FreshConversationTransport {
  request(operation: FreshConversationTransportOperation, arguments_: unknown, signal: AbortSignal,
    contract?:FreshConversationContract): Promise<unknown>;
}
export function freshConversationPath(operation:FreshConversationTransportOperation,contract:FreshConversationContract='legacy-v1'){
  if(contract==='native-v2'&&Object.prototype.hasOwnProperty.call(NATIVE_FRESH_PATHS,operation))return NATIVE_FRESH_PATHS[operation];
  if(contract==='legacy-v1'&&Object.prototype.hasOwnProperty.call(FRESH_CONVERSATION_PATHS,operation))
    return FRESH_CONVERSATION_PATHS[operation as FreshConversationFixedOperation];
  throw Error('FRESH_CONVERSATION_REQUEST_INVALID');
}
export function freshConversationArguments(operation: FreshConversationTransportOperation, value: unknown,
  contract:FreshConversationContract='legacy-v1'): FreshConversationRequest|FreshConversationTurnRequest|NativeFreshRequest {
  freshConversationPath(operation,contract);
  if(contract==='native-v2')return validateNativeFreshRequest(value,operation);
  const legacy=operation as FreshConversationFixedOperation;
  const request = legacy==='preview'||legacy==='create'||legacy==='status'||legacy==='read'
    ? validateFreshConversationRequest(value, legacy):validateFreshConversationTurnRequest(value,legacy);
  if (!request) throw Error("FRESH_CONVERSATION_REQUEST_INVALID");
  return Object.freeze(request);
}
export function freshConversationNeedsWorkspace(operation: FreshConversationTransportOperation,
  contract:FreshConversationContract='legacy-v1'): boolean {
  freshConversationPath(operation,contract);
  return operation === "preview" || operation === "create" || operation==='consume' || operation==='turn' ||
    operation==='turn_preview'||operation==='resume_preview'||operation==='resume'||operation==='stop'||
    contract==='native-v2'&&(operation==='recover'||operation==='turn_recover');
}
