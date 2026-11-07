import { vi } from "vitest";
import sourceFixture from "../fixtures/project-execution-history-owner.json";
import identityFixture from "../fixtures/project-conversation-history-owner.json";
import { createProjectConversationCatalogueReader } from "./project-conversation-catalogue-factory";
import type { ProjectConversationHistoryTransport } from "./project-conversation-history-owner";

export const executionFixture = sourceFixture;
export const executionWork = sourceFixture.catalogue.work_ref;
export const executionReference = sourceFixture.catalogue.entries[0]!.reference;
export function deferred<T = unknown>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
export function executionHistoryHarness() {
  const state = {
    workRef: executionWork as string | null, selection: "project-selection-1", auth: 1, available: true,
    principalScope: "1".repeat(64), catalogue: structuredClone(sourceFixture.catalogue) as unknown,
    window: structuredClone(sourceFixture.completed_read) as unknown,
    contextExpiry: Math.floor(Date.now() / 1000) + 600,
  };
  const listeners = new Set<() => void>();
  const historyContext = vi.fn(async () => {
    const frame = structuredClone(identityFixture.context);
    frame.data.selection.work_ref = executionWork;
    frame.data.principal_scope = state.principalScope;
    frame.data.verified_expiry = state.contextExpiry;
    return frame;
  });
  const references = vi.fn(async () => state.catalogue);
  const read = vi.fn(async () => state.window);
  const send = vi.fn(async () => { throw Error("MUTATION_MUST_NOT_RUN"); });
  const target = vi.fn(async () => { throw Error("TARGET_MUST_NOT_RUN"); });
  const originalReferences = vi.fn(async () => { throw Error("LEGACY_REFERENCE_MUST_NOT_RUN"); });
  const reply = vi.fn(async () => { throw Error("LEGACY_REPLY_MUST_NOT_RUN"); });
  const request = vi.fn(async (operation: string, _args: unknown, _signal: AbortSignal): Promise<unknown> => {
    if (operation === "execution_references") return references();
    if (operation === "execution_read") return read();
    throw Error("UNREQUESTED_HISTORY_SOURCE");
  });
  const transport: ProjectConversationHistoryTransport = {
    authGeneration: () => state.auth, available: () => state.available,
    subscribe(listener) { listeners.add(listener); return () => { listeners.delete(listener); }; },
    context: target, send, reply, projectReferences: originalReferences, historyContext,
    projectConversations: { request },
  };
  const handle = createProjectConversationCatalogueReader({ transport, selection: {
    workRef: executionWork, currentWorkRef: () => state.workRef, selectionGeneration: () => state.selection,
  } });
  return {
    state, transport, handle, owner: handle.owner, request, references, read, historyContext, send, target, reply, originalReferences,
    notify() { for (const listener of listeners) listener(); },
    dispose: handle.dispose,
  };
}
