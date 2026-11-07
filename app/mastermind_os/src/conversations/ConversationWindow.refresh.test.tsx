// @vitest-environment jsdom
import { useState } from "react";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ConversationWindow } from "./ConversationWindow";
import { decodeMissionv3 } from "../mission";
import { decodeWindow } from "../workspace-contract";
import { projectOffice, type OfficeInput, type OfficeProjection, type ProjectionContext } from "../meta-ceo/projection";
import fixture from "../fixtures/window-mission-association-producer.json";

afterEach(cleanup);
async function input() {
  const context: ProjectionContext = { authGeneration: 3,
    selection: { workRef: fixture.selection.work_ref, rootJobId: fixture.selection.root_job_id },
    sessionRef: null, bindingGeneration: null,
    revisions: { mission: "m1", programs: null, result: null, conversation: "w1" } };
  const source = { owner: "EXECUTIVE_OS", ref: "private:mission", revision: "m1", observed_at: "2026-10-04T08:00:00Z", state: "CURRENT" as const, coverage: "COMPLETE" };
  const reads: OfficeInput = { programs: null, result: null,
    mission: { context, source, value: decodeMissionv3(structuredClone(fixture.mission), context.selection!) },
    conversation: { context, source: { ...source, owner: "CURRENT_WINDOW", ref: "private:window", revision: "w1", coverage: "OBSERVED_WINDOW" }, value: await decodeWindow(structuredClone(fixture.window)) } };
  return { reads, context, projection: projectOffice(reads, context) };
}
function Harness({ projection }: { projection: OfficeProjection }) {
  const [draft, setDraft] = useState("Original notes. 继续\nSecond line.");
  return <ConversationWindow projection={projection} draft={draft} onDraftChange={setDraft} notesPresentation="collapsed" />;
}

