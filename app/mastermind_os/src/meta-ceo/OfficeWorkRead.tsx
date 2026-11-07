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
    return <p>{t("Work information is loading.", "正在读取工作信息。")}</p>;
  if (
    state.kind === "UNAVAILABLE" ||
    state.document.availability !== "AVAILABLE"
  )
    return (
      <p>
        {t(
          "Work information is unavailable. This does not mean there is no work.",
          "工作信息暂不可用。这不代表没有工作。",
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
      "Completed; acceptance is not reported here",
      "已完成；此处未提供验收状态",
    ),
    FAILED: t("Failed", "失败"),
    LOST: t("Contact lost", "连接丢失"),
    CANCELLED: t("Cancelled", "已取消"),
  };
  const reference = (id: string) =>
    id.length > 18 ? `${id.slice(0, 8)}…${id.slice(-6)}` : id;
  const nextAction = (value: string) =>
    value === "NEEDS_SOL"
      ? t("Sol needs to act", "需要 Sol 处理")
      : value === "NEEDS_WORKER"
        ? t("A worker needs to act", "需要执行者处理")
        : t("Next owner not reported", "未提供下一位负责人");
  const list = (subset: typeof rows) => (
    <ul className="office-lanes">
      {subset.map((row) => (
        <li key={row.root_job_id}>
          <div>
            <strong title={row.root_job_id}>
              {t("Work item", "工作项")} {reference(row.root_job_id)}
            </strong>
            <p>{status[row.lifecycle.status]}</p>
            <p>{nextAction(row.next_actor.value)}</p>
          </div>
        </li>
      ))}
    </ul>
  );
  return (
    <section aria-label={t("Work items in this view", "此视图中的工作项")}>
      <p>
        {t(
          `${doc.coverage.count} work items in this view.`,
          `此视图中有 ${doc.coverage.count} 个工作项。`,
        )}
      </p>
      <p className="office-muted">
        {t(
          doc.coverage.completeness === "PARTIAL" || doc.coverage.truncated
            ? "Some work may be missing from this view."
            : "Only the work provided for this view is shown.",
          doc.coverage.completeness === "PARTIAL" || doc.coverage.truncated
            ? "此视图可能未显示全部工作。"
            : "这里只显示此视图已提供的工作。",
        )}
      </p>
      {rows.length ? (
        list(rows.slice(0, 8))
      ) : (
        <p>
          {t(
            "No work items were supplied for this view.",
            "此视图未提供工作项。",
          )}
        </p>
      )}
      {rows.length > 8 && (
        <details>
          <summary>
            {t(
              `Show ${rows.length - 8} more items`,
              `查看其余 ${rows.length - 8} 个工作项`,
            )}
          </summary>
          {list(rows.slice(8))}
        </details>
      )}
      <details className="office-raw">
        <summary>{t("Work source details", "工作来源详情")}</summary>
        <p>{t("Full work references", "完整工作引用")}</p>
        <ul className="office-ref">
          {rows.map((row) => (
            <li key={row.root_job_id}>
              <code>{row.root_job_id}</code>
            </li>
          ))}
        </ul>
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
        <p className="office-ref">
          {t("Runtime observation", "运行时观测")} ·{" "}
          {doc.source_observation.runtime?.snapshot_digest ??
            t("Unknown", "未知")}
        </p>
      </details>
      {onInspect && (
        <button type="button" onClick={onInspect}>
          {t("Inspect Work", "查看工作")}
        </button>
      )}
    </section>
  );
}
