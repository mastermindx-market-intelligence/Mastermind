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
import json
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
    target_generation: str
    current_writer: Mapping[str, Any]
    work_ref: str
    commission_ref: Mapping[str, Any]
    session_ref: str
    dialogue_operation_key: str
    watch_mode: str | None
    applies_to: Mapping[str, Any]
    thread_ts: str
    reply_to_message_key: str

    @property
    def continuation_operation_key(self) -> str:
        """Host-derived identity for exactly one carrier/writer/generation.

        Payload is excluded so conflicting retries reconcile under one key.
        This pure projection is not a second operation registry.
        """
        witness = dataclasses.asdict(self)
        digest = hashlib.sha256(json.dumps(
            {"schema": "mastermind.session_bridge.continuation_binding.v1", **witness},
            sort_keys=True, separators=(",", ":"), ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")).hexdigest()
        return "session-continue-" + digest


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
        before_commit: Callable[..., Any] | None = None,
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
        if before_commit is not None and not callable(before_commit):
            raise TypeError("before_commit must be callable")
        self._before_commit = before_commit

    @staticmethod
    def _context(binding: ExecutiveReplyBinding) -> dict[str, Any]:
        if not isinstance(binding, ExecutiveReplyBinding):
            raise BridgeError("binding_unavailable", "reply binding is unavailable")
        if (
            not isinstance(binding.target_generation, str) or not binding.target_generation
            or dict(binding.current_writer) != {
                "kind": "worker_attempt",
                "job_id": binding.applies_to.get("job_id"),
                "attempt_id": binding.applies_to.get("attempt_id"),
                "worker_id": binding.applies_to.get("worker_id"),
            }
        ):
            raise BridgeError("binding_unavailable", "current writer binding is invalid")
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
            or message.get("actor_ref") != dict(binding.current_writer)
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
        # Identity excludes payload and return version. The incumbent engine
        # compares the fingerprint under this key, including concurrent sends.
        # The trusted host still owns binding the operation to its exact carrier.
        digest = hashlib.sha256(
            (
                "mastermind.session_bridge.continue.v1\n" + operation_key
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
            context = self._context(binding)
            if binding.target_ref != target_ref:
                raise ValueError("target binding drifted")
            bound_key = binding.continuation_operation_key
            # Deep snapshot includes nested owner facts; a frozen dataclass
            # alone cannot detect mapping mutation across the awaited read.
            bound_witness = dataclasses.asdict(binding)
        except Exception:
            raise BridgeError("binding_unavailable", "exact target binding unavailable") from None
        if operation_key != bound_key:
            raise BridgeError(
                "operation_carrier_conflict", "continuation operation belongs to another carrier"
            )
        request_message, existing_reply = await self._read(
            binding=binding,
            context=context,
        )
        try:
            current_binding = self._resolver.resolve(target_ref)
            current_context = self._context(current_binding)
            current_witness = dataclasses.asdict(current_binding)
            current_key = current_binding.continuation_operation_key
        except Exception:
            raise BridgeError(
                "binding_unavailable",
                "exact target binding unavailable after dialogue read",
            ) from None
        if (
            current_binding.target_ref != target_ref
            or current_context != context
            or current_witness != bound_witness
            or current_key != operation_key
        ):
            raise BridgeError(
                "binding_unavailable",
                "exact target binding changed during dialogue read",
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
        async def before_write():
            # This closure runs only after the incumbent Relay has returned
            # READY for this exact fingerprint, immediately before COMMIT.
            latest_request, latest_reply = await self._read(binding=binding, context=context)
            final_binding = self._resolver.resolve(target_ref)
            if (dataclasses.asdict(final_binding) != bound_witness
                    or self._context(final_binding) != context
                    or latest_request != request_message or latest_reply):
                raise BridgeError("binding_unavailable", "continuation changed before COMMIT")
            self._before_commit(
                binding=final_binding, context=context,
                request_message=latest_request, message=message,
            )

        try:
            if self._before_commit is None:
                response = await self._service_call(self._socket_path, send_request)
            else:
                response = await self._service_call(
                    self._socket_path, send_request, before_write=before_write)
        except BridgeError:
            raise
        except DialogueServiceError as exc:
            code = "carrier_effect_unknown" if exc.code == "SEND_EFFECT_UNKNOWN" else "carrier_unavailable"
            raise BridgeError(code, exc.code) from None
        except Exception:
            # Only the service's typed pre-commit refusal proves no effect.
            raise BridgeError("carrier_effect_unknown", "dialogue send outcome is unknown") from None
        if not isinstance(response, dict):
            raise BridgeError("carrier_effect_unknown", "dialogue send outcome is unknown")
        if response.get("ok") is not True:
            error = response.get("error")
            detail = error.get("code") if isinstance(error, dict) else None
            if set(response) != {"ok", "error"} or response.get("ok") is not False or (
                not isinstance(error, dict) or set(error) != {"code"}
            ):
                raise BridgeError("carrier_effect_unknown", "dialogue send outcome is unknown")
            try:
                typed_error = DialogueServiceError(detail)
            except (TypeError, ValueError):
                raise BridgeError("carrier_effect_unknown", "dialogue send outcome is unknown") from None
            code = "carrier_effect_unknown" if typed_error.code == "SEND_EFFECT_UNKNOWN" else "dialogue_refused"
            raise BridgeError(code, typed_error.code)
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
