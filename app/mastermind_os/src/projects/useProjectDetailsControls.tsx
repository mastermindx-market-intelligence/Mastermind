import { useMemo, useRef } from "react";
import type { MissionHost } from "../host";
import type { DraftSource } from "../conversations/drafts";
import type { PendingPointerStore } from "../orchestration/operation-controller";
import { useStandingInstructionsWorkspace } from "../instructions/useStandingInstructionsWorkspace";
import { useProjectAccessWorkspace } from "../access/useProjectAccessWorkspace";

export type ProjectDetailsControlHost = Pick<MissionHost,
  "readProjectInstructions" | "readInstructionAdmissionControl" |
  "pauseInstructionAdmission" | "readInstructionAdmissionOperation" | "readProjectAccess">;

export interface ProjectDetailsControlsProps {
  selection: { work_ref: string } | null;
  host: ProjectDetailsControlHost | null;
  authGeneration: number;
  sourceGeneration?: () => number;
  canRead: () => boolean;
  /** The actual incumbent command binding's store; never another store. */
  store?: PendingPointerStore;
  locale: "en" | "zh-CN";
  /** Existing local conversation draft insertion only, never send. */
  onChangeInConversation?: (source: DraftSource) => void;
}

function capturedMethod<Request, Result>(
  receiver: ProjectDetailsControlHost,
  method: (request: Request) => Promise<Result>,
  current: () => unknown,
) {
  return async (request: Request): Promise<Result> => {
    if (current() !== method) throw new Error("PROJECT_CONTROL_SOURCE_CHANGED");
    const result = await method.call(receiver, request);
    if (current() !== method) throw new Error("PROJECT_CONTROL_SOURCE_CHANGED");
    return result;
  };
}

/** Thin App-lifetime composition of accepted owners. No I/O on mount, new
 * controller/store, permission editor, or project Pause/Resume substitution.
 * Existing projectAdmissionPanel remains the separate project gate consumer. */
export function useProjectDetailsControls(props: ProjectDetailsControlsProps) {
  const live = useRef(props);
  live.current = props;
  const host = props.host;
  const content = host?.readProjectInstructions;
  const current = host?.readInstructionAdmissionControl;
  const pause = host?.pauseInstructionAdmission;
  const status = host?.readInstructionAdmissionOperation;
  const access = host?.readProjectAccess;
  const ports = useMemo(() => ({
    canRead: () => live.current.host === host && host !== null &&
      host.readProjectInstructions === content && host.readInstructionAdmissionControl === current &&
      host.pauseInstructionAdmission === pause && host.readInstructionAdmissionOperation === status &&
      live.current.canRead() === true,
    content: host && content ? capturedMethod(host, content, () => host.readProjectInstructions) : undefined,
    current: host && current ? capturedMethod(host, current, () => host.readInstructionAdmissionControl) : undefined,
    instruction: host && pause && status ? {
      pause: capturedMethod(host, pause, () => host.pauseInstructionAdmission),
      status: capturedMethod(host, status, () => host.readInstructionAdmissionOperation),
    } : undefined,
  }), [host, content, current, pause, status]);
  const accessPort = useMemo(() => ({
    canRead: () => live.current.host === host && host !== null &&
      host.readProjectAccess === access && live.current.canRead() === true,
    read: host && access ? capturedMethod(host, access, () => host.readProjectAccess) : undefined,
  }), [host, access]);

  const instructions = useStandingInstructionsWorkspace({
    selection: props.selection, authGeneration: props.authGeneration,
    sourceGeneration: props.sourceGeneration, canRead: ports.canRead,
    readContent: ports.content, readCurrent: ports.current,
    transport: ports.instruction, store: props.store, locale: props.locale,
    onChangeInConversation: props.onChangeInConversation,
  });
  const effectiveAccess = useProjectAccessWorkspace({
    selection: props.selection, authGeneration: props.authGeneration,
    sourceGeneration: props.sourceGeneration, canRead: accessPort.canRead,
    readCurrent: accessPort.read, locale: props.locale,
  });
  return { instructions, access: effectiveAccess };
}
