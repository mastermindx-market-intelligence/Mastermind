"""Wake obligation envelope — source-anchored, route-independent.

A wake obligation exists because a canonical source fact occurred.  It is not a
Job, Attempt, lease, queue, or command, and it does not change identity when
session routing, transport, account, or native handles change.

Identity
--------
``obligation_id`` is a deterministic wake-obligation identity, NOT a hash of
the complete envelope::

    WAKE- + sha256(canonical JSON of
      schema, source_kind, source_ref, wake_kind)[:32]

``source_created_at`` and ``emitted_at`` are recorded and excluded from the
hash.  Session alias, seat, transport, reasoning surface, native handle,
account, and route configuration MUST NOT participate.

``job_id`` / ``attempt_id`` / ``root_job_id`` are optional correlation.  A CEO
attention item with no Job is a valid obligation.  There is no free-form
``project_id``.

Later persistence (PR-2) reuses Executive OS ``events.command_id`` with
phase suffixes defined in :mod:`control_plane.wake_dispatcher`.  This module
does not write SQLite.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import re
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping, Sequence


SCHEMA = "mastermind.wake_obligation.v1"
OBLIGATION_ID_PREFIX = "WAKE-"
IDENTITY_HEX_LEN = 32
MAX_EVIDENCE_REFS = 8

JOB_ID_RE = re.compile(r"^JOB-\d{3,}$")
ATTEMPT_ID_RE = re.compile(r"^ATT-[0-9a-f]{32}$")
WAKE_ID_RE = re.compile(rf"^{OBLIGATION_ID_PREFIX}[0-9a-f]{{{IDENTITY_HEX_LEN}}}$")
ATTENTION_ID_RE = re.compile(r"^eia-[0-9a-f]{12}$")
RUNTIME_REF_RE = re.compile(
    r"^runtime:(job|attempt|worker):[A-Za-z0-9._:-]+:[1-9][0-9]*$"
)
WORKSTREAM_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
ISO_UTC_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]00:00)$"
)

SEATS = frozenset({"chairman", "ceo", "coo"})

#: Inbox v2 kinds that already mean executive attention, plus the one runtime
#: continuation kind that Inbox currently suppresses as routine completion.
WAKE_KINDS = frozenset(
    {
        "job_failed",
        "job_lost",
        "job_rate_limited",
        "cancel_requested",
        "aggregation_blocked",
        "attempts_exhausted",
        "malformed_result_evidence",
        "review_not_independent",
        "completed_with_errors",
        "unresolved_next_actions",
        "stale_lease",
        "escalated_exception",
        "ceo_decision_pending",
        "review_required",
    }
)
INBOX_WAKE_KINDS = WAKE_KINDS - {"review_required"}
RUNTIME_WAKE_KINDS = frozenset({"review_required"})

SOURCE_KINDS = frozenset(
    {
        "executive_runtime_event",
        "executive_inbox_attention",
    }
)

ENVELOPE_KEYS = frozenset(
    {
        "schema",
        "obligation_id",
        "wake_kind",
        "source_kind",
        "source_ref",
        "source_created_at",
        "emitted_at",
        "declared_target_seat",
        "job_id",
        "attempt_id",
        "root_job_id",
        "workstream",
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
        "session_alias",
        "external_handle",
        "native_handle",
        "adapter_type",
        "wake_transport",
        "reasoning_surface",
        "project_id",
        "event_type",
        "reason_code",
        "event_id",
        "target_seat",
    }
)


class WakeObligationError(ValueError):
    """The wake obligation is missing, malformed, or outside the closed vocabulary."""


class WakeKind(str, Enum):
    JOB_FAILED = "job_failed"
    JOB_LOST = "job_lost"
    JOB_RATE_LIMITED = "job_rate_limited"
    CANCEL_REQUESTED = "cancel_requested"
    AGGREGATION_BLOCKED = "aggregation_blocked"
    ATTEMPTS_EXHAUSTED = "attempts_exhausted"
    MALFORMED_RESULT_EVIDENCE = "malformed_result_evidence"
    REVIEW_NOT_INDEPENDENT = "review_not_independent"
    COMPLETED_WITH_ERRORS = "completed_with_errors"
    UNRESOLVED_NEXT_ACTIONS = "unresolved_next_actions"
    STALE_LEASE = "stale_lease"
    ESCALATED_EXCEPTION = "escalated_exception"
    CEO_DECISION_PENDING = "ceo_decision_pending"
    REVIEW_REQUIRED = "review_required"


class SourceKind(str, Enum):
    EXECUTIVE_RUNTIME_EVENT = "executive_runtime_event"
    EXECUTIVE_INBOX_ATTENTION = "executive_inbox_attention"


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")


def mint_obligation_id(
    *,
    source_kind: str | SourceKind,
    source_ref: str,
    wake_kind: str | WakeKind,
) -> str:
    identity = {
        "schema": SCHEMA,
        "source_kind": _source_kind(source_kind).value,
        "source_ref": _source_ref(source_kind, source_ref),
        "wake_kind": _wake_kind(wake_kind).value,
    }
    digest = hashlib.sha256(canonical_json_bytes(identity)).hexdigest()
    return f"{OBLIGATION_ID_PREFIX}{digest[:IDENTITY_HEX_LEN]}"


def utc_now_iso(now: datetime | None = None) -> str:
    stamp = now if now is not None else datetime.now(timezone.utc)
    if stamp.tzinfo is None:
        raise WakeObligationError("timestamps must be timezone-aware UTC")
    stamp = stamp.astimezone(timezone.utc).replace(microsecond=0)
    return stamp.strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclasses.dataclass(frozen=True)
class WakeObligation:
    """Source-anchored wake obligation.  Construct through :func:`mint_obligation`."""

    schema: str
    obligation_id: str
    wake_kind: WakeKind
    source_kind: SourceKind
    source_ref: str
    source_created_at: str | None
    emitted_at: str
    declared_target_seat: str
    job_id: str | None
    attempt_id: str | None
    root_job_id: str | None
    workstream: str | None
    evidence_refs: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "obligation_id": self.obligation_id,
            "wake_kind": self.wake_kind.value,
            "source_kind": self.source_kind.value,
            "source_ref": self.source_ref,
            "source_created_at": self.source_created_at,
            "emitted_at": self.emitted_at,
            "declared_target_seat": self.declared_target_seat,
            "job_id": self.job_id,
            "attempt_id": self.attempt_id,
            "root_job_id": self.root_job_id,
            "workstream": self.workstream,
            "evidence_refs": list(self.evidence_refs),
        }


def mint_obligation(
    *,
    wake_kind: str | WakeKind,
    source_kind: str | SourceKind,
    source_ref: str,
    declared_target_seat: str,
    job_id: str | None = None,
    attempt_id: str | None = None,
    root_job_id: str | None = None,
    workstream: str | None = None,
    source_created_at: str | None = None,
    emitted_at: str | None = None,
    evidence_refs: Sequence[str] | None = None,
) -> WakeObligation:
    resolved_kind = _wake_kind(wake_kind)
    resolved_source = _source_kind(source_kind)
    resolved_ref = _source_ref(resolved_source, source_ref)
    seat = _seat(declared_target_seat)
    job = _optional_job_id(job_id)
    attempt = _optional_attempt_id(attempt_id)
    root = _optional_job_id(root_job_id)
    stream = _optional_workstream(workstream)
    if resolved_source is SourceKind.EXECUTIVE_INBOX_ATTENTION:
        if resolved_kind.value not in INBOX_WAKE_KINDS:
            raise WakeObligationError(
                f"inbox source cannot mint wake_kind {resolved_kind.value!r}"
            )
    elif resolved_kind.value not in RUNTIME_WAKE_KINDS:
        raise WakeObligationError(
            f"runtime source cannot mint wake_kind {resolved_kind.value!r}"
        )
    refs = _evidence_refs(
        evidence_refs,
        source_ref=resolved_ref,
        job_id=job,
        attempt_id=attempt,
        root_job_id=root,
    )
    obligation_id = mint_obligation_id(
        source_kind=resolved_source,
        source_ref=resolved_ref,
        wake_kind=resolved_kind,
    )
    return WakeObligation(
        schema=SCHEMA,
        obligation_id=obligation_id,
        wake_kind=resolved_kind,
        source_kind=resolved_source,
        source_ref=resolved_ref,
        source_created_at=_optional_timestamp(source_created_at),
        emitted_at=_created_at(emitted_at),
        declared_target_seat=seat,
        job_id=job,
        attempt_id=attempt,
        root_job_id=root,
        workstream=stream,
        evidence_refs=refs,
    )


def parse_obligation(value: Mapping[str, Any]) -> WakeObligation:
    if not isinstance(value, Mapping):
        raise WakeObligationError("wake obligation must be a mapping")
    keys = set(value)
    forbidden = sorted(keys & FORBIDDEN_KEYS)
    if forbidden:
        raise WakeObligationError(
            f"wake obligation contains forbidden field(s): {', '.join(forbidden)}"
        )
    extra = sorted(keys - ENVELOPE_KEYS)
    if extra:
        raise WakeObligationError(
            f"wake obligation contains unknown field(s): {', '.join(extra)}"
        )
    missing = sorted(ENVELOPE_KEYS - keys)
    if missing:
        raise WakeObligationError(
            f"wake obligation missing required field(s): {', '.join(missing)}"
        )
    if value.get("schema") != SCHEMA:
        raise WakeObligationError(
            f"unsupported wake schema {value.get('schema')!r}"
        )
    minted = mint_obligation(
        wake_kind=value["wake_kind"],
        source_kind=value["source_kind"],
        source_ref=value["source_ref"],
        declared_target_seat=value["declared_target_seat"],
        job_id=value.get("job_id"),
        attempt_id=value.get("attempt_id"),
        root_job_id=value.get("root_job_id"),
        workstream=value.get("workstream"),
        source_created_at=value.get("source_created_at"),
        emitted_at=value.get("emitted_at"),
        evidence_refs=value.get("evidence_refs"),
    )
    supplied_id = value.get("obligation_id")
    if not isinstance(supplied_id, str) or WAKE_ID_RE.fullmatch(supplied_id) is None:
        raise WakeObligationError(
            "obligation_id must be a canonical WAKE-* identity"
        )
    if supplied_id != minted.obligation_id:
        raise WakeObligationError(
            "obligation_id does not match the deterministic source identity"
        )
    return minted


def runtime_source_ref(*, aggregate_type: str, aggregate_id: str, sequence: int) -> str:
    token = f"runtime:{str(aggregate_type).strip()}:{str(aggregate_id).strip()}:{int(sequence)}"
    if RUNTIME_REF_RE.fullmatch(token) is None:
        raise WakeObligationError("runtime source_ref is malformed")
    return token


def _wake_kind(value: str | WakeKind) -> WakeKind:
    if isinstance(value, WakeKind):
        return value
    token = str(value or "").strip()
    if token not in WAKE_KINDS:
        raise WakeObligationError(f"unsupported wake_kind {token!r}")
    return WakeKind(token)


def _source_kind(value: str | SourceKind) -> SourceKind:
    if isinstance(value, SourceKind):
        return value
    token = str(value or "").strip()
    try:
        return SourceKind(token)
    except ValueError as exc:
        raise WakeObligationError(f"unsupported source_kind {token!r}") from exc


def _source_ref(source_kind: str | SourceKind, value: Any) -> str:
    kind = _source_kind(source_kind)
    token = str(value or "").strip()
    if kind is SourceKind.EXECUTIVE_INBOX_ATTENTION:
        if ATTENTION_ID_RE.fullmatch(token) is None:
            raise WakeObligationError(
                "inbox source_ref must be a canonical attention_id"
            )
        return token
    if RUNTIME_REF_RE.fullmatch(token) is None:
        raise WakeObligationError("runtime source_ref must be runtime:type:id:sequence")
    return token


def _seat(value: Any) -> str:
    token = str(value or "").strip().lower()
    if token not in SEATS:
        raise WakeObligationError(f"unsupported declared_target_seat {token!r}")
    return token


def _optional_job_id(value: Any) -> str | None:
    if value is None or value == "":
        return None
    token = str(value).strip()
    if JOB_ID_RE.fullmatch(token) is None:
        raise WakeObligationError("job_id/root_job_id must be a canonical JOB-* identity")
    return token


def _optional_attempt_id(value: Any) -> str | None:
    if value is None or value == "":
        return None
    token = str(value).strip()
    if ATTEMPT_ID_RE.fullmatch(token) is None:
        raise WakeObligationError("attempt_id must be a canonical ATT-* identity")
    return token


def _optional_workstream(value: Any) -> str | None:
    if value is None or value == "":
        return None
    token = str(value).strip().lower()
    if WORKSTREAM_RE.fullmatch(token) is None:
        raise WakeObligationError("workstream must be a bounded identifier")
    return token


def _optional_timestamp(value: Any) -> str | None:
    if value is None or value == "":
        return None
    return _created_at(value)


def _created_at(value: Any) -> str:
    if value is None or value == "":
        return utc_now_iso()
    token = str(value).strip()
    if ISO_UTC_RE.fullmatch(token) is None:
        raise WakeObligationError("timestamps must be UTC ISO-8601")
    normalized = token[:-1] + "+00:00" if token.endswith("Z") else token
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise WakeObligationError("timestamps must be UTC ISO-8601") from exc
    if parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise WakeObligationError("timestamps must be UTC")
    return token


def _evidence_refs(
    value: Any,
    *,
    source_ref: str,
    job_id: str | None,
    attempt_id: str | None,
    root_job_id: str | None,
) -> tuple[str, ...]:
    expected = [source_ref]
    for item in (job_id, attempt_id, root_job_id):
        if item is not None and item not in expected:
            expected.append(item)
    expected_tuple = tuple(expected)
    if value is None:
        return expected_tuple
    if not isinstance(value, (list, tuple)):
        raise WakeObligationError("evidence_refs must be a list")
    if len(value) > MAX_EVIDENCE_REFS:
        raise WakeObligationError("evidence_refs exceeds its ceiling")
    refs: list[str] = []
    for raw in value:
        token = str(raw or "").strip()
        if not _allowed_evidence(token):
            raise WakeObligationError(
                "evidence_refs may contain only canonical JOB-*, ATT-*, "
                "attention_id, or runtime event references"
            )
        if token not in refs:
            refs.append(token)
    if tuple(refs) != expected_tuple:
        raise WakeObligationError(
            "evidence_refs must be exactly the source_ref plus optional job/attempt/root ids"
        )
    return tuple(refs)


def _allowed_evidence(token: str) -> bool:
    return bool(
        JOB_ID_RE.fullmatch(token)
        or ATTEMPT_ID_RE.fullmatch(token)
        or ATTENTION_ID_RE.fullmatch(token)
        or RUNTIME_REF_RE.fullmatch(token)
    )


__all__ = [
    "ATTENTION_ID_RE",
    "ATTEMPT_ID_RE",
    "ENVELOPE_KEYS",
    "FORBIDDEN_KEYS",
    "INBOX_WAKE_KINDS",
    "JOB_ID_RE",
    "RUNTIME_WAKE_KINDS",
    "SCHEMA",
    "SEATS",
    "SOURCE_KINDS",
    "WAKE_ID_RE",
    "WAKE_KINDS",
    "SourceKind",
    "WakeKind",
    "WakeObligation",
    "WakeObligationError",
    "mint_obligation",
    "mint_obligation_id",
    "parse_obligation",
    "runtime_source_ref",
    "utc_now_iso",
]
