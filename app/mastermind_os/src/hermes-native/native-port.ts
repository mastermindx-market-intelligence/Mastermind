import { invoke, isTauri } from "@tauri-apps/api/core";
import { createIndexedDbPendingPointerStore, type DurablePendingPointerStore } from "../orchestration/indexeddb-pending-pointer-store";
import type { OperationPointer } from "../orchestration/operation-controller";
import { parseNativeView, type NativeHermesPort, type NativeOperation, type NativeView } from "./contract";
import { nativePendingPointer, readNativePending, type NativePendingOperation } from "./pending-pointer";

type NativeInvoke = (command: string, args: Record<string, unknown>) => Promise<unknown>;
const preDispatch = new Set(["REQUEST_INVALID", "NATIVE_BUSY", "NATIVE_INSTALL_UNAVAILABLE",
  "NATIVE_PLATFORM_UNAVAILABLE", "NATIVE_CLIENT_NOT_STARTED", "NATIVE_AUTH_NOT_DISPATCHED"]);

/** One foreground adapter over the EXISTING durable pointer owner. Reserve before
 * invoking; only original owner evidence can settle. No payload is persisted and
 * reopening never submits. The native host separately fences auth before spawn.
 * localScope is a same-OS-user storage namespace, not cloud identity/authority. */
