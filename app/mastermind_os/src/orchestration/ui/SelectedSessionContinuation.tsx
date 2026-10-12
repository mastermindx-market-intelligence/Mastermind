import { useId, useRef, useState } from "react";
import type {
  OperationPointer,
  OperationState,
} from "../operation-controller";

/**
 * Selected-session continuation panel.
 *
 * Presentation only: it shows the host-projected fabric_attempt target and
 * the closed receipt outcome of the dedicated session controller, and it
 * captures the explicit user-entered instruction and completion/stop
 * condition once per submit through the accepted synchronous provider. It
 * never renders transcript, reply text, worker execution, attention delivery
 * or parent consumption — an effect receipt is not proof of any of those —
 * and it offers no Stop control: stop_condition is content, not cancel.
 * Recovery is status-only and always uses the original operation key.
 */

/** Exact accepted Unicode/blank bounds: 1..700 code points, matching the port. */
export const MAX_CONDITION_CODEPOINTS = 700;

export type SessionContinuationOutcome =
  | { status: "accepted" }
  | { status: "refused" };

export interface SelectedSessionContinuationProps {
  /** Host-projected target ref when send is exactly capable; otherwise null. */
  sessionKey: string | null;
  unavailableReason?: string;
  /** Last closed controller state; null before any dispatch this epoch. */
  status: OperationState | null;
  /** Durable retained pointer for this scope, when discovery/hold found one. */
  retainedPointer: OperationPointer | null;
  reading: boolean;
  recoveryRequired?: boolean;
  recovering: boolean;
  /** Owner-side dispatch in flight; never releases the local guard. */
  sending: boolean;
  refusalReason?: string;
  onContinue: (
    instruction: string,
    stopCondition: string,
    onComplete: (outcome: SessionContinuationOutcome) => void,
  ) => void;
  onRecover: () => void;
  /** Explicit context qualification; separate from original-key recovery. */
  onRequalify?: () => void;
}

export function codePointLength(value: string): number {
  return [...value].length;
}

function isTerminal(outcome: unknown): outcome is SessionContinuationOutcome {
  try {
    if (typeof outcome !== "object" || outcome === null || Array.isArray(outcome)) return false;
    const status = Reflect.get(outcome, "status");
    return status === "accepted" || status === "refused";
  } catch {
    return false;
  }
}

