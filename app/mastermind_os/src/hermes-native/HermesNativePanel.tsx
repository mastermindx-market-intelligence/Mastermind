import { useCallback, useEffect, useRef, useState } from "react";
import type { NativeHermesPort, NativeOperation, NativeReceipt, NativeSession, NativeView } from "./contract";
import { nativeHermesPort } from "./native-port";
import type { NativePendingOperation } from "./pending-pointer";
import { HermesChatView } from "./HermesChatView";
import type { NativeLiveFrame } from "./live-stream";
import { registerUnsavedNavigationHold } from "../auth-navigation-guard";
import "./chat-view.css";

const beforeDispatch = new Set(["REQUEST_INVALID", "NATIVE_BUSY", "NATIVE_INSTALL_UNAVAILABLE", "NATIVE_PLATFORM_UNAVAILABLE", "NATIVE_CLIENT_NOT_STARTED", "NATIVE_AUTH_NOT_DISPATCHED"]);
const knownErrors = new Set([...beforeDispatch, "NATIVE_RECOVERY_UNAVAILABLE", "AUTHENTICATION_CHANGED", "NATIVE_IDENTITY_CHANGED", "NATIVE_RECOVERY_REQUIRED", "NATIVE_RESPONSE_INVALID", "NATIVE_CLIENT_UNAVAILABLE"]);
function requestId(): string { return crypto.randomUUID().replaceAll("-", ""); }
function originalPointer(request: NativeOperation): NativePendingOperation | null {
  return request.operation === "create" ? { kind: "create", requestId: request.requestId }
    : request.operation === "send" ? { kind: "send", requestId: request.requestId, sessionId: request.sessionId } : null;
}

