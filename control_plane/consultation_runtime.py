"""Runtime consultation receipts as immutable event-plane observations."""
from __future__ import annotations

import copy
import hashlib
import json
import sqlite3
import subprocess
from datetime import datetime, timezone

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Mapping

from common.agent_dialogue_consultation_contract import (
    CONSULTATION_SCHEMA,
    canonical_consultation_json,
    validate_consultation,
)
from control_plane.executive_runtime import (
    Event,
    Runtime,
    StateConflict,
    _event_from_row,
)
from control_plane.dialogue_source_resolution import (
    ConsultationSourceIdentity,
    peer_attention_source_ref,
)
from control_plane.runtime_binding_projection import project_runtime_binding
from control_plane.session_targets import SessionTarget
from control_plane.wake_ledger import DeliveryAttempt, LedgerPhase
from control_plane.wake_events import SourceKind, WakeKind, mint_obligation
from control_plane.wake_persist import WakeLedgerRepository


CONSULTATION_INTENT_SCHEMA = "mastermind.consultation_intent/v1"
CONSULTATION_RECEIPT_SCHEMA = "mastermind.consultation_receipt/v1"
CONSULTATION_RECEIPT_EVENTS = (
    "INTENT",
    "DISPATCH_ATTEMPT",
    "NATIVE_ACCEPTED",
    "CONSUMED_BY_RECIPIENT",
    "ANSWER_AVAILABLE",
    "CONSUMED_BY_REQUESTER",
)
REFUSAL_RECEIPT_EVENTS = frozenset({"BUDGET_EXHAUSTED"})
ANSWER_EVENTS = frozenset({"ANSWER_AVAILABLE", "CONSUMED_BY_REQUESTER"})
REFUSAL_EVENTS = frozenset({"ANSWER_REFUSED"})


class ConsultationConflict(StateConflict):
    def __init__(self, message: str, *, conflict: str = "CONFLICT") -> None:
        super().__init__(message)
        self.conflict = conflict


@dataclass(frozen=True)
class ConsultationEventResult:
    event: Event
    inserted: bool


@dataclass(frozen=True)
class _ConsultationRuntimeContext:
    repository_root: Path
    consultation_id: str | None = None


def _utc(value: str) -> str:
    if not isinstance(value, str) or not value.endswith("Z") or ":" not in value:
        raise StateConflict("observed_at must be a UTC timestamp")
    return value


def _expired(valid_until: str, observed_at: str) -> bool:
    deadline = datetime.fromisoformat(_utc(valid_until).replace("Z", "+00:00"))
    observed = datetime.fromisoformat(_utc(observed_at).replace("Z", "+00:00"))
    return observed > deadline


def _artifact_digest(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_consultation_json(value).encode()).hexdigest()


def _semantic_answer_digest(value: Mapping[str, Any]) -> str:
    answer = value.get("answer")
    if not isinstance(answer, Mapping):
        raise StateConflict("answer frame requires a semantic answer")
    try:
        parsed = json.loads(str(answer.get("text", "")))
    except (TypeError, json.JSONDecodeError) as exc:
        raise StateConflict("answer text must be canonical semantic JSON") from exc
    if not isinstance(parsed, Mapping):
        raise StateConflict("answer text must decode to an object")
    return hashlib.sha256(
        canonical_consultation_json(parsed).encode()
    ).hexdigest()


