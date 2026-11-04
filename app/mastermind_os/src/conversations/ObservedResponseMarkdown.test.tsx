// @vitest-environment jsdom
import { useRef } from "react";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ObservedResponseMarkdown } from "./ObservedResponseMarkdown";

type Record = { callback: IntersectionObserverCallback; target: Element | null; disconnect: () => void; options?: IntersectionObserverInit };
let observers: Record[];
function installObserver() {
  vi.stubGlobal("IntersectionObserver", class {
    record: Record;
    constructor(callback: IntersectionObserverCallback, options?: IntersectionObserverInit) {
      this.record = { callback, target: null, disconnect: vi.fn(), options };
      observers.push(this.record);
    }
    observe(target: Element) { this.record.target = target; }
    disconnect() { this.record.disconnect(); }
  });
}
function intersect(record: Record, value = true, target = record.target!) {
  act(() => record.callback([{ target, isIntersecting: value } as IntersectionObserverEntry], {} as IntersectionObserver));
}
function Harness({ source = "## Original response\n\nExact **source**.", streaming = false, locale = "en", count = 1 }:
  { source?: string; streaming?: boolean; locale?: "en" | "zh-CN"; count?: number }) {
  const viewport = useRef<HTMLDivElement>(null);
  return <div ref={viewport} data-testid="viewport">
    {Array.from({ length: count }, (_, i) => <ObservedResponseMarkdown key={i} source={source}
      streaming={streaming} locale={locale} viewport={viewport} />)}
  </div>;
}
beforeEach(() => { observers = []; installObserver(); });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe("demand-driven observed response formatting", () => {
  it("keeps exact source before intersection without constructing a Markdown tree", () => {
    const { container } = render(<Harness />);
    expect(container.querySelector(".conversation-answer")?.textContent).toBe("## Original response\n\nExact **source**.");
    expect(container.querySelector(".source-markdown")).toBeNull();
    expect(observers).toHaveLength(1);
    expect(observers[0].options).toMatchObject({ root: screen.getByTestId("viewport"), rootMargin: "0px", threshold: 0 });
  });
  it("loads only the exact intersecting response and disconnects its observer", async () => {
    const { container } = render(<Harness count={3} />);
    intersect(observers[1]);
    await screen.findByRole("heading", { name: "Original response" });
    expect(container.querySelectorAll(".source-markdown")).toHaveLength(1);
    expect(container.querySelectorAll('[data-format="deferred"]')).toHaveLength(2);
    expect(observers[1].disconnect).toHaveBeenCalled();
  });
  it("ignores offscreen and foreign-node observations", () => {
    const { container } = render(<Harness />);
    intersect(observers[0], false); intersect(observers[0], true, document.createElement("div"));
    expect(container.querySelector(".source-markdown")).toBeNull();
  });
  it("provides explicit user-driven fallback without IntersectionObserver", async () => {
    vi.stubGlobal("IntersectionObserver", undefined);
    render(<Harness />);
    expect(screen.queryByRole("heading")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Format this response" }));
    await screen.findByRole("heading", { name: "Original response" });
  });
  it("uses the newest source when an initially offscreen response is corrected", async () => {
    const view = render(<Harness source="## Old" />);
    view.rerender(<Harness source="## Corrected" />);
    intersect(observers[0]);
    await screen.findByRole("heading", { name: "Corrected" });
    expect(screen.queryByText("Old")).toBeNull();
  });
  it("preserves partial/settled ownership after lazy activation", async () => {
    const view = render(<Harness streaming />);
    intersect(observers[0]); await screen.findByRole("heading", { name: "Original response" });
    expect(view.container.querySelector('.source-markdown[data-streaming="true"]')).not.toBeNull();
    view.rerender(<Harness streaming={false} />);
    expect(view.container.querySelector('.source-markdown[data-streaming="false"]')).not.toBeNull();
  });
  it("does not reactivate a withdrawn source from a retained observer callback", () => {
    const view = render(<Harness />); const previous = observers[0];
    view.unmount(); intersect(previous);
    expect(previous.disconnect).toHaveBeenCalled();
    expect(screen.queryByText(/Original response/)).toBeNull();
  });
  it("keeps format demand local and translated without changing source text", async () => {
    render(<Harness locale="zh-CN" source="## Source stays English" />);
    fireEvent.click(screen.getByRole("button", { name: "格式化此回复" }));
    await screen.findByRole("heading", { name: "Source stays English" });
  });
  it("does not eagerly multiply Markdown parsing across all 256 legal rows", async () => {
    const { container } = render(<Harness count={256} source={"*x* ".repeat(1000)} />);
    expect(container.querySelectorAll(".source-markdown")).toHaveLength(0);
    expect(container.querySelectorAll(".conversation-answer")).toHaveLength(256);
    expect(observers).toHaveLength(256);
    intersect(observers[255]);
    await waitFor(() => expect(container.querySelectorAll(".source-markdown")).toHaveLength(1));
    expect(container.querySelectorAll(".source-markdown")).toHaveLength(1);
    expect(container.querySelectorAll('[data-format="deferred"]')).toHaveLength(255);
  });
});
