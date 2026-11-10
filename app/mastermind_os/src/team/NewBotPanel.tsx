import { useId, useState } from "react";
import type { TeamRosterRead } from "./team-roster";
import type { TeamGatewayState } from "./TeamWorkspace";
import { TeamSurfaceDialog } from "./TeamSurfaceDialog";

/** HC02 — New teammate surface: role and launch. Every person shown comes
 *  from the real roster read; the launch route stays honest because no team
 *  model policy is exposed to this surface; and the primary action can only
 *  land in the honest "not wired" state — no create-teammate route exists on
 *  this connection, so nothing is ever sent or faked. */
const STRINGS = {
  en: {
    title: "New teammate",
    heading: "Give your bot a role and a place on the team.",
    nameLabel: "Name",
    nameHint: "You can change this later.",
    roleLabel: "What should this bot do?",
    roleHint: "Clear scope helps the team know when to involve this bot.",
    startFromLabel: "Start from",
    startFromHint: "Or use an existing teammate's instructions and capabilities.",
    startFresh: "Start fresh",
    rosterUnavailableOption: "Roster not verified on this connection",
    rosterPendingOption: "Reading the roster…",
    rosterUnavailablePrefix: "Roster read:",
    emptyRosterHint: "The verified roster has no teammates yet.",
    accessTitle: "Access & capabilities",
    accessEdit: "Edit →",
    accessEditReason:
      "Capability editing is not wired on this connection. This card describes what a new teammate starts with.",
    accessBody: "Fresh personal memory. Credentials stay with the connection.",
    launchTitle: "Launch route",
    launchTeamDefault: "Team default",
    launchChange: "Change",
    launchChangeReason:
      "The team's launch policy is not exposed on this connection, so the route cannot be changed here.",
    launchBody: "Model and placement follow your team's policy.",
    launchUnknownNote:
      "This connection does not verify the team's model policy, so no specific model or provider is claimed.",
    advanced: "Advanced settings",
    notProjected: "Not projected in this build.",
    previewLabel: "PREVIEW",
    previewUnnamed: "Unnamed teammate",
    previewNoRole: "No role described yet",
    notCreatedChip: "Not created yet",
    step1: "Create a profile",
    step2: "Start the bot",
    step3: "Open its conversation",
    step3Note: "You'll see Ready when the bot can respond.",
    stepsLabel: "Creation steps",
    teamNote: "Make it part of the team",
    teamNoteBody:
      "A created teammate joins the roster read with its own host and readiness.",
    cancel: "Cancel",
    submit: "Create teammate",
    notWiredChip: "Not wired on this connection",
    effectNoneChip: "EFFECT·NONE",
    notWiredBody:
      "No create-teammate route exists on this connection. Nothing was sent and no teammate was created.",
    closeLabel: "Close new teammate surface",
    gatewayNote: {
      live: "Team gateway is live on this connection.",
      else: "The team gateway is not verified on this connection.",
    },
  },
  "zh-CN": {
    title: "新队友",
    heading: "为你的机器人设定角色与团队位置。",
    nameLabel: "名称",
    nameHint: "以后可以更改。",
    roleLabel: "这个机器人应该做什么？",
    roleHint: "清晰的职责范围能帮助团队判断何时需要这位成员。",
    startFromLabel: "从谁开始",
    startFromHint: "或沿用一位现有成员的指令与能力。",
    startFresh: "从零开始",
    rosterUnavailableOption: "此连接未验证名册",
    rosterPendingOption: "正在读取名册…",
    rosterUnavailablePrefix: "名册读取：",
    emptyRosterHint: "已验证的名册中还没有成员。",
    accessTitle: "权限与能力",
    accessEdit: "编辑 →",
    accessEditReason:
      "能力编辑未在此连接上接通。此卡片只描述新队友的初始状态。",
    accessBody: "全新的个人记忆。凭据保留在连接中。",
    launchTitle: "启动路由",
    launchTeamDefault: "团队默认",
    launchChange: "更改",
    launchChangeReason:
      "此连接未暴露团队的启动策略，因此无法在此更改路由。",
    launchBody: "模型与部署位置遵循你的团队策略。",
    launchUnknownNote:
      "此连接未验证团队的模型策略，因此不指明任何具体模型或提供商。",
    advanced: "高级设置",
    notProjected: "此构建尚未投影。",
    previewLabel: "预览",
    previewUnnamed: "未命名队友",
    previewNoRole: "尚未描述职责",
    notCreatedChip: "尚未创建",
    step1: "创建资料",
    step2: "启动机器人",
    step3: "打开它的对话",
    step3Note: "机器人可以响应时，你会看到“就绪”。",
    stepsLabel: "创建步骤",
    teamNote: "让它成为团队的一员",
    teamNoteBody: "创建的队友会以自己的主机与就绪状态加入名册读取。",
    cancel: "取消",
    submit: "创建队友",
    notWiredChip: "此连接未接通",
    effectNoneChip: "无效果",
    notWiredBody:
      "此连接上不存在创建队友的路由。未发送任何请求，也未创建任何队友。",
    closeLabel: "关闭新队友界面",
    gatewayNote: {
      live: "团队网关在此连接上在线。",
      else: "此连接未验证团队网关。",
    },
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

export function NewBotPanel({
  locale = "en",
  roster,
  gatewayState,
  onClose,
}: {
  locale?: "en" | "zh-CN";
  /** The SAME real roster read the roster table renders — no second source. */
  roster: TeamRosterRead;
  gatewayState?: TeamGatewayState;
  onClose: () => void;
}) {
  const t = STRINGS[locale];
  const nameId = useId();
  const roleId = useId();
  const startFromId = useId();
  const accessReasonId = useId();
  const launchReasonId = useId();
  const [name, setName] = useState("");
  const [role, setRole] = useState("");
  const [startFrom, setStartFrom] = useState("");
  const [notWired, setNotWired] = useState(false);

  const bots = roster.kind === "AVAILABLE" ? roster.roster.bots : null;
  const rosterReason =
    roster.kind === "UNAVAILABLE" ? roster.reason : null;

  return (
    <TeamSurfaceDialog
      title={t.title}
      closeLabel={t.closeLabel}
      onClose={onClose}
      wide
    >
      <div className="mm-surface-body">
        <form
          className="mm-surface-main"
          onSubmit={(event) => {
            event.preventDefault();
            // Honest terminal state: no create-teammate backend route exists
            // on this connection. Never fake a created teammate.
            setNotWired(true);
          }}
        >
          <p className="mm-surface-heading">{t.heading}</p>
          <div className="mm-field">
            <label htmlFor={nameId}>{t.nameLabel}</label>
            <input
              id={nameId}
              value={name}
              maxLength={120}
              onChange={(event) => setName(event.target.value)}
              aria-describedby={`${nameId}-hint`}
            />
            <p className="mm-field-hint" id={`${nameId}-hint`}>
              {t.nameHint}
            </p>
          </div>
          <div className="mm-field">
            <label htmlFor={roleId}>{t.roleLabel}</label>
            <textarea
              id={roleId}
              value={role}
              rows={3}
              maxLength={600}
              onChange={(event) => setRole(event.target.value)}
              aria-describedby={`${roleId}-hint`}
            />
            <p className="mm-field-hint" id={`${roleId}-hint`}>
              {t.roleHint}
            </p>
          </div>
          <div className="mm-field">
            <label htmlFor={startFromId}>{t.startFromLabel}</label>
            <select
              id={startFromId}
              value={startFrom}
              disabled={!bots}
              onChange={(event) => setStartFrom(event.target.value)}
              aria-describedby={`${startFromId}-hint`}
            >
              {bots ? (
                <>
                  <option value="">{t.startFresh}</option>
                  {bots.map((bot) => (
                    <option key={bot.id} value={bot.id}>
                      {bot.displayName}
                    </option>
                  ))}
                </>
              ) : (
                <option value="">
                  {roster.kind === "PENDING"
                    ? t.rosterPendingOption
                    : t.rosterUnavailableOption}
                </option>
              )}
            </select>
            <p className="mm-field-hint" id={`${startFromId}-hint`}>
              {t.startFromHint}
              {rosterReason ? (
                <>
                  {" "}
                  {t.rosterUnavailablePrefix} <code>{rosterReason}</code>
                </>
              ) : null}
              {bots && bots.length === 0 ? (
                <>
                  {" "}
                  {t.emptyRosterHint}
                </>
              ) : null}
            </p>
          </div>
          <section className="mm-surface-card" aria-label={t.accessTitle}>
            <div className="mm-surface-card-head">
              <h3>{t.accessTitle}</h3>
              <button
                type="button"
                className="mm-card-action"
                disabled
                aria-describedby={accessReasonId}
              >
                {t.accessEdit}
              </button>
            </div>
            <p className="mm-surface-card-body">{t.accessBody}</p>
            <p className="mm-card-action-reason" id={accessReasonId}>
              {t.accessEditReason}
            </p>
          </section>
          <section className="mm-surface-card" aria-label={t.launchTitle}>
            <div className="mm-surface-card-head">
              <h3>{t.launchTitle}</h3>
              <span className="mm-surface-value">{t.launchTeamDefault}</span>
              <button
                type="button"
                className="mm-card-action"
                disabled
                aria-describedby={launchReasonId}
              >
                {t.launchChange}
              </button>
            </div>
            <p className="mm-surface-card-body">{t.launchBody}</p>
            <p className="mm-card-action-reason" id={launchReasonId}>
              {t.launchChangeReason} {t.launchUnknownNote}
              {gatewayState ? (
                <>
                  {" "}
                  {gatewayState === "live"
                    ? t.gatewayNote.live
                    : t.gatewayNote.else}
                </>
              ) : null}
            </p>
          </section>
          <details className="mm-surface-details">
            <summary>{t.advanced} ›</summary>
            <p className="muted">{t.notProjected}</p>
          </details>
          {notWired ? (
            <div className="mm-not-wired" role="status">
              <div className="mm-not-wired-chips">
                <span className="mm-chip mm-chip-state" data-state="unknown">
                  {t.notWiredChip}
                </span>
                <span className="mm-chip mm-chip-effect-none">
                  {t.effectNoneChip}
                </span>
              </div>
              <p className="mm-not-wired-body">{t.notWiredBody}</p>
            </div>
          ) : null}
          <div className="mm-surface-actions">
            <button type="button" onClick={onClose}>
              {t.cancel}
            </button>
            <button type="submit" className="mm-primary">
              {t.submit}
            </button>
          </div>
        </form>
        <aside className="mm-surface-side">
          <p className="mm-eyebrow">{t.previewLabel}</p>
          <div className="mm-preview-teammate">
            <span className="mm-avatar" aria-hidden="true">
              {initials(name)}
            </span>
            <div>
              <p className="mm-preview-name">
                {name.trim() || t.previewUnnamed}
              </p>
              <p className="mm-preview-role">
                {role.trim() || t.previewNoRole}
              </p>
            </div>
            <span className="mm-chip mm-chip-state" data-state="unknown">
              {t.notCreatedChip}
            </span>
          </div>
          <ol className="mm-steps" aria-label={t.stepsLabel}>
            <li className="mm-step">
              <span className="mm-step-num">01</span>
              <div>
                <p className="mm-step-title">{t.step1}</p>
              </div>
            </li>
            <li className="mm-step">
              <span className="mm-step-num">02</span>
              <div>
                <p className="mm-step-title">{t.step2}</p>
              </div>
            </li>
            <li className="mm-step">
              <span className="mm-step-num">03</span>
              <div>
                <p className="mm-step-title">{t.step3}</p>
                <p className="mm-step-note">{t.step3Note}</p>
              </div>
            </li>
          </ol>
          <div className="mm-preview-note">
            <p className="mm-step-title">{t.teamNote}</p>
            <p className="mm-step-note">{t.teamNoteBody}</p>
          </div>
        </aside>
      </div>
    </TeamSurfaceDialog>
  );
}

