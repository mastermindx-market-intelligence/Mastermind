"""Compose an already authenticated principal's exact decision source.

This is a receiving-host factory, not an App frame, peer authenticator, source
route, enrollment or installed selection. It neither chooses another obligation
nor performs a send. Existing Runtime and Relay owners retain effect identity.
"""
from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

from control_plane.coo_principal_host import CooHostProvider
from control_plane.agentos_product_acceptance_basis import AgentOsProductAcceptanceBasisReader
from control_plane.executive_runtime import Runtime
from control_plane.principal_dialogue_obligation import read_principal_dialogue_obligation
from integrations.mastermind_company_mcp.adapter import DialogueBinding
from integrations.mastermind_company_principal_host import (
    PrincipalCompanyDialogueHost, build_principal_company_dialogue_host,
)
from integrations.slack_agent_dialogue.company_dialogue_runtime_binding import CooPrincipalDialogueCaller
from integrations.slack_agent_dialogue.executive_observation_client import ExecutiveDialogueObservationClient
from integrations.slack_agent_dialogue.host_local_observation import HostLocalDialogueObservationReader
from integrations.slack_agent_dialogue.principal_current_reader import _wire
from integrations.slack_agent_dialogue.principal_source_acquisition import acquire_principal_decision_source


def _detached(binding: DialogueBinding) -> DialogueBinding:
    # The canonical reducer returns MappingProxyType fields, not picklable DTOs.
    return replace(binding, actor_ref=_wire(binding.actor_ref),
        commission_ref=_wire(binding.commission_ref), applies_to=_wire(binding.applies_to))


@dataclass(frozen=True)
class _AcquiredBinding:
    binding: DialogueBinding
    guard: Callable[[], None]

    def resolve(self) -> DialogueBinding:
        self.guard()
        return _detached(self.binding)


async def build_acquired_principal_decision_host(
    *, runtime: Runtime, authority: CooHostProvider, caller: CooPrincipalDialogueCaller,
    obligation_id: str, socket_path: Path,
    observation_client: ExecutiveDialogueObservationClient | HostLocalDialogueObservationReader,
    receiving_request_guard: Callable[[], None],
    product_acceptance_reader: AgentOsProductAcceptanceBasisReader | None = None,
) -> PrincipalCompanyDialogueHost:
    """Acquire once and select the existing fresh RULING effect composition.

    The actual App peer and current service binding must already be authenticated
    by the receiving service. Its mandatory synchronous request guard must check
    that exact peer, current service binding and admission state. It is supplied
    by host composition, never decoded from a request. Observations grant no installed
    capability. Original uncertain effects retain the existing Runtime owner's
    reconciliation path; rebuilding this factory is never a retry mechanism.
    """
    def require_request():
        if not callable(receiving_request_guard):
            raise ValueError("receiving principal request unavailable")
        guarded = receiving_request_guard()
        if guarded is not None:
            if inspect.iscoroutine(guarded):
                guarded.close()
            raise ValueError("receiving principal request unavailable")

    require_request()
    acquired = await acquire_principal_decision_source(
        runtime=runtime, authority=authority, caller=caller,
        obligation_id=obligation_id, socket_path=socket_path,
        observation_client=observation_client,
    )
    require_request()

    def current_principal_guard():
        require_request()
        authority.guard_dialogue(context=caller.admission_context,
            root_job_id=caller.root_job_id,
            capability_profile_digest=caller.capability_profile_digest)
        require_request()

    def current_source_guard(*, context, root_job_id, capability_profile_digest):
        # Runtime invokes this synchronously inside its sole COMMIT transaction.
        # ACK is only attention delivery; SOURCE_RESOLVED closes the source.
        require_request()
        authority.guard_dialogue(context=context, root_job_id=root_job_id,
            capability_profile_digest=capability_profile_digest)
        anchor = read_principal_dialogue_obligation(runtime,
            obligation_id=obligation_id, expected_work_ref=context.work_ref,
            expected_root_job_id=root_job_id)
        if anchor.physical_source != acquired.decision_source.physical_source:
            raise ValueError("principal decision source changed")
        require_request()

    return build_principal_company_dialogue_host(
        runtime=runtime, binding_resolver=_AcquiredBinding(
            _detached(acquired.current.binding), current_principal_guard),
        socket_path=socket_path, principal_authority_guard=current_source_guard,
        principal_decision_source=acquired.decision_source,
        product_acceptance_reader=product_acceptance_reader,
    )
