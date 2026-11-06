import { useEffect, useId, useMemo, useRef, useState } from "react";
import type { MissionHost } from "../host";
import type { ModelConfigurationRead as ConfigurationRead } from "./model-configuration";
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
  const reader = host?.readModelConfiguration;
  const epoch = host?.invalidationGeneration?.();
  const auth = host?.auth?.getState();
  const permitted = !!host && !!reader && Number.isSafeInteger(epoch)
    && auth?.status === "signed_in" && auth.acquisition;
  const [value, setValue] = useState<{ host: MissionHost; reader: typeof reader; epoch: number; read: ReadState } | null>(null);
  const [query, setQuery] = useState("");
  const [provider, setProvider] = useState("");
  const [limit, setLimit] = useState(20);
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
        <h3 id={titleId}>{t("One routing configuration, inspectable models", "统一路由配置，模型清晰可查")}</h3>
        <p className="muted">{t("Read the existing Executive router’s configured providers, models and workload rules.", "读取现有 Executive 路由器配置的供应商、模型和工作负载规则。")}</p></div>
      <button type="button" onClick={() => void load()} disabled={!permitted || visible?.state === "PENDING"}>
        {visible?.state === "PENDING" ? t("Reading…", "正在读取…") : t("Read configuration", "读取配置")}
      </button>
    </header>
    <p className="model-configuration-boundary">{t(
      "Configuration only. These logical aliases do not prove available paid accounts, live capacity, model entitlement or permission to start work. Keys stay with their original secure owners.",
      "仅为配置。逻辑别名不能证明付费账号可用、实时容量、模型授权或工作启动权限。密钥保留在原有安全管理方。")}</p>
    {!configuration && <p role="status" className="muted">{visible?.state === "PENDING" ? t("Reading the current owner configuration…", "正在读取当前来源配置…")
      : visible?.state === "UNAVAILABLE" ? t("The configuration could not be released by its owner. No empty pool or healthy state is inferred.", "来源未能提供配置，不能据此推断池为空或状态正常。")
      : !permitted ? t("Sign in with Workspace access and a host that exposes this read.", "请使用具备 Workspace 访问权限且已提供此读取功能的主机登录。")
      : t("Choose Read configuration to inspect the source. No background polling is started.", "选择“读取配置”查看来源，不会启动后台轮询。")}</p>}
    {configuration && <>
      <dl className="model-configuration-metrics">
        <div><dt>{t("Provider aliases", "供应商别名")}</dt><dd>{Object.keys(configuration.providers).length}</dd></div>
        <div><dt>{t("Model aliases", "模型别名")}</dt><dd>{Object.keys(configuration.models).length}</dd></div>
        <div><dt>{t("Workload routes", "工作负载路由")}</dt><dd>{Object.keys(configuration.routes).length}</dd></div>
      </dl>
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
      <details className="model-configuration-routes"><summary>{t("Workload routing rules", "工作负载路由规则")}</summary>
        {Object.entries(configuration.routes).map(([kind, route]) => <section key={kind}><h4>{kind}</h4>
          <p className="muted">{t("Required capabilities", "所需能力")}: {route.required_capabilities.join(", ") || t("None supplied", "未提供")}</p>
          {(["routine", "elevated"] as const).map(risk => <div key={risk}><strong>{risk === "routine" ? t("Routine", "常规") : t("Elevated", "增强")}</strong>
            <ol>{route[risk].map(tier => <li key={tier.tier_id}><code>{tier.tier_id}</code>: {tier.model_aliases.join(" → ")}</li>)}</ol></div>)}
        </section>)}
      </details>
      <details><summary>{t("Configuration source and change control", "配置来源与变更控制")}</summary>
        <dl><div><dt>{t("Policy", "策略")}</dt><dd>{configuration.policy_version}</dd></div>
          <div><dt>{t("Configuration revision", "配置版本")}</dt><dd><code>{configuration.revision}</code></dd></div>
          <div><dt>{t("Capability policy revision", "能力策略版本")}</dt><dd><code>{configuration.capability_policy_digest}</code></dd></div>
          <div><dt>{t("Read time", "读取时间")}</dt><dd>{visible?.state === "AVAILABLE" && <time dateTime={visible.observedAt}>{visible.observedAt}</time>}</dd></div></dl>
        <p className="muted">{t("Inspect proposed changes with the existing model_pool_control preview command and this revision. Publication, account draining and key-reference rotation stay with their existing authorized owners; this panel does not activate them.", "使用现有 model_pool_control preview 命令和此版本查看拟议变更。发布、账号排空和密钥引用轮换仍由原有授权方执行，本面板不会激活这些操作。")}</p>
      </details>
    </>}
  </section>;
}
