import type { CapacityMetricName, HostCapacityState } from "./host-capacity";

/** Already-qualified retained evidence only; no acquisition and no readiness inference. */
export function HostTelemetryPanel({ state, locale = "en" }: { state: HostCapacityState; locale?: "en" | "zh-CN" }) {
  const zh = locale === "zh-CN";
  const t = (en: string, cn: string) => zh ? cn : en;
  const document = state.state === "AVAILABLE" ? state.document : null;
  const shown: [CapacityMetricName, string][] = [
    ["host_cpu_busy_milli_pct", t("Observed CPU busy", "已观测 CPU 繁忙比例")],
    ["effective_cpu_capacity_millicores", t("CPU scope ceiling", "CPU 范围上限")],
    ["effective_memory_headroom_estimate_bytes", t("Estimated memory headroom", "估计内存余量")],
    ["disk_usable_bytes", t("Unprivileged disk space", "普通用户可用磁盘空间")],
  ];
  return <section className="card resources-telemetry" aria-label={t("Host telemetry observation", "主机遥测观测")} aria-busy={state.state === "PENDING"}>
    <h3>{t("Host telemetry", "主机遥测")}</h3>
    {document ? <>
      <p>{t("Observed Linux host", "已观测 Linux 主机")} · {document.telemetry_status === "COMPLETE" ? t("Complete observation", "观测完整") : t("Partial observation", "观测不完整")}</p>
      <p className="muted">{t("Retained observation only. Placement readiness and queue pressure have not been evaluated.", "仅为保留的观测。尚未评估调度就绪情况或队列压力。")}</p>
      <p>{t("Observed", "观测时间")} <time dateTime={new Date(document.observed_at_ms).toISOString()}>{new Date(document.observed_at_ms).toISOString()}</time></p>
      <dl className="resources-telemetry-metrics">{shown.map(([name, label]) => {
        const metric = document.metrics[name];
        return <div key={name}><dt>{label}</dt><dd>{metric.value === null ? t("Not supplied", "未提供") :
          metric.unit === "milli_percent" ? `${metric.value / 1000}%` : `${metric.value.toLocaleString(zh ? "zh-CN" : "en-GB")} ${metric.unit}`}</dd></div>;
      })}</dl>
      <details><summary>{t("Capture scope and missing readings", "采集范围与缺失读数")}</summary>
        <dl>
          <div><dt>{t("Host", "主机")}</dt><dd><code>{document.host_ref}</code></dd></div>
          <div><dt>{t("Source snapshot", "来源快照")}</dt><dd><code>{document.snapshot_sha256}</code></dd></div>
          <div><dt>{t("Execution scope", "执行范围")}</dt><dd><code>{document.execution_scope_sha256}</code></dd></div>
          <div><dt>{t("Observation window", "观测窗口")}</dt><dd>{document.total_observation_window_ms} ms</dd></div>
          <div><dt>{t("Admission", "准入")}</dt><dd>{t("Not evaluated; cannot place work", "未评估；不能安排工作")}</dd></div>
        </dl>
        {document.unknown_fields.length ? <ul>{document.unknown_fields.map(name => <li key={name}><code>{name}</code>: {document.metrics[name].null_reason}</li>)}</ul>
          : <p>{t("No missing applicable metrics in this observation. This does not establish serviceability.", "本次观测中适用指标均未缺失，但这不能证明服务能力。")}</p>}
        <p><code>OBSERVATION_ONLY · NOT_EVALUATED · can_place_work=false</code></p>
      </details>
    </> : <p role="status">{state.state === "PENDING" ? t("Reading retained host observation…", "正在读取保留的主机观测…") : t("No qualified retained host observation is connected. CPU, memory and disk readings remain unknown.", "尚未连接合格的保留主机观测。CPU、内存和磁盘读数仍然未知。")}</p>}
  </section>;
}
