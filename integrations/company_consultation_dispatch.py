"""Runtime-backed Company MCP consultation dispatcher.

This joins ``CompanyConsultationGateway`` to ``ConsultationRuntime``. The
dispatcher owns no peer registry and no Runtime lookup of its own — the host
supplies the verified ``CallerIdentity`` (current RuntimeBinding), the
``recipients`` resolver that maps each trusted ``peer.peer_ref`` to the
recipient's actor ref + ``recipient_binding``, the injected
``ConsultationPacketCarrier`` (the only carrier of question/answer bodies),
and the ``InvocationContextSource`` (the only source of the owner-issued
invocation identity for ``company.consult``).

Production packet carriage is declared ``UNAVAILABLE`` in this slice; the
owner of body production is the existing dialogue carrier lineage
(issues #611, #719, #738). No module-level state, dictionary, transcript
store or mailbox table may be added here.
"""
from __future__ import annotations

import copy
import dataclasses
import datetime as dt
import hashlib
import json
import re
from collections.abc import Awaitable, Callable, Mapping
from pathlib import Path
from typing import Any, Protocol

from common.agent_dialogue_contract import DialogueContractError
from common.agent_dialogue_consultation_contract import (
    CONSULTATION_PACKET_MAX_BYTES,
    CONSULTATION_SCHEMA,
    CONSULTATION_V2_SCHEMA,
    GROK_CONSULTATION_SCHEMA,
    RECEIPT_KEYS,
    build_consultation,
    canonical_consultation_json,
    render_consultation_packet,
    validate_consultation,
)
from control_plane.company_inbox_projection import (
    company_inbox_row,
    project_company_inbox,
)
from control_plane.consultation_runtime import (
    ConsultationConflict,
    ConsultationEventResult,
    ConsultationRuntime,
)
from control_plane.executive_runtime import Runtime, StateConflict
from control_plane.wake_events import utc_now_iso
from control_plane.wake_ledger import (
    LedgerPhase,
    reconstruct_status,
    requested_record,
)
from control_plane.wake_persist import WakeLedgerRepository
from integrations.mastermind_company_mcp.adapter import (
    DialogueBinding,
    DialogueBindingResolver,
)
from integrations.mastermind_company_mcp.consultation import (
    validate_company_consult_dispatch_request,
)
from integrations.slack_agent_dialogue.engine_v2 import DialogueContextV2
from integrations.slack_agent_dialogue.service import (
    CONTROL_VERSION_V2,
    EXACT_SEND_PROTOCOL,
    DialogueServiceError,
    call_service,
)
from integrations.slack_agent_dialogue.persisted_wake_carrier import (
    ConsultationWakeExtension,
    RequesterAnswerWakeExtension,
)


# IAC-1 self-contained constants. Not in ``common/*`` (forbidden).
_INBOX_SCHEMA = "mastermind.company_inbox.v1"
_CONSULTATION_REF_RE = re.compile(r"\Aconsult-[0-9a-f]{32}\Z")
_REPLY_SEMANTIC_KEYS = frozenset(
    {"consultation_ref", "answer", "supersedes_message_key", "evidence_refs"}
)
_READ_SEMANTIC_KEYS = frozenset({"consultation_ref"})
_ACKNOWLEDGED_WAKE_STATES = frozenset(
    {"TARGET_ACKNOWLEDGED", "SOURCE_RESOLVED"}
)

# Closed set of refusal codes. Every ``ConsultationRefusal`` raised by the
# dispatcher carries exactly one of these; the gateway surfaces the raise
# as ``{"ok": False, "error": {"code": "EFFECT_UNKNOWN"}}``.
REFUSAL_CODES = frozenset(
    {
        "INVALID_REQUEST",
        "NOT_A_PARTY",
        "STALE_BINDING",
        "CARRIER_UNAVAILABLE",
        "CARRIER_INTEGRITY",
        "CARRIER_RECONCILIATION_REQUIRED",
        "INVOCATION_CONTEXT_UNAVAILABLE",
        "CONFLICT",
        "WAKE_NOT_ACKNOWLEDGED",
        "UNAVAILABLE",
        "BODY_OVER_BUDGET",
        "EXPIRED",
    }
)

# Body-over-budget threshold for the dispatcher-emitted read result.
_BODY_BUDGET_BYTES = 60_000

# Production packet carriage is intentionally declared UNAVAILABLE here.
# The owner is the existing dialogue carrier lineage (issues #611, #719,
# #738). This dispatcher never reads bodies from a dictionary, transcript
# store or mailbox table — only from the injected ``ConsultationPacketCarrier``.
PRODUCTION_PACKET_CARRIAGE = "UNAVAILABLE"

# Fixed default response budget used when the ``InvocationContext`` does not
# override it. Closed shape; ``max_payload_bytes`` is the cap enforced on the
# canonical answer JSON at reply time.
_DEFAULT_RESPONSE_BUDGET = {
    "max_answers": 1,
    "max_evidence_reads": 4,
    "max_forward_hops": 0,
    "max_payload_bytes": 32768,
}


PacketCommitHook = Callable[[], Awaitable[None]]
ServiceCall = Callable[..., Awaitable[dict[str, Any]]]


class ConsultationPacketCarrierUnknown(RuntimeError):
    """The existing carrier could not prove packet presence or absence."""


class ConsultationPacketEffectUnknown(RuntimeError):
    """The exact carrier COMMIT crossed but could not be reconciled."""


class ConsultationPacketCommitAborted(RuntimeError):
    """The caller deliberately closed after READY without COMMIT."""


async def _noop_packet_commit() -> None:
    return None


class ConsultationPacketCarrier(Protocol):
    """Single injected port for QUESTION/ANSWER bodies."""

    async def put_question(
        self,
        consultation_id: str,
        frame: Mapping[str, Any],
        *,
        before_commit: PacketCommitHook,
    ) -> None: ...

    async def get_question(
        self, consultation_id: str
    ) -> Mapping[str, Any] | None: ...

    async def put_answer(
        self,
        consultation_id: str,
        frame: Mapping[str, Any],
        *,
        before_commit: PacketCommitHook,
    ) -> None: ...

    async def get_answer(
        self, consultation_id: str
    ) -> Mapping[str, Any] | None: ...


class InMemoryConsultationPacketCarrier:
    """TEST-ONLY hermetic packet carrier."""

    requires_dialogue_binding = False
    requires_packet_wire = False

    def __init__(self) -> None:
        self._questions: dict[str, dict[str, Any]] = {}
        self._answers: dict[str, dict[str, Any]] = {}

    async def put_question(
        self,
        consultation_id: str,
        frame: Mapping[str, Any],
        *,
        before_commit: PacketCommitHook,
    ) -> None:
        await before_commit()
        self._questions[consultation_id] = dict(frame)

    async def get_question(
        self, consultation_id: str
    ) -> Mapping[str, Any] | None:
        frame = self._questions.get(consultation_id)
        return dict(frame) if frame is not None else None

    async def put_answer(
        self,
        consultation_id: str,
        frame: Mapping[str, Any],
        *,
        before_commit: PacketCommitHook,
    ) -> None:
        await before_commit()
        self._answers[consultation_id] = dict(frame)

    async def get_answer(
        self, consultation_id: str
    ) -> Mapping[str, Any] | None:
        frame = self._answers.get(consultation_id)
        return dict(frame) if frame is not None else None


def _dialogue_carrier_identity(binding: DialogueBinding) -> tuple[object, ...]:
    """Return the incumbent Relay parent identity, not one child Attempt.

    Every worker context remains bound to its own exact ``actor_ref`` and
    ``applies_to`` Attempt.  The shared physical parent is separately keyed by
    work/commission/session/operation/watch/thread; requiring the child Job to
    match would make two simultaneously current Runtime Attempts impossible.
    """

    if not isinstance(binding, DialogueBinding):
        raise StateConflict("trusted dialogue binding is unavailable")
    actor = dict(binding.actor_ref)
    applies_to = dict(binding.applies_to)
    if (
        actor.get("kind") != "worker_attempt"
        or applies_to.get("kind") != "executive_attempt"
        or any(
            not isinstance(actor.get(field), str)
            or not actor.get(field)
            or actor.get(field) != applies_to.get(field)
            for field in ("job_id", "attempt_id", "worker_id")
        )
    ):
        raise StateConflict("dialogue binding applicability carrier is invalid")
    return (
        binding.work_ref,
        canonical_consultation_json(dict(binding.commission_ref)),
        binding.session_ref,
        binding.operation_key,
        binding.watch_mode,
        binding.thread_ts,
    )


def _require_same_dialogue_carrier(
    caller_binding: DialogueBinding | None,
    recipient_binding: DialogueBinding | None,
    *,
    caller_actor_ref: Mapping[str, Any],
    recipient_actor_ref: Mapping[str, Any],
) -> None:
    if not isinstance(caller_binding, DialogueBinding) or not isinstance(
        recipient_binding, DialogueBinding
    ):
        raise StateConflict("same exact parent dialogue binding is unavailable")
    if dict(caller_binding.actor_ref) != dict(caller_actor_ref):
        raise StateConflict("caller dialogue binding actor is not trusted")
    if dict(recipient_binding.actor_ref) != dict(recipient_actor_ref):
        raise StateConflict("recipient dialogue binding actor is not trusted")
    if _dialogue_carrier_identity(caller_binding) != _dialogue_carrier_identity(
        recipient_binding
    ):
        raise StateConflict("parties do not share the same exact parent carrier")


def _require_trusted_caller_binding(
    caller_binding: DialogueBinding | None,
    *,
    caller_actor_ref: Mapping[str, Any],
) -> None:
    """Prove the caller's own binding without requiring a shared parent.

    Cross-parent carriage still needs the sender's authority to come from the
    caller's own trusted binding. What it must NOT require is that the two
    parties share one physical Relay parent, which is exactly the lawful
    cross-session case ``_require_same_dialogue_carrier`` refuses.
    """

    if not isinstance(caller_binding, DialogueBinding):
        raise StateConflict("caller dialogue binding is unavailable")
    if dict(caller_binding.actor_ref) != dict(caller_actor_ref):
        raise StateConflict("caller dialogue binding actor is not trusted")
    # Reuse the incumbent applicability law for the caller's own parent.
    _dialogue_carrier_identity(caller_binding)


class AgentDialogueConsultationPacketCarrier:
    """Adapter over the incumbent authenticated Agent Relay AF_UNIX service."""

    requires_dialogue_binding = True
    requires_packet_wire = True

    def __init__(
        self,
        *,
        binding_resolver: DialogueBindingResolver,
        socket_path: Path,
        service_call: ServiceCall = call_service,
        timeout_seconds: float = 30.0,
    ) -> None:
        if not isinstance(socket_path, Path) or not socket_path.is_absolute():
            raise TypeError("socket_path must be an absolute Path")
        if not callable(getattr(binding_resolver, "resolve", None)):
            raise TypeError("binding_resolver must resolve the current binding")
        if not callable(service_call):
            raise TypeError("service_call must be callable")
        if not isinstance(timeout_seconds, (int, float)) or timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._binding_resolver = binding_resolver
        self._socket_path = socket_path
        self._service_call = service_call
        self._timeout_seconds = float(timeout_seconds)

    def _binding(self) -> DialogueBinding:
        try:
            binding = self._binding_resolver.resolve()
        except Exception as exc:
            raise ConsultationPacketCarrierUnknown(
                "current Agent Relay binding is unavailable"
            ) from exc
        if not isinstance(binding, DialogueBinding):
            raise ConsultationPacketCarrierUnknown(
                "current Agent Relay binding is unavailable"
            )
        return binding

    @staticmethod
    def _context(binding: DialogueBinding) -> dict[str, Any]:
        return DialogueContextV2(
            work_ref=binding.work_ref,
            commission_ref=dict(binding.commission_ref),
            session_ref=binding.session_ref,
            operation_key=binding.operation_key,
            watch_mode=binding.watch_mode,
            actor_ref=dict(binding.actor_ref),
            applies_to=dict(binding.applies_to),
        ).normalized()

    @staticmethod
    def _sender_actor(frame: Mapping[str, Any]) -> Mapping[str, Any]:
        if frame["purpose"] == "QUESTION":
            return frame["requester_actor_ref"]
        if frame["purpose"] == "ANSWER":
            return frame["recipient_actor_ref"]
        raise StateConflict("consultation packet purpose is not sendable")

    @staticmethod
    def _assert_current_party(
        binding: DialogueBinding, frame: Mapping[str, Any]
    ) -> None:
        actor = dict(binding.actor_ref)
        parties = (
            dict(frame["requester_actor_ref"]),
            dict(frame["recipient_actor_ref"]),
        )
        if actor not in parties:
            raise StateConflict("current dialogue binding is not a packet party")

    async def _call(
        self,
        request: Mapping[str, Any],
        *,
        before_write: PacketCommitHook | None = None,
    ) -> dict[str, Any]:
        try:
            return await self._service_call(
                self._socket_path,
                request,
                timeout_seconds=self._timeout_seconds,
                before_write=before_write,
            )
        except ConsultationPacketCommitAborted:
            raise
        except DialogueServiceError as exc:
            if exc.code == "SEND_EFFECT_UNKNOWN":
                raise ConsultationPacketEffectUnknown(
                    "consultation packet effect remains unknown"
                ) from exc
            raise ConsultationPacketCarrierUnknown(
                "Agent Relay packet carrier is unavailable"
            ) from exc

    async def _put(
        self,
        consultation_id: str,
        frame: Mapping[str, Any],
        *,
        purpose: str,
        before_commit: PacketCommitHook,
    ) -> None:
        item = validate_consultation(frame)
        if (
            consultation_id != item["consultation_id"]
            or item["purpose"] != purpose
        ):
            raise StateConflict("consultation packet identity disagrees")
        binding = self._binding()
        if dict(binding.actor_ref) != dict(self._sender_actor(item)):
            raise StateConflict("current dialogue binding is not the packet sender")
        response = await self._call(
            {
                "version": CONTROL_VERSION_V2,
                "operation": "send_consultation_packet",
                "args": {
                    "context": self._context(binding),
                    "thread_ts": binding.thread_ts,
                    "message": item,
                    "send_protocol": EXACT_SEND_PROTOCOL,
                },
            },
            before_write=before_commit,
        )
        result = response.get("result") if isinstance(response, Mapping) else None
        if (
            not isinstance(response, Mapping)
            or response.get("ok") is not True
            or not isinstance(result, Mapping)
            or result.get("message_key") != item["message_key"]
            or result.get("fingerprint") != item["fingerprint"]
            or result.get("thread_ts") != binding.thread_ts
        ):
            raise ConsultationPacketCarrierUnknown(
                "Agent Relay packet receipt is invalid"
            )

    async def put_question(
        self,
        consultation_id: str,
        frame: Mapping[str, Any],
        *,
        before_commit: PacketCommitHook,
    ) -> None:
        await self._put(
            consultation_id,
            frame,
            purpose="QUESTION",
            before_commit=before_commit,
        )

    async def put_answer(
        self,
        consultation_id: str,
        frame: Mapping[str, Any],
        *,
        before_commit: PacketCommitHook,
    ) -> None:
        await self._put(
            consultation_id,
            frame,
            purpose="ANSWER",
            before_commit=before_commit,
        )

    async def _get(
        self, consultation_id: str, *, purpose: str
    ) -> Mapping[str, Any] | None:
        if _CONSULTATION_REF_RE.fullmatch(consultation_id) is None:
            raise StateConflict("consultation packet identity is invalid")
        binding = self._binding()
        response = await self._call(
            {
                "version": CONTROL_VERSION_V2,
                "operation": "read_consultation_packet",
                "args": {
                    "context": self._context(binding),
                    "thread_ts": binding.thread_ts,
                    "consultation_id": consultation_id,
                    "purpose": purpose,
                },
            }
        )
        if not isinstance(response, Mapping) or response.get("ok") is not True:
            raise ConsultationPacketCarrierUnknown(
                "Agent Relay packet read is invalid"
            )
        result = response.get("result")
        if result is None:
            return None
        if not isinstance(result, Mapping) or set(result) != {
            "packet",
            "primary_ts",
            "duplicate_timestamps",
        }:
            raise ConsultationPacketCarrierUnknown(
                "Agent Relay packet read is invalid"
            )
        packet = result.get("packet")
        try:
            item = validate_consultation(packet)
        except Exception as exc:
            raise ConsultationPacketCarrierUnknown(
                "Agent Relay packet read is invalid"
            ) from exc
        if (
            item["consultation_id"] != consultation_id
            or item["purpose"] != purpose
            or result.get("duplicate_timestamps") != []
        ):
            raise ConsultationPacketCarrierUnknown(
                "Agent Relay packet read is conflicting"
            )
        self._assert_current_party(binding, item)
        return item

    async def get_question(
        self, consultation_id: str
    ) -> Mapping[str, Any] | None:
        return await self._get(consultation_id, purpose="QUESTION")

    async def get_answer(
        self, consultation_id: str
    ) -> Mapping[str, Any] | None:
        return await self._get(consultation_id, purpose="ANSWER")


