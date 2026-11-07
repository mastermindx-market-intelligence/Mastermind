"""Native Hermes plugin adapter for the closed selected-child delegation tool.

Native Hermes owns its plugins: the loader calls ``register(ctx)`` with
one :class:`hermes_cli.plugins.PluginContext`, and ``ctx.register_tool`` owns
the installed entry, its profile scope and its unload. This module is the
adapter behind that owner. It registers exactly one tool, ``mmx_delegate``, and
publishes only the closed selected-child request shape.

The module owns no transport, no listener, no credential, no principal and no
selected child. The authenticated Executive transport, the currentness guard
and the frozen native target arrive from the host as one immutable
:class:`NativeDelegateBinding`, and the *same* binding object is captured by
the handler and by the availability probe. There is no replaceable
process-global binding: the handler holds the binding it was registered with,
so a later binding cannot retarget a live handler, and two registrations never
share a command, a root or a transport.

Two states stay distinct. A refusal decided before the transport is called is a
proved no-effect. Anything after a possible send - a timeout, an exception, an
unparsable or mismatched return - is uncertain: the original command identity
is kept and the state is ``EFFECT_UNKNOWN`` (submit) or ``UNAVAILABLE``
(status). Nothing is retried, cancelled or moved to another carrier.

This is a source adapter. It opens no listener, mints no token, imports no
mutable source through the environment, changes no installed runtime, and does
not clear ``NATIVE_EXTENSION_NOT_INSTALLED``.
"""
from __future__ import annotations

import inspect
import json
import os
import re
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Protocol, runtime_checkable

from integrations.hermes_delegate.policy import TOOL_NAME, TOOLSET_NAME
from integrations.hermes_delegate.schema import (
    COMMAND_RE,
    SELECTED_CHILD_ACTIONS,
    SubmissionError,
    parse_selected_child,
)

__all__ = [
    "NATIVE_TOOL_SCHEMA",
    "NativeDelegateBinding",
    "NativeDelegateRegistration",
    "NativeDelegateStartup",
    "NativeDelegateTransport",
    "NativeToolRegistrationError",
    "SELECTED_CHILD_SCHEMA",
    "SELECTED_CHILD_STATES",
    "SUPPORTED_LOADING_MODE",
    "TOOL_NAME",
    "TOOLSET_NAME",
    "native_delegate_check_fn",
    "native_delegate_handler",
    "register_native_delegate_tool",
    "register_native_delegate_tools",
]

# The canonical envelope schema of the accepted selected-child contract. It
# mirrors integrations.hermes_delegate.executive.SELECTED_CHILD_SCHEMA; the
# focused test fails if the two drift.
SELECTED_CHILD_SCHEMA = "mastermind.hermes_delegate.selected_child/v1"

# The canonical selected-child states. Same set as the accepted contract's
# envelope projection; the focused test fails if the two drift.
SELECTED_CHILD_STATES = frozenset({
    "ACTIVE", "NOT_CLAIMED", "EFFECT_UNKNOWN", "COMPLETED", "FAILED",
    "CANCELLED", "RATE_LIMITED", "CANCEL_REQUESTED", "UNVERIFIED", "REFUSED",
    "UNAVAILABLE",
})

# States that may legitimately carry no canonical Attempt.
_ATTEMPT_OPTIONAL_STATES = frozenset({
    "NOT_CLAIMED", "EFFECT_UNKNOWN", "REFUSED", "UNAVAILABLE",
})

# States whose observation is uncertain rather than a proved no-effect.
_UNCERTAIN_STATES = frozenset({"EFFECT_UNKNOWN", "UNAVAILABLE"})

# Hermes keeps third-party plugin code in the Hermes process
# (``plugins.isolation: in_process``) or in a separate plugin-host process
# (``host``). A live transport binding cannot cross that boundary, so only the
# in-process loading mode is supported here.
SUPPORTED_LOADING_MODE = "in_process"

# The canonical command reference is
# ``coo-cycle:{root_job_id}:dispatch:{job_id}:attempt:{ordinal}``. The Job
# segment is extracted to prove that the binding's job identity and its
# command reference describe the same child.
_COMMAND_PARTS = re.compile(
    r"^coo-cycle:([^:\s]{1,128}):dispatch:([^:\s]{1,128}):attempt:([1-9][0-9]{0,9})$"
)

