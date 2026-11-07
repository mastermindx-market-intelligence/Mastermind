import type { RetainedProviderCapacityState } from "./retained-provider-capacity";

export function RetainedProviderCapacityPanel({ state, locale = "en" }: { state: RetainedProviderCapacityState; locale?: "en" | "zh-CN" }) {
  const zh = locale === "zh-CN";
  const t = (en: string, cn: string) => zh ? cn : en;
  const document = state.state === "AVAILABLE" ? state.document : null;
  const unknown = t("Not supplied", "未提供");
  const auth = document?.realm_auth.state;
  const health = document?.provider_health.state;
  return <section className="card" aria-label={t("Retained provider evidence", "保留的供应商证据")} aria-busy={state.state === "PENDING"}>
    <h3>{t("Provider observation at the original work claim", "原始工作认领时的供应商观测")}</h3>
    <p className="muted">{t("Historical authentication, quota and cooling evidence. Current eligibility has not been evaluated.", "历史认证、配额和冷却证据。尚未评估当前执行资格。")}</p>
    {document ? <>
      <dl className="resources-telemetry-metrics">
        <div><dt>{t("Provider", "供应商")}</dt><dd>MiniMax</dd></div>
        <div><dt>{t("Authentication at claim", "认领时的认证")}</dt><dd>{auth === "authenticated" ? t("Authenticated", "已认证") : auth === "unauthenticated" ? t("Unauthenticated", "未认证") : unknown}</dd></div>
        <div><dt>{t("Provider health at claim", "认领时的供应商健康情况")}</dt><dd>{health === "healthy" ? t("Healthy observation", "观测健康") : health === "unhealthy" ? t("Unhealthy observation", "观测异常") : unknown}</dd></div>
        <div><dt>{t("Cooling at claim", "认领时的冷却状态")}</dt><dd>{document.cooling.active === null ? unknown : document.cooling.active ? t("Cooling observed", "观测到冷却") : t("No cooling observed", "未观测到冷却")}</dd></div>
      </dl>
      <p>{t("Observed", "观测时间")} <time dateTime={new Date(document.observed_at_ms).toISOString()}>{new Date(document.observed_at_ms).toISOString()}</time></p>
      <p>{t("Observation age when read", "读取时的观测年龄")}: {Math.floor(document.age_ms / 1000)} {t("seconds", "秒")}</p>
      <details><summary>{t("Original claim and quota receipts", "原始认领与配额凭据")}</summary>
        <dl>
          <div><dt>{t("Root / work / attempt", "根任务 / 工作 / 尝试")}</dt><dd><code>{document.root_job_id} / {document.job_id} / {document.attempt_id}</code></dd></div>
          <div><dt>{t("Claim recorded at", "认领记录时间")}</dt><dd>{new Date(document.claim_recorded_at_ms).toISOString()}</dd></div>
          <div><dt>{t("Original claim / physical BEGIN event", "原始认领 / 物理 BEGIN 事件")}</dt><dd>{document.claim_event_id} / {document.begin_event_id}</dd></div>
          <div><dt>{t("Snapshot digest", "快照摘要")}</dt><dd><code>{document.source_snapshot_sha256}</code></dd></div>
          <div><dt>{t("Source release", "来源版本")}</dt><dd><code>{document.source_release_commit}</code></dd></div>
        </dl>
        {document.quota_horizons.length ? <ul>{document.quota_horizons.map(horizon => <li key={horizon.name}>{horizon.name}: {horizon.remaining} / {horizon.limit} · {t("reset recorded for", "记录的重置时间")} {horizon.reset_at}</li>)}</ul>
          : <p>{t("No quota horizons were supplied at claim.", "认领时未提供配额周期。")}</p>}
        <p>{t("This receipt is not a current quota check, host telemetry, queue pressure reading or placement grant.", "此凭据不代表当前配额检查、主机遥测、队列压力读数或调度授权。")}</p>
        <code>RETAINED_CLAIM · NOT_EVALUATED · can_place_work=false</code>
      </details>
    </> : <p role="status">{state.state === "PENDING" ? t("Reading the original retained claim…", "正在读取原始保留认领…") : t("No qualified retained claim was supplied for the selected work.", "所选工作尚未提供合格的保留认领。")}</p>}
  </section>;
}
