"""Host composition for the source-only COO-principal Company Dialogue facet.

This module wires the existing principal gateway to the existing Executive
Runtime event-backed COMMIT fence. It creates no capability grant, principal
identity, Runtime lifecycle, server registration, listener, transport, queue,
retry owner, or provider selection.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable

from control_plane.executive_runtime import Runtime
from integrations.mastermind_company_mcp.adapter import (
    CompanyDialogueGateway,
    DialogueBindingResolver,
)
from control_plane.agentos_product_acceptance_basis import (
    AgentOsProductAcceptanceBasisReader,
)
from integrations.product_acceptance_request_owner import ProductAcceptanceRequestOwner
from integrations.mastermind_company_mcp.principal_adapter import (
    PrincipalCompanyDialogueGateway,
    PrincipalDialogueBindingResolver,
)
from integrations.mastermind_company_principal_runtime_fence import (
    PrincipalCommitObservation,
    PrincipalDialogueRuntimeCommitOwner,
)
from integrations.slack_agent_dialogue.service import call_service
from integrations.slack_agent_dialogue.principal_decision_source_fence import (
    PrincipalDecisionSource, PrincipalDecisionSourceFence,
)

ServiceCall = Callable[..., Awaitable[dict[str, Any]]]
UtcNow = Callable[[], str]


@dataclass(frozen=True)
class PrincipalCompanyDialogueHost:
    """One composed gateway plus its exact durable COMMIT owner."""

    gateway: PrincipalCompanyDialogueGateway
    commit_owner: PrincipalDialogueRuntimeCommitOwner
    request_gateway: CompanyDialogueGateway | None = None
    request_owner: ProductAcceptanceRequestOwner | None = None

    async def reconcile(self, message_key: str) -> PrincipalCommitObservation:
        """Read-only same-carrier reconciliation; never authorizes a replay."""

        return await self.commit_owner.reconcile(message_key)

    def observe_product_acceptance(self, message_key: str) -> dict[str, Any]:
        """Read the exact original return for an existing host/Office consumer.

        This adds no model tool or public listener. The host must explicitly
        compose the acceptance owners; the ordinary host remains unchanged.
        """
        if self.request_owner is None or self.request_owner.ruling_owner is None:
            raise ValueError("product acceptance is not composed for this host")
        return self.request_owner.ruling_owner.observe_acceptance(message_key)


def build_principal_company_dialogue_host(
    *,
    runtime: Runtime,
    binding_resolver: PrincipalDialogueBindingResolver,
    socket_path: Path,
    service_call: ServiceCall = call_service,
    utc_now: UtcNow | None = None,
    principal_authority_guard: Callable[..., None] | None = None,
    request_binding_resolver: DialogueBindingResolver | None = None,
    product_acceptance_macro_root: Path | None = None,
    product_acceptance_reader: AgentOsProductAcceptanceBasisReader | None = None,
    principal_decision_source: PrincipalDecisionSource | None = None,
) -> PrincipalCompanyDialogueHost:
    """Compose existing H6 owners without admitting or starting a principal.

    The caller must supply an already-current binding resolver and exact Runtime.
    This factory does not choose a principal, child, provider, account, session,
    route, profile, or authorization generation.
    """

    path = Path(socket_path)
    if not path.is_absolute():
        raise ValueError("socket_path must be absolute")
    if type(runtime) is not Runtime:
        raise TypeError("runtime must be the exact Executive Runtime owner")
    if not callable(service_call):
        raise TypeError("service_call must be callable")

    if (request_binding_resolver is None) != (product_acceptance_macro_root is None):
        raise ValueError(
            "product acceptance requires both its source root and assigning-parent resolver"
        )
    if product_acceptance_reader is not None and (
        type(product_acceptance_reader) is not AgentOsProductAcceptanceBasisReader
        or product_acceptance_macro_root is not None
    ):
        raise TypeError("product acceptance requires one exact host-owned reader")
    if principal_decision_source is not None and principal_authority_guard is None:
        raise ValueError("decision source requires the receiving principal authority guard")

    commit_owner = PrincipalDialogueRuntimeCommitOwner(
        runtime,
        binding_resolver,
        socket_path=path,
        service_call=service_call,
        principal_authority_guard=principal_authority_guard,
    )
    gateway_kwargs: dict[str, Any] = {
        "socket_path": path,
        "before_commit": (commit_owner.before_commit if principal_decision_source is None
            else PrincipalDecisionSourceFence(principal_decision_source, commit_owner).before_commit),
        "service_call": service_call,
    }
    if utc_now is not None:
        if not callable(utc_now):
            raise TypeError("utc_now must be callable")
        gateway_kwargs["utc_now"] = utc_now

    gateway = PrincipalCompanyDialogueGateway(
        binding_resolver,
        **gateway_kwargs,
    )
    request_gateway = request_owner = None
    if request_binding_resolver is not None or product_acceptance_reader is not None:
        request_owner = ProductAcceptanceRequestOwner(
            runtime,
            product_acceptance_reader if product_acceptance_reader is not None else AgentOsProductAcceptanceBasisReader(
                macro_root=product_acceptance_macro_root
            ),
            principal_owner=commit_owner,
        )
    if request_binding_resolver is not None:
        request_gateway = CompanyDialogueGateway(
            request_binding_resolver,
            socket_path=path,
            service_call=service_call,
            product_acceptance_owner=request_owner,
            **({"utc_now": utc_now} if utc_now is not None else {}),
        )
    return PrincipalCompanyDialogueHost(
        gateway=gateway,
        commit_owner=commit_owner,
        request_gateway=request_gateway,
        request_owner=request_owner,
    )


__all__ = [
    "PrincipalCompanyDialogueHost",
    "build_principal_company_dialogue_host",
]
