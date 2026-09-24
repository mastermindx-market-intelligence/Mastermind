"""Runtime consultation receipts as immutable event-plane observations."""
from __future__ import annotations

import copy
import hashlib
import json
import sqlite3
import subprocess
from datetime import datetime

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable, Mapping

from common.agent_dialogue_consultation_contract import (
    CONSULTATION_V2_SCHEMA,
    canonical_consultation_json,
    validate_consultation,
)
from common.agent_dialogue_contract_v2 import _UTC_RE
from control_plane.executive_runtime import (
    Event,
    Runtime,
    StateConflict,
    _event_from_row,
)
from control_plane.dialogue_source_resolution import (
    ConsultationSourceIdentity,
    RequesterAnswerAvailableSourceIdentity,
    peer_attention_source_ref,
    requester_answer_attention_source_ref,
)
from control_plane.runtime_binding_projection import (
    project_runtime_binding,
    reasoning_surface_for_provider,
)
from control_plane.session_targets import RuntimeBinding, SessionTarget
from control_plane.wake_ledger import (
    LedgerPhase,
    ObligationStatus,
    assert_causal,
    reconstruct_status,
)
from control_plane.wake_events import (
    SourceKind,
    WakeKind,
    WakeObligation,
    mint_obligation,
    utc_now_iso,
)
from control_plane.wake_persist import WakeLedgerRepository


