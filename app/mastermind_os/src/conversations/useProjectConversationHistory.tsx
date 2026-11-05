import { useEffect, useRef, useState } from "react";
import type { MissionHost } from "../host";
import { ProjectConversationHistory } from "./ProjectConversationHistory";
import type { ProjectConversationHistoryReaderFactory } from "./project-conversation-history-owner";

type HistoryHost = MissionHost & { session?: NonNullable<MissionHost["session"]> & {
  createProjectHistoryReader?: ProjectConversationHistoryReaderFactory;
} };
export interface ProjectConversationHistoryWorkspace {
  host: HistoryHost | undefined;
  workRef: string | null;
  authGeneration: number;
  hostGeneration: number | null;
  /** Actual monotonically fenced catalogue/project selection epoch. */
  selectionGeneration: string;
  /** Fresh original catalogue-acquisition witness, including actual current
   * host/receiver/auth/generation and exact selected work; never a render bool.
   * The Executive history READ principal remains separately authenticated. */
  canReadCurrentProject: () => boolean;
  locale?: "en" | "zh-CN";
  theme?: "dark" | "light";
}

/** One selected project only. Construction subscribes but performs no READ.
 * Every context/reference/body request remains an explicit consumer gesture. */
export function useProjectConversationHistory(props: ProjectConversationHistoryWorkspace) {
  const live = useRef(props); live.current = props;
  const session = props.host?.session, factory = session?.createProjectHistoryReader;
  const sourceGeneration = JSON.stringify([props.workRef, props.authGeneration, props.hostGeneration, props.selectionGeneration]);
  const [held, setHeld] = useState<{ host: HistoryHost; session: NonNullable<HistoryHost["session"]>;
    factory: ProjectConversationHistoryReaderFactory; sourceGeneration: string;
    reader: ReturnType<ProjectConversationHistoryReaderFactory> } | null>(null);
  const canRead = () => {
    try { return !!live.current.workRef && live.current.canReadCurrentProject(); } catch { return false; }
  };
  const readAllowed = canRead();
  useEffect(() => {
    const p = live.current;
    if (!p.host || !p.workRef || !session || !factory || !canRead()) { setHeld(null); return; }
    const selected = p.workRef, host = p.host;
    let reader: ReturnType<ProjectConversationHistoryReaderFactory>;
    try { reader = factory.call(session, { workRef: selected,
      currentWorkRef: () => live.current.host === host && live.current.host?.session === session &&
        session.createProjectHistoryReader === factory && canRead() ? live.current.workRef : null,
      selectionGeneration: () => JSON.stringify([live.current.authGeneration, live.current.hostGeneration, live.current.selectionGeneration]),
    }); } catch { setHeld(null); return; }
    setHeld({ host, session, factory, sourceGeneration, reader });
    return () => reader.dispose();
  }, [props.host, session, factory, sourceGeneration, readAllowed]);
  const current = held && held.host === props.host && held.session === session && held.factory === factory &&
    held.sourceGeneration === sourceGeneration ? held.reader : undefined;
  return { history: current, panel: props.workRef ? <ProjectConversationHistory key={`saved-replies:${sourceGeneration}`}
    workRef={props.workRef} sourceGeneration={sourceGeneration} history={current}
    canRead={canRead} locale={props.locale} theme={props.theme}/> : null };
}
