import {useEffect, useLayoutEffect, useRef, useState} from "react";
import {ProjectAdmissionPanel} from "./admission/ProjectAdmissionPanel";
import {createProjectAdmissionCommandPort, type ProjectAdmissionSnapshot, type ProjectAdmissionTransport} from "./admission/project-admission-command-port";
import {decodeProjectAdmissionControl, validProjectAdmissionSelection, type ProjectAdmissionSelection} from "./admission/project-admission";
import {OperationController, type PendingPointerStore} from "./orchestration/operation-controller";

type Request = {selection: ProjectAdmissionSelection; signal: AbortSignal};
export interface ProjectAdmissionWorkspaceProps {
  selection: ProjectAdmissionSelection | null;
  authGeneration: number;
  sourceGeneration?: () => number;
  canRead: () => boolean;
  readCurrent?: (request: Request) => Promise<unknown>;
  transport?: ProjectAdmissionTransport;
  /** The actual incumbent commandBinding.store; no substitute is constructed. */
  store?: PendingPointerStore;
  locale: "en" | "zh-CN";
}
type ReadState = {
  scope: string;
  source: {data: unknown; generation: string; readVersion: number} | null;
  reading: boolean;
  hydrate: boolean;
};

/** App-lifetime composition over the existing controller/store and fixed ports.
 * Reads are explicit. Reopen hydration is one original-operation reconciliation
 * after that read, never a new submission, mount loop or background watcher. */
