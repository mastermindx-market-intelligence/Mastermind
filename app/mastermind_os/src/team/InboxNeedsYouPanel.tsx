import { useId, useMemo, useRef, useState } from "react";
import type { TeamBot, TeamRosterRead } from "./team-roster";
import "./conversation-surfaces.css";

/** Needs-you inbox (HC18): waiting requests from the roster plus the exact
 *  ask of the selected request. Every identity comes from the roster and every
 *  card from the `requests` projection — `null` renders the honest unwired
 *  state, never a fabricated inbox. No send path exists on this surface. */

export type InboxRequestKind = "question" | "result_review" | "action_needed";

/** One observed message inside a request's conversation excerpt. */
export interface InboxExcerptMessage {
  author: string;
  text: string;
  at: string;
}

export interface InboxRequest {
  id: string;
  /** Roster key of the waiting teammate — resolved against `roster`, never a hardcoded name. */
  teammateId: string;
  kind: InboxRequestKind;
  summary: string;
  /** ISO timestamp; the kind · age chip is computed from this value. */
  waitingSince: string;
  /** Exact-request option labels. Absent or empty = no exact options projected. */
  options?: string[];
  conversationExcerpt: InboxExcerptMessage[] | null;
}

/** Pinned/archived inbox rows (HC18 rail). Display-only: no open callback is
 *  projected yet, so they never render as fake affordances. */
export interface InboxSideRow {
  id: string;
  label: string;
}

const STRINGS = {
  en: {
    heading: "Needs you",
    searchLabel: "Search messages and people",
    waitingSection: "WAITING FOR YOUR RESPONSE",
    readingKeepsOpen: "Reading keeps requests open.",
    pinnedSection: "PINNED",
    archivedSection: "ARCHIVED",
    archivedView: "View →",
    kindQuestion: "Question",
    kindResultReview: "Result to review",
    kindActionNeeded: "Action needed",
    ageNow: "now",
    ageMinutes: (value: number) => `${value} min`,
    ageHours: (value: number) => `${value} h`,
    ageDays: (value: number) => `${value} d`,
    ageUnknown: "unknown age",
    noMatches: (query: string) => `No matches for “${query}”.`,
    emptyInbox: "No requests are waiting for your response.",
    unavailableChip: "Requests not wired",
    unavailableTitle: "No request projection is wired",
    unavailableBody:
      "The needs-you inbox reads from a request projection that this surface has not been given. Nothing is shown or invented.",
    unavailableNote: "An unwired source is never shown as an empty inbox.",
    selectPrompt: "Select a request to read the exact ask.",
    missingSelection: "The selected request is not in the current list.",
    waitingForAnswer: "Waiting for your answer",
    openBeside: "Open beside",
    details: "Details",
    actionUnavailableReason: "This action is not wired to a live surface yet.",
    identityUnverified: "Teammate identity not verified against the roster.",
    excerptHeading: "Request conversation",
    excerptNone: "No conversation excerpt is projected for this request.",
    exactRequestLabel: "EXACT REQUEST",
    noOptions: "No exact options are projected for this request.",
    answerUnavailableReason:
      "Answering needs a wired answer path. Reading keeps the request open.",
    composerTo: (name: string) => `To ${name} · Private conversation`,
    composerPlaceholder: "No send path is wired. Reply is unavailable.",
    send: "Send",
    sendUnavailable: "Send is unavailable",
    composerReason:
      "No send path exists on this surface. Nothing can be sent from here.",
    openRequest: (name: string) => `Open request from ${name}`,
  },
  "zh-CN": {
    heading: "需要你",
    searchLabel: "搜索消息与成员",
    waitingSection: "等待你的回复",
    readingKeepsOpen: "阅读不会关闭请求。",
    pinnedSection: "已置顶",
    archivedSection: "已归档",
    archivedView: "查看 →",
    kindQuestion: "问题",
    kindResultReview: "待审结果",
    kindActionNeeded: "需要行动",
    ageNow: "刚刚",
    ageMinutes: (value: number) => `${value} 分钟`,
    ageHours: (value: number) => `${value} 小时`,
    ageDays: (value: number) => `${value} 天`,
    ageUnknown: "时长未知",
    noMatches: (query: string) => `没有与“${query}”匹配的结果。`,
    emptyInbox: "暂无等待你回复的请求。",
    unavailableChip: "请求来源未接通",
    unavailableTitle: "尚未接入请求投影",
    unavailableBody:
      "此收件箱从一个尚未接入的请求投影读取数据。不会显示或虚构任何内容。",
    unavailableNote: "来源未接通时，绝不显示为空收件箱。",
    selectPrompt: "选择一条请求以阅读确切内容。",
    missingSelection: "所选请求不在当前列表中。",
    waitingForAnswer: "等待你的回答",
    openBeside: "在旁边打开",
    details: "详情",
    actionUnavailableReason: "此操作尚未接入可用界面。",
    identityUnverified: "成员身份尚未通过名册核验。",
    excerptHeading: "请求对话",
    excerptNone: "该请求未投影对话摘录。",
    exactRequestLabel: "确切请求",
    noOptions: "该请求未投影确切选项。",
    answerUnavailableReason: "回答需要已接通的回复通道。阅读不会关闭请求。",
    composerTo: (name: string) => `发送给 ${name} · 私密对话`,
    composerPlaceholder: "未接通发送通道。暂无法回复。",
    send: "发送",
    sendUnavailable: "暂时无法发送",
    composerReason: "此界面没有发送通道，无法从这里发送任何内容。",
    openRequest: (name: string) => `打开来自 ${name} 的请求`,
  },
};

