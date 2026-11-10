"""Closed public READ envelope for the per-attempt execution-return delivery.

This contract grants no delivery, retry, transport, admission or placement
authority.  The document body projects the ONE persisted
``EXECUTION_RETURN_DELIVERY`` events row the seam
(``control_plane/execution_return_wiring.py``) writes per attempt, keyed by the
deterministic command id ``execution-return:{attempt_id}``.  Only the read
frame, the envelope shape and their validators are defined here; the receipt
vocabulary is owned by ``control_plane/execution_return_projection.py`` and the
v1.2 ``original_requester`` block by ``control_plane/child_execution_contracts.py``
— both are mirrored closed below, never re-invented.

The served document pairs the receipt facts with a two-field availability
envelope so ONE authenticated GET can carry every honest state::

    {
      "schema": "mastermind.execution_return_read/v1",
      "availability": "AVAILABLE" | "UNAVAILABLE",
      "reason": null | "<TOKEN>",
      "attempt_id": "<run id>",
      "job_id": "JOB-<n>" | null,
      "delivery": <receipt mapping verbatim> | null,
      "stage": "<stage token>" | null,
      "refusal_detail": "<text>" | null,
      "original_requester": <v1.2 block> | null,
      "read_at_utc": "<ISO-8601 UTC>"
    }

``job_id`` is the attempt's owning Executive job id, taken verbatim from the
persisted event row's ``job_id`` column (the seam writes ``job.job_id`` on
every receipt row) — read-only provenance, never invented.  The result
reference a Paperclip tab needs is the receipt's own ``transport_ref`` field
inside ``delivery`` (the deliverable locator the deliverer recorded); the
document never fabricates one when the receipt carries none.

``AVAILABLE`` always carries ``null`` reason and the receipt verbatim;
``UNAVAILABLE`` always carries a closed reason token and null facts — an
honest absence (no receipt recorded) or a typed refusal (unreadable store,
malformed receipt payload) is never a partial projection and never an error.
"""
from __future__ import annotations

import re
from datetime import datetime

READ_SCHEMA = "mastermind.execution_return_read/v1"
FRAME_SCHEMA = "mastermind.workspace_execution_return_read.v1"
OPERATION = "execution_return"
#: Same response ceiling law as the sibling fleet/thread read contracts.
MAX_RESPONSE_BYTES = 16_384

#: Attempt ids are company run ids (``runs/...``) — they CONTAIN ``/`` and so
#: are never valid under the ordinary identifier grammars.  This is byte-for-
#: byte the fleet contract's grammar (and the projection's ``ATTEMPT_ID_RE``):
#: it admits run ids, never paths, dot-dots or control characters.
ATTEMPT_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_./:%=-]{0,159}\Z")

#: Executive job ids (``JOB-<n>``) — byte-for-byte the installed grammar
#: (``common/executive_workspace_contract.py`` ``_JOB_ID_RE_V2``).
JOB_ID = re.compile(r"JOB-[0-9]{1,9}\Z")

#: The delivery receipt wire schema (owner:
#: ``control_plane.execution_return_projection`` — mirrored, not re-invented).
DELIVERY_SCHEMA = "mastermind.execution_return_delivery/v1"

#: Closed delivery receipt states (owner: ``execution_return_projection``).
DELIVERY_STATES = frozenset({"delivered", "unknown", "refused"})

AVAILABILITIES = frozenset({"AVAILABLE", "UNAVAILABLE"})

#: Closed absence/refusal vocabulary.  ``EXECUTION_RETURN_NOT_RECORDED`` is
#: the honest unknown (no receipt event exists for the attempt);
#: ``STORE_READ_FAILED`` names an unreadable store; ``RECEIPT_PAYLOAD_MALFORMED``
#: names a receipt row that is not the closed seam payload (never served
#: partially); ``SOURCE_*`` are the transport refusals the frame handler raises
#: when the installed source is absent or swapped mid-read.
REASONS = frozenset({
    "EXECUTION_RETURN_NOT_RECORDED",
    "STORE_READ_FAILED",
    "RECEIPT_PAYLOAD_MALFORMED",
    "SOURCE_UNAVAILABLE",
    "SOURCE_CHANGED",
})

#: The v1.2 ``original_requester`` block fields (owner:
#: ``control_plane.child_execution_contracts`` ``OriginalRequesterBinding``).
#: References only — the authenticated namespace is joined at settlement and
#: is never part of this persisted block.
REQUESTER_KEYS = frozenset({
    "teammate_id", "conversation_id", "project_id", "carrier_kind",
})

DOCUMENT_KEYS = frozenset({
    "schema", "availability", "reason", "attempt_id", "job_id", "delivery",
    "stage", "refusal_detail", "original_requester", "read_at_utc",
})

_REASON_TOKEN = re.compile(r"[A-Z][A-Z0-9_]{0,63}\Z")
_RECEIPT_KEY = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,63}\Z")
_MAX_RECEIPT_FIELDS = 24
_MAX_RECEIPT_TEXT = 512
_MAX_DETAIL_TEXT = 512
_MAX_STAGE_TOKEN = 64


def attempt_id(value) -> str:
    """Validate one attempt id (run id grammar) or raise ``ValueError``."""
    if type(value) is not str or ATTEMPT_ID.fullmatch(value) is None:
        raise ValueError("attempt_id_invalid")
    return value


def job_id(value) -> str:
    """Validate one Executive job id (``JOB-<n>``) or raise ``ValueError``."""
    if type(value) is not str or JOB_ID.fullmatch(value) is None:
        raise ValueError("job_id_invalid")
    return value


