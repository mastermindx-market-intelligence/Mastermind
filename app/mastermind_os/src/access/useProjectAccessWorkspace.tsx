import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { ProjectAccessPanel } from "./ProjectAccessPanel";
import {
  decodeCurrentProjectAccess,
  validProjectAccessSelection,
  type ProjectAccessSelection,
} from "./project-access-current";
import type { ProjectAccessRequest } from "./project-access-host";
export interface ProjectAccessWorkspaceProps {
  selection: ProjectAccessSelection | null;
  authGeneration: number;
  sourceGeneration?: () => number;
  canRead: () => boolean;
  readCurrent?: (request: ProjectAccessRequest) => Promise<unknown>;
  locale: "en" | "zh-CN";
}
/** App-lifetime explicit READ. No mount I/O, controller, grant cache or mutation. */
export function useProjectAccessWorkspace(props: ProjectAccessWorkspaceProps) {
  const owner = useRef({ method: props.readCurrent, epoch: 0 });
  if (owner.current.method !== props.readCurrent)
    owner.current = {
      method: props.readCurrent,
      epoch: owner.current.epoch + 1,
    };
  const live = useRef(props);
  live.current = props;
  let hostGeneration: number | null = null,
    authorized = false;
  try {
    const value = props.sourceGeneration?.();
    if (Number.isSafeInteger(value) && value !== undefined && value >= 0)
      hostGeneration = value;
    authorized = props.canRead() === true;
  } catch {
    /* absent owner is unqualified */
  }
  const selection =
    props.selection && validProjectAccessSelection(props.selection)
      ? props.selection
      : null;
  const generation = JSON.stringify([
    props.authGeneration,
    hostGeneration,
    owner.current.epoch,
  ]);
  const canRead =
    authorized &&
    selection !== null &&
    hostGeneration !== null &&
    typeof props.readCurrent === "function";
  const scope = JSON.stringify([selection, generation, canRead]);
  const currentScope = useRef(scope);
  currentScope.current = scope;
  const [state, setState] = useState<{
    scope: string;
    data: unknown;
    reading: boolean;
    failed: boolean;
  } | null>(null);
  const current = state?.scope === scope ? state : null;
  const abort = useRef<AbortController | null>(null),
    ticket = useRef(0),
    committed = useRef(scope);
  useLayoutEffect(() => {
    if (committed.current !== scope) {
      committed.current = scope;
      abort.current?.abort();
      ticket.current++;
      setState(null);
    }
  }, [scope]);
  useEffect(
    () => () => {
      abort.current?.abort();
      ticket.current++;
    },
    [],
  );
  function qualified(
    started: string,
    method: ProjectAccessWorkspaceProps["readCurrent"],
    auth: number,
    host: number | null,
  ): boolean {
    try {
      return (
        currentScope.current === started &&
        live.current.readCurrent === method &&
        live.current.authGeneration === auth &&
        live.current.sourceGeneration?.() === host &&
        host !== null &&
        live.current.canRead() === true
      );
    } catch {
      return false;
    }
  }
  async function read() {
    const method = props.readCurrent;
    if (
      !canRead ||
      !selection ||
      !method ||
      !qualified(scope, method, props.authGeneration, hostGeneration)
    )
      return;
    const started = scope,
      pending = new AbortController(),
      request = ++ticket.current;
    abort.current?.abort();
    abort.current = pending;
    setState({ scope: started, data: null, reading: true, failed: false });
    const release = () =>
      !pending.signal.aborted &&
      ticket.current === request &&
      qualified(started, method, props.authGeneration, hostGeneration);
    try {
      const raw = await method({
          selection: { ...selection },
          signal: pending.signal,
        }),
        body = decodeCurrentProjectAccess(raw, selection);
      if (!body) throw Error("PROJECT_ACCESS_RESPONSE_INVALID");
      if (release())
        setState({ scope: started, data: body, reading: false, failed: false });
    } catch {
      if (release())
        setState({ scope: started, data: null, reading: false, failed: true });
    }
  }
  return (
    <ProjectAccessPanel
      selection={selection}
      canRead={canRead}
      sourceGeneration={generation}
      source={
        canRead && current?.data ? { data: current.data, generation } : null
      }
      reading={current?.reading ?? false}
      failed={current?.failed ?? false}
      locale={props.locale}
      onReadCurrent={props.readCurrent ? () => void read() : undefined}
    />
  );
}
