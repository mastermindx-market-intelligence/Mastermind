// Bounded discovery workspace (AT06 Search / AT07 Sources / AT11 Tools).
// Read-only presentation over one supplied DiscoveryView. Private state is
// limited to query, filter, selection id and the retained-result tuple; the
// view itself is re-derived every render. No reads, acquisition, catalogue
// registry, credentials, permission, recipient or command authority: every
// action forwards to an existing owner callback the caller actually supplied,
// and button presence never grants permission.
import { useEffect, useId, useRef, useState } from "react";
import type { KeyboardEvent as ReactKeyboardEvent, ReactNode } from "react";
import { Knowledge } from "../knowledge/Knowledge";
import type { KnowledgeProps } from "../knowledge/Knowledge";
import { sameTarget } from "../meta-ceo/projection";
import type { OfficeProjection, ProjectionContext } from "../meta-ceo/projection";
import type {
  DiscoveryCapability,
  DiscoveryItem,
  DiscoveryMode,
  DiscoverySource,
  DiscoveryView,
} from "./contract";
import type { MissionSelection, EvidenceRef } from "../mission";
import type { ResultSelection } from "../result";
import "./discovery.css";

export interface DiscoveryWorkspaceProps {
  view: DiscoveryView;
  projection: OfficeProjection;
  mode: DiscoveryMode;
  locale?: "en" | "zh-CN";
  theme?: "dark" | "light";
  sourceProps?: Pick<
    KnowledgeProps,
    "readResultReferences" | "readResult" | "hostGeneration" | "draftPort" | "onOpenSource"
  >;
  onModeChange?: (mode: DiscoveryMode) => void;
  onOpenProject?: (selection: MissionSelection, mode: "current" | "history") => void;
  onOpenConversation?: () => void;
  onOpenMetaCeo?: () => void;
  onOpenKnowledge?: () => void;
  onOpenPreferences?: () => void;
  onRefreshSources?: () => void;
}

/** Exact requested-result tuple the concurrent Knowledge seam validates before
 * its existing detail read. Built only from the supplied ResultSelection and
 * forwarded unchanged; this workspace never reads a result itself. */
interface RequestedResultTuple {
  workRef: string;
  rootJobId: string;
  jobId: string;
  attemptId: string;
  resultEnvelopeDigest: string;
}

const MAX_VISIBLE = 8;
const CONTEXT_KEYS = ["mission", "programs", "result", "conversation"] as const;
type KindFilter = "all" | "project" | "conversation" | "knowledge";
interface FilterState {
  kind: KindFilter;
  expanded: boolean;
}
interface SelectedResultState {
  itemId: string;
  selection: ResultSelection;
  role: string;
}

const ZH = {
  "Search": "搜索",
  "SEARCH AVAILABLE SOURCES": "搜索可用来源",
  "Search available sources": "搜索可用来源",
  "Only the supplied workspace window is searched. Coverage beyond these supplied records is not established, the current window is not complete conversation history, and retained-result references are not the result full text.":
    "仅搜索已提供的工作区窗口。这些已提供记录之外的覆盖范围未确认，当前窗口不是完整对话历史，保留结果引用也不是结果全文。",
  "All": "全部",
  "Projects": "项目",
  "Conversations": "对话",
  "Knowledge": "知识",
  "Type filter": "类型筛选",
  "No supplied results match this search.": "没有符合此搜索的已提供结果。",
  "Supplied results": "已提供结果",
  "Search sources are unavailable. No search results can be confirmed.": "搜索来源暂不可用，无法确认搜索结果。",
  "Inspect": "检查",
  "Close": "关闭",
  "Selected result": "已选结果",
  "No summary was supplied for this item.": "该项目未提供摘要。",
  "Observed excerpt": "观察摘录",
  "Source metadata": "来源元数据",
  "Evidence context": "证据上下文",
  "Owner": "所有者",
  "Reference": "引用",
  "Revision": "版本",
  "State": "状态",
  "Coverage": "覆盖",
  "Observed at": "观察时间",
  "Source time": "来源时间",
  "Freshness": "新鲜度",
  "Facet": "切面",
  "Role": "角色",
  "Project": "项目",
  "Conversation": "对话",
  "Evidence": "证据",
  "Result": "结果",
  "Open project (current)": "打开项目（当前）",
  "Open project (history)": "打开项目（历史）",
  "Project route not supplied on this surface.": "此界面未提供项目路由。",
  "This project item has no supplied selection.": "该项目条目没有已提供的选择。",
  "Open conversation window": "打开对话窗口",
  "Conversation route not supplied on this surface.": "此界面未提供对话路由。",
  "Opens the observed window only; not a new session and not the full conversation history.":
    "仅打开已观察窗口；不是新会话，也不是完整对话历史。",
  "Open original content": "打开原始内容",
  "Original content is not supplied on this surface; no source route was provided.":
    "此界面未提供原始内容；未提供来源路由。",
  "Open source": "打开来源",
  "Back to search": "返回搜索",
  "This item is no longer in the supplied window.": "该项目已不在已提供窗口中。",
  "Unavailable": "不可用",
  "The supplied view does not match the current projection, so this surface keeps no saved query, selection or source content.":
    "提供的视图与当前投影不一致，因此此界面不保留已保存的查询、选择或来源内容。",
  "The retained-result identity for this record is incomplete.": "该记录的保留结果标识不完整。",
  "Sources": "来源",
  "Review missing evidence and freshness": "查看缺失证据与新鲜度",
  "Supplied sources": "已提供来源",
  "No sources were supplied.": "未提供来源。",
  "Refresh observations": "刷新观察",
  "Refreshing observations is not supplied on this surface.": "此界面未提供刷新观察。",
  "Open display preferences": "打开显示偏好设置",
  "Display preferences are not supplied on this surface.": "此界面未提供显示偏好设置。",
  "Appearance": "外观",
  "Dark": "深色",
  "Light": "浅色",
  "Not supplied": "未提供",
  "Observed copy": "观察副本",
  "Observed copy supplied — a decoded projection, not the full canonical original.":
    "已提供观察副本——是解码投影，不是完整规范原文。",
  "Reference only": "仅引用",
  "Reference metadata only — original content is not supplied here. This is not an access denial.":
    "仅有引用元数据——此处未提供原始内容。这不是访问被拒。",
  "This source is unavailable here.": "此来源在此处不可用。",
  "Reason": "原因",
  "Health, connectivity or live status is not inferred here.": "此处不推断健康、连接或实时状态。",
  "Source observation": "来源观察",
  "Local acquisition": "本地获取",
  "System observations": "系统观察",
  "Provider": "提供方",
  "Installed": "已安装",
  "Yes": "是",
  "No": "否",
  "Version": "版本",
  "Detail": "详情",
  "Limitations": "限制",
  "Tools": "工具",
  "CAPABILITIES, IN CONTEXT": "上下文中的能力",
  "Capabilities shown here come from the supplied view only. Buttons open existing routes; button presence never grants permission, and this read-only surface never sends work.":
    "此处显示的能力仅来自已提供视图。按钮只打开既有路由；按钮的存在从不授予许可，此只读界面从不发送工作。",
  "Project context": "项目上下文",
  "Work reference": "工作引用",
  "Root job": "根作业",
  "Session": "会话",
  "Binding generation": "绑定代",
  "Capabilities": "能力",
  "Direction preview": "方向预览",
  "Return review": "回报复核",
  "Source context": "来源上下文",
  "Placement": "安置",
  "Release": "释放",
  "Open Meta-CEO office": "打开 Meta-CEO 办公室",
  "Selected tool": "已选工具",
  "Other tools": "其他工具",
  "Open search": "打开搜索",
  "Open source context": "打开来源上下文",
  "Open return review": "打开回报复核",
  "Open placement": "打开安置",
  "Open release": "打开释放",
  "Read only": "只读",
  "Preview only": "仅预览",
  "Preview only — sending is separate and unavailable here; this read-only surface never accepts or releases work.":
    "仅预览——发送是独立操作且此处不可用；此只读界面从不接受或释放工作。",
  "Route not supplied on this surface.": "此界面未提供路由。",
  "This capability needs {port}; it was not supplied on this surface.":
    "此能力需要{port}；此界面未提供。",
  "Unavailable in the supplied capabilities; no action is offered.": "已提供能力中该能力不可用；不提供任何操作。",
  "Meta-CEO route": "Meta-CEO 路由",
  "Search route": "搜索路由",
  "Knowledge route": "知识路由",
  "Sources route": "来源路由",
  "Owner route": "所有者路由",
  "Excerpts are exact supplied text or bounded excerpts, never generated summaries.":
    "摘录是精确的已提供文本或有界摘录，从不是生成的摘要。",
  "The supplied evidence tuple is incomplete, so no original-content route is offered.":
    "已提供证据元组不完整，因此不提供原始内容路由。",
  "Inspect a supplied result to see its exact source, state and coverage.":
    "检查一个已提供结果以查看其确切来源、状态与覆盖。",
  "Select a supplied source to review its clocks and coverage.": "选择一个已提供来源以查看其时钟与覆盖。",
  "Observed at kind": "观察时间类型",
  "No system observations were supplied.": "未提供系统观察。",
  "No limitations were supplied.": "未提供限制。",
  "No capabilities were supplied.": "未提供能力。",
} as const;
type CopyKey = keyof typeof ZH;