# The model-facing fields of the canonical envelope. The identity projections
# the contract also allows (role, operation_key, session_ref) are not part of
# the model-facing envelope and are not projected.
_MODEL_FIELDS = (
    "schema", "state", "reason", "command_id", "job_id", "attempt_id",
    "attempt_status", "job_status", "live_submit", "result_status",
    "result_envelope_digest", "terminal_evidence_digest",
)

NATIVE_TOOL_SCHEMA: dict[str, Any] = {
    "name": TOOL_NAME,
    "description": (
        "Submit or observe exactly the Executive child the authenticated host "
        "already froze, under its canonical command reference. The request "
        "carries only the action and that command. The model cannot select, "
        "create, review, consume or cancel a child, and an uncertain effect "
        "is never retried."
    ),
    "parameters": {
        "type": "object",
        "additionalProperties": False,
        "required": ["action", "command"],
        "properties": {
            "action": {"type": "string", "enum": sorted(SELECTED_CHILD_ACTIONS)},
            "command": {"type": "string"},
        },
    },
}


class NativeToolRegistrationError(RuntimeError):
    """One closed refusal code for the native registration."""

    def __init__(self, code: str, *, context=None, binding=None, scope=None, handle=None) -> None:
        super().__init__(code)
        self.code = code
        # Private original-owner references for an uncertain registration or
        # rollback. These are not a replacement registry or model response.
        self.original_context = context
        self.original_binding = binding
        self.original_scope = scope
        self.original_handle = handle
        self.original_tool_name = TOOL_NAME if context is not None else None


@runtime_checkable
class NativeDelegateTransport(Protocol):
    """The authenticated Executive transport the host already owns.

    The transport is the parent's live MCP/App/Control channel. It returns the
    canonical selected-child envelope for one command reference. It is not a
    connection this module opens, and it is never a process global.
    """

    def submit_selected_child(self, command_id: str) -> Mapping[str, Any]:
        """Send one frozen command. May raise; the caller keeps the uncertainty."""

    def selected_child_status(self, command_id: str) -> Mapping[str, Any]:
        """Read the same original command. Never resubmits."""


@dataclass(frozen=True)
class NativeDelegateBinding:
    """One immutable qualified binding: target, caller lineage and transport.

    The host supplies every field. Nothing here is derived from a role label,
    a model argument or an environment lookup.
    """

    transport: Any
    currentness_guard: Callable[[], bool]
    profile_id: str
    session_id: str
    command: str
    job_id: str
    session_key: str | None = None
    task_id: str | None = None

    def __post_init__(self) -> None:
        transport = self.transport
        if not isinstance(transport, NativeDelegateTransport):
            raise NativeToolRegistrationError("NATIVE_TRANSPORT_INVALID")
        if (not callable(self.currentness_guard)
                or inspect.iscoroutinefunction(self.currentness_guard)
                or inspect.iscoroutinefunction(getattr(self.currentness_guard, "__call__", None))):
            raise NativeToolRegistrationError("NATIVE_CURRENTNESS_GUARD_INVALID")
        for value, code in (
            (self.profile_id, "NATIVE_PROFILE_ID_INVALID"),
            (self.session_id, "NATIVE_SESSION_ID_INVALID"),
            (self.job_id, "NATIVE_JOB_ID_INVALID"),
        ):
            if not isinstance(value, str) or not 0 < len(value) <= 256:
                raise NativeToolRegistrationError(code)
        for value, code in (
            (self.session_key, "NATIVE_SESSION_KEY_INVALID"),
            (self.task_id, "NATIVE_TASK_ID_INVALID"),
        ):
            if value is not None and (not isinstance(value, str) or not 0 < len(value) <= 256):
                raise NativeToolRegistrationError(code)
        if not isinstance(self.command, str) or COMMAND_RE.fullmatch(self.command) is None:
            raise NativeToolRegistrationError("NATIVE_COMMAND_INVALID")
        parts = _COMMAND_PARTS.fullmatch(self.command)
        if parts is None or parts.group(2) != self.job_id:
            raise NativeToolRegistrationError("NATIVE_COMMAND_JOB_MISMATCH")


