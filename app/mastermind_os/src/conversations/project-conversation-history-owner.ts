import { ExecutiveSessionCommandPort, type ExecutiveSessionTransport } from "../orchestration/executive-session-command-port";
import type { OperationPointer } from "../orchestration/operation-controller";
import { decodeSavedConversationPage, type SavedConversationReference, type SavedConversationSearchOwner } from "../discovery/saved-conversations";
import { decodeProjectConversationHistoryContext, type ProjectConversationHistoryContext } from "./project-conversation-history-context";
import type { ProjectConversationFixedReadTransport } from './project-conversation-transport';

/** Additive private READ on the incumbent transport. Existing command port
 * source and its mutation/session interfaces remain byte-identical. */
export type ProjectConversationHistoryTransport = ExecutiveSessionTransport & {
  projectConversations?: ProjectConversationFixedReadTransport;
  historyContext?(selection: { workRef: string }, signal: AbortSignal): Promise<unknown>;
};
export interface ProjectConversationHistoryReaderSelection {
  workRef: string;
  currentWorkRef: () => string | null;
  selectionGeneration: () => string;
}
export type ProjectConversationHistoryReaderFactory = (selection: ProjectConversationHistoryReaderSelection) =>
  ReturnType<typeof createProjectConversationHistoryOwner>;

/** An explicit chosen project's READ lifecycle. No target lookup, store,
 * registry, send, continuation, consume, create or automatic history read. */
