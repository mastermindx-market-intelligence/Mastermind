"""Acquire one principal decision from canonical Wake and Runtime owners.

Only an already authenticated host may call this reader. It creates no App
frame, principal route, grant, write or reusable authority lease. In particular,
a CEO-targeted obligation does not become a COO-principal obligation here.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from control_plane.coo_principal_host import CooHostProvider
from control_plane.coo_principal_mandate import NewEffectGate
from control_plane.executive_delegation_identity import derive_delegation_identity
from control_plane.executive_runtime import Runtime, _dialogue_source_from_root_creation
from control_plane.principal_dialogue_obligation import read_principal_dialogue_obligation
from integrations.slack_agent_dialogue.company_dialogue_runtime_binding import CooPrincipalDialogueCaller
from integrations.slack_agent_dialogue.engine_v2 import DialogueContextV2
from integrations.slack_agent_dialogue.executive_observation_client import ExecutiveDialogueObservationClient
from integrations.slack_agent_dialogue.host_local_observation import HostLocalDialogueObservationReader
from integrations.slack_agent_dialogue.principal_current_reader import PrincipalCurrentSourceRead, read_current_principal_source
from integrations.slack_agent_dialogue.principal_decision_source_fence import PrincipalDecisionSource
from integrations.slack_agent_dialogue.principal_pending_decision import require_unanswered_principal_decision


class PrincipalSourceAcquisitionUnavailable(RuntimeError):
    def __init__(self) -> None:
        super().__init__("PRINCIPAL_SOURCE_ACQUISITION_UNAVAILABLE")


@dataclass(frozen=True)
class AcquiredPrincipalDecision:
    """Detached observations for the existing host; not a send authorization."""

    decision_source: PrincipalDecisionSource
    current: PrincipalCurrentSourceRead


def _canonical_context(runtime, caller, obligation_id):
    anchor = read_principal_dialogue_obligation(runtime,
        obligation_id=obligation_id,
        expected_work_ref=caller.admission_context.work_ref,
        expected_root_job_id=caller.root_job_id)
    candidate = anchor.physical_source.candidate
    if candidate.mode != "ACTIVE_CURRENT_WORKER":
        raise PrincipalSourceAcquisitionUnavailable()
    child = runtime.jobs.get_job(candidate.job_id)
    if (child is None or child.root_job_id != caller.root_job_id
            or child.current_attempt_id != candidate.attempt_id):
        raise PrincipalSourceAcquisitionUnavailable()
    attempt = runtime.attempts.get_attempt(candidate.attempt_id)
    if (attempt is None or attempt.job_id != child.job_id
            or attempt.worker_id != candidate.worker_id):
        raise PrincipalSourceAcquisitionUnavailable()
    identity = derive_delegation_identity(child)
    if (identity.root_job_id != caller.root_job_id
            or identity.operation_key != anchor.physical_source.operation_key):
        raise PrincipalSourceAcquisitionUnavailable()
    with runtime.store.read() as connection:
        source = _dialogue_source_from_root_creation(connection, root_job_id=caller.root_job_id)
    if source is None or source.work_ref != caller.admission_context.work_ref:
        raise PrincipalSourceAcquisitionUnavailable()
    admission = caller.admission_context
    context = DialogueContextV2(
        work_ref=source.work_ref, commission_ref=MappingProxyType(source.to_dict()["commission_ref"]),
        watch_mode=source.watch_mode, session_ref=identity.session_ref,
        operation_key=identity.operation_key,
        actor_ref=MappingProxyType({"kind": "executive_principal", "seat": "coo",
            "reasoning_surface": caller.reasoning_surface, "root_job_id": caller.root_job_id,
            "principal_binding_digest": admission.principal_binding_digest,
            "mission_authority_ref": admission.mission_authority_ref,
            "authority_generation_digest": admission.authority_generation_digest,
            "capability_profile_digest": caller.capability_profile_digest}),
        applies_to=MappingProxyType({"kind": "executive_attempt", "job_id": candidate.job_id,
            "attempt_id": candidate.attempt_id, "worker_id": candidate.worker_id}),
    )
    context.normalized()
    return anchor, context


async def acquire_principal_decision_source(
    *, runtime: Runtime, authority: CooHostProvider, caller: CooPrincipalDialogueCaller,
    obligation_id: str, socket_path: Path,
    observation_client: ExecutiveDialogueObservationClient | HostLocalDialogueObservationReader,
) -> AcquiredPrincipalDecision:
    """Derive inputs from one exact obligation, then re-read after source I/O.

    Authentication and kernel-peer admission remain with the host. No caller
    supplied physical/context DTO is accepted. The final effect must still use
    the existing fresh source fence and Runtime COMMIT owner; these reads are
    not an atomic cross-service snapshot and cannot reserve a decision.
    """
    try:
        if (type(runtime) is not Runtime or type(authority) is not CooHostProvider
                or type(caller) is not CooPrincipalDialogueCaller
                or type(observation_client) not in (ExecutiveDialogueObservationClient, HostLocalDialogueObservationReader)
                or (type(observation_client) is HostLocalDialogueObservationReader
                    and observation_client.runtime is not runtime)
                or caller.new_effect_gate is not NewEffectGate.OPEN
                or caller.accountable_seat != "coo" or caller.owed_seat != "coo"):
            raise PrincipalSourceAcquisitionUnavailable()

        def guard():
            authority.guard_dialogue(context=caller.admission_context,
                root_job_id=caller.root_job_id,
                capability_profile_digest=caller.capability_profile_digest)

        guard()
        before, context = _canonical_context(runtime, caller, obligation_id)
        current = await read_current_principal_source(caller=caller, context=context,
            physical_source=before.physical_source, socket_path=socket_path,
            observation_client=observation_client)
        require_unanswered_principal_decision(current)
        # No awaits after this comparison; still an observation, never a lease.
        after, current_context = _canonical_context(runtime, caller, obligation_id)
        if before != after or context.normalized() != current_context.normalized():
            raise PrincipalSourceAcquisitionUnavailable()
        guard()
        return AcquiredPrincipalDecision(
            PrincipalDecisionSource(caller, context, before.physical_source, observation_client), current)
    except Exception:
        raise PrincipalSourceAcquisitionUnavailable() from None
