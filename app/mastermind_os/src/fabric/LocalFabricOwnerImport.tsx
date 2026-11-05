import { useEffect, useRef, useState } from "react";
import type { MissionHost } from "../host";
import {
  decodeLocalOwnerSnapshot, MAX_IMPORT_BYTES,
  type LocalOwnerSnapshot,
} from "./local-fabric-owner-contract";
import "./local-fabric-owner-import.css";

/**
 * Explicit offline file import for the signed-in M2 native operator.
 * It never acquires a machine ledger, invokes C3 tools or sends data to OS.
 * Ordinary website users never receive this panel.
 */
export function LocalFabricOwnerImport({
  host, locale = "en",
}: { host?: MissionHost; locale?: "en" | "zh-CN" }) {
  const [source, setSource] = useState<{ document: LocalOwnerSnapshot; host: MissionHost; epoch: number } | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [error, setError] = useState<string | null>(null);
  const serial = useRef(0);
  const t = (en: string, zh: string) => locale === "zh-CN" ? zh : en;
  const native = typeof window !== "undefined" && Boolean(
    (window as unknown as { __TAURI_INTERNALS__?: unknown }).__TAURI_INTERNALS__
  );
  const ownerEpoch = host?.invalidationGeneration?.();
  // The existing App already owns authentication subscriptions and identity
  // generation. An additional observer here can displace a single-subscriber
  // host and is not a new authentication/permission plane.
  useEffect(() => {
    serial.current++;
    setSource(null); setSelected(null); setQuery(""); setError(null);
    return () => { serial.current++; };
  }, [host, ownerEpoch]);
  const state = host?.auth?.getState();
  const signed = native && state?.status === "signed_in" && state.acquisition &&
    Number.isSafeInteger(ownerEpoch);
  const document = signed && source && source.host === host &&
    source.epoch === ownerEpoch ? source.document : null;
  const rows = document?.rows ?? [];
  const needle = query.trim().toLowerCase();
  const filtered = rows.filter(row =>
    [row.run_id, row.root_id, row.parent_run_id, row.pool, row.model].some(
      value => value?.toLowerCase().includes(needle)
    ));
  const current = filtered.find(row => row.run_id === selected);
  const parent = current?.root_id && current.parent_run_id &&
    current.parent_run_id !== current.root_id && current.parent_run_id !== current.run_id
    ? rows.find(row => row.run_id === current.parent_run_id && row.root_id === current.root_id)
    : undefined;
  const children = current?.root_id ? rows.filter(row =>
    row.root_id === current.root_id && row.run_id !== current.run_id &&
      row.parent_run_id === current.run_id) : [];
  const navigate = (id: string) => {
    setQuery(""); setSelected(id);
  };
  async function importFile(file?: File) {
    const auth = host?.auth;
    if (!file || !signed || !host || !auth) return;
    const epoch = host.invalidationGeneration?.();
    if (epoch === undefined) return;
    const ticket = ++serial.current;
    setSource(null); setSelected(null); setError(null);
    try {
      if (file.size > MAX_IMPORT_BYTES || file.size === 0)
        throw new Error("LOCAL_FABRIC_SNAPSHOT_SIZE_REFUSED");
      const raw = await file.text();
      if (raw.length > MAX_IMPORT_BYTES)
        throw new Error("LOCAL_FABRIC_SNAPSHOT_SIZE_REFUSED");
      const parsed = decodeLocalOwnerSnapshot(JSON.parse(raw));
      if (ticket !== serial.current ||
        host.invalidationGeneration?.() !== epoch ||
        auth.getState().status !== "signed_in" ||
        !auth.getState().acquisition) return;
      setSource({ document: parsed, host, epoch });
    } catch (err) {
      if (ticket === serial.current) {
        setError(err instanceof Error && /^(LOCAL_FABRIC_SNAPSHOT_INVALID|LOCAL_FABRIC_SNAPSHOT_SIZE_REFUSED)$/.test(err.message)
          ? err.message : "LOCAL_FABRIC_SNAPSHOT_INVALID");
      }
    }
  }
  if (!native) return null;
  return <section className="fl-local" aria-label={t("Local M2 Fabric owner history", "M2 本机 Fabric 拥有者历史")}>
    <header className="fl-head">
      <div>
        <small>{t("LOCAL MACHINE OWNER • HISTORICAL RECORDS", "本机拥有者 · 历史记录")}</small>
        <h3>{t("Direct M2 Fabric history", "直接查看 M2 Fabric 历史")}</h3>
      </div>
      <span>{t("Private native import", "本机私有导入")}</span>
    </header>
    <p>{t(
      "Choose a sanitized report generated locally by the Fabric owner. The file stays in this native app session: no upload, controller call or server authorization is performed.",
      "选择由本机 Fabric 拥有者生成的脱敏报告。文件只在本机应用会话中读取，不上传、调用控制器或授予服务器权限。",
    )}</p>
    <p className="fl-warning">{t(
      "Historical ledger outcomes only. Not a complete fleet, live-worker reading, validated acceptance, or access to other users' runs.",
      "仅为账本中的历史结果，不代表完整工作代理池、实时运行、验收结论或其他用户的访问权限。",
    )}</p>
    <label>
      {t("Import local Fabric snapshot (JSON)", "导入本机 Fabric 快照（JSON）")}
      <input type="file" accept=".json,application/json" disabled={!signed}
        onChange={event => {
          const file = event.currentTarget.files?.[0];
          event.currentTarget.value = "";
          void importFile(file);
        }} />
    </label>
    {!signed && <p role="status">{t(
      "Signed-in native Workspace acquisition is required. No local machine data was loaded.",
      "需要已登录的本机 Workspace 读取权限。未加载本机数据。",
    )}</p>}
    {error && <p role="alert">{error}</p>}
    {document && <>
      <div className="fl-coverage">
        <span>{rows.length} {t("retained outcome rows", "条保留的历史记录")}</span>
        <span>{t("Observed", "观测时间")}: {new Date(document.observed_at_unix_s * 1000).toLocaleString()}</span>
        <span>{t("Fleet total and active count unknown", "工作代理总数和运行中数量未知")}</span>
      </div>
      <label>
        {t("Search loaded local run, root or parent", "搜索已加载的本机运行、根或父级")}
        <input type="search" value={query} onChange={event => { setQuery(event.target.value); setSelected(null); }} />
      </label>
      <div className="fl-layout">
        <div className="fl-list" role="group" aria-label={t("Retained local runs", "本机保留的运行")}>
          {filtered.map(row => <button type="button" key={row.run_id}
            aria-pressed={selected === row.run_id}
            onClick={() => setSelected(row.run_id)}>
            <strong>{row.run_id}</strong>
            <span>{row.pool ?? t("Pool unknown", "资源池未知")} · {row.model ?? t("Model unknown", "模型未知")}</span>
            <small>{t("Recorded return code", "记录的返回码")}: {row.rc ?? t("Unknown", "未知")}</small>
          </button>)}
          {filtered.length === 0 && <small>{t("No matching rows in this limited report.", "有限报告中没有匹配记录。")}</small>}
        </div>
        <div className="fl-detail">
          {current ? <>
            <h4>{t("Selected retained run", "所选保留运行")}</h4>
            <dl>
              {([
                [t("Run ID", "运行 ID"), current.run_id],
                [t("Original root label", "原始根标签"), current.root_id],
                [t("Immediate parent label", "直接父级标签"), current.parent_run_id],
                [t("Pool", "资源池"), current.pool],
                [t("Model", "模型"), current.model],
                [t("Return code", "返回码"), current.rc],
                [t("Signal", "信号"), current.signal],
                [t("Recorded", "记录时间"), current.recorded_at_unix_s == null
                  ? null : new Date(current.recorded_at_unix_s * 1000).toLocaleString()],
              ] as const).map(([label, v]) => <div key={label}><dt>{label}</dt><dd>{v ?? t("Unknown", "未知")}</dd></div>)}
            </dl>
            {parent && <button type="button" onClick={() => navigate(parent.run_id)}>
              {t("View loaded parent", "查看已加载父级")}: {parent.run_id}
            </button>}
            {children.map(row => <button type="button" key={row.run_id} onClick={() => navigate(row.run_id)}>
              {t("View loaded child", "查看已加载子级")}: {row.run_id}
            </button>)}
            <small>{t(
              "Links refer only to rows in this user-selected file. Missing ancestors and acceptance remain unknown.",
              "关联仅限于用户所选文件中的记录。缺失的祖先和验收状态仍未知。",
            )}</small>
          </> : <p>{t("Select a retained run. No controller status is read.", "选择一条保留运行。不会读取控制器状态。")}</p>}
        </div>
      </div>
    </>}
  </section>;
}
