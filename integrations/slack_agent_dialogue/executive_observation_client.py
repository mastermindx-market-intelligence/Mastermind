"""One-shot client for the dedicated Executive dialogue-coordination listener."""
from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import json
import os
import re
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from control_plane.executive_delegation_identity import ExecutiveDelegationIdentity
from control_plane.executive_dialogue_observation import (
    ACTIVE_CURRENT_WORKER,
    RECONCILE_WAKE,
    SUBMIT_WAKE,
    DialogueCandidateReference,
    MAX_RESPONSE_BYTES,
    REQUEST_SCHEMA,
    RESPONSE_SCHEMA,
    TERMINAL_RESULT,
    TerminalProjectionReceiptReference,
    WAKE_REQUEST_SCHEMA,
    WAKE_RESPONSE_SCHEMA,
)
from control_plane.executive_runtime import (
    AttemptStatus,
    EXECUTIVE_DIALOGUE_SOURCE_SCHEMA,
    ExecutiveDialogueSource,
    WorkerStatus,
)
from control_plane.executive_terminal_return import TerminalReturnCandidate
from control_plane.session_targets import RuntimeBinding, WakeRoute, route_digest
from control_plane.wake_dispatcher import WakeEffectUnknownError, WakePreSubmitError
from control_plane.wake_events import WakeObligation, mint_obligation
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
)
from integrations.slack_agent_dialogue.turn_observer import WakeCarrierState