const makeT = (locale?: "en" | "zh-CN") => (en: CopyKey): string =>
  locale === "zh-CN" ? ZH[en] : en;

const countResults = (locale: "en" | "zh-CN", n: number): string =>
  locale === "zh-CN" ? `${n} 条已提供结果` : `${n} supplied result${n === 1 ? "" : "s"}`;

const showAllResults = (locale: "en" | "zh-CN", n: number): string =>
  locale === "zh-CN" ? `显示全部 ${n} 条已提供结果` : `Show all ${n} supplied results`;

const limitedNote = (locale: "en" | "zh-CN", n: number): string =>
  locale === "zh-CN"
    ? `显示 ${n} 条已提供结果中的前 ${MAX_VISIBLE} 条；已提供窗口中的内容不会被丢弃。`
    : `Showing the first ${MAX_VISIBLE} of ${n} supplied results; nothing in the supplied window is dropped.`;

const evidenceStateNote = (locale: "en" | "zh-CN", state: string): string =>
  locale === "zh-CN" ? `证据状态为 ${state} 时不提供原始内容。` : `Original content is not offered while the evidence state is ${state}.`;

const openSourceNeeds = (locale: "en" | "zh-CN", missing: string): string =>
  locale === "zh-CN" ? `打开来源需要宿主提供 ${missing}；此处未提供。` : `Open source needs ${missing} from the host; not supplied here.`;

const unavailablePort = (locale: "en" | "zh-CN", port: string): string =>
  locale === "zh-CN" ? `不可用——未提供${port}。` : `Unavailable — ${port} is not supplied.`;

/** Port named when a capability cannot act; the actual missing owner route. */
function portLabel(locale: "en" | "zh-CN", target: DiscoveryCapability["target"]): string {
  const t = makeT(locale);
  switch (target) {
    case "meta_ceo":
      return t("Meta-CEO route");
    case "search":
      return t("Search route");
    case "knowledge":
      return t("Knowledge route");
    case "sources":
      return t("Sources route");
    default:
      return t("Owner route");
  }
}

const LIMITATION_ZH: Record<string, string> = {
  BOUNDED_SCOPE: "范围有限——仅搜索已提供窗口。",
  NO_PEOPLE_INDEX: "无人员索引。",
  NO_GLOBAL_HISTORY: "无全公司历史。",
  NO_GENERIC_SOURCE_READER: "无通用来源读取器。",
  CONTROL_ROOM_NOT_SUPPLIED: "未提供控制室。",
};

const KIND_KEY: Record<string, CopyKey> = {
  project: "Project",
  conversation: "Conversation",
  evidence: "Evidence",
  result: "Result",
};

function kindLabel(locale: "en" | "zh-CN", kind: string): string {
  return makeT(locale)(KIND_KEY[kind] ?? "Result");
}

