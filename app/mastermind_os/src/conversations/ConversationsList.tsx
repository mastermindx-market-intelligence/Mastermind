import { useEffect, useRef, useState } from "react";
import type { ConversationListProps, ConversationListSourceState } from "./conversation-list-contract";
import { isListedConversationProject, isListedCurrentConversation } from "./conversation-list-source";
import "./conversations-list.css";

export function ConversationsList(props: ConversationListProps) {
  const live = useRef(props); live.current = props;
  const search = useRef<HTMLInputElement>(null);
  const newConversation = useRef<HTMLButtonElement>(null);
  const buttons = useRef(new Map<string, HTMLButtonElement>());
  const [refused, setRefused] = useState(false);
  const zh = props.locale === "zh-CN", t = (en: string, cn: string) => zh ? cn : en;
  const needle = props.query.trim().toLocaleLowerCase(zh ? "zh-CN" : "en");
  const matches = (...values: (string | null)[]) => !needle || values.some(value =>
    value?.toLocaleLowerCase(zh ? "zh-CN" : "en").includes(needle));
  const recent = props.model.recentState === "CURRENT" ? props.model.recent.filter(row =>
    matches(row.title, row.projectTitle, row.locator.workRef)) : [];
  const projects = props.model.projectsState === "CURRENT" ? props.model.projects.filter(row =>
    matches(row.title, row.nextAction, row.locator.workRef)) : [];
  const shownProjects = props.showAllProjects ? projects : projects.slice(0, 8);
  useEffect(() => {
    if (!props.restoreFocus || props.restoreFocus.request < 1) return;
    const button = props.restoreFocus.key === 'new-conversation' ? newConversation.current
      : props.restoreFocus.key ? buttons.current.get(props.restoreFocus.key) : undefined;
    (button?.isConnected ? button : search.current)?.focus();
  }, [props.restoreFocus?.request]);

  const unavailable = (state: ConversationListSourceState, project = false) => {
    if (state === "PENDING") return project ? t("Reading projects…", "正在读取项目…") : t("Reading the current conversation…", "正在读取当前对话…");
    if (state === "WITHHELD") return project ? t("Project access is unavailable here.", "此处无法访问项目。") : t("Conversation access is unavailable here.", "此处无法访问对话。");
    if (state === "STALE") return t("This source has changed. Refresh this view to continue.", "此来源已更改。请刷新此视图后继续。");
    return project ? t("Projects are unavailable here.", "此处无法获取项目。") : t("No current conversation can be shown here.", "此处暂时无法显示当前对话。");
  };
  const sourceLabel = (state: ConversationListSourceState) => ({
    CURRENT: t("Current observation", "当前观测"), PENDING: t("Reading", "正在读取"),
    STALE: t("Changed", "已更改"), WITHHELD: t("Access unavailable", "无法访问"),
    UNAVAILABLE: t("Unavailable", "无法获取"), UNASSOCIATED: t("Not associated", "未确认关联"),
    UNKNOWN: t("Not established", "尚未确认"),
  })[state];
  const remember = (key: string, element: HTMLButtonElement | null) => {
    if (element) buttons.current.set(key, element); else buttons.current.delete(key);
  };
  const failed = () => setRefused(true);
  const noMatches = Boolean(needle) && recent.length === 0 && projects.length === 0 &&
    (props.model.recentState === "CURRENT" || props.model.projectsState === "CURRENT");

  return <section className="conversations-list" data-theme={props.theme ?? "dark"} lang={props.locale ?? "en"} aria-labelledby="conversations-list-title">
    <header className="conversations-list__header">
      <div><h1 id="conversations-list-title">{t("Conversations", "对话")}</h1>
        <p>{props.onNewConversation ? t("Continue a conversation or start a new one.", "继续对话或开始新对话。")
          : t("Continue a conversation or open a project.", "继续对话或打开项目。")}</p></div>
      {props.onNewConversation ? <button type="button" ref={newConversation} onClick={() => live.current.onNewConversation?.()}>{t("New conversation", "新建对话")}</button> : null}
    </header>
    <div className="conversations-list__coverage">
      <p role="note">{t("This list is incomplete. More conversations may be available within a project.", "此列表不完整。项目中可能还有其他对话。")}</p>
      <button type="button" onClick={() => live.current.onSourcesAndAccess()}>{t("Sources and access", "来源与访问")}</button>
    </div>
    <div className="conversations-list__filter">
      <label htmlFor="conversations-list-query">{t("Find by project or topic", "按项目或主题查找")}</label>
      <input id="conversations-list-query" ref={search} type="search" maxLength={128} value={props.query}
        onChange={event => { setRefused(false); props.onQueryChange(event.target.value); }} />
      {props.onRefresh ? <button type="button" disabled={props.model.recentState === "PENDING" || props.model.projectsState === "PENDING"}
        onClick={() => live.current.onRefresh?.()}>{t("Refresh", "刷新")}</button> : null}
    </div>
    {refused ? <p className="conversations-list__notice" role="status">{t("This source is no longer current. Refresh this view before opening it.", "此来源已不是当前状态。请刷新此视图后再打开。")}</p> : null}
    {noMatches ? <p role="status">{t("No matches in the available records.", "可用记录中没有匹配项。")}</p> : null}
    <section className="conversations-list__section" aria-labelledby="conversations-list-recent">
      <h2 id="conversations-list-recent">{t("Current conversation", "当前对话")}</h2>
      {props.model.recentState !== "CURRENT" ? <p role="status">{unavailable(props.model.recentState)}</p>
        : !props.model.recent.length ? <p>{t("No current conversation is listed here.", "此处暂未列出当前对话。")}</p> : null}
      {recent.map(row => {
        const title = row.title ?? t("Current conversation", "当前对话");
        return <article className="conversations-list__row" key={row.key} data-conversation-key={row.key}>
          <div className="conversations-list__row-copy">
            <p className="conversations-list__project">{row.projectTitle ?? row.locator.workRef}</p>
            <h3>{title}</h3>
            <p>{t("Conversation available.", "可以查看对话。")}</p>
            <div className="conversations-list__meta"><span>{t("Observed", "观测时间")} <time dateTime={row.observedAt}>{row.observedAt}</time></span>
              {row.unsentDraft ? <span>{t("Unsent draft", "未发送草稿")}</span> : null}</div>
          </div>
          <button type="button" ref={element => remember(row.key, element)} aria-label={t(`Open conversation: ${title}`, `打开对话：${title}`)}
            onClick={() => { const current = live.current; try {
              if (!isListedCurrentConversation(current.model, row.locator) || !current.onOpenCurrent(row.locator)) failed();
              else setRefused(false);
            } catch { failed(); } }}>{t("Open", "打开")}</button>
        </article>;
      })}
      {props.onOpenSessionRequests ? <button type="button" ref={element => remember("selected-session", element)}
        onClick={() => {try {if (!live.current.onOpenSessionRequests?.()) failed(); else setRefused(false);} catch {failed();}}}>
        {t("Open session requests", "查看会话请求")}</button> : null}
    </section>
    <section className="conversations-list__section" aria-labelledby="conversations-list-projects">
      <h2 id="conversations-list-projects">{t("Projects", "项目")}</h2>
      <p className="conversations-list__scope">{t("Project records are shown separately. Their conversation history is not loaded here.", "项目记录单独列出，此处尚未加载其对话历史。")}</p>
      {props.model.projectsState !== "CURRENT" ? <p role="status">{unavailable(props.model.projectsState, true)}</p>
        : !props.model.projects.length ? <p>{t("No projects are listed in this view.", "此视图中暂未列出项目。")}</p> : null}
      {shownProjects.map(row => <article className="conversations-list__row" key={row.key} data-conversation-key={row.key}>
        <div className="conversations-list__row-copy"><h3>{row.title ?? row.locator.workRef}</h3>
          <p>{t("You can open this project's workspace.", "您可以打开此项目的工作区。")}</p></div>
        <button type="button" ref={element => remember(row.key, element)} aria-label={t(`Open project ${row.title ?? row.locator.workRef}`, `打开项目 ${row.title ?? row.locator.workRef}`)}
          onClick={() => { const current = live.current; try {
            if (!isListedConversationProject(current.model, row.locator) || !current.onOpenProject(row.locator)) failed();
            else setRefused(false);
          } catch { failed(); } }}>{t("Open project", "打开项目")}</button>
      </article>)}
      {!props.showAllProjects && projects.length > 8 ? <button type="button" className="conversations-list__more" onClick={props.onShowAllProjects}>
        {t(`Show all ${projects.length} matching projects`, `显示全部 ${projects.length} 个匹配项目`)}</button> : null}
    </section>
    <footer className="conversations-list__footer">
      <p>{t("Plan priorities and direction with Meta-CEO.", "与 Meta-CEO 讨论优先事项和方向。")}</p>
      <button type="button" onClick={() => live.current.onOpenMetaCeo()}>{t("Open Meta-CEO", "打开 Meta-CEO")}</button>
    </footer>
    <details className="conversations-list__sources"><summary>{t("List sources", "列表来源")}</summary>
      <p>{t("Current conversation contains the one currently associated window. Projects keep the supplied catalogue order. Retained conversation history has not been enumerated.", "“当前对话”仅包含当前确认关联的窗口。项目保持所提供目录的顺序，尚未枚举已保留的对话历史。")}</p>
      <p>{t("Search covers the current Mission title and the project titles and authored next actions shown in this source.", "搜索覆盖当前任务标题，以及此来源中的项目标题和已记录的下一步行动。")}</p>
      <dl>{props.model.sources.map(source => {
        const state = source.owner === "CURRENT_WINDOW" ? props.model.recentState : props.model.projectsState;
        return <div key={source.owner}><dt>{source.owner === "CURRENT_WINDOW" ? t("Current conversation", "当前对话") : t("Projects", "项目")}</dt>
          <dd>{sourceLabel(state)} <code>{state}</code>
            {state !== "WITHHELD" && source.observedAt ? <p>{t("Read observation", "读取观测")} <time dateTime={source.observedAt}>{source.observedAt}</time></p> : null}
            {state !== "WITHHELD" && source.revision ? <code>{source.revision}</code> : null}</dd></div>;
      })}</dl>
      {projects.length ? <ul>{projects.map(row => <li key={row.key}>{row.title ? <span>{row.title} — </span> : null}<code>{row.locator.workRef}</code></li>)}</ul> : null}
    </details>
  </section>;
}
