import { useLayoutEffect, useRef, useState, type ReactNode } from "react";
import type { OperationController, OperationPointer, OperationState, OwnerContext } from "../orchestration/operation-controller";
import { decodePlanAdoptionRequest, type PlanAdoptionRequest } from "./plan-adoption-request";
import { validProjectPlanSelection } from "./project-plan";
import "./plan-adoption-review.css";

/** A real owner-prepared preview; shape validation and UI presence grant nothing. */
export interface PlanAdoptionPrepared {
  readonly request: PlanAdoptionRequest;
  readonly preview: ReactNode;
  readonly isCurrent: () => boolean;
}
export interface PlanAdoptionBinding {
  /** This port must be scoped to ADOPT_PLAN and this selected work_ref. */
  readonly controller: OperationController;
  readonly context: () => OwnerContext | null;
  readonly canAdopt: () => boolean;
  readonly canInspect: () => boolean;
}
export interface PlanAdoptionReviewProps {
  /** Selection exists independently of prepared payload, including after reopen. */
  readonly workRef: string;
  readonly prepared?: PlanAdoptionPrepared;
  readonly binding?: PlanAdoptionBinding;
  readonly locale?: "en" | "zh-CN";
  /** Workflow opt-in: restore only through default read-only controller recovery. */
  readonly recoverOnMount?: boolean;
  /** An explicit enclosing Review gesture already prepared this exact input. */
  readonly openPrepared?: boolean;
}
interface Live {
  workRef: string | null;
  context: OwnerContext | null;
  controller: OperationController | null;
  request: PlanAdoptionRequest | null;
  identity: string | null;
  inspect: boolean;
  adopt: boolean;
  current: boolean;
}
interface Review {
  workRef: string;
  context: OwnerContext;
  controller: OperationController;
  request: PlanAdoptionRequest;
  identity: string;
}
type Mode = "adopt" | "check" | "advance" | "read";
interface View {
  workRef: string;
  context: OwnerContext;
  controller: OperationController;
  state: OperationState | null;
  pointer: OperationPointer | null;
  identity: string | null;
  associated: boolean;
  busy: boolean;
  uncertain: boolean;
  mode: Mode;
}
const yes = (read?: () => boolean) => { try { return read?.() === true; } catch { return false; } };
function capture(props: PlanAdoptionReviewProps): Live {
  const workRef = validProjectPlanSelection({ work_ref: props.workRef }) ? props.workRef : null;
  let context: OwnerContext | null = null;
  try {
    const value = props.binding?.context();
    if (value && typeof value.principalScope === "string" && value.principalScope.length > 0 &&
        typeof value.generation === "string" && value.generation.length > 0) {
      context = { principalScope: value.principalScope, generation: value.generation };
    }
  } catch { /* closed unavailable */ }
  let request: PlanAdoptionRequest | null = null;
  try { if (workRef && props.prepared) request = decodePlanAdoptionRequest(props.prepared.request, workRef); }
  catch { /* no invalid/foreign prepared content or errors are published */ }
  return { workRef, context, controller: props.binding?.controller ?? null, request,
    identity: request ? JSON.stringify(request) : null,
    inspect: yes(props.binding?.canInspect), adopt: yes(props.binding?.canAdopt),
    current: request !== null && yes(props.prepared?.isCurrent) };
}
function sameOwner(snapshot: { workRef: string; context: OwnerContext; controller: OperationController }, live: Live) {
  return live.context !== null && snapshot.workRef === live.workRef && snapshot.controller === live.controller &&
    snapshot.context.principalScope === live.context.principalScope && snapshot.context.generation === live.context.generation;
}
function owns(pointer: OperationPointer | null, workRef: string | null): boolean {
  return pointer !== null && pointer.kind === "project_adopt" && pointer.targetKey === workRef &&
    /^mmos-project-adopt-[0-9a-f]{40}$/.exec(pointer.operationKey)?.[0] === pointer.operationKey;
}
function pending(view: View): boolean {
  return view.busy || view.uncertain || view.state?.status === "unknown" ||
    view.state?.status === "checking" || view.state?.status === "submitting";
}
function ready(view: View | null): boolean {
  return view !== null && !view.busy && !view.uncertain && view.state?.status === "unknown" && view.associated &&
    typeof view.state.advance?.phase_receipt_digest === "string" &&
    view.state.reason === "READY_FOR_ADVANCE" &&
    /^[0-9a-f]{64}$/.exec(view.state.advance?.phase_receipt_digest ?? "")?.[0] === view.state.advance?.phase_receipt_digest;
}

