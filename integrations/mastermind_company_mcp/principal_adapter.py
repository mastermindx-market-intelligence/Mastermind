"""Principal-only Company Dialogue adapter over the existing exact-send owner.

This facade consumes an already-resolved H6 principal binding. It selects no
mission, child, thread, identity, provider, account, host, or authority. Every
modifying call uses the existing Relay READY/COMMIT protocol and requires a
trusted host-supplied durable pre-COMMIT fence.
"""
from __future__ import annotations

import hashlib
import inspect
import re
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from integrations.mastermind_company_mcp.adapter import DialogueBinding
from integrations.mastermind_company_mcp.principal_schemas import (
    PrincipalGatewayError,
    canonical_principal_json,
    principal_error_envelope,
    principal_result_envelope,
    validate_principal_tool_arguments,
)
from integrations.slack_agent_dialogue.contract import DialogueContractError
from integrations.slack_agent_dialogue.contract_v2 import (
    MESSAGE_SCHEMA_V2,
    build_message_v2,
)
from integrations.slack_agent_dialogue.engine import (
    ERROR_CODES as DIALOGUE_ENGINE_ERROR_CODES,
)
from integrations.slack_agent_dialogue.engine_v2 import DialogueContextV2
from integrations.slack_agent_dialogue.service import (
    CONTROL_VERSION_V2,
    EXACT_SEND_PROTOCOL,
    ERROR_CODES as DIALOGUE_SERVICE_ERROR_CODES,
    DialogueServiceError,
    call_service,
)

PRINCIPAL_COMMIT_INTENT_SCHEMA = (
    "mastermind.company_dialogue_principal_commit_intent.v1"
)
PRINCIPAL_COMMIT_FENCE_RECEIPT_SCHEMA = (
    "mastermind.company_dialogue_principal_commit_fence_receipt.v1"
)
_PUBLIC_REF_RE = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._:@/-]{0,255}\Z")
_THREAD_TS_RE = re.compile(r"\A[0-9]{10,16}\.[0-9]{6}\Z")
_MESSAGE_KEY_RE = re.compile(r"\Aasd-[a-z0-9][a-z0-9-]{7,95}\Z")
_SHA64_RE = re.compile(r"\A[0-9a-f]{64}\Z")
_DETAIL_CODE_RE = re.compile(r"\A[A-Z][A-Z0-9_]{1,63}\Z")
_PRINCIPAL_MESSAGES = ("RULING", "CONTINUE", "STOP")
_DOWNSTREAM_ERROR_CODES = DIALOGUE_ENGINE_ERROR_CODES | DIALOGUE_SERVICE_ERROR_CODES
_UNAVAILABLE_DETAIL_CODES = {
    "PEER_CREDENTIALS_UNAVAILABLE",
    "SERVICE_UNAVAILABLE",
    "TRANSPORT_UNAVAILABLE",
}
_TOOL_TO_MESSAGE = {
    "ruling": "RULING",
    "continue": "CONTINUE",
    "stop": "STOP",
}
_SUMMARIES = {
    "ruling": "COO ruling returned.",
    "continue": "COO continuation returned.",
    "stop": "COO terminal stop returned.",
}


class PrincipalDialogueBindingResolver(Protocol):
    """Host-owned resolver for one exact current principal→child carrier."""

    def resolve(self) -> DialogueBinding: ...


@dataclass(frozen=True)
class PrincipalCommitIntent:
    """Public, secret-free facts a durable effect owner must fence before COMMIT."""

    schema: str
    work_ref: str
    session_ref: str
    operation_key: str
    thread_ts: str
    reply_to_message_key: str
    message_key: str
    message_fingerprint: str
    message_type: str
    principal_binding_digest: str
    authority_generation_digest: str
    capability_profile_digest: str
    child_job_id: str
    child_attempt_id: str
    child_worker_id: str

    def to_dict(self) -> dict[str, str]:
        return {
            field: str(getattr(self, field))
            for field in self.__dataclass_fields__
        }

    def digest(self) -> str:
        return hashlib.sha256(canonical_principal_json(self.to_dict())).hexdigest()


