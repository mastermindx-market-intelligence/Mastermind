import { memo, useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import type { NativeReceipt, NativeSession, NativeView } from "./contract";
import type { NativePendingOperation } from "./pending-pointer";
import { ObservedResponseMarkdown } from "../conversations/ObservedResponseMarkdown";
import { observeComposition } from "../vendor/deepseek/keyboard-composition";
import { scrollMetrics, useScrollFollow } from "../vendor/deepseek/use-scroll-follow";

function Icon({ name }: { name: "send" | "stop" | "history" | "new" | "refresh" | "down" | "close" | "search" }) {
  const paths: Record<typeof name, ReactNode> = {
    send: <><path d="M12 19V5m-6 6 6-6 6 6" /></>,
    stop: <rect x="6" y="6" width="12" height="12" rx="2" fill="currentColor" stroke="none" />,
    history: <><path d="M9 4H5a1 1 0 0 0-1 1v14a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1V5a1 1 0 0 0-1-1H9v16" /><path d="M13 8h4m-4 4h4" /></>,
    new: <><path d="M12 5v14M5 12h14" /></>,
    refresh: <><path d="M20 10a8 8 0 1 0-2 8M20 4v6h-6" /></>,
    down: <><path d="M12 5v14m-6-6 6 6 6-6" /></>,
    close: <><path d="m6 6 12 12M6 18 18 6" /></>,
    search: <><circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 4 4" /></>,
  };
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]}</svg>;
}

export function conversationTitle(value: string) {
  return value.replace(/ · [a-f0-9]{32}$/, "") || "Untitled conversation";
}

export interface HermesChatViewProps {
  locale: string;
  runtime: NativeView["runtime"];
  session?: NativeSession;
  history: NativeView["sessions"];
  receipt?: NativeReceipt;
  role: "meta-ceo" | "secretary";
  draft: string;
  busy: boolean;
  notice: string;
  held: NativePendingOperation | null;
  pending: boolean;
  canSend: boolean;
  canStop: boolean;
  sendEligible: boolean;
  unknownAdmission: boolean;
  originalUnsettledForSession: boolean;
  pendingText?: string;
  liveText?: string;
  liveStatus?: "connecting" | "live" | "interrupted";
  liveActivity?: "working" | "responding" | "tool";
  onRole: (role: "meta-ceo" | "secretary") => void;
  onDraft: (value: string) => void;
  onConnect: () => void;
  onCreate: () => void;
  onHistory: () => void;
  onRead: () => void;
  onSelect: (sessionId: string) => void;
  onRecover: () => void;
  onSend: () => void;
  onStop: () => void;
}

const Message = memo(function Message({ role, text, streaming = false, locale, viewport }: {
  role: "user" | "assistant"; text: string; streaming?: boolean; locale: "en" | "zh-CN";
  viewport: React.RefObject<HTMLDivElement | null>;
}) {
  return <article className="hermes-chat-message" data-speaker={role}>
    <div className="hermes-chat-avatar" aria-hidden="true">{role === "assistant" ? "H" : locale === "zh-CN" ? "你" : "Y"}</div>
    <div className="hermes-chat-message-body">
      <strong>{role === "assistant" ? "Hermes" : locale === "zh-CN" ? "你" : "You"}</strong>
      {role === "user" ? <p>{text}</p> : <ObservedResponseMarkdown source={text} streaming={streaming} locale={locale} viewport={viewport} />}
    </div>
  </article>;
});

