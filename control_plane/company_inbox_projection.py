"""Actor-scoped Company Inbox projection (pure read).

Renders one row per consultation visible to ``actor`` (an exact
``{job_id, attempt_id, worker_id}`` mapping). The projection is
read-only — never writes to the store, never claims a clock, never
broadens the existing wake rules that ``control_plane.consultation_runtime``
already enforces.

The projection holds ONE read context for the whole call so the
sqlite connection is opened and closed exactly once per
``company_inbox_row`` / ``project_company_inbox`` invocation. The wake
ledger read reuses that connection.

Schema: ``mastermind.company_inbox.v1``.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from control_plane.consultation_runtime import ConsultationRuntime
from control_plane.executive_runtime import Runtime, StateConflict
from control_plane.executive_runtime import _event_from_row
from control_plane.wake_ledger import ObligationStatus


COMPANY_INBOX_SCHEMA = "mastermind.company_inbox.v1"

_VALID_STATES = frozenset(
    {
        "QUESTION_PENDING_WAKE",
        "QUESTION_DELIVERED",
        "ANSWER_AVAILABLE",
        "CONSUMED",
        "EXPIRED",
        "RECONCILIATION_REQUIRED",
    }
)

_OBLIGATION_STATUS_VALUES = frozenset(status.value for status in ObligationStatus)

_ACTOR_KEYS = frozenset({"job_id", "attempt_id", "worker_id"})


def _coerce_actor(actor: Any) -> tuple[dict[str, str], str | None]:
    """Validate the actor mapping. Return ``(actor, None)`` on success or
    ``(empty, "error")`` on validation failure."""
    if not isinstance(actor, Mapping):
        return {}, "INVALID_ACTOR"
    coerced: dict[str, str] = {}
    for key in _ACTOR_KEYS:
        value = actor.get(key)
        if not isinstance(value, str) or not value:
            return {}, "INVALID_ACTOR"
        coerced[key] = value
    return coerced, None


def _actor_digest(actor_ref: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            dict(actor_ref), sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()


def _actor_worker_id_digest(worker_id: str) -> str:
    return _actor_digest({"worker_id": worker_id})


def _peer_digest(peer_ref: str) -> str:
    return hashlib.sha256(peer_ref.encode("utf-8")).hexdigest()


def _consultations(runtime: Runtime) -> ConsultationRuntime:
    return ConsultationRuntime(runtime, repository_root=runtime.store.root)


def _wake_state_value(
    runtime: Runtime,
    connection: Any,
    question_item: Mapping[str, Any],
) -> tuple[str | None, str | None]:
    """Return ``(ObligationStatus.value | None, blocker | None)`` from the ledger.

    Only ``TARGET_ACKNOWLEDGED`` is blocker-free. ``SOURCE_RESOLVED`` returns
    ``(state, "SOURCE_RESOLVED_NOT_CONSUMED")`` — source resolution is not
    consumption. A runtime ``StateConflict`` on the ledger read surfaces
    ``RECONCILIATION_REQUIRED``; any other failure returns
    ``(None, "WAKE_STATE_UNAVAILABLE")``.
    """
    consultations = _consultations(runtime)
    try:
        _, status = consultations._exact_wake_evidence_on_connection(
            question_item, connection
        )
    except StateConflict:
        return (
            ObligationStatus.RECONCILIATION_REQUIRED.value,
            "WAKE_STATE_UNAVAILABLE",
        )
    except Exception:
        return (None, "WAKE_STATE_UNAVAILABLE")
    state = status.value
    if state == "TARGET_ACKNOWLEDGED":
        return (state, None)
    if state == "SOURCE_RESOLVED":
        return (state, "SOURCE_RESOLVED_NOT_CONSUMED")
    return (state, state)


def _deadline_state(
    intent_event: Any, now: str
) -> tuple[bool | None, str | None]:
    """Tri-state deadline evaluation.

    Returns ``(is_expired, blocker)``:
        ``(True, None)`` — past deadline;
        ``(False, None)`` — not yet expired;
        ``(None, "INVALID_DEADLINE")`` — ``valid_until`` or ``now`` was
        not a parseable ISO-8601 instant.
    """
    valid_until = intent_event.payload.get("valid_until")
    if not isinstance(valid_until, str):
        return None, "INVALID_DEADLINE"
    try:
        now_instant = datetime.fromisoformat(now.replace("Z", "+00:00"))
        valid_instant = datetime.fromisoformat(valid_until.replace("Z", "+00:00"))
    except ValueError:
        return None, "INVALID_DEADLINE"
    return bool(now_instant > valid_instant), None


def _answer_event_split(events: list[Any]) -> tuple[list[int], list[int]]:
    """Split ``ANSWER_AVAILABLE`` event ids by ``historical`` flag.

    Returns ``(current_event_ids, historical_event_ids)``.
    """
    current: list[int] = []
    historical: list[int] = []
    for event in events:
        if event.event_type != "ANSWER_AVAILABLE":
            continue
        if event.payload.get("historical") is True:
            historical.append(event.event_id)
        else:
            current.append(event.event_id)
    return current, historical


def _state_for(
    runtime: Runtime,
    connection: Any,
    *,
    intent_event: Any,
    events: list[Any],
    now: str,
) -> tuple[str, str | None, str | None]:
    """Return ``(state, blocker, wake_state)`` for the projected row.

    ``state`` is the lifecycle state derived from the persisted events.
    ``wake_state`` is the canonical ``ObligationStatus.value`` read from
    the ledger (or ``None`` when unreadable). Every branch consults the
    ledger — there is no fast path that copies ``state`` into ``wake_state``.
    """
    event_types = {event.event_type for event in events}
    deadline_state, deadline_blocker = _deadline_state(intent_event, now)
    current_answer_event_ids, historical_answer_event_ids = _answer_event_split(
        events
    )
    has_current_answer = bool(current_answer_event_ids)
    has_historical_answer = bool(historical_answer_event_ids)

    question_item: Mapping[str, Any] | None
    try:
        question_item = _consultations(runtime)._intent_from_event(intent_event)
    except Exception:
        question_item = None
    if question_item is None:
        wake_state, wake_blocker = None, "WAKE_STATE_UNAVAILABLE"
    else:
        wake_state, wake_blocker = _wake_state_value(
            runtime, connection, question_item
        )

    if deadline_blocker is not None:
        return ("RECONCILIATION_REQUIRED", deadline_blocker, wake_state)

    if "CONSUMED_BY_REQUESTER" in event_types:
        return ("CONSUMED", None, wake_state)
    if deadline_state is True:
        return ("EXPIRED", None, wake_state)
    if has_current_answer:
        return ("ANSWER_AVAILABLE", None, wake_state)

    historical_only_blocker = (
        "HISTORICAL_ANSWER_ONLY" if has_historical_answer else None
    )

    if wake_state == "TARGET_ACKNOWLEDGED":
        return ("QUESTION_DELIVERED", historical_only_blocker, wake_state)
    if wake_state == "RECONCILIATION_REQUIRED":
        return (
            "RECONCILIATION_REQUIRED",
            historical_only_blocker or wake_blocker or "WAKE_STATE_UNAVAILABLE",
            wake_state,
        )
    if wake_state is None:
        return (
            "QUESTION_PENDING_WAKE",
            historical_only_blocker or wake_blocker or "WAKE_STATE_UNAVAILABLE",
            wake_state,
        )
    return (
        "QUESTION_PENDING_WAKE",
        historical_only_blocker or wake_blocker or wake_state,
        wake_state,
    )


def _owed_turn(
    state: str,
    role: str | None,
    actor_matches_persisted: bool,
) -> str | None:
    if role is None or not actor_matches_persisted:
        return None
    if state == "QUESTION_DELIVERED":
        return "RECIPIENT"
    if state == "ANSWER_AVAILABLE":
        return "REQUESTER"
    return None


def _intent_event_for_connection(
    connection: Any, consultation_id: str
) -> Any | None:
    """Return the INTENT event for ``consultation_id`` using the supplied
    read connection — never opens its own ``store.read()`` context."""
    row = connection.execute(
        "SELECT * FROM events WHERE aggregate_type=? "
        "AND aggregate_id=? AND event_type=? ORDER BY event_id LIMIT 1",
        ("consultation", consultation_id, "INTENT"),
    ).fetchone()
    if row is None:
        return None
    return _event_from_row(row)


def _events_for_connection(
    connection: Any, consultation_id: str
) -> list[Any]:
    """Return every consultation event for ``consultation_id`` using the
    supplied read connection — never opens its own ``store.read()``."""
    rows = connection.execute(
        "SELECT * FROM events WHERE aggregate_type=? "
        "AND aggregate_id=? ORDER BY event_id",
        ("consultation", consultation_id),
    ).fetchall()
    return [_event_from_row(row) for row in rows]


def _intent_ids_on_connection(connection: Any) -> list[str]:
    """Return stable, deduplicated ``consultation`` aggregate ids that
    carry an INTENT event, using the supplied read connection."""
    rows = connection.execute(
        "SELECT aggregate_id FROM events WHERE aggregate_type=? "
        "AND event_type='INTENT' GROUP BY aggregate_id "
        "ORDER BY MIN(event_id)",
        ("consultation",),
    ).fetchall()
    return [str(row[0]) for row in rows]


def _intent_event_for(
    runtime: Runtime, consultation_id: str
) -> Any | None:
    """Compatibility seam. Opens its own read context — only used outside
    the balanced read context (e.g. inside ``company_inbox_row``)."""
    with runtime.store.read() as connection:
        return _intent_event_for_connection(connection, consultation_id)


def _events_for(runtime: Runtime, consultation_id: str) -> list[Any]:
    """Compatibility seam. Opens its own read context."""
    with runtime.store.read() as connection:
        return _events_for_connection(connection, consultation_id)


def _obligation_id_for(
    runtime: Runtime,
    connection: Any,
    question_item: Mapping[str, Any],
) -> str | None:
    """Return the canonical obligation id, or ``None`` when unreadable."""
    try:
        obligation_id, _status = _consultations(
            runtime
        )._exact_wake_evidence_on_connection(question_item, connection)
    except Exception:
        return None
    return obligation_id


def _party_check(
    payload: Mapping[str, Any], actor_worker_id: str
) -> tuple[bool, str | None, bool]:
    """Try to determine if ``actor_worker_id`` is a requester or recipient
    worker. Returns ``(is_party, role, can_determine)``.

    ``can_determine`` is False when the INTENT payload is so malformed
    that party-ness cannot be determined at all (no mapping refs at all,
    or every mapping's worker_id is missing/non-string).
    """
    requester_ref = payload.get("requester_actor_ref")
    recipient_ref = payload.get("recipient_actor_ref")
    requester_mapping = isinstance(requester_ref, Mapping)
    recipient_mapping = isinstance(recipient_ref, Mapping)

    if not requester_mapping and not recipient_mapping:
        return False, None, False

    if requester_mapping:
        rw = requester_ref.get("worker_id")
        if isinstance(rw, str) and rw:
            if rw == actor_worker_id:
                return True, "REQUESTER", True
            requester_ok = True
        else:
            requester_ok = False
    else:
        requester_ok = False

    if recipient_mapping:
        nw = recipient_ref.get("worker_id")
        if isinstance(nw, str) and nw:
            if nw == actor_worker_id:
                return True, "RECIPIENT", True
            recipient_ok = True
        else:
            recipient_ok = False
    else:
        recipient_ok = False

    if not requester_ok and not recipient_ok:
        return False, None, False
    return False, None, True


def _actor_matches_persisted_party(
    persisted_actor_ref: Mapping[str, Any],
    actor: Mapping[str, str],
) -> bool:
    return (
        str(persisted_actor_ref.get("job_id", "")) == actor["job_id"]
        and str(persisted_actor_ref.get("attempt_id", "")) == actor["attempt_id"]
        and str(persisted_actor_ref.get("worker_id", "")) == actor["worker_id"]
    )


def _row_for_actor(
    runtime: Runtime,
    connection: Any,
    intent_event: Any,
    *,
    actor: Mapping[str, str],
    now: str,
) -> tuple[str, Any]:
    """Return ``(outcome, payload)``.

    ``outcome`` is one of:
        ``"OK"`` — full row appended in ``payload``;
        ``"DEGRADED"`` — party check succeeded but later evaluation failed;
            ``payload`` is a degraded row with ``role`` filled and no actor data;
        ``"UNATTRIBUTABLE"`` — refs missing/non-mapping, no row emitted;
        ``"NOT_A_PARTY"`` — actor worker not in the row, no row emitted.
    """
    payload = intent_event.payload
    actor_worker_id = actor["worker_id"]
    is_party, role, can_determine = _party_check(payload, actor_worker_id)
    if not can_determine:
        return "UNATTRIBUTABLE", None
    if not is_party:
        return "NOT_A_PARTY", None

    consultation_id = str(intent_event.aggregate_id)
    try:
        # The runtime's own INTENT rehydration is the well-formedness
        # contract: a payload it cannot rebuild is a DEGRADED authorized
        # row, never a healthy-looking one.
        _expired_unused, deadline_blocker = _deadline_state(intent_event, now)
        if deadline_blocker is not None:
            # An unparseable deadline is a specific, truthful degradation:
            # never "unexpired", never a healthy row.
            return "DEGRADED", _typed_row(
                consultation_ref=consultation_id,
                state="RECONCILIATION_REQUIRED",
                blocker=deadline_blocker,
                role=role,
            )
        question_item = _consultations(runtime)._intent_from_event(intent_event)
        requester_ref = payload.get("requester_actor_ref") or {}
        recipient_ref = payload.get("recipient_actor_ref") or {}
        persisted_party_ref = (
            requester_ref if role == "REQUESTER" else recipient_ref
        )
        actor_matches_persisted = _actor_matches_persisted_party(
            persisted_party_ref, actor
        )

        events = _events_for_connection(connection, consultation_id)
        state, blocker, wake_state = _state_for(
            runtime,
            connection,
            intent_event=intent_event,
            events=events,
            now=now,
        )
        owed = _owed_turn(state, role, actor_matches_persisted)
        actor_rotation_blocker = (
            None if actor_matches_persisted else "ACTOR_ROTATED"
        )
        if actor_rotation_blocker is not None:
            # Worker-only match — surface ACTOR_ROTATED instead of the
            # wake-derived blocker so the caller cannot mistake a rotated
            # attempt for a current owed turn.
            blocker = actor_rotation_blocker

        evidence: dict[str, list[int]] = {}
        for event in events:
            evidence.setdefault(event.event_type, []).append(event.event_id)
        current_answer_event_ids, historical_answer_event_ids = _answer_event_split(
            events
        )
        evidence_refs: list[dict[str, Any]] = [
            {"kind": "INTENT", "event_ids": sorted(evidence.get("INTENT", []))}
        ]
        if current_answer_event_ids:
            evidence_refs.append(
                {
                    "kind": "ANSWER_AVAILABLE",
                    "event_ids": sorted(current_answer_event_ids),
                }
            )
        if historical_answer_event_ids:
            evidence_refs.append(
                {
                    "kind": "ANSWER_AVAILABLE_HISTORICAL",
                    "event_ids": sorted(historical_answer_event_ids),
                }
            )
        if "ANSWER_REFUSED" in evidence:
            evidence_refs.append(
                {
                    "kind": "ANSWER_REFUSED",
                    "event_ids": sorted(evidence["ANSWER_REFUSED"]),
                }
            )
        if "CONSUMED_BY_REQUESTER" in evidence:
            evidence_refs.append(
                {
                    "kind": "CONSUMED_BY_REQUESTER",
                    "event_ids": sorted(evidence["CONSUMED_BY_REQUESTER"]),
                }
            )

        obligation_id: str | None
        try:
            obligation_id = _obligation_id_for(
                runtime, connection, question_item
            )
        except Exception:
            obligation_id = None
    except Exception:
        return "DEGRADED", _typed_row(
            consultation_ref=consultation_id,
            state="RECONCILIATION_REQUIRED",
            blocker="ROW_DEGRADED",
            role=role,
        )

    counterpart_ref = recipient_ref if role == "REQUESTER" else requester_ref
    return (
        "OK",
        {
            "schema": COMPANY_INBOX_SCHEMA,
            "consultation_ref": consultation_id,
            "role": role,
            "peer_digest": _peer_digest(str(payload.get("recipient_peer_ref", ""))),
            "actor_digest": _actor_digest(actor),
            "counterpart_digest": _actor_digest(counterpart_ref)
            if isinstance(counterpart_ref, Mapping)
            else "",
            "question_digest": str(payload.get("question_digest", "")),
            "evidence_revision_digest": str(payload.get("artifact_revision_digest", "")),
            "state": state,
            "wake_state": wake_state,
            "deadline": str(payload.get("valid_until", "")),
            "blocker": blocker,
            "owed_turn": owed,
            "obligation_id": obligation_id,
            "evidence_refs": evidence_refs,
        },
    )


def _empty_envelope(
    *,
    actor: Mapping[str, str],
    now: str,
    blocker: str | None,
    consultations_scanned: int,
) -> dict[str, Any]:
    return {
        "schema": COMPANY_INBOX_SCHEMA,
        "actor_worker_id_digest": _actor_worker_id_digest(actor["worker_id"]),
        "actor_digest": _actor_digest(actor),
        "now": now,
        "blocker": blocker,
        "items": [],
        "coverage": {
            "consultations_scanned": consultations_scanned,
            "rows_returned": 0,
            "rows_degraded": 0,
            "rows_unattributable": 0,
            "status": "COMPLETE",
        },
    }


def company_inbox_row(
    runtime: Runtime,
    consultation_id: str,
    actor: Mapping[str, str],
    now: str,
) -> dict[str, Any]:
    """Return one Company Inbox row for ``actor``.

    ``actor`` is the exact ``{job_id, attempt_id, worker_id}`` mapping.
    Non-party or missing INTENT returns a typed ``NOT_A_PARTY`` /
    ``NO_INTENT`` envelope; never raises to the caller.
    """
    coerced_actor, actor_error = _coerce_actor(actor)
    if actor_error is not None:
        return _typed_row(
            consultation_ref=consultation_id,
            state="RECONCILIATION_REQUIRED",
            blocker=actor_error,
        )
    try:
        with runtime.store.read() as connection:
            intent_event = _intent_event_for_connection(connection, consultation_id)
            if intent_event is None:
                return _typed_row(
                    consultation_ref=consultation_id,
                    state="RECONCILIATION_REQUIRED",
                    blocker="NO_INTENT",
                )
            outcome, row = _row_for_actor(
                runtime,
                connection,
                intent_event,
                actor=coerced_actor,
                now=now,
            )
    except Exception:
        return _typed_row(
            consultation_ref=consultation_id,
            state="RECONCILIATION_REQUIRED",
            blocker="WAKE_STATE_UNAVAILABLE",
        )
    if outcome == "OK":
        return row
    if outcome == "DEGRADED":
        return row
    if outcome == "UNATTRIBUTABLE":
        return _typed_row(
            consultation_ref=consultation_id,
            state="RECONCILIATION_REQUIRED",
            blocker="ROW_UNATTRIBUTABLE",
        )
    return _typed_row(
        consultation_ref=consultation_id,
        state="RECONCILIATION_REQUIRED",
        blocker="NOT_A_PARTY",
    )


def project_company_inbox(
    runtime: Runtime,
    *,
    actor: Mapping[str, str],
    now: str,
) -> dict[str, Any]:
    """Return the actor-scoped inbox projection envelope.

    Items are digests only — no question/answer text, no clear worker_id,
    no token/secret. Items are returned in stable consultation-id order.
    The envelope also carries a ``coverage`` block that records the
    consultations scanned, rows returned, and any rows degraded or
    unattributable while evaluating them.
    """
    coerced_actor, actor_error = _coerce_actor(actor)
    if actor_error is not None:
        envelope = _empty_envelope(
            actor={"job_id": "", "attempt_id": "", "worker_id": ""},
            now=now,
            blocker=actor_error,
            consultations_scanned=0,
        )
        envelope["coverage"]["status"] = "UNAVAILABLE"
        return envelope

    consultation_ids: list[str] = []
    rows: list[dict[str, Any]] = []
    rows_returned = 0
    rows_degraded = 0
    rows_unattributable = 0
    actor_worker_id = coerced_actor["worker_id"]
    actor_digest_value = _actor_digest(coerced_actor)
    try:
        # The projection opens exactly ONE read context for the whole call.
        # All event fetching (id scan, per-consultation event fetch, and
        # the wake ledger read) reuses the connection below.
        with runtime.store.read() as connection:
            consultation_ids = _intent_ids_on_connection(connection)
            for cid in sorted(consultation_ids):
                intent = _intent_event_for_connection(connection, cid)
                if intent is None:
                    continue
                outcome, row = _row_for_actor(
                    runtime,
                    connection,
                    intent,
                    actor=coerced_actor,
                    now=now,
                )
                if outcome == "OK":
                    rows.append(row)
                    rows_returned += 1
                elif outcome == "DEGRADED":
                    rows.append(row)
                    rows_degraded += 1
                elif outcome == "UNATTRIBUTABLE":
                    rows_unattributable += 1
                # NOT_A_PARTY: actor not in the row, nothing to count
    except Exception:
        return {
            "schema": COMPANY_INBOX_SCHEMA,
            "actor_worker_id_digest": _actor_worker_id_digest(actor_worker_id),
            "actor_digest": actor_digest_value,
            "now": now,
            "blocker": "INBOX_UNAVAILABLE",
            "items": [],
            "coverage": {
                "consultations_scanned": 0,
                "rows_returned": 0,
                "rows_degraded": 0,
                "rows_unattributable": 0,
                "status": "UNAVAILABLE",
            },
        }

    coverage = {
        "consultations_scanned": len(consultation_ids),
        "rows_returned": rows_returned,
        "rows_degraded": rows_degraded,
        "rows_unattributable": rows_unattributable,
        "status": "COMPLETE",
    }
    if rows_degraded > 0 or rows_unattributable > 0:
        coverage["status"] = "DEGRADED"

    return {
        "schema": COMPANY_INBOX_SCHEMA,
        "actor_worker_id_digest": _actor_worker_id_digest(actor_worker_id),
        "actor_digest": actor_digest_value,
        "now": now,
        "blocker": None,
        "items": rows,
        "coverage": coverage,
    }


def _typed_row(
    *,
    consultation_ref: str,
    state: str,
    blocker: str | None,
    role: str | None = None,
) -> dict[str, Any]:
    return {
        "schema": COMPANY_INBOX_SCHEMA,
        "consultation_ref": consultation_ref,
        "role": role,
        "actor_digest": "",
        "counterpart_digest": "",
        "peer_digest": "",
        "question_digest": "",
        "evidence_revision_digest": "",
        "state": state,
        "wake_state": None,
        "deadline": "",
        "blocker": blocker,
        "owed_turn": None,
        "obligation_id": None,
        "evidence_refs": [],
    }


__all__ = [
    "COMPANY_INBOX_SCHEMA",
    "company_inbox_row",
    "project_company_inbox",
]