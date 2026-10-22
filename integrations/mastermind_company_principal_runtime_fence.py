"""Runtime-backed single-COMMIT owner for the COO-principal Dialogue facet.

This host-composition layer reuses the existing Executive Runtime event store and
the existing Agent Dialogue read/send carrier. It creates no table, listener,
queue, retry plane, wake owner, identity store, or provider/session registry.

The first exact principal edge writes one COMMIT_STARTED event immediately before
Relay COMMIT. Any replay of that message key is refused before a second COMMIT.
Reconciliation is read-only: the stored original binding is used to inspect the
same Dialogue carrier and classify the exact message as APPLIED, EFFECT_UNKNOWN,
NOT_APPLIED, or CONFLICT.
"""
from __future__ import annotations

import copy
import dataclasses
import hashlib
import inspect
import re
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Protocol

from control_plane.coo_principal_envelope import PrincipalAdmissionContext
from control_plane.executive_runtime import Runtime
from integrations.mastermind_company_mcp.adapter import DialogueBinding
from integrations.mastermind_company_mcp.principal_adapter import (
    PRINCIPAL_COMMIT_FENCE_RECEIPT_SCHEMA,
    PRINCIPAL_COMMIT_INTENT_SCHEMA,
    PrincipalCommitFenceReceipt,
    PrincipalCommitIntent,
)
from integrations.mastermind_company_mcp.principal_schemas import (
    canonical_principal_json,
)
from integrations.slack_agent_dialogue.contract import DialogueContractError
from integrations.slack_agent_dialogue.contract_v2 import validate_message_v2
from integrations.slack_agent_dialogue.engine_v2 import DialogueContextV2
from integrations.slack_agent_dialogue.service import (
    CONTROL_VERSION_V2,
    DialogueServiceError,
    call_service,
)

PRINCIPAL_RUNTIME_COMMIT_EVENT_SCHEMA = (
    "mastermind.company_dialogue_principal_runtime_commit.v1"
)
PRINCIPAL_RUNTIME_OBSERVATION_SCHEMA = (
    "mastermind.company_dialogue_principal_commit_observation.v1"
)
PRINCIPAL_RUNTIME_AGGREGATE_TYPE = "company_dialogue_principal_commit"
PRINCIPAL_RUNTIME_EVENT_TYPE = "COMPANY_DIALOGUE_PRINCIPAL_COMMIT_STARTED"
PRINCIPAL_RUNTIME_ACTOR = "coo-principal-dialogue"
PRINCIPAL_RUNTIME_COMMAND_PREFIX = "company-dialogue-principal-commit:"

_MESSAGE_KEY_RE = re.compile(r"\Aasd-principal-[0-9a-f]{32}\Z")
_SHA64_RE = re.compile(r"\A[0-9a-f]{64}\Z")
_PRINCIPAL_MESSAGE_TYPES = ("RULING", "CONTINUE", "STOP")
_ACTIVE_ATTEMPT_STATUSES = frozenset({"CLAIMED", "RUNNING", "CHECKPOINTED"})
_ACTIVE_JOB_STATUSES = frozenset({"RUNNING", "CHECKPOINTED"})


class PrincipalRuntimeFenceError(RuntimeError):
    """The exact principal edge cannot be newly admitted."""


class PrincipalCommitObservationState(str, Enum):
    NOT_APPLIED = "NOT_APPLIED"
    APPLIED = "APPLIED"
    EFFECT_UNKNOWN = "EFFECT_UNKNOWN"
    CONFLICT = "CONFLICT"


class PrincipalRuntimeBindingResolver(Protocol):
    """Fresh trusted H6 binding source; it selects no model-visible target."""

    def resolve(self) -> DialogueBinding: ...


ServiceCall = Callable[..., Awaitable[dict[str, Any]]]


@dataclass(frozen=True)
class PrincipalCommitObservation:
    schema: str
    state: PrincipalCommitObservationState
    message_key: str
    message_fingerprint: str | None
    durable_ref: str | None
    event_id: int | None
    canonical_digest: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "state": self.state.value,
            "message_key": self.message_key,
            "message_fingerprint": self.message_fingerprint,
            "durable_ref": self.durable_ref,
            "event_id": self.event_id,
            "canonical_digest": self.canonical_digest,
        }


