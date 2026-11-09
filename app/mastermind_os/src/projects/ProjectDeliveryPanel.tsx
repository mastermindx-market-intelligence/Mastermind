import { DelegatedTaskCard } from "../team/DelegatedTaskCard";
import type { DelegatedTask } from "../team/delegated-task";
import "./ProjectDeliveryPanel.css";

/** TD03 — project work and delivery. The objective and task states come from
 *  real sources; while a source is missing the panel says so instead of
 *  inventing progress. Delivery returns here for review (HC08). */
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
    outcomeUnavailable: "The next outcome has not been read from the project source.",
    codingHeading: "Coding now",
    noTask: "No delegated coding task is projected for this project yet.",
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
    codingHeading: "正在进行",
    noTask: "尚未为该项目投影受派的编码任务。",
    trailHeading: "交付轨迹",
    trailNote: "编码结果返回此项目，供审阅与发布。",
    trailUnknown: "未投影",
    openProject: "打开计划 →",
    ownerNote: (owner: string) => `${owner} 负责交付`,
  },
};

export function ProjectDeliveryPanel({ locale = "en", objective, owner, delegatedTask, trail, onOpenCode, onOpenPlan }: {
  locale?: "en" | "zh-CN";
  /** Objective text from the existing project plan source; null = not read. */
  objective: string | null;
  owner: string | null;
  delegatedTask: DelegatedTask | null;
  trail: readonly DeliveryTrailStep[];
  onOpenCode?: () => void;
  onOpenPlan?: () => void;
}) {
  const t = STRINGS[locale];
  return (
    <div className="mm-delivery">
      <div className="card mm-delivery-outcome">
        <p className="mm-eyebrow">{t.outcomeEyebrow}</p>
        {objective !== null
          ? <h3 className="mm-delivery-objective">{objective}</h3>
          : <p className="muted">{t.outcomeUnavailable}</p>}
        {owner ? <p className="muted">{t.ownerNote(owner)}</p> : null}
        {onOpenPlan ? <button type="button" className="mm-delivery-open-plan" onClick={onOpenPlan}>{t.openProject}</button> : null}
      </div>
      <section className="mm-delivery-coding">
        <h3>{t.codingHeading}</h3>
        {delegatedTask !== null
          ? <DelegatedTaskCard task={delegatedTask} locale={locale} onOpenCode={onOpenCode} />
          : <p className="muted">{t.noTask}</p>}
      </section>
      <section className="mm-delivery-trail-section">
        <h3>{t.trailHeading}</h3>
        <ul className="mm-delivery-trail">
          {trail.map(step => (
            <li key={step.key}>
              <span className="mm-trail-step">{step.step}</span>
              <span className="mm-trail-label" data-state={step.state === "pending" || step.state === "unknown" ? "pending" : "done"}>
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
