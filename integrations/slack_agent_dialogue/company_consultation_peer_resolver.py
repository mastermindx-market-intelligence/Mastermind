"""Pure current-program peer resolver for the Company consultation facet."""
from __future__ import annotations

import dataclasses
import re
from collections.abc import Mapping, Sequence
from typing import Any

from common.agent_dialogue_consultation_contract import (
    consultation_schema_for_reasoning_surface,
)
from common.agent_dialogue_contract import DialogueContractError
from integrations.slack_agent_dialogue.company_dialogue_runtime_binding import (
    BindingReason,
    BindingState,
    CompanyDialogueBindingResolution,
    CurrentWorkerDialogueSnapshot,
    WorkerDialogueCaller,
    resolve_company_dialogue_binding,
)


class ConsultationPeerRefused(RuntimeError):
    """A typed peer-resolution refusal."""

    def __init__(self, code: str, data: Any = None) -> None:
        if code not in {"UNAVAILABLE", "AMBIGUOUS", "BINDING_UNAVAILABLE"}:
            raise ValueError("unknown consultation peer refusal code")
        self.code = code
        self.data = data
        super().__init__(code)


@dataclasses.dataclass(frozen=True)
class ConsultationPeer:
    peer_ref: str
    display_name: str
    program_ref: str
    actor_ref: Mapping[str, Any]
    binding: Mapping[str, Any]

    @property
    def consultation_schema(self) -> str:
        surface = (
            self.binding.get("reasoning_surface")
            if isinstance(self.binding, Mapping)
            else None
        )
        try:
            return consultation_schema_for_reasoning_surface(surface)
        except DialogueContractError:
            raise ConsultationPeerRefused("BINDING_UNAVAILABLE") from None

    def public_projection(self) -> dict[str, str]:
        return {"peer_ref": self.peer_ref, "display_name": self.display_name}


@dataclasses.dataclass(frozen=True)
class CompanyConsultationPeerResolver:
    """Resolve exact same-program peers supplied by a trusted host fixture.

    W6-C2 will connect this protocol to Runtime lookup.  The public functions in
    the forbidden Runtime owner remain the intended adapter boundary; no caller
    identity is accepted here.
    """

    peers: Sequence[ConsultationPeer]
    expected_actor_ref: Mapping[str, Any] | None = None
    expected_binding: Mapping[str, Any] | None = None

    def resolve(self, alias: str, *, program_ref: str) -> ConsultationPeer:
        alias = alias.strip().lower()
        matches = [
            peer
            for peer in self.peers
            if peer.program_ref == program_ref
            and (
                peer.peer_ref.lower() == alias
                or peer.display_name.strip().lower() == alias
                or peer.actor_ref.get("worker_id", "").lower() == alias
            )
        ]
        if not matches:
            raise ConsultationPeerRefused("UNAVAILABLE")
        if len({peer.peer_ref for peer in matches}) > 1:
            raise ConsultationPeerRefused(
                "AMBIGUOUS",
                {"peers": [peer.public_projection() for peer in matches]},
            )
        peer = matches[0]
        self._validate(peer)
        if self.expected_actor_ref is not None and dict(peer.actor_ref) != dict(self.expected_actor_ref):
            raise ConsultationPeerRefused("BINDING_UNAVAILABLE")
        if self.expected_binding is not None and dict(peer.binding) != dict(self.expected_binding):
            raise ConsultationPeerRefused("BINDING_UNAVAILABLE")
        return peer

    def current_program(self, *, root_job_id: str, operation_key: str) -> str:
        if not isinstance(root_job_id, str) or not isinstance(operation_key, str):
            raise ConsultationPeerRefused("BINDING_UNAVAILABLE")
        return f"{root_job_id}/{operation_key}"

    @staticmethod
    def _validate(peer: ConsultationPeer) -> None:
        if not isinstance(peer.peer_ref, str) or re.fullmatch(
            r"peer-[0-9a-f]{32}", peer.peer_ref
        ) is None:
            raise ConsultationPeerRefused("BINDING_UNAVAILABLE")
        actor = peer.actor_ref
        if not isinstance(actor, Mapping) or actor.get("kind") != "worker_attempt":
            raise ConsultationPeerRefused("BINDING_UNAVAILABLE")
        binding = peer.binding
        if (
            not isinstance(binding, Mapping)
            or set(binding) != {"binding_id", "binding_generation", "reasoning_surface"}
            or re.fullmatch(r"bind-[A-Za-z0-9][A-Za-z0-9._:-]{7,127}", str(binding.get("binding_id"))) is None
            or type(binding.get("binding_generation")) is not int
            or binding.get("binding_generation") < 1
        ):
            raise ConsultationPeerRefused("BINDING_UNAVAILABLE")
        try:
            consultation_schema_for_reasoning_surface(
                binding.get("reasoning_surface")
            )
        except DialogueContractError:
            raise ConsultationPeerRefused("BINDING_UNAVAILABLE") from None


@dataclasses.dataclass(frozen=True)
class CompanyConsultationPeerResolution:
    schema: str
    state: BindingState
    reason: BindingReason
    peer: ConsultationPeer | None
    evidence_digest: str


def peer_from_company_dialogue(
    *,
    peer_ref: str,
    display_name: str,
    program_ref: str,
    delegation_identity: Any,
    dialogue_parent: Mapping[str, Any],
    thread_ts: str,
    current: CurrentWorkerDialogueSnapshot | None,
    actor: WorkerDialogueCaller,
) -> CompanyConsultationPeerResolution:
    """Derive a peer through the existing exact current-worker resolver."""

    resolution: CompanyDialogueBindingResolution = resolve_company_dialogue_binding(
        delegation_identity=delegation_identity,
        dialogue_parent=dialogue_parent,
        thread_ts=thread_ts,
        current=current,
        actor=actor,
    )
    if resolution.state is not BindingState.RESOLVED or resolution.binding is None:
        return CompanyConsultationPeerResolution(
            schema="mastermind.company_consultation_peer.v1",
            state=resolution.state,
            reason=resolution.reason,
            peer=None,
            evidence_digest=resolution.evidence_digest,
        )
    binding = resolution.binding
    runtime = getattr(current, "runtime_binding", None)
    public_binding = {
        "binding_id": runtime.binding_id,
        "binding_generation": runtime.binding_generation,
        "reasoning_surface": runtime.reasoning_surface,
    }
    peer = ConsultationPeer(
        peer_ref=peer_ref,
        display_name=display_name,
        program_ref=program_ref,
        actor_ref=dict(binding.actor_ref),
        binding=public_binding,
    )
    CompanyConsultationPeerResolver(
        [peer],
        expected_actor_ref=dict(binding.actor_ref),
        expected_binding=public_binding,
    ).resolve(peer_ref, program_ref=program_ref)
    return CompanyConsultationPeerResolution(
        schema="mastermind.company_consultation_peer.v1",
        state=BindingState.RESOLVED,
        reason=BindingReason.EXACT_CURRENT_WORKER,
        peer=peer,
        evidence_digest=resolution.evidence_digest,
    )
__all__ = [
    "CompanyConsultationPeerResolver",
    "ConsultationPeer",
    "ConsultationPeerRefused",
    "peer_from_company_dialogue",
]
