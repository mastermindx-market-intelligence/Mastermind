import type { OperationPointer } from "../orchestration/operation-controller";

/** A lookup hint in the incumbent pending-pointer store; never a transcript,
 * credential, permission, execution record, retry queue or session authority. */
export type NativePendingOperation =
  | { kind: "create"; requestId: string }
  | { kind: "send"; requestId: string; sessionId: string };

const createKey = /^mmos-hermes-create-([a-f0-9]{32})$/;
const sendKey = /^mmos-hermes-send-([a-f0-9]{32})$/;
const sessionId = /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}$/;
export const NATIVE_CREATE_TARGET = "hermes-native-local.v1";

export function nativePendingPointer(value: NativePendingOperation): OperationPointer {
  if (/^[a-f0-9]{32}$/.exec(value.requestId)?.[0] !== value.requestId ||
      value.kind === "send" && sessionId.exec(value.sessionId)?.[0] !== value.sessionId) {
    throw new Error("REQUEST_INVALID");
  }
  return value.kind === "create"
    ? { kind: "conversation_create", operationKey: `mmos-hermes-create-${value.requestId}`, targetKey: NATIVE_CREATE_TARGET }
    : { kind: "conversation_turn", operationKey: `mmos-hermes-send-${value.requestId}`, targetKey: value.sessionId };
}

export function readNativePending(pointer: OperationPointer): NativePendingOperation | null {
  const create = createKey.exec(pointer.operationKey);
  if (pointer.kind === "conversation_create" && create?.[0] === pointer.operationKey &&
      pointer.targetKey === NATIVE_CREATE_TARGET) return { kind: "create", requestId: create[1] };
  const send = sendKey.exec(pointer.operationKey);
  if (pointer.kind === "conversation_turn" && send?.[0] === pointer.operationKey &&
      typeof pointer.targetKey === "string" && sessionId.exec(pointer.targetKey)?.[0] === pointer.targetKey) {
    return { kind: "send", requestId: send[1], sessionId: pointer.targetKey };
  }
  return null;
}
