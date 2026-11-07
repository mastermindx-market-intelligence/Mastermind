import { Channel, invoke, isTauri } from "@tauri-apps/api/core";
import { liveFrameGuard } from "./live-stream";
import { createIndexedDbPendingPointerStore, type DurablePendingPointerStore } from "../orchestration/indexeddb-pending-pointer-store";
import type { OperationPointer } from "../orchestration/operation-controller";
import { parseNativeView, type NativeHermesPort, type NativeOperation, type NativeView } from "./contract";
import { nativePendingPointer, readNativePending, type NativePendingOperation } from "./pending-pointer";

type NativeInvoke = (command: string, args: Record<string, unknown>) => Promise<unknown>;
const preDispatch = new Set(["REQUEST_INVALID", "NATIVE_BUSY", "NATIVE_INSTALL_UNAVAILABLE",
  "NATIVE_PLATFORM_UNAVAILABLE", "NATIVE_CLIENT_NOT_STARTED", "NATIVE_AUTH_NOT_DISPATCHED"]);

type Invocation = { operation: string; requestId?: string; sessionId?: string };
function noSendCode(error: unknown, request: Invocation, generation: number): string | null {
  if (!error || typeof error !== "object" || Array.isArray(error)) return null;
  const value = error as Record<string, unknown>;
  const keys = ["schema", "operation", "requestId", "expectedAuthGeneration", "code",
    ...(request.operation === "send" ? ["sessionId"] : [])];
  if (!["create", "send"].includes(request.operation) || Object.keys(value).length !== keys.length ||
      keys.some(key => !Object.prototype.hasOwnProperty.call(value, key)) || value.schema !== "mastermind.hermes_native_no_send.v1" ||
      value.operation !== request.operation || value.requestId !== request.requestId ||
      value.expectedAuthGeneration !== generation ||
      request.operation === "send" && value.sessionId !== request.sessionId ||
      typeof value.code !== "string" || /^[A-Z][A-Z0-9_]{0,99}$/.exec(value.code)?.[0] !== value.code) return null;
  return value.code;
}

/** One foreground adapter over the EXISTING durable pointer owner. Reserve before
 * invoking; only original owner evidence can settle. No payload is persisted and
 * reopening never submits. The native host separately fences auth before spawn.
 * localScope is a same-OS-user storage namespace, not cloud identity/authority. */
