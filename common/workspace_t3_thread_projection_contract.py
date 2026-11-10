"""Closed public READ frame for the T3 thread-list projection.

The UI's frozen, fail-closed parser lives in
``app/mastermind_os/src/code/t3-thread-projection.ts``.  Its projection list is
``{schema, threads:[<=64 rows]}`` where each row is exactly the eight frozen
fields ``threadId``, ``environment``, ``title``, ``runState``, ``lastActivity``,
``prLink``, ``repository`` and ``companyManaged`` — no ``schema`` key rides on a
row (the TS parser injects the row ``schema`` itself and rejects any extra key),
so this wire never adds one.

The TS read union ``T3ProjectionRead`` can also be ``UNAVAILABLE{reason}``.  To
carry that state over ONE authenticated GET (as this route must), the served
document pairs the frozen list with a two-field read envelope::

    {
      "schema": "mastermind.t3_thread_projection_list.v1",
      "availability": "AVAILABLE" | "UNAVAILABLE",
      "reason": null | "<TOKEN>",
      "threads": [ <frozen T3ThreadProjection rows> ]
    }

``threads`` is byte-for-byte the frozen projection list, so it parses unchanged
under the UI parser once de-enveloped.  ``AVAILABLE`` always carries ``null``
reason; ``UNAVAILABLE`` always carries a closed reason token and an empty
``threads`` list — a typed refusal or honest absence is never a partial
projection.

This contract grants no launch, interrupt, send, retry, thread-read, bridge,
admission or placement authority.  It owns only the closed wire shape and its
validators; ``control_plane/workspace_t3_thread_projection_read.py`` owns the
read composition and never invents a fact this frame can carry.
"""
from __future__ import annotations

import re
from datetime import datetime

LIST_SCHEMA = "mastermind.t3_thread_projection_list.v1"
ROW_SCHEMA = "mastermind.t3_thread_projection.v1"
FRAME_SCHEMA = "mastermind.workspace_t3_thread_projection_read.v1"
OPERATION = "t3_thread_projection"
MAX_THREADS = 64
MAX_RESPONSE_BYTES = 65_536

#: UI run-state vocabulary (closed).  ``blocked`` is admitted for future
#: evidence sources; the durable-adapter projection never emits it because no
#: persisted adapter status honestly distinguishes an approval-blocked run.
RUN_STATES = frozenset({"running", "idle", "blocked", "unknown"})

AVAILABILITIES = frozenset({"AVAILABLE", "UNAVAILABLE"})

#: Closed refusal/absence vocabulary.  Every code the read owner can surface
#: is listed here so a typed refusal can never invalidate the envelope itself.
#: ``T3_ENVIRONMENT_SOURCE_UNAVAILABLE`` names the missing environment fact
#: source (never a defaulted environment id); the ``ADAPTER_*`` codes mirror the
#: incumbent adapter-state read; ``THREADS_OVER_CAP`` refuses an over-cap list
#: instead of truncating; the ``SOURCE_*`` codes are the transport refusals the
#: frame handler raises when the installed source is absent or swapped.
REASONS = frozenset({
    "T3_ENVIRONMENT_SOURCE_UNAVAILABLE",
    "ADAPTER_STATE_UNREADABLE",
    "ADAPTER_STATE_SCHEMA_UNKNOWN",
    "ADAPTER_ROW_MALFORMED",
    "THREADS_OVER_CAP",
    "RESPONSE_OVER_BUDGET",
    "SOURCE_UNAVAILABLE",
    "SOURCE_CHANGED",
})
_REASON_TOKEN = re.compile(r"[A-Z][A-Z0-9_]{0,63}\Z")

#: Frozen field grammars, mirrored byte-for-byte from the TS parser.
THREAD_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")
ENVIRONMENT_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z")
ISO_8601 = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})\Z"
)
HTTPS_URL = re.compile(r"https://[A-Za-z0-9.-]+(:[0-9]+)?(/[^\s\"<>]*)?\Z")

