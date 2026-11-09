import type { ReactNode } from "react";

/** HC08 — a result returned to its originating bot/project. Delivery is an
 *  observation, never acceptance: the two states are always shown separately. */
export interface TaskResultReturn {
  resultId: string;
  title: string;
  /** The origin that receives this result (bot, team room or project). */
  deliveredTo: string;
  /** ISO timestamp of the delivery observation, or null if not observed. */
  deliveredAt: string | null;
  /** True only when the origin's owner has actually accepted the result. */
  accepted: boolean;
  evidence: readonly { label: string; value: string }[];
}

const STRINGS = {
  en: {
    heading: "Result returned to origin",
    deliveredLabel: "Delivered",
    deliveredTo: (value: string) => `Delivered to ${value}`,
    deliveredWhen: (value: string) => `Delivery observed ${value}`,
    acceptedLabel: "Accepted",
    acceptedNo: "Not yet accepted",
    notAcceptedNote: "Delivery is not acceptance. The receiving owner still reviews this result.",
    evidenceHeading: "Evidence",
    evidenceEmpty: "No evidence attached yet.",
    openOrigin: "Open origin →",
  },
  "zh-CN": {
    heading: "结果已返回来源",
    deliveredLabel: "已交付",
    deliveredTo: (value: string) => `已交付给 ${value}`,
    deliveredWhen: (value: string) => `交付观测于 ${value}`,
    acceptedLabel: "已接受",
    acceptedNo: "尚未接受",
    notAcceptedNote: "交付不等于接受。接收方负责人仍需审阅该结果。",
    evidenceHeading: "证据",
    evidenceEmpty: "尚未附加证据。",
    openOrigin: "打开来源 →",
  },
};

export function ResultReturnCard({ result, locale = "en", onOpenOrigin }: {
  result: TaskResultReturn;
  locale?: "en" | "zh-CN";
  onOpenOrigin?: () => void;
}) {
  const t = STRINGS[locale];
  return (
    <article className="mm-result-return" aria-labelledby="mm-result-return-heading">
      <h3 id="mm-result-return-heading">{t.heading}</h3>
      <p className="mm-result-title">{result.title}</p>
      <dl className="mm-result-status">
        <div>
          <dt>{t.deliveredLabel}</dt>
          <dd>
            {t.deliveredTo(result.deliveredTo)}
            {result.deliveredAt ? <small>{t.deliveredWhen(result.deliveredAt)}</small> : null}
          </dd>
        </div>
        <div>
          <dt>{t.acceptedLabel}</dt>
          <dd>
            <span data-accepted={result.accepted}>{result.accepted ? t.acceptedLabel : t.acceptedNo}</span>
            {!result.accepted ? <small>{t.notAcceptedNote}</small> : null}
          </dd>
        </div>
      </dl>
      <div className="mm-result-evidence">
        <h4>{t.evidenceHeading}</h4>
        {result.evidence.length === 0 ? <p>{t.evidenceEmpty}</p> : (
          <dl>{result.evidence.map(item => <div key={item.label}><dt>{item.label}</dt><dd>{item.value}</dd></div>)}</dl>
        )}
      </div>
      {onOpenOrigin ? <button type="button" className="mm-result-open-origin" onClick={onOpenOrigin}>{t.openOrigin}</button> : null}
    </article>
  );
}

/** Convenience: render the origin link slot consistently. */
export function resultOriginSlot(node: ReactNode): ReactNode {
  return <div className="mm-result-origin-slot">{node}</div>;
}
