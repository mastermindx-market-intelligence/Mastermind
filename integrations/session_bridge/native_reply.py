"""Native session replies on their original Agent Dialogue V2 carrier.

This is a host-composed adapter, not an endpoint, registry, credential service,
writer lease or retry owner. The installed host must authenticate the native
connection, resolve its current RuntimeBinding and enforce the existing writer
fence at the service commit. A second pre-send read detects intervening drift;
it does not replace that atomic owner check. No tool is auto-registered here.
"""
from __future__ import annotations

import dataclasses
import hashlib
import inspect
import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID

from integrations.slack_agent_dialogue.contract_v2 import (
    MESSAGE_SCHEMA_V2, build_message_v2, validate_message_v2,
)
from integrations.slack_agent_dialogue.engine_v2 import DialogueContextV2
from integrations.slack_agent_dialogue.service import (
    CONTROL_VERSION_V2, EXACT_SEND_PROTOCOL, call_service,
)
from .schemas import BridgeError

_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$")
_OPERATION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,95}$")
_TS = re.compile(r"^[0-9]{10}\.[0-9]{6}$")
_COMMITTED = frozenset({"POSTED", "RECOVERED", "DUPLICATE"})


@dataclasses.dataclass(frozen=True)
class NativeReplyBinding:
    """Transient projection from existing owners; never caller-authored."""
    native_session_id: str
    binding_id: str
    binding_generation: int
    process_generation_id: str
    context: DialogueContextV2
    thread_ts: str
    request_message_key: str
    reply_operation_key: str
    reply_predecessor_advanced: bool = False


def native_reply_message_key(operation_key: str) -> str:
    return "asd-native-reply-" + hashlib.sha256(
        ("mastermind.session_bridge.native_reply.v1\n" + operation_key).encode()
    ).hexdigest()[:40]


class NativeReplyResolver(Protocol):
    def resolve(self, *, native_session_id: str, operation_key: str,
                in_reply_to: str) -> NativeReplyBinding: ...


async def _await(value: Any) -> Any:
    return await value if inspect.isawaitable(value) else value


def _text(value: Any, *, limit: int = 700) -> str:
    if (not isinstance(value, str) or not value.strip() or len(value) > limit
            or any(ord(c) < 32 and c not in "\n\t" for c in value)):
        raise BridgeError("invalid_input", "native reply text is invalid")
    # Reject invalid Unicode before any canonical read or write.
    try:
        value.encode("utf-8")
    except UnicodeError:
        raise BridgeError("invalid_input", "native reply text is invalid") from None
    return value


def validate_native_reply_arguments(arguments: Any) -> dict[str, str]:
    required = {"operation_key", "in_reply_to", "text", "next_step"}
    if not isinstance(arguments, Mapping) or set(arguments) != required:
        raise BridgeError("invalid_input", "native reply fields must match the exact schema")
    result = {key: _text(arguments[key]) for key in required}
    if (_OPERATION.fullmatch(result["operation_key"]) is None
            or _ID.fullmatch(result["in_reply_to"]) is None):
        raise BridgeError("invalid_input", "native reply identity is invalid")
    return result


def validate_native_reply_context(context: Mapping[str, Any]) -> None:
    """Keep the existing actor; never recast attended executives as workers.

    The caller must first normalize through DialogueContextV2. The trusted
    native resolver binds this context to its authenticated native connection.
    """
    actor, applies = context["actor_ref"], context["applies_to"]
    if actor.get("kind") == "worker_attempt":
        if (applies.get("kind") != "executive_attempt"
                or any(actor.get(k) != applies.get(k)
                       for k in ("job_id", "attempt_id", "worker_id"))):
            raise ValueError("native worker applicability mismatch")
        return
    if (actor.get("kind") == "executive_surface"
            and actor.get("seat") in {"ceo", "coo"}
            and actor.get("reasoning_surface") in {"codex", "claude"}):
        return
    raise ValueError("native reply cannot impersonate a Web or Chairman actor")