@dataclasses.dataclass(frozen=True)
class ConsultationDeliveryTarget:
    """Internal packet-routing projection of ONE destination Attempt.

    This is not a Company Dialogue grant, not a model input, not a lifecycle
    binding and not a persisted route. It names the exact physical Agent Relay
    parent a packet must be delivered into, reconstructed by the trusted host
    from existing Executive/Wake evidence.

    ``applies_to`` is carried rather than derived. The carrier context needs
    it, and ``_dialogue_carrier_identity`` independently requires it to agree
    with ``actor_ref``; synthesizing it by swapping ``kind`` would fabricate
    trusted identity instead of reconstructing it.
    """

    actor_ref: Mapping[str, Any]
    applies_to: Mapping[str, Any]
    work_ref: str
    commission_ref: Mapping[str, Any]
    session_ref: str
    operation_key: str
    watch_mode: str | None
    thread_ts: str
    evidence_digest: str

    def __post_init__(self) -> None:
        actor = dict(self.actor_ref)
        applies_to = dict(self.applies_to)
        if (
            actor.get("kind") != "worker_attempt"
            or applies_to.get("kind") != "executive_attempt"
            or any(
                not isinstance(actor.get(field), str)
                or not actor.get(field)
                or actor.get(field) != applies_to.get(field)
                for field in ("job_id", "attempt_id", "worker_id")
            )
        ):
            raise StateConflict("consultation delivery target identity is invalid")
        if not isinstance(self.commission_ref, Mapping):
            raise StateConflict("consultation delivery target identity is invalid")
        if self.watch_mode is not None and not isinstance(self.watch_mode, str):
            raise StateConflict("consultation delivery target identity is invalid")
        for field in (
            "work_ref",
            "session_ref",
            "operation_key",
            "thread_ts",
            "evidence_digest",
        ):
            value = getattr(self, field)
            if not isinstance(value, str) or not value:
                raise StateConflict(
                    "consultation delivery target identity is invalid"
                )


class ConsultationPacketTargetResolver(Protocol):
    """Host-owned packet destination resolver; no model input reaches it.

    ``resolve_target`` maps one destination Attempt to its exact physical
    dialogue source. ``resolve_read_target`` reconstructs the destination of
    an already-admitted consultation from the persisted Consultation Runtime
    party facts, which is what keeps an admitted target sticky across restart
    and peer rotation. Both refuse rather than choose when the physical source
    is missing or ambiguous.
    """

    def resolve_target(
        self, actor_ref: Mapping[str, Any]
    ) -> ConsultationDeliveryTarget: ...

    def resolve_read_target(
        self, consultation_id: str, purpose: str
    ) -> ConsultationDeliveryTarget: ...


class TargetedAgentDialogueConsultationPacketCarrier:
    """Cross-parent adapter over the incumbent authenticated Agent Relay service.

    Sender authority and physical destination are two separate authorities
    here. The caller's own trusted binding still proves the semantic sender;
    the injected target resolver alone supplies the destination parent.

    Nothing below this class re-checks the destination. The Relay engine's
    send/read paths and the service request path are context-parametric with
    no actor-to-context coupling, and the service authenticates an OS peer uid
    rather than a binding, so this resolution is the ONLY authority for
    physical destination. A caller-supplied destination must remain
    impossible by construction: no method here accepts a thread, context,
    session or binding argument.
    """

    requires_dialogue_binding = True
    requires_packet_wire = True
    supports_cross_parent_target = True

    def __init__(
        self,
        *,
        binding_resolver: DialogueBindingResolver,
        target_resolver: ConsultationPacketTargetResolver,
        socket_path: Path,
        service_call: ServiceCall = call_service,
        timeout_seconds: float = 30.0,
    ) -> None:
        if not isinstance(socket_path, Path) or not socket_path.is_absolute():
            raise TypeError("socket_path must be an absolute Path")
        if not callable(getattr(binding_resolver, "resolve", None)):
            raise TypeError("binding_resolver must resolve the current binding")
        if not callable(getattr(target_resolver, "resolve_target", None)) or not callable(
            getattr(target_resolver, "resolve_read_target", None)
        ):
            raise TypeError(
                "target_resolver must resolve send and read packet targets"
            )
        if not callable(service_call):
            raise TypeError("service_call must be callable")
        if not isinstance(timeout_seconds, (int, float)) or timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._binding_resolver = binding_resolver
        self._target_resolver = target_resolver
        self._socket_path = socket_path
        self._service_call = service_call
        self._timeout_seconds = float(timeout_seconds)

    def _binding(self) -> DialogueBinding:
        try:
            binding = self._binding_resolver.resolve()
        except Exception as exc:
            raise ConsultationPacketCarrierUnknown(
                "current Agent Relay binding is unavailable"
            ) from exc
        if not isinstance(binding, DialogueBinding):
            raise ConsultationPacketCarrierUnknown(
                "current Agent Relay binding is unavailable"
            )
        return binding

    @staticmethod
    def _target_context(target: ConsultationDeliveryTarget) -> dict[str, Any]:
        return DialogueContextV2(
            work_ref=target.work_ref,
            commission_ref=dict(target.commission_ref),
            session_ref=target.session_ref,
            operation_key=target.operation_key,
            watch_mode=target.watch_mode,
            actor_ref=dict(target.actor_ref),
            applies_to=dict(target.applies_to),
        ).normalized()

    @staticmethod
    def _sender_actor(frame: Mapping[str, Any]) -> Mapping[str, Any]:
        if frame["purpose"] == "QUESTION":
            return frame["requester_actor_ref"]
        if frame["purpose"] == "ANSWER":
            return frame["recipient_actor_ref"]
        raise StateConflict("consultation packet purpose is not sendable")

    @staticmethod
    def _destination_actor(frame: Mapping[str, Any]) -> Mapping[str, Any]:
        """The semantic destination is the party that is not the sender."""
        if frame["purpose"] == "QUESTION":
            return frame["recipient_actor_ref"]
        if frame["purpose"] == "ANSWER":
            return frame["requester_actor_ref"]
        raise StateConflict("consultation packet purpose is not sendable")

    @staticmethod
    def _assert_current_party(
        binding: DialogueBinding, frame: Mapping[str, Any]
    ) -> None:
        actor = dict(binding.actor_ref)
        parties = (
            dict(frame["requester_actor_ref"]),
            dict(frame["recipient_actor_ref"]),
        )
        if actor not in parties:
            raise StateConflict("current dialogue binding is not a packet party")

    def _checked_target(
        self,
        target: Any,
        *,
        expected_actor_ref: Mapping[str, Any] | None,
    ) -> ConsultationDeliveryTarget:
        """Refuse before any effect unless the target is the exact destination."""
        if not isinstance(target, ConsultationDeliveryTarget):
            raise StateConflict("consultation packet target is unavailable")
        if expected_actor_ref is not None:
            try:
                expected = _normalized_actor_ref(expected_actor_ref)
            except KeyError as exc:
                raise StateConflict(
                    "consultation packet destination actor is invalid"
                ) from exc
            if _normalized_actor_ref(target.actor_ref) != expected:
                raise StateConflict(
                    "consultation packet target is not the semantic destination"
                )
        return target

    def _send_target(self, frame: Mapping[str, Any]) -> ConsultationDeliveryTarget:
        destination = self._destination_actor(frame)
        try:
            resolved = self._target_resolver.resolve_target(
                _normalized_actor_ref(destination)
            )
        except StateConflict:
            raise
        except KeyError as exc:
            raise StateConflict(
                "consultation packet destination actor is invalid"
            ) from exc
        except Exception as exc:
            raise ConsultationPacketCarrierUnknown(
                "consultation packet target is unavailable"
            ) from exc
        return self._checked_target(resolved, expected_actor_ref=destination)

    def _read_target(
        self, consultation_id: str, purpose: str
    ) -> ConsultationDeliveryTarget:
        try:
            resolved = self._target_resolver.resolve_read_target(
                consultation_id, purpose
            )
        except StateConflict:
            raise
        except Exception as exc:
            raise ConsultationPacketCarrierUnknown(
                "consultation packet target is unavailable"
            ) from exc
        return self._checked_target(resolved, expected_actor_ref=None)

    async def _call(
        self,
        request: Mapping[str, Any],
        *,
        before_write: PacketCommitHook | None = None,
    ) -> dict[str, Any]:
        try:
            return await self._service_call(
                self._socket_path,
                request,
                timeout_seconds=self._timeout_seconds,
                before_write=before_write,
            )
        except ConsultationPacketCommitAborted:
            raise
        except DialogueServiceError as exc:
            if exc.code == "SEND_EFFECT_UNKNOWN":
                raise ConsultationPacketEffectUnknown(
                    "consultation packet effect remains unknown"
                ) from exc
            raise ConsultationPacketCarrierUnknown(
                "Agent Relay packet carrier is unavailable"
            ) from exc

    async def _put(
        self,
        consultation_id: str,
        frame: Mapping[str, Any],
        *,
        purpose: str,
        before_commit: PacketCommitHook,
    ) -> None:
        item = validate_consultation(frame)
        if (
            consultation_id != item["consultation_id"]
            or item["purpose"] != purpose
        ):
            raise StateConflict("consultation packet identity disagrees")
        binding = self._binding()
        if dict(binding.actor_ref) != dict(self._sender_actor(item)):
            raise StateConflict("current dialogue binding is not the packet sender")
        # The destination is resolved and checked BEFORE any effect. A target
        # never grants the sender authority; the sender check above already
        # stands on the caller's own trusted binding.
        target = self._send_target(item)
        response = await self._call(
            {
                "version": CONTROL_VERSION_V2,
                "operation": "send_consultation_packet",
                "args": {
                    "context": self._target_context(target),
                    "thread_ts": target.thread_ts,
                    "message": item,
                    "send_protocol": EXACT_SEND_PROTOCOL,
                },
            },
            before_write=before_commit,
        )
        result = response.get("result") if isinstance(response, Mapping) else None
        if (
            not isinstance(response, Mapping)
            or response.get("ok") is not True
            or not isinstance(result, Mapping)
            or result.get("message_key") != item["message_key"]
            or result.get("fingerprint") != item["fingerprint"]
            or result.get("thread_ts") != target.thread_ts
        ):
            raise ConsultationPacketCarrierUnknown(
                "Agent Relay packet receipt is invalid"
            )

    async def put_question(
        self,
        consultation_id: str,
        frame: Mapping[str, Any],
        *,
        before_commit: PacketCommitHook,
    ) -> None:
        await self._put(
            consultation_id,
            frame,
            purpose="QUESTION",
            before_commit=before_commit,
        )

    async def put_answer(
        self,
        consultation_id: str,
        frame: Mapping[str, Any],
        *,
        before_commit: PacketCommitHook,
    ) -> None:
        await self._put(
            consultation_id,
            frame,
            purpose="ANSWER",
            before_commit=before_commit,
        )

    async def _get(
        self, consultation_id: str, *, purpose: str
    ) -> Mapping[str, Any] | None:
        if _CONSULTATION_REF_RE.fullmatch(consultation_id) is None:
            raise StateConflict("consultation packet identity is invalid")
        binding = self._binding()
        target = self._read_target(consultation_id, purpose)
        response = await self._call(
            {
                "version": CONTROL_VERSION_V2,
                "operation": "read_consultation_packet",
                "args": {
                    "context": self._target_context(target),
                    "thread_ts": target.thread_ts,
                    "consultation_id": consultation_id,
                    "purpose": purpose,
                },
            }
        )
        if not isinstance(response, Mapping) or response.get("ok") is not True:
            raise ConsultationPacketCarrierUnknown(
                "Agent Relay packet read is invalid"
            )
        result = response.get("result")
        if result is None:
            return None
        if not isinstance(result, Mapping) or set(result) != {
            "packet",
            "primary_ts",
            "duplicate_timestamps",
        }:
            raise ConsultationPacketCarrierUnknown(
                "Agent Relay packet read is invalid"
            )
        packet = result.get("packet")
        try:
            item = validate_consultation(packet)
        except Exception as exc:
            raise ConsultationPacketCarrierUnknown(
                "Agent Relay packet read is invalid"
            ) from exc
        if (
            item["consultation_id"] != consultation_id
            or item["purpose"] != purpose
            or result.get("duplicate_timestamps") != []
        ):
            raise ConsultationPacketCarrierUnknown(
                "Agent Relay packet read is conflicting"
            )
        # The reader's own binding must still be a packet party: a target
        # grants delivery, never readership.
        self._assert_current_party(binding, item)
        # The packet that came back must belong to the destination we read.
        self._checked_target(
            target, expected_actor_ref=self._destination_actor(item)
        )
        return item

    async def get_question(
        self, consultation_id: str
    ) -> Mapping[str, Any] | None:
        return await self._get(consultation_id, purpose="QUESTION")

    async def get_answer(
        self, consultation_id: str
    ) -> Mapping[str, Any] | None:
        return await self._get(consultation_id, purpose="ANSWER")


