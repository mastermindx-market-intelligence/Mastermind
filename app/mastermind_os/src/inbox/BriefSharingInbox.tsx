// Original Paper Inbox brief-sharing request review.
// Presentation only: renders exactly the requests the parent supplies, hands
// the selected request back verbatim, and never claims a share outcome.
// Sharing and privacy decisions stay in the original Terminal context.
import { useEffect, useRef, useState, type ReactNode } from "react";
import "./brief-sharing-inbox.css";

export interface BriefSharingRequestView {
  readonly requestRef: string;
  readonly requestRevision: string;
  readonly deliveryId: string;
  readonly contentSha256: string;
  readonly title: string;
  readonly version: string | null;
  readonly audienceName: string;
  readonly audienceMemberCount: number | null;
  readonly access: "VIEW_ONLY";
}

export interface BriefSharingInboxProps {
  locale: "en" | "zh-CN";
  state: "unavailable" | "loading" | "ready";
  requests: readonly BriefSharingRequestView[];
  sourceDetails?: ReactNode;
  /** Exact selected-request handoff; the parent validates it before any effect. */
  onReview?: (request: BriefSharingRequestView) => Promise<void>;
}

interface Copy {
  readonly regionLabel: string;
  readonly more: (count: number) => string;
  readonly eyebrow: string;
  readonly heading: string;
  readonly scope: string;
  readonly terminal: string;
  readonly question: string;
  readonly versionLabel: string;
  readonly viewOnly: string;
  readonly members: (count: number) => string;
  readonly terminalNote: string;
  readonly continueInTerminal: string;
  readonly reviewUnavailable: string;
  readonly pending: string;
  readonly requested: string;
  readonly requestedNote: string;
  readonly outcomeUnavailable: string;
  readonly outcomeNote: string;
  readonly loading: string;
  readonly empty: string;
  readonly emptyNote: string;
  readonly sourceUnavailable: string;
  readonly sourceUnavailableNote: string;
  readonly footerMissing: string;
  readonly footerSources: string;
  readonly footerScope: string;
}

const COPY: Record<BriefSharingInboxProps["locale"], Copy> = {
  en: {
    regionLabel: "Brief sharing requests",
    more: count => `Show ${count} more ${count === 1 ? "request" : "requests"}`,
    eyebrow: "Needs you",
    heading: "Brief sharing requests",
    scope: "Only requests supplied by the owner in the current scope are shown.",
    terminal: "Terminal",
    question: "Share this brief?",
    versionLabel: "Version",
    viewOnly: "View only",
    members: count => `${count} ${count === 1 ? "member" : "members"}`,
    terminalNote: "Review this request and choose whether to share in Terminal.",
    continueInTerminal: "Continue in Terminal",
    reviewUnavailable: "Review in Terminal is unavailable.",
    pending: "Opening Terminal…",
    requested: "Continue in Terminal to review this request.",
    requestedNote: "Sharing has not changed.",
    outcomeUnavailable: "Terminal could not be confirmed open.",
    outcomeNote: "Check the original Terminal page.",
    loading: "Loading brief-sharing requests…",
    empty: "No requests were returned from Terminal.",
    emptyNote: "An empty list is not an all-clear.",
    sourceUnavailable: "Requests are unavailable.",
    sourceUnavailableNote: "An unavailable source is not an empty list.",
    footerMissing: "Some requests may be missing.",
    footerSources: "Sources and access",
    footerScope: "This section shows only the requests supplied in the current scope.",
  },
  "zh-CN": {
    regionLabel: "简报共享请求",
    more: count => `查看其余 ${count} 项请求`,
    eyebrow: "需要你",
    heading: "简报共享请求",
    scope: "仅显示当前范围内由所有者提供的请求。",
    terminal: "Terminal",
    question: "共享这份简报？",
    versionLabel: "版本",
    viewOnly: "仅查看",
    members: count => `${count} 名成员`,
    terminalNote: "请在 Terminal 中审阅此请求，并决定是否分享。",
    continueInTerminal: "在 Terminal 中继续",
    reviewUnavailable: "暂时无法在 Terminal 中审阅。",
    pending: "正在打开 Terminal…",
    requested: "请在 Terminal 中继续审阅此请求。",
    requestedNote: "分享状态尚未改变。",
    outcomeUnavailable: "暂时无法确认 Terminal 是否已打开。",
    outcomeNote: "请查看原来的 Terminal 页面。",
    loading: "正在载入简报共享请求…",
    empty: "Terminal 未返回请求。",
    emptyNote: "列表为空并不表示一切正常。",
    sourceUnavailable: "暂时无法加载请求。",
    sourceUnavailableNote: "来源不可用并非列表为空。",
    footerMissing: "部分请求可能缺失。",
    footerSources: "来源与访问",
    footerScope: "本区域仅显示当前范围内提供的请求。",
  },
};

type AttemptStatus = "pending" | "requested" | "unavailable";

interface AttemptRecord {
  readonly status: AttemptStatus;
  readonly token: number;
}