export function SelectedSessionContinuation({
  sessionKey,
  unavailableReason,
  status,
  retainedPointer,
  reading,
  recoveryRequired = false,
  recovering,
  sending,
  refusalReason,
  onContinue,
  onRecover,
  onRequalify,
}: SelectedSessionContinuationProps) {
  const formId = useId();
  const instructionId = `${formId}-instruction`;
  const conditionId = `${formId}-condition`;
  const [instruction, setInstruction] = useState("");
  const [condition, setCondition] = useState("");
  const instructionRef = useRef("");
  const conditionRef = useRef("");
  const sentInstructionRef = useRef("");
  const sentConditionRef = useRef("");
  const tokenRef = useRef<number | null>(null);
  const tokenSeq = useRef(0);
  const [inFlight, setInFlight] = useState(false);

  const setField = (which: "instruction" | "condition", value: string) => {
    if (which === "instruction") {
      instructionRef.current = value;
      setInstruction(value);
    } else {
      conditionRef.current = value;
      setCondition(value);
    }
  };

  const complete = (token: number, outcome: unknown) => {
    if (!isTerminal(outcome)) return;
    if (tokenRef.current !== token) return;
    tokenRef.current = null;
    setInFlight(false);
    if (outcome.status === "accepted" &&
        instructionRef.current === sentInstructionRef.current &&
        conditionRef.current === sentConditionRef.current) {
      // Success clears only the exact submitted pair; anything retyped is kept.
      instructionRef.current = "";
      conditionRef.current = "";
      setInstruction("");
      setCondition("");
    }
  };

  const dispatchBusy = sending || inFlight || recovering;
  const instructionPoints = codePointLength(instruction);
  const conditionPoints = codePointLength(condition);
  const instructionValid = instructionPoints >= 1 && instructionPoints <= MAX_CONDITION_CODEPOINTS && instruction.trim().length > 0;
  const conditionValid =
    conditionPoints >= 1 &&
    conditionPoints <= MAX_CONDITION_CODEPOINTS &&
    condition.trim().length > 0;
  const canContinue =
    sessionKey !== null && !unavailableReason && !dispatchBusy && !reading && !retainedPointer && !recoveryRequired && instructionValid && conditionValid;

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    if (!canContinue || tokenRef.current !== null) return;
    const token = ++tokenSeq.current;
    tokenRef.current = token;
    sentInstructionRef.current = instruction;
    sentConditionRef.current = condition;
    setInFlight(true);
    try {
      onContinue(instruction, condition, (outcome) => {
        try {
          complete(token, outcome);
        } catch {
          /* not terminal: stays in flight */
        }
      });
    } catch {
      /* a thrown host callback is not an outcome; the dispatch stays in flight */
    }
  };

  const retained = retainedPointer !== null;
  const outcomeState = status?.status ?? null;
  return (
    <section className="card" aria-label="Selected session continuation">
      <div className="section-title">
        <div>
          <h2>Session continuation</h2>
          <p className="muted">
            Continuation for the exact selected Mission's verified fabric_attempt
            target. A committed receipt is the only shown outcome; it is not
            worker execution, result evidence or parent consumption.
          </p>
        </div>
        <span
          className={`state state-${sessionKey && !unavailableReason ? "available" : "unavailable"}`}
        >
          {sessionKey && !unavailableReason ? "AVAILABLE" : "UNAVAILABLE"}
        </span>
      </div>
          {retained || recoveryRequired ? (
            <div className="unjoined" role="note">
              <b>Retained continuation</b>
              <p>
                Original message reference: <code>{retainedPointer?.operationKey ?? "POINTER_READ_UNAVAILABLE"}</code>. Its
                outcome is unresolved here; status recovery reads that exact
                original key only and never sends again.
              </p>
              <div className="form-actions">
                <button type="button" onClick={onRecover} disabled={recovering || reading}>
                  {recovering ? "Checking…" : "Check status"}
                </button>
              </div>
            </div>
          ) : reading ? (
            <p className="muted">Checking for a retained continuation…</p>
          ) : null}
      {unavailableReason ? (
        <>
          <p className="muted">
            Session continuation is unavailable for the exact selected mission.
          </p>
          <details className="reason-details">
            <summary>Technical details</summary>
            <code>{unavailableReason}</code>
          </details>
          {onRequalify ? (
            <button type="button" onClick={onRequalify}>
              Refresh session capability
            </button>
          ) : null}
        </>
      ) : (
        <>
          <dl>
            <dt>Continuation target</dt>
            <dd>{sessionKey ? <code>{sessionKey}</code> : <code>SESSION_UNAVAILABLE</code>}</dd>
            <dt>Send capability</dt>
            <dd>{sessionKey ? "Exactly one verified target" : "No verified target; nothing is guessed"}</dd>
            <dt>Stop control</dt>
            <dd>Not offered — the completion condition is content, not cancel.</dd>
          </dl>
          {outcomeState === "accepted" && !retained ? (
            <p className="muted">
              Continuation committed. Receipt only — no transcript, worker
              execution or parent consumption is proven by this client.
            </p>
          ) : null}
          {outcomeState === "refused" && !retained ? (
            <p className="muted">
              This invocation was refused before any effect:{" "}
              <code>{status?.reason}</code>
            </p>
          ) : null}
          {refusalReason ? (
            <div className="form-error" role="alert">
              {refusalReason}
            </div>
          ) : null}
          <form onSubmit={submit} noValidate className="session-send-form">
            <div className="form-field">
              <label htmlFor={instructionId}>
                <span>Instruction</span>
                {instructionPoints > MAX_CONDITION_CODEPOINTS && (
                  <span className="field-error">
                    {" "}
                    ({instructionPoints}/{MAX_CONDITION_CODEPOINTS})
                  </span>
                )}
              </label>
              <textarea
                id={instructionId}
                value={instruction}
                onChange={(e) => setField("instruction", e.target.value)}
                rows={3}
                disabled={dispatchBusy}
                aria-invalid={instructionPoints > MAX_CONDITION_CODEPOINTS}
              />
            </div>
            <div className="form-field">
              <label htmlFor={conditionId}>
                <span>Completion condition</span>
                {(conditionPoints > MAX_CONDITION_CODEPOINTS || (conditionPoints > 0 && !conditionValid)) && (
                  <span className="field-error">
                    {" "}
                    ({conditionPoints}/{MAX_CONDITION_CODEPOINTS})
                  </span>
                )}
              </label>
              <textarea
                id={conditionId}
                value={condition}
                onChange={(e) => setField("condition", e.target.value)}
                rows={2}
                placeholder="Explicit completion or stop condition for this continuation"
                disabled={dispatchBusy}
                aria-invalid={conditionPoints > MAX_CONDITION_CODEPOINTS || (conditionPoints > 0 && !conditionValid)}
              />
              <p className="muted">
                Captured once with the instruction when the continuation is
                made; it is never re-evaluated here and authorizes no stop.
              </p>
            </div>
            <div className="form-actions">
              <button type="submit" disabled={!canContinue} className="primary">
                {dispatchBusy ? "Sending…" : "Continue session"}
              </button>
            </div>
          </form>
        </>
      )}
    </section>
  );
}
