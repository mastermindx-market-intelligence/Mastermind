// @vitest-environment jsdom
import { useRef, useState } from "react";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ConversationWindow } from "./ConversationWindow";
import { ResultSourceReader } from "./ResultSourceReader";
import { appendDraftSource, emptyDrafts, readDraft, readDraftInsertion, readDraftRevision, undoDraftSource, writeDraft } from "./drafts";
import { decodeMissionv3 } from "../mission";
import { decodeWindow } from "../workspace-contract";
import { decodeResultEnvelope, type ResultSelection } from "../result";
import type { MissionResultRead } from "../host";
import { projectOffice, type OfficeInput, type OfficeProjection, type ProjectionContext } from "../meta-ceo/projection";
import windowFixture from "../fixtures/window-mission-association-producer.json";
import resultFixture from "../fixtures/result-design-available-reject-unicode.json";

afterEach(cleanup);
async function fixture() {
  const context: ProjectionContext = { authGeneration: 3,
    selection: { workRef: windowFixture.selection.work_ref, rootJobId: windowFixture.selection.root_job_id },
    sessionRef: null, bindingGeneration: null,
    revisions: { mission: "m1", programs: null, result: null, conversation: "w1" } };
  const window = await decodeWindow(structuredClone(windowFixture.window));
  if (!window || window.schema !== "mastermind.workspace.window_read_candidate.v2") throw new Error("V2 required");
  const result = structuredClone(resultFixture);
  const binding = window.observation_binding;
  result.selection = { ...result.selection, work_ref: context.selection!.workRef,
    root_job_id: context.selection!.rootJobId, job_id: binding.job_id, attempt_id: binding.attempt_id };
  result.source_observation.selection = { ...result.selection };
  result.result.selection = { ...result.result.selection, root_job_id: context.selection!.rootJobId,
    job_id: binding.job_id, attempt_id: binding.attempt_id };
  const selection: ResultSelection = { workRef: result.selection.work_ref, rootJobId: result.selection.root_job_id,
    jobId: result.selection.job_id, attemptId: result.selection.attempt_id, resultEnvelopeDigest: result.selection.result_envelope_digest };
  expect(decodeResultEnvelope(result, selection)).not.toBeNull();
  const mission = decodeMissionv3(structuredClone(windowFixture.mission), context.selection!)!;
  mission.result_refs.refs = [{ ...result.result.selection, orchestration_role: "review", validation: "UNVALIDATED" }];
  mission.result_refs.absent_job_ids = [context.selection!.rootJobId];
  mission.source.owner_observation!.control_room = structuredClone(result.source_observation.control_room);
  mission.result_refs.generation = structuredClone(result.result.generation) as typeof mission.result_refs.generation;
  const source = { owner: "EXECUTIVE_OS", ref: "private:mission", revision: "m1", observed_at: "2026-10-04T08:00:00Z", state: "CURRENT" as const, coverage: "COMPLETE" };
  const reads: OfficeInput = { programs: null, result: null,
    mission: { context, source, value: mission },
    conversation: { context, source: { ...source, owner: "CURRENT_WINDOW", ref: "private:window", revision: "w1", coverage: "OBSERVED_WINDOW" }, value: window } };
  return { result, selection, context, reads, projection: projectOffice(reads, context) };
}
function Harness({ projection, readResult, locale = "en" }: { projection: OfficeProjection; readResult: MissionResultRead; locale?: "en" | "zh-CN" }) {
  const [drafts, setDrafts] = useState(() => emptyDrafts(projection.context.authGeneration));
  const latest = useRef(drafts); latest.current = drafts;
  const context = projection.context;
  const publish = (next: typeof drafts) => {
    if (next === latest.current) return false;
    latest.current = next; setDrafts(next); return true;
  };
  return <ConversationWindow projection={projection} readResult={readResult} locale={locale}
    draft={readDraft(drafts, context)} draftRevision={readDraftRevision(drafts, context)} draftInsertion={readDraftInsertion(drafts, context)}
    onDraftChange={text => publish(writeDraft(latest.current, context, text))}
    onAppendSource={(source, revision) => publish(appendDraftSource(latest.current, context, revision, source))}
    onUndoSource={(identity, revision) => publish(undoDraftSource(latest.current, context, revision, identity))} />;
}
async function openReader() {
  fireEvent.click(screen.getByRole("button", { name: "Review evidence" }));
  fireEvent.click(screen.getByRole("button", { name: "Read exact result source" }));
  await screen.findByRole("button", { name: "Add result summary to draft" });
}

