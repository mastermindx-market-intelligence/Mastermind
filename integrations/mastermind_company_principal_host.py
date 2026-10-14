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
from integrations.mastermind_company_mcp.principal_adapter import (
    PrincipalCompanyDialogueGateway,
    PrincipalDialogueBindingResolver,
)
from integrations.mastermind_company_principal_runtime_fence import (
    PrincipalCommitObservation,
    PrincipalDialogueRuntimeCommitOwner,
)
from integrations.slack_agent_dialogue.service import call_service


ServiceCall = Callable[..., Awaitable[dict[str, Any]]]
UtcNow = Callable[[], str]


@dataclass(frozen=True)
class PrincipalCompanyDialogueHost:
    """One composed gateway plus its exact durable COMMIT owner."""

    gateway: PrincipalCompanyDialogueGateway
    commit_owner: PrincipalDialogueRuntimeCommitOwner

    async def reconcile(self, message_key: str) -> PrincipalCommitObservation:
        """Read-only same-carrier reconciliation; never authorizes a replay."""

        return await self.commit_owner.reconcile(message_key)


def build_principal_company_dialogue_host(
    *,
    runtime: Runtime,
    binding_resolver: PrincipalDialogueBindingResolver,
    socket_path: Path,
    service_call: ServiceCall = call_service,
    utc_now: UtcNow | None = None,
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

    commit_owner = PrincipalDialogueRuntimeCommitOwner(
        runtime,
        binding_resolver,
        socket_path=path,
        service_call=service_call,
    )
    gateway_kwargs: dict[str, Any] = {
        "socket_path": path,
        "before_commit": commit_owner.before_commit,
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
    return PrincipalCompanyDialogueHost(
        gateway=gateway,
        commit_owner=commit_owner,
    )


__all__ = [
    "PrincipalCompanyDialogueHost",
    "build_principal_company_dialogue_host",
]
