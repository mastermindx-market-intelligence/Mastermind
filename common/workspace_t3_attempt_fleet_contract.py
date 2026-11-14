"""Closed public READ envelope for the per-attempt T3 fleet projection.

This contract grants no launch, interrupt, send, retry, thread-read or
native-bridge authority.  The document body is the existing
``mastermind.t3_attempt_fleet/v1`` projection owned by
``control_plane/t3_attempt_fleet_projection.py``; only the read frame and the
envelope shape are defined here.  A typed refusal never carries evidence
content and never becomes a partial projection.
"""
from __future__ import annotations

import re
from datetime import datetime

FLEET_SCHEMA = "mastermind.t3_attempt_fleet/v1"
FRAME_SCHEMA = "mastermind.workspace_t3_attempt_fleet_read.v1"
OPERATION = "t3_attempt_fleet"
MAX_RESPONSE_BYTES = 16_384
MAX_ATTEMPTS = 1  # one attempt per read; the route is per-attempt by design
MAX_NOTES = 8
MAX_NOTE_TOKEN = re.compile(r"[A-Z][A-Z0-9_]{0,63}\Z")

#: Attempt ids are company run ids (``runs/...``) — they CONTAIN ``/`` and so
#: are never valid under the ordinary identifier grammars.  This is the same
#: grammar as the projection's ``ATTEMPT_ID_RE``; it admits run ids, never
#: paths, dot-dots or control characters.
ATTEMPT_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_./:%=-]{0,159}\Z")

#: Closed refusal vocabulary: every typed refusal the projection can raise
#: (``T3AttemptFleetError`` codes, including the per-field validator family the
#: composition applies to its own output), plus the two read-composition
#: refusals (source not installed, source replaced mid-read).  Nothing else may
#: occupy ``refusal``; completeness keeps fail-closed — no raised code can make
#: the refusal envelope itself invalid.
EVIDENCE_REFUSALS = frozenset({
    "ADAPTER_ROW_MALFORMED",
    "ADAPTER_STATE_UNREADABLE",
    "ADAPTER_STATE_SCHEMA_UNKNOWN",
    "ATTEMPT_FIELDS_INVALID",
    "ATTEMPT_ID_INVALID",
    "CENSUS_INVALID",
    "CLOCK_INVALID",
    "DUPLICATE_FIELDS_INVALID",
    "EVIDENCE_FIELDS_INVALID",
    "FRESHNESS_FIELDS_INVALID",
    "FRESHNESS_WINDOW_INVALID",
    "HARNESS_FIELDS_INVALID",
    "IDEMPOTENCY_FIELDS_INVALID",
    "INVARIANT_FIELDS_INVALID",
    "THREAD_FIELDS_INVALID",
    "THREAD_READ_INVALID",
    "TOO_MANY_ATTEMPTS",
})
READ_REFUSALS = frozenset({"SOURCE_UNAVAILABLE", "SOURCE_CHANGED"})
REFUSALS = EVIDENCE_REFUSALS | READ_REFUSALS


def attempt_id(value) -> str:
    """Validate one attempt id (run id grammar) or raise ``ValueError``."""
    if type(value) is not str or ATTEMPT_ID.fullmatch(value) is None:
        raise ValueError("attempt_id_invalid")
    return value


def _utc(value) -> None:
    if type(value) is not str or len(value) > 40 or not value.endswith(("Z", "+00:00")):
        raise ValueError("evaluated_at_invalid")
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if stamp.utcoffset() is None:
        raise ValueError("evaluated_at_invalid")


def validate_frame(frame):
    """Validate the closed read frame ``{schema, operation, selection, principal}``.

    ``selection`` is the attempt id string (run-id grammar above).
    """
    if (type(frame) is not dict
            or frame.get("schema") != FRAME_SCHEMA
            or frame.get("operation") != OPERATION
            or "principal" not in frame
            or set(frame) != {"schema", "operation", "selection", "principal"}):
        raise ValueError("invalid_input")
    attempt_id(frame["selection"])
    return frame


def refusal_document(code: str) -> dict:
    """The fail-closed typed refusal body — never a partial projection."""
    if code not in REFUSALS:
        raise ValueError("refusal_invalid")
    return {"schema": FLEET_SCHEMA, "refusal": code, "attempts": []}


def _notes(value) -> None:
    if (type(value) is not list or len(value) > MAX_NOTES
            or any(type(note) is not str or MAX_NOTE_TOKEN.fullmatch(note) is None
                   for note in value)):
        raise ValueError("notes_invalid")


def validate_document(body, *, attempt_validator=None):
    """Validate the closed envelope of one fleet document.

    Exactly one of ``evaluated_at_utc`` (success) or ``refusal`` (typed
    refusal) is present.  ``attempts`` carries at most one attempt; when a
    ``attempt_validator`` callable is supplied (the projection's
    ``validate_attempt``), every attempt is checked through it so the wire
    envelope and the canonical per-attempt validator agree.
    """
    if type(body) is not dict:
        raise ValueError("document_invalid")
    attempts = body.get("attempts")
    if (type(attempts) is not list or len(attempts) > MAX_ATTEMPTS
            or body.get("schema") != FLEET_SCHEMA):
        raise ValueError("document_invalid")
    if "refusal" in body:
        if (set(body) != {"schema", "refusal", "attempts"}
                or body["refusal"] not in REFUSALS or attempts != []):
            raise ValueError("document_invalid")
        return body
    if set(body) != {"schema", "evaluated_at_utc", "attempts", "notes"}:
        raise ValueError("document_invalid")
    _utc(body["evaluated_at_utc"])
    _notes(body["notes"])
    if attempt_validator is not None:
        for attempt in attempts:
            attempt_validator(attempt)
    return body
