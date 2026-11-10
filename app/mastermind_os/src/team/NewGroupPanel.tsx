import { useId, useState } from "react";
import type { TeamRosterRead } from "./team-roster";
import type { TeamGatewayState } from "./TeamWorkspace";
import { TeamSurfaceDialog } from "./TeamSurfaceDialog";

/** HC03 — New group surface: members and room behavior. Members, the
 *  searchable teammate count and the selected count all come from the real
 *  roster read and the user's real selection. The roster contract carries no
 *  member cap, so none is invented (the Paper "up to 6" is sample data).
 *  Creating a group has no backend route on this connection — the primary
 *  action lands in the honest "not wired" state, never a fake success. */
const STRINGS = {
  en: {
    title: "New group",
    heading: "Give the right teammates a shared place to work.",
    nameLabel: "Group name",
    purposeLabel: "Purpose",
    purposeHint: "Everyone in the room can use this shared direction.",
    membersLabel: "Members",
    selectedCount: (count: number) => `${count} selected`,
    searchTeammates: (count: number) => `Search ${count} teammates…`,
    searchUnavailable: "Member search unavailable",
    rosterPendingBody: "Reading the roster…",
    noMatches: "No teammates match this search.",
    addTeammates: "＋ Add teammates",
    addTeammatesNote:
      "Search picks from the same verified roster the Team view reads.",
    removeMember: (name: string) => `Remove ${name}`,
    respondHeading: "Who responds?",
    respondAutomatic: "Automatic",
    respondAutomaticNote: "The room brings in the relevant members.",
    respondLead: "Lead",
    respondLeadNote: "One teammate coordinates the responses.",
    respondEveryone: "Everyone",
    respondEveryoneNote: "Each selected teammate gets a turn.",
    availabilityHeading: "Room availability",
    availabilityAlwaysOn: "Always-on available",
    availabilityAlwaysOnNote:
      "This room can continue when you close the app.",
    availabilityGatewayLive: "Team gateway is live on this connection.",
    availabilityGatewayUnknown:
      "Whether the room can continue depends on the team gateway, which is not verified on this connection.",
    sharedContextHeading: "Shared context",
    addContext: "＋ Add file or project",
    addContextReason:
      "Attaching files or projects is not wired on this connection.",
    roomBehaviorLabel: "ROOM BEHAVIOR",
    cancel: "Cancel",
    submit: "Create group",
    notWiredChip: "Not wired on this connection",
    effectNoneChip: "EFFECT·NONE",
    notWiredBody:
      "No create-group route exists on this connection. Nothing was sent and no group was created.",
    closeLabel: "Close new group surface",
  },
  "zh-CN": {
    title: "新群组",
    heading: "为合适的成员提供一个共享的工作空间。",
    nameLabel: "群组名称",
    purposeLabel: "目的",
    purposeHint: "房间里的每个人都可以使用这份共享方向。",
    membersLabel: "成员",
    selectedCount: (count: number) => `已选择 ${count} 位`,
    searchTeammates: (count: number) => `搜索 ${count} 位成员…`,
    searchUnavailable: "成员搜索不可用",
    rosterPendingBody: "正在读取名册…",
    noMatches: "没有匹配此搜索的成员。",
    addTeammates: "＋ 添加成员",
    addTeammatesNote: "搜索范围与团队视图读取的已验证名册相同。",
    removeMember: (name: string) => `移除 ${name}`,
    respondHeading: "谁来响应？",
    respondAutomatic: "自动",
    respondAutomaticNote: "房间会召集相关的成员。",
    respondLead: "主持人",
    respondLeadNote: "由一位成员协调响应。",
    respondEveryone: "所有人",
    respondEveryoneNote: "每位选中的成员依次发言。",
    availabilityHeading: "房间可用性",
    availabilityAlwaysOn: "常时在线",
    availabilityAlwaysOnNote: "关闭应用后，此房间仍可继续。",
    availabilityGatewayLive: "团队网关在此连接上在线。",
    availabilityGatewayUnknown:
      "房间能否继续取决于团队网关，而此连接未验证网关状态。",
    sharedContextHeading: "共享上下文",
    addContext: "＋ 添加文件或项目",
    addContextReason: "附加文件或项目未在此连接上接通。",
    roomBehaviorLabel: "房间行为",
    cancel: "取消",
    submit: "创建群组",
    notWiredChip: "此连接未接通",
    effectNoneChip: "无效果",
    notWiredBody:
      "此连接上不存在创建群组的路由。未发送任何请求，也未创建任何群组。",
    closeLabel: "关闭新群组界面",
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

export function NewGroupPanel({
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
  const purposeId = useId();
  const searchId = useId();
  const contextReasonId = useId();
  const [name, setName] = useState("");
  const [purpose, setPurpose] = useState("");
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  const [responders, setResponders] =
    useState<"automatic" | "lead" | "everyone">("automatic");
  const [alwaysOn, setAlwaysOn] = useState(true);
  const [notWired, setNotWired] = useState(false);

  const bots = roster.kind === "AVAILABLE" ? roster.roster.bots : null;
  const rosterReason = roster.kind === "UNAVAILABLE" ? roster.reason : null;
  const search = query.trim().toLowerCase();
  const matches = (bots ?? []).filter((bot) =>
    !search
      ? true
      : [bot.displayName, bot.role].some((text) =>
          text.toLowerCase().includes(search),
        ),
  );
  const selectedBots = (bots ?? []).filter((bot) =>
    selected.includes(bot.id),
  );
  const toggle = (id: string) =>
    setSelected((current) =>
      current.includes(id)
        ? current.filter((item) => item !== id)
        : [...current, id],
    );

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
            // Honest terminal state: no create-group backend route exists on
            // this connection. Never fake a created group.
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
            />
          </div>
          <div className="mm-field">
            <label htmlFor={purposeId}>{t.purposeLabel}</label>
            <textarea
              id={purposeId}
              value={purpose}
              rows={2}
              maxLength={600}
              onChange={(event) => setPurpose(event.target.value)}
              aria-describedby={`${purposeId}-hint`}
            />
            <p className="mm-field-hint" id={`${purposeId}-hint`}>
              {t.purposeHint}
            </p>
          </div>
          <fieldset className="mm-member-picker">
            <legend>{t.membersLabel}</legend>
            <p className="mm-member-count" aria-live="polite">
              {t.selectedCount(selected.length)}
              {/* No cap text: the roster contract carries no member cap, and
                  the Paper "up to 6" is sample data. */}
            </p>
            {bots ? (
              <>
                <input
                  id={searchId}
                  type="search"
                  value={query}
                  placeholder={t.searchTeammates(bots.length)}
                  maxLength={120}
                  aria-label={t.searchTeammates(bots.length)}
                  onChange={(event) => setQuery(event.target.value)}
                />
                <ul className="mm-member-results" aria-label={t.membersLabel}>
                  {matches.map((bot) => (
                    <li key={bot.id}>
                      <button
                        type="button"
                        className="mm-member-option"
                        aria-pressed={selected.includes(bot.id)}
                        onClick={() => toggle(bot.id)}
                      >
                        <span className="mm-avatar" aria-hidden="true">
                          {initials(bot.displayName)}
                        </span>
                        <span className="mm-member-name">
                          {bot.displayName}
                        </span>
                        {bot.role ? (
                          <span className="mm-member-role">{bot.role}</span>
                        ) : null}
                      </button>
                    </li>
                  ))}
                  {matches.length === 0 ? (
                    <li className="mm-member-empty">{t.noMatches}</li>
                  ) : null}
                </ul>
                {selectedBots.length > 0 ? (
                  <ul className="mm-member-selected">
                    {selectedBots.map((bot) => (
                      <li key={bot.id}>
                        <span>{bot.displayName}</span>
                        <button
                          type="button"
                          className="mm-member-remove"
                          aria-label={t.removeMember(bot.displayName)}
                          onClick={() => toggle(bot.id)}
                        >
                          ✕
                        </button>
                      </li>
                    ))}
                  </ul>
                ) : null}
                <button
                  type="button"
                  className="mm-card-action mm-add-teammates"
                  onClick={() =>
                    document.getElementById(searchId)?.focus()
                  }
                >
                  {t.addTeammates}
                </button>
                <p className="mm-field-hint">{t.addTeammatesNote}</p>
              </>
            ) : (
              <div className="mm-member-unavailable">
                <p className="mm-surface-value">{t.searchUnavailable}</p>
                <p className="mm-field-hint">
                  {rosterReason ? (
                    <>
                      <code>{rosterReason}</code>
                    </>
                  ) : (
                    t.rosterPendingBody
                  )}
                </p>
              </div>
            )}
          </fieldset>
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
          <p className="mm-eyebrow">{t.roomBehaviorLabel}</p>
          <fieldset className="mm-room-fieldset">
            <legend>{t.respondHeading}</legend>
            <label className="mm-radio">
              <input
                type="radio"
                name="mm-group-responders"
                value="automatic"
                checked={responders === "automatic"}
                onChange={() => setResponders("automatic")}
              />
              <span>
                <span className="mm-radio-title">{t.respondAutomatic}</span>
                <span className="mm-radio-note">{t.respondAutomaticNote}</span>
              </span>
            </label>
            <label className="mm-radio">
              <input
                type="radio"
                name="mm-group-responders"
                value="lead"
                checked={responders === "lead"}
                onChange={() => setResponders("lead")}
              />
              <span>
                <span className="mm-radio-title">{t.respondLead}</span>
                <span className="mm-radio-note">{t.respondLeadNote}</span>
              </span>
            </label>
            <label className="mm-radio">
              <input
                type="radio"
                name="mm-group-responders"
                value="everyone"
                checked={responders === "everyone"}
                onChange={() => setResponders("everyone")}
              />
              <span>
                <span className="mm-radio-title">{t.respondEveryone}</span>
                <span className="mm-radio-note">{t.respondEveryoneNote}</span>
              </span>
            </label>
          </fieldset>
          <fieldset className="mm-room-fieldset">
            <legend>{t.availabilityHeading}</legend>
            <label className="mm-radio mm-radio-check">
              <input
                type="checkbox"
                checked={alwaysOn}
                onChange={(event) => setAlwaysOn(event.target.checked)}
              />
              <span>
                <span className="mm-radio-title">
                  {t.availabilityAlwaysOn}
                </span>
                <span className="mm-radio-note">
                  {t.availabilityAlwaysOnNote}
                </span>
              </span>
            </label>
            <p
              className={`mm-gateway ${
                gatewayState === "live"
                  ? "mm-gateway-live"
                  : "mm-gateway-unknown"
              }`}
            >
              {gatewayState === "live"
                ? t.availabilityGatewayLive
                : t.availabilityGatewayUnknown}
            </p>
          </fieldset>
          <fieldset className="mm-room-fieldset">
            <legend>{t.sharedContextHeading}</legend>
            <button
              type="button"
              className="mm-card-action"
              disabled
              aria-describedby={contextReasonId}
            >
              {t.addContext}
            </button>
            <p className="mm-card-action-reason" id={contextReasonId}>
              {t.addContextReason}
            </p>
          </fieldset>
        </aside>
      </div>
    </TeamSurfaceDialog>
  );
}
