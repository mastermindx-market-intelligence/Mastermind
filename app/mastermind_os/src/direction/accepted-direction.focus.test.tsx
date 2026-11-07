// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AcceptedDirectionPanel } from "./AcceptedDirectionPanel";
import { decodeAcceptedDirection, type AcceptedDirectionRead } from "./accepted-direction";

// jsdom has no layout engine: stub scrolling for this focused suite only.
const scrollIntoViewMock = vi.fn();
HTMLElement.prototype.scrollIntoView = scrollIntoViewMock as typeof HTMLElement.prototype.scrollIntoView;

const work = { work_ref: "WS:DIRECTION-TEST" };
function directionDocument(): AcceptedDirectionRead {
  const source = { repository: "mastermindx-market-intelligence/macro", commit: "a".repeat(40),
    path: "agentos/workstreams/WS-DIRECTION-TEST.md", content_sha256: "b".repeat(64) };
  const row = (key: string, answer: string, predecessor: string | null) => ({ decision_ref: `DEC:${key}`, answer,
    rationale: `Why ${answer}`, decided_by: "delegated-root", decided_at: "2026-11-04", date_precision: "DAY",
    predecessor, source: { ...source, path: `agentos/decisions/DEC-${key}.md` } });
  return decodeAcceptedDirection({ schema: "mastermind.workspace_project_direction.v1", selection: work,
    availability: "AVAILABLE", source, reason_codes: [], direction: { work_ref: work.work_ref, workstream_source: source,
      current: row("CURRENT", "Complete the original journey", "DEC:PREVIOUS"),
      history: { revisions: [row("PREVIOUS", "An explicitly superseded Direction", null)], has_more: false, total_count: 2 } } }, work);
}

const inspectorHeading = (name: string) => screen.getByRole("heading", { level: 4, name });
const attachExternalInput = () => {
  const input = document.createElement("input");
  input.setAttribute("aria-label", "external");
  document.body.appendChild(input);
  input.focus();
  return input;
};

