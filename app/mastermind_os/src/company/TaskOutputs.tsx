import type { CompanyCollection } from "./contract";
import { SourceLink } from "./SourceLink";

export function TaskOutputs({
  products,
  executions,
  locale,
}: {
  products?: CompanyCollection;
  executions?: CompanyCollection;
  locale: "en" | "zh-CN";
}) {
  const zh = locale === "zh-CN",
    t = (en: string, cn: string) => (zh ? cn : en);
  return (
    <>
      <h3>{t("Outputs attached to this task", "本任务关联成果")}</h3>
      {products?.state === "CURRENT" ? (
        products.items.length ? (
          <div className="company-work-grid">
            {products.items.map((product) => (
              <article className="company-inset" key={product.id}>
                <span className="company-kicker">
                  {String(product.kind ?? "artifact")} ·{" "}
                  {String(product.provider ?? "Paperclip")}
                </span>
                <h3>{String(product.title ?? product.id)}</h3>
                {product.summary && (
                  <p className="company-preserve">{String(product.summary)}</p>
                )}
                <div className="company-row-meta">
                  <span>
                    {t("Source product state", "来源成果状态")}:{" "}
                    {String(product.status ?? "—")}
                  </span>
                  <time>
                    {String(product.updatedAt ?? product.createdAt ?? "")}
                  </time>
                </div>
                <div className="company-inline-actions">
                  <SourceLink
                    row={product}
                    label={t("Open original source", "打开原始来源")}
                  />
                </div>
                <details>
                  <summary>
                    {t("Original result references", "原始成果引用")}
                  </summary>
                  <dl className="company-facts">
                    <dt>{t("Work product", "成果")}</dt>
                    <dd>
                      <code>{product.id}</code>
                    </dd>
                    <dt>{t("Source run", "来源执行")}</dt>
                    <dd>
                      <code>{String(product.createdByRunId ?? "—")}</code>
                    </dd>
                    <dt>{t("Execution workspace", "执行工作区")}</dt>
                    <dd>
                      <code>{String(product.executionWorkspaceId ?? "—")}</code>
                    </dd>
                    <dt>{t("Source review state", "来源审查状态")}</dt>
                    <dd>{String(product.reviewState ?? "—")}</dd>
                  </dl>
                </details>
              </article>
            ))}
          </div>
        ) : (
          <p className="company-muted">
            {t(
              "No work products are attached at the source.",
              "来源尚未关联工作成果。",
            )}
          </p>
        )
      ) : (
        <p className="company-muted" role="status">
          {t(
            "The work-product source is unavailable. The task and available discussion remain usable.",
            "工作成果来源暂不可用，任务与可用讨论仍可查看。",
          )}
        </p>
      )}
      {products?.hasMore && (
        <p className="company-muted">
          {t(
            "This is a bounded output window; more records exist at the source.",
            "此处为有限成果窗口，来源还有更多记录。",
          )}
        </p>
      )}
      <p className="company-muted">
        {t(
          "These are the original task's source snapshots, not independent proof of a GitHub approval, deployment or parent acceptance.",
          "这些是原任务的来源快照，不单独证明 GitHub 审批、部署或父任务验收。",
        )}
      </p>
      <details>
        <summary>
          {t("Execution history", "执行历史")}
          {executions?.state === "CURRENT"
            ? ` · ${executions.items.length}${executions.hasMore ? "+" : ""}`
            : ""}
        </summary>
        {executions?.state === "CURRENT" ? (
          executions.items.length ? (
            <div className="company-timeline">
              {executions.items.map((run) => (
                <article key={run.id}>
                  <div className="company-row-meta">
                    <strong>{String(run.status ?? "unknown")}</strong>
                    <time>{String(run.startedAt ?? run.createdAt ?? "")}</time>
                  </div>
                  <dl className="company-facts">
                    <dt>{t("Source run", "来源执行")}</dt>
                    <dd>
                      <code>{run.id}</code>
                    </dd>
                    <dt>{t("Agent", "成员")}</dt>
                    <dd>
                      <code>{String(run.agentId ?? "—")}</code>
                    </dd>
                    <dt>{t("Adapter", "适配器")}</dt>
                    <dd>{String(run.adapterType ?? "—")}</dd>
                    <dt>{t("Finished", "结束时间")}</dt>
                    <dd>{String(run.finishedAt ?? "—")}</dd>
                  </dl>
                  {run.errorCode && (
                    <p>
                      <code>{String(run.errorCode)}</code>
                    </p>
                  )}
                </article>
              ))}
            </div>
          ) : (
            <p>
              {t(
                "No source runs are linked to this task.",
                "本任务尚未关联来源执行。",
              )}
            </p>
          )
        ) : (
          <p role="status">
            {t(
              "Source execution history is unavailable.",
              "来源执行历史暂不可用。",
            )}
          </p>
        )}
        <p className="company-muted">
          {t(
            "Status and original run references only. Private logs, tool outputs and runtime configuration are not included.",
            "仅展示状态与原始执行引用，不包含私有日志、工具输出或运行时配置。",
          )}
        </p>
      </details>
    </>
  );
}
