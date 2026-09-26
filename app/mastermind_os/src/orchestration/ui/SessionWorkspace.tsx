import { useId, useRef, useState } from "react";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface SessionMessage {
  id: string;
  role: "user" | "assistant" | "activity";
  text: string;
}

/** Explicit terminal outcome of one dispatched send or stop. */
export type SessionOutcome = { status: "accepted" } | { status: "refused" };

/**
 * Correlated completion handle for exactly one dispatched send or stop.
 *
 * Host contract:
 * - Call `onComplete` exactly once with the terminal outcome.
 * - Only an object whose `status` is exactly `"accepted"` or `"refused"` is
 *   terminal. The outcome is validated before any latch, pending, or draft
 *   mutation. Missing, null, array, unknown, non-string, throwing-getter, or
 *   proxy values stay visibly in flight; the same handle remains usable for a
 *   later valid reconciliation and does not throw. Stop uses this same gate.
 * - `"accepted"` on a send clears the submitted draft (only if the draft still
 *   holds the submitted text) and releases the guard. On a stop it simply
 *   releases the guard.
 * - `"refused"` releases the guard and preserves the draft for an explicit
 *   retry. Surface the reason via the `error` prop.
 * - Never calling `onComplete` — a void/lost host — or throwing from the
 *   callback leaves the action visibly in flight and does NOT authorize a
 *   retry. There is no timer-based or inference-based unlock.
 * - The handle is correlated to its own dispatch and to the session in whose
 *   context it was dispatched: it stays valid across rerenders (an owner may
 *   store it and reconcile the same pending action later without a remount),
 *   but after a session switch it is a no-op, so a late promise or receipt for
 *   session A can never complete — or clear a draft in — session B.
 *
 * `sending`, `stopping`, and `error` are display/owner-state inputs only.
 * Neither a pending edge nor a changed error string ever releases a guard.
 */
export type SessionCompletion = (outcome: SessionOutcome) => void;

