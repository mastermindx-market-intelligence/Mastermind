import {
  decodeDirectNativeResult,
  directConsumeIdentity,
  parseDirectConsumeTarget,
  type DirectNativeTransport,
  type DirectSelection,
  type DirectTerminalSelection,
} from "../direct-native-result";
import type {
  CommandIntent,
  EffectReceipt,
  FiniteCommandPort,
  OperationPointer,
  OwnerContext,
} from "./operation-controller";
import { canonicalJson } from "./operation-key";

/** One explicit consume; recovery reads the same terminal selection, never writes. */
export class DirectNativeCommandPort implements FiniteCommandPort {
  constructor(
    private readonly transport: DirectNativeTransport,
    private readonly owner: () => OwnerContext | null,
  ) {}
  context() {
    return this.owner();
  }
  makeConsumeIntent(
    selection: DirectTerminalSelection,
    digest: string,
  ): CommandIntent | null {
    try {
      const context = this.owner();
      if (!context) return null;
      const pointer = directConsumeIdentity(
        context.principalScope,
        selection,
        digest,
      );
      return {
        kind: "consume",
        targetKey: pointer.targetKey,
        payload: {
          ...selection,
          result_digest: digest,
          operation_key: pointer.operationKey,
        },
      };
    } catch {
      return null;
    }
  }
  prepare(intent: CommandIntent): OperationPointer {
    const context = this.owner(),
      target = parseDirectConsumeTarget(intent.targetKey);
    if (!context || intent.kind !== "consume" || !target)
      throw Error("DIRECT_CONSUME_INVALID");
    const { result_digest, ...selection } = target;
    const expected = this.makeConsumeIntent(selection, result_digest)!;
    if (
      canonicalJson(expected.payload) !== canonicalJson(intent.payload) ||
      expected.targetKey !== intent.targetKey
    )
      throw Error("DIRECT_CONSUME_INVALID");
    return directConsumeIdentity(
      context.principalScope,
      selection,
      result_digest,
    );
  }
  private async request(
    pointer: OperationPointer,
    signal: AbortSignal,
    write: boolean,
  ): Promise<EffectReceipt> {
    const result = (accepted = false): EffectReceipt => ({
      ...pointer,
      disposition: accepted ? "accepted" : "unknown",
    });
    const context = this.owner(),
      target = parseDirectConsumeTarget(pointer.targetKey);
    if (!context || pointer.kind !== "consume" || !target || signal.aborted)
      return result();
    const { result_digest, ...selection } = target;
    const expected = directConsumeIdentity(
      context.principalScope,
      selection,
      result_digest,
    );
    if (expected.operationKey !== pointer.operationKey) return result();
    try {
      const raw = write
        ? await this.transport.consume(
            { ...target, operation_key: pointer.operationKey },
            signal,
          )
        : await this.transport.read(selection, signal);
      const current = this.owner();
      if (
        signal.aborted ||
        !current ||
        current.principalScope !== context.principalScope ||
        current.generation !== context.generation
      )
        return result();
      const decoded = decodeDirectNativeResult(raw, selection);
      return result(
        decoded?.availability === "AVAILABLE" &&
          decoded.result?.result_digest === result_digest &&
          decoded.consumption?.state === "CONSUMED",
      );
    } catch {
      return result();
    }
  }
  async submit(
    pointer: OperationPointer,
    intent: CommandIntent,
    signal: AbortSignal,
  ) {
    try {
      const expected = this.prepare(intent);
      if (
        expected.operationKey !== pointer.operationKey ||
        expected.targetKey !== pointer.targetKey
      )
        throw Error();
    } catch {
      return { ...pointer, disposition: "unknown" as const };
    }
    return this.request(pointer, signal, true);
  }
  readOperation(pointer: OperationPointer, signal: AbortSignal) {
    return this.request(pointer, signal, false);
  }
  read(selection: DirectSelection, signal: AbortSignal) {
    return this.transport.read(selection, signal);
  }
}