class ConsultationRuntime:
    """Own consultation facts without changing Job/Attempt lifecycle state."""

    def __init__(self, runtime: Runtime, *, repository_root: Path) -> None:
        if not isinstance(runtime, Runtime):
            raise TypeError("runtime must be the existing Executive Runtime")
        self.runtime = runtime
        self._context = _ConsultationRuntimeContext(
            Path(repository_root).resolve()
        )

    def intent(
        self,
        frame: Mapping[str, Any],
        *,
        requester_attempt_id: str,
        carrier_ref: str,
        observed_at: str,
        repository_root: Path | None = None,
    ) -> ConsultationEventResult:
        item = validate_consultation(frame)
        if item["purpose"] != "QUESTION":
            raise StateConflict("INTENT requires a QUESTION frame")
        _utc(observed_at)
        self._context = replace(
            self._context, consultation_id=item["consultation_id"]
        )
        self._validate_artifact_revisions(item, repository_root)
        self._require_requester(item, requester_attempt_id)
        self._require_current_recipient(item)
        payload = {
            "schema_version": CONSULTATION_INTENT_SCHEMA,
            "consultation_schema": CONSULTATION_SCHEMA,
            "message_key": item["message_key"],
            "consultation_id": item["consultation_id"],
            "semantic_fingerprint": item["fingerprint"],
            "carrier_ref": str(carrier_ref),
            "requester_actor_ref": copy.deepcopy(item["requester_actor_ref"]),
            "recipient_actor_ref": copy.deepcopy(item["recipient_actor_ref"]),
            "recipient_binding": copy.deepcopy(item["recipient_binding"]),
            "correlation": copy.deepcopy(item["correlation"]),
            "artifact_revisions": copy.deepcopy(item["artifact_revisions"]),
            "artifact_revision_digest": hashlib.sha256(
                canonical_consultation_json(item["artifact_revisions"]).encode()
            ).hexdigest(),
            "valid_until": item["valid_until"],
            "deadline_ms": item["deadline_ms"],
            "response_budget": copy.deepcopy(item["response_budget"]),
            "payload_digest": item["fingerprint"],
            "question_digest": hashlib.sha256(item["question"].encode()).hexdigest(),
            "observed_at": _utc(observed_at),
        }
        return self._append(
            item,
            "INTENT",
            payload,
            actor="requester-runtime",
        )

    def dispatch_attempt(
        self,
        frame: Mapping[str, Any],
        *,
        wake_attempt: DeliveryAttempt | None = None,
        observed_at: str,
    ) -> ConsultationEventResult:
        item = validate_consultation(frame)
        if item["fingerprint"] == "":
            raise StateConflict("Runtime requires a normalized nonblank fingerprint")
        self._context = replace(
            self._context, consultation_id=item["consultation_id"]
        )
        if item["purpose"] != "QUESTION":
            raise StateConflict("dispatch requires the QUESTION frame")
        if not isinstance(wake_attempt, DeliveryAttempt):
            raise StateConflict("dispatch requires the exact typed Wake DeliveryAttempt")
        intent = self._intent_event(item)
        if intent is None:
            raise StateConflict("consultation INTENT must precede dispatch")
        self._require_intent_identity(item, intent)
        if self._event(item, "DISPATCH_ATTEMPT") is not None:
            if self._terminal_dispatch_state(item) is None:
                self._append(
                    item,
                    "EFFECT_UNKNOWN",
                    {
                        "schema_version": CONSULTATION_RECEIPT_SCHEMA,
                        "fact": "EFFECT_UNKNOWN",
                        "reason": "dispatch_attempt_without_terminal_receipt",
                        "wake_attempt_command_id": self._event(
                            item, "DISPATCH_ATTEMPT"
                        ).payload["wake_attempt_command_id"],
                        "sticky_binding": copy.deepcopy(item["recipient_binding"]),
                        "observed_at": _utc(observed_at),
                    },
                    actor="wake-runtime",
                )
                raise StateConflict(
                    "restart DISPATCH_ATTEMPT has no terminal receipt: EFFECT_UNKNOWN"
                )
            return ConsultationEventResult(
                event=self._event(item, "DISPATCH_ATTEMPT"), inserted=False
                )
        with self.runtime.store.read() as connection:
            binding = self._require_current_recipient(
                item, connection=connection
            )
            self._exact_wake_attempt(wake_attempt, item, binding, connection)
        return self._append(
            item,
            "DISPATCH_ATTEMPT",
            {
                "schema_version": CONSULTATION_RECEIPT_SCHEMA,
                "fact": "DISPATCH_ATTEMPT",
                "wake_obligation_id": wake_attempt.obligation_id,
                "wake_attempt_command_id": wake_attempt.attempt_command_id,
                "wake_attempt_n": wake_attempt.attempt_n,
                "wake_route_digest": wake_attempt.route_digest,
                "wake_destination_digest": wake_attempt.destination_digest,
                "recipient_binding": copy.deepcopy(item["recipient_binding"]),
                "observed_at": _utc(observed_at),
            },
            actor="wake-runtime",
        )

    def native_accepted(
        self,
        frame: Mapping[str, Any],
        *,
        native_thread_id: str,
        native_turn_id: str,
        wake_attempt_command_id: str,
        observed_at: str,
    ) -> ConsultationEventResult:
        item = validate_consultation(frame)
        if item["fingerprint"] == "":
            raise StateConflict("Runtime requires a normalized nonblank fingerprint")
        self._context = replace(
            self._context, consultation_id=item["consultation_id"]
        )
        self._require_fact_order(item, "NATIVE_ACCEPTED")
        with self.runtime.store.read() as connection:
            intent = self._intent_event(item)
            if intent is None:
                raise StateConflict("NATIVE_ACCEPTED requires consultation INTENT")
            self._require_intent_identity(item, intent)
            dispatch = self._event(item, "DISPATCH_ATTEMPT")
            assert dispatch is not None
            if (
                dispatch.payload.get("wake_attempt_command_id")
                != wake_attempt_command_id
            ):
                raise StateConflict(
                    "native evidence is not bound to the exact Wake attempt"
                )
            binding = self._require_current_recipient(item, connection=connection)
            self._require_persisted_wake_attempt(
                str(wake_attempt_command_id), item, binding, connection
            )
            projected = project_runtime_binding(
                self.runtime,
                item["recipient_actor_ref"]["attempt_id"],
                self._recipient_target(),
                connection=connection,
            )
            if projected.native_handle is None:
                raise StateConflict("current recipient has no managed Codex thread")
            if native_thread_id != projected.native_handle:
                raise StateConflict("native thread does not match the current binding")
            if not isinstance(native_turn_id, str) or not native_turn_id.strip():
                raise StateConflict("native turn id is required")
            return self._append(
                item,
                "NATIVE_ACCEPTED",
                {
                    "schema_version": CONSULTATION_RECEIPT_SCHEMA,
                    "fact": "NATIVE_ACCEPTED",
                    "evidence": {
                        "wake_attempt_command_id": wake_attempt_command_id,
                        "native_thread_id": native_thread_id,
                        "native_turn_id": native_turn_id,
                        "accepted": True,
                    },
                    "binding": copy.deepcopy(binding),
                    "observed_at": _utc(observed_at),
                },
                actor="codex-app-server-adapter",
            )

    def consumed_by_recipient(
        self,
        frame: Mapping[str, Any],
        *,
        native_thread_id: str,
        native_turn_id: str,
        observed_at: str,
    ) -> ConsultationEventResult:
        item = validate_consultation(frame)
        if item["fingerprint"] == "":
            raise StateConflict("Runtime requires a normalized nonblank fingerprint")
        self._context = replace(
            self._context, consultation_id=item["consultation_id"]
        )
        intent = self._intent_event(item)
        if intent is None:
            raise StateConflict("recipient consumption requires consultation INTENT")
        self._require_intent_identity(item, intent)
        with self.runtime.store.read() as connection:
            self._require_current_recipient(item, connection=connection)
            accepted = self._event(item, "NATIVE_ACCEPTED")
            if accepted is None:
                raise StateConflict("recipient consumption requires native acceptance")
            evidence = accepted.payload["evidence"]
            if (
                evidence["native_thread_id"] != native_thread_id
                or evidence["native_turn_id"] != native_turn_id
            ):
                raise StateConflict("recipient consumption identity drifted")
            return self._append(
                item,
                "CONSUMED_BY_RECIPIENT",
                {
                    "schema_version": CONSULTATION_RECEIPT_SCHEMA,
                    "fact": "CONSUMED_BY_RECIPIENT",
                    "message_key": item["message_key"],
                    "semantic_fingerprint": item["fingerprint"],
                    "evidence": dict(evidence),
                    "observed_at": _utc(observed_at),
                },
                actor="recipient-runtime",
            )

    def answer_available(
        self,
        frame: Mapping[str, Any],
        *,
        observed_at: str,
        historical: bool = False,
    ) -> ConsultationEventResult:
        item = validate_consultation(frame)
        self._context = replace(
            self._context, consultation_id=item["consultation_id"]
        )
        if item["purpose"] not in {"ANSWER", "CORRECTION"}:
            raise StateConflict("ANSWER_AVAILABLE requires an ANSWER frame")
        if item["fingerprint"] == "":
            raise StateConflict("Runtime requires a normalized nonblank fingerprint")
        request = self._request_for_answer(item)
        if self._event(request, "CONSUMED_BY_RECIPIENT") is None:
            raise StateConflict("answer availability requires recipient consumption")
        if item["recipient_actor_ref"] != request["recipient_actor_ref"]:
            raise StateConflict("answer recipient actor drifted")
        if item["recipient_binding"] != request["recipient_binding"]:
            raise StateConflict("answer recipient binding drifted")
        if self._artifact_digest(item) != self._artifact_digest(request):
            raise StateConflict("answer evidence revisions drifted")
        if item["correlation"]["request_message_key"] != request["message_key"]:
            raise StateConflict("answer correlation drifted")
        with self.runtime.store.transaction() as connection:
            events = self._events_on_connection(item, connection)
            if item["purpose"] == "CORRECTION":
                predecessor = item["supersedes_message_key"]
                predecessor_event = next(
                    (
                        event
                        for event in events
                        if event.event_type == "ANSWER_AVAILABLE"
                        and event.payload.get("message_key") == predecessor
                    ),
                    None,
                )
                if predecessor_event is None:
                    raise StateConflict(
                        "CORRECTION requires its exact predecessor ANSWER_AVAILABLE"
                    )
                previous_correction = next(
                    (
                        event
                        for event in events
                        if event.event_type == "ANSWER_AVAILABLE"
                        and event.payload.get("supersedes_message_key") == predecessor
                    ),
                    None,
                )
                if previous_correction is not None:
                    raise StateConflict("CORRECTION chain is not deterministic")
            reserved = next(
                (
                    event
                    for event in events
                    if event.event_type == "ANSWER_AVAILABLE"
                    and event.payload.get("historical") is False
                ),
                None,
            )
            same_answer = (
                reserved is not None
                and reserved.payload.get("answer_fingerprint") == item["fingerprint"]
            )
            historical = bool(historical) or _expired(
                str(request["valid_until"]), observed_at
            )
            if reserved is not None and not same_answer:
                if item["purpose"] == "CORRECTION":
                    return self._append_on_connection(
                        item,
                        "ANSWER_AVAILABLE",
                        self._answer_payload(
                            item, historical=True, observed_at=observed_at
                        ),
                        actor="dialogue-carrier",
                        connection=connection,
                    )
                payload = {
                    "schema_version": CONSULTATION_RECEIPT_SCHEMA,
                    "fact": "ANSWER_REFUSED",
                    "consultation_id": item["consultation_id"],
                    "refused_message_key": item["message_key"],
                    "answer_fingerprint": item["fingerprint"],
                    "semantic_answer_digest": _semantic_answer_digest(item),
                    "evidence_revision_digest": self._artifact_digest(item),
                    "historical": True,
                    "conflict": "ANSWER_ALREADY_RESERVED",
                    "supersedes_message_key": item["supersedes_message_key"],
                    "observed_at": _utc(observed_at),
                }
                return self._append_on_connection(
                    item,
                    "ANSWER_REFUSED",
                    payload,
                    actor="dialogue-carrier",
                    connection=connection,
                )
            if same_answer:
                replay_payload = {
                    "schema_version": CONSULTATION_RECEIPT_SCHEMA,
                    "fact": "ANSWER_AVAILABLE",
                    "consultation_id": item["consultation_id"],
                    "message_key": item["message_key"],
                    "answer_fingerprint": item["fingerprint"],
                    "semantic_answer_digest": _semantic_answer_digest(item),
                    "evidence_revision_digest": self._artifact_digest(item),
                    "historical": False,
                    "supersedes_message_key": item["supersedes_message_key"],
                    "observed_at": reserved.payload["observed_at"],
                }
                self._assert_replay(reserved, replay_payload)
                return ConsultationEventResult(event=reserved, inserted=False)
            return self._append_on_connection(
                item,
                "ANSWER_AVAILABLE",
                self._answer_payload(
                    item, historical=historical, observed_at=observed_at
                ),
                actor="dialogue-carrier",
                connection=connection,
            )

    def _answer_payload(
        self,
        item: Mapping[str, Any],
        *,
        historical: bool,
        observed_at: str,
    ) -> dict[str, Any]:
        return {
            "schema_version": CONSULTATION_RECEIPT_SCHEMA,
            "fact": "ANSWER_AVAILABLE",
            "consultation_id": item["consultation_id"],
            "message_key": item["message_key"],
            "answer_fingerprint": item["fingerprint"],
            "semantic_answer_digest": _semantic_answer_digest(item),
            "evidence_revision_digest": self._artifact_digest(item),
            "historical": historical,
            "supersedes_message_key": item["supersedes_message_key"],
            "observed_at": _utc(observed_at),
        }

    def consumed_by_requester(
        self,
        frame: Mapping[str, Any],
        *,
        observed_at: str,
    ) -> ConsultationEventResult:
        item = validate_consultation(frame)
        self._context = replace(
            self._context, consultation_id=item["consultation_id"]
        )
        request = self._request_for_answer(item)
        if item["requester_actor_ref"] != request["requester_actor_ref"]:
            raise StateConflict("answer requester actor drifted")
        if item["recipient_actor_ref"] != request["recipient_actor_ref"]:
            raise StateConflict("answer recipient actor drifted")
        if _expired(str(request["valid_until"]), observed_at):
            raise StateConflict("answer expired before requester consumption")
        with self.runtime.store.transaction() as connection:
            reserved = next(
                (
                    event
                    for event in self._events_on_connection(item, connection)
                    if event.event_type == "ANSWER_AVAILABLE"
                    and event.payload.get("answer_fingerprint")
                    == item["fingerprint"]
                ),
                None,
            )
            if reserved is None:
                raise StateConflict(
                    "requester consumption requires its exact reserved answer"
                )
            if reserved.payload.get("historical") is True:
                raise ConsultationConflict(
                    "historical answer cannot receive current credit",
                    conflict="HISTORICAL_ANSWER",
                )
            self._require_requester_on_connection(
                request,
                request["requester_actor_ref"]["attempt_id"],
                connection,
            )
            return self._append_on_connection(
                item,
                "CONSUMED_BY_REQUESTER",
                {
                    "schema_version": CONSULTATION_RECEIPT_SCHEMA,
                    "fact": "CONSUMED_BY_REQUESTER",
                    "consultation_id": item["consultation_id"],
                    "answer_fingerprint": item["fingerprint"],
                    "semantic_answer_digest": _semantic_answer_digest(item),
                    "requester_actor_ref": copy.deepcopy(item["requester_actor_ref"]),
                    "observed_at": _utc(observed_at),
                },
                actor="requester-runtime",
                connection=connection,
            )

    def resolve_restart(self, frame: Mapping[str, Any]) -> str:
        item = validate_consultation(frame)
        self._context = replace(
            self._context, consultation_id=item["consultation_id"]
        )
        if self._intent_event(item) is None:
            return "NOT_STARTED"
        if self._event(item, "DISPATCH_ATTEMPT") is None:
            return "NOT_DISPATCHED"
        if self._terminal_dispatch_state(item) is None:
            return "EFFECT_UNKNOWN"
        return "RESOLVED"

    def events(self, frame: Mapping[str, Any]) -> list[Event]:
        item = validate_consultation(frame)
        self._context = replace(
            self._context, consultation_id=item["consultation_id"]
        )
        prefix = self._command_prefix(item)
        return [
            event
            for event in self.runtime.events.list_events(
                aggregate_type="consultation", aggregate_id=item["consultation_id"]
            )
            if event.command_id.startswith(prefix)
        ]

    def _append(
        self,
        item: Mapping[str, Any],
        fact: str,
        payload: Mapping[str, Any],
        *,
        actor: str,
    ) -> ConsultationEventResult:
        command_id = self._command_id(item, fact)
        existing = self.runtime.events.get_event_by_command_id(command_id)
        if existing is not None:
            self._assert_replay(existing, payload)
            return ConsultationEventResult(event=existing, inserted=False)
        try:
            with self.runtime.store.transaction() as connection:
                existing_transaction = self.runtime.store.get_event_by_command_id(
                    command_id, connection=connection
                )
                if existing_transaction is not None:
                    self._assert_replay(existing_transaction, payload)
                    return ConsultationEventResult(
                        event=existing_transaction, inserted=False
                    )
                self.runtime.store.append_event(
                    connection,
                    aggregate_type="consultation",
                    aggregate_id=str(item["consultation_id"]),
                    event_type=fact,
                    command_id=command_id,
                    actor=actor,
                    job_id=str(item["requester_actor_ref"]["job_id"]),
                    attempt_id=str(item["requester_actor_ref"]["attempt_id"]),
                    worker_id=str(item["requester_actor_ref"]["worker_id"]),
                    payload=dict(payload),
                )
                written_event = self.runtime.store.get_event_by_command_id(
                    command_id, connection=connection
                )
                assert written_event is not None
                return ConsultationEventResult(event=written_event, inserted=True)
        except sqlite3.IntegrityError as exc:
            existing = self.runtime.events.get_event_by_command_id(command_id)
            if existing is not None:
                self._assert_replay(existing, payload)
                return ConsultationEventResult(event=existing, inserted=False)
            raise ConsultationConflict("duplicate key race is CONFLICT") from exc

    def _append_on_connection(
        self,
        item: Mapping[str, Any],
        fact: str,
        payload: Mapping[str, Any],
        *,
        actor: str,
        connection: sqlite3.Connection,
    ) -> ConsultationEventResult:
        command_id = self._command_id(item, fact)
        existing = self.runtime.store.get_event_by_command_id(
            command_id, connection=connection
        )
        if existing is not None:
            self._assert_replay(existing, payload)
            return ConsultationEventResult(event=existing, inserted=False)
        self.runtime.store.append_event(
            connection,
            aggregate_type="consultation",
            aggregate_id=str(item["consultation_id"]),
            event_type=fact,
            command_id=command_id,
            actor=actor,
            job_id=str(item["requester_actor_ref"]["job_id"]),
            attempt_id=str(item["requester_actor_ref"]["attempt_id"]),
            worker_id=str(item["requester_actor_ref"]["worker_id"]),
            payload=dict(payload),
        )
        written = self.runtime.store.get_event_by_command_id(
            command_id, connection=connection
        )
        assert written is not None
        return ConsultationEventResult(event=written, inserted=True)

    def _events_on_connection(
        self, item: Mapping[str, Any], connection: sqlite3.Connection
    ) -> list[Event]:
        rows = connection.execute(
            "SELECT * FROM events WHERE aggregate_type=? AND aggregate_id=? ORDER BY event_id",
            ("consultation", item["consultation_id"]),
        ).fetchall()
        events = [_event_from_row(row) for row in rows]
        return [event for event in events if event.command_id.startswith(self._command_prefix(item))]

    def _assert_replay(self, existing: Event, payload: Mapping[str, Any]) -> None:
        timestamped_keys = {"observed_at"}
        normalized_existing = {
            key: value
            for key, value in existing.payload.items()
            if key not in timestamped_keys
        }
        normalized_replay = {
            key: value for key, value in payload.items() if key not in timestamped_keys
        }
        if normalized_existing != normalized_replay:
            raise ConsultationConflict("duplicate consultation key is CONFLICT")

    def _require_fact_order(self, item: Mapping[str, Any], fact: str) -> None:
        if self._intent_event(item) is None:
            raise StateConflict(f"{fact} requires consultation INTENT")
        if fact == "NATIVE_ACCEPTED" and self._event(item, "DISPATCH_ATTEMPT") is None:
            raise StateConflict(f"{fact} requires consultation DISPATCH_ATTEMPT")

    def _require_intent_identity(
        self, item: Mapping[str, Any], intent: Event
    ) -> None:
        payload = intent.payload
        request = self._intent_from_event(intent)
        if (
            item["message_key"] != payload["message_key"]
            or item["consultation_id"] != payload["consultation_id"]
            or item["fingerprint"] != payload["semantic_fingerprint"]
            or item["requester_actor_ref"] != request["requester_actor_ref"]
            or item["recipient_actor_ref"] != request["recipient_actor_ref"]
            or item["recipient_binding"] != request["recipient_binding"]
            or item["correlation"] != request["correlation"]
            or item["artifact_revisions"] != request["artifact_revisions"]
            or item["valid_until"] != request["valid_until"]
            or item["deadline_ms"] != request["deadline_ms"]
            or item["response_budget"] != request["response_budget"]
        ):
            raise StateConflict("dispatch frame identity drifted from INTENT")

    def _require_requester(
        self, item: Mapping[str, Any], requester_attempt_id: str
    ) -> None:
        with self.runtime.store.read() as connection:
            self._require_requester_on_connection(
                item, requester_attempt_id, connection
            )

    def _require_requester_on_connection(
        self,
        item: Mapping[str, Any],
        requester_attempt_id: str,
        connection: sqlite3.Connection,
    ) -> None:
        actor = item["requester_actor_ref"]
        if actor["attempt_id"] != requester_attempt_id:
            raise StateConflict("requester actor is not the Runtime Attempt")
        row = connection.execute(
            "SELECT a.*,j.root_job_id AS job_root FROM attempts a JOIN jobs j ON j.job_id=a.job_id WHERE a.attempt_id=?",
            (requester_attempt_id,),
        ).fetchone()
        if (
            row is None
            or row["job_id"] != actor["job_id"]
            or row["worker_id"] != actor["worker_id"]
            or row["job_root"] is None
        ):
            raise StateConflict("requester actor is not Runtime-bound")

    def _require_current_recipient(
        self,
        item: Mapping[str, Any],
        *,
        connection: sqlite3.Connection | None = None,
    ) -> Mapping[str, Any]:
        binding = item["recipient_binding"]
        actor = item["recipient_actor_ref"]
        if connection is None:
            with self.runtime.store.read() as owned_connection:
                return self._require_current_recipient(
                    item, connection=owned_connection
                )
        target = self._recipient_target()
        projected = project_runtime_binding(
            self.runtime, actor["attempt_id"], target, connection=connection
        )
        if (
            projected.binding_id != binding["binding_id"]
            or projected.binding_generation != binding["binding_generation"]
            or projected.native_handle is None
            or binding["reasoning_surface"] != "codex"
        ):
            raise StateConflict("consultation recipient is not the current Runtime binding")
        return binding

    def _exact_wake_attempt(
        self,
        wake_attempt: DeliveryAttempt,
        item: Mapping[str, Any],
        binding: Mapping[str, Any],
        connection: sqlite3.Connection,
    ) -> None:
        repository = WakeLedgerRepository(self.runtime)
        records = repository.list_ledger_records_on_connection(
            connection, wake_attempt.obligation_id
        )
        requested = tuple(
            record for record in records if record.phase is LedgerPhase.WAKE_REQUESTED
        )
        if len(requested) != 1 or requested[0].obligation is None:
            raise StateConflict("Wake DeliveryAttempt has no canonical WAKE_REQUESTED evidence")
        delivery = tuple(
            record
            for record in records
            if record.phase is LedgerPhase.DELIVERY_ATTEMPT
        )
        if len(delivery) != 1 or delivery[0].command_id != wake_attempt.attempt_command_id:
            raise StateConflict("Wake DeliveryAttempt has no exact persisted evidence")
        if not delivery[0].matches_attempt(wake_attempt):
            raise StateConflict("Wake DeliveryAttempt evidence disagrees")
        if (
            wake_attempt.binding_id != binding["binding_id"]
            or wake_attempt.binding_generation != binding["binding_generation"]
            or wake_attempt.reasoning_surface != binding["reasoning_surface"]
        ):
            raise StateConflict("Wake DeliveryAttempt targets a different RuntimeBinding")
        identity = self._consultation_source_identity_on_connection(
            item, connection
        )
        if requested[0].obligation.source_ref != peer_attention_source_ref(identity):
            raise StateConflict("Wake DeliveryAttempt is not bound to consultation INTENT")

    def _require_persisted_wake_attempt(
        self,
        wake_attempt_command_id: str,
        item: Mapping[str, Any],
        binding: Mapping[str, Any],
        connection: sqlite3.Connection,
    ) -> None:
        repository = WakeLedgerRepository(self.runtime)
        identity = self._consultation_source_identity_on_connection(
            item, connection
        )
        records = repository.list_ledger_records_on_connection(
                connection,
                mint_obligation(
                    wake_kind=WakeKind.DIALOGUE_TURN_PENDING,
                    source_kind=SourceKind.AGENT_DIALOGUE_ATTENTION,
                    source_ref=peer_attention_source_ref(identity),
                    declared_target_seat="coo",
                    root_job_id=identity.root_job_id,
                ).obligation_id,
            )
        attempts = tuple(
            record
            for record in records
            if record.phase is LedgerPhase.DELIVERY_ATTEMPT
            and record.command_id == wake_attempt_command_id
        )
        if len(attempts) != 1:
            raise StateConflict("native evidence has no exact persisted Wake attempt")
        record = attempts[0]
        if (
            record.binding_id != binding["binding_id"]
            or record.binding_generation != binding["binding_generation"]
            or record.reasoning_surface != binding["reasoning_surface"]
        ):
            raise StateConflict("native evidence Wake attempt targets a different binding")

    def _consultation_source_identity_on_connection(
        self, item: Mapping[str, Any], connection: sqlite3.Connection
    ) -> ConsultationSourceIdentity:
        actor = item["recipient_actor_ref"]
        binding = item["recipient_binding"]
        return ConsultationSourceIdentity.create(
            consultation_id=item["consultation_id"],
            message_key=item["message_key"],
            semantic_fingerprint=item["fingerprint"],
            root_job_id=self._root_job_id_on_connection(
                actor["attempt_id"], connection
            ),
            requester_job_id=item["requester_actor_ref"]["job_id"],
            requester_attempt_id=item["requester_actor_ref"]["attempt_id"],
            recipient_job_id=actor["job_id"],
            recipient_attempt_id=actor["attempt_id"],
            binding_id=binding["binding_id"],
            binding_generation=binding["binding_generation"],
        )

    def _root_job_id_on_connection(
        self, attempt_id: str, connection: sqlite3.Connection
    ) -> str:
        row = connection.execute(
            "SELECT j.root_job_id FROM attempts a JOIN jobs j ON j.job_id=a.job_id WHERE a.attempt_id=?",
            (attempt_id,),
        ).fetchone()
        if row is None or row["root_job_id"] is None:
            raise StateConflict("consultation source requires a Runtime root Job")
        return row["root_job_id"]

    def _provider_session(self, binding: Mapping[str, Any]) -> str:
        del binding
        raise StateConflict("provider session lookup requires Runtime context")

    def _current_recipient_thread(self, item: Mapping[str, Any]) -> str:
        with self.runtime.store.read() as connection:
            self._require_current_recipient(item, connection=connection)
            projected = project_runtime_binding(
                self.runtime,
                item["recipient_actor_ref"]["attempt_id"],
                self._recipient_target(),
                connection=connection,
            )
        if projected.native_handle is None:
            raise StateConflict("current recipient has no managed Codex thread")
        return projected.native_handle

    def _recipient_target(self) -> SessionTarget:
        return SessionTarget(
            session_alias="CONSULTATION-RECIPIENT",
            target_seat="coo",
            reasoning_surface="codex",
            wake_transport="managed-codex-attention",
            allowed_transports=("managed-codex-attention",),
            workstream=None,
            target_enabled=True,
        )

    def _artifact_digest(self, item: Mapping[str, Any]) -> str:
        return hashlib.sha256(
            canonical_consultation_json(item["artifact_revisions"]).encode()
        ).hexdigest()

    def _validate_artifact_revisions(
        self, item: Mapping[str, Any], repository_root: Path | None
    ) -> None:
        for revision in item["artifact_revisions"]:
            path = revision["path"]
            if Path(path).is_absolute() or ".." in Path(path).parts:
                raise StateConflict("artifact revision path escapes repository")
            blob = subprocess.run(
                ["git", "show", f'{revision["commit"]}:{path}'],
                cwd=repository_root or self._context.repository_root,
                check=False,
                capture_output=True,
            ).stdout
            if (
                not blob
                or hashlib.sha256(blob).hexdigest() != revision["content_sha256"]
            ):
                raise StateConflict("artifact revision content digest disagrees")

    def _intent_event(self, item: Mapping[str, Any]) -> Event | None:
        return self._event(item, "INTENT")

    def _event(self, item: Mapping[str, Any], fact: str) -> Event | None:
        return self.runtime.events.get_event_by_command_id(
            self._command_id(item, fact)
        )

    def _terminal_dispatch_state(self, item: Mapping[str, Any]) -> str | None:
        native = self._event(item, "NATIVE_ACCEPTED")
        if native is not None:
            return native.event_type
        unknown = self._event(item, "EFFECT_UNKNOWN")
        if unknown is not None:
            return unknown.event_type
        return None

    def _request_for_answer(self, answer: Mapping[str, Any]) -> Mapping[str, Any]:
        for event in self.runtime.events.list_events(
            aggregate_type="consultation", aggregate_id=answer["consultation_id"]
        ):
            if event.event_type != "INTENT":
                continue
            if (
                event.payload.get("message_key")
                == answer["correlation"]["request_message_key"]
            ):
                return self._intent_from_event(event)
        raise StateConflict("answer has no correlated Runtime INTENT")

    def _intent_from_event(self, event: Event) -> Mapping[str, Any]:
        payload = event.payload
        return {
            "message_key": payload["message_key"],
            "consultation_id": payload["consultation_id"],
            "requester_actor_ref": payload["requester_actor_ref"],
            "recipient_actor_ref": payload["recipient_actor_ref"],
            "recipient_binding": payload["recipient_binding"],
            "correlation": payload["correlation"],
            "artifact_revisions": payload["artifact_revisions"],
            "response_budget": payload["response_budget"],
            "valid_until": payload["valid_until"],
            "deadline_ms": payload["deadline_ms"],
        }

    def _accepted_answer_digest(self) -> str | None:
        accepted = None
        for event in self.runtime.events.list_events(
            aggregate_type="consultation", aggregate_id=self._context.consultation_id
        ):
            if event.event_type != "CONSUMED_BY_REQUESTER":
                continue
            accepted = str(event.payload.get("semantic_answer_digest", ""))
        return accepted

    def _command_prefix(self, item: Mapping[str, Any]) -> str:
        return f"consult:{item['consultation_id']}:"

    def _command_id(self, item: Mapping[str, Any], fact: str) -> str:
        if fact in ANSWER_EVENTS or fact in REFUSAL_RECEIPT_EVENTS or fact in REFUSAL_EVENTS:
            return f"consult:{item['consultation_id']}:{fact}:{item['message_key']}"
        return self._command_prefix(item) + fact


