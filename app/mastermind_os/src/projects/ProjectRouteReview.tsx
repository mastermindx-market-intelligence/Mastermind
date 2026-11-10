import type { DelegatedRouteReview } from "./delivery-route-run";
import "./project-route-run.css";

/** TD06 — "Route · Review execution" (node 117C-0): the route-review step
 *  BEFORE dispatch. Preview-only by construction: this surface can confirm
 *  what is proposed, but submission needs an admitted coding handoff on the
 *  Executive path, so the submit action stays disabled with its visible
 *  reason while authority is preview-only (same vocabulary as
 *  DelegatedTaskCard's dispatch reason).
 *
 *  Honesty rules: every fact row renders either a value its source actually
 *  projected or "Not projected" with the reason naming the missing source.
 *  The work-request and workspace rows are not projected by any source today
 *  (the admission contract has no requester block and no workspace facts);
 *  null placement slots mean admission has not proposed a route yet. Nothing
 *  here fabricates people, projects, hosts, runtimes or models. */

interface RouteStrings {
  heading: string;
  previewChip: string;
  intro: string;
  noRoute: string;
  requestColumn: string;
  placementColumn: string;
  workCard: string;
  workRow: string;
  ownerRow: string;
  projectRow: string;
  returnRow: string;
  notProjected: string;
  workNote: string;
  workspaceCard: string;
  workspaceNote: string;
  bindingHeading: string;
  noBinding: string;
  rootRunRef: string;
  immediateParent: string;
  logicalChildKey: string;
  requestDigest: string;
  effectiveComplexity: string;
  taskKind: string;
  runtimeKind: string;
  operationKey: string;
  unset: string;
  routeCard: string;
  routeTitleRow: string;
  hostRow: string;
  runtimeRow: string;
  engineRow: string;
  modelRow: string;
  poolRow: string;
  placementNote: string;
  viewRouting: string;
  readinessCard: string;
  readinessUnknown: string;
  readinessNote: string;
  readinessReason: (label: string) => string;
  submitHeading: string;
  submitNote: string;
  followNote: string;
  submit: string;
  submitPreviewReason: string;
  back: string;
}

const STRINGS: Record<"en" | "zh-CN", RouteStrings> = {
  en: {
    heading: "Review coding route",
    previewChip: "Preview only",
    intro: "Confirm the work and proposed route. Nothing has started.",
    noRoute: "No coding route is projected for this project yet.",
    requestColumn: "Request details",
    placementColumn: "Placement details",
    workCard: "Work request",
    workRow: "The work",
    ownerRow: "Owner",
    projectRow: "Project",
    returnRow: "Return",
    notProjected: "Not projected",
    workNote:
      "The work request and its requester facts arrive with the admitted handoff; no requester projection is wired yet.",
    workspaceCard: "Workspace",
    workspaceNote:
      "The admission binding does not project workspace or custody facts yet.",
    bindingHeading: "Admission binding",
    noBinding: "No admission binding is projected yet.",
    rootRunRef: "Root run",
    immediateParent: "Immediate parent",
    logicalChildKey: "Logical child",
    requestDigest: "Request digest",
    effectiveComplexity: "Effective complexity",
    taskKind: "Task kind",
    runtimeKind: "Runtime",
    operationKey: "Operation key",
    unset: "Not set",
    routeCard: "Proposed route",
    routeTitleRow: "Route title",
    hostRow: "Host",
    runtimeRow: "Runtime",
    engineRow: "Engine",
    modelRow: "Model",
    poolRow: "Proposed pool selection",
    placementNote: "Admission has not proposed a route yet.",
    viewRouting: "View routing & limits",
    readinessCard: "Readiness",
    readinessUnknown: "Unknown",
    readinessNote:
      "No readiness row shows green until its own source is observed.",
    readinessReason: (label) => `${label} is not projected on this surface.`,
    submitHeading: "Submit request",
    submitNote: "Execution begins only after admission.",
    followNote: "Follow this work from OS launch team or the project.",
    submit: "Submit request",
    submitPreviewReason:
      "Submission needs an admitted coding handoff on the Executive path. This surface can only preview.",
    back: "Back",
  },
  "zh-CN": {
    heading: "审阅编码路由",
    previewChip: "仅预览",
    intro: "确认工作内容与提议的路由。尚未开始任何执行。",
    noRoute: "尚无为该项目投影的编码路由。",
    requestColumn: "请求详情",
    placementColumn: "放置详情",
    workCard: "工作请求",
    workRow: "工作内容",
    ownerRow: "负责人",
    projectRow: "项目",
    returnRow: "返回路径",
    notProjected: "未投影",
    workNote:
      "工作请求及其请求方事实随获受理的交接一同到来；目前尚未接入请求方投影。",
    workspaceCard: "工作区",
    workspaceNote: "受理绑定尚未投影工作区或保管事实。",
    bindingHeading: "受理绑定",
    noBinding: "尚无已投影的受理绑定。",
    rootRunRef: "根运行",
    immediateParent: "直接父级",
    logicalChildKey: "逻辑子键",
    requestDigest: "请求摘要",
    effectiveComplexity: "生效复杂度",
    taskKind: "任务类型",
    runtimeKind: "运行时",
    operationKey: "操作键",
    unset: "未设置",
    routeCard: "提议路由",
    routeTitleRow: "路由标题",
    hostRow: "主机",
    runtimeRow: "运行时",
    engineRow: "引擎",
    modelRow: "模型",
    poolRow: "提议资源池选择",
    placementNote: "受理尚未提出路由。",
    viewRouting: "查看路由与限制",
    readinessCard: "就绪状态",
    readinessUnknown: "未知",
    readinessNote: "在其各自的来源被观测到之前，任何就绪状态都不会显示为绿色。",
    readinessReason: (label) => `${label}尚未投影到此界面。`,
    submitHeading: "提交请求",
    submitNote: "仅在受理之后才会开始执行。",
    followNote: "从 OS 启动团队或该项目跟进这项工作。",
    submit: "提交请求",
    submitPreviewReason: "提交需要经由 Executive 路径受理的编码交接。此界面仅可预览。",
    back: "返回",
  },
};