describe("unsent notes during observation refresh", () => {
  it.each(["conversation", "mission", "result"] as const)("keeps the actual focused textarea and caret across a passive %s revision", async revision => {
    const { context, reads, projection } = await input();
    const { rerender } = render(<Harness projection={projection} />);
    fireEvent.click(screen.getByRole("button", { name: "Unsent notes" }));
    const notes = screen.getByRole<HTMLTextAreaElement>("textbox", { name: "Unsent notes" });
    notes.focus(); notes.setSelectionRange(3, 8, "backward"); notes.scrollTop = 17;
    const next = structuredClone(context); next.revisions[revision] = "next";
    const nextReads = structuredClone(reads);
    for (const name of ["conversation", "mission"] as const) {
      nextReads[name]!.context = next;
      if (name === revision) nextReads[name]!.source.revision = "next";
    }
    rerender(<Harness projection={projectOffice(nextReads, next)} />);
    expect(screen.getByRole("textbox", { name: "Unsent notes" })).toBe(notes);
    expect(document.activeElement).toBe(notes);
    expect([notes.selectionStart, notes.selectionEnd, notes.selectionDirection, notes.scrollTop]).toEqual([3, 8, "backward", 17]);
    expect(notes.value).toBe("Original notes. 继续\nSecond line.");
  });
  it("preserves open notes through clear and reacquisition while withdrawing inspected evidence", async () => {
    const { context, projection } = await input();
    const { rerender } = render(<Harness projection={projection} />);
    fireEvent.click(screen.getByRole("button", { name: "Unsent notes" }));
    const notes = screen.getByRole("textbox", { name: "Unsent notes" });
    fireEvent.click(screen.getByRole("button", { name: "Review evidence" }));
    expect(screen.getByRole("region", { name: "Conversation evidence" })).toBeTruthy();
    const clearedContext = { ...context, revisions: { conversation: null, mission: null, programs: null, result: null } };
    rerender(<Harness projection={projectOffice({ mission: null, conversation: null, result: null, programs: null }, clearedContext)} />);
    expect(screen.getByRole("textbox", { name: "Unsent notes" })).toBe(notes);
    expect(screen.queryByRole("region", { name: "Conversation evidence" })).toBeNull();
    rerender(<Harness projection={projection} />);
    expect(screen.getByRole("textbox", { name: "Unsent notes" })).toBe(notes);
    expect(screen.queryByRole("region", { name: "Conversation evidence" })).toBeNull();
  });
  it.each(["auth", "target", "session", "binding", "permission"])("resets notes on the %s boundary and does not resurrect them on return", async boundary => {
    const { context, projection, reads } = await input();
    const { rerender } = render(<Harness projection={projection} />);
    fireEvent.click(screen.getByRole("button", { name: "Unsent notes" }));
    const notes = screen.getByRole("textbox", { name: "Unsent notes" }); notes.focus();
    const next = structuredClone(context);
    if (boundary === "auth") next.authGeneration++;
    if (boundary === "target") next.selection!.rootJobId = "JOB-999";
    if (boundary === "session") next.sessionRef = "another-session";
    if (boundary === "binding") next.bindingGeneration = 2;
    const changed = projectOffice(reads, next);
    if (boundary === "permission") changed.conversation = {
      source: { ...changed.conversation.source, state: "WITHHELD" }, value: null, reason: "CONTENT_PERMISSION_WITHHELD",
    };
    rerender(<Harness projection={changed} />);
    expect(screen.queryByRole("textbox", { name: "Unsent notes" })).toBeNull();
    expect(notes.isConnected).toBe(false);
    rerender(<Harness projection={projection} />);
    expect(screen.queryByRole("textbox", { name: "Unsent notes" })).toBeNull();
  });
  it("aborts a pending source read on revision change and does not revive it on an A-B-A return", async () => {
    const { reads, context } = await input();
    const window = reads.conversation!.value!;
    const mission = reads.mission!.value!;
    if (window.schema !== "mastermind.workspace.window_read_candidate.v2" || mission.schema !== "mastermind.mission_workspace.v3") throw new Error("typed fixtures required");
    mission.result_refs.refs = [{ root_job_id: context.selection!.rootJobId, job_id: window.observation_binding.job_id,
      attempt_id: window.observation_binding.attempt_id, result_envelope_digest: "c".repeat(64), orchestration_role: "work", validation: "UNVALIDATED" }];
    const projection = projectOffice(reads, context);
    let settle!: (value: unknown) => void;
    const read = vi.fn(() => new Promise<unknown>(resolve => { settle = resolve; }));
    const props = { draft: "Unsent original", onDraftChange: vi.fn(), readResult: read, notesPresentation: "collapsed" as const };
    const { rerender } = render(<ConversationWindow {...props} projection={projection} />);
    fireEvent.click(screen.getByRole("button", { name: "Unsent notes" }));
    const notes = screen.getByRole("textbox", { name: "Unsent notes" });
    fireEvent.click(screen.getByRole("button", { name: "Review evidence" }));
    fireEvent.click(screen.getByRole("button", { name: "Read exact result source" }));
    expect(read).toHaveBeenCalledTimes(1);
    const signal = (read.mock.calls[0] as unknown as [{ signal: AbortSignal }])[0].signal;
    expect(signal.aborted).toBe(false);
    const next = structuredClone(context); next.revisions.conversation = "w2";
    rerender(<ConversationWindow {...props} projection={projectOffice(reads, next)} />);
    expect(signal.aborted).toBe(true);
    expect(screen.getByRole("textbox", { name: "Unsent notes" })).toBe(notes);
    rerender(<ConversationWindow {...props} projection={projection} />);
    expect(screen.queryByRole("region", { name: "Result source reader" })).toBeNull();
    expect(screen.queryByRole("region", { name: "Conversation evidence" })).toBeNull();
    await act(async () => { settle(null); });
    expect(read).toHaveBeenCalledTimes(1);
    expect(props.onDraftChange).not.toHaveBeenCalled();
    expect(screen.getByRole("textbox", { name: "Unsent notes" })).toBe(notes);
  });
});
