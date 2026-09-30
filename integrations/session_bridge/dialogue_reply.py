"""Executive-side CONTINUE adapter over the existing Agent Dialogue V2 owner.

The model never supplies Slack/thread/context/actor/Attempt identity. A trusted
host resolver binds one opaque target_ref to the exact current dialogue carrier.
This adapter fresh-reads that carrier, reconciles the exact unresolved request,
and commits one canonical CONTINUE through the existing Agent Dialogue service.

It creates no dialogue store, target registry, retry plane, lifecycle state, or
provider session. Native attention is a separate post-commit concern.
"""
from __future__ import annotations

import dataclasses
import hashlib
from collections.abc import Awaitable, Callable, Mapping
from pathlib import Path
from typing import Any, Protocol

from integrations.slack_agent_dialogue.contract_v2 import (
    MESSAGE_SCHEMA_V2,
    build_message_v2,
)
from integrations.slack_agent_dialogue.engine import DialogueEngineError
from integrations.slack_agent_dialogue.engine_v2 import DialogueContextV2
from integrations.slack_agent_dialogue.service import (
    CONTROL_VERSION_V2,
    EXACT_SEND_PROTOCOL,
    DialogueServiceError,
    call_service,
)

from .schemas import BridgeError

_ELIGIBLE_REQUEST_TYPES = frozenset({"ACK", "PROGRESS", "BLOCKED", "RESULT"})
_COMMITTED_ACTIONS = frozenset({"POSTED", "RECOVERED", "DUPLICATE"})
ServiceCall = Callable[[Path, Mapping[str, Any]], Awaitable[dict[str, Any]]]


@dataclasses.dataclass(frozen=True)
class ExecutiveReplyBinding:
    """Trusted exact-current binding; every field comes from incumbent owners."""

    target_ref: str
    work_ref: str
    commission_ref: Mapping[str, Any]
    session_ref: str
    dialogue_operation_key: str
    watch_mode: str | None
    applies_to: Mapping[str, Any]
    thread_ts: str
    reply_to_message_key: str


class ExecutiveReplyBindingResolver(Protocol):
    def resolve(self, target_ref: str) -> ExecutiveReplyBinding: ...