export function useProjectAdmissionWorkspace(props: ProjectAdmissionWorkspaceProps) {
  const owner = useRef({read: props.readCurrent, transport: props.transport, store: props.store, epoch: 0});
  if (owner.current.read !== props.readCurrent || owner.current.transport !== props.transport || owner.current.store !== props.store)
    owner.current = {read: props.readCurrent, transport: props.transport, store: props.store, epoch: owner.current.epoch + 1};
  let hostGeneration: number | null = null, authorized = false;
  try {
    const value = props.sourceGeneration?.();
    if (typeof value === "number" && Number.isSafeInteger(value) && value >= 0) hostGeneration = value;
    authorized = props.canRead() === true;
  } catch { /* Missing/broken owner remains unavailable. */ }
  const selection = props.selection && validProjectAdmissionSelection(props.selection) ? props.selection : null;
  const generation = hostGeneration === null ? null : JSON.stringify([props.authGeneration, hostGeneration, owner.current.epoch]);
  const canRead = authorized && selection !== null && generation !== null && typeof props.readCurrent === "function";
  const scope = JSON.stringify([selection, generation, canRead]);
  const live = useRef(props); live.current = props;
  const liveScope = useRef(scope); liveScope.current = scope;
  const [readState, setReadState] = useState<ReadState | null>(null);
  const [, repaint] = useState(0);
  const version = useRef(0), ticket = useRef(0), abort = useRef<AbortController | null>(null);
  const source = canRead && readState?.scope === scope ? readState.source : null;
  const snapshot = useRef<ProjectAdmissionSnapshot>({selection:null, data:null, dataGeneration:null, generation:null, canRead:false});
  snapshot.current = {selection, data:source?.data ?? null, dataGeneration:source?.generation ?? null, generation, canRead};
  const port = useRef<ReturnType<typeof createProjectAdmissionCommandPort> | null>(null);
  if (!port.current) port.current = createProjectAdmissionCommandPort(() => snapshot.current, {
    pause: request => {
      if (!live.current.transport) return Promise.reject(new Error("PROJECT_CONTROL_UNAVAILABLE"));
      return live.current.transport.pause(request);
    },
    resume: request => {
      if (!live.current.transport) return Promise.reject(new Error("PROJECT_CONTROL_UNAVAILABLE"));
      return live.current.transport.resume(request);
    },
    status: request => {
      if (!live.current.transport) return Promise.reject(new Error("PROJECT_CONTROL_UNAVAILABLE"));
      return live.current.transport.status(request);
    },
  });
  const slot = useRef<{store: PendingPointerStore; controller: OperationController} | null>(null);
  if (props.store && props.transport && slot.current?.store !== props.store)
    slot.current = {store:props.store, controller:new OperationController(port.current, props.store)};
  // Retain the original slot for same-store recovery, but withdrawal of the
  // actual binding must immediately withdraw its action/status capability.
  const controller = props.store && props.transport && slot.current?.store === props.store
    ? slot.current.controller : undefined;
  const committedScope = useRef(scope), committedController = useRef(controller);
  // Mask old state in this render; invalidate before paint. Durable hints stay.
  const scopedController = committedScope.current === scope && committedController.current === controller && props.transport
    ? controller : undefined;
  useLayoutEffect(() => {
    const previous = committedController.current;
    if (committedScope.current !== scope || previous !== controller) {
      previous?.invalidate();
      if (previous !== controller) controller?.invalidate();
      abort.current?.abort(); ticket.current++;
      committedScope.current = scope; committedController.current = controller;
      repaint(value => value + 1);
    }
  }, [scope, controller]);
  useEffect(() => () => {abort.current?.abort(); committedController.current?.invalidate();}, []);

  const hydrated = useRef(0);
  useLayoutEffect(() => {
    if (!source || !readState?.hydrate || !controller || !canRead || source.readVersion === hydrated.current) return;
    hydrated.current = source.readVersion;
    const body = decodeProjectAdmissionControl(source.data, selection!);
    if (body?.availability !== "AVAILABLE") return;
    // Establish only the independently qualified Workspace identity. Its scope
    // is not relabelled as the Executive command owner's principal scope.
    if (!port.current!.context()) return;
    const started = scope, readVersion = source.readVersion;
    setReadState(value => value?.scope === started ? {...value,reading:true,hydrate:false} : value);
    void controller.recover().then(result => {
      if (liveScope.current !== started) return;
      setReadState(value => value?.scope === started && value.source?.readVersion === readVersion
        ? {...value,reading:false,source:result.status === "accepted" || result.status === "refused" ? null : value.source} : value);
      repaint(value => value + 1);
    }, () => {
      if (liveScope.current === started) {
        setReadState(value => value?.scope === started ? {...value,reading:false} : value);
        repaint(value => value + 1);
      }
    });
  }, [source, readState?.hydrate, controller, canRead, selection, scope]);

  async function readCurrent() {
    if (!canRead || !selection || !generation || !live.current.readCurrent) return;
    const started = scope, request = ++ticket.current;
    abort.current?.abort(); const pending = new AbortController(); abort.current = pending;
    setReadState({scope:started,source:null,reading:true,hydrate:false});
    try {
      const data = await live.current.readCurrent({selection:{...selection},signal:pending.signal});
      if (pending.signal.aborted || liveScope.current !== started || ticket.current !== request) return;
      setReadState({scope:started,source:{data,generation,readVersion:++version.current},reading:false,hydrate:true});
    } catch {
      if (!pending.signal.aborted && liveScope.current === started && ticket.current === request)
        setReadState({scope:started,source:null,reading:false,hydrate:false});
    }
  }
  return <ProjectAdmissionPanel selection={selection} canRead={canRead}
    sourceGeneration={generation ?? "SOURCE_UNAVAILABLE"} source={source}
    reading={readState?.scope === scope && readState.reading} onReadCurrent={props.readCurrent ? () => void readCurrent() : undefined}
    controller={scopedController} locale={props.locale} onOperationSettled={() => {
      // Panel disclosure/route remounts must not resurrect the pre-action gate.
      const readVersion=source?.readVersion;
      if(liveScope.current===scope && readVersion!==undefined)
        setReadState(value => value?.scope===scope && value.source?.readVersion===readVersion
          ? {...value,source:null} : value);
    }}/>;
}