@dataclasses.dataclass(frozen=True)
class CallerIdentity:
    """The verified current RuntimeBinding the host injects.

    ``job_id`` is REQUIRED — the runtime cross-checks requester/recipient
    actor identity at all four edges (consult, reply, read, consume).
    """

    job_id: str
    worker_id: str
    attempt_id: str
    reasoning_surface: str
    binding: Mapping[str, Any]
    dialogue_binding: DialogueBinding | None = None


@dataclasses.dataclass(frozen=True)
class RecipientBinding:
    """One recipient resolved by the trusted host resolver."""

    actor_ref: Mapping[str, Any]
    recipient_binding: Mapping[str, Any]
    dialogue_binding: DialogueBinding | None = None


RecipientResolver = Callable[[str], RecipientBinding]
ClockFn = Callable[[], str]


@dataclasses.dataclass(frozen=True)
class InvocationContext:
    """The owner-issued invocation identity for one ``company.consult``.

    Every field is required; there are no defaults. ``invocation_id`` is
    the owner's correlation id for this exact consult request and is bound
    into the requester identity hash. ``parent_fingerprint`` is a 64-hex
    sha256 digest used as the upstream trace fingerprint.
    """

    invocation_id: str
    issued_at: str
    parent_fingerprint: str
    deadline_ms: int
    valid_for_seconds: int
    response_budget: Mapping[str, Any]

    def __post_init__(self) -> None:
        if not isinstance(self.invocation_id, str) or not self.invocation_id:
            raise ValueError("invocation_id is required")
        if (
            not isinstance(self.parent_fingerprint, str)
            or not re.fullmatch(r"[0-9a-f]{64}", self.parent_fingerprint)
        ):
            raise ValueError("parent_fingerprint must be 64 lowercase hex")
        if not isinstance(self.issued_at, str) or not self.issued_at:
            raise ValueError("issued_at is required")
        if not isinstance(self.deadline_ms, int) or self.deadline_ms <= 0:
            raise ValueError("deadline_ms must be a positive int")
        if (
            not isinstance(self.valid_for_seconds, int)
            or self.valid_for_seconds <= 0
        ):
            raise ValueError("valid_for_seconds must be a positive int")
        if not isinstance(self.response_budget, Mapping):
            raise ValueError("response_budget must be a mapping")


class InvocationContextSource(Protocol):
    """Single injected port for the owner-issued invocation identity.

    The owner process issues an ``InvocationContext`` per consult request.
    Returning ``None`` means no live invocation is in scope and the
    dispatcher refuses with zero effect.
    """

    def current(self) -> InvocationContext | None: ...


class ConsultationRefusal(Exception):
    """Typed zero-effect refusal raised by the dispatcher.

    The refusal carries exactly one closed-set ``code`` and never the raw
    exception text. ``detail_digest`` is the 16-hex prefix of the sha256
    of the diagnostic detail; the raw detail is not stored and not
    returned anywhere. ``__str__`` returns the code only.
    """

    def __init__(
        self,
        code: str,
        *,
        detail: str | None = None,
        effect: str = "NONE",
    ) -> None:
        if code not in REFUSAL_CODES:
            raise ValueError(f"unknown refusal code: {code}")
        if effect != "NONE":
            raise ValueError("refusal effect must be NONE")
        self.code = code
        self.effect = effect
        if detail is None:
            self.detail_digest = ""
        else:
            self.detail_digest = hashlib.sha256(
                detail.encode("utf-8")
            ).hexdigest()[:16]
        super().__init__(code)

    def __str__(self) -> str:
        return self.code


class NoSuchRecipient(Exception):
    """The trust host has no current RuntimeBinding for ``peer_ref``."""


def _sha64(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        canonical_consultation_json(value).encode("utf-8")
    ).hexdigest()


def _parse_utc_seconds(value: str) -> dt.datetime:
    return dt.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=dt.timezone.utc
    )


