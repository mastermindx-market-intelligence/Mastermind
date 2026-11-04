import {
  correctionIdentity,
  parseCorrectionTarget,
  decodeDirectCorrection,
} from "../direct-native-correction";
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
  async inspectCorrection(selection: DirectSelection, signal: AbortSignal) {
    const owner = this.owner();
    if (!owner || !this.transport.correction)
      throw Error("DIRECT_CORRECTION_UNAVAILABLE");
    const value = await this.transport.correction(
        { ...selection, operation: "inspect" },
        signal,
      ),
      current = this.owner();
    if (
      signal.aborted ||
      !current ||
      current.principalScope !== owner.principalScope ||
      current.generation !== owner.generation
    )
      throw Error("DIRECT_CORRECTION_UNAVAILABLE");
    return decodeDirectCorrection(value, selection);
  }
  makeCorrectionIntent(
    selection: DirectTerminalSelection,
    fence: number,
  ): CommandIntent | null {
    try {
      const owner = this.owner();
      if (!owner || !this.transport.correction) return null;
      const pointer = correctionIdentity(
        owner.principalScope,
        selection,
        fence,
      );
      return {
        kind: "stop",
        targetKey: pointer.targetKey,
        payload: {
          ...selection,
          fence_generation: fence,
          operation_key: pointer.operationKey,
        },
      };
    } catch {
      return null;
    }
  }
  prepare(intent: CommandIntent): OperationPointer {
    if (intent.kind === "stop") {
      const context = this.owner(),
        target = parseCorrectionTarget(intent.targetKey);
      if (!context || !target) throw Error("DIRECT_CORRECTION_INVALID");
      const { fence_generation, ...selection } = target,
        expected = this.makeCorrectionIntent(selection, fence_generation);
      if (
        !expected ||
        canonicalJson(expected.payload) !== canonicalJson(intent.payload)
      )
        throw Error("DIRECT_CORRECTION_INVALID");
      return correctionIdentity(
        context.principalScope,
        selection,
        fence_generation,
      );
    }

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
    if (pointer.kind === "stop") {
      const context = this.owner(),
        target = parseCorrectionTarget(pointer.targetKey);
      if (!context || !target || !this.transport.correction || signal.aborted)
        return result();
      const { fence_generation, ...selection } = target,
        expected = correctionIdentity(
          context.principalScope,
          selection,
          fence_generation,
        );
      if (expected.operationKey !== pointer.operationKey) return result();
      try {
        const raw = await this.transport.correction(
          write
            ? {
                ...target,
                operation_key: pointer.operationKey,
                operation: "request",
              }
            : { ...selection, operation: "inspect" },
          signal,
        );
        const current = this.owner(),
          decoded = decodeDirectCorrection(raw, selection);
        if (
          signal.aborted ||
          !current ||
          current.principalScope !== context.principalScope ||
          current.generation !== context.generation ||
          !decoded ||
          decoded.fence_generation !== fence_generation
        )
          return result();
        // Recovery accepts actual same-attempt cancellation/terminal state,
        // never RUNNING and never another write after response loss.
        return result(
          write
            ? decoded.operation_key === pointer.operationKey
            : !["RUNNING", "CHECKPOINTED"].includes(decoded.status),
        );
      } catch {
        return result();
      }
    }
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
