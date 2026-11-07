import { useCallback, useEffect, useRef, useState } from "react";
import type { NativeHermesPort, NativeOperation, NativeReceipt, NativeSession, NativeView } from "./contract";
import { nativeHermesPort } from "./native-port";
import type { NativePendingOperation } from "./pending-pointer";
import "./native-panel.css";

const beforeDispatch = new Set(["REQUEST_INVALID", "NATIVE_BUSY", "NATIVE_INSTALL_UNAVAILABLE", "NATIVE_PLATFORM_UNAVAILABLE", "NATIVE_CLIENT_NOT_STARTED", "NATIVE_AUTH_NOT_DISPATCHED"]);
const knownErrors = new Set([...beforeDispatch, "NATIVE_RECOVERY_UNAVAILABLE", "AUTHENTICATION_CHANGED", "NATIVE_IDENTITY_CHANGED", "NATIVE_RECOVERY_REQUIRED", "NATIVE_RESPONSE_INVALID", "NATIVE_CLIENT_UNAVAILABLE"]);
function requestId(): string { return crypto.randomUUID().replaceAll("-", ""); }
function originalPointer(request: NativeOperation): NativePendingOperation | null {
  return request.operation === "create" ? { kind: "create", requestId: request.requestId }
    : request.operation === "send" ? { kind: "send", requestId: request.requestId, sessionId: request.sessionId } : null;
}
function title(value: string): string { return value.replace(/ · [a-f0-9]{32}$/, "") || "Native conversation"; }

