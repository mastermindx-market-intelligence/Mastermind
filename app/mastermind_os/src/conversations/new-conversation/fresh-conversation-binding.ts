import type { CommandIntent, OperationController, OwnerContext, PendingPointerStore } from "../../orchestration/operation-controller";
import type { FreshConversationData } from "./fresh-conversation";

/** Exact wire selectors; ordinary client keys are never Runtime/session IDs. */
export interface ConversationRequestSelection {
  readonly work_ref: string;
  readonly operation_key: string;
}
export interface ConversationPreviewRequest extends ConversationRequestSelection {
  readonly message: string;
}

/**
 * Fixed host adapter over the incumbent controller/store. Preview is an
 * observation; only controller.begin(makeCreateIntent(...)) can submit create.
 * Original recovery always belongs to that controller and its retained pointer.
 * The shared Host/native/App implementation is owned by the Release integrator.
 */
export interface FreshConversationBinding {
  readonly controller: OperationController;
  readonly store: PendingPointerStore;
  context(): OwnerContext | null;
  /** Synchronous, effect-free. Mint once for an explicit new draft, not recovery. */
  makePreviewRequest(workRef: string, message: string): ConversationPreviewRequest | null;
  preview(request: ConversationPreviewRequest, signal: AbortSignal): Promise<unknown>;
  /** Must preserve the request key and actual preview digest, distinct kind conversation_create. */
  makeCreateIntent(request: ConversationPreviewRequest, preview: FreshConversationData): CommandIntent | null;
  readOriginal(selection: ConversationRequestSelection, signal: AbortSignal): Promise<unknown>;
}

export interface ConversationProjectChoice {
  readonly workRef: string;
  readonly title: string | null;
}

/** A view identity comparison, never authentication or a derived permission. */
export function sameConversationOwner(a: OwnerContext | null, b: OwnerContext | null): boolean {
  return a !== null && b !== null && a.principalScope === b.principalScope && a.generation === b.generation;
}
