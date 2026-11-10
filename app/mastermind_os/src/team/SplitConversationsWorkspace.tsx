import { useId, useState } from "react";
import "./conversation-surfaces.css";

/** Split workspace (HC19): exactly two conversation panes side by side, each
 *  with its own header, timeline, composer and footer. Each pane's draft is
 *  its own React state — typing in one pane never touches the other. With no
 *  `onCompose` the composers stay disabled with their honest reason: no send
 *  path is wired, and nothing on this surface claims local persistence. */

export interface SplitExcerptMessage {
  author: string;
  text: string;
  at: string;
}

export interface SplitConversationPane {
  id: string;
  header: { title: string; subtitle: string };
  excerpt: SplitExcerptMessage[] | null;
}

const STRINGS = {
  en: {
    heading: "Two conversations",
    /* Board copy reads "Workspace saved on this device"; no persistence is
       wired to this surface, so the strip states what is actually true. */
    strip: "Split view · drafts stay independent per conversation",
    notProjected: "This conversation is not projected yet.",
    noMessages: "No messages yet.",
    timelineLabel: "Conversation timeline",
    composerPlaceholder: "No send path is wired. Composing is unavailable.",
    composerLivePlaceholder: "Write to this conversation…",
    composerLabel: "Message",
    send: "Send",
    sendUnavailable: "Send is unavailable",
    composerReason:
      "No send path is wired to this workspace. Drafts cannot be sent from here.",
    footerNote: "Draft stays with this conversation.",
    needsTwo: "This workspace needs two conversations.",
  },
  "zh-CN": {
    heading: "两个对话",
    strip: "分屏视图 · 各对话草稿相互独立",
    notProjected: "此对话尚未投影。",
    noMessages: "暂无消息。",
    timelineLabel: "对话时间线",
    composerPlaceholder: "未接通发送通道。暂无法撰写。",
    composerLivePlaceholder: "写入此对话…",
    composerLabel: "消息",
    send: "发送",
    sendUnavailable: "暂时无法发送",
    composerReason: "此工作区未接通发送通道，无法从这里发送草稿。",
    footerNote: "草稿保留在此对话中。",
    needsTwo: "此工作区需要两个对话。",
  },
};

/** Clock time as written in the ISO timestamp itself (stable across host
 *  timezones); a non-ISO value renders verbatim, never reformatted. */
function clockLabel(at: string): string {
  const match = /^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2})/.exec(at);
  return match ? match[2] : at;
}

/** One pane. The draft lives here as this pane's own React state, so the two
 *  composers can never share or clobber each other's text. */
function SplitPaneView({
  pane,
  t,
  onCompose,
}: {
  pane: SplitConversationPane;
  t: typeof STRINGS.en;
  onCompose?: (paneId: string, text: string) => void;
}) {
  const uid = useId();
  const [draft, setDraft] = useState("");
  const composerReasonId = `${uid}-composer-reason`;

  const send = () => {
    const text = draft.trim();
    if (text.length === 0 || onCompose === undefined) return;
    onCompose(pane.id, text);
    setDraft("");
  };

  return (
    <article className="mm-cv-pane" aria-labelledby={`${uid}-title`}>
      <header className="mm-cv-pane-head">
        <h3 id={`${uid}-title`}>{pane.header.title}</h3>
        <p className="muted">{pane.header.subtitle}</p>
      </header>
      <section className="mm-cv-pane-timeline" aria-label={t.timelineLabel}>
        {pane.excerpt === null ? (
          <p className="muted mm-cv-none-note">{t.notProjected}</p>
        ) : pane.excerpt.length === 0 ? (
          <p className="muted mm-cv-none-note">{t.noMessages}</p>
        ) : (
          <ol className="mm-cv-messages">
            {pane.excerpt.map((message, index) => (
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
        )}
      </section>
      <footer className="mm-cv-pane-foot">
        <div className="mm-cv-composer" data-connected={onCompose ? "true" : "false"}>
          <label htmlFor={`${uid}-composer`} className="mm-screenreader-only">
            {t.composerLabel}
          </label>
          {onCompose ? (
            <textarea
              id={`${uid}-composer`}
              placeholder={t.composerLivePlaceholder}
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
            />
          ) : (
            <textarea
              id={`${uid}-composer`}
              disabled
              placeholder={t.composerPlaceholder}
              aria-describedby={composerReasonId}
            />
          )}
          <button
            type="button"
            className="mm-cv-send"
            onClick={send}
            disabled={onCompose === undefined || draft.trim().length === 0}
            title={onCompose === undefined ? t.sendUnavailable : undefined}
          >
            {t.send}
          </button>
          {onCompose === undefined ? (
            <p className="muted mm-cv-composer-reason" id={composerReasonId}>
              {t.composerReason}
            </p>
          ) : null}
        </div>
        <p className="muted mm-cv-pane-footer-note">{t.footerNote}</p>
      </footer>
    </article>
  );
}

export function SplitConversationsWorkspace({
  locale = "en",
  panes,
  onCompose,
}: {
  locale?: "en" | "zh-CN";
  panes: SplitConversationPane[];
  /** Absent = both composers disabled with their honest reason (no send path). */
  onCompose?: (paneId: string, text: string) => void;
}) {
  const t = STRINGS[locale];
  const shown = panes.slice(0, 2);
  return (
    <section className="mm-cv mm-cv-split" aria-labelledby="mm-cv-split-heading">
      <header className="mm-cv-split-head">
        <h2 id="mm-cv-split-heading" className="mm-cv-heading">
          {t.heading}
        </h2>
        <p className="mm-cv-strip">{t.strip}</p>
      </header>
      {shown.length === 0 ? (
        <p className="muted mm-cv-none-note">{t.needsTwo}</p>
      ) : (
        <div className="mm-cv-split-grid">
          {shown.map((pane) => (
            <SplitPaneView key={pane.id} pane={pane} t={t} onCompose={onCompose} />
          ))}
        </div>
      )}
    </section>
  );
}
