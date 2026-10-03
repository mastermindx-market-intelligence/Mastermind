"""Installed Session Bridge transport over the existing Executive CeoIngress App peer.

This module owns no Runtime, target registry, provider connection, OAuth realm,
queue, retry loop, or lifecycle. The network-side MCP process serializes one
already-verified principal projection and one validated Session Bridge call to
the existing private CeoIngress socket. The Runtime-owning Executive service
injects the canonical target/reply/admission owners into
:class:`InstalledSessionBridgeProvider`.
"""
from __future__ import annotations

import dataclasses
import inspect
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from control_plane.principal_projection import (
    NeutralPrincipalProjection,
    neutral_principal_projection,
)
from integrations.business_mcp_auth.contracts import VerifiedPrincipal
from integrations.business_mcp_auth.principal_projection import principal_projection
from integrations.mastermind_executive_app.gateway import (
    CeoIngressClient,
    TRANSPORT_NOT_SENT,
    TRANSPORT_SENT_OK,
    TRANSPORT_SENT_UNKNOWN,
)
from .schemas import (
    BridgeError,
    MODIFYING_TOOLS,
    validate_tool_arguments,
)

PRIVATE_SCHEMA = "mastermind.executive_ceo_ingress_session_bridge.v1"
PRIVATE_RESULT_SCHEMA = "mastermind.executive_ceo_ingress_session_bridge_result.v1"
_PRIVATE_KEYS = frozenset({"schema", "tool", "principal", "arguments"})
_PRINCIPAL_KEYS = frozenset({
    "policy_id", "issuer", "issuer_digest", "resource", "subject_digest",
    "client_ref", "scopes", "issued_at", "expires_at", "jti_digest",
})
_MAX_TARGETS = 256


async def _maybe(value: Any) -> Any:
    return await value if inspect.isawaitable(value) else value


def principal_frame(principal: VerifiedPrincipal) -> dict[str, Any]:
    projection = principal_projection(principal)
    return {
        "policy_id": projection.policy_id,
        "issuer": projection.issuer,
        "issuer_digest": projection.issuer_digest,
        "resource": projection.resource,
        "subject_digest": projection.subject_digest,
        "client_ref": projection.client_ref,
        "scopes": list(projection.scopes),
        "issued_at": projection.issued_at,
        "expires_at": projection.expires_at,
        "jti_digest": projection.jti_digest,
    }


def _principal(value: Any) -> NeutralPrincipalProjection:
    if not isinstance(value, Mapping) or set(value) != _PRINCIPAL_KEYS:
        raise BridgeError("invalid_input", "verified principal projection is invalid")
    scopes = value.get("scopes")
    if not isinstance(scopes, list) or any(type(item) is not str for item in scopes):
        raise BridgeError("invalid_input", "verified principal projection is invalid")
    try:
        return neutral_principal_projection(
            policy_id=value["policy_id"],
            issuer=value["issuer"],
            issuer_digest=value["issuer_digest"],
            resource=value["resource"],
            subject_digest=value["subject_digest"],
            client_ref=value["client_ref"],
            scopes=tuple(scopes),
            issued_at=value["issued_at"],
            expires_at=value["expires_at"],
            jti_digest=value["jti_digest"],
        )
    except (TypeError, ValueError, KeyError):
        raise BridgeError("invalid_input", "verified principal projection is invalid") from None


def _result(tool: str, *, data: Any = None, code: str | None = None,
            message: str | None = None) -> dict[str, Any]:
    return {
        "schema": PRIVATE_RESULT_SCHEMA,
        "tool": tool,
        "ok": code is None,
        "data": data if code is None else None,
        "error": None if code is None else {
            "code": code,
            "message": message or "installed Session Bridge operation was refused",
        },
    }


def validate_private_frame(value: Any) -> tuple[str, NeutralPrincipalProjection, dict[str, Any]]:
    if not isinstance(value, Mapping) or set(value) != _PRIVATE_KEYS:
        raise BridgeError("invalid_input", "installed Session Bridge frame is invalid")
    if value.get("schema") != PRIVATE_SCHEMA:
        raise BridgeError("invalid_input", "installed Session Bridge frame is invalid")
    tool = value.get("tool")
    if not isinstance(tool, str):
        raise BridgeError("invalid_input", "installed Session Bridge tool is invalid")
    principal = _principal(value.get("principal"))
    arguments = validate_tool_arguments(tool, value.get("arguments"))
    return tool, principal, arguments


