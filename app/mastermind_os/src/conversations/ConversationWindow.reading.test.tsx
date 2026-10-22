// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ConversationWindow } from "./ConversationWindow";
import { decodeMissionv3 } from "../mission";
import { decodeWindow, type WindowDocumentV2 } from "../workspace-contract";
import { projectOffice, type OfficeInput, type ProjectionContext } from "../meta-ceo/projection";
import fixture from "../fixtures/window-mission-association-producer.json";

afterEach(cleanup);
async function setup() {
  const context: ProjectionContext = { authGeneration: 3,
    selection: { workRef: fixture.selection.work_ref, rootJobId: fixture.selection.root_job_id },
    sessionRef: null, bindingGeneration: null,
    revisions: { mission: "m1", programs: null, result: null, conversation: "w1" } };
  const window = await decodeWindow(structuredClone(fixture.window));
  if (!window || window.schema !== "mastermind.workspace.window_read_candidate.v2") throw new Error("fixture V2 required");
  const source = { owner: "EXECUTIVE_OS", ref: "private:mission", revision: "m1", observed_at: "2026-10-04T08:00:00Z", state: "CURRENT" as const, coverage: "COMPLETE" };
  const reads: OfficeInput = { programs: null, result: null,
    mission: { context, source, value: decodeMissionv3(structuredClone(fixture.mission), context.selection!) },
    conversation: { context, source: { ...source, owner: "CURRENT_WINDOW", ref: "private:window", revision: "w1", coverage: "OBSERVED_WINDOW" }, value: window } };
  return { reads, context, window };
}

describe("actual ConversationWindow reader composition", () => {
  it("searching the real window never edits notes or invokes the result reader", async () => {
    const f = await setup(); const onDraftChange = vi.fn(), readResult = vi.fn();
    render(<ConversationWindow projection={projectOffice(f.reads, f.context)} draft="Keep original notes" onDraftChange={onDraftChange} readResult={readResult} />);
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "not in this window" } });
    expect(screen.getByRole<HTMLTextAreaElement>("textbox").value).toBe("Keep original notes");
    expect(onDraftChange).not.toHaveBeenCalled(); expect(readResult).not.toHaveBeenCalled();
    expect(screen.getByText("No visible responses match this search.")).toBeTruthy();
  });
  it("resets search when the canonical window epoch changes but keeps notes", async () => {
    const f = await setup();
    const props = { draft: "Retained notes", onDraftChange: vi.fn() };
    const view = render(<ConversationWindow {...props} projection={projectOffice(f.reads, f.context)} />);
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "old query" } });
    f.window.view.epoch = "c".repeat(64);
    view.rerender(<ConversationWindow {...props} projection={projectOffice(f.reads, f.context)} />);
    expect(screen.getByRole<HTMLInputElement>("searchbox").value).toBe("");
    expect(screen.getByRole<HTMLTextAreaElement>("textbox").value).toBe("Retained notes");
  });
  it("preserves search on passive observation refresh with unchanged source binding", async () => {
    const f = await setup(); const props = { draft: "notes", onDraftChange: vi.fn() };
    const view = render(<ConversationWindow {...props} projection={projectOffice(f.reads, f.context)} />);
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "plan" } });
    f.context.revisions.conversation = "w2";
    f.reads.conversation!.source.revision = "w2";
    view.rerender(<ConversationWindow {...props} projection={projectOffice(f.reads, f.context)} />);
    expect(screen.getByRole<HTMLInputElement>("searchbox").value).toBe("plan");
  });
  it.each(["WITHHELD", "UNAVAILABLE", "UNKNOWN"] as const)("withdraws the reader when current source is %s", async state => {
    const f = await setup(); const props = { draft: "", onDraftChange: vi.fn() };
    const view = render(<ConversationWindow {...props} projection={projectOffice(f.reads, f.context)} />);
    expect(screen.getByRole("searchbox")).toBeTruthy();
    f.reads.conversation!.source.state = state;
    view.rerender(<ConversationWindow {...props} projection={projectOffice(f.reads, f.context)} />);
    expect(screen.queryByRole("searchbox")).toBeNull();
    expect(screen.queryByText("plan child visible")).toBeNull();
  });
  it("does not render foreign Job/Attempt text even if the supplied window has visible items", async () => {
    const f = await setup();
    (f.reads.conversation!.value as WindowDocumentV2).observation_binding.attempt_id = "ATT-" + "a".repeat(32);
    render(<ConversationWindow projection={projectOffice(f.reads, f.context)} draft="" onDraftChange={vi.fn()} />);
    expect(screen.queryByRole("searchbox")).toBeNull();
    expect(screen.queryByText("plan child visible")).toBeNull();
  });
  it("keeps qualified send-slot identity outside display-reader lifetime", async () => {
    const f = await setup(); const continuation = <button>Separate qualified continuation</button>;
    const props = { draft: "", onDraftChange: vi.fn(), continuation };
    const view = render(<ConversationWindow {...props} projection={projectOffice(f.reads, f.context)} />);
    const button = screen.getByRole("button", { name: "Separate qualified continuation" });
    f.window.view.epoch = "b".repeat(64);
    view.rerender(<ConversationWindow {...props} projection={projectOffice(f.reads, f.context)} />);
    expect(screen.getByRole("button", { name: "Separate qualified continuation" })).toBe(button);
  });
});
