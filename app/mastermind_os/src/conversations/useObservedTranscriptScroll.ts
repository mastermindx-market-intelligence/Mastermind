import { useLayoutEffect, useRef, useState, type KeyboardEvent, type WheelEvent } from "react";
import { scrollMetrics, useScrollFollow } from "../vendor/deepseek/use-scroll-follow";

/** A view-only scroll adapter. It owns no conversation data, transport or history. */
export function useObservedTranscriptScroll(contentRevision: unknown, filtering: boolean) {
  const viewport = useRef<HTMLDivElement>(null);
  const content = useRef<HTMLDivElement>(null);
  const follow = useScrollFollow(true, 48);
  const filteringRef = useRef(filtering);
  filteringRef.current = filtering;
  const [following, setFollowing] = useState(true);
  const sync = () => setFollowing(follow.active && !filteringRef.current);
  const grow = () => {
    const element = viewport.current;
    if (!element || filteringRef.current || !follow.active) return;
    follow.toBottom(element, scrollMetrics(element), "instant");
    sync();
  };
  useLayoutEffect(() => {
    const element = viewport.current, body = content.current;
    if (!element || !body) return;
    const release = follow.bind(element);
    const onEnd = () => {
      if (!filteringRef.current) follow.settle(scrollMetrics(element));
      sync();
    };
    element.addEventListener("scrollend", onEnd);
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(grow);
    observer?.observe(element);
    observer?.observe(body);
    grow();
    return () => {
      observer?.disconnect();
      element.removeEventListener("scrollend", onEnd);
      release();
    };
  }, [follow]);
  useLayoutEffect(() => {
    if (filtering) {
      follow.reset();
      if (viewport.current) viewport.current.scrollTop = 0;
      sync();
    } else grow();
  }, [contentRevision, filtering, follow]);
  const interrupt = () => {
    const element = viewport.current;
    if (element) follow.interrupt(element, scrollMetrics(element));
  };
  const releaseFollowing = () => {
    interrupt();
    follow.setFollowing(false);
    sync();
  };
  return {
    viewport, content, following,
    onScroll: () => {
      if (!viewport.current || filteringRef.current) return;
      follow.sample(scrollMetrics(viewport.current));
      sync();
    },
    onWheel: (event: WheelEvent<HTMLDivElement>) => {
      interrupt();
      // Release before the native scroll arrives, including content growth in between.
      if (event.deltaY < 0) releaseFollowing();
    },
    onPointerDown: releaseFollowing,
    onTouchStart: interrupt,
    onKeyDown: (event: KeyboardEvent<HTMLDivElement>) => {
      if (event.target !== event.currentTarget) return;
      if (["ArrowUp", "PageUp", "Home"].includes(event.key)) releaseFollowing();
    },
    jumpToLatest: () => {
      const element = viewport.current;
      if (!element || filteringRef.current) return;
      follow.toBottom(element, scrollMetrics(element), "instant");
      sync();
      element.focus({ preventScroll: true });
    },
  };
}
