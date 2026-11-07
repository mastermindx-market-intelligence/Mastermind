import { useLayoutEffect, useMemo, useRef, useState } from "react";
import {
  OperationController,
  type PendingPointerStore,
} from "../orchestration/operation-controller";
import { createIndexedDbPendingPointerStore } from "../orchestration/indexeddb-pending-pointer-store";
import { validProjectPlanSelection } from "./project-plan";
import { planAdoptionRequestFromRead } from "./plan-adoption-from-read";
import type { PlanAdoptionRequest } from "./plan-adoption-request";
import {
  bindPlanAdoptionOwner,
  createPlanAdoptionPort,
  preparePlanAdoption,
  type PreparedPlanAdoption,
  type PlanAdoptionTransport,
} from "./plan-adoption-port";
import { planAdoptionPreparedReview } from "./PlanAdoptionPreparedSummary";
import { PlanAdoptionReview } from "./PlanAdoptionReview";
import type {
  PlanAdoptionInspection,
  PlanAdoptionWorkflowHost,
} from "./plan-adoption-workspace";

export interface PlanAdoptionWorkflowProps {
  workRef: string;
  inspection: PlanAdoptionInspection | null;
  host: PlanAdoptionWorkflowHost;
  /** Caller-owned live host/auth identity; absence preserves component compatibility. */
  isHostCurrent?: () => boolean;
  locale?: "en" | "zh-CN";
  store?: PendingPointerStore;
  crypto?: Pick<Crypto, "getRandomValues">;
}
interface Frame {
  host: PlanAdoptionWorkflowHost;
  isHostCurrent: PlanAdoptionWorkflowProps["isHostCurrent"];
  workRef: string;
  epoch: number;
  transport: PlanAdoptionTransport;
  read: NonNullable<PlanAdoptionWorkflowHost["readSourceOperationContext"]>;
  auth: PlanAdoptionWorkflowHost["auth"];
  generation: PlanAdoptionWorkflowHost["invalidationGeneration"];
}
interface Context {
  frame: Frame;
  raw: unknown;
}
interface Prepared {
  context: Context;
  inspection: PlanAdoptionInspection;
  anchor: PreparedPlanAdoption;
}
const permits = (read: () => boolean) => {
  try {
    return read() === true;
  } catch {
    return false;
  }
};
function epoch(host: PlanAdoptionWorkflowHost): number | null {
  try {
    const value = host.invalidationGeneration?.();
    return typeof value === "number" &&
      Number.isSafeInteger(value) &&
      value >= 0
      ? value
      : null;
  } catch {
    return null;
  }
}
function authenticated(host: PlanAdoptionWorkflowHost): boolean {
  return permits(() => {
    const state = host.auth?.getState();
    return state?.status === "signed_in" && state.acquisition === true;
  });
}
function sameInspection(
  left: PlanAdoptionInspection | null,
  right: PlanAdoptionInspection | null,
): boolean {
  return (
    left !== null &&
    right !== null &&
    left.read === right.read &&
    left.proposalId === right.proposalId &&
    left.selection.work_ref === right.selection.work_ref &&
    permits(left.isCurrent) &&
    permits(left.canRead) &&
    permits(right.isCurrent) &&
    permits(right.canRead)
  );
}

/** Composition over the incumbent owner, port, controller and durable store.
 * Context/reopen reads are independent of plan acquisition. Only explicit
 * gestures prepare a preview, submit, reconcile or advance the original.
 */
