import { Component, Suspense, lazy, useEffect, useId, useMemo, useRef, useState, type ReactNode } from "react";
import type { WindowItem } from "../workspace-contract";
import { useObservedTranscriptScroll } from "./useObservedTranscriptScroll";
import "./observed-transcript.css";

const SourceMarkdown = lazy(() => import("./SourceMarkdown").then(module => ({ default: module.SourceMarkdown })));
type Locale = "en" | "zh-CN";
const labels = {
  "Observed responses": "已观察的回复",
  "Search observed responses": "搜索已观察的回复",
  "Search this window only": "仅搜索此窗口",
  "Clear search": "清除搜索",
  "Formatted responses": "格式化回复",
  "Exact source": "原始文本",
  "Only this observed window is searched. Full history is not established.": "仅搜索此观察窗口，尚未确认完整历史记录。",
  "Observed response list": "已观察的回复列表",
  "Owner-visible response": "所有者提供的回复",
  "Content withheld": "内容已隐藏",
  "Content withheld by its owner.": "内容已被所有者隐藏。",
  "No visible response was supplied in this observed window.": "此窗口尚未提供可见回复。",
  "No visible responses match this search.": "没有与搜索匹配的可见回复。",
  "No visible text was supplied.": "尚未提供可见文本。",
  "Withheld content is not searched or copied.": "不会搜索或复制已隐藏的内容。",
  "Jump to latest observed response": "跳到最新观察回复",
  "Following latest observed response": "跟随最新观察回复",
  "Reading earlier responses": "正在阅读较早回复",
  "Loading formatted response…": "正在加载格式化回复…",
  "Formatting unavailable. Exact source follows.": "格式化暂不可用，下方为原始文本。",
  "Copy": "复制",
  "Copying…": "正在复制…",
  "Copied": "已复制",
  "Copy unavailable": "无法复制",
} as const;
const t = (locale: Locale, text: keyof typeof labels) => locale === "zh-CN" ? labels[text] : text;
const visible = (item: WindowItem) => item.kind === "visible-response" && item.representation !== "WITHHELD";

class FormattingBoundary extends Component<{ children: ReactNode; source: string; locale: Locale }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() {
    return this.state.failed ? <><p className="muted">{t(this.props.locale, "Formatting unavailable. Exact source follows.")}</p>
      <p className="conversation-answer">{this.props.source}</p></> : this.props.children;
  }
}

/** Mounted for one exact text value. Changing source or scope unmounts pending feedback. */
function ResponseCopy({ text, ordinal, locale }: { text: string; ordinal: number; locale: Locale }) {
  const [state, setState] = useState<"idle" | "pending" | "copied" | "failed">("idle");
  const mounted = useRef(false), pending = useRef(false);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  const available = typeof navigator !== "undefined" && typeof navigator.clipboard?.writeText === "function";
  const copy = async () => {
    if (!available || pending.current) return;
    pending.current = true; setState("pending");
    try {
      await navigator.clipboard.writeText(text);
      if (mounted.current) setState("copied");
    } catch {
      if (mounted.current) setState("failed");
    } finally { pending.current = false; }
  };
  const caption = state === "pending" ? "Copying…" : state === "copied" ? "Copied"
    : state === "failed" || !available ? "Copy unavailable" : "Copy";
  return <button type="button" onClick={() => { void copy(); }} disabled={!available || state === "pending"}
    aria-label={locale === "zh-CN" ? `复制回复 ${ordinal}` : `Copy response ${ordinal}`}>
    {t(locale, caption)}
  </button>;
}

export interface ObservedTranscriptProps {
  items: readonly WindowItem[];
  locale?: Locale;
}

/** Display-only consumer of the already-qualified, bounded visible window.
 * Parent remounts on source/auth/target changes. No retained history, request,
 * send callback, URL fetch, authority derivation or second session store.
 */