function clockLabel(locale: "en" | "zh-CN", value: string | null): string {
  return value ?? makeT(locale)("Not supplied");
}

/** The private body is keyed by actual auth, selected work, session, binding
 * and the caller's actual host generation, so any of those changes remounts
 * it before paint and clears query, filter, selection and the source detour. */
function bodyIdentity(projection: OfficeProjection, sourceProps?: DiscoveryWorkspaceProps["sourceProps"]): string {
  const c = projection.context;
  const host = sourceProps?.hostGeneration;
  const hostPart = typeof host === "string" && host.length > 0 || typeof host === "number" && Number.isFinite(host) ? [typeof host, host] : null;
  return JSON.stringify([
    c.authGeneration,
    c.selection?.workRef ?? null,
    c.selection?.rootJobId ?? null,
    c.sessionRef ?? null,
    c.bindingGeneration,
    hostPart,
  ]);
}

/** The workspace renders only when the supplied view still describes the
 * actual projection: same auth generation, same selected work/session/binding
 * and the same per-source revisions. */
function contextMatches(view: ProjectionContext, projection: ProjectionContext): boolean {
  if (view.authGeneration !== projection.authGeneration) return false;
  if (!sameTarget(view, projection)) return false;
  return CONTEXT_KEYS.every((key) => view.revisions[key] === projection.revisions[key]);
}

function resultTuple(selection: ResultSelection): RequestedResultTuple | null {
  const tuple: RequestedResultTuple = {
    workRef: selection.workRef,
    rootJobId: selection.rootJobId,
    jobId: selection.jobId,
    attemptId: selection.attemptId,
    resultEnvelopeDigest: selection.resultEnvelopeDigest,
  };
  const values = Object.values(tuple);
  if (values.some((value) => typeof value !== "string" || value.length === 0)) return null;
  return tuple;
}

function chipClass(state: string): string {
  if (state === "CURRENT") return "discovery-chip discovery-chip-current";
  if (state === "STALE") return "discovery-chip discovery-chip-stale";
  return "discovery-chip";
}

function MetaRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="discovery-meta-row">
      <span className="discovery-meta-label">{label}</span>
      <span className="discovery-meta-value">{value}</span>
    </div>
  );
}

function ItemRow({
  item,
  locale,
  selected,
  onInspect,
}: {
  item: DiscoveryItem;
  locale: "en" | "zh-CN";
  selected: boolean;
  onInspect: () => void;
}) {
  const t = makeT(locale);
  return (
    <li>
      <button
        type="button"
        className={selected ? "discovery-item discovery-item-selected" : "discovery-item"}
        data-disc-item={item.id}
        aria-pressed={selected}
        onClick={onInspect}
      >
        <span className="discovery-item-kind">{kindLabel(locale, item.kind)}</span>
        <span className="discovery-item-title">{item.title}</span>
        {item.summary ? <span className="discovery-item-summary">{item.summary}</span> : null}
        <span className="discovery-item-foot">
          <span className={chipClass(item.source.state)}>{item.source.state}</span>
          <span className="discovery-inspect-hint">{t("Inspect")}</span>
        </span>
      </button>
    </li>
  );
}

function EvidenceContext({
  evidence,
  facet,
  locale,
}: {
  evidence: EvidenceRef;
  facet: string;
  locale: "en" | "zh-CN";
}) {
  const t = makeT(locale);
  return (
    <section className="discovery-preview-section" aria-label={t("Evidence context")}>
      <h3 className="discovery-section-label">{t("Evidence context")}</h3>
      <MetaRow label={t("Owner")} value={evidence.owner} />
      <MetaRow label={t("Reference")} value={evidence.ref} />
      <MetaRow label={t("Revision")} value={clockLabel(locale, evidence.source_revision)} />
      <MetaRow label={t("Source time")} value={clockLabel(locale, evidence.source_time)} />
      <MetaRow label={t("Observed at")} value={clockLabel(locale, evidence.observed_at)} />
      <MetaRow label={t("Freshness")} value={evidence.freshness_state} />
      <MetaRow label={t("Facet")} value={facet} />
    </section>
  );
}

