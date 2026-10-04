"""Authorized original-request reads over the incumbent Agent Dialogue service.

An authenticated Executive host supplies VerifiedPrincipal; this module never
verifies tokens, creates identities, chooses a native session, writes messages,
records consumption, or installs an endpoint. The resolver consumes existing
request/Dialogue/permission owners, not a shadow read-reference registry.
"""
from __future__ import annotations

import dataclasses
import inspect
import json
import math
import re
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Protocol

from control_plane.principal_projection import NeutralPrincipalProjection
from integrations.business_mcp_auth.principal_projection import principal_projection
from integrations.slack_agent_dialogue.contract_v2 import validate_message_v2
from integrations.slack_agent_dialogue.engine_v2 import DialogueContextV2
from integrations.slack_agent_dialogue.service import CONTROL_VERSION_V2, call_service
from .native_reply import validate_native_reply_context
from .schemas import BridgeError

READ_SCOPE = "mastermind.executive.read"
RESULT_SCHEMA = "mastermind.native_reply_read.v1"
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$")
_TS = re.compile(r"^[0-9]{10,16}\.[0-9]{6}$")
_SHA = re.compile(r"^[0-9a-f]{64}$")
_ERROR = "authorized canonical reply is unavailable"


@dataclasses.dataclass(frozen=True)
class NativeReplyReadBinding:
    """Transient current authorization and immutable reply provenance."""
    authorized_principal: NeutralPrincipalProjection
    read_ref: str
    request_ref: str
    request_message_key: str
    thread_ts: str
    reply_message_key: str
    reply_fingerprint: str
    context: DialogueContextV2
    authorization_revision: str


class NativeReplyReadResolver(Protocol):
    def resolve_read(self, *, principal: NeutralPrincipalProjection,
                     read_ref: str) -> NativeReplyReadBinding: ...


async def _await(value: Any) -> Any:
    return await value if inspect.isawaitable(value) else value


def _identity(principal: NeutralPrincipalProjection) -> tuple[str, ...]:
    if type(principal) is not NeutralPrincipalProjection:
        raise ValueError
    # Token rotation is not a new principal. Issuer/resource/client are retained
    # so equal subjects across tenants cannot alias each other.
    return (principal.policy_id, principal.issuer_digest, principal.resource,
            principal.subject_digest, principal.client_ref)


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False)