/** Local native conversation only. A future qualified backend implements the same port. */
export function HermesNativePanel({ locale, port = nativeHermesPort }: { locale: string; port?: NativeHermesPort }) {
  const zh = locale.toLowerCase().startsWith("zh");
  const t = (en: string, cn: string) => zh ? cn : en;
  const [runtime, setRuntime] = useState<NativeView["runtime"]>();
  const [session, setSession] = useState<NativeSession>();
  const [history, setHistory] = useState<NativeView["sessions"]>();
  const [receipt, setReceipt] = useState<NativeReceipt>();
  const [role, setRole] = useState<"meta-ceo" | "secretary">("meta-ceo");
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [held, setHeld] = useState<NativePendingOperation | null>(null);
  const heldRef = useRef<NativePendingOperation | null>(null);
  // Private, component-local draft cleanup only; never stored as an effect record.
  const submittedDraft = useRef<{ requestId: string; text: string } | null>(null);
  const generation = useRef<number | undefined>(undefined);
  const inFlight = useRef(false);
  const mounted = useRef(true);
  const pollCount = useRef(0);
  const stopAutomatic = useRef(false);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  const clearPrivate = useCallback(() => {
    setRuntime(undefined); setSession(undefined); setHistory(undefined); setReceipt(undefined); setDraft("");
    heldRef.current = null; setHeld(null); submittedDraft.current = null;
    generation.current = undefined; stopAutomatic.current = true;
  }, []);

  const perform = useCallback(async (request: NativeOperation): Promise<NativeView | undefined> => {
    const mutating = request.operation === "send" || request.operation === "create";
    if (inFlight.current || (mutating && heldRef.current)) return;
    const originalHeld = heldRef.current;
    if (request.operation === "send") submittedDraft.current = { requestId: request.requestId, text: request.text };
    inFlight.current = true; setBusy(true); setNotice("");
    try {
      const result = await port.request(request);
      if (!mounted.current) return;
      if (generation.current !== undefined && generation.current !== result.authGeneration) {
        clearPrivate(); setNotice("AUTHENTICATION_CHANGED"); return;
      }
      generation.current = result.authGeneration;
      if ("sessionId" in request && result.session && request.sessionId !== result.session.id && request.sessionId !== result.session.storedId) {
        throw new Error("NATIVE_RESPONSE_INVALID");
      }
      if ("sessionId" in request && result.receipt && result.receipt.sessionId !== request.sessionId) throw new Error("NATIVE_RESPONSE_INVALID");
      if (request.operation === "receipt" && result.receipt && result.receipt.id !== request.admissionId) throw new Error("NATIVE_RESPONSE_INVALID");
      if (result.pendingOperation !== undefined) {
        heldRef.current = result.pendingOperation; setHeld(result.pendingOperation);
        if (result.pendingOperation && result.state === "READY") {
          stopAutomatic.current = true; setNotice("EFFECT_UNKNOWN");
        }
      }
      if (result.runtime) setRuntime(result.runtime);
      if (result.session) setSession(result.session);
      if (result.sessions) setHistory(result.sessions);
      if (result.receipt) setReceipt(result.receipt);
      if (result.state === "OPENED") { setReceipt(undefined); setDraft(""); submittedDraft.current = null; pollCount.current = 0; stopAutomatic.current = false; }
      if (result.state === "ADMITTED") {
        const acceptedDraft = request.operation === "send" ? { requestId: request.requestId, text: request.text }
          : request.operation === "recover" && originalHeld?.kind === "send" && submittedDraft.current?.requestId === originalHeld.requestId
            ? submittedDraft.current : null;
        if (acceptedDraft) {
          setDraft(value => value === acceptedDraft.text ? "" : value);
          submittedDraft.current = null;
        }
        if (request.operation === "send") pollCount.current = 0;
        // A receipt settles only this admission. Refresh history before reusing send eligibility.
        if (request.operation === "recover") setSession(previous => previous && result.receipt &&
          [previous.id, previous.storedId].includes(result.receipt.sessionId) ? { ...previous, canSend: false, sendCheckRequired: undefined } : undefined);
        stopAutomatic.current = result.receipt?.status === "terminal";
      }
      if (result.state === "EFFECT_UNKNOWN") {
        if (mutating && result.pendingOperation === undefined) {
          heldRef.current = originalPointer(request); setHeld(heldRef.current);
        }
        stopAutomatic.current = true; setNotice("EFFECT_UNKNOWN");
      } else if (["REFUSED", "UNAVAILABLE", "NOT_SENT"].includes(result.state)) {
        stopAutomatic.current = true; setNotice(result.code || result.state);
      }
      return result;
    } catch (error) {
      if (!mounted.current) return;
      const raw = typeof error === "string" ? error : error instanceof Error ? error.message : "";
      const code = knownErrors.has(raw) ? raw : "NATIVE_CLIENT_UNAVAILABLE";
      stopAutomatic.current = true;
      if (code === "AUTHENTICATION_CHANGED" || code === "NATIVE_AUTH_NOT_DISPATCHED" || code === "NATIVE_IDENTITY_CHANGED") {
        clearPrivate(); setNotice(code === "NATIVE_AUTH_NOT_DISPATCHED" ? "AUTHENTICATION_CHANGED" : code);
      }
      else if (mutating && !beforeDispatch.has(code)) {
        heldRef.current = originalPointer(request); setHeld(heldRef.current); setNotice("EFFECT_UNKNOWN");
      } else setNotice(code);
    } finally {
      inFlight.current = false;
      if (mounted.current) setBusy(false);
    }
  }, [port, clearPrivate]);

  // This is a bounded read of the original admission while this panel is open,
  // not a background model loop, scheduler, retry, or second runtime owner.
  const activeAdmission = receipt && ["queued", "started"].includes(receipt.status) ? receipt.id
    : session?.pending.find(row => ["queued", "started"].includes(row.status))?.id;
  useEffect(() => {
    if ((!session && !receipt) || !activeAdmission || busy || stopAutomatic.current || pollCount.current >= 30) return;
    const original = receipt?.sessionId ?? session!.id;
    const timer = window.setTimeout(async () => {
      pollCount.current += 1;
      const result = await perform(heldRef.current ? { operation: "recover" }
        : { operation: "receipt", sessionId: original, admissionId: activeAdmission });
      if (result?.receipt?.status === "terminal" && mounted.current) await perform({ operation: "read", sessionId: original });
    }, 2000);
    return () => window.clearTimeout(timer);
  }, [session, activeAdmission, busy, held, receipt, perform]);

  const checkPrevious = async () => {
    pollCount.current = 0;
    const result = await perform({ operation: "recover" });
    if (result?.receipt) {
      await perform({ operation: "read", sessionId: result.receipt.sessionId });
    }
  };
  const readOriginal = async () => {
    if (heldRef.current) { await checkPrevious(); return; }
    const target = session?.id ?? receipt?.sessionId;
    if (!target) return;
    if (receipt && receipt.status !== "terminal") await perform({ operation: "receipt", sessionId: receipt.sessionId, admissionId: receipt.id });
    await perform({ operation: "read", sessionId: target });
  };
  const unknownAdmission = receipt?.status === "unknown" || session?.pending.some(row => row.status === "unknown");
  const unresolved = Boolean(held || unknownAdmission);
  const pending = Boolean(session?.running || activeAdmission);
  const sendEligible = Boolean(session?.canSend || session?.sendCheckRequired);
  // Describe the original effect without inferring a new tool-policy observation.
  const sessionIds = session ? [session.id, session.storedId] : [];
  const receiptForSession = receipt && sessionIds.includes(receipt.sessionId) ? receipt : undefined;
  const originalUnsettledForSession = Boolean(
    (held?.kind === "send" && sessionIds.includes(held.sessionId)) ||
    (receiptForSession && receiptForSession.status !== "terminal") ||
    session?.pending.some(row => row.status !== "terminal"));
  const canSend = sendEligible && !busy && !unresolved && !pending && !session?.promptsPending && draft.trim().length > 0 && new TextEncoder().encode(draft).length <= 32768;

  if (!port.available()) return <section className="hermes-native-panel" aria-label={t("Native Hermes", "原生 Hermes")}>
    <h3>{t("Native Hermes", "原生 Hermes")}</h3>
    <p>{t("Use the desktop app on the Mac running Hermes for this local connection. Remote gateway integration is separate.", "请在运行 Hermes 的 Mac 上使用桌面应用连接本地服务；远程网关集成将独立提供。")}</p>
  </section>;

  return <section className="hermes-native-panel" aria-label={t("Native Hermes", "原生 Hermes")} aria-busy={busy}>
    <header><div><p className="hermes-native-eyebrow">{t("LOCAL NATIVE RUNTIME", "本地原生运行时")}</p>
      <h3>Hermes <span>{runtime ? `v${runtime.version ?? "unknown"}` : t("Not connected", "未连接")}</span></h3></div>
      <button type="button" disabled={busy} onClick={() => void perform({ operation: "status" })}>
        {t("Connect local Hermes", "连接本地 Hermes")}</button></header>
    <p className="hermes-native-muted">{t("Your existing local conversations, one native runtime. Worker dispatch is not enabled by this connection.", "沿用本地会话与原生运行时；此连接不会启用工作代理调度。")}</p>
    <div className="hermes-native-actions">
      <label>{t("Conversation purpose", "会话用途")} <select value={role} disabled={busy || unresolved} onChange={event => setRole(event.target.value as typeof role)}>
        <option value="meta-ceo">Meta-CEO</option><option value="secretary">{t("Secretary", "秘书")}</option>
      </select></label>
      <button type="button" disabled={!runtime || busy || unresolved || pending} onClick={() => void perform({ operation: "create", role, requestId: requestId() })}>{t("New conversation", "新建会话")}</button>
      <button type="button" disabled={!runtime || busy} onClick={() => void perform({ operation: "list" })}>{t("Local history", "本地历史")}</button>
      {held && <button type="button" disabled={!runtime || busy} onClick={() => void checkPrevious()}>
        {t("Check previous request", "检查原请求")}</button>}
    </div>
    {notice && <div role="alert" className="hermes-native-notice">
      {notice === "AUTHENTICATION_CHANGED" ? t("Sign-in changed. The previous conversation is hidden; reconnect under your current sign-in.", "登录状态已更改。原会话已隐藏，请使用当前账号重新连接。")
        : notice === "EFFECT_UNKNOWN" ? t("Outcome unknown. Check the previous request before sending again.", "结果未知。请先检查原请求，再继续发送。")
        : notice === "NATIVE_NOT_SENT" || notice === "NOT_SENT" ? t("The request was not sent. Reconnect and try again when Hermes is available.", "请求尚未发送。请在 Hermes 可用后重新连接并重试。")
        : notice === "NATIVE_RECOVERY_UNAVAILABLE" ? t("Request recovery is unavailable. Sending is paused to protect the original request.", "原请求恢复暂不可用。为保护原请求，发送已暂停。")
        : notice === "NATIVE_IDENTITY_CHANGED" ? t("The local connection changed. Reconnect to check the original request.", "本地连接已更改，请重新连接并检查原请求。")
        : `${t("Native runtime response", "原生运行时响应")}: ${notice}`}
    </div>}
    {held && <p className="hermes-native-muted">{t("Original request", "原请求")}: <code>{held.requestId}</code></p>}
    {history && <nav className="hermes-native-history" aria-label={t("Local Hermes conversations", "本地 Hermes 会话")}>
      {history.length === 0 ? <p>{t("No local conversations returned.", "没有返回本地会话。")}</p> : history.map(row => <button key={row.id} type="button"
        disabled={busy || unresolved} onClick={() => { setReceipt(undefined); void perform({ operation: "read", sessionId: row.id }); }}>
        <span>{title(row.title)}</span><small>{row.running ? t("Running", "运行中") : `${row.messageCount} ${t("messages", "条消息")}`}</small></button>)}
    </nav>}
      {receipt && <p role="status" className="hermes-native-muted">{t("Native admission", "原生受理记录")}: <code>{receipt.id}</code> · {receipt.status}{receipt.outcome ? ` · ${receipt.outcome}` : ""}</p>}
    {receipt && !session && <button type="button" disabled={busy} onClick={() => void readOriginal()}>{t("Read original conversation", "读取原会话")}</button>}
    {session && <div className="hermes-native-conversation">
      <div className="hermes-native-session-heading"><h4>{title(session.title)}</h4>
        <button type="button" disabled={busy} onClick={() => void readOriginal()}>{t("Read original conversation", "读取原会话")}</button></div>
      <p className="hermes-native-muted">{t("Configured model", "已配置模型")}: {session.requestedModel || t("Not reported", "未提供")} · {
        session.toolAccess === "ADVISORY_READ_ONLY" ? t("Local planning advice and capacity previews", "本地规划建议与容量预览")
          : session.toolAccess === "CAPACITY_READ_ONLY" ? t("Capacity catalog and route preview only", "仅容量目录与路由预览")
          : session.toolAccess === "NONE" ? t("Text only", "仅文本")
          : originalUnsettledForSession ? t("Sending is paused until the original request’s outcome is confirmed.", "确认原请求的结果前，发送已暂停。")
          : session.sendCheckRequired ? t("Saved history · current send access is checked when you send", "已保存的历史 · 发送时检查当前权限")
          : receiptForSession?.status === "terminal" && !sendEligible ? t("Refresh the original conversation before sending again.", "请先刷新原会话，再继续发送。")
          : t("Tool scope not qualified for sending", "工具范围未确认，暂不可发送")}</p>
      <div className="hermes-native-messages" tabIndex={0} role="log" aria-label={t("Native conversation messages", "原生会话消息")} aria-live="polite">
        {session.historyTruncated && <p>{t("Showing the latest available messages, up to 100.", "显示最近可用的消息，最多 100 条。")}</p>}
        {session.messages.length === 0 && <p className="hermes-native-muted">{t("The native conversation is ready. Start with your question or project context.", "原生会话已就绪。请输入问题或项目背景。")}</p>}
        {session.messages.map((message, i) => <article key={`${session.id}:${i}`} data-speaker={message.role}>
          <strong>{message.role === "user" ? t("You", "你") : "Hermes"}</strong><p>{message.text}</p></article>)}
      </div>
      {unknownAdmission && <p role="alert">{t("The original native admission is unknown. Sending stays held until its owner resolves it.", "原生请求状态未知；解决原请求前暂停发送。")}</p>}
      {session.promptsPending && <p role="status">{t("A native prompt needs attention in Hermes. This client does not auto-approve it.", "Hermes 中有待处理提示；此客户端不会自动批准。")}</p>}
      <label className="hermes-native-composer">{t("Message Hermes", "发送给 Hermes")}
        <textarea value={draft} rows={4} disabled={busy || unresolved || !sendEligible}
          onChange={event => setDraft(event.target.value)} placeholder={t("What should we work through?", "要讨论什么？")} /></label>
      <div className="hermes-native-send-row"><small>{t("The message is sent exactly as written. No automatic resend.", "按原文发送，不自动重试。")}</small>
        <button type="button" disabled={!canSend} onClick={async () => {
          const result = await perform({ operation: "send", sessionId: session.id, requestId: requestId(), text: draft });
          if (result?.state === "ADMITTED" && result.receipt?.status === "terminal") await perform({ operation: "read", sessionId: session.id });
        }}>{busy ? t("Working…", "处理中…") : session.sendCheckRequired ? t("Check and send message", "检查并发送消息") : t("Send message", "发送消息")}</button></div>
    </div>}
  </section>;
}