export interface SessionWorkspaceProps {
  sessionKey: string;
  title: string;
  messages: readonly SessionMessage[];
  observedAt: string | null;
  connection: "connected" | "disconnected" | "unknown";
  coverage: string;
  turnBusy: boolean;
  /** Owner-side pending signal. Disables the form; never releases the guard. */
  sending: boolean;
  unavailableReason?: string;
  error?: string;
  stopLabel?: "Interrupt turn" | "Request stop";
  stopping?: boolean;
  onSend: (text: string, onComplete: SessionCompletion) => void;
  onStop?: (onComplete: SessionCompletion) => void;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/** Conservative UI ceiling for user-supplied message text */
const MAX_TEXT_BYTES = 16384;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Returns the byte length of a UTF-8 string */
function utf8ByteLength(s: string): number {
  return new TextEncoder().encode(s).length;
}

/**
 * Snapshot a terminal status from a completion argument.
 * Reads `status` once; a throw, missing value, array, or any other shape is
 * not terminal. Extra own fields are ignored when status is exact.
 */
function readTerminalStatus(outcome: unknown): "accepted" | "refused" | null {
  try {
    if (typeof outcome !== "object" || outcome === null || Array.isArray(outcome)) {
      return null;
    }
    const status = Reflect.get(outcome, "status");
    if (status === "accepted" || status === "refused") return status;
    return null;
  } catch {
    return null;
  }
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function SessionWorkspace({
  sessionKey,
  title,
  messages,
  observedAt,
  connection,
  coverage,
  turnBusy,
  sending,
  unavailableReason,
  error,
  stopLabel,
  stopping,
  onSend,
  onStop,
}: SessionWorkspaceProps) {
  const formId = useId();
  const sendId = `${formId}-send`;

  // Draft state — preserved until the owner reports a successful send.
  const [draft, setDraft] = useState("");
  const draftRef = useRef("");
  const setDraftText = (next: string) => {
    draftRef.current = next;
    setDraft(next);
  };

  // In-flight actions owned by this component: armed synchronously when the
  // action is dispatched, resolved only by its correlated completion.
  const [sendInFlight, setSendInFlight] = useState(false);
  const [stopInFlight, setStopInFlight] = useState(false);
  // Synchronous duplicate latches and correlation tokens. `null` means idle;
  // a number is the token of the dispatch currently in flight. Each
  // completion closure captures its token, so only the matching dispatch can
  // release its guard — a stale or duplicated completion is a no-op.
  const sendTokenRef = useRef<number | null>(null);
  const stopTokenRef = useRef<number | null>(null);
  const tokenSeqRef = useRef(0);

  const sentTextRef = useRef("");

  const completeSend = (token: number, outcome: unknown) => {
    const status = readTerminalStatus(outcome);
    if (status === null) return;
    if (sendTokenRef.current !== token) return;
    sendTokenRef.current = null;
    setSendInFlight(false);
    if (status === "accepted" && draftRef.current === sentTextRef.current) {
      // Success clears only the text that was actually submitted; anything
      // else in the box is preserved. A refusal keeps the draft.
      setDraftText("");
    }
  };

  const completeStop = (token: number, outcome: unknown) => {
    const status = readTerminalStatus(outcome);
    if (status === null) return;
    if (stopTokenRef.current !== token) return;
    stopTokenRef.current = null;
    setStopInFlight(false);
  };

  // Session identity change: drop local state and every latch, and invalidate
  // every local completion so a late promise/receipt for the previous session
  // cannot resolve or clear anything for the new one. This is a context
  // switch, not a cancellation claim about the previous session.
  const previousSessionKey = useRef(sessionKey);
  if (sessionKey !== previousSessionKey.current) {
    previousSessionKey.current = sessionKey;
    setDraftText("");
    sentTextRef.current = "";
    sendTokenRef.current = null;
    stopTokenRef.current = null;
    setSendInFlight(false);
    setStopInFlight(false);
  }

  const textBytes = utf8ByteLength(draft);
  const textTooLong = textBytes > MAX_TEXT_BYTES;
  const textBlank = draft.trim().length === 0;

  const sendPending = sending || sendInFlight;

  const canSend =
    !unavailableReason &&
    connection === "connected" &&
    !turnBusy &&
    !sendPending &&
    !textBlank &&
    !textTooLong;

  // Stop is offered only when the parent explicitly scopes it.
  const stopPending = !!stopping || stopInFlight;
  const canStop = !!stopLabel && !!onStop && !stopPending;

  const handleSend = (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSend || sendTokenRef.current !== null) return;
    const token = ++tokenSeqRef.current;
    sendTokenRef.current = token;
    sentTextRef.current = draft;
    setSendInFlight(true);
    // Draft is kept until the correlated completion reports the outcome, so a
    // refusal never loses the user's text.
    try {
      onSend(draft, (outcome) => {
        try {
          completeSend(token, outcome);
        } catch {
          // A throw while reading or applying the outcome is not terminal:
          // the send stays in flight and the handle remains usable.
        }
      });
    } catch {
      // A thrown host callback is not an accepted or refused outcome: the
      // send stays visibly in flight and does not authorize a retry.
    }
  };

  const handleStop = () => {
    if (!canStop || stopTokenRef.current !== null) return;
    const token = ++tokenSeqRef.current;
    stopTokenRef.current = token;
    setStopInFlight(true);
    try {
      onStop?.((outcome) => {
        try {
          completeStop(token, outcome);
        } catch {
          // A throw while reading the outcome is not terminal: the stop
          // stays in flight and the handle remains usable.
        }
      });
    } catch {
      // A thrown stop callback is not an outcome: the stop stays visibly in
      // flight and does not authorize a repeat.
    }
  };

  const roleLabel = (role: SessionMessage["role"]): string => {
    switch (role) {
      case "user":
        return "User";
      case "assistant":
        return "Assistant";
      case "activity":
        return "Activity";
    }
  };

  return (
    <section className="card">
      <div className="section-title">
        <div>
          <h2>{title || "Session Workspace"}</h2>
          {!unavailableReason && (
            <p className="muted">
              {connection === "connected"
                ? "Connected"
                : connection === "disconnected"
                  ? "Disconnected"
                  : "Connection unknown"}
              {" · "}
              {coverage}
              {observedAt ? (
                <>
                  {" · "}
                  Observed at{" "}
                  <time dateTime={observedAt}>{observedAt}</time>
                </>
              ) : null}
            </p>
          )}
        </div>
      </div>

      {unavailableReason ? (
        <div className="empty">
          <p>{unavailableReason}</p>
        </div>
      ) : (
        <>
          {/* Message list — React renders text children as inert text */}
          <div className="session-messages" aria-label="Session messages">
            {messages.length === 0 ? (
              <div className="empty">
                <p>No messages in this session.</p>
              </div>
            ) : (
              <ul className="items">
                {messages.map((msg) => (
                  <li key={msg.id}>
                    <span className="message-role">{roleLabel(msg.role)}</span>
                    <span className="message-text">{msg.text}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>

          {/* Error display */}
          {error && (
            <div
              id={`${formId}-error`}
              className="form-error"
              role="alert"
              // tabIndex=-1 so an integrator can focus this element
              tabIndex={-1}
            >
              {error}
            </div>
          )}

          {/* Send form */}
          <form onSubmit={handleSend} noValidate className="session-send-form">
            <div className="form-field">
              <label htmlFor={sendId}>
                <span>Message</span>
                {textTooLong && (
                  <span className="field-error">
                    {" "}
                    ({textBytes}/{MAX_TEXT_BYTES} bytes)
                  </span>
                )}
              </label>
              <textarea
                id={sendId}
                value={draft}
                onChange={(e) => setDraftText(e.target.value)}
                rows={3}
                placeholder={
                  connection !== "connected"
                    ? "Connect to send messages."
                    : turnBusy || sendPending
                      ? "Wait for the current turn to complete."
                      : "Type a message…"
                }
                disabled={connection !== "connected" || turnBusy || sendPending}
                aria-describedby={textTooLong ? `${sendId}-length` : undefined}
                aria-invalid={textTooLong}
              />
              {textTooLong && (
                <p id={`${sendId}-length`} className="field-error" role="alert">
                  Message exceeds the {MAX_TEXT_BYTES} byte UTF-8 ceiling.
                </p>
              )}
            </div>

            <div className="form-actions">
              <button type="submit" disabled={!canSend} className="primary">
                {sendPending ? "Sending…" : "Send"}
              </button>
              {stopLabel && (
                <button type="button" onClick={handleStop} disabled={!canStop}>
                  {stopPending ? "Stopping…" : stopLabel}
                </button>
              )}
            </div>
          </form>

          {/* Disconnected notice */}
          {connection === "disconnected" && (
            <p className="muted disconnected-notice">
              Session is disconnected. Messages cannot be sent until the
              connection is restored.
            </p>
          )}
        </>
      )}
    </section>
  );
}