class InstalledSessionBridgeProvider:
    """Runtime-side composition over already-existing canonical owners."""

    def __init__(
        self,
        *,
        target_projector: Callable[[NeutralPrincipalProjection, str | None], Any],
        reply_handler: Callable[[NeutralPrincipalProjection, Mapping[str, Any]], Any],
        summon_handler: Callable[[NeutralPrincipalProjection, Mapping[str, Any]], Any],
    ) -> None:
        for name, value in (
            ("target_projector", target_projector),
            ("reply_handler", reply_handler),
            ("summon_handler", summon_handler),
        ):
            if not callable(value):
                raise TypeError(f"{name} must be callable")
        self._target_projector = target_projector
        self._reply_handler = reply_handler
        self._summon_handler = summon_handler

    async def handle_frame(self, frame: Any) -> dict[str, Any]:
        tool, principal, arguments = validate_private_frame(frame)
        modifying = tool in MODIFYING_TOOLS
        try:
            if tool == "session_targets":
                data = await _maybe(self._target_projector(principal, arguments.get("kind")))
                if (
                    not isinstance(data, (list, tuple))
                    or len(data) > _MAX_TARGETS
                    or any(not isinstance(item, Mapping) for item in data)
                ):
                    raise BridgeError(
                        "backend_unavailable",
                        "authorized target projection is unavailable",
                    )
                return _result(tool, data=[dict(item) for item in data])
            if tool == "session_send":
                data = await _maybe(self._reply_handler(principal, dict(arguments)))
            else:
                data = await _maybe(self._summon_handler(principal, dict(arguments)))
            if not isinstance(data, Mapping):
                return _result(
                    tool,
                    code="effect_unknown" if modifying else "backend_unavailable",
                    message=(
                        "operation outcome is unknown; reconcile the original operation"
                        if modifying
                        else "installed Session Bridge owner is unavailable"
                    ),
                )
            return _result(tool, data=dict(data))
        except BridgeError as exc:
            return _result(tool, code=exc.code, message=exc.message)
        except BaseException as exc:
            # Cancellation/SystemExit/KeyboardInterrupt are not converted to an
            # ordinary response. They may interrupt an in-flight modification,
            # and the caller must reconcile the original transport operation.
            if not isinstance(exc, Exception):
                raise
            return _result(
                tool,
                code="effect_unknown" if modifying else "backend_unavailable",
                message=(
                    "operation outcome is unknown; reconcile the original operation"
                    if modifying
                    else "installed Session Bridge owner is unavailable"
                ),
            )


def build_runtime_session_bridge(runtime: Any, *, dialogue_socket_path: Path):
    """Compose the installed fabric path from existing Runtime/Dialogue owners.

    Compatibility schemas do not grant native Codex or Claude ownership. Those
    kinds stay absent until their actual host-owned session adapters are bound.
    """
    from .runtime_owner import RuntimeFabricTargetProjector, RuntimeExecutiveReplyBindingResolver
    from .dialogue_reply import AgentDialogueContinueWriter
    from .native_backends import CanonicalReplyCoordinator, CanonicalTargetReader, ExactTargetRouter

    projector = RuntimeFabricTargetProjector(runtime)
    writer = AgentDialogueContinueWriter(
        RuntimeExecutiveReplyBindingResolver(projector), socket_path=dialogue_socket_path)
    reader = CanonicalTargetReader(
        fabric_reader=projector.project, codex_reader=lambda: [], claude_reader=lambda: [])

    def unavailable(*_):
        raise BridgeError("backend_unavailable", "installed native session owner is unavailable")

    # A canonical reply receipt is never promoted into attention/consumption.
    # The existing Dialogue/Wake loop remains the attention owner; this bridge
    # cannot inject a raw provider prompt or launch another worker.
    coordinator = CanonicalReplyCoordinator(
        reply_writer=writer, attention_waker=lambda *_: {"state": "UNAVAILABLE"})
    router = ExactTargetRouter(
        fabric_reply=coordinator, codex_reply=unavailable, claude_reply=unavailable)

    def targets(principal, kind):
        values = reader(kind)
        if isinstance(values, Mapping):
            return [item for group in values.values() for item in group]
        return values

    async def send(principal, arguments):
        return await _maybe(router(
            arguments["target_ref"], arguments["instruction"],
            arguments["stop_condition"], arguments["operation_key"]))

    return InstalledSessionBridgeProvider(
        target_projector=targets, reply_handler=send, summon_handler=unavailable)


