import { useEffect, useId, useMemo, useRef, useState } from "react";
import type { MissionHost } from "../host";
import { capacitySummary, type CapacityAdvice, type CapacityFabricRead as Read, type Pressure, type QuotaWindow } from "./capacity-fabric";
import "./capacity-fabric.css";

type ReadState = Read | { state: "PENDING" };

/** Manual source refresh; no polling, provider calls, placement or purchases. */
export function CapacityFabricRead({ host, locale = "en", headingLevel = 2 }: {
  host?: MissionHost; locale?: "en" | "zh-CN"; headingLevel?: 1 | 2;
}) {
  const zh = locale === "zh-CN", t = (en: string, cn: string) => zh ? cn : en;
  const id = useId(), Heading = headingLevel === 1 ? "h1" : "h2";
  const reader = host?.readCapacityFabric, epoch = host?.invalidationGeneration?.();
  const auth = host?.auth?.getState();
  const permitted = !!host && !!reader && Number.isSafeInteger(epoch) && auth?.status === "signed_in" && auth.acquisition;
  const [owned, setOwned] = useState<{ host: MissionHost; reader: typeof reader; epoch: number; read: ReadState } | null>(null);
  const [query, setQuery] = useState(""), [provider, setProvider] = useState(""), [attention, setAttention] = useState(false), [limit, setLimit] = useState(8);
  const abort = useRef<AbortController | null>(null), current = useRef({ host, reader });
  current.current = { host, reader };
  const visible = permitted && owned?.host === host && owned.reader === reader && owned.epoch === epoch ? owned.read : null;
  const document = visible?.state === "AVAILABLE" && Date.parse(visible.document.expires_at) > Date.now() ? visible.document : null;
  useEffect(() => {
    abort.current?.abort(); setOwned(null);
    const off = host?.auth?.subscribe(() => { abort.current?.abort(); setOwned(null); });
    return () => { abort.current?.abort(); off?.(); };
  }, [host, reader]);
  useEffect(() => {
    if (visible?.state !== "AVAILABLE") return;
    // Expire local evidence at the earliest source/window deadline. No fetch.
    const timer = setTimeout(() => setOwned(value => value?.read === visible ? { ...value, read: { state: "UNAVAILABLE", reason: "SOURCE_EXPIRED" } } : value),
      Math.max(0, Date.parse(visible.document.expires_at) - Date.now()));
    return () => clearTimeout(timer);
  }, [visible]);
  const refresh = async () => {
    if (!host || !reader || !permitted || epoch === undefined) return;
    abort.current?.abort(); const controller = new AbortController(); abort.current = controller;
    const origin = { host, reader, epoch };
    const valid = () => !controller.signal.aborted && current.current.host === host && current.current.reader === reader
      && host.invalidationGeneration?.() === epoch && host.auth?.getState().status === "signed_in" && host.auth?.getState().acquisition;
    setOwned({ ...origin, read: { state: "PENDING" } });
    try {
      const read = await reader.call(host, { signal: controller.signal });
      if (valid()) {
        setOwned({ ...origin, read }); setLimit(8);
        if (read.state === "AVAILABLE") setProvider(value => read.document.resources.some(row => row.provider === value) ? value : "");
      }
    } catch { if (valid()) setOwned({ ...origin, read: { state: "UNAVAILABLE", reason: "SOURCE_UNAVAILABLE" } }); }
  };
  const rows = useMemo(() => document?.resources.filter(row => (!provider || row.provider === provider)
    && (!attention || row.pressure !== "HEADROOM_RECORDED")
    && (!query.trim() || `${row.resource_ref} ${row.provider} ${row.pool}`.toLowerCase().includes(query.trim().toLowerCase()))) ?? [], [document, provider, attention, query]);
  const summary = document ? capacitySummary(document) : null;
  const label = (state: Pressure) => ({ UNKNOWN: t("Usage unknown", "用量未知"), HEADROOM_RECORDED: t("Allowance available", "有剩余额度"),
    LOW_ALLOWANCE: t("Allowance running low", "额度偏低"), LIMIT_REACHED: t("Limit reached", "已达上限"), COOLDOWN: t("Cooling down", "冷却中"),
    SLOTS_OCCUPIED: t("Slots occupied", "槽位已占满"), UNAVAILABLE: t("Not ready", "尚未就绪") })[state];
  const when = (value: string | null) => value ? new Intl.DateTimeFormat(locale, { dateStyle: "short", timeStyle: "short" }).format(new Date(value)) : t("Not supplied", "未提供");
  const windowName = (name: string) => ({ "5h": t("5 hours", "5 小时"), weekly: t("Weekly", "每周"), monthly: t("Monthly", "每月") } as Record<string, string>)[name] ?? name;
  const windowStatus = (w?: QuotaWindow) => !w || w.state === "UNKNOWN" ? t("Not supplied", "未提供") : w.state === "STALE" ? t("Reading expired", "读数已过期") : t("Not qualified", "尚未核实");
  const advice: Record<CapacityAdvice, [string, string]> = {
    UPDATE_USAGE: [t("Update usage readings", "更新用量读数"), t("Some account limits need fresh evidence before routing can use them.", "部分账号额度需要新读数，才能用于路由。")],
    CONSERVE_ALLOWANCE: [t("Conserve the tightest limit", "保留紧张额度"), t("Reduce optional work on accounts with little allowance remaining.", "减少低余额账号上的非必要工作。")],
    WAIT_FOR_RESET: [t("Recheck held accounts", "重新核实受限账号"), t("A reset time alone does not restore capacity; wait for a fresh reading.", "到达重置时间不等于额度恢复，仍需新读数。")],
    REVIEW_QUEUE: [t("Review queue pressure", "查看排队压力"), t("Review occupied slots and queued work. Check sustained demand before adding capacity.", "查看已占用槽位与排队工作，扩容前先确认持续需求。")],
    REVIEW_ROUTING: [t("Review eligible routing", "查看合适路由"), t("Recorded headroom can inform routing within the permitted model tier.", "已观测余额可供同一合适模型等级内的路由参考。")],
    MEASURE_DEMAND: [t("Measure before expanding", "按需求评估扩容"), t("An upgrade size needs demand history and reset coverage; this snapshot cannot price it.", "扩容规模需要需求历史与重置周期数据，单次快照不足以估价。")],
  };
  return <section className="capacity-fabric" aria-labelledby={id} lang={locale} aria-busy={visible?.state === "PENDING"}>
    <header className="capacity-fabric-heading"><div><p className="eyebrow">{t("SHARED AI RESOURCES", "共享 AI 资源")}</p>
      <Heading id={id} tabIndex={-1}>{t("Capacity Fabric", "统一容量")}</Heading>
      <p className="muted">{t("Account limits, pool pressure and connected applications.", "账号额度、容量压力与应用接入。")}</p></div>
      <button type="button" onClick={() => void refresh()} disabled={!permitted || visible?.state === "PENDING"}>{visible?.state === "PENDING" ? t("Reading…", "读取中…") : t("Read capacity", "读取容量")}</button>
    </header>
    {!document ? <div className="capacity-fabric-empty" role="status">
      <h3>{visible?.state === "PENDING" ? t("Reading shared capacity", "正在读取共享容量") : visible?.state === "UNAVAILABLE" && visible.reason === "SOURCE_EXPIRED" ? t("Readings need an update", "读数需要更新") : t("Capacity is not observed", "尚未观测容量")}</h3>
      <p>{!permitted ? auth?.status === "signed_in" && auth.acquisition
        ? t("The capacity reader is not connected to this workspace.", "此工作区尚未连接容量读取器。")
        : t("Sign in with Workspace access to read connected capacity.", "登录具有 Workspace 权限的账号后查看容量。")
        : visible?.state === "PENDING" ? t("Checking the current recorded observations.", "正在检查当前已记录的观测。")
        : visible?.state === "UNAVAILABLE" ? t("Current readings are unavailable. Models and recorded work remain available below.", "当前读数不可用，下方仍可查看模型与工作记录。")
        : t("Read the latest recorded limits and account pressure.", "读取最新记录的额度与账号压力。")}</p>
    </div> : <>
      <div className="capacity-fabric-overview"><div><h3>{summary!.constrained ? t("Capacity needs attention", "容量需要关注") : summary!.unknown ? t("Usage evidence is incomplete", "用量证据尚不完整") : t("Review recorded capacity", "查看已记录容量")}</h3>
        <p>{summary!.constrained ? t(`${summary!.constrained} account views show pressure. Review their binding limits.`, `${summary!.constrained} 个账号视图存在压力，请查看限制周期。`)
          : t("Check each allowance and its freshness before placing work.", "安排工作前，查看各项额度与读数时间。")}</p></div>
        <p className="capacity-fabric-time">{t("Observed", "观测于")} <time dateTime={document.observed_at}>{when(document.observed_at)}</time></p>
      </div>
      <div className="capacity-fabric-controls"><label htmlFor={`${id}-search`}>{t("Find an account", "查找账号")}<input id={`${id}-search`} type="search" value={query} maxLength={128} onChange={e => { setQuery(e.target.value); setLimit(8); }}/></label>
        <label htmlFor={`${id}-provider`}>{t("Provider", "供应商")}<select id={`${id}-provider`} value={provider} onChange={e => { setProvider(e.target.value); setLimit(8); }}><option value="">{t("All providers", "全部供应商")}</option>{[...new Set(document.resources.map(row => row.provider))].sort().map(name => <option key={name} value={name}>{name}</option>)}</select></label>
        <label className="capacity-fabric-check"><input type="checkbox" checked={attention} onChange={e => { setAttention(e.target.checked); setLimit(8); }}/>{t("Needs attention", "需要关注")}</label>
      </div>
      <p className="muted" aria-live="polite">{t(`${rows.length} account views · shared allowances are never added together`, `${rows.length} 个账号视图 · 共享额度不会重复相加`)}</p>
      <ul className="capacity-fabric-accounts">{rows.slice(0, limit).map(row => <li key={row.resource_ref}>
        <div className="capacity-fabric-account"><strong>{row.resource_ref}</strong><span className={`capacity-fabric-status capacity-pressure-${row.pressure.toLowerCase()}`}>{label(row.pressure)}</span></div>
        <div className="capacity-fabric-windows">{["5h", "weekly", "monthly"].map(name => { const w = row.windows.find(x => x.window === name); return <div key={name} className="capacity-fabric-window"><span>{windowName(name)}</span>
          {w && w.remaining_pct !== null ? <><strong>{w.remaining_pct.toLocaleString(locale, { maximumFractionDigits: 1 })}% <small>{t("left", "剩余")}</small></strong><meter min={0} max={100} value={w.remaining_pct} aria-label={`${row.resource_ref} ${windowName(name)} ${t("remaining", "剩余额度")}`}/></> : <strong className="capacity-fabric-unknown">{windowStatus(w)}</strong>}
        </div>; })}</div>
        <div className="capacity-fabric-slots"><span>{t("In use", "使用中")} <b>{row.active ?? t("Unknown", "未知")}</b></span><span>{t("Queued", "排队中")} <b>{row.queued ?? t("Unknown", "未知")}</b></span><span>{row.configured_cap_basis === "ACCOUNT" ? t("Account cap", "账号上限") : row.configured_cap_basis === "POOL" ? t("Shared pool cap", "共享池上限") : t("Cap · scope unknown", "上限 · 范围未知")} <b>{row.configured_concurrency ?? t("Unknown", "未知")}</b></span></div>
        <details><summary>{t("Limits, resets & evidence", "额度、重置与证据")}</summary><dl>
          <div><dt>{t("Shared allowance", "共享额度")}</dt><dd>{row.allowance_scope ?? t("Physical identity not joined", "尚未关联物理额度身份")}</dd></div>
          <div><dt>{t("Recorded hold until", "记录的限制截止")}</dt><dd>{when(row.cooldown_until)}</dd></div>
          {row.windows.map(w => <div key={w.window}><dt>{windowName(w.window)} · {w.required ? t("binding window", "约束周期") : t("not supplied as binding", "未提供为约束周期")}</dt><dd>{t("Reset", "重置")} {when(w.reset_at)}<small>{t("Observed", "观测")} {when(w.observed_at)} · {w.reason}</small></dd></div>)}
          <div><dt>{t("Single-window preview", "单周期预览")}</dt><dd>{row.single_window_remaining_pct === null ? t("Unknown", "未知") : `${row.single_window_remaining_pct}%`} · {row.single_window_source === "LOCAL_ESTIMATE" ? t("Local estimate", "本地估计") : row.single_window_source === "RECORDED_OBSERVATION" ? t("Recorded source", "记录来源") : t("Unknown source", "来源未知")}<small>{t("Observed", "观测")} {when(row.single_window_observed_at)}</small></dd></div>
        </dl><p className="muted">{t("Queued work is waiting, not reserved. A shared pool cap applies across its accounts. Quota and permission to run are checked separately.", "排队工作尚未获得预留。共享池上限适用于池内所有账号，额度与执行许可分别核实。")}</p></details>
      </li>)}</ul>
      {!rows.length && <p role="status">{document.resources.length ? t("No accounts match these filters.", "没有符合筛选条件的账号。") : t("This observation returned no accounts. Available capacity remains unknown.", "本次观测未返回账号，可用容量仍未知。")}</p>}
      {rows.length > limit && <button type="button" onClick={() => setLimit(n => Math.min(256, n + 8))}>{t("Show more accounts", "显示更多账号")}</button>}
      {document.recommendations.length > 0 && <section className="capacity-fabric-advice" aria-label={t("Capacity suggestions", "容量建议")}><h3>{t("What to review", "建议关注")}</h3><ul>{document.recommendations.map(code => <li key={code}><strong>{advice[code][0]}</strong><p>{advice[code][1]}</p></li>)}</ul></section>}
      <section className="capacity-fabric-consumers"><h3>{t("Connected applications", "接入应用")}</h3><ul>{document.consumers.map(row => <li key={row.consumer}><strong>{{ hermes: t("Hermes bots", "Hermes 机器人"), deepseek: "DeepSeek Harness", t3_code: "T3 Code", website: t("Website AI", "网站 AI") }[row.consumer]}</strong>
        <span>{row.runtime_state === "RESULT_PROVEN" ? t("Result verified", "结果已核实") : row.runtime_state === "RUNNING" ? t("Execution observed", "已观测执行") : row.runtime_state === "ENROLLED" ? t("Enrollment observed", "已观测接入") : t("Live connection not observed", "尚未观测实时连接")}</span>
        <details><summary>{t("Integration evidence", "接入证据")}</summary><p>{row.source_state === "BUILT" ? t("Adapter source is implemented.", "适配器源码已实现。") : t("Integration specification is recorded.", "已记录接入规范。")}</p><p>{row.evidence_ref ?? t("No current runtime receipt supplied.", "未提供当前运行凭据。")}</p>{row.observed_at && <time dateTime={row.observed_at}>{when(row.observed_at)}</time>}</details>
      </li>)}</ul></section>
      <details className="capacity-fabric-method"><summary>{t("How this view works", "此视图如何工作")}</summary><p>{t("This reads existing quota, broker and application observations. It does not refresh provider accounts, reserve slots, change routing or buy capacity. Missing and expired readings stay unknown.", "此视图读取现有额度、调度与应用观测，不刷新供应商账号、不预留槽位、不修改路由，也不购买容量。缺失或过期读数保持未知。")}</p><p>{t("Source revision", "来源版本")} <code>{document.source_revision}</code></p></details>
    </>}
  </section>;
}
