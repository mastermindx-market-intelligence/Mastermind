import { useEffect, useId, useRef, useState } from "react";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface SessionMessage {
  id: string;
  role: "user" | "assistant" | "activity";
  text: string;
}

export interface SessionWorkspaceProps {
  sessionKey: string;
  title: string;
  messages: readonly SessionMessage[];
  observedAt: string | null;
  connection: "connected" | "disconnected" | "unknown";
  coverage: string;
  turnBusy: boolean;
  sending: boolean;
  unavailableReason?: string;
  error?: string;
  stopLabel?: "Interrupt turn" | "Request stop";
  stopping?: boolean;
  onSend: (text: string) => void;
  onStop?: () => void;
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

  // Duplicate guards, one per outward action: armed when the action fires and
  // released only by an observed owner signal (pending true->false cycle, or a
  // changed error signal = refused outcome). Never by a timer, so a duplicate
  // cannot slip through between event ticks before the owner makes progress.
  const sendLatchRef = useRef(false);
  const sentTextRef = useRef("");
  const stopLatchRef = useRef(false);
  const prevOwnerRef = useRef({ sending, stopping: !!stopping, error });

  useEffect(() => {
    const prev = prevOwnerRef.current;
    prevOwnerRef.current = { sending, stopping: !!stopping, error };
    const errorChanged = error !== prev.error;
    if (prev.sending && !sending) {
      // Owner completed the send cycle: release the latch, and only now drop
      // the sent draft. An error on that cycle means the text is preserved.
      sendLatchRef.current = false;
      if (!error && draftRef.current === sentTextRef.current) setDraftText("");
    } else if (errorChanged) {
      sendLatchRef.current = false;
    }
    if ((prev.stopping && !stopping) || errorChanged) stopLatchRef.current = false;
  });

  // Session identity change: drop local state and every latch. This is a
  // context switch, not a cancellation claim about the previous session.
  const previousSessionKey = useRef(sessionKey);
  if (sessionKey !== previousSessionKey.current) {
    previousSessionKey.current = sessionKey;
    setDraftText("");
    sentTextRef.current = "";
    sendLatchRef.current = false;
    stopLatchRef.current = false;
    prevOwnerRef.current = { sending, stopping: !!stopping, error };
  }

  const textBytes = utf8ByteLength(draft);
  const textTooLong = textBytes > MAX_TEXT_BYTES;
  const textBlank = draft.trim().length === 0;

  const canSend =
    !unavailableReason &&
    connection === "connected" &&
    !turnBusy &&
    !sending &&
    !textBlank &&
    !textTooLong;

  // Stop is offered only when the parent explicitly scopes it.
  const canStop = !!stopLabel && !!onStop && !stopping;

  const handleSend = (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSend || sendLatchRef.current) return;
    sendLatchRef.current = true;
    sentTextRef.current = draft;
    // Draft is kept until the owner reports the completed cycle, so an error
    // never loses the user's text.
    onSend(draft);
  };

  const handleStop = () => {
    if (!canStop || stopLatchRef.current) return;
    stopLatchRef.current = true;
    onStop();
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
                    : turnBusy || sending
                      ? "Wait for the current turn to complete."
                      : "Type a message…"
                }
                disabled={connection !== "connected" || turnBusy || sending}
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
                {sending ? "Sending…" : "Send"}
              </button>
              {stopLabel && (
                <button type="button" onClick={handleStop} disabled={!canStop}>
                  {stopping ? "Stopping…" : stopLabel}
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
