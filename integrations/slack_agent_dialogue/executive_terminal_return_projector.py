"""Bound one canonical Executive terminal candidate to Agent Dialogue V2.

The projector owns no binding persistence, parent creation, retry state, Slack
client, or Wake state.  Its resolver is a trusted host-owned seam; the result is
sent only through the existing peer-authenticated Agent Dialogue AF_UNIX
service and is reconciled by ``DialogueEngineV2``.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import re
from collections.abc import Awaitable, Callable, Mapping
from pathlib import Path
from typing import Any, Protocol

from control_plane.executive_terminal_return import (
    TerminalReturnCandidate,
    TerminalReturnProjectionError,
    reduce_terminal_return,
)
from control_plane.executive_delegation_identity import derive_delegation_identity
from integrations.mastermind_company_mcp.adapter import (
    DialogueBinding,
)
from integrations.slack_agent_dialogue.contract import (
    DialogueContractError,
    FABLE_MESSAGE_TYPES,
)
from integrations.slack_agent_dialogue.contract_v2 import (
    MESSAGE_SCHEMA_V2,
    build_message_v2,
)
from integrations.slack_agent_dialogue.engine import DialogueEngineError
from integrations.slack_agent_dialogue.engine_v2 import DialogueContextV2
from integrations.slack_agent_dialogue.service import (
    CONTROL_VERSION_V2,
    DialogueServiceError,
    EXACT_SEND_PROTOCOL,
    call_service,
)

_DIGEST_RE = re.compile(r"\A[0-9a-f]{64}\Z")
_THREAD_TS_RE = re.compile(r"\A[0-9]{10,16}\.[0-9]{6}\Z")
_SLACK_USER_ID_RE = re.compile(r"\A[UW][A-Z0-9]{8,31}\Z")
_RECEIPT_ACTIONS = frozenset({"POSTED", "RECOVERED", "DUPLICATE"})
_RELAY_PARENT_ATTESTATION = "mastermind.agent_dialogue.relay_parent/v1"
ServiceCall = Callable[
    [Path, Mapping[str, Any]], Awaitable[dict[str, Any]]
]


class TerminalReturnBindingResolver(Protocol):
    """Resolve only the exact candidate currently being projected."""

    def resolve(
        self, candidate: TerminalReturnCandidate
    ) -> "ResolvedTerminalReturnBinding | DialogueBinding": ...


@dataclasses.dataclass(frozen=True)
class ResolvedTerminalReturnBinding:
    """Runtime-attested V2 context; Relay alone selects the canonical parent."""

    work_ref: str
    commission_ref: dict[str, str]
    session_ref: str
    operation_key: str
    watch_mode: str | None
    actor_ref: dict[str, str]
    applies_to: dict[str, str]
    allowed_message_types: tuple[str, ...] = ("RESULT",)


class RuntimeTerminalReturnBindingResolver:
    """Revalidate one candidate against current immutable Runtime evidence."""

    def __init__(self, runtime_provider: Callable[[], Any]) -> None:
        if not callable(runtime_provider):
            raise TypeError("runtime_provider must be callable")
        self._runtime_provider = runtime_provider

    def resolve(
        self, candidate: TerminalReturnCandidate
    ) -> ResolvedTerminalReturnBinding:
        runtime = self._runtime_provider()
        material = runtime.validated_role_completion(
            candidate.job_id,
            expected_attempt_id=candidate.attempt_id,
        )
        if reduce_terminal_return(material=material) != candidate:
            raise ValueError("terminal-return candidate drifted from Runtime truth")
        source = material.dialogue_source
        if source is None:
            raise ValueError("terminal-return root has no dialogue admission")
        identity = derive_delegation_identity(material.job)
        if (
            identity.operation_key != candidate.operation_key
            or identity.session_ref != candidate.session_ref
            or identity.root_job_id != candidate.root_job_id
        ):
            raise ValueError("terminal-return delegation identity drifted")
        return ResolvedTerminalReturnBinding(
            work_ref=source.work_ref,
            commission_ref=_commission_ref_dict(source.commission_ref),
            session_ref=identity.session_ref,
            operation_key=identity.operation_key,
            watch_mode=source.watch_mode,
            actor_ref=_candidate_attempt_ref(candidate, kind="worker_attempt"),
            applies_to=_candidate_attempt_ref(candidate, kind="executive_attempt"),
        )


@dataclasses.dataclass(frozen=True)
class TerminalReturnProjectionReceipt:
    """Validated Agent Dialogue receipt; never an Executive lifecycle fact."""

    action: str
    message_key: str
    fingerprint: str
    message_ts: str
    duplicate_timestamps: tuple[str, ...]
    thread_ts: str
    parent_author_user_id: str
    parent_fingerprint: str


@dataclasses.dataclass(frozen=True)
class _RelayParentAttestation:
    """One immutable Relay-owned parent identity for a physical RESULT."""

    thread_ts: str
    parent_author_user_id: str
    parent_fingerprint: str


def _refuse(code: str) -> None:
    raise TerminalReturnProjectionError(code)


def _candidate_attempt_ref(candidate: TerminalReturnCandidate, *, kind: str) -> dict[str, str]:
    return {
        "kind": kind,
        "job_id": candidate.job_id,
        "attempt_id": candidate.attempt_id,
        "worker_id": candidate.worker_id,
    }


def _commission_ref_dict(value: Any) -> dict[str, str]:
    """Adapt the Runtime-owned immutable CommissionRef at the dialogue edge."""

    to_dict = getattr(value, "to_dict", None)
    raw = to_dict() if callable(to_dict) else value
    if not isinstance(raw, Mapping):
        raise TypeError("commission_ref must expose a mapping")
    return dict(raw)


def _normalize_binding(
    candidate: TerminalReturnCandidate,
    binding: ResolvedTerminalReturnBinding | DialogueBinding,
) -> tuple[dict[str, Any], str | None]:
    if not isinstance(binding, (ResolvedTerminalReturnBinding, DialogueBinding)):
        _refuse("DIALOGUE_BINDING_UNAVAILABLE")
    allowed = binding.allowed_message_types
    expected_thread_ts = (
        binding.thread_ts if isinstance(binding, DialogueBinding) else None
    )
    if (
        not isinstance(allowed, tuple)
        or any(not isinstance(item, str) for item in allowed)
        or allowed != tuple(dict.fromkeys(allowed))
        or "RESULT" not in allowed
        or any(item not in FABLE_MESSAGE_TYPES for item in allowed)
        or (
            isinstance(binding, DialogueBinding)
            and (
                binding.reply_to_message_key is not None
                or not isinstance(binding.thread_ts, str)
                or _THREAD_TS_RE.fullmatch(binding.thread_ts) is None
            )
        )
    ):
        _refuse("DIALOGUE_BINDING_UNAVAILABLE")
    try:
        normalized = DialogueContextV2(
            work_ref=binding.work_ref,
            commission_ref=dict(binding.commission_ref),
            session_ref=binding.session_ref,
            operation_key=binding.operation_key,
            watch_mode=binding.watch_mode,
            actor_ref=dict(binding.actor_ref),
            applies_to=dict(binding.applies_to),
        ).normalized()
    except (DialogueEngineError, TypeError, ValueError):
        _refuse("DIALOGUE_BINDING_UNAVAILABLE")
    source = candidate.dialogue_source
    try:
        source_commission_ref = (
            _commission_ref_dict(source.commission_ref)
            if source is not None
            else None
        )
    except TypeError:
        _refuse("DIALOGUE_BINDING_UNAVAILABLE")
    if (
        source is None
        or source.work_ref != normalized["work_ref"]
        or source_commission_ref != normalized["commission_ref"]
        or source.watch_mode != normalized["watch_mode"]
        or normalized["session_ref"] != candidate.session_ref
        or normalized["operation_key"] != candidate.operation_key
        or normalized["actor_ref"]
        != _candidate_attempt_ref(candidate, kind="worker_attempt")
        or normalized["applies_to"]
        != _candidate_attempt_ref(candidate, kind="executive_attempt")
    ):
        _refuse("DIALOGUE_BINDING_UNAVAILABLE")
    return normalized, expected_thread_ts


def _bound_thread(
    response: Any,
    *,
    expected_thread_ts: str | None,
) -> _RelayParentAttestation:
    """Validate one closed Relay-owned parent-attestation response."""

    if not isinstance(response, dict) or set(response) not in (
        {"ok", "result"},
        {"ok", "error"},
    ):
        _refuse("DIALOGUE_BINDING_UNAVAILABLE")
    if response.get("ok") is not True:
        error = response.get("error")
        code = error.get("code") if isinstance(error, dict) else None
        if code in {"SERVICE_UNAVAILABLE", "PEER_CREDENTIALS_UNAVAILABLE"}:
            _refuse("SERVICE_UNAVAILABLE")
        if code == "TRANSPORT_UNAVAILABLE":
            _refuse("TRANSPORT_UNAVAILABLE")
        _refuse("DIALOGUE_BINDING_UNAVAILABLE")
    result = response.get("result")
    if (
        not isinstance(result, dict)
        or set(result)
        != {
            "attestation",
            "thread_ts",
            "parent_author_user_id",
            "parent_fingerprint",
        }
        or result.get("attestation") != _RELAY_PARENT_ATTESTATION
        or (
            expected_thread_ts is not None
            and result.get("thread_ts") != expected_thread_ts
        )
        or not isinstance(result.get("thread_ts"), str)
        or _THREAD_TS_RE.fullmatch(result["thread_ts"]) is None
        or not isinstance(result.get("parent_author_user_id"), str)
        or _SLACK_USER_ID_RE.fullmatch(result["parent_author_user_id"]) is None
        or not isinstance(result.get("parent_fingerprint"), str)
        or _DIGEST_RE.fullmatch(result["parent_fingerprint"]) is None
    ):
        _refuse("DIALOGUE_BINDING_UNAVAILABLE")
    return _RelayParentAttestation(
        thread_ts=result["thread_ts"],
        parent_author_user_id=result["parent_author_user_id"],
        parent_fingerprint=result["parent_fingerprint"],
    )


def _build_message(
    candidate: TerminalReturnCandidate,
    context: Mapping[str, Any],
) -> dict[str, Any]:
    if (
        not isinstance(candidate, TerminalReturnCandidate)
        or candidate.runtime_status != "COMPLETED"
        or candidate.result_status != "RESULT"
        or not isinstance(candidate.terminal_evidence_digest, str)
        or _DIGEST_RE.fullmatch(candidate.terminal_evidence_digest) is None
        or candidate.message_key
        != f"asd-exec-result-{candidate.terminal_evidence_digest}"
        or candidate.role not in {"plan", "work", "review", "repair"}
        or any(
            not isinstance(value, str) or _DIGEST_RE.fullmatch(value) is None
            for value in (
                candidate.result_envelope_digest,
                candidate.terminal_evidence_digest,
                candidate.artifact_receipt_digest,
                candidate.validation_receipt_digest,
                candidate.effective_grant_digest,
            )
        )
        or not isinstance(candidate.summary, str)
    ):
        _refuse("DIALOGUE_REFUSED")
    if candidate.role == "review":
        if (
            not isinstance(candidate.review_verdict, str)
            or candidate.review_verdict not in ("approve", "reject")
        ):
            _refuse("DIALOGUE_REFUSED")
        body_status = "PASS" if candidate.review_verdict == "approve" else "FAIL"
    else:
        if candidate.review_verdict is not None:
            _refuse("DIALOGUE_REFUSED")
        body_status = "PASS"

    def envelope(result: str) -> dict[str, Any]:
        return {
            "schema": MESSAGE_SCHEMA_V2,
            "message_key": candidate.message_key,
            "message_type": "RESULT",
            "work_ref": context["work_ref"],
            "commission_ref": context["commission_ref"],
            "session_ref": context["session_ref"],
            "actor_ref": context["actor_ref"],
            "reply_to_message_key": None,
            "applies_to": context["applies_to"],
            "summary": f"Executive {candidate.role} terminal result.",
            "body": {"status": body_status, "result": result},
            "evidence_refs": [],
            "requires_response": False,
            "created_at": candidate.terminal_at,
        }

    def synopsis(*, include_summary: bool) -> str:
        result: dict[str, str] = {
            "schema": "mastermind.executive_terminal_result_synopsis/v1",
            "role": candidate.role,
            "outcome": body_status,
            "result_envelope_digest": candidate.result_envelope_digest,
            "terminal_evidence_digest": candidate.terminal_evidence_digest,
            "artifact_receipt_digest": candidate.artifact_receipt_digest,
            "validation_receipt_digest": candidate.validation_receipt_digest,
            "effective_grant_digest": candidate.effective_grant_digest,
        }
        if include_summary:
            result["summary"] = candidate.summary
        else:
            result["summary_sha256"] = hashlib.sha256(
                candidate.summary.encode("utf-8")
            ).hexdigest()
        return json.dumps(
            result,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )

    # RESULT always carries the stable evidence synopsis.  Contract-only
    # refusal of the raw summary (too large or unsafe) selects its digest form.
    try:
        return build_message_v2(envelope(synopsis(include_summary=True)))
    except DialogueContractError:
        try:
            return build_message_v2(envelope(synopsis(include_summary=False)))
        except DialogueContractError:
            _refuse("DIALOGUE_REFUSED")


def _receipt(
    response: Any,
    *,
    message: Mapping[str, Any],
    parent: _RelayParentAttestation,
) -> TerminalReturnProjectionReceipt:
    if not isinstance(response, dict) or set(response) not in (
        {"ok", "result"},
        {"ok", "error"},
    ):
        _refuse("EFFECT_UNKNOWN")
    if response.get("ok") is not True:
        error = response.get("error")
        code = error.get("code") if isinstance(error, dict) else None
        if code == "SEND_EFFECT_UNKNOWN":
            _refuse("EFFECT_UNKNOWN")
        if code == "TRANSPORT_UNAVAILABLE":
            _refuse("TRANSPORT_UNAVAILABLE")
        if code in {"SERVICE_UNAVAILABLE", "PEER_CREDENTIALS_UNAVAILABLE"}:
            _refuse("SERVICE_UNAVAILABLE")
        _refuse("DIALOGUE_REFUSED")
    value = response.get("result")
    if not isinstance(value, dict) or set(value) != {
        "action",
        "message_key",
        "fingerprint",
        "message_ts",
        "duplicate_timestamps",
        "thread_ts",
        "parent_author_user_id",
        "parent_fingerprint",
    }:
        _refuse("EFFECT_UNKNOWN")
    duplicates = value["duplicate_timestamps"]
    if (
        not isinstance(value["action"], str)
        or value["action"] not in _RECEIPT_ACTIONS
        or value["message_key"] != message["message_key"]
        or value["fingerprint"] != message["fingerprint"]
        or not isinstance(value["message_ts"], str)
        or _THREAD_TS_RE.fullmatch(value["message_ts"]) is None
        or value["thread_ts"] != parent.thread_ts
        or value["parent_author_user_id"] != parent.parent_author_user_id
        or value["parent_fingerprint"] != parent.parent_fingerprint
        or not isinstance(duplicates, list)
        or bool(duplicates)
        or any(
            not isinstance(item, str) or _THREAD_TS_RE.fullmatch(item) is None
            for item in duplicates
        )
        or len(duplicates) != len(set(duplicates))
    ):
        _refuse("EFFECT_UNKNOWN")
    return TerminalReturnProjectionReceipt(
        action=value["action"],
        message_key=value["message_key"],
        fingerprint=value["fingerprint"],
        message_ts=value["message_ts"],
        duplicate_timestamps=tuple(duplicates),
        thread_ts=value["thread_ts"],
        parent_author_user_id=value["parent_author_user_id"],
        parent_fingerprint=value["parent_fingerprint"],
    )


class ExecutiveTerminalReturnProjector:
    """Project one candidate through the existing Agent Dialogue service."""

    def __init__(
        self,
        binding_resolver: TerminalReturnBindingResolver,
        *,
        socket_path: Path,
        service_call: ServiceCall = call_service,
    ) -> None:
        path = Path(socket_path)
        if not path.is_absolute():
            raise ValueError("socket_path must be absolute")
        if not hasattr(binding_resolver, "resolve") or not callable(
            binding_resolver.resolve
        ):
            raise TypeError("binding_resolver must expose resolve()")
        if not callable(service_call):
            raise TypeError("service_call must be callable")
        self._binding_resolver = binding_resolver
        self._socket_path = path
        self._service_call = service_call

    def _resolve(
        self,
        candidate: TerminalReturnCandidate,
    ) -> tuple[dict[str, Any], str | None, dict[str, Any]]:
        if not isinstance(candidate, TerminalReturnCandidate):
            _refuse("DIALOGUE_REFUSED")
        try:
            binding = self._binding_resolver.resolve(candidate)
        except Exception:
            _refuse("DIALOGUE_BINDING_UNAVAILABLE")
        context, thread_ts = _normalize_binding(
            candidate,
            binding,
        )
        return context, thread_ts, _build_message(candidate, context)

    async def _bind(
        self,
        *,
        context: Mapping[str, Any],
        thread_ts: str | None,
    ) -> _RelayParentAttestation:
        bind_request = {
            "version": CONTROL_VERSION_V2,
            "operation": "bind_or_verify_relay_parent_thread",
            "args": {"context": context},
        }
        try:
            bound_response = await self._service_call(self._socket_path, bind_request)
        except DialogueServiceError as exc:
            if exc.code in {
                "SERVICE_UNAVAILABLE",
                "PEER_CREDENTIALS_UNAVAILABLE",
            }:
                _refuse("SERVICE_UNAVAILABLE")
            if exc.code == "TRANSPORT_UNAVAILABLE":
                _refuse("TRANSPORT_UNAVAILABLE")
            _refuse("DIALOGUE_BINDING_UNAVAILABLE")
        except TerminalReturnProjectionError:
            raise
        except Exception:
            _refuse("SERVICE_UNAVAILABLE")
        return _bound_thread(
            bound_response,
            expected_thread_ts=thread_ts,
        )

    async def project(
        self,
        candidate: TerminalReturnCandidate,
        *,
        before_write: Callable[[], Any] | None = None,
    ) -> TerminalReturnProjectionReceipt:
        context, expected_thread_ts, message = self._resolve(candidate)
        parent = await self._bind(
            context=context,
            thread_ts=expected_thread_ts,
        )
        request = {
            "version": CONTROL_VERSION_V2,
            "operation": "send_message",
            "args": {
                "context": context,
                "thread_ts": parent.thread_ts,
                "message": message,
                "send_protocol": EXACT_SEND_PROTOCOL,
            },
        }
        try:
            if before_write is None:
                response = await self._service_call(self._socket_path, request)
            else:
                response = await self._service_call(
                    self._socket_path,
                    request,
                    before_write=before_write,
                )
        except DialogueServiceError as exc:
            if exc.code == "SEND_EFFECT_UNKNOWN":
                _refuse("EFFECT_UNKNOWN")
            if exc.code == "TRANSPORT_UNAVAILABLE":
                _refuse("TRANSPORT_UNAVAILABLE")
            if exc.code in {
                "SERVICE_UNAVAILABLE",
                "PEER_CREDENTIALS_UNAVAILABLE",
            }:
                _refuse("SERVICE_UNAVAILABLE")
            _refuse("DIALOGUE_REFUSED")
        except TerminalReturnProjectionError:
            raise
        except Exception:
            _refuse("SERVICE_UNAVAILABLE")
        return _receipt(response, message=message, parent=parent)

    async def reconcile(
        self,
        candidate: TerminalReturnCandidate,
    ) -> TerminalReturnProjectionReceipt | None:
        """Read-only reconciliation after a durable projection intent.

        This method never calls ``send_message``.  Absence is returned as
        ``None`` so the service preserves EFFECT_UNKNOWN instead of retrying.
        """

        context, expected_thread_ts, message = self._resolve(candidate)
        parent = await self._bind(
            context=context,
            thread_ts=expected_thread_ts,
        )
        request = {
            "version": CONTROL_VERSION_V2,
            "operation": "read_thread",
            "args": {"context": context, "thread_ts": parent.thread_ts},
        }
        try:
            response = await self._service_call(self._socket_path, request)
        except DialogueServiceError as exc:
            if exc.code in {
                "SERVICE_UNAVAILABLE",
                "PEER_CREDENTIALS_UNAVAILABLE",
            }:
                _refuse("SERVICE_UNAVAILABLE")
            if exc.code == "TRANSPORT_UNAVAILABLE":
                _refuse("TRANSPORT_UNAVAILABLE")
            _refuse("DIALOGUE_REFUSED")
        except TerminalReturnProjectionError:
            raise
        except Exception:
            _refuse("SERVICE_UNAVAILABLE")
        if not isinstance(response, dict) or set(response) not in (
            {"ok", "result"},
            {"ok", "error"},
        ):
            _refuse("EFFECT_UNKNOWN")
        if response.get("ok") is not True:
            error = response.get("error")
            code = error.get("code") if isinstance(error, dict) else None
            if code in {"SERVICE_UNAVAILABLE", "PEER_CREDENTIALS_UNAVAILABLE"}:
                _refuse("SERVICE_UNAVAILABLE")
            if code == "TRANSPORT_UNAVAILABLE":
                _refuse("TRANSPORT_UNAVAILABLE")
            _refuse("DIALOGUE_REFUSED")
        result = response.get("result")
        expected_keys = {
            "thread_ts",
            "messages",
            "historical_messages",
            "ineligible_count",
            "mutated_count",
        }
        if (
            not isinstance(result, dict)
            or set(result) != expected_keys
            or result.get("thread_ts") != parent.thread_ts
            or not isinstance(result.get("messages"), list)
            or result.get("historical_messages") != []
            or type(result.get("ineligible_count")) is not int
            or type(result.get("mutated_count")) is not int
            or result["ineligible_count"] < 0
            or result["mutated_count"] < 0
        ):
            _refuse("EFFECT_UNKNOWN")
        matches: list[dict[str, Any]] = []
        for item in result["messages"]:
            if (
                not isinstance(item, dict)
                or set(item)
                != {"message", "primary_ts", "duplicate_timestamps"}
                or not isinstance(item.get("message"), dict)
            ):
                _refuse("EFFECT_UNKNOWN")
            if item["message"].get("message_key") == message["message_key"]:
                matches.append(item)
        if not matches:
            return None
        if len(matches) != 1:
            _refuse("EFFECT_UNKNOWN")
        match = matches[0]
        duplicates = match["duplicate_timestamps"]
        if (
            match["message"] != message
            or not isinstance(match.get("primary_ts"), str)
            or _THREAD_TS_RE.fullmatch(match["primary_ts"]) is None
            or not isinstance(duplicates, list)
            or bool(duplicates)
            or len(duplicates) != len(set(duplicates))
            or any(
                not isinstance(item, str) or _THREAD_TS_RE.fullmatch(item) is None
                for item in duplicates
            )
        ):
            _refuse("EFFECT_UNKNOWN")
        return TerminalReturnProjectionReceipt(
            action="RECOVERED",
            message_key=str(message["message_key"]),
            fingerprint=str(message["fingerprint"]),
            message_ts=str(match["primary_ts"]),
            duplicate_timestamps=tuple(duplicates),
            thread_ts=parent.thread_ts,
            parent_author_user_id=parent.parent_author_user_id,
            parent_fingerprint=parent.parent_fingerprint,
        )

    async def __call__(self, candidate: TerminalReturnCandidate) -> None:
        await self.project(candidate)


__all__ = [
    "ExecutiveTerminalReturnProjector",
    "TerminalReturnProjectionError",
    "TerminalReturnBindingResolver",
    "TerminalReturnProjectionReceipt",
]