function kindLabel(
  kind: InboxRequestKind,
  t: typeof STRINGS.en,
): string {
  if (kind === "question") return t.kindQuestion;
  if (kind === "result_review") return t.kindResultReview;
  return t.kindActionNeeded;
}

/** Age computed from the request's own `waitingSince` (ISO) — never a sample
 *  value. An unparseable timestamp renders as honestly unknown. */
function ageLabel(since: string, t: typeof STRINGS.en, now: number): string {
  const at = Date.parse(since);
  if (Number.isNaN(at)) return t.ageUnknown;
  const minutes = Math.max(0, Math.floor((now - at) / 60000));
  if (minutes < 1) return t.ageNow;
  if (minutes < 60) return t.ageMinutes(minutes);
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return t.ageHours(hours);
  return t.ageDays(Math.floor(hours / 24));
}

/** Clock time as written in the ISO timestamp itself (stable across host
 *  timezones); a non-ISO value renders verbatim, never reformatted. */
function clockLabel(at: string): string {
  const match = /^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2})/.exec(at);
  return match ? match[2] : at;
}

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).slice(0, 2);
  return (
    parts
      .map((part) => [...part][0] ?? "")
      .join("")
      .toUpperCase() || "·"
  );
}

/** Roster identity stays honest: an unresolvable key renders as its own key
 *  with an unverified note — a name is never guessed. */
function resolveTeammate(
  roster: TeamRosterRead,
  teammateId: string,
): TeamBot | null {
  return roster.kind === "AVAILABLE"
    ? (roster.roster.bots.find((bot) => bot.id === teammateId) ?? null)
    : null;
}

function RequestExcerpt({
  excerpt,
  t,
}: {
  excerpt: InboxExcerptMessage[] | null;
  t: typeof STRINGS.en;
}) {
  if (excerpt === null) {
    return <p className="muted mm-cv-none-note">{t.excerptNone}</p>;
  }
  if (excerpt.length === 0) {
    return <p className="muted mm-cv-none-note">{t.excerptNone}</p>;
  }
  return (
    <ol className="mm-cv-messages" aria-label={t.excerptHeading}>
      {excerpt.map((message, index) => (
        <li key={index} className="mm-cv-message">
          <p className="mm-cv-message-meta">
            <span className="mm-cv-message-author">{message.author}</span>
            <time className="mm-cv-message-time" title={message.at}>
              {clockLabel(message.at)}
            </time>
          </p>
          <p className="mm-cv-message-text">{message.text}</p>
        </li>
      ))}
    </ol>
  );
}

