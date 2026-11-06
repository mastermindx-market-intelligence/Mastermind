import type { WorkDocument } from "../work";
import { WORK_GROUP_ORDER } from "../work";
export type OfficeWorkReadState =
  | { kind: "PENDING" }
  | { kind: "UNAVAILABLE"; reason: string }
  | { kind: "DOCUMENT"; document: WorkDocument };

/** Existing bounded Work acquisition only. This view has no reader/controller. */
export function OfficeWorkRead({
  state,
  locale = "en",
  onInspect,
}: {
  state: OfficeWorkReadState;
  locale?: "en" | "zh-CN";
  onInspect?: () => void;
}) {
  const t = (en: string, zh: string) => (locale === "zh-CN" ? zh : en);
  if (state.kind === "PENDING")
    return <p>{t("Work observation is pending.", "正在等待工作观测。")}</p>;
  if (
    state.kind === "UNAVAILABLE" ||
    state.document.availability !== "AVAILABLE"
  )
    return (
      <p>
        {t(
          "Work source unavailable. This is not evidence of zero work.",
          "工作来源不可用。这不代表没有工作。",
        )}
      </p>
    );
  const doc = state.document,
    rows = WORK_GROUP_ORDER.flatMap((group) => doc.groups[group]);
  const status = {
    QUEUED: t("Queued", "已排队"),
    RUNNING: t("Running", "运行中"),
    CHECKPOINTED: t("Checkpoint recorded", "已记录检查点"),
    RATE_LIMITED: t("Rate limited", "速率受限"),
    CANCEL_REQUESTED: t("Stop requested", "已请求停止"),
    COMPLETED: t(
      "Completed; acceptance is separate",
      "已完成；接受状态另行报告",
    ),
    FAILED: t("Failed", "失败"),
    LOST: t("Contact lost", "连接丢失"),
    CANCELLED: t("Cancelled", "已取消"),
  };
  const list = (subset: typeof rows) => (
    <ul className="office-lanes">
      {subset.map((row) => (
        <li key={row.root_job_id}>
          <div>
            <strong className="office-ref">{row.root_job_id}</strong>
            <p>{status[row.lifecycle.status]}</p>
            <p>
              {t("Next owner", "下一位负责人")} ·{" "}
              {row.next_actor.value === "UNKNOWN"
                ? t("Not supplied", "未提供")
                : row.next_actor.value}
            </p>
          </div>
        </li>
      ))}
    </ul>
  );
  return (
    <section aria-label={t("Observed Work roots", "已观测工作根任务")}>
      <p>
        {t(
          `${doc.coverage.count} Work roots supplied by the bounded source.`,
          `有界来源提供了 ${doc.coverage.count} 个工作根任务。`,
        )}
      </p>
      <p className="office-muted">
        {t(
          "This is a Work observation, not a company-wide total or an acceptance ruling.",
          "这是工作观测，不是全公司总量，也不是接受结论。",
        )}
      </p>
      {rows.length ? (
        list(rows.slice(0, 8))
      ) : (
        <p>
          {t(
            "No Work roots were supplied in this qualified observation.",
            "此合格观测未提供工作根任务。",
          )}
        </p>
      )}
      {rows.length > 8 && (
        <details>
          <summary>
            {t(
              `Show ${rows.length - 8} more supplied roots`,
              `查看其余 ${rows.length - 8} 个已提供根任务`,
            )}
          </summary>
          {list(rows.slice(8))}
        </details>
      )}
      <details className="office-raw">
        <summary>{t("Work source details", "工作来源详情")}</summary>
        <p>
          {doc.coverage.completeness} · {t("Observed at", "观测时间")}{" "}
          {doc.generated_at}
        </p>
        <p>
          {t("Source-reported total", "来源报告总量")} ·{" "}
          {doc.coverage.total ?? t("Unknown", "未知")} ·{" "}
          {t("Truncated", "已截断")} {String(doc.coverage.truncated)}
        </p>
        <p>
          {t("Effect exception", "效果例外")} · {doc.effect_exception.value}
        </p>
        <p className="office-ref">{t("Runtime observation", "运行时观测")} · {doc.source_observation.runtime?.snapshot_digest ?? t("Unknown", "未知")}</p>
      </details>
      {onInspect && (
        <button type="button" onClick={onInspect}>
          {t("Inspect Work", "查看工作")}
        </button>
      )}
    </section>
  );
}
