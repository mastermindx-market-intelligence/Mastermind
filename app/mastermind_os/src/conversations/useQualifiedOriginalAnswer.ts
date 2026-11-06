import { useEffect, useRef, useState } from "react";
import type { OperationPointer } from "../orchestration/operation-controller";
import type { QualifiedSessionAnswer } from "../orchestration/executive-session-command-port";
import type { QualifiedConversationReply } from "./ConversationWindow";

/**
 * In-memory presentation of ONE current original answer.
 *
 * The existing OperationController/IndexedDB store owns the only durable
 * operation pointer. The trusted native session port owns validation.
 * This hook owns neither authority nor an answer history: it admits a
 * bounded reply only after the actual ConversationWindow commits the view.
 */
export interface QualifiedAnswerOwner {
  readonly binding: object;
  readonly principalScope: string;
  readonly generation: string;
  readonly selectionSeq: number;
  readonly authRevision: number;
}

type CurrentView = QualifiedAnswerOwner & {
  readonly active: boolean;
};

export interface CurrentQualifiedAnswer extends QualifiedConversationReply, QualifiedAnswerOwner {}

function identityMatches(a: QualifiedAnswerOwner, b: QualifiedAnswerOwner | null): boolean {
  return b !== null && a.binding === b.binding &&
    a.principalScope === b.principalScope &&
    a.generation === b.generation &&
    a.selectionSeq === b.selectionSeq &&
    a.authRevision === b.authRevision;
}

function sameAnswer(a: QualifiedConversationReply, pointer: OperationPointer,
                    answer: QualifiedSessionAnswer): boolean {
  return a.pointer.operationKey === pointer.operationKey &&
    a.pointer.targetKey === pointer.targetKey &&
    a.pointer.kind === pointer.kind &&
    a.answer.text === answer.text &&
    a.answer.nextStep === answer.nextStep &&
    a.answer.readRef === answer.readRef &&
    a.answer.parentConsumed === false &&
    answer.parentConsumed === false;
}

export function useQualifiedOriginalAnswer() {
  const [view, setView] = useState<CurrentQualifiedAnswer | null>(null);
  const [, refreshVisibility] = useState(0);
  const staged = useRef<CurrentQualifiedAnswer | null>(null);
  const committed = useRef<CurrentQualifiedAnswer | null>(null);
  const current = useRef<CurrentView | null>(null);
  const pending = useRef<{
    value: CurrentQualifiedAnswer;
    promise: Promise<boolean>;
    settle: (accepted: boolean) => void;
  } | null>(null);

  const invalidate = () => {
    pending.current?.settle(false);
    pending.current = null;
    const had = staged.current !== null;
    staged.current = null;
    committed.current = null;
    if (had) setView(null);
  };

  useEffect(() => () => {
    pending.current?.settle(false);
    pending.current = null;
    staged.current = null;
    committed.current = null;
  }, []);

  // Route navigation is not an authority change. A view already accepted
  // under the same auth/selection remains locally available when the user
  // returns; only an in-flight, unrendered publication must be withdrawn.
  const leavePresentation = () => {
    if (pending.current !== null) invalidate();
  };
  const setCurrent = (value: CurrentView | null) => {
    const previous = current.current;
    current.current = value;
    // The shell commits its active route in layout phase, never during an
    // uncommitted React render. Re-entering an already-accepted view needs
    // one committed repaint after that owner/route transition.
    if (previous?.active === false && value?.active === true &&
        staged.current !== null && committed.current === staged.current) {
      refreshVisibility(n => n + 1);
    }
  };
  const matches = (owner: QualifiedAnswerOwner) =>
    identityMatches(owner, current.current) && current.current?.active === true;

  const stage = (owner: QualifiedAnswerOwner,
                 pointer: OperationPointer, answer: QualifiedSessionAnswer): Promise<boolean> => {
    if (!matches(owner) || pointer.kind !== "message" || answer.parentConsumed !== false) {
      return Promise.resolve(false);
    }
    const existing = staged.current;
    if (existing) {
      if (!identityMatches(existing, owner) || !sameAnswer(existing, pointer, answer)) {
        // Different answer for the same operation is never an append or a
        // replacement. The existing owner must invalidate before a new SEND.
        return Promise.resolve(false);
      }
      if (committed.current === existing) return Promise.resolve(true);
      return pending.current?.value === existing ? pending.current.promise : Promise.resolve(false);
    }
    const value: CurrentQualifiedAnswer = Object.freeze({
      ...owner,
      pointer: Object.freeze({ ...pointer }),
      answer: Object.freeze({ ...answer }),
    });
    let settle!: (accepted: boolean) => void;
    const promise = new Promise<boolean>(resolve => { settle = resolve; });
    pending.current = { value, promise, settle };
    staged.current = value;
    setView(value);
    return promise;
  };

  const acknowledgeRender = (candidate: QualifiedConversationReply) => {
    const currentValue = staged.current;
    if (!currentValue || candidate !== currentValue || !matches(currentValue)) return;
    const hold = pending.current;
    if (hold?.value !== currentValue) return;
    committed.current = currentValue;
    pending.current = null;
    hold.settle(true);
  };

  const visible = (owner: QualifiedAnswerOwner | null): CurrentQualifiedAnswer | null =>
    view && identityMatches(view, owner) && matches(view) ? view : null;

  return { setCurrent, isCurrent: matches, invalidate, leavePresentation,
    stage, acknowledgeRender, visible };
}