describe("DeepSeek-derived formatted preview in the existing source reader", () => {
  it("keeps formatting separate from exact evidence insertion and reads only once", async () => {
    const f = await fixture();
    const read = vi.fn().mockResolvedValue(f.result);
    const { container } = render(<Harness projection={f.projection} readResult={read} />);
    await openReader();
    const original = f.result.result.content.summary;
    expect(container.querySelector(".conversation-source-excerpt")?.textContent).toBe(original);
    fireEvent.click(screen.getByRole("button", { name: "Formatted preview" }));
    await waitFor(() => expect(container.querySelector(".source-markdown")).not.toBeNull());
    expect(container.querySelector(".conversation-source-excerpt")).toBeNull();
    expect(container.querySelector(".source-markdown")?.querySelectorAll("a,img,iframe")).toHaveLength(0);
    fireEvent.click(screen.getByRole("button", { name: "Add result summary to draft" }));
    expect(screen.getByRole<HTMLTextAreaElement>("textbox").value).toContain(original);
    expect(screen.getByRole<HTMLTextAreaElement>("textbox").value).toContain("Source: Executive review result");
    fireEvent.click(screen.getByRole("button", { name: "View exact source" }));
    expect(container.querySelector(".conversation-source-excerpt")?.textContent).toBe(original);
    expect(read).toHaveBeenCalledTimes(1);
  });
});