#: Exact frozen row field set (order-independent) and document field set.
ROW_KEYS = frozenset({
    "threadId", "environment", "title", "runState",
    "lastActivity", "prLink", "repository", "companyManaged",
})
DOCUMENT_KEYS = frozenset({"schema", "availability", "reason", "threads"})


def _text(value, maximum, code):
    if type(value) is not str or not 1 <= len(value) <= maximum:
        raise ValueError(code)
    return value


def _optional_text(value, maximum, code):
    if value is None:
        return None
    return _text(value, maximum, code)


def _iso(value):
    if type(value) is not str or len(value) > 40 or ISO_8601.fullmatch(value) is None:
        raise ValueError("invalid_last_activity")
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if stamp.utcoffset() is None:
        raise ValueError("invalid_last_activity")
    return value


def _https(value):
    if type(value) is not str or len(value) > 512 or HTTPS_URL.fullmatch(value) is None:
        raise ValueError("invalid_pr_link")
    return value


def thread_id(value):
    """Validate one ``threadId`` (frozen grammar) or raise ``ValueError``."""
    if type(value) is not str or THREAD_ID.fullmatch(value) is None:
        raise ValueError("invalid_thread_id")
    return value


def environment_id(value):
    """Validate one ``environment`` (frozen grammar) or raise ``ValueError``."""
    if type(value) is not str or ENVIRONMENT_ID.fullmatch(value) is None:
        raise ValueError("invalid_environment_id")
    return value


def validate_row(row):
    """Validate one closed projection row, exactly the frozen eight fields."""
    if type(row) is not dict or set(row) != ROW_KEYS:
        raise ValueError("invalid_row")
    thread_id(row["threadId"])
    environment_id(row["environment"])
    _optional_text(row["title"], 240, "invalid_title")
    if row["runState"] not in RUN_STATES:
        raise ValueError("invalid_run_state")
    if row["lastActivity"] is not None:
        _iso(row["lastActivity"])
    if row["prLink"] is not None:
        _https(row["prLink"])
    _optional_text(row["repository"], 240, "invalid_repository")
    if type(row["companyManaged"]) is not bool:
        raise ValueError("invalid_company_managed")
    return row


def validate_document(document):
    """Validate the closed read document ``{schema, availability, reason, threads}``."""
    if type(document) is not dict or set(document) != DOCUMENT_KEYS:
        raise ValueError("invalid_document")
    if document["schema"] != LIST_SCHEMA:
        raise ValueError("invalid_document")
    availability = document["availability"]
    if availability not in AVAILABILITIES:
        raise ValueError("invalid_document")
    threads = document["threads"]
    if type(threads) is not list:
        raise ValueError("invalid_document")
    if availability == "UNAVAILABLE":
        if document["reason"] not in REASONS or threads != []:
            raise ValueError("invalid_document")
        return document
    if document["reason"] is not None:
        raise ValueError("invalid_document")
    if len(threads) > MAX_THREADS:
        raise ValueError("invalid_document")
    identities = set()
    for row in threads:
        validate_row(row)
        identity = (row["environment"], row["threadId"])
        if identity in identities:
            raise ValueError("invalid_document")
        identities.add(identity)
    return document


def validate_frame(frame):
    """Validate the fixed no-selection read frame ``{schema, operation, selection, principal}``."""
    if (type(frame) is not dict
            or frame.get("schema") != FRAME_SCHEMA
            or frame.get("operation") != OPERATION
            or frame.get("selection") is not None
            or "principal" not in frame
            or set(frame) != {"schema", "operation", "selection", "principal"}):
        raise ValueError("invalid_input")
    return frame


def unavailable(reason):
    """The honest absence/refusal document — never a partial projection."""
    if reason not in REASONS:
        raise ValueError("invalid_reason")
    return {"schema": LIST_SCHEMA, "availability": "UNAVAILABLE",
            "reason": reason, "threads": []}


def available(threads):
    """The available projection document, validated closed before it is served."""
    return validate_document({
        "schema": LIST_SCHEMA,
        "availability": "AVAILABLE",
        "reason": None,
        "threads": list(threads),
    })
