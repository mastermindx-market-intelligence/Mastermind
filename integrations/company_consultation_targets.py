"""Exact-target consultation carriage over the existing Agent Relay service.

A caller's current DialogueBinding proves who is speaking, not where a packet
belongs. The injected host resolver supplies destination and party facts from
existing Executive/Consultation/Wake owners. Neither target objects nor their
evidence digests confer permission or constitute Company Dialogue grants.

This source-only seam installs nothing. It has no route cache, peer registry,
persistence, retry loop, socket server, or model-facing routing fields. The
canonical target resolver is a separate read-only host adapter; production
composition remains gated. Historical reads resolve the admitted exact parties;
resolver implementations must never substitute a peer's newer current session.
"""
from __future__ import annotations

import dataclasses
import re
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType
from typing import Any, Protocol

from common.agent_dialogue_consultation_contract import (
    canonical_consultation_json,
    validate_consultation,
)
from control_plane.executive_runtime import StateConflict
from integrations.company_consultation_dispatch import (
    AgentDialogueConsultationPacketCarrier,
    ConsultationPacketCarrierUnknown,
    PacketCommitHook,
    ServiceCall,
    _dialogue_carrier_identity,
)
from integrations.mastermind_company_mcp.adapter import (
    DialogueBinding,
    DialogueBindingResolver,
)
from integrations.slack_agent_dialogue.engine_v2 import DialogueContextV2
from integrations.slack_agent_dialogue.service import (
    CONTROL_VERSION_V2,
    EXACT_SEND_PROTOCOL,
    call_service,
)

# Closed set of Relay engine codes that name a deterministic destination
# conflict. The service returns these verbatim in an error envelope on both
# the send and read edges, including after COMMIT, because they are engine
# codes rather than service ``ERROR_CODES``.
_DESTINATION_REFUSAL_CODES = frozenset(
    {"THREAD_BINDING_AMBIGUOUS", "THREAD_CONTEXT_MISMATCH"}
)

_ACTOR_KEYS = frozenset({"kind", "job_id", "attempt_id", "worker_id"})
_CONSULTATION_ID = re.compile(r"\Aconsult-[0-9a-f]{32}\Z")
_THREAD_TS = re.compile(r"\A[0-9]{10,16}\.[0-9]{6}\Z")
_DIGEST = re.compile(r"\A[0-9a-f]{64}\Z")


def _actor(value: Mapping[str, Any]) -> Mapping[str, str]:
    if (
        not isinstance(value, Mapping)
        or set(value) != _ACTOR_KEYS
        or value.get("kind") != "worker_attempt"
        or any(not isinstance(value[key], str) or not value[key] for key in _ACTOR_KEYS)
    ):
        raise StateConflict("exact consultation actor is unavailable")
    return MappingProxyType(dict(value))


class ConsultationTargetConflict(StateConflict):
    """Deterministic target adjudication: missing, ambiguous, foreign or sticky.

    A ``StateConflict`` subtype so every incumbent handler keeps working. It
    exists so a closed owner adjudication is never mistaken for a carrier
    outage and retried or re-resolved onto a different parent.
    """


class ConsultationTargetEvidenceUnavailable(ConsultationPacketCarrierUnknown):
    """Owner evidence could not be observed; the target is NOT re-resolvable.

    A ``ConsultationPacketCarrierUnknown`` subtype: genuine observation
    uncertainty must never become a safe refusal. It is typed only so a
    consumer can tell unreadable owner evidence from a dead transport and
    reconcile on the same target instead of choosing a new one.
    """


