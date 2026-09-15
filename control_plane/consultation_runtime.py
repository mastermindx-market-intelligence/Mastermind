"""Runtime consultation receipts as immutable event-plane observations."""
from __future__ import annotations

import copy
import hashlib
import json
import sqlite3
import subprocess

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Mapping

from common.agent_dialogue_consultation_contract import (
    canonical_consultation_json,
    validate_consultation,
)
from control_plane.executive_runtime import Event, Runtime, StateConflict
from control_plane.operator_harness_contract import runtime_binding_id_for


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
            "consultation_schema": item["schema"],
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
        wake_obligation_id: str,
        wake_attempt_command_id: str,
        observed_at: str,
    ) -> ConsultationEventResult:
        item = validate_consultation(frame)
        self._context = replace(
            self._context, consultation_id=item["consultation_id"]
        )
        if item["purpose"] != "QUESTION":
            raise StateConflict("dispatch requires the QUESTION frame")
        if (
            not isinstance(wake_obligation_id, str)
            or not wake_obligation_id.startswith("WAKE-")
        ):
            raise StateConflict("Wake obligation id is invalid")
        if wake_attempt_command_id.split(":", 1)[0] != wake_obligation_id:
            raise StateConflict("Wake attempt does not match its obligation")
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
                        "sticky_binding": copy.deepcopy(item["recipient_binding"]),
                        "observed_at": _utc(observed_at),
                    },
                    actor="wake-runtime",
                )
                raise StateConflict(
                    "restart DISPATCH_ATTEMPT has no terminal receipt: EFFECT_UNKNOWN"
                )
        self._require_current_recipient(item)
        return self._append(
            item,
            "DISPATCH_ATTEMPT",
            {
                "schema_version": CONSULTATION_RECEIPT_SCHEMA,
                "fact": "DISPATCH_ATTEMPT",
                "wake_obligation_id": wake_obligation_id,
                "wake_attempt_command_id": wake_attempt_command_id,
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
        observed_at: str,
    ) -> ConsultationEventResult:
        item = validate_consultation(frame)
        self._context = replace(
            self._context, consultation_id=item["consultation_id"]
        )
        self._require_fact_order(item, "NATIVE_ACCEPTED")
        intent = self._intent_event(item)
        if intent is None:
            raise StateConflict("NATIVE_ACCEPTED requires consultation INTENT")
        self._require_intent_identity(item, intent)
        binding = self._require_current_recipient(item)
        thread_id = self._current_recipient_thread(item)
        if native_thread_id != thread_id:
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
        self._context = replace(
            self._context, consultation_id=item["consultation_id"]
        )
        intent = self._intent_event(item)
        if intent is None:
            raise StateConflict("recipient consumption requires consultation INTENT")
        self._require_intent_identity(item, intent)
        self._require_current_recipient(item)
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
        if item["purpose"] != "ANSWER":
            raise StateConflict("ANSWER_AVAILABLE requires an ANSWER frame")
        request = self._request_for_answer(item)
        if self._event(request, "CONSUMED_BY_RECIPIENT") is None:
            raise StateConflict("answer availability requires recipient consumption")
        self._require_current_recipient(item)
        if self._artifact_digest(item) != self._artifact_digest(request):
            raise StateConflict("answer evidence revisions drifted")
        if item["correlation"]["request_message_key"] != request["message_key"]:
            raise StateConflict("answer correlation drifted")
        events = self.runtime.events.list_events(
            aggregate_type="consultation",
            aggregate_id=item["consultation_id"],
        )
        answer_count = sum(
            event.event_type == "ANSWER_AVAILABLE"
            for event in events
        )
        if answer_count >= item["response_budget"]["max_answers"]:
            return self._budget_exhausted(item, observed_at)
        latest_digest = self._accepted_answer_digest()
        historical = historical or (
            latest_digest is not None
            and latest_digest != _semantic_answer_digest(item)
        )
        return self._append(
            item,
            "ANSWER_AVAILABLE",
            {
                "schema_version": CONSULTATION_RECEIPT_SCHEMA,
                "fact": "ANSWER_AVAILABLE",
                "consultation_id": item["consultation_id"],
                "answer_fingerprint": item["fingerprint"],
                "semantic_answer_digest": _semantic_answer_digest(item),
                "evidence_revision_digest": self._artifact_digest(item),
                "historical": historical,
                "observed_at": _utc(observed_at),
            },
            actor="dialogue-carrier",
        )

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
        budget = self._event(item, "BUDGET_EXHAUSTED")
        if budget is not None and budget.event_type == "BUDGET_EXHAUSTED":
            raise StateConflict("answer budget exhausted")
        available = self._event(item, "ANSWER_AVAILABLE")
        if available is None:
            raise StateConflict("requester consumption requires an available answer")
        if available.payload.get("historical") is True:
            raise ConsultationConflict(
                "historical answer cannot alter newer acceptance",
                conflict="HISTORICAL_ANSWER",
            )
        self._require_requester(request, request["requester_actor_ref"]["attempt_id"])
        return self._append(
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
        )

    def _budget_exhausted(
        self,
        item: Mapping[str, Any],
        observed_at: str,
    ) -> ConsultationEventResult:
        answer_count = sum(
            event.event_type == "ANSWER_AVAILABLE"
            for event in self.runtime.events.list_events(
                aggregate_type="consultation",
                aggregate_id=item["consultation_id"],
            )
        )
        request = self._request_for_answer(item)
        if answer_count != request["response_budget"]["max_answers"]:
            raise StateConflict("answer budget is already exhausted")
        payload = {
            "schema_version": CONSULTATION_RECEIPT_SCHEMA,
            "fact": "BUDGET_EXHAUSTED",
            "consultation_id": item["consultation_id"],
            "refused_message_key": item["message_key"],
            "answer_fingerprint": item["fingerprint"],
            "semantic_answer_digest": _semantic_answer_digest(item),
            "evidence_revision_digest": self._artifact_digest(item),
            "historical": True,
            "conflict": "BUDGET_EXHAUSTED",
            "observed_at": _utc(observed_at),
        }
        return self._append_budget_receipt(item, payload)

    def _append_budget_receipt(
        self,
        item: Mapping[str, Any],
        payload: Mapping[str, Any],
    ) -> ConsultationEventResult:
        command_id = self._command_id(item, "BUDGET_EXHAUSTED")
        existing = self.runtime.events.get_event_by_command_id(command_id)
        if existing is not None:
            self._assert_replay(existing, payload)
            return ConsultationEventResult(event=existing, inserted=False)
        try:
            with self.runtime.store.transaction() as connection:
                existing = self.runtime.store.get_event_by_command_id(
                    command_id, connection=connection
                )
                if existing is not None:
                    self._assert_replay(existing, payload)
                    return ConsultationEventResult(
                        event=existing, inserted=False
                    )
                self.runtime.store.append_event(
                    connection,
                    aggregate_type="consultation",
                    aggregate_id=str(item["consultation_id"]),
                    event_type="BUDGET_EXHAUSTED",
                    command_id=command_id,
                    actor="dialogue-carrier",
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
        except sqlite3.IntegrityError as exc:
            existing = self.runtime.events.get_event_by_command_id(command_id)
            if existing is not None:
                self._assert_replay(existing, payload)
                return ConsultationEventResult(event=existing, inserted=False)
            raise ConsultationConflict("budget-exhausted race is CONFLICT") from exc

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
        actor = item["requester_actor_ref"]
        if actor["attempt_id"] != requester_attempt_id:
            raise StateConflict("requester actor is not the Runtime Attempt")
        with self.runtime.store.read() as connection:
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
        self, item: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        binding = item["recipient_binding"]
        actor = item["recipient_actor_ref"]
        with self.runtime.store.read() as connection:
            row = connection.execute(
                """
                SELECT e.session_epoch_id,e.attempt_id,e.worker_id,
                       e.provider_session_id,e.state,
                       g.generation_number,g.executive_writer_held
                FROM harness_session_epochs e
                JOIN process_generations g ON g.session_epoch_id=e.session_epoch_id
                WHERE e.attempt_id=? AND e.state='CURRENT'
                ORDER BY g.generation_number DESC LIMIT 1
                """,
                (actor["attempt_id"],),
            ).fetchone()
        expected = (
            runtime_binding_id_for(actor["attempt_id"], row["session_epoch_id"])
            if row is not None
            else None
        )
        if (
            row is None
            or row["attempt_id"] != actor["attempt_id"]
            or row["worker_id"] != actor["worker_id"]
            or not row["executive_writer_held"]
            or binding["binding_id"] != expected
            or binding["binding_generation"] != row["generation_number"]
            or binding["reasoning_surface"] != "codex"
        ):
            raise StateConflict("consultation recipient is not the current Runtime binding")
        return binding

    def _provider_session(self, binding: Mapping[str, Any]) -> str:
        del binding
        raise StateConflict("provider session lookup requires Runtime context")

    def _current_recipient_thread(self, item: Mapping[str, Any]) -> str:
        actor = item["recipient_actor_ref"]
        with self.runtime.store.read() as connection:
            row = connection.execute(
                """
                SELECT e.provider_session_id,e.state
                FROM harness_session_epochs e
                WHERE e.attempt_id=? AND e.state='CURRENT'
                ORDER BY e.epoch_number DESC LIMIT 1
                """,
                (actor["attempt_id"],),
            ).fetchone()
        if row is None or not str(row["provider_session_id"] or "").strip():
            raise StateConflict("current recipient has no managed Codex thread")
        return str(row["provider_session_id"])

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
        if self._event(item, "EFFECT_UNKNOWN") is not None:
            return None
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
        if fact in ANSWER_EVENTS or fact in REFUSAL_RECEIPT_EVENTS:
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
