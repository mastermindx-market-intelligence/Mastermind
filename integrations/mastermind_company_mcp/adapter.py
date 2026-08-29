"""Bounded adapter from semantic MCP calls to the accepted Dialogue V2 service."""
from __future__ import annotations

import re
import uuid
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from integrations.mastermind_company_mcp.schemas import (
    GatewayError,
    error_envelope,
    result_envelope,
    validate_tool_arguments,
)
from integrations.slack_agent_dialogue.contract import (
    FABLE_MESSAGE_TYPES,
    DialogueContractError,
)
from integrations.slack_agent_dialogue.contract_v2 import (
    MESSAGE_SCHEMA_V2,
    build_message_v2,
)
from integrations.slack_agent_dialogue.engine import (
    ERROR_CODES as DIALOGUE_ENGINE_ERROR_CODES,
    DialogueEngineError,
)
from integrations.slack_agent_dialogue.engine_v2 import DialogueContextV2
from integrations.slack_agent_dialogue.service import (
    CONTROL_VERSION_V2,
    ERROR_CODES as DIALOGUE_SERVICE_ERROR_CODES,
    DialogueServiceError,
    call_service,
)

_THREAD_TS_RE = re.compile(r"\A[0-9]{10,16}\.[0-9]{6}\Z")
_DETAIL_CODE_RE = re.compile(r"\A[A-Z][A-Z0-9_]{1,63}\Z")
_DOWNSTREAM_ERROR_CODES = DIALOGUE_ENGINE_ERROR_CODES | DIALOGUE_SERVICE_ERROR_CODES
_UNAVAILABLE_DETAIL_CODES = {
    "PEER_CREDENTIALS_UNAVAILABLE",
    "SERVICE_UNAVAILABLE",
    "TRANSPORT_UNAVAILABLE",
}

_MESSAGE_TYPES = {
    "ack": "ACK",
    "progress": "PROGRESS",
    "blocked": "BLOCKED",
    "request_decision": "DECISION_REQUEST",
    "result": "RESULT",
}
_SUMMARIES = {
    "ack": "Bounded dialogue context acknowledged.",
    "request_decision": "Decision requested.",
}


def _error(
    tool_name: str,
    code: str,
    *,
    detail_code: str | None = None,
    reconciliation_message_key: str | None = None,
) -> dict[str, Any]:
    return error_envelope(
        tool_name,
        code=code,
        message=code,
        detail_code=detail_code,
        reconciliation_message_key=reconciliation_message_key,
    )


@dataclass(frozen=True)
class DialogueBinding:
    """Trusted resolver output; none of these fields are model inputs."""

    actor_ref: Mapping[str, Any]
    work_ref: str
    commission_ref: Mapping[str, Any]
    session_ref: str
    operation_key: str
    watch_mode: str | None
    applies_to: Mapping[str, Any]
    thread_ts: str
    allowed_message_types: tuple[str, ...]
    reply_to_message_key: str | None = None


class DialogueBindingResolver(Protocol):
    """Host-owned, zero-input resolver for the active commissioned context."""

    def resolve(self) -> DialogueBinding: ...


ServiceCall = Callable[[Path, Mapping[str, Any]], Awaitable[dict[str, Any]]]
UuidSource = Callable[[], uuid.UUID]
UtcNow = Callable[[], str]