export function createProjectConversationHistoryOwner(deps: {
  transport: ProjectConversationHistoryTransport;
  workRef: () => string | null;
  /** Actual monotonic App/project acquisition epoch, including A→B→A. */
  selectionGeneration: () => string;
  clock?: () => number;
}) {
  const transport = deps.transport, now = deps.clock ?? Date.now;
  const methods = Object.freeze({ context: transport.historyContext, references: transport.projectReferences,
    reply: transport.reply, auth: transport.authGeneration, available: transport.available, subscribe: transport.subscribe });
  let verified: ProjectConversationHistoryContext | null = null, verifiedAuth: number | null = null;
  let verifiedSelectionGeneration: string | null = null;
  let epoch = 0, pageEpoch = 0, disposed = false;
  let boundary = new AbortController(), expiry: ReturnType<typeof setTimeout> | undefined;
  let references = new Map<string, SavedConversationReference>();
  const listeners = new Set<() => void>();
  const notify = () => { for (const listener of listeners) listener(); };
  function invalidate() {
    epoch++; pageEpoch++; verified = null; verifiedAuth = null; verifiedSelectionGeneration = null; references.clear();
    boundary.abort(); boundary = new AbortController(); clearTimeout(expiry); expiry = undefined; notify();
  }
  const sameMethods = () => transport.historyContext === methods.context && transport.projectReferences === methods.references &&
    transport.reply === methods.reply && transport.authGeneration === methods.auth &&
    transport.available === methods.available && transport.subscribe === methods.subscribe;
  function context() {
    try {
      const timestamp = now();
      if (disposed || !verified || !sameMethods() || !methods.available.call(transport) ||
          methods.auth.call(transport) !== verifiedAuth || deps.workRef() !== verified.workRef ||
          deps.selectionGeneration() !== verifiedSelectionGeneration ||
          !Number.isSafeInteger(timestamp) || timestamp < 0 || timestamp >= verified.expiresAtMs || !sameMethods()) return null;
      return Object.freeze({ principalScope: verified.principalScope, generation: String(epoch) });
    } catch { return null; }
  }
  const current = (captured: ReturnType<typeof context>) => {
    const value = context();
    return !!captured && !!value && value.principalScope === captured.principalScope && value.generation === captured.generation;
  };
  // Only the incumbent original-reply verifier is used. Its session getter is
  // null, so no target/mutation intent can exist; only its read is exposed.
  const readPort = new ExecutiveSessionCommandPort({
    authGeneration: () => methods.auth.call(transport), available: () => !!context(), subscribe: () => () => {},
    context: async () => { throw new Error("HISTORY_READ_ONLY"); },
    send: async () => { throw new Error("HISTORY_READ_ONLY"); },
    reply: (args, signal) => methods.reply.call(transport, args, signal),
  }, () => null, context);
  const owner: SavedConversationSearchOwner = Object.freeze({
    context,
    authGeneration: () => methods.auth.call(transport),
    async readReferences({ workRef, pageSize, cursor, signal }: Parameters<SavedConversationSearchOwner["readReferences"]>[0]) {
      const captured = context(), ticket = ++pageEpoch; references.clear();
      if (!captured || !verified || workRef !== verified.workRef || pageSize !== 4 || !methods.references || signal.aborted ||
          (cursor !== undefined && (typeof cursor !== "string" || /^[A-Za-z0-9_=-]{1,2048}$/.exec(cursor)?.[0] !== cursor)))
        throw new Error("HISTORY_SOURCE_UNAVAILABLE");
      const raw = await methods.references.call(transport, { work_ref: workRef, page_size: 4,
        ...(cursor === undefined ? {} : { cursor }) }, signal);
      const page = decodeSavedConversationPage(raw, workRef);
      if (!page || signal.aborted || ticket !== pageEpoch || !current(captured)) throw new Error("HISTORY_SOURCE_UNAVAILABLE");
      references = new Map(page.references.map(row => [row.operation_key, row]));
      // Return detached validated source fields, never a mutable raw frame.
      return Object.freeze({ schema: "mastermind.os.executive.session_result.v1", operation: "references", ok: true,
        effect: "NONE", operation_key: null, error: null, data: Object.freeze({
          schema: "mastermind.session_reply_references.v1", status: page.nextCursor === null ? "COMPLETE" : "PARTIAL",
          references: page.references, next_cursor: page.nextCursor, high_water: page.highWater }) });
    },
    async readAnswer(pointer: OperationPointer, signal: AbortSignal) {
      // Detach only closed data descriptors before a reference lookup. Caller
      // accessors must not retarget the operation between membership and READ.
      const denied = { receipt: { operationKey: "", kind: "message" as const, targetKey: null,
        disposition: "unknown" as const, reason: "HISTORY_SOURCE_UNAVAILABLE" }, answer: null };
      let original: OperationPointer;
      try {
        if (!pointer || ![Object.prototype, null].includes(Object.getPrototypeOf(pointer))) return denied;
        const fields = Object.getOwnPropertyDescriptors(pointer);
        if (Reflect.ownKeys(fields).length !== 3 || Object.keys(fields).sort().join(",") !== "kind,operationKey,targetKey" ||
            Object.values(fields).some(field => !("value" in field)) || fields.kind.value !== "message" ||
            typeof fields.operationKey.value !== "string" || typeof fields.targetKey.value !== "string") return denied;
        original = Object.freeze({ kind: "message", operationKey: fields.operationKey.value, targetKey: fields.targetKey.value });
      } catch { return denied; }
      const captured = context(), reference = references.get(original.operationKey);
      const withheld = () => ({ receipt: { ...original, disposition: "unknown" as const, reason: "HISTORY_SOURCE_UNAVAILABLE" }, answer: null });
      if (!captured || !reference || signal.aborted || original.targetKey !== reference.target_ref) return withheld();
      const result = await readPort.readQualifiedAnswer(original, signal);
      if (signal.aborted || !current(captured) || references.get(original.operationKey) !== reference ||
          result.receipt.disposition !== "accepted" || !result.answer ||
          result.answer.readRef !== reference.read_ref || result.answer.parentConsumed !== false) return withheld();
      return result;
    },
  });
  const unsubscribe = methods.subscribe.call(transport, invalidate);
  return Object.freeze({ owner,
    subscribe(listener: () => void) { listeners.add(listener); return () => { listeners.delete(listener); }; },
    async refresh() {
      invalidate(); const ticket = epoch, selected = deps.workRef(), selectedGeneration = deps.selectionGeneration(),
        auth = methods.auth.call(transport), signal = boundary.signal;
      if (disposed || !selected || typeof selectedGeneration !== "string" || !selectedGeneration || selectedGeneration.length > 1024 ||
          !methods.context || !methods.references || !sameMethods() || !methods.available.call(transport)) return;
      try {
        const raw = await methods.context.call(transport, { workRef: selected }, signal);
        const value = decodeProjectConversationHistoryContext(raw, selected, now());
        if (!value || disposed || signal.aborted || ticket !== epoch || !sameMethods() ||
            methods.auth.call(transport) !== auth || !methods.available.call(transport) || deps.workRef() !== selected ||
            deps.selectionGeneration() !== selectedGeneration) return;
        verified = value; verifiedAuth = auth; verifiedSelectionGeneration = selectedGeneration;
        expiry = setTimeout(invalidate, Math.min(2147483647, value.expiresAtMs - now())); notify();
      } catch { /* Fixed unavailable state; no source exception escapes. */ }
    },
    dispose() { disposed = true; invalidate(); unsubscribe(); listeners.clear(); },
  });
}

/** Installed host composition only: absent fixed transport means no reader.
 * Presence constructs a restricted reader, never authenticates its context. */
export function createProjectConversationHistoryReaderFactory(transport: ProjectConversationHistoryTransport):
  ProjectConversationHistoryReaderFactory | undefined {
  if (typeof transport.historyContext !== "function" || typeof transport.projectReferences !== "function" ||
      typeof transport.reply !== "function" || typeof transport.authGeneration !== "function" ||
      typeof transport.available !== "function" || typeof transport.subscribe !== "function") return undefined;
  return ({ workRef, currentWorkRef, selectionGeneration }) => createProjectConversationHistoryOwner({ transport,
    workRef: () => currentWorkRef() === workRef ? workRef : null, selectionGeneration });
}
