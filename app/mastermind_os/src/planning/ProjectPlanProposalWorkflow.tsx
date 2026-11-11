import { useEffect, useLayoutEffect, useRef, useState } from "react";
import type { MissionHost } from "../host";
import type { DirectResult } from "../direct-native-result";
import {
  OperationController,
  type OperationState,
  type OwnerContext,
  type PendingPointerStore,
} from "../orchestration/operation-controller";
import { decodeSourceOperationContext } from "../source-operations/context";
import { canonicalJson } from "../orchestration/operation-key";
import { ProjectPlanPanel } from "./ProjectPlanPanel";
import type { SourceOperationStatus } from "./plan-adoption-status";
import {
  createPlanProposalPort,
  preparePlanProposal,
  proposalPointer,
  qualifyPlanProposalStatus,
  type PlanProposalOwner,
  type PreparedPlanProposal,
} from "./project-plan-proposal-port";
import {
  PLAN_PROPOSAL_ACTION as ACTION,
  decodePlanProposalOriginal,
  planProposalOriginalFromRead,
  proposalUnavailable,
  type PlanProposalOriginal,
} from "./project-plan-proposal";

export interface ProjectPlanProposalWorkflowProps {
  host: MissionHost | null;
  store: PendingPointerStore;
  workRef: string;
  planningOperationKey: string;
  result: DirectResult | null;
  consumed: boolean;
  hasDeclaration: boolean;
  executiveOwner: () => OwnerContext | null;
  isCurrent: () => boolean;
  original: PlanProposalOriginal | null;
  /** Synchronous read of the incumbent URL/state owner; never a grant. */
  currentOriginal: () => PlanProposalOriginal | null;
  /** The existing App owner commits safe URL metadata before preparation. */
  onOriginalChange: (original: PlanProposalOriginal) => void;
  locale?: "en" | "zh-CN";
}
type Host = NonNullable<ProjectPlanProposalWorkflowProps["host"]>;
interface Frame {
  host: Host;
  epoch: number;
  binding: NonNullable<Host["commandBinding"]>;
  store: PendingPointerStore;
  workRef: string;
  planningKey: string;
  source: NonNullable<Host["sourceOperations"]>;
  context: NonNullable<Host["readSourceOperationContext"]>;
}
export function ProjectPlanProposalWorkflow(
  props: ProjectPlanProposalWorkflowProps,
) {
  const live = useRef(props);
  live.current = props;
  const durable = useRef({
    store: props.store,
    read: props.store.read,
    reserve: props.store.reserve,
    clear: props.store.clearIfEqual,
  }).current;
  function storeCurrent(): boolean {
    try {
      return (
        live.current.isCurrent() &&
        live.current.store === durable.store &&
        live.current.host?.commandBinding?.store === durable.store &&
        durable.store.read === durable.read &&
        durable.store.reserve === durable.reserve &&
        durable.store.clearIfEqual === durable.clear
      );
    } catch {
      return false;
    }
  }
  function requireStore() {
    if (!storeCurrent()) return proposalUnavailable();
  }

  const zh = props.locale === "zh-CN",
    say = (en: string, cn: string) => (zh ? cn : en);
  const [prepared, setPrepared] = useState<PreparedPlanProposal | null>(null);
  const preparedRef = useRef(prepared);
  preparedRef.current = prepared;
  const [status, setStatus] = useState<SourceOperationStatus | null>(null);
  const [state, setState] = useState<OperationState>({
    status: "idle",
    pointer: null,
    reason: "IDLE",
  });
  const [busy, setBusy] = useState(false),
    busyRef = useRef(false);
  const [notice, setNotice] = useState<
    "unavailable" | "unknown" | "prepared" | null
  >(null);
  const [showCompare, setShowCompare] = useState(false);
  const request = useRef<AbortController | null>(null);
  const publishButton=useRef<HTMLButtonElement|null>(null),compareButton=useRef<HTMLButtonElement|null>(null);
  const focusIntent=useRef<{frame:Frame;target:"publish"|"compare";trigger:HTMLButtonElement}|null>(null);
  const basis = useRef<PlanProposalOriginal | null>(null);
  function originalCurrent(): PlanProposalOriginal | null {
    try {
      return live.current.currentOriginal();
    } catch {
      return null;
    }
  }
  const preparedFrame = useRef<Frame | null>(null),
    statusFrame = useRef<Frame | null>(null);
  const statusOriginal = useRef<string | null>(null);
  const publicationStarted = useRef(false);
  const identity = useRef<{ frame: Frame; scope: string } | null>(null);
  function frameCurrent(f: Frame): boolean {
    const p = live.current,
      h = p.host;
    try {
      return (
        p.isCurrent() &&
        storeCurrent() &&
        p.store === f.store &&
        h?.commandBinding === f.binding &&
        f.binding.store === f.store &&
        h === f.host &&
        h.sourceOperations === f.source &&
        h.readSourceOperationContext === f.context &&
        h.auth?.getState().status === "signed_in" &&
        h.auth.getState().acquisition === true &&
        h.invalidationGeneration?.() === f.epoch &&
        p.workRef === f.workRef &&
        p.planningOperationKey === f.planningKey
      );
    } catch {
      return false;
    }
  }
  function capture(): Frame {
    const p = live.current,
      h = p.host,
      epoch = h?.invalidationGeneration?.();
    if (
      !h ||
      !h.sourceOperations ||
      !h.commandBinding ||
      !storeCurrent() ||
      !h.readSourceOperationContext ||
      !Number.isSafeInteger(epoch)
    )
      return proposalUnavailable();
    const f = {
      host: h,
      epoch: epoch!,
      binding: h.commandBinding,
      store: durable.store,
      workRef: p.workRef,
      planningKey: p.planningOperationKey,
      source: h.sourceOperations,
      context: h.readSourceOperationContext,
    };
    if (!frameCurrent(f)) return proposalUnavailable();
    return f;
  }
  const owner = useRef<PlanProposalOwner>({
    context: () => {
      const i = identity.current;
      return i && frameCurrent(i.frame)
        ? { principalScope: i.scope, generation: String(i.frame.epoch) }
        : null;
    },
    canInspect: () =>
      !!identity.current && frameCurrent(identity.current.frame),
    canPublish: () =>
      !!identity.current &&
      frameCurrent(identity.current.frame) &&
      basis.current !== null &&
      originalCurrent() !== null &&
      canonicalJson(basis.current) === canonicalJson(originalCurrent()),
  });
  function resultMatches(o: PlanProposalOriginal): boolean {
    const p = live.current,
      r = p.result;
    return (
      p.consumed &&
      !!r?.result &&
      r.selection.work_ref === o.work_ref &&
      r.selection.job_id === o.proposal_request.selection.job_id &&
      r.selection.attempt_id === o.proposal_request.selection.attempt_id &&
      r.result.result_digest === o.proposal_request.result_digest
    );
  }
  function preparedCurrent(p: PreparedPlanProposal): boolean {
    const e = live.current.executiveOwner();
    return (
      !!preparedFrame.current &&
      frameCurrent(preparedFrame.current) &&
      !!e &&
      e.principalScope === p.executive.principalScope &&
      e.generation === p.executive.generation &&
      originalCurrent() !== null &&
      canonicalJson(originalCurrent()) === canonicalJson(p.original) &&
      resultMatches(p.original)
    );
  }
  function observeStatus(value:SourceOperationStatus,frame:Frame){
    const original=originalCurrent();if(!original||!frameCurrent(frame))return;
    statusFrame.current=frame;statusOriginal.current=canonicalJson(original);setStatus(value);
    if(value.disposition==="accepted"&&value.receipt?.kind==="SOURCE_OBSERVED")setNotice(null);
  }
  const machine = useRef<OperationController | null>(null);
  if (machine.current === null) {
    const source = {
      prepareSourceOperation: (
        ...args: Parameters<
          NonNullable<Host["sourceOperations"]>["prepareSourceOperation"]
        >
      ) => live.current.host!.sourceOperations!.prepareSourceOperation(...args),
      readSourceOperation: (
        ...args: Parameters<
          NonNullable<Host["sourceOperations"]>["readSourceOperation"]
        >
      ) => live.current.host!.sourceOperations!.readSourceOperation(...args),
      submitSourceOperation: (
        ...args: Parameters<
          NonNullable<Host["sourceOperations"]>["submitSourceOperation"]
        >
      ) => live.current.host!.sourceOperations!.submitSourceOperation(...args),
      reconcileSourceOperation: (
        ...args: Parameters<
          NonNullable<Host["sourceOperations"]>["reconcileSourceOperation"]
        >
      ) =>
        live.current.host!.sourceOperations!.reconcileSourceOperation(...args),
      advanceSourceOperation: (
        ...args: Parameters<
          NonNullable<Host["sourceOperations"]>["advanceSourceOperation"]
        >
      ) => live.current.host!.sourceOperations!.advanceSourceOperation(...args),
    };
    const port = createPlanProposalPort({
      workRef: props.workRef,
      source,
      owner: owner.current,
      original: () => originalCurrent(),
      prepared: () => preparedRef.current,
      isPreparedCurrent: preparedCurrent,
      onStatus: (value) => {const frame=identity.current?.frame;if(frame)observeStatus(value,frame);},
    });
    machine.current = new OperationController(port, {
      read: (...a) => {
        requireStore();
        return durable.read.call(durable.store, ...a);
      },
      reserve: (...a) => {
        requireStore();
        return durable.reserve.call(durable.store, ...a);
      },
      clearIfEqual: (...a) => {
        requireStore();
        return durable.clear.call(durable.store, ...a);
      },
    });
  }
  useEffect(() => {
    const h = props.host;
    const stop = h?.auth?.subscribe(() => {
      request.current?.abort();
      machine.current!.invalidate();
      identity.current = null;
      basis.current = null;
      setPrepared(null);
      setStatus(null);
      setShowCompare(false);focusIntent.current=null;
      setNotice(null);
    });
    return () => {
      stop?.();focusIntent.current=null;
      request.current?.abort();
      machine.current!.invalidate();
      identity.current = null;
      basis.current = null;
    };
  }, [props.host, props.workRef, props.planningOperationKey]);
  async function qualify(f: Frame, signal: AbortSignal) {
    const raw = await f.context({ action: ACTION, workRef: f.workRef, signal });
    if (signal.aborted || !frameCurrent(f)) return proposalUnavailable();
    const c = decodeSourceOperationContext(raw, {
      action: ACTION,
      workRef: f.workRef,
    });
    identity.current = { frame: f, scope: c.owner_context.principal_scope };
    return c;
  }
  async function run(body: (f: Frame, signal: AbortSignal) => Promise<void>) {
    if (busyRef.current) return;
    busyRef.current = true;
    setBusy(true);
    const signal = new AbortController();
    request.current = signal;
    try {
      const f = capture();
      await body(f, signal.signal);
    } catch {
      setNotice("unavailable");
    } finally {
      if (request.current === signal) request.current = null;
      busyRef.current = false;
      setBusy(false);
    }
  }
  const prepare = (trigger:HTMLButtonElement) =>
    run(async (f, signal) => {
      const p = live.current,
        r = p.result;
      if (
        !p.consumed ||
        !p.hasDeclaration ||
        !r?.result ||
        !r.selection.attempt_id ||
        r.selection.work_ref !== p.workRef ||
        !f.host.readProjectPlan ||
        !f.host.projectPlanning
      )
        return proposalUnavailable();
      const material = {
        jobId: r.selection.job_id,
        attemptId: r.selection.attempt_id,
        resultDigest: r.result.result_digest,
      };
      const read = await f.host.readProjectPlan({
        work_ref: f.workRef,
        signal,
      });
      if (signal.aborted || !frameCurrent(f)) return proposalUnavailable();
      let original = p.original;
      if (original === null) {
        const bytes = new Uint8Array(20);
        crypto.getRandomValues(bytes);
        const id =
          "mmos-project-plan-proposal-" +
          Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
        original = planProposalOriginalFromRead({
          read,
          workRef: p.workRef,
          planningOperationKey: p.planningOperationKey,
          requestId: id,
          ...material,
        });
        // Sync URL write must succeed before either private preparation or publication.
        p.onOriginalChange(original);
      } else {
        original = decodePlanProposalOriginal(original, p.workRef);
        const same = planProposalOriginalFromRead({
          read,
          workRef: p.workRef,
          planningOperationKey: p.planningOperationKey,
          requestId: original.proposal_request.request_id,
          ...material,
        });
        if (canonicalJson(same) !== canonicalJson(original))
          return proposalUnavailable();
      }
      basis.current = original;
      await qualify(f, signal);
      const value = await preparePlanProposal(
        {
          original,
          planning: f.host.projectPlanning,
          owner: owner.current,
          executiveOwner: () => live.current.executiveOwner(),
          isCurrent: () =>
            frameCurrent(f) &&
            originalCurrent() !== null &&
            canonicalJson(originalCurrent()) === canonicalJson(original) &&
            live.current.consumed,
        },
        signal,
      );
      if (!frameCurrent(f) || signal.aborted) return;
      preparedFrame.current = f;
      focusIntent.current={frame:f,target:"publish",trigger};
      setPrepared(value);
      setNotice("prepared");
    });
  const publish = () =>
    run(async (f, signal) => {
      const p = preparedRef.current,
        o = originalCurrent();
      if (
        publicationStarted.current ||
        !p ||
        !preparedCurrent(p) ||
        !o ||
        !f.host.readProjectPlan
      )
        return proposalUnavailable();
      // Fresh current Plan/base before the separate source-write gesture. Never rebase.
      const read = await f.host.readProjectPlan({
        work_ref: f.workRef,
        signal,
      });
      if (!frameCurrent(f) || signal.aborted) return proposalUnavailable();
      const same = planProposalOriginalFromRead({
        read,
        workRef: f.workRef,
        planningOperationKey: o.operation_key,
        requestId: o.proposal_request.request_id,
        jobId: o.proposal_request.selection.job_id,
        attemptId: o.proposal_request.selection.attempt_id,
        resultDigest: o.proposal_request.result_digest,
      });
      if (canonicalJson(same) !== canonicalJson(o))
        return proposalUnavailable();
      basis.current = same;
      await qualify(f, signal);
      const pointer = proposalPointer(p);
      publicationStarted.current = true;
      const next = await machine.current!.begin({
        kind: pointer.kind,
        targetKey: pointer.targetKey,
        payload: { action: ACTION, original: o },
      });
      if (!frameCurrent(f) || signal.aborted) return;
      setState(next);
      setNotice(next.status === "unknown" ? "unknown" : null);
    });
  const check = (reconcile: boolean) =>
    run(async (f, signal) => {
      const o = originalCurrent();
      if (!o) return proposalUnavailable();
      await qualify(f, signal);
      const next = await machine.current!.recover(
        reconcile ? { reconcileSource: true } : undefined,
      );
      if (!frameCurrent(f) || signal.aborted) return;
      setState(next);
      if (next.status === "idle" && next.reason === "RECOVER_NO_POINTER") {
        const lookup = {
          schema: "mastermind.workspace_source_operation_lookup.v1" as const,
          action: ACTION,
          request_id: o.proposal_request.request_id,
          work_ref: o.work_ref,
        };
        const raw = reconcile
          ? await f.source.reconcileSourceOperation(lookup, signal)
          : await f.source.readSourceOperation(lookup, signal);
        if (!frameCurrent(f) || signal.aborted) return;
        observeStatus(qualifyPlanProposalStatus(raw,o,identity.current!.scope),f);
      }
    });
  let current = false;
  try {
    capture();
    current = true;
  } catch {
    /* actual owner absent */
  }
  const o = props.original,
    published =
      !!o &&
      statusOriginal.current === canonicalJson(o) &&
      current &&
      !!statusFrame.current &&
      frameCurrent(statusFrame.current) &&
      status?.disposition === "accepted" &&
      status.receipt?.kind === "SOURCE_OBSERVED";
  const preparedVisible = !!prepared && preparedCurrent(prepared);
  const unknown =
    state.status === "unknown" ||
    state.status === "submitting" ||
    state.status === "checking";
  const eligible =
    current &&
    props.consumed &&
    props.hasDeclaration &&
    props.result?.result != null &&
    props.result.selection.work_ref === props.workRef &&
    props.result.selection.attempt_id !== null;
  const compareFrame = useRef<Frame | null>(null);
  const showPlan = () => {
    try {
      compareFrame.current = capture();
      setShowCompare(true);
    } catch {
      setNotice("unavailable");
    }
  };
  const compareCurrent = useRef(
    () => !!compareFrame.current && frameCurrent(compareFrame.current),
  ).current;
  const canCompare =
    current && typeof props.host?.readProjectPlan === "function";
  useLayoutEffect(()=>{
    const intent=focusIntent.current;if(!intent)return;
    if(!frameCurrent(intent.frame)){focusIntent.current=null;return;}
    if(busy)return;
    focusIntent.current=null;
    const button=intent.target==="publish"?publishButton.current:compareButton.current;
    if(button?.isConnected&&!button.disabled&&
      (document.activeElement===document.body||document.activeElement===intent.trigger))button.focus();
  },[prepared,busy,showCompare,props.original,props.host]);

  return (
    <section aria-label={say("Planning proposal", "规划提案")} aria-busy={busy}>
      <h3>{say("Planning proposal", "规划提案")}</h3>
      <p>
        {published
          ? say(
              "Proposal published. Compare it with the current plan; adoption is a separate step.",
              "提案已发布。请与当前计划比较；采纳是独立步骤。",
            )
          : say(
              "Keep the original planning result, then prepare and explicitly publish its proposal.",
              "保留原始规划结果后，准备并明确发布提案。",
            )}
      </p>
      {!props.consumed && (
        <p>
          {say(
            "The original planning result must be kept before proposal preparation.",
            "准备提案前，必须先保留原始规划结果。",
          )}
        </p>
      )}
      {notice === "unavailable" && (
        <p role="status">
          {say(
            "The proposal operation is unavailable. Check the original request; no replacement was created.",
            "提案操作不可用。请查询原始请求；未创建替代请求。",
          )}
        </p>
      )}
      {notice === "unknown" && (
        <p role="status">
          {say(
            "Publication outcome is unknown. Check this original request instead of sending it again.",
            "发布结果未知。请查询此原始请求，不要重新发送。",
          )}
        </p>
      )}
      {!published && !preparedVisible && (
        <p>
          <button
            className="primary"
            disabled={busy || !eligible || unknown}
            onClick={event=>prepare(event.currentTarget)}
          >
            {o
              ? say("Restore original proposal preview", "恢复原始提案预览")
              : say("Prepare planning proposal", "准备规划提案")}
          </button>
        </p>
      )}
      {current &&
        preparedVisible &&
        prepared &&
        o &&
        canonicalJson(prepared.original) === canonicalJson(o) &&
        !published && (
          <>
            <p>
              {say(
                "Proposal preview ready. Publishing records this proposal; it does not adopt it or start work.",
                "提案预览已就绪。发布会记录提案，不会采纳提案或开始工作。",
              )}
            </p>
            <p>{prepared.preview.proposal_id}</p>
            <button
              className="primary"
              disabled={
                busy || unknown || !eligible || publicationStarted.current
              }
              ref={publishButton} onClick={publish}
            >
              {say("Publish planning proposal", "发布规划提案")}
            </button>
          </>
        )}
      {o && (
        <p className="form-actions">
          <button
            className={unknown ? "primary" : undefined}
            disabled={busy || !current}
            onClick={() => check(false)}
          >
            {say("Check original proposal", "查询原始提案")}
          </button>{" "}
          <button disabled={busy || !current} onClick={() => check(true)}>
            {say("Check proposal publication", "查询提案发布状态")}
          </button>
        </p>
      )}
      {o && (
        <p>
          <button
            className={published ? "primary" : undefined}
            disabled={busy || !canCompare}
            ref={compareButton} onClick={showPlan}
          >
            {say("View current Plan and Compare", "查看当前计划并比较")}
          </button>
        </p>
      )}
      {showCompare && canCompare && (
        <div>
          <button onClick={event=>{
            const frame=compareFrame.current;if(!frame||!frameCurrent(frame))return;
            focusIntent.current={frame,target:"compare",trigger:event.currentTarget};setShowCompare(false);
          }}>
            {say("Back to proposal", "返回提案")}
          </button>
          <ProjectPlanPanel
            key={o?.proposal_request.request_id ?? props.workRef}
            selection={{ work_ref: props.workRef }}
            read={props.host?.readProjectPlan}
            sourceGeneration={props.host?.invalidationGeneration}
            canRead={compareCurrent}
            initialProposalId={
              o ? `PLAN-${o.proposal_request.request_id.slice(-40)}` : null
            }
            locale={props.locale}
          />
        </div>
      )}
      {o && (
        <details className="reason-details">
          <summary>{say("Proposal source details", "提案来源详情")}</summary>
          <dl>
            <dt>{say("Original request", "原始请求")}</dt>
            <dd>
              <code>{o.proposal_request.request_id}</code>
            </dd>
            <dt>{say("Original planning request", "原始规划请求")}</dt>
            <dd>
              <code>{o.operation_key}</code>
            </dd>
            <dt>{say("Result digest", "结果摘要")}</dt>
            <dd>
              <code>{o.proposal_request.result_digest}</code>
            </dd>
            <dt>{say("Original base", "原始基线")}</dt>
            <dd>
              <code>{o.proposal_request.expected_commit}</code>
            </dd>
          </dl>
        </details>
      )}
    </section>
  );
}
