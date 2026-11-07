import { afterEach, describe, expect, it, vi } from "vitest";
import { decodeProjectExecutionReference } from "./project-execution-history-contract";
import {
  deferred, executionFixture as fixture, executionHistoryHarness, executionReference as reference, executionWork as work,
} from "./project-execution-history.test-support";

const handles: ReturnType<typeof executionHistoryHarness>[] = [];
const setup = () => { const value = executionHistoryHarness(); handles.push(value); return value; };
const signal = () => new AbortController().signal;
afterEach(() => { handles.splice(0).forEach(value => value.dispose()); vi.useRealTimers(); });
async function acquire(e: ReturnType<typeof setup>) {
  await e.owner.refresh();
  return e.owner.executionCatalogue({ workRef: work, signal: signal() });
}

describe("project execution reads through the actual catalogue and identity owners", () => {
  it("requires an explicit authenticated catalogue member before a read and exposes no write path", async () => {
    const e = setup();
    expect(e.owner.context()).toBeNull();
    await expect(e.owner.readExecution(reference, signal())).rejects.toThrow();
    await e.owner.refresh();
    await expect(e.owner.readExecution(reference, signal())).rejects.toThrow();
    expect(e.request).not.toHaveBeenCalled();
    const page = await e.owner.executionCatalogue({ workRef: work, signal: signal() });
    const window = await e.owner.readExecution(page.entries[0]!.reference, signal());
    expect(e.request.mock.calls.map(call => call[0])).toEqual(["execution_references", "execution_read"]);
    expect(e.request.mock.calls[0]![1]).toEqual({ work_ref: work });
    expect(e.request.mock.calls[1]![1]).toEqual(reference);
    expect(e.owner.currentExecution(window)).toBe(true);
    expect(e.owner.currentExecution(structuredClone(window))).toBe(false);
    expect(e.send).not.toHaveBeenCalled(); expect(e.target).not.toHaveBeenCalled();
    expect(e.reply).not.toHaveBeenCalled(); expect(e.originalReferences).not.toHaveBeenCalled();
  });

  it("does not issue a read for an unknown member, another project, or a changed source/principal witness", async () => {
    const e = setup(); await acquire(e);
    for (const patch of [
      { root_job_id: "JOB-999" }, { work_ref: "WS:FOREIGN" }, { root_event_id: reference.root_event_id + 1 },
      { project_execution_source_sha256: "f".repeat(64) }, { principal_scope_sha256: "f".repeat(64) },
    ]) await expect(e.owner.readExecution({ ...reference, ...patch }, signal())).rejects.toThrow();
    expect(e.read).not.toHaveBeenCalled();
    await expect(e.owner.executionCatalogue({ workRef: "WS:FOREIGN", signal: signal() })).rejects.toThrow();
    expect(e.references).toHaveBeenCalledTimes(1);
  });

  it("accepts real QUEUED-to-COMPLETED state progress while keeping the immutable source member", async () => {
    const e = setup(); e.state.catalogue = fixture.pending_catalogue;
    const page = await acquire(e);
    expect(page.entries[0]!.root_state).toBe("QUEUED");
    e.state.window = fixture.completed_read;
    const window = await e.owner.readExecution(page.entries[0]!.reference, signal());
    expect(window.state).toBe("COMPLETED");
    expect(window.parent_witness).toEqual(fixture.completed_read.parent_witness);
    expect(e.owner.currentExecution(window)).toBe(true);
  });

  it("rejects a validly shaped response if its original project goal changed after membership", async () => {
    const e = setup(); await acquire(e);
    e.state.window = { ...fixture.completed_read, goal: "A different project request" };
    await expect(e.owner.readExecution(reference, signal())).rejects.toThrow();
    const original = decodeProjectExecutionReference(reference, work);
    expect(original).toEqual(reference);
  });

  it("allows only the latest concurrent read completion to remain current", async () => {
    const e = setup(); await acquire(e);
    const first = deferred(), second = deferred();
    e.read.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise);
    const old = e.owner.readExecution(reference, signal()).then(() => "accepted", () => "withheld");
    const latest = e.owner.readExecution(reference, signal());
    second.resolve(fixture.completed_read);
    const window = await latest;
    first.resolve(fixture.pending_read);
    expect(await old).toBe("withheld");
    expect(e.owner.currentExecution(window)).toBe(true);
  });

  it("invalidates a prior continuation witness as soon as the current page is reacquired", async () => {
    const e = setup(); await acquire(e);
    const first = await e.owner.readExecution(reference, signal());
    const pending = deferred(); e.references.mockReturnValueOnce(pending.promise);
    const nextPage = e.owner.executionCatalogue({ workRef: work, signal: signal() });
    expect(e.owner.currentExecution(first)).toBe(false);
    pending.resolve(fixture.catalogue); await nextPage;
    const next = await e.owner.readExecution(reference, signal());
    expect(e.owner.currentExecution(first)).toBe(false);
    expect(e.owner.currentExecution(next)).toBe(true);
  });

  it("withholds an older read after a fresh catalogue changed the current member", async () => {
    const e = setup(); await acquire(e);
    const pending = deferred(); e.read.mockReturnValueOnce(pending.promise);
    const old = e.owner.readExecution(reference, signal()).then(() => "accepted", () => "withheld");
    await e.owner.executionCatalogue({ workRef: work, signal: signal() });
    pending.resolve(fixture.completed_read);
    expect(await old).toBe("withheld");
  });

  it.each(["auth", "selection", "unavailable", "callback", "transport", "dispose"] as const)(
    "withholds a late completed result across the %s boundary", async boundary => {
      const e = setup(); await acquire(e);
      const pending = deferred(); e.read.mockReturnValueOnce(pending.promise);
      const result = e.owner.readExecution(reference, signal()).then(() => "accepted", () => "withheld");
      if (boundary === "auth") { e.state.auth++; e.notify(); }
      if (boundary === "selection") {
        e.state.workRef = "WS:FOREIGN"; e.state.selection = "project-selection-2";
        e.state.workRef = work; e.state.selection = "project-selection-3";
      }
      if (boundary === "unavailable") e.state.available = false;
      if (boundary === "callback") e.transport.projectConversations!.request = vi.fn(async () => fixture.completed_read);
      if (boundary === "transport") e.transport.projectConversations = { request: e.request };
      if (boundary === "dispose") e.dispose();
      pending.resolve(fixture.completed_read);
      expect(await result).toBe("withheld");
      expect(e.owner.context()).toBeNull();
      expect(e.send).not.toHaveBeenCalled();
    });

  it("rejects identity refresh that completed after auth replacement and requires new membership", async () => {
    const e = setup(), pending = deferred<Awaited<ReturnType<typeof e.historyContext>>>();
    e.historyContext.mockReturnValueOnce(pending.promise);
    const refresh = e.owner.refresh().then(() => "accepted", () => "withheld");
    e.state.auth++; e.notify();
    pending.resolve(await e.historyContext());
    expect(await refresh).toBe("withheld");
    expect(e.owner.context()).toBeNull(); expect(e.references).not.toHaveBeenCalled();
    await e.owner.refresh();
    await expect(e.owner.readExecution(reference, signal())).rejects.toThrow();
    await e.owner.executionCatalogue({ workRef: work, signal: signal() });
    expect((await e.owner.readExecution(reference, signal())).state).toBe("COMPLETED");
  });

  it("invalidates a current result on principal context refresh and on verified expiry", async () => {
    vi.useFakeTimers(); const e = setup(); await acquire(e);
    const first = await e.owner.readExecution(reference, signal());
    const originalContext = e.owner.context();
    e.state.principalScope = "2".repeat(64); await e.owner.refresh();
    expect(e.owner.current(originalContext)).toBe(false); expect(e.owner.currentExecution(first)).toBe(false);
    await e.owner.executionCatalogue({ workRef: work, signal: signal() });
    const current = await e.owner.readExecution(reference, signal());
    expect(e.owner.currentExecution(current)).toBe(true);
    await vi.advanceTimersByTimeAsync(601_000);
    expect(e.owner.context()).toBeNull(); expect(e.owner.currentExecution(current)).toBe(false);
    await expect(e.owner.readExecution(reference, signal())).rejects.toThrow();
  });

  it("respects caller cancellation before transport and during a pending read", async () => {
    const e = setup(); await acquire(e); const preflight = new AbortController(); preflight.abort();
    await expect(e.owner.readExecution(reference, preflight.signal)).rejects.toThrow();
    expect(e.read).not.toHaveBeenCalled();
    const pending = deferred(), controller = new AbortController(); e.read.mockReturnValueOnce(pending.promise);
    const result = e.owner.readExecution(reference, controller.signal).then(() => "accepted", () => "withheld");
    const capturedSignal = e.request.mock.calls.at(-1)![2]; controller.abort();
    expect(capturedSignal.aborted).toBe(true);
    pending.resolve(fixture.completed_read);
    expect(await result).toBe("withheld");
  });
});
