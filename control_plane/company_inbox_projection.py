"""Actor-scoped Company Inbox projection (pure read).

Renders one row per consultation visible to ``actor_worker_id`` as either
the requester or the recipient. The projection is read-only — never writes
to the store, never claims a clock, never broadens the existing wake rules
that ``control_plane.consultation_runtime`` already enforces.

Schema: ``mastermind.company_inbox.v1``.
"""
from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

from control_plane.consultation_runtime import ConsultationRuntime
from control_plane.executive_runtime import Runtime, StateConflict
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


def _actor_digest(actor_ref: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            dict(actor_ref), sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()


def _peer_digest(peer_ref: str) -> str:
    return hashlib.sha256(peer_ref.encode("utf-8")).hexdigest()


def _consultations(runtime: Runtime) -> ConsultationRuntime:
    return ConsultationRuntime(runtime, repository_root=runtime.store.root)


def _question_item_from_intent(intent_event: Any) -> dict[str, Any]:
    consultations = _consultations(runtime=intent_event.payload.get("__runtime__"))
    return consultations._intent_from_event(intent_event)  # noqa: SLF001


def _wake_state(
    runtime: Runtime, question_item: Mapping[str, Any]
) -> tuple[str, str | None]:
    """Return ``(state, blocker)`` from the canonical Wake state."""
    consultations = _consultations(runtime)
    try:
        state = consultations._canonical_wake_state(question_item).value
    except StateConflict:
        return ("RECONCILIATION_REQUIRED", "WAKE_STATE_UNAVAILABLE")
    except Exception:
        return ("RECONCILIATION_REQUIRED", "WAKE_STATE_UNAVAILABLE")

    if state in {"TARGET_ACKNOWLEDGED", "SOURCE_RESOLVED"}:
        return (state, None)
    if state == ObligationStatus.NOT_SEEN.value:
        return (state, "NOT_SEEN")
    return (state, state)


def _state_for(
    runtime: Runtime,
    *,
    intent_event: Any,
    events: list[Any],
    now: str,
) -> tuple[str, str | None]:
    event_types = {event.event_type for event in events}
    valid_until = intent_event.payload.get("valid_until")
    is_expired = False
    if isinstance(valid_until, str):
        try:
            from datetime import datetime

            now_instant = datetime.fromisoformat(now.replace("Z", "+00:00"))
            valid_instant = datetime.fromisoformat(valid_until.replace("Z", "+00:00"))
            is_expired = now_instant > valid_instant
        except ValueError:
            is_expired = False

    if "CONSUMED_BY_REQUESTER" in event_types:
        return ("CONSUMED", None)
    if is_expired:
        return ("EXPIRED", None)
    if "ANSWER_AVAILABLE" in event_types:
        return ("ANSWER_AVAILABLE", None)

    payload_with_runtime = dict(intent_event.payload)
    payload_with_runtime["__runtime__"] = runtime
    intent_event_with_runtime = _event_with_payload(intent_event, payload_with_runtime)
    question_item = _consultations(runtime)._intent_from_event(intent_event_with_runtime)  # noqa: SLF001
    wake_state, blocker = _wake_state(runtime, question_item)
    if wake_state == "TARGET_ACKNOWLEDGED":
        return ("QUESTION_DELIVERED", None)
    if wake_state == "RECONCILIATION_REQUIRED":
        return ("RECONCILIATION_REQUIRED", blocker or "WAKE_STATE_UNAVAILABLE")
    return ("QUESTION_PENDING_WAKE", blocker or wake_state)


def _event_with_payload(event: Any, payload: dict[str, Any]) -> Any:
    from dataclasses import replace

    if hasattr(event, "payload"):
        try:
            return replace(event, payload=payload)
        except Exception:
            return event
    return event


def _owed_turn(state: str, role: str | None) -> str | None:
    if role is None:
        return None
    if state == "QUESTION_DELIVERED":
        return "RECIPIENT"
    if state == "ANSWER_AVAILABLE":
        return "REQUESTER"
    return None


def _intent_event_for(
    runtime: Runtime, consultation_id: str
) -> Any | None:
    for event in runtime.events.list_events(
        aggregate_type="consultation", aggregate_id=consultation_id
    ):
        if event.event_type == "INTENT":
            return event
    return None


def _events_for(runtime: Runtime, consultation_id: str) -> list[Any]:
    return list(
        runtime.events.list_events(
            aggregate_type="consultation", aggregate_id=consultation_id
        )
    )


def _row_for_actor(
    runtime: Runtime,
    intent_event: Any,
    *,
    actor_worker_id: str,
    now: str,
) -> dict[str, Any] | None:
    payload = intent_event.payload
    requester_ref = payload.get("requester_actor_ref") or {}
    recipient_ref = payload.get("recipient_actor_ref") or {}
    requester_worker = str(requester_ref.get("worker_id", ""))
    recipient_worker = str(recipient_ref.get("worker_id", ""))
    if actor_worker_id not in (requester_worker, recipient_worker):
        return None
    role = "REQUESTER" if actor_worker_id == requester_worker else "RECIPIENT"

    consultation_id = str(intent_event.aggregate_id)
    events = _events_for(runtime, consultation_id)
    state, blocker = _state_for(
        runtime, intent_event=intent_event, events=events, now=now
    )
    owed = _owed_turn(state, role)

    evidence: dict[str, list[int]] = {}
    for event in events:
        evidence.setdefault(event.event_type, []).append(event.event_id)
    evidence_refs: list[dict[str, Any]] = [
        {"kind": "INTENT", "event_ids": sorted(evidence.get("INTENT", []))}
    ]
    if "ANSWER_AVAILABLE" in evidence:
        evidence_refs.append(
            {"kind": "ANSWER_AVAILABLE", "event_ids": sorted(evidence["ANSWER_AVAILABLE"])}
        )
    if "ANSWER_REFUSED" in evidence:
        evidence_refs.append(
            {"kind": "ANSWER_REFUSED", "event_ids": sorted(evidence["ANSWER_REFUSED"])}
        )
    if "CONSUMED_BY_REQUESTER" in evidence:
        evidence_refs.append(
            {
                "kind": "CONSUMED_BY_REQUESTER",
                "event_ids": sorted(evidence["CONSUMED_BY_REQUESTER"]),
            }
        )

    obligation_id = None
    try:
        payload_with_runtime = dict(payload)
        payload_with_runtime["__runtime__"] = runtime
        intent_with_runtime = _event_with_payload(intent_event, payload_with_runtime)
        consultations = _consultations(runtime)
        obligation_id, _status = consultations._exact_wake_evidence_on_connection(  # noqa: SLF001
            consultations._intent_from_event(intent_with_runtime),  # noqa: SLF001
            _connection_for(runtime),
        )
    except Exception:
        obligation_id = None

    return {
        "schema": COMPANY_INBOX_SCHEMA,
        "consultation_ref": consultation_id,
        "role": role,
        "peer_digest": _peer_digest(str(payload.get("recipient_peer_ref", ""))),
        "actor_digest": _actor_digest(
            requester_ref if role == "REQUESTER" else recipient_ref
        ),
        "counterpart_digest": _actor_digest(
            recipient_ref if role == "REQUESTER" else requester_ref
        ),
        "question_digest": str(payload.get("question_digest", "")),
        "evidence_revision_digest": str(payload.get("artifact_revision_digest", "")),
        "state": state,
        "wake_state": state,
        "deadline": str(payload.get("valid_until", "")),
        "blocker": blocker,
        "owed_turn": owed,
        "obligation_id": obligation_id,
        "evidence_refs": evidence_refs,
    }


def _connection_for(runtime: Runtime):
    """Return an open read connection for the projection's internal wake lookup."""
    ctx = runtime.store.read()
    connection = ctx.__enter__()
    return connection


def company_inbox_row(
    runtime: Runtime,
    consultation_id: str,
    actor_worker_id: str,
    now: str,
) -> dict[str, Any]:
    """Return one Company Inbox row for ``actor_worker_id``.

    Non-party or missing INTENT returns a typed ``NOT_A_PARTY`` /
    ``NO_INTENT`` envelope; never raises to the caller.
    """
    intent_event = _intent_event_for(runtime, consultation_id)
    if intent_event is None:
        return _typed_row(
            consultation_ref=consultation_id,
            state="RECONCILIATION_REQUIRED",
            blocker="NO_INTENT",
        )
    try:
        row = _row_for_actor(
            runtime, intent_event, actor_worker_id=actor_worker_id, now=now
        )
    except Exception:
        return _typed_row(
            consultation_ref=consultation_id,
            state="RECONCILIATION_REQUIRED",
            blocker="WAKE_STATE_UNAVAILABLE",
        )
    if row is None:
        return _typed_row(
            consultation_ref=consultation_id,
            state="RECONCILIATION_REQUIRED",
            blocker="NOT_A_PARTY",
        )
    return row


def project_company_inbox(
    runtime: Runtime,
    *,
    actor_worker_id: str,
    now: str,
) -> dict[str, Any]:
    """Return the actor-scoped inbox projection envelope.

    Items are digests only — no question/answer text, no clear worker_id,
    no token/secret. Items are returned in stable consultation-id order.
    """
    rows: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    consultation_ids: list[str] = []
    for event in runtime.events.list_events(aggregate_type="consultation"):
        if event.event_type != "INTENT":
            continue
        cid = str(event.aggregate_id)
        if cid in seen_ids:
            continue
        seen_ids.add(cid)
        consultation_ids.append(cid)
    for cid in sorted(consultation_ids):
        intent = _intent_event_for(runtime, cid)
        if intent is None:
            continue
        try:
            row = _row_for_actor(
                runtime, intent, actor_worker_id=actor_worker_id, now=now
            )
        except Exception:
            continue
        if row is not None:
            rows.append(row)
    return {
        "schema": COMPANY_INBOX_SCHEMA,
        "actor_worker_id_digest": _actor_digest({"worker_id": actor_worker_id}),
        "now": now,
        "items": rows,
    }


def _typed_row(
    *, consultation_ref: str, state: str, blocker: str | None
) -> dict[str, Any]:
    return {
        "schema": COMPANY_INBOX_SCHEMA,
        "consultation_ref": consultation_ref,
        "role": None,
        "actor_digest": "",
        "counterpart_digest": "",
        "peer_digest": "",
        "question_digest": "",
        "evidence_revision_digest": "",
        "state": state,
        "wake_state": state,
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
