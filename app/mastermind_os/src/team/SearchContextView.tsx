/** HC20 — "Team · Search with exact-message context" (board 1OVH-0).
 *
 * Left results list (448): query row, result rows grouped by conversation,
 * footer count. Right context pane (920): conversation header, the
 * SURROUNDING MESSAGES window around the exact match, footer actions.
 *
 * Honesty law for this surface: `results: null` means NO conversation-search
 * read exists in this build — the view says so and renders no rows and no
 * count. An empty array is a real read with zero matches. Counts come only
 * from the real array; the Paper sample copy ("3 results in available
 * history") is never hardcoded anywhere in this file. No author, title or
 * conversation name is ever rendered except from the provided array. */
import { useId, useMemo, useRef } from "react";
import "./team.css";
import "./work-search.css";

/** One adjacent message in the surrounding window. */
export interface SearchMessageContextItem {
  author: string;
  text: string;
  /** ISO timestamp. */
  at: string;
}

/** One exact-message search hit, with its optional surrounding window. */
export interface SearchMessageResult {
  id: string;
  conversationId: string;
  conversationTitle: string;
  author: string;
  text: string;
  /** ISO timestamp. */
  at: string;
  /** null = the surrounding window is not projected for this result; the
   *  view shows only the exact match and says so. */
  surrounding: {
    before: SearchMessageContextItem[];
    after: SearchMessageContextItem[];
  } | null;
}

interface Strings {
  heading: string;
  summary: string;
  resultsLabel: string;
  queryLabel: string;
  queryEmpty: string;
  notProjectedTitle: string;
  notProjectedBody: string;
  zeroTitle: string;
  zeroBody: string;
  count: (n: number) => string;
  contextHeading: string;
  contextNone: string;
  contextMissing: string;
  surroundingHeading: string;
  exactMatchChip: string;
  surroundingNotProjected: string;
  surroundingEmpty: string;
  openConversation: string;
  openConversationReason: string;
  selectResult: (author: string) => string;
}

const STRINGS: Record<"en" | "zh-CN", Strings> = {
  en: {
    heading: "Search",
    summary:
      "Search messages across conversations and open the exact match in its context.",
    resultsLabel: "Search results",
    queryLabel: "Query",
    queryEmpty: "No search text",
    notProjectedTitle: "Search source not projected in this build",
    notProjectedBody:
      "No conversation-search read exists in this build. Nothing is searched or shown here.",
    zeroTitle: "No results",
    zeroBody: "Nothing in the available history matches this search.",
    count: (n) => `${n} result${n === 1 ? "" : "s"} in available history`,
    contextHeading: "Message context",
    contextNone: "Select a result to see the exact message in its surrounding window.",
    contextMissing: "The selected message is not in the projected results.",
    surroundingHeading: "Surrounding messages",
    exactMatchChip: "Exact match",
    surroundingNotProjected:
      "Surrounding messages are not projected for this result; only the exact match is shown.",
    surroundingEmpty: "No adjacent messages are in the projected window.",
    openConversation: "Open conversation →",
    openConversationReason:
      "Opening a conversation is not wired in this build; no open path exists.",
    selectResult: (author) => `Show message context — ${author}`,
  },
  "zh-CN": {
    heading: "搜索",
    summary: "跨对话搜索消息，并在其上下文中打开确切匹配。",
    resultsLabel: "搜索结果",
    queryLabel: "搜索词",
    queryEmpty: "无搜索词",
    notProjectedTitle: "此构建未投影搜索来源",
    notProjectedBody:
      "此构建中不存在对话搜索读取。这里不搜索、也不显示任何内容。",
    zeroTitle: "无结果",
    zeroBody: "可用历史中没有与该搜索匹配的内容。",
    count: (n) => `可用历史中 ${n} 条结果`,
    contextHeading: "消息上下文",
    contextNone: "选择一条结果，在其周边窗口中查看确切消息。",
    contextMissing: "所选消息不在已投影的结果中。",
    surroundingHeading: "周边消息",
    exactMatchChip: "确切匹配",
    surroundingNotProjected: "该结果未投影周边消息；仅显示确切匹配。",
    surroundingEmpty: "投影窗口中没有相邻消息。",
    openConversation: "打开对话 →",
    openConversationReason: "此构建未接通打开对话的路径；不存在打开通道。",
    selectResult: (author) => `查看消息上下文 — ${author}`,
  },
};

