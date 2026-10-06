import { useRef, useState } from "react";
import type { MissionSelection, Missionv3Document } from "../mission";
import type { WindowDocument } from "../workspace-contract";
import { projectOffice, type OfficeInput, type ProjectionContext } from "../meta-ceo/projection";
import { alignDrafts, emptyDrafts, readDraft, writeDraft } from "./drafts";
import { captureObservedConversation, completeObservedConversation, type ObservedConversationSnapshot } from "./observation-adapter";

const emptyInput = (): OfficeInput => ({ mission: null, programs: null, result: null, conversation: null });
const emptyRevisions = (): ProjectionContext["revisions"] => ({ mission: null, programs: null, result: null, conversation: null });

/** Ephemeral presentation of the existing paired reader; no acquisition, session
 * registry or send port. Unaddressed drafts are separate from Office directions. */
export function useObservedConversation(authGeneration: number, selection: MissionSelection | null, contentAllowed: boolean | undefined) {
  const [snapshot, setSnapshot] = useState<ObservedConversationSnapshot | null>(null);
  const [drafts, setDrafts] = useState(() => emptyDrafts(authGeneration));
  const context: ProjectionContext = { authGeneration, selection, sessionRef: null, bindingGeneration: null,
    revisions: snapshot?.context.revisions ?? emptyRevisions() };
  const current = useRef(context); current.current = context;
  const clear = () => { current.current = { ...current.current, revisions: emptyRevisions() }; setSnapshot(null); };
  const projection = projectOffice(snapshot?.input ?? emptyInput(), context);
  if (contentAllowed === false) projection.conversation = {
    source: { owner: "CURRENT_WINDOW", ref: null, revision: null, observed_at: null, state: "WITHHELD", coverage: "NOT_PROJECTED" },
    value: null, reason: "CONTENT_PERMISSION_WITHHELD",
  };
  return {
    projection, clear,
    draft: contentAllowed === false ? "" : readDraft(drafts, context),
    changeDraft: (text: string) => setDrafts(previous => writeDraft(previous, context, text)),
    invalidateAuth: () => {
      const next = current.current.authGeneration + 1;
      clear(); current.current = { ...current.current, authGeneration: next };
      setDrafts(previous => alignDrafts(previous, next));
    },
    begin: () => { clear(); return captureObservedConversation(current.current); },
    accept: (pending: ReturnType<typeof captureObservedConversation>, mission: Missionv3Document | null, window: WindowDocument | null) => {
      const result = completeObservedConversation(pending, current.current, mission, window, new Date().toISOString());
      if (result.kind === "observed") { current.current = result.context; setSnapshot(result); }
    },
  };
}
