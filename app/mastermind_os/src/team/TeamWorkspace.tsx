import { useRef, useState, type ReactNode } from "react";
import type { MissionHost } from "../host";
import type { TeamBot, TeamRosterRead } from "./team-roster";
import { DelegatedTaskCard } from "./DelegatedTaskCard";
import { NewBotPanel } from "./NewBotPanel";
import { NewGroupPanel } from "./NewGroupPanel";
import { BotSettingsPanel } from "./BotSettingsPanel";
import { RoutinesPanel } from "./RoutinesPanel";
import { InboxNeedsYouPanel } from "./InboxNeedsYouPanel";
import { SplitConversationsWorkspace } from "./SplitConversationsWorkspace";
import { SearchContextView } from "./SearchContextView";
import { WorkHierarchyView } from "./WorkHierarchyView";
import type { DelegatedTask } from "./delegated-task";
import "./team.css";

/** Distinct conversation gateway states (HS01 + D2). A code-based classifier
 *  keeps labels honest: unknown codes stay unknown, never "healthy". */
export type TeamGatewayState =
  | "live" | "viewer-disconnected" | "gateway-busy" | "quota" | "unknown";

const VIEWER_DISCONNECTED = new Set([
  "NATIVE_PLATFORM_UNAVAILABLE",
  "NATIVE_CLIENT_NOT_STARTED",
  "NATIVE_CLIENT_UNAVAILABLE",
  "NATIVE_INSTALL_UNAVAILABLE",
]);

export function classifyGatewayState(
  state: string | null,
  code: string | null,
): TeamGatewayState {
  if (state === "OPENED" || state === "ADMITTED") return "live";
  if (code !== null && VIEWER_DISCONNECTED.has(code))
    return "viewer-disconnected";
  if (code === "NATIVE_BUSY") return "gateway-busy";
  if (code !== null && code.includes("QUOTA")) return "quota";
  return "unknown";
}

/** Human-readable copy for the producer's CLOSED reason vocabulary
 * (bridge.py team_roster / control_plane/team_roster_projection.py). The code
 * itself always stays visible; an unmapped code renders as the code alone —
 * never a guessed explanation. */
const REASON_COPY: Record<string, { en: string; zh: string }> = {
  GATEWAY_IDENTIFY_READY: {
    en: "Gateway verified by control-socket identify",
    zh: "控制套接字 identify 已验证网关",
  },
  GATEWAY_LOCK_PID_VERIFIED: {
    en: "Gateway verified by lock file and running process",
    zh: "锁文件与运行进程已验证网关",
  },
  NO_GATEWAY_LOCK: {
    en: "No gateway lock observed",
    zh: "未观察到网关锁",
  },
  GATEWAY_PID_NOT_RUNNING: {
    en: "Locked gateway process is not running",
    zh: "锁定的网关进程未在运行",
  },
  GATEWAY_PID_RECYCLED: {
    en: "Locked pid now runs another process",
    zh: "锁定的 pid 已被其他进程占用",
  },
  GATEWAY_PID_START_MISMATCH: {
    en: "Locked pid start time does not match",
    zh: "锁定的 pid 启动时间不匹配",
  },
  NO_STATE_DB: {
    en: "No state database on disk",
    zh: "磁盘上没有状态数据库",
  },
  STATE_DB_UNREADABLE: {
    en: "State database could not be read",
    zh: "状态数据库无法读取",
  },
  NO_SESSIONS: {
    en: "No sessions recorded yet",
    zh: "尚无已记录的会话",
  },
  ACTIVITY_TIMESTAMP_INVALID: {
    en: "Recorded activity timestamp is invalid",
    zh: "记录的活动时间戳无效",
  },
};

function ReasonCode({ code, locale }: { code: string; locale: "en" | "zh-CN" }) {
  const copy = REASON_COPY[code];
  const phrase = copy ? (locale === "zh-CN" ? copy.zh : copy.en) : code;
  return (
    <>
      {phrase !== code ? `${phrase} ` : null}
      <code>{code}</code>
    </>
  );
}