export function PlanAdoptionWorkflow(props: PlanAdoptionWorkflowProps) {
  const latest = useRef(props);
  latest.current = props;
  const [, renderAuth] = useState(0);
  const [retry, setRetry] = useState(0);
  const [context, setContext] = useState<Context | null>(null);
  const contextRef = useRef<Context | null>(null);
  const [contextFailed, setContextFailed] = useState(false);
  const [prepared, setPrepared] = useState<Prepared | null>(null);
  const preparedRef = useRef<Prepared | null>(null);
  const requestRef = useRef<{
    context: Context;
    inspection: PlanAdoptionInspection;
    request: PlanAdoptionRequest;
  } | null>(null);
  const [preparing, setPreparing] = useState(false);
  const [prepareFailed, setPrepareFailed] = useState(false);
  const prepareLatch = useRef(false);
  const prepareAbort = useRef<AbortController | null>(null);
  const defaultStore = useMemo(
    () => createIndexedDbPendingPointerStore(globalThis.indexedDB),
    [],
  );
  const store = props.store ?? defaultStore;
  const currentEpoch = epoch(props.host),
    signed = authenticated(props.host);
  const transport = props.host.sourceOperations,
    readContext = props.host.readSourceOperationContext;
  const frame = useMemo<Frame | null>(
    () =>
      validProjectPlanSelection({ work_ref: props.workRef }) &&
      (props.isHostCurrent === undefined || permits(props.isHostCurrent)) &&
      signed &&
      currentEpoch !== null &&
      transport &&
      typeof transport.readSourceOperation === "function" &&
      typeof readContext === "function"
        ? {
            host: props.host,
            isHostCurrent: props.isHostCurrent,
            workRef: props.workRef,
            epoch: currentEpoch,
            transport,
            read: readContext,
            auth: props.host.auth,
            generation: props.host.invalidationGeneration,
          }
        : null,
    [
      props.host,
      props.isHostCurrent,
      props.host.auth,
      props.host.invalidationGeneration,
      props.workRef,
      signed,
      currentEpoch,
      transport,
      readContext,
    ],
  );
  const frameCurrent = (captured: Frame) => {
    const now = latest.current;
    return (
      now.host === captured.host &&
      now.isHostCurrent === captured.isHostCurrent &&
      (captured.isHostCurrent === undefined || permits(captured.isHostCurrent)) &&
      now.workRef === captured.workRef &&
      now.host.sourceOperations === captured.transport &&
      now.host.readSourceOperationContext === captured.read &&
      now.host.auth === captured.auth &&
      now.host.invalidationGeneration === captured.generation &&
      authenticated(now.host) &&
      epoch(now.host) === captured.epoch
    );
  };
  const contextCurrent = (captured: Context) =>
    contextRef.current === captured && frameCurrent(captured.frame);
  const inspectionCurrent = (captured: PlanAdoptionInspection) =>
    sameInspection(captured, latest.current.inspection) &&
    captured.selection.work_ref === latest.current.workRef;

  useLayoutEffect(
    () => props.host.auth?.subscribe(() => renderAuth((n) => n + 1)),
    [props.host, props.host.auth],
  );
  useLayoutEffect(() => {
    contextRef.current = null;
    setContext(null);
    setContextFailed(false);
    preparedRef.current = null;
    setPrepared(null);
    setPrepareFailed(false);
    prepareAbort.current?.abort();
    if (frame === null) return;
    const controller = new AbortController();
    let active = true;
    void (async () => {
      try {
        if (!frameCurrent(frame)) return;
        const raw = await frame.read.call(frame.host, {
          action: "ADOPT_PLAN",
          workRef: frame.workRef,
          signal: controller.signal,
        });
        if (!active || controller.signal.aborted || !frameCurrent(frame))
          return;
        // Validate the actual closed body before publishing any capability.
        bindPlanAdoptionOwner({
          raw,
          workRef: frame.workRef,
          generation: String(frame.epoch),
          isCurrent: () => true,
          sourceReady: () => false,
        });
        const value = { frame, raw };
        contextRef.current = value;
        setContext(value);
      } catch {
        if (active && !controller.signal.aborted && frameCurrent(frame))
          setContextFailed(true);
      }
    })();
    return () => {
      active = false;
      controller.abort();
      contextRef.current = null;
      prepareAbort.current?.abort();
    };
  }, [frame, retry]);

  const session = useMemo(() => {
    if (context === null || context.frame !== frame) return null;
    const owner = bindPlanAdoptionOwner({
      raw: context.raw,
      workRef: context.frame.workRef,
      generation: String(context.frame.epoch),
      isCurrent: () => contextCurrent(context),
      // Method readiness is an enablement hint; the actual owner revalidates
      // the exact private recipe/current source/grant on every effect.
      sourceReady: () =>
        typeof context.frame.transport.prepareSourceOperation === "function" &&
        typeof context.frame.transport.submitSourceOperation === "function" &&
        typeof context.frame.transport.advanceSourceOperation === "function",
    });
    const port = createPlanAdoptionPort({
      workRef: context.frame.workRef,
      transport: context.frame.transport,
      owner,
      prepared: () =>
        preparedRef.current?.context === context
          ? preparedRef.current.anchor
          : null,
      isPreparedCurrent: (anchor) => {
        const value = preparedRef.current;
        return (
          value?.anchor === anchor &&
          value.context === context &&
          contextCurrent(context) &&
          inspectionCurrent(value.inspection)
        );
      },
    });
    return { context, owner, controller: new OperationController(port, store) };
  }, [context, frame, store]);
  useLayoutEffect(() => () => session?.controller.invalidate(), [session]);

  const startReview = async () => {
    const inspection = latest.current.inspection;
    if (
      prepareLatch.current ||
      session === null ||
      !contextCurrent(session.context) ||
      inspection === null ||
      !inspectionCurrent(inspection)
    )
      return;
    prepareLatch.current = true;
    setPreparing(true);
    setPrepareFailed(false);
    preparedRef.current = null;
    setPrepared(null);
    const abort = new AbortController();
    prepareAbort.current?.abort();
    prepareAbort.current = abort;
    try {
      let original = requestRef.current;
      if (
        original === null ||
        original.context !== session.context ||
        !sameInspection(original.inspection, inspection)
      ) {
        const crypto = latest.current.crypto ?? globalThis.crypto;
        if (!crypto || typeof crypto.getRandomValues !== "function")
          throw Error();
        const bytes = new Uint8Array(20);
        crypto.getRandomValues(bytes);
        const id =
          "mmos-project-adopt-" +
          Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
        const request = planAdoptionRequestFromRead(
          inspection.read,
          inspection.selection,
          inspection.proposalId,
          id,
        );
        original = { context: session.context, inspection, request };
        requestRef.current = original;
      }
      const anchor = await preparePlanAdoption(
        {
          workRef: session.context.frame.workRef,
          request: original.request,
          transport: session.context.frame.transport,
          owner: session.owner,
          isCurrent: () =>
            contextCurrent(session.context) && inspectionCurrent(inspection),
        },
        abort.signal,
      );
      if (
        abort.signal.aborted ||
        !contextCurrent(session.context) ||
        !inspectionCurrent(inspection)
      )
        return;
      const value = { context: session.context, inspection, anchor };
      preparedRef.current = value;
      setPrepared(value);
    } catch {
      if (
        !abort.signal.aborted &&
        contextCurrent(session.context) &&
        inspectionCurrent(inspection)
      )
        setPrepareFailed(true);
    } finally {
      prepareLatch.current = false;
      if (prepareAbort.current === abort) prepareAbort.current = null;
      setPreparing(false);
    }
  };
  let review;
  if (
    prepared &&
    session?.context === prepared.context &&
    contextCurrent(prepared.context) &&
    inspectionCurrent(prepared.inspection)
  ) {
    try {
      review = planAdoptionPreparedReview(prepared.anchor, {
        read: prepared.inspection.read,
        selection: prepared.inspection.selection,
        proposalId: prepared.inspection.proposalId,
        isCurrent: () =>
          contextCurrent(prepared.context) &&
          inspectionCurrent(prepared.inspection),
        canReadComparison: () => inspectionCurrent(prepared.inspection),
        locale: props.locale,
      });
    } catch {
      /* no stale comparison */
    }
  }
  const zh = props.locale === "zh-CN";
  const random = props.crypto ?? globalThis.crypto;
  const canPrepare =
    session !== null &&
    contextCurrent(session.context) &&
    props.inspection !== null &&
    inspectionCurrent(props.inspection) &&
    typeof random?.getRandomValues === "function" &&
    !preparing;
  return (
    <>
      <div
        className="mm-plan-adoption__heading-actions"
        lang={props.locale ?? "en"}
      >
        {!review && (
          <button
            type="button"
            className="mm-plan-adoption__action"
            disabled={!canPrepare}
            onClick={() => void startReview()}
          >
            {preparing
              ? zh
                ? "正在准备审查…"
                : "Preparing review…"
              : zh
                ? "审查采纳"
                : "Review adoption"}
          </button>
        )}
        {contextFailed && (
          <button
            type="button"
            className="mm-plan-adoption__action"
            onClick={() => setRetry((n) => n + 1)}
          >
            {zh ? "重新检查访问权限" : "Check access again"}
          </button>
        )}
      </div>
      {(frame === null || contextFailed) && (
        <p role="status">
          {zh
            ? "此处暂时无法采纳计划；仍可查看已记录的计划。"
            : "Plan adoption is unavailable here. The recorded plan remains available."}
        </p>
      )}
      {prepareFailed && (
        <p role="status">
          {zh
            ? "无法准备采纳审查。原始操作仍可单独检查。"
            : "The adoption review could not be prepared. The original operation can still be checked separately."}
        </p>
      )}
      <PlanAdoptionReview
        workRef={props.workRef}
        locale={props.locale}
        prepared={review}
        recoverOnMount
        openPrepared
        binding={
          session
            ? {
                controller: session.controller,
                context: session.owner.context,
                canAdopt: session.owner.canAdopt,
                canInspect: session.owner.canInspect,
              }
            : undefined
        }
      />
    </>
  );
}
