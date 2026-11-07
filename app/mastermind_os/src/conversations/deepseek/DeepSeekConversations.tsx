import {useEffect, useMemo, useRef, useState, type ReactNode} from "react";
import {
  MAX_PROJECTS, deepSeekAppConfig, validWorkRef,
  type CompanyView, type DeepSeekAppConfig,
} from "../../../../../integrations/deepseek_harness/company_plugin/src/protocol";
import type {ConversationListModel, ConversationProjectLocator} from "../conversation-list-contract";
import {createCompanyFrameBridge, type CompanyBridgeState} from "./company-frame-bridge";
import "./deepseek-workspace.css";

interface Props {
  model: ConversationListModel;
  signedIn: boolean;
  authGeneration: number;
  locale?: "en" | "zh-CN";
  theme?: "dark" | "light";
  selectedProject?: string | null;
  onOpenProject: (locator: ConversationProjectLocator) => boolean;
  onNewConversation?: () => void;
  children: ReactNode;
  /** Immutable deployment input, exposed for composition tests. */
  config?: DeepSeekAppConfig | null;
}
export function readDeepSeekAppConfig(): DeepSeekAppConfig | null {
  return deepSeekAppConfig(document.querySelector('meta[name="mastermind-dsh-app"]')?.getAttribute("content"), window.location.origin);
}
function presentation(props: Props, generation: number): CompanyView {
  const current = props.model.authGeneration === props.authGeneration && props.model.projectsState === "CURRENT";
  const projects = props.signedIn && current
    ? props.model.projects.slice(0, MAX_PROJECTS).flatMap(row => {
      if (row.locator.authGeneration !== props.authGeneration) return [];
      const title = (row.title ?? row.locator.workRef).replace(/[\u0000-\u001f\u007f]/g, " ").trim().slice(0, 256);
      return validWorkRef(row.locator.workRef) && title ? [{workRef: row.locator.workRef, title}] : [];
    }) : [];
  const unique = projects.filter((row, index) => projects.findIndex(other => other.workRef === row.workRef) === index);
  return {
    generation,
    state: !props.signedIn ? "SIGNED_OUT" : current ? "CURRENT" : "UNAVAILABLE",
    locale: props.locale ?? "en", theme: props.theme ?? "dark", projects: unique,
    selectedProject: unique.some(row => row.workRef === props.selectedProject) ? props.selectedProject! : null,
  };
}
function NativeChatFrame(props: Props & {config: DeepSeekAppConfig}) {
  const frame = useRef<HTMLIFrameElement>(null);
  const live = useRef(props); live.current = props;
  const bridge = useRef<ReturnType<typeof createCompanyFrameBridge> | null>(null);
  const serial = useRef(0);
  const [state, setState] = useState<CompanyBridgeState>("loading");
  const [slow, setSlow] = useState(false);
  const serialized = JSON.stringify(presentation(props, 0));
  useEffect(() => {
    const target = frame.current?.contentWindow;
    if (!target) return;
    const owner = createCompanyFrameBridge({
      target, origin: props.config.origin,
      view: presentation(live.current, ++serial.current),
      onState: setState,
      onOpenProject: workRef => {
        const current = live.current;
        if (!current.signedIn || current.model.authGeneration !== current.authGeneration ||
          current.model.projectsState !== "CURRENT") return false;
        const matches = current.model.projects.filter(row => row.locator.workRef === workRef &&
          row.locator.authGeneration === current.authGeneration);
        return matches.length === 1 && current.onOpenProject(matches[0].locator);
      },
    });
    bridge.current = owner;
    const receive = (event: MessageEvent) => owner.receive(event);
    window.addEventListener("message", receive);
    owner.connect();
    return () => {
      window.removeEventListener("message", receive);
      owner.dispose();
      if (bridge.current === owner) bridge.current = null;
    };
  }, [props.config.origin, props.config.url]);
  useEffect(() => {
    bridge.current?.update(presentation(live.current, ++serial.current));
  }, [serialized]);
  useEffect(() => {
    if (state !== "loading") { setSlow(false); return; }
    const timer = window.setTimeout(() => setSlow(true), 12000);
    return () => window.clearTimeout(timer);
  }, [state]);
  const zh = props.locale === "zh-CN";
  return <section className="dsh-workspace__frame" aria-label={zh ? "聊天工作区" : "Chat workspace"}>
    {slow || state === "unavailable" ? <div className="dsh-workspace__connection" role="status">
      <p>{zh ? "聊天连接尚未就绪。您仍可以打开项目对话。" : "The chat connection is not ready. You can still open project conversations."}</p>
      <a href={props.config.url} target="_blank" rel="noopener noreferrer">{zh ? "打开聊天应用" : "Open chat application"}</a>
    </div> : null}
    <iframe ref={frame} src={props.config.url} title={zh ? "Mastermind 聊天" : "Mastermind chat"}
      referrerPolicy="no-referrer" sandbox="allow-scripts allow-same-origin allow-forms allow-downloads allow-popups allow-popups-to-escape-sandbox"
      allow="clipboard-write; camera 'none'; microphone 'none'; geolocation 'none'; payment 'none'; clipboard-read 'none'"
      onLoad={() => { setState("loading"); bridge.current?.connect(); }}
      onError={() => setState("unavailable")} />
    <details className="dsh-workspace__details"><summary>{zh ? "连接详情" : "Connection details"}</summary>
      <p>{state === "connected"
        ? zh ? "您的项目已连接到 Mastermind OS。" : "Your projects are connected to Mastermind OS."
        : zh ? "正在连接您的 Mastermind OS 项目。" : "Connecting your Mastermind OS projects."}</p>
    </details>
  </section>;
}

