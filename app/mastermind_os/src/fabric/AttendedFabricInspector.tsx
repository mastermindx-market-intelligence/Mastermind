import { useEffect, useId, useRef, useState } from "react";
import type { MissionHost } from "../host";
import { attendedSelection, decodeAttendedStatus, type AttendedStatus } from "./attended-status";
import "./fabric-inspector.css";

export function AttendedFabricInspector({ host, locale = "en" }: { host?: MissionHost; locale?: "en" | "zh-CN" }) {
  const zh = locale === "zh-CN";
  const t = (en: string, cn: string) => zh ? cn : en;
  const id = useId();
  const [rootId, setRoot] = useState("");
  const [runId, setRun] = useState("");
  const [result, setResult] = useState<{ value: AttendedStatus; acquiredAt: string; epoch: number; rootId: string; runId: string; host: MissionHost } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [, invalidate] = useState(0);
  const request = useRef<AbortController | null>(null);
  const serial = useRef(0);
  const mountedHost = useRef(host);
  mountedHost.current = host;
  const cancel = () => { serial.current++; request.current?.abort(); request.current = null; setBusy(false); setResult(null); setError(null); };
  useEffect(() => {
    // Current host source generation, not a new session/identity. No retained private results.
    cancel();
    // An unmounted source must not install an extra authentication observer.
    if (!host?.readAttendedFabric || typeof host.invalidationGeneration !== "function") return;
    const unsub = host.auth?.subscribe(() => { cancel(); invalidate(n => n + 1); });
    return () => { serial.current++; request.current?.abort(); unsub?.(); };
  }, [host]);
  const state = host?.auth?.getState();
  const ready = !!host?.readAttendedFabric && typeof host.invalidationGeneration === "function" && state?.status === "signed_in" && state.acquisition;
  const epoch = host?.invalidationGeneration?.() ?? 0;
  const shown = ready && result?.host === host && result?.epoch === epoch && result.rootId === rootId && result.runId === runId ? result : null;
  const selection = attendedSelection({ rootId, runId });
  async function inspect() {
    if (!host?.readAttendedFabric || !ready || !selection || busy) return;
    request.current?.abort();
    const abort = new AbortController(); request.current = abort;
    const ticket = ++serial.current, started = host.invalidationGeneration?.() ?? 0;
    setBusy(true); setResult(null); setError(null);
    try {
      const raw = await host.readAttendedFabric({ ...selection, signal: abort.signal });
      if (abort.signal.aborted || ticket !== serial.current || mountedHost.current !== host || started !== (host.invalidationGeneration?.() ?? 0)) return;
      const now = host.auth?.getState();
      if (now?.status !== "signed_in" || !now.acquisition) throw new Error("FABRIC_READ_UNAUTHORIZED");
      setResult({ value: decodeAttendedStatus(raw, selection), acquiredAt: new Date().toISOString(), epoch: started, ...selection, host });
    } catch (cause) {
      if (abort.signal.aborted || ticket !== serial.current) return;
      const code = cause instanceof Error ? cause.message : "";
      setError(["FABRIC_STATUS_INVALID", "FABRIC_ROOT_MISMATCH", "FABRIC_ACCEPTANCE_CONFLICT", "FABRIC_READ_UNAUTHORIZED"].includes(code) ? code : "FABRIC_SOURCE_UNAVAILABLE");
    } finally { if (ticket === serial.current) setBusy(false); }
  }
  const value = (v: unknown): string => v === null || v === undefined ? t("Unknown", "未知") : typeof v === "boolean" ? (v ? t("Yes", "是") : t("No", "否")) : String(v);
  const fields = shown ? [
    [t("Run", "运行标识"), shown.value.run_id], [t("Observed root", "观测根标识"), shown.value.root_id],
    [t("Observed parent", "观测父标识"), shown.value.parent_run_id], [t("Controller state", "控制器状态"), shown.value.state],
    [t("Exit code", "退出码"), shown.value.rc], [t("Signal", "信号"), shown.value.signal],
    [t("Result present", "存在结果"), shown.value.result_available], [t("Result bytes", "结果字节数"), shown.value.result_bytes],
    [t("Acceptance", "验收"), shown.value.acceptance_state], [t("Accepted by", "验收方式"), shown.value.accepted_by],
    [t("Acceptance reason", "验收依据"), shown.value.acceptance_reason], [t("Locally acquired", "本地获取时间"), shown.acquiredAt]
  ] : [];
  return <details className="fi-workspace fi-attended"><summary>{t("Direct M2 Fabric · inspect an existing run", "直接 M2 Fabric · 查看现有运行")}</summary>
    <p>{t("A separate source from Executive missions. Run and root labels are selectors, not permission or native-session identity.", "此来源不同于 Executive 任务。运行和根标识仅用于选择，不构成权限或原生会话身份。")}</p>
    {!ready ? <p className="fi-notice" role="status">{t("No authorized direct Fabric reader is mounted. This is not an idle-fleet reading.", "尚未挂载已授权的直接 Fabric 读取器，不代表代理池空闲。")}</p> : <form className="fi-inspect-form" onSubmit={e => { e.preventDefault(); void inspect(); }}>
      <label htmlFor={`${id}-root`}>{t("Original root", "原始根标识")}</label>
      <input id={`${id}-root`} autoComplete="off" maxLength={128} value={rootId} onChange={e => { cancel(); setRoot(e.target.value); }} />
      <label htmlFor={`${id}-run`}>{t("Existing run ID", "现有运行标识")}</label>
      <input id={`${id}-run`} autoComplete="off" maxLength={128} value={runId} onChange={e => { cancel(); setRun(e.target.value); }} />
      <button type="submit" disabled={!selection || busy}>{busy ? t("Reading…", "读取中…") : t("Inspect run", "查看运行")}</button>
    </form>}
    {error && <p role="alert" className="fi-warning">{error}</p>}
    {shown && <div className="fi-detail" aria-label={t("Direct Fabric observation", "直接 Fabric 观测")}>
      {shown.value.state === "EFFECT_UNKNOWN" && <p className="fi-warning">{t("Effects are unresolved. This observation does not authorize replay or failover.", "效果尚未核实，此观测不授权重放或切换。")}</p>}
      {shown.value.root_id === null && <p className="fi-warning">{t("The source did not establish root or parent lineage.", "来源尚未确认根或父级关系。")}</p>}
      <dl>{fields.map(([label, v]) => <div key={String(label)}><dt>{label}</dt><dd>{value(v)}</dd></div>)}</dl>
      <p>{t("Active or waiting is not proof of worker START. Terminal is not product acceptance. Local acquisition time is not a source heartbeat.", "活动或等待不证明工作代理已启动。终止不等于产品验收。本地获取时间不等于来源心跳。")}</p>
    </div>}
  </details>;
}
