// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { ProjectExecutionHistory } from "./ProjectExecutionHistory";
import { deferred, executionFixture as fixture, executionHistoryHarness, executionWork as work } from "./project-execution-history.test-support";
const handles: ReturnType<typeof executionHistoryHarness>[] = [];
const setup = () => { const e = executionHistoryHarness(); handles.push(e); return e; };
afterEach(() => { cleanup(); handles.splice(0).forEach(e => e.dispose()); });

it("reads explicitly through the real catalogue factory without cancelling its own authenticated refresh", async () => {
  const e = setup();
  render(<ProjectExecutionHistory workRef={work} owner={e.owner}/>);
  expect(e.historyContext).not.toHaveBeenCalled(); expect(e.references).not.toHaveBeenCalled(); expect(e.read).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Read project runs" }));
  const open = await screen.findByRole("button", { name: "Open run" });
  expect(e.historyContext).toHaveBeenCalledTimes(1); expect(e.references).toHaveBeenCalledTimes(1);
  fireEvent.click(open);
  await screen.findByText(fixture.completed_read.result.envelope.summary);
  expect(e.read).toHaveBeenCalledTimes(1); expect(e.send).not.toHaveBeenCalled(); expect(e.target).not.toHaveBeenCalled();
});

it("focuses the reader heading and restores the current run opener after Escape or Back", async () => {
  const e = setup(); render(<ProjectExecutionHistory workRef={work} owner={e.owner}/>);
  fireEvent.click(screen.getByRole("button", { name: "Read project runs" }));
  fireEvent.click(await screen.findByRole("button", { name: "Open run" }));
  await screen.findByText(fixture.completed_read.result.envelope.summary);
  expect(document.activeElement).toBe(screen.getByRole("heading", { name: "Project team conversation" }));
  fireEvent.keyDown(document, { key: "Escape" });
  expect(document.activeElement).toBe(screen.getByRole("button", { name: "Open run" }));
  fireEvent.click(screen.getByRole("button", { name: "Open run" }));
  await screen.findByText(fixture.completed_read.result.envelope.summary);
  fireEvent.click(screen.getByRole("button", { name: "Back to project runs" }));
  expect(document.activeElement).toBe(screen.getByRole("button", { name: "Open run" }));
});


it.each(["en", "zh-CN"] as const)("shows explicit loading, empty, partial and failure states in %s", async locale => {
  const e = setup(), pending = deferred();
  const label = locale === "en" ? "Read project runs" : "读取项目执行";
  const loading = locale === "en" ? "Reading project work…" : "正在读取项目工作…";
  const empty = locale === "en" ? "No project runs yet. Start work to begin your team conversation." : "尚无项目执行。开始工作即可创建团队对话。";
  const partial = locale === "en" ? "Showing the most recent runs that fit this view." : "显示此视图可容纳的最近执行。";
  const failure = locale === "en" ? "Project work is unavailable. Read again to check its current source." : "项目工作暂不可用。请重新读取当前来源。";
  e.references.mockReturnValueOnce(pending.promise);
  render(<ProjectExecutionHistory workRef={work} owner={e.owner} locale={locale} theme="light"/>);
  const region = screen.getByRole("region", { name: locale === "en" ? "Project team conversation" : "项目团队对话" });
  expect(region.getAttribute("lang")).toBe(locale); expect(region.getAttribute("data-theme")).toBe("light");
  expect(screen.queryByText(empty)).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: label }));
  expect(await screen.findByText(loading)).toBeTruthy();
  await act(async () => { pending.resolve({ ...fixture.catalogue, entries: [], coverage: { state: "PARTIAL", limit: 8, returned: 0 } }); });
  expect(await screen.findByText(empty)).toBeTruthy(); expect(screen.getByText(partial)).toBeTruthy();
  e.references.mockRejectedValueOnce(Error("SOURCE_UNAVAILABLE"));
  fireEvent.click(screen.getByRole("button", { name: label }));
  expect(await screen.findByText(failure)).toBeTruthy(); expect(screen.queryByText(empty)).toBeNull();
  expect((screen.getByRole("button", { name: label }) as HTMLButtonElement).disabled).toBe(false);
});

it("keeps a double click during authenticated refresh to one explicit acquisition", async () => {
  const e = setup(), pending = deferred<Awaited<ReturnType<typeof e.historyContext>>>();
  const createContext = e.historyContext.getMockImplementation()!;
  e.historyContext.mockReturnValueOnce(pending.promise);
  render(<ProjectExecutionHistory workRef={work} owner={e.owner}/>);
  const read = screen.getByRole("button", { name: "Read project runs" });
  act(() => { fireEvent.click(read); fireEvent.click(read); });
  expect(e.historyContext).toHaveBeenCalledTimes(1); expect(e.references).not.toHaveBeenCalled();
  await act(async () => { pending.resolve(await createContext()); });
  await screen.findByRole("button", { name: "Open run" });
  expect(e.references).toHaveBeenCalledTimes(1); expect(e.read).not.toHaveBeenCalled();
});

