/** App-lifetime presentation custody for the existing fixed Control Room host.
 * No token, cache, action ledger, retry policy or host operation is created here.
 */
import { useEffect, useRef, useState, type MutableRefObject } from "react";
import type { AuthState, MissionHost } from "./host";
import type { MissionSelection } from "./mission";
import {
  ControlRoomActionTransportError,
  controlRoomActionIsUncertain,
  decodeControlRoomActionPayload,
  decodeControlRoomActionResult,
  type ControlRoomActionResult,
  type ControlRoomOperation,
} from "./control-room";
import { decodeControlRoomDiscovery } from "./control-room-navigation";
import type {
  ControlRoomActionPresentation,
  ControlRoomDiscoveryPresentation,
  ControlRoomSurfaceControlsProps,
} from "./ControlRoomSurfaceControls";

type ActionMethodName = "openControlRoomSurface" | "bindControlRoomSurface"
  | "unbindControlRoomSurface" | "refreshControlRoomBuilds";
type MethodName = ActionMethodName | "readControlRoomDiscovery";
const METHOD: Readonly<Record<ControlRoomOperation, ActionMethodName>> = {
  open: "openControlRoomSurface", bind: "bindControlRoomSurface",
  unbind: "unbindControlRoomSurface", "refresh-builds": "refreshControlRoomBuilds",
};
type Scope = Readonly<{
  host: MissionHost;
  auth: NonNullable<MissionHost["auth"]>;
  getState: () => AuthState;
  getGeneration: MissionHost["invalidationGeneration"];
  generation: number | undefined;
  methodName: MethodName;
  method: NonNullable<MissionHost[MethodName]>;
  authEpoch: number;
  selectionEpoch: number;
  selection: Readonly<MissionSelection> | null;
}>;
type RenderBinding = Omit<Scope, "methodName" | "method"> & Readonly<{
  methods: Readonly<Pick<MissionHost, MethodName>>;
}>;
type ActionFlight = {
  scope: Scope | null;
  held: boolean;
  controller: AbortController;
  /** Retain the exact detached request for this original invocation only. */
  payload: Readonly<Record<string, unknown>> | null;
  presentation: ControlRoomActionPresentation;
};
type DiscoveryFlight = {
  scope: Scope;
  controller: AbortController;
  presentation: ControlRoomDiscoveryPresentation;
};

/** Mount once in App, above the auth-keyed ControlRoomPanel. Ordinary view and
 * auth changes may cancel READs; they never abort, clear or resend an action.
 * Full App/process loss is outside this in-memory presentation's guarantee.
 */
