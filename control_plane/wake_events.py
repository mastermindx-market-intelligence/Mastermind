"""Canonical Executive Wake Event envelope — typed, versioned, fail-closed.

A WAKE event is a *notification contract*, not a Job, Attempt, lease, or
command.  Executive OS SQLite remains the sole lifecycle authority.  This
module mints and validates envelopes; it never writes a database, never
schedules work, and never executes a provider.

Identity
--------
``event_id`` is content-addressed, not a random UUID::

    WAKE- + sha256(canonical identity tuple)[:32]

The identity tuple is ``schema``, ``event_type``, ``job_id``, ``attempt_id``,
``project_id``, ``target_seat``, ``session_alias``, ``reason_code``.
``created_at`` is recorded on the envelope and excluded from the hash so a
replay of the same lifecycle fact reconstructs the same ``WAKE-*`` id.

That id is shaped to fit Executive OS ``events.command_id``
(``^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$``).  PR-2 is expected to persist a wake
by using this id as ``command_id``; the UNIQUE index is then the durable
idempotency mechanism.  This module does not perform that write.

No executable command, argv, authority grant, or model-authored field is part
of the schema.  Extra keys fail closed.  Evidence is references (``JOB-*``,
``ATT-*``), never copied transcripts.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import re
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping, Sequence


SCHEMA = "mastermind.wake_event.v1"
EVENT_ID_PREFIX = "WAKE-"
IDENTITY_HEX_LEN = 32
MAX_EVIDENCE_REFS = 8

JOB_ID_RE = re.compile(r"^JOB-\d{3,}$")
ATTEMPT_ID_RE = re.compile(r"^ATT-[0-9a-f]{32}$")
WAKE_ID_RE = re.compile(rf"^{EVENT_ID_PREFIX}[0-9a-f]{{{IDENTITY_HEX_LEN}}}$")
SESSION_ALIAS_RE = re.compile(r"^[A-Z][A-Z0-9]*(-[A-Z0-9]+)+$")
PROJECT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$")
ISO_UTC_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]00:00)$"
)

SEATS = frozenset({"ceo", "coo"})
REASON_CODES = frozenset(
    {
        "worker_completion_requires_review",
        "revision_completed_requires_review",
        "architectural_contradiction",
        "strategic_ambiguity",
        "mandate_change",
    }
)
ENVELOPE_KEYS = frozenset(
    {
        "schema",
        "event_id",
        "event_type",
        "created_at",
        "project_id",
        "job_id",
        "attempt_id",
        "target_seat",
        "session_alias",
        "reason_code",
        "evidence_refs",
    }
)
FORBIDDEN_KEYS = frozenset(
    {
        "command",
        "argv",
        "executable",
        "authority",
        "requested_authorities",
        "validation_commands",
        "actor",
        "next_actions",
        "prompt",
        "instructions",
        "session_title",
        "external_handle",
    }
)


class WakeEventError(ValueError):
    """The wake envelope is missing, malformed, or outside the closed vocabulary."""


class WakeEventType(str, Enum):
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    REVISION_COMPLETED = "REVISION_COMPLETED"
    ARCHITECTURAL_CONTRADICTION = "ARCHITECTURAL_CONTRADICTION"
    STRATEGIC_AMBIGUITY = "STRATEGIC_AMBIGUITY"
    MANDATE_CHANGE = "MANDATE_CHANGE"


def canonical_json_bytes(value: Any) -> bytes:
    """Stable UTF-8 JSON used only for identity hashing."""

    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")


def mint_wake_event_id(
    *,
    event_type: str | WakeEventType,
    job_id: str,
    attempt_id: str | None,
    project_id: str | None,
    target_seat: str,
    session_alias: str,
    reason_code: str,
) -> str:
    """Return the content-addressed ``WAKE-*`` id for one identity tuple."""

    identity = {
        "schema": SCHEMA,
        "event_type": _event_type(event_type).value,
        "job_id": _job_id(job_id),
        "attempt_id": _optional_attempt_id(attempt_id),
        "project_id": _optional_project_id(project_id),
        "target_seat": _seat(target_seat),
        "session_alias": _session_alias(session_alias),
        "reason_code": _reason_code(reason_code),
    }
    digest = hashlib.sha256(canonical_json_bytes(identity)).hexdigest()
    return f"{EVENT_ID_PREFIX}{digest[:IDENTITY_HEX_LEN]}"


def utc_now_iso(now: datetime | None = None) -> str:
    stamp = now if now is not None else datetime.now(timezone.utc)
    if stamp.tzinfo is None:
        raise WakeEventError("created_at must be timezone-aware UTC")
    stamp = stamp.astimezone(timezone.utc).replace(microsecond=0)
    return stamp.strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclasses.dataclass(frozen=True)
class WakeEvent:
    """Versioned wake envelope.  Construct through :func:`mint_wake_event`."""

    schema: str
    event_id: str
    event_type: WakeEventType
    created_at: str
    project_id: str | None
    job_id: str
    attempt_id: str | None
    target_seat: str
    session_alias: str
    reason_code: str
    evidence_refs: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "created_at": self.created_at,
            "project_id": self.project_id,
            "job_id": self.job_id,
            "attempt_id": self.attempt_id,
            "target_seat": self.target_seat,
            "session_alias": self.session_alias,
            "reason_code": self.reason_code,
            "evidence_refs": list(self.evidence_refs),
        }


def mint_wake_event(
    *,
    event_type: str | WakeEventType,
    job_id: str,
    target_seat: str,
    session_alias: str,
    reason_code: str,
    attempt_id: str | None = None,
    project_id: str | None = None,
    created_at: str | None = None,
    evidence_refs: Sequence[str] | None = None,
) -> WakeEvent:
    """Build a valid envelope.  Unknown or extra authority-bearing fields never enter."""

    resolved_type = _event_type(event_type)
    resolved_job = _job_id(job_id)
    resolved_attempt = _optional_attempt_id(attempt_id)
    resolved_project = _optional_project_id(project_id)
    resolved_seat = _seat(target_seat)
    resolved_alias = _session_alias(session_alias)
    resolved_reason = _reason_code(reason_code)
    resolved_created = _created_at(created_at)
    expected_evidence = _derive_evidence_refs(resolved_job, resolved_attempt)
    if evidence_refs is not None:
        supplied = _evidence_refs(evidence_refs)
        if supplied != expected_evidence:
            raise WakeEventError(
                "evidence_refs must be exactly the job and attempt identifiers"
            )
    event_id = mint_wake_event_id(
        event_type=resolved_type,
        job_id=resolved_job,
        attempt_id=resolved_attempt,
        project_id=resolved_project,
        target_seat=resolved_seat,
        session_alias=resolved_alias,
        reason_code=resolved_reason,
    )
    return WakeEvent(
        schema=SCHEMA,
        event_id=event_id,
        event_type=resolved_type,
        created_at=resolved_created,
        project_id=resolved_project,
        job_id=resolved_job,
        attempt_id=resolved_attempt,
        target_seat=resolved_seat,
        session_alias=resolved_alias,
        reason_code=resolved_reason,
        evidence_refs=expected_evidence,
    )


def parse_wake_event(value: Mapping[str, Any]) -> WakeEvent:
    """Validate a mapping fail-closed.  Extra keys and forbidden keys refuse."""

    if not isinstance(value, Mapping):
        raise WakeEventError("wake event must be a mapping")
    keys = set(value)
    forbidden = sorted(keys & FORBIDDEN_KEYS)
    if forbidden:
        raise WakeEventError(
            f"wake event contains forbidden field(s): {', '.join(forbidden)}"
        )
    extra = sorted(keys - ENVELOPE_KEYS)
    if extra:
        raise WakeEventError(
            f"wake event contains unknown field(s): {', '.join(extra)}"
        )
    missing = sorted(ENVELOPE_KEYS - keys)
    if missing:
        raise WakeEventError(
            f"wake event missing required field(s): {', '.join(missing)}"
        )
    if value.get("schema") != SCHEMA:
        raise WakeEventError(f"unsupported wake schema {value.get('schema')!r}")
    event = mint_wake_event(
        event_type=value["event_type"],
        job_id=value["job_id"],
        attempt_id=value.get("attempt_id"),
        project_id=value.get("project_id"),
        target_seat=value["target_seat"],
        session_alias=value["session_alias"],
        reason_code=value["reason_code"],
        created_at=value["created_at"],
        evidence_refs=value["evidence_refs"],
    )
    supplied_id = value.get("event_id")
    if not isinstance(supplied_id, str) or WAKE_ID_RE.fullmatch(supplied_id) is None:
        raise WakeEventError("event_id must be a canonical WAKE-* identity")
    if supplied_id != event.event_id:
        raise WakeEventError("event_id does not match the content-addressed identity")
    return event


def _event_type(value: str | WakeEventType) -> WakeEventType:
    if isinstance(value, WakeEventType):
        return value
    token = str(value or "").strip()
    try:
        return WakeEventType(token)
    except ValueError as exc:
        raise WakeEventError(f"unsupported event_type {token!r}") from exc


def _job_id(value: Any) -> str:
    token = str(value or "").strip()
    if JOB_ID_RE.fullmatch(token) is None:
        raise WakeEventError("job_id must be a canonical JOB-* identity")
    return token


def _optional_attempt_id(value: Any) -> str | None:
    if value is None or value == "":
        return None
    token = str(value).strip()
    if ATTEMPT_ID_RE.fullmatch(token) is None:
        raise WakeEventError("attempt_id must be a canonical ATT-* identity")
    return token


def _optional_project_id(value: Any) -> str | None:
    if value is None or value == "":
        return None
    token = str(value).strip()
    if PROJECT_ID_RE.fullmatch(token) is None:
        raise WakeEventError("project_id must be a bounded identifier")
    return token


def _seat(value: Any) -> str:
    token = str(value or "").strip().lower()
    if token not in SEATS:
        raise WakeEventError(f"unsupported target_seat {token!r}")
    return token


def _session_alias(value: Any) -> str:
    token = str(value or "").strip()
    if SESSION_ALIAS_RE.fullmatch(token) is None:
        raise WakeEventError("session_alias must be a provider-neutral logical alias")
    return token


def _reason_code(value: Any) -> str:
    token = str(value or "").strip()
    if token not in REASON_CODES:
        raise WakeEventError(f"unsupported reason_code {token!r}")
    return token


def _created_at(value: Any) -> str:
    if value is None or value == "":
        return utc_now_iso()
    token = str(value).strip()
    if ISO_UTC_RE.fullmatch(token) is None:
        raise WakeEventError("created_at must be UTC ISO-8601")
    normalized = token[:-1] + "+00:00" if token.endswith("Z") else token
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise WakeEventError("created_at must be UTC ISO-8601") from exc
    if parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise WakeEventError("created_at must be UTC")
    return token


def _evidence_refs(value: Any) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise WakeEventError("evidence_refs must be a list")
    if len(value) > MAX_EVIDENCE_REFS:
        raise WakeEventError("evidence_refs exceeds its ceiling")
    refs: list[str] = []
    for raw in value:
        token = str(raw or "").strip()
        if JOB_ID_RE.fullmatch(token) is None and ATTEMPT_ID_RE.fullmatch(token) is None:
            raise WakeEventError(
                "evidence_refs may contain only JOB-* and ATT-* identities"
            )
        if token not in refs:
            refs.append(token)
    return tuple(refs)


def _derive_evidence_refs(job_id: str, attempt_id: str | None) -> tuple[str, ...]:
    refs = [job_id]
    if attempt_id is not None:
        refs.append(attempt_id)
    return tuple(refs)


__all__ = [
    "ATTEMPT_ID_RE",
    "ENVELOPE_KEYS",
    "FORBIDDEN_KEYS",
    "JOB_ID_RE",
    "REASON_CODES",
    "SCHEMA",
    "SEATS",
    "SESSION_ALIAS_RE",
    "WAKE_ID_RE",
    "WakeEvent",
    "WakeEventError",
    "WakeEventType",
    "mint_wake_event",
    "mint_wake_event_id",
    "parse_wake_event",
    "utc_now_iso",
]
