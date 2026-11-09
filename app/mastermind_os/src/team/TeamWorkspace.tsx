import { useRef, useState, type ReactNode } from "react";
import type { TeamRosterEntry, TeamRosterRead } from "./team-roster-contract";
import { DelegatedTaskCard } from "./DelegatedTaskCard";
import type { DelegatedTask } from "./delegated-task";
import "./team.css";

/** Distinct conversation gateway states (HS01 + D2). A code-based classifier
 *  keeps labels honest: unknown codes stay unknown, never "healthy". */
export type TeamGatewayState = "live" | "viewer-disconnected" | "gateway-busy" | "quota" | "unknown";

const VIEWER_DISCONNECTED = new Set(["NATIVE_PLATFORM_UNAVAILABLE", "NATIVE_CLIENT_NOT_STARTED", "NATIVE_CLIENT_UNAVAILABLE", "NATIVE_INSTALL_UNAVAILABLE"]);

export function classifyGatewayState(state: string | null, code: string | null): TeamGatewayState {
  if (state === "OPENED" || state === "ADMITTED") return "live";
  if (code !== null && VIEWER_DISCONNECTED.has(code)) return "viewer-disconnected";
  if (code === "NATIVE_BUSY") return "gateway-busy";
  if (code !== null && code.includes("QUOTA")) return "quota";
  return "unknown";
}

const STRINGS = {
  en: {
    heading: "Team roster",
    headingSummary: "The enrolled company roster with each teammate's host, readiness and current focus.",
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
    rosterUnavailableTitle: "Team needs a connection",
    rosterUnavailableChip: "Roster not verified",
    rosterUnavailableBody: "Connect to the team source to confirm who is enrolled and available.",
    rosterUnavailableBody2: "Previously opened conversations stay accessible. Their last-known status may be out of date.",
    rosterSizeLabel: "Current team size",
    rosterSizeValue: "Not verified",
    presenceLabel: "Presence",
    presenceValue: "Not observed",
    checkConnection: "Check connection",
    openRecent: "Open recent conversations",
    rosterUnavailableNote: "An unavailable source is never shown as an empty company.",
    rosterInvalidNote: "The roster source returned data this surface could not verify. Nothing is shown from it.",
    conversationHeading: "Conversation",
    conversationSectionNote: "The existing persistent conversation surface. This view never creates a second transport.",
    gatewayLive: "Live",
    gatewayDisconnected: "Viewer disconnected",
    gatewayBusy: "Gateway busy",
    gatewayQuota: "Quota limited",
    gatewayUnknown: "Connection unknown",
    gatewayBusyNote: "The team gateway is handling one operation. Try again when it is free.",
    gatewayDisconnectedNote: "This viewer cannot reach the team gateway. Saved conversations and drafts are preserved.",
    gatewayQuotaNote: "The gateway reports a quota limit. No automatic fallback is attempted.",
    gatewayUnknownNote: "The connection state is not confirmed. Controls stay limited until it is.",
    previewChip: "PREVIEW",
    workHeading: "Delegated coding work",
    noTask: "No delegated coding task is projected for this teammate yet.",
    profileLabel: "Profile",
    roleLabel: "Role",
    hostLabel: "Host",
    gatewayLabel: "Gateway instance",
    readinessLabel: "Readiness",
    activityLabel: "Last activity",
  },
  "zh-CN": {
    heading: "团队名册",
    headingSummary: "已登记的公司名册，显示每位成员的主机、就绪状态与当前工作。",
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
    rosterInvalidNote: "名册来源返回的数据无法通过验证，因此不显示其中任何内容。",
    conversationHeading: "对话",
    conversationSectionNote: "既有的持久对话界面。此视图绝不创建第二个传输通道。",
    gatewayLive: "在线",
    gatewayDisconnected: "查看端已断开",
    gatewayBusy: "网关繁忙",
    gatewayQuota: "配额受限",
    gatewayUnknown: "连接未知",
    gatewayBusyNote: "团队网关正在处理一项操作。空闲后可重试。",
    gatewayDisconnectedNote: "当前查看端无法连接团队网关。已保存的对话与草稿均已保留。",
    gatewayQuotaNote: "网关报告配额限制。不会自动切换到其他通道。",
    gatewayUnknownNote: "连接状态尚未确认。在确认之前，操作保持受限。",
    previewChip: "预览",
    workHeading: "受派的编码工作",
    noTask: "尚未为该成员投影受派的编码任务。",
    profileLabel: "简介",
    roleLabel: "角色",
    hostLabel: "主机",
    gatewayLabel: "网关实例",
    readinessLabel: "就绪状态",
    activityLabel: "最近活动",
  },
};

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).slice(0, 2);
  return parts.map(part => [...part][0] ?? "").join("").toUpperCase() || "·";
}