function Preview({
  item,
  locale,
  sourceProps,
  onOpenProject,
  onOpenConversation,
  onOpenResult,
}: {
  item: DiscoveryItem;
  locale: "en" | "zh-CN";
  sourceProps?: DiscoveryWorkspaceProps["sourceProps"];
  onOpenProject?: DiscoveryWorkspaceProps["onOpenProject"];
  onOpenConversation?: DiscoveryWorkspaceProps["onOpenConversation"];
  onOpenResult: (item: DiscoveryItem) => void;
}) {
  const t = makeT(locale);
  const source = item.source;

  let projectAction: ReactNode = null;
  if (item.target.kind === "project") {
    const selection = item.target.selection;
    const mode = item.target.mode;
    const label = mode === "current" ? t("Open project (current)") : t("Open project (history)");
    if (selection && onOpenProject) {
      projectAction = (
        <div className="discovery-action-block">
          <button type="button" className="discovery-action" onClick={() => onOpenProject(selection, mode)}>
            {label}
          </button>
        </div>
      );
    } else {
      projectAction = (
        <div className="discovery-action-block">
          <button type="button" className="discovery-action" disabled>
            {label}
          </button>
          <p className="discovery-reason">
            {selection ? t("Project route not supplied on this surface.") : t("This project item has no supplied selection.")}
          </p>
        </div>
      );
    }
  }

  let conversationAction: ReactNode = null;
  if (item.target.kind === "conversation") {
    conversationAction = (
      <div className="discovery-action-block">
        <button
          type="button"
          className="discovery-action"
          disabled={!onOpenConversation}
          onClick={onOpenConversation ? () => onOpenConversation() : undefined}
        >
          {t("Open conversation window")}
        </button>
        <p className="discovery-reason">
          {onOpenConversation
            ? t("Opens the observed window only; not a new session and not the full conversation history.")
            : t("Conversation route not supplied on this surface.")}
        </p>
      </div>
    );
  }

  let evidenceAction: ReactNode = null;
  if (item.target.kind === "evidence") {
    const evidence = item.target.evidence;
    const revision = evidence.source_revision;
    const navMode: "current" | "history" = evidence.freshness_state === "HISTORICAL" ? "history" : "current";
    const routeReady = typeof sourceProps?.onOpenSource === "function";
    const stateReady = source.state === "CURRENT" || source.state === "STALE";
    const tupleReady = evidence.ref.length > 0 && revision !== null;
    let reason: string;
    if (!routeReady) {
      reason = t("Original content is not supplied on this surface; no source route was provided.");
    } else if (!stateReady) {
      reason = evidenceStateNote(locale, source.state);
    } else {
      reason = tupleReady ? "" : t("The supplied evidence tuple is incomplete, so no original-content route is offered.");
    }
    const open = routeReady && stateReady && tupleReady
      ? () => {
          const openSource = sourceProps?.onOpenSource;
          if (openSource) openSource({ owner: evidence.owner, ref: evidence.ref, revision, mode: navMode });
        }
      : undefined;
    evidenceAction = (
      <div className="discovery-action-block">
        <button type="button" className="discovery-action" disabled={!open} onClick={open}>
          {t("Open original content")}
        </button>
        {reason ? <p className="discovery-reason">{reason}</p> : null}
      </div>
    );
  }

  let resultAction: ReactNode = null;
  if (item.target.kind === "result") {
    const referencesReady = typeof sourceProps?.readResultReferences === "function";
    const readReady = typeof sourceProps?.readResult === "function";
    const hostGeneration = sourceProps?.hostGeneration;
    const hostReady = typeof hostGeneration === "string" && hostGeneration.length > 0 || typeof hostGeneration === "number" && Number.isFinite(hostGeneration);
    const missing: string[] = [];
    if (!referencesReady) missing.push("readResultReferences");
    if (!readReady) missing.push("readResult");
    if (!hostReady) missing.push("hostGeneration");
    resultAction = referencesReady && readReady && hostReady ? (
      <div className="discovery-action-block">
        <button type="button" className="discovery-action" onClick={() => onOpenResult(item)}>
          {t("Open source")}
        </button>
      </div>
    ) : (
      <div className="discovery-action-block">
        <button type="button" className="discovery-action" disabled>
          {t("Open source")}
        </button>
        <p className="discovery-reason">{openSourceNeeds(locale, missing.join(", "))}</p>
      </div>
    );
  }

  return (
    <aside className="discovery-panel discovery-preview" aria-label={t("Selected result")}>
      <div className="discovery-preview-head">
        <span className="discovery-item-kind">{kindLabel(locale, item.kind)}</span>
        <h2>{item.title}</h2>
      </div>
      <section className="discovery-preview-section" aria-label={t("Observed excerpt")}>
        <h3 className="discovery-section-label">{t("Observed excerpt")}</h3>
        {item.summary ? (
          <p className="discovery-excerpt">{item.summary}</p>
        ) : (
          <p className="discovery-muted">{t("No summary was supplied for this item.")}</p>
        )}
        <p className="discovery-fineprint">
          {t("Excerpts are exact supplied text or bounded excerpts, never generated summaries.")}
        </p>
      </section>
      <section className="discovery-preview-section" aria-label={t("Source metadata")}>
        <h3 className="discovery-section-label">{t("Source metadata")}</h3>
        <MetaRow label={t("Owner")} value={source.owner} />
        <MetaRow label={t("Reference")} value={clockLabel(locale, source.ref)} />
        <MetaRow label={t("Revision")} value={clockLabel(locale, source.revision)} />
        <MetaRow label={t("State")} value={source.state} />
        <MetaRow label={t("Coverage")} value={source.coverage} />
        <MetaRow label={t("Observed at")} value={clockLabel(locale, source.observed_at)} />
      </section>
      {item.target.kind === "evidence" ? (
        <EvidenceContext evidence={item.target.evidence} facet={item.target.facet} locale={locale} />
      ) : null}
      {item.target.kind === "result" ? (
        <section className="discovery-preview-section" aria-label={t("Role")}>
          <h3 className="discovery-section-label">{t("Role")}</h3>
          <MetaRow label={t("Role")} value={item.target.role} />
        </section>
      ) : null}
      <div className="discovery-actions">
        {projectAction}
        {conversationAction}
        {evidenceAction}
        {resultAction}
      </div>
    </aside>
  );
}

const LIMITATION_EN: Record<string, string> = {
  BOUNDED_SCOPE: "Bounded scope — only the supplied window is searched.",
  NO_PEOPLE_INDEX: "No people index.",
  NO_GLOBAL_HISTORY: "No company-wide history.",
  NO_GENERIC_SOURCE_READER: "No generic source reader.",
  CONTROL_ROOM_NOT_SUPPLIED: "Control room not supplied.",
};

const sourceKey = (id: string): string => `source:${id}`;

const contentChip = (locale: "en" | "zh-CN", content: DiscoverySource["content"]): string => {
  const t = makeT(locale);
  if (content === "OBSERVED") return t("Observed copy");
  if (content === "REFERENCE_ONLY") return t("Reference only");
  return t("Unavailable");
};

const needsPort = (locale: "en" | "zh-CN", port: string): string =>
  locale === "zh-CN" ? `此能力需要${port}；此界面未提供。` : `This capability needs ${port}; it was not supplied on this surface.`;

const TABS: ReadonlyArray<{ kind: KindFilter; label: CopyKey }> = [
  { kind: "all", label: "All" },
  { kind: "project", label: "Projects" },
  { kind: "conversation", label: "Conversations" },
  { kind: "knowledge", label: "Knowledge" },
];