@dataclass(frozen=True)
class NativeDelegateStartup:
    """The one startup binding this process may register.

    The default is unbound: ``NativeDelegateStartup()`` has no binding, and a
    registration against it refuses. The host owns the instance and installs
    the binding it actually holds.
    """

    binding: NativeDelegateBinding | None = None


@dataclass(frozen=True)
class NativeDelegateRegistration:
    """The readback of one installed registration.

    ``handle`` is the upstream owner's own registration lease; disposing it
    releases the entry exactly as Hermes unload does. ``entry`` is the
    owner's installed entry, captured for the readback proof.
    """

    name: str
    toolset: str
    scope: str
    profile_id: str
    session_id: str
    command: str
    job_id: str
    handler: Callable[..., str]
    check_fn: Callable[[], bool]
    handle: Any
    entry: Any


def _bound_session_key() -> str | None:
    """The native route key bound in this context, or None when unavailable.

    Upstream ``gateway.session_context.bound_session_key`` deliberately has no
    environment fallback, so an unavailable module means "not provable", not
    "no key". No fallback is invented here either.
    """
    try:
        from gateway.session_context import bound_session_key
    except Exception:
        return None
    try:
        value = bound_session_key()
    except Exception:
        return None
    return value if isinstance(value, str) and value else None


def _caller_lineage_refusal(
    binding: NativeDelegateBinding, session_id: Any, task_id: Any,
) -> str | None:
    """Prove the live native caller is the bound session, or refuse.

    ``session_id`` and ``task_id`` arrive as the native dispatcher's own
    keyword arguments, outside the model's arguments. They are never read
    from the request body and never guessed from the environment.
    """
    if not isinstance(session_id, str) or not session_id:
        return "NATIVE_CALLER_SESSION_MISSING"
    if session_id != binding.session_id:
        return "NATIVE_CALLER_SESSION_MISMATCH"
    if binding.task_id is not None and task_id != binding.task_id:
        return "NATIVE_CALLER_TASK_MISMATCH"
    if binding.session_key is not None:
        observed = _bound_session_key()
        if observed is None:
            return "NATIVE_CALLER_SESSION_KEY_UNAVAILABLE"
        if observed != binding.session_key:
            return "NATIVE_CALLER_SESSION_KEY_MISMATCH"
    return None


def _binding_is_current(binding: NativeDelegateBinding) -> bool:
    """Re-prove the binding immediately before a possible transport write."""
    try:
        observed = binding.currentness_guard()
        if inspect.iscoroutine(observed):
            observed.close()
            return False
        # A coroutine, custom awaitable or another truthy object is not a
        # completed synchronous qualification of the current host binding.
        return observed is True
    except Exception:
        return False


def _parse_request(arguments: Any) -> tuple[dict[str, Any] | None, str | None]:
    """Return the closed request, or the closed refusal reason.

    The action is type-checked before it is compared with the closed action
    set, so an unhashable model value (a list or a dict) is refused instead of
    escaping the handler.
    """
    if not isinstance(arguments, Mapping):
        return None, "ARGUMENTS_NOT_OBJECT"
    action = arguments.get("action")
    if type(action) is not str:
        return None, "UNKNOWN_ACTION"
    try:
        request = parse_selected_child(arguments)
    except SubmissionError as exc:
        return None, exc.reason
    return request, None