afterEach(() => { cleanup(); document.body.innerHTML = ""; });
describe("Accepted Direction gesture focus (AT27 focus-only repair)", () => {
  it("focuses the selected previous-revision inspector after its DOM commits and scrolls it into view", async () => {
    const focusSpy = vi.spyOn(HTMLElement.prototype, "focus");
    render(<AcceptedDirectionPanel selection={work} read={async () => directionDocument()} sourceGeneration={() => 1} canRead={() => true} onChangeDirection={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: "Read Direction" }));
    await screen.findByRole("article", { name: "Current accepted Direction" });
    expect(focusSpy).not.toHaveBeenCalled(); // passive read never focuses
    focusSpy.mockClear(); scrollIntoViewMock.mockClear();
    fireEvent.click(screen.getByRole("button", { name: /An explicitly superseded Direction/ }));
    const heading = inspectorHeading("Previous revision · Read only");
    expect(document.activeElement).toBe(heading);
    expect(focusSpy).toHaveBeenCalledTimes(1);
    expect(scrollIntoViewMock).toHaveBeenCalledTimes(1);
    expect(scrollIntoViewMock).toHaveBeenCalledWith({ block: "start" });
    expect(scrollIntoViewMock.mock.contexts[0]).toBe(heading);
  });

  it("re-focusing the already selected row focuses the existing inspector without re-reading", async () => {
    const read = vi.fn(async () => directionDocument());
    const focusSpy = vi.spyOn(HTMLElement.prototype, "focus");
    render(<AcceptedDirectionPanel selection={work} read={read} sourceGeneration={() => 1} canRead={() => true} onChangeDirection={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: "Read Direction" }));
    await screen.findByRole("article", { name: "Current accepted Direction" });
    fireEvent.click(screen.getByRole("button", { name: /An explicitly superseded Direction/ }));
    const heading = inspectorHeading("Previous revision · Read only");
    focusSpy.mockClear(); scrollIntoViewMock.mockClear();
    fireEvent.click(screen.getByRole("button", { name: /An explicitly superseded Direction/ }));
    expect(inspectorHeading("Previous revision · Read only")).toBe(heading);
    expect(document.activeElement).toBe(heading);
    expect(focusSpy).toHaveBeenCalledTimes(1);
    expect(scrollIntoViewMock).toHaveBeenCalledTimes(1);
    expect(read).toHaveBeenCalledTimes(1);
  });

  it("focuses the current inspector h4 on the View current Direction gesture", async () => {
    const focusSpy = vi.spyOn(HTMLElement.prototype, "focus");
    render(<AcceptedDirectionPanel selection={work} read={async () => directionDocument()} sourceGeneration={() => 1} canRead={() => true} onChangeDirection={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: "Read Direction" }));
    await screen.findByRole("article", { name: "Current accepted Direction" });
    fireEvent.click(screen.getByRole("button", { name: /An explicitly superseded Direction/ }));
    inspectorHeading("Previous revision · Read only");
    focusSpy.mockClear(); scrollIntoViewMock.mockClear();
    fireEvent.click(screen.getByRole("button", { name: "View current Direction" }));
    const heading = inspectorHeading("Current revision · Read only");
    expect(document.activeElement).toBe(heading);
    expect(focusSpy).toHaveBeenCalledTimes(1);
    expect(scrollIntoViewMock).toHaveBeenCalledWith({ block: "start" });
    expect(screen.getByRole("article", { name: "Current accepted Direction" }).textContent).toContain("Complete the original journey");
  });

  it("never steals existing external input focus on initial render, late read reply, or passive rerender", async () => {
    let resolve!: (value: AcceptedDirectionRead) => void;
    const read = vi.fn(() => new Promise<AcceptedDirectionRead>(done => { resolve = done; }));
    const focusSpy = vi.spyOn(HTMLElement.prototype, "focus");
    const props = { selection: work, read, sourceGeneration: () => 1, canRead: () => true, onChangeDirection: vi.fn() };
    const view = render(<AcceptedDirectionPanel {...props} />);
    const input = attachExternalInput();
    focusSpy.mockClear(); // the test's own external focus is not a panel focus
    fireEvent.click(screen.getByRole("button", { name: "Read Direction" }));
    expect(document.activeElement).toBe(input); // pending read does not focus
    await act(async () => resolve(directionDocument()));
    await screen.findByRole("article", { name: "Current accepted Direction" });
    expect(document.activeElement).toBe(input); // late reply does not steal focus
    view.rerender(<AcceptedDirectionPanel {...props} />);
    expect(document.activeElement).toBe(input); // passive rerender does not focus
    expect(focusSpy).not.toHaveBeenCalled();
    input.remove();
  });

  it("refuses gesture focus on a no-render live permission loss and never revives on passive regrant", async () => {
    const focusSpy = vi.spyOn(HTMLElement.prototype, "focus");
    let allowed = true;
    const read = vi.fn(async () => directionDocument());
    const props = { selection: work, read, sourceGeneration: () => 1, canRead: () => allowed, onChangeDirection: vi.fn() };
    const view = render(<AcceptedDirectionPanel {...props} />);
    fireEvent.click(screen.getByRole("button", { name: "Read Direction" }));
    await screen.findByRole("article", { name: "Current accepted Direction" });
    allowed = false; // live permission loss without any render
    fireEvent.click(screen.getByRole("button", { name: /An explicitly superseded Direction/ }));
    expect(screen.queryByRole("heading", { level: 4, name: "Previous revision · Read only" })).toBeNull();
    expect(document.activeElement).toBe(document.body);
    expect(screen.queryByRole("article", { name: "Previous Direction, read only" })).toBeNull();
    expect(focusSpy).not.toHaveBeenCalled();
    allowed = true; // passive regrant: discarded intent must not revive
    view.rerender(<AcceptedDirectionPanel {...props} />);
    expect(screen.queryByRole("article", { name: "Current accepted Direction" })).toBeNull();
    view.rerender(<AcceptedDirectionPanel {...props} />);
    expect(focusSpy).not.toHaveBeenCalled();
    // A new explicit gesture after a fresh read is honoured again.
    fireEvent.click(screen.getByRole("button", { name: "Read Direction" }));
    await screen.findByRole("article", { name: "Current accepted Direction" });
    expect(read).toHaveBeenCalledTimes(2);
    fireEvent.click(screen.getByRole("button", { name: /An explicitly superseded Direction/ }));
    expect(document.activeElement).toBe(inspectorHeading("Previous revision · Read only"));
    expect(focusSpy).toHaveBeenCalledTimes(1);
  });

  it("refuses gesture focus on a no-render source-generation loss", async () => {
    const focusSpy = vi.spyOn(HTMLElement.prototype, "focus");
    let epoch = 4;
    const read = vi.fn(async () => directionDocument());
    const props = { selection: work, read, sourceGeneration: () => epoch, canRead: () => true, onChangeDirection: vi.fn() };
    const view = render(<AcceptedDirectionPanel {...props} />);
    fireEvent.click(screen.getByRole("button", { name: "Read Direction" }));
    await screen.findByRole("article", { name: "Current accepted Direction" });
    epoch = 5; // live generation loss without any render
    fireEvent.click(screen.getByRole("button", { name: /An explicitly superseded Direction/ }));
    expect(screen.queryByRole("article", { name: "Previous Direction, read only" })).toBeNull();
    expect(focusSpy).not.toHaveBeenCalled();
    epoch = 4; // regrant is passive; discarded intent must not revive
    view.rerender(<AcceptedDirectionPanel {...props} />);
    fireEvent.click(screen.getByRole("button", { name: "Read Direction" }));
    await screen.findByRole("article", { name: "Current accepted Direction" });
    expect(focusSpy).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: /An explicitly superseded Direction/ }));
    expect(document.activeElement).toBe(inspectorHeading("Previous revision · Read only"));
  });

  it("focuses the localized inspector heading for a zh-CN history gesture", async () => {
    render(<AcceptedDirectionPanel selection={work} read={async () => directionDocument()} sourceGeneration={() => 1} canRead={() => true} onChangeDirection={() => {}} locale="zh-CN" />);
    fireEvent.click(screen.getByRole("button", { name: "读取方向" }));
    await screen.findByRole("article", { name: "当前已接受的方向" });
    fireEvent.click(screen.getByRole("button", { name: /An explicitly superseded Direction/ }));
    expect(document.activeElement).toBe(inspectorHeading("历史修订 · 只读"));
    expect(scrollIntoViewMock).toHaveBeenCalledWith({ block: "start" });
  });
});
