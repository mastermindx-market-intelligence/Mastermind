// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import fixture from "../fixtures/project-conversation-history-owner.json";
import { createProjectConversationHistoryOwner } from "./project-conversation-history-owner";
import { ProjectConversationHistory } from "./ProjectConversationHistory";
import type { ProjectConversationHistoryTransport } from "./project-conversation-history-owner";

beforeEach(async () => {
  const { webcrypto } = await vi.importActual<{ webcrypto: Crypto }>("node:crypto"); vi.stubGlobal("crypto", webcrypto);
});
const handles: ReturnType<typeof createProjectConversationHistoryOwner>[] = [];
afterEach(() => { cleanup(); for (const handle of handles.splice(0)) handle.dispose(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });
function setup() {
  let selected: string | null = fixture.work_ref, selectionGeneration = 0, auth = 1, available = true, now = fixture.now_ms;
  const listeners = new Set<() => void>();
  const contextFrame = structuredClone(fixture.context), page = structuredClone(fixture.page), answer = structuredClone(fixture.answer);
  const historyContext = vi.fn(async () => contextFrame);
  const references = vi.fn(async () => page), reply = vi.fn(async () => answer);
  const send = vi.fn(async () => { throw new Error("MUTATION_MUST_NOT_RUN"); });
  const target = vi.fn(async () => { throw new Error("TARGET_MUST_NOT_RUN"); });
  const transport: ProjectConversationHistoryTransport = { authGeneration: () => auth, available: () => available,
    subscribe: listener => { listeners.add(listener); return () => { listeners.delete(listener); }; },
    context: target, send, historyContext, projectReferences: references, reply };
  const handle = createProjectConversationHistoryOwner({ transport, workRef: () => selected,
    selectionGeneration: () => String(selectionGeneration), clock: () => now }); handles.push(handle);
  const row = page.data!.references[0], pointer = { kind: "message" as const, operationKey: row.operation_key, targetKey: row.target_ref };
  return { handle, transport, historyContext, references, reply, target, send, page, answer, contextFrame, row, pointer,
    select: (value: string | null) => { selected = value; selectionGeneration++; }, revoke: () => { available = false; }, rotate: () => { auth++; },
    expire: () => { now = fixture.context.data!.verified_expiry * 1000; },
    notify: () => { for (const listener of listeners) listener(); } };
}
const signal = () => new AbortController().signal;
async function page(e: ReturnType<typeof setup>) {
  await e.handle.refresh(); return e.handle.owner.readReferences({ workRef: fixture.work_ref, pageSize: 4, signal: signal() });
}

it("joins actual signed-ASGI fixture into a rootless reference page and incumbent cryptographically-qualified original reply", async () => {
  const e = setup(); expect(e.handle.owner.context()).toBeNull();
  expect(e.historyContext).not.toHaveBeenCalled(); expect(e.references).not.toHaveBeenCalled();
  await page(e);
  expect(e.historyContext).toHaveBeenCalledWith({ workRef: fixture.work_ref }, expect.any(AbortSignal));
  expect(e.references).toHaveBeenCalledWith({ work_ref: fixture.work_ref, page_size: 4 }, expect.any(AbortSignal));
  const result = await e.handle.owner.readAnswer(e.pointer, signal());
  expect(result.receipt.disposition).toBe("accepted");
  expect(result.answer).toMatchObject({ text: fixture.answer.data!.text, readRef: e.row.read_ref, parentConsumed: false });
  expect(e.send).not.toHaveBeenCalled(); expect(e.target).not.toHaveBeenCalled();
});
it("does not read a body until the exact pointer is witnessed in this project's current bounded reference page", async () => {
  const e = setup(); await e.handle.refresh();
  expect((await e.handle.owner.readAnswer(e.pointer, signal())).answer).toBeNull(); expect(e.reply).not.toHaveBeenCalled();
  await page(e);
  expect((await e.handle.owner.readAnswer({ ...e.pointer, targetKey: "fabric_attempt:" + "f".repeat(64) }, signal())).answer).toBeNull();
  let accessed = 0; const hostile = { ...e.pointer, get operationKey() { accessed++; return e.pointer.operationKey; } };
  expect((await e.handle.owner.readAnswer(hostile, signal())).answer).toBeNull();
  expect(accessed).toBe(0); expect(e.reply).not.toHaveBeenCalled();
});
it("rejects cross-project context and reference rows without borrowing a selected or dummy root", async () => {
  const e = setup(); e.contextFrame.data!.selection.work_ref = "WS:FOREIGN";
  await e.handle.refresh(); expect(e.handle.owner.context()).toBeNull(); expect(e.references).not.toHaveBeenCalled();
  e.contextFrame.data!.selection.work_ref = fixture.work_ref; e.page.data!.references[0].work_ref = "WS:FOREIGN";
  await expect(page(e)).rejects.toThrow("HISTORY_SOURCE_UNAVAILABLE");
  expect((await e.handle.owner.readAnswer(e.pointer, signal())).answer).toBeNull(); expect(e.reply).not.toHaveBeenCalled();
});
it.each(["selection", "selection-ABA", "grant", "auth", "expiry"] as const)("withholds stale %s before any subsequent reference/body read", async boundary => {
  const e = setup(); await page(e);
  if (boundary === "selection") e.select("WS:FOREIGN");
  if (boundary === "selection-ABA") { e.select("WS:FOREIGN"); e.select(fixture.work_ref); }
  if (boundary === "grant") e.revoke();
  if (boundary === "auth") e.rotate();
  if (boundary === "expiry") e.expire();
  expect(e.handle.owner.context()).toBeNull();
  await expect(e.handle.owner.readReferences({ workRef: fixture.work_ref, pageSize: 4, signal: signal() })).rejects.toThrow();
  expect((await e.handle.owner.readAnswer(e.pointer, signal())).answer).toBeNull();
  expect(e.references).toHaveBeenCalledTimes(1); expect(e.reply).not.toHaveBeenCalled();
});
it("withholds a late original body after principal refresh without reading a replacement turn", async () => {
  const e = setup(); await page(e); let finish!: (value: typeof fixture.answer) => void;
  e.reply.mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
  const pending = e.handle.owner.readAnswer(e.pointer, signal());
  e.contextFrame.data!.principal_scope = "f".repeat(64); await e.handle.refresh(); finish(structuredClone(fixture.answer));
  expect((await pending).answer).toBeNull(); expect(e.reply).toHaveBeenCalledTimes(1); expect(e.send).not.toHaveBeenCalled();
});
it("retains authentic partial/empty page coverage and never loops through cursors automatically", async () => {
  const e = setup(); e.page.data!.status = "PARTIAL"; e.page.data!.next_cursor = "Y3Vyc29y" as never;
  const raw = await page(e) as any;
  expect(raw.data.status).toBe("PARTIAL"); expect(raw.data.next_cursor).toBe("Y3Vyc29y"); expect(e.references).toHaveBeenCalledTimes(1);
  e.page.data!.status = "COMPLETE"; e.page.data!.next_cursor = null; e.page.data!.references = [];
  const empty = await e.handle.owner.readReferences({ workRef: fixture.work_ref, pageSize: 4, signal: signal() }) as any;
  expect(empty.data.references).toEqual([]); expect(empty.data.status).toBe("COMPLETE"); expect(e.reply).not.toHaveBeenCalled();
});
it("publishes no body for a foreign original read reference despite a syntactically successful reply", async () => {
  const e = setup(); await page(e); e.answer.data!.read_ref = "session-reply-" + "f".repeat(64);
  expect((await e.handle.owner.readAnswer(e.pointer, signal())).answer).toBeNull();
});
it("renders no owner IO on mount, then explicit page→Open→Back through the same original qualified source", async () => {
  const e = setup();
  render(<ProjectConversationHistory workRef={fixture.work_ref} sourceGeneration="actual-test-host1" history={e.handle} canRead={() => true}/>);
  expect(e.historyContext).not.toHaveBeenCalled(); expect(e.references).not.toHaveBeenCalled(); expect(e.reply).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Read saved replies" }));
  const open = await screen.findByRole("button", { name: `Open saved reply requested ${e.row.requested_at}` });
  expect(screen.queryByText(fixture.answer.data!.text)).toBeNull(); expect(e.reply).not.toHaveBeenCalled();
  fireEvent.click(open); await screen.findByText(fixture.answer.data!.text);
  fireEvent.click(screen.getByRole("button", { name: "Back to saved replies" }));
  expect(screen.getByRole("button", { name: `Open saved reply requested ${e.row.requested_at}` })).toBeTruthy();
  expect(e.references).toHaveBeenCalledTimes(1); expect(e.reply).toHaveBeenCalledTimes(1); expect(e.send).not.toHaveBeenCalled();
});
it("masks old project rows on source selection replacement and permits an independent fresh read rather than leaving a stale loading state", async () => {
  const e = setup();
  const view = render(<ProjectConversationHistory workRef={fixture.work_ref} sourceGeneration="host1" history={e.handle} canRead={() => true}/>);
  fireEvent.click(screen.getByRole("button", { name: "Read saved replies" })); await screen.findByRole("button", { name: /Open saved reply requested/ });
  e.select("WS:OTHER"); view.rerender(<ProjectConversationHistory workRef="WS:OTHER" sourceGeneration="host2" history={e.handle} canRead={() => true}/>);
  expect(screen.queryByRole("button", { name: /Open saved reply requested/ })).toBeNull();
  expect(screen.getByRole("button", { name: "Read saved replies" }).hasAttribute("disabled")).toBe(false);
});
