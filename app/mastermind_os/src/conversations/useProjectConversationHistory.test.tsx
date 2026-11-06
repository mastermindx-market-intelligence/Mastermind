// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { MissionHost } from "../host";
import fixture from "../fixtures/project-conversation-history-owner.json";
import { createProjectConversationHistoryReaderFactory, type ProjectConversationHistoryTransport } from "./project-conversation-history-owner";
import { useProjectConversationHistory, type ProjectConversationHistoryWorkspace } from "./useProjectConversationHistory";

beforeEach(async () => {
  const { webcrypto } = await vi.importActual<{ webcrypto: Crypto }>("node:crypto"); vi.stubGlobal("crypto", webcrypto);
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });
function Harness(props: ProjectConversationHistoryWorkspace) { return useProjectConversationHistory(props).panel; }
function setup() {
  const historyContext = vi.fn(async () => structuredClone(fixture.context));
  const references = vi.fn(async () => structuredClone(fixture.page)), reply = vi.fn(async () => structuredClone(fixture.answer));
  const context = vi.fn(async () => { throw new Error("NO_TARGET_DISCOVERY"); });
  const send = vi.fn(async () => { throw new Error("NO_MUTATION"); });
  const transport: ProjectConversationHistoryTransport = { historyContext, projectReferences: references, reply, context, send,
    authGeneration: () => 1, available: () => true, subscribe: () => () => {} };
  const factory = vi.fn(createProjectConversationHistoryReaderFactory(transport)!);
  const host = { session: { refresh: vi.fn(), setStopCondition: vi.fn(), createProjectHistoryReader: factory } } as unknown as MissionHost;
  const props: ProjectConversationHistoryWorkspace = { host, workRef: fixture.work_ref, authGeneration: 1,
    hostGeneration: 1, selectionGeneration: "catalogue-acquisition-1", canReadCurrentProject: () => true };
  return { props, host, factory, transport, historyContext, references, reply, context, send };
}
it("keeps a legacy host compatible and never infers a missing fixed reader from a session or READ flag", () => {
  const e = setup(); delete (e.host.session as any).createProjectHistoryReader;
  render(<Harness {...e.props}/>);
  expect(screen.getByRole("button", { name: "Read saved replies" }).hasAttribute("disabled")).toBe(true);
  expect(e.historyContext).not.toHaveBeenCalled(); expect(e.references).not.toHaveBeenCalled();
});
it("composes one effect-free selected reader into explicit source→list→Open and performs no cross-project fanout", async () => {
  const e = setup(), view = render(<Harness {...e.props}/>);
  expect(e.factory).toHaveBeenCalledTimes(1); expect(e.historyContext).not.toHaveBeenCalled(); expect(e.references).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Read saved replies" }));
  fireEvent.click(await screen.findByRole("button", { name: /Open saved reply requested/ }));
  await screen.findByText(fixture.answer.data!.text);
  expect(e.historyContext).toHaveBeenCalledTimes(1); expect(e.references).toHaveBeenCalledTimes(1); expect(e.reply).toHaveBeenCalledTimes(1);
  view.rerender(<Harness {...e.props} workRef="WS:OTHER" selectionGeneration="catalogue-acquisition-2"/>);
  expect(screen.queryByText(fixture.answer.data!.text)).toBeNull(); expect(e.factory).toHaveBeenCalledTimes(2);
  expect(e.historyContext).toHaveBeenCalledTimes(1); expect(e.references).toHaveBeenCalledTimes(1);
  expect(e.context).not.toHaveBeenCalled(); expect(e.send).not.toHaveBeenCalled();
});
it("refuses no-render project qualification loss before Open and masks source metadata on the next render", async () => {
  const e = setup(); let allowed = true;
  const props = { ...e.props, canReadCurrentProject: () => allowed };
  const view = render(<Harness {...props}/>);
  fireEvent.click(screen.getByRole("button", { name: "Read saved replies" }));
  const open = await screen.findByRole("button", { name: /Open saved reply requested/ });
  allowed = false; fireEvent.click(open);
  expect(e.reply).not.toHaveBeenCalled(); expect(screen.queryByText(fixture.answer.data!.text)).toBeNull();
  view.rerender(<Harness {...props}/>);
  expect(screen.queryByRole("button", { name: /Open saved reply requested/ })).toBeNull();
  expect(screen.getByRole("button", { name: "Read saved replies" }).hasAttribute("disabled")).toBe(true);
});
it("fails closed if a supplied optional reader factory throws, without exposing an exception or breaking the surrounding project", () => {
  const e = setup(); (e.host.session as any).createProjectHistoryReader = () => { throw new Error("PRIVATE-FACTORY-DETAIL"); };
  render(<Harness {...e.props}/>);
  expect(screen.getByRole("button", { name: "Read saved replies" }).hasAttribute("disabled")).toBe(true);
  expect(document.body.textContent).not.toContain("PRIVATE-FACTORY-DETAIL"); expect(e.historyContext).not.toHaveBeenCalled();
});