class AgentDialogueContinueWriter:
    """Fresh-read and commit one typed executive CONTINUE with no retry."""

    def __init__(
        self,
        resolver: ExecutiveReplyBindingResolver,
        *,
        socket_path: Path,
        service_call: ServiceCall = call_service,
    ) -> None:
        path = Path(socket_path)
        if not path.is_absolute():
            raise ValueError("socket_path must be absolute")
        if not hasattr(resolver, "resolve") or not callable(resolver.resolve):
            raise TypeError("resolver must expose resolve()")
        if not callable(service_call):
            raise TypeError("service_call must be callable")
        self._resolver = resolver
        self._socket_path = path
        self._service_call = service_call

    @staticmethod
    def _context(binding: ExecutiveReplyBinding) -> dict[str, Any]:
        if not isinstance(binding, ExecutiveReplyBinding):
            raise BridgeError("binding_unavailable", "reply binding is unavailable")
        try:
            return DialogueContextV2(
                work_ref=binding.work_ref,
                commission_ref=dict(binding.commission_ref),
                session_ref=binding.session_ref,
                operation_key=binding.dialogue_operation_key,
                watch_mode=binding.watch_mode,
                actor_ref={
                    "kind": "executive_surface",
                    "seat": "ceo",
                    "reasoning_surface": "chatgpt",
                },
                applies_to=dict(binding.applies_to),
            ).normalized()
        except (DialogueEngineError, TypeError, ValueError):
            raise BridgeError("binding_unavailable", "reply binding is invalid") from None

    async def _read(
        self,
        *,
        binding: ExecutiveReplyBinding,
        context: Mapping[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        request = {
            "version": CONTROL_VERSION_V2,
            "operation": "read_thread",
            "args": {"context": dict(context), "thread_ts": binding.thread_ts},
        }
        try:
            response = await self._service_call(self._socket_path, request)
        except DialogueServiceError as exc:
            raise BridgeError("carrier_unavailable", exc.code) from None
        except Exception:
            raise BridgeError("carrier_unavailable", "dialogue read failed") from None
        if not isinstance(response, dict) or response.get("ok") is not True:
            raise BridgeError("carrier_unavailable", "dialogue read was not proven")
        result = response.get("result")
        if (
            not isinstance(result, dict)
            or result.get("thread_ts") != binding.thread_ts
            or not isinstance(result.get("messages"), list)
            or result.get("historical_messages") != []
            or result.get("mutated_count") != 0
        ):
            raise BridgeError("carrier_stale", "dialogue history is not exact/current")

        matches = []
        replies = []
        eligible_worker_items = []
        for item in result["messages"]:
            if not isinstance(item, dict) or not isinstance(item.get("message"), dict):
                raise BridgeError("carrier_stale", "dialogue history is malformed")
            message = item["message"]
            actor = message.get("actor_ref")
            if (
                isinstance(actor, Mapping)
                and actor.get("kind") == "worker_attempt"
                and message.get("message_type") in _ELIGIBLE_REQUEST_TYPES
            ):
                eligible_worker_items.append(item)
            if message.get("message_key") == binding.reply_to_message_key:
                matches.append(item)
            if (
                message.get("reply_to_message_key") == binding.reply_to_message_key
                and isinstance(actor, Mapping)
                and actor.get("kind") == "executive_surface"
            ):
                replies.append(item)

        if len(matches) != 1:
            raise BridgeError("carrier_stale", "reply target is missing or ambiguous")
        current = matches[0]
        message = current["message"]
        if (
            message.get("message_type") not in _ELIGIBLE_REQUEST_TYPES
            or message.get("applies_to") != dict(binding.applies_to)
            or not isinstance(message.get("created_at"), str)
        ):
            raise BridgeError("carrier_stale", "reply target is not continuation-eligible")
        if (
            message.get("message_type") == "BLOCKED"
            and (
                not isinstance(message.get("body"), Mapping)
                or message["body"].get("needed_from") != "sol"
            )
        ):
            raise BridgeError("carrier_stale", "blocked return is not waiting on executive")
        if not eligible_worker_items or current.get("primary_ts") != max(
            item.get("primary_ts", "") for item in eligible_worker_items
        ):
            raise BridgeError("carrier_stale", "reply target is not the latest eligible return")
        if len(replies) > 1:
            raise BridgeError("carrier_stale", "multiple executive replies already exist")
        return message, replies[0]["message"] if replies else {}

    @staticmethod
    def _message(
        *,
        request_message: Mapping[str, Any],
        context: Mapping[str, Any],
        instruction: str,
        stop_condition: str,
        operation_key: str,
    ) -> dict[str, Any]:
        digest = hashlib.sha256(
            (
                operation_key
                + "\n"
                + str(request_message["message_key"])
                + "\n"
                + instruction
                + "\n"
                + stop_condition
            ).encode("utf-8")
        ).hexdigest()[:40]
        try:
            return build_message_v2(
                {
                    "schema": MESSAGE_SCHEMA_V2,
                    "message_key": f"asd-dot-continue-{digest}",
                    "message_type": "CONTINUE",
                    "work_ref": context["work_ref"],
                    "commission_ref": context["commission_ref"],
                    "session_ref": context["session_ref"],
                    "actor_ref": context["actor_ref"],
                    "reply_to_message_key": request_message["message_key"],
                    "applies_to": context["applies_to"],
                    "summary": "Continue the current commissioned operation.",
                    "body": {
                        "instruction": instruction,
                        "stop_condition": stop_condition,
                        "scope_change": False,
                    },
                    "evidence_refs": [],
                    "requires_response": False,
                    # Reuse the immutable request timestamp so identical
                    # operation_key + body deterministically rebuilds the same
                    # exact reply for effect reconciliation without a new store.
                    "created_at": request_message["created_at"],
                }
            )
        except Exception:
            raise BridgeError("dialogue_refused", "CONTINUE frame is invalid") from None

    async def __call__(
        self,
        target_ref: str,
        instruction: str,
        stop_condition: str,
        operation_key: str,
    ) -> dict[str, Any]:
        try:
            binding = self._resolver.resolve(target_ref)
        except Exception:
            raise BridgeError("binding_unavailable", "exact target binding unavailable") from None
        if binding.target_ref != target_ref:
            raise BridgeError("binding_unavailable", "target binding drifted")
        context = self._context(binding)
        request_message, existing_reply = await self._read(
            binding=binding,
            context=context,
        )
        message = self._message(
            request_message=request_message,
            context=context,
            instruction=instruction,
            stop_condition=stop_condition,
            operation_key=operation_key,
        )

        if existing_reply:
            if existing_reply != message:
                raise BridgeError(
                    "carrier_stale", "a different executive reply already exists"
                )
            return {
                "reply_committed": True,
                "action": "DUPLICATE",
                "message_key": message["message_key"],
                "fingerprint": message["fingerprint"],
                "thread_ts": binding.thread_ts,
            }

        send_request = {
            "version": CONTROL_VERSION_V2,
            "operation": "send_message",
            "args": {
                "context": context,
                "thread_ts": binding.thread_ts,
                "message": message,
                "send_protocol": EXACT_SEND_PROTOCOL,
            },
        }
        try:
            response = await self._service_call(self._socket_path, send_request)
        except DialogueServiceError as exc:
            code = "carrier_effect_unknown" if exc.code == "SEND_EFFECT_UNKNOWN" else "carrier_unavailable"
            raise BridgeError(code, exc.code) from None
        except Exception:
            raise BridgeError("carrier_unavailable", "dialogue send failed") from None
        if not isinstance(response, dict) or response.get("ok") is not True:
            error = response.get("error") if isinstance(response, dict) else None
            detail = error.get("code") if isinstance(error, dict) else "dialogue send refused"
            code = "carrier_effect_unknown" if detail == "SEND_EFFECT_UNKNOWN" else "dialogue_refused"
            raise BridgeError(code, str(detail))
        receipt = response.get("result")
        if (
            not isinstance(receipt, dict)
            or receipt.get("action") not in _COMMITTED_ACTIONS
            or receipt.get("message_key") != message["message_key"]
            or receipt.get("fingerprint") != message["fingerprint"]
        ):
            raise BridgeError(
                "carrier_effect_unknown",
                "dialogue commit receipt is incomplete or mismatched",
            )
        return {
            "reply_committed": True,
            "action": receipt["action"],
            "message_key": message["message_key"],
            "fingerprint": message["fingerprint"],
            "thread_ts": binding.thread_ts,
        }


__all__ = [
    "AgentDialogueContinueWriter",
    "ExecutiveReplyBinding",
    "ExecutiveReplyBindingResolver",
]