describe("exact result source to original unsent draft", () => {
  it("localizes the reader without rereading or changing the original source insertion", async () => {
    const f = await fixture(); const read = vi.fn().mockResolvedValue(f.result);
    const { rerender } = render(<Harness projection={f.projection} readResult={read} locale="zh-CN" />);
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "保留我的问题。 Original question." } });
    fireEvent.click(screen.getByRole("button", { name: "审阅证据" }));
    fireEvent.click(screen.getByRole("button", { name: "阅读精确结果来源" }));
    const add = await screen.findByRole("button", { name: "将结果摘要添加到草稿" });
    const region = screen.getByRole("region", { name: "结果来源阅读器" });
    expect(document.activeElement).toBe(region);
    expect(screen.getByText("完整来源详情")).toBeTruthy();
    expect(region.querySelector("blockquote")?.textContent).toBe(f.result.result.content.summary);
    fireEvent.click(add);
    const inserted = screen.getByRole<HTMLTextAreaElement>("textbox").value;
    expect(inserted).toContain(`保留我的问题。 Original question.\n\n“${f.result.result.content.summary}”\nSource: Executive review result`);
    expect(screen.getByRole("status").textContent).toBe("已添加到草稿 · 未发送");
    rerender(<Harness projection={f.projection} readResult={read} locale="en" />);
    expect(screen.getByRole("region", { name: "Result source reader" })).toBe(region);
    expect(screen.getByRole("status").textContent).toBe("Added to draft · Not sent");
    expect(screen.getByRole<HTMLTextAreaElement>("textbox").value).toBe(inserted);
    rerender(<Harness projection={f.projection} readResult={read} locale="zh-CN" />);
    fireEvent.click(screen.getByRole("button", { name: "撤销来源插入" }));
    expect(screen.getByRole<HTMLTextAreaElement>("textbox").value).toBe("保留我的问题。 Original question.");
    expect(screen.getByRole("status").textContent).toBe("已移除插入的来源，原草稿已保留。");
    expect(read).toHaveBeenCalledExactlyOnceWith({ ...f.selection, signal: expect.any(AbortSignal) });
    expect(read.mock.calls[0][0].signal.aborted).toBe(false);
    fireEvent.click(screen.getByRole("button", { name: "返回证据" }));
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "阅读精确结果来源" }));
  });
  it("localizes unavailable content without exposing a malformed result", async () => {
    const f = await fixture(); const read = vi.fn().mockResolvedValue({ ...f.result, unexpected: true });
    render(<Harness projection={f.projection} readResult={read} locale="zh-CN" />);
    fireEvent.click(screen.getByRole("button", { name: "审阅证据" }));
    fireEvent.click(screen.getByRole("button", { name: "阅读精确结果来源" }));
    await screen.findByText("结果内容不可用，无法添加摘录。");
    expect(document.querySelector("blockquote")).toBeNull();
    expect(screen.queryByRole("button", { name: "将结果摘要添加到草稿" })).toBeNull();
    expect(screen.getByRole("button", { name: "重新核对精确结果" })).toBeTruthy();
    expect(read).toHaveBeenCalledTimes(1);
  });
  it("does not offer a result from another root even in a contradictory projection", async () => {
    const f = await fixture(); const read = vi.fn().mockResolvedValue(f.result);
    const projection = structuredClone(f.projection);
    if (projection.mission.value?.schema !== "mastermind.mission_workspace.v3") throw new Error("V3 required");
    projection.mission.value.result_refs.refs[0].root_job_id = "JOB-999";
    render(<Harness projection={projection} readResult={read} />);
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "Keep the original draft" } });
    fireEvent.click(screen.getByRole("button", { name: "Review evidence" }));
    const source = screen.getByRole<HTMLButtonElement>("button", { name: "Read exact result source" });
    expect(source.disabled).toBe(true);
    fireEvent.click(source);
    expect(read).not.toHaveBeenCalled();
    expect(screen.queryByRole("region", { name: "Result source reader" })).toBeNull();
    expect(screen.getByRole<HTMLTextAreaElement>("textbox").value).toBe("Keep the original draft");
  });
  it("performs one fixed exact read, inserts once, undoes only the insertion, and restores nested focus", async () => {
    const f = await fixture(); const read = vi.fn().mockResolvedValue(f.result);
    render(<Harness projection={f.projection} readResult={read} />);
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "Keep my original question.\n第二行" } });
    await openReader();
    expect(read).toHaveBeenCalledTimes(1);
    expect(read.mock.calls[0][0]).toEqual({ ...f.selection, signal: expect.any(AbortSignal) });
    expect(document.activeElement).toBe(screen.getByRole("region", { name: "Result source reader" }));
    expect(screen.getByRole<HTMLTextAreaElement>("textbox").value).toBe("Keep my original question.\n第二行");
    const add = screen.getByRole("button", { name: "Add result summary to draft" });
    fireEvent.click(add); fireEvent.click(add);
    const inserted = screen.getByRole<HTMLTextAreaElement>("textbox").value;
    expect(inserted).toContain(`Keep my original question.\n第二行\n\n“${f.result.result.content.summary}”\nSource: Executive review result`);
    expect(inserted.split("Source: Executive review result")).toHaveLength(2);
    expect(screen.getByText("Added to draft · Not sent")).toBeTruthy();
    expect(screen.getByRole<HTMLButtonElement>("button", { name: "Send message" }).disabled).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Undo source insertion" }));
    expect(screen.getByRole<HTMLTextAreaElement>("textbox").value).toBe("Keep my original question.\n第二行");
    fireEvent.click(screen.getByRole("button", { name: "Back to evidence" }));
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Read exact result source" }));
    fireEvent.click(screen.getByRole("button", { name: "Close evidence" }));
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Review evidence" }));
  });
  it("withholds Undo after newer typing, even if text is edited back", async () => {
    const f = await fixture(); render(<Harness projection={f.projection} readResult={async () => f.result} />);
    await openReader(); fireEvent.click(screen.getByRole("button", { name: "Add result summary to draft" }));
    const textarea = screen.getByRole<HTMLTextAreaElement>("textbox"); const inserted = textarea.value;
    fireEvent.change(textarea, { target: { value: "New text" } });
    fireEvent.change(textarea, { target: { value: inserted } });
    expect(screen.queryByRole("button", { name: "Undo source insertion" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Edit draft" }));
    expect(document.activeElement).toBe(textarea); expect(textarea.value).toBe(inserted);
  });
  it("requires renewed review if the original draft changed while reading", async () => {
    const f = await fixture(); render(<Harness projection={f.projection} readResult={async () => f.result} />);
    await openReader(); fireEvent.change(screen.getByRole("textbox"), { target: { value: "Typing after opening" } });
    expect(screen.getByRole<HTMLButtonElement>("button", { name: "Add result summary to draft" }).disabled).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Back to evidence" }));
    fireEvent.click(screen.getByRole("button", { name: "Read exact result source" }));
    const add = await screen.findByRole<HTMLButtonElement>("button", { name: "Add result summary to draft" });
    expect(add.disabled).toBe(false); fireEvent.click(add);
    expect(screen.getByRole<HTMLTextAreaElement>("textbox").value.startsWith("Typing after opening\n\n")).toBe(true);
  });
  it.each(["wrong tuple", "malformed", "owner conflict", "over budget"])("does not expose or insert %s content", async failure => {
    const f = await fixture(); const value = structuredClone(f.result);
    if (failure === "wrong tuple") value.selection.job_id = "JOB-999";
    if (failure === "malformed") Object.assign(value, { unexpected: true });
    if (failure === "owner conflict") value.source_observation.control_room.document_digest = "b".repeat(64);
    if (failure === "over budget") value.result.content.summary = "x".repeat(20_000);
    render(<Harness projection={f.projection} readResult={async () => value} />);
    fireEvent.click(screen.getByRole("button", { name: "Review evidence" }));
    fireEvent.click(screen.getByRole("button", { name: "Read exact result source" }));
    await screen.findByText("Result content is unavailable. No excerpt can be added.");
    expect(screen.queryByRole("button", { name: "Add result summary to draft" })).toBeNull();
    expect(document.body.textContent).not.toContain(value.result.content.summary);
  });
  it("clears content during recheck and on failure without deleting inserted user draft", async () => {
    const f = await fixture(); let reject!: (error: Error) => void;
    const read = vi.fn().mockResolvedValueOnce(f.result).mockImplementationOnce(() => new Promise((_, no) => { reject = no; }));
    render(<Harness projection={f.projection} readResult={read} />);
    await openReader(); fireEvent.click(screen.getByRole("button", { name: "Add result summary to draft" }));
    const draft = screen.getByRole<HTMLTextAreaElement>("textbox").value;
    const recheck = screen.getByRole("button", { name: "Recheck exact result" });
    fireEvent.click(recheck); fireEvent.click(recheck);
    expect(read).toHaveBeenCalledTimes(2);
    expect(screen.queryByRole("button", { name: "Undo source insertion" })).toBeNull();
    expect(screen.queryByText("Exact summary excerpt")).toBeNull();
    await act(async () => reject(new Error("unavailable")));
    expect(screen.getByText("Result content is unavailable. No excerpt can be added.")).toBeTruthy();
    expect(screen.getByRole<HTMLTextAreaElement>("textbox").value).toBe(draft);
  });
  it.each(["auth", "target", "source", "permission"])("cancels an obsolete read at the %s boundary", async boundary => {
    const f = await fixture(); let resolve!: (value: unknown) => void;
    const read = vi.fn().mockImplementation(() => new Promise(yes => { resolve = yes; }));
    const { rerender } = render(<Harness projection={f.projection} readResult={read} />);
    fireEvent.click(screen.getByRole("button", { name: "Review evidence" }));
    fireEvent.click(screen.getByRole("button", { name: "Read exact result source" }));
    const context = structuredClone(f.context), reads = structuredClone(f.reads);
    if (boundary === "auth") context.authGeneration++;
    if (boundary === "target") context.selection!.rootJobId = "JOB-999";
    if (boundary === "source") context.revisions.mission = "m2";
    if (boundary === "permission") reads.conversation!.source.state = "WITHHELD";
    rerender(<Harness projection={projectOffice(reads, context)} readResult={read} />);
    expect(read.mock.calls[0][0].signal.aborted).toBe(true);
    await act(async () => resolve(f.result));
    expect(screen.queryByRole("region", { name: "Result source reader" })).toBeNull();
    expect(document.body.textContent).not.toContain(f.result.result.content.summary);
  });
  it("does not close on IME Escape and provides reading without composition capability", async () => {
    const f = await fixture(); const close = vi.fn(), append = vi.fn();
    render(<ResultSourceReader projection={f.projection} selection={f.selection} readResult={async () => f.result}
      draftRevision={0} draftInsertion={null} appendAvailable={false} onAppend={append} onUndo={() => false} onClose={close} onEditDraft={() => {}} />);
    const add = await screen.findByRole<HTMLButtonElement>("button", { name: "Add result summary to draft" });
    expect(add.disabled).toBe(true); fireEvent.click(add); expect(append).not.toHaveBeenCalled();
    fireEvent.keyDown(screen.getByRole("region"), { key: "Escape", isComposing: true });
    expect(close).not.toHaveBeenCalled();
    fireEvent.keyDown(screen.getByRole("region"), { key: "Escape" }); expect(close).toHaveBeenCalledOnce();
  });
  it("refuses a sibling selector before issuing any source read", async () => {
    const f = await fixture(); const read = vi.fn().mockResolvedValue(f.result);
    render(<ResultSourceReader projection={f.projection} selection={{ ...f.selection, jobId: "JOB-999" }} readResult={read}
      draftRevision={0} draftInsertion={null} appendAvailable={false} onAppend={() => false} onUndo={() => false} onClose={() => {}} onEditDraft={() => {}} />);
    await screen.findByText("Result content is unavailable. No excerpt can be added.");
    expect(read).not.toHaveBeenCalled();
  });
});