function readinessLabel(entry: TeamRosterEntry, t: typeof STRINGS.en): string {
  return entry.readiness === "ready" ? t.stateReady : entry.readiness === "degraded" ? t.stateDegraded : t.stateUnknown;
}

export function TeamWorkspace({ locale = "en", roster, conversationPanel, gateway, delegatedTask, onOpenConversations, onOpenCode, onCheckConnection, previewAuthority = true }: {
  locale?: "en" | "zh-CN";
  roster: TeamRosterRead;
  /** The EXISTING conversation surface node (App-owned). Never a second transport. */
  conversationPanel?: ReactNode;
  gateway?: { state: string | null; code: string | null };
  delegatedTask?: DelegatedTask | null;
  onOpenConversations?: () => void;
  onOpenCode?: () => void;
  onCheckConnection?: () => void;
  /** True while this surface can only observe (PREVIEW chips stay honest). */
  previewAuthority?: boolean;
}) {
  const t = STRINGS[locale];
  const [selectedBotId, setSelectedBotId] = useState<string | null>(null);
  const rosterButtons = useRef<(HTMLButtonElement | null)[]>([]);

  if (roster.kind === "UNAVAILABLE") {
    return (
      <section className="mm-team mm-team-unavailable" aria-labelledby="mm-team-heading">
        <h1 id="mm-team-heading" tabIndex={-1}>{t.heading}</h1>
        <div className="card mm-team-connect">
          <p className="mm-eyebrow">{t.rosterUnavailableChip}</p>
          <h2>{t.rosterUnavailableTitle}</h2>
          <p>{roster.reason === "TEAM_ROSTER_SOURCE_INVALID" ? t.rosterInvalidNote : t.rosterUnavailableBody}</p>
          <p className="muted">{t.rosterUnavailableBody2}</p>
          <dl>
            <div><dt>{t.rosterSizeLabel}</dt><dd>{t.rosterSizeValue}</dd></div>
            <div><dt>{t.presenceLabel}</dt><dd>{t.presenceValue}</dd></div>
          </dl>
          <div className="mm-team-connect-actions">
            {onCheckConnection ? <button type="button" className="mm-primary" onClick={onCheckConnection}>{t.checkConnection}</button> : null}
            {onOpenConversations ? <button type="button" onClick={onOpenConversations}>{t.openRecent}</button> : null}
          </div>
          <p className="muted">{t.rosterUnavailableNote}</p>
        </div>
      </section>
    );
  }

  const bots = roster.kind === "AVAILABLE" ? roster.roster.bots : [];
  const selected = bots.find(bot => bot.botId === selectedBotId) ?? null;
  const gatewayState = classifyGatewayState(gateway?.state ?? null, gateway?.code ?? null);

  const focusRow = (index: number) => {
    const target = rosterButtons.current[index];
    if (target) target.focus();
  };
  const onRosterKeyDown = (event: React.KeyboardEvent, index: number) => {
    if (event.key === "ArrowDown") { event.preventDefault(); focusRow(Math.min(index + 1, bots.length - 1)); }
    else if (event.key === "ArrowUp") { event.preventDefault(); focusRow(Math.max(index - 1, 0)); }
    else if (event.key === "Home") { event.preventDefault(); focusRow(0); }
    else if (event.key === "End") { event.preventDefault(); focusRow(bots.length - 1); }
  };

  if (selected) {
    return (
      <section className="mm-team mm-team-detail" aria-labelledby="mm-team-heading">
        <h1 id="mm-team-heading" tabIndex={-1}>{t.heading}</h1>
        <button type="button" className="mm-team-back" onClick={() => setSelectedBotId(null)}>{t.backToRoster}</button>
        <div className="mm-team-detail-grid">
          <div className="mm-team-conversation">
            <header className="mm-team-bot-head">
              <div className="mm-avatar" aria-hidden="true">{initials(selected.displayName)}</div>
              <div>
                <h2>{selected.displayName}</h2>
                <p className="muted">{selected.role}{selected.host ? ` · ${selected.host}` : ""}</p>
              </div>
              {previewAuthority ? <span className="mm-chip mm-chip-preview">{t.previewChip}</span> : null}
            </header>
            <dl className="mm-team-bot-facts">
              <div><dt>{t.readinessLabel}</dt><dd data-readiness={selected.readiness}>{readinessLabel(selected, t)}{selected.readinessReason ? ` — ${selected.readinessReason}` : ""}</dd></div>
              <div><dt>{t.activityLabel}</dt><dd>{selected.lastActivity ? t.activity(selected.lastActivity) : t.activityNever}</dd></div>
              <div><dt>{t.gatewayLabel}</dt><dd>{selected.gatewayInstance ?? t.stateUnknown}</dd></div>
              {selected.profile ? <div><dt>{t.profileLabel}</dt><dd>{selected.profile}</dd></div> : null}
            </dl>
            <h3>{t.conversationHeading}</h3>
            <p className={`mm-gateway mm-gateway-${gatewayState}`} role="status">
              {gatewayState === "live" ? t.gatewayLive
                : gatewayState === "viewer-disconnected" ? t.gatewayDisconnected
                : gatewayState === "gateway-busy" ? t.gatewayBusy
                : gatewayState === "quota" ? t.gatewayQuota
                : t.gatewayUnknown}
            </p>
            <p className="muted mm-gateway-note">
              {gatewayState === "gateway-busy" ? t.gatewayBusyNote
                : gatewayState === "viewer-disconnected" ? t.gatewayDisconnectedNote
                : gatewayState === "quota" ? t.gatewayQuotaNote
                : gatewayState === "unknown" ? t.gatewayUnknownNote : null}
            </p>
            {conversationPanel ?? <p className="muted">{t.conversationSectionNote}</p>}
            <h3>{t.workHeading}</h3>
            {delegatedTask ? <DelegatedTaskCard task={delegatedTask} locale={locale} onOpenCode={onOpenCode} />
              : <p className="muted">{t.noTask}</p>}
          </div>
        </div>
      </section>
    );
  }

  return (
    <section className="mm-team" aria-labelledby="mm-team-heading">
      <h1 id="mm-team-heading" tabIndex={-1}>{t.heading}</h1>
      <p className="muted">{t.headingSummary}</p>
      <table className="mm-roster" aria-label={t.rosterLabel}>
        <thead>
          <tr>
            <th scope="col" className="mm-col-teammate">{t.colTeammate}</th>
            <th scope="col" className="mm-col-state">{t.colState}</th>
            <th scope="col" className="mm-col-focus">{t.colFocus}</th>
            <th scope="col" className="mm-col-go" aria-hidden="true"></th>
          </tr>
        </thead>
        <tbody>
          {bots.map((bot, index) => (
            <tr key={bot.botId} data-readiness={bot.readiness}>
              <td className="mm-col-teammate">
                <button
                  type="button"
                  className="mm-roster-row"
                  ref={node => { rosterButtons.current[index] = node; }}
                  aria-label={t.openEntry(bot.displayName)}
                  onKeyDown={event => onRosterKeyDown(event, index)}
                  onClick={() => setSelectedBotId(bot.botId)}
                >
                  <span className="mm-avatar" aria-hidden="true">{initials(bot.displayName)}</span>
                  <span className="mm-roster-name">{bot.displayName}</span>
                  {bot.host ? <span className="mm-roster-host">{bot.host}</span> : null}
                </button>
              </td>
              <td className="mm-col-state">
                <span className="mm-roster-state" data-readiness={bot.readiness}>
                  {readinessLabel(bot, t)}
                  {bot.readinessReason ? <small>{bot.readinessReason}</small> : null}
                </span>
              </td>
              <td className="mm-col-focus">
                {bot.activitySummary ?? <span className="muted">{t.stateUnknown}</span>}
                {bot.lastActivity ? <small className="mm-roster-activity">{t.activity(bot.lastActivity)}</small> : null}
              </td>
              <td className="mm-col-go" aria-hidden="true">›</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