def _format_utc_seconds(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _is_expired(valid_until: str, observed_at: str) -> bool:
    """Mirror of the runtime's expiry rule: expired iff strictly after
    ``valid_until`` (a consult observed exactly at ``valid_until`` is
    still valid)."""
    return _parse_utc_seconds(observed_at) > _parse_utc_seconds(valid_until)


def _wake_request_readback(
    repository: WakeLedgerRepository, obligation_id: str
) -> bool | None:
    """Tri-state readback of the exact ``WAKE_REQUESTED`` on one ledger.

    ``True`` = exactly one request record exists; ``False`` = the
    ledger is readable and holds no request (proven absent); ``None``
    = the readback is unavailable or conflicting, so neither presence
    nor absence is proven.
    """
    try:
        records = repository.list_records(obligation_id)
    except Exception:
        return None
    requested = 0
    for item in records:
        if item.record.phase is LedgerPhase.WAKE_REQUESTED:
            requested += 1
    if requested == 1:
        return True
    if requested == 0:
        return False
    return None


def _wake_state_readback(
    repository: WakeLedgerRepository, obligation_id: str
) -> str | None:
    try:
        records = repository.list_records(obligation_id)
        state = reconstruct_status(
            obligation_id, tuple(item.record for item in records)
        )
    except Exception:
        return None
    return state.value


def _consultation_schema_for(surface: str) -> str:
    if surface == "grok-bot":
        return GROK_CONSULTATION_SCHEMA
    return CONSULTATION_SCHEMA


def _mint_request_identity(
    *,
    caller: CallerIdentity,
    peer_ref: str,
    invocation_id: str,
) -> str:
    """Deterministic program-scoped consultation identity input.

    The hash binds only the semantic identity inputs (caller job+attempt+
    worker+surface, the trusted peer ref, and the owner-issued
    invocation_id). It never enters the request question text, evidence,
    artifact revisions, ``issued_at`` or any other time.
    """
    payload = {
        "actor": {
            "job_id": caller.job_id,
            "worker_id": caller.worker_id,
            "attempt_id": caller.attempt_id,
            "reasoning_surface": caller.reasoning_surface,
        },
        "peer_ref": peer_ref,
        "invocation_id": invocation_id,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _build_deterministic_ids(identity_hash: str) -> tuple[str, str]:
    consultation_id = f"consult-{identity_hash[:32]}"
    message_key_digest = hashlib.sha256(
        f"message:{identity_hash}".encode("utf-8")
    ).hexdigest()
    message_key = f"asd-consultation-{message_key_digest[:16]}"
    return consultation_id, message_key


def _validate_reply_semantic(semantic: Mapping[str, Any]) -> str | None:
    """Return an ``INVALID_REQUEST`` detail or ``None`` if valid."""
    if set(semantic) != _REPLY_SEMANTIC_KEYS:
        return (
            "semantic must carry exactly "
            "{consultation_ref, answer, supersedes_message_key, evidence_refs}"
        )
    consultation_ref = semantic.get("consultation_ref")
    if not isinstance(consultation_ref, str):
        return "consultation_ref must be a string"
    if _CONSULTATION_REF_RE.fullmatch(consultation_ref) is None:
        return "consultation_ref must match ^consult-[0-9a-f]{32}$"
    answer = semantic.get("answer")
    supersedes = semantic.get("supersedes_message_key")
    evidence_refs = semantic.get("evidence_refs")
    if not isinstance(answer, str):
        return "answer must be a string"
    if supersedes is not None and not isinstance(supersedes, str):
        return "supersedes_message_key must be a string or null"
    if not isinstance(evidence_refs, list) or any(
        not isinstance(item, str) for item in evidence_refs
    ):
        return "evidence_refs must be a list of strings"
    return None


def _validate_read_semantic(semantic: Mapping[str, Any]) -> str | None:
    """Return an ``INVALID_REQUEST`` detail or ``None`` if valid."""
    if set(semantic) != _READ_SEMANTIC_KEYS:
        return "semantic must carry exactly {consultation_ref}"
    consultation_ref = semantic.get("consultation_ref")
    if not isinstance(consultation_ref, str):
        return "consultation_ref must be a string"
    if _CONSULTATION_REF_RE.fullmatch(consultation_ref) is None:
        return "consultation_ref must match ^consult-[0-9a-f]{32}$"
    return None


def _question_digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _intent_matches_frame(
    intent_payload: Mapping[str, Any], frame: Mapping[str, Any]
) -> bool:
    """Compare every persisted INTENT field against the carrier frame."""
    request = {
        "message_key": intent_payload["message_key"],
        "consultation_id": intent_payload["consultation_id"],
        "fingerprint": intent_payload["semantic_fingerprint"],
        "requester_actor_ref": intent_payload["requester_actor_ref"],
        "recipient_actor_ref": intent_payload["recipient_actor_ref"],
        "recipient_binding": intent_payload["recipient_binding"],
        "recipient_peer_ref": intent_payload["recipient_peer_ref"],
        "correlation": intent_payload["correlation"],
        "artifact_revisions": intent_payload["artifact_revisions"],
        "response_budget": intent_payload["response_budget"],
        "valid_until": intent_payload["valid_until"],
        "deadline_ms": intent_payload["deadline_ms"],
    }
    for key, value in request.items():
        if frame.get(key) != value:
            return False
    return True


def _validated_question_frame(
    intent_payload: Mapping[str, Any], frame: Mapping[str, Any] | None
) -> Mapping[str, Any] | None:
    """Return the frame if it fully matches the persisted INTENT, else ``None``.

    Every persisted identity and scope field must agree with the carrier
    frame, the frame must pass ``validate_consultation``, the persisted
    fingerprint and the persisted question digest must equal the
    corresponding frame fields, and the frame's ``consultation_id`` must
    equal the requested ``consultation_ref`` (already encoded in
    ``intent_payload['consultation_id']``).
    """
    if not isinstance(frame, Mapping):
        return None
    try:
        validate_consultation(dict(frame))
    except Exception:
        return None
    if not _intent_matches_frame(intent_payload, frame):
        return None
    if frame.get("fingerprint") != intent_payload.get("semantic_fingerprint"):
        return None
    if _question_digest(str(frame.get("question", ""))) != intent_payload.get(
        "question_digest"
    ):
        return None
    if frame.get("consultation_id") != intent_payload.get("consultation_id"):
        return None
    return frame


def _validated_answer_frame(
    intent_payload: Mapping[str, Any],
    answer_event: Any | None,
    frame: Mapping[str, Any] | None,
) -> Mapping[str, Any] | None:
    """Return the ANSWER frame iff every persisted field agrees.

    ``answer_event`` is the admitted non-historical ``ANSWER_AVAILABLE``
    event; ``frame`` is the carrier's ``get_answer`` result. The frame
    must pass ``validate_consultation``, be ``purpose == 'ANSWER'``,
    match the INTENT's ``consultation_id`` / ``message_key`` /
    ``correlation`` (with ``request_message_key`` set to the INTENT's
    message_key), agree with the INTENT on actors / binding / peer /
    artifact_revisions / valid_until / deadline_ms / response_budget,
    and agree with the admitted ``ANSWER_AVAILABLE`` payload on
    ``message_key``, ``fingerprint``, semantic answer digest and
    evidence revision digest.
    """
    if not isinstance(frame, Mapping):
        return None
    try:
        validate_consultation(dict(frame))
    except Exception:
        return None
    if frame.get("purpose") != "ANSWER":
        return None
    if frame.get("consultation_id") != intent_payload.get("consultation_id"):
        return None
    if frame.get("question_message_key") != intent_payload.get("message_key"):
        return None
    expected_correlation = dict(intent_payload.get("correlation") or {})
    expected_correlation["request_message_key"] = intent_payload.get(
        "message_key"
    )
    if dict(frame.get("correlation") or {}) != expected_correlation:
        return None
    if dict(frame.get("requester_actor_ref") or {}) != dict(
        intent_payload.get("requester_actor_ref") or {}
    ):
        return None
    if dict(frame.get("recipient_actor_ref") or {}) != dict(
        intent_payload.get("recipient_actor_ref") or {}
    ):
        return None
    if dict(frame.get("recipient_binding") or {}) != dict(
        intent_payload.get("recipient_binding") or {}
    ):
        return None
    if frame.get("recipient_peer_ref") != intent_payload.get(
        "recipient_peer_ref"
    ):
        return None
    if list(frame.get("artifact_revisions") or []) != list(
        intent_payload.get("artifact_revisions") or []
    ):
        return None
    if frame.get("valid_until") != intent_payload.get("valid_until"):
        return None
    if frame.get("deadline_ms") != intent_payload.get("deadline_ms"):
        return None
    if dict(frame.get("response_budget") or {}) != dict(
        intent_payload.get("response_budget") or {}
    ):
        return None
    if answer_event is None:
        return None
    admitted_payload = answer_event.payload
    if frame.get("message_key") != admitted_payload.get("message_key"):
        return None
    if frame.get("fingerprint") != admitted_payload.get("answer_fingerprint"):
        return None
    if _semantic_answer_digest(frame) != admitted_payload.get(
        "semantic_answer_digest"
    ):
        return None
    admitted_evidence_digest = admitted_payload.get("evidence_revision_digest")
    if admitted_evidence_digest:
        frame_artifact_digest = hashlib.sha256(
            canonical_consultation_json(
                frame.get("artifact_revisions", [])
            ).encode("utf-8")
        ).hexdigest()
        if frame_artifact_digest != admitted_evidence_digest:
            return None
    return frame


def _find_consultation_event(
    runtime: Runtime, consultation_id: str, event_type: str
) -> Any | None:
    for event in runtime.events.list_events(
        aggregate_type="consultation", aggregate_id=consultation_id
    ):
        if event.event_type == event_type:
            return event
    return None


def _non_historical_answer_event(
    runtime: Runtime, consultation_id: str
) -> Any | None:
    for event in runtime.events.list_events(
        aggregate_type="consultation", aggregate_id=consultation_id
    ):
        if event.event_type == "ANSWER_AVAILABLE" and not event.payload.get(
            "historical", False
        ):
            return event
    return None


def _caller_matches_actor(
    caller: CallerIdentity, actor_ref: Mapping[str, Any]
) -> bool:
    return (
        caller.job_id == str(actor_ref.get("job_id", ""))
        and caller.attempt_id == str(actor_ref.get("attempt_id", ""))
        and caller.worker_id == str(actor_ref.get("worker_id", ""))
    )


def _caller_matches_binding(
    caller: CallerIdentity, binding: Mapping[str, Any]
) -> bool:
    return (
        caller.binding.get("binding_id")
        == binding.get("binding_id")
        and caller.binding.get("binding_generation")
        == binding.get("binding_generation")
        and caller.binding.get("reasoning_surface")
        == binding.get("reasoning_surface")
    )


def _canonical_size(value: Mapping[str, Any]) -> int:
    return len(canonical_consultation_json(value).encode("utf-8"))


def _max_length_packet_evidence_refs(count: int) -> list[str]:
    """Return deterministic distinct valid evidence refs at the 500-char ceiling."""

    refs: list[str] = []
    for index in range(count):
        prefix = (
            "https://github.com/mastermindx-market-intelligence/Mastermind/blob/"
            f"{index + 1:040x}/"
        )
        suffix = f"-{index:02d}"
        filler = "a" * (500 - len(prefix) - len(suffix))
        refs.append(prefix + filler + suffix)
    return refs


_PACKET_BUDGET_TEXT_PATTERNS = ("x", '"', "\\", "界", "😀")


def _max_pattern_text_for_semantic_budget(
    pattern: str,
    *,
    semantic_budget: int,
    evidence_refs: list[str],
) -> str | None:
    """Largest repetition of one hostile text pattern within semantic bytes."""

    best: str | None = None
    low = 0
    high = semantic_budget
    while low <= high:
        repeats = (low + high) // 2
        candidate = pattern * repeats
        semantic_bytes = len(
            canonical_consultation_json(
                {"text": candidate, "evidence_refs": evidence_refs}
            ).encode("utf-8")
        )
        if semantic_bytes <= semantic_budget:
            best = candidate
            low = repeats + 1
        else:
            high = repeats - 1
    return best


def _packet_safe_answer_payload_limit(
    question_frame: Mapping[str, Any],
) -> int:
    """Largest semantic-answer byte budget safe for hostile valid text.

    The complete ANSWER packet is probed with maximum-length admitted evidence
    references and text classes that maximize each JSON/UTF-8 amplification
    boundary: plain ASCII, quote, backslash, BMP Unicode, and astral Unicode.
    """

    question = validate_consultation(copy.deepcopy(dict(question_frame)))
    evidence_count = int(question["response_budget"]["max_evidence_reads"])
    evidence_refs = _max_length_packet_evidence_refs(evidence_count)
    requested = int(question["response_budget"]["max_payload_bytes"])
    minimum = len(
        canonical_consultation_json(
            {"text": "", "evidence_refs": evidence_refs}
        ).encode("utf-8")
    )
    if requested < minimum:
        return 0
    best = 0
    low = minimum
    high = requested
    while low <= high:
        semantic_budget = (low + high) // 2
        safe = True
        for pattern in _PACKET_BUDGET_TEXT_PATTERNS:
            answer_text = _max_pattern_text_for_semantic_budget(
                pattern,
                semantic_budget=semantic_budget,
                evidence_refs=evidence_refs,
            )
            if answer_text is None:
                safe = False
                break
            try:
                answer = _build_answer_frame(
                    question,
                    answer_text=answer_text,
                    evidence_refs=evidence_refs,
                    supersedes=None,
                )
                render_consultation_packet(answer)
            except (DialogueContractError, ValueError, TypeError):
                safe = False
                break
        if safe:
            best = semantic_budget
            low = semantic_budget + 1
        else:
            high = semantic_budget - 1
    return best


def _packet_safe_question_frame(
    question_frame: Mapping[str, Any],
) -> dict[str, Any]:
    """Clamp only payload bytes; never silently narrow evidence semantics.

    The first measurement includes the caller's original numeric budget in
    every candidate ANSWER frame. Replacing it with an equal-or-smaller value
    cannot increase canonical packet bytes, so one conservative measurement is
    sufficient and no unstable refinement loop is needed.
    """

    question = validate_consultation(copy.deepcopy(dict(question_frame)))
    requested = dict(question["response_budget"])
    requested_payload = int(requested["max_payload_bytes"])
    safe_limit = _packet_safe_answer_payload_limit(question)
    next_limit = min(requested_payload, safe_limit)
    if next_limit <= 0:
        raise DialogueContractError("FRAME_TOO_LARGE")

    candidate = copy.deepcopy(question)
    candidate["response_budget"] = {
        **requested,
        "max_payload_bytes": next_limit,
    }
    candidate["fingerprint"] = ""
    candidate = build_consultation(candidate)
    render_consultation_packet(candidate)
    return candidate


class RuntimeConsultationDispatcher:
    """Async gateway dispatcher; delegates durable effects to ConsultationRuntime.

    The dispatcher never invents body content; question/answer bodies are
    only ever taken from the ``packets`` carrier or returned to the caller
    after the runtime admitted the corresponding event. The
    ``invocations`` source is the only allowed source of identity for
    ``company.consult``. Production packet carriage is declared
    ``UNAVAILABLE``; see ``PRODUCTION_PACKET_CARRIAGE``.
    """

    _ALLOWED_TOOLS = frozenset(
        {"company.consult", "company.reply", "company.consultation"}
    )

    def __init__(
        self,
        *,
        runtime: Runtime,
        repository_root: Path,
        caller: CallerIdentity,
        recipients: RecipientResolver,
        packets: ConsultationPacketCarrier,
        invocations: InvocationContextSource,
        _clock: ClockFn | None = None,
        _wake_repository: WakeLedgerRepository | None = None,
    ) -> None:
        if not isinstance(runtime, Runtime):
            raise TypeError("runtime must be the existing Executive Runtime")
        if _wake_repository is None:
            _wake_repository = WakeLedgerRepository(runtime)
        if not isinstance(_wake_repository, WakeLedgerRepository):
            raise TypeError("_wake_repository must be WakeLedgerRepository")
        self._wake_repository = _wake_repository
        self.runtime = runtime
        self.repository_root = Path(repository_root).resolve()
        self.caller = caller
        self.recipients = recipients
        self.packets = packets
        self.invocations = invocations
        self._clock = _clock or utc_now_iso
        self._consultations = ConsultationRuntime(
            runtime, repository_root=self.repository_root, _clock=self._clock
        )

    async def __call__(
        self, tool_name: str, request: Mapping[str, Any]
    ) -> dict[str, Any]:
        if tool_name not in self._ALLOWED_TOOLS:
            raise ConsultationRefusal(
                "INVALID_REQUEST",
                detail=f"unknown tool: {tool_name}",
            )
        if tool_name == "company.consult":
            return await self._dispatch_consult(request)
        if tool_name == "company.reply":
            return await self._dispatch_reply(request)
        return await self._dispatch_read(request)

    # -- explicit authenticated consumption seam (NOT reachable via __call__) --

    async def consume_answer(self, consultation_ref: str) -> dict[str, Any]:
        """Append one exact ``CONSUMED_BY_REQUESTER`` event for the requester.

        This is the only Python seam that appends ``CONSUMED_BY_REQUESTER``
        — the read tool ``company.consultation`` is zero-write and never
        calls it. ``self.caller`` must equal the persisted
        ``requester_actor_ref`` on job_id+attempt_id+worker_id (else
        ``NOT_A_PARTY``). The admitted non-historical ``ANSWER_AVAILABLE``
        event must exist (else ``CONFLICT``). The carrier must hold a
        frame that matches it (else ``CARRIER_UNAVAILABLE``).
        """
        intent = _find_consultation_event(
            self.runtime, consultation_ref, "INTENT"
        )
        if intent is None:
            raise ConsultationRefusal(
                "UNAVAILABLE", detail="no INTENT for consultation_ref"
            )
        requester_ref = intent.payload.get("requester_actor_ref") or {}
        if not _caller_matches_actor(self.caller, requester_ref):
            raise ConsultationRefusal(
                "NOT_A_PARTY",
                detail="caller is not the requester Runtime Attempt",
            )
        try:
            answer_frame = await self.packets.get_answer(consultation_ref)
        except (
            ConsultationPacketCarrierUnknown,
            ConsultationPacketEffectUnknown,
        ) as exc:
            raise ConsultationRefusal(
                "CARRIER_RECONCILIATION_REQUIRED",
                detail="ANSWER carrier history is unavailable",
            ) from exc
        if answer_frame is None:
            raise ConsultationRefusal(
                "CARRIER_UNAVAILABLE",
                detail="no admitted ANSWER frame on the carrier",
            )
        reserved = _non_historical_answer_event(
            self.runtime, consultation_ref
        )
        if reserved is None:
            raise ConsultationRefusal(
                "CONFLICT",
                detail="no admitted non-historical ANSWER_AVAILABLE",
            )
        if (
            str(reserved.payload.get("message_key", ""))
            != str(answer_frame.get("message_key", ""))
            or str(reserved.payload.get("answer_fingerprint", ""))
            != str(answer_frame.get("fingerprint", ""))
            or str(reserved.payload.get("semantic_answer_digest", ""))
            != _semantic_answer_digest(answer_frame)
        ):
            raise ConsultationRefusal(
                "CONFLICT",
                detail="carrier ANSWER frame does not match admitted event",
            )
        try:
            result = self._consultations.consumed_by_requester(
                answer_frame,
                requester_attempt_id=self.caller.attempt_id,
                observed_at=self._clock(),
            )
        except (StateConflict, ConsultationConflict) as exc:
            raise ConsultationRefusal(
                "CONFLICT", detail=type(exc).__name__
            ) from exc
        return {
            "consultation_ref": consultation_ref,
            "state": "CONSUMED",
            "inserted": bool(result.inserted),
        }

    # -- company.consult --

    async def _dispatch_consult(
        self, request: Mapping[str, Any]
    ) -> dict[str, Any]:
        try:
            validated = validate_company_consult_dispatch_request(dict(request))
        except Exception as exc:
            raise ConsultationRefusal(
                "INVALID_REQUEST",
                detail=f"dispatch envelope invalid: {type(exc).__name__}",
            ) from exc

        peer_ref = validated["peer"]["peer_ref"]
        semantic = dict(validated["semantic"])

        if semantic.get("to") != peer_ref:
            raise ConsultationRefusal(
                "INVALID_REQUEST",
                detail="semantic.to must equal peer.peer_ref",
            )

        try:
            recipient = self.recipients(peer_ref)
            recipient_actor_ref = _normalized_actor_ref(recipient.actor_ref)
            normalized_recipient_binding = dict(recipient.recipient_binding)
        except NoSuchRecipient as exc:
            raise ConsultationRefusal(
                "NOT_A_PARTY", detail=type(exc).__name__
            ) from exc
        except (KeyError, TypeError, ValueError) as exc:
            raise ConsultationRefusal(
                "INVALID_REQUEST",
                detail=f"recipient binding normalization failed: {type(exc).__name__}",
            ) from exc

        caller_actor_ref = {
            "kind": "worker_attempt",
            "job_id": self.caller.job_id,
            "attempt_id": self.caller.attempt_id,
            "worker_id": self.caller.worker_id,
        }
        if getattr(self.packets, "supports_cross_parent_target", False):
            # A cross-parent carrier separates sender authority from physical
            # destination: the caller's own binding proves the sender here, and
            # the carrier's injected target resolver proves the destination.
            # Requiring one shared parent would refuse the lawful case.
            try:
                _require_trusted_caller_binding(
                    self.caller.dialogue_binding,
                    caller_actor_ref=caller_actor_ref,
                )
            except StateConflict as exc:
                raise ConsultationRefusal(
                    "NOT_A_PARTY",
                    detail="caller Agent Relay binding is not trusted",
                ) from exc
        elif getattr(self.packets, "requires_dialogue_binding", False):
            try:
                _require_same_dialogue_carrier(
                    self.caller.dialogue_binding,
                    recipient.dialogue_binding,
                    caller_actor_ref=caller_actor_ref,
                    recipient_actor_ref=recipient_actor_ref,
                )
            except StateConflict as exc:
                raise ConsultationRefusal(
                    "NOT_A_PARTY",
                    detail="consultation parties do not share one Agent Relay parent",
                ) from exc

        if recipient_actor_ref["worker_id"] == self.caller.worker_id:
            raise ConsultationRefusal(
                "INVALID_REQUEST",
                detail="requester and recipient worker_ids must differ",
            )

        ctx = self.invocations.current()
        if ctx is None:
            raise ConsultationRefusal(
                "INVOCATION_CONTEXT_UNAVAILABLE",
                detail="invocations.current() returned None",
            )

        # IAC-1 r4d-N1: the dispatcher's trusted clock, read once for
        # the publication fence. The invocation's historic ``issued_at``
        # is never "now".
        now = self._clock()

        identity_hash = _mint_request_identity(
            caller=self.caller,
            peer_ref=peer_ref,
            invocation_id=ctx.invocation_id,
        )
        consultation_id, message_key = _build_deterministic_ids(identity_hash)

        # Deadline / valid_until derive from the owner-issued context.
        valid_until = _format_utc_seconds(
            _parse_utc_seconds(ctx.issued_at)
            + dt.timedelta(seconds=ctx.valid_for_seconds)
        )

        response_budget = dict(ctx.response_budget)

        requester_actor_ref = {
            "kind": "worker_attempt",
            "job_id": self.caller.job_id,
            "attempt_id": self.caller.attempt_id,
            "worker_id": self.caller.worker_id,
        }
        (
            requester_actor_digest,
            recipient_actor_digest,
        ) = _correlation_digests(requester_actor_ref, recipient_actor_ref)

        correlation = {
            "parent_fingerprint": ctx.parent_fingerprint,
            "request_message_key": message_key,
            "consultation_id": consultation_id,
            "requester_actor_digest": requester_actor_digest,
            "recipient_actor_digest": recipient_actor_digest,
        }

        try:
            question_frame = _build_question_frame(
                caller=self.caller,
                requester_actor_ref=requester_actor_ref,
                recipient_actor_ref=recipient_actor_ref,
                recipient_peer_ref=peer_ref,
                recipient_binding=normalized_recipient_binding,
                correlation=correlation,
                question_text=semantic["question"],
                evidence_refs=list(semantic.get("evidence_refs", [])),
                artifact_revisions=list(semantic.get("artifact_revisions", [])),
                message_key=message_key,
                consultation_id=consultation_id,
                valid_until=valid_until,
                deadline_ms=ctx.deadline_ms,
                response_budget=response_budget,
            )
            if getattr(self.packets, "requires_packet_wire", False):
                question_frame = _packet_safe_question_frame(question_frame)
                render_consultation_packet(question_frame)
        except (DialogueContractError, TypeError, ValueError) as exc:
            raise ConsultationRefusal(
                "BODY_OVER_BUDGET",
                detail="QUESTION packet exceeds the bounded Relay wire",
            ) from exc

        # If an INTENT for this consultation_id already exists, reconcile
        # the entire normalized semantic request against the persisted
        # INTENT. Rebuild a CANDIDATE frame under the persisted identity
        # and scope (message_key, consultation_id, requester/recipient
        # refs, recipient_binding, peer, correlation, artifact handling,
        # valid_until, deadline_ms, response_budget) but with the NEW
        # request's ``question``, ``evidence_refs``, and
        # ``artifact_revisions``. The candidate's contract fingerprint
        # must equal the persisted semantic fingerprint and its
        # recipient peer_ref must equal the persisted recipient peer
        # ref; when the carrier holds the original QUESTION packet, the
        # body parts (``question``, ``evidence_refs``,
        # ``artifact_revisions``) must also be exactly equal to the
        # carrier frame. Any mismatch → CONFLICT with zero ``intent()``
        # and zero ``put_question``. On full equality, replay
        # ``intent()`` (returns ``inserted=False``) and call
        # ``put_question`` only if the carrier doesn't already hold it.
        existing_intent = _find_consultation_event(
            self.runtime, consultation_id, "INTENT"
        )
        try:
            carrier_question_frame = await self.packets.get_question(consultation_id)
        except (
            ConsultationPacketCarrierUnknown,
            ConsultationPacketEffectUnknown,
        ) as exc:
            if existing_intent is not None:
                return {
                    "ok": True,
                    "result": _committed_consult_result(
                        consultation_id=consultation_id,
                        valid_until=str(existing_intent.payload.get("valid_until", valid_until)),
                        carrier_ref=f"company-mcp://{consultation_id}",
                        intent_inserted=False,
                        attention_requested=self._existing_wake_request(existing_intent),
                        wake_state=None,
                        blocker="CARRIER_RECONCILIATION_REQUIRED",
                    ),
                }
            raise ConsultationRefusal(
                "CARRIER_RECONCILIATION_REQUIRED",
                detail="QUESTION carrier history is unavailable before INTENT",
            ) from exc
        carrier_holds_packet = carrier_question_frame is not None
        # The carrier read is an await boundary. Re-read canonical Runtime
        # before classifying a visible packet as orphaned; an identical
        # concurrent caller may have committed INTENT and packet meanwhile.
        existing_intent = _find_consultation_event(
            self.runtime, consultation_id, "INTENT"
        )
        if existing_intent is None and carrier_holds_packet:
            raise ConsultationRefusal(
                "CONFLICT",
                detail="orphan QUESTION packet exists without canonical INTENT",
            )
        if existing_intent is not None:
            persisted_payload = existing_intent.payload
            candidate = _build_question_frame(
                caller=self.caller,
                requester_actor_ref=dict(
                    persisted_payload.get("requester_actor_ref")
                    or requester_actor_ref
                ),
                recipient_actor_ref=dict(
                    persisted_payload.get("recipient_actor_ref")
                    or recipient_actor_ref
                ),
                recipient_peer_ref=str(
                    persisted_payload.get(
                        "recipient_peer_ref", peer_ref
                    )
                ),
                recipient_binding=dict(
                    persisted_payload.get("recipient_binding")
                    or normalized_recipient_binding
                ),
                correlation=dict(
                    persisted_payload.get("correlation") or correlation
                ),
                question_text=str(semantic["question"]),
                evidence_refs=list(semantic.get("evidence_refs", [])),
                artifact_revisions=list(
                    semantic.get("artifact_revisions", [])
                ),
                message_key=str(persisted_payload.get("message_key")),
                consultation_id=str(
                    persisted_payload.get("consultation_id")
                ),
                valid_until=str(persisted_payload.get("valid_until")),
                deadline_ms=int(persisted_payload.get("deadline_ms")),
                response_budget=dict(
                    persisted_payload.get("response_budget")
                    or response_budget
                ),
            )
            persisted_fingerprint = str(
                persisted_payload.get("semantic_fingerprint", "")
            )
            persisted_peer_ref = str(
                persisted_payload.get("recipient_peer_ref", "")
            )
            candidate_fingerprint = str(candidate.get("fingerprint", ""))
            fingerprint_agrees = (
                candidate_fingerprint == persisted_fingerprint
            )
            peer_ref_agrees = (
                str(candidate.get("recipient_peer_ref", ""))
                == persisted_peer_ref
            )
            body_agrees = True
            if carrier_holds_packet:
                body_agrees = (
                    str(candidate.get("question", ""))
                    == str(carrier_question_frame.get("question", ""))
                    and list(candidate.get("evidence_refs", []))
                    == list(carrier_question_frame.get("evidence_refs", []))
                    and list(candidate.get("artifact_revisions", []))
                    == list(
                        carrier_question_frame.get("artifact_revisions", [])
                    )
                )
            if not (fingerprint_agrees and peer_ref_agrees and body_agrees):
                raise ConsultationRefusal(
                    "CONFLICT",
                    detail="consultation_id reused with changed semantic payload",
                )
            question_frame = candidate
            # IAC-1 r4d-N1: a replay is bounded by the PERSISTED validity.
            valid_until = str(persisted_payload.get("valid_until"))
            if _is_expired(valid_until, now):
                # Expired replay: no publication, no Wake origination.
                # ``attention_requested`` reports only whether the exact
                # request ALREADY exists (read-only readback).
                return {
                    "ok": True,
                    "result": _committed_consult_result(
                        consultation_id=consultation_id,
                        valid_until=valid_until,
                        carrier_ref=f"company-mcp://{consultation_id}",
                        intent_inserted=False,
                        attention_requested=self._existing_wake_request(
                            existing_intent
                        ),
                        wake_state=None,
                        blocker="EXPIRED",
                    ),
                }
        elif _is_expired(valid_until, now):
            # IAC-1 r4d-N1: first publication after validity elapsed is
            # refused with zero effect (no intent(), no put, no Wake).
            raise ConsultationRefusal(
                "EXPIRED", detail="valid_until elapsed before publication"
            )

        carrier_ref = f"company-mcp://{consultation_id}"
        intent_result: Any | None = None
        intent_event: Any | None = None

        def _append_intent() -> Any:
            try:
                return self._consultations.intent(
                    question_frame,
                    requester_attempt_id=self.caller.attempt_id,
                    carrier_ref=carrier_ref,
                    observed_at=ctx.issued_at,
                    repository_root=self.repository_root,
                )
            except (ConsultationConflict, StateConflict) as exc:
                raise ConsultationRefusal(
                    "CONFLICT", detail=type(exc).__name__
                ) from exc

        if existing_intent is not None:
            # Canonical Runtime already owns this identity. Reconcile the
            # idempotent Runtime edge directly and require exact physical
            # readback; a replay never authorizes a resend.
            intent_result = _append_intent()
            intent_event = _find_consultation_event(
                self.runtime, consultation_id, "INTENT"
            )
            try:
                carrier_question_frame = await self.packets.get_question(
                    consultation_id
                )
            except (
                ConsultationPacketCarrierUnknown,
                ConsultationPacketEffectUnknown,
            ):
                carrier_question_frame = None
            carrier_holds_packet = carrier_question_frame is not None
            if (
                intent_event is None
                or not carrier_holds_packet
                or _validated_question_frame(
                    intent_event.payload, carrier_question_frame
                )
                is None
            ):
                return {
                    "ok": True,
                    "result": _committed_consult_result(
                        consultation_id=consultation_id,
                        valid_until=valid_until,
                        carrier_ref=carrier_ref,
                        intent_inserted=False,
                        attention_requested=(
                            self._existing_wake_request(intent_event)
                            if intent_event is not None
                            else None
                        ),
                        wake_state=None,
                        blocker="CARRIER_RECONCILIATION_REQUIRED",
                    ),
                }
        else:
            intent_box: dict[str, Any] = {}
            runtime_refusal: ConsultationRefusal | None = None

            async def _commit_intent_after_ready() -> None:
                nonlocal runtime_refusal
                try:
                    result = _append_intent()
                except ConsultationRefusal as exc:
                    runtime_refusal = exc
                    raise ConsultationPacketCommitAborted(
                        "Runtime INTENT refused before Relay COMMIT"
                    ) from exc
                intent_box["result"] = result
                if not result.inserted:
                    raise ConsultationPacketCommitAborted(
                        "Runtime INTENT replay/race loser cannot Relay COMMIT"
                    )

            try:
                await self.packets.put_question(
                    consultation_id,
                    question_frame,
                    before_commit=_commit_intent_after_ready,
                )
            except ConsultationPacketCommitAborted:
                if runtime_refusal is not None:
                    raise runtime_refusal
                intent_result = intent_box.get("result")
                intent_event = _find_consultation_event(
                    self.runtime, consultation_id, "INTENT"
                )
                try:
                    readback = await self.packets.get_question(consultation_id)
                except (
                    ConsultationPacketCarrierUnknown,
                    ConsultationPacketEffectUnknown,
                ):
                    readback = None
                if intent_event is None:
                    if readback is not None:
                        raise ConsultationRefusal(
                            "CONFLICT",
                            detail="orphan QUESTION packet exists without canonical INTENT",
                        )
                    raise ConsultationRefusal(
                        "CARRIER_RECONCILIATION_REQUIRED",
                        detail="Relay COMMIT aborted before canonical INTENT",
                    )
                if (
                    _validated_question_frame(intent_event.payload, readback)
                    is None
                ):
                    return {
                        "ok": True,
                        "result": _committed_consult_result(
                            consultation_id=consultation_id,
                            valid_until=valid_until,
                            carrier_ref=carrier_ref,
                            intent_inserted=False,
                            attention_requested=self._existing_wake_request(
                                intent_event
                            ),
                            wake_state=None,
                            blocker="CARRIER_RECONCILIATION_REQUIRED",
                        ),
                    }
            except ConsultationPacketEffectUnknown:
                intent_result = intent_box.get("result")
                intent_event = _find_consultation_event(
                    self.runtime, consultation_id, "INTENT"
                )
                if intent_event is None:
                    raise ConsultationRefusal(
                        "CARRIER_RECONCILIATION_REQUIRED",
                        detail="Relay COMMIT is uncertain and INTENT is unavailable",
                    )
                # One same-carrier readback may prove that the uncertain COMMIT
                # actually landed. It never authorizes a resend. Continue to
                # the owed Wake only when the exact persisted QUESTION validates.
                try:
                    readback = await self.packets.get_question(consultation_id)
                except (
                    ConsultationPacketCarrierUnknown,
                    ConsultationPacketEffectUnknown,
                ):
                    readback = None
                existing_wake = self._existing_wake_request(intent_event)
                if (
                    _validated_question_frame(intent_event.payload, readback)
                    is None
                    or existing_wake is True
                ):
                    return {
                        "ok": True,
                        "result": _committed_consult_result(
                            consultation_id=consultation_id,
                            valid_until=valid_until,
                            carrier_ref=carrier_ref,
                            intent_inserted=bool(
                                getattr(intent_result, "inserted", False)
                            ),
                            attention_requested=existing_wake,
                            wake_state=None,
                            blocker="CARRIER_RECONCILIATION_REQUIRED",
                        ),
                    }
                # Validated readback proves the packet is already committed.
                # Fall through to the single existing Wake creation path.
            except ConsultationPacketCarrierUnknown as exc:
                intent_result = intent_box.get("result")
                intent_event = _find_consultation_event(
                    self.runtime, consultation_id, "INTENT"
                )
                if intent_event is not None:
                    return {
                        "ok": True,
                        "result": _committed_consult_result(
                            consultation_id=consultation_id,
                            valid_until=valid_until,
                            carrier_ref=carrier_ref,
                            intent_inserted=bool(
                                getattr(intent_result, "inserted", False)
                            ),
                            attention_requested=self._existing_wake_request(intent_event),
                            wake_state=None,
                            blocker="CARRIER_RECONCILIATION_REQUIRED",
                        ),
                    }
                raise ConsultationRefusal(
                    "CARRIER_RECONCILIATION_REQUIRED",
                    detail="Relay packet carrier unavailable before INTENT",
                ) from exc


            intent_result = intent_box.get("result")
            intent_event = _find_consultation_event(
                self.runtime, consultation_id, "INTENT"
            )

            if intent_result is None:
                try:
                    readback = await self.packets.get_question(consultation_id)
                except (
                    ConsultationPacketCarrierUnknown,
                    ConsultationPacketEffectUnknown,
                ):
                    if intent_event is not None:
                        return {
                            "ok": True,
                            "result": _committed_consult_result(
                                consultation_id=consultation_id,
                                valid_until=valid_until,
                                carrier_ref=carrier_ref,
                                intent_inserted=False,
                                attention_requested=self._existing_wake_request(
                                    intent_event
                                ),
                                wake_state="RECONCILIATION_REQUIRED",
                                blocker="CARRIER_RECONCILIATION_REQUIRED",
                            ),
                        }
                    raise ConsultationRefusal(
                        "CARRIER_RECONCILIATION_REQUIRED",
                        detail="Relay duplicate returned without Runtime/readback",
                    )
                if intent_event is None:
                    if readback is not None:
                        raise ConsultationRefusal(
                            "CONFLICT",
                            detail="orphan QUESTION packet exists without canonical INTENT",
                        )
                    raise ConsultationRefusal(
                        "CARRIER_RECONCILIATION_REQUIRED",
                        detail="Relay returned without Runtime INTENT or packet",
                    )
                if (
                    _validated_question_frame(intent_event.payload, readback)
                    is None
                ):
                    return {
                        "ok": True,
                        "result": _committed_consult_result(
                            consultation_id=consultation_id,
                            valid_until=valid_until,
                            carrier_ref=carrier_ref,
                            intent_inserted=False,
                            attention_requested=self._existing_wake_request(
                                intent_event
                            ),
                            wake_state="RECONCILIATION_REQUIRED",
                            blocker="CARRIER_RECONCILIATION_REQUIRED",
                        ),
                    }
                intent_result = ConsultationEventResult(
                    event=intent_event, inserted=False
                )

        if intent_result is None or intent_event is None:
            raise ConsultationRefusal(
                "CONFLICT", detail="INTENT missing after Relay/Runtime composition"
            )

        # IAC-1 r4c2: the production dispatcher creates exactly one
        # durable WAKE_REQUESTED per admitted consult. The recipe
        # derives the RuntimeBinding from the persisted INTENT via the
        # existing runtime owner and writes the record through the
        # existing WakeLedgerRepository. Any exception leaves the
        # committed INTENT durable and the caller sees a typed blocker
        # (no silent failure, no hidden retry).
        repository = self._wake_repository
        try:
            obligation = self._wake_obligation(intent_event)
        except Exception:
            # The obligation could not be derived, so no same-ledger
            # readback is possible: the state is unknown (None). It is
            # never inferred from ``intent_result.inserted`` — insertion
            # granted publication, not exclusive ownership of the Wake.
            return {
                "ok": True,
                "result": _committed_consult_result(
                    consultation_id=consultation_id,
                    valid_until=valid_until,
                    carrier_ref=carrier_ref,
                    intent_inserted=intent_result.inserted,
                    attention_requested=None,
                    wake_state="RECONCILIATION_REQUIRED",
                    blocker="WAKE_REQUEST_UNRESOLVED",
                ),
            }

        # IAC-1 r4d-N1: second fence immediately before the request
        # append. Validity elapsed between publication and request →
        # no append; ``attention_requested`` is a read-only readback.
        if _is_expired(valid_until, self._clock()):
            return {
                "ok": True,
                "result": _committed_consult_result(
                    consultation_id=consultation_id,
                    valid_until=valid_until,
                    carrier_ref=carrier_ref,
                    intent_inserted=intent_result.inserted,
                    attention_requested=_wake_request_readback(
                        repository, obligation.obligation_id
                    ),
                    wake_state=None,
                    blocker="EXPIRED",
                ),
            }

        try:
            repository.append_record(
                requested_record(obligation), obligation=obligation
            )
            attention_requested: bool | None = True
        except Exception:
            # IAC-1 r4d-N3: a post-append failure is reconciled on the
            # SAME ledger. True only if the exact request is visible,
            # False only if proven absent, None (unknown) if the
            # readback is unavailable or conflicting. Never raise: the
            # INTENT append is a known effect that must not be hidden.
            attention_requested = _wake_request_readback(
                repository, obligation.obligation_id
            )
            if attention_requested is not True:
                return {
                    "ok": True,
                    "result": _committed_consult_result(
                        consultation_id=consultation_id,
                        valid_until=valid_until,
                        carrier_ref=carrier_ref,
                        intent_inserted=intent_result.inserted,
                        attention_requested=attention_requested,
                        wake_state="RECONCILIATION_REQUIRED",
                        blocker="WAKE_REQUEST_UNRESOLVED",
                    ),
                }

        try:
            wake_state = self._consultations.resolve_restart(question_frame)
        except StateConflict:
            return {
                "ok": True,
                "result": _committed_consult_result(
                    consultation_id=consultation_id,
                    valid_until=valid_until,
                    carrier_ref=carrier_ref,
                    intent_inserted=intent_result.inserted,
                    attention_requested=attention_requested,
                    wake_state="RECONCILIATION_REQUIRED",
                    blocker="WAKE_STATE_UNAVAILABLE",
                ),
            }
        return {
            "ok": True,
            "result": _committed_consult_result(
                consultation_id=consultation_id,
                valid_until=valid_until,
                carrier_ref=carrier_ref,
                intent_inserted=intent_result.inserted,
                attention_requested=attention_requested,
                wake_state=wake_state,
                blocker=None,
            ),
        }

    def _wake_obligation(self, intent_event: Any):
        """Derive the canonical Wake obligation from the persisted INTENT
        via the existing runtime owners (no caller-provided target)."""
        question_item = self._consultations._intent_from_event(intent_event)
        with self.runtime.store.read() as connection:
            binding = self._consultations._require_current_recipient(
                question_item, connection=connection
            )
            identity = (
                self._consultations
                ._consultation_source_identity_on_connection(
                    question_item, connection
                )
            )
        return ConsultationWakeExtension(
            repository=self._wake_repository,
            requester_job_id=identity.requester_job_id,
            requester_attempt_id=identity.requester_attempt_id,
            root_job_id=identity.root_job_id,
            recipient_job_id=identity.recipient_job_id,
            recipient_attempt_id=identity.recipient_attempt_id,
            consultation_id=identity.consultation_id,
            message_key=identity.message_key,
            semantic_fingerprint=identity.semantic_fingerprint,
            current_binding=binding,
        ).obligation()

    def _existing_wake_request(self, intent_event: Any) -> bool | None:
        """Read-only tri-state: does the exact WAKE_REQUESTED already
        exist for this persisted INTENT? Never appends."""
        try:
            obligation = self._wake_obligation(intent_event)
        except Exception:
            return None
        return _wake_request_readback(
            self._wake_repository, obligation.obligation_id
        )

    # -- company.reply --

    async def _dispatch_reply(
        self, request: Mapping[str, Any]
    ) -> dict[str, Any]:
        raw_semantic = request.get("semantic")
        if not isinstance(raw_semantic, Mapping):
            raise ConsultationRefusal(
                "INVALID_REQUEST", detail="semantic mapping required"
            )
        semantic = dict(raw_semantic)
        invalid = _validate_reply_semantic(semantic)
        if invalid is not None:
            raise ConsultationRefusal("INVALID_REQUEST", detail=invalid)

        consultation_ref = semantic["consultation_ref"]
        intent = _find_consultation_event(
            self.runtime, consultation_ref, "INTENT"
        )
        if intent is None:
            raise ConsultationRefusal(
                "UNAVAILABLE", detail="no INTENT for consultation_ref"
            )
        recipient_actor_ref = intent.payload.get("recipient_actor_ref") or {}
        recipient_binding = intent.payload.get("recipient_binding") or {}
        if not _caller_matches_actor(self.caller, recipient_actor_ref):
            raise ConsultationRefusal(
                "NOT_A_PARTY",
                detail="caller is not the recipient Runtime Attempt",
            )
        if not _caller_matches_binding(self.caller, recipient_binding):
            raise ConsultationRefusal(
                "STALE_BINDING",
                detail="caller RuntimeBinding does not match persisted recipient_binding",
            )

        try:
            question_frame = await self.packets.get_question(consultation_ref)
        except (
            ConsultationPacketCarrierUnknown,
            ConsultationPacketEffectUnknown,
        ) as exc:
            raise ConsultationRefusal(
                "CARRIER_RECONCILIATION_REQUIRED",
                detail="QUESTION carrier history is unavailable",
            ) from exc
        if question_frame is None:
            raise ConsultationRefusal(
                "CARRIER_UNAVAILABLE",
                detail="no QUESTION frame on the carrier",
            )
        try:
            validate_consultation(dict(question_frame))
        except Exception as exc:
            raise ConsultationRefusal(
                "CONFLICT",
                detail=f"carrier QUESTION frame invalid: {type(exc).__name__}",
            ) from exc
        if (
            question_frame.get("consultation_id") != consultation_ref
            or question_frame.get("message_key")
            != intent.payload.get("message_key")
            or question_frame.get("fingerprint")
            != intent.payload.get("semantic_fingerprint")
            or _question_digest(str(question_frame.get("question", "")))
            != intent.payload.get("question_digest")
        ):
            raise ConsultationRefusal(
                "CONFLICT",
                detail="carrier QUESTION frame does not match persisted INTENT",
            )
        if not _intent_matches_frame(intent.payload, question_frame):
            raise ConsultationRefusal(
                "CONFLICT",
                detail="carrier QUESTION frame fields disagree with persisted INTENT",
            )

        # Enforce the persisted packet-safe response budget before any
        # ANSWER_AVAILABLE append. Both semantic-answer bytes and the complete
        # nested ANSWER packet must fit the frozen Relay wire.
        answer_text = str(semantic.get("answer", ""))
        evidence_refs = list(semantic.get("evidence_refs", []))
        response_budget = dict(intent.payload.get("response_budget", {}))
        max_evidence_reads = int(
            response_budget.get(
                "max_evidence_reads",
                _DEFAULT_RESPONSE_BUDGET["max_evidence_reads"],
            )
        )
        packet_wire_required = getattr(
            self.packets, "requires_packet_wire", False
        )
        if packet_wire_required and len(evidence_refs) > max_evidence_reads:
            raise ConsultationRefusal(
                "INVALID_REQUEST",
                detail=f"answer evidence exceeds {max_evidence_reads} references",
            )
        answer_canonical = canonical_consultation_json(
            {"text": answer_text, "evidence_refs": evidence_refs}
        )
        max_payload_bytes = int(
            response_budget.get(
                "max_payload_bytes", _DEFAULT_RESPONSE_BUDGET["max_payload_bytes"]
            )
        )
        if len(answer_canonical.encode("utf-8")) > max_payload_bytes:
            raise ConsultationRefusal(
                "INVALID_REQUEST",
                detail=f"answer canonical JSON exceeds {max_payload_bytes} bytes",
            )

        try:
            answer_frame = _build_answer_frame(
                question_frame,
                answer_text=answer_text,
                evidence_refs=evidence_refs,
                supersedes=semantic.get("supersedes_message_key"),
            )
            if packet_wire_required:
                render_consultation_packet(answer_frame)
        except DialogueContractError as exc:
            raise ConsultationRefusal(
                "INVALID_REQUEST",
                detail="complete ANSWER packet exceeds the bounded Relay wire",
            ) from exc
        except Exception as exc:
            raise ConsultationRefusal(
                "CONFLICT",
                detail=f"answer frame invalid: {type(exc).__name__}",
            ) from exc

        try:
            question_item = self._consultations._intent_from_event(intent)
            pre_wake_state = self._consultations._canonical_wake_state(
                question_item
            ).value
        except ConsultationConflict as exc:
            raise ConsultationRefusal(
                "CONFLICT", detail=type(exc).__name__
            ) from exc
        except StateConflict as exc:
            raise ConsultationRefusal(
                "WAKE_NOT_ACKNOWLEDGED",
                detail=f"wake state unavailable: {type(exc).__name__}",
            ) from exc

        if pre_wake_state not in _ACKNOWLEDGED_WAKE_STATES:
            raise ConsultationRefusal(
                "WAKE_NOT_ACKNOWLEDGED",
                detail="answer requires canonical TARGET_ACKNOWLEDGED Wake evidence",
            )

        def _reconciled_envelope(
            reserved_event: Any, validated_frame: Mapping[str, Any]
        ) -> dict[str, Any]:
            attention_requested, wake_state, blocker = (
                self._request_answer_attention(validated_frame, intent)
            )
            return {
                "ok": True,
                "result": {
                    "schema": _INBOX_SCHEMA,
                    "consultation_ref": consultation_ref,
                    "state": "ANSWER_AVAILABLE",
                    "answer_fingerprint": reserved_event.payload.get(
                        "answer_fingerprint", ""
                    ),
                    "semantic_answer_digest": reserved_event.payload.get(
                        "semantic_answer_digest", ""
                    ),
                    "historical": False,
                    "inserted": False,
                    "reconciled": True,
                    "attention_requested": attention_requested,
                    "wake_state": wake_state,
                    "blocker": blocker,
                },
            }

        # Reconcile on the carrier FIRST. If the runtime already admitted
        # a non-historical ANSWER_AVAILABLE, the carrier is the
        # single source of truth for the admitted packet: validate it
        # with ``_validated_answer_frame`` and reconcile without
        # touching the runtime or the carrier again. A missing or
        # mismatched carrier frame is the same-carrier recovery
        # barrier (CARRIER_RECONCILIATION_REQUIRED); we never rewrite
        # and never resend.
        reserved = _non_historical_answer_event(
            self.runtime, consultation_ref
        )
        if reserved is not None:
            # A DIFFERENT second answer can never replace or be
            # relabelled as the admitted one: refuse with zero effect.
            if _semantic_answer_digest(answer_frame) != reserved.payload.get(
                "semantic_answer_digest"
            ):
                raise ConsultationRefusal(
                    "CONFLICT",
                    detail="second answer differs from the admitted answer",
                )
            try:
                packet = await self.packets.get_answer(consultation_ref)
            except (
                ConsultationPacketCarrierUnknown,
                ConsultationPacketEffectUnknown,
            ) as exc:
                raise ConsultationRefusal(
                    "CARRIER_RECONCILIATION_REQUIRED",
                    detail="admitted ANSWER carrier history is unavailable",
                ) from exc
            validated = _validated_answer_frame(
                intent.payload, reserved, packet
            )
            if validated is None:
                raise ConsultationRefusal(
                    "CARRIER_RECONCILIATION_REQUIRED",
                    detail="admitted ANSWER_AVAILABLE but carrier frame is missing or fails validation",
                )
            return _reconciled_envelope(reserved, validated)

        answer_box: dict[str, Any] = {}
        runtime_refusal: ConsultationRefusal | None = None

        def _answer_event_facts(result: Any) -> tuple[Any, str, Any, bool]:
            event = result.event
            event_type = getattr(event, "event_type", "")
            payload_fact = (
                event.payload.get("fact")
                if hasattr(event, "payload")
                else None
            )
            historical = bool(event.payload.get("historical", False))
            return event, event_type, payload_fact, historical

        async def _commit_answer_after_ready() -> None:
            nonlocal runtime_refusal
            try:
                result = self._consultations.answer_available(
                    answer_frame, observed_at=self._clock()
                )
            except ConsultationConflict as exc:
                runtime_refusal = ConsultationRefusal(
                    "CONFLICT", detail=type(exc).__name__
                )
                raise ConsultationPacketCommitAborted(
                    "Runtime ANSWER_AVAILABLE refused before Relay COMMIT"
                ) from exc
            except StateConflict as exc:
                message = str(exc)
                code = (
                    "WAKE_NOT_ACKNOWLEDGED"
                    if "TARGET_ACKNOWLEDGED" in message
                    else "CONFLICT"
                )
                runtime_refusal = ConsultationRefusal(
                    code, detail=type(exc).__name__
                )
                raise ConsultationPacketCommitAborted(
                    "Runtime ANSWER_AVAILABLE refused before Relay COMMIT"
                ) from exc

            answer_box["result"] = result
            event, event_type, payload_fact, historical = _answer_event_facts(result)
            if event_type == "ANSWER_REFUSED" or payload_fact == "ANSWER_REFUSED":
                runtime_refusal = ConsultationRefusal(
                    "CONFLICT", detail="ANSWER_REFUSED"
                )
                raise ConsultationPacketCommitAborted(
                    "Runtime refused the answer before Relay COMMIT"
                )
            if historical or not result.inserted:
                raise ConsultationPacketCommitAborted(
                    "historical/replayed answer cannot Relay COMMIT"
                )

        try:
            await self.packets.put_answer(
                consultation_ref,
                answer_frame,
                before_commit=_commit_answer_after_ready,
            )
        except ConsultationPacketCommitAborted:
            if runtime_refusal is not None:
                raise runtime_refusal
            answer = answer_box.get("result")
            if answer is None:
                raise ConsultationRefusal(
                    "CARRIER_RECONCILIATION_REQUIRED",
                    detail="Relay COMMIT aborted without a canonical answer fact",
                )
            event, event_type, payload_fact, historical = _answer_event_facts(answer)
            if historical:
                return {
                    "ok": True,
                    "result": {
                        "schema": _INBOX_SCHEMA,
                        "consultation_ref": consultation_ref,
                        "state": "ANSWER_HISTORICAL",
                        "answer_fingerprint": event.payload.get(
                            "answer_fingerprint", ""
                        ),
                        "semantic_answer_digest": event.payload.get(
                            "semantic_answer_digest", ""
                        ),
                        "historical": True,
                        "inserted": bool(answer.inserted),
                        "attention_requested": False,
                        "wake_state": None,
                        "blocker": None,
                    },
                }

            current_reserved = _non_historical_answer_event(
                self.runtime, consultation_ref
            )
            try:
                packet = await self.packets.get_answer(consultation_ref)
            except (
                ConsultationPacketCarrierUnknown,
                ConsultationPacketEffectUnknown,
            ) as exc:
                raise ConsultationRefusal(
                    "CARRIER_RECONCILIATION_REQUIRED",
                    detail="replayed ANSWER carrier history is unavailable",
                ) from exc
            validated = _validated_answer_frame(
                intent.payload, current_reserved, packet
            )
            if validated is None:
                raise ConsultationRefusal(
                    "CARRIER_RECONCILIATION_REQUIRED",
                    detail="replay ANSWER_AVAILABLE admitted but carrier frame is missing or fails validation",
                )
            return _reconciled_envelope(current_reserved, validated)
        except ConsultationPacketEffectUnknown:
            answer = answer_box.get("result")
            current_reserved = _non_historical_answer_event(
                self.runtime, consultation_ref
            )
            if answer is None or current_reserved is None:
                raise ConsultationRefusal(
                    "CARRIER_RECONCILIATION_REQUIRED",
                    detail="Relay ANSWER COMMIT is uncertain without canonical readback",
                )
            # Reconcile the exact admitted answer once on the same carrier.
            # A validated readback proves the COMMIT landed and allows the
            # existing requester-attention path below to continue. Any absent,
            # uncertain, or mismatched readback preserves the barrier.
            try:
                packet = await self.packets.get_answer(consultation_ref)
            except (
                ConsultationPacketCarrierUnknown,
                ConsultationPacketEffectUnknown,
            ):
                packet = None
            if (
                _validated_answer_frame(
                    intent.payload, current_reserved, packet
                )
                is None
            ):
                event, _event_type, _payload_fact, historical = _answer_event_facts(
                    answer
                )
                return {
                    "ok": True,
                    "result": {
                        "schema": _INBOX_SCHEMA,
                        "consultation_ref": consultation_ref,
                        "state": (
                            "ANSWER_HISTORICAL"
                            if historical
                            else "ANSWER_AVAILABLE"
                        ),
                        "answer_fingerprint": event.payload.get(
                            "answer_fingerprint", ""
                        ),
                        "semantic_answer_digest": event.payload.get(
                            "semantic_answer_digest", ""
                        ),
                        "historical": historical,
                        "inserted": bool(answer.inserted),
                        "attention_requested": None,
                        "wake_state": "RECONCILIATION_REQUIRED",
                        "blocker": "CARRIER_RECONCILIATION_REQUIRED",
                    },
                }
            # Exact readback proves the answer is already on the carrier.
            # Fall through to the single existing requester-attention path.
        except ConsultationPacketCarrierUnknown as exc:
            answer = answer_box.get("result")
            current_reserved = _non_historical_answer_event(
                self.runtime, consultation_ref
            )
            if answer is not None and current_reserved is not None:
                event, _event_type, _payload_fact, historical = _answer_event_facts(answer)
                return {
                    "ok": True,
                    "result": {
                        "schema": _INBOX_SCHEMA,
                        "consultation_ref": consultation_ref,
                        "state": (
                            "ANSWER_HISTORICAL"
                            if historical
                            else "ANSWER_AVAILABLE"
                        ),
                        "answer_fingerprint": event.payload.get(
                            "answer_fingerprint", ""
                        ),
                        "semantic_answer_digest": event.payload.get(
                            "semantic_answer_digest", ""
                        ),
                        "historical": historical,
                        "inserted": bool(answer.inserted),
                        "attention_requested": None,
                        "wake_state": "RECONCILIATION_REQUIRED",
                        "blocker": "CARRIER_RECONCILIATION_REQUIRED",
                    },
                }
            raise ConsultationRefusal(
                "CARRIER_RECONCILIATION_REQUIRED",
                detail="Relay packet carrier unavailable before ANSWER_AVAILABLE",
            ) from exc


        answer = answer_box.get("result")
        if answer is None:
            current_reserved = _non_historical_answer_event(
                self.runtime, consultation_ref
            )
            try:
                packet = await self.packets.get_answer(consultation_ref)
            except (
                ConsultationPacketCarrierUnknown,
                ConsultationPacketEffectUnknown,
            ):
                if current_reserved is not None:
                    return {
                        "ok": True,
                        "result": {
                            "schema": _INBOX_SCHEMA,
                            "consultation_ref": consultation_ref,
                            "state": "ANSWER_AVAILABLE",
                            "answer_fingerprint": current_reserved.payload.get(
                                "answer_fingerprint", ""
                            ),
                            "semantic_answer_digest": current_reserved.payload.get(
                                "semantic_answer_digest", ""
                            ),
                            "historical": False,
                            "inserted": False,
                            "reconciled": True,
                            "attention_requested": None,
                            "wake_state": "RECONCILIATION_REQUIRED",
                            "blocker": "CARRIER_RECONCILIATION_REQUIRED",
                        },
                    }
                raise ConsultationRefusal(
                    "CARRIER_RECONCILIATION_REQUIRED",
                    detail="Relay duplicate returned without Runtime/readback",
                )
            if current_reserved is None:
                if packet is not None:
                    raise ConsultationRefusal(
                        "CONFLICT",
                        detail="orphan ANSWER packet exists without canonical ANSWER_AVAILABLE",
                    )
                raise ConsultationRefusal(
                    "CARRIER_RECONCILIATION_REQUIRED",
                    detail="Relay returned without ANSWER_AVAILABLE or packet",
                )
            validated = _validated_answer_frame(
                intent.payload, current_reserved, packet
            )
            if validated is None:
                return {
                    "ok": True,
                    "result": {
                        "schema": _INBOX_SCHEMA,
                        "consultation_ref": consultation_ref,
                        "state": "ANSWER_AVAILABLE",
                        "answer_fingerprint": current_reserved.payload.get(
                            "answer_fingerprint", ""
                        ),
                        "semantic_answer_digest": current_reserved.payload.get(
                            "semantic_answer_digest", ""
                        ),
                        "historical": False,
                        "inserted": False,
                        "reconciled": True,
                        "attention_requested": None,
                        "wake_state": "RECONCILIATION_REQUIRED",
                        "blocker": "CARRIER_RECONCILIATION_REQUIRED",
                    },
                }
            return _reconciled_envelope(current_reserved, validated)
        event, event_type, payload_fact, historical = _answer_event_facts(answer)
        if historical or not answer.inserted:
            raise ConsultationRefusal(
                "CONFLICT", detail="Relay committed a non-inserted or historical answer"
            )

        attention_requested, wake_state, blocker = (
            self._request_answer_attention(answer_frame, intent)
        )
        return {
            "ok": True,
            "result": {
                "schema": _INBOX_SCHEMA,
                "consultation_ref": consultation_ref,
                "state": "ANSWER_AVAILABLE",
                "answer_fingerprint": event.payload.get(
                    "answer_fingerprint", ""
                ),
                "semantic_answer_digest": event.payload.get(
                    "semantic_answer_digest", ""
                ),
                "historical": False,
                "inserted": bool(answer.inserted),
                "attention_requested": attention_requested,
                "wake_state": wake_state,
                "blocker": blocker,
            },
        }

    def _request_answer_attention(
        self, answer_frame: Mapping[str, Any], intent_event: Any
    ) -> tuple[bool | None, str | None, str | None]:
        """Create/reconcile the one requester-directed answer Wake request."""

        requester = intent_event.payload.get("requester_actor_ref") or {}
        requester_attempt_id = requester.get("attempt_id")
        if not isinstance(requester_attempt_id, str) or not requester_attempt_id:
            return None, "RECONCILIATION_REQUIRED", "ANSWER_ATTENTION_UNRESOLVED"
        try:
            projection = self._consultations.requester_answer_attention_replay(
                answer_frame, requester_attempt_id=requester_attempt_id
            )
            extension = RequesterAnswerWakeExtension(
                repository=self._wake_repository, projection=projection
            )
        except ConsultationConflict as exc:
            if exc.conflict == "ANSWER_ALREADY_CONSUMED":
                return False, None, "ANSWER_ALREADY_CONSUMED"
            return None, "RECONCILIATION_REQUIRED", "ANSWER_ATTENTION_UNRESOLVED"
        except StateConflict:
            return None, "RECONCILIATION_REQUIRED", "ANSWER_ATTENTION_UNRESOLVED"

        obligation_id = projection.obligation.obligation_id
        try:
            extension.persist_requested_if_current(self._consultations)
        except ConsultationConflict as exc:
            present = _wake_request_readback(
                self._wake_repository, obligation_id
            )
            if present is True:
                return (
                    True,
                    _wake_state_readback(self._wake_repository, obligation_id),
                    None,
                )
            if exc.conflict == "ANSWER_ALREADY_CONSUMED" and present is False:
                return False, None, "ANSWER_ALREADY_CONSUMED"
            return (
                present,
                "RECONCILIATION_REQUIRED",
                "ANSWER_ATTENTION_UNRESOLVED",
            )
        except Exception:
            present = _wake_request_readback(
                self._wake_repository, obligation_id
            )
            if present is True:
                return (
                    True,
                    _wake_state_readback(self._wake_repository, obligation_id),
                    None,
                )
            return (
                present,
                "RECONCILIATION_REQUIRED",
                "ANSWER_ATTENTION_UNRESOLVED",
            )
        return (
            True,
            _wake_state_readback(self._wake_repository, obligation_id),
            None,
        )

    # -- company.consultation --

    async def _dispatch_read(
        self, request: Mapping[str, Any]
    ) -> dict[str, Any]:
        raw_semantic = request.get("semantic")
        if not isinstance(raw_semantic, Mapping):
            raise ConsultationRefusal(
                "INVALID_REQUEST", detail="semantic mapping required"
            )
        semantic = dict(raw_semantic)
        invalid = _validate_read_semantic(semantic)
        if invalid is not None:
            raise ConsultationRefusal("INVALID_REQUEST", detail=invalid)

        consultation_ref = semantic["consultation_ref"]
        intent = _find_consultation_event(
            self.runtime, consultation_ref, "INTENT"
        )
        if intent is None:
            raise ConsultationRefusal(
                "UNAVAILABLE", detail="no INTENT for consultation_ref"
            )
        requester_ref = intent.payload.get("requester_actor_ref") or {}
        recipient_ref = intent.payload.get("recipient_actor_ref") or {}
        if not (
            _caller_matches_actor(self.caller, requester_ref)
            or _caller_matches_actor(self.caller, recipient_ref)
        ):
            raise ConsultationRefusal(
                "NOT_A_PARTY",
                detail="caller is neither requester nor recipient Runtime Attempt",
            )
        # The detail edge revalidates the recipient's RuntimeBinding exactly as
        # the reply edge does: a rolled binding reads nothing. The requester leg
        # has no persisted binding on the INTENT (only the recipient's is
        # admitted), so requester detail access is bound by exact actor only.
        if _caller_matches_actor(self.caller, recipient_ref) and not (
            _caller_matches_binding(
                self.caller, intent.payload.get("recipient_binding") or {}
            )
        ):
            raise ConsultationRefusal(
                "STALE_BINDING",
                detail="caller RuntimeBinding does not match persisted recipient_binding",
            )

        row = company_inbox_row(
            self.runtime,
            consultation_ref,
            {
                "job_id": self.caller.job_id,
                "attempt_id": self.caller.attempt_id,
                "worker_id": self.caller.worker_id,
            },
            self._clock(),
        )

        question_carrier_unknown = False
        answer_carrier_unknown = False
        try:
            question_frame = await self.packets.get_question(consultation_ref)
        except (
            ConsultationPacketCarrierUnknown,
            ConsultationPacketEffectUnknown,
        ):
            question_frame = None
            question_carrier_unknown = True
        try:
            answer_frame = await self.packets.get_answer(consultation_ref)
        except (
            ConsultationPacketCarrierUnknown,
            ConsultationPacketEffectUnknown,
        ):
            answer_frame = None
            answer_carrier_unknown = True

        # Validate every carrier frame against the persisted INTENT and
        # (for answers) the admitted non-historical ANSWER_AVAILABLE
        # event. Reject the body entirely on any mismatch; the row's
        # blocker becomes ``CARRIER_INTEGRITY`` and no part of the
        # rejected frame reaches the read result, blocker, log, or
        # exception.
        reserved_answer = _non_historical_answer_event(
            self.runtime, consultation_ref
        )
        validated_question = _validated_question_frame(
            intent.payload, question_frame
        )
        validated_answer = _validated_answer_frame(
            intent.payload, reserved_answer, answer_frame
        )

        question_body, question_blocker = _build_question_body(
            question_frame, validated_question is not None
        )
        answer_body, answer_blocker = _build_answer_body(
            answer_frame, reserved_answer, validated_answer is not None
        )

        body_status, body_blocker = _body_status_for(
            question_body, answer_body, question_blocker, answer_blocker
        )

        result = dict(row)
        result["question"] = question_body
        result["answer"] = answer_body
        result["body_status"] = body_status
        if question_carrier_unknown or answer_carrier_unknown:
            if question_carrier_unknown:
                result["question"] = None
            if answer_carrier_unknown:
                result["answer"] = None
            result["body_status"] = "UNAVAILABLE"
            result["carrier_blocker"] = "CARRIER_RECONCILIATION_REQUIRED"
            if row.get("blocker") is None:
                result["blocker"] = "CARRIER_RECONCILIATION_REQUIRED"
        elif body_blocker is not None:
            result["blocker"] = body_blocker
        elif row.get("blocker") is None:
            result["blocker"] = None

        if _canonical_size(result) > _BODY_BUDGET_BYTES:
            digest_only = dict(row)
            digest_only["question"] = None
            digest_only["answer"] = None
            digest_only["body_status"] = "UNAVAILABLE"
            digest_only["blocker"] = "BODY_OVER_BUDGET"
            return {"ok": True, "result": digest_only}

        return {"ok": True, "result": result}

    def inbox_projection(self) -> dict[str, Any]:
        """Return the full inbox projection for the caller. Read-only."""
        return project_company_inbox(
            self.runtime,
            actor={
                "job_id": self.caller.job_id,
                "attempt_id": self.caller.attempt_id,
                "worker_id": self.caller.worker_id,
            },
            now=self._clock(),
        )


# ---------------------------------------------------------------------------
# Helpers (module-private)
# ---------------------------------------------------------------------------


def _committed_consult_result(
    *,
    consultation_id: str,
    valid_until: str,
    carrier_ref: str,
    intent_inserted: bool,
    attention_requested: bool | None,
    wake_state: str | None,
    blocker: str | None,
) -> dict[str, Any]:
    """Build the closed-shape ``company.consult`` result envelope.

    Committed INTENT facts are never dropped because a downstream step
    (carrier write, wake creation, wake state read) failed. The
    ``blocker`` is the closed-set recovery label a caller or operator
    reads to understand which seam needs reconciliation.
    ``attention_requested`` is tri-state: ``True`` = the exact
    ``WAKE_REQUESTED`` record exists on the ledger, ``False`` = proven
    absent, ``None`` = unknown (ledger readback unavailable or
    conflicting; reconciliation required).
    """
    return {
        "schema": _INBOX_SCHEMA,
        "consultation_ref": consultation_id,
        "consultation_id": consultation_id,
        "state": "ALREADY_INTENDED" if not intent_inserted else "INTENDED",
        "intended": intent_inserted,
        "is_already_intended": not intent_inserted,
        "attention_requested": attention_requested,
        "wake_state": wake_state,
        "deadline": valid_until,
        "carrier_ref": carrier_ref,
        "blocker": blocker,
    }


def _semantic_answer_digest(frame: Mapping[str, Any]) -> str:
    answer = frame.get("answer")
    if not isinstance(answer, Mapping):
        return ""
    try:
        parsed = json.loads(str(answer.get("text", "")))
    except (TypeError, json.JSONDecodeError):
        return ""
    if not isinstance(parsed, Mapping):
        return ""
    return hashlib.sha256(
        canonical_consultation_json(parsed).encode("utf-8")
    ).hexdigest()


def _normalized_actor_ref(actor_ref: Mapping[str, Any]) -> dict[str, str]:
    actor = dict(actor_ref)
    job_id = actor.get("job_id")
    attempt_id = actor.get("attempt_id")
    worker_id = actor.get("worker_id")
    if not (
        isinstance(job_id, str)
        and isinstance(attempt_id, str)
        and isinstance(worker_id, str)
    ):
        raise KeyError(
            "recipient actor_ref requires job_id, attempt_id, worker_id"
        )
    if not (job_id and attempt_id and worker_id):
        raise KeyError(
            "recipient actor_ref requires non-empty job_id, attempt_id, worker_id"
        )
    return {
        "kind": str(actor.get("kind", "worker_attempt")),
        "job_id": job_id,
        "attempt_id": attempt_id,
        "worker_id": worker_id,
    }


def _correlation_digests(
    requester: Mapping[str, Any], recipient: Mapping[str, Any]
) -> tuple[str, str]:
    return (
        _sha64(dict(requester)),
        _sha64(dict(recipient)),
    )


def _build_question_frame(
    *,
    caller: CallerIdentity,
    requester_actor_ref: Mapping[str, Any],
    recipient_actor_ref: Mapping[str, Any],
    recipient_peer_ref: str,
    recipient_binding: Mapping[str, Any],
    correlation: Mapping[str, Any],
    question_text: str,
    evidence_refs: list[str],
    artifact_revisions: list[dict[str, str]],
    message_key: str,
    consultation_id: str,
    valid_until: str,
    deadline_ms: int,
    response_budget: Mapping[str, Any],
) -> dict[str, Any]:
    raw: dict[str, Any] = {
        "schema": _consultation_schema_for(caller.reasoning_surface),
        "message_key": message_key,
        "consultation_id": consultation_id,
        "purpose": "QUESTION",
        "requester_actor_ref": dict(requester_actor_ref),
        "recipient_actor_ref": dict(recipient_actor_ref),
        "recipient_peer_ref": recipient_peer_ref,
        "recipient_binding": dict(recipient_binding),
        "correlation": dict(correlation),
        "question": question_text,
        "answer": None,
        "evidence_refs": list(evidence_refs),
        "artifact_revisions": list(artifact_revisions),
        "valid_until": valid_until,
        "deadline_ms": int(deadline_ms),
        "response_budget": dict(response_budget),
        "supersedes_message_key": None,
        "receipts": {key: None for key in RECEIPT_KEYS},
        "fingerprint": "",
    }
    return build_consultation(raw)


def _build_answer_frame(
    question_frame: Mapping[str, Any],
    *,
    answer_text: str,
    evidence_refs: list[str],
    supersedes: Any,
) -> dict[str, Any]:
    semantic_answer = {"text": answer_text, "evidence_refs": list(evidence_refs)}
    semantic_answer_text = json.dumps(
        semantic_answer, sort_keys=True, separators=(",", ":")
    )
    raw_answer_digest_payload = {
        "text": semantic_answer_text,
        "evidence_refs": list(evidence_refs),
    }
    sem_answer_digest = hashlib.sha256(
        canonical_consultation_json(raw_answer_digest_payload).encode("utf-8")
    ).hexdigest()
    message_key_digest = hashlib.sha256(
        ("asd-answer-" + sem_answer_digest).encode("utf-8")
    ).hexdigest()
    message_key = f"asd-consultation-{message_key_digest[:16]}"

    raw = {
        "schema": CONSULTATION_V2_SCHEMA,
        "message_key": message_key,
        "consultation_id": question_frame["consultation_id"],
        "purpose": "ANSWER",
        "requester_actor_ref": dict(question_frame["requester_actor_ref"]),
        "recipient_actor_ref": dict(question_frame["recipient_actor_ref"]),
        "recipient_peer_ref": question_frame["recipient_peer_ref"],
        "recipient_binding": dict(question_frame["recipient_binding"]),
        "correlation": {
            **dict(question_frame["correlation"]),
            "request_message_key": question_frame["message_key"],
        },
        "question": None,
        "answer": raw_answer_digest_payload,
        "evidence_refs": list(evidence_refs),
        "artifact_revisions": list(question_frame["artifact_revisions"]),
        "valid_until": question_frame["valid_until"],
        "deadline_ms": int(question_frame["deadline_ms"]),
        "response_budget": dict(question_frame["response_budget"]),
        "supersedes_message_key": supersedes,
        "question_message_key": question_frame["message_key"],
        "receipts": {key: None for key in RECEIPT_KEYS},
        "fingerprint": "",
    }
    return build_consultation(raw)


def _build_question_body(
    question_frame: Mapping[str, Any] | None,
    is_validated: bool,
) -> tuple[dict[str, Any] | None, str | None]:
    """Return ``(body, blocker)``.

    ``is_validated`` is the result of ``_validated_question_frame`` against
    the persisted INTENT. Three cases:

    * Validated frame with a string ``question`` → body + no blocker.
    * Frame present but fails any validation check → body withheld,
      blocker ``CARRIER_INTEGRITY`` (the frame is corrupted relative to
      the persisted INTENT).
    * No frame on the carrier → body withheld, blocker
      ``CARRIER_UNAVAILABLE`` (the carrier never received the question).
    """
    if question_frame is None:
        return (None, "CARRIER_UNAVAILABLE")
    if not is_validated:
        return (None, "CARRIER_INTEGRITY")
    question = question_frame.get("question")
    if not isinstance(question, str):
        return (None, "CARRIER_INTEGRITY")
    return (
        {
            "text": question,
            "evidence_refs": list(question_frame.get("evidence_refs", [])),
        },
        None,
    )


def _build_answer_body(
    answer_frame: Mapping[str, Any] | None,
    reserved_event: Any | None,
    is_validated: bool,
) -> tuple[dict[str, Any] | None, str | None]:
    """Return ``(body, blocker)``.

    Four cases:

    * No admitted non-historical ``ANSWER_AVAILABLE`` → body not yet
      available, blocker ``CARRIER_UNAVAILABLE``.
    * Admitted ``ANSWER_AVAILABLE`` but the carrier has no ANSWER frame
      → body withheld, blocker ``CARRIER_UNAVAILABLE`` (the carrier
      never received the answer; the lost-write barrier on the reply
      path is the recovery seam).
    * Frame present but fails ``_validated_answer_frame`` (or the frame
      has no parseable answer text) → body withheld, blocker
      ``CARRIER_INTEGRITY`` (the frame is corrupted relative to the
      admitted ``ANSWER_AVAILABLE``).
    * Validated frame → body with the recipient's original text +
      evidence_refs.
    """
    if reserved_event is None and answer_frame is None:
        return (None, "CARRIER_UNAVAILABLE")
    if reserved_event is None:
        return (None, "CARRIER_UNAVAILABLE")
    if answer_frame is None:
        return (None, "CARRIER_UNAVAILABLE")
    if not is_validated:
        return (None, "CARRIER_INTEGRITY")
    raw_answer = answer_frame.get("answer")
    if not isinstance(raw_answer, Mapping):
        return (None, "CARRIER_INTEGRITY")
    raw_text = raw_answer.get("text")
    if not isinstance(raw_text, str):
        return (None, "CARRIER_INTEGRITY")
    try:
        parsed = json.loads(raw_text)
    except (TypeError, json.JSONDecodeError):
        return (None, "CARRIER_INTEGRITY")
    if not isinstance(parsed, Mapping):
        return (None, "CARRIER_INTEGRITY")
    text = parsed.get("text")
    if not isinstance(text, str):
        return (None, "CARRIER_INTEGRITY")
    evidence_refs = parsed.get("evidence_refs", [])
    if not isinstance(evidence_refs, list):
        evidence_refs = []
    return ({"text": text, "evidence_refs": list(evidence_refs)}, None)


def _body_status_for(
    question_body: dict[str, Any] | None,
    answer_body: dict[str, Any] | None,
    question_blocker: str | None,
    answer_blocker: str | None,
) -> tuple[str, str | None]:
    if question_body is not None and answer_body is not None:
        return ("AVAILABLE", None)
    blocker = question_blocker or answer_blocker
    if question_body is None and answer_body is None:
        return ("UNAVAILABLE", blocker or "CARRIER_UNAVAILABLE")
    return ("PARTIAL", blocker or "CARRIER_UNAVAILABLE")


__all__ = [
    "AgentDialogueConsultationPacketCarrier",
    "CallerIdentity",
    "ConsultationPacketCarrier",
    "ConsultationPacketCarrierUnknown",
    "ConsultationPacketCommitAborted",
    "ConsultationPacketEffectUnknown",
    "ConsultationRefusal",
    "InMemoryConsultationPacketCarrier",
    "InvocationContext",
    "InvocationContextSource",
    "NoSuchRecipient",
    "PRODUCTION_PACKET_CARRIAGE",
    "REFUSAL_CODES",
    "RecipientBinding",
    "RecipientResolver",
    "RuntimeConsultationDispatcher",
]