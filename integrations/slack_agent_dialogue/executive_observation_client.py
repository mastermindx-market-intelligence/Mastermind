"""One-shot bounded client for the dedicated Executive observation listener."""
from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from control_plane.executive_delegation_identity import ExecutiveDelegationIdentity
from control_plane.executive_dialogue_observation import (
    ACTIVE_CURRENT_WORKER,
    MAX_RESPONSE_BYTES,
    REQUEST_SCHEMA,
    RESPONSE_SCHEMA,
    TERMINAL_RESULT,
)
from control_plane.executive_runtime import (
    AttemptStatus,
    ExecutiveDialogueSource,
    WorkerStatus,
)
from control_plane.executive_terminal_return import TerminalReturnCandidate
from control_plane.session_targets import RuntimeBinding
from integrations.mastermind_company_mcp.schemas import (
    SERVER_IDENTITY,
    SERVER_VERSION,
    TOOL_SCHEMA_DIGEST,
)
from integrations.slack_agent_dialogue.company_dialogue_runtime_binding import (
    CurrentWorkerDialogueSnapshot,
    WorkerDialogueCaller,
)
from integrations.slack_agent_dialogue.contract import DialogueContractError
from integrations.slack_agent_dialogue.contract_v2 import validate_parent_v2
from integrations.slack_agent_dialogue.executive_terminal_return_projector import (
    ResolvedTerminalReturnBinding,
    TerminalReturnProjectionReceipt,
)


_STATES = frozenset(
    {"RESOLVED", "UNAVAILABLE", "UNKNOWN", "CONFLICT", "HELD", "REFUSED"}
)
_RESPONSE_FLAGS = frozenset(
    {
        "action_authoritative",
        "provider_action_authorized",
        "wake_write_authorized",
        "lifecycle_write_authorized",
    }
)
_RESOLVED_KEYS = frozenset({"schema", "state", "mode", "observation"}) | _RESPONSE_FLAGS
_CLOSED_KEYS = frozenset({"schema", "state", "reason"})
_DIGEST_RE = re.compile(r"\A[0-9a-f]{64}\Z")
_THREAD_TS_RE = re.compile(r"\A[1-9][0-9]{9,15}\.[0-9]{6}\Z")
_ERROR_CODES = frozenset(
    {
        "TRANSPORT_UNAVAILABLE",
        "RESPONSE_REFUSED",
        "REFUSED_ZERO_EFFECT",
        "HELD_ZERO_EFFECT",
        "UNKNOWN_ZERO_EFFECT",
        "CONFLICT_ZERO_EFFECT",
        "UNAVAILABLE_ZERO_EFFECT",
    }
)


class ExecutiveObservationClientError(RuntimeError):
    """One fixed zero-effect observation client outcome."""

    def __init__(self, code: str) -> None:
        if code not in _ERROR_CODES:
            raise ValueError("unknown Executive observation client error code")
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class ResolvedDialogueObservation:
    state: str
    mode: str
    dialogue_parent: Mapping[str, Any]
    thread_ts: str
    delegation_identity: ExecutiveDelegationIdentity
    current_worker: CurrentWorkerDialogueSnapshot | None
    actor: WorkerDialogueCaller | None
    terminal_candidate: TerminalReturnCandidate | None = None
    terminal_projection_receipt: TerminalReturnProjectionReceipt | None = None
    terminal_binding: ResolvedTerminalReturnBinding | None = None


def _reject_constant(_value: str) -> None:
    raise ValueError("constant refused")


def _pairs_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _digest(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(dict(value))).hexdigest()


def _strict_json(raw: bytes) -> dict[str, Any]:
    try:
        value = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_pairs_object,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, TypeError, ValueError):
        raise ExecutiveObservationClientError("RESPONSE_REFUSED") from None
    if not isinstance(value, dict):
        raise ExecutiveObservationClientError("RESPONSE_REFUSED")
    return value


def _validated_parent(parent: Mapping[str, Any]) -> dict[str, Any]:
    try:
        normalized = validate_parent_v2(dict(parent))
    except (DialogueContractError, TypeError, ValueError):
        raise ExecutiveObservationClientError("RESPONSE_REFUSED") from None
    if normalized != parent:
        raise ExecutiveObservationClientError("RESPONSE_REFUSED")
    return normalized