/** Local native conversation only. A future qualified backend implements the same port. */
export function HermesNativePanel({ locale, port = nativeHermesPort, visible = true }: { locale: string; port?: NativeHermesPort; visible?: boolean }) {
  const zh = locale.toLowerCase().startsWith("zh");
  const t = (en: string, cn: string) => zh ? cn : en;
  const [runtime, setRuntime] = useState<NativeView["runtime"]>();
  const [session, setSession] = useState<NativeSession>();
  const [history, setHistory] = useState<NativeView["sessions"]>();
  const [receipt, setReceipt] = useState<NativeReceipt>();
  const [role, setRole] = useState<"meta-ceo" | "secretary">("meta-ceo");
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [pendingText, setPendingText] = useState<string>();
  const [live, setLive] = useState<NativeLiveFrame>();
  const [liveStatus, setLiveStatus] = useState<"connecting" | "live" | "interrupted">();
  const [watching, setWatching] = useState(false);
  const [notice, setNotice] = useState("");
  const [held, setHeld] = useState<NativePendingOperation | null>(null);
  const heldRef = useRef<NativePendingOperation | null>(null);
  // Private, component-local draft cleanup only; never stored as an effect record.
  const submittedDraft = useRef<{ requestId: string; text: string } | null>(null);
  const pendingProjection = useRef(false);
  const generation = useRef<number | undefined>(undefined);
  const inFlight = useRef(false);
  const mounted = useRef(true);
  const pollCount = useRef(0);
  const stopAutomatic = useRef(false);
  const stopAttempt = useRef<string | null>(null);
  const connectedOnce = useRef(false);
  useEffect(() => registerUnsavedNavigationHold(() => draft.length > 0), [draft]);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  const clearPrivate = useCallback(() => {
    setRuntime(undefined); setSession(undefined); setHistory(undefined); setReceipt(undefined); setDraft("");
    heldRef.current = null; setHeld(null); submittedDraft.current = null;
    pendingProjection.current = false;
    generation.current = undefined; stopAutomatic.current = true; stopAttempt.current = null; setPendingText(undefined);
    setLive(undefined); setLiveStatus(undefined); setWatching(false);
  }, []);

  const perform = useCallback(async (request: NativeOperation): Promise<NativeView | undefined> => {
    const mutating = request.operation === "send" || request.operation === "create";
    if (inFlight.current || (mutating && heldRef.current)) return;
    const originalHeld = heldRef.current;
    if (request.operation === "send") {
      submittedDraft.current = { requestId: request.requestId, text: request.text };
      pendingProjection.current = true;
      setPendingText(request.text);
      setLive(undefined); setLiveStatus(undefined);
    }
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
        const next = result.pendingOperation;
        if (next && request.operation !== "send" && request.operation !== "create" &&
          (!originalHeld || next.kind !== originalHeld.kind || next.requestId !== originalHeld.requestId ||
            next.kind === "send" && originalHeld.kind === "send" && next.sessionId !== originalHeld.sessionId)) {
          setReceipt(undefined); setLive(undefined); setPendingText(undefined);
          submittedDraft.current = null; pendingProjection.current = false;
        }
        heldRef.current = result.pendingOperation; setHeld(result.pendingOperation);
        if (result.pendingOperation && result.state === "READY") {
          stopAutomatic.current = true; setNotice("EFFECT_UNKNOWN");
        }
      }
      if (result.runtime) setRuntime(result.runtime);
      if (result.session) {
        const observed = result.session;
        // Mid-turn history lacks submission IDs. Preserve the previous transcript
        // until the original settles, instead of deduplicating identical text.
        setSession(previous => request.operation === "read" && result.pendingOperation?.kind === "send" &&
          previous && previous.id === observed.id && result.pendingOperation.sessionId === observed.id && pendingProjection.current
          ? { ...observed, messages: previous.messages, messageCount: previous.messageCount } : observed);
        // Only the original settled history replaces the optimistic projection.
        if (request.operation === "read" && !result.pendingOperation &&
            !result.session.pending.some(item => item.status !== "terminal")) {
          setPendingText(undefined); setLive(undefined); setLiveStatus(undefined); submittedDraft.current = null; pendingProjection.current = false;
        }
      }
      if (result.sessions) setHistory(result.sessions);
      const crossedPending = result.pendingOperation && originalHeld &&
        (result.pendingOperation.kind !== originalHeld.kind || result.pendingOperation.requestId !== originalHeld.requestId) &&
        result.requestId !== result.pendingOperation.requestId;
      if (result.receipt && !crossedPending) setReceipt(result.receipt);
      if (result.state === "OPENED") { setReceipt(undefined); setDraft(""); setPendingText(undefined); submittedDraft.current = null; pendingProjection.current = false; pollCount.current = 0; stopAutomatic.current = false; }
      if (result.state === "ADMITTED") {
        const acceptedDraft = request.operation === "send" ? { requestId: request.requestId, text: request.text }
          : (request.operation === "recover" || request.operation === "stop") && originalHeld?.kind === "send" && submittedDraft.current?.requestId === originalHeld.requestId
            ? submittedDraft.current : null;
        if (acceptedDraft) {
          setDraft(value => value === acceptedDraft.text ? "" : value);
          submittedDraft.current = null;
        }
        if (request.operation === "send") pollCount.current = 0;
        // A receipt settles only this admission. Refresh history before reusing send eligibility.
        if (request.operation === "recover" || request.operation === "stop") setSession(previous => previous && result.receipt &&
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
        if (mutating && result.pendingOperation == null) { setPendingText(undefined); pendingProjection.current = false; }
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
      } else { setNotice(code); if (mutating && beforeDispatch.has(code)) setPendingText(undefined); }
    } finally {
      inFlight.current = false;
      if (mounted.current) setBusy(false);
    }
  }, [port, clearPrivate]);

  // Read-only automatic attachment in the installed desktop client. Opening the
  // page never creates a session, sends a prompt, retries or recovers an effect.
  useEffect(() => {
    if (port !== nativeHermesPort || !port.available() || connectedOnce.current) return;
    connectedOnce.current = true;
    void perform({ operation: "status" });
  }, [port, perform]);

  const liveAdmission = receipt && ["queued", "started"].includes(receipt.status) ? receipt.id : undefined;
  const liveSession = receipt?.sessionId;
  const authorityEpoch = runtime?.authorityEpoch;
  useEffect(() => {
    if (!visible || !port.observe || !liveAdmission || !liveSession || authorityEpoch === undefined) return;
    let active = true;
    let renderFrame = 0;
    let latest: NativeLiveFrame | undefined;
    setWatching(true); setLiveStatus("connecting");
    const flush = () => {
      renderFrame = 0;
      if (active && latest) { setLive(latest); setLiveStatus(latest.state === "interrupted" ? "interrupted" : "live"); }
    };
    const dispose = port.observe({ sessionId: liveSession, admissionId: liveAdmission, authorityEpoch,
      executionGeneration: receipt?.executionGeneration ?? null }, frame => {
      if (!active) return;
      latest = frame;
      if (!renderFrame) renderFrame = window.requestAnimationFrame(flush);
      if (frame.state !== "live") setWatching(false);
      if (frame.state === "complete") {
        if (renderFrame) { window.cancelAnimationFrame(renderFrame); renderFrame = 0; }
        flush();
        // The stream never clears the durable pointer. Reconcile the original
        // receipt through its existing owner, then replace with canonical history.
        void perform(heldRef.current ? { operation: "recover" }
          : { operation: "receipt", sessionId: liveSession, admissionId: liveAdmission }).then(async result => {
          if (mounted.current && result?.receipt?.status === "terminal") await perform({ operation: "read", sessionId: liveSession });
        });
      }
    }, code => {
      if (!active) return;
      setWatching(false); setLiveStatus("interrupted");
      if (code === "AUTHENTICATION_CHANGED") { clearPrivate(); setNotice(code); }
    });
    return () => { active = false; dispose(); if (renderFrame) window.cancelAnimationFrame(renderFrame); setWatching(false); };
    // One observer per original admission, not a fresh observer for each receipt
    // poll or execution-generation update. The port binds the native generation.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [port, liveAdmission, liveSession, authorityEpoch, visible, perform, clearPrivate]);

  // This is a bounded read of the original admission while this panel is open,
  // not a background model loop, scheduler, retry, or second runtime owner.
  const activeAdmission = receipt && ["queued", "started"].includes(receipt.status) ? receipt.id
    : session?.pending.find(row => ["queued", "started"].includes(row.status))?.id;
  useEffect(() => {
    if (!visible || watching || (!session && !receipt) || !activeAdmission || busy || stopAutomatic.current) return;
    if (pollCount.current >= 30) { setLiveStatus("interrupted"); return; }
    const original = receipt?.sessionId ?? session!.id;
    const timer = window.setTimeout(async () => {
      pollCount.current += 1;
      const result = await perform(heldRef.current ? { operation: "recover" }
        : { operation: "receipt", sessionId: original, admissionId: activeAdmission });
      if (result?.receipt?.status === "terminal" && mounted.current) await perform({ operation: "read", sessionId: original });
    }, 2000);
    return () => window.clearTimeout(timer);
  }, [session, activeAdmission, busy, held, receipt, perform, visible, watching]);

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
  const stopOriginal = async () => {
    const original = held;
    const current = heldRef.current;
    if (original?.kind !== "send" || current?.kind !== "send" || original.requestId !== current.requestId ||
      original.sessionId !== current.sessionId || original.stopReserved || stopAttempt.current === original.requestId || inFlight.current) return;
    stopAttempt.current = original.requestId;
    stopAutomatic.current = true;
    const result = await perform({ operation: "stop", sessionId: original.sessionId, requestId: original.requestId });
    if (result?.receipt?.status === "terminal") {
      await perform({ operation: "read", sessionId: result.receipt.sessionId });
    }
  };
  const canStop = held?.kind === "send" && receipt && receipt.sessionId === held.sessionId &&
    ["queued", "started"].includes(receipt.status) && !held.stopReserved && stopAttempt.current !== held.requestId && !busy;
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

  const visibleNotice = notice === "AUTHENTICATION_CHANGED" ? t("Sign-in changed. The previous conversation is hidden; reconnect under your current sign-in.", "登录状态已更改。原会话已隐藏，请使用当前账号重新连接。")
    : notice === "EFFECT_UNKNOWN" ? t("Outcome unknown. Check the previous request before sending again.", "结果未知。请先检查原请求，再继续发送。")
    : notice === "NATIVE_NOT_SENT" || notice === "NOT_SENT" ? t("The request was not sent. Reconnect and try again when Hermes is available.", "请求尚未发送。请在 Hermes 可用后重新连接并重试。")
    : notice === "NATIVE_RECOVERY_UNAVAILABLE" ? t("Request recovery is unavailable. Sending is paused to protect the original request.", "原请求恢复暂不可用。为保护原请求，发送已暂停。")
    : notice === "NATIVE_IDENTITY_CHANGED" ? t("The local connection changed. Reconnect to check the original request.", "本地连接已更改，请重新连接并检查原请求。")
    : notice ? `${t("Native runtime response", "原生运行时响应")}: ${notice}` : "";
  return <HermesChatView locale={locale} runtime={runtime} session={session} history={history} receipt={receipt}
    role={role} draft={draft} busy={busy} notice={visibleNotice} held={held} pending={pending}
    canSend={canSend} canStop={Boolean(canStop)} sendEligible={sendEligible} unknownAdmission={Boolean(unknownAdmission)}
    originalUnsettledForSession={originalUnsettledForSession}
    pendingText={pendingText} liveText={live?.text} liveStatus={liveStatus} liveActivity={live?.activity} onRole={setRole} onDraft={setDraft}
    onConnect={() => void perform({ operation: "status" })}
    onCreate={() => void perform({ operation: "create", role, requestId: requestId() })}
    onHistory={() => void perform({ operation: "list" })}
    onSelect={sessionId => { setReceipt(undefined); setPendingText(undefined); setLive(undefined); setLiveStatus(undefined); void perform({ operation: "read", sessionId }); }}
    onRead={() => void readOriginal()} onRecover={() => void checkPrevious()} onStop={() => void stopOriginal()}
    onSend={() => {
      if (!session || !canSend) return;
      const original = session.id;
      void perform({ operation: "send", sessionId: original, requestId: requestId(), text: draft }).then(async result => {
        if (result?.state === "ADMITTED" && result.receipt?.status === "terminal") await perform({ operation: "read", sessionId: original });
      });
    }} />;
}