def _default_utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class CompanyDialogueGateway:
    """One-call gateway with no persistence, retry, or target-selection power."""

    def __init__(
        self,
        binding_resolver: DialogueBindingResolver,
        *,
        socket_path: Path,
        service_call: ServiceCall = call_service,
        uuid_source: UuidSource = uuid.uuid4,
        utc_now: UtcNow = _default_utc_now,
    ) -> None:
        path = Path(socket_path)
        if not path.is_absolute():
            raise ValueError("socket_path must be absolute")
        self._binding_resolver = binding_resolver
        self._socket_path = path
        self._service_call = service_call
        self._uuid_source = uuid_source
        self._utc_now = utc_now

    @staticmethod
    def _binding_context(binding: DialogueBinding) -> dict[str, Any]:
        if not isinstance(binding, DialogueBinding):
            raise GatewayError("BINDING_UNAVAILABLE")
        allowed = binding.allowed_message_types
        if (
            not isinstance(allowed, tuple)
            or allowed != tuple(dict.fromkeys(allowed))
            or any(item not in FABLE_MESSAGE_TYPES for item in allowed)
        ):
            raise GatewayError("BINDING_UNAVAILABLE")
        if (
            not isinstance(binding.thread_ts, str)
            or _THREAD_TS_RE.fullmatch(binding.thread_ts) is None
        ):
            raise GatewayError("BINDING_UNAVAILABLE")
        try:
            return DialogueContextV2(
                work_ref=binding.work_ref,
                commission_ref=dict(binding.commission_ref),
                session_ref=binding.session_ref,
                operation_key=binding.operation_key,
                watch_mode=binding.watch_mode,
                actor_ref=dict(binding.actor_ref),
                applies_to=dict(binding.applies_to),
            ).normalized()
        except (DialogueEngineError, TypeError, ValueError):
            raise GatewayError("BINDING_UNAVAILABLE") from None

    def _message(
        self,
        tool_name: str,
        arguments: Mapping[str, Any],
        binding: DialogueBinding,
        context: Mapping[str, Any],
    ) -> dict[str, Any]:
        message_type = _MESSAGE_TYPES[tool_name]
        if message_type not in binding.allowed_message_types:
            raise GatewayError("DIALOGUE_REFUSED", "MESSAGE_TYPE_DENIED")
        evidence_refs = list(arguments.get("evidence_refs", []))
        body = {key: value for key, value in arguments.items() if key != "evidence_refs"}
        if message_type == "ACK":
            body = {"acknowledged": True}
        if tool_name == "progress":
            summary = f"Progress: {arguments['stage']}."
        elif tool_name == "blocked":
            summary = f"Blocked: {arguments['blocker_code']}."
        elif tool_name == "result":
            summary = f"Result: {arguments['status']}."
        else:
            summary = _SUMMARIES[tool_name]
        try:
            message_uuid = self._uuid_source()
            if not isinstance(message_uuid, uuid.UUID):
                raise TypeError
            return build_message_v2(
                {
                    "schema": MESSAGE_SCHEMA_V2,
                    "message_key": f"asd-mcp-{message_uuid.hex}",
                    "message_type": message_type,
                    "work_ref": context["work_ref"],
                    "commission_ref": context["commission_ref"],
                    "session_ref": context["session_ref"],
                    "actor_ref": context["actor_ref"],
                    "reply_to_message_key": binding.reply_to_message_key,
                    "applies_to": context["applies_to"],
                    "summary": summary,
                    "body": body,
                    "evidence_refs": evidence_refs,
                    "requires_response": message_type in {"BLOCKED", "DECISION_REQUEST"},
                    "created_at": self._utc_now(),
                }
            )
        except (DialogueContractError, KeyError, TypeError, ValueError):
            raise GatewayError("DIALOGUE_REFUSED") from None

    @staticmethod
    def _service_result(
        tool_name: str,
        response: Any,
        *,
        reconciliation_message_key: str | None,
    ) -> dict[str, Any]:
        if not isinstance(response, dict) or set(response) not in (
            {"ok", "result"},
            {"ok", "error"},
        ):
            return _error(
                tool_name,
                "INTERNAL_ERROR",
                reconciliation_message_key=reconciliation_message_key,
            )
        if response.get("ok") is True and set(response) == {"ok", "result"}:
            try:
                return result_envelope(tool_name, data=response["result"])
            except (GatewayError, TypeError, ValueError):
                return _error(
                    tool_name,
                    "INTERNAL_ERROR",
                    reconciliation_message_key=reconciliation_message_key,
                )
        error = response.get("error")
        if response.get("ok") is not False or not isinstance(error, dict) or set(error) != {"code"}:
            return _error(
                tool_name,
                "INTERNAL_ERROR",
                reconciliation_message_key=reconciliation_message_key,
            )
        detail_code = error.get("code")
        if (
            not isinstance(detail_code, str)
            or _DETAIL_CODE_RE.fullmatch(detail_code) is None
            or detail_code not in _DOWNSTREAM_ERROR_CODES
        ):
            return _error(
                tool_name,
                "INTERNAL_ERROR",
                reconciliation_message_key=reconciliation_message_key,
            )
        code = (
            "SERVICE_UNAVAILABLE"
            if detail_code in _UNAVAILABLE_DETAIL_CODES
            else "DIALOGUE_REFUSED"
        )
        return _error(
            tool_name,
            code,
            detail_code=detail_code,
            reconciliation_message_key=reconciliation_message_key,
        )

    async def call(self, tool_name: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
        """Perform exactly one resolved Dialogue V2 operation with no retry."""

        try:
            normalized_arguments = validate_tool_arguments(tool_name, arguments)
        except GatewayError as exc:
            return _error(tool_name, exc.code)

        try:
            binding = self._binding_resolver.resolve()
            context = self._binding_context(binding)
        except Exception:
            return _error(
                tool_name,
                "BINDING_UNAVAILABLE",
                detail_code="BINDING_UNAVAILABLE",
            )

        try:
            reconciliation_message_key = None
            if tool_name == "read_thread":
                operation = "read_thread"
                args = {"context": context, "thread_ts": binding.thread_ts}
            else:
                operation = "send_message"
                message = self._message(tool_name, normalized_arguments, binding, context)
                reconciliation_message_key = message["message_key"]
                args = {
                    "context": context,
                    "thread_ts": binding.thread_ts,
                    "message": message,
                }
        except GatewayError as exc:
            detail = str(exc) if _DETAIL_CODE_RE.fullmatch(str(exc)) else exc.code
            return _error(tool_name, exc.code, detail_code=detail)

        request = {"version": CONTROL_VERSION_V2, "operation": operation, "args": args}
        try:
            response = await self._service_call(self._socket_path, request)
        except DialogueServiceError as exc:
            code = (
                "SERVICE_UNAVAILABLE"
                if exc.code in _UNAVAILABLE_DETAIL_CODES
                else "DIALOGUE_REFUSED"
            )
            return _error(
                tool_name,
                code,
                detail_code=exc.code,
                reconciliation_message_key=reconciliation_message_key,
            )
        except Exception:
            return _error(
                tool_name,
                "SERVICE_UNAVAILABLE",
                detail_code="SERVICE_UNAVAILABLE",
                reconciliation_message_key=reconciliation_message_key,
            )
        return self._service_result(
            tool_name,
            response,
            reconciliation_message_key=reconciliation_message_key,
        )


__all__ = [
    "CompanyDialogueGateway",
    "DialogueBinding",
    "DialogueBindingResolver",
]
