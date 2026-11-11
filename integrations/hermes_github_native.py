"""Native Hermes mmx_github tool, registered by the incumbent plugin owner.

No model-supplied repository, app identity, token, role or session binding.
An installed host must supply one current session resolver and return the lease.
Source import by itself registers nothing and enables no GitHub write.
"""
from __future__ import annotations

import asyncio
import inspect
import json
from dataclasses import dataclass
from typing import Any, Callable

from integrations.hermes_harness.native_tool_registration import (
    NativeToolRegistrationError as _NativeRegistrationError,
    _ctx_profile_name, _ctx_scope, _loading_mode_refusal, _registry,
)
from integrations.hermes_github_app import (
    HermesGitHubApp, HostGitHubSession, GitHubBotEffectUnknown,
    GitHubBotRefused, GitHubBotUnavailable, SCHEMA,
)

TOOL_NAME = "mmx_github"
TOOLSET = "mmx_github"
TOOL_SCHEMA = {
    "name": TOOL_NAME,
    "description": (
        "Act via the host-scoped GitHub App for this exact Hermes operation. "
        "Create your bound branch, commit one allowed source file with an "
        "expected head, create its PR, or comment on a host-granted issue/PR. "
        "Never retry an EFFECT_UNKNOWN action."
    ),
    "parameters": {
        "type": "object",
        "additionalProperties": False,
        "required": ["action"],
        "properties": {
            "action": {"type": "string", "enum": [
                "status", "branch_create", "file_commit", "pr_create",
                "comment_find", "comment_create",
            ]},
            "expected_head": {"type": "string"},
            "path": {"type": "string"},
            "content": {"type": "string"},
            "message": {"type": "string"},
            "title": {"type": "string"},
            "body": {"type": "string"},
            "issue_number": {"type": "integer", "minimum": 1},
            "request_id": {"type": "string"},
        },
    },
}
_WRITES = frozenset(("branch_create", "file_commit", "pr_create", "comment_create"))


class NativeToolRegistrationError(_NativeRegistrationError):
    def __init__(self, code: str, **origin):
        super().__init__(code, **origin)
        if self.original_context is not None:
            self.original_tool_name = TOOL_NAME


def _current(check: Callable[[], bool]) -> bool:
    try:
        value = check()
        if inspect.iscoroutine(value):
            value.close()
            return False
        return value is True
    except Exception:
        return False


@dataclass(frozen=True)
class HostHermesGitHubBinding:
    """Session mapping stays in the existing native host context."""

    profile_id: str
    resolve_client: Callable[[str], HermesGitHubApp | None]
    currentness_guard: Callable[[], bool]

    def __post_init__(self) -> None:
        if (not isinstance(self.profile_id, str) or not self.profile_id
                or not callable(self.resolve_client)
                or inspect.iscoroutinefunction(self.resolve_client)
                or not callable(self.currentness_guard)
                or inspect.iscoroutinefunction(self.currentness_guard)):
            raise NativeToolRegistrationError("GITHUB_NATIVE_BINDING_INVALID")

    def is_current(self) -> bool:
        return _current(self.currentness_guard)

    def resolve(self, session_id: Any) -> HermesGitHubApp | None:
        if type(session_id) is not str or not 0 < len(session_id) <= 128:
            return None
        try:
            client = self.resolve_client(session_id)
            if inspect.iscoroutine(client):
                client.close()
                return None
            if (isinstance(client, HermesGitHubApp)
                    and isinstance(client.binding, HostGitHubSession)
                    and client.binding.session_id == session_id
                    and client.binding.profile_id == self.profile_id):
                return client
        except Exception:
            pass
        return None


def native_handler(binding: HostHermesGitHubBinding, *,
                   native_current: Callable[[], bool] | None = None):
    if not isinstance(binding, HostHermesGitHubBinding):
        raise NativeToolRegistrationError("GITHUB_NATIVE_BINDING_INVALID")
    check = native_current if native_current is not None else binding.is_current

    async def handle(arguments: Any, *, session_id: Any = None,
                     task_id: Any = None) -> str:
        action = arguments.get("action") if isinstance(arguments, dict) else None
        if (type(arguments) is not dict
                or task_id is not None and task_id != session_id):
            result = {"schema": SCHEMA, "state": "REFUSED",
                      "reason": "GITHUB_NATIVE_ARGUMENTS_REFUSED"}
        elif not _current(check):
            result = {"schema": SCHEMA, "state": "REFUSED",
                      "reason": "GITHUB_NATIVE_NOT_CURRENT"}
        else:
            client = binding.resolve(session_id)
            if client is None:
                result = {"schema": SCHEMA, "state": "REFUSED",
                          "reason": "GITHUB_NATIVE_SESSION_NOT_BOUND"}
            else:
                try:
                    result = await asyncio.to_thread(client.perform, arguments)
                except GitHubBotRefused as error:
                    result = {"schema": SCHEMA, "state": "REFUSED",
                              "reason": str(error)}
                except GitHubBotUnavailable as error:
                    result = {"schema": SCHEMA, "state": "UNAVAILABLE",
                              "reason": str(error)}
                except GitHubBotEffectUnknown as error:
                    result = {"schema": SCHEMA, "state": "EFFECT_UNKNOWN",
                              "reason": str(error),
                              "operation": client.binding.operation_id}
                except Exception:
                    result = {"schema": SCHEMA, "state": (
                        "EFFECT_UNKNOWN" if action in _WRITES else "UNAVAILABLE"),
                        "reason": "GITHUB_NATIVE_UNEXPECTED_FAILURE",
                        "operation": client.binding.operation_id}
                if (not _current(check)
                        or binding.resolve(session_id) is not client):
                    result = {"schema": SCHEMA, "state": (
                        "EFFECT_UNKNOWN" if action in _WRITES else "UNAVAILABLE"),
                        "reason": "GITHUB_NATIVE_BINDING_CHANGED",
                        "operation": client.binding.operation_id}
        return json.dumps(result, ensure_ascii=False,
                          allow_nan=False, separators=(",", ":"))
    return handle


