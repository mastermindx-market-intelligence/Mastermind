// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ObservedTranscript } from "./ObservedTranscript";
import type { WindowItem } from "../workspace-contract";

const item = (id: string, text: string | null, extra: Partial<WindowItem> = {}): WindowItem => ({
  id, text, source_sequence: 1, publication_sequence: 1, state: "completed",
  kind: "visible-response", representation: "VISIBLE_TEXT", display_sha256: "a".repeat(64), ...extra,
});
const search = () => screen.getByRole<HTMLInputElement>("searchbox");
const clipboard = (writeText = vi.fn().mockResolvedValue(undefined)) => {
  Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
  return writeText;
};
afterEach(() => { cleanup(); vi.restoreAllMocks(); Object.defineProperty(navigator, "clipboard", { configurable: true, value: undefined }); });

describe("observed transcript over the existing qualified window", () => {
  it("renders exact visible text and never interprets HTML or exposes send controls", () => {
    const text = "<script>window.stolen = true</script>\n**original**\n<script-src>";
    const { container } = render(<ObservedTranscript items={[item("1", text)]} />);
    expect(container.querySelector(".conversation-answer")?.textContent).toBe(text);
    expect(container.querySelectorAll("script,iframe,img,a")).toHaveLength(0);
    expect(screen.queryByRole("button", { name: /send|stop/i })).toBeNull();
    expect(screen.getByText(/Full history is not established/)).toBeTruthy();
  });
  it.each([
    { kind: "withheld" as const, representation: "VISIBLE_TEXT" as const },
    { kind: "visible-response" as const, representation: "WITHHELD" as const },
  ])("never searches or copies withheld text, even contradictory input: %j", extra => {
    clipboard();
    const { container } = render(<ObservedTranscript items={[item("secret", "SECRET-HIDDEN", extra), item("2", "Visible")]} />);
    fireEvent.change(search(), { target: { value: "SECRET-HIDDEN" } });
    expect(container.textContent).not.toContain("SECRET-HIDDEN");
    expect(screen.getByText("0 of 1 visible responses match")).toBeTruthy();
    expect(screen.getByText("Content withheld by its owner.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Copy response 1" })).toBeNull();
  });
  it("searches literally and case-insensitively within only supplied visible rows", () => {
    render(<ObservedTranscript items={[item("1", "Alpha [.*] source"), item("2", "Beta source")]} />);
    fireEvent.change(search(), { target: { value: "ALPHA [.*]" } });
    expect(screen.getByText("Alpha [.*] source")).toBeTruthy();
    expect(screen.queryByText("Beta source")).toBeNull();
    expect(screen.getByText("1 of 2 visible responses match")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Clear search" }));
    expect(search().value).toBe("");
    expect(document.activeElement).toBe(search());
    expect(screen.getByText("Beta source")).toBeTruthy();
  });
  it("filters Unicode without changing or reconstructing source bytes", () => {
    const text = "研究结果 🧭\nKeep exact text.";
    render(<ObservedTranscript items={[item("1", text)]} locale="zh-CN" />);
    fireEvent.change(search(), { target: { value: "🧭" } });
    expect(screen.getByText("1 / 1 条可见回复匹配")).toBeTruthy();
    expect(document.querySelector(".conversation-answer")?.textContent).toBe(text);
  });
  it("does not clear a query on IME Escape; ordinary Escape clears it", () => {
    render(<ObservedTranscript items={[item("1", "result")]} />);
    fireEvent.change(search(), { target: { value: "query" } });
    fireEvent.keyDown(search(), { key: "Escape", isComposing: true });
    expect(search().value).toBe("query");
    fireEvent.keyDown(search(), { key: "Escape" });
    expect(search().value).toBe("");
  });
  it("withdraws prior text immediately on source correction", () => {
    const view = render(<ObservedTranscript items={[item("1", "old")]} />);
    view.rerender(<ObservedTranscript items={[item("1", "corrected")]} />);
    expect(screen.queryByText("old")).toBeNull();
    expect(screen.getByText("corrected")).toBeTruthy();
  });
  it("preserves a query across passive updates but resets with the parent scope key", () => {
    const view = render(<ObservedTranscript key="A" items={[item("1", "old")]} />);
    fireEvent.change(search(), { target: { value: "old" } });
    view.rerender(<ObservedTranscript key="A" items={[item("1", "old"), item("2", "new")]} />);
    expect(search().value).toBe("old");
    view.rerender(<ObservedTranscript key="B" items={[item("3", "other scope")]} />);
    expect(search().value).toBe("");
    expect(screen.queryByText("old")).toBeNull();
  });
  it.each([null, ""])("does not infer content or offer copying for %j", text => {
    render(<ObservedTranscript items={[item("1", text)]} />);
    expect(screen.getByText("No visible text was supplied.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Copy response 1" })).toBeNull();
  });
  it("renders empty and no-match states separately", () => {
    const view = render(<ObservedTranscript items={[]} />);
    expect(screen.getByText("No visible response was supplied in this observed window.")).toBeTruthy();
    view.rerender(<ObservedTranscript items={[item("1", "visible")]} />);
    fireEvent.change(search(), { target: { value: "missing" } });
    expect(screen.getByText("No visible responses match this search.")).toBeTruthy();
  });
  it("copies only after a deliberate click and preserves exact Unicode/newlines", async () => {
    const write = clipboard(); const text = "# Heading\n\nExact 🧭  text\n";
    render(<ObservedTranscript items={[item("1", text)]} />);
    expect(write).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Copy response 1" }));
    await screen.findByText("Copied");
    expect(write).toHaveBeenCalledExactlyOnceWith(text);
  });
  it("reports denied clipboard access without claiming success", async () => {
    clipboard(vi.fn().mockRejectedValue(new Error("denied")));
    render(<ObservedTranscript items={[item("1", "text")]} />);
    fireEvent.click(screen.getByRole("button", { name: "Copy response 1" }));
    await screen.findByText("Copy unavailable");
    expect(screen.queryByText("Copied")).toBeNull();
  });
  it("truthfully disables copying when the browser capability is absent", () => {
    render(<ObservedTranscript items={[item("1", "text")]} />);
    expect(screen.getByRole<HTMLButtonElement>("button", { name: "Copy response 1" }).disabled).toBe(true);
    expect(screen.getByText("Copy unavailable")).toBeTruthy();
  });
  it("does not duplicate pending copy or apply old completion to changed source", async () => {
    let finish!: () => void;
    const write = clipboard(vi.fn(() => new Promise<void>(resolve => { finish = resolve; })));
    const view = render(<ObservedTranscript items={[item("1", "old")]} />);
    fireEvent.click(screen.getByRole("button", { name: "Copy response 1" }));
    fireEvent.click(screen.getByRole("button", { name: "Copy response 1" }));
    expect(write).toHaveBeenCalledTimes(1);
    view.rerender(<ObservedTranscript items={[item("1", "new")]} />);
    await act(async () => finish());
    expect(screen.queryByText("Copied")).toBeNull();
    expect(screen.getByText("new")).toBeTruthy();
  });
  it("formats the actual partial response safely and restores exact source", async () => {
    const original = "# Research\n\n| Item | Value |\n| --- | --- |\n| A | 2 |\n\n[x](https://example.invalid) ![private](https://example.invalid/image)";
    const view = render(<ObservedTranscript items={[item("1", original, { state: "partial" })]} />);
    fireEvent.click(screen.getByRole("button", { name: "Formatted responses" }));
    // jsdom has no IntersectionObserver: the exact source remains until explicit demand.
    fireEvent.click(screen.getByRole("button", { name: "Format this response" }));
    await screen.findByRole("heading", { name: "Research" });
    expect(screen.getByRole("table")).toBeTruthy();
    expect(view.container.querySelectorAll("a,img,iframe")).toHaveLength(0);
    expect(view.container.querySelector('.source-markdown[data-streaming="true"]')).not.toBeNull();
    view.rerender(<ObservedTranscript items={[item("1", original + "\n\nFinal response", { state: "completed" })]} />);
    await screen.findByText("Final response");
    fireEvent.click(screen.getByRole("button", { name: "Exact source" }));
    expect(view.container.querySelector(".conversation-answer")?.textContent).toBe(original + "\n\nFinal response");
  });
  it("keeps withheld rows in their original positions during search", () => {
    render(<ObservedTranscript items={[item("1", "match"), item("2", null, { kind: "withheld", representation: "WITHHELD" }), item("3", "match")] } />);
    fireEvent.change(search(), { target: { value: "match" } });
    const region = screen.getByRole("region", { name: "Observed response list" });
    expect(within(region).getAllByRole("article").map(node => node.getAttribute("aria-label")))
      .toEqual(["Observed response 1", "Observed response 2", "Observed response 3"]);
  });
  it("source filtering exposes no browser persistence or network calls", () => {
    const fetch = vi.fn(); vi.stubGlobal("fetch", fetch);
    const store = vi.spyOn(Storage.prototype, "setItem");
    render(<ObservedTranscript items={[item("1", "answer")]} />);
    fireEvent.change(search(), { target: { value: "answer" } });
    expect(fetch).not.toHaveBeenCalled(); expect(store).not.toHaveBeenCalled();
    vi.unstubAllGlobals();
  });
});