/** Mount the complete donor app, preserving its own session, composer and stream. */
export function DeepSeekConversations(props: Props) {
  const config = useMemo(() => props.config === undefined ? readDeepSeekAppConfig() : props.config, [props.config]);
  const [surface, setSurface] = useState<"chat" | "projects">(() => config ? "chat" : "projects");
  const zh = props.locale === "zh-CN";
  return <div className="dsh-workspace" data-theme={props.theme ?? "dark"}>
    <div className="dsh-workspace__tabs" role="tablist" aria-label={zh ? "对话视图" : "Conversation views"}
      onKeyDown={event => {
        if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
        event.preventDefault();
        const next = event.key === "Home" ? "chat" : event.key === "End" ? "projects" : surface === "chat" ? "projects" : "chat";
        setSurface(next);
        event.currentTarget.querySelector<HTMLButtonElement>(next === "chat" ? "#dsh-chat-tab" : "#dsh-projects-tab")?.focus();
      }}>
      <button id="dsh-chat-tab" type="button" role="tab" aria-selected={surface === "chat"}
        tabIndex={surface === "chat" ? 0 : -1} aria-controls="dsh-chat-panel" onClick={() => setSurface("chat")}>{zh ? "聊天" : "Chat"}</button>
      <button id="dsh-projects-tab" type="button" role="tab" aria-selected={surface === "projects"}
        tabIndex={surface === "projects" ? 0 : -1} aria-controls="dsh-projects-panel" onClick={() => setSurface("projects")}>{zh ? "项目对话" : "Project conversations"}</button>
    </div>
    <div id="dsh-chat-panel" role="tabpanel" aria-labelledby="dsh-chat-tab" hidden={surface !== "chat"}>
      {config && props.signedIn
        ? <NativeChatFrame key={props.authGeneration + ":" + config.url} {...props} config={config} />
        : <section className="dsh-workspace__empty">
          <div className="dsh-workspace__mark" aria-hidden="true">M</div>
          <h2>{!props.signedIn ? zh ? "登录后继续聊天" : "Sign in to continue chatting"
            : zh ? "聊天连接尚未安装" : "The chat connection is not installed"}</h2>
          <p>{!props.signedIn ? zh ? "使用 Mastermind OS 的登录按钮连接您的工作区。" : "Use Mastermind OS sign-in to connect your workspace."
            : zh ? "原生聊天应用需要由工作区服务连接。您的项目对话仍可使用。" : "The native chat application needs to be connected by the workspace service. Your project conversations remain available."}</p>
          <div className="dsh-workspace__actions">
            <button type="button" onClick={() => setSurface("projects")}>{zh ? "查看项目对话" : "View project conversations"}</button>
            {props.signedIn && props.onNewConversation ? <button type="button" onClick={props.onNewConversation}>{zh ? "新建项目对话" : "New project conversation"}</button> : null}
          </div>
        </section>}
    </div>
    <div id="dsh-projects-panel" role="tabpanel" aria-labelledby="dsh-projects-tab" hidden={surface !== "projects"}>{props.children}</div>
  </div>;
}