def _validated_thread_ts(value: str) -> str:
    if not isinstance(value, str) or _THREAD_TS_RE.fullmatch(value) is None:
        raise ExecutiveObservationClientError("RESPONSE_REFUSED")
    return value


class ExecutiveDialogueObservationClient:
    """Perform exactly one request with one absolute timeout and no fallback."""

    def __init__(
        self,
        socket_path: Path | str,
        *,
        timeout_seconds: float = 5.0,
        max_response_bytes: int = MAX_RESPONSE_BYTES,
    ) -> None:
        path = Path(socket_path)
        if not path.is_absolute() or "\x00" in os.fspath(path):
            raise ValueError("Executive observation socket path must be absolute")
        if path in {
            Path("/var/run/mastermind-executive/control.sock"),
            Path("/var/run/mastermind-agent-relay/agent-relay.sock"),
        }:
            raise ValueError("Executive observation client cannot use a fallback socket")
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, (int, float))
            or not 0.001 <= float(timeout_seconds) <= 60.0
        ):
            raise ValueError("timeout_seconds must be between 0.001 and 60")
        if (
            isinstance(max_response_bytes, bool)
            or not isinstance(max_response_bytes, int)
            or not 1024 <= max_response_bytes <= MAX_RESPONSE_BYTES
        ):
            raise ValueError("max_response_bytes is outside the closed bound")
        self.socket_path = path
        self.timeout_seconds = float(timeout_seconds)
        self.max_response_bytes = max_response_bytes

    async def _exchange(self, request: Mapping[str, Any]) -> dict[str, Any]:
        writer: asyncio.StreamWriter | None = None
        try:
            async with asyncio.timeout(self.timeout_seconds):
                reader, writer = await asyncio.open_unix_connection(
                    self.socket_path,
                    limit=self.max_response_bytes + 1,
                )
                writer.write(_canonical_json(dict(request)) + b"\n")
                await writer.drain()
                try:
                    raw = await reader.readuntil(b"\n")
                except (asyncio.IncompleteReadError, asyncio.LimitOverrunError):
                    raise ExecutiveObservationClientError("RESPONSE_REFUSED") from None
                if not raw or len(raw) > self.max_response_bytes:
                    raise ExecutiveObservationClientError("RESPONSE_REFUSED")
                await asyncio.sleep(0)
                if getattr(reader, "_buffer", b""):
                    raise ExecutiveObservationClientError("RESPONSE_REFUSED")
                return _strict_json(raw)
        except ExecutiveObservationClientError:
            raise
        except (TimeoutError, OSError, ConnectionError):
            raise ExecutiveObservationClientError("TRANSPORT_UNAVAILABLE") from None
        finally:
            if writer is not None:
                writer.close()
                try:
                    await writer.wait_closed()
                except (BrokenPipeError, ConnectionError, OSError):
                    pass

    async def resolve(
        self,
        *,
        parent: Mapping[str, Any],
        thread_ts: str,
    ) -> ResolvedDialogueObservation:
        canonical_parent = _validated_parent(parent)
        canonical_thread_ts = _validated_thread_ts(thread_ts)
        response = await self._exchange(
            {
                "schema": REQUEST_SCHEMA,
                "parent": canonical_parent,
            }
        )
        if response.get("schema") != RESPONSE_SCHEMA:
            raise ExecutiveObservationClientError("RESPONSE_REFUSED")
        state = response.get("state")
        if state not in _STATES:
            raise ExecutiveObservationClientError("RESPONSE_REFUSED")
        if state != "RESOLVED":
            if set(response) != _CLOSED_KEYS or not isinstance(
                response.get("reason"), str
            ):
                raise ExecutiveObservationClientError("RESPONSE_REFUSED")
            raise ExecutiveObservationClientError(f"{state}_ZERO_EFFECT")
        if (
            set(response) != _RESOLVED_KEYS
            or any(response.get(flag) is not False for flag in _RESPONSE_FLAGS)
            or not isinstance(response.get("observation"), dict)
        ):
            raise ExecutiveObservationClientError("RESPONSE_REFUSED")
        mode = response.get("mode")
        if mode == ACTIVE_CURRENT_WORKER:
            return self._active(
                parent=canonical_parent,
                thread_ts=canonical_thread_ts,
                observation=response["observation"],
            )
        if mode == TERMINAL_RESULT:
            return self._terminal(
                parent=canonical_parent,
                thread_ts=canonical_thread_ts,
                observation=response["observation"],
            )
        raise ExecutiveObservationClientError("RESPONSE_REFUSED")

    @staticmethod
    def _active(
        *,
        parent: Mapping[str, Any],
        thread_ts: str,
        observation: Mapping[str, Any],
    ) -> ResolvedDialogueObservation:
        keys = {
            "root_job_id",
            "job_id",
            "attempt_id",
            "worker_id",
            "attempt_status",
            "worker_status",
            "execution_profile_id",
            "execution_profile_digest",
            "capability_policy_digest",
            "runtime_binding",
            "parent_fingerprint",
            "company_dialogue_server_identity",
            "company_dialogue_server_version",
            "company_dialogue_tool_schema_digest",
            "company_dialogue_attested",
            "evidence_digest",
        }
        if set(observation) != keys:
            raise ExecutiveObservationClientError("RESPONSE_REFUSED")
        material = dict(observation)
        evidence_digest = material.pop("evidence_digest")
        if not isinstance(evidence_digest, str) or evidence_digest != _digest(material):
            raise ExecutiveObservationClientError("RESPONSE_REFUSED")
        binding_value = material["runtime_binding"]
        if not isinstance(binding_value, dict) or set(binding_value) != {
            "session_alias",
            "binding_id",
            "binding_generation",
            "reasoning_surface",
        }:
            raise ExecutiveObservationClientError("RESPONSE_REFUSED")
        try:
            attempt_status = AttemptStatus(material["attempt_status"])
            worker_status = WorkerStatus(material["worker_status"])
            binding = RuntimeBinding(**binding_value)
        except (TypeError, ValueError):
            raise ExecutiveObservationClientError("RESPONSE_REFUSED") from None
        if (
            attempt_status
            not in {AttemptStatus.CLAIMED, AttemptStatus.RUNNING, AttemptStatus.CHECKPOINTED}
            or worker_status is not WorkerStatus.BUSY
            or material["parent_fingerprint"] != parent["fingerprint"]
            or material["company_dialogue_server_identity"] != SERVER_IDENTITY
            or material["company_dialogue_server_version"] != SERVER_VERSION
            or material["company_dialogue_tool_schema_digest"] != TOOL_SCHEMA_DIGEST
            or material["company_dialogue_attested"] is not True
            or any(
                not isinstance(material[name], str)
                or _DIGEST_RE.fullmatch(material[name]) is None
                for name in (
                    "execution_profile_digest",
                    "capability_policy_digest",
                )
            )
        ):
            raise ExecutiveObservationClientError("RESPONSE_REFUSED")
        current = CurrentWorkerDialogueSnapshot(
            root_job_id=material["root_job_id"],
            job_id=material["job_id"],
            attempt_id=material["attempt_id"],
            worker_id=material["worker_id"],
            attempt_status=attempt_status,
            worker_status=worker_status,
            execution_profile_id=material["execution_profile_id"],
            execution_profile_digest=material["execution_profile_digest"],
            capability_policy_digest=material["capability_policy_digest"],
            runtime_binding=binding,
            parent_fingerprint=material["parent_fingerprint"],
            company_dialogue_server_identity=SERVER_IDENTITY,
            company_dialogue_server_version=SERVER_VERSION,
            company_dialogue_tool_schema_digest=TOOL_SCHEMA_DIGEST,
            company_dialogue_attested=True,
        )
        actor = WorkerDialogueCaller(
            attempt_id=current.attempt_id,
            worker_id=current.worker_id,
            execution_profile_id=current.execution_profile_id,
            execution_profile_digest=current.execution_profile_digest,
            capability_policy_digest=current.capability_policy_digest,
            runtime_binding=current.runtime_binding,
        )
        identity = ExecutiveDelegationIdentity(
            job_id=current.job_id,
            root_job_id=current.root_job_id,
            operation_key=str(parent["operation_key"]),
            session_ref=str(parent["session_ref"]),
        )
        return ResolvedDialogueObservation(
            state="RESOLVED",
            mode=ACTIVE_CURRENT_WORKER,
            dialogue_parent=dict(parent),
            thread_ts=thread_ts,
            delegation_identity=identity,
            current_worker=current,
            actor=actor,
        )

    @staticmethod
    def _terminal(
        *,
        parent: Mapping[str, Any],
        thread_ts: str,
        observation: Mapping[str, Any],
    ) -> ResolvedDialogueObservation:
        if set(observation) != {
            "candidate",
            "projection_receipt",
            "projection_receipt_digest",
            "projection_effect",
            "evidence_digest",
        }:
            raise ExecutiveObservationClientError("RESPONSE_REFUSED")
        material = dict(observation)
        evidence = material.pop("evidence_digest")
        if (
            material.get("projection_effect") != "APPLIED"
            or not isinstance(evidence, str)
            or evidence != _digest(material)
        ):
            raise ExecutiveObservationClientError("RESPONSE_REFUSED")
        candidate_value = material["candidate"]
        receipt_value = material["projection_receipt"]
        if not isinstance(candidate_value, dict) or not isinstance(receipt_value, dict):
            raise ExecutiveObservationClientError("RESPONSE_REFUSED")
        candidate_keys = {
            "job_id", "attempt_id", "worker_id", "root_job_id", "role",
            "operation_key", "session_ref", "runtime_status", "result_status",
            "result_envelope_digest", "terminal_evidence_digest",
            "artifact_receipt_digest", "validation_receipt_digest",
            "effective_grant_digest", "terminal_at", "message_key", "summary",
            "review_verdict", "dialogue_source",
        }
        receipt_keys = {
            "action", "message_key", "fingerprint", "message_ts",
            "duplicate_timestamps", "thread_ts", "parent_author_user_id",
            "parent_fingerprint",
        }
        if set(candidate_value) != candidate_keys or set(receipt_value) != receipt_keys:
            raise ExecutiveObservationClientError("RESPONSE_REFUSED")
        if material["projection_receipt_digest"] != _digest(receipt_value):
            raise ExecutiveObservationClientError("RESPONSE_REFUSED")
        source_value = candidate_value.get("dialogue_source")
        if not isinstance(source_value, dict):
            raise ExecutiveObservationClientError("RESPONSE_REFUSED")
        try:
            source = ExecutiveDialogueSource(**source_value)
            candidate = TerminalReturnCandidate(
                **{**candidate_value, "dialogue_source": source}
            )
            duplicates = receipt_value.get("duplicate_timestamps")
            if not isinstance(duplicates, list):
                raise TypeError
            receipt = TerminalReturnProjectionReceipt(
                **{**receipt_value, "duplicate_timestamps": tuple(duplicates)}
            )
        except (TypeError, ValueError):
            raise ExecutiveObservationClientError("RESPONSE_REFUSED") from None
        if (
            candidate.operation_key != parent["operation_key"]
            or candidate.session_ref != parent["session_ref"]
            or source.work_ref != parent["work_ref"]
            or source.commission_ref.to_dict() != parent["commission_ref"]
            or source.watch_mode != parent["watch_mode"]
            or receipt.parent_fingerprint != parent["fingerprint"]
            or receipt.thread_ts != thread_ts
            or receipt.message_key != candidate.message_key
            or receipt.duplicate_timestamps != ()
            or candidate.runtime_status != "COMPLETED"
            or candidate.result_status != "RESULT"
        ):
            raise ExecutiveObservationClientError("RESPONSE_REFUSED")
        attempt_ref = {
            "job_id": candidate.job_id,
            "attempt_id": candidate.attempt_id,
            "worker_id": candidate.worker_id,
        }
        binding = ResolvedTerminalReturnBinding(
            work_ref=source.work_ref,
            commission_ref=source.commission_ref.to_dict(),
            session_ref=candidate.session_ref,
            operation_key=candidate.operation_key,
            watch_mode=source.watch_mode,
            actor_ref={"kind": "worker_attempt", **attempt_ref},
            applies_to={"kind": "executive_attempt", **attempt_ref},
        )
        identity = ExecutiveDelegationIdentity(
            job_id=candidate.job_id,
            root_job_id=candidate.root_job_id,
            operation_key=candidate.operation_key,
            session_ref=candidate.session_ref,
        )
        return ResolvedDialogueObservation(
            state="RESOLVED",
            mode=TERMINAL_RESULT,
            dialogue_parent=dict(parent),
            thread_ts=thread_ts,
            delegation_identity=identity,
            current_worker=None,
            actor=None,
            terminal_candidate=candidate,
            terminal_projection_receipt=receipt,
            terminal_binding=binding,
        )


__all__ = [
    "ExecutiveDialogueObservationClient",
    "ExecutiveObservationClientError",
    "ResolvedDialogueObservation",
]
