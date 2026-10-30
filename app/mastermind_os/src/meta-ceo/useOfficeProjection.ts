import { useRef, useState } from "react";
import type { MissionDocument, MissionSelection, Missionv3Document } from "../mission";
import type { ResultEnvelopeDigestShape } from "../result";
import type { ProgramsObservation } from "../programs-observation";
import { alignDrafts, emptyDrafts, readDraft, writeDraft } from "../conversations/drafts";
import { captureMissionOfficeRead, completeMissionOfficeRead, completeMissionResultOfficeRead, captureMissionResultOfficeRead, type PendingMissionOfficeRead, type PendingMissionResultOfficeRead } from "./mission-adapter";
import { captureProgramsOfficeRead, completeProgramsOfficeRead, type PendingProgramsOfficeRead } from "./programs-adapter";
import { projectOffice, type OfficeInput, type ProjectionContext, type SourceKey } from "./projection";

const empty = (): OfficeInput => ({ mission: null, programs: null, result: null, conversation: null });

/** Presentation state only. The existing App effects own all fixed acquisitions,
 * request lifetimes and auth invalidation; this hook never performs a read. */
export function useOfficeProjection(
  authGeneration: number,
  selection: MissionSelection | null,
  boundSession: { sessionRef: string | null; bindingGeneration: string | null } = {
    sessionRef: null, bindingGeneration: null,
  },
) {
  const [input, setInput] = useState<OfficeInput>(empty);
  const latest = useRef(input);
  const pairEpoch = useRef(0);
  const [drafts, setDrafts] = useState(() => emptyDrafts(authGeneration));
  const context: ProjectionContext = { authGeneration, selection,
    // A verified Executive native session may qualify this read context.
    // No DSH/Grok/Hermes session ID is inferred from a title or channel.
    sessionRef: boundSession.sessionRef, bindingGeneration: boundSession.bindingGeneration,
    revisions: { mission: input.mission?.source.revision ?? null, programs: input.programs?.source.revision ?? null,
      result: input.result?.source.revision ?? null, conversation: input.conversation?.source.revision ?? null } };
  const current = useRef(context);
  current.current = context;
  const publish = (next: OfficeInput) => { latest.current = next; setInput(next); };
  const clearPair = () => {
    current.current = { ...current.current, revisions: { ...current.current.revisions, mission: null, result: null } };
    publish({ ...latest.current, mission: null, result: null });
  };
  const clearSource = (key: SourceKey) => {
    current.current = { ...current.current, revisions: { ...current.current.revisions, [key]: null } };
    publish({ ...latest.current, [key]: null });
  };
  const clear = () => {
    current.current = { ...current.current, revisions: { mission: null, programs: null, result: null, conversation: null } };
    publish(empty());
  };
  return {
    projection: projectOffice(input, context),
    draft: { context, text: readDraft(drafts, context) },
    changeDraft: (text: string) => setDrafts(previous => writeDraft(previous, context, text)),
    invalidateAuth: () => {
      pairEpoch.current += 1;
      const next = current.current.authGeneration + 1;
      clear(); current.current = { ...current.current, authGeneration: next };
      setDrafts(previous => alignDrafts(previous, next));
    },
    clearSelection: (next: MissionSelection | null) => {
      if (current.current.selection?.workRef !== next?.workRef || current.current.selection?.rootJobId !== next?.rootJobId) {
        pairEpoch.current += 1;
        clear();
      }
    },
    /** Independent Mission refresh: drop both halves and fence any in-flight compound accept. */
    supersedePair: () => {
      pairEpoch.current += 1;
      clearPair();
    },
    beginMissionResult: (): PendingMissionResultOfficeRead => {
      const token = ++pairEpoch.current;
      clearPair();
      return captureMissionResultOfficeRead(current.current, token);
    },
    acceptMissionResult: (
      pending: PendingMissionResultOfficeRead,
      mission: Missionv3Document,
      result: ResultEnvelopeDigestShape,
      localAcquiredAt: string,
    ) => {
      if (pending.token !== pairEpoch.current)
        return { kind: "discarded" as const, state: "STALE" as const, reason: "READ_SUPERSEDED" };
      const accepted = completeMissionResultOfficeRead(
        pending, current.current, mission, result, localAcquiredAt,
        { programs: latest.current.programs, conversation: latest.current.conversation },
      );
      if (pending.token !== pairEpoch.current || accepted.kind !== "observed") return accepted;
      current.current = accepted.context;
      publish({ ...latest.current, mission: accepted.mission, result: accepted.result });
      return accepted;
    },
    beginMission: () => { clearSource("mission"); return captureMissionOfficeRead(current.current); },
    acceptMission: (pending: PendingMissionOfficeRead, document: MissionDocument | Missionv3Document | null) => {
      const accepted = completeMissionOfficeRead(pending, current.current, document, new Date().toISOString());
      if (accepted.kind === "observed") {
        current.current = accepted.context; publish({ ...latest.current, mission: accepted.snapshot });
      }
    },
    beginPrograms: () => { clearSource("programs"); return captureProgramsOfficeRead(current.current); },
    acceptPrograms: (pending: PendingProgramsOfficeRead, document: ProgramsObservation | null) => {
      const accepted = completeProgramsOfficeRead(pending, current.current, document, new Date().toISOString());
      if (accepted.kind === "observed") {
        current.current = accepted.context; publish({ ...latest.current, programs: accepted.snapshot });
      }
    },
  };
}