class NativeReplyWriter:
    """Write one PROGRESS reply; commitment never implies parent consumption."""
    def __init__(self, resolver: NativeReplyResolver, *, native_session_id: str,
                 socket_path: Path, service_call=call_service) -> None:
        if not callable(getattr(resolver, "resolve", None)) or not callable(service_call):
            raise TypeError("native reply requires resolver and canonical service")
        try:
            if str(UUID(native_session_id)) != native_session_id:
                raise ValueError
        except (ValueError, TypeError, AttributeError):
            raise ValueError("native session must be an exact canonical UUID") from None
        if not Path(socket_path).is_absolute():
            raise ValueError("canonical service socket must be absolute")
        self._resolver = resolver
        self._native_session_id = native_session_id
        self._socket_path = Path(socket_path)
        self._service_call = service_call

    async def _resolve(self, args: Mapping[str, str]):
        try:
            binding = await _await(self._resolver.resolve(
                native_session_id=self._native_session_id,
                operation_key=args["operation_key"], in_reply_to=args["in_reply_to"]))
            if type(binding) is not NativeReplyBinding:
                raise ValueError
            if (binding.native_session_id != self._native_session_id
                    or binding.reply_operation_key != args["operation_key"]
                    or binding.request_message_key != args["in_reply_to"]
                    or type(binding.binding_generation) is not int
                    or binding.binding_generation < 1
                    or not isinstance(binding.binding_id, str)
                    or not binding.binding_id.startswith("bind-")
                    or _ID.fullmatch(binding.binding_id) is None
                    or not isinstance(binding.process_generation_id, str)
                    or _ID.fullmatch(binding.process_generation_id) is None
                    or not isinstance(binding.thread_ts, str)
                    or _TS.fullmatch(binding.thread_ts) is None
                    or type(binding.context) is not DialogueContextV2
                    or type(binding.reply_predecessor_advanced) is not bool):
                raise ValueError
            context = binding.context.normalized()
            validate_native_reply_context(context)
            # Capture nested mutable maps now. Re-resolution must match the
            # whole projection, not merely the provider UUID or thread title.
            identity = json.dumps({"native_session_id": binding.native_session_id,
                "binding_id": binding.binding_id, "binding_generation": binding.binding_generation,
                "process_generation_id": binding.process_generation_id,
                "context": context, "thread_ts": binding.thread_ts,
                "request_message_key": binding.request_message_key,
                "reply_operation_key": binding.reply_operation_key,
                "reply_predecessor_advanced": binding.reply_predecessor_advanced}, sort_keys=True)
            context = json.loads(json.dumps(context))
            return binding, context, identity
        except Exception:
            raise BridgeError("binding_unavailable", "exact native return binding unavailable") from None

    async def _read(self, binding, context):
        try:
            response = await self._service_call(self._socket_path, {
                "version": CONTROL_VERSION_V2, "operation": "read_thread",
                "args": {"context": context, "thread_ts": binding.thread_ts}})
            if not isinstance(response, dict) or response.get("ok") is not True:
                raise ValueError
            result = response["result"]
            if (result.get("thread_ts") != binding.thread_ts
                    or result.get("historical_messages") != []
                    or type(result.get("mutated_count")) is not int
                    or result["mutated_count"] != 0
                    or not isinstance(result.get("messages"), list)):
                raise ValueError
            items = []
            for item in result["messages"]:
                if not isinstance(item, dict) or _TS.fullmatch(item.get("primary_ts", "")) is None:
                    raise ValueError
                message = validate_message_v2(item["message"])
                if any(message.get(k) != context[k] for k in
                       ("work_ref", "commission_ref", "session_ref", "applies_to")):
                    raise ValueError
                items.append((item["primary_ts"], message))
            return items
        except Exception:
            raise BridgeError("carrier_stale", "exact original carrier read unavailable") from None

    @staticmethod
    def _receipt(binding, message, action):
        return {"reply_committed": True, "action": action,
            "message_key": message["message_key"], "fingerprint": message["fingerprint"],
            "thread_ts": binding.thread_ts, "in_reply_to": binding.request_message_key,
            "parent_consumed": False}

    async def __call__(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        args = validate_native_reply_arguments(arguments)
        binding, context, identity = await self._resolve(args)
        items = await self._read(binding, context)
        matches = [(ts, m) for ts, m in items if m["message_key"] == binding.request_message_key]
        if len(matches) != 1:
            raise BridgeError("carrier_stale", "original executive request is missing or ambiguous")
        request_ts, request = matches[0]
        if (request["message_type"] != "CONTINUE"
                or request["actor_ref"].get("kind") != "executive_surface"
                or request["actor_ref"].get("seat") != "ceo"):
            raise BridgeError("carrier_stale", "original message is not an executive continuation")
        key = native_reply_message_key(binding.reply_operation_key)
        try:
            message = build_message_v2({
                "schema": MESSAGE_SCHEMA_V2, "message_key": key, "message_type": "PROGRESS",
                "work_ref": context["work_ref"], "commission_ref": context["commission_ref"],
                "session_ref": context["session_ref"], "actor_ref": context["actor_ref"],
                "reply_to_message_key": binding.request_message_key,
                "applies_to": context["applies_to"],
                "summary": "Native session replied to the current executive message.",
                "body": {"stage": "message_reply", "completed": args["text"], "next": args["next_step"]},
                "evidence_refs": [], "requires_response": False,
                # Immutable request timestamp keeps same-operation retries stable.
                # Actual transport time remains the canonical service's primary_ts.
                "created_at": request["created_at"]})
        except Exception:
            raise BridgeError("invalid_input", "native reply frame is invalid") from None
        _, _, current_identity = await self._resolve(args)
        if current_identity != identity:
            raise BridgeError("binding_unavailable", "native return binding changed before send")
        prior = [m for _, m in items if m["message_key"] == key]
        if prior:
            if len(prior) != 1 or prior[0] != message:
                raise BridgeError("operation_conflict", "reply operation already has different content")
            return self._receipt(binding, message, "DUPLICATE")
        if binding.reply_predecessor_advanced:
            raise BridgeError("carrier_stale", "advanced reply predecessor has no exact canonical reply")
        executive = [(ts, m) for ts, m in items if m["actor_ref"].get("kind") == "executive_surface"]
        if any(ts > request_ts or (ts == request_ts and m["message_key"] != binding.request_message_key)
               for ts, m in executive):
            raise BridgeError("carrier_stale", "a newer executive instruction supersedes this request")
        payload = {"version": CONTROL_VERSION_V2, "operation": "send_message", "args": {
            "context": context, "thread_ts": binding.thread_ts,
            "message": message, "send_protocol": EXACT_SEND_PROTOCOL}}
        try:
            response = await self._service_call(self._socket_path, payload)
            if not isinstance(response, dict) or response.get("ok") is not True:
                raise ValueError
            receipt = response["result"]
            if (receipt.get("action") not in _COMMITTED
                    or receipt.get("message_key") != key
                    or receipt.get("fingerprint") != message["fingerprint"]):
                raise ValueError
        except Exception:
            # After send entry, only an exact canonical receipt establishes an
            # effect. Do not infer absence from timeout or arbitrary diagnostics.
            # Cancellation propagates; the owning operation must reconcile it.
            raise BridgeError("carrier_effect_unknown", "native reply send requires original-operation reconciliation") from None
        return self._receipt(binding, message, receipt["action"])


__all__ = ["NativeReplyBinding", "NativeReplyResolver", "NativeReplyWriter", "validate_native_reply_arguments", "validate_native_reply_context"]