it("withholds continuation until a pending run returns a verified completed result", async () => {
  const e = setup(); e.state.catalogue = fixture.pending_catalogue; e.state.window = fixture.pending_read;
  const continueProject = vi.fn();
  render(<ProjectExecutionHistory workRef={work} owner={e.owner} onContinue={continueProject}/>);
  fireEvent.click(screen.getByRole("button", { name: "Read project runs" }));
  fireEvent.click(await screen.findByRole("button", { name: "Open run" }));
  await screen.findByText("Follow-up work becomes available after the team returns a verified result.");
  expect(screen.queryByRole("button", { name: "Reply to project team" })).toBeNull();
  expect(continueProject).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Back to project runs" }));
  e.state.window = fixture.completed_read;
  fireEvent.click(screen.getByRole("button", { name: "Open run" }));
  await screen.findByText(fixture.completed_read.result.envelope.summary);
  expect((screen.getByRole("button", { name: "Reply to project team" }) as HTMLButtonElement).disabled).toBe(false);
});

it("prepares one follow-up preview, never sends, and keeps its guard valid only while the exact read is current", async () => {
  const e = setup(), pending = deferred<string>(), continueProject = vi.fn((_witness: unknown, _current: () => boolean) => pending.promise);
  render(<ProjectExecutionHistory workRef={work} owner={e.owner} onContinue={continueProject}/>);
  fireEvent.click(screen.getByRole("button", { name: "Read project runs" }));
  fireEvent.click(await screen.findByRole("button", { name: "Open run" }));
  await screen.findByText(fixture.completed_read.result.envelope.summary);
  const reply = screen.getByRole("button", { name: "Reply to project team" });
  act(() => { fireEvent.click(reply); fireEvent.click(reply); });
  expect(continueProject).toHaveBeenCalledTimes(1);
  expect(continueProject.mock.calls[0]![0]).toEqual(fixture.completed_read.parent_witness);
  const current = continueProject.mock.calls[0]![1]; expect(current()).toBe(true);
  expect(screen.getByText("Preparing your next message…")).toBeTruthy();
  await act(async () => { pending.resolve("Project preview is ready."); });
  expect(screen.getByText("Project preview is ready.")).toBeTruthy(); expect(current()).toBe(true);
  expect(e.send).not.toHaveBeenCalled(); expect(e.target).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Back to project runs" }));
  expect(current()).toBe(false); expect(screen.queryByText("Project preview is ready.")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Open run" }));
  await screen.findByText(fixture.completed_read.result.envelope.summary);
  expect(current()).toBe(false);
});

it("hides stale follow-up completion after Back and permits a new preview before the old one returns", async () => {
  const e = setup(), first = deferred<string>(), second = deferred<string>();
  const continueProject = vi.fn((_witness: unknown, _current: () => boolean) => first.promise)
    .mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise);
  render(<ProjectExecutionHistory workRef={work} owner={e.owner} onContinue={continueProject}/>);
  fireEvent.click(screen.getByRole("button", { name: "Read project runs" }));
  fireEvent.click(await screen.findByRole("button", { name: "Open run" }));
  await screen.findByText(fixture.completed_read.result.envelope.summary);
  fireEvent.click(screen.getByRole("button", { name: "Reply to project team" }));
  const oldCurrent = continueProject.mock.calls[0]![1];
  fireEvent.keyDown(document, { key: "Escape" });
  expect(oldCurrent()).toBe(false);
  fireEvent.click(screen.getByRole("button", { name: "Open run" }));
  await screen.findByText(fixture.completed_read.result.envelope.summary);
  fireEvent.click(screen.getByRole("button", { name: "Reply to project team" }));
  expect(continueProject).toHaveBeenCalledTimes(2);
  await act(async () => { first.resolve("OLD_PREVIEW_MUST_STAY_HIDDEN"); });
  expect(screen.queryByText("OLD_PREVIEW_MUST_STAY_HIDDEN")).toBeNull();
  expect(screen.getByText("Preparing your next message…")).toBeTruthy();
  expect(continueProject.mock.calls[1]![1]()).toBe(true);
  await act(async () => { second.resolve("Current preview is ready."); });
  expect(screen.getByText("Current preview is ready.")).toBeTruthy();
});

it("aborts and hides a late read result when authenticated identity changes", async () => {
  const e = setup(), pending = deferred(); e.read.mockReturnValueOnce(pending.promise);
  render(<ProjectExecutionHistory workRef={work} owner={e.owner}/>);
  fireEvent.click(screen.getByRole("button", { name: "Read project runs" }));
  fireEvent.click(await screen.findByRole("button", { name: "Open run" }));
  await waitFor(() => expect(e.read).toHaveBeenCalledTimes(1));
  const readSignal = e.request.mock.calls.at(-1)![2];
  act(() => { e.state.auth++; e.notify(); });
  expect(readSignal.aborted).toBe(true);
  await act(async () => { pending.resolve(fixture.completed_read); });
  expect(screen.queryByText(fixture.completed_read.result.envelope.summary)).toBeNull();
  expect(screen.queryByRole("button", { name: "Reply to project team" })).toBeNull();
  expect((screen.getByRole("button", { name: "Read project runs" }) as HTMLButtonElement).disabled).toBe(false);
});