class NativeReplyReader:
    def __init__(self, resolver: NativeReplyReadResolver, *, socket_path: Path,
                 service_call=call_service, clock=time.time, projected_principal=False):
        if (not callable(getattr(resolver, "resolve_read", None))
                or not callable(service_call) or not callable(clock)):
            raise TypeError("canonical reader dependencies are required")
        path = Path(socket_path)
        if not path.is_absolute():
            raise ValueError("canonical service socket must be absolute")
        if type(projected_principal) is not bool:
            raise TypeError("projected principal mode must be explicit")
        # Only the installed authenticated private-peer composition selects this.
        # Public tool calls retain the exact VerifiedPrincipal boundary.
        self._projected_principal = projected_principal
        self._resolver, self._socket_path = resolver, path
        self._service_call, self._clock = service_call, clock

    def _current_principal(self, principal):
        if self._projected_principal:
            if type(principal) is not NeutralPrincipalProjection:
                raise ValueError
            projection = principal
        else:
            projection = principal_projection(principal)
        now = self._clock()
        if (type(now) not in (int, float) or not math.isfinite(now)
                or type(projection.issued_at) is not int
                or type(projection.expires_at) is not int
                or not projection.issued_at <= now < projection.expires_at
                or READ_SCOPE not in projection.scopes):
            raise ValueError
        return projection

    async def _resolve(self, principal, read_ref):
        binding = await _await(self._resolver.resolve_read(principal=principal, read_ref=read_ref))
        if (type(binding) is not NativeReplyReadBinding
                or _identity(binding.authorized_principal) != _identity(principal)
                or READ_SCOPE not in binding.authorized_principal.scopes
                or binding.read_ref != read_ref
                or type(binding.context) is not DialogueContextV2):
            raise ValueError
        for field in ("read_ref", "request_ref", "request_message_key", "reply_message_key", "authorization_revision"):
            value = getattr(binding, field)
            if not isinstance(value, str) or _ID.fullmatch(value) is None:
                raise ValueError
        if (not isinstance(binding.thread_ts, str) or _TS.fullmatch(binding.thread_ts) is None
                or not isinstance(binding.reply_fingerprint, str)
                or _SHA.fullmatch(binding.reply_fingerprint) is None):
            raise ValueError
        context = binding.context.normalized()
        validate_native_reply_context(context)
        snapshot = _canonical({"principal": _identity(binding.authorized_principal),
            "read_ref": binding.read_ref, "request_ref": binding.request_ref,
            "request_message_key": binding.request_message_key,
            "thread_ts": binding.thread_ts, "reply_message_key": binding.reply_message_key,
            "reply_fingerprint": binding.reply_fingerprint, "context": context,
            "authorization_revision": binding.authorization_revision})
        # Preserve nested maps across awaited calls, even if an owner reuses its
        # transient projection object. Re-resolution must match the whole fact.
        return binding, json.loads(_canonical(context)), snapshot

    async def __call__(self, principal, arguments: Mapping[str, Any]) -> dict[str, Any]:
        try:
            if (not isinstance(arguments, Mapping) or set(arguments) != {"read_ref"}
                    or not isinstance(arguments["read_ref"], str)
                    or _ID.fullmatch(arguments["read_ref"]) is None):
                raise ValueError
            current = self._current_principal(principal)
            binding, context, snapshot = await self._resolve(current, arguments["read_ref"])
            response = await self._service_call(self._socket_path, {
                "version": CONTROL_VERSION_V2, "operation": "read_thread",
                "args": {"context": context, "thread_ts": binding.thread_ts}})
            if not isinstance(response, dict) or response.get("ok") is not True:
                raise ValueError
            data = response["result"]
            if (not isinstance(data, dict) or data.get("thread_ts") != binding.thread_ts
                    or data.get("historical_messages") != []
                    or type(data.get("mutated_count")) is not int or data["mutated_count"] != 0
                    or not isinstance(data.get("messages"), list) or len(data["messages"]) > 256):
                raise ValueError
            matches = []
            for item in data["messages"]:
                if not isinstance(item, dict) or not isinstance(item.get("message"), dict):
                    raise ValueError
                message = validate_message_v2(item["message"])
                if message["message_key"] == binding.reply_message_key:
                    if (not isinstance(item.get("primary_ts"), str)
                            or _TS.fullmatch(item["primary_ts"]) is None):
                        raise ValueError
                    matches.append((message, item["primary_ts"]))
            if len(matches) != 1:
                raise ValueError
            message, primary_ts = matches[0]
            if (message["fingerprint"] != binding.reply_fingerprint
                    or message["message_type"] != "PROGRESS"
                    or message["body"]["stage"] != "message_reply"
                    or message["reply_to_message_key"] != binding.request_message_key
                    or any(message[k] != context[k] for k in
                        ("actor_ref", "applies_to", "work_ref", "commission_ref", "session_ref"))):
                raise ValueError
            refreshed = self._current_principal(principal)
            _, _, after = await self._resolve(refreshed, arguments["read_ref"])
            self._current_principal(principal)
            if after != snapshot:
                raise ValueError
            result = {"schema": RESULT_SCHEMA, "read_ref": binding.read_ref,
                "request_ref": binding.request_ref, "in_reply_to": binding.request_message_key,
                "message_key": message["message_key"], "fingerprint": message["fingerprint"],
                "text": message["body"]["completed"], "next_step": message["body"]["next"],
                "primary_ts": primary_ts, "reply_committed": True, "parent_consumed": False}
            if len(_canonical(result).encode("ascii")) > 16384:
                raise ValueError
            return result
        except Exception:
            # Same public error for foreign, missing, stale and unavailable:
            # the caller learns neither existence nor private diagnostics.
            raise BridgeError("reply_unavailable", _ERROR) from None


__all__ = ["NativeReplyReadBinding", "NativeReplyReadResolver", "NativeReplyReader"]
