import { useEffect, useId, useRef, useState } from "react";
import type { MissionHost } from "../host";
import { decodeBrowserScopedFabricCatalog, type CatalogRow, type FabricCatalog } from "./catalog-contract";
import { observedRunLineage, type RunLineageState } from "./catalog-lineage";
import "./fabric-catalog.css";

type Filter = "all" | "active" | "results" | "review" | "attention" | "nested";
const relationCopy: Record<RunLineageState, [string, string]> = {
  ROOT_PARENT_LABEL: ["Parent is the original root label (not necessarily a worker)", "上级为原始根标签（不一定是工作代理）"],
  OBSERVED_ANCESTRY: ["Contiguous parent chain in these records", "本次记录中连续可见的父级链"],
  PARENT_OUTSIDE_RESPONSE: ["Parent not supplied in these records", "本次记录中未包含父级"],
  PARENT_STATUS_UNAVAILABLE: ["Parent status is unavailable", "父级状态不可用"],
  ROOT_UNVERIFIED: ["Original root not verified", "原始根未核实"],
  PARENT_UNVERIFIED: ["Immediate parent not verified", "直接父级未核实"],
  ROOT_CONFLICT: ["Root identities conflict — not joined", "根身份不一致，未关联"],
  PARENT_CYCLE: ["Parent cycle — relationship invalid", "父级循环，关系无效"],
  DUPLICATE_ID: ["Duplicate run identity — not joined", "重复运行标识，未关联"],
  STATUS_UNAVAILABLE: ["Source status is unavailable", "来源状态不可用"],
};
const needsReview = (r: CatalogRow) => r.status?.state === "TERMINAL" && r.status.rc === 0 &&
  r.status.signal === "ok" && r.status.result_available && r.status.accepted === false;
const attention = (r: CatalogRow) => !!r.reason_code || !r.status ||
  ["EFFECT_UNKNOWN", "TERMINAL_FAILURE", "RESULT_UNAVAILABLE", "STATUS_UNREADABLE"].includes(r.status.state) ||
  r.status.state === "TERMINAL" && r.status.rc !== null && r.status.rc !== 0;
const filterRow = (r: CatalogRow, filter: Filter, nested: boolean) => filter === "all" ||
  filter === "nested" && nested ||
  filter === "active" && r.status?.state === "ACTIVE_OR_WAITING" ||
  filter === "results" && r.status?.result_available === true || filter === "review" && needsReview(r) ||
  filter === "attention" && attention(r);
interface Observation { document: FabricCatalog; host: MissionHost; epoch: number }
export interface FabricRunCatalogProps {
  host?: MissionHost; locale?: "en" | "zh-CN";
  onInspect?: (selection: { rootId: string; runId: string }) => void;
}