it("hides stale selected results and invalidates continuation after source refresh or project reselection", async () => {
  const e = setup(), continueProject = vi.fn((_witness: unknown, _current: () => boolean) => "Preview prepared.");
  const view = render(<ProjectExecutionHistory workRef={work} owner={e.owner} onContinue={continueProject}/>);
  fireEvent.click(screen.getByRole("button", { name: "Read project runs" }));
  fireEvent.click(await screen.findByRole("button", { name: "Open run" }));
  await screen.findByText(fixture.completed_read.result.envelope.summary);
  fireEvent.click(screen.getByRole("button", { name: "Reply to project team" }));
  await screen.findByText("Preview prepared.");
  const current = continueProject.mock.calls[0]![1];
  await act(async () => { await e.owner.refresh(); });
  expect(current()).toBe(false);
  expect(screen.queryByText(fixture.completed_read.result.envelope.summary)).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Read project runs" }));
  fireEvent.click(await screen.findByRole("button", { name: "Open run" }));
  await screen.findByText(fixture.completed_read.result.envelope.summary);
  act(() => { e.state.workRef = "WS:FOREIGN"; e.state.selection = "selection-2"; });
  view.rerender(<ProjectExecutionHistory workRef="WS:FOREIGN" owner={e.owner} onContinue={continueProject}/>);
  expect(screen.queryByText(fixture.completed_read.result.envelope.summary)).toBeNull();
  act(() => { e.state.workRef = work; e.state.selection = "selection-3"; });
  view.rerender(<ProjectExecutionHistory workRef={work} owner={e.owner} onContinue={continueProject}/>);
  expect(screen.queryByText(fixture.completed_read.result.envelope.summary)).toBeNull();
  expect(e.read).toHaveBeenCalledTimes(2); expect(e.send).not.toHaveBeenCalled();
});

it("disables explicit reads when no authenticated read owner is available", () => {
  render(<ProjectExecutionHistory workRef={work}/>);
  expect((screen.getByRole("button", { name: "Read project runs" }) as HTMLButtonElement).disabled).toBe(true);
  expect(screen.queryByRole("button", { name: "Open run" })).toBeNull();
});

it("handles Escape at the reader focus handoff and cleans up after return or unmount", async () => {
  const e = setup();
  const view = render(<ProjectExecutionHistory workRef={work} owner={e.owner}/>);
  const gestures: { unrelatedPrevented: boolean; readerRetained: boolean; escapePrevented: boolean }[] = [];
  let escapeOnFocus = true;
  const onFocus = (event: FocusEvent) => {
    if (!escapeOnFocus || event.target !== screen.queryByRole("heading", { name: "Project team conversation" }) ||
        !screen.queryByRole("button", { name: "Back to project runs" })) return;
    const unrelated = new KeyboardEvent("keydown", { key: "x", bubbles: true, cancelable: true });
    document.dispatchEvent(unrelated);
    const readerRetained = !!screen.queryByRole("button", { name: "Back to project runs" });
    const escape = new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true });
    document.dispatchEvent(escape);
    gestures.push({ unrelatedPrevented: unrelated.defaultPrevented, readerRetained, escapePrevented: escape.defaultPrevented });
  };
  document.addEventListener("focusin", onFocus);
  try {
    fireEvent.click(screen.getByRole("button", { name: "Read project runs" }));
    await screen.findByRole("button", { name: "Open run" });
    for (const reads of [1, 2]) {
      await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Open run" })); });
      expect(gestures).toHaveLength(reads);
      expect(gestures[reads - 1]).toEqual({ unrelatedPrevented: false, readerRetained: true, escapePrevented: true });
      expect(screen.queryByRole("button", { name: "Back to project runs" })).toBeNull();
      expect(document.activeElement).toBe(screen.getByRole("button", { name: "Open run" }));
      expect(e.references).toHaveBeenCalledTimes(1); expect(e.read).toHaveBeenCalledTimes(reads);
      const afterReturn = new KeyboardEvent("keydown", { key: "Escape", cancelable: true });
      document.dispatchEvent(afterReturn);
      expect(afterReturn.defaultPrevented).toBe(false);
    }
    escapeOnFocus = false;
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Open run" })); });
    expect(screen.getByRole("button", { name: "Back to project runs" })).toBeTruthy();
    view.unmount();
    const afterUnmount = new KeyboardEvent("keydown", { key: "Escape", cancelable: true });
    document.dispatchEvent(afterUnmount);
    expect(afterUnmount.defaultPrevented).toBe(false);
    expect(e.references).toHaveBeenCalledTimes(1); expect(e.read).toHaveBeenCalledTimes(3);
    expect(e.send).not.toHaveBeenCalled(); expect(e.target).not.toHaveBeenCalled();
  } finally {
    document.removeEventListener("focusin", onFocus);
  }
});
