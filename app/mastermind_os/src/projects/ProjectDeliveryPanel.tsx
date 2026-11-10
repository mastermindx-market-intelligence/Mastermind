import { DelegatedTaskCard } from "../team/DelegatedTaskCard";
import { ResultReturnCard } from "../team/ResultReturnCard";
import type { DelegatedTask } from "../team/delegated-task";
import type {
  ExecutionReturnDeliveryReceipt,
  ExecutionReturnRecord,
} from "../hermes-native/execution-return-contract";
import { ProjectRouteReview } from "./ProjectRouteReview";
import { ProjectRunOutcome } from "./ProjectRunOutcome";
import type {
  DelegatedRouteReview,
  DelegatedRunOutcome,
} from "./delivery-route-run";
import "./ProjectDeliveryPanel.css";

/** TD03 — project work and delivery. The objective and task states come from
 *  real sources; while a source is missing the panel says so instead of
 *  inventing progress. Delivery returns here for review (HC08): the return
 *  card consumes Director F's authoritative execution_return/v1 contract and
 *  is null-fed until a producer exists. */
export interface DeliveryTrailStep {
  key: string;
  step: string;
  label: string;
  state: "done" | "active" | "pending" | "unknown";
}

const STRINGS = {
  en: {
    heading: "Team delivery",
    outcomeEyebrow: "NEXT OUTCOME",
    outcomeUnavailable:
      "The next outcome has not been read from the project source.",
    routeHeading: "Review the route",
    codingHeading: "Coding now",
    runHeading: "Run and return",
    noTask: "No delegated coding task is projected for this project yet.",
    returnHeading: "Result return",
    trailHeading: "Delivery trail",
    trailNote: "Code results return to this project for review and release.",
    trailUnknown: "Not projected",
    openProject: "Open plan →",
    ownerNote: (owner: string) => `${owner} owns delivery`,
  },
  "zh-CN": {
    heading: "团队交付",
    outcomeEyebrow: "下一个成果",
    outcomeUnavailable: "尚未从项目来源读取下一个成果。",
    routeHeading: "审阅路由",
    codingHeading: "正在进行",
    runHeading: "运行与返回",
    noTask: "尚未为该项目投影受派的编码任务。",
    returnHeading: "结果返回",
    trailHeading: "交付轨迹",
    trailNote: "编码结果返回此项目，供审阅与发布。",
    trailUnknown: "未投影",
    openProject: "打开计划 →",
    ownerNote: (owner: string) => `${owner} 负责交付`,
  },
};

export function ProjectDeliveryPanel({
  locale = "en",
  objective,
  owner,
  route = null,
  delegatedTask,
  run = null,
  executionReturn,
  deliveryReceipt = null,
  trail,
  onOpenCode,
  onOpenPlan,
  onBackFromRoute,
}: {
  locale?: "en" | "zh-CN";
  /** Objective text from the existing project plan source; null = not read. */
  objective: string | null;
  owner: string | null;
  /** TD06 — the route-review step before dispatch (admission binding facts +
   *  proposed placement); null = nothing projected yet, step renders honest. */
  route?: DelegatedRouteReview | null;
  delegatedTask: DelegatedTask | null;
  /** TD07 — the run/result step after dispatch (execution return, delivery
   *  receipt, retained-activity trail); null = nothing projected yet. */
  run?: DelegatedRunOutcome | null;
  /** Director F's parsed mastermind.execution_return/v1 record for this
   *  project's latest settled attempt; null today (no producer wired) — the
   *  card renders the honest no-return state, never fixture data. */
  executionReturn: ExecutionReturnRecord | null;
  /** Optional parsed delivery receipt for that same return. */
  deliveryReceipt?: ExecutionReturnDeliveryReceipt | null;
  trail: readonly DeliveryTrailStep[];
  onOpenCode?: () => void;
  onOpenPlan?: () => void;
  /** Optional back action for the route-review footer. */
  onBackFromRoute?: () => void;
}) {
  const t = STRINGS[locale];
  return (
    <div className="mm-delivery">
      <div className="card mm-delivery-outcome">
        <p className="mm-eyebrow">{t.outcomeEyebrow}</p>
        {objective !== null ? (
          <h3 className="mm-delivery-objective">{objective}</h3>
        ) : (
          <p className="muted">{t.outcomeUnavailable}</p>
        )}
        {owner ? <p className="muted">{t.ownerNote(owner)}</p> : null}
        {onOpenPlan ? (
          <button
            type="button"
            className="mm-delivery-open-plan"
            onClick={onOpenPlan}
          >
            {t.openProject}
          </button>
        ) : null}
      </div>
      <section
        className="mm-delivery-route-review"
        aria-labelledby="mm-delivery-route-heading"
      >
        <h3 id="mm-delivery-route-heading" tabIndex={-1}>
          {t.routeHeading}
        </h3>
        <ProjectRouteReview
          route={route}
          locale={locale}
          onBack={onBackFromRoute}
        />
      </section>
      <section className="mm-delivery-coding">
        <h3>{t.codingHeading}</h3>
        {delegatedTask !== null ? (
          <DelegatedTaskCard
            task={delegatedTask}
            locale={locale}
            onOpenCode={onOpenCode}
          />
        ) : (
          <p className="muted">{t.noTask}</p>
        )}
      </section>
      <section
        className="mm-delivery-run"
        aria-labelledby="mm-delivery-run-heading"
      >
        <h3 id="mm-delivery-run-heading" tabIndex={-1}>
          {t.runHeading}
        </h3>
        <ProjectRunOutcome
          run={run}
          locale={locale}
          onOpenCode={onOpenCode}
        />
      </section>
      <section className="mm-delivery-return">
        <h3>{t.returnHeading}</h3>
        <ResultReturnCard
          executionReturn={executionReturn}
          deliveryReceipt={deliveryReceipt}
          locale={locale}
        />
      </section>
      <section className="mm-delivery-trail-section">
        <h3>{t.trailHeading}</h3>
        <ul className="mm-delivery-trail">
          {trail.map((step) => (
            <li key={step.key}>
              <span className="mm-trail-step">{step.step}</span>
              <span
                className="mm-trail-label"
                data-state={
                  step.state === "pending" || step.state === "unknown"
                    ? "pending"
                    : "done"
                }
              >
                {step.state === "unknown" ? t.trailUnknown : step.label}
              </span>
            </li>
          ))}
        </ul>
        <p className="muted">{t.trailNote}</p>
      </section>
    </div>
  );
}