CONSULTATION_INTENT_SCHEMA = "mastermind.consultation_intent/v2"
CONSULTATION_RECEIPT_SCHEMA = "mastermind.consultation_receipt/v1"
CONSULTATION_RECEIPT_EVENTS = (
    "INTENT",
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
class RequesterAnswerAttentionProjection:
    identity: RequesterAnswerAvailableSourceIdentity
    target: SessionTarget
    binding: RuntimeBinding
    obligation: WakeObligation


@dataclass(frozen=True)
class _ConsultationRuntimeContext:
    repository_root: Path
    consultation_id: str | None = None


def _utc(value: str) -> str:
    if not isinstance(value, str) or _UTC_RE.fullmatch(value) is None:
        raise StateConflict("observed_at must be a UTC timestamp")
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise StateConflict("observed_at must be a UTC timestamp") from None
    return value


def _utc_instant(value: str) -> datetime:
    return datetime.fromisoformat(_utc(value).replace("Z", "+00:00"))


def _expired(valid_until: str, observed_at: str) -> bool:
    return _utc_instant(observed_at) > _utc_instant(valid_until)


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


def _require_normalized(item: Mapping[str, Any]) -> None:
    if item["fingerprint"] == "":
        raise StateConflict("Runtime requires a normalized nonblank fingerprint")


def _identity_digest(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_consultation_json(value).encode()).hexdigest()


def _question_message_key(item: Mapping[str, Any]) -> str:
    """Resolve the request key without changing protected v1 frame bytes."""

    if item["schema"] == CONSULTATION_V2_SCHEMA:
        return str(item["question_message_key"])
    return str(item["correlation"]["request_message_key"])


def _consultation_intent_payload(
    item: Mapping[str, Any],
    *,
    requester_binding: Mapping[str, Any],
    carrier_ref: str,
    trusted_observed_at: str,
) -> dict[str, Any]:
    return {
        "schema_version": CONSULTATION_INTENT_SCHEMA,
        "consultation_schema": item["schema"],
        "message_key": item["message_key"],
        "consultation_id": item["consultation_id"],
        "semantic_fingerprint": item["fingerprint"],
        "carrier_ref": str(carrier_ref),
        "requester_actor_ref": copy.deepcopy(item["requester_actor_ref"]),
        "requester_binding": copy.deepcopy(dict(requester_binding)),
        "recipient_actor_ref": copy.deepcopy(item["recipient_actor_ref"]),
        "recipient_peer_ref": copy.deepcopy(item["recipient_peer_ref"]),
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
        "observed_at": _utc(trusted_observed_at),
    }


class ConsultationRuntime:
    """Own consultation facts without changing Job/Attempt lifecycle state."""

    def __init__(
        self,
        runtime: Runtime,
        *,
        repository_root: Path,
        _clock: Callable[[], str] | None = None,
    ) -> None:
        if not isinstance(runtime, Runtime):
            raise TypeError("runtime must be the existing Executive Runtime")
        if _clock is not None and not callable(_clock):
            raise TypeError("_clock must be callable")
        self.runtime = runtime
        self._clock = _clock or utc_now_iso
        self._context = _ConsultationRuntimeContext(
            Path(repository_root).resolve()
        )

    def _trusted_observed_at(self, claimed_observed_at: str) -> str:
        """Validate the compatibility claim but derive authority from trusted time."""

        _utc(claimed_observed_at)
        return _utc(self._clock())

    def _latest_observed_at_on_connection(
        self,
        item: Mapping[str, Any],
        connection: sqlite3.Connection,
    ) -> str | None:
        latest_token: str | None = None
        latest_instant: datetime | None = None
        for event in self._events_on_connection(item, connection):
            candidate = event.payload.get("observed_at")
            if candidate is None:
                continue
            candidate_token = _utc(str(candidate))
            candidate_instant = _utc_instant(candidate_token)
            if latest_instant is None or candidate_instant > latest_instant:
                latest_token = candidate_token
                latest_instant = candidate_instant
        return latest_token

    def _fenced_trusted_observed_at(
        self,
        claimed_observed_at: str,
        item: Mapping[str, Any],
        connection: sqlite3.Connection,
    ) -> str:
        trusted = self._trusted_observed_at(claimed_observed_at)
        latest = self._latest_observed_at_on_connection(item, connection)
        if latest is not None and _utc_instant(trusted) < _utc_instant(latest):
            raise StateConflict(
                "trusted clock regressed below durable consultation time"
            )
        return trusted

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
        _require_normalized(item)
        trusted_observed_at = self._trusted_observed_at(observed_at)
        self._context = replace(
            self._context, consultation_id=item["consultation_id"]
        )
        self._validate_artifact_revisions(item, repository_root)
        with self.runtime.store.transaction() as connection:
            self._require_requester_on_connection(
                item, requester_attempt_id, connection
            )
            _requester_target, requester_binding = (
                self._requester_target_and_binding_on_connection(
                    requester_attempt_id, connection
                )
            )
            self._require_current_recipient(item, connection=connection)
            payload = _consultation_intent_payload(
                item,
                requester_binding={
                    "binding_id": requester_binding.binding_id,
                    "binding_generation": requester_binding.binding_generation,
                    "reasoning_surface": requester_binding.reasoning_surface,
                },
                carrier_ref=carrier_ref,
                trusted_observed_at=trusted_observed_at,
            )
            return self._append_on_connection(
                item,
                "INTENT",
                payload,
                actor="requester-runtime",
                connection=connection,
            )


    def answer_available(
        self,
        frame: Mapping[str, Any],
        *,
        observed_at: str,
    ) -> ConsultationEventResult:
        item = validate_consultation(frame)
        self._context = replace(
            self._context, consultation_id=item["consultation_id"]
        )
        if item["purpose"] not in {"ANSWER", "CORRECTION"}:
            raise StateConflict("ANSWER_AVAILABLE requires an ANSWER frame")
        _require_normalized(item)
        with self.runtime.store.transaction() as connection:
            trusted_observed_at = self._fenced_trusted_observed_at(
                observed_at, item, connection
            )
            request = self._request_for_answer_on_connection(item, connection)
            if item["requester_actor_ref"] != request["requester_actor_ref"]:
                raise StateConflict("answer requester actor drifted")
            if item["recipient_actor_ref"] != request["recipient_actor_ref"]:
                raise StateConflict("answer recipient actor drifted")
            if item["recipient_peer_ref"] != request["recipient_peer_ref"]:
                raise StateConflict("answer recipient peer drifted")
            if item["recipient_binding"] != request["recipient_binding"]:
                raise StateConflict("answer recipient binding drifted")
            if self._artifact_digest(item) != self._artifact_digest(request):
                raise StateConflict("answer evidence revisions drifted")
            if item["correlation"] != request["correlation"]:
                raise StateConflict("answer correlation drifted")
            if _question_message_key(item) != request["message_key"]:
                raise StateConflict("answer request identity drifted")
            self._require_wake_consumption(item, request, connection)
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
            semantic_answer_digest = _semantic_answer_digest(item)
            evidence_revision_digest = self._artifact_digest(item)
            same_answer = (
                reserved is not None
                and reserved.payload.get("message_key") == item["message_key"]
                and reserved.payload.get("answer_fingerprint") == item["fingerprint"]
                and reserved.payload.get("semantic_answer_digest")
                == semantic_answer_digest
                and reserved.payload.get("evidence_revision_digest")
                == evidence_revision_digest
                and reserved.payload.get("supersedes_message_key")
                == item["supersedes_message_key"]
            )
            historical = _expired(
                str(request["valid_until"]), trusted_observed_at
            )
            if (
                reserved is not None
                and reserved.payload.get("message_key") == item["message_key"]
                and not same_answer
            ):
                raise ConsultationConflict(
                    "answer replay payload conflicts",
                    conflict="CONFLICT",
                )
            if reserved is not None and not same_answer:
                if item["purpose"] == "CORRECTION":
                    return self._append_on_connection(
                        item,
                        "ANSWER_AVAILABLE",
                        self._answer_payload(
                            item,
                            historical=True,
                            observed_at=trusted_observed_at,
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
                    "observed_at": trusted_observed_at,
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
                    item,
                    historical=historical,
                    observed_at=trusted_observed_at,
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

    def requester_answer_attention(
        self,
        frame: Mapping[str, Any],
        *,
        requester_attempt_id: str,
    ) -> RequesterAnswerAttentionProjection:
        """Project one requester-directed answer obligation without writing state."""

        item = validate_consultation(frame)
        if item["purpose"] not in {"ANSWER", "CORRECTION"}:
            raise StateConflict(
                "requester answer attention requires an ANSWER frame"
            )
        _require_normalized(item)
        with self.runtime.store.read() as connection:
            request = self._request_for_answer_on_connection(item, connection)
            if item["requester_actor_ref"] != request["requester_actor_ref"]:
                raise StateConflict("answer requester actor drifted")
            if item["recipient_actor_ref"] != request["recipient_actor_ref"]:
                raise StateConflict("answer recipient actor drifted")
            if item["recipient_binding"] != request["recipient_binding"]:
                raise StateConflict("answer recipient binding drifted")
            if item["recipient_peer_ref"] != request["recipient_peer_ref"]:
                raise StateConflict("answer recipient peer drifted")
            if item["correlation"] != request["correlation"]:
                raise StateConflict("answer correlation drifted")
            if _question_message_key(item) != request["message_key"]:
                raise StateConflict("answer request identity drifted")
            if self._artifact_digest(item) != self._artifact_digest(request):
                raise StateConflict("answer evidence revisions drifted")
            self._require_requester_on_connection(
                request, requester_attempt_id, connection
            )
            semantic_digest = _semantic_answer_digest(item)
            evidence_digest = self._artifact_digest(item)
            answers = tuple(
                event
                for event in self._events_on_connection(item, connection)
                if event.event_type == "ANSWER_AVAILABLE"
                and event.payload.get("message_key") == item["message_key"]
                and event.payload.get("answer_fingerprint") == item["fingerprint"]
                and event.payload.get("semantic_answer_digest") == semantic_digest
                and event.payload.get("evidence_revision_digest") == evidence_digest
            )
            if len(answers) != 1:
                raise StateConflict(
                    "requester answer attention requires one exact admitted answer"
                )
            answer = answers[0]
            if answer.payload.get("historical") is True:
                raise ConsultationConflict(
                    "historical answer cannot request current attention",
                    conflict="HISTORICAL_ANSWER",
                )
            consumed = any(
                event.event_type == "CONSUMED_BY_REQUESTER"
                and event.payload.get("answer_message_key")
                == item["message_key"]
                and event.payload.get("answer_fingerprint")
                == item["fingerprint"]
                and event.payload.get("semantic_answer_digest")
                == semantic_digest
                and event.payload.get("evidence_revision_digest")
                == evidence_digest
                for event in self._events_on_connection(item, connection)
            )
            if consumed:
                raise ConsultationConflict(
                    "answer is already consumed by requester",
                    conflict="ANSWER_ALREADY_CONSUMED",
                )

            target, binding = self._requester_target_and_binding_on_connection(
                requester_attempt_id, connection
            )
            frozen_binding = request.get("requester_binding")
            if (
                not isinstance(frozen_binding, Mapping)
                or set(frozen_binding)
                != {"binding_id", "binding_generation", "reasoning_surface"}
                or frozen_binding["binding_id"] != binding.binding_id
                or frozen_binding["binding_generation"]
                != binding.binding_generation
                or frozen_binding["reasoning_surface"]
                != binding.reasoning_surface
            ):
                raise StateConflict("original requester binding is stale")
            surface = str(frozen_binding["reasoning_surface"])
            root_job_id = self._root_job_id_on_connection(
                requester_attempt_id, connection
            )
            identity = RequesterAnswerAvailableSourceIdentity.create(
                consultation_id=item["consultation_id"],
                answer_message_key=item["message_key"],
                answer_fingerprint=item["fingerprint"],
                semantic_answer_digest=semantic_digest,
                root_job_id=root_job_id,
                requester_job_id=request["requester_actor_ref"]["job_id"],
                requester_attempt_id=requester_attempt_id,
                requester_binding_id=str(frozen_binding["binding_id"]),
                requester_binding_generation=int(
                    frozen_binding["binding_generation"]
                ),
                requester_reasoning_surface=surface,
            )
            obligation = mint_obligation(
                wake_kind=WakeKind.CONSULTATION_ANSWER_AVAILABLE,
                source_kind=SourceKind.CONSULTATION_ANSWER_ATTENTION,
                source_ref=requester_answer_attention_source_ref(identity),
                declared_target_seat=target.target_seat,
                job_id=identity.requester_job_id,
                attempt_id=identity.requester_attempt_id,
                root_job_id=identity.root_job_id,
            )
            return RequesterAnswerAttentionProjection(
                identity=identity,
                target=target,
                binding=binding,
                obligation=obligation,
            )

    def assert_requester_answer_attention_current(
        self,
        projection: RequesterAnswerAttentionProjection,
        *,
        connection: sqlite3.Connection,
    ) -> None:
        """Revalidate one projection at the first durable Wake boundary."""

        if not isinstance(projection, RequesterAnswerAttentionProjection):
            raise TypeError(
                "projection must be RequesterAnswerAttentionProjection"
            )
        if not connection.in_transaction:
            raise StateConflict(
                "requester answer currentness requires an active transaction"
            )
        identity = projection.identity
        events = self._events_on_connection(
            {"consultation_id": identity.consultation_id}, connection
        )
        intents = tuple(
            event for event in events if event.event_type == "INTENT"
        )
        if len(intents) != 1:
            raise StateConflict(
                "requester answer attention requires one exact Runtime INTENT"
            )
        request = self._intent_from_event(intents[0])
        frozen_binding = request.get("requester_binding")
        actor = request.get("requester_actor_ref")
        if (
            not isinstance(actor, Mapping)
            or actor.get("job_id") != identity.requester_job_id
            or actor.get("attempt_id") != identity.requester_attempt_id
            or not isinstance(frozen_binding, Mapping)
            or frozen_binding.get("binding_id")
            != identity.requester_binding_id
            or frozen_binding.get("binding_generation")
            != identity.requester_binding_generation
            or frozen_binding.get("reasoning_surface")
            != identity.requester_reasoning_surface
            or self._root_job_id_on_connection(
                identity.requester_attempt_id, connection
            )
            != identity.root_job_id
        ):
            raise StateConflict(
                "requester answer source drifted from its Runtime INTENT"
            )

        current_answers = tuple(
            event
            for event in events
            if event.event_type == "ANSWER_AVAILABLE"
            and event.payload.get("historical") is False
        )
        exact_answers = tuple(
            event
            for event in current_answers
            if event.payload.get("message_key")
            == identity.answer_message_key
            and event.payload.get("answer_fingerprint")
            == identity.answer_fingerprint
            and event.payload.get("semantic_answer_digest")
            == identity.semantic_answer_digest
        )
        if len(current_answers) != 1 or len(exact_answers) != 1:
            raise StateConflict(
                "requester answer attention source is not the current answer"
            )
        consumed = any(
            event.event_type == "CONSUMED_BY_REQUESTER"
            and event.payload.get("answer_message_key")
            == identity.answer_message_key
            and event.payload.get("answer_fingerprint")
            == identity.answer_fingerprint
            and event.payload.get("semantic_answer_digest")
            == identity.semantic_answer_digest
            for event in events
        )
        if consumed:
            raise ConsultationConflict(
                "answer is already consumed by requester",
                conflict="ANSWER_ALREADY_CONSUMED",
            )

        target, binding = self._requester_target_and_binding_on_connection(
            identity.requester_attempt_id, connection
        )
        if (
            target != projection.target
            or binding != projection.binding
            or binding.binding_id != identity.requester_binding_id
            or binding.binding_generation
            != identity.requester_binding_generation
            or binding.reasoning_surface
            != identity.requester_reasoning_surface
        ):
            raise StateConflict(
                "original requester binding is stale"
            )

    def consumed_by_requester(
        self,
        frame: Mapping[str, Any],
        *,
        requester_attempt_id: str,
        observed_at: str,
    ) -> ConsultationEventResult:
        item = validate_consultation(frame)
        _require_normalized(item)
        self._context = replace(
            self._context, consultation_id=item["consultation_id"]
        )
        with self.runtime.store.transaction() as connection:
            trusted_observed_at = self._fenced_trusted_observed_at(
                observed_at, item, connection
            )
            request = self._request_for_answer_on_connection(item, connection)
            if item["requester_actor_ref"] != request["requester_actor_ref"]:
                raise StateConflict("answer requester actor drifted")
            if item["recipient_actor_ref"] != request["recipient_actor_ref"]:
                raise StateConflict("answer recipient actor drifted")
            if item["recipient_binding"] != request["recipient_binding"]:
                raise StateConflict("answer recipient binding drifted")
            if item["recipient_peer_ref"] != request["recipient_peer_ref"]:
                raise StateConflict("answer recipient peer drifted")
            if item["correlation"] != request["correlation"]:
                raise StateConflict("answer correlation drifted")
            if _question_message_key(item) != request["message_key"]:
                raise StateConflict("answer request identity drifted")
            if self._artifact_digest(item) != self._artifact_digest(request):
                raise StateConflict("answer evidence revisions drifted")
            if _expired(
                str(request["valid_until"]), trusted_observed_at
            ):
                raise StateConflict("answer expired before requester consumption")
            reserved = next(
                (
                    event
                    for event in self._events_on_connection(item, connection)
                    if event.event_type == "ANSWER_AVAILABLE"
                    and event.payload.get("message_key") == item["message_key"]
                    and event.payload.get("answer_fingerprint")
                    == item["fingerprint"]
                    and event.payload.get("semantic_answer_digest")
                    == _semantic_answer_digest(item)
                    and event.payload.get("evidence_revision_digest")
                    == self._artifact_digest(item)
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
                requester_attempt_id,
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
                    "answer_message_key": item["message_key"],
                    "request_message_key": request["message_key"],
                    "semantic_answer_digest": _semantic_answer_digest(item),
                    "requester_actor_digest": request["correlation"][
                        "requester_actor_digest"
                    ],
                    "recipient_actor_digest": request["correlation"][
                        "recipient_actor_digest"
                    ],
                    "recipient_binding": copy.deepcopy(request["recipient_binding"]),
                    "correlation_digest": _identity_digest(request["correlation"]),
                    "evidence_revision_digest": self._artifact_digest(item),
                    "requester_actor_ref": copy.deepcopy(item["requester_actor_ref"]),
                    "observed_at": trusted_observed_at,
                },
                actor="requester-runtime",
                connection=connection,
            )

    def resolve_restart(self, frame: Mapping[str, Any]) -> str:
        item = validate_consultation(frame)
        _require_normalized(item)
        self._context = replace(
            self._context, consultation_id=item["consultation_id"]
        )
        intent = self._intent_event(item)
        if intent is None:
            return "NOT_STARTED"
        self._require_intent_identity(item, intent)
        return self._canonical_wake_state(item).value

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

    def _requester_target_and_binding_on_connection(
        self,
        requester_attempt_id: str,
        connection: sqlite3.Connection,
    ) -> tuple[SessionTarget, RuntimeBinding]:
        facts = self.runtime.current_harness_binding_source(
            requester_attempt_id, connection=connection
        )
        surface = reasoning_surface_for_provider(facts.provider)
        if surface != "codex":
            raise StateConflict(
                "requester answer attention transport is unavailable"
            )
        target = SessionTarget(
            session_alias="CONSULTATION-REQUESTER",
            target_seat=facts.owner_seat,
            reasoning_surface=surface,
            wake_transport="codex-app-server",
            allowed_transports=("codex-app-server",),
            workstream=None,
            target_enabled=True,
        )
        return target, project_runtime_binding(
            self.runtime,
            requester_attempt_id,
            target,
            connection=connection,
        )

    def _require_current_recipient(
        self,
        item: Mapping[str, Any],
        *,
        connection: sqlite3.Connection | None = None,
    ) -> RuntimeBinding:
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
            or projected.reasoning_surface != "codex"
            or binding["reasoning_surface"] != projected.reasoning_surface
        ):
            raise StateConflict("consultation recipient is not the current Runtime binding")
        return projected

    def _exact_wake_evidence_on_connection(
        self,
        item: Mapping[str, Any],
        connection: sqlite3.Connection,
    ) -> tuple[str, ObligationStatus]:
        expected_binding = item["recipient_binding"]
        expected_target = self._recipient_target()
        if expected_binding["reasoning_surface"] != expected_target.reasoning_surface:
            raise StateConflict(
                "consultation INTENT binding does not match its recipient target"
            )
        repository = WakeLedgerRepository(self.runtime)
        identity = self._consultation_source_identity_on_connection(item, connection)
        obligation = mint_obligation(
            wake_kind=WakeKind.DIALOGUE_TURN_PENDING,
            source_kind=SourceKind.AGENT_DIALOGUE_ATTENTION,
            source_ref=peer_attention_source_ref(identity),
            declared_target_seat="coo",
            root_job_id=identity.root_job_id,
        )
        records = repository.list_ledger_records_on_connection(
            connection, obligation.obligation_id
        )
        requested = tuple(
            record for record in records if record.phase is LedgerPhase.WAKE_REQUESTED
        )
        if not records:
            return obligation.obligation_id, ObligationStatus.NOT_SEEN
        if len(requested) != 1 or requested[0].obligation is None:
            raise StateConflict("Wake evidence has no exact canonical WAKE_REQUESTED")
        frozen = requested[0].obligation
        if (
            frozen.obligation_id != obligation.obligation_id
            or frozen.wake_kind is not obligation.wake_kind
            or frozen.source_kind is not obligation.source_kind
            or frozen.source_ref != obligation.source_ref
            or frozen.declared_target_seat != obligation.declared_target_seat
            or frozen.root_job_id != obligation.root_job_id
            or frozen.job_id != obligation.job_id
            or frozen.attempt_id != obligation.attempt_id
        ):
            raise StateConflict("Wake evidence is not bound to consultation INTENT")
        try:
            assert_causal(records)
        except ValueError as exc:
            raise StateConflict("Wake evidence is not a canonical causal stream") from exc
        attempt_phases = {
            LedgerPhase.DELIVERY_ATTEMPT,
            LedgerPhase.ACCEPTED,
            LedgerPhase.DELIVERED,
            LedgerPhase.FAILED,
            LedgerPhase.TARGET_UNAVAILABLE,
        }
        attempts = tuple(
            record for record in records if record.phase in attempt_phases
        )
        for record in attempts:
            if (
                record.binding_id != expected_binding["binding_id"]
                or record.binding_generation
                != expected_binding["binding_generation"]
                or record.session_alias != expected_target.session_alias
                or record.reasoning_surface
                != expected_binding["reasoning_surface"]
            ):
                raise StateConflict(
                    "Wake attempt is not bound to the current RuntimeBinding"
                )
        destinations = {
            str(record.destination_digest)
            for record in attempts
            if record.destination_digest is not None
        }
        if len(destinations) > 1:
            raise StateConflict("Wake evidence spans more than one exact destination")
        destination_digest = next(iter(destinations), None)
        return obligation.obligation_id, reconstruct_status(
            obligation.obligation_id,
            records,
            destination_digest=destination_digest,
        )

    def _canonical_wake_state(self, item: Mapping[str, Any]) -> ObligationStatus:
        with self.runtime.store.read() as connection:
            return self._exact_wake_evidence_on_connection(item, connection)[1]

    def _require_wake_consumption(
        self,
        item: Mapping[str, Any],
        request: Mapping[str, Any],
        connection: sqlite3.Connection,
    ) -> None:
        self._require_current_recipient(item, connection=connection)
        obligation_id, status = self._exact_wake_evidence_on_connection(
            request, connection
        )
        if status is not ObligationStatus.TARGET_ACKNOWLEDGED:
            raise StateConflict(
                "answer requires canonical TARGET_ACKNOWLEDGED Wake evidence: "
                f"{obligation_id} {status.value}"
            )

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

    def _recipient_target(self) -> SessionTarget:
        return SessionTarget(
            session_alias="CONSULTATION-RECIPIENT",
            target_seat="coo",
            reasoning_surface="codex",
            wake_transport="codex-app-server",
            allowed_transports=("codex-app-server",),
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

    def _request_for_answer_on_connection(
        self, answer: Mapping[str, Any], connection: sqlite3.Connection
    ) -> Mapping[str, Any]:
        for event in self._events_on_connection(answer, connection):
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
        requester_binding = payload.get("requester_binding")
        if (
            payload.get("schema_version") != CONSULTATION_INTENT_SCHEMA
            or not isinstance(requester_binding, Mapping)
            or set(requester_binding)
            != {"binding_id", "binding_generation", "reasoning_surface"}
        ):
            raise StateConflict(
                "consultation INTENT lacks immutable requester binding"
            )
        return {
            "message_key": payload["message_key"],
            "consultation_id": payload["consultation_id"],
            "fingerprint": payload["semantic_fingerprint"],
            "requester_actor_ref": payload["requester_actor_ref"],
            "requester_binding": copy.deepcopy(requester_binding),
            "recipient_actor_ref": payload["recipient_actor_ref"],
            "recipient_binding": payload["recipient_binding"],
            "recipient_peer_ref": payload["recipient_peer_ref"],
            "correlation": payload["correlation"],
            "artifact_revisions": payload["artifact_revisions"],
            "response_budget": payload["response_budget"],
            "valid_until": payload["valid_until"],
            "deadline_ms": payload["deadline_ms"],
        }

    def _command_prefix(self, item: Mapping[str, Any]) -> str:
        return f"consult:{item['consultation_id']}:"

    def _command_id(self, item: Mapping[str, Any], fact: str) -> str:
        if fact in ANSWER_EVENTS or fact in REFUSAL_RECEIPT_EVENTS or fact in REFUSAL_EVENTS:
            return f"consult:{item['consultation_id']}:{fact}:{item['message_key']}"
        return self._command_prefix(item) + fact


def consultation_projection(runtime: Runtime) -> list[dict[str, Any]]:
    if not isinstance(runtime, Runtime):
        raise TypeError("projection requires the existing Executive Runtime")
    consultations = ConsultationRuntime(runtime, repository_root=Path.cwd())
    result = []
    for event in runtime.events.list_events(aggregate_type="consultation"):
        if event.event_type != "INTENT":
            continue
        payload = event.payload
        try:
            state = consultations._canonical_wake_state(
                consultations._intent_from_event(event)
            ).value
        except StateConflict:
            state = ObligationStatus.RECONCILIATION_REQUIRED.value
            blocker = "WAKE_STATE_UNAVAILABLE"
        else:
            blocker = (
                None
                if state in {"TARGET_ACKNOWLEDGED", "SOURCE_RESOLVED"}
                else state
            )
        result.append(
            {
                "consultation_id": event.aggregate_id,
                "sender_digest": hashlib.sha256(
                    payload["requester_actor_ref"]["worker_id"].encode()
                ).hexdigest(),
                "recipient_digest": hashlib.sha256(
                    payload["recipient_actor_ref"]["worker_id"].encode()
                ).hexdigest(),
                "question_digest": payload["question_digest"],
                "evidence_revision_digest": payload["artifact_revision_digest"],
                "current_wake_state": state,
                "wake_state": state,
                "deadline": payload["valid_until"],
                "blocker": blocker,
            }
        )
    return result