def _read_at(value, code="invalid_read_at") -> None:
    if type(value) is not str or len(value) > 40 or not value.endswith(("Z", "+00:00")):
        raise ValueError(code)
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if stamp.utcoffset() is None:
        raise ValueError(code)


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


def validate_delivery(receipt):
    """Validate one persisted delivery receipt, verbatim but closed.

    The receipt is a FLAT mapping (the seam and the hermes deliverer both
    write flat string fields); every field is preserved byte-for-byte — this
    validator only proves the receipt is bounded and carries the receipt
    schema plus a state from the closed vocabulary.  Anything else is a typed
    refusal at the read owner, never a partially-served receipt.
    """
    if type(receipt) is not dict or not receipt or len(receipt) > _MAX_RECEIPT_FIELDS:
        raise ValueError("delivery_invalid")
    for key, value in receipt.items():
        if type(key) is not str or _RECEIPT_KEY.fullmatch(key) is None:
            raise ValueError("delivery_invalid")
        if value is None:
            continue
        if type(value) is bool:
            continue
        if type(value) is str:
            if (len(value) > _MAX_RECEIPT_TEXT
                    or any(ord(char) < 32 or ord(char) == 127 for char in value)):
                raise ValueError("delivery_invalid")
            continue
        raise ValueError("delivery_invalid")
    if receipt.get("schema") != DELIVERY_SCHEMA:
        raise ValueError("delivery_invalid")
    if receipt.get("state") not in DELIVERY_STATES:
        raise ValueError("delivery_invalid")
    return receipt


def validate_requester(block):
    """Validate one v1.2 ``original_requester`` block or return ``None``.

    The block is the persisted ``OriginalRequesterBinding`` dict: the three
    required bounded identifiers plus the optional ``carrier_kind``.  A block
    that is not exactly that closed shape is not projected (``None``) — the
    join is honest or absent, never guessed.
    """
    if type(block) is not dict:
        return None
    if not set(block) <= REQUESTER_KEYS:
        return None
    for field in ("teammate_id", "conversation_id", "project_id"):
        value = block.get(field)
        if (type(value) is not str or not value or len(value) > 256
                or any(ord(char) < 32 or ord(char) == 127 for char in value)):
            return None
    carrier = block.get("carrier_kind", "")
    if carrier is None:
        carrier = ""
    if (type(carrier) is not str or len(carrier) > 256
            or any(ord(char) < 32 or ord(char) == 127 for char in carrier)):
        return None
    projected = {
        "teammate_id": block["teammate_id"],
        "conversation_id": block["conversation_id"],
        "project_id": block["project_id"],
        "carrier_kind": carrier,
    }
    return projected


def unavailable(attempt_id_value: str, reason: str, read_at_utc: str) -> dict:
    """The honest absence / typed refusal document — never a partial receipt."""
    attempt_id(attempt_id_value)
    if reason not in REASONS or _REASON_TOKEN.fullmatch(reason) is None:
        raise ValueError("reason_invalid")
    _read_at(read_at_utc)
    return {
        "schema": READ_SCHEMA,
        "availability": "UNAVAILABLE",
        "reason": reason,
        "attempt_id": attempt_id_value,
        "job_id": None,
        "delivery": None,
        "stage": None,
        "refusal_detail": None,
        "original_requester": None,
        "read_at_utc": read_at_utc,
    }


def available(attempt_id_value: str, *, job_id_value=None, delivery, stage,
              refusal_detail, original_requester, read_at_utc: str) -> dict:
    """The available receipt document, validated closed before it is served.

    ``job_id_value`` is the owning Executive job id from the persisted event
    row; ``None`` when the row's column is not a valid job id — an honest
    absence, never a reason to poison the receipt projection.
    """
    document = {
        "schema": READ_SCHEMA,
        "availability": "AVAILABLE",
        "reason": None,
        "attempt_id": attempt_id(attempt_id_value),
        "job_id": None if job_id_value is None else job_id(job_id_value),
        "delivery": validate_delivery(delivery),
        "stage": stage,
        "refusal_detail": refusal_detail,
        "original_requester": original_requester,
        "read_at_utc": read_at_utc,
    }
    return validate_document(document)


def validate_document(document):
    """Validate the closed read document (see the module docstring shape)."""
    if type(document) is not dict or set(document) != DOCUMENT_KEYS:
        raise ValueError("document_invalid")
    if document["schema"] != READ_SCHEMA:
        raise ValueError("document_invalid")
    attempt_id(document["attempt_id"])
    _read_at(document["read_at_utc"])
    if document["availability"] not in AVAILABILITIES:
        raise ValueError("document_invalid")
    if document["job_id"] is not None:
        job_id(document["job_id"])
    if document["availability"] == "UNAVAILABLE":
        if (document["reason"] not in REASONS
                or document["job_id"] is not None
                or document["delivery"] is not None
                or document["stage"] is not None
                or document["refusal_detail"] is not None
                or document["original_requester"] is not None):
            raise ValueError("document_invalid")
        return document
    if document["reason"] is not None:
        raise ValueError("document_invalid")
    validate_delivery(document["delivery"])
    stage = document["stage"]
    if stage is not None and (type(stage) is not str or len(stage) > _MAX_STAGE_TOKEN
                              or any(ord(c) < 32 or ord(c) == 127 for c in stage)):
        raise ValueError("document_invalid")
    detail = document["refusal_detail"]
    if detail is not None and (type(detail) is not str or len(detail) > _MAX_DETAIL_TEXT
                               or any(ord(c) < 32 or ord(c) == 127 for c in detail)):
        raise ValueError("document_invalid")
    if document["original_requester"] is not None:
        validate_requester(document["original_requester"])
    return document