@dataclass(frozen=True)
class NativeGitHubRegistration:
    handler: Callable
    check_fn: Callable
    handle: Any
    entry: Any
    scope: str
    _live: dict

    def dispose(self) -> None:
        self._live["active"] = False
        self.handle.dispose()


def register_native_tool(ctx: Any, binding: HostHermesGitHubBinding, *,
                         profile_id: str) -> NativeGitHubRegistration:
    """Exactly one native owner lease; fail closed on collision or uncertain write."""
    if not isinstance(binding, HostHermesGitHubBinding) or not binding.is_current():
        raise NativeToolRegistrationError("GITHUB_NATIVE_BINDING_INVALID")
    if not callable(getattr(ctx, "register_tool", None)):
        raise NativeToolRegistrationError("GITHUB_NATIVE_CONTEXT_INVALID")
    refusal = _loading_mode_refusal(ctx)
    if refusal:
        raise NativeToolRegistrationError(refusal)
    scope = _ctx_scope(ctx)
    if (type(profile_id) is not str or not profile_id
            or _ctx_profile_name(ctx) != profile_id
            or binding.profile_id != profile_id):
        raise NativeToolRegistrationError("GITHUB_NATIVE_PROFILE_MISMATCH")
    registry = _registry()
    try:
        from registration_lifecycle import replacement_coordinator
    except Exception:
        raise NativeToolRegistrationError("GITHUB_NATIVE_API_UNAVAILABLE") from None
    live = {"entry": None, "active": False}

    def current() -> bool:
        return (live["active"]
                and _ctx_scope(ctx) == scope
                and _ctx_profile_name(ctx) == profile_id
                and registry.snapshot_registration(TOOL_NAME, scope=scope)
                    is live["entry"]
                and binding.is_current())

    handler = native_handler(binding, native_current=current)
    check_fn = lambda: _current(current)
    with replacement_coordinator.transaction():
        if registry.snapshot_registration(TOOL_NAME, scope=scope) is not None:
            raise NativeToolRegistrationError("GITHUB_NATIVE_COLLISION")
        if registry.get_entry(TOOL_NAME, scope=scope) is not None:
            raise NativeToolRegistrationError("GITHUB_NATIVE_NAME_TAKEN")
        try:
            handle = ctx.register_tool(
                name=TOOL_NAME, toolset=TOOLSET, schema=TOOL_SCHEMA,
                handler=handler, check_fn=check_fn, is_async=True,
                description=TOOL_SCHEMA["description"], emoji="github",
            )
        except Exception:
            raise NativeToolRegistrationError(
                "GITHUB_NATIVE_REGISTRATION_EFFECT_UNKNOWN",
                context=ctx, binding=binding, scope=scope,
            ) from None
        if handle is None:
            code = ("GITHUB_NATIVE_NOT_REGISTERED"
                    if registry.snapshot_registration(TOOL_NAME, scope=scope) is None
                    else "GITHUB_NATIVE_REGISTRATION_EFFECT_UNKNOWN")
            raise NativeToolRegistrationError(
                code, context=ctx, binding=binding, scope=scope,
            )
        try:
            entry = registry.snapshot_registration(TOOL_NAME, scope=scope)
            if (entry is None or entry.handler is not handler
                    or entry.check_fn is not check_fn
                    or entry.schema != TOOL_SCHEMA or entry.toolset != TOOLSET
                    or entry.is_async is not True):
                raise ValueError("GITHUB_NATIVE_READBACK_MISMATCH")
        except Exception:
            try:
                handle.dispose()
            except Exception:
                raise NativeToolRegistrationError(
                    "GITHUB_NATIVE_ROLLBACK_EFFECT_UNKNOWN",
                    context=ctx, binding=binding, scope=scope, handle=handle,
                ) from None
            raise NativeToolRegistrationError("GITHUB_NATIVE_READBACK_MISMATCH") from None
        live.update(entry=entry, active=True)
        return NativeGitHubRegistration(
            handler, check_fn, handle, entry, scope, live,
        )