function SearchView({
  view,
  locale,
  query,
  filter,
  selectedId,
  selectedItem,
  sourceProps,
  onOpenProject,
  onOpenConversation,
  onQuery,
  onFilter,
  onExpand,
  onInspect,
  onOpenResult,
}: {
  view: DiscoveryView;
  locale: "en" | "zh-CN";
  query: string;
  filter: FilterState;
  selectedId: string | null;
  selectedItem: DiscoveryItem | null;
  sourceProps?: DiscoveryWorkspaceProps["sourceProps"];
  onOpenProject?: DiscoveryWorkspaceProps["onOpenProject"];
  onOpenConversation?: DiscoveryWorkspaceProps["onOpenConversation"];
  onQuery: (value: string) => void;
  onFilter: (kind: KindFilter) => void;
  onExpand: () => void;
  onInspect: (id: string) => void;
  onOpenResult: (item: DiscoveryItem) => void;
}) {
  const t = makeT(locale);
  const inputId = useId();
  const composingRef = useRef(false);
  const normalized = query.trim().toLocaleLowerCase();
  const matches = view.items.filter((item) => {
    const kindOk =
      filter.kind === "all"
        ? true
        : filter.kind === "knowledge"
          ? item.kind === "evidence" || item.kind === "result"
          : item.kind === filter.kind;
    if (!kindOk) return false;
    if (!normalized) return true;
    return [item.title, item.summary ?? "", item.searchText].some((text) =>
      text.toLocaleLowerCase().includes(normalized),
    );
  });
  const total = matches.length;
  const visible = filter.expanded ? matches : matches.slice(0, MAX_VISIBLE);
  const sourceAvailable = view.sources.some(source =>
    (source.state === "CURRENT" || source.state === "STALE") && source.content !== "UNAVAILABLE");
  const status =
    total === 0 && !sourceAvailable
      ? t("Search sources are unavailable. No search results can be confirmed.")
      : total === 0
      ? t("No supplied results match this search.")
      : total <= visible.length
        ? countResults(locale, total)
        : `${countResults(locale, total)} — ${limitedNote(locale, total)}`;
  return (
    <section className="discovery-view">
      <header className="discovery-heading">
        <p className="discovery-eyebrow">{t("SEARCH AVAILABLE SOURCES")}</p>
        <h1>{t("Search")}</h1>
        <p className="discovery-lede">
          {t("Only the supplied workspace window is searched. Coverage beyond these supplied records is not established, the current window is not complete conversation history, and retained-result references are not the result full text.")}
        </p>
      </header>
      <div className="discovery-searchbar">
        <label className="discovery-search-label" htmlFor={inputId}>
          {t("Search available sources")}
        </label>
        <input
          id={inputId}
          className="discovery-search-input"
          type="search"
          value={query}
          onChange={(event) => onQuery(event.target.value)}
          onCompositionStart={() => {
            composingRef.current = true;
          }}
          onCompositionEnd={() => {
            composingRef.current = false;
          }}
          onKeyDown={(event) => {
            if (event.key !== "Enter") return;
            if (composingRef.current || event.nativeEvent.isComposing) return;
            const first = visible[0];
            if (first) onInspect(first.id);
          }}
        />
      </div>
      <div className="discovery-tabs" role="group" aria-label={t("Type filter")}>
        {TABS.map((tab) => (
          <button
            key={tab.kind}
            type="button"
            className="discovery-tab"
            aria-pressed={filter.kind === tab.kind}
            onClick={() => onFilter(tab.kind)}
          >
            {t(tab.label)}
          </button>
        ))}
      </div>
      <p className="discovery-status" role="status">
        {status}
      </p>
      {total > MAX_VISIBLE && !filter.expanded ? (
        <button type="button" className="discovery-show-all" onClick={onExpand}>
          {showAllResults(locale, total)}
        </button>
      ) : null}
      <div className="discovery-layout discovery-search-layout">
        <section className="discovery-panel discovery-results" aria-label={t("Supplied results")}>
          {visible.length > 0 ? (
            <ul className="discovery-list">
              {visible.map((item) => (
                <ItemRow
                  key={item.id}
                  item={item}
                  locale={locale}
                  selected={item.id === selectedId}
                  onInspect={() => onInspect(item.id)}
                />
              ))}
            </ul>
          ) : null}
        </section>
        {selectedItem ? (
          <Preview
            item={selectedItem}
            locale={locale}
            sourceProps={sourceProps}
            onOpenProject={onOpenProject}
            onOpenConversation={onOpenConversation}
            onOpenResult={onOpenResult}
          />
        ) : (
          <aside className="discovery-panel discovery-preview" aria-label={t("Selected result")}>
            <p className="discovery-muted">
              {t("Inspect a supplied result to see its exact source, state and coverage.")}
            </p>
          </aside>
        )}
      </div>
    </section>
  );
}

/** Embedded retained-result detour: renders the existing Knowledge owner with
 * the caller's real readers, host generation, draft port and source route,
 * plus the exact requested tuple. No reader is imitated here. */
function SourceDetour({
  projection,
  locale,
  selected,
  item,
  sourceProps,
  onBack,
}: {
  projection: OfficeProjection;
  locale: "en" | "zh-CN";
  selected: SelectedResultState;
  item: DiscoveryItem | null;
  sourceProps?: DiscoveryWorkspaceProps["sourceProps"];
  onBack: () => void;
}) {
  const t = makeT(locale);
  const tuple = item ? resultTuple(selected.selection) : null;
  if (!item || !tuple) {
    return (
      <section className="discovery-panel discovery-removed" aria-label={t("Selected result")}>
        <h1>{t("Unavailable")}</h1>
        <p className="discovery-lede">
          {item ? t("The retained-result identity for this record is incomplete.") : t("This item is no longer in the supplied window.")}
        </p>
        <button type="button" className="discovery-action" onClick={onBack}>
          {t("Back to search")}
        </button>
      </section>
    );
  }
  // Object spread (not inline attributes) keeps the concurrent seam
  // forward-compatible without narrowing this file to one snapshot of it.
  const forward: KnowledgeProps & { requestedResult: RequestedResultTuple; onReturnToSearch: () => void } = {
    projection,
    locale,
    readResultReferences: sourceProps?.readResultReferences,
    readResult: sourceProps?.readResult,
    hostGeneration: sourceProps?.hostGeneration,
    draftPort: sourceProps?.draftPort,
    onOpenSource: sourceProps?.onOpenSource,
    requestedResult: tuple,
    onReturnToSearch: onBack,
  };
  return (
    <div className="discovery-source-host">
      <Knowledge {...forward} />
    </div>
  );
}