const STRINGS = {
  en: {
    heading: "Team roster",
    headingSummary:
      "The enrolled company roster with each teammate's host, readiness and current focus.",
    rosterLabel: "Team roster",
    colTeammate: "Teammate",
    colState: "State",
    colFocus: "Current focus",
    openEntry: (name: string) => `Open ${name}`,
    backToRoster: "← Team",
    stateReady: "Ready",
    stateDegraded: "Degraded",
    stateUnknown: "Unknown",
    activity: (value: string) => `Last activity ${value}`,
    activityNever: "No activity observed",
    host: (value: string) => `Host ${value}`,
    gateway: (value: string) => `Gateway ${value}`,
    rosterPendingChip: "Reading roster",
    rosterPendingTitle: "Reading the team roster…",
    rosterPendingBody:
      "The roster is read once from the local native runtime when this view opens. Nothing is shown or inferred until it returns.",
    rosterUnavailableTitle: "Team needs a connection",
    rosterUnavailableChip: "Roster not verified",
    rosterUnavailableBody:
      "Connect to the team source to confirm who is enrolled and available.",
    rosterUnavailableBody2:
      "Previously opened conversations stay accessible. Their last-known status may be out of date.",
    rosterSizeLabel: "Current team size",
    rosterSizeValue: "Not verified",
    presenceLabel: "Presence",
    presenceValue: "Not observed",
    checkConnection: "Check connection",
    openRecent: "Open recent conversations",
    rosterUnavailableNote:
      "An unavailable source is never shown as an empty company.",
    rosterInvalidNote:
      "The roster source returned data this surface could not verify. Nothing is shown from it.",
    rosterReadLabel: "Native roster read",
    toolbarLabel: "Team actions",
    newGroup: "New group",
    newBot: "＋ New bot",
    botSettings: "Bot settings",
    routines: "Routines",
    needsYou: "Needs you",
    splitView: "Split view",
    searchMode: "/ Search",
    workMode: "/ Work",
    conversationHeading: "Conversation",
    conversationSectionNote:
      "No conversation is bound to this runtime profile in this view.",
    gatewayLive: "Live",
    gatewayDisconnected: "Viewer disconnected",
    gatewayBusy: "Gateway busy",
    gatewayQuota: "Quota limited",
    gatewayUnknown: "Connection unknown",
    gatewayBusyNote:
      "The team gateway is handling one operation. Try again when it is free.",
    gatewayDisconnectedNote:
      "This viewer cannot reach the team gateway. Saved conversations and drafts are preserved.",
    gatewayQuotaNote:
      "The gateway reports a quota limit. No automatic fallback is attempted.",
    gatewayUnknownNote:
      "The connection state is not confirmed. Controls stay limited until it is.",
    previewChip: "PREVIEW",
    workHeading: "Delegated coding work",
    noTask: "No delegated coding task is projected for this teammate yet.",
    profileLabel: "Profile",
    roleLabel: "Role",
    hostLabel: "Host",
    gatewayLabel: "Gateway instance",
    managedLabel: "Managed profile",
    managedYes: "Yes",
    managedNo: "No",
    readinessLabel: "Readiness",
    activityLabel: "Last activity",
    gatewaySourceLabel: "Gateway source",
  },
  "zh-CN": {
    heading: "团队名册",
    headingSummary:
      "已登记的公司名册，显示每位成员的主机、就绪状态与当前工作。",
    rosterLabel: "团队名册",
    colTeammate: "成员",
    colState: "状态",
    colFocus: "当前工作",
    openEntry: (name: string) => `打开 ${name}`,
    backToRoster: "← 团队",
    stateReady: "就绪",
    stateDegraded: "降级",
    stateUnknown: "未知",
    activity: (value: string) => `最近活动 ${value}`,
    activityNever: "未观察到活动",
    host: (value: string) => `主机 ${value}`,
    gateway: (value: string) => `网关 ${value}`,
    rosterPendingChip: "正在读取名册",
    rosterPendingTitle: "正在读取团队名册…",
    rosterPendingBody:
      "打开此视图时从本地原生运行时读取一次名册；在返回之前，不显示也不推断任何内容。",
    rosterUnavailableTitle: "团队需要连接",
    rosterUnavailableChip: "名册未验证",
    rosterUnavailableBody: "连接团队来源，以确认谁已登记、谁可用。",
    rosterUnavailableBody2: "此前打开的对话仍可访问。其最近状态可能已过期。",
    rosterSizeLabel: "当前团队规模",
    rosterSizeValue: "未验证",
    presenceLabel: "在线状态",
    presenceValue: "未观测",
    checkConnection: "检查连接",
    openRecent: "打开最近的对话",
    rosterUnavailableNote: "来源不可用时，绝不显示为空公司。",
    rosterInvalidNote:
      "名册来源返回的数据无法通过验证，因此不显示其中任何内容。",
    rosterReadLabel: "原生名册读取",
    toolbarLabel: "团队操作",
    newGroup: "新群组",
    newBot: "＋ 新机器人",
    botSettings: "机器人设置",
    routines: "例行事务",
    needsYou: "待你处理",
    splitView: "分屏对话",
    searchMode: "/ 搜索",
    workMode: "/ 工作",
    conversationHeading: "对话",
    conversationSectionNote:
      "此视图未为该运行配置绑定对话。",
    gatewayLive: "在线",
    gatewayDisconnected: "查看端已断开",
    gatewayBusy: "网关繁忙",
    gatewayQuota: "配额受限",
    gatewayUnknown: "连接未知",
    gatewayBusyNote: "团队网关正在处理一项操作。空闲后可重试。",
    gatewayDisconnectedNote:
      "当前查看端无法连接团队网关。已保存的对话与草稿均已保留。",
    gatewayQuotaNote: "网关报告配额限制。不会自动切换到其他通道。",
    gatewayUnknownNote: "连接状态尚未确认。在确认之前，操作保持受限。",
    previewChip: "预览",
    workHeading: "受派的编码工作",
    noTask: "尚未为该成员投影受派的编码任务。",
    profileLabel: "简介",
    roleLabel: "角色",
    hostLabel: "主机",
    gatewayLabel: "网关实例",
    managedLabel: "受管资料",
    managedYes: "是",
    managedNo: "否",
    readinessLabel: "就绪状态",
    activityLabel: "最近活动",
    gatewaySourceLabel: "网关来源",
  },
};

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).slice(0, 2);
  return (
    parts
      .map((part) => [...part][0] ?? "")
      .join("")
      .toUpperCase() || "·"
  );
}