export function SearchContextView({
  locale = "en",
  query,
  results,
  selectedId,
  onSelectResult,
  onOpenConversation,
  onCloseSelection,
}: {
  locale?: "en" | "zh-CN";
  query: string;
  results: SearchMessageResult[] | null;
  selectedId: string | null;
  onSelectResult: (id: string) => void;
  onOpenConversation?: (conversationId: string) => void;
  /** Escape clears the selection through this callback; absent = a no-op,
   *  never a focus trap. */
  onCloseSelection?: () => void;
}) {
  const t = STRINGS[locale];
  const uid = useId().replace(/[^a-zA-Z0-9-]/g, "");
  const rowRefs = useRef<(HTMLButtonElement | null)[]>([]);

  const when = useMemo(() => {
    const format = new Intl.DateTimeFormat(locale, {
      dateStyle: "short",
      timeStyle: "short",
    });
    return (value: string) => {
      const date = new Date(value);
      return Number.isNaN(date.getTime()) ? value : format.format(date);
    };
  }, [locale]);

  const rows = results ?? [];
  const selected = rows.find((row) => row.id === selectedId) ?? null;
  const focusIndex = selected ? rows.indexOf(selected) : 0;

  /** Group by conversation identity (first-appearance order), so a
   *  conversation split across the array still renders as one group. */
  const groups = useMemo(() => {
    const map = new Map<
      string,
      {
        conversationId: string;
        title: string;
        items: { row: SearchMessageResult; index: number }[];
      }
    >();
    rows.forEach((row, index) => {
      const group = map.get(row.conversationId);
      if (group) group.items.push({ row, index });
      else
        map.set(row.conversationId, {
          conversationId: row.conversationId,
          title: row.conversationTitle,
          items: [{ row, index }],
        });
    });
    return [...map.values()];
    // rows is results ?? [] — recomputed when the results identity changes.
  }, [results]);

  const focusRow = (index: number) => {
    rowRefs.current[index]?.focus();
  };
  const onRowKeyDown = (
    event: React.KeyboardEvent,
    index: number,
  ) => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      focusRow(Math.min(index + 1, rows.length - 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      focusRow(Math.max(index - 1, 0));
    } else if (event.key === "Home") {
      event.preventDefault();
      focusRow(0);
    } else if (event.key === "End") {
      event.preventDefault();
      focusRow(rows.length - 1);
    }
  };
  const onSurfaceKeyDown = (event: React.KeyboardEvent) => {
    // Escape clears the selection only when a handler exists; without one it
    // stays a no-op (default browser behavior) — never a trap.
    if (event.key === "Escape" && onCloseSelection) {
      event.preventDefault();
      onCloseSelection();
    }
  };

  return (
    <section
      className="mm-search-surface"
      aria-labelledby={`${uid}-heading`}
      onKeyDown={onSurfaceKeyDown}
    >
      <h2 id={`${uid}-heading`} tabIndex={-1}>
        {t.heading}
      </h2>
      <p className="muted">{t.summary}</p>
      <div className="mm-search-view">
        {/* ── Left · results list (448) ───────────────────────────────── */}
        <aside className="mm-search-results" aria-label={t.resultsLabel}>
          <div className="mm-search-query-row">
            <span className="mm-search-query-label">{t.queryLabel}</span>
            <span className="mm-search-query-text">
              {query ? `“${query}”` : t.queryEmpty}
            </span>
          </div>
          {results === null ? (
            <div className="mm-search-honest" role="status">
              <p className="mm-eyebrow">{t.notProjectedTitle}</p>
              <p>{t.notProjectedBody}</p>
            </div>
          ) : rows.length === 0 ? (
            <div className="mm-search-honest" role="status">
              <p className="mm-eyebrow">{t.zeroTitle}</p>
              <p>{t.zeroBody}</p>
            </div>
          ) : (
            <div className="mm-search-groups">
              {groups.map((group) => (
                <div key={group.conversationId}>
                  <p className="mm-search-conversation">{group.title}</p>
                  {group.items.map(({ row, index }) => (
                    <button
                      key={row.id}
                      type="button"
                      className="mm-search-row"
                      ref={(node) => {
                        rowRefs.current[index] = node;
                      }}
                      data-selected={row.id === selectedId}
                      aria-current={row.id === selectedId ? "true" : undefined}
                      aria-label={t.selectResult(row.author)}
                      tabIndex={index === focusIndex ? 0 : -1}
                      onClick={() => onSelectResult(row.id)}
                      onKeyDown={(event) => onRowKeyDown(event, index)}
                    >
                      <span className="mm-search-row-author">{row.author}</span>
                      <span className="mm-search-row-text">{row.text}</span>
                      <small className="mm-search-row-time">
                        {when(row.at)}
                      </small>
                    </button>
                  ))}
                </div>
              ))}
            </div>
          )}
          {/* Count only ever from the real array — never when null. */}
          {results !== null ? (
            <p className="mm-search-count" data-testid="mm-search-count">
              {t.count(results.length)}
            </p>
          ) : null}
        </aside>

        {/* ── Right · message context pane (920) ──────────────────────── */}
        <div className="mm-search-context" aria-label={t.contextHeading}>
          {selected === null ? (
            <div className="mm-search-honest" role="status">
              <p className="mm-eyebrow">{t.contextHeading}</p>
              <p>{selectedId ? t.contextMissing : t.contextNone}</p>
            </div>
          ) : (
            <>
              <header className="mm-search-context-head">
                <h3>{selected.conversationTitle}</h3>
                <p className="mm-context-sub">
                  <code>{selected.conversationId}</code>
                </p>
              </header>
              <section aria-label={t.surroundingHeading}>
                <h4 className="mm-window-heading">
                  {t.surroundingHeading}
                </h4>
                {selected.surrounding === null ? (
                  <>
                    <p className="mm-honest-line">
                      {t.surroundingNotProjected}
                    </p>
                    <ol className="mm-search-window">
                      <li className="mm-search-msg" data-match="true">
                        <span className="mm-search-msg-author">
                          {selected.author} · {when(selected.at)}
                        </span>
                        <p className="mm-search-msg-text">{selected.text}</p>
                        <span className="mm-chip mm-chip-match">
                          {t.exactMatchChip}
                        </span>
                      </li>
                    </ol>
                  </>
                ) : (
                  <>
                    {selected.surrounding.before.length === 0 &&
                    selected.surrounding.after.length === 0 ? (
                      <p className="mm-honest-line">{t.surroundingEmpty}</p>
                    ) : null}
                    <ol className="mm-search-window">
                      {selected.surrounding.before.map((message, index) => (
                        <li
                          key={`before-${index}`}
                          className="mm-search-msg"
                        >
                          <span className="mm-search-msg-author">
                            {message.author} · {when(message.at)}
                          </span>
                          <p className="mm-search-msg-text">{message.text}</p>
                        </li>
                      ))}
                      <li className="mm-search-msg" data-match="true">
                        <span className="mm-search-msg-author">
                          {selected.author} · {when(selected.at)}
                        </span>
                        <p className="mm-search-msg-text">{selected.text}</p>
                        <span className="mm-chip mm-chip-match">
                          {t.exactMatchChip}
                        </span>
                      </li>
                      {selected.surrounding.after.map((message, index) => (
                        <li
                          key={`after-${index}`}
                          className="mm-search-msg"
                        >
                          <span className="mm-search-msg-author">
                            {message.author} · {when(message.at)}
                          </span>
                          <p className="mm-search-msg-text">{message.text}</p>
                        </li>
                      ))}
                    </ol>
                  </>
                )}
              </section>
              <footer className="mm-pane-footer">
                {onOpenConversation ? (
                  <button
                    type="button"
                    className="mm-pane-action"
                    onClick={() =>
                      onOpenConversation(selected.conversationId)
                    }
                  >
                    {t.openConversation}
                  </button>
                ) : (
                  <>
                    <button
                      type="button"
                      className="mm-pane-action"
                      disabled
                      aria-describedby={`${uid}-open-reason`}
                    >
                      {t.openConversation}
                    </button>
                    <p
                      className="mm-pane-reason"
                      id={`${uid}-open-reason`}
                    >
                      {t.openConversationReason}
                    </p>
                  </>
                )}
              </footer>
            </>
          )}
        </div>
      </div>
    </section>
  );
}
