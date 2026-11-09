import { useState } from "react";
import type { TerminalSharingSource } from "../terminal/terminal-sharing-host";
import { BriefSharingInbox } from "./BriefSharingInbox";
import { useTerminalSharing } from "./use-terminal-sharing";

/** The Terminal session is separate from the shell's Auth0 grants and Mission context. */
export function TerminalSharingInbox({ host, locale }: {
  host?: TerminalSharingSource;
  locale: "en" | "zh-CN";
}) {
  const sharing = useTerminalSharing(host ?? null, true);
  const [connecting, setConnecting] = useState(false);
  const zh = locale === "zh-CN";
  const session = sharing.session;
  const canConnect = !!host && (session?.state === "SIGNED_OUT" || session?.state === "ERROR")
    && !["NOT_CONFIGURED", "INVALID_CONFIG", "SERVICE_KEY_REFUSED"].includes(session?.reason ?? "");
  const connect = async () => {
    if (!canConnect || connecting) return;
    setConnecting(true);
    try { await sharing.onConnect?.(); }
    catch { /* The private owner exposes only its closed public state. */ }
    finally { setConnecting(false); }
  };
  return <section aria-label={zh ? "Terminal 简报请求" : "Terminal brief requests"}>
    {canConnect && <button type="button" disabled={connecting} onClick={() => { void connect(); }}>
      {connecting ? (zh ? "正在连接 Terminal…" : "Connecting to Terminal…")
        : (zh ? "连接 Terminal" : "Connect Terminal")}
    </button>}
    {session?.state === "SIGNING_IN" && <button type="button" onClick={() => {
      void sharing.onDisconnect().catch(() => {});
    }}>{zh ? "取消 Terminal 连接" : "Cancel Terminal connection"}</button>}
    <BriefSharingInbox key={JSON.stringify([session?.generation ?? null,
      session?.principal_scope ?? null, session?.session_scope ?? null])}
      locale={locale} state={sharing.state} requests={sharing.requests}
      onReview={sharing.onReview} sourceDetails={<>
    <p className="inbox-muted">{zh
      ? "Terminal 使用独立的账户连接。工作区登录不代表已获得简报访问权限。"
      : "Terminal uses a separate connection. Workspace sign-in does not establish brief access."}</p>
    {session?.state === "SIGNED_IN" && <button type="button" onClick={() => {
      void sharing.onDisconnect?.().catch(() => {});
    }}>{zh ? "断开此应用的 Terminal 连接" : "Disconnect Terminal from this app"}</button>}
      </>} />

  </section>;
}