/** Attempt identity: one attempt per requestRef+revision+delivery+digest while mounted. */
function attemptKey(request: BriefSharingRequestView): string {
  return [request.requestRef, request.requestRevision, request.deliveryId, request.contentSha256].join("\u0000");
}

export function BriefSharingInbox({ locale, state, requests, onReview, sourceDetails }: BriefSharingInboxProps) {
  const copy = COPY[locale];
  const [attempts, setAttempts] = useState<ReadonlyMap<string, AttemptRecord>>(() => new Map());
  const nextToken = useRef(0);
  const attempted = useRef(new Set<string>());
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);

  const settleAttempt = (key: string, token: number, status: "requested" | "unavailable") => {
    if (!mounted.current) return;
    setAttempts(previous => {
      const record = previous.get(key);
      // A late completion never mutates a row whose attempt is no longer current.
      if (!record || record.token !== token) return previous;
      return new Map(previous).set(key, { status, token });
    });
  };

  const review = (request: BriefSharingRequestView) => {
    if (!onReview) return;
    const key = attemptKey(request);
    if (attempted.current.has(key)) return; // Synchronous latch survives batched clicks.
    attempted.current.add(key);
    const token = nextToken.current + 1;
    nextToken.current = token;
    setAttempts(previous => new Map(previous).set(key, { status: "pending", token }));
    try {
      void Promise.resolve(onReview(request)).then(
        () => settleAttempt(key, token, "requested"),
        () => settleAttempt(key, token, "unavailable"));
    } catch {
      settleAttempt(key, token, "unavailable");
    }
  };

  const listed = state === "ready" ? requests : [];

  const renderRequest = (request: BriefSharingRequestView) => {
      const record = attempts.get(attemptKey(request));
      const status = !onReview ? copy.reviewUnavailable
        : record?.status === "pending" ? copy.pending
        : record?.status === "requested" ? copy.requested
        : record?.status === "unavailable" ? copy.outcomeUnavailable
        : null;
      const note = record?.status === "requested" ? copy.requestedNote
        : record?.status === "unavailable" ? copy.outcomeNote
        : null;
      return <article className="brief-sharing-card" key={attemptKey(request)} data-attempt={record?.status}>
        <p className="brief-sharing-context">{copy.terminal}</p>
        <h2>{copy.question}</h2>
        <div className="brief-sharing-brief">
          <p className="brief-sharing-title">{request.title}</p>
          {request.version !== null && <p className="brief-sharing-muted">{copy.versionLabel} {request.version}</p>}
        </div>
        <div className="brief-sharing-audience">
          <p>{request.audienceName}</p>
          {request.audienceMemberCount !== null && <p className="brief-sharing-muted">{copy.members(request.audienceMemberCount)}</p>}
          <span className="brief-sharing-chip">{copy.viewOnly}</span>
        </div>
        <p className="brief-sharing-muted">{copy.terminalNote}</p>
        <div className="brief-sharing-actions">
          <button type="button" onClick={() => review(request)} disabled={!onReview || !!record}>
            {copy.continueInTerminal}
          </button>
          {status !== null && <p className="brief-sharing-status" role="status">{status}</p>}
          {note !== null && <p className="brief-sharing-muted">{note}</p>}
        </div>
      </article>;
  };

  return <section className="brief-sharing-inbox" lang={locale} aria-label={copy.regionLabel}>
    {state === "loading" && <p className="brief-sharing-note" role="status">{copy.loading}</p>}
    {state === "unavailable" && <div className="brief-sharing-note">
      <p>{copy.sourceUnavailable}</p>
    </div>}
    {state === "ready" && requests.length === 0 && <div className="brief-sharing-note">
      <p>{copy.empty}</p>
    </div>}
    {listed.slice(0, 8).map(renderRequest)}
    {listed.length > 8 && <details className="brief-sharing-more">
      <summary>{copy.more(listed.length - 8)}</summary>
      {listed.slice(8).map(renderRequest)}
    </details>}

    <footer className="brief-sharing-footer">
      <p>{copy.footerMissing}</p>
      <details className="brief-sharing-sources">
        <summary>{copy.footerSources}</summary>
        <p className="brief-sharing-muted">{locale === "zh-CN"
          ? "Terminal 为此连接返回的明确共享请求。打开请求不会授予访问权限；Terminal 会再次核实账户和团队。"
          : "Explicit sharing requests returned by Terminal for this connection. Opening a request does not grant access; Terminal checks the account and team again."}</p>
        {sourceDetails}
        {listed.length > 0 && <ul>{listed.map(request => <li key={attemptKey(request)}><dl>
          <dt>{locale === "zh-CN" ? "请求" : "Request"}</dt><dd>{request.requestRef}</dd>
          <dt>{locale === "zh-CN" ? "请求修订" : "Request revision"}</dt><dd>{request.requestRevision}</dd>
          <dt>{locale === "zh-CN" ? "简报交付" : "Brief delivery"}</dt><dd>{request.deliveryId}</dd>
          <dt>{locale === "zh-CN" ? "内容摘要" : "Content digest"}</dt><dd>{request.contentSha256}</dd>
        </dl></li>)}</ul>}
      </details>
    </footer>
  </section>;
}