export function InboxNeedsYouPanel({
  locale = "en",
  roster,
  requests,
  selectedId = null,
  onSelectRequest,
  onOpenConversation,
  onOpenDetails,
  onAnswer,
  pinned,
  archived,
}: {
  locale?: "en" | "zh-CN";
  roster: TeamRosterRead;
  requests: InboxRequest[] | null;
  selectedId?: string | null;
  onSelectRequest?: (id: string) => void;
  onOpenConversation?: () => void;
  onOpenDetails?: () => void;
  /** Answering an exact-request option. Absent = option buttons stay disabled with a reason. */
  onAnswer?: (option: string) => void;
  pinned?: InboxSideRow[];
  archived?: InboxSideRow[];
}) {
  const t = STRINGS[locale];
  const uid = useId();
  const [query, setQuery] = useState("");
  const [localSelected, setLocalSelected] = useState<string | null>(null);
  const cardRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const now = Date.now();

  const selected = selectedId ?? localSelected;
  const selectedRequest =
    requests !== null
      ? (requests.find((request) => request.id === selected) ?? null)
      : null;

  const visible = useMemo(() => {
    if (requests === null) return [];
    const needle = query.trim().toLowerCase();
    if (needle === "") return requests;
    return requests.filter((request) => {
      const teammate = resolveTeammate(roster, request.teammateId);
      const haystack = [
        request.summary,
        kindLabel(request.kind, t),
        teammate ? teammate.displayName : request.teammateId,
      ]
        .join(" ")
        .toLowerCase();
      return haystack.includes(needle);
    });
  }, [requests, query, roster, t]);

  const focusCard = (index: number) => {
    const target = cardRefs.current[index];
    if (target) target.focus();
  };
  const onCardKeyDown = (
    event: React.KeyboardEvent,
    index: number,
  ) => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      focusCard(Math.min(index + 1, visible.length - 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      focusCard(Math.max(index - 1, 0));
    } else if (event.key === "Home") {
      event.preventDefault();
      focusCard(0);
    } else if (event.key === "End") {
      event.preventDefault();
      focusCard(visible.length - 1);
    }
  };

  if (requests === null) {
    return (
      <section className="mm-cv mm-cv-inbox" aria-labelledby={uid}>
        <h2 id={uid} className="mm-cv-heading">
          {t.heading}
        </h2>
        <div className="card mm-cv-unavailable">
          <p className="mm-eyebrow">{t.unavailableChip}</p>
          <h3>{t.unavailableTitle}</h3>
          <p>{t.unavailableBody}</p>
          <p className="muted">{t.unavailableNote}</p>
        </div>
      </section>
    );
  }

  const actionReasonId = `${uid}-action-reason`;
  const answerReasonId = `${uid}-answer-reason`;
  const composerReasonId = `${uid}-composer-reason`;
  const detailTeammate = selectedRequest
    ? resolveTeammate(roster, selectedRequest.teammateId)
    : null;
  const detailName = detailTeammate
    ? detailTeammate.displayName
    : selectedRequest
      ? `#${selectedRequest.teammateId}`
      : null;

  const select = (id: string) => {
    setLocalSelected(id);
    onSelectRequest?.(id);
  };

  return (
    <section className="mm-cv mm-cv-inbox" aria-labelledby={`${uid}-heading`}>
      <h2 id={`${uid}-heading`} className="mm-cv-heading">
        {t.heading}
      </h2>
      <div className="mm-cv-inbox-grid">
        {/* ── Rail 304: search + waiting requests + pinned/archived ── */}
        <div className="mm-cv-inbox-rail">
          <input
            type="search"
            className="mm-cv-search"
            aria-label={t.searchLabel}
            placeholder={t.searchLabel}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
          <section
            className="mm-cv-rail-section"
            aria-label={t.waitingSection}
          >
            <h3 className="mm-cv-section-label">{t.waitingSection}</h3>
            {visible.length === 0 ? (
              <p className="muted mm-cv-none-note">
                {query.trim() !== ""
                  ? t.noMatches(query.trim())
                  : t.emptyInbox}
              </p>
            ) : (
              <ul className="mm-cv-request-list">
                {visible.map((request, index) => {
                  const teammate = resolveTeammate(
                    roster,
                    request.teammateId,
                  );
                  const name = teammate
                    ? teammate.displayName
                    : `#${request.teammateId}`;
                  return (
                    <li key={request.id}>
                      <button
                        type="button"
                        className="mm-cv-request-card"
                        aria-current={request.id === selected ? true : undefined}
                        aria-label={t.openRequest(name)}
                        ref={(node) => {
                          cardRefs.current[index] = node;
                        }}
                        onKeyDown={(event) => onCardKeyDown(event, index)}
                        onClick={() => select(request.id)}
                      >
                        <span className="mm-avatar" aria-hidden="true">
                          {initials(name)}
                        </span>
                        <span className="mm-cv-request-body">
                          <span className="mm-cv-request-name">{name}</span>
                          <span className="mm-cv-request-summary">
                            {request.summary}
                          </span>
                        </span>
                        <span className="mm-chip mm-cv-kind-chip" data-kind={request.kind}>
                          {kindLabel(request.kind, t)} ·{" "}
                          {ageLabel(request.waitingSince, t, now)}
                        </span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
            <p className="muted mm-cv-rail-note">{t.readingKeepsOpen}</p>
          </section>
          {pinned && pinned.length > 0 ? (
            <section className="mm-cv-rail-section" aria-label={t.pinnedSection}>
              <h3 className="mm-cv-section-label">
                {t.pinnedSection} · {pinned.length}
              </h3>
              <ul className="mm-cv-side-rows">
                {pinned.map((row) => (
                  <li key={row.id}>{row.label}</li>
                ))}
              </ul>
            </section>
          ) : null}
          {archived && archived.length > 0 ? (
            <section className="mm-cv-rail-section" aria-label={t.archivedSection}>
              <h3 className="mm-cv-section-label">{t.archivedSection}</h3>
              <ul className="mm-cv-side-rows">
                {archived.map((row) => (
                  <li key={row.id}>
                    {row.label} <span aria-hidden="true">{t.archivedView}</span>
                  </li>
                ))}
              </ul>
            </section>
          ) : null}
        </div>

        {/* ── Detail 1064: the exact request ── */}
        <div className="mm-cv-inbox-detail">
          {selectedRequest === null ? (
            selected === null ? (
              <div className="card mm-cv-detail-empty">
                <h3>{t.heading}</h3>
                <p className="muted">{t.selectPrompt}</p>
              </div>
            ) : (
              <div className="card mm-cv-detail-empty">
                <h3>{t.heading}</h3>
                <p className="muted">{t.missingSelection}</p>
              </div>
            )
          ) : (
            <article className="mm-cv-detail-card">
              <header className="mm-cv-detail-head">
                <span className="mm-avatar mm-cv-detail-avatar" aria-hidden="true">
                  {initials(detailName ?? "")}
                </span>
                <div className="mm-cv-detail-id">
                  <h3>{detailName}</h3>
                  {detailTeammate && detailTeammate.role.length > 0 ? (
                    <p className="muted">{detailTeammate.role}</p>
                  ) : null}
                  {detailTeammate === null ? (
                    <p className="muted">{t.identityUnverified}</p>
                  ) : null}
                </div>
                <span className="mm-chip mm-cv-waiting-chip">
                  {t.waitingForAnswer}
                </span>
                <div className="mm-cv-detail-actions">
                  {onOpenConversation ? (
                    <button type="button" onClick={onOpenConversation}>
                      {t.openBeside}
                    </button>
                  ) : (
                    <button
                      type="button"
                      disabled
                      aria-describedby={actionReasonId}
                    >
                      {t.openBeside}
                    </button>
                  )}
                  {onOpenDetails ? (
                    <button type="button" onClick={onOpenDetails}>
                      {t.details}
                    </button>
                  ) : (
                    <button
                      type="button"
                      disabled
                      aria-describedby={actionReasonId}
                    >
                      {t.details}
                    </button>
                  )}
                </div>
              </header>
              {(onOpenConversation === undefined ||
                onOpenDetails === undefined) && (
                <p
                  className="muted mm-cv-action-reason"
                  id={actionReasonId}
                >
                  {t.actionUnavailableReason}
                </p>
              )}
              <section className="mm-cv-detail-section">
                <h4>{t.excerptHeading}</h4>
                <RequestExcerpt
                  excerpt={selectedRequest.conversationExcerpt}
                  t={t}
                />
              </section>
              <section className="mm-cv-exact" aria-label={t.exactRequestLabel}>
                <p className="mm-eyebrow">{t.exactRequestLabel}</p>
                <h4 className="mm-cv-exact-title">{selectedRequest.summary}</h4>
                {selectedRequest.options &&
                selectedRequest.options.length > 0 ? (
                  <div className="mm-cv-options">
                    {selectedRequest.options.map((option) =>
                      onAnswer ? (
                        <button
                          key={option}
                          type="button"
                          className="mm-cv-option"
                          onClick={() => onAnswer(option)}
                        >
                          {option}
                        </button>
                      ) : (
                        <button
                          key={option}
                          type="button"
                          className="mm-cv-option"
                          disabled
                          aria-describedby={answerReasonId}
                        >
                          {option}
                        </button>
                      ),
                    )}
                  </div>
                ) : (
                  <p className="muted mm-cv-none-note">{t.noOptions}</p>
                )}
                {onAnswer === undefined &&
                selectedRequest.options &&
                selectedRequest.options.length > 0 ? (
                  <p className="muted mm-cv-action-reason" id={answerReasonId}>
                    {t.answerUnavailableReason}
                  </p>
                ) : null}
              </section>
              <footer className="mm-cv-composer" data-connected="false">
                <label className="mm-cv-composer-to" htmlFor={`${uid}-composer`}>
                  {t.composerTo(detailName ?? "")}
                </label>
                <textarea
                  id={`${uid}-composer`}
                  disabled
                  placeholder={t.composerPlaceholder}
                  aria-describedby={composerReasonId}
                />
                <button type="button" disabled title={t.sendUnavailable}>
                  {t.send}
                </button>
                <p className="muted mm-cv-composer-reason" id={composerReasonId}>
                  {t.composerReason}
                </p>
              </footer>
            </article>
          )}
        </div>
      </div>
    </section>
  );
}