@dataclass(frozen=True)
class PrincipalCommitFenceReceipt:
    """Proof that an existing durable owner fenced this exact semantic edge."""

    schema: str
    intent_sha256: str
    durable_ref: str

    @classmethod
    def for_intent(
        cls, intent: PrincipalCommitIntent, *, durable_ref: str
    ) -> "PrincipalCommitFenceReceipt":
        return cls(
            schema=PRINCIPAL_COMMIT_FENCE_RECEIPT_SCHEMA,
            intent_sha256=intent.digest(),
            durable_ref=durable_ref,
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "schema": self.schema,
            "intent_sha256": self.intent_sha256,
            "durable_ref": self.durable_ref,
        }


BeforeCommit = Callable[[PrincipalCommitIntent], Any]
ServiceCall = Callable[..., Awaitable[dict[str, Any]]]
UtcNow = Callable[[], str]


def _default_utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class _CommitFenceRefused(RuntimeError):
    pass


def _error(
    tool_name: str,
    code: str,
    *,
    detail_code: str | None = None,
    reconciliation_message_key: str | None = None,
) -> dict[str, Any]:
    return principal_error_envelope(
        tool_name,
        code=code,
        message=code,
        detail_code=detail_code,
        reconciliation_message_key=reconciliation_message_key,
    )


