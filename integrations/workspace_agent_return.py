"""Bounded Workspace Agent candidate return over the existing Agent Dialogue owner.

This is intentionally not a result-acceptance API. A Workspace Agent receives one
short-lived signed return reference, then may emit one bounded RESULT-shaped
candidate into the already-owned Agent Dialogue carrier. The carrier receipt is
transport evidence only: it does not complete an Executive Job, accept a result,
grant Wake acknowledgement, change responsibility, or create a new lifecycle plane.

The signed reference is stateless. It binds one message identity to one exact
current DialogueBinding digest and operation key. On return, the host re-resolves
the current binding and must match the frozen digest before any send is attempted.
"""
from __future__ import annotations

import base64
import copy
import dataclasses
import hashlib
import hmac
import json
import re
from collections.abc import Awaitable, Callable, Mapping
from pathlib import Path
from typing import Any, Protocol

from integrations.mastermind_company_mcp.adapter import DialogueBinding
from integrations.slack_agent_dialogue.contract import (
    MAX_EVIDENCE_REFS,
    DialogueContractError,
    validate_body,
    validate_evidence_ref,
)
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
    ERROR_CODES as DIALOGUE_SERVICE_ERROR_CODES,
    DialogueServiceError,
    call_service,
)

RETURN_TICKET_SCHEMA = "mastermind.workspace_agent_return_ticket.v1"
RETURN_TICKET_PURPOSE = "workspace_candidate_return"
RETURN_RESULT_SCHEMA = "mastermind.workspace_agent_candidate_return.v1"
MAX_RETURN_REF_BYTES = 4096
MAX_REQUEST_BYTES = 32 * 1024
MAX_TICKET_TTL_MS = 15 * 60 * 1000
WORKSPACE_ACTOR_REF = {
    "kind": "executive_surface",
    "seat": "coo",
    "reasoning_surface": "workspace-agent",
}
_STATUS = frozenset({"PASS", "PARTIAL", "BLOCKED", "FAIL"})
_SHA256 = re.compile(r"\A[0-9a-f]{64}\Z")
_TICKET_ID = re.compile(r"\Awr-[a-z0-9][a-z0-9-]{7,91}\Z")
_MESSAGE_KEY = re.compile(r"\Aasd-wsa-[0-9a-f]{32}\Z")
_THREAD_TS = re.compile(r"\A[1-9][0-9]{9,15}\.[0-9]{6}\Z")
_DOWNSTREAM_ERRORS = DIALOGUE_ENGINE_ERROR_CODES | DIALOGUE_SERVICE_ERROR_CODES
_NO_EFFECT_ERRORS = frozenset(
    {
        "SERVICE_UNAVAILABLE",
        "PEER_CREDENTIALS_UNAVAILABLE",
        "REQUEST_INVALID",
        "REQUEST_TOO_LARGE",
    }
)


