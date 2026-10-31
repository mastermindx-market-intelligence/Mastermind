import { Component, Suspense, lazy, useEffect, useRef, useState, type ReactNode, type RefObject } from "react";

const SourceMarkdown = lazy(() => import("./SourceMarkdown").then(module => ({ default: module.SourceMarkdown })));
type Locale = "en" | "zh-CN";
class FormattingBoundary extends Component<{ children: ReactNode; source: string; locale: Locale }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() {
    return this.state.failed ? <>
      <p className="muted">{this.props.locale === "zh-CN" ? "格式化暂不可用，下方为原始文本。" : "Formatting unavailable. Exact source follows."}</p>
      <p className="conversation-answer">{this.props.source}</p>
    </> : this.props.children;
  }
}

/** Demand-driven display only. Exact source remains available before formatting.
 * One valid window can contain 256 responses / 1 MiB. Do not multiply the per-
 * response Markdown AST budget by every offscreen response on one user click.
 * Intersection observation supplies no session identity, history or authority.
 */
export function ObservedResponseMarkdown({ source, streaming, locale, viewport }: {
  source: string;
  streaming: boolean;
  locale: Locale;
  viewport: RefObject<HTMLDivElement | null>;
}) {
  const element = useRef<HTMLDivElement>(null);
  const [requested, setRequested] = useState(false);
  useEffect(() => {
    if (requested || !element.current || !viewport.current || typeof IntersectionObserver === "undefined") return;
    let active = true;
    const observer = new IntersectionObserver(entries => {
      if (!active || !entries.some(entry => entry.target === element.current && entry.isIntersecting)) return;
      active = false;
      observer.disconnect();
      setRequested(true);
    }, { root: viewport.current, rootMargin: "0px", threshold: 0 });
    observer.observe(element.current);
    return () => { active = false; observer.disconnect(); };
  }, [requested, viewport]);
  const exact = <p className="conversation-answer">{source}</p>;
  return <div ref={element} className="observed-response-format" data-format={requested ? "requested" : "deferred"}>
    {requested ? <FormattingBoundary source={source} locale={locale}>
      <Suspense fallback={exact}>
        <SourceMarkdown source={source} streaming={streaming} locale={locale} />
      </Suspense>
    </FormattingBoundary> : <>{exact}
      <button type="button" className="observed-format-on-demand" onClick={() => setRequested(true)}>
        {locale === "zh-CN" ? "格式化此回复" : "Format this response"}
      </button>
    </>}
  </div>;
}