class PrincipalCompanyDialogueGateway:
    """One exact principal dialogue edge; no retry or target-selection authority."""

    def __init__(
        self,
        binding_resolver: PrincipalDialogueBindingResolver,
        *,
        socket_path: Path,
        before_commit: BeforeCommit,
        service_call: ServiceCall = call_service,
        utc_now: UtcNow = _default_utc_now,
    ) -> None:
        path = Path(socket_path)
        if not path.is_absolute():
            raise ValueError("socket_path must be absolute")
        if not callable(before_commit):
            raise TypeError("before_commit must be callable")
        self._binding_resolver = binding_resolver
        self._socket_path = path
        if not callable(utc_now):
            raise TypeError("utc_now must be callable")
        self._before_commit = before_commit
        self._service_call = service_call
        self._utc_now = utc_now

    @staticmethod
    def _binding_context(
        binding: DialogueBinding,
    ) -> dict[str, Any]:
        if not isinstance(binding, DialogueBinding):
            raise PrincipalGatewayError("BINDING_UNAVAILABLE")
        if binding.allowed_message_types != _PRINCIPAL_MESSAGES:
            raise PrincipalGatewayError("BINDING_UNAVAILABLE")
        if (
            not isinstance(binding.thread_ts, str)
            or _THREAD_TS_RE.fullmatch(binding.thread_ts) is None
            or not isinstance(binding.reply_to_message_key, str)
            or _MESSAGE_KEY_RE.fullmatch(binding.reply_to_message_key) is None
        ):
            raise PrincipalGatewayError("BINDING_UNAVAILABLE")
        actor = binding.actor_ref
        applies = binding.applies_to
        if (
            not isinstance(actor, Mapping)
            or actor.get("kind") != "executive_principal"
            or actor.get("seat") != "coo"
            or not isinstance(applies, Mapping)
            or applies.get("kind") != "executive_attempt"
        ):
            raise PrincipalGatewayError("BINDING_UNAVAILABLE")
        try:
            return DialogueContextV2(
                work_ref=binding.work_ref,
                commission_ref=dict(binding.commission_ref),
                session_ref=binding.session_ref,
                operation_key=binding.operation_key,
                watch_mode=binding.watch_mode,
                actor_ref=dict(actor),
                applies_to=dict(applies),
            ).normalized()
        except (DialogueContractError, Exception) as exc:
            # Keep the provider-facing error fixed; no private binding detail leaks.
            if isinstance(exc, PrincipalGatewayError):
                raise
            raise PrincipalGatewayError("BINDING_UNAVAILABLE") from None

    @staticmethod
    def _edge_message_key(
        binding: DialogueBinding,
        context: Mapping[str, Any],
    ) -> str:
        """One semantic reply slot per exact child return, independent of body/actor generation."""

        edge_identity = {
            "work_ref": context["work_ref"],
            "commission_ref": context["commission_ref"],
            "session_ref": context["session_ref"],
            "operation_key": context["operation_key"],
            "applies_to": context["applies_to"],
            "thread_ts": binding.thread_ts,
            "reply_to_message_key": binding.reply_to_message_key,
        }
        digest = hashlib.sha256(canonical_principal_json(edge_identity)).hexdigest()
        return f"asd-principal-{digest[:32]}"

    def _message(
        self,
        tool_name: str,
        arguments: Mapping[str, Any],
        binding: DialogueBinding,
        context: Mapping[str, Any],
    ) -> dict[str, Any]:
        message_type = _TOOL_TO_MESSAGE[tool_name]
        if message_type not in binding.allowed_message_types:
            raise PrincipalGatewayError("DIALOGUE_REFUSED", "MESSAGE_TYPE_DENIED")
        body = {
            key: value
            for key, value in arguments.items()
            if key != "evidence_refs"
        }
        evidence_refs = list(arguments.get("evidence_refs", []))
        try:
            return build_message_v2(
                {
                    "schema": MESSAGE_SCHEMA_V2,
                    "message_key": self._edge_message_key(binding, context),
                    "message_type": message_type,
                    "work_ref": context["work_ref"],
                    "commission_ref": context["commission_ref"],
                    "session_ref": context["session_ref"],
                    "actor_ref": context["actor_ref"],
                    "reply_to_message_key": binding.reply_to_message_key,
                    "applies_to": context["applies_to"],
                    "summary": _SUMMARIES[tool_name],
                    "body": body,
                    "evidence_refs": evidence_refs,
                    "requires_response": False,
                    "created_at": self._utc_now(),
                }
            )
        except (DialogueContractError, KeyError, TypeError, ValueError):
            raise PrincipalGatewayError("DIALOGUE_REFUSED") from None

    @staticmethod
    def _commit_intent(
        binding: DialogueBinding,
        context: Mapping[str, Any],
        message: Mapping[str, Any],
    ) -> PrincipalCommitIntent:
        actor = context["actor_ref"]
        applies = context["applies_to"]
        return PrincipalCommitIntent(
            schema=PRINCIPAL_COMMIT_INTENT_SCHEMA,
            work_ref=str(context["work_ref"]),
            session_ref=str(context["session_ref"]),
            operation_key=str(context["operation_key"]),
            thread_ts=binding.thread_ts,
            reply_to_message_key=str(binding.reply_to_message_key),
            message_key=str(message["message_key"]),
            message_fingerprint=str(message["fingerprint"]),
            message_type=str(message["message_type"]),
            principal_binding_digest=str(actor["principal_binding_digest"]),
            authority_generation_digest=str(actor["authority_generation_digest"]),
            capability_profile_digest=str(actor["capability_profile_digest"]),
            child_job_id=str(applies["job_id"]),
            child_attempt_id=str(applies["attempt_id"]),
            child_worker_id=str(applies["worker_id"]),
        )

    async def _fence(self, intent: PrincipalCommitIntent) -> None:
        try:
            outcome = self._before_commit(intent)
            if inspect.isawaitable(outcome):
                outcome = await outcome
            if (
                not isinstance(outcome, PrincipalCommitFenceReceipt)
                or outcome.schema != PRINCIPAL_COMMIT_FENCE_RECEIPT_SCHEMA
                or outcome.intent_sha256 != intent.digest()
                or not isinstance(outcome.durable_ref, str)
                or _PUBLIC_REF_RE.fullmatch(outcome.durable_ref) is None
            ):
                raise ValueError("durable fence receipt mismatch")
        except Exception:
            raise _CommitFenceRefused() from None

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
                return principal_result_envelope(tool_name, data=response["result"])
            except (PrincipalGatewayError, TypeError, ValueError):
                return _error(
                    tool_name,
                    "INTERNAL_ERROR",
                    reconciliation_message_key=reconciliation_message_key,
                )
        error = response.get("error")
        if (
            response.get("ok") is not False
            or not isinstance(error, dict)
            or set(error) != {"code"}
        ):
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

    async def call(
        self, tool_name: str, arguments: Mapping[str, Any] | None
    ) -> dict[str, Any]:
        """Read once or execute one fenced READY→COMMIT principal edge."""

        try:
            normalized_arguments = validate_principal_tool_arguments(
                tool_name, arguments or {}
            )
        except PrincipalGatewayError as exc:
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

        if tool_name == "read_thread":
            request = {
                "version": CONTROL_VERSION_V2,
                "operation": "read_thread",
                "args": {
                    "context": context,
                    "thread_ts": binding.thread_ts,
                },
            }
            try:
                response = await self._service_call(self._socket_path, request)
            except DialogueServiceError as exc:
                code = (
                    "SERVICE_UNAVAILABLE"
                    if exc.code in _UNAVAILABLE_DETAIL_CODES
                    else "DIALOGUE_REFUSED"
                )
                return _error(tool_name, code, detail_code=exc.code)
            except Exception:
                return _error(
                    tool_name,
                    "SERVICE_UNAVAILABLE",
                    detail_code="SERVICE_UNAVAILABLE",
                )
            return self._service_result(
                tool_name,
                response,
                reconciliation_message_key=None,
            )

        message_key: str | None = None
        try:
            message = self._message(
                tool_name,
                normalized_arguments,
                binding,
                context,
            )
            message_key = str(message["message_key"])
            intent = self._commit_intent(binding, context, message)
            request = {
                "version": CONTROL_VERSION_V2,
                "operation": "send_message",
                "args": {
                    "context": context,
                    "thread_ts": binding.thread_ts,
                    "message": message,
                    "send_protocol": EXACT_SEND_PROTOCOL,
                },
            }

            async def before_write() -> None:
                await self._fence(intent)

            response = await self._service_call(
                self._socket_path,
                request,
                before_write=before_write,
            )
        except _CommitFenceRefused:
            return _error(
                tool_name,
                "EFFECT_FENCE_UNAVAILABLE",
                reconciliation_message_key=message_key,
            )
        except DialogueServiceError as exc:
            if exc.code == "SEND_EFFECT_UNKNOWN":
                return _error(
                    tool_name,
                    "EFFECT_UNKNOWN",
                    detail_code=exc.code,
                    reconciliation_message_key=message_key,
                )
            code = (
                "SERVICE_UNAVAILABLE"
                if exc.code in _UNAVAILABLE_DETAIL_CODES
                else "DIALOGUE_REFUSED"
            )
            return _error(
                tool_name,
                code,
                detail_code=exc.code,
                reconciliation_message_key=message_key,
            )
        except PrincipalGatewayError as exc:
            return _error(tool_name, exc.code)
        except Exception:
            return _error(
                tool_name,
                "SERVICE_UNAVAILABLE",
                reconciliation_message_key=message_key,
            )
        return self._service_result(
            tool_name,
            response,
            reconciliation_message_key=message_key,
        )


__all__ = [
    "BeforeCommit",
    "PRINCIPAL_COMMIT_FENCE_RECEIPT_SCHEMA",
    "PRINCIPAL_COMMIT_INTENT_SCHEMA",
    "PrincipalCommitFenceReceipt",
    "PrincipalCommitIntent",
    "PrincipalCompanyDialogueGateway",
    "PrincipalDialogueBindingResolver",
]