export function createNativeHermesPort(input: {
  invoke: NativeInvoke;
  available: () => boolean;
  store: DurablePendingPointerStore;
  channel?: (receive: (value: unknown) => void) => { onmessage: (value: unknown) => void };
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
    ...(input.channel ? { observe: ((target, receive, failed) => {
      const context = current;
      if (!context || !input.available()) { failed("NATIVE_STREAM_UNAVAILABLE"); return () => {}; }
      const observerId = crypto.randomUUID().replaceAll("-", "");
      const guard = liveFrameGuard(target, context.generation);
      let active = true;
      let ended = false;
      const channel = input.channel!((value: unknown) => {
        if (!active || ended) return;
        try {
          if (!current || current.scope !== context.scope || current.generation !== context.generation) throw new Error("AUTHENTICATION_CHANGED");
          const frame = guard(value);
          ended = frame.state !== "live";
          receive(frame);
        } catch (error) {
          ended = true;
          failed(error instanceof Error && error.message === "AUTHENTICATION_CHANGED" ? error.message : "NATIVE_STREAM_INVALID");
          void input.invoke("hermes_native_unobserve", { observerId }).catch(() => {});
        }
      });
      // This command only reads the original native event ring. Its cancellation
      // closes the view's pipe; it never invokes prompt.cancel or session lifecycle.
      void input.invoke("hermes_native_observe", { observerId, request: {
        operation: "observe", sessionId: target.sessionId, admissionId: target.admissionId,
        authorityEpoch: target.authorityEpoch,
      }, expectedAuthGeneration: context.generation, onEvent: channel }).then(() => {
        if (active && !ended) { ended = true; failed("NATIVE_STREAM_INTERRUPTED"); }
      }).catch((error: unknown) => {
        if (!active || ended) return;
        ended = true;
        const code = typeof error === "string" ? error : error instanceof Error ? error.message : "";
        if (code === "AUTHENTICATION_CHANGED" || code === "NATIVE_AUTH_NOT_DISPATCHED") {
          current = null; failed("AUTHENTICATION_CHANGED");
        } else failed("NATIVE_STREAM_INTERRUPTED");
      });
      return () => {
        active = false; channel.onmessage = () => {};
        void input.invoke("hermes_native_unobserve", { observerId }).catch(() => {});
      };
    }) satisfies NonNullable<NativeHermesPort["observe"]> } : {}),
    async request(inputRequest: NativeOperation): Promise<NativeView> {
      const request = { ...inputRequest };
      if (!input.available()) throw new Error("NATIVE_PLATFORM_UNAVAILABLE");
      if (inFlight) throw new Error("NATIVE_BUSY");
      inFlight = true;
      let reserved: OperationPointer | null = null;
      let scope: string | null = null;
      let dispatched = false;
      let invocation: { request: Invocation; generation: number } | null = null;
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
        if (request.operation === "stop" && original?.kind !== "send") {
          return { schema: "mastermind.hermes_native_view.v1", state: "REFUSED", operation: "stop",
            authGeneration: context.generation, capabilities: [], delegation: "NOT_ENABLED",
            retryAllowed: false, code: "NATIVE_STOP_UNAVAILABLE", pendingOperation: original };
        }
        if (request.operation === "stop" && original?.kind === "send" && pointer) {
          // Bind the click to the displayed original before reserving cancellation.
          // Another view may have settled A and admitted B in this same session.
          if (original.requestId !== request.requestId || original.sessionId !== request.sessionId) {
            return { schema: "mastermind.hermes_native_view.v1", state: "REFUSED", operation: "stop",
              authGeneration: context.generation, capabilities: [], delegation: "NOT_ENABLED",
              retryAllowed: false, code: "NATIVE_STOP_TARGET_CHANGED", pendingOperation: original };
          }
          if (original.stopReserved || !input.store.reserveNativeStop) {
            return { schema: "mastermind.hermes_native_view.v1", state: "EFFECT_UNKNOWN", operation: "stop",
              authGeneration: context.generation, capabilities: [], delegation: "NOT_ENABLED",
              retryAllowed: false, code: "NATIVE_RECOVERY_REQUIRED", pendingOperation: original };
          }
          if (!await input.store.reserveNativeStop(scope, pointer)) {
            return { schema: "mastermind.hermes_native_view.v1", state: "EFFECT_UNKNOWN", operation: "stop",
              authGeneration: context.generation, capabilities: [], delegation: "NOT_ENABLED",
              retryAllowed: false, code: "NATIVE_RECOVERY_REQUIRED", pendingOperation: pending(await input.store.read(scope)) };
          }
          original = { ...original, stopReserved: true };
          pointer = nativePendingPointer(original);
          // Never roll this fence back: interruption may occur before an IPC reply.
          // Reopen and all failures can only read the original admission to settle it.
        }
        // Stop can name only the already reserved original send. No caller target,
        // new request, replacement prompt, or additional durable owner is accepted.
        const wire = request.operation === "stop" && original?.kind === "send"
          ? { operation: "stop_send", sessionId: original.sessionId, requestId: original.requestId }
          : request.operation === "recover" && original
          ? original.kind === "send"
            ? { operation: "recover_send", sessionId: original.sessionId, requestId: original.requestId }
            : { operation: "recover_create", requestId: original.requestId }
          : request;
        invocation = { request: wire, generation: context.generation };
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
        if (result.operation !== request.operation || result.requestId !== invocation.request.requestId ||
            result.requestSessionId !== (invocation.request.requestId ? invocation.request.sessionId : undefined)) {
          throw new Error("NATIVE_RESPONSE_INVALID");
        }
        checkTarget(result, wire as { sessionId?: string; admissionId?: string });
        const isRecovery = request.operation === "recover" || request.operation === "stop";
        const settled = mutating && ["REFUSED", "NOT_SENT"].includes(result.state) ||
          (mutating || isRecovery) && original?.kind === "create" && result.state === "OPENED" && !!result.session ||
          (mutating || isRecovery) && original?.kind === "send" && result.state === "ADMITTED" &&
            result.receipt?.status === "terminal" && result.receipt.sessionId === original.sessionId;
        if (settled && pointer) {
          if (!await input.store.clearIfEqual(scope, pointer)) {
            return { ...result, state: "EFFECT_UNKNOWN", code: "NATIVE_RECOVERY_REQUIRED", pendingOperation: pending(await input.store.read(scope)) };
          }
        }
        const remaining = pending(await input.store.read(scope));
        return { ...result, pendingOperation: remaining };
      } catch (error) {
        const code = typeof error === "string" ? error : error instanceof Error ? error.message : "";
        if (code === "AUTHENTICATION_CHANGED" || code === "NATIVE_AUTH_NOT_DISPATCHED" || code === "NATIVE_IDENTITY_CHANGED") current = null;
        const proof = invocation ? noSendCode(error, invocation.request, invocation.generation) : null;
        if (reserved && scope && (!dispatched || proof !== null)) {
          let cleared = false;
          try { cleared = await input.store.clearIfEqual(scope, reserved); }
          catch { throw new Error("NATIVE_RECOVERY_UNAVAILABLE"); }
          if (!cleared) throw new Error("NATIVE_RECOVERY_UNAVAILABLE");
          if (proof !== null) {
            if (proof === "NATIVE_AUTH_NOT_DISPATCHED") current = null;
            // These UI codes mean before-dispatch only AFTER the exact proof cleared.
            throw new Error(preDispatch.has(proof) ? proof : "NATIVE_CLIENT_NOT_STARTED");
          }
        }
        if (code.startsWith("PENDING_POINTER_")) throw new Error("NATIVE_RECOVERY_UNAVAILABLE");
        // A generic IPC string has no request-bound no-send proof. In particular,
        // never let its spelling make the UI offer another mutation after IO.
        if (dispatched && preDispatch.has(code)) {
          throw new Error(code === "NATIVE_AUTH_NOT_DISPATCHED" ? "AUTHENTICATION_CHANGED" : "NATIVE_CLIENT_UNAVAILABLE");
        }
        throw error;
      } finally { inFlight = false; }
    },
  };
}

/** No browser fetch, native URL, bearer, profile picker or raw RPC escape hatch. */
export const nativeHermesPort: NativeHermesPort = createNativeHermesPort({
  invoke,
  channel: receive => new Channel<unknown>(receive),
  available: () => typeof window !== "undefined" && isTauri(),
  store: createIndexedDbPendingPointerStore(typeof indexedDB === "undefined" ? undefined : indexedDB),
});