export function useControlRoomSurfaceControls({
  selection, selectionSeq, authEpoch, authRevision, active,
}: {
  selection: MissionSelection | null;
  selectionSeq: MutableRefObject<number>;
  authEpoch: MutableRefObject<number>;
  authRevision: number;
  active: boolean;
}): Omit<ControlRoomSurfaceControlsProps, "navigation" | "locale"> {
  const action = useRef<ActionFlight | null>(null);
  const discovery = useRef<DiscoveryFlight | null>(null);
  const [, render] = useState(0);
  // A callback belonging to an earlier render cannot acquire the authority of
  // an auth/selection transition that occurred before React's next commit.
  const renderedAuthEpoch = authEpoch.current;
  const renderedSelectionEpoch = selectionSeq.current;
  // Retain the binding that supplied this render's explicit controls. An old
  // click closure must never adopt a replacement host or method at invocation.
  const renderedBinding: RenderBinding | null = (() => {
    try {
      const host = window.MastermindMissionHost;
      const auth = host?.auth;
      const getState = auth?.getState;
      const getGeneration = host?.invalidationGeneration;
      if (!host || !auth || typeof getState !== "function") return null;
      const methods = Object.freeze({
        openControlRoomSurface: host.openControlRoomSurface,
        bindControlRoomSurface: host.bindControlRoomSurface,
        unbindControlRoomSurface: host.unbindControlRoomSurface,
        refreshControlRoomBuilds: host.refreshControlRoomBuilds,
        readControlRoomDiscovery: host.readControlRoomDiscovery,
      });
      return Object.freeze({
        host, auth, getState, getGeneration, methods,
        generation: getGeneration?.call(host),
        authEpoch: renderedAuthEpoch,
        selectionEpoch: renderedSelectionEpoch,
        selection: selection ? Object.freeze({ ...selection }) : null,
      });
    } catch { return null; }
  })();

  function current(scope: Scope | RenderBinding): boolean {
    try {
      const host = window.MastermindMissionHost;
      const auth = host?.auth;
      const getState = auth?.getState;
      const getGeneration = host?.invalidationGeneration;
      const state = getState?.call(auth);
      const generation = getGeneration?.call(host);
      const eligible = state?.status === "signed_in" && state.acquisition === true;
      // Read every dependency before the final internal epoch checks. A state
      // or generation callback cannot reenter auth and then pass an old epoch.
      const sameBinding = host === scope.host && auth === scope.auth
        && getState === scope.getState && getGeneration === scope.getGeneration
        && (!("methodName" in scope) || host?.[scope.methodName] === scope.method)
        && window.MastermindMissionHost === scope.host
        && scope.host.auth === scope.auth
        && scope.auth.getState === scope.getState
        && scope.host.invalidationGeneration === scope.getGeneration;
      return eligible && sameBinding && generation === scope.generation
        && authEpoch.current === scope.authEpoch
        && selectionSeq.current === scope.selectionEpoch;
    } catch { return false; }
  }

  function capture(methodName: MethodName): Scope {
    const method = renderedBinding?.methods[methodName];
    if (!renderedBinding || typeof method !== "function")
      throw new Error("CONTROL_ROOM_METHOD_UNAVAILABLE");
    const { methods: _methods, ...owner } = renderedBinding;
    const scope: Scope = Object.freeze({ ...owner, methodName, method });
    if (!current(scope)) throw new Error("CONTROL_ROOM_CONTEXT_CHANGED");
    return scope;
  }

  function settle(flight: ActionFlight, presentation: ControlRoomActionPresentation, held: boolean) {
    if (action.current !== flight) return;
    flight.presentation = presentation;
    flight.held = held;
    render(value => value + 1);
  }

  async function runAction(operation: ControlRoomOperation, request: unknown = {}) {
    if (action.current?.held) return;
    // Reserve before any callback, payload decoding or promise boundary can
    // reenter this handler. Two clicks in the same render share this one hold.
    const flight: ActionFlight = {
      scope: null, held: true, controller: new AbortController(), payload: null,
      presentation: { state: "PENDING", operation },
    };
    action.current = flight;
    render(value => value + 1);
    let scope: Scope;
    let payload: Readonly<Record<string, unknown>>;
    try {
      scope = capture(METHOD[operation]);
      flight.scope = scope;
      payload = decodeControlRoomActionPayload(request, operation);
      flight.payload = payload;
      if (!current(scope) || flight.controller.signal.aborted)
        throw new Error("CONTROL_ROOM_ACTION_NOT_ADMITTED");
    } catch {
      settle(flight, { state: "FAILURE", operation, disposition: "NOT_DISPATCHED" }, false);
      return;
    }

    let value: unknown;
    try {
      // Invoke the captured fixed method once. No route is synthesized and the
      // action controller is deliberately outside all READ cleanup effects.
      if (operation === "refresh-builds") {
        value = await (scope.method as NonNullable<MissionHost["refreshControlRoomBuilds"]>)
          .call(scope.host, { signal: flight.controller.signal });
      } else {
        value = await (scope.method as NonNullable<MissionHost["openControlRoomSurface"]>)
          .call(scope.host, { payload, signal: flight.controller.signal });
      }
    } catch (error) {
      let disposition: "NOT_DISPATCHED" | "EFFECT_UNKNOWN" = "EFFECT_UNKNOWN";
      try {
        if (error instanceof ControlRoomActionTransportError && error.operation === operation
            && (error.disposition === "NOT_DISPATCHED" || error.disposition === "EFFECT_UNKNOWN"))
          disposition = error.disposition;
      } catch { /* An uninspectable original-owner error remains uncertain. */ }
      settle(flight, { state: "FAILURE", operation, disposition }, disposition === "EFFECT_UNKNOWN");
      return;
    }

    let result: ControlRoomActionResult;
    try {
      const status = value && typeof value === "object" && !Array.isArray(value)
        ? (value as { status?: number }).status : NaN;
      result = decodeControlRoomActionResult(value, operation, status as number);
    } catch {
      settle(flight, { state: "FAILURE", operation, disposition: "EFFECT_UNKNOWN" }, true);
      return;
    }
    // Keep a qualified owner result even when auth or navigation changed while
    // awaiting it. Only its presentation is withheld under a different scope.
    settle(flight, { state: "RESULT", result }, controlRoomActionIsUncertain(result));
  }

  async function discover() {
    discovery.current?.controller.abort();
    discovery.current = null;
    render(value => value + 1);
    let flight: DiscoveryFlight | null = null;
    try {
      const scope = capture("readControlRoomDiscovery");
      flight = { scope, controller: new AbortController(), presentation: { state: "PENDING" } };
      discovery.current = flight;
      render(value => value + 1);
      if (!current(scope)) throw new Error("CONTROL_ROOM_CONTEXT_CHANGED");
      const raw = await (scope.method as NonNullable<MissionHost["readControlRoomDiscovery"]>)
        .call(scope.host, { signal: flight.controller.signal });
      const document = decodeControlRoomDiscovery(raw);
      if (discovery.current !== flight) return;
      if (flight.controller.signal.aborted || !current(scope)) {
        discovery.current = null;
        render(value => value + 1);
        return;
      }
      flight.presentation = { state: "AVAILABLE", document };
    } catch {
      const owned = discovery.current;
      if (!owned || owned !== flight) return;
      if (owned.controller.signal.aborted || !current(owned.scope)) {
        discovery.current = null;
        render(value => value + 1);
        return;
      }
      owned.presentation = { state: "UNAVAILABLE" };
    }
    render(value => value + 1);
  }

  useEffect(() => () => {
    discovery.current?.controller.abort();
    discovery.current = null;
  }, [active, authRevision, renderedSelectionEpoch]);

  const pending = action.current;
  const actionPresentation: ControlRoomActionPresentation = !pending
    ? { state: "IDLE" }
    : pending.scope && current(pending.scope)
      ? pending.presentation
      : { state: "WITHHELD", held: pending.held };
  const observed = discovery.current;
  const discoveryPresentation: ControlRoomDiscoveryPresentation = observed && current(observed.scope)
    ? observed.presentation : { state: "IDLE" };
  const canAct = renderedBinding !== null && current(renderedBinding);
  const methods = renderedBinding?.methods;
  return {
    discovery: discoveryPresentation,
    action: actionPresentation,
    held: pending?.held ?? false,
    canAct,
    onDiscover: typeof methods?.readControlRoomDiscovery === "function" ? () => { void discover(); } : undefined,
    onOpenSurface: typeof methods?.openControlRoomSurface === "function" ? payload => { void runAction("open", payload); } : undefined,
    onBindSurface: typeof methods?.bindControlRoomSurface === "function" ? payload => { void runAction("bind", payload); } : undefined,
    onUnbindSurface: typeof methods?.unbindControlRoomSurface === "function" ? payload => { void runAction("unbind", payload); } : undefined,
    onRefreshBuilds: typeof methods?.refreshControlRoomBuilds === "function" ? () => { void runAction("refresh-builds"); } : undefined,
  };
}
