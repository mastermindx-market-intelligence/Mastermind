"""Join an authenticated principal's exact Relay source to current Runtime facts.

This read-only composition uses the incumbent observation client and binding
reducer. It authenticates no caller, selects no replacement child or source,
and authorizes no send. A returned observation is not a lease: the host must
repeat its current-source and unresolved-request checks at the existing COMMIT
boundary. Foreground composition does not require a new Wake delivery.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from control_plane.dialogue_source_resolution import (
    PhysicalDialogueSourceIdentity, parse_source_candidate,
)
from control_plane.coo_principal_mandate import NewEffectGate
from control_plane.executive_dialogue_observation import ACTIVE_CURRENT_WORKER, DialogueCandidateReference
from integrations.mastermind_company_mcp.adapter import DialogueBinding
from integrations.slack_agent_dialogue.company_dialogue_runtime_binding import (
    CooPrincipalDialogueCaller,
    require_company_dialogue_principal_binding,
)
from integrations.slack_agent_dialogue.contract_v2 import validate_message_v2
from integrations.slack_agent_dialogue.engine_v2 import DialogueContextV2
from integrations.slack_agent_dialogue.executive_observation_client import (
    ResolvedDialogueObservation,
)
from integrations.slack_agent_dialogue.principal_source_reader import (
    PrincipalSourceRead,
    read_principal_source,
)
from integrations.slack_agent_dialogue.service import call_service


class PrincipalCurrentSourceUnavailable(RuntimeError):
    def __init__(self) -> None:
        super().__init__("PRINCIPAL_CURRENT_SOURCE_UNAVAILABLE")


@dataclass(frozen=True)
class PrincipalCurrentSourceRead:
    source: PrincipalSourceRead
    observation: ResolvedDialogueObservation
    binding: DialogueBinding


def _wire(value: Any) -> Any:
    """Detach immutable Relay snapshots into the existing JSON contract shape."""
    if isinstance(value, Mapping):
        return {key: _wire(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_wire(item) for item in value]
    return value


async def read_current_principal_source(
    *, caller: CooPrincipalDialogueCaller, context: DialogueContextV2,
    physical_source: PhysicalDialogueSourceIdentity, socket_path: Path,
    observation_client: Any, service_call=call_service,
) -> PrincipalCurrentSourceRead:
    """Read only the original physical source and its exact current child.

    Caller/context come from trusted host composition after request admission.
    The physical identity must be acquired from its canonical source owner;
    constructing a DTO is never a grant. The selected observation reader uses
    either the authenticated Relay socket exchange or the Control service's
    existing host-local Runtime snapshot. Both share the canonical reducer and
    closed decoder. No global mission enumeration or timestamp selection occurs.
    """
    try:
        if (type(caller) is not CooPrincipalDialogueCaller
                or type(context) is not DialogueContextV2
                or type(physical_source) is not PhysicalDialogueSourceIdentity):
            raise PrincipalCurrentSourceUnavailable()
        normalized = context.normalized()
        admission = caller.admission_context
        expected_actor = {"kind": "executive_principal", "seat": "coo",
            "reasoning_surface": caller.reasoning_surface,
            "principal_binding_digest": admission.principal_binding_digest,
            "mission_authority_ref": admission.mission_authority_ref,
            "authority_generation_digest": admission.authority_generation_digest,
            "capability_profile_digest": caller.capability_profile_digest,
            "root_job_id": caller.root_job_id}
        if (caller.new_effect_gate is not NewEffectGate.OPEN
                or caller.accountable_seat != "coo" or caller.owed_seat != "coo"
                or normalized["actor_ref"] != expected_actor
                or normalized["work_ref"] != admission.work_ref
                or physical_source.candidate.root_job_id != caller.root_job_id):
            raise PrincipalCurrentSourceUnavailable()
        source = await read_principal_source(socket_path=socket_path,
            context=context, physical_source=physical_source, service_call=service_call)
        parent = _wire(source.parent)
        observed = await observation_client.resolve(parent=parent, thread_ts=source.thread_ts)
        if (type(observed) is not ResolvedDialogueObservation
                or observed.state != "RESOLVED"
                or observed.mode != ACTIVE_CURRENT_WORKER
                or observed.current_worker is None
                or observed.dialogue_parent != parent
                or observed.thread_ts != source.thread_ts
                or type(observed.candidate) is not DialogueCandidateReference
                or observed.candidate.mode != observed.mode
                or parse_source_candidate(observed.candidate.to_dict()) != physical_source.candidate):
            raise PrincipalCurrentSourceUnavailable()
        current = observed.current_worker
        predecessor = validate_message_v2(_wire(source.predecessor.message))
        worker = {"job_id": current.job_id, "attempt_id": current.attempt_id,
                  "worker_id": current.worker_id}
        if (predecessor["actor_ref"] != {"kind": "worker_attempt", **worker}
                or predecessor["applies_to"] != {"kind": "executive_attempt", **worker}):
            raise PrincipalCurrentSourceUnavailable()
        binding = require_company_dialogue_principal_binding(
            delegation_identity=observed.delegation_identity, dialogue_parent=parent,
            thread_ts=source.thread_ts, current=current, actor=caller,
            reply_to_message_key=predecessor["message_key"])
        # The supplied Relay read context must be exactly the resolved actor and
        # target, not another authorized principal or old child epoch.
        if (normalized["actor_ref"] != dict(binding.actor_ref)
                or normalized["applies_to"] != dict(binding.applies_to)):
            raise PrincipalCurrentSourceUnavailable()
        return PrincipalCurrentSourceRead(source, observed, binding)
    except Exception:
        raise PrincipalCurrentSourceUnavailable() from None