@dataclass(frozen=True)
class PrincipalCommittedMessageRead:
    """Exact original message, available only for a qualified committed read.

    This is a carrier observation, not a product acceptance verdict. The
    consumer must still join the issued request and the current result.
    """

    observation: PrincipalCommitObservation
    message: dict[str, Any] | None


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_principal_json(value)).hexdigest()


def _validate_intent(intent: object) -> PrincipalCommitIntent:
    if type(intent) is not PrincipalCommitIntent:
        raise PrincipalRuntimeFenceError("principal commit intent has wrong exact type")
    if intent.schema != PRINCIPAL_COMMIT_INTENT_SCHEMA:
        raise PrincipalRuntimeFenceError("principal commit intent schema is unsupported")
    if _MESSAGE_KEY_RE.fullmatch(intent.message_key) is None:
        raise PrincipalRuntimeFenceError("principal commit message key is invalid")
    if (
        _SHA64_RE.fullmatch(intent.message_fingerprint) is None
        or _SHA64_RE.fullmatch(intent.principal_binding_digest) is None
        or _SHA64_RE.fullmatch(intent.authority_generation_digest) is None
        or _SHA64_RE.fullmatch(intent.capability_profile_digest) is None
    ):
        raise PrincipalRuntimeFenceError("principal commit digest is invalid")
    if intent.message_type not in _PRINCIPAL_MESSAGE_TYPES:
        raise PrincipalRuntimeFenceError("principal commit message type is invalid")
    for value in (
        intent.work_ref,
        intent.session_ref,
        intent.operation_key,
        intent.thread_ts,
        intent.reply_to_message_key,
        intent.child_job_id,
        intent.child_attempt_id,
        intent.child_worker_id,
    ):
        if not isinstance(value, str) or not value:
            raise PrincipalRuntimeFenceError("principal commit identity is invalid")
    return intent


def _binding_snapshot(binding: object) -> dict[str, Any]:
    if type(binding) is not DialogueBinding:
        raise PrincipalRuntimeFenceError("principal dialogue binding is unavailable")
    if binding.allowed_message_types != _PRINCIPAL_MESSAGE_TYPES:
        raise PrincipalRuntimeFenceError("principal dialogue generation is not exact")
    if (
        not isinstance(binding.reply_to_message_key, str)
        or not isinstance(binding.thread_ts, str)
    ):
        raise PrincipalRuntimeFenceError("principal dialogue carrier is unavailable")
    actor = dict(binding.actor_ref)
    applies = dict(binding.applies_to)
    if (
        actor.get("kind") != "executive_principal"
        or actor.get("seat") != "coo"
        or applies.get("kind") != "executive_attempt"
    ):
        raise PrincipalRuntimeFenceError("principal dialogue actor/target is unavailable")
    try:
        context = DialogueContextV2(
            work_ref=binding.work_ref,
            commission_ref=dict(binding.commission_ref),
            session_ref=binding.session_ref,
            operation_key=binding.operation_key,
            watch_mode=binding.watch_mode,
            actor_ref=actor,
            applies_to=applies,
        ).normalized()
    except (DialogueContractError, TypeError, ValueError):
        raise PrincipalRuntimeFenceError("principal dialogue context is unavailable") from None
    return {
        "context": context,
        "thread_ts": binding.thread_ts,
        "reply_to_message_key": binding.reply_to_message_key,
        "allowed_message_types": list(binding.allowed_message_types),
    }


