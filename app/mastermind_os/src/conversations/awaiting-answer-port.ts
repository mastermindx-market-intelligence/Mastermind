import type {
  CommandIntent, EffectReceipt, FiniteCommandPort, OperationPointer, OwnerContext,
} from "../orchestration/operation-controller";

/** Already qualified by the existing session reply owner; this wrapper never
 * decodes, authenticates or stores an answer. Receipt and local display are
 * distinct from canonical parent consumption. */
export interface QualifiedAnswerRead<TAnswer> {
  readonly receipt: EffectReceipt;
  readonly answer: TAnswer | null;
}
export interface AwaitingAnswerDependencies<TAnswer> {
  readonly port: FiniteCommandPort;
  readonly readAnswer: (pointer: OperationPointer, signal: AbortSignal) => Promise<QualifiedAnswerRead<TAnswer>>;
  /** Checks current auth, exact selection and target identity. A newer owner
   * continuation key alone must not invalidate this original request. */
  readonly isCurrent: (pointer: OperationPointer) => boolean;
  readonly onAdmission?: (pointer: OperationPointer) => void;
  /** Accepts this detached answer into the current local view only. This is
   * never a canonical ACK or a parent_consumed transition. */
  readonly onAnswer: (pointer: OperationPointer, answer: TAnswer) => boolean | Promise<boolean>;
}

function snapshot(pointer: OperationPointer): OperationPointer {
  return Object.freeze({ operationKey: pointer.operationKey, kind: pointer.kind, targetKey: pointer.targetKey });
}
function unknown(pointer: OperationPointer): EffectReceipt {
  return { ...pointer, disposition: "unknown", reason: "UNKNOWN_RECEIPT" };
}
function exactReceipt(pointer: OperationPointer, raw: unknown): raw is EffectReceipt {
  try {
    if (!raw || typeof raw !== "object" || Array.isArray(raw)) return false;
    const r = raw as Record<string, unknown>;
    if (Object.keys(r).some(k => !["operationKey", "kind", "targetKey", "disposition", "reason"].includes(k))) return false;
    return r.operationKey === pointer.operationKey && r.kind === "message" && pointer.kind === "message" &&
      r.targetKey === pointer.targetKey && typeof r.disposition === "string" && ["accepted", "refused", "unknown"].includes(r.disposition) &&
      (r.reason === undefined || typeof r.reason === "string");
  } catch { return false; }
}

/** Two-phase Office view over the incumbent controller/store. A committed SEND
 * remains nonterminal here until an exactly associated answer is read. The
 * existing OperationController therefore retains its one atomic pointer;
 * reserve, recovery and clearIfEqual keep their original owners. No payload,
 * answer, queue, key, retry or additional persistence is created. */
export function createAwaitingAnswerPort<TAnswer>(deps: AwaitingAnswerDependencies<TAnswer>): FiniteCommandPort {
  const owner = (): OwnerContext | null => {
    try {
      const context = deps.port.context();
      return context && typeof context.principalScope === "string" && context.principalScope.length > 0 &&
        typeof context.generation === "string" && context.generation.length > 0
        ? { principalScope: context.principalScope, generation: context.generation } : null;
    } catch { return null; }
  };
  const owns = (captured: OwnerContext | null, pointer: OperationPointer, signal: AbortSignal): boolean => {
    try {
      const current = owner();
      return !signal.aborted && !!captured && current?.principalScope === captured.principalScope &&
        current.generation === captured.generation && deps.isCurrent(pointer) === true;
    } catch { return false; }
  };
  return {
    context: () => deps.port.context(),
    prepare: (intent: CommandIntent) => deps.port.prepare(intent),
    async submit(original, intent, signal) {
      const pointer = snapshot(original), captured = owner();
      if (pointer.kind !== "message" || !owns(captured, pointer, signal)) return unknown(pointer);
      let receipt: unknown;
      try { receipt = await deps.port.submit(pointer, intent, signal); }
      catch { return unknown(pointer); }
      if (!owns(captured, pointer, signal) || !exactReceipt(pointer, receipt)) return unknown(pointer);
      if (receipt.disposition === "refused") return { ...pointer, disposition: "refused", reason: "REFUSED" };
      if (receipt.disposition === "accepted") {
        try { deps.onAdmission?.(pointer); } catch { return unknown(pointer); }
      }
      // Accepted transport admission is phase one, not the answer. Unknown
      // admission remains the same original request, with no automatic resend.
      return unknown(pointer);
    },
    async readOperation(original, signal) {
      const pointer = snapshot(original), captured = owner();
      if (pointer.kind !== "message" || !owns(captured, pointer, signal)) return unknown(pointer);
      let observed: QualifiedAnswerRead<TAnswer>;
      try { observed = await deps.readAnswer(pointer, signal); }
      catch { return unknown(pointer); }
      if (!owns(captured, pointer, signal) || !observed ||
          !exactReceipt(pointer, observed.receipt) || observed.receipt.disposition !== "accepted" ||
          observed.answer === null || observed.answer === undefined) return unknown(pointer);
      try {
        // An owner may acknowledge only after its actual view commits; a
        // scheduled state update is not a rendered/retained answer. Keep the
        // original hint through this await and recheck owner afterwards.
        if (await deps.onAnswer(pointer, observed.answer) !== true) return unknown(pointer);
      } catch { return unknown(pointer); }
      // A local callback may itself cause selection/auth invalidation.
      if (!owns(captured, pointer, signal)) return unknown(pointer);
      return { ...pointer, disposition: "accepted", reason: "ACCEPTED" };
    },
  };
}
