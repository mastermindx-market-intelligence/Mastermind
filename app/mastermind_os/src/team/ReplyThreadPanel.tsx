import { useId, useState } from "react";
import "./conversation-surfaces.css";

/** Thread-reply panel (HC12): the origin message, its projected replies, an
 *  optional attachment and a reply composer. `replies === null` renders the
 *  honest not-projected state; with no `onReply` the composer is disabled with
 *  its reason — no send path is invented on this surface. */

export interface ThreadOrigin {
  author: string;
  text: string;
  at: string;
  onViewOriginal?: () => void;
}

export interface ThreadReply {
  id: string;
  author: string;
  text: string;
  at: string;
  taskLink?: { label: string; onOpen: () => void };
}

export interface ThreadAttachment {
  name: string;
  kind: string;
  onOpenPreview?: () => void;
}

const STRINGS = {
  en: {
    heading: "Thread",
    close: "Close thread",
    originHeading: "Original message",
    viewOriginal: "View original message →",
    viewOriginalUnavailable:
      "The original message view is not wired to this surface.",
    repliesHeading: (count: number) =>
      `${count} ${count === 1 ? "reply" : "replies"}`,
    repliesNotProjected: "Replies are not projected for this message.",
    noReplies: "No replies yet.",
    attachmentHeading: "Attachment",
    openPreview: "Open preview",
    previewUnavailable: "Preview is not wired for this attachment.",
    replyPlaceholder: "Reply to this thread…",
    replyAction: "Reply",
    replyUnavailableReason:
      "No send path is wired to this surface. Replies cannot be sent from here.",
    mention: "＋ @ Mention",
    mentionUnavailable: "Mention needs a wired people picker.",
    note: "Replies stay with this message. Mention a teammate to bring them in.",
  },
  "zh-CN": {
    heading: "回复串",
    close: "关闭回复串",
    originHeading: "原始消息",
    viewOriginal: "查看原始消息 →",
    viewOriginalUnavailable: "此界面尚未接通原始消息视图。",
    repliesHeading: (count: number) => `${count} 条回复`,
    repliesNotProjected: "此消息未投影回复。",
    noReplies: "暂无回复。",
    attachmentHeading: "附件",
    openPreview: "打开预览",
    previewUnavailable: "该附件尚未接通预览。",
    replyPlaceholder: "回复此串…",
    replyAction: "回复",
    replyUnavailableReason:
      "此界面未接通发送通道，无法从这里发送回复。",
    mention: "＋ @ 提及",
    mentionUnavailable: "提及需要已接通的人员选择器。",
    note: "回复保留在这条消息上。提及成员可将其带入。",
  },
};

/** Clock time as written in the ISO timestamp itself (stable across host
 *  timezones); a non-ISO value renders verbatim, never reformatted. */
function clockLabel(at: string): string {
  const match = /^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2})/.exec(at);
  return match ? match[2] : at;
}