def _validate_envelope(raw: Any, binding: NativeDelegateBinding) -> dict[str, Any] | None:
    """Validate the canonical envelope the transport returned.

    A return that does not describe the original command is not a proved
    no-effect: the transport may already have sent it. The caller keeps the
    uncertainty instead of projecting a false state.
    """
    body: Any = raw
    if isinstance(body, str):
        try:
            body = json.loads(body)
        except (TypeError, ValueError):
            return None
    if not isinstance(body, Mapping):
        return None
    if body.get("schema") != SELECTED_CHILD_SCHEMA:
        return None
    if body.get("command_id") != binding.command:
        return None
    if body.get("job_id") != binding.job_id:
        return None
    state = body.get("state")
    if type(state) is not str or state not in SELECTED_CHILD_STATES:
        return None
    attempt = body.get("attempt_id")
    if attempt is not None and (type(attempt) is not str or not 0 < len(attempt) <= 128):
        return None
    if state not in _ATTEMPT_OPTIONAL_STATES and attempt is None:
        return None
    expected_live = True if attempt is not None else (
        None if state in _UNCERTAIN_STATES else False
    )
    live = body.get("live_submit")
    if live is not None and type(live) is not bool:
        return None
    if live is not expected_live:
        return None
    projected: dict[str, Any] = {"schema": SELECTED_CHILD_SCHEMA}
    for field in _MODEL_FIELDS:
        if field == "schema":
            continue
        value = body.get(field)
        if field == "live_submit":
            projected[field] = expected_live
            continue
        if value is not None and (not isinstance(value, str) or len(value) > 256):
            return None
        projected[field] = value
    if "result_capsule" in body:
        from control_plane.executive_terminal_return import validate_selected_child_result_capsule
        try:
            projected["result_capsule"] = validate_selected_child_result_capsule(
                body["result_capsule"], observation=dict(body))
        except (ValueError, TypeError, KeyError):
            return None
    return projected


def _refusal(reason: str, binding: NativeDelegateBinding) -> dict[str, Any]:
    """A proved no-effect: the transport was never called."""
    return {
        "schema": SELECTED_CHILD_SCHEMA,
        "state": "REFUSED",
        "reason": reason,
        "command_id": binding.command,
        "job_id": binding.job_id,
        "attempt_id": None,
        "attempt_status": None,
        "job_status": None,
        "live_submit": False,
    }


def _uncertain(
    state: str, reason: str, binding: NativeDelegateBinding,
) -> dict[str, Any]:
    """A possible send whose effect is unknown. The original command stays."""
    return {
        "schema": SELECTED_CHILD_SCHEMA,
        "state": state,
        "reason": reason,
        "command_id": binding.command,
        "job_id": binding.job_id,
        "attempt_id": None,
        "attempt_status": None,
        "job_status": None,
        "live_submit": None,
    }


def _dump(body: Mapping[str, Any]) -> str:
    return json.dumps(body, sort_keys=True, ensure_ascii=False, default=str)


def native_delegate_handler(binding: NativeDelegateBinding) -> Callable[..., str]:
    """Build the one handler this binding may ever serve.

    The binding is captured here, once. No call path reads a module-level
    binding, so a later binding cannot retarget this handler and two
    registered handlers never exchange a command, a root or a transport.
    """
    if not isinstance(binding, NativeDelegateBinding):
        raise NativeToolRegistrationError("NATIVE_BINDING_INVALID")

    def handle(arguments: Any, *, session_id: Any = None, task_id: Any = None) -> str:
        request, refusal = _parse_request(arguments)
        if refusal is not None:
            return _dump(_refusal(refusal, binding))
        # The binding owns one frozen command. A model cannot name another.
        if request["command"] != binding.command:
            return _dump(_refusal("NATIVE_COMMAND_MISMATCH", binding))
        lineage = _caller_lineage_refusal(binding, session_id, task_id)
        if lineage is not None:
            return _dump(_refusal(lineage, binding))
        if not _binding_is_current(binding):
            return _dump(_refusal("NATIVE_BINDING_STALE", binding))

        action = request["action"]
        try:
            if action == "selected_child_submit":
                raw = binding.transport.submit_selected_child(binding.command)
            else:
                raw = binding.transport.selected_child_status(binding.command)
        except Exception:
            # The transport may already have sent the command. The original
            # command identity is kept; nothing is retried or cancelled.
            if action == "selected_child_submit":
                return _dump(_uncertain(
                    "EFFECT_UNKNOWN", "EXECUTIVE_SELECTED_CHILD_EFFECT_UNKNOWN", binding))
            return _dump(_uncertain(
                "UNAVAILABLE", "EXECUTIVE_SELECTED_CHILD_UNAVAILABLE", binding))

        envelope = _validate_envelope(raw, binding)
        if envelope is None:
            if action == "selected_child_submit":
                return _dump(_uncertain(
                    "EFFECT_UNKNOWN", "EXECUTIVE_SELECTED_CHILD_EFFECT_UNKNOWN", binding))
            return _dump(_uncertain(
                "UNAVAILABLE", "EXECUTIVE_SELECTED_CHILD_UNAVAILABLE", binding))
        # A synchronous RPC can still cross a native connection/authority change.
        # Re-prove the original caller before exposing any result text.
        if (_caller_lineage_refusal(binding, session_id, task_id) is not None
                or not _binding_is_current(binding)):
            if action == "selected_child_submit":
                return _dump(_uncertain(
                    "EFFECT_UNKNOWN", "EXECUTIVE_SELECTED_CHILD_EFFECT_UNKNOWN", binding))
            return _dump(_uncertain(
                "UNAVAILABLE", "EXECUTIVE_SELECTED_CHILD_UNAVAILABLE", binding))
        return _dump(envelope)

    handle.__name__ = "mmx_delegate_selected_child"
    handle.__qualname__ = handle.__name__
    return handle


