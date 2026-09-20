"""Stateless current-binding resolver for Workspace Agent candidate return.

This adapter reuses the existing Agent Relay parent-discovery seam and Executive
dialogue observation authority. It owns no registry, cache, cursor, lifecycle
state, credential, retry loop, or alternate source of current-target truth.
"""
from __future__ import annotations

from typing import Any, Mapping, Protocol

from control_plane.executive_dialogue_observation import ACTIVE_CURRENT_WORKER
from integrations.mastermind_company_mcp.adapter import DialogueBinding
from integrations.slack_agent_dialogue.company_dialogue_runtime_binding import (
    CompanyDialogueBindingError,
    require_company_dialogue_binding,
)
from integrations.slack_agent_dialogue.engine_v2 import DiscoveredDialogueParent
from integrations.slack_agent_dialogue.executive_observation_client import (
    ExecutiveObservationClientError,
    ResolvedDialogueObservation,
)

MAX_DISCOVERED_PARENTS = 64


class WorkspaceCurrentBindingError(RuntimeError):
    """Fixed refusal for missing, stale, ambiguous, or untrusted current state."""

    def __init__(self) -> None:
        super().__init__("BINDING_UNAVAILABLE")
        self.code = "BINDING_UNAVAILABLE"


class WorkspaceParentDiscovery(Protocol):
    async def discover_validated_parents(
        self, *, maximum: int
    ) -> tuple[DiscoveredDialogueParent, ...]: ...


class WorkspaceExecutiveObservation(Protocol):
    async def resolve(
        self,
        *,
        parent: Mapping[str, Any],
        thread_ts: str,
    ) -> ResolvedDialogueObservation: ...


def _operation_token(value: object) -> str:
    if (
        type(value) is not str
        or not 1 <= len(value) <= 128
        or not value.isascii()
        or value != value.strip()
        or any(ord(char) < 33 or ord(char) > 126 for char in value)
    ):
        raise WorkspaceCurrentBindingError()
    return value


class WorkspaceOperationBindingResolver:
    """Re-derive one current DialogueBinding from existing canonical owners."""

    def __init__(
        self,
        *,
        parent_discovery: WorkspaceParentDiscovery,
        executive_observation: WorkspaceExecutiveObservation,
    ) -> None:
        if not callable(getattr(parent_discovery, "discover_validated_parents", None)):
            raise TypeError("parent_discovery must expose discover_validated_parents")
        if not callable(getattr(executive_observation, "resolve", None)):
            raise TypeError("executive_observation must expose resolve")
        self._parent_discovery = parent_discovery
        self._executive_observation = executive_observation

    async def resolve(self, operation_key: str) -> DialogueBinding:
        operation = _operation_token(operation_key)
        try:
            discovered = await self._parent_discovery.discover_validated_parents(
                maximum=MAX_DISCOVERED_PARENTS
            )
        except Exception:
            raise WorkspaceCurrentBindingError() from None
        if not isinstance(discovered, tuple):
            raise WorkspaceCurrentBindingError()

        matches = [
            item
            for item in discovered
            if (
                isinstance(item, DiscoveredDialogueParent)
                and isinstance(item.parent, Mapping)
                and item.parent.get("operation_key") == operation
            )
        ]
        if len(matches) != 1:
            raise WorkspaceCurrentBindingError()
        selected = matches[0]

        try:
            observation = await self._executive_observation.resolve(
                parent=selected.parent,
                thread_ts=selected.thread_ts,
            )
        except ExecutiveObservationClientError:
            raise WorkspaceCurrentBindingError() from None
        except Exception:
            raise WorkspaceCurrentBindingError() from None

        if (
            not isinstance(observation, ResolvedDialogueObservation)
            or observation.state != "RESOLVED"
            or observation.mode != ACTIVE_CURRENT_WORKER
            or observation.dialogue_parent != selected.parent
            or observation.thread_ts != selected.thread_ts
            or observation.delegation_identity.operation_key != operation
            or observation.current_worker is None
            or observation.actor is None
        ):
            raise WorkspaceCurrentBindingError()

        try:
            binding = require_company_dialogue_binding(
                delegation_identity=observation.delegation_identity,
                dialogue_parent=selected.parent,
                thread_ts=selected.thread_ts,
                current=observation.current_worker,
                actor=observation.actor,
            )
        except CompanyDialogueBindingError:
            raise WorkspaceCurrentBindingError() from None
        except Exception:
            raise WorkspaceCurrentBindingError() from None

        if (
            not isinstance(binding, DialogueBinding)
            or binding.operation_key != operation
            or binding.thread_ts != selected.thread_ts
        ):
            raise WorkspaceCurrentBindingError()
        return binding


__all__ = [
    "MAX_DISCOVERED_PARENTS",
    "WorkspaceCurrentBindingError",
    "WorkspaceExecutiveObservation",
    "WorkspaceOperationBindingResolver",
    "WorkspaceParentDiscovery",
]
