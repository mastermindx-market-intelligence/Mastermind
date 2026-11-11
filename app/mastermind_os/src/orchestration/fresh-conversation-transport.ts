import {validateFreshConversationRequest, type FreshConversationOperation, type FreshConversationRequest} from "../conversations/new-conversation/fresh-conversation";
import {validateFreshConversationTurnRequest,type FreshConversationTurnOperation,type FreshConversationTurnRequest} from '../conversations/new-conversation/fresh-conversation-turn';
export type FreshConversationFixedOperation=FreshConversationOperation|FreshConversationTurnOperation;
export const FRESH_CONVERSATION_PATHS=Object.freeze({preview:'conversation/preview',create:'conversation/create',
  status:'conversation/status',read:'conversation/read',consume:'conversation/consume',turn:'conversation/turn',
  turn_status:'conversation/turn/status',turn_read:'conversation/turn/read',
  consume_status:'conversation/consume/status',turn_preview:'conversation/turn/preview'});

/** Ten fixed source-owned endpoints. DATA validation confers no admission. */
export interface FreshConversationTransport {
  request(operation: FreshConversationFixedOperation, arguments_: unknown, signal: AbortSignal): Promise<unknown>;
}
export function freshConversationArguments(operation: FreshConversationFixedOperation, value: unknown): FreshConversationRequest|FreshConversationTurnRequest {
  const request = operation==='preview'||operation==='create'||operation==='status'||operation==='read'
    ? validateFreshConversationRequest(value, operation):validateFreshConversationTurnRequest(value,operation);
  if (!request) throw Error("FRESH_CONVERSATION_REQUEST_INVALID");
  return Object.freeze(request);
}
export function freshConversationNeedsWorkspace(operation: FreshConversationFixedOperation): boolean {
  return operation === "preview" || operation === "create" || operation==='consume' || operation==='turn' || operation==='turn_preview';
}