def _require_binding_intent_match(
    snapshot: Mapping[str, Any],
    intent: PrincipalCommitIntent,
) -> None:
    context = snapshot["context"]
    actor = context["actor_ref"]
    applies = context["applies_to"]
    expected = {
        "work_ref": intent.work_ref,
        "session_ref": intent.session_ref,
        "operation_key": intent.operation_key,
        "thread_ts": intent.thread_ts,
        "reply_to_message_key": intent.reply_to_message_key,
        "principal_binding_digest": intent.principal_binding_digest,
        "authority_generation_digest": intent.authority_generation_digest,
        "capability_profile_digest": intent.capability_profile_digest,
        "child_job_id": intent.child_job_id,
        "child_attempt_id": intent.child_attempt_id,
        "child_worker_id": intent.child_worker_id,
    }
    actual = {
        "work_ref": context["work_ref"],
        "session_ref": context["session_ref"],
        "operation_key": context["operation_key"],
        "thread_ts": snapshot["thread_ts"],
        "reply_to_message_key": snapshot["reply_to_message_key"],
        "principal_binding_digest": actor.get("principal_binding_digest"),
        "authority_generation_digest": actor.get("authority_generation_digest"),
        "capability_profile_digest": actor.get("capability_profile_digest"),
        "child_job_id": applies.get("job_id"),
        "child_attempt_id": applies.get("attempt_id"),
        "child_worker_id": applies.get("worker_id"),
    }
    if actual != expected:
        raise PrincipalRuntimeFenceError("principal dialogue binding changed")