function SourcesView({
  view,
  locale,
  theme,
  selectedId,
  onSelect,
  onRefreshSources,
  onOpenPreferences,
}: {
  view: DiscoveryView;
  locale: "en" | "zh-CN";
  theme?: "dark" | "light";
  selectedId: string | null;
  onSelect: (key: string | null) => void;
  onRefreshSources?: () => void;
  onOpenPreferences?: () => void;
}) {
  const t = makeT(locale);
  const selected = selectedId
    ? view.sources.find((source) => sourceKey(source.id) === selectedId) ?? null
    : null;
  return (
    <section className="discovery-view">
      <header className="discovery-heading">
        <p className="discovery-eyebrow">{t("SEARCH AVAILABLE SOURCES")}</p>
        <h1>{t("Sources")}</h1>
        <p className="discovery-lede">{t("Review missing evidence and freshness")}</p>
      </header>
      {view.sources.length === 0 ? (
        <p className="discovery-muted">{t("No sources were supplied.")}</p>
      ) : null}
      <div className="discovery-source-controls">
        <button
          type="button"
          className="discovery-action"
          disabled={!onRefreshSources}
          onClick={onRefreshSources ? () => onRefreshSources() : undefined}
        >
          {t("Refresh observations")}
        </button>
        {!onRefreshSources ? <p className="discovery-reason">{t("Refreshing observations is not supplied on this surface.")}</p> : null}
        <button
          type="button"
          className="discovery-action"
          disabled={!onOpenPreferences}
          onClick={onOpenPreferences ? () => onOpenPreferences() : undefined}
        >
          {t("Open display preferences")}
        </button>
        {!onOpenPreferences ? <p className="discovery-reason">{t("Display preferences are not supplied on this surface.")}</p> : null}
        <div className="discovery-meta-row">
          <span className="discovery-meta-label">{t("Appearance")}</span>
          <span className="discovery-meta-value">
            {theme === "dark" ? t("Dark") : theme === "light" ? t("Light") : t("Not supplied")}
          </span>
        </div>
      </div>
      <div className="discovery-layout">
        <section className="discovery-panel discovery-results" aria-label={t("Supplied sources")}>
          {view.sources.length > 0 ? (
            <ul className="discovery-list">
              {view.sources.map((source) => (
                <li key={source.id}>
                  <button
                    type="button"
                    className={selectedId === sourceKey(source.id) ? "discovery-item discovery-item-selected" : "discovery-item"}
                    data-disc-item={sourceKey(source.id)}
                    aria-pressed={selectedId === sourceKey(source.id)}
                    onClick={() => onSelect(selectedId === sourceKey(source.id) ? null : sourceKey(source.id))}
                  >
                    <span className="discovery-item-kind">{source.owner}</span>
                    <span className="discovery-item-title">{source.title}</span>
                    <span className="discovery-item-summary">{contentChip(locale, source.content)}</span>
                    <span className="discovery-item-foot">
                      <span className={chipClass(source.state)}>{source.state}</span>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="discovery-muted">{t("No sources were supplied.")}</p>
          )}
        </section>
        <aside className="discovery-panel discovery-preview" aria-label={t("Supplied sources")}>
          {selected ? (
            <>
              <div className="discovery-preview-head">
                <span className="discovery-item-kind">{selected.owner}</span>
                <h2>{selected.title}</h2>
              </div>
              <MetaRow label={t("Reference")} value={clockLabel(locale, selected.reference)} />
              <MetaRow label={t("Revision")} value={clockLabel(locale, selected.revision)} />
              <MetaRow label={t("State")} value={selected.state} />
              <MetaRow label={t("Coverage")} value={selected.coverage} />
              <MetaRow label={t("Observed at")} value={clockLabel(locale, selected.observedAt)} />
              {selected.observedAt && selected.observedKind ? (
                <MetaRow
                  label={t("Observed at kind")}
                  value={selected.observedKind === "LOCAL_ACQUISITION" ? t("Local acquisition") : t("Source observation")}
                />
              ) : null}
              <MetaRow label={t("Source time")} value={clockLabel(locale, selected.sourceTime)} />
              {selected.content === "OBSERVED" ? (
                <p className="discovery-fineprint">{t("Observed copy supplied — a decoded projection, not the full canonical original.")}</p>
              ) : selected.content === "REFERENCE_ONLY" ? (
                <p className="discovery-fineprint">{t("Reference metadata only — original content is not supplied here. This is not an access denial.")}</p>
              ) : (
                <p className="discovery-fineprint">
                  {t("This source is unavailable here.")}
                  {selected.reason ? ` ${t("Reason")}: ${selected.reason}` : ""}
                </p>
              )}
              <p className="discovery-fineprint">{t("Health, connectivity or live status is not inferred here.")}</p>
            </>
          ) : (
            <p className="discovery-muted">{t("Select a supplied source to review its clocks and coverage.")}</p>
          )}
        </aside>
      </div>
      <div className="discovery-lower">
        <section className="discovery-panel discovery-systems" aria-label={t("System observations")}>
          <h2 className="discovery-section-title">{t("System observations")}</h2>
          {view.systems.length === 0 ? (
            <p className="discovery-muted">{t("No system observations were supplied.")}</p>
          ) : (
            <ul className="discovery-system-list">
              {view.systems.map((system, index) => (
                <li key={`${system.provider}:${index}`}>
                  <MetaRow label={t("Provider")} value={system.provider} />
                  <MetaRow label={t("Installed")} value={system.installed ? t("Yes") : t("No")} />
                  <MetaRow label={t("State")} value={system.state} />
                  <MetaRow label={t("Version")} value={clockLabel(locale, system.version)} />
                  <MetaRow label={t("Detail")} value={system.detail} />
                  <MetaRow label={t("Observed at")} value={clockLabel(locale, system.observedAt)} />
                </li>
              ))}
            </ul>
          )}
        </section>
        <section className="discovery-panel discovery-limitations" aria-label={t("Limitations")}>
          <h2 className="discovery-section-title">{t("Limitations")}</h2>
          {view.limitations.length === 0 ? (
            <p className="discovery-muted">{t("No limitations were supplied.")}</p>
          ) : (
            <dl className="discovery-limitations-list">
              {view.limitations.map((code) => (
                <div key={code} className="discovery-limitation">
                  <dt>{code}</dt>
                  <dd>{(locale === "zh-CN" ? LIMITATION_ZH[code] : LIMITATION_EN[code]) ?? code}</dd>
                </div>
              ))}
            </dl>
          )}
        </section>
      </div>
    </section>
  );
}

type CapabilityCallbacks = {
  onModeChange?: DiscoveryWorkspaceProps["onModeChange"];
  onOpenMetaCeo?: DiscoveryWorkspaceProps["onOpenMetaCeo"];
  onOpenKnowledge?: DiscoveryWorkspaceProps["onOpenKnowledge"];
};

const CAP_ACTIONS: Record<
  DiscoveryCapability["id"],
  { label: CopyKey; button: CopyKey; route: "meta_ceo" | "search" | "knowledge" | "sources" | "none" }
> = {
  direction_preview: { label: "Direction preview", button: "Open Meta-CEO office", route: "meta_ceo" },
  search: { label: "Search", button: "Open search", route: "search" },
  return_review: { label: "Return review", button: "Open return review", route: "knowledge" },
  source_context: { label: "Source context", button: "Open source context", route: "sources" },
  placement: { label: "Placement", button: "Open placement", route: "none" },
  release: { label: "Release", button: "Open release", route: "none" },
};

function CapabilityCard({
  capability,
  locale,
  callbacks,
}: {
  capability: DiscoveryCapability;
  locale: "en" | "zh-CN";
  callbacks: CapabilityCallbacks;
}) {
  const t = makeT(locale);
  const action = CAP_ACTIONS[capability.id];
  const routeAction =
    action.route === "meta_ceo"
      ? callbacks.onOpenMetaCeo
      : action.route === "search"
        ? callbacks.onModeChange
          ? () => callbacks.onModeChange?.("Search")
          : undefined
        : action.route === "sources"
          ? callbacks.onModeChange
            ? () => callbacks.onModeChange?.("Sources")
            : undefined
          : action.route === "knowledge"
            ? callbacks.onOpenKnowledge
            : undefined;
  const targetMatches = action.route !== "none" && capability.target === action.route;
  const enabled = capability.state !== "UNAVAILABLE" && targetMatches && typeof routeAction === "function";
  const reason =
    capability.state === "UNAVAILABLE" || !targetMatches
      ? `${t("Unavailable in the supplied capabilities; no action is offered.")} ${unavailablePort(locale, portLabel(locale, capability.target))}`
      : !routeAction
        ? needsPort(locale, portLabel(locale, capability.target))
        : null;
  const note =
    capability.state === "PREVIEW_ONLY"
      ? t("Preview only — sending is separate and unavailable here; this read-only surface never accepts or releases work.")
      : capability.state === "READ_ONLY"
        ? t("Read only")
        : null;
  return (
    <article className="discovery-capability">
      <div className="discovery-capability-head">
        <h3>{t(action.label)}</h3>
        <span className={capability.state === "UNAVAILABLE" ? "discovery-chip" : chipClass(capability.state)}>
          {capability.state === "READ_ONLY" ? t("Read only") : capability.state === "PREVIEW_ONLY" ? t("Preview only") : t("Unavailable")}
        </span>
      </div>
      {note ? <p className="discovery-fineprint">{note}</p> : null}
      <button type="button" className="discovery-action" disabled={!enabled} onClick={enabled ? routeAction : undefined}>
        {t(action.button)}
      </button>
      {reason ? <p className="discovery-reason">{reason}</p> : null}
    </article>
  );
}

function ToolsView({
  view,
  projection,
  locale,
  onModeChange,
  onOpenMetaCeo,
  onOpenKnowledge,
}: {
  view: DiscoveryView;
  projection: OfficeProjection;
  locale: "en" | "zh-CN";
  onModeChange?: DiscoveryWorkspaceProps["onModeChange"];
  onOpenMetaCeo?: DiscoveryWorkspaceProps["onOpenMetaCeo"];
  onOpenKnowledge?: DiscoveryWorkspaceProps["onOpenKnowledge"];
}) {
  const t = makeT(locale);
  const context = projection.context;
  const callbacks: CapabilityCallbacks = { onModeChange, onOpenMetaCeo, onOpenKnowledge };
  const [selectedCapability, setSelectedCapability] = useState<DiscoveryCapability["id"] | null>(null);
  const selected = view.capabilities.find((item) => item.id === selectedCapability)
    ?? view.capabilities.find((item) => item.state !== "UNAVAILABLE") ?? view.capabilities[0];
  return (
    <section className="discovery-view">
      <header className="discovery-heading">
        <p className="discovery-eyebrow">{t("CAPABILITIES, IN CONTEXT")}</p>
        <h1>{t("Tools")}</h1>
        <p className="discovery-lede">
          {t("Capabilities shown here come from the supplied view only. Buttons open existing routes; button presence never grants permission, and this read-only surface never sends work.")}
        </p>
      </header>
      <div className="discovery-layout discovery-tools-layout">
        <section className="discovery-panel discovery-tool-inspector" aria-label={t("Selected tool")}>
          <h2 className="discovery-section-title">{t("Selected tool")}</h2>
          {selected ? <CapabilityCard capability={selected} locale={locale} callbacks={callbacks} /> :
            <p className="discovery-muted">{t("No capabilities were supplied.")}</p>}
          <details className="discovery-preview-section"><summary>{t("Project context")}</summary>
            <MetaRow label={t("Work reference")} value={context.selection?.workRef ?? t("Not supplied")} />
            <MetaRow label={t("Root job")} value={context.selection?.rootJobId ?? t("Not supplied")} />
            <MetaRow label={t("Session")} value={context.sessionRef ?? t("Not supplied")} />
            <MetaRow label={t("Binding generation")} value={context.bindingGeneration === null ? t("Not supplied") : String(context.bindingGeneration)} />
          </details>
        </section>
        <section className="discovery-panel discovery-capabilities" aria-label={t("Other tools")}>
          <h2 className="discovery-section-title">{t("Other tools")}</h2>
          {view.capabilities.length === 0 ? <p className="discovery-muted">{t("No capabilities were supplied.")}</p> :
            <ul className="discovery-list">{view.capabilities.map((capability) => {
              const label = t(CAP_ACTIONS[capability.id].label);
              return <li key={capability.id}><button type="button" className="discovery-item"
                aria-label={label} aria-pressed={selected?.id === capability.id}
                onClick={() => setSelectedCapability(capability.id)}>
                <span className="discovery-item-title">{label}</span>
                <span className="discovery-muted">{capability.state === "READ_ONLY" ? t("Read only") : capability.state === "PREVIEW_ONLY" ? t("Preview only") : t("Unavailable")}</span>
              </button></li>;
            })}</ul>}
        </section>
      </div>
    </section>
  );
}

function DiscoveryBody(props: DiscoveryWorkspaceProps) {
  const {
    view,
    projection,
    mode,
    locale: localeProp,
    theme,
    sourceProps,
    onOpenProject,
    onOpenConversation,
    onModeChange,
    onOpenMetaCeo,
    onOpenKnowledge,
    onOpenPreferences,
    onRefreshSources,
  } = props;
  const locale: "en" | "zh-CN" = localeProp === "zh-CN" ? "zh-CN" : "en";
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<FilterState>({ kind: "all", expanded: false });
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedResult, setSelectedResult] = useState<SelectedResultState | null>(null);
  const rootRef = useRef<HTMLDivElement | null>(null);
  const focusReturnRef = useRef<string | null>(null);

  // Selection is derived from the current view on every render and withheld
  // when its record is no longer supplied.
  const selectedItem = selectedId
    ? view.items.find((item) => item.id === selectedId) ?? null
    : null;
  const detourItem = selectedResult
    ? view.items.find((item) => item.id === selectedResult.itemId) ?? null
    : null;

  const closeSelection = () => {
    focusReturnRef.current = selectedId;
    setSelectedId(null);
  };
  const backToSearch = () => {
    focusReturnRef.current = selectedId;
    setSelectedResult(null);
  };
  const openResult = (item: DiscoveryItem) => {
    if (item.target.kind !== "result") return;
    setSelectedResult({ itemId: item.id, selection: item.target.selection, role: item.target.role });
  };
  const onKeyDown = (event: ReactKeyboardEvent<HTMLDivElement>) => {
    if (event.key !== "Escape" || event.nativeEvent.isComposing) return;
    if (selectedResult) {
      event.preventDefault();
      backToSearch();
      return;
    }
    if (selectedId) {
      event.preventDefault();
      closeSelection();
    }
  };
  // Focus returns to the invoking list item after a selection or source detour
  // closes; the query and the caller-owned unsent draft are untouched. The
  // detour closes while the selection is still set, so the guard checks the
  // detour only.
  useEffect(() => {
    if (selectedResult !== null) return;
    const pending = focusReturnRef.current;
    if (!pending) return;
    focusReturnRef.current = null;
    const root = rootRef.current;
    if (!root) return;
    const target = root.querySelector<HTMLElement>(`[data-disc-item="${CSS.escape(pending)}"]`);
    target?.focus();
  }, [selectedId, selectedResult]);

  const body =
    mode === "Search" ? (
      <SearchView
        view={view}
        locale={locale}
        query={query}
        filter={filter}
        selectedId={selectedId}
        selectedItem={selectedItem}
        sourceProps={sourceProps}
        onOpenProject={onOpenProject}
        onOpenConversation={onOpenConversation}
        onQuery={(value) => {
          setQuery(value);
          setFilter((current) => ({ ...current, expanded: false }));
        }}
        onFilter={(kind) => setFilter({ kind, expanded: false })}
        onExpand={() => setFilter((current) => ({ ...current, expanded: true }))}
        onInspect={(id) => {
          focusReturnRef.current = null;
          setSelectedId(id);
        }}
        onOpenResult={openResult}
      />
    ) : mode === "Sources" ? (
      <SourcesView
        view={view}
        locale={locale}
        theme={theme}
        selectedId={selectedId}
        onSelect={setSelectedId}
        onRefreshSources={onRefreshSources}
        onOpenPreferences={onOpenPreferences}
      />
    ) : (
      <ToolsView
        view={view}
        projection={projection}
        locale={locale}
        onModeChange={onModeChange}
        onOpenMetaCeo={onOpenMetaCeo}
        onOpenKnowledge={onOpenKnowledge}
      />
    );

  if (selectedResult && mode === "Search") {
    return (
      <div ref={rootRef} className="atelier-discovery" lang={locale} onKeyDown={onKeyDown}>
        <SourceDetour
          projection={projection}
          locale={locale}
          selected={selectedResult}
          item={detourItem}
          sourceProps={sourceProps}
          onBack={backToSearch}
        />
      </div>
    );
  }
  return (
    <div ref={rootRef} className="atelier-discovery" lang={locale} onKeyDown={onKeyDown}>
      {body}
    </div>
  );
}

/** The workspace renders only while the supplied view still describes the
 * actual projection (auth, selected work, session, binding, revisions). On any
 * mismatch it shows nothing private; otherwise the private body is keyed by
 * the same identity, so auth/selection/host changes clear query, filter,
 * selection and any open source before paint. */
export function DiscoveryWorkspace(props: DiscoveryWorkspaceProps) {
  const locale: "en" | "zh-CN" = props.locale === "zh-CN" ? "zh-CN" : "en";
  if (!contextMatches(props.view.context, props.projection.context)) {
    return (
      <section className="atelier-discovery discovery-unavailable" lang={locale}>
        <h1>{makeT(locale)("Unavailable")}</h1>
        <p className="discovery-lede">
          {makeT(locale)("The supplied view does not match the current projection, so this surface keeps no saved query, selection or source content.")}
        </p>
      </section>
    );
  }
  return <DiscoveryBody key={bodyIdentity(props.projection, props.sourceProps)} {...props} />;
}