def consultation_projection(runtime: Runtime) -> list[dict[str, Any]]:
    if not isinstance(runtime, Runtime):
        raise TypeError("projection requires the existing Executive Runtime")
    intents: dict[str, Event] = {}
    events: dict[str, list[Event]] = {}
    for event in runtime.events.list_events(aggregate_type="consultation"):
        consultation_id = str(event.aggregate_id)
        if event.event_type == "INTENT":
            intents[consultation_id] = event
        events.setdefault(consultation_id, []).append(event)
    result = []
    for consultation_id, intent in intents.items():
        payload = intent.payload
        stages = [event.event_type for event in events[consultation_id]]
        stage = next(
            (
                fact
                for fact in reversed(CONSULTATION_RECEIPT_EVENTS)
                if fact in stages
            ),
            None,
        )
        blocker = None
        if "EFFECT_UNKNOWN" in stages and "NATIVE_ACCEPTED" not in stages:
            blocker = "EFFECT_UNKNOWN"
        result.append(
            {
                "consultation_id": consultation_id,
                "sender": payload["requester_actor_ref"]["worker_id"],
                "recipient": payload["recipient_actor_ref"]["worker_id"],
                "question_digest": payload["question_digest"],
                "evidence_revisions": payload["artifact_revisions"],
                "current_receipt_stage": stage,
                "receipt_stage": stage,
                "deadline": payload["valid_until"],
                "blocker": blocker,
            }
        )
    return result
