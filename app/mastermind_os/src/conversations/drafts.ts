import type { ProjectionContext } from "../meta-ceo/projection";

/** Ephemeral unsent text only. The shell owns this React state across route detours.
 * No storage, transcript, session registry, operation pointer or send queue. */
export interface ConversationDrafts {
  readonly authGeneration: number;
  readonly entries: Readonly<Record<string, string>>;
}
export function emptyDrafts(authGeneration: number): ConversationDrafts {
  return { authGeneration, entries: {} };
}
function key(context: ProjectionContext): string {
  // These are draft isolation keys, never proof that content belongs to a session.
  return JSON.stringify([context.selection?.workRef ?? null, context.selection?.rootJobId ?? null,
    context.sessionRef, context.bindingGeneration]);
}
export function alignDrafts(state: ConversationDrafts, authGeneration: number): ConversationDrafts {
  return authGeneration > state.authGeneration ? emptyDrafts(authGeneration) : state;
}
export function readDraft(state: ConversationDrafts, context: ProjectionContext): string {
  return state.authGeneration === context.authGeneration ? state.entries[key(context)] ?? "" : "";
}
export function writeDraft(state: ConversationDrafts, context: ProjectionContext, text: string): ConversationDrafts {
  if (context.authGeneration < state.authGeneration) return state;
  const current = alignDrafts(state, context.authGeneration);
  return { ...current, entries: { ...current.entries, [key(context)]: text } };
}