def native_delegate_check_fn(binding: NativeDelegateBinding) -> Callable[[], bool]:
    """Build the availability probe for one binding.

    The probe is discovery only. ``ToolRegistry.dispatch`` never calls it, so
    it is never treated as the handler's authorization: the handler re-checks
    the caller lineage and the binding currentness itself, immediately before a
    possible transport write.
    """
    if not isinstance(binding, NativeDelegateBinding):
        raise NativeToolRegistrationError("NATIVE_BINDING_INVALID")

    def check() -> bool:
        return _binding_is_current(binding)

    check.__name__ = "mmx_delegate_selected_child_available"
    check.__qualname__ = check.__name__
    return check


def _registry() -> Any:
    """The upstream tool registry that owns the installed entry."""
    try:
        from tools.registry import registry
    except Exception:
        raise NativeToolRegistrationError("NATIVE_TOOL_API_UNAVAILABLE") from None
    return registry


def _ctx_scope(ctx: Any) -> str:
    """The profile scope the upstream owner registers into.

    ``PluginContext.register_tool`` uses its manager's ``scope_key``; the
    readback must use the same scope or it would prove nothing. If the owner
    stops exposing it, the registration refuses instead of reading back a
    scope it did not write.
    """
    manager = getattr(ctx, "_manager", None)
    scope = getattr(manager, "scope_key", None)
    if not isinstance(scope, str) or not scope:
        raise NativeToolRegistrationError("NATIVE_SCOPE_UNAVAILABLE")
    return scope


def _ctx_profile_name(ctx: Any) -> str:
    """The active native profile name, as the upstream owner reports it."""
    profile = getattr(ctx, "profile_name", None)
    if not isinstance(profile, str) or not profile:
        raise NativeToolRegistrationError("NATIVE_PROFILE_UNAVAILABLE")
    return profile


def _loading_mode_refusal(ctx: Any) -> str | None:
    """Refuse a loading mode that cannot carry a live binding.

    Under ``plugins.isolation: host`` a third-party plugin runs in a separate
    plugin-host process, where a live transport binding does not exist and the
    profile lineage is not the Hermes process's. Bundled plugins stay
    in-process and are unaffected.
    """
    try:
        from hermes_cli.plugin_isolation import (
            HOST_PROCESS_ENV,
            ISOLATION_HOST,
            isolation_mode,
        )
    except Exception:
        return "NATIVE_PLUGIN_API_UNAVAILABLE"
    if os.environ.get(HOST_PROCESS_ENV) == "1":
        return "NATIVE_PLUGIN_HOST_PROCESS_REFUSED"
    source = getattr(getattr(ctx, "manifest", None), "source", "")
    try:
        mode = isolation_mode()
    except Exception:
        return "NATIVE_PLUGIN_ISOLATION_UNKNOWN"
    if mode == ISOLATION_HOST and source != "bundled":
        return "NATIVE_PLUGIN_ISOLATION_HOST_REFUSED"
    return None


