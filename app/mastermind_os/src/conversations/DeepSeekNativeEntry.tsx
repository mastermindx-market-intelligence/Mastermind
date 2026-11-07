import { useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";

/** Open the complete incumbent native application; never proxy its messages. */
export function DeepSeekNativeEntry({ locale = "en" }: { locale?: string }) {
  const zh = locale.startsWith("zh");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const opening = useRef(false);
  const open = async () => {
    if (opening.current) return;
    opening.current = true; setBusy(true); setNotice("");
    try {
      const result = await invoke<{ state: string; window_label: string }>("open_deepseek_chat");
      if (result.state !== "OPENED" || result.window_label !== "deepseek-chat") throw new Error("NATIVE_CHAT_WINDOW_UNAVAILABLE");
      setNotice(zh ? "DeepSeek 聊天窗口已打开。" : "DeepSeek is open in its chat window.");
    } catch (error) {
      const code = typeof error === "string" ? error : error instanceof Error ? error.message : "";
      setNotice(code === "NATIVE_CHAT_SIGN_IN_REQUIRED" || code === "AUTHENTICATION_CHANGED"
        ? zh ? "请先登录 Mastermind OS，再打开 DeepSeek。" : "Sign in to Mastermind OS, then open DeepSeek."
        : zh ? "DeepSeek 窗口暂时无法打开。" : "The DeepSeek window could not be opened.");
    } finally { opening.current = false; setBusy(false); }
  };
  return <section className="native-chat-entry" aria-label={zh ? "DeepSeek 原生聊天" : "DeepSeek native chat"}>
    <div className="native-chat-entry-mark" aria-hidden="true">D</div>
    <h2>{zh ? "与 DeepSeek 一起工作" : "Work with DeepSeek"}</h2>
    <p>{zh ? "在专属窗口继续你的对话，使用 DeepSeek 原有的模型、实时回复和历史记录。" : "Continue in its dedicated window, with DeepSeek’s models, live replies, and conversation history."}</p>
    <button type="button" disabled={busy} onClick={() => void open()}>{busy ? zh ? "正在打开…" : "Opening…" : zh ? "打开 DeepSeek" : "Open DeepSeek"}</button>
    <p className="native-chat-entry-note">{zh ? "首次连接需要完成原生应用登录。" : "The first connection requires the native application’s sign-in."}</p>
    {notice && <p role="status">{notice}</p>}
  </section>;
}