export function createNativeHermesPort(input: {
  invoke: NativeInvoke;
  available: () => boolean;
  store: DurablePendingPointerStore;
}): NativeHermesPort {
  let current: { scope: string; generation: number } | null = null;
  let inFlight = false;
  const pending = (pointer: OperationPointer | null): NativePendingOperation | null => {
    if (!pointer) return null;
    const value = readNativePending(pointer);
    if (!value) throw new Error("NATIVE_RECOVERY_UNAVAILABLE");
    return value;
  };
  const checkTarget = (result: NativeView, request: { sessionId?: string; admissionId?: string }) => {
    if (request.sessionId && result.session && ![result.session.id, result.session.storedId].includes(request.sessionId)) {
      throw new Error("NATIVE_RESPONSE_INVALID");
    }
    if (request.sessionId && result.receipt?.sessionId !== undefined && result.receipt.sessionId !== request.sessionId ||
        request.admissionId && result.receipt?.id !== undefined && result.receipt.id !== request.admissionId) {
      throw new Error("NATIVE_RESPONSE_INVALID");
    }
  };
  return {
    available: input.available,
    async request(request: NativeOperation): Promise<NativeView> {
      if (!input.available()) throw new Error("NATIVE_PLATFORM_UNAVAILABLE");
      if (inFlight) throw new Error("NATIVE_BUSY");
      inFlight = true;
      let reserved: OperationPointer | null = null;
      let scope: string | null = null;
      let dispatched = false;
      try {
        if (request.operation === "status") {
          const result = parseNativeView(await input.invoke("hermes_native", { request }));
          if (result.operation !== "status") throw new Error("NATIVE_RESPONSE_INVALID");
          if (result.state !== "READY") return result;
          const nextScope = result.runtime?.localScope;
          if (!nextScope) throw new Error("NATIVE_RECOVERY_UNAVAILABLE");
          if (current && current.scope !== nextScope) throw new Error("NATIVE_IDENTITY_CHANGED");
          const held = pending(await input.store.read(nextScope));
          current = { scope: nextScope, generation: result.authGeneration };
          return { ...result, pendingOperation: held, ...(held ? { code: "NATIVE_RECOVERY_REQUIRED" } : {}) };
        }
        const context = current;
        if (!context) throw new Error("NATIVE_RECOVERY_UNAVAILABLE");
        scope = context.scope;
        let pointer = await input.store.read(scope);
        let original = pending(pointer);
        const mutating = request.operation === "create" || request.operation === "send";
        if (mutating) {
          if (pointer) {
            return { schema: "mastermind.hermes_native_view.v1", state: "EFFECT_UNKNOWN",
              authGeneration: context.generation, capabilities: [], delegation: "NOT_ENABLED",
              retryAllowed: false, code: "NATIVE_RECOVERY_REQUIRED", pendingOperation: original };
          }
          original = request.operation === "create"
            ? { kind: "create", requestId: request.requestId }
            : { kind: "send", sessionId: request.sessionId, requestId: request.requestId };
          pointer = nativePendingPointer(original);
          const reservation = await input.store.reserve(scope, pointer);
          if (!reservation.reserved) {
            return { schema: "mastermind.hermes_native_view.v1", state: "EFFECT_UNKNOWN",
              authGeneration: context.generation, capabilities: [], delegation: "NOT_ENABLED",
              retryAllowed: false, code: "NATIVE_RECOVERY_REQUIRED", pendingOperation: pending(reservation.pointer) };
          }
          reserved = pointer;
        }
        if (request.operation === "recover" && (!pointer || !original)) {
          return { schema: "mastermind.hermes_native_view.v1", state: "READY",
            authGeneration: context.generation, capabilities: [], delegation: "NOT_ENABLED",
            retryAllowed: false, pendingOperation: null };
        }
        const wire = request.operation === "recover" && original
          ? original.kind === "send"
            ? { operation: "recover_send", sessionId: original.sessionId, requestId: original.requestId }
            : { operation: "recover_create", requestId: original.requestId }
          : request;
        dispatched = true;
        const result = parseNativeView(await input.invoke("hermes_native",
          { request: wire, expectedAuthGeneration: context.generation }));
        if (result.authGeneration !== context.generation) {
          current = null;
          throw new Error("AUTHENTICATION_CHANGED");
        }
        if (result.runtime?.localScope && result.runtime.localScope !== scope) {
          current = null;
          throw new Error("NATIVE_IDENTITY_CHANGED");
        }
        // Settlement must describe this invocation, including the public recovery operation.
        if (result.operation !== request.operation) throw new Error("NATIVE_RESPONSE_INVALID");
        checkTarget(result, wire as { sessionId?: string; admissionId?: string });
        const isRecovery = request.operation === "recover";
        const settled = mutating && ["REFUSED", "NOT_SENT"].includes(result.state) ||
          (mutating || isRecovery) && original?.kind === "create" && result.state === "OPENED" && !!result.session ||
          (mutating || isRecovery) && original?.kind === "send" && result.state === "ADMITTED" &&
            result.receipt?.status === "terminal" && result.receipt.sessionId === original.sessionId;
        if (settled && pointer) {
          if (!await input.store.clearIfEqual(scope, pointer)) {
            return { ...result, state: "EFFECT_UNKNOWN", code: "NATIVE_RECOVERY_REQUIRED", pendingOperation: original };
          }
        }
        const remaining = pending(await input.store.read(scope));
        return { ...result, pendingOperation: remaining };
      } catch (error) {
        const code = typeof error === "string" ? error : error instanceof Error ? error.message : "";
        if (code === "AUTHENTICATION_CHANGED" || code === "NATIVE_AUTH_NOT_DISPATCHED" || code === "NATIVE_IDENTITY_CHANGED") current = null;
        // Only a typed before-spawn refusal may clear this call's reservation.
        // An unclassified auth change can happen AFTER IO and must retain the original.
        if (reserved && scope && (!dispatched || preDispatch.has(code))) {
          await input.store.clearIfEqual(scope, reserved);
        }
        if (code.startsWith("PENDING_POINTER_")) throw new Error("NATIVE_RECOVERY_UNAVAILABLE");
        throw error;
      } finally { inFlight = false; }
    },
  };
}

/** No browser fetch, native URL, bearer, profile picker or raw RPC escape hatch. */
export const nativeHermesPort: NativeHermesPort = createNativeHermesPort({
  invoke,
  available: () => typeof window !== "undefined" && isTauri(),
  store: createIndexedDbPendingPointerStore(typeof indexedDB === "undefined" ? undefined : indexedDB),
});