_STATES = frozenset(
    {"RESOLVED", "UNAVAILABLE", "UNKNOWN", "CONFLICT", "HELD"}
)
_RESPONSE_FLAGS = frozenset(
    {
        "action_authoritative",
        "provider_action_authorized",
        "wake_write_authorized",
        "lifecycle_write_authorized",
    }
)
_RESOLVED_KEYS = (
    frozenset({"schema", "state", "mode", "observation", "target_bindings"})
    | _RESPONSE_FLAGS
)
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
    candidate: DialogueCandidateReference
    target_bindings: Mapping[str, RuntimeBinding | None]
    current_worker: CurrentWorkerDialogueSnapshot | None
    actor: WorkerDialogueCaller | None
    terminal_candidate: TerminalReturnCandidate | None = None
    terminal_projection_receipt: TerminalProjectionReceiptReference | None = None
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
        self._wake_context: ContextVar[Any] | None = None

    def bind_wake_context(
        self,
        context: ContextVar[Any],
    ) -> None:
        """Bind once to the exact candidate scope owned by Agent Relay."""

        if not isinstance(context, ContextVar) or self._wake_context is not None:
            raise ValueError("Wake request context is invalid or already bound")
        self._wake_context = context

    def _wake_request(
        self,
        *,
        operation: str,
        obligation: WakeObligation,
        route: WakeRoute,
    ) -> dict[str, Any]:
        if (
            operation not in {RECONCILE_WAKE, SUBMIT_WAKE}
            or not isinstance(obligation, WakeObligation)
            or not isinstance(route, WakeRoute)
            or route.obligation_id != obligation.obligation_id
            or self._wake_context is None
        ):
            raise WakePreSubmitError("dialogue Wake request is not bound")
        context = self._wake_context.get()
        try:
            if isinstance(context, Mapping):
                if set(context) != {"parent", "thread_ts", "candidate"}:
                    raise KeyError
                parent_value = context["parent"]
                thread_value = context["thread_ts"]
                candidate_value = context["candidate"]
            else:
                parent_value = context.dialogue_parent
                thread_value = context.thread_ts
                candidate_value = context.candidate
            parent = _validated_parent(parent_value)
            thread_ts = _validated_thread_ts(thread_value)
            if not isinstance(candidate_value, DialogueCandidateReference):
                raise TypeError
            candidate = candidate_value.to_dict()
            if (
                obligation.root_job_id != candidate_value.root_job_id
                or obligation.source_workstream != parent["work_ref"]
                or obligation.job_id not in {None, candidate_value.job_id}
                or obligation.attempt_id not in {None, candidate_value.attempt_id}
            ):
                raise ValueError
            observation_digest = hashlib.sha256(
                _canonical_json(
                    {
                        "schema": "mastermind.dialogue_observation_identity/v1",
                        "attention_source_ref": obligation.source_ref,
                        "parent_fingerprint": parent["fingerprint"],
                        "operation_key": parent["operation_key"],
                        "candidate": candidate,
                    }
                )
            ).hexdigest()
            correlated_obligation = mint_obligation(
                wake_kind=obligation.wake_kind,
                source_kind=obligation.source_kind,
                source_ref="agent_dialogue_attention:" + observation_digest,
                declared_target_seat=obligation.declared_target_seat,
                job_id=candidate_value.job_id,
                attempt_id=candidate_value.attempt_id,
                root_job_id=candidate_value.root_job_id,
                workstream=obligation.workstream,
                source_workstream=obligation.source_workstream,
                source_created_at=obligation.source_created_at,
                emitted_at=obligation.emitted_at,
            )
            correlated_route = dataclasses.replace(
                route,
                obligation_id=correlated_obligation.obligation_id,
                route_digest=route_digest(
                    obligation_id=correlated_obligation.obligation_id,
                    destination=route.destination_digest,
                    policy_digest=route.policy_digest,
                ),
            )
        except (
            AttributeError,
            ExecutiveObservationClientError,
            KeyError,
            TypeError,
            ValueError,
        ):
            raise WakePreSubmitError("dialogue Wake parent context is invalid") from None
        return {
            "schema": WAKE_REQUEST_SCHEMA,
            "operation": operation,
            "parent": parent,
            "thread_ts": thread_ts,
            "candidate": candidate,
            "obligation": correlated_obligation.to_dict(),
            "route": correlated_route.to_dict(),
        }

    async def _wake_exchange(
        self,
        request: Mapping[str, Any],
        *,
        submit: bool,
    ) -> dict[str, Any]:
        writer: asyncio.StreamWriter | None = None
        may_have_reached_executive = False
        try:
            async with asyncio.timeout(self.timeout_seconds):
                reader, writer = await asyncio.open_unix_connection(
                    self.socket_path,
                    limit=self.max_response_bytes + 1,
                )
                may_have_reached_executive = True
                writer.write(_canonical_json(dict(request)) + b"\n")
                await writer.drain()
                try:
                    raw = await reader.readuntil(b"\n")
                except (asyncio.IncompleteReadError, asyncio.LimitOverrunError):
                    raise ValueError("Wake response frame refused") from None
                if not raw or len(raw) > self.max_response_bytes:
                    raise ValueError("Wake response frame refused")
                await asyncio.sleep(0)
                if getattr(reader, "_buffer", b""):
                    raise ValueError("multiple Wake response frames refused")
                try:
                    response = _strict_json(raw)
                except ExecutiveObservationClientError:
                    raise ValueError("Wake response JSON refused") from None
                if (
                    set(response) != {"schema", "state", "reason"}
                    or response.get("schema") != WAKE_RESPONSE_SCHEMA
                    or response.get("state")
                    not in {"MISSING", "RECORDED", "EFFECT_UNKNOWN"}
                    or not isinstance(response.get("reason"), str)
                ):
                    raise ValueError("Wake response refused")
                return response
        except (WakeEffectUnknownError, WakePreSubmitError):
            raise
        except Exception:
            if submit and may_have_reached_executive:
                raise WakeEffectUnknownError(
                    "dialogue Wake submit effect is unknown"
                ) from None
            raise WakePreSubmitError(
                "dialogue Wake coordination is unavailable"
            ) from None
        finally:
            if writer is not None:
                writer.close()
                try:
                    await writer.wait_closed()
                except (BrokenPipeError, ConnectionError, OSError):
                    pass

    async def reconcile(
        self,
        obligation: WakeObligation,
        route: WakeRoute,
    ) -> WakeCarrierState:
        response = await self._wake_exchange(
            self._wake_request(
                operation=RECONCILE_WAKE,
                obligation=obligation,
                route=route,
            ),
            submit=False,
        )
        return WakeCarrierState(response["state"])

    async def submit(
        self,
        obligation: WakeObligation,
        route: WakeRoute,
    ) -> None:
        response = await self._wake_exchange(
            self._wake_request(
                operation=SUBMIT_WAKE,
                obligation=obligation,
                route=route,
            ),
            submit=True,
        )
        if response["state"] == "RECORDED":
            return
        if response["state"] == "EFFECT_UNKNOWN":
            raise WakeEffectUnknownError("Executive recorded an unknown Wake effect")
        raise WakePreSubmitError("Executive proved no Wake submit effect")

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
                "request_id": (
                    "observation-"
                    + hashlib.sha256(_canonical_json(canonical_parent)).hexdigest()[:32]
                ),
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
            or not isinstance(response.get("target_bindings"), dict)
        ):
            raise ExecutiveObservationClientError("RESPONSE_REFUSED")
        mode = response.get("mode")
        target_bindings = self._target_bindings(response["target_bindings"])
        if mode == ACTIVE_CURRENT_WORKER:
            return self._active(
                parent=canonical_parent,
                thread_ts=canonical_thread_ts,
                observation=response["observation"],
                target_bindings=target_bindings,
            )
        if mode == TERMINAL_RESULT:
            return self._terminal(
                parent=canonical_parent,
                thread_ts=canonical_thread_ts,
                observation=response["observation"],
                target_bindings=target_bindings,
            )
        raise ExecutiveObservationClientError("RESPONSE_REFUSED")

    @staticmethod
    def _target_bindings(
        value: Mapping[str, Any],
    ) -> dict[str, RuntimeBinding | None]:
        if set(value) != {"coo", "ceo"}:
            raise ExecutiveObservationClientError("RESPONSE_REFUSED")
        result: dict[str, RuntimeBinding | None] = {}
        for seat in ("coo", "ceo"):
            raw = value[seat]
            if raw is None:
                result[seat] = None
                continue
            if not isinstance(raw, dict) or set(raw) != {
                "session_alias",
                "binding_id",
                "binding_generation",
                "reasoning_surface",
            }:
                raise ExecutiveObservationClientError("RESPONSE_REFUSED")
            try:
                binding = RuntimeBinding(**raw)
            except (TypeError, ValueError):
                raise ExecutiveObservationClientError("RESPONSE_REFUSED") from None
            if binding.native_handle is not None or binding.account_label is not None:
                raise ExecutiveObservationClientError("RESPONSE_REFUSED")
            result[seat] = binding
        return result

    @staticmethod
    def _active(
        *,
        parent: Mapping[str, Any],
        thread_ts: str,
        observation: Mapping[str, Any],
        target_bindings: Mapping[str, RuntimeBinding | None],
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
        candidate = DialogueCandidateReference(
            mode=ACTIVE_CURRENT_WORKER,
            root_job_id=current.root_job_id,
            job_id=current.job_id,
            attempt_id=current.attempt_id,
            worker_id=current.worker_id,
            evidence_digest=evidence_digest,
        )
        return ResolvedDialogueObservation(
            state="RESOLVED",
            mode=ACTIVE_CURRENT_WORKER,
            dialogue_parent=dict(parent),
            thread_ts=thread_ts,
            delegation_identity=identity,
            candidate=candidate,
            target_bindings=dict(target_bindings),
            current_worker=current,
            actor=actor,
        )

    @staticmethod
    def _terminal(
        *,
        parent: Mapping[str, Any],
        thread_ts: str,
        observation: Mapping[str, Any],
        target_bindings: Mapping[str, RuntimeBinding | None],
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
            "job_id", "attempt_id", "worker_id", "root_job_id",
            "runtime_status", "result_status", "result_envelope_digest",
            "terminal_evidence_digest", "artifact_receipt_digest",
            "validation_receipt_digest", "effective_grant_digest", "terminal_at",
            "projection_command_digest",
        }
        receipt_keys = {"action", "message_fingerprint", "receipt_digest"}
        if set(candidate_value) != candidate_keys or set(receipt_value) != receipt_keys:
            raise ExecutiveObservationClientError("RESPONSE_REFUSED")
        if material["projection_receipt_digest"] != receipt_value.get(
            "receipt_digest"
        ):
            raise ExecutiveObservationClientError("RESPONSE_REFUSED")
        try:
            candidate_material = dict(candidate_value)
            projection_command_digest = candidate_material.pop(
                "projection_command_digest"
            )
            if _DIGEST_RE.fullmatch(str(projection_command_digest)) is None:
                raise ValueError
            source = ExecutiveDialogueSource(
                schema_version=EXECUTIVE_DIALOGUE_SOURCE_SCHEMA,
                work_ref=str(parent["work_ref"]),
                commission_ref=parent["commission_ref"],
                watch_mode=parent["watch_mode"],
            )
            candidate = TerminalReturnCandidate(
                **candidate_material,
                role="worker",
                operation_key=str(parent["operation_key"]),
                session_ref=str(parent["session_ref"]),
                message_key=(
                    "asd-exec-result-"
                    + str(candidate_material["terminal_evidence_digest"])
                ),
                summary="",
                review_verdict=None,
                dialogue_source=source,
            )
            receipt = TerminalProjectionReceiptReference(**receipt_value)
        except (TypeError, ValueError):
            raise ExecutiveObservationClientError("RESPONSE_REFUSED") from None
        expected_projection_command_digest = hashlib.sha256(
            (
                f"terminal-return:{candidate.attempt_id}:"
                f"{candidate.terminal_digest}:applied"
            ).encode("ascii")
        ).hexdigest()
        if (
            candidate.operation_key != parent["operation_key"]
            or candidate.session_ref != parent["session_ref"]
            or source.work_ref != parent["work_ref"]
            or source.commission_ref.to_dict() != parent["commission_ref"]
            or source.watch_mode != parent["watch_mode"]
            or receipt.action not in {"POSTED", "RECOVERED", "DUPLICATE"}
            or projection_command_digest != expected_projection_command_digest
            or _DIGEST_RE.fullmatch(receipt.message_fingerprint) is None
            or _DIGEST_RE.fullmatch(receipt.receipt_digest) is None
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
        candidate_ref = DialogueCandidateReference(
            mode=TERMINAL_RESULT,
            root_job_id=candidate.root_job_id,
            job_id=candidate.job_id,
            attempt_id=candidate.attempt_id,
            worker_id=candidate.worker_id,
            evidence_digest=evidence,
        )
        return ResolvedDialogueObservation(
            state="RESOLVED",
            mode=TERMINAL_RESULT,
            dialogue_parent=dict(parent),
            thread_ts=thread_ts,
            delegation_identity=identity,
            candidate=candidate_ref,
            target_bindings=dict(target_bindings),
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
