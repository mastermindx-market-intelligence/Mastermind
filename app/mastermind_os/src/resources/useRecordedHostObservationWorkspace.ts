import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { decodeRecordedHostObservation, validHostObservationSelection, type HostObservationRead, type HostObservationSelection, type RecordedHostObservationState } from "./recorded-host-observation";
import type { HostObservationRequest } from "./host-observation-host";
export interface RecordedHostWorkspaceProps {
  selection: HostObservationSelection | null;
  authGeneration: number;
  sourceGeneration?: () => number;
  canRead: () => boolean;
  readCurrent?: (request: HostObservationRequest) => Promise<HostObservationRead>;
}
/** Explicit read only. App owns this lifetime; route toggles cannot restore a
 * document hidden by owner/selection departure. No mount read or live sampling. */
export function useRecordedHostObservationWorkspace(props: RecordedHostWorkspaceProps) {
  const methodOwner = useRef({ method: props.readCurrent, epoch: 0 });
  if (methodOwner.current.method !== props.readCurrent) methodOwner.current = { method: props.readCurrent, epoch: methodOwner.current.epoch + 1 };
  const live = useRef(props); live.current = props;
  let source: number | null = null, authorized = false;
  try {
    const current = props.sourceGeneration?.();
    if (current !== undefined && Number.isSafeInteger(current) && current >= 0) source = current;
    authorized = props.canRead() === true;
  } catch { /* owner unavailable */ }
  const selection = props.selection && validHostObservationSelection(props.selection) ? props.selection : null;
  const readable = authorized && selection !== null && source !== null && typeof props.readCurrent === "function";
  const scope = JSON.stringify([selection, props.authGeneration, source, methodOwner.current.epoch, readable]);
  const scopeRef = useRef(scope); scopeRef.current = scope;
  const [stored, setStored] = useState<{ scope: string; state: RecordedHostObservationState } | null>(null);
  const abort = useRef<AbortController | null>(null), ticket = useRef(0), committed = useRef(scope);
  useLayoutEffect(() => {
    if (committed.current !== scope) {
      committed.current = scope; abort.current?.abort(); ticket.current++; setStored(null);
    }
  }, [scope]);
  useEffect(() => () => { abort.current?.abort(); ticket.current++; }, []);
  const current = readable && stored?.scope === scope ? stored.state : null;
  const read = async () => {
    const method = props.readCurrent, auth = props.authGeneration, generation = source, selected = selection, started = scope;
    if (!readable || !method || !selected) return;
    const qualified = () => {
      try { return scopeRef.current === started && live.current.readCurrent === method && live.current.authGeneration === auth && live.current.sourceGeneration?.() === generation && live.current.canRead() === true; }
      catch { return false; }
    };
    if (!qualified()) return;
    abort.current?.abort(); const controller = new AbortController(); abort.current = controller;
    const serial = ++ticket.current;
    const valid = () => !controller.signal.aborted && ticket.current === serial && qualified();
    setStored({ scope: started, state: { state: "PENDING" } });
    try {
      const result = await method({ selection: selected, signal: controller.signal });
      if (!valid()) return;
      const state: HostObservationRead = result.state === "AVAILABLE"
        ? { state: "AVAILABLE", document: decodeRecordedHostObservation(result.document, selected) }
        : { state: "UNAVAILABLE" };
      if (valid()) setStored({ scope: started, state });
    } catch { if (valid()) setStored({ scope: started, state: { state: "UNAVAILABLE" } }); }
  };
  return { state: current ?? { state: "UNAVAILABLE" } as RecordedHostObservationState,
    canRead: readable, reading: current?.state === "PENDING", read };
}