/** Local review and explicit calls to the incumbent controller only.
 * No mount publication, timer, cancellation, key minting, getState, store write or
 * baseline mutation. The source owner alone proves grant/publication/adoption.
 */
export function PlanAdoptionReview(props: PlanAdoptionReviewProps) {
  const zh = props.locale === "zh-CN";
  const t = (en: string, cn: string) => zh ? cn : en;
  const latest = useRef(props); latest.current = props;
  const mounted = useRef(true);
  const latch = useRef(false);
  const recovered = useRef<{controller:OperationController;workRef:string;scope:string;generation:string}|null>(null);
  const opened = useRef<{controller:OperationController;identity:string;generation:string}|null>(null);
  const [review, setReview] = useState<Review | null>(null);
  const [invalidated, setInvalidated] = useState(false);
  const [view, setView] = useState<View | null>(null);
  const live = capture(props);
  const reviewLive = review !== null && sameOwner(review, live) && live.current && live.inspect && live.adopt &&
    review.identity === live.identity;
  const visible = view !== null && sameOwner(view, live) && live.inspect ? view : null;
  const held = visible !== null && pending(visible);
  const terminal = visible !== null && visible.identity === live.identity &&
    (visible.state?.status === "accepted" || visible.state?.status === "refused");
  useLayoutEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);
  useLayoutEffect(() => {
    // Once invalidated, A -> B -> A cannot silently reopen an old review.
    if (review !== null && !reviewLive) { setReview(null); setInvalidated(true); }
  }, [review, reviewLive]);
  const open = () => {
    const now = capture(latest.current);
    if (latch.current || !now.workRef || !now.context || !now.controller || !now.request ||
        !now.identity || !now.current || !now.inspect || !now.adopt) return;
    setReview({ workRef: now.workRef, context: now.context, controller: now.controller,
      request: now.request, identity: now.identity });
    setInvalidated(false);
  };
  const close = () => { setReview(null); setInvalidated(false); };
  const run = (mode: Mode) => {
    const now = capture(latest.current);
    if (latch.current || !now.workRef || !now.context || !now.controller || !now.inspect) return;
    const prior = view !== null && sameOwner(view, now) ? view : null;
    if (mode === "adopt" && (review === null || !sameOwner(review, now) || review.identity !== now.identity ||
        !now.current || !now.adopt || (prior !== null && (pending(prior) ||
          ((prior.state?.status === "accepted" || prior.state?.status === "refused") && prior.identity === now.identity))))) return;
    if (mode === "advance" && (!now.adopt || !ready(prior))) return;
    latch.current = true;
    const request = mode === "adopt" ? review!.request : null;
    const pointer: OperationPointer | null = request
      ? { kind: "project_adopt", targetKey: request.work_ref, operationKey: request.request_id }
      : prior?.pointer ?? null;
    const started: View = { workRef: now.workRef, context: now.context, controller: now.controller,
      state: null, pointer, identity: request ? review!.identity : prior?.identity ?? null,
      associated: owns(pointer, now.workRef), busy: true, uncertain: prior?.uncertain ?? false, mode };
    setView(started);
    void (async () => {
      let state: OperationState | null = null;
      let failed = false;
      try {
        state = mode === "adopt" ? await started.controller.begin({ kind: "project_adopt", targetKey: request!.work_ref,
            payload: { action: "ADOPT_PLAN", request } })
          : mode === "advance" ? await started.controller.advance()
          : mode === "check" ? await started.controller.recover({reconcileSource:true})
          : await started.controller.recover();
      } catch { failed = true; /* an exception does not prove no dispatch */ }
      finally { latch.current = false; }
      const after = capture(latest.current);
      if (!mounted.current || !sameOwner(started, after) || !after.inspect) return;
      const actual = state && "pointer" in state ? state.pointer : null;
      const associated = actual !== null ? owns(actual, after.workRef) : started.associated;
      const lostHint = state?.status === "idle" && prior !== null && pending(prior);
      // A missing local hint cannot turn a previously unknown effect into a
      // claim of non-dispatch or enable a replacement submission.
      setView(lostHint ? { ...prior, busy: false, uncertain: true, mode }
        : { ...started, state, pointer: actual ?? started.pointer, associated, busy: false,
            uncertain: failed, mode });
    })();
  };
  useLayoutEffect(()=>{
    if(!props.recoverOnMount||!live.controller||!live.context||!live.workRef||!live.inspect||latch.current)return;
    const previous=recovered.current;
    if(previous?.controller===live.controller&&previous.workRef===live.workRef&&previous.scope===live.context.principalScope&&previous.generation===live.context.generation)return;
    recovered.current={controller:live.controller,workRef:live.workRef,scope:live.context.principalScope,generation:live.context.generation};
    run("read");
  },[props.recoverOnMount,live.controller,live.workRef,live.context?.principalScope,live.context?.generation,live.inspect]);
  useLayoutEffect(()=>{
    if(!props.openPrepared||!live.controller||!live.context||!live.identity||!live.current||!live.inspect||!live.adopt||held||latch.current)return;
    const prior=opened.current;
    if(prior?.controller===live.controller&&prior.identity===live.identity&&prior.generation===live.context.generation)return;
    opened.current={controller:live.controller,identity:live.identity,generation:live.context.generation};open();
  },[props.openPrepared,live.controller,live.context?.generation,live.identity,live.current,live.inspect,live.adopt,held]);
  const sourceFacts = props.prepared && reviewLive && live.request ? live.request : null;
  let status: string | null = null;
  if (visible) {
    if (visible.busy) status = visible.mode === "adopt" ? t("Submitting this adoption… the outcome is not confirmed yet.", "正在提交此采纳…结果尚未确认。")
      : visible.mode === "advance" ? t("Continuing the original adoption…", "正在继续原始采纳操作…")
      : t("Checking the original adoption operation…", "正在检查原始采纳操作…");
    else if (visible.state?.status === "checking") status = t("An original adoption is pending. Check the original operation before submitting another proposal.", "一个原始采纳仍待核实。提交另一提案前，请检查原始操作。");
    else if (ready(visible)) status = t("The proposed plan is saved. Adoption is not confirmed yet. Continue the original adoption when ready.",
      "提议的计划已保存，采纳尚未确认。准备好后可继续原采纳操作。");
    else if (!visible.associated && pending(visible) && !visible.uncertain) status = t(
      "An operation that is not this plan's adoption is still being resolved. Its details stay private here.",
      "一个不属于此计划采纳的操作仍待核实，此处不显示其详情。");
    else if (visible.uncertain || visible.state?.status === "unknown" || visible.state?.status === "submitting") status = t(
      "The original adoption outcome is not known yet. Use “Check original operation” before doing anything else.",
      "此采纳的结果尚不确定。请先使用“检查原始操作”。");
    else if (visible.state?.status === "accepted") status = visible.associated ? t(
      "Publication of the original adoption is confirmed. Refresh the plan to read its recorded adoption decision.",
      "此采纳的发布已确认。请刷新计划以读取其已记录的采纳决定。") : t(
      "An original operation has settled. This view has no matching plan-adoption receipt; refresh the plan to read its current decision.",
      "一个原始操作已结束。此视图没有匹配的计划采纳凭据；请刷新计划以读取当前决定。");
    else if (visible.state?.status === "refused") status = visible.associated
      ? t("This adoption request was refused. Refresh the plan to check its current decision.", "此采纳请求已被拒绝。请刷新计划，查看当前决定。")
      : t("An original operation was refused. It is not attributed to this plan.", "一个原始操作已被拒绝；不将其归属于此计划。");
    else if(visible.state?.status==='idle'&&visible.state.reason!=='RECOVER_NO_POINTER') status=t(
      "Operation recovery is unavailable on this device. Check again when local storage is available.",
      "此设备暂时无法恢复操作。本地存储可用后请再次检查。");
    else status = t("No pending adoption was found on this device. Refresh the plan to check its recorded decision.",
      "此设备未找到待处理的采纳操作。请刷新计划，查看已记录的决定。");
  }
  const unavailable = !live.controller || !live.context || !live.workRef
    ? t("Plan adoption is unavailable in this view. The plan and its sources remain separate.", "此视图暂无法采纳计划；计划及其来源仍可单独查看。")
    : !live.request ? props.openPrepared ? null : t("No prepared comparison was supplied. Choose a recorded proposal to review adoption; the original operation can still be checked.",
      "未提供已准备的对比。请选择已记录的提案以审查采纳；仍可检查原始操作。")
    : !live.current ? t("A current plan and proposal are required before reviewing adoption.", "审查采纳前，需要获取当前计划和提案。")
    : !live.adopt || !live.inspect ? t("Adoption is not currently permitted for this session.", "此会话目前不允许采纳计划。") : null;
  return <section className="mm-plan-adoption" lang={props.locale ?? "en"} aria-label={t("Plan adoption review", "计划采纳审查")}>
    <div className="mm-plan-adoption__heading"><div><h2>{t("Plan adoption", "计划采纳")}</h2>
      <p className="mm-plan-adoption__subtitle">{t("Review the exact proposal and baseline before adopting. Closing the review does not cancel an operation.",
        "采纳前请审查准确的提案和基线。关闭审查不会取消操作。")}</p></div>
      <div className="mm-plan-adoption__heading-actions">
        {reviewLive ? <button type="button" className="mm-plan-adoption__action" onClick={close}>{t("Close review", "关闭审查")}</button>
          : (!props.openPrepared||live.request!==null)&&<button type="button" className="mm-plan-adoption__action" onClick={open}
              disabled={!live.controller || !live.context || !live.current || !live.inspect || !live.adopt}>{t("Review plan", "审查计划")}</button>}
        <button type="button" className="mm-plan-adoption__action" onClick={() => run("check")}
          disabled={!live.controller || !live.context || !live.workRef || !live.inspect || visible?.busy === true}>{t("Check original operation", "检查原始操作")}</button>
        {ready(visible) && <button type="button" className="mm-plan-adoption__action" onClick={() => run("advance")}
          disabled={!live.adopt || !live.inspect || visible?.busy === true}>{t("Continue original adoption", "继续原始采纳")}</button>}
      </div>
    </div>
    {invalidated && <p className="mm-plan-adoption__status" role="status">{t("The review no longer matches the current request, source or session. Reopen it to continue.",
      "审查已不再匹配当前请求、来源或会话。请重新打开后继续。")}</p>}
    {sourceFacts && <div className="mm-plan-adoption__preview">
      <h3 className="mm-plan-adoption__preview-title">{t("Prepared comparison", "已准备的对比")}</h3>
      <p className="mm-plan-adoption__note">{t("This preview does not adopt the plan. The recorded current decision is shown separately.", "此预览不会采纳计划。已记录的当前决定单独显示。")}</p>
      <div className="mm-plan-adoption__preview-slot">{props.prepared!.preview}</div>
      <details className="mm-plan-adoption__ids"><summary>{t("Planning sources", "规划来源")}</summary>
        <dl className="mm-plan-adoption__facts">
          <div><dt>{t("Plan target", "计划目标")}</dt><dd><code>{sourceFacts.work_ref}</code></dd></div>
          <div><dt>{t("Current adoption decision", "当前采纳决定")}</dt><dd>{sourceFacts.expected_adoption ?? t("No adopted baseline recorded", "未记录已采纳基线")}</dd></div>
          <div><dt>{t("Proposal source", "提案来源")}</dt><dd>{sourceFacts.proposal_source.repository} · {sourceFacts.proposal_source.path}</dd></div>
          <div><dt>{t("Baseline source", "基线来源")}</dt><dd>{sourceFacts.base_source.repository} · {sourceFacts.base_source.path}</dd></div>
        </dl>
        <dl className="mm-plan-adoption__id-list">
          {[[t("Prepared request ID", "已准备的请求 ID"), sourceFacts.request_id], [t("Expected commit", "预期提交"), sourceFacts.expected_commit],
            [t("Proposal commit", "提案提交"), sourceFacts.proposal_source.commit], [t("Proposal content SHA-256", "提案内容 SHA-256"), sourceFacts.proposal_source.content_sha256],
            [t("Baseline commit", "基线提交"), sourceFacts.base_source.commit], [t("Baseline content SHA-256", "基线内容 SHA-256"), sourceFacts.base_source.content_sha256],
            [t("Candidate SHA-256", "候选内容 SHA-256"), sourceFacts.candidate_sha256]].map(([label, value]) => <div key={label}><dt>{label}</dt><dd><code>{value}</code></dd></div>)}
        </dl>
      </details>
      <div className="mm-plan-adoption__actions"><button type="button" className="mm-plan-adoption__action mm-plan-adoption__adopt"
        disabled={!reviewLive || held || terminal} onClick={() => run("adopt")}>{t("Adopt this plan", "采纳此计划")}</button></div>
    </div>}
    {unavailable && <p className="mm-plan-adoption__status" role="status">{unavailable}</p>}
    {status && <p className="mm-plan-adoption__status" role="status">{status}</p>}
  </section>;
}