class WorkspaceReturnError(RuntimeError):
    """Fixed-code refusal. Rejected values and provider prose never cross it."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclasses.dataclass(frozen=True)
class WorkspaceReturnTicket:
    schema: str
    purpose: str
    ticket_id: str
    operation_key: str
    binding_digest: str
    message_key: str
    issued_at_ms: int
    expires_at_ms: int


class WorkspaceReturnBindingResolver(Protocol):
    """Resolve the current canonical dialogue binding for one operation key."""

    def resolve(self, operation_key: str) -> DialogueBinding: ...


ServiceCall = Callable[[Path, Mapping[str, Any]], Awaitable[dict[str, Any]]]


def _canonical_json(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
    except (TypeError, ValueError, UnicodeError, RecursionError):
        raise WorkspaceReturnError("INVALID_REQUEST") from None


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    if type(value) is not str or not value or any(ord(c) > 127 for c in value):
        raise WorkspaceReturnError("INVALID_RETURN_REF")
    padding = "=" * ((4 - len(value) % 4) % 4)
    try:
        return base64.b64decode(
            value + padding,
            altchars=b"-_",
            validate=True,
        )
    except (ValueError, TypeError):
        raise WorkspaceReturnError("INVALID_RETURN_REF") from None


def _operation_key(value: Any) -> str:
    if (
        type(value) is not str
        or not 1 <= len(value) <= 256
        or not value.isascii()
        or any(ord(c) < 33 or ord(c) > 126 for c in value)
    ):
        raise WorkspaceReturnError("INVALID_RETURN_REF")
    return value


def _ticket_document(ticket: WorkspaceReturnTicket) -> dict[str, Any]:
    if not isinstance(ticket, WorkspaceReturnTicket):
        raise WorkspaceReturnError("INVALID_RETURN_REF")
    value = dataclasses.asdict(ticket)
    if (
        value["schema"] != RETURN_TICKET_SCHEMA
        or value["purpose"] != RETURN_TICKET_PURPOSE
        or type(value["ticket_id"]) is not str
        or _TICKET_ID.fullmatch(value["ticket_id"]) is None
        or _operation_key(value["operation_key"]) != value["operation_key"]
        or type(value["binding_digest"]) is not str
        or _SHA256.fullmatch(value["binding_digest"]) is None
        or type(value["message_key"]) is not str
        or _MESSAGE_KEY.fullmatch(value["message_key"]) is None
        or type(value["issued_at_ms"]) is not int
        or isinstance(value["issued_at_ms"], bool)
        or type(value["expires_at_ms"]) is not int
        or isinstance(value["expires_at_ms"], bool)
        or value["issued_at_ms"] < 0
        or value["expires_at_ms"] <= value["issued_at_ms"]
        or value["expires_at_ms"] - value["issued_at_ms"] > MAX_TICKET_TTL_MS
    ):
        raise WorkspaceReturnError("INVALID_RETURN_REF")
    return value


def _binding_document(binding: DialogueBinding) -> dict[str, Any]:
    if not isinstance(binding, DialogueBinding):
        raise WorkspaceReturnError("BINDING_UNAVAILABLE")
    if (
        not isinstance(binding.allowed_message_types, tuple)
        or "RESULT" not in binding.allowed_message_types
        or binding.allowed_message_types != tuple(dict.fromkeys(binding.allowed_message_types))
        or not isinstance(binding.thread_ts, str)
        or _THREAD_TS.fullmatch(binding.thread_ts) is None
    ):
        raise WorkspaceReturnError("BINDING_UNAVAILABLE")
    try:
        context = DialogueContextV2(
            work_ref=binding.work_ref,
            commission_ref=dict(binding.commission_ref),
            session_ref=binding.session_ref,
            operation_key=binding.operation_key,
            watch_mode=binding.watch_mode,
            actor_ref=dict(binding.actor_ref),
            applies_to=dict(binding.applies_to),
        ).normalized()
    except Exception:
        raise WorkspaceReturnError("BINDING_UNAVAILABLE") from None
    reply = binding.reply_to_message_key
    if reply is not None and (not isinstance(reply, str) or len(reply) > 128):
        raise WorkspaceReturnError("BINDING_UNAVAILABLE")
    return {
        "context": context,
        "thread_ts": binding.thread_ts,
        "allowed_message_types": list(binding.allowed_message_types),
        "reply_to_message_key": reply,
    }


def binding_digest(binding: DialogueBinding) -> str:
    """One-way identity of the current target/dialogue binding."""

    return hashlib.sha256(_canonical_json(_binding_document(binding))).hexdigest()


class WorkspaceReturnTicketCodec:
    """Stateless HMAC envelope for exactly one bounded candidate-return message."""

    def __init__(self, key: bytes) -> None:
        if type(key) is not bytes or len(key) < 32:
            raise ValueError("workspace return key must contain at least 32 bytes")
        self._key = bytes(key)

    def _signature(self, payload: bytes) -> bytes:
        material = RETURN_TICKET_SCHEMA.encode("ascii") + b"\x00" + payload
        return hmac.new(self._key, material, hashlib.sha256).digest()

    def mint(
        self,
        *,
        binding: DialogueBinding,
        ticket_id: str,
        issued_at_ms: int,
        expires_at_ms: int,
    ) -> str:
        document = _binding_document(binding)
        if type(ticket_id) is not str or _TICKET_ID.fullmatch(ticket_id) is None:
            raise WorkspaceReturnError("INVALID_TICKET_ID")
        if (
            type(issued_at_ms) is not int
            or isinstance(issued_at_ms, bool)
            or type(expires_at_ms) is not int
            or isinstance(expires_at_ms, bool)
            or issued_at_ms < 0
            or expires_at_ms <= issued_at_ms
            or expires_at_ms - issued_at_ms > MAX_TICKET_TTL_MS
        ):
            raise WorkspaceReturnError("INVALID_TICKET_TIME")
        digest = hashlib.sha256(_canonical_json(document)).hexdigest()
        message_key = "asd-wsa-" + hashlib.sha256(
            (ticket_id + "\x00" + digest).encode("ascii")
        ).hexdigest()[:32]
        ticket = WorkspaceReturnTicket(
            schema=RETURN_TICKET_SCHEMA,
            purpose=RETURN_TICKET_PURPOSE,
            ticket_id=ticket_id,
            operation_key=binding.operation_key,
            binding_digest=digest,
            message_key=message_key,
            issued_at_ms=issued_at_ms,
            expires_at_ms=expires_at_ms,
        )
        payload = _canonical_json(_ticket_document(ticket))
        token = _b64encode(payload) + "." + _b64encode(self._signature(payload))
        if len(token.encode("ascii")) > MAX_RETURN_REF_BYTES:
            raise WorkspaceReturnError("RETURN_REF_TOO_LARGE")
        return token

    def decode(self, token: object, *, now_ms: int) -> WorkspaceReturnTicket:
        if (
            type(token) is not str
            or not token
            or len(token.encode("utf-8")) > MAX_RETURN_REF_BYTES
            or token.count(".") != 1
            or type(now_ms) is not int
            or isinstance(now_ms, bool)
            or now_ms < 0
        ):
            raise WorkspaceReturnError("INVALID_RETURN_REF")
        payload_part, signature_part = token.split(".", 1)
        payload = _b64decode(payload_part)
        signature = _b64decode(signature_part)
        if len(signature) != hashlib.sha256().digest_size or not hmac.compare_digest(
            signature, self._signature(payload)
        ):
            raise WorkspaceReturnError("INVALID_RETURN_REF")
        try:
            value = json.loads(payload.decode("ascii"))
        except (ValueError, UnicodeError, RecursionError):
            raise WorkspaceReturnError("INVALID_RETURN_REF") from None
        if not isinstance(value, dict) or set(value) != {
            "schema",
            "purpose",
            "ticket_id",
            "operation_key",
            "binding_digest",
            "message_key",
            "issued_at_ms",
            "expires_at_ms",
        }:
            raise WorkspaceReturnError("INVALID_RETURN_REF")
        try:
            ticket = WorkspaceReturnTicket(**value)
            _ticket_document(ticket)
        except (TypeError, WorkspaceReturnError):
            raise WorkspaceReturnError("INVALID_RETURN_REF") from None
        if now_ms > ticket.expires_at_ms:
            raise WorkspaceReturnError("RETURN_REF_EXPIRED")
        if now_ms < ticket.issued_at_ms:
            raise WorkspaceReturnError("RETURN_REF_NOT_YET_VALID")
        return ticket


def _validate_arguments(arguments: Any) -> dict[str, Any]:
    if not isinstance(arguments, Mapping):
        raise WorkspaceReturnError("INVALID_REQUEST")
    raw = copy.deepcopy(dict(arguments))
    if len(_canonical_json(raw)) > MAX_REQUEST_BYTES:
        raise WorkspaceReturnError("INVALID_REQUEST")
    if not {"return_ref", "status", "result"} <= set(raw) or not set(raw) <= {
        "return_ref",
        "status",
        "result",
        "evidence_refs",
    }:
        raise WorkspaceReturnError("INVALID_REQUEST")
    if (
        type(raw["return_ref"]) is not str
        or not raw["return_ref"]
        or len(raw["return_ref"].encode("utf-8")) > MAX_RETURN_REF_BYTES
    ):
        raise WorkspaceReturnError("INVALID_REQUEST")
    try:
        body = validate_body(
            "RESULT",
            {"status": raw["status"], "result": raw["result"]},
        )
    except DialogueContractError:
        raise WorkspaceReturnError("INVALID_REQUEST") from None
    evidence = raw.get("evidence_refs", [])
    if (
        not isinstance(evidence, list)
        or len(evidence) > MAX_EVIDENCE_REFS
        or len(evidence) != len(set(evidence))
    ):
        raise WorkspaceReturnError("INVALID_REQUEST")
    try:
        refs = [validate_evidence_ref(item) for item in evidence]
    except DialogueContractError:
        raise WorkspaceReturnError("INVALID_REQUEST") from None
    return {
        "return_ref": raw["return_ref"],
        "status": body["status"],
        "result": body["result"],
        "evidence_refs": refs,
    }


def _error(code: str, *, message_key: str | None = None) -> dict[str, Any]:
    value: dict[str, Any] = {
        "schema": RETURN_RESULT_SCHEMA,
        "ok": False,
        "state": code,
    }
    if message_key is not None and _MESSAGE_KEY.fullmatch(message_key):
        value["message_key"] = message_key
    return value


def _success(*, message_key: str, action: str) -> dict[str, Any]:
    return {
        "schema": RETURN_RESULT_SCHEMA,
        "ok": True,
        "state": "CANDIDATE_RECORDED",
        "message_key": message_key,
        "transport_action": action,
        "accepted": False,
        "wake_acknowledged": False,
    }


class WorkspaceCandidateReturnGateway:
    """One-call, no-retry Workspace candidate ingress over Agent Dialogue."""

    def __init__(
        self,
        *,
        codec: WorkspaceReturnTicketCodec,
        binding_resolver: WorkspaceReturnBindingResolver,
        socket_path: Path,
        clock_ms: Callable[[], int],
        utc_now: Callable[[], str],
        service_call: ServiceCall = call_service,
    ) -> None:
        path = Path(socket_path)
        if not path.is_absolute():
            raise ValueError("socket_path must be absolute")
        self._codec = codec
        self._binding_resolver = binding_resolver
        self._socket_path = path
        self._clock_ms = clock_ms
        self._utc_now = utc_now
        self._service_call = service_call

    async def call(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        """Return one bounded candidate; never retries or accepts it as company truth."""

        try:
            normalized = _validate_arguments(arguments)
            now_ms = self._clock_ms()
            ticket = self._codec.decode(normalized["return_ref"], now_ms=now_ms)
        except WorkspaceReturnError as exc:
            return _error(exc.code)
        except Exception:
            return _error("INVALID_REQUEST")

        message_key = ticket.message_key
        try:
            current = self._binding_resolver.resolve(ticket.operation_key)
            current_document = _binding_document(current)
            if binding_digest(current) != ticket.binding_digest:
                return _error("CURRENT_TARGET_CHANGED", message_key=message_key)
            if current.operation_key != ticket.operation_key:
                return _error("CURRENT_TARGET_CHANGED", message_key=message_key)
            context = DialogueContextV2(
                work_ref=current.work_ref,
                commission_ref=dict(current.commission_ref),
                session_ref=current.session_ref,
                operation_key=current.operation_key,
                watch_mode=current.watch_mode,
                actor_ref=WORKSPACE_ACTOR_REF,
                applies_to=dict(current.applies_to),
            ).normalized()
            message = build_message_v2(
                {
                    "schema": MESSAGE_SCHEMA_V2,
                    "message_key": message_key,
                    "message_type": "RESULT",
                    "work_ref": context["work_ref"],
                    "commission_ref": context["commission_ref"],
                    "session_ref": context["session_ref"],
                    "actor_ref": context["actor_ref"],
                    "reply_to_message_key": current_document["reply_to_message_key"],
                    "applies_to": context["applies_to"],
                    "summary": f"Workspace candidate: {normalized['status']}.",
                    "body": {
                        "status": normalized["status"],
                        "result": normalized["result"],
                    },
                    "evidence_refs": normalized["evidence_refs"],
                    "requires_response": False,
                    "created_at": self._utc_now(),
                }
            )
        except WorkspaceReturnError as exc:
            return _error(exc.code, message_key=message_key)
        except Exception:
            return _error("BINDING_UNAVAILABLE", message_key=message_key)

        request = {
            "version": CONTROL_VERSION_V2,
            "operation": "send_message",
            "args": {
                "context": context,
                "thread_ts": current.thread_ts,
                "message": message,
            },
        }
        try:
            response = await self._service_call(self._socket_path, request)
        except DialogueServiceError as exc:
            if exc.code == "SEND_EFFECT_UNKNOWN":
                return _error("EFFECT_UNKNOWN", message_key=message_key)
            if exc.code in _NO_EFFECT_ERRORS:
                return _error("SERVICE_UNAVAILABLE", message_key=message_key)
            if exc.code in _DOWNSTREAM_ERRORS:
                return _error("RETURN_REFUSED", message_key=message_key)
            return _error("EFFECT_UNKNOWN", message_key=message_key)
        except Exception:
            return _error("EFFECT_UNKNOWN", message_key=message_key)

        if (
            not isinstance(response, Mapping)
            or set(response) != {"ok", "result"}
            or response.get("ok") is not True
            or not isinstance(response.get("result"), Mapping)
        ):
            return _error("EFFECT_UNKNOWN", message_key=message_key)
        receipt = dict(response["result"])
        required = {
            "action",
            "message_key",
            "fingerprint",
            "message_ts",
            "duplicate_timestamps",
            "thread_ts",
            "parent_author_user_id",
            "parent_fingerprint",
        }
        if (
            set(receipt) != required
            or receipt.get("message_key") != message_key
            or receipt.get("fingerprint") != message.get("fingerprint")
            or receipt.get("thread_ts") != current.thread_ts
            or receipt.get("action") not in {"POSTED", "RECOVERED", "DUPLICATE"}
            or receipt.get("duplicate_timestamps") != []
        ):
            return _error("EFFECT_UNKNOWN", message_key=message_key)
        return _success(message_key=message_key, action=str(receipt["action"]))


__all__ = [
    "MAX_RETURN_REF_BYTES",
    "MAX_TICKET_TTL_MS",
    "RETURN_RESULT_SCHEMA",
    "RETURN_TICKET_SCHEMA",
    "WorkspaceCandidateReturnGateway",
    "WorkspaceReturnBindingResolver",
    "WorkspaceReturnError",
    "WorkspaceReturnTicket",
    "WorkspaceReturnTicketCodec",
    "binding_digest",
]
