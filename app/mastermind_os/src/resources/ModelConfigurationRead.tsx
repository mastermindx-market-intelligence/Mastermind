import { useEffect, useId, useMemo, useRef, useState } from "react";
import type { MissionHost } from "../host";
import type { ModelConfigurationRead as ConfigurationRead } from "./model-configuration";
import { displayObservationTime, explainConfiguredRoute, policyModelCounts, type PolicyReason, type RouteRisk } from "./model-route-explanation";
import "./model-configuration.css";

type ReadState = ConfigurationRead | { state: "PENDING" };

/** Explicit authenticated inspection of configured routing. No polling,
 * credential inputs, editing/publishing, activation, placement or provider call. */
export function ModelConfigurationRead({ host, locale = "en" }: {
  host?: MissionHost; locale?: "en" | "zh-CN";
}) {
  const zh = locale === "zh-CN";
  const t = (en: string, cn: string) => zh ? cn : en;
  const titleId = useId(), searchId = useId(), providerId = useId();
  const workloadId = useId(), riskId = useId(), aliasId = useId();
  const reader = host?.readModelConfiguration;
  const epoch = host?.invalidationGeneration?.();
  const auth = host?.auth?.getState();
  const permitted = !!host && !!reader && Number.isSafeInteger(epoch)
    && auth?.status === "signed_in" && auth.acquisition;
  const [value, setValue] = useState<{ host: MissionHost; reader: typeof reader; epoch: number; read: ReadState } | null>(null);
  const [query, setQuery] = useState("");
  const [provider, setProvider] = useState("");
  const [limit, setLimit] = useState(20);
  const [workload, setWorkload] = useState("");
  const [risk, setRisk] = useState<RouteRisk>("routine");
  const [exactAlias, setExactAlias] = useState("");
  const abort = useRef<AbortController | null>(null);
  const current = useRef({ host, reader });
  current.current = { host, reader };
  useEffect(() => {
    abort.current?.abort(); setValue(null);
    const off = host?.auth?.subscribe(() => { abort.current?.abort(); setValue(null); });
    return () => { abort.current?.abort(); off?.(); };
  }, [host, reader]);
  const visible = permitted && value?.host === host && value.reader === reader && value.epoch === epoch ? value.read : null;
  const configuration = visible?.state === "AVAILABLE" ? visible.configuration : null;
  const counts = configuration ? policyModelCounts(configuration) : null;
  const currentWorkload = configuration && Object.hasOwn(configuration.routes, workload)
    ? workload : Object.keys(configuration?.routes ?? {})[0] ?? "";
  const explanation = configuration ? explainConfiguredRoute(configuration, currentWorkload, risk, exactAlias) : null;
  const timeZone = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  const observedTime = visible?.state === "AVAILABLE" ? displayObservationTime(visible.observedAt, locale, timeZone) : null;
  const policyReason = (reason: PolicyReason) => ({
    PROVIDER_DISABLED: t("Provider disabled in policy", "策略中已停用供应商"),
    AUTONOMOUS_DISABLED: t("Autonomous work disabled in policy", "策略中未启用自主工作"),
    WORKER_NOT_ELIGIBLE: t("Not eligible for worker routing in policy", "策略中未允许用于工作者路由"),
    CAPABILITIES_MISSING: t("Required capabilities missing", "缺少所需能力"),
  })[reason];
  const rows = useMemo(() => {
    const search = query.trim().toLowerCase();
    return Object.entries(configuration?.models ?? {}).filter(([alias, row]) =>
      (!provider || row.provider_alias === provider)
      && (!search || [alias, row.model, row.provider_alias, ...row.capabilities].some(text => text.toLowerCase().includes(search))));
  }, [configuration, query, provider]);
  const load = async () => {
    if (!host || !reader || !permitted || epoch === undefined) return;
    abort.current?.abort();
    const controller = new AbortController(); abort.current = controller;
    const owned = { host, reader, epoch };
    const stillOwned = () => {
      const state = host.auth?.getState();
      return !controller.signal.aborted && current.current.host === host && current.current.reader === reader
        && host.invalidationGeneration?.() === epoch && state?.status === "signed_in" && state.acquisition;
    };
    setValue({ ...owned, read: { state: "PENDING" } });
    try {
      const read = await reader.call(host, { signal: controller.signal });
      if (stillOwned()) {
        setValue({ ...owned, read });
        if (read.state === "AVAILABLE") {
          setProvider(selected => Object.hasOwn(read.configuration.providers, selected) ? selected : "");
          setExactAlias(selected => Object.hasOwn(read.configuration.models, selected) ? selected : "");
        }
        setLimit(20);
      }
    } catch {
      if (stillOwned()) setValue({ ...owned, read: { state: "UNAVAILABLE", reason: "SOURCE_UNAVAILABLE" } });
    }
  };
  return <section className="card model-configuration-panel" aria-labelledby={titleId} aria-busy={visible?.state === "PENDING"}>
    <header className="model-configuration-heading">
      <div><p className="eyebrow">{t("SHARED MODEL ROUTING", "共享模型路由")}</p>
        <h3 id={titleId}>{t("Models & capacity", "模型与容量")}</h3>
        <p className="muted">{t("Inspect configured models and the evidence still needed for live readiness.", "查看已配置模型及实时就绪状态尚缺的证据。")}</p></div>
      <button type="button" onClick={() => void load()} disabled={!permitted || visible?.state === "PENDING"}>
        {visible?.state === "PENDING" ? t("Reading…", "正在读取…") : t("Read configuration", "读取配置")}
      </button>
    </header>
    <p className="model-configuration-boundary">{t(
      "Configuration snapshot only. Account capacity and permission to start work still need owner evidence.",
      "仅为配置快照。账号容量及工作启动权限仍需来源证据。")}</p>
    {!configuration && <p role="status" className="muted">{visible?.state === "PENDING" ? t("Reading the current owner configuration…", "正在读取当前来源配置…")
      : visible?.state === "UNAVAILABLE" ? t("The configuration could not be released by its owner. No empty pool or healthy state is inferred.", "来源未能提供配置，不能据此推断池为空或状态正常。")
      : !permitted ? t("Sign in with Workspace access and a host that exposes this read.", "请使用具备 Workspace 访问权限且已提供此读取功能的主机登录。")
      : t("Choose Read configuration to inspect the source. No background polling is started.", "选择“读取配置”查看来源，不会启动后台轮询。")}</p>}
    {configuration && counts && <>
      <dl className="model-configuration-metrics model-configuration-readiness" aria-label={t("Independent readiness evidence", "独立就绪证据")}>
        <div><dt>{t("Configured models", "已配置模型")}</dt><dd>{counts.configured}</dd></div>
        <div><dt>{t("Enabled in policy", "策略中已启用")}</dt><dd>{counts.enabledInPolicy}</dd></div>
        <div><dt>{t("Qualified", "已完成资格验证")}</dt><dd className="model-evidence-unknown">{t("Unproven", "尚未证实")}</dd></div>
        <div><dt>{t("Eligible now", "当前可用")}</dt><dd className="model-evidence-unknown">{t("Unknown", "未知")}</dd></div>
        <div><dt>{t("Real-path proven", "真实执行已验证")}</dt><dd className="model-evidence-unknown">{t("Unproven", "尚未证实")}</dd></div>
      </dl>
      <details className="model-capacity-evidence"><summary>{t("Account capacity · evidence needed", "账号容量 · 待补证据")}</summary>
        <p>{t("Physical accounts have not been joined to these aliases. Several model names can share one allowance; an alias count is not a pool count.", "物理账号尚未与这些别名关联。多个模型名称可能共享同一额度，别名数量不等于容量池数量。")}</p>
        <dl>
          <div><dt>{t("Physical allowance owners", "物理额度归属")}</dt><dd>{t("Not joined", "尚未关联")}</dd></div>
          <div><dt>{t("Usage and observation age", "用量与观测时间")}</dt><dd>{t("Not observed", "尚未观测")}</dd></div>
          <div><dt>{t("Applicable windows and resets", "适用周期及重置时间")}</dt><dd>{t("Unknown · no reset is inferred", "未知 · 不推测重置时间")}</dd></div>
          <div><dt>{t("Local cap and reservations", "本地上限及已预留容量")}</dt><dd>{t("Not observed", "尚未观测")}</dd></div>
          <div><dt>{t("Budget and reserved capacity", "预算及保留容量")}</dt><dd>{t("Not observed", "尚未观测")}</dd></div>
          <div><dt>{t("Wait or refusal reason", "等待或拒绝原因")}</dt><dd>{t("Not evaluated", "尚未评估")}</dd></div>
        </dl>
        <p className="muted">{t("Missing or stale usage never means unused quota. Waiting is not running. Credentials stay with their existing secure owners.", "缺失或过期的用量数据不代表额度未使用。等待不等于正在执行。凭据仍由现有安全来源管理。")}</p>
      </details>
      <div className="model-configuration-filters">
        <label htmlFor={searchId}>{t("Find a model or capability", "查找模型或能力")}
          <input id={searchId} value={query} maxLength={128} onChange={e => { setQuery(e.target.value); setLimit(20); }} type="search" />
        </label>
        <label htmlFor={providerId}>{t("Provider alias", "供应商别名")}
          <select id={providerId} value={provider} onChange={e => { setProvider(e.target.value); setLimit(20); }}>
            <option value="">{t("All configured providers", "全部已配置供应商")}</option>
            {Object.keys(configuration.providers).map(name => <option key={name} value={name}>{name}</option>)}
          </select>
        </label>
      </div>
      <p className="muted" aria-live="polite">{t(`Showing ${Math.min(limit, rows.length)} of ${rows.length} matching model aliases`, `显示 ${rows.length} 个匹配模型别名中的 ${Math.min(limit, rows.length)} 个`)}</p>
      <ul className="model-configuration-models">{rows.slice(0, limit).map(([alias, row]) => <li key={alias}>
        <div><strong>{alias}</strong><span>{row.model}</span></div>
        <div><b>{row.provider_alias}</b><span>{configuration.providers[row.provider_alias].enabled ? t("Provider enabled in policy", "策略中已启用供应商") : t("Provider disabled in policy", "策略中已停用供应商")}</span></div>
        <div><b>{row.worker_eligible ? t("Worker profile configured", "已配置工作者配置档") : t("Not a worker profile", "非工作者配置档")}</b><span>{t("Live admission not observed", "尚未观测实时准入")}</span></div>
        <details><summary>{t("Capabilities and source binding", "能力与来源绑定")}</summary>
          <dl><div><dt>{t("Capabilities", "能力")}</dt><dd>{row.capabilities.join(", ") || t("None supplied", "未提供")}</dd></div>
            <div><dt>{t("Adapter / effort / cost class", "适配器 / 推理强度 / 成本类别")}</dt><dd>{row.adapter_id} · {row.effort} · {row.cost_class}</dd></div>
            <div><dt>{t("Execution profile", "执行配置档")}</dt><dd>{row.execution_profile_id}</dd></div>
            <div><dt>{t("Profile revision", "配置档版本")}</dt><dd><code>{row.execution_profile_digest}</code></dd></div></dl>
        </details>
      </li>)}</ul>
      {rows.length > limit && <button type="button" onClick={() => setLimit(count => Math.min(count + 20, 1024))}>{t("Show more configured models", "显示更多已配置模型")}</button>}
      <details className="model-configuration-routes"><summary>{t("Explain configured routing", "解释已配置路由")}</summary>
        <p className="model-route-preview-label">{t("Policy inspection · no capacity reserved", "策略查看 · 不预留容量")}</p>
        <div className="model-configuration-filters model-route-filters">
          <label htmlFor={workloadId}>{t("Workload", "工作类型")}<select id={workloadId} value={currentWorkload} disabled={!currentWorkload} onChange={event => setWorkload(event.target.value)}>
            {!currentWorkload && <option value="">{t("No configured routes", "尚未配置路由")}</option>}
            {Object.keys(configuration.routes).map(kind => <option key={kind} value={kind}>{kind}</option>)}
          </select></label>
          <label htmlFor={riskId}>{t("Policy tier", "策略等级")}<select id={riskId} value={risk} onChange={event => setRisk(event.target.value as RouteRisk)}>
            <option value="routine">{t("Routine", "常规")}</option><option value="elevated">{t("Elevated", "增强")}</option>
          </select></label>
          <label htmlFor={aliasId}>{t("Inspect exact alias", "查看指定别名")}<select id={aliasId} value={exactAlias} onChange={event => setExactAlias(event.target.value)}>
            <option value="">{t("All aliases in this route", "此路由中的全部别名")}</option>
            {Object.keys(configuration.models).map(alias => <option key={alias} value={alias}>{alias}</option>)}
          </select></label>
        </div>
        {explanation && <div aria-live="polite">
          <p className="muted">{t("Required capabilities", "所需能力")}: {explanation.requiredCapabilities.join(", ") || t("None supplied", "未提供")}</p>
          {(explanation.pinState === "OUTSIDE_ROUTE" || explanation.pinState === "UNKNOWN_ALIAS") && <p role="status">{t("The inspected alias is outside this configured route. No alternate is chosen.", "指定别名不在此配置路由中，不会改选其他模型。")}</p>}
          {explanation.rows.length === 0 && explanation.pinState === "NONE" && <p role="status">{t("No aliases are configured for this workload and tier. This is not evidence that all pools are busy.", "此工作类型和等级尚未配置别名，不能据此判断所有容量池繁忙。")}</p>}
          <ol className="model-route-explanation">{explanation.rows.map((row, index) => <li key={`${row.tier}:${row.alias}:${index}`}>
            <div><strong>{row.alias}</strong><span>{row.model} · {row.provider}</span></div>
            <p>{row.reasons.length ? row.reasons.map(policyReason).join(" · ") : t("Configured candidate · live eligibility unknown", "已配置候选 · 实时可用性未知")}</p>
            {row.missingCapabilities.length > 0 && <p className="muted">{t("Missing", "缺少")}: {row.missingCapabilities.join(", ")}</p>}
            <small><code>{row.tier}</code></small>
          </li>)}</ol>
          <p className="muted">{t("Order comes from this policy snapshot. Account choice, use-before-reset preference, exact runtime pins and served model require the selection owner's evidence.", "顺序来自此策略快照。账号选择、重置前优先使用、运行时精确固定及实际服务模型仍需选择来源的证据。")}</p>
        </div>}
      </details>
      <details><summary>{t("Configuration source and change control", "配置来源与变更控制")}</summary>
        <dl><div><dt>{t("Policy", "策略")}</dt><dd>{configuration.policy_version}</dd></div>
          <div><dt>{t("Provider aliases", "供应商别名")}</dt><dd>{Object.keys(configuration.providers).length}</dd></div>
          <div><dt>{t("Model aliases", "模型别名")}</dt><dd>{Object.keys(configuration.models).length}</dd></div>
          <div><dt>{t("Workload routes", "工作负载路由")}</dt><dd>{Object.keys(configuration.routes).length}</dd></div>
          <div><dt>{t("Configuration revision", "配置版本")}</dt><dd><code>{configuration.revision}</code></dd></div>
          <div><dt>{t("Capability policy revision", "能力策略版本")}</dt><dd><code>{configuration.capability_policy_digest}</code></dd></div>
          <div><dt>{t("Read time", "读取时间")}</dt><dd>{visible?.state === "AVAILABLE" && <><time dateTime={visible.observedAt}>{observedTime ?? visible.observedAt}</time><span className="model-observation-zone">{timeZone}</span></>}</dd></div></dl>
        <p className="muted">{t("Read again to inspect the latest configuration. Qualification and execution evidence are independent of policy enablement.", "重新读取可查看最新配置。资格验证及执行证据与策略启用状态彼此独立。")}</p>
        <details><summary>{t("Policy changes and active requests", "策略变更及进行中的请求")}</summary>
          <p>{t("Policy changes are not available in this view. Publishing, revision conflicts, draining and rollback remain with the existing authorized owner.", "此视图暂不提供策略变更。发布、版本冲突、排空及回滚仍由现有授权来源处理。")}</p>
          <p className="muted">{t("This read does not observe or change an active request's original model, account or policy commitment. It creates no reservation or running work.", "此读取不会观测或改变进行中请求的原始模型、账号或策略绑定，也不会预留容量或启动工作。")}</p>
        </details>
      </details>
    </>}
  </section>;
}