/** Optional presentation over an owner-authorized port, not a source, grant or poller. */
export function FabricRunCatalog({ host, locale = "en", onInspect }: FabricRunCatalogProps) {
  const t = (en: string, zh: string) => locale === "zh-CN" ? zh : en;
  const id = useId();
  const [observation, setObservation] = useState<Observation | null>(null);
  const [selectedId, select] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<Filter>("all");
  const [query, setQuery] = useState("");
  const [, renderGeneration] = useState(0);
  const serial = useRef(0), request = useRef<AbortController | null>(null), currentHost = useRef(host);
  currentHost.current = host;
  const clear = () => { serial.current++; request.current?.abort(); request.current = null;
    setObservation(null); select(null); setFilter("all"); setQuery(""); setBusy(false); setError(null); };
  useEffect(() => {
    clear();
    if (!host?.readAttendedFabricCatalog || typeof host.invalidationGeneration !== "function") return;
    const unsubscribe = host.auth?.subscribe(() => { clear(); renderGeneration(n => n + 1); });
    return () => { serial.current++; request.current?.abort(); unsubscribe?.(); };
  }, [host]);
  const auth = host?.auth?.getState(), epoch = host?.invalidationGeneration?.();
  const ready = !!host?.readAttendedFabricCatalog && typeof host.invalidationGeneration === "function" &&
    Number.isSafeInteger(epoch) && auth?.status === "signed_in" && auth.acquisition;
  const document = ready && observation?.host === host && observation.epoch === epoch ? observation.document : null;
  const rows = document?.items ?? [];
  const lineage = observedRunLineage(rows);
  const nestedCount = rows.filter(row => lineage.get(row.run_id)?.declared_nested_parent === true).length;
  const needle = query.trim().toLocaleLowerCase();
  const filtered = rows.filter(row => filterRow(row, filter, lineage.get(row.run_id)?.declared_nested_parent === true) && [row.run_id, row.status?.root_id, row.status?.parent_run_id]
    .some(v => v?.toLocaleLowerCase().includes(needle)));
  const selected = filtered.find(row => row.run_id === selectedId);
  const selectedLineage = selected ? lineage.get(selected.run_id) : undefined;
  const lineageAllowsObservedEdges = selectedLineage?.state === "ROOT_PARENT_LABEL" ||
    selectedLineage?.state === "OBSERVED_ANCESTRY" || selectedLineage?.state === "PARENT_OUTSIDE_RESPONSE";
  const selectedRoot = selected?.status?.root_id;
  const selectedParent = selectedRoot && lineageAllowsObservedEdges &&
    (selectedLineage?.state === "OBSERVED_ANCESTRY" || selectedLineage?.state === "PARENT_OUTSIDE_RESPONSE")
    ? rows.find(row => row.run_id === selected?.status?.parent_run_id && row.run_id !== selected.run_id &&
        row.status?.root_id === selectedRoot && row.reason_code === null) : undefined;
  const observedChildren = selectedRoot && lineageAllowsObservedEdges
    ? rows.filter(row => row.run_id !== selected?.run_id && row.status?.parent_run_id === selected?.run_id &&
        row.status.root_id === selectedRoot && row.reason_code === null &&
        ["OBSERVED_ANCESTRY", "PARENT_OUTSIDE_RESPONSE"].includes(lineage.get(row.run_id)?.state ?? "")) : [];
  // Selection is local to one verified source generation; it never calls the status port.
  const selectObserved = (targetId: string) => {
    if (!ready || observation?.host !== host || observation.epoch !== host?.invalidationGeneration?.()) return;
    if (targetId !== selectedParent?.run_id && !observedChildren.some(child => child.run_id === targetId)) return;
    setFilter("all");
    setQuery("");
    select(targetId);
  };
  const active = rows.filter(row => row.status?.state === "ACTIVE_OR_WAITING").length;
  const value = (v: unknown): string => v === null || v === undefined ? t("Unknown", "未知") :
    typeof v === "boolean" ? (v ? t("Yes", "是") : t("No", "否")) : String(v);
  async function load() {
    if (!ready || !host?.readAttendedFabricCatalog || epoch === undefined || busy) return;
    const controller = new AbortController(); request.current?.abort(); request.current = controller;
    const ticket = ++serial.current, started = epoch;
    setObservation(null); select(null); setError(null); setBusy(true);
    try {
      const raw = await host.readAttendedFabricCatalog({ signal: controller.signal });
      if (controller.signal.aborted || ticket !== serial.current || currentHost.current !== host ||
          started !== host.invalidationGeneration?.()) return;
      const after = host.auth?.getState();
      if (after?.status !== "signed_in" || !after.acquisition) throw new Error("FABRIC_ACCESS_CHANGED");
      setObservation({ document: decodeBrowserScopedFabricCatalog(raw), host, epoch: started });
    } catch (cause) {
      if (controller.signal.aborted || ticket !== serial.current || currentHost.current !== host ||
          started !== host.invalidationGeneration?.()) return;
      const code = cause instanceof Error ? cause.message : "";
      setError(["FABRIC_CATALOG_INVALID", "FABRIC_CATALOG_SCOPE_REFUSED", "FABRIC_ACCESS_CHANGED"].includes(code) ? code : "FABRIC_SOURCE_UNAVAILABLE");
    } finally { if (ticket === serial.current) setBusy(false); }
  }
  const filters: Array<[Filter, string, string]> = [["all", "All", "全部"], ["active", "Active or waiting", "活动或等待"],
    ["results", "With results", "包含结果"], ["review", "Awaiting acceptance", "等待验收"], ["attention", "Needs inspection", "需要检查"], ["nested", "Nested parents", "嵌套父级"]];
  const fields: Array<[string, unknown]> = selected ? [
    [t("Run", "运行标识"), selected.run_id], [t("Root", "根标识"), selected.status?.root_id],
    [t("Immediate parent", "直接父标识"), selected.status?.parent_run_id], [t("Controller state", "控制器状态"), selected.status?.state],
    [t("Exit code", "退出码"), selected.status?.rc], [t("Signal", "信号"), selected.status?.signal],
    [t("Result present", "存在结果"), selected.status?.result_available], [t("Result bytes", "结果字节数"), selected.status?.result_bytes],
    [t("Acceptance", "验收"), selected.status?.acceptance_state], [t("Accepted by", "验收方式"), selected.status?.accepted_by],
    [t("Acceptance reason", "验收依据"), selected.status?.acceptance_reason],
    [t("Controller file modified", "控制器文件修改时间"), selected.controller_modified_at],
  ] : [];
  const inspect = () => {
    if (ready && observation?.host === host && observation.epoch === host?.invalidationGeneration?.() &&
        selected?.status?.root_id && !selected.reason_code) onInspect?.({ rootId: selected.status.root_id, runId: selected.run_id });
  };
  return <section className="fc-panel" aria-labelledby={`${id}-title`}>
    <header className="fc-heading"><div><p className="fc-eyebrow">{t("Direct M2 Fabric", "直接 M2 Fabric")}</p>
      <h2 id={`${id}-title`}>{t("Recent Fabric runs", "近期 Fabric 运行")}</h2>
      <p>{t("Browse observed records, then inspect a run without copying its ID.", "浏览观测记录，然后直接查看运行，无需复制标识。")}</p></div>
      <button className="fc-load" type="button" disabled={!ready || busy} onClick={() => void load()}>
        {busy ? t("Reading…", "读取中…") : document ? t("Refresh runs", "刷新运行") : t("Load runs", "加载运行")}</button></header>
    <p className="fc-scope">{t("Recent controller records only — not all native sessions or a count of running workers. No launch, replay or acceptance actions.", "仅含近期控制器记录，不代表全部原生会话或运行中代理总数。不提供启动、重放或验收操作。")}</p>
    {!ready && <p className="fc-notice" role="status">{t("No authorized catalog reader is connected. This does not mean the fleet is idle.", "未连接已授权的目录读取器，不代表代理池空闲。")}</p>}
    {ready && !document && !busy && !error && <p className="fc-notice">{t("Load the permitted source to see recent runs.", "加载已授权来源以查看近期运行。")}</p>}
    {error && <p className="fc-notice" role="alert">{error}</p>}
    {document && <><div className="fc-coverage"><strong>{document.availability}</strong>
      <span>{t("Shown", "已显示")} {document.coverage.returned_count} / {t("Source candidates", "来源候选记录")} {value(document.coverage.candidate_count)}</span>
      <span>{t("Omitted", "省略")} {value(document.coverage.omitted_count)}</span><span>{document.source.scope}</span>
      <small>{t("Locally acquired", "本地获取时间")} · {document.observed_at}</small></div>
      <p>{t("Sequential observation, not an atomic live snapshot. Controller file time is not a worker heartbeat.", "顺序观测，并非原子实时快照。控制器文件时间不等于工作代理心跳。")}</p>
      {document.reason_codes.length > 0 && <p className="fc-notice">{document.reason_codes.join(" · ")}</p>}
      {document.availability !== "UNAVAILABLE" && <>
        <div className="fc-summary"><span>{active} {t("active or waiting in these rows", "条活动或等待记录")}</span>
          <span>{rows.filter(r => !r.status).length} {t("unverified records", "条尚未核实记录")}</span>
          <span>{rows.filter(needsReview).length} {t("awaiting acceptance", "条等待验收记录")}</span>
          <span>{rows.filter(attention).length} {t("need inspection", "条需要检查记录")}</span>
          <span>{nestedCount} {t("declared nested parents in these rows", "条记录声明了嵌套父级")}</span></div>
        <div className="fc-controls"><div className="fc-filters" role="group" aria-label={t("Filter recent runs", "筛选近期运行")}>
          {filters.map(([f, en, zh]) => <button type="button" key={f} aria-pressed={filter === f} onClick={() => { setFilter(f); select(null); }}>{t(en, zh)}</button>)}</div>
          <label htmlFor={`${id}-search`}>{t("Search loaded run, root or parent", "搜索已加载的运行、根或父标识")}</label>
          <input id={`${id}-search`} maxLength={128} value={query} onChange={e => { setQuery(e.target.value); select(null); }} autoComplete="off" /></div>
        <div className="fc-layout"><div className="fc-list">{filtered.length ? filtered.map(row => <button type="button" className="fc-row" key={row.run_id}
          aria-label={`${row.run_id} · ${row.status?.state ?? row.reason_code}`} aria-pressed={row.run_id === selectedId} onClick={() => select(row.run_id)}>
          <strong>{row.run_id}</strong><span>{row.status?.state ?? row.reason_code}</span>
          <small>{t("Root", "根标识")} · {value(row.status?.root_id)}</small>
          <small>{t("Parent relation", "父级关系")} · {t(...relationCopy[lineage.get(row.run_id)?.state ?? "STATUS_UNAVAILABLE"])}</small>
          <span>{t("Acceptance", "验收")} · {value(row.status?.acceptance_state)}</span>
        </button>) : <p className="fc-notice">{t("No matching records in this response.", "本次响应中没有匹配记录。")}</p>}</div>
          <aside className="fc-detail" aria-label={t("Selected recent run", "所选近期运行")}><h3>{t("Selected run", "所选运行")}</h3>
            {!selected ? <p>{t("Choose a record to inspect its source-qualified metadata.", "选择记录以查看带来源限定的元数据。")}</p> : <>
              {selected.reason_code && <p className="fc-notice">{selected.reason_code}</p>}
              {selectedLineage && <div className="fc-lineage" data-state={selectedLineage.state} role="group" aria-label={t("Observed run ancestry", "观测运行层级")}>
                <strong>{t("Observed ancestry in this response", "本次响应中观测到的层级")}</strong>
                <p>{selectedLineage.path.join(" → ")}</p>
                <small>{t(...relationCopy[selectedLineage.state])} · {selectedLineage.contiguous_to_root_label
                  ? `${t("Declared depth", "声明深度")} ${selectedLineage.observed_depth}`
                  : t("Full depth unknown", "完整深度未知")}</small>
                <small>{t("Root labels identify correlation, not authority or verified worker START.", "根标签仅用于关联，不代表权限或工作代理已启动。")}</small>
              </div>}
              {(selectedParent || observedChildren.length > 0) && <div className="fc-relations" role="group"
                aria-label={t("Related observed runs", "已观测的关联运行")}>
                <strong>{t("Related runs in this response", "本次响应中的关联运行")}</strong>
                {selectedParent && <button type="button"
                  aria-label={`${t("View observed parent", "查看已观测父级")}: ${selectedParent.run_id}`}
                  onClick={() => selectObserved(selectedParent.run_id)}>
                  <span>{t("Parent", "父级")}</span><code>{selectedParent.run_id}</code>
                </button>}
                <small>{t("Observed children in loaded records", "已加载记录中的观测子级")} · {observedChildren.length}</small>
                {observedChildren.map(item => <button type="button" key={item.run_id}
                  aria-label={`${t("View observed child", "查看已观测子级")}: ${item.run_id}`}
                  onClick={() => selectObserved(item.run_id)}>
                  <span>{t("Child", "子级")}</span><code>{item.run_id}</code>
                </button>)}
                <small>{t("Navigation only selects an already-loaded record; it does not grant access or read a new run.",
                  "导航仅选择已加载的记录，不授予权限，也不读取新的运行。")}</small>
              </div>}
              <dl>{fields.map(([label, v]) => <div key={label}><dt>{label}</dt><dd>{value(v)}</dd></div>)}</dl>
              <button className="fc-load" type="button" onClick={inspect} disabled={!onInspect || !selected.status?.root_id || !!selected.reason_code}>
                {t("Use in run inspector", "在运行检查器中打开")}</button>
              {!selected.status?.root_id && <p>{t("Root lineage is not established. No root has been invented for this record.", "根级关系尚未确认，未为此记录编造根标识。")}</p>}
              <p>{t("Choosing a run supplies a selector, not permission, execution or acceptance.", "选择运行仅提供查询条件，不授予权限，也不代表执行或验收。")}</p>
            </>}
          </aside></div>
      </>}
    </>}
  </section>;
}