class InstalledSessionBridgeClient:
    """Network-side one-frame client of the existing private CeoIngress peer."""

    def __init__(
        self,
        socket_path: str | Path,
        *,
        client: CeoIngressClient | Any | None = None,
    ) -> None:
        path = Path(socket_path)
        if not path.is_absolute():
            raise ValueError("CeoIngress socket path must be absolute")
        selected = client if client is not None else CeoIngressClient()
        if not callable(getattr(selected, "send_frame", None)):
            raise TypeError("CeoIngress client must expose send_frame")
        self._socket_path = path
        self._client = selected

    async def _call(
        self,
        principal: VerifiedPrincipal,
        tool: str,
        arguments: Mapping[str, Any],
    ) -> Any:
        args = validate_tool_arguments(tool, arguments)
        modifying = tool in MODIFYING_TOOLS
        frame = {
            "schema": PRIVATE_SCHEMA,
            "tool": tool,
            "principal": principal_frame(principal),
            "arguments": args,
        }
        response = await self._client.send_frame(self._socket_path, frame)
        transport = getattr(response, "transport", None)
        if transport == TRANSPORT_NOT_SENT:
            raise BridgeError(
                "backend_unavailable",
                "installed Session Bridge owner is unavailable",
            )
        if transport == TRANSPORT_SENT_UNKNOWN:
            raise BridgeError(
                "effect_unknown" if modifying else "backend_unavailable",
                (
                    "operation outcome is unknown; reconcile the original operation"
                    if modifying
                    else "installed Session Bridge owner is unavailable"
                ),
            )
        if transport != TRANSPORT_SENT_OK or response.ok is not True:
            raise BridgeError(
                "effect_unknown" if modifying else "backend_unavailable",
                (
                    "operation outcome is unknown; reconcile the original operation"
                    if modifying
                    else "installed Session Bridge owner is unavailable"
                ),
            )
        payload = response.result
        if (
            not isinstance(payload, Mapping)
            or payload.get("schema") != PRIVATE_RESULT_SCHEMA
            or payload.get("tool") != tool
            or type(payload.get("ok")) is not bool
            or set(payload) != {"schema", "tool", "ok", "data", "error"}
        ):
            raise BridgeError(
                "effect_unknown" if modifying else "backend_unavailable",
                (
                    "operation outcome is unknown; reconcile the original operation"
                    if modifying
                    else "installed Session Bridge owner is unavailable"
                ),
            )
        if payload["ok"] is False:
            error = payload.get("error")
            if (
                not isinstance(error, Mapping)
                or set(error) != {"code", "message"}
                or not isinstance(error.get("code"), str)
                or not isinstance(error.get("message"), str)
            ):
                raise BridgeError(
                    "effect_unknown" if modifying else "backend_unavailable",
                    "installed Session Bridge response is unavailable",
                )
            raise BridgeError(error["code"], error["message"])
        if payload.get("error") is not None:
            raise BridgeError(
                "effect_unknown" if modifying else "backend_unavailable",
                "installed Session Bridge response is unavailable",
            )
        return payload.get("data")

    async def targets(
        self, principal: VerifiedPrincipal, kind: str | None = None
    ) -> Any:
        args = {} if kind is None else {"kind": kind}
        return await self._call(principal, "session_targets", args)

    async def send(
        self, principal: VerifiedPrincipal, arguments: Mapping[str, Any]
    ) -> Any:
        return await self._call(principal, "session_send", arguments)

    async def summon(
        self, principal: VerifiedPrincipal, arguments: Mapping[str, Any]
    ) -> Any:
        return await self._call(principal, "session_summon", arguments)


__all__ = [
    "InstalledSessionBridgeClient",
    "InstalledSessionBridgeProvider",
    "PRIVATE_RESULT_SCHEMA",
    "PRIVATE_SCHEMA",
    "principal_frame",
    "validate_private_frame",
]