@dataclasses.dataclass(frozen=True)
class ConsultationDeliveryTarget:
    """Immutable physical destination facts, deliberately not a send grant."""

    actor_ref: Mapping[str, Any]
    work_ref: str
    commission_ref: Mapping[str, Any]
    session_ref: str
    operation_key: str
    watch_mode: str | None
    thread_ts: str
    evidence_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "actor_ref", _actor(self.actor_ref))
        if (
            not isinstance(self.thread_ts, str)
            or _THREAD_TS.fullmatch(self.thread_ts) is None
            or not isinstance(self.evidence_digest, str)
            or _DIGEST.fullmatch(self.evidence_digest) is None
        ):
            raise StateConflict("exact consultation destination is invalid")
        try:
            normalized = self.context()
        except Exception:
            raise StateConflict("exact consultation destination is invalid") from None
        # The incumbent commission contract is closed and scalar-valued.
        object.__setattr__(
            self, "commission_ref", MappingProxyType(dict(normalized["commission_ref"]))
        )

    def context(self) -> dict[str, Any]:
        applies_to = dict(self.actor_ref)
        applies_to["kind"] = "executive_attempt"
        return DialogueContextV2(
            work_ref=self.work_ref,
            commission_ref=dict(self.commission_ref),
            session_ref=self.session_ref,
            operation_key=self.operation_key,
            watch_mode=self.watch_mode,
            actor_ref=dict(self.actor_ref),
            applies_to=applies_to,
        ).normalized()


@dataclasses.dataclass(frozen=True)
class ConsultationPacketAccess:
    """Exact destination plus admitted parties, reconstructed by the host."""

    target: ConsultationDeliveryTarget
    requester_actor_ref: Mapping[str, Any]
    recipient_actor_ref: Mapping[str, Any]

    def __post_init__(self) -> None:
        if not isinstance(self.target, ConsultationDeliveryTarget):
            raise StateConflict("exact consultation destination is unavailable")
        object.__setattr__(self, "requester_actor_ref", _actor(self.requester_actor_ref))
        object.__setattr__(self, "recipient_actor_ref", _actor(self.recipient_actor_ref))
        if self.requester_actor_ref == self.recipient_actor_ref:
            raise StateConflict("consultation parties must be distinct")


class ConsultationPacketTargetResolver(Protocol):
    """Trusted exact-fact reader; never a model-supplied target or route store.

    ``frame`` is supplied only for a validated send or pre-INTENT QUESTION
    lookup. Existing INTENT facts take precedence when present. With no frame,
    party facts must already be recoverable from the canonical consultation.
    Missing/ambiguous/changed facts raise; they must not become packet absence.
    """

    def resolve(
        self,
        consultation_id: str,
        *,
        purpose: str,
        frame: Mapping[str, Any] | None = None,
    ) -> ConsultationPacketAccess: ...