function readinessLabel(bot: TeamBot, t: typeof STRINGS.en): string {
  return bot.readiness === "ready"
    ? t.stateReady
    : bot.readiness === "degraded"
      ? t.stateDegraded
      : t.stateUnknown;
}

/** B's contract keeps `host: "unknown"` for an unobserved host — never render
 *  the literal sentinel as if it were an observed hostname. */
function observedHost(bot: TeamBot): string | null {
  return bot.host !== "unknown" ? bot.host : null;
}

export function TeamWorkspace({
  locale = "en",
  roster,
  conversationPanel,
  gateway,
  delegatedTask,
  host,
  onOpenConversations,
  onOpenCode,
  onCheckConnection,
  previewAuthority = true,
  runtimeOnly = false,
}: {
  locale?: "en" | "zh-CN";
  roster: TeamRosterRead;
  /** The EXISTING conversation surface node (App-owned). Never a second transport. */
  conversationPanel?: ReactNode;
  gateway?: { state: string | null; code: string | null };
  delegatedTask?: DelegatedTask | null;
  /** Host carrying the model-configuration read for bot settings (HC09).
   *  Falls back to the existing window host facade, the CodeWorkspace way;
   *  absent → BotSettingsPanel renders its honest unavailable state. */
  host?: MissionHost;
  onOpenConversations?: () => void;
  onOpenCode?: () => void;
  onCheckConnection?: () => void;
  /** True while this surface can only observe (PREVIEW chips stay honest). */
  previewAuthority?: boolean;
  /** Company actions remain with the company consumer in the shared shell. */
  runtimeOnly?: boolean;
}) {
  const t = runtimeOnly ? { ...STRINGS[locale],
    heading: locale === "zh-CN" ? "运行配置" : "Runtime profiles",
    headingSummary: locale === "zh-CN" ? "本地已登记的 Hermes 运行配置与观测到的运行状态。" : "Locally enrolled Hermes profiles and their observed runtime state.",
    rosterLabel: locale === "zh-CN" ? "运行配置" : "Runtime profiles",
    backToRoster: locale === "zh-CN" ? "← 运行配置" : "← Runtime profiles",
    rosterUnavailableTitle: locale === "zh-CN" ? "运行配置来源不可用" : "Runtime profiles could not be read",
    rosterUnavailableBody: locale === "zh-CN" ? "当前无法核验本地运行配置。" : "The local profile source could not be verified.",
    rosterUnavailableNote: locale === "zh-CN" ? "运行配置的当前可用性尚未核验。" : "Current profile availability is not verified.",
  } : STRINGS[locale];
  const [selectedBotId, setSelectedBotId] = useState<string | null>(null);
  const [surface, setSurface] = useState<
    | "new-bot"
    | "new-group"
    | "bot-settings"
    | "routines"
    | "needs-you"
    | "split"
    | "search"
    | "work"
    | null
  >(null);
  /** Search-mode selection is owned here so the panel stays controlled and
   *  Escape/toolbar switches reset it — never a stale highlighted result. */
  const [searchSelection, setSearchSelection] = useState<string | null>(null);
  /** A Paper board mode (HC10/HC18/HC19/HC20/HC21) replaces the roster table;
   *  the create panels (HC02/HC03) stay overlays above whatever is shown. */
  const modeSurface =
    surface === "routines" ||
    surface === "needs-you" ||
    surface === "split" ||
    surface === "search" ||
    surface === "work";
  const rosterButtons = useRef<(HTMLButtonElement | null)[]>([]);
  const resolvedHost =
    host ??
    (typeof window !== "undefined"
      ? window.MastermindMissionHost
      : undefined);

  if (roster.kind === "UNAVAILABLE") {
    return (
      <section
        className="mm-team mm-team-unavailable"
        aria-labelledby="mm-team-heading"
      >
        <h1 id="mm-team-heading" tabIndex={-1}>
          {t.heading}
        </h1>
        <div className="card mm-team-connect">
          <p className="mm-eyebrow">{t.rosterUnavailableChip}</p>
          <h2>{t.rosterUnavailableTitle}</h2>
          <p>
            {roster.reason === "NATIVE_RESPONSE_INVALID"
              ? t.rosterInvalidNote
              : t.rosterUnavailableBody}
          </p>
          <p className="muted">{t.rosterUnavailableBody2}</p>
          <p className="muted">
            {t.rosterReadLabel}: <code>{roster.reason}</code>
          </p>
          <dl>
            <div>
              <dt>{t.rosterSizeLabel}</dt>
              <dd>{t.rosterSizeValue}</dd>
            </div>
            <div>
              <dt>{t.presenceLabel}</dt>
              <dd>{t.presenceValue}</dd>
            </div>
          </dl>
          <div className="mm-team-connect-actions">
            {onCheckConnection ? (
              <button
                type="button"
                className="mm-primary"
                onClick={onCheckConnection}
              >
                {t.checkConnection}
              </button>
            ) : null}
            {onOpenConversations ? (
              <button type="button" onClick={onOpenConversations}>
                {t.openRecent}
              </button>
            ) : null}
          </div>
          <p className="muted">{t.rosterUnavailableNote}</p>
        </div>
      </section>
    );
  }

  if (roster.kind === "PENDING") {
    return (
      <section
        className="mm-team mm-team-unavailable"
        aria-labelledby="mm-team-heading"
        aria-busy="true"
      >
        <h1 id="mm-team-heading" tabIndex={-1}>
          {t.heading}
        </h1>
        <div className="card mm-team-connect">
          <p className="mm-eyebrow">{t.rosterPendingChip}</p>
          <h2>{t.rosterPendingTitle}</h2>
          <p>{t.rosterPendingBody}</p>
        </div>
      </section>
    );
  }

  const bots = roster.roster.bots;
  const selected = bots.find((bot) => bot.id === selectedBotId) ?? null;
  const gatewayState = classifyGatewayState(
    gateway?.state ?? null,
    gateway?.code ?? null,
  );

  const focusRow = (index: number) => {
    const target = rosterButtons.current[index];
    if (target) target.focus();
  };
  const onRosterKeyDown = (event: React.KeyboardEvent, index: number) => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      focusRow(Math.min(index + 1, bots.length - 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      focusRow(Math.max(index - 1, 0));
    } else if (event.key === "Home") {
      event.preventDefault();
      focusRow(0);
    } else if (event.key === "End") {
      event.preventDefault();
      focusRow(bots.length - 1);
    }
  };

  if (selected) {
    const host = observedHost(selected);
    return (
      <section
        className="mm-team mm-team-detail"
        aria-labelledby="mm-team-heading"
      >
        <h1 id="mm-team-heading" tabIndex={-1}>
          {t.heading}
        </h1>
        <button
          type="button"
          className="mm-team-back"
          onClick={() => setSelectedBotId(null)}
        >
          {t.backToRoster}
        </button>
        <div className="mm-team-detail-grid">
          <div className="mm-team-conversation">
            <header className="mm-team-bot-head">
              <div className="mm-avatar" aria-hidden="true">
                {initials(selected.displayName)}
              </div>
              <div>
                <h2>{selected.displayName}</h2>
                <p className="muted">
                  {selected.role}
                  {host ? ` · ${host}` : ""}
                </p>
              </div>
              {previewAuthority ? (
                <span className="mm-chip mm-chip-preview">{t.previewChip}</span>
              ) : null}
              <div className="mm-team-bot-head-actions">
                <button
                  type="button"
                  className="mm-toolbar-button"
                  onClick={() => setSurface("bot-settings")}
                >
                  {t.botSettings}
                </button>
              </div>
            </header>
            <dl className="mm-team-bot-facts">
              <div>
                <dt>{t.readinessLabel}</dt>
                <dd data-readiness={selected.readiness}>
                  {readinessLabel(selected, t)} —{" "}
                  <ReasonCode
                    code={selected.readinessReason}
                    locale={locale}
                  />
                </dd>
              </div>
              <div>
                <dt>{t.activityLabel}</dt>
                <dd>
                  {selected.lastActivity
                    ? t.activity(selected.lastActivity)
                    : t.activityNever}
                  {!selected.lastActivity && selected.activityReason ? (
                    <>
                      {" "}
                      —{" "}
                      <ReasonCode
                        code={selected.activityReason}
                        locale={locale}
                      />
                    </>
                  ) : null}
                </dd>
              </div>
              <div>
                <dt>{t.gatewayLabel}</dt>
                <dd>
                  {selected.gateway.instanceId ?? t.stateUnknown}
                  {selected.gateway.observed && selected.gateway.state
                    ? ` · ${selected.gateway.state}`
                    : ""}
                </dd>
              </div>
              <div>
                <dt>{t.gatewaySourceLabel}</dt>
                <dd>
                  <code>{selected.gateway.source}</code>
                  {selected.gateway.authorityEpoch !== null
                    ? ` · epoch ${selected.gateway.authorityEpoch}`
                    : ""}
                </dd>
              </div>
              <div>
                <dt>{t.managedLabel}</dt>
                <dd>
                  {selected.managed === null
                    ? t.stateUnknown
                    : selected.managed
                      ? t.managedYes
                      : t.managedNo}
                </dd>
              </div>
              {selected.profilePath ? (
                <div>
                  <dt>{t.profileLabel}</dt>
                  <dd>{selected.profilePath}</dd>
                </div>
              ) : null}
            </dl>
            {runtimeOnly ? <p className="muted">{t.conversationSectionNote}</p> : <>
            <h3>{t.conversationHeading}</h3>
            <p
              className={`mm-gateway mm-gateway-${gatewayState}`}
              role="status"
            >
              {gatewayState === "live"
                ? t.gatewayLive
                : gatewayState === "viewer-disconnected"
                  ? t.gatewayDisconnected
                  : gatewayState === "gateway-busy"
                    ? t.gatewayBusy
                    : gatewayState === "quota"
                      ? t.gatewayQuota
                      : t.gatewayUnknown}
            </p>
            <p className="muted mm-gateway-note">
              {gatewayState === "gateway-busy"
                ? t.gatewayBusyNote
                : gatewayState === "viewer-disconnected"
                  ? t.gatewayDisconnectedNote
                  : gatewayState === "quota"
                    ? t.gatewayQuotaNote
                    : gatewayState === "unknown"
                      ? t.gatewayUnknownNote
                      : null}
            </p>
            {conversationPanel ?? (
              <p className="muted">{t.conversationSectionNote}</p>
            )}
            <h3>{t.workHeading}</h3>
            {delegatedTask ? (
              <DelegatedTaskCard
                task={delegatedTask}
                locale={locale}
                onOpenCode={onOpenCode}
              />
            ) : (
              <p className="muted">{t.noTask}</p>
            )}
            </>}
          </div>
        </div>
        {surface === "bot-settings" && selected ? (
          <BotSettingsPanel
            locale={locale}
            bot={selected}
            host={resolvedHost}
            onClose={() => setSurface(null)}
          />
        ) : null}
      </section>
    );
  }

  return (
    <section className="mm-team" aria-labelledby="mm-team-heading">
      <h1 id="mm-team-heading" tabIndex={-1}>
        {t.heading}
      </h1>
      <p className="muted">{t.headingSummary}</p>
      {!runtimeOnly && <div className="mm-team-toolbar" role="toolbar" aria-label={t.toolbarLabel}>
        {(
          [
            ["routines", t.routines],
            ["needs-you", t.needsYou],
            ["split", t.splitView],
            ["search", t.searchMode],
            ["work", t.workMode],
          ] as const
        ).map(([mode, label]) => (
          <button
            key={mode}
            type="button"
            className="mm-toolbar-button"
            aria-pressed={surface === mode}
            onClick={() => {
              setSearchSelection(null);
              setSurface(surface === mode ? null : mode);
            }}
          >
            {label}
          </button>
        ))}
        <button
          type="button"
          className="mm-toolbar-button"
          onClick={() => setSurface("new-group")}
        >
          {t.newGroup}
        </button>
        <button
          type="button"
          className="mm-primary mm-toolbar-primary"
          onClick={() => setSurface("new-bot")}
        >
          {t.newBot}
        </button>
      </div>}
      {!runtimeOnly && modeSurface ? null : (
      <table className="mm-roster" aria-label={t.rosterLabel}>
        <thead>
          <tr>
            <th scope="col" className="mm-col-teammate">
              {t.colTeammate}
            </th>
            <th scope="col" className="mm-col-state">
              {t.colState}
            </th>
            <th scope="col" className="mm-col-focus">
              {t.colFocus}
            </th>
            <th scope="col" className="mm-col-go" aria-hidden="true"></th>
          </tr>
        </thead>
        <tbody>
          {bots.map((bot, index) => (
            <tr key={bot.id} data-readiness={bot.readiness}>
              <td className="mm-col-teammate">
                <button
                  type="button"
                  className="mm-roster-row"
                  ref={(node) => {
                    rosterButtons.current[index] = node;
                  }}
                  aria-label={t.openEntry(bot.displayName)}
                  onKeyDown={(event) => onRosterKeyDown(event, index)}
                  onClick={() => setSelectedBotId(bot.id)}
                >
                  <span className="mm-avatar" aria-hidden="true">
                    {initials(bot.displayName)}
                  </span>
                  <span className="mm-roster-name">{bot.displayName}</span>
                  {observedHost(bot) ? (
                    <span className="mm-roster-host">{observedHost(bot)}</span>
                  ) : null}
                </button>
              </td>
              <td className="mm-col-state">
                <span
                  className="mm-roster-state"
                  data-readiness={bot.readiness}
                >
                  {readinessLabel(bot, t)}
                  <small>
                    <ReasonCode code={bot.readinessReason} locale={locale} />
                  </small>
                </span>
              </td>
              <td className="mm-col-focus">
                {bot.activitySummary ?? (
                  <span className="muted">{t.stateUnknown}</span>
                )}
                {bot.lastActivity ? (
                  <small className="mm-roster-activity">
                    {t.activity(bot.lastActivity)}
                  </small>
                ) : bot.activityReason ? (
                  <small className="mm-roster-activity">
                    <ReasonCode code={bot.activityReason} locale={locale} />
                  </small>
                ) : null}
              </td>
              <td className="mm-col-go" aria-hidden="true">
                ›
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      )}
      {!runtimeOnly && surface === "routines" ? (
        <RoutinesPanel
          locale={locale}
          roster={roster.roster}
          routine={null}
          onBack={() => setSurface(null)}
        />
      ) : null}
      {!runtimeOnly && surface === "needs-you" ? (
        <InboxNeedsYouPanel locale={locale} roster={roster} requests={null} />
      ) : null}
      {!runtimeOnly && surface === "split" ? (
        <SplitConversationsWorkspace locale={locale} panes={[]} />
      ) : null}
      {!runtimeOnly && surface === "search" ? (
        <SearchContextView
          locale={locale}
          query=""
          results={null}
          selectedId={searchSelection}
          onSelectResult={setSearchSelection}
          onCloseSelection={() => setSearchSelection(null)}
        />
      ) : null}
      {!runtimeOnly && surface === "work" ? (
        <WorkHierarchyView
          locale={locale}
          parentWork={null}
          delegated={null}
          selectedTask={null}
        />
      ) : null}
      {!runtimeOnly && surface === "new-bot" ? (
        <NewBotPanel
          locale={locale}
          roster={roster}
          gatewayState={gatewayState}
          onClose={() => setSurface(null)}
        />
      ) : null}
      {!runtimeOnly && surface === "new-group" ? (
        <NewGroupPanel
          locale={locale}
          roster={roster}
          gatewayState={gatewayState}
          onClose={() => setSurface(null)}
        />
      ) : null}
    </section>
  );
}
