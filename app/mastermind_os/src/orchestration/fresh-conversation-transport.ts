import {validateFreshConversationRequest, type FreshConversationOperation, type FreshConversationRequest} from "../conversations/new-conversation/fresh-conversation";

/** Four original-operation endpoints. DATA validation confers no admission. */
export interface FreshConversationTransport {
  request(operation: FreshConversationOperation, arguments_: unknown, signal: AbortSignal): Promise<unknown>;
}
export function freshConversationArguments(operation: FreshConversationOperation, value: unknown): FreshConversationRequest {
  const request = validateFreshConversationRequest(value, operation);
  if (!request) throw Error("FRESH_CONVERSATION_REQUEST_INVALID");
  return Object.freeze(request);
}
export function freshConversationNeedsWorkspace(operation: FreshConversationOperation): boolean {
  return operation === "preview" || operation === "create";
}