export function ObservedTranscript({ items, locale = "en" }: ObservedTranscriptProps) {
  const [query, setQuery] = useState("");
  const [formatted, setFormatted] = useState(false);
  const id = useId(), search = useRef<HTMLInputElement>(null);
  const normalized = query.trim().toLowerCase();
  const rows = useMemo(() => items.map((item, index) => ({ item, ordinal: index + 1 })), [items]);
  const readable = rows.filter(({ item }) => visible(item));
  const matches = readable.filter(({ item }) => !normalized || (item.text ?? "").toLowerCase().includes(normalized));
  const withheld = rows.filter(({ item }) => !visible(item));
  const matchedIds = new Set(matches.map(({ item }) => item.id));
  // Keep source order, including visible gaps. A withheld row is never queried.
  const rendered = rows.filter(({ item }) => !visible(item) || matchedIds.has(item.id));
  const contentRevision = useMemo(() => [items, formatted], [items, formatted]);
  const scroll = useObservedTranscriptScroll(contentRevision, normalized.length > 0);
  const clear = () => { setQuery(""); search.current?.focus(); };
  return <section className="observed-transcript" aria-label={t(locale, "Observed responses")}>
    <div className="observed-transcript-toolbar">
      <div className="observed-search">
        <label htmlFor={`${id}-search`}>{t(locale, "Search observed responses")}</label>
        <div className="observed-search-input">
          <input id={`${id}-search`} ref={search} type="search" value={query} maxLength={160}
            placeholder={t(locale, "Search this window only")} aria-describedby={`${id}-coverage`}
            onChange={event => setQuery(event.target.value)} onKeyDown={event => {
              if (event.key === "Escape" && !event.nativeEvent.isComposing && event.nativeEvent.keyCode !== 229) {
                event.preventDefault(); event.stopPropagation(); clear();
              }
            }} />
          {query && <button type="button" onClick={clear}>{t(locale, "Clear search")}</button>}
        </div>
      </div>
      <button type="button" aria-pressed={formatted} disabled={readable.length === 0}
        onClick={() => setFormatted(value => !value)}>
        {t(locale, formatted ? "Exact source" : "Formatted responses")}
      </button>
    </div>
    <p id={`${id}-coverage`} className="observed-transcript-coverage">
      {t(locale, "Only this observed window is searched. Full history is not established.")}
    </p>
    {normalized && <p role="status" className="observed-transcript-count">
      {locale === "zh-CN" ? `${matches.length} / ${readable.length} 条可见回复匹配` : `${matches.length} of ${readable.length} visible responses match`}
    </p>}
    <div ref={scroll.viewport} className="observed-transcript-viewport" tabIndex={0} role="region"
      aria-label={t(locale, "Observed response list")} onScroll={scroll.onScroll} onWheel={scroll.onWheel}
      onPointerDown={scroll.onPointerDown} onTouchStart={scroll.onTouchStart} onKeyDown={scroll.onKeyDown}>
      <div ref={scroll.content} className="conversation-transcript">
        {rendered.map(({ item, ordinal }) => <article key={item.id} className="conversation-response"
          aria-label={locale === "zh-CN" ? `观察回复 ${ordinal}` : `Observed response ${ordinal}`}>
          <header className="observed-response-header">
            <p className="conversation-eyebrow">{t(locale, visible(item) ? "Owner-visible response" : "Content withheld")} · {item.state}</p>
            {visible(item) && typeof item.text === "string" && item.text.length > 0 &&
              <ResponseCopy key={item.text} text={item.text} ordinal={ordinal} locale={locale} />}
          </header>
          {!visible(item) ? <p>{t(locale, "Content withheld by its owner.")}</p>
            : item.text == null || item.text === "" ? <p>{t(locale, "No visible text was supplied.")}</p>
            : formatted ? <FormattingBoundary source={item.text} locale={locale}>
              <Suspense fallback={<p className="muted">{t(locale, "Loading formatted response…")}</p>}>
                <SourceMarkdown source={item.text} streaming={item.state === "partial"} locale={locale} />
              </Suspense>
            </FormattingBoundary> : <p className="conversation-answer">{item.text}</p>}
        </article>)}
        {items.length === 0 && <p>{t(locale, "No visible response was supplied in this observed window.")}</p>}
        {normalized && matches.length === 0 && <p>{t(locale, "No visible responses match this search.")}</p>}
      </div>
    </div>
    {withheld.length > 0 && <p className="observed-transcript-coverage">{t(locale, "Withheld content is not searched or copied.")}</p>}
    {items.length > 0 && !normalized && <div className="observed-transcript-footer">
      <span>{t(locale, scroll.following ? "Following latest observed response" : "Reading earlier responses")}</span>
      {!scroll.following && <button type="button" onClick={scroll.jumpToLatest}>{t(locale, "Jump to latest observed response")}</button>}
    </div>}
  </section>;
}
