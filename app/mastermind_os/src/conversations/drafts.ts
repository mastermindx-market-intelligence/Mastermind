import type { ProjectionContext } from "../meta-ceo/projection";

/** Ephemeral unsent text only. The shell owns this React state across route detours.
 * No storage, transcript, session registry, operation pointer or send queue. */
export interface ConversationDrafts {
  readonly authGeneration: number;
  readonly entries: Readonly<Record<string, DraftEntry>>;
}
export interface DraftSource { identity: string; excerpt: string; label: string }
export interface DraftInsertion {
  readonly source: DraftSource;
  readonly before: string;
  readonly after: string;
  readonly revision: number;
}
interface DraftEntry { readonly text: string; readonly revision: number; readonly insertion?: DraftInsertion }
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
  return state.authGeneration === context.authGeneration ? state.entries[key(context)]?.text ?? "" : "";
}
export function readDraftRevision(state: ConversationDrafts, context: ProjectionContext): number {
  return state.authGeneration === context.authGeneration ? state.entries[key(context)]?.revision ?? 0 : 0;
}
export function readDraftInsertion(state: ConversationDrafts, context: ProjectionContext): DraftInsertion | null {
  return state.authGeneration === context.authGeneration ? state.entries[key(context)]?.insertion ?? null : null;
}
export function writeDraft(state: ConversationDrafts, context: ProjectionContext, text: string): ConversationDrafts {
  if (context.authGeneration < state.authGeneration) return state;
  const current = alignDrafts(state, context.authGeneration);
  const previous = current.entries[key(context)];
  return { ...current, entries: { ...current.entries, [key(context)]: {
    ...previous, text, revision: (previous?.revision ?? 0) + 1,
  } } };
}

/** One explicit local insertion into the existing scoped draft. The revision is
 * compared at the owner, not inferred from matching text. No send or storage. */
export function appendDraftSource(state: ConversationDrafts, context: ProjectionContext,
  expectedRevision: number, source: DraftSource): ConversationDrafts {
  if (state.authGeneration !== context.authGeneration || !context.selection ||
      readDraftRevision(state, context) !== expectedRevision ||
      !source.identity || !source.excerpt || !source.label ||
      readDraftInsertion(state, context)?.source.identity === source.identity) return state;
  const before = readDraft(state, context);
  const after = `${before}${before ? "\n\n" : ""}“${source.excerpt}”\nSource: ${source.label}`;
  const revision = expectedRevision + 1;
  return { ...state, entries: { ...state.entries, [key(context)]: {
    text: after, revision, insertion: { source: { ...source }, before, after, revision },
  } } };
}

/** Conditional Undo of only the last insertion, before any intervening edit. */
export function undoDraftSource(state: ConversationDrafts, context: ProjectionContext,
  expectedRevision: number, identity: string): ConversationDrafts {
  const insertion = readDraftInsertion(state, context);
  if (!insertion || insertion.source.identity !== identity ||
      readDraftRevision(state, context) !== expectedRevision || insertion.revision !== expectedRevision ||
      readDraft(state, context) !== insertion.after) return state;
  return { ...state, entries: { ...state.entries, [key(context)]: {
    text: insertion.before, revision: expectedRevision + 1,
  } } };
}