export function ReplyThreadPanel({
  locale = "en",
  origin,
  replies,
  attachment,
  onReply,
  onMention,
  onClose,
}: {
  locale?: "en" | "zh-CN";
  origin: ThreadOrigin;
  replies: ThreadReply[] | null;
  attachment?: ThreadAttachment;
  /** Absent = composer disabled with its honest reason (no send path). */
  onReply?: (text: string) => void;
  onMention?: () => void;
  /** Escape (or the close button) closes this popover. */
  onClose?: () => void;
}) {
  const t = STRINGS[locale];
  const uid = useId();
  const [draft, setDraft] = useState("");
  const reasonBase = `${uid}-reason`;
  const composerReasonId = `${reasonBase}-composer`;
  const mentionReasonId = `${reasonBase}-mention`;
  const viewOriginalReasonId = `${reasonBase}-origin`;
  const previewReasonId = `${reasonBase}-preview`;

  const sendReply = () => {
    const text = draft.trim();
    if (text.length === 0 || onReply === undefined) return;
    onReply(text);
    setDraft("");
  };

  return (
    <aside
      className="mm-cv mm-cv-thread"
      aria-labelledby={`${uid}-heading`}
      onKeyDown={(event) => {
        // Escape closes the thread panel and stops here: the mounting owner
        // restores focus to its trigger in onClose (adversarial note).
        if (event.key === "Escape" && onClose) {
          event.stopPropagation();
          onClose();
        }
      }}
    >
      <header className="mm-cv-thread-head">
        <div className="mm-cv-thread-title">
          <h3 id={`${uid}-heading`}>{t.heading}</h3>
          {replies !== null ? (
            <span className="mm-cv-thread-count">
              {t.repliesHeading(replies.length)}
            </span>
          ) : null}
        </div>
        {onClose ? (
          <button
            type="button"
            className="mm-cv-thread-close"
            aria-label={t.close}
            onClick={onClose}
          >
            ×
          </button>
        ) : null}
      </header>

      <article className="mm-cv-origin" aria-label={t.originHeading}>
        <p className="mm-cv-message-meta">
          <span className="mm-cv-message-author">{origin.author}</span>
          <time className="mm-cv-message-time" title={origin.at}>
            {clockLabel(origin.at)}
          </time>
        </p>
        <p className="mm-cv-message-text">{origin.text}</p>
        {origin.onViewOriginal ? (
          <button
            type="button"
            className="mm-cv-link-action"
            onClick={origin.onViewOriginal}
          >
            {t.viewOriginal}
          </button>
        ) : (
          <button
            type="button"
            className="mm-cv-link-action"
            disabled
            aria-describedby={viewOriginalReasonId}
          >
            {t.viewOriginal}
          </button>
        )}
        {origin.onViewOriginal === undefined ? (
          <p className="muted mm-cv-action-reason" id={viewOriginalReasonId}>
            {t.viewOriginalUnavailable}
          </p>
        ) : null}
      </article>

      <section className="mm-cv-replies">
        {replies === null ? (
          <p className="muted mm-cv-none-note">{t.repliesNotProjected}</p>
        ) : replies.length === 0 ? (
          <p className="muted mm-cv-none-note">{t.noReplies}</p>
        ) : (
          <ul className="mm-cv-messages">
            {replies.map((reply) => (
              <li key={reply.id} className="mm-cv-message">
                <p className="mm-cv-message-meta">
                  <span className="mm-cv-message-author">{reply.author}</span>
                  <time className="mm-cv-message-time" title={reply.at}>
                    {clockLabel(reply.at)}
                  </time>
                </p>
                <p className="mm-cv-message-text">{reply.text}</p>
                {reply.taskLink ? (
                  <button
                    type="button"
                    className="mm-cv-link-action"
                    onClick={reply.taskLink.onOpen}
                  >
                    {reply.taskLink.label} →
                  </button>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </section>

      {attachment ? (
        <section className="mm-cv-attachment" aria-label={t.attachmentHeading}>
          <p className="mm-cv-section-label">{t.attachmentHeading}</p>
          <p className="mm-cv-attachment-row">
            <span className="mm-cv-attachment-name">{attachment.name}</span>
            <span className="mm-cv-attachment-kind">{attachment.kind}</span>
            {attachment.onOpenPreview ? (
              <button
                type="button"
                className="mm-cv-link-action"
                onClick={attachment.onOpenPreview}
              >
                {t.openPreview}
              </button>
            ) : (
              <button
                type="button"
                className="mm-cv-link-action"
                disabled
                aria-describedby={previewReasonId}
              >
                {t.openPreview}
              </button>
            )}
          </p>
          {attachment.onOpenPreview === undefined ? (
            <p className="muted mm-cv-action-reason" id={previewReasonId}>
              {t.previewUnavailable}
            </p>
          ) : null}
        </section>
      ) : null}

      <footer className="mm-cv-composer" data-connected={onReply ? "true" : "false"}>
        {onReply ? (
          <>
            <label htmlFor={`${uid}-reply`} className="mm-screenreader-only">
              {t.replyPlaceholder}
            </label>
            <textarea
              id={`${uid}-reply`}
              placeholder={t.replyPlaceholder}
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
            />
            <div className="mm-cv-composer-row">
              <button
                type="button"
                className="mm-cv-send"
                onClick={sendReply}
                disabled={draft.trim().length === 0}
              >
                {t.replyAction}
              </button>
              {onMention ? (
                <button type="button" className="mm-cv-mention" onClick={onMention}>
                  {t.mention}
                </button>
              ) : (
                <button
                  type="button"
                  className="mm-cv-mention"
                  disabled
                  aria-describedby={mentionReasonId}
                >
                  {t.mention}
                </button>
              )}
            </div>
            {onMention === undefined ? (
              <p className="muted mm-cv-composer-reason" id={mentionReasonId}>
                {t.mentionUnavailable}
              </p>
            ) : null}
          </>
        ) : (
          <>
            <label htmlFor={`${uid}-reply`} className="mm-screenreader-only">
              {t.replyPlaceholder}
            </label>
            <textarea
              id={`${uid}-reply`}
              disabled
              placeholder={t.replyPlaceholder}
              aria-describedby={composerReasonId}
            />
            <div className="mm-cv-composer-row">
              <button type="button" className="mm-cv-send" disabled>
                {t.replyAction}
              </button>
              <button
                type="button"
                className="mm-cv-mention"
                disabled
                aria-describedby={mentionReasonId}
              >
                {t.mention}
              </button>
            </div>
            <p className="muted mm-cv-composer-reason" id={composerReasonId}>
              {t.replyUnavailableReason}
            </p>
            <p className="muted mm-cv-composer-reason" id={mentionReasonId}>
              {t.mentionUnavailable}
            </p>
          </>
        )}
      </footer>
      <p className="muted mm-cv-thread-note">{t.note}</p>
    </aside>
  );
}