/** A presentation of the incumbent native controller, never a message or session store. */
export function HermesChatView(props: HermesChatViewProps) {
  const { session, runtime, history, receipt, held, pending, busy, draft } = props;
  const zh = props.locale.toLowerCase().startsWith("zh");
  const locale = zh ? "zh-CN" : "en";
  const t = (en: string, cn: string) => zh ? cn : en;
  const [historyOpen, setHistoryOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [following, setFollowing] = useState(true);
  const viewport = useRef<HTMLDivElement>(null);
  const composer = useRef<HTMLTextAreaElement>(null);
  const historyToggle = useRef<HTMLButtonElement>(null);
  const historySearch = useRef<HTMLInputElement>(null);
  const composition = useRef<ReturnType<typeof observeComposition> | null>(null);
  const follow = useScrollFollow(true, 72);
  const previousSession = useRef(session?.id);
  const unresolved = Boolean(held || props.unknownAdmission);
  const receiptForSession = receipt && session && [session.id, session.storedId].includes(receipt.sessionId) ? receipt : undefined;
  const scopeDescription = session?.toolAccess === "ADVISORY_READ_ONLY" ? t("Local planning advice and capacity previews", "本地规划建议与容量预览")
    : session?.toolAccess === "CAPACITY_READ_ONLY" ? t("Capacity catalog and route preview only", "仅容量目录与路由预览")
    : session?.toolAccess === "NONE" ? t("Text only", "仅文本")
    : props.originalUnsettledForSession ? t("Sending is paused until the original request’s outcome is confirmed.", "确认原请求的结果前，发送已暂停。")
    : session?.sendCheckRequired ? t("Saved history · current send access is checked when you send", "已保存的历史 · 发送时检查当前权限")
    : receiptForSession?.status === "terminal" && !props.sendEligible ? t("Refresh the original conversation before sending again.", "请先刷新原会话，再继续发送。")
    : t("Tool scope not qualified for sending", "工具范围未确认，暂不可发送");
  const stopVisible = held?.kind === "send" && receipt && receipt.sessionId === held.sessionId && ["queued", "started"].includes(receipt.status);

  useEffect(() => {
    composition.current = observeComposition(document);
    return () => { composition.current?.dispose(); composition.current = null; };
  }, []);
  useLayoutEffect(() => {
    const input = composer.current;
    if (!input) return;
    input.style.height = "auto";
    input.style.height = `${Math.min(180, Math.max(44, input.scrollHeight))}px`;
  }, [draft, session?.id]);
  useLayoutEffect(() => {
    const element = viewport.current;
    if (!element) return;
    if (previousSession.current !== session?.id) {
      previousSession.current = session?.id;
      follow.setFollowing(true);
    }
    if (follow.active) {
      follow.toBottom(element, scrollMetrics(element), "instant");
      setFollowing(true);
    }
  }, [session?.id, session?.messages, props.pendingText, props.liveText, pending, follow]);
  useEffect(() => {
    const element = viewport.current;
    if (!element) return;
    const unbind = follow.bind(element);
    const content = element.firstElementChild;
    const observer = typeof ResizeObserver !== "undefined" ? new ResizeObserver(() => {
      if (follow.active) follow.toBottom(element, scrollMetrics(element), "instant");
    }) : null;
    if (content) observer?.observe(content);
    return () => { unbind(); observer?.disconnect(); };
  }, [session?.id, follow]);
  useEffect(() => { if (historyOpen) historySearch.current?.focus(); }, [historyOpen]);
  const closeHistory = () => { setHistoryOpen(false); historyToggle.current?.focus(); };
  const send = () => { if (props.canSend) { follow.setFollowing(true); props.onSend(); composer.current?.focus(); } };
  const matches = history?.filter(row => conversationTitle(row.title).toLocaleLowerCase().includes(search.toLocaleLowerCase()));
  const activity = props.liveStatus === "interrupted" ? t("Live updates paused", "实时更新已暂停")
    : held?.kind === "send" && held.stopReserved ? t("Checking Stop…", "正在确认停止…")
    : props.liveActivity === "tool" ? t("Using a tool…", "正在使用工具…")
    : props.liveText ? t("Replying…", "正在回复…")
    : pending ? t("Hermes is working…", "Hermes 正在处理…")
    : busy ? t("Connecting…", "正在连接…") : runtime ? t("Connected", "已连接") : t("Not connected", "未连接");

  return <section className="hermes-native-panel hermes-chat" aria-label={t("Native Hermes", "原生 Hermes")} aria-busy={busy} data-history-open={historyOpen}>
    <header className="hermes-chat-header">
      <button ref={historyToggle} className="hermes-chat-icon-button" type="button" aria-label={t("Local history", "本地历史")} aria-expanded={historyOpen}
        onClick={() => { if (historyOpen) closeHistory(); else { setHistoryOpen(true); if (runtime && !busy) props.onHistory(); } }}><Icon name="history" /></button>
      <div className="hermes-chat-heading"><h3>{session ? conversationTitle(session.title) : t("Your workspace", "你的工作空间")}</h3>
        <span><span className="hermes-chat-presence" data-connected={Boolean(runtime)} />Hermes <span aria-hidden="true">·</span> {activity}</span></div>
      <button className="hermes-chat-icon-button" type="button" disabled={busy} aria-label={t("Connect local Hermes", "连接本地 Hermes")} onClick={props.onConnect}><Icon name="refresh" /></button>
      <button className="hermes-chat-new" type="button" aria-label={t("New conversation", "新建会话")} disabled={!runtime || busy || unresolved || pending} onClick={props.onCreate}><Icon name="new" /><span>{t("New conversation", "新建会话")}</span></button>
    </header>
    <div className="hermes-chat-workspace">
      {historyOpen && <aside className="hermes-chat-history" aria-label={t("Local Hermes conversations", "本地 Hermes 会话")} onKeyDown={e => { if (e.key === "Escape") closeHistory(); }}>
        <div className="hermes-chat-history-heading"><strong>{t("Conversations", "会话")}</strong><button type="button" className="hermes-chat-icon-button" aria-label={t("Close history", "关闭历史")} onClick={closeHistory}><Icon name="close" /></button></div>
        <label className="hermes-chat-search"><Icon name="search" /><input ref={historySearch} value={search} onChange={e => setSearch(e.target.value)} placeholder={t("Search conversations", "搜索会话")} aria-label={t("Search conversations", "搜索会话")} /></label>
        <nav className="hermes-chat-history-list">{matches?.map(row => <button key={row.id} type="button" aria-current={session && [session.id, session.storedId].includes(row.id) ? "true" : undefined}
          disabled={busy || unresolved || pending} onClick={() => { props.onSelect(row.id); closeHistory(); }}>
          <span>{conversationTitle(row.title)}</span><small>{row.running ? t("Working", "处理中") : `${row.messageCount} ${t("messages", "条消息")}`}</small>
        </button>)}</nav>
        {matches?.length === 0 && <p>{search ? t("No matching conversations.", "没有匹配的会话。") : t("No local conversations returned.", "没有返回本地会话。")}</p>}
        {!history && <p>{runtime ? t("Loading conversations…", "正在加载会话…") : t("Connect Hermes to see your conversations.", "连接 Hermes 后即可查看会话。")}</p>}
      </aside>}
      <div className="hermes-chat-main">
        {props.notice && <div role="alert" className="hermes-chat-notice">{props.notice}</div>}
        <div ref={viewport} className="hermes-chat-transcript" role="log" aria-label={t("Native conversation messages", "原生会话消息")} aria-live="off" tabIndex={0}
          onScroll={event => setFollowing(follow.sample(scrollMetrics(event.currentTarget)))}
          onWheel={event => follow.interrupt(event.currentTarget, scrollMetrics(event.currentTarget))}
          onTouchStart={event => follow.interrupt(event.currentTarget, scrollMetrics(event.currentTarget))}>
          <div className="hermes-chat-reading-column">
            {!session && <div className="hermes-chat-welcome"><div className="hermes-chat-welcome-mark" aria-hidden="true">H</div>
              <p className="hermes-chat-kicker">{t("Your local workspace", "你的本地工作空间")}</p>
              <h2>{t("What are we working on?", "今天一起做什么？")}</h2>
              <p>{runtime ? t("Start a conversation, or pick up where you left off.", "开始新会话，或继续上次的讨论。") : t("Connect to your local Hermes to get started.", "连接本地 Hermes 即可开始。")}</p>
              {!runtime && <button type="button" disabled={busy} onClick={props.onConnect}>{t("Connect Hermes", "连接 Hermes")}</button>}
            </div>}
            {session?.historyTruncated && <p className="hermes-chat-history-limit">{t("Showing the latest available messages, up to 100.", "显示最近可用的消息，最多 100 条。")}</p>}
            {session && session.messages.length === 0 && !props.pendingText && <div className="hermes-chat-welcome"><div className="hermes-chat-welcome-mark" aria-hidden="true">H</div><h2>{t("Let's work through it.", "一起理清思路。")}</h2><p>{t("Ask a question. Share an idea. Start something.", "提出问题，分享想法，开始行动。")}</p></div>}
            {session?.messages.map((message, i) => <Message key={`${session.storedId}:${session.messageCount - session.messages.length + i}`} {...message} locale={locale} viewport={viewport} />)}
            {props.pendingText && <div data-pending-message="true"><Message role="user" text={props.pendingText} locale={locale} viewport={viewport} /><small className="hermes-chat-pending-label">{held && props.notice ? t("Checking delivery", "正在确认发送状态") : receipt ? t("Sent", "已发送") : t("Sending…", "发送中…")}</small></div>}
            {props.liveText && <Message role="assistant" text={props.liveText} streaming locale={locale} viewport={viewport} />}
            {(pending || props.pendingText) && !props.liveText && <div className="hermes-chat-activity" aria-hidden="true"><span /><span /><span />{activity}</div>}
          </div>
        </div>
        {!following && session && <button className="hermes-chat-jump" type="button" onClick={() => { const node = viewport.current; if (node) { follow.toBottom(node, scrollMetrics(node), "smooth"); setFollowing(true); } }}><Icon name="down" />{t("Jump to latest", "查看最新消息")}</button>}
        <div className="hermes-chat-status" role="status" aria-live="polite">{pending ? activity : ""}</div>
        <footer className="hermes-chat-footer">
          {props.unknownAdmission && <p role="alert" className="hermes-chat-recovery">{t("The original native admission is unknown. Sending stays held until its owner resolves it.", "原生请求状态未知；解决原请求前暂停发送。")}</p>}
          {held && (!pending || props.notice || props.liveStatus === "interrupted" || held.kind === "send" && held.stopReserved) && <div className="hermes-chat-recovery"><span>{held.kind === "send" && held.stopReserved ? t("Stop outcome is not confirmed. Check the original request before continuing.", "停止结果尚未确认。请先检查原请求，再继续。") : props.liveStatus === "interrupted" ? t("Live updates paused. Check the original conversation to continue.", "实时更新已暂停。请检查原会话以继续。") : t("Check the previous request before sending again.", "请先检查原请求，再继续发送。")}</span><button type="button" disabled={!runtime || busy} onClick={props.onRecover}>{t("Check previous request", "检查原请求")}</button></div>}
          {session?.promptsPending && <p role="status">{t("A native prompt needs attention in Hermes. This client does not auto-approve it.", "Hermes 中有待处理提示；此客户端不会自动批准。")}</p>}
          {session?.toolAccess === "UNQUALIFIED" && <p className="hermes-chat-scope" role="status">{scopeDescription}</p>}
          {session && <div className="hermes-chat-composer">
            <label className="hermes-chat-sr-only" htmlFor="hermes-chat-message">{t("Message Hermes", "发送给 Hermes")}</label>
            <textarea id="hermes-chat-message" ref={composer} rows={1} value={draft} onChange={e => props.onDraft(e.target.value)}
              placeholder={t("Message Hermes…", "发送消息给 Hermes…")} onKeyDown={event => {
                if (event.key === "Enter" && !event.shiftKey && !event.altKey && !composition.current?.guards(event.nativeEvent)) { event.preventDefault(); send(); }
              }} />
            <div className="hermes-chat-composer-toolbar"><span>{session.requestedModel || "Hermes"}</span><span className="hermes-chat-key-hint">{t("Enter to send", "Enter 发送")}</span>
              {stopVisible ? <button className="hermes-chat-send" type="button" disabled={!props.canStop} aria-label={t("Stop generation", "停止生成")} onClick={props.onStop}><Icon name="stop" /></button>
                : <button className="hermes-chat-send" type="button" disabled={!props.canSend} aria-label={session.sendCheckRequired ? t("Check and send message", "检查并发送消息") : t("Send message", "发送消息")} onClick={send}><Icon name="send" /></button>}
            </div>
          </div>}
          <div className="hermes-chat-footer-tools"><details className="hermes-chat-details"><summary>{t("Connection details", "连接详情")}</summary>
            <div><p>Hermes {runtime?.version ? `v${runtime.version}` : t("Not connected", "未连接")}</p>
              <label>{t("Conversation purpose", "会话用途")} <select value={props.role} disabled={busy || unresolved || pending} onChange={e => props.onRole(e.target.value as typeof props.role)}><option value="meta-ceo">Meta-CEO</option><option value="secretary">{t("Secretary", "秘书")}</option></select></label>
              {session && <p>{t("Configured model", "已配置模型")}: {session.requestedModel || t("Not reported", "未提供")} · {session.toolAccess === "UNQUALIFIED" ? null : scopeDescription}</p>}
              {receipt && <p>{t("Native admission", "原生受理记录")}: <code>{receipt.id}</code> · {receipt.status}{receipt.outcome ? ` · ${receipt.outcome}` : ""}</p>}
              {held && <p>{t("Original request", "原请求")}: <code>{held.requestId}</code></p>}
              <p>{t("The message is sent exactly as written. No automatic resend.", "按原文发送，不自动重试。")}</p>
              <p>{t("Worker dispatch is not enabled by this connection.", "此连接不会启用工作代理调度。")}</p>
            </div></details>
            {(session || receipt) && <button type="button" className="hermes-chat-text-button" disabled={busy} onClick={props.onRead} aria-label={t("Read original conversation", "读取原会话")}>{t("Refresh conversation", "刷新会话")}</button>}
          </div>
        </footer>
      </div>
    </div>
  </section>;
}
