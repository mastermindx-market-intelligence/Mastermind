"""Request-local project binding for the Mastermind Context MCP port.

This layer composes authenticated caller identity with an EXISTING deployment-owned
project binding. It creates no project registry, root mapping, source custody, auth
scope, lifecycle, or persistence. Deployment handlers close over their already-approved
owner configuration; the model receives no host path or credential.
"""

from __future__ import annotations

import dataclasses
import inspect
import re
from collections.abc import Awaitable, Callable, Mapping
from types import MappingProxyType
from typing import Any

from .contracts import TOOL_NAMES
from .model import ContextCaller, ContextPortRefused

_GENERATION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,255}$")
_REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_OPERATION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$")


@dataclasses.dataclass(frozen=True)
class ContextProjectBinding:
    """Projection of one existing owner decision; never a persisted grant."""

    caller: ContextCaller
    project_ref: str
    generation: str
    repositories: tuple[str, ...]
    workspace_operations: tuple[str, ...]
    tools: tuple[str, ...]


BindingResolver = Callable[[ContextCaller, str], ContextProjectBinding | None]
ContextHandler = Callable[
    [ContextCaller, ContextProjectBinding, Mapping[str, Any]],
    Awaitable[Mapping[str, Any]],
]
Clock = Callable[[], int]


def _binding(
    value: object,
    *,
    caller: ContextCaller,
    project_ref: str,
    tool_name: str,
    now_ms: int,
) -> ContextProjectBinding:
    if type(value) is not ContextProjectBinding:
        raise ContextPortRefused()
    if value.caller != caller or value.project_ref != project_ref:
        raise ContextPortRefused("CONTEXT_BINDING_CHANGED")
    if (
        type(now_ms) is not int
        or isinstance(now_ms, bool)
        or now_ms < 0
        or type(caller.expires_at) is not int
        or caller.expires_at * 1000 <= now_ms
    ):
        raise ContextPortRefused("CONTEXT_BINDING_CHANGED")
    if (
        type(value.generation) is not str
        or _GENERATION_RE.fullmatch(value.generation) is None
    ):
        raise ContextPortRefused()
    if (
        type(value.repositories) is not tuple
        or len(value.repositories) > 32
        or len(value.repositories) != len(set(value.repositories))
        or any(
            type(item) is not str or _REPOSITORY_RE.fullmatch(item) is None
            for item in value.repositories
        )
    ):
        raise ContextPortRefused()
    if (
        type(value.workspace_operations) is not tuple
        or len(value.workspace_operations) > 64
        or len(value.workspace_operations) != len(set(value.workspace_operations))
        or any(
            type(item) is not str or _OPERATION_RE.fullmatch(item) is None
            for item in value.workspace_operations
        )
    ):
        raise ContextPortRefused()
    if (
        type(value.tools) is not tuple
        or not value.tools
        or len(value.tools) != len(set(value.tools))
        or any(item not in TOOL_NAMES for item in value.tools)
        or tool_name not in value.tools
    ):
        raise ContextPortRefused()
    return ContextProjectBinding(
        caller=caller,
        project_ref=project_ref,
        generation=value.generation,
        repositories=tuple(sorted(value.repositories)),
        workspace_operations=tuple(sorted(value.workspace_operations)),
        tools=tuple(sorted(value.tools)),
    )


def _request_scope(
    binding: ContextProjectBinding,
    tool_name: str,
    request: Mapping[str, Any],
) -> None:
    if tool_name == "atlas_search":
        repository = request.get("repository")
        if repository not in binding.repositories:
            raise ContextPortRefused()
    elif tool_name == "workspace_overlay":
        operation_id = request.get("operation_id")
        if operation_id not in binding.workspace_operations:
            raise ContextPortRefused()


def create_context_port_bundle(
    *,
    resolve_binding: BindingResolver,
    handlers: Mapping[str, ContextHandler],
    clock_ms: Clock,
) -> tuple[
    Callable[
        [ContextCaller, str, Mapping[str, Any]],
        Awaitable[Mapping[str, Any]],
    ],
    Callable[
        [ContextCaller, str, Mapping[str, Any]],
        Callable[[], None],
    ],
]:
    """Build the app port and its final-authorization factory from one owner seam."""

    if not callable(resolve_binding) or not callable(clock_ms):
        raise TypeError("explicit binding resolver and clock required")
    if not isinstance(handlers, Mapping) or set(handlers) != set(TOOL_NAMES):
        raise TypeError("exact Context MCP handler set required")
    if any(not callable(handler) for handler in handlers.values()):
        raise TypeError("all Context MCP handlers must be callable")

    def resolve_current(
        caller: ContextCaller,
        tool_name: str,
        request: Mapping[str, Any],
    ) -> ContextProjectBinding:
        if type(caller) is not ContextCaller:
            raise ContextPortRefused()
        if caller.scopes != ("workbench.read",) or any(
            type(getattr(caller, name)) is not str
            for name in ("subject_digest", "client_ref", "resource")
        ):
            raise ContextPortRefused()
        project_ref = request.get("project_ref")
        if type(project_ref) is not str:
            raise ContextPortRefused()
        try:
            now = clock_ms()
            raw = resolve_binding(caller, project_ref)
        except ContextPortRefused:
            raise
        except Exception:
            raise ContextPortRefused() from None
        selected = _binding(
            raw,
            caller=caller,
            project_ref=project_ref,
            tool_name=tool_name,
            now_ms=now,
        )
        _request_scope(selected, tool_name, request)
        return selected

    async def context_port(
        caller: ContextCaller,
        tool_name: str,
        request: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        if tool_name not in handlers:
            raise ContextPortRefused()
        selected_request = MappingProxyType(dict(request))
        original = resolve_current(caller, tool_name, selected_request)
        try:
            pending = handlers[tool_name](caller, original, selected_request)
            if not inspect.isawaitable(pending):
                raise ContextPortRefused("CONTEXT_UNAVAILABLE")
            observed = await pending
        except ContextPortRefused:
            raise
        except Exception:
            raise ContextPortRefused("CONTEXT_UNAVAILABLE") from None
        current = resolve_current(caller, tool_name, selected_request)
        if current != original:
            raise ContextPortRefused("CONTEXT_BINDING_CHANGED")
        if not isinstance(observed, Mapping):
            raise ContextPortRefused("CONTEXT_UNAVAILABLE")
        result = dict(observed)
        if result.get("project_ref") != original.project_ref:
            raise ContextPortRefused("CONTEXT_SOURCE_CHANGED")
        return result

    def final_authorization(
        caller: ContextCaller,
        tool_name: str,
        request: Mapping[str, Any],
    ) -> Callable[[], None]:
        selected_request = MappingProxyType(dict(request))
        original = resolve_current(caller, tool_name, selected_request)

        def revalidate() -> None:
            current = resolve_current(caller, tool_name, selected_request)
            if current != original:
                raise ContextPortRefused("CONTEXT_BINDING_CHANGED")
            return None

        return revalidate

    return context_port, final_authorization
