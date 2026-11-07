// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useObservedTranscriptScroll } from "./useObservedTranscriptScroll";
import { ScrollFollow, scrollMetrics } from "../vendor/deepseek/use-scroll-follow";

function Probe({ revision = 1, filtering = false }: { revision?: number; filtering?: boolean }) {
  const scroll = useObservedTranscriptScroll(revision, filtering);
  return <><div ref={scroll.viewport} role="region" tabIndex={0} aria-label="viewport"
    onScroll={scroll.onScroll} onWheel={scroll.onWheel} onPointerDown={scroll.onPointerDown}
    onTouchStart={scroll.onTouchStart} onKeyDown={scroll.onKeyDown}>
    <div ref={scroll.content}><button>Child control</button></div>
  </div><span>{scroll.following ? "following" : "reading"}</span>
  <button onClick={scroll.jumpToLatest}>Latest</button></>;
}
function geometry(element: HTMLElement, top: number, total = 1600, height = 600) {
  Object.defineProperty(element, "clientHeight", { configurable: true, value: height });
  Object.defineProperty(element, "scrollHeight", { configurable: true, value: total });
  element.scrollTop = top;
}
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe("DeepSeek scroll-follow adapter in the observed window", () => {
  it("follows growing content only while at the bottom", () => {
    const view = render(<Probe />); const element = screen.getByRole("region");
    geometry(element, 1000); fireEvent.scroll(element);
    geometry(element, 1000, 2000); view.rerender(<Probe revision={2} />);
    expect(element.scrollTop).toBe(1400);
    expect(screen.getByText("following")).toBeTruthy();
  });
  it("preserves earlier reading position across passive updates", () => {
    const view = render(<Probe />); const element = screen.getByRole("region");
    geometry(element, 1000); fireEvent.scroll(element);
    geometry(element, 210); fireEvent.scroll(element);
    geometry(element, 210, 2400); view.rerender(<Probe revision={2} />);
    expect(element.scrollTop).toBe(210);
    expect(screen.getByText("reading")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Latest" }));
    expect(element.scrollTop).toBe(1800); expect(document.activeElement).toBe(element);
  });
  it("releases follow on upward wheel before browser scroll delivery", () => {
    const view = render(<Probe />); const element = screen.getByRole("region");
    geometry(element, 1000); fireEvent.scroll(element);
    fireEvent.wheel(element, { deltaY: -15 });
    geometry(element, 1000, 2200); view.rerender(<Probe revision={2} />);
    expect(element.scrollTop).toBe(1000);
    expect(screen.getByText("reading")).toBeTruthy();
  });
  it.each(["Home", "PageUp", "ArrowUp"])("preserves user intent on %s", key => {
    const view = render(<Probe />); const element = screen.getByRole("region");
    geometry(element, 1000); fireEvent.scroll(element); fireEvent.keyDown(element, { key });
    geometry(element, 1000, 2200); view.rerender(<Probe revision={2} />);
    expect(element.scrollTop).toBe(1000);
  });
  it("does not interpret a child control's keys as viewport navigation", () => {
    render(<Probe />); const element = screen.getByRole("region");
    geometry(element, 1000); fireEvent.scroll(element);
    fireEvent.keyDown(screen.getByRole("button", { name: "Child control" }), { key: "Home" });
    expect(screen.getByText("following")).toBeTruthy();
  });
  it("pauses following while searching and does not jump on query clear", () => {
    const view = render(<Probe />); const element = screen.getByRole("region");
    geometry(element, 1000); fireEvent.scroll(element);
    view.rerender(<Probe filtering revision={2} />); expect(element.scrollTop).toBe(0);
    fireEvent.scroll(element); fireEvent.click(screen.getByRole("button", { name: "Latest" }));
    expect(element.scrollTop).toBe(0);
    view.rerender(<Probe filtering={false} revision={3} />);
    expect(element.scrollTop).toBe(0); expect(screen.getByText("reading")).toBeTruthy();
  });
  it("releases on pointer interaction and resumes only through actual bottom arrival", () => {
    render(<Probe />); const element = screen.getByRole("region");
    geometry(element, 1000); fireEvent.scroll(element); fireEvent.pointerDown(element);
    expect(screen.getByText("reading")).toBeTruthy();
    geometry(element, 300); fireEvent.scroll(element); geometry(element, 1000); fireEvent.scroll(element);
    expect(screen.getByText("following")).toBeTruthy();
  });
  it("uses and releases the donor's exact scrollport association", () => {
    const view = render(<Probe />); const element = screen.getByRole("region");
    expect(ScrollFollow.forElement(element)).toBeDefined(); view.unmount();
    expect(ScrollFollow.forElement(element)).toBeUndefined();
  });
  it("observes real layout growth and cleans up its existing browser observers", () => {
    let notify!: ResizeObserverCallback; const disconnect = vi.fn(), observe = vi.fn();
    vi.stubGlobal("ResizeObserver", class {
      constructor(callback: ResizeObserverCallback) { notify = callback; }
      observe = observe;
      disconnect = disconnect;
    });
    const view = render(<Probe />); const element = screen.getByRole("region");
    geometry(element, 1000); fireEvent.scroll(element); geometry(element, 1000, 2400);
    act(() => notify([], {} as ResizeObserver)); expect(element.scrollTop).toBe(1800);
    expect(observe).toHaveBeenCalledTimes(2); view.unmount(); expect(disconnect).toHaveBeenCalledTimes(1);
  });
});

describe("byte-identical donor scrolling invariants", () => {
  it("clamps metrics and explicit jumps to the real document range", () => {
    const element = document.createElement("div"); geometry(element, 20, 400, 600);
    const follow = new ScrollFollow(true, 48); expect(scrollMetrics(element).floor).toBe(0);
    expect(follow.jump(element, scrollMetrics(element), 100).top).toBe(0);
  });
  it("does not release a newer controller when an older binding unmounts", () => {
    const element = document.createElement("div");
    const first = new ScrollFollow(true, 48), second = new ScrollFollow(false, 48);
    const release = first.bind(element); second.bind(element); release();
    expect(ScrollFollow.forElement(element)).toBe(second);
  });
  it("respects reduced motion on an explicit smooth request", () => {
    vi.stubGlobal("matchMedia", () => ({ matches: true }));
    const element = document.createElement("div"); geometry(element, 0);
    const move = vi.fn(); element.scrollTo = move;
    new ScrollFollow(false, 48).toBottom(element, scrollMetrics(element), "smooth");
    expect(element.scrollTop).toBe(1000); expect(move).not.toHaveBeenCalled();
  });
  it("settles interrupted native animation without inventing follow intent", () => {
    const element = document.createElement("div"); geometry(element, 0);
    const move = vi.fn(); element.scrollTo = move;
    const follow = new ScrollFollow(false, 48); follow.toBottom(element, scrollMetrics(element), "smooth");
    expect(move).toHaveBeenCalledWith({ top: 1000, behavior: "smooth" });
    expect(follow.animating).toBe(true);
    follow.settle({ top: 200, floor: 1000, height: 600 });
    expect(follow.active).toBe(false); expect(follow.animating).toBe(false);
  });
});