def register_native_delegate_tool(
    ctx: Any, binding: NativeDelegateBinding,
) -> NativeDelegateRegistration:
    """Register the one selected-child tool through the upstream owner.

    The actual registration is ``ctx.register_tool``: Hermes keeps ownership
    of the installed entry, its profile scope and its unload. The readback
    proves the exact installed entry, schema, handler and profile scope with
    the owner's own registry API. A collision never reports REGISTERED.
    """
    if not isinstance(binding, NativeDelegateBinding):
        raise NativeToolRegistrationError("NATIVE_BINDING_INVALID")
    if not hasattr(ctx, "register_tool") or not callable(ctx.register_tool):
        raise NativeToolRegistrationError("NATIVE_PLUGIN_CONTEXT_INVALID")

    refusal = _loading_mode_refusal(ctx)
    if refusal is not None:
        raise NativeToolRegistrationError(refusal)

    scope = _ctx_scope(ctx)
    profile = _ctx_profile_name(ctx)
    if profile != binding.profile_id:
        raise NativeToolRegistrationError("NATIVE_PROFILE_MISMATCH")

    registry = _registry()
    try:
        from registration_lifecycle import replacement_coordinator
    except Exception:
        raise NativeToolRegistrationError("NATIVE_PLUGIN_API_UNAVAILABLE") from None
    handler = native_delegate_handler(binding)
    check_fn = native_delegate_check_fn(binding)
    # Serialize the complete operation with the incumbent native context/lease
    # owner. Its lock is reentrant. Raw-registry writers are outside that
    # supported owner path; this is not a new or universal registration lock.
    with replacement_coordinator.transaction():
        if registry.snapshot_registration(TOOL_NAME, scope=scope) is not None:
            raise NativeToolRegistrationError("NATIVE_TOOL_COLLISION")
        if registry.get_entry(TOOL_NAME, scope=scope) is not None:
            raise NativeToolRegistrationError("NATIVE_TOOL_NAME_TAKEN")
        try:
            handle = ctx.register_tool(
                name=TOOL_NAME,
                toolset=TOOLSET_NAME,
                schema=NATIVE_TOOL_SCHEMA,
                handler=handler,
                check_fn=check_fn,
                is_async=False,
                description=NATIVE_TOOL_SCHEMA["description"],
                emoji="mmx",
            )
        except Exception as exc:
            # The owner may have written its slot before returning its lease.
            # Retain the original owner; no retry or broad unregister can
            # safely infer that this exception means nothing was installed.
            raise NativeToolRegistrationError(
                "NATIVE_TOOL_REGISTRATION_EFFECT_UNKNOWN", context=ctx,
                binding=binding, scope=scope) from exc
        if handle is None:
            raise NativeToolRegistrationError("NATIVE_TOOL_NOT_REGISTERED")
        try:
            entry = registry.snapshot_registration(TOOL_NAME, scope=scope)
            if (
                entry is None
                or entry.handler is not handler
                or entry.toolset != TOOLSET_NAME
                or entry.schema != NATIVE_TOOL_SCHEMA
                or entry.check_fn is not check_fn
            ):
                raise NativeToolRegistrationError("NATIVE_TOOL_READBACK_MISMATCH")
        except Exception as exc:
            try:
                # Dispose only the captured native lease. Its owner restores
                # conditionally by identity and preserves later generations.
                handle.dispose()
            except Exception as cleanup_exc:
                raise NativeToolRegistrationError(
                    "NATIVE_TOOL_ROLLBACK_EFFECT_UNKNOWN", context=ctx,
                    binding=binding, scope=scope, handle=handle) from cleanup_exc
            if isinstance(exc, NativeToolRegistrationError):
                raise
            raise NativeToolRegistrationError("NATIVE_TOOL_READBACK_FAILED") from exc
        return NativeDelegateRegistration(
            name=TOOL_NAME,
            toolset=TOOLSET_NAME,
            scope=scope,
            profile_id=binding.profile_id,
            session_id=binding.session_id,
            command=binding.command,
            job_id=binding.job_id,
            handler=handler,
            check_fn=check_fn,
            handle=handle,
            entry=entry,
        )


def register_native_delegate_tools(
    ctx: Any, startup: NativeDelegateStartup,
) -> NativeDelegateRegistration:
    """Private host composition helper for one existing startup binding.

    The loader calls ``register(ctx)`` with the plugin context only, so
    the binding has to come from the host's own startup state. The default
    startup is unbound and a registration against it refuses; this module
    never invents a target, a transport or a principal.
    """
    binding = startup.binding if isinstance(startup, NativeDelegateStartup) else None
    if binding is None:
        raise NativeToolRegistrationError("NATIVE_TOOL_STARTUP_UNBOUND")
    return register_native_delegate_tool(ctx, binding)
