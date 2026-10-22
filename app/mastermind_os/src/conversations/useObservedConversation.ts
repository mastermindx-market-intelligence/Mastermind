import { useRef, useState } from "react";
import type { MissionSelection, Missionv3Document } from "../mission";
import type { WindowDocument } from "../workspace-contract";
import { projectOffice, sameTarget, type OfficeInput, type ProjectionContext } from "../meta-ceo/projection";
import { alignDrafts, appendDraftSource, emptyDrafts, readDraft, readDraftInsertion, readDraftRevision, undoDraftSource, writeDraft, type ConversationDrafts, type DraftSource } from "./drafts";
import { captureObservedConversation, completeObservedConversation, type ObservedConversationSnapshot } from "./observation-adapter";

const emptyInput = (): OfficeInput => ({ mission: null, programs: null, result: null, conversation: null });
const emptyRevisions = (): ProjectionContext["revisions"] => ({ mission: null, programs: null, result: null, conversation: null });

/** Ephemeral presentation of the existing paired reader; no acquisition, session
 * registry or send port. Unaddressed drafts are separate from Office directions. */
export function useObservedConversation(authGeneration: number, selection: MissionSelection | null, contentAllowed: boolean | undefined) {
  const [snapshot, setSnapshot] = useState<ObservedConversationSnapshot | null>(null);
  const [drafts, setDrafts] = useState(() => emptyDrafts(authGeneration));
  const latestDrafts = useRef(drafts); latestDrafts.current = drafts;
  const allowed = useRef(contentAllowed); allowed.current = contentAllowed;
  const context: ProjectionContext = { authGeneration, selection, sessionRef: null, bindingGeneration: null,
    revisions: snapshot?.context.revisions ?? emptyRevisions() };
  const current = useRef(context); current.current = context;
  const canEdit = () => allowed.current !== false && current.current.authGeneration === context.authGeneration && sameTarget(current.current, context);
  const publishDrafts = (next: ConversationDrafts) => {
    if (next === latestDrafts.current) return false;
    latestDrafts.current = next; setDrafts(next); return true;
  };
  const clear = () => { current.current = { ...current.current, revisions: emptyRevisions() }; setSnapshot(null); };
  const projection = projectOffice(snapshot?.input ?? emptyInput(), context);
  if (contentAllowed === false) projection.conversation = {
    source: { owner: "CURRENT_WINDOW", ref: null, revision: null, observed_at: null, state: "WITHHELD", coverage: "NOT_PROJECTED" },
    value: null, reason: "CONTENT_PERMISSION_WITHHELD",
  };
  return {
    projection, clear,
    draft: contentAllowed === false ? "" : readDraft(drafts, context),
    draftRevision: readDraftRevision(drafts, context),
    draftInsertion: contentAllowed === false ? null : readDraftInsertion(drafts, context),
    changeDraft: (text: string) => { if (canEdit()) publishDrafts(writeDraft(latestDrafts.current, context, text)); },
    appendSource: (source: DraftSource, expectedRevision: number) => canEdit() &&
      publishDrafts(appendDraftSource(latestDrafts.current, context, expectedRevision, source)),
    undoSource: (identity: string, expectedRevision: number) => canEdit() &&
      publishDrafts(undoDraftSource(latestDrafts.current, context, expectedRevision, identity)),
    invalidateAuth: () => {
      const next = current.current.authGeneration + 1;
      clear(); current.current = { ...current.current, authGeneration: next };
      publishDrafts(alignDrafts(latestDrafts.current, next));
    },
    begin: () => { clear(); return captureObservedConversation(current.current); },
    accept: (pending: ReturnType<typeof captureObservedConversation>, mission: Missionv3Document | null, window: WindowDocument | null) => {
      const result = completeObservedConversation(pending, current.current, mission, window, new Date().toISOString());
      if (result.kind === "observed") { current.current = result.context; setSnapshot(result); }
    },
  };
}
