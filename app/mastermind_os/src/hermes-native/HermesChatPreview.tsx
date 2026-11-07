/** Development-only interaction fixture. Never imported by the application and
 * never a provider/runtime acceptance receipt. Use the explicit event buttons. */
import { useState } from "react";
import { createRoot } from "react-dom/client";
import { HermesNativePanel } from "./HermesNativePanel";
import type { NativeHermesPort, NativeReceipt, NativeSession, NativeView } from "./contract";
import type { NativeLiveFrame } from "./live-stream";
import "../styles.css";
import "../meta-ceo/workspace.css";

if (!import.meta.env.DEV) throw new Error("INTERACTION_FIXTURE_DEVELOPMENT_ONLY");
const runtime = { protocol: 1 as const, instanceId: "fixture", authorityEpoch: 1, version: "0.23.0", sourceRevision: null };
const view = (extra: Partial<NativeView> = {}): NativeView => ({ schema: "mastermind.hermes_native_view.v1", state: "READY", authGeneration: 1,
  capabilities: [], delegation: "NOT_ENABLED", retryAllowed: false, runtime, ...extra });
const saved = (): NativeSession => ({ id: "strategy", storedId: "strategy", title: "Making the workspace feel alive", requestedModel: "qwen3:14b",
  canSend: true, toolAccess: "CAPACITY_READ_ONLY", running: false, executionGeneration: 1, messageCount: 4,
  messages: [
    { role: "user", text: "How should our workspace feel when we're working through an idea together?" },
    { role: "assistant", text: "It should feel like an ongoing conversation.\n\n### Start with the work\n\nKeep the current conversation in focus, with enough space to read and a composer that stays within reach. History belongs beside the conversation.\n\n- Show responses as they arrive.\n- Keep your next draft editable.\n- Let you read earlier messages without being pulled to the bottom.\n\nThe connection details can stay a click away." },
    { role: "user", text: "And what happens when I need to pause or change direction?" },
    { role: "assistant", text: "Stop should act on the reply you're looking at. Your draft stays yours, and the conversation is there when you come back.\n\nWe can keep the interface quiet and make the important actions easy to reach." },
  ], historyTruncated: false, pending: [], promptsPending: false });
let current = saved(), receipt: NativeReceipt | undefined, pending: { kind: "send"; requestId: string; sessionId: string } | null = null;
let receive: ((frame: NativeLiveFrame) => void) | undefined, sequence = 0, partial = "";
const port: NativeHermesPort = {
  available: () => true,
  async request(request) {
    if (request.operation === "status") return view({ operation: "status", pendingOperation: pending });
    if (request.operation === "list") return view({ operation: "list", sessions: Array.from({ length: 28 }, (_,i) => ({ id: i === 0 ? current.id : `history-${i}`, title: i === 0 ? current.title : ["Research notes", "A clearer product direction", "Weekly review", "Thinking through the next release"][i%4], running: false, messageCount: 4+i })) });
    if (request.operation === "read") { if (request.sessionId !== current.id) current = { ...saved(), id: request.sessionId, storedId: request.sessionId }; return view({ operation: "read", session: current, pendingOperation: pending }); }
    if (request.operation === "create") { current = { ...saved(), messages: [], messageCount: 0, title: "New conversation" }; return view({ operation: "create", state: "OPENED", session: current, pendingOperation: null }); }
    if (request.operation === "send") {
      pending = { kind: "send", requestId: request.requestId, sessionId: current.id };
      current = { ...current, messages: [...current.messages, { role: "user", text: request.text }], messageCount: current.messageCount+1 };
      receipt = { id: request.requestId, sessionId: current.id, status: "started", sequence: 1, outcome: null, executionGeneration: 1 };
      return view({ state: "ADMITTED", operation: "send", receipt, pendingOperation: pending });
    }
    if (request.operation === "stop" && receipt) { receipt = { ...receipt, status: "terminal", outcome: "cancelled" }; pending = null; }
    return view({ operation: request.operation, state: "ADMITTED", receipt, pendingOperation: pending });
  },
  observe(_target, onFrame) { receive = onFrame; return () => { receive = undefined; }; },
};
function emit(complete = false) {
  if (!receipt || !receive) return;
  partial += "This text comes from an explicit interaction fixture. It exercises the same render path used by native events. ";
  const frame: NativeLiveFrame = { schema: "mastermind.hermes_native_stream.v1", authGeneration: 1, sessionId: current.id, admissionId: receipt.id,
    authorityEpoch: 1, executionGeneration: 1, replayEpoch: "fixture-epoch", sequence: ++sequence, state: complete ? "complete" : "live", text: partial, activity: "responding", code: null };
  if (complete) { current = { ...current, messages: [...current.messages, { role: "assistant", text: partial }], messageCount: current.messageCount+1 }; receipt = { ...receipt, status: "terminal", outcome: "completed" }; pending = null; }
  receive(frame);
}
function Preview() {
  const [theme, setTheme] = useState("dark"), [locale, setLocale] = useState("en");
  return <><div style={{ position: "fixed", zIndex: 200, right: 10, bottom: 2, display: "flex", gap: 8, alignItems: "center", font: "10px system-ui", background: "var(--panel)", color: "var(--muted)", padding: 4 }}>
    <span>INTERACTION FIXTURE · NO PROVIDER</span><button onClick={() => setTheme(theme === "dark" ? "light" : "dark")}>Theme</button><button onClick={() => setLocale(locale === "en" ? "zh-CN" : "en")}>EN / 中文</button><button onClick={() => emit()}>Emit event</button><button onClick={() => emit(true)}>Complete</button></div>
    <div className="shell" data-theme={theme} lang={locale}><aside><div className="nav-top"><strong style={{ fontSize: 22, padding: "8px 12px" }}>mastermind</strong><p style={{ padding: "0 12px", fontSize: 10, letterSpacing: 2 }}>EXECUTIVE OS</p><button>＋ New conversation</button><button>⌕ Search</button></div><nav className="nav-scroll">{["Today", "Projects", "Inbox", "Conversations", "Knowledge", "Tools", "Meta-CEO", "Work"].map(label => <button key={label} style={{ minHeight: 44, textAlign: "left", padding: "12px", background: label === "Meta-CEO" ? "var(--raised)" : "transparent", color: "var(--muted)", border: 0, borderRadius: 10 }}>{label}</button>)}</nav><div className="nav-bottom"><button>Display settings</button><small>Signed in · preview</small></div></aside>
      <main id="content"><header className="workspace-header workspace-header-quiet"><h2>Meta-CEO</h2><span style={{ color: "var(--faint)", fontSize: 11 }}>Sources and access</span></header><div className="office-chat-workspace" data-view="chat"><div className="office-chat-tabs"><button aria-selected>Hermes</button><button>DeepSeek ↗</button><button>Company workspace</button></div><div className="office-chat-panel"><HermesNativePanel port={port} locale={locale} /></div></div></main>
    </div></>;
}
createRoot(document.getElementById("root")!).render(<Preview />);