def _event_payload(
    intent: PrincipalCommitIntent,
    snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    binding = copy.deepcopy(dict(snapshot))
    return {
        "schema": PRINCIPAL_RUNTIME_COMMIT_EVENT_SCHEMA,
        "intent": intent.to_dict(),
        "intent_sha256": intent.digest(),
        "binding": binding,
        "binding_sha256": _digest(binding),
    }


def _command_id(message_key: str) -> str:
    return PRINCIPAL_RUNTIME_COMMAND_PREFIX + message_key


def _event_matches(event: Any, payload: Mapping[str, Any], intent: PrincipalCommitIntent) -> bool:
    return bool(
        event is not None
        and event.aggregate_type == PRINCIPAL_RUNTIME_AGGREGATE_TYPE
        and event.aggregate_id == intent.message_key
        and event.event_type == PRINCIPAL_RUNTIME_EVENT_TYPE
        and event.actor == PRINCIPAL_RUNTIME_ACTOR
        and event.command_id == _command_id(intent.message_key)
        and event.job_id == intent.child_job_id
        and event.attempt_id == intent.child_attempt_id
        and event.worker_id == intent.child_worker_id
        and event.payload == dict(payload)
    )


def _payload_intent(payload: object) -> PrincipalCommitIntent:
    if not isinstance(payload, Mapping):
        raise PrincipalRuntimeFenceError("principal commit event payload is invalid")
    if set(payload) != {
        "schema",
        "intent",
        "intent_sha256",
        "binding",
        "binding_sha256",
    }:
        raise PrincipalRuntimeFenceError("principal commit event payload shape changed")
    if payload["schema"] != PRINCIPAL_RUNTIME_COMMIT_EVENT_SCHEMA:
        raise PrincipalRuntimeFenceError("principal commit event schema changed")
    raw_intent = payload["intent"]
    if not isinstance(raw_intent, Mapping):
        raise PrincipalRuntimeFenceError("principal commit event intent is invalid")
    try:
        intent = PrincipalCommitIntent(**dict(raw_intent))
    except (TypeError, ValueError):
        raise PrincipalRuntimeFenceError("principal commit event intent is invalid") from None
    _validate_intent(intent)
    if payload["intent_sha256"] != intent.digest():
        raise PrincipalRuntimeFenceError("principal commit intent digest changed")
    binding = payload["binding"]
    if not isinstance(binding, Mapping) or payload["binding_sha256"] != _digest(binding):
        raise PrincipalRuntimeFenceError("principal commit binding digest changed")
    return intent


class PrincipalDialogueRuntimeCommitOwner:
    """One existing-Runtime-backed pre-COMMIT fence and reconciliation reader."""

    def __init__(
        self,
        runtime: Runtime,
        binding_resolver: PrincipalRuntimeBindingResolver,
        *,
        socket_path: Path,
        service_call: ServiceCall = call_service,
        principal_authority_guard: Callable[..., None] | None = None,
    ) -> None:
        if type(runtime) is not Runtime:
            raise TypeError("runtime must be the exact Executive Runtime owner")
        path = Path(socket_path)
        if not path.is_absolute():
            raise ValueError("socket_path must be absolute")
        if not callable(service_call):
            raise TypeError("service_call must be callable")
        if principal_authority_guard is not None and (
            not callable(principal_authority_guard)
            or inspect.iscoroutinefunction(principal_authority_guard)
        ):
            raise TypeError("principal authority guard must be synchronous and callable")
        self.runtime = runtime
        self.binding_resolver = binding_resolver
        self.socket_path = path
        self.service_call = service_call
        self.principal_authority_guard = principal_authority_guard

    def before_commit(self, intent: PrincipalCommitIntent, *,
                      expected_binding: DialogueBinding | None = None) -> PrincipalCommitFenceReceipt:
        """Persist the sole COMMIT-start fact after a fresh exact binding recheck."""

        intent = _validate_intent(intent)
        snapshot = _binding_snapshot(self.binding_resolver.resolve())
        if expected_binding is not None and snapshot != _binding_snapshot(expected_binding):
            raise PrincipalRuntimeFenceError("principal source binding changed")
        _require_binding_intent_match(snapshot, intent)
        actor = snapshot["context"]["actor_ref"]
        payload = _event_payload(intent, snapshot)
        command_id = _command_id(intent.message_key)

        with self.runtime.store.transaction() as connection:
            row = connection.execute(
                """
                SELECT
                  j.root_job_id,
                  j.status AS job_status,
                  j.current_attempt_id,
                  j.assigned_worker_id,
                  j.assigned_quota_class,
                  a.job_id AS attempt_job_id,
                  a.worker_id AS attempt_worker_id,
                  a.quota_class AS attempt_quota_class,
                  a.status AS attempt_status,
                  a.lease_expires_at_ms,
                  q.status AS quota_status,
                  q.held_attempt_id
                FROM jobs j
                JOIN attempts a ON a.attempt_id=j.current_attempt_id
                JOIN worker_quota_classes q
                  ON q.worker_id=a.worker_id AND q.quota_class=a.quota_class
                WHERE j.job_id=?
                """,
                (intent.child_job_id,),
            ).fetchone()
            now_ms = self.runtime.store.now_ms()
            if (
                row is None
                or row["root_job_id"] != actor.get("root_job_id")
                or row["job_status"] not in _ACTIVE_JOB_STATUSES
                or row["current_attempt_id"] != intent.child_attempt_id
                or row["assigned_worker_id"] != intent.child_worker_id
                or row["attempt_job_id"] != intent.child_job_id
                or row["attempt_worker_id"] != intent.child_worker_id
                or row["attempt_quota_class"] != row["assigned_quota_class"]
                or row["attempt_status"] not in _ACTIVE_ATTEMPT_STATUSES
                or int(row["lease_expires_at_ms"]) <= now_ms
                or row["quota_status"] != "BUSY"
                or row["held_attempt_id"] != intent.child_attempt_id
            ):
                raise PrincipalRuntimeFenceError(
                    "principal dialogue child is no longer exact/current"
                )

            existing = self.runtime.store.get_event_by_command_id(
                command_id, connection=connection
            )
            aggregate = self.runtime.store.list_events(
                aggregate_type=PRINCIPAL_RUNTIME_AGGREGATE_TYPE,
                aggregate_id=intent.message_key,
                connection=connection,
            )
            if existing is not None or aggregate:
                if (
                    existing is None
                    or len(aggregate) != 1
                    or aggregate[0].event_id != existing.event_id
                    or not _event_matches(existing, payload, intent)
                ):
                    raise PrincipalRuntimeFenceError(
                        "principal dialogue commit identity conflicts"
                    )
                raise PrincipalRuntimeFenceError(
                    "principal dialogue COMMIT may already have occurred"
                )

            # Different foreground surfaces can derive different outbound keys
            # for the same original request. Fence the semantic request inside
            # this existing BEGIN IMMEDIATE transaction as well as the key.
            # Caller/authority rotation and an uncertain prior send do not grant
            # another disposition. Reconciliation retains the first message key.
            prior_disposition = connection.execute(
                """
                SELECT event_id FROM events
                WHERE aggregate_type=? AND event_type=? AND job_id=?
                  AND json_extract(payload_json, '$.intent.reply_to_message_key')=?
                LIMIT 1
                """,
                (PRINCIPAL_RUNTIME_AGGREGATE_TYPE, PRINCIPAL_RUNTIME_EVENT_TYPE,
                 intent.child_job_id, intent.reply_to_message_key),
            ).fetchone()
            if prior_disposition is not None:
                raise PrincipalRuntimeFenceError(
                    "principal dialogue request already has a COMMIT"
                )

            if self.principal_authority_guard is not None:
                try:
                    # Receiving Control rechecks its enrolled mission while it
                    # holds the same write transaction that records COMMIT.
                    # The callback comes from host composition, never the tool.
                    guarded = self.principal_authority_guard(
                        context=PrincipalAdmissionContext(
                            intent.work_ref, actor["principal_binding_digest"],
                            actor["mission_authority_ref"], actor["authority_generation_digest"],
                        ),
                        root_job_id=actor["root_job_id"],
                        capability_profile_digest=actor["capability_profile_digest"],
                    )
                    if guarded is not None:
                        if inspect.iscoroutine(guarded):
                            guarded.close()
                        raise ValueError("principal guard must return synchronously")
                except Exception:
                    raise PrincipalRuntimeFenceError(
                        "principal dialogue authority is no longer current"
                    ) from None

            self.runtime.store.append_event(
                connection,
                aggregate_type=PRINCIPAL_RUNTIME_AGGREGATE_TYPE,
                aggregate_id=intent.message_key,
                event_type=PRINCIPAL_RUNTIME_EVENT_TYPE,
                actor=PRINCIPAL_RUNTIME_ACTOR,
                job_id=intent.child_job_id,
                attempt_id=intent.child_attempt_id,
                worker_id=intent.child_worker_id,
                quota_class=str(row["assigned_quota_class"]),
                payload=payload,
                command_id=command_id,
            )
            event = self.runtime.store.get_event_by_command_id(
                command_id, connection=connection
            )
            if not _event_matches(event, payload, intent):
                raise PrincipalRuntimeFenceError(
                    "principal dialogue durable fence could not be read back"
                )
            assert event is not None
            durable_ref = f"runtime-event:{event.event_id}"

        return PrincipalCommitFenceReceipt(
            schema=PRINCIPAL_COMMIT_FENCE_RECEIPT_SCHEMA,
            intent_sha256=intent.digest(),
            durable_ref=durable_ref,
        )

    def _event_for_message_key(self, message_key: str):
        if not isinstance(message_key, str) or _MESSAGE_KEY_RE.fullmatch(message_key) is None:
            raise PrincipalRuntimeFenceError("principal message key is invalid")
        event = self.runtime.events.get_event_by_command_id(_command_id(message_key))
        if event is None:
            return None
        intent = _payload_intent(event.payload)
        if intent.message_key != message_key or not _event_matches(
            event, event.payload, intent
        ):
            raise PrincipalRuntimeFenceError("principal commit event changed")
        return event, intent

    @staticmethod
    def _observation(
        state: PrincipalCommitObservationState,
        *,
        message_key: str,
        intent: PrincipalCommitIntent | None,
        event: Any | None,
    ) -> PrincipalCommitObservation:
        without_digest = {
            "schema": PRINCIPAL_RUNTIME_OBSERVATION_SCHEMA,
            "state": state.value,
            "message_key": message_key,
            "message_fingerprint": (
                None if intent is None else intent.message_fingerprint
            ),
            "durable_ref": (
                None if event is None else f"runtime-event:{event.event_id}"
            ),
            "event_id": None if event is None else int(event.event_id),
        }
        return PrincipalCommitObservation(
            schema=PRINCIPAL_RUNTIME_OBSERVATION_SCHEMA,
            state=state,
            message_key=message_key,
            message_fingerprint=without_digest["message_fingerprint"],
            durable_ref=without_digest["durable_ref"],
            event_id=without_digest["event_id"],
            canonical_digest=_digest(without_digest),
        )

    async def reconcile(self, message_key: str) -> PrincipalCommitObservation:
        """Read the original carrier; never admit or repeat a COMMIT."""

        return (await self.read_committed_message(message_key)).observation

    async def reconcile_obligation(
        self, *, obligation_id: str, context: PrincipalAdmissionContext,
        root_job_id: str, receiving_read_guard: Callable[[], None],
    ) -> PrincipalCommitObservation | None:
        """Recover an original reply when its transport response was lost.

        The authenticated host supplies the original caller scope and a current
        synchronous read-permission guard. New-effect arming and an unanswered
        source are deliberately unnecessary. Exact principal/generation/mission
        scope is still required; this does not grant a successor access to a
        predecessor's records. No binding resolver, new-effect guard, write or
        fresh source acquisition runs. None means no matching COMMIT was observed
        at this instant, never permission to replay an uncertain request.
        """
        from control_plane.principal_dialogue_obligation import (
            read_original_principal_dialogue_obligation,
        )

        def guard():
            if not callable(receiving_read_guard):
                raise ValueError
            result = receiving_read_guard()
            if result is not None:
                if inspect.iscoroutine(result):
                    result.close()
                raise ValueError

        try:
            guard()
            if type(context) is not PrincipalAdmissionContext:
                raise ValueError
            anchor = read_original_principal_dialogue_obligation(self.runtime,
                obligation_id=obligation_id, expected_work_ref=context.work_ref,
                expected_root_job_id=root_job_id)
            physical = anchor.physical_source
            child = physical.candidate
            matches = []
            for event in self.runtime.events.list_events(job_id=child.job_id,
                    attempt_id=child.attempt_id,
                    aggregate_type=PRINCIPAL_RUNTIME_AGGREGATE_TYPE):
                stored = self._event_for_message_key(event.aggregate_id)
                if stored is None or stored[0] != event:
                    raise ValueError
                _, intent = stored
                if (intent.reply_to_message_key != physical.predecessor_message_key
                        or intent.thread_ts != physical.thread_ts):
                    continue
                snapshot = event.payload["binding"]
                _require_binding_intent_match(snapshot, intent)
                actor = snapshot["context"]["actor_ref"]
                if (intent.work_ref != context.work_ref
                        or intent.operation_key != physical.operation_key
                        or intent.child_worker_id != child.worker_id
                        or intent.principal_binding_digest != context.principal_binding_digest
                        or intent.authority_generation_digest != context.authority_generation_digest
                        or actor.get("mission_authority_ref") != context.mission_authority_ref
                        or actor.get("root_job_id") != root_job_id
                        or actor.get("kind") != "executive_principal"
                        or actor.get("seat") != "coo"
                        or intent.message_type != "RULING"):
                    raise ValueError
                matches.append(intent.message_key)
            if len(matches) > 1:
                raise ValueError
            guard()
            if not matches:
                return None
            observation = await self.reconcile(matches[0])
            guard()  # Do not disclose a read after its receiving permission moved.
            return observation
        except Exception:
            raise PrincipalRuntimeFenceError(
                "principal original reply unavailable"
            ) from None

    def _committed_read(
        self,
        state: PrincipalCommitObservationState,
        *,
        message_key: str,
        intent: PrincipalCommitIntent | None,
        event: Any | None,
        message: dict[str, Any] | None = None,
    ) -> PrincipalCommittedMessageRead:
        if (state is PrincipalCommitObservationState.APPLIED) is not (message is not None):
            raise PrincipalRuntimeFenceError("committed message read is inconsistent")
        return PrincipalCommittedMessageRead(
            observation=self._observation(state, message_key=message_key, intent=intent, event=event),
            message=copy.deepcopy(message),
        )

    async def read_committed_message(self, message_key: str) -> PrincipalCommittedMessageRead:
        """Acquire canonical body using the retained original COMMIT identity.

        No replay, resolver reselection, or state write occurs. Unknown delivery
        and a duplicate or changed message never produce a consumable body.
        """

        try:
            stored = self._event_for_message_key(message_key)
        except PrincipalRuntimeFenceError:
            return self._committed_read(
                PrincipalCommitObservationState.CONFLICT,
                message_key=str(message_key),
                intent=None,
                event=None,
            )
        if stored is None:
            return self._committed_read(
                PrincipalCommitObservationState.NOT_APPLIED,
                message_key=message_key,
                intent=None,
                event=None,
            )

        event, intent = stored
        payload = event.payload
        binding = payload.get("binding")
        try:
            if not isinstance(binding, Mapping):
                raise ValueError
            context = binding.get("context")
            if not isinstance(context, Mapping):
                raise ValueError
            normalized_context = DialogueContextV2(**dict(context)).normalized()
            if normalized_context != dict(context):
                raise ValueError
            if (
                binding.get("thread_ts") != intent.thread_ts
                or binding.get("reply_to_message_key") != intent.reply_to_message_key
            ):
                raise ValueError
            response = await self.service_call(
                self.socket_path,
                {
                    "version": CONTROL_VERSION_V2,
                    "operation": "read_thread",
                    "args": {
                        "context": normalized_context,
                        "thread_ts": intent.thread_ts,
                    },
                },
            )
            if not isinstance(response, dict) or response.get("ok") is not True:
                raise ValueError
            result = response.get("result")
            if (
                not isinstance(result, dict)
                or result.get("thread_ts") != intent.thread_ts
                or result.get("historical_messages") != []
                or type(result.get("mutated_count")) is not int
                or result["mutated_count"] != 0
                or not isinstance(result.get("messages"), list)
                or len(result["messages"]) > 256
            ):
                raise ValueError
            messages = [
                validate_message_v2(item["message"])
                for item in result["messages"]
                if isinstance(item, Mapping) and isinstance(item.get("message"), Mapping)
            ]
            matches = [m for m in messages if m["message_key"] == message_key]
            if not matches:
                return self._committed_read(
                    PrincipalCommitObservationState.EFFECT_UNKNOWN,
                    message_key=message_key,
                    intent=intent,
                    event=event,
                )
            if (
                len(matches) != 1
                or matches[0]["fingerprint"] != intent.message_fingerprint
                or matches[0]["message_type"] != intent.message_type
            ):
                return self._committed_read(
                    PrincipalCommitObservationState.CONFLICT,
                    message_key=message_key,
                    intent=intent,
                    event=event,
                )
            return self._committed_read(
                PrincipalCommitObservationState.APPLIED,
                message_key=message_key,
                intent=intent,
                event=event,
                message=matches[0],
            )
        except (DialogueContractError, DialogueServiceError, TypeError, ValueError):
            return self._committed_read(
                PrincipalCommitObservationState.EFFECT_UNKNOWN,
                message_key=message_key,
                intent=intent,
                event=event,
            )
        except Exception:
            return self._committed_read(
                PrincipalCommitObservationState.EFFECT_UNKNOWN,
                message_key=message_key,
                intent=intent,
                event=event,
            )


__all__ = [
    "PRINCIPAL_RUNTIME_ACTOR",
    "PRINCIPAL_RUNTIME_AGGREGATE_TYPE",
    "PRINCIPAL_RUNTIME_COMMAND_PREFIX",
    "PRINCIPAL_RUNTIME_COMMIT_EVENT_SCHEMA",
    "PRINCIPAL_RUNTIME_EVENT_TYPE",
    "PRINCIPAL_RUNTIME_OBSERVATION_SCHEMA",
    "PrincipalCommitObservation",
    "PrincipalCommitObservationState",
    "PrincipalDialogueRuntimeCommitOwner",
    "PrincipalRuntimeBindingResolver",
    "PrincipalRuntimeFenceError",
]