/** Workspace/custody dimensions (5 rows). None is projected by the admission
 *  binding today; each renders "Not projected" with the card's reason. */
const WORKSPACE_ROWS: readonly (readonly [string, string])[] = [
  ["Workspace", "工作区"],
  ["Custody", "保管"],
  ["Isolation", "隔离"],
  ["Checkout", "检出"],
  ["Shared store", "共享存储"],
];

/** Readiness dimensions (5 rows) — always honest Unknown with a reason while
 *  unobserved; the view has no green branch for them at all. */
const READINESS_ROWS: readonly (readonly [string, string])[] = [
  ["Host quota", "主机配额"],
  ["Provider admission", "提供方受理"],
  ["Model availability", "模型可用性"],
  ["Pool capacity", "资源池容量"],
  ["Reserved review slot", "预留审阅席位"],
];

export function ProjectRouteReview({
  route,
  locale = "en",
  adapterLabel = null,
  onBack,
  onViewRouting,
}: {
  /** The admitted handoff's binding facts plus the proposed placement;
   *  null/undefined = nothing projected yet (the step still renders). */
  route: DelegatedRouteReview | null;
  locale?: "en" | "zh-CN";
  /** Optional route-family prefix for the heading (e.g. "Teamlink adapter");
   *  null = the plain step heading. Never invented by this component. */
  adapterLabel?: string | null;
  onBack?: () => void;
  onViewRouting?: () => void;
}) {
  const t = STRINGS[locale];
  const zh = locale === "zh-CN";
  const label = (row: readonly [string, string]) => (zh ? row[1] : row[0]);

  const placement: readonly (readonly [string, string | null])[] = [
    [t.routeTitleRow, null], // no route-title source exists yet
    [t.hostRow, route?.host ?? null],
    [t.runtimeRow, route?.runtime ?? null],
    [t.engineRow, route?.engine ?? null],
    [t.modelRow, route?.model ?? null],
    [t.poolRow, route?.pool ?? null],
  ];
  const placementMissing = placement.some(([, value]) => value === null);

  const bindingRows: readonly (readonly [string, string])[] = route
    ? [
        [t.rootRunRef, route.root_run_ref],
        [t.immediateParent, route.immediate_parent_run_ref],
        [t.logicalChildKey, route.logical_child_key],
        [t.requestDigest, route.request_digest],
        [t.effectiveComplexity, route.effective_complexity],
        [t.taskKind, route.task_kind || t.unset],
        [t.runtimeKind, route.runtime_kind || t.unset],
        [t.operationKey, route.operation_key || t.unset],
      ]
    : [];

  return (
    <article
      className="mm-route-review"
      aria-labelledby="mm-route-review-heading"
      data-route={route ? "projected" : "not-projected"}
    >
      <header className="mm-route-review-head">
        <h4 id="mm-route-review-heading" tabIndex={-1}>
          {adapterLabel ? `${adapterLabel} / ${t.heading}` : t.heading}
        </h4>
        <span className="mm-chip mm-chip-preview">{t.previewChip}</span>
      </header>
      <p className="mm-route-review-intro">{t.intro}</p>
      {route === null || route === undefined ? (
        <p className="mm-route-review-missing">{t.noRoute}</p>
      ) : null}
      <div className="mm-route-review-grid">
        <section className="mm-route-review-col" aria-label={t.requestColumn}>
          <h5>{t.requestColumn}</h5>
          <div className="card mm-route-card">
            <h6>{t.workCard}</h6>
            <dl className="mm-route-facts">
              {(
                [
                  [t.workRow],
                  [t.ownerRow],
                  [t.projectRow],
                  [t.returnRow],
                ] as const
              ).map(([row]) => (
                <div key={row}>
                  <dt>{row}</dt>
                  <dd data-projected="false">{t.notProjected}</dd>
                </div>
              ))}
            </dl>
            <p className="mm-route-card-note">{t.workNote}</p>
          </div>
          <div className="card mm-route-card">
            <h6>{t.workspaceCard}</h6>
            <dl className="mm-route-facts">
              {WORKSPACE_ROWS.map((row) => (
                <div key={row[0]}>
                  <dt>{label(row)}</dt>
                  <dd data-projected="false">{t.notProjected}</dd>
                </div>
              ))}
            </dl>
            <p className="mm-route-card-note">{t.workspaceNote}</p>
          </div>
          {bindingRows.length > 0 ? (
            <details className="mm-task-binding">
              <summary>{t.bindingHeading}</summary>
              <dl>
                {bindingRows.map(([row, value]) => (
                  <div key={row}>
                    <dt>{row}</dt>
                    <dd>
                      <code>{value}</code>
                    </dd>
                  </div>
                ))}
              </dl>
            </details>
          ) : (
            <p className="mm-route-card-note">{t.noBinding}</p>
          )}
        </section>
        <section
          className="mm-route-review-col"
          aria-label={t.placementColumn}
        >
          <h5>{t.placementColumn}</h5>
          <div className="card mm-route-card">
            <h6>{t.routeCard}</h6>
            <dl className="mm-route-facts">
              {placement.map(([row, value]) => (
                <div key={row}>
                  <dt>{row}</dt>
                  <dd data-projected={value === null ? "false" : "true"}>
                    {value ?? t.notProjected}
                  </dd>
                </div>
              ))}
            </dl>
            {placementMissing ? (
              <p className="mm-route-card-note">{t.placementNote}</p>
            ) : null}
            {onViewRouting ? (
              <button
                type="button"
                className="mm-route-view-routing"
                onClick={onViewRouting}
              >
                {t.viewRouting}
              </button>
            ) : null}
          </div>
          <div className="card mm-route-card">
            <h6>{t.readinessCard}</h6>
            <dl className="mm-route-facts">
              {READINESS_ROWS.map((row) => (
                <div key={row[0]}>
                  <dt>{label(row)}</dt>
                  <dd data-readiness="unknown">
                    {t.readinessUnknown}
                    <small>{t.readinessReason(label(row))}</small>
                  </dd>
                </div>
              ))}
            </dl>
            <p className="mm-route-card-note">{t.readinessNote}</p>
          </div>
        </section>
      </div>
      <footer className="mm-route-review-footer">
        <h5>{t.submitHeading}</h5>
        <p className="muted">{t.submitNote}</p>
        <p className="muted">{t.followNote}</p>
        <div className="mm-route-actions">
          {/* Preview-only surface: the submit stays disabled with its visible
              reason until an admitted handoff carries real authority. */}
          <button
            type="button"
            className="mm-route-submit"
            disabled
            aria-describedby="mm-route-submit-reason"
          >
            {t.submit}
          </button>
          {onBack ? (
            <button
              type="button"
              className="mm-route-back"
              onClick={onBack}
            >
              {t.back}
            </button>
          ) : null}
        </div>
        <p className="mm-route-submit-reason" id="mm-route-submit-reason">
          {t.submitPreviewReason}
        </p>
      </footer>
    </article>
  );
}