class TargetedAgentDialogueConsultationPacketCarrier(AgentDialogueConsultationPacketCarrier):
    """Keep sender authority and destination separate without remembering routes.

    The legacy carrier and public Company MCP schemas are unchanged. Host
    composition must explicitly opt into this carrier after qualifying its
    exact-target resolver and the existing consultation capability policy.
    """

    supports_targeted_delivery = True

    def __init__(
        self,
        *,
        binding_resolver: DialogueBindingResolver,
        targets: ConsultationPacketTargetResolver,
        socket_path: Path,
        service_call: ServiceCall = call_service,
        timeout_seconds: float = 30.0,
    ) -> None:
        if not callable(getattr(targets, "resolve", None)):
            raise TypeError("targets must resolve exact packet access")
        super().__init__(
            binding_resolver=binding_resolver,
            socket_path=socket_path,
            service_call=service_call,
            timeout_seconds=timeout_seconds,
        )
        self._targets = targets

    @staticmethod
    def _identity(consultation_id: str, purpose: str) -> None:
        if (
            not isinstance(consultation_id, str)
            or _CONSULTATION_ID.fullmatch(consultation_id) is None
            or purpose not in ("QUESTION", "ANSWER")
        ):
            raise StateConflict("consultation packet identity is invalid")

    @staticmethod
    def _caller_snapshot(binding: DialogueBinding) -> str:
        _dialogue_carrier_identity(binding)
        return canonical_consultation_json({
            "context": AgentDialogueConsultationPacketCarrier._context(binding),
            "thread_ts": binding.thread_ts,
            "allowed_message_types": list(binding.allowed_message_types),
            "reply_to_message_key": binding.reply_to_message_key,
        })

    @staticmethod
    def _access_snapshot(access: ConsultationPacketAccess) -> str:
        return canonical_consultation_json({
            "context": access.target.context(),
            "thread_ts": access.target.thread_ts,
            "evidence_digest": access.target.evidence_digest,
            "requester_actor_ref": dict(access.requester_actor_ref),
            "recipient_actor_ref": dict(access.recipient_actor_ref),
        })

    def _access(
        self,
        consultation_id: str,
        *,
        purpose: str,
        frame: Mapping[str, Any] | None,
        sender_required: bool,
    ) -> tuple[ConsultationPacketAccess, tuple[str, str]]:
        self._identity(consultation_id, purpose)
        binding = self._binding()
        caller_snapshot = self._caller_snapshot(binding)
        # A destination never grants authority to act as the other party.
        if sender_required and (
            frame is None or dict(binding.actor_ref) != dict(self._sender_actor(frame))
        ):
            raise StateConflict("current dialogue binding is not the packet sender")
        try:
            access = self._targets.resolve(
                consultation_id, purpose=purpose, frame=frame,
            )
        except StateConflict:
            raise
        except ConsultationPacketCarrierUnknown:
            # Keep the resolver's closed classification; re-wrapping here would
            # erase the owner-evidence distinction it just established.
            raise
        except Exception:
            raise ConsultationPacketCarrierUnknown(
                "exact consultation target facts are unavailable"
            ) from None
        if not isinstance(access, ConsultationPacketAccess):
            raise ConsultationPacketCarrierUnknown("exact consultation access is invalid")
        parties = (dict(access.requester_actor_ref), dict(access.recipient_actor_ref))
        if dict(binding.actor_ref) not in parties:
            raise StateConflict("current dialogue binding is not a packet party")
        destination = parties[1 if purpose == "QUESTION" else 0]
        if dict(access.target.actor_ref) != destination:
            raise StateConflict("consultation target actor disagrees with destination")
        if frame is not None and (
            dict(frame["requester_actor_ref"]) != parties[0]
            or dict(frame["recipient_actor_ref"]) != parties[1]
        ):
            raise StateConflict("consultation target parties disagree with packet")
        return access, (caller_snapshot, self._access_snapshot(access))

    def _fence(
        self,
        expected: tuple[str, str],
        consultation_id: str,
        *,
        purpose: str,
        frame: Mapping[str, Any] | None,
        sender_required: bool,
    ) -> None:
        _, current = self._access(
            consultation_id, purpose=purpose, frame=frame,
            sender_required=sender_required,
        )
        if current != expected:
            raise StateConflict("consultation identity changed before effect or readback")

    @staticmethod
    def _destination_refusal(response: Any) -> str | None:
        """Name a deterministic destination refusal in a Relay error envelope."""
        if not isinstance(response, Mapping) or response.get("ok") is not False:
            return None
        error = response.get("error")
        if not isinstance(error, Mapping) or set(error) != {"code"}:
            return None
        code = error.get("code")
        if not isinstance(code, str) or code not in _DESTINATION_REFUSAL_CODES:
            return None
        return code

    def _refuse_inconsistent_destination(self, response: Any) -> None:
        code = self._destination_refusal(response)
        if code is None:
            return
        raise ConsultationTargetConflict(
            "Agent Relay refused the consultation packet destination: " + code
        )

    async def _put(
        self,
        consultation_id: str,
        frame: Mapping[str, Any],
        *,
        purpose: str,
        before_commit: PacketCommitHook,
    ) -> None:
        item = validate_consultation(frame)
        if item["consultation_id"] != consultation_id or item["purpose"] != purpose:
            raise StateConflict("consultation packet identity disagrees")
        access, snapshot = self._access(
            consultation_id, purpose=purpose, frame=item, sender_required=True,
        )

        async def commit_gate() -> None:
            # READY is not COMMIT. Revalidate before and after the owner's
            # awaited Runtime INTENT/ANSWER_AVAILABLE admission callback.
            self._fence(snapshot, consultation_id, purpose=purpose,
                        frame=item, sender_required=True)
            await before_commit()
            self._fence(snapshot, consultation_id, purpose=purpose,
                        frame=item, sender_required=True)

        response = await self._call({
            "version": CONTROL_VERSION_V2,
            "operation": "send_consultation_packet",
            "args": {
                "context": access.target.context(),
                "thread_ts": access.target.thread_ts,
                "message": item,
                "send_protocol": EXACT_SEND_PROTOCOL,
            },
        }, before_write=commit_gate)
        # The transport is reporting that the destination this carrier supplied
        # was internally inconsistent. That is deterministic, not an outage, and
        # must not degrade into one that a caller may retry or re-resolve.
        self._refuse_inconsistent_destination(response)
        result = response.get("result") if isinstance(response, Mapping) else None
        if (
            not isinstance(response, Mapping)
            or response.get("ok") is not True
            or not isinstance(result, Mapping)
            or result.get("message_key") != item["message_key"]
            or result.get("fingerprint") != item["fingerprint"]
            or result.get("thread_ts") != access.target.thread_ts
        ):
            raise ConsultationPacketCarrierUnknown("Agent Relay packet receipt is invalid")

    async def _get_targeted(
        self,
        consultation_id: str,
        *,
        purpose: str,
        frame: Mapping[str, Any] | None = None,
    ) -> Mapping[str, Any] | None:
        access, snapshot = self._access(
            consultation_id, purpose=purpose, frame=frame,
            sender_required=frame is not None,
        )
        response = await self._call({
            "version": CONTROL_VERSION_V2,
            "operation": "read_consultation_packet",
            "args": {
                "context": access.target.context(),
                "thread_ts": access.target.thread_ts,
                "consultation_id": consultation_id,
                "purpose": purpose,
            },
        })
        # Suppress even absence if the exact caller/target changed during I/O.
        self._fence(snapshot, consultation_id, purpose=purpose, frame=frame,
                    sender_required=frame is not None)
        # Fence first, then classify: identity drift outranks a stale refusal.
        self._refuse_inconsistent_destination(response)
        if not isinstance(response, Mapping) or response.get("ok") is not True:
            raise ConsultationPacketCarrierUnknown("Agent Relay packet read is invalid")
        result = response.get("result")
        if result is None:
            return None
        if not isinstance(result, Mapping) or set(result) != {
            "packet", "primary_ts", "duplicate_timestamps",
        }:
            raise ConsultationPacketCarrierUnknown("Agent Relay packet read is invalid")
        try:
            item = validate_consultation(result["packet"])
        except Exception:
            raise ConsultationPacketCarrierUnknown("Agent Relay packet read is invalid") from None
        if (
            item["consultation_id"] != consultation_id
            or item["purpose"] != purpose
            or result["duplicate_timestamps"] != []
            or dict(item["requester_actor_ref"]) != dict(access.requester_actor_ref)
            or dict(item["recipient_actor_ref"]) != dict(access.recipient_actor_ref)
        ):
            raise ConsultationPacketCarrierUnknown("Agent Relay packet read is conflicting")
        return item

    async def _get(self, consultation_id: str, *, purpose: str) -> Mapping[str, Any] | None:
        return await self._get_targeted(consultation_id, purpose=purpose)

    async def get_question_for(self, frame: Mapping[str, Any]) -> Mapping[str, Any] | None:
        """Pre-INTENT lookup using a validated candidate, without caching it."""
        item = validate_consultation(frame)
        if item["purpose"] != "QUESTION":
            raise StateConflict("pre-INTENT packet lookup requires a QUESTION")
        return await self._get_targeted(
            item["consultation_id"], purpose="QUESTION", frame=item,
        )
