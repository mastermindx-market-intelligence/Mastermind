// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AcceptedDirectionPanel } from "./AcceptedDirectionPanel";
import { decodeAcceptedDirection, type AcceptedDirectionRead } from "./accepted-direction";

const work = { work_ref: "WS:DIRECTION-TEST" };
function document(): AcceptedDirectionRead {
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
afterEach(cleanup);
describe("Accepted Direction AT27 composition", () => {
  it("reads only explicitly, keeps current visible while old revision is inspected, and opens exact conversation", async () => {
    const read = vi.fn(async (_request: { work_ref: string; signal: AbortSignal }) => document()), navigate = vi.fn();
    const generation = () => 1, permission = () => true;
    render(<AcceptedDirectionPanel selection={work} read={read} sourceGeneration={generation} canRead={permission} onChangeDirection={navigate} />);
    expect(read).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Read Direction" }));
    await screen.findByRole("article", { name: "Current accepted Direction" });
    expect(read.mock.calls[0][0]).toMatchObject(work);
    fireEvent.click(screen.getByRole("button", { name: /An explicitly superseded Direction/ }));
    expect(screen.getByRole("article", { name: "Current accepted Direction" }).textContent).toContain("Complete the original journey");
    expect(screen.getByRole("article", { name: "Previous Direction, read only" }).textContent).toContain("An explicitly superseded Direction");
    expect(screen.queryByRole("button", { name: /make current|adopt|commit/i })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Change direction in conversation" }));
    expect(navigate).toHaveBeenCalledExactlyOnceWith(work.work_ref);
  });

  it("labels date precision and sources without inventing an observation clock", async () => {
    render(<AcceptedDirectionPanel selection={work} read={async () => document()} sourceGeneration={() => 1} canRead={() => true} onChangeDirection={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: "Read Direction" }));
    await screen.findByRole("article", { name: "Current accepted Direction" });
    expect(screen.getByText("Decision date (day precision)")).toBeTruthy();
    expect(screen.queryByText(/observed at|approved by chairman/i)).toBeNull();
    expect(screen.getByText("agentos/decisions/DEC-CURRENT.md")).toBeTruthy();
  });

  it("clears held data on same-render permission loss and requires a new read after regrant", async () => {
    let allowed = true;
    const read = vi.fn(async () => document()), epoch = () => 3, permission = () => allowed;
    const props = { selection: work, read, sourceGeneration: epoch, canRead: permission, onChangeDirection: vi.fn() };
    const view = render(<AcceptedDirectionPanel {...props} />);
    fireEvent.click(screen.getByRole("button", { name: "Read Direction" }));
    await screen.findByRole("article", { name: "Current accepted Direction" });
    allowed = false; view.rerender(<AcceptedDirectionPanel {...props} />);
    expect(screen.queryByRole("article", { name: "Current accepted Direction" })).toBeNull();
    allowed = true; view.rerender(<AcceptedDirectionPanel {...props} />);
    expect(screen.queryByRole("article", { name: "Current accepted Direction" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Read Direction" }));
    await screen.findByRole("article", { name: "Current accepted Direction" });
    expect(read).toHaveBeenCalledTimes(2);
  });

  it("aborts a stale request on selection and source-generation changes", async () => {
    let resolve!: (value: AcceptedDirectionRead) => void;
    const read = vi.fn((request: { signal: AbortSignal }) => new Promise<AcceptedDirectionRead>(done => { resolve = done; expect(request.signal.aborted).toBe(false); }));
    let epoch = 4; const generation = () => epoch, permission = () => true;
    const props = { selection: work, read, sourceGeneration: generation, canRead: permission, onChangeDirection: vi.fn() };
    const view = render(<AcceptedDirectionPanel {...props} />);
    fireEvent.click(screen.getByRole("button", { name: "Read Direction" }));
    epoch = 5; view.rerender(<AcceptedDirectionPanel {...props} selection={{ work_ref: "WS:OTHER" }} />);
    expect(read.mock.calls[0][0].signal.aborted).toBe(true);
    await act(async () => resolve(document()));
    expect(screen.queryByRole("article", { name: "Current accepted Direction" })).toBeNull();
  });

  it("shows source absence in Chinese and never substitutes an authored objective", async () => {
    const value = { schema: "mastermind.workspace_project_direction.v1", selection: work, availability: "UNAVAILABLE", source: null, direction: null, reason_codes: ["NOT_DECLARED"] };
    render(<AcceptedDirectionPanel selection={work} read={async () => decodeAcceptedDirection(value, work)} sourceGeneration={() => 1} canRead={() => true} onChangeDirection={() => {}} locale="zh-CN" />);
    fireEvent.click(screen.getByRole("button", { name: "读取方向" }));
    await screen.findByText("此项目尚未声明已接受的方向。");
    expect(screen.queryByText(/Complete the original|项目目标/)).toBeNull();
    expect(screen.getByRole("button", { name: "在对话中更改方向" })).toBeTruthy();
  });

  it("makes failed reads retryable without keeping prior accepted content", async () => {
    const read = vi.fn().mockResolvedValueOnce(document()).mockRejectedValueOnce(new Error("private diagnostic"));
    render(<AcceptedDirectionPanel selection={work} read={read} sourceGeneration={() => 1} canRead={() => true} onChangeDirection={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: "Read Direction" }));
    await screen.findByRole("article", { name: "Current accepted Direction" });
    fireEvent.click(screen.getByRole("button", { name: "Read Direction" }));
    await waitFor(() => expect(screen.getByText("Direction could not be read. Read again to retry.")).toBeTruthy());
    expect(screen.queryByRole("article", { name: "Current accepted Direction" })).toBeNull();
    expect(screen.queryByText("private diagnostic")).toBeNull();
  });

  it("checks live permission again before reading or navigating", () => {
    let allowed = true;
    const read = vi.fn(async () => document()), navigate = vi.fn();
    render(<AcceptedDirectionPanel selection={work} read={read} sourceGeneration={() => 1} canRead={() => allowed} onChangeDirection={navigate} />);
    allowed = false;
    fireEvent.click(screen.getByRole("button", { name: "Read Direction" }));
    fireEvent.click(screen.getByRole("button", { name: "Change direction in conversation" }));
    expect(read).not.toHaveBeenCalled(); expect(navigate).not.toHaveBeenCalled();
  });
});

it("does not offer an enabled conversation action without an actual navigation owner",()=>{
  render(<AcceptedDirectionPanel selection={work} read={async()=>document()} sourceGeneration={()=>1} canRead={()=>true}/>);
  expect(screen.queryByRole("button",{name:"Change direction in conversation"})).toBeNull();
  expect(screen.getByText("This project's current conversation is not connected here.")).toBeTruthy();
});
