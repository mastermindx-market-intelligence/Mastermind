"""Private, local control service for the Executive OS supervisor.

The service is deliberately smaller than a scheduler or remote API.  It opens
the durable :mod:`control_plane.executive_runtime` state, reconciles attempts at
startup, and accepts one bounded JSON request per local Unix-domain connection.
There is no TCP listener and no generic command-execution request.

Provider execution remains owned by an injected ``ExecutiveSupervisor``.  The
injection seam keeps service tests model-free and lets the dedicated macOS host
compose the reviewed worker-principal boundary without importing the financial
application or APScheduler.
"""
from __future__ import annotations

import asyncio
import ctypes
import dataclasses
import errno
import fcntl
import hashlib
import inspect
import json
import os
import re
import signal
import socket
import sqlite3
import stat
import struct
import subprocess
import sys
from contextlib import nullcontext
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Mapping, Protocol
from uuid import uuid4

from common.redaction import sanitize_external_text
from control_plane import ceo_intent
from control_plane import executive_dialogue_observation as dialogue_observation
from control_plane import executive_ceo_ingress as ceo_ingress
from control_plane.executive_agent_capabilities import CapabilityPolicyError
from control_plane.executive_coo_cycle import CooCycle, CooCycleOutcome
from control_plane.executive_runtime import (
    AttemptStatus,
    EXECUTIVE_DIALOGUE_SOURCE_SCHEMA,
    Job,
    JobStatus,
    OrchestrationDispatchOutcome,
    PersistenceError,
    Runtime,
    RuntimeProofError,
    SCHEMA_VERSION,
    StateConflict,
    ValidatedRoleCompletion,
    V2_HOST_EXECUTION_BINDING_KEYS,
    _attempt_from_row,
    _dialogue_source_from_root_creation,
    _job_from_row,
    _strict_canonical_json_loads,
    _validated_role_completion_material,
    normalize_executive_dialogue_source,
)
from control_plane.executive_dialogue_observation import (
    MAX_REQUEST_BYTES as DIALOGUE_OBSERVATION_MAX_REQUEST_BYTES,
    RESPONSE_SCHEMA as DIALOGUE_OBSERVATION_RESPONSE_SCHEMA,
    WAKE_RESPONSE_SCHEMA as DIALOGUE_WAKE_RESPONSE_SCHEMA,
    ActiveObservationFacts,
    CanonicalTerminalWakeCandidate,
    CanonicalTerminalWakeRead,
    DialogueCandidateReference,
    DialogueDelayedAckRequest,
    DialogueObservationFacts,
    DialogueObservationProtocolError,
    DialogueWakeRequest,
    DialogueSourceReconcileRequest,
    RECONCILE_WAKE,
    SUBMIT_WAKE,
    PublicRuntimeBindingFacts,
    TerminalObservationFacts,
    TerminalProjectionReceiptFacts,
    TERMINAL_RETURN_APPLIED_EVENT as _TERMINAL_RETURN_APPLIED_EVENT,
    TERMINAL_RETURN_ATTEMPTED_EVENT as _TERMINAL_RETURN_ATTEMPTED_EVENT,
    TERMINAL_RETURN_EFFECT_UNKNOWN_EVENT as _TERMINAL_RETURN_EFFECT_UNKNOWN_EVENT,
    TERMINAL_RETURN_PREPARED_EVENT as _TERMINAL_RETURN_PREPARED_EVENT,
    TERMINAL_RETURN_PRE_SUBMIT_REFUSED_EVENT as _TERMINAL_RETURN_PRE_SUBMIT_REFUSED_EVENT,
    TERMINAL_RETURN_PROVEN_NO_EFFECT_EVENT as _TERMINAL_RETURN_PROVEN_NO_EFFECT_EVENT,
    parse_observation_request,
    parse_delayed_ack_request,
    parse_source_reconcile_request,
    parse_wake_request,
    reduce_dialogue_observation,
    response_bytes as dialogue_observation_response_bytes,
    SOURCE_RECONCILE_RESPONSE_SCHEMA,
    DELAYED_ACK_RESPONSE_SCHEMA,
)
from control_plane.executive_terminal_return import (
    TerminalReturnCandidate,
    TerminalReturnError,
    TerminalReturnProjectionError,
    reduce_terminal_return,
)
from control_plane.model_router import ModelRouter, RoutingPolicyError
from control_plane.operator_harness_contract import AttemptExecutionMode
from control_plane.executive_workspace import (
    GitHandoffError,
    LAUNCH_CLEAN_STATUS_ARGS,
    LAUNCH_CLEAN_UNTRACKED_ARGS,
    WorkspaceError,
    git_observation_env,
    observe_launch_cleanliness,
    prepare_credentialless_clone,
    validate_shared_git_handoff,
)


CONTROL_PROTOCOL_VERSION = "mastermind.executive_control/v1"
DEFAULT_MAX_REQUEST_BYTES = 64 * 1024
DEFAULT_MAX_RESPONSE_BYTES = 1024 * 1024
DIALOGUE_OBSERVATION_IO_TIMEOUT_SECONDS = 5.0
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_BACKUP_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}\.sqlite3$")
_PROOF_WORKSPACE_RE = re.compile(r"^proof-([0-9a-f]{32})$")
_COO_ROOT_SCAN_LIMIT = 64
_COO_ACTIVE_ATTEMPT_STATUSES = frozenset(
    {
        AttemptStatus.CLAIMED,
        AttemptStatus.RUNNING,
        AttemptStatus.CHECKPOINTED,
        AttemptStatus.CANCEL_REQUESTED,
    }
)
_COO_TERMINAL_RETURN_ROLES = frozenset({"plan", "work", "review", "repair"})
_TERMINAL_RETURN_STARTUP_REPLAY_LIMIT = 256
_TERMINAL_RETURN_STARTUP_PHASE_AUDIT_LIMIT = 4096
_WORKSPACE_ROTATION_SCHEMA = "mastermind.executive_workspace_rotation/v1"
_PROOF_ARTIFACT = "research/executive_os_phase1c_worker_proof/receipt.md"
_SERVICE_GIT_OBSERVATION_ALLOWLIST = frozenset(
    {
        ("rev-parse", "--verify", "HEAD^{commit}"),
        ("rev-parse", "--abbrev-ref", "HEAD"),
        LAUNCH_CLEAN_STATUS_ARGS,
        LAUNCH_CLEAN_UNTRACKED_ARGS,
        ("remote",),
    }
)
_PROOF_OBJECTIVE = (
    "Create the bounded Executive OS Phase 1C-A proof receipt at "
    f"{_PROOF_ARTIFACT}. Record only the assigned Job, Attempt, exact base SHA, "
    "and a short harmless completion statement. Do not access credentials, "
    "network resources, financial state, Git remotes, or any undeclared path."
)
_PROOF_VALIDATION = (
    "/usr/bin/python3",
    "-c",
    (
        "from pathlib import Path; "
        f"p=Path({_PROOF_ARTIFACT!r}); "
        "t=p.read_text(encoding='utf-8'); "
        "assert t.startswith('# Phase 1C-A Worker Proof'); "
        "assert 'Job:' in t and 'Attempt:' in t and 'Base SHA:' in t"
    ),
)
# A local peer that goes away mid-reply is a normal condition, not a service
# fault: the reply (very often an error envelope) simply has nowhere to land.
_CLIENT_GONE = (BrokenPipeError, ConnectionResetError, ConnectionAbortedError)


class ServiceError(RuntimeProofError):
    """A private control-service request could not be completed safely."""


class SupervisorProtocol(Protocol):
    async def start_job(self, job_id: str) -> Any: ...

    async def start_cycle_job(
        self, job_id: str, *, command_id: str
    ) -> Any: ...

    async def finish_job(self, active: Any) -> Any: ...

    def reconcile_restart(self, *, requeue_lost: bool = False) -> list[Any]: ...


class OperatorSupervisorProtocol(Protocol):
    async def start_cycle_job(
        self, job_id: str, *, command_id: str
    ) -> OrchestrationDispatchOutcome: ...

    def reconcile_restart(self, *, requeue_lost: bool = False) -> list[Any]: ...


class BackupBackendProtocol(Protocol):
    def create_online_backup(self, store: Any, destination_dir: Path) -> Any: ...

    def verify_backup(
        self, database_path: Path, manifest_path: Path | None = None
    ) -> Any: ...


TerminalReturnProjector = Callable[[TerminalReturnCandidate], Awaitable[None] | None]
TerminalReturnProjectorFactory = Callable[
    [Callable[[], Runtime], Path], TerminalReturnProjector
]
CeoIngressDialogueSourceProvider = Callable[
    [str, str], Mapping[str, Any] | None
]
DialogueObservationFactsProvider = Callable[
    [Runtime, Mapping[str, Any]], DialogueObservationFacts
]
DialogueWakeHandler = Callable[
    [Runtime, DialogueWakeRequest], Awaitable["DialogueWakeResult"] | "DialogueWakeResult"
]


@dataclasses.dataclass(frozen=True)
class DialogueWakeResult:
    state: str
    reason: str

    def __post_init__(self) -> None:
        if self.state not in {"MISSING", "RECORDED", "EFFECT_UNKNOWN"}:
            raise ValueError("dialogue Wake result state is invalid")
        if re.fullmatch(r"[A-Z][A-Z0-9_]{2,127}", self.reason) is None:
            raise ValueError("dialogue Wake result reason is invalid")


@dataclasses.dataclass(frozen=True)
class DialogueWakeTarget:
    """Executive-owned Stage-B1 resolution of one proposed Wake target."""

    registry: Any
    runtime_binding: Any
    target_attempt_id: str
    process_generation_id: str
    operator_adapter: Any

    def __post_init__(self) -> None:
        if (
            not str(self.target_attempt_id or "").strip()
            or not str(self.process_generation_id or "").strip()
            or not callable(getattr(self.operator_adapter, "deliver_attention", None))
        ):
            raise ValueError("dialogue Wake target is incomplete")


DialogueWakeTargetProvider = Callable[
    [Runtime, Mapping[str, Any], Any], DialogueWakeTarget | None
]


@dataclasses.dataclass(frozen=True)
class DialogueWakeHistoricalTarget:
    """Exact immutable OHF generation used only to reconcile an accepted attempt."""

    runtime_binding: Any
    generation: Any
    target_attempt_id: str
    operator_adapter: Any


def _dialogue_candidate_from_response(
    response: Mapping[str, Any],
) -> DialogueCandidateReference | None:
    """Project the exact public candidate identity from a fresh source read."""

    try:
        if response.get("state") != "RESOLVED":
            return None
        mode = response["mode"]
        observation = response["observation"]
        candidate = (
            observation
            if mode == "ACTIVE_CURRENT_WORKER"
            else observation["candidate"]
        )
        return DialogueCandidateReference(
            mode=mode,
            root_job_id=candidate["root_job_id"],
            job_id=candidate["job_id"],
            attempt_id=candidate["attempt_id"],
            worker_id=candidate["worker_id"],
            evidence_digest=observation["evidence_digest"],
        )
    except (KeyError, TypeError, ValueError):
        return None


def _dialogue_target_bindings_for_root(
    runtime: Runtime,
    connection: sqlite3.Connection,
    *,
    root_job_id: str,
    registry: Any,
) -> dict[str, PublicRuntimeBindingFacts | None]:
    """Project the exact current COO/CEO writers for one candidate root.

    The candidate enumeration, OHF proof and public projection deliberately use
    the caller's one Runtime read snapshot.  A missing, stale or non-unique seat
    stays unavailable; no historical or seat-adjacent fallback is permitted.
    """

    from control_plane.runtime_binding_projection import project_runtime_binding

    result: dict[str, PublicRuntimeBindingFacts | None] = {
        "coo": None,
        "ceo": None,
    }
    rows = connection.execute(
        """
        SELECT current_attempt_id
        FROM jobs
        WHERE root_job_id=?
          AND current_attempt_id IS NOT NULL
          AND status IN ('RUNNING','CHECKPOINTED','CANCEL_REQUESTED')
        ORDER BY job_id
        """,
        (root_job_id,),
    ).fetchall()
    by_seat: dict[str, list[PublicRuntimeBindingFacts]] = {
        "coo": [],
        "ceo": [],
    }
    for row in rows:
        attempt_id = str(row["current_attempt_id"] or "")
        try:
            source = runtime.current_harness_binding_source(
                attempt_id,
                connection=connection,
            )
            seat = str(source.owner_seat or "").lower()
            if seat not in by_seat:
                continue
            root_alias = registry.root_job_bindings.get(root_job_id, {}).get(seat)
            target = (
                registry.get(root_alias)
                if root_alias is not None
                else registry.resolve(seat)
            )
            binding = project_runtime_binding(
                runtime,
                attempt_id,
                target,
                connection=connection,
            )
            by_seat[seat].append(
                PublicRuntimeBindingFacts(
                    session_alias=binding.session_alias,
                    binding_id=binding.binding_id,
                    binding_generation=binding.binding_generation,
                    reasoning_surface=str(binding.reasoning_surface or ""),
                )
            )
        except Exception:
            continue
    for seat, bindings in by_seat.items():
        if len(bindings) == 1:
            result[seat] = bindings[0]
    return result


class ExecutiveDialogueWakeBridge:
    """Re-resolve a Relay proposal into existing Executive Wake owners."""

    def __init__(
        self,
        *,
        target_provider: DialogueWakeTargetProvider | None,
        retry_policy: Any,
        operator_adapter: Any = None,
        carrier_factory: Callable[..., Any] | None = None,
        canary_profile: Any = None,
        canary_current_facts_for: Callable[..., Any] | None = None,
        canary_now_epoch_seconds: Callable[[], int] | None = None,
        historical_target_for: Callable[..., Any] | None = None,
        installed_release_sha: str | None = None,
        operation_key: str | None = None,
    ) -> None:
        from control_plane.wake_ledger import WakeRetryPolicy

        if target_provider is not None and not callable(target_provider):
            raise TypeError("target_provider must be callable or None")
        if not isinstance(retry_policy, WakeRetryPolicy):
            raise TypeError("retry_policy must be WakeRetryPolicy")
        if operator_adapter is not None and not callable(
            getattr(operator_adapter, "deliver_attention", None)
        ):
            raise TypeError("operator_adapter must support deliver_attention")
        if not callable(carrier_factory):
            raise TypeError("carrier_factory must be callable")
        from control_plane.dialogue_wake_canary_activation import DialogueWakeCanaryProfile

        if canary_profile is not None and type(canary_profile) is not DialogueWakeCanaryProfile:
            raise TypeError("canary_profile must be a closed DialogueWakeCanaryProfile")
        if canary_profile is not None and not callable(canary_current_facts_for) and (
            not isinstance(installed_release_sha, str)
            or not installed_release_sha
            or not isinstance(operation_key, str)
            or not operation_key
        ):
            raise TypeError("canary composition requires attested release and operation")
        if canary_profile is not None and not callable(canary_now_epoch_seconds):
            raise TypeError("canary_now_epoch_seconds is required for current submission")
        if historical_target_for is not None and not callable(historical_target_for):
            raise TypeError("historical_target_for must be callable or None")
        self._target_provider = target_provider
        self._retry_policy = retry_policy
        self._operator_adapter = operator_adapter
        self._carrier_factory = carrier_factory
        self._canary_profile = canary_profile
        self._canary_current_facts_for = canary_current_facts_for
        self._canary_now_epoch_seconds = canary_now_epoch_seconds
        self._historical_target_for = historical_target_for
        self._installed_release_sha = installed_release_sha
        self._operation_key = operation_key

    @property
    def canary_profile(self) -> Any:
        return self._canary_profile

    def reconcile_dialogue_sources(
        self, runtime: Runtime, request: DialogueSourceReconcileRequest
    ) -> dict[str, str]:
        """Reconcile one accepted source snapshot without provider access."""

        from control_plane.dialogue_source_resolution import (
            DialogueSourceObservation,
            DialogueSourceSnapshot,
            PhysicalDialogueSourceIdentity,
            attention_source_ref,
            correlated_source_ref,
        )
        from control_plane.executive_dialogue_observation import (
            ACTIVE_CURRENT_WORKER, TERMINAL_RESULT,
        )
        from control_plane.wake_events import canonical_json_bytes, mint_obligation_id
        from control_plane.wake_ledger import (
            LedgerPhase, SourceReadHealth, SourceResolutionCode,
            assert_causal, resolve_source, resolved_record,
        )
        from control_plane.wake_persist import WakeLedgerRepository
        from control_plane.session_targets import route_digest
        from common.agent_dialogue_turn_watcher import (
            TurnAction, TurnRoutingFacts, classify_turn,
        )

        profile = self._canary_profile
        if profile is None:
            return {"state": "NOT_APPLICABLE", "reason": "NONCANARY_PROFILE"}
        grant = profile.grant
        if grant is None or type(request.snapshot) is not DialogueSourceSnapshot:
            return {"state": "UNKNOWN", "reason": "CANARY_GRANT_UNAVAILABLE"}
        snapshot = request.snapshot
        if (
            request.parent.get("operation_key") != grant.operation_key
            or snapshot.operation_key != grant.operation_key
        ):
            return {"state": "UNKNOWN", "reason": "SOURCE_IDENTITY_DISAGREES"}
        messages = tuple(item.to_dict() for item in snapshot.messages)
        decision = classify_turn(
            parent=request.parent,
            messages=messages,
            routing=TurnRoutingFacts(
                bound_operation_key=grant.operation_key,
                bound_commission_fingerprint=snapshot.parent_fingerprint,
                root_job_id=grant.source_root_job_id,
                routing_workstream=None,
                source_workstream=str(request.parent["work_ref"]),
                ceo_target_bound=True,
                coo_target_bound=True,
            ),
        )
        if decision.action is TurnAction.REFUSE:
            return {"state": "UNKNOWN", "reason": "SOURCE_SEMANTICS_REFUSED"}
        repository = WakeLedgerRepository(runtime)
        try:
            with runtime.store.transaction() as connection:
                records = repository.list_ledger_records_on_connection(
                    connection, grant.obligation_id
                )
                assert_causal(records)
                if not records:
                    matches = 0
                    matched_physical = None
                    if decision.attention is not None:
                        classified_attention = attention_source_ref(
                            parent_fingerprint=snapshot.parent_fingerprint,
                            message_key=decision.attention.message_key,
                            target_seat=grant.target_seat,
                        )
                        if (
                            decision.attention.target_seat != grant.target_seat
                            or decision.attention.source_ref
                            != classified_attention
                        ):
                            return {
                                "state": "UNKNOWN",
                                "reason": "SOURCE_GRANT_DISAGREES",
                            }
                        for mode in (ACTIVE_CURRENT_WORKER, TERMINAL_RESULT):
                            candidate = {
                                "mode": mode,
                                "root_job_id": grant.source_root_job_id,
                                "job_id": grant.source_job_id,
                                "attempt_id": grant.source_attempt_id,
                                "worker_id": grant.source_worker_id,
                                "evidence_digest": grant.source_semantic_digest,
                            }
                            logical = correlated_source_ref(
                                attention_source_ref=classified_attention,
                                parent_fingerprint=snapshot.parent_fingerprint,
                                operation_key=snapshot.operation_key,
                                candidate=candidate,
                            )
                            if mint_obligation_id(
                                source_kind="agent_dialogue_attention",
                                source_ref=logical,
                                wake_kind="dialogue_turn_pending",
                            ) == grant.obligation_id:
                                matches += 1
                                matched_physical = (
                                    PhysicalDialogueSourceIdentity.create(
                                        logical_source_ref=logical,
                                        obligation_id=grant.obligation_id,
                                        observation=DialogueSourceObservation(
                                            workspace_id=snapshot.workspace_id,
                                            channel_id=snapshot.channel_id,
                                            thread_ts=snapshot.thread_ts,
                                            predecessor_message_key=(
                                                decision.attention.message_key
                                            ),
                                            predecessor_message_fingerprint=(
                                                decision.attention.message_fingerprint
                                            ),
                                        ),
                                        parent_fingerprint=(
                                            snapshot.parent_fingerprint
                                        ),
                                        operation_key=snapshot.operation_key,
                                        target_seat=grant.target_seat,
                                        candidate=candidate,
                                    )
                                )
                    if matches == 1:
                        assert matched_physical is not None
                        repository.assert_physical_source_request_available_on_connection(
                            connection,
                            matched_physical,
                            obligation_id=grant.obligation_id,
                        )
                        return {"state": "NO_RESOLUTION_REQUIRED", "reason": "SOURCE_PRESENT"}
                    if matches > 1:
                        return {
                            "state": "UNKNOWN",
                            "reason": "SOURCE_CANDIDATE_AMBIGUOUS",
                        }
                    return {"state": "ACK_REQUIRED", "reason": "ADVANCED_WITHOUT_REQUEST"}
                requested = records[0]
                obligation = requested.obligation
                physical = requested.physical_source
                if obligation is None or physical is None:
                    return {"state": "CARRIER_IDENTITY_UNAVAILABLE", "reason": "LEGACY_SOURCE_IDENTITY"}
                if (
                    physical.workspace_id != snapshot.workspace_id
                    or physical.channel_id != snapshot.channel_id
                    or physical.thread_ts != snapshot.thread_ts
                    or physical.parent_fingerprint != snapshot.parent_fingerprint
                    or physical.operation_key != snapshot.operation_key
                    or physical.obligation_id != grant.obligation_id
                ):
                    return {"state": "UNKNOWN", "reason": "SOURCE_CARRIER_DISAGREES"}
                candidate = physical.candidate
                if (
                    candidate.root_job_id != grant.source_root_job_id
                    or candidate.job_id != grant.source_job_id
                    or candidate.attempt_id != grant.source_attempt_id
                    or candidate.worker_id != grant.source_worker_id
                    or candidate.evidence_digest != grant.source_semantic_digest
                    or physical.target_seat != grant.target_seat
                    or obligation.root_job_id != grant.source_root_job_id
                    or obligation.job_id != grant.source_job_id
                    or obligation.attempt_id != grant.source_attempt_id
                    or obligation.declared_target_seat != grant.target_seat
                    or obligation.source_workstream != request.parent["work_ref"]
                ):
                    return {"state": "UNKNOWN", "reason": "SOURCE_GRANT_DISAGREES"}
                delivery_attempts = tuple(
                    record for record in records
                    if record.phase is LedgerPhase.DELIVERY_ATTEMPT
                )
                if len(delivery_attempts) > 1:
                    return {"state": "UNKNOWN", "reason": "SOURCE_ATTEMPT_AMBIGUOUS"}
                if delivery_attempts:
                    attempted = delivery_attempts[0]
                    effective_policy = hashlib.sha256(
                        canonical_json_bytes(
                            {
                                "base_policy_digest": grant.policy_digest,
                                "grant_digest": grant.digest,
                            }
                        )
                    ).hexdigest()[:16]
                    expected_route_digest = route_digest(
                        obligation_id=grant.obligation_id,
                        destination=str(attempted.destination_digest),
                        policy_digest=effective_policy,
                    )
                    if (
                        attempted.attempt_n != 1
                        or attempted.binding_id != grant.binding_id
                        or attempted.binding_generation != grant.binding_generation
                        or attempted.session_alias != grant.target_session_alias
                        or attempted.route_digest != expected_route_digest
                    ):
                        return {"state": "UNKNOWN", "reason": "SOURCE_ATTEMPT_DISAGREES"}
                phases = {record.phase for record in records}
                if LedgerPhase.SOURCE_RESOLVED in phases:
                    return {"state": "RECORDED", "reason": "SOURCE_ALREADY_RESOLVED"}
                predecessor_documents = tuple(
                    message for message in messages
                    if message["message_key"] == physical.predecessor_message_key
                    and message["fingerprint"] == physical.predecessor_message_fingerprint
                )
                initial_key = f"asd-initial-{snapshot.parent_fingerprint}"
                predecessor_proven = bool(predecessor_documents) or (
                    physical.predecessor_message_key == initial_key
                    and physical.predecessor_message_fingerprint == snapshot.parent_fingerprint
                )
                expected_attention = attention_source_ref(
                    parent_fingerprint=snapshot.parent_fingerprint,
                    message_key=physical.predecessor_message_key,
                    target_seat=physical.target_seat,
                )
                present = (
                    predecessor_proven
                    and decision.attention is not None
                    and decision.attention.source_ref == expected_attention
                )
                if present:
                    return {"state": "NO_RESOLUTION_REQUIRED", "reason": "SOURCE_PRESENT"}
                if LedgerPhase.TARGET_ACKNOWLEDGED not in phases:
                    if (
                        len(delivery_attempts) == 1
                        and LedgerPhase.DELIVERED in phases
                        and LedgerPhase.FAILED not in phases
                        and LedgerPhase.TARGET_UNAVAILABLE not in phases
                        and delivery_attempts[0].nudge_id is not None
                        and delivery_attempts[0].nudge_attempt_command_ids
                        == (delivery_attempts[0].command_id,)
                    ):
                        return {
                            "state": "ACK_REQUIRED",
                            "reason": "DELIVERED_ACK_PENDING",
                            "source_observation": {
                                "workspace_id": physical.workspace_id,
                                "channel_id": physical.channel_id,
                                "thread_ts": physical.thread_ts,
                                "predecessor_message_key": physical.predecessor_message_key,
                                "predecessor_message_fingerprint": physical.predecessor_message_fingerprint,
                            },
                        }
                    return {"state": "ACK_REQUIRED", "reason": "TARGET_ACK_REQUIRED"}
                successors = []
                initial_predecessor = (
                    physical.predecessor_message_key == initial_key
                    and physical.predecessor_message_fingerprint == snapshot.parent_fingerprint
                )
                for message in messages:
                    if (
                        message["reply_to_message_key"]
                        != (None if initial_predecessor else physical.predecessor_message_key)
                    ):
                        continue
                    actor = message["actor_ref"]
                    executive_target = (
                        actor["kind"] == "executive_surface"
                        and actor["seat"] == physical.target_seat
                    )
                    worker_target = (
                        physical.target_seat == "coo"
                        and actor["kind"] == "worker_attempt"
                        and actor["job_id"] == physical.candidate.job_id
                        and actor["attempt_id"] == physical.candidate.attempt_id
                        and actor["worker_id"] == physical.candidate.worker_id
                    )
                    if executive_target or worker_target:
                        successors.append(message)
                if not predecessor_proven or len(successors) != 1:
                    return {"state": "UNKNOWN", "reason": "SOURCE_SUCCESSOR_AMBIGUOUS"}
                successor = successors[0]
                by_key = {message["message_key"]: message for message in messages}
                causal_prefix = []
                cursor = successor
                while cursor is not None:
                    causal_prefix.append(cursor)
                    reply_to = cursor["reply_to_message_key"]
                    cursor = by_key.get(reply_to) if reply_to is not None else None
                causal_prefix.reverse()
                direct_decision = classify_turn(
                    parent=request.parent,
                    messages=causal_prefix,
                    routing=TurnRoutingFacts(
                        bound_operation_key=grant.operation_key,
                        bound_commission_fingerprint=snapshot.parent_fingerprint,
                        root_job_id=grant.source_root_job_id,
                        routing_workstream=None,
                        source_workstream=str(request.parent["work_ref"]),
                        ceo_target_bound=True,
                        coo_target_bound=True,
                    ),
                )
                if direct_decision.action is TurnAction.REFUSE:
                    return {"state": "UNKNOWN", "reason": "SOURCE_SUCCESSOR_REFUSED"}
                resolution = resolve_source(
                    obligation,
                    code=SourceResolutionCode.DIALOGUE_ATTENTION_ABSENT,
                    health=SourceReadHealth.HEALTHY,
                    source_present=False,
                    snapshot_digest=snapshot.digest,
                    evidence_refs=(str(successor["fingerprint"]),),
                )
                repository.append_records_on_connection(
                    connection, ((resolved_record(obligation, resolution), None),)
                )
                return {"state": "RECORDED", "reason": "SOURCE_RESOLVED"}
        except Exception:
            return {"state": "UNKNOWN", "reason": "SOURCE_RECONCILIATION_UNKNOWN"}

    async def reconcile_delayed_ack(
        self, runtime: Runtime, request: DialogueDelayedAckRequest
    ) -> dict[str, str]:
        """Attempt one provider ACK drain for an exact stored v2 delivery."""

        from control_plane.dialogue_source_resolution import PhysicalDialogueSourceIdentity
        from control_plane.wake_ledger import LedgerPhase, assert_causal
        from control_plane.wake_persist import WakeLedgerRepository

        profile = self._canary_profile
        if profile is None:
            return {"state": "NOT_APPLICABLE", "reason": "NONCANARY_PROFILE"}
        grant = profile.grant
        if grant is None:
            return {"state": "HOLD", "reason": "ACK_GRANT_UNAVAILABLE"}
        if request.parent.get("operation_key") != grant.operation_key:
            return {"state": "HOLD", "reason": "ACK_SOURCE_REFUSED"}
        repository = WakeLedgerRepository(runtime)
        persisted = repository.list_records(grant.obligation_id)
        records = tuple(item.record for item in persisted)
        try:
            assert_causal(records)
        except Exception:
            return {"state": "HOLD", "reason": "ACK_HISTORY_REFUSED"}
        if not persisted:
            return {"state": "HOLD", "reason": "ACK_HISTORY_MISSING"}
        requested = tuple(
            item for item in persisted
            if item.record.phase is LedgerPhase.WAKE_REQUESTED
        )
        if len(requested) != 1:
            return {"state": "HOLD", "reason": "ACK_HISTORY_REFUSED"}
        physical = requested[0].record.physical_source
        obligation = requested[0].obligation
        if (
            type(physical) is not PhysicalDialogueSourceIdentity
            or obligation is None
            or physical.operation_key != request.parent.get("operation_key")
            or physical.parent_fingerprint != request.parent.get("fingerprint")
            or request.source_observation.to_dict()
            != {
                "workspace_id": physical.workspace_id,
                "channel_id": physical.channel_id,
                "thread_ts": physical.thread_ts,
                "predecessor_message_key": physical.predecessor_message_key,
                "predecessor_message_fingerprint": physical.predecessor_message_fingerprint,
            }
            or physical.obligation_id != grant.obligation_id
            or physical.target_seat != grant.target_seat
            or physical.candidate.root_job_id != grant.source_root_job_id
            or physical.candidate.job_id != grant.source_job_id
            or physical.candidate.attempt_id != grant.source_attempt_id
            or physical.candidate.worker_id != grant.source_worker_id
            or physical.candidate.evidence_digest != grant.source_semantic_digest
        ):
            return {"state": "HOLD", "reason": "ACK_SOURCE_REFUSED"}
        carrier = self._carrier_factory(
            runtime=runtime,
            resolved=None,
            target=None,
            current_binding=None,
            retry_policy=self._retry_policy,
            generation=None,
            canary_profile=profile,
            pre_submit_guard=None,
            historical_context_for=lambda attempt: (
                self._historical_target_for(runtime, attempt)
                if callable(self._historical_target_for)
                else self._resolve_historical_target(runtime, attempt)
            ),
            historical_only=True,
            physical_source=physical,
        )
        history_matches = getattr(carrier, "delayed_ack_history_matches", None)
        if not callable(history_matches) or not history_matches(obligation):
            return {"state": "HOLD", "reason": "ACK_HISTORY_REFUSED"}
        phases = tuple(record.phase for record in records)
        if (
            LedgerPhase.TARGET_ACKNOWLEDGED in phases
            or LedgerPhase.SOURCE_RESOLVED in phases
        ):
            return {"state": "RECORDED", "reason": "ACK_ALREADY_RECORDED"}
        if (
            LedgerPhase.FAILED in phases
            or LedgerPhase.TARGET_UNAVAILABLE in phases
        ):
            return {"state": "HOLD", "reason": "ACK_HISTORY_INELIGIBLE"}
        method = getattr(carrier, "reconcile_delivered_ack", None)
        if not callable(method):
            return {"state": "HOLD", "reason": "ACK_CARRIER_UNAVAILABLE"}
        try:
            state = await method(request.source_observation, obligation)
        except Exception:
            return {"state": "EFFECT_UNKNOWN", "reason": "ACK_EFFECT_UNKNOWN"}
        if state.value == "RECORDED":
            return {"state": "RECORDED", "reason": "ACK_RECORDED"}
        if state.value == "EFFECT_UNKNOWN":
            return {"state": "EFFECT_UNKNOWN", "reason": "ACK_EFFECT_UNKNOWN"}
        return {"state": "HOLD", "reason": "ACK_NOT_RECORDED"}

    def _historical_carrier(self, runtime: Runtime, request: DialogueWakeRequest) -> Any:
        profile = self._canary_profile
        if profile is None:
            raise TypeError("historical carrier requires the closed canary profile")

        def resolve(attempt: Any) -> Any:
            provider = self._historical_target_for
            if callable(provider):
                return provider(runtime, attempt)
            return self._resolve_historical_target(runtime, attempt)

        return self._carrier_factory(
            runtime=runtime,
            resolved=None,
            target=None,
            current_binding=None,
            retry_policy=self._retry_policy,
            generation=None,
            canary_profile=profile,
            pre_submit_guard=None,
            historical_context_for=resolve,
            historical_only=True,
            physical_source=request.physical_source,
        )

    def _resolve_historical_target(self, runtime: Runtime, attempt: Any) -> Any:
        """Recover only the grant's immutable generation; never select a successor."""

        from control_plane.operator_harness_contract import runtime_binding_id_for
        from control_plane.session_targets import RuntimeBinding

        profile = self._canary_profile
        grant = None if profile is None else profile.grant
        if grant is None or attempt.attempt_n != 1:
            raise StateConflict("historical canary identity is unavailable")
        epoch, generation = runtime.operator_harness.generation_refs(
            grant.process_generation_id
        )
        if (
            epoch.attempt_id != grant.target_attempt_id
            or generation.process_generation_id != grant.process_generation_id
            or generation.generation_number != grant.binding_generation
            or runtime_binding_id_for(epoch.attempt_id, epoch.session_epoch_id)
            != grant.binding_id
        ):
            raise StateConflict("historical canary generation identity disagrees")
        with runtime.store.read() as connection:
            rows = connection.execute(
                """
                SELECT e.provider_session_id AS epoch_provider_session,
                       g.provider_session_id AS generation_provider_session
                FROM process_generations AS g
                JOIN harness_session_epochs AS e
                  ON e.session_epoch_id=g.session_epoch_id
                WHERE g.process_generation_id=?
                  AND e.attempt_id=?
                  AND g.generation_number=?
                """,
                (
                    grant.process_generation_id,
                    grant.target_attempt_id,
                    grant.binding_generation,
                ),
            ).fetchall()
        if (
            len(rows) != 1
            or not rows[0]["epoch_provider_session"]
            or rows[0]["generation_provider_session"]
            != rows[0]["epoch_provider_session"]
        ):
            raise StateConflict("historical provider identity is unavailable")
        binding = RuntimeBinding(
            session_alias=grant.target_session_alias,
            binding_id=grant.binding_id,
            binding_generation=grant.binding_generation,
            native_handle=str(rows[0]["epoch_provider_session"]),
            reasoning_surface=str(attempt.reasoning_surface),
        )
        return DialogueWakeHistoricalTarget(
            runtime_binding=binding,
            generation=generation,
            target_attempt_id=grant.target_attempt_id,
            operator_adapter=self._operator_adapter,
        )

    def _current_canary_facts(
        self,
        runtime: Runtime,
        request: DialogueWakeRequest,
        resolved: DialogueWakeTarget,
        base_route: Any,
    ) -> Any:
        """Derive all current admission facts from one fresh Runtime snapshot."""

        from control_plane.dialogue_wake_canary_activation import DialogueWakeCanaryCurrentFacts
        from control_plane.runtime_binding_projection import project_runtime_binding

        profile = self._canary_profile
        grant = None if profile is None else profile.grant
        if grant is None:
            raise StateConflict("current canary grant is unavailable")
        if (
            request.parent.get("operation_key") != self._operation_key
            or self._operation_key != grant.operation_key
            or request.candidate.root_job_id != grant.source_root_job_id
            or request.candidate.job_id != grant.source_job_id
            or request.candidate.attempt_id != grant.source_attempt_id
            or request.candidate.worker_id != grant.source_worker_id
            or request.candidate.evidence_digest != grant.source_semantic_digest
        ):
            raise StateConflict("current canary source grant disagrees")
        now_provider = self._canary_now_epoch_seconds
        assert callable(now_provider)
        with runtime.store.read() as connection:
            reader = object.__new__(ExecutiveControlService)
            source_facts = reader._runtime_dialogue_observation_facts(
                runtime,
                request.parent,
                connection=connection,
            )
            source_response = reduce_dialogue_observation(
                parent=request.parent,
                thread_ts=request.thread_ts,
                facts=source_facts,
            )
            if _dialogue_candidate_from_response(source_response) != request.candidate:
                raise StateConflict("current canary source candidate disagrees")
            source = runtime.current_harness_binding_source(
                resolved.target_attempt_id,
                connection=connection,
            )
            target = resolved.registry.get(resolved.runtime_binding.session_alias)
            binding = project_runtime_binding(
                runtime,
                resolved.target_attempt_id,
                target,
                connection=connection,
            )
            rows = connection.execute(
                """
                SELECT g.process_generation_id
                FROM process_generations AS g
                JOIN harness_session_epochs AS e
                  ON e.session_epoch_id=g.session_epoch_id
                WHERE e.attempt_id=? AND e.state='CURRENT'
                  AND g.executive_writer_held=1
                  AND g.ended_at_ms IS NULL
                  AND g.generation_number=?
                """,
                (resolved.target_attempt_id, binding.binding_generation),
            ).fetchall()
            if (
                len(rows) != 1
                or source.owner_seat != grant.target_seat
                or binding != resolved.runtime_binding
                or str(rows[0]["process_generation_id"])
                != resolved.process_generation_id
            ):
                raise StateConflict("current canary writer identity disagrees")
            facts = DialogueWakeCanaryCurrentFacts(
                installed_release_sha=str(self._installed_release_sha),
                operation_key=str(self._operation_key),
                source_root_job_id=request.candidate.root_job_id,
                source_job_id=request.candidate.job_id,
                source_attempt_id=request.candidate.attempt_id,
                source_worker_id=request.candidate.worker_id,
                source_semantic_digest=request.candidate.evidence_digest,
                obligation_id=request.obligation.obligation_id,
                target_seat=source.owner_seat,
                target_session_alias=binding.session_alias,
                target_attempt_id=resolved.target_attempt_id,
                binding_id=binding.binding_id,
                binding_generation=binding.binding_generation,
                process_generation_id=str(rows[0]["process_generation_id"]),
                policy_digest=base_route.policy_digest,
            )
            # The Executive clock is deliberately the final observation made
            # while this fresh read snapshot is still owned by the worker thread.
            now = now_provider()
        return facts, now

    async def historical_only(
        self,
        runtime: Runtime,
        request: DialogueWakeRequest,
    ) -> DialogueWakeResult:
        """Read or reconcile exact persisted canary history without current gates."""

        from control_plane.dialogue_wake_canary_activation import DialogueWakeCanaryActivationError
        from control_plane.wake_dispatcher import WakeEffectUnknownError

        if self._canary_profile is None or not isinstance(runtime, Runtime):
            return DialogueWakeResult("MISSING", "CANDIDATE_BINDING_REQUIRED")
        if request.operation not in {SUBMIT_WAKE, RECONCILE_WAKE}:
            return DialogueWakeResult("MISSING", "WAKE_REQUEST_REFUSED")
        grant = self._canary_profile.grant
        request_mismatch = (
            request.obligation.root_job_id != request.candidate.root_job_id
            or request.obligation.job_id != request.candidate.job_id
            or request.obligation.attempt_id != request.candidate.attempt_id
            or request.obligation.source_workstream != request.parent.get("work_ref")
            or (
                grant is not None
                and (
                    request.parent.get("operation_key") != grant.operation_key
                    or request.candidate.root_job_id != grant.source_root_job_id
                    or request.candidate.job_id != grant.source_job_id
                    or request.candidate.attempt_id != grant.source_attempt_id
                    or request.candidate.worker_id != grant.source_worker_id
                    or request.candidate.evidence_digest
                    != grant.source_semantic_digest
                    or request.obligation.obligation_id != grant.obligation_id
                )
            )
        )
        try:
            carrier = self._historical_carrier(runtime, request)
            has_attempt = carrier.has_persisted_attempt(request.obligation)
            if request_mismatch:
                if has_attempt:
                    return DialogueWakeResult("EFFECT_UNKNOWN", "WAKE_EFFECT_UNKNOWN")
                return DialogueWakeResult("MISSING", "WAKE_REQUEST_REFUSED")
            state = await carrier.reconcile(
                request.obligation,
                request.proposed_route,
            )
        except (DialogueWakeCanaryActivationError, WakeEffectUnknownError):
            return DialogueWakeResult("EFFECT_UNKNOWN", "WAKE_EFFECT_UNKNOWN")
        except Exception:
            return DialogueWakeResult("EFFECT_UNKNOWN", "WAKE_COORDINATION_EFFECT_UNKNOWN")
        reasons = {
            "MISSING": "WAKE_NOT_RECORDED",
            "RECORDED": "WAKE_RECORDED",
            "EFFECT_UNKNOWN": "WAKE_EFFECT_UNKNOWN",
        }
        return DialogueWakeResult(state.value, reasons[state.value])

    def _resolve_current_target(
        self,
        runtime: Runtime,
        request: DialogueWakeRequest,
    ) -> DialogueWakeTarget | None:
        from control_plane.runtime_binding_projection import project_runtime_binding
        from control_plane.session_targets import load_session_targets

        operator_adapter = self._operator_adapter
        if not callable(getattr(operator_adapter, "deliver_attention", None)):
            return None
        root_job_id = request.candidate.root_job_id
        seat = request.obligation.declared_target_seat
        resolved: list[DialogueWakeTarget] = []
        with runtime.store.read() as connection:
            registry = load_session_targets()
            rows = connection.execute(
                """
                SELECT current_attempt_id
                FROM jobs
                WHERE root_job_id=?
                  AND current_attempt_id IS NOT NULL
                  AND status IN ('RUNNING','CHECKPOINTED','CANCEL_REQUESTED')
                ORDER BY job_id
                """,
                (root_job_id,),
            ).fetchall()
            for row in rows:
                attempt_id = str(row["current_attempt_id"] or "")
                try:
                    source = runtime.current_harness_binding_source(
                        attempt_id,
                        connection=connection,
                    )
                    if source.owner_seat != seat:
                        continue
                    seat_map = registry.root_job_bindings.get(root_job_id, {})
                    alias = seat_map.get(seat)
                    target = (
                        registry.get(alias)
                        if alias is not None
                        else registry.resolve(seat)
                    )
                    if alias is None:
                        root_bindings = {
                            key: dict(value)
                            for key, value in registry.root_job_bindings.items()
                        }
                        root_bindings[root_job_id] = {
                            **root_bindings.get(root_job_id, {}),
                            seat: target.session_alias,
                        }
                        registry = registry.with_root_job_bindings(root_bindings)
                    binding = project_runtime_binding(
                        runtime,
                        attempt_id,
                        target,
                        connection=connection,
                    )
                    generation_rows = connection.execute(
                        """
                        SELECT g.process_generation_id
                        FROM process_generations AS g
                        JOIN harness_session_epochs AS e
                          ON e.session_epoch_id=g.session_epoch_id
                        WHERE e.attempt_id=?
                          AND e.state='CURRENT'
                          AND g.executive_writer_held=1
                          AND g.generation_number=?
                        """,
                        (attempt_id, binding.binding_generation),
                    ).fetchall()
                    if len(generation_rows) != 1:
                        continue
                    resolved.append(
                        DialogueWakeTarget(
                            registry=registry,
                            runtime_binding=binding,
                            target_attempt_id=attempt_id,
                            process_generation_id=str(
                                generation_rows[0]["process_generation_id"]
                            ),
                            operator_adapter=operator_adapter,
                        )
                    )
                except Exception:
                    continue
        return resolved[0] if len(resolved) == 1 else None

    async def __call__(
        self,
        runtime: Runtime,
        request: DialogueWakeRequest,
    ) -> DialogueWakeResult:
        from control_plane.runtime_binding_projection import project_runtime_binding
        from control_plane.session_targets import (
            RuntimeBinding,
            SessionTargetRegistry,
            route_obligation,
        )
        from control_plane.wake_dispatcher import (
            WakeEffectUnknownError,
            WakePreSubmitError,
        )
        from control_plane.dialogue_wake_canary_activation import (
            DialogueWakeCanaryActivationError,
            effective_dialogue_wake_canary_route,
            match_dialogue_wake_canary_activation,
        )

        if not isinstance(runtime, Runtime) or not isinstance(
            request, DialogueWakeRequest
        ):
            return DialogueWakeResult("MISSING", "WAKE_REQUEST_REFUSED")
        if (
            request.obligation.root_job_id != request.candidate.root_job_id
            or request.obligation.job_id != request.candidate.job_id
            or request.obligation.attempt_id != request.candidate.attempt_id
            or request.obligation.source_workstream != request.parent["work_ref"]
        ):
            return DialogueWakeResult("MISSING", "WAKE_REQUEST_REFUSED")
        profile = self._canary_profile
        if profile is not None:
            historical = await self.historical_only(runtime, request)
            if (
                historical.state != "MISSING"
                or request.operation == RECONCILE_WAKE
                or historical.reason != "WAKE_NOT_RECORDED"
            ):
                return historical
            if request.physical_source is None:
                return DialogueWakeResult("MISSING", "WAKE_REQUEST_REFUSED")
        provider = self._target_provider
        try:
            resolved = (
                provider(runtime, request.parent, request.obligation)
                if callable(provider)
                else self._resolve_current_target(runtime, request)
            )
        except Exception:
            return DialogueWakeResult(
                "MISSING", "STAGE_B1_RUNTIME_PROVIDER_REQUIRED"
            )
        if (
            not isinstance(resolved, DialogueWakeTarget)
            or not isinstance(resolved.registry, SessionTargetRegistry)
            or not isinstance(resolved.runtime_binding, RuntimeBinding)
        ):
            return DialogueWakeResult(
                "MISSING", "STAGE_B1_RUNTIME_PROVIDER_REQUIRED"
            )
        try:
            target = resolved.registry.get(resolved.runtime_binding.session_alias)
            current_binding = project_runtime_binding(
                runtime,
                resolved.target_attempt_id,
                target,
            )
            if current_binding != resolved.runtime_binding:
                return DialogueWakeResult("MISSING", "CURRENT_BINDING_REFUSED")
            authoritative_route = route_obligation(
                request.obligation,
                resolved.registry,
                binding=current_binding,
            )
            if authoritative_route != request.proposed_route:
                return DialogueWakeResult("MISSING", "WAKE_ROUTE_REFUSED")
            epoch, generation = runtime.operator_harness.generation_refs(
                resolved.process_generation_id
            )
            if (
                epoch.attempt_id != resolved.target_attempt_id
                or (
                    profile is None
                    and runtime.operator_harness.current_writer_generation(epoch)
                    != generation
                )
            ):
                return DialogueWakeResult("MISSING", "CURRENT_WRITER_REFUSED")
            carrier_route = authoritative_route
            extra_factory: dict[str, Any] = {}
            if profile is not None:
                current_provider = self._canary_current_facts_for
                now_provider = self._canary_now_epoch_seconds
                assert callable(now_provider)

                def validate_current() -> None:
                    if callable(current_provider):
                        facts = current_provider(
                            runtime, request, resolved, authoritative_route
                        )
                        now = now_provider()
                    else:
                        facts, now = self._current_canary_facts(
                            runtime, request, resolved, authoritative_route
                        )
                    match_dialogue_wake_canary_activation(
                        profile.grant,
                        facts,
                        now_epoch_seconds=now,
                    )

                validate_current()
                carrier_route = effective_dialogue_wake_canary_route(
                    profile, authoritative_route
                )

                def final_guard() -> None:
                    validate_current()

                extra_factory = {
                    "canary_profile": profile,
                    "pre_submit_guard": final_guard,
                    "historical_context_for": lambda attempt: (
                        self._historical_target_for(runtime, attempt)
                        if callable(self._historical_target_for)
                        else self._resolve_historical_target(runtime, attempt)
                    ),
                    "historical_only": False,
                    "physical_source": request.physical_source,
                }
            carrier = self._carrier_factory(
                runtime=runtime,
                resolved=resolved,
                target=target,
                current_binding=current_binding,
                retry_policy=self._retry_policy,
                generation=generation,
                **extra_factory,
            )
        except DialogueWakeCanaryActivationError:
            return DialogueWakeResult("MISSING", "WAKE_TARGET_UNAVAILABLE")
        except Exception:
            return DialogueWakeResult("MISSING", "WAKE_TARGET_UNAVAILABLE")

        try:
            if request.operation == RECONCILE_WAKE:
                state = await carrier.reconcile(
                    request.obligation,
                    carrier_route,
                )
                reasons = {
                    "MISSING": "WAKE_NOT_RECORDED",
                    "RECORDED": "WAKE_RECORDED",
                    "EFFECT_UNKNOWN": "WAKE_EFFECT_UNKNOWN",
                }
                return DialogueWakeResult(state.value, reasons[state.value])
            if request.operation != SUBMIT_WAKE:
                return DialogueWakeResult("MISSING", "WAKE_REQUEST_REFUSED")
            await carrier.submit(request.obligation, carrier_route)
            return DialogueWakeResult("RECORDED", "WAKE_RECORDED")
        except WakePreSubmitError:
            return DialogueWakeResult("MISSING", "WAKE_TARGET_UNAVAILABLE")
        except WakeEffectUnknownError:
            return DialogueWakeResult("EFFECT_UNKNOWN", "WAKE_EFFECT_UNKNOWN")
        except Exception:
            return DialogueWakeResult(
                "EFFECT_UNKNOWN", "WAKE_COORDINATION_EFFECT_UNKNOWN"
            )


@dataclasses.dataclass(frozen=True)
class ServiceConfig:
    """Reviewed host configuration; requests cannot override these values."""

    runtime_root: Path
    socket_path: Path
    proof_source_repository: Path
    proof_workspace_root: Path
    proof_base_sha: str
    proof_branch: str = "codex/phase1c-a-proof"
    proof_shared_gid: int | None = None
    backup_root: Path | None = None
    worker_id: str = "codex-01"
    worker_account_label: str = "dedicated-codex-home"
    worker_type: str = "codex-cli"
    provider: str = "codex"
    quota_class: str = "codex-native"
    model: str = "gpt-5.6-sol"
    effort: str = "xhigh"
    cost_class: str = "standard"
    coo_autonomy_armed: bool = False
    coo_operator_harness_armed: bool = False
    coo_tick_interval_seconds: float = 15.0
    coo_model_alias: str = "coo.sealed"
    coo_quota_class: str = "codex-coo"
    coo_default_quota_class: str = "codex-coo-default"
    coo_operator_model_alias: str = "coo.operator.readonly"
    coo_operator_quota_class: str = "codex-coo-operator"
    terminal_return_armed: bool = False
    terminal_return_socket_path: Path | None = None
    operator_harness_binary_digest: str = "0" * 64
    operator_harness_version: str = "unproven"
    allowed_peer_uids: tuple[int, ...] = ()
    max_request_bytes: int = DEFAULT_MAX_REQUEST_BYTES
    max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES
    shutdown_grace_seconds: float = 10.0

    def __post_init__(self) -> None:
        for field_name in (
            "runtime_root",
            "socket_path",
            "proof_source_repository",
            "proof_workspace_root",
        ):
            value = Path(getattr(self, field_name))
            if not value.is_absolute():
                raise ValueError(f"{field_name} must be absolute")
            object.__setattr__(self, field_name, value.resolve(strict=False))
        source = self.proof_source_repository
        workspace_root = self.proof_workspace_root
        if source == workspace_root or source in workspace_root.parents or workspace_root in source.parents:
            raise ValueError("proof source repository and workspace root must not overlap")
        if self.backup_root is not None:
            backup_root = Path(self.backup_root)
            if not backup_root.is_absolute():
                raise ValueError("backup_root must be absolute")
            object.__setattr__(self, "backup_root", backup_root.resolve(strict=False))
        base_sha = str(self.proof_base_sha).strip().lower()
        if re.fullmatch(r"[0-9a-f]{40,64}", base_sha) is None:
            raise ValueError("proof_base_sha must be a full hexadecimal Git object id")
        object.__setattr__(self, "proof_base_sha", base_sha)
        for field_name in (
            "worker_id",
            "quota_class",
            "coo_quota_class",
            "coo_default_quota_class",
            "coo_operator_quota_class",
        ):
            if _ID_RE.fullmatch(str(getattr(self, field_name))) is None:
                raise ValueError(f"invalid {field_name}")
        if not isinstance(self.coo_autonomy_armed, bool):
            raise ValueError("coo_autonomy_armed must be boolean")
        if not isinstance(self.coo_operator_harness_armed, bool):
            raise ValueError("coo_operator_harness_armed must be boolean")
        if self.coo_operator_harness_armed and not self.coo_autonomy_armed:
            raise ValueError(
                "the COO Operator Harness cannot be armed while COO autonomy is off"
            )
        if not isinstance(self.terminal_return_armed, bool):
            raise ValueError("terminal-return arming must be boolean")
        terminal_fields_present = self.terminal_return_socket_path is not None
        if self.terminal_return_armed and not terminal_fields_present:
            raise ValueError(
                "terminal-return arming requires the Relay socket"
            )
        if terminal_fields_present:
            terminal_socket = Path(self.terminal_return_socket_path)
            if not terminal_socket.is_absolute():
                raise ValueError("terminal-return socket path must be absolute")
            terminal_socket = terminal_socket.resolve(strict=False)
            if terminal_socket == self.socket_path:
                raise ValueError(
                    "terminal-return Agent Relay socket must differ from the control socket"
                )
            object.__setattr__(self, "terminal_return_socket_path", terminal_socket)
        for field_name in ("coo_model_alias", "coo_operator_model_alias"):
            alias = str(getattr(self, field_name)).strip().lower()
            if _ID_RE.fullmatch(alias) is None:
                raise ValueError(f"invalid {field_name}")
            object.__setattr__(self, field_name, alias)
        quota_names = {
            self.quota_class,
            self.coo_quota_class,
            self.coo_default_quota_class,
            self.coo_operator_quota_class,
        }
        if len(quota_names) != 4:
            raise ValueError("proof and COO quota classes must be distinct")
        digest = str(self.operator_harness_binary_digest).strip().lower()
        if re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise ValueError("operator_harness_binary_digest must be SHA-256")
        object.__setattr__(self, "operator_harness_binary_digest", digest)
        version = str(self.operator_harness_version).strip()
        if not version or len(version) > 64:
            raise ValueError("operator_harness_version is invalid")
        object.__setattr__(self, "operator_harness_version", version)
        if not 1.0 <= float(self.coo_tick_interval_seconds) <= 3600.0:
            raise ValueError("coo_tick_interval_seconds must be between 1 and 3600")
        if not str(self.proof_branch).startswith("codex/"):
            raise ValueError("proof_branch must remain under codex/")
        if self.proof_shared_gid is not None and int(self.proof_shared_gid) < 0:
            raise ValueError("proof_shared_gid must be a non-negative integer")
        if not 1024 <= int(self.max_request_bytes) <= 1024 * 1024:
            raise ValueError("max_request_bytes must be between 1 KiB and 1 MiB")
        if not 4096 <= int(self.max_response_bytes) <= 16 * 1024 * 1024:
            raise ValueError("max_response_bytes must be between 4 KiB and 16 MiB")
        if not 0.1 <= float(self.shutdown_grace_seconds) <= 60:
            raise ValueError("shutdown_grace_seconds must be between 0.1 and 60 seconds")


def _jsonable(value: Any) -> Any:
    if hasattr(value, "to_dict"):
        return _jsonable(value.to_dict())
    if dataclasses.is_dataclass(value):
        return _jsonable(dataclasses.asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "value") and isinstance(getattr(value, "value"), str):
        return value.value
    return value


def _canonical_json(value: Any) -> bytes:
    return (
        json.dumps(
            _jsonable(value),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
    )


def _peer_uid(connection: socket.socket) -> int | None:
    """Return the local peer uid where the platform exposes it."""

    getpeereid = getattr(connection, "getpeereid", None)
    if callable(getpeereid):
        uid, _gid = getpeereid()
        return int(uid)
    if sys.platform == "darwin":
        libc = ctypes.CDLL(None, use_errno=True)
        function = libc.getpeereid
        function.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_uint32), ctypes.POINTER(ctypes.c_uint32)]
        function.restype = ctypes.c_int
        uid = ctypes.c_uint32()
        gid = ctypes.c_uint32()
        if function(connection.fileno(), ctypes.byref(uid), ctypes.byref(gid)) != 0:
            error = ctypes.get_errno()
            raise OSError(error, os.strerror(error))
        return int(uid.value)
    if hasattr(socket, "SO_PEERCRED"):
        size = struct.calcsize("3i")
        raw = connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, size)
        _pid, uid, _gid = struct.unpack("3i", raw)
        return int(uid)
    return None


def _require_listening_if_queryable(listener: socket.socket) -> None:
    """Check SO_ACCEPTCONN where AF_UNIX exposes it (Darwin may not)."""

    try:
        accepting = listener.getsockopt(socket.SOL_SOCKET, socket.SO_ACCEPTCONN)
    except OSError as exc:
        unsupported = {
            errno.EINVAL,
            getattr(errno, "ENOPROTOOPT", -1),
            getattr(errno, "EOPNOTSUPP", -1),
        }
        if exc.errno not in unsupported:
            raise
        return
    if accepting != 1:
        raise ServiceError("activated control socket is not listening")


def activate_launchd_socket(name: str) -> socket.socket:
    """Claim exactly one named launchd listener without trusting an fd env var."""

    if sys.platform != "darwin":
        raise ServiceError("launchd socket activation is available only on macOS")
    if not isinstance(name, str) or _ID_RE.fullmatch(name) is None:
        raise ServiceError("invalid launchd socket name")
    libc = ctypes.CDLL(None, use_errno=True)
    function = libc.launch_activate_socket
    function.argtypes = [
        ctypes.c_char_p,
        ctypes.POINTER(ctypes.POINTER(ctypes.c_int)),
        ctypes.POINTER(ctypes.c_size_t),
    ]
    function.restype = ctypes.c_int
    values = ctypes.POINTER(ctypes.c_int)()
    count = ctypes.c_size_t()
    result = function(name.encode("utf-8"), ctypes.byref(values), ctypes.byref(count))
    if result != 0:
        raise ServiceError(f"launchd did not activate socket {name!r}: error {result}")
    try:
        if count.value != 1:
            for index in range(count.value):
                os.close(int(values[index]))
            raise ServiceError(
                f"launchd socket {name!r} returned {count.value} descriptors; expected one"
            )
        listener = socket.socket(fileno=int(values[0]))
    finally:
        libc.free(values)
    try:
        if listener.family != socket.AF_UNIX or listener.type & socket.SOCK_STREAM == 0:
            raise ServiceError("launchd control listener is not AF_UNIX/SOCK_STREAM")
        _require_listening_if_queryable(listener)
        listener.setblocking(False)
        return listener
    except Exception:
        listener.close()
        raise


class _ModuleBackupBackend:
    """Lazy adapter so the service can land independently of backup helpers."""

    @staticmethod
    def _module() -> Any:
        try:
            from control_plane import executive_backup
        except ImportError as exc:  # pragma: no cover - exercised before sibling lands
            raise ServiceError("Executive backup support is not installed") from exc
        return executive_backup

    def create_online_backup(self, store: Any, destination_dir: Path) -> Any:
        function = getattr(self._module(), "create_online_backup", None)
        if not callable(function):
            raise ServiceError("Executive backup module has no create_online_backup()")
        return function(store, destination_dir)

    def verify_backup(
        self, database_path: Path, manifest_path: Path | None = None
    ) -> Any:
        function = getattr(self._module(), "verify_backup", None)
        if not callable(function):
            raise ServiceError("Executive backup module has no verify_backup()")
        return function(database_path, manifest_path)


class ExecutiveControlService:
    """One private AF_UNIX service around one durable Executive runtime."""

    def __init__(
        self,
        config: ServiceConfig,
        *,
        runtime_factory: Callable[[Path], Runtime] = Runtime.at,
        supervisor_factory: Callable[[Runtime], SupervisorProtocol] | None = None,
        operator_supervisor_factory: (
            Callable[[Runtime, SupervisorProtocol], OperatorSupervisorProtocol]
            | None
        ) = None,
        operator_identity_verifier: Callable[[], Awaitable[None]] | None = None,
        autonomy_guard: Callable[[], None] | None = None,
        backup_backend: BackupBackendProtocol | None = None,
        activated_socket: socket.socket | None = None,
        service_state: str = "READY",
        canary_loader: Callable[[], Mapping[str, Any]] | None = None,
        ceo_ingress_socket_path: Path | str | None = None,
        ceo_ingress_peer_uid: int | None = None,
        ceo_ingress_grounding_provider: "ceo_ingress.GroundingProvider | None" = None,
        ceo_ingress_dialogue_source_provider: (
            CeoIngressDialogueSourceProvider | None
        ) = None,
        ceo_ingress_armed: bool = False,
        ceo_ingress_activated_socket: socket.socket | None = None,
        terminal_return_projector: TerminalReturnProjector | None = None,
        terminal_return_projector_factory: (
            TerminalReturnProjectorFactory | None
        ) = None,
        terminal_return_binding_resolver: Any | None = None,
        dialogue_observation_socket_path: Path | str | None = None,
        dialogue_observation_peer_uid: int | None = None,
        dialogue_observation_group_gid: int | None = None,
        dialogue_observation_facts_provider: (
            DialogueObservationFactsProvider | None
        ) = None,
        dialogue_wake_handler: DialogueWakeHandler | None = None,
        dialogue_observation_activated_socket: socket.socket | None = None,
    ) -> None:
        self.config = config
        self._runtime_factory = runtime_factory
        self._supervisor_factory = supervisor_factory
        self._operator_supervisor_factory = operator_supervisor_factory
        self._operator_identity_verifier = operator_identity_verifier
        self._autonomy_guard = autonomy_guard
        if self.config.coo_autonomy_armed and not callable(self._autonomy_guard):
            raise ValueError("armed COO autonomy requires an autonomy guard")
        self._backup_backend = backup_backend or _ModuleBackupBackend()
        if activated_socket is not None and activated_socket.family != socket.AF_UNIX:
            raise ValueError("activated_socket must use AF_UNIX")
        if activated_socket is not None:
            bound = activated_socket.getsockname()
            if isinstance(bound, bytes):
                bound = os.fsdecode(bound)
            if (
                not isinstance(bound, str)
                or not bound
                or bound.startswith("\0")
                or Path(bound).resolve(strict=False) != config.socket_path
            ):
                raise ValueError("activated_socket path does not match ServiceConfig")
            try:
                _require_listening_if_queryable(activated_socket)
            except ServiceError as exc:
                raise ValueError("activated_socket must already be listening") from exc
        self._activated_socket = activated_socket
        self._launchd_activated = activated_socket is not None
        self.runtime: Runtime | None = None
        self.supervisor: SupervisorProtocol | None = None
        self.operator_supervisor: OperatorSupervisorProtocol | None = None
        self._server: asyncio.AbstractServer | None = None
        self._lock_fd: int | None = None
        self._dispatch_lock = asyncio.Lock()
        self._workspace_lock = asyncio.Lock()
        self._coo_cycle_lock = asyncio.Lock()
        self._dispatch_tasks: dict[str, asyncio.Task[Any]] = {}
        self._dispatch_errors: dict[str, str] = {}
        # Default-off composition.  Agent Dialogue owns the concrete Relay
        # projector and injects its factory at the host composition edge; the
        # Executive control plane never reaches back into an integration.
        if self.config.terminal_return_armed:
            if terminal_return_projector is not None:
                raise ValueError(
                    "armed terminal-return composition cannot replace its canonical projector"
                )
            if terminal_return_binding_resolver is not None:
                raise ValueError(
                    "armed terminal-return composition owns its Runtime resolver"
                )
            if not callable(terminal_return_projector_factory):
                raise ValueError(
                    "armed terminal-return composition requires an injected "
                    "Agent Dialogue projector factory"
                )
            self._terminal_return_projector = terminal_return_projector_factory(
                lambda: self._require_runtime(),
                Path(self.config.terminal_return_socket_path),
            )
            if not all(
                callable(getattr(self._terminal_return_projector, method, None))
                for method in ("project", "reconcile")
            ):
                raise ValueError(
                    "terminal-return projector factory must return a projector "
                    "with project() and reconcile()"
                )
        else:
            if (
                terminal_return_binding_resolver is not None
                or terminal_return_projector_factory is not None
            ):
                raise ValueError(
                    "terminal-return factory or binding resolver requires explicit arming"
                )
            self._terminal_return_projector = terminal_return_projector
        # Process-local coalescing only. Runtime Events remain the durable phase
        # authority; different candidates never wait behind one global I/O lock.
        self._terminal_return_registry_lock = asyncio.Lock()
        self._terminal_return_flights: dict[
            str, tuple[str, asyncio.Task[None]]
        ] = {}
        self._terminal_return_requires_source = bool(
            self.config.terminal_return_armed
        )
        self._terminal_return_last_diagnostic: str | None = None
        self._coo_execution_binding = self._load_coo_execution_binding()
        self._coo_tick_task: asyncio.Task[Any] | None = None
        self._coo_shutdown_event: asyncio.Event | None = None
        self._coo_action_tasks: set[asyncio.Task[Any]] = set()
        self._coo_last_outcome: dict[str, Any] | None = None
        self._coo_last_error: str | None = None
        self._coo_last_tick_at: str | None = None
        self._closing = False
        self._startup_reconciliation: list[Any] = []
        self._started_at: str | None = None
        if service_state not in {"READY", "AWAITING_CANARY"}:
            raise ValueError("service_state must be READY or AWAITING_CANARY")
        self._service_state = service_state
        self._canary_loader = canary_loader
        self.instance_id = f"executive-service-{uuid4().hex}"

        # --- MAS-75 PR-A: optional dedicated CeoIngress composition --------
        #
        # Absent (the default) => byte-compatible-unchanged current behavior
        # (adjudication §8.2, R2 §3): no second listener, no startup latch, no
        # ingress handler drain set is ever populated.  One process / one
        # Runtime / one service lock still governs both listeners when
        # present (§8.1) — CeoIngress never opens its own Runtime or lock.
        if ceo_ingress_socket_path is None:
            if ceo_ingress_activated_socket is not None:
                raise ValueError(
                    "ceo_ingress_activated_socket requires ceo_ingress_socket_path"
                )
            if ceo_ingress_peer_uid is not None or ceo_ingress_grounding_provider is not None:
                raise ValueError(
                    "ceo_ingress_peer_uid/ceo_ingress_grounding_provider require "
                    "ceo_ingress_socket_path"
                )
            self._ceo_ingress_socket_path: Path | None = None
        else:
            resolved_ceo_ingress_path = Path(ceo_ingress_socket_path)
            if not resolved_ceo_ingress_path.is_absolute():
                raise ValueError("ceo_ingress_socket_path must be absolute")
            resolved_ceo_ingress_path = resolved_ceo_ingress_path.resolve(strict=False)
            # §17.1: ingress path same as Operator path -> constructor/
            # composition refusal.  The two sockets are transport separation,
            # never one path serving both surfaces.
            if resolved_ceo_ingress_path == config.socket_path:
                raise ValueError(
                    "ceo_ingress_socket_path must differ from the Operator socket_path"
                )
            if (
                config.terminal_return_socket_path is not None
                and resolved_ceo_ingress_path
                == config.terminal_return_socket_path
            ):
                raise ValueError(
                    "terminal-return Relay socket must differ from CeoIngress"
                )
            if ceo_ingress_peer_uid is None:
                raise ValueError(
                    "ceo_ingress_peer_uid is required when ceo_ingress_socket_path is set"
                )
            if ceo_ingress_grounding_provider is None:
                raise ValueError(
                    "ceo_ingress_grounding_provider is required when "
                    "ceo_ingress_socket_path is set"
                )
            if ceo_ingress_activated_socket is not None:
                if ceo_ingress_activated_socket.family != socket.AF_UNIX:
                    raise ValueError("ceo_ingress_activated_socket must use AF_UNIX")
                bound = ceo_ingress_activated_socket.getsockname()
                if isinstance(bound, bytes):
                    bound = os.fsdecode(bound)
                if (
                    not isinstance(bound, str)
                    or not bound
                    or bound.startswith("\0")
                    or Path(bound).resolve(strict=False) != resolved_ceo_ingress_path
                ):
                    raise ValueError(
                        "ceo_ingress_activated_socket path does not match "
                        "ceo_ingress_socket_path"
                    )
                try:
                    _require_listening_if_queryable(ceo_ingress_activated_socket)
                except ServiceError as exc:
                    raise ValueError(
                        "ceo_ingress_activated_socket must already be listening"
                    ) from exc
            self._ceo_ingress_socket_path = resolved_ceo_ingress_path
        self._ceo_ingress_peer_uid = ceo_ingress_peer_uid
        self._ceo_ingress_grounding_provider = ceo_ingress_grounding_provider
        if (
            ceo_ingress_dialogue_source_provider is not None
            and not callable(ceo_ingress_dialogue_source_provider)
        ):
            raise ValueError("ceo_ingress_dialogue_source_provider must be callable")
        self._ceo_ingress_dialogue_source_provider = (
            ceo_ingress_dialogue_source_provider
        )
        # A trusted dialogue-source provider is required at admission time, not
        # at service construction.  Keeping startup independent of that provider
        # lets the same armed process reconcile an already-admitted terminal
        # result while the admission source is temporarily unavailable.
        # §9: host-owned/injected policy, default false.  Never set by a
        # request; PR-A models it as constructor/test policy only.
        self._ceo_ingress_armed = bool(ceo_ingress_armed)
        self._ceo_ingress_activated_socket = ceo_ingress_activated_socket
        self._ceo_ingress_launchd_activated = ceo_ingress_activated_socket is not None
        self._ceo_ingress_server: asyncio.AbstractServer | None = None
        # R1 §2.1 in-memory, non-durable startup/readiness latch.  Process
        # lifecycle only; grants no durable authority and is never set by a
        # request.
        self._ceo_ingress_ready = False
        # §14.1 in-memory handler drain set.  No durable request registry,
        # lease, or table backs this.
        self._ceo_ingress_tasks: set[asyncio.Task[Any]] = set()

        # Optional W3C coordination listener.  Observation remains read-only;
        # Wake requests are re-authorized and executed only through existing
        # Executive-owned Stage-B1 owners.  The listener shares this process,
        # Runtime, service lock, startup reconciliation and shutdown owner.  An
        # absent path is the byte-compatible default-disabled composition.
        if dialogue_observation_socket_path is None:
            if any(
                value is not None
                for value in (
                    dialogue_observation_peer_uid,
                    dialogue_observation_group_gid,
                    dialogue_observation_facts_provider,
                    dialogue_wake_handler,
                    dialogue_observation_activated_socket,
                )
            ):
                raise ValueError(
                    "dialogue observation fields require dialogue_observation_socket_path"
                )
            self._dialogue_observation_socket_path: Path | None = None
        else:
            raw_observation_path = Path(dialogue_observation_socket_path)
            if not raw_observation_path.is_absolute() or "\x00" in os.fspath(
                raw_observation_path
            ):
                raise ValueError("dialogue observation socket path must be absolute")
            observation_path = Path(os.path.normpath(os.fspath(raw_observation_path)))
            forbidden = {
                config.socket_path,
                config.terminal_return_socket_path,
                self._ceo_ingress_socket_path,
            }
            if observation_path in forbidden:
                raise ValueError(
                    "dialogue observation socket must be distinct from every service path"
                )
            if dialogue_observation_peer_uid != 457:
                raise ValueError("dialogue observation peer uid must be Agent Relay uid 457")
            if (
                isinstance(dialogue_observation_group_gid, bool)
                or not isinstance(dialogue_observation_group_gid, int)
                or dialogue_observation_group_gid < 0
            ):
                raise ValueError("dialogue observation group gid is required")
            if (
                dialogue_observation_facts_provider is not None
                and not callable(dialogue_observation_facts_provider)
            ):
                raise ValueError("dialogue observation facts provider must be callable")
            if dialogue_wake_handler is not None and not callable(
                dialogue_wake_handler
            ):
                raise ValueError("dialogue Wake handler must be callable")
            if dialogue_observation_activated_socket is not None:
                if dialogue_observation_activated_socket.family != socket.AF_UNIX:
                    raise ValueError(
                        "dialogue_observation_activated_socket must use AF_UNIX"
                    )
                bound = dialogue_observation_activated_socket.getsockname()
                if isinstance(bound, bytes):
                    bound = os.fsdecode(bound)
                if (
                    not isinstance(bound, str)
                    or not bound
                    or bound.startswith("\0")
                    or Path(os.path.normpath(bound)) != observation_path
                ):
                    raise ValueError(
                        "dialogue observation activated socket path mismatch"
                    )
                try:
                    _require_listening_if_queryable(
                        dialogue_observation_activated_socket
                    )
                except ServiceError as exc:
                    raise ValueError(
                        "dialogue observation activated socket must already be listening"
                    ) from exc
            self._dialogue_observation_socket_path = observation_path
        if self._dialogue_observation_socket_path is not None:
            self._dialogue_observation_peer_uid = dialogue_observation_peer_uid
            self._dialogue_observation_group_gid = dialogue_observation_group_gid
            self._dialogue_observation_facts_provider = (
                dialogue_observation_facts_provider
                if dialogue_observation_facts_provider is not None
                else self._runtime_dialogue_observation_facts
            )
            self._dialogue_wake_handler = dialogue_wake_handler
            self._dialogue_observation_activated_socket = (
                dialogue_observation_activated_socket
            )
            self._dialogue_observation_launchd_activated = (
                dialogue_observation_activated_socket is not None
            )
            self._dialogue_observation_server: asyncio.AbstractServer | None = None
            self._dialogue_observation_ready = False
            self._dialogue_observation_tasks: set[asyncio.Task[Any]] = set()
            self._dialogue_observation_inode: tuple[int, int] | None = None

    def _load_coo_execution_binding(self) -> dict[str, Any]:
        """Resolve one reviewed sealed-COO alias into host-owned Job identity."""

        try:
            router = ModelRouter.load()
            alias = router.model_aliases[self.config.coo_model_alias]
            profile = router.capability_registry.resolve(alias.execution_profile_id)
            operator_alias = router.model_aliases[
                self.config.coo_operator_model_alias
            ]
            operator_profile = router.capability_registry.resolve(
                operator_alias.execution_profile_id
            )
        except (KeyError, RoutingPolicyError, CapabilityPolicyError) as exc:
            raise ValueError(f"configured COO execution alias is invalid: {exc}") from exc
        if (
            not alias.worker_eligible
            or alias.adapter_id != "codex-cli"
            or profile.execution_surface != "codex-exec"
            or not profile.write_capable
            or profile.auth_realm != "dedicated-worker-account"
            or profile.approval_policy != "never"
            or profile.network_policy != "disabled"
            or profile.native_helper_policy.value != "DISABLED"
            or profile.skills
            or profile.mcp_servers
            or profile.plugins
        ):
            raise ValueError(
                "configured COO alias must be a sealed, extension-free, write-capable Codex worker"
            )
        if (
            not operator_alias.worker_eligible
            or operator_alias.adapter_id != "codex-cli"
            or operator_profile.execution_surface != "codex-app-server"
            or operator_profile.write_capable
            or operator_profile.auth_realm != "dedicated-worker-account"
            or operator_profile.sandbox_policy != "read-only"
            or operator_profile.approval_policy != "never"
            or operator_profile.network_policy != "disabled"
            or operator_profile.native_helper_policy.value
            != "PARENT_READ_ONLY_CEILING"
            or operator_profile.native_helper is None
            or operator_profile.skills
            or operator_profile.profile_id
            != "operator.appserver.readonly.docs-mcp.native-helper.v1"
            or operator_profile.mcp_servers != ("openai-developer-docs-v1",)
            or operator_profile.plugins
        ):
            raise ValueError(
                "configured COO operator alias must be read-only and use the "
                "reviewed depth-one docs-MCP native-helper App Server profile"
            )
        binding = {
            "eligible_quota_classes": sorted(
                {
                    self.config.coo_quota_class,
                    self.config.coo_default_quota_class,
                }
            ),
            "provider": alias.provider_alias,
            "model": alias.model,
            "effort": alias.effort,
            "cost_class": alias.cost_class,
            "base_sha": self.config.proof_base_sha,
            "routing_policy_version": router.policy_version,
            "execution_profile_id": alias.execution_profile_id,
            "execution_profile_digest": alias.execution_profile_digest,
            "capability_policy_version": alias.capability_policy_version,
            "capability_policy_digest": alias.capability_policy_digest,
            "operator_eligible_quota_classes": [
                self.config.coo_operator_quota_class
            ],
            "operator_provider": operator_alias.provider_alias,
            "operator_model": operator_alias.model,
            "operator_effort": operator_alias.effort,
            "operator_cost_class": operator_alias.cost_class,
            "operator_routing_policy_version": router.policy_version,
            "operator_execution_profile_id": operator_alias.execution_profile_id,
            "operator_execution_profile_digest": (
                operator_alias.execution_profile_digest
            ),
            "operator_capability_policy_version": (
                operator_alias.capability_policy_version
            ),
            "operator_capability_policy_digest": (
                operator_alias.capability_policy_digest
            ),
            "operator_harness_binary_digest": (
                self.config.operator_harness_binary_digest
            ),
            "operator_harness_version": self.config.operator_harness_version,
            "operator_harness_armed": self.config.coo_operator_harness_armed,
        }
        if set(binding) != set(V2_HOST_EXECUTION_BINDING_KEYS):
            raise ValueError("configured COO host binding fields drifted")
        return binding

    def _require_current_coo_binding(self) -> dict[str, Any]:
        current = self._load_coo_execution_binding()
        if current != self._coo_execution_binding:
            raise ServiceError("installed COO routing/capability policy drifted")
        return dict(current)

    @property
    def ceo_ingress_socket_path(self) -> Path | None:
        return self._ceo_ingress_socket_path

    @property
    def ceo_ingress_armed(self) -> bool:
        return self._ceo_ingress_armed

    @property
    def ceo_ingress_ready(self) -> bool:
        """The R1/R2 in-memory startup latch — true only after BOTH listeners
        have started serving in dual-listener mode."""

        return self._ceo_ingress_ready

    @property
    def dialogue_observation_socket_path(self) -> Path | None:
        return self._dialogue_observation_socket_path

    @property
    def dialogue_observation_ready(self) -> bool:
        return bool(getattr(self, "_dialogue_observation_ready", False))

    @property
    def socket_path(self) -> Path:
        return self.config.socket_path

    @property
    def service_state(self) -> str:
        return self._service_state

    def _require_current_autonomy(self) -> None:
        if not self.config.coo_autonomy_armed:
            return
        guard = self._autonomy_guard
        if guard is None:  # constructor proves this; retain a fail-closed seam.
            self._service_state = "QUARANTINED"
            raise StateConflict("Executive autonomy receipt refused")
        try:
            guard()
        except Exception as exc:
            self._service_state = "QUARANTINED"
            self._coo_last_error = "AutonomyReceiptRefusal: closed"
            raise StateConflict("Executive autonomy receipt refused") from exc

    @property
    def runtime_state_dir(self) -> Path:
        return self.config.runtime_root / "data" / "control_plane"

    @property
    def service_lock_path(self) -> Path:
        return self.runtime_state_dir / "executive-service.lock"

    @property
    def running_marker_path(self) -> Path:
        return self.runtime_state_dir / "executive-service.running"

    def _require_runtime(self) -> Runtime:
        if self.runtime is None:
            raise ServiceError("Executive control service is not started")
        return self.runtime

    def _require_supervisor(self) -> SupervisorProtocol:
        if self.supervisor is None:
            raise ServiceError("Executive supervisor is not configured")
        return self.supervisor

    def _require_operator_supervisor(self) -> OperatorSupervisorProtocol:
        if self.operator_supervisor is None:
            raise ServiceError("Executive Operator Harness supervisor is not configured")
        return self.operator_supervisor

    async def activate_canary(self, verdict: Mapping[str, Any]) -> None:
        """Leave bootstrap quarantine without changing the live launchd PID."""

        if self._service_state != "AWAITING_CANARY":
            raise ServiceError("Executive control service is not awaiting a canary")
        from control_plane.codex_worker import validate_secret_canary_verdict

        validated = validate_secret_canary_verdict(verdict, require_passed=True)
        supervisor = self._require_supervisor()
        if not hasattr(supervisor, "secret_canary_verdict") or not hasattr(
            supervisor, "require_complete_launch_attestation"
        ):
            raise ServiceError("Executive supervisor cannot activate a complete canary")
        supervisor.secret_canary_verdict = validated
        supervisor.require_complete_launch_attestation = True
        self._startup_reconciliation = await asyncio.to_thread(
            supervisor.reconcile_restart,
            requeue_lost=False,
        )
        # Activation is the first moment this bootstrap-quarantined instance
        # may resume durable terminal obligations.  Replay while admission is
        # still closed; exposing READY first would create a race and omitting
        # replay would strand every completion committed before the canary.
        self._service_state = "ACTIVATING_CANARY"
        try:
            await self._replay_terminal_returns_on_startup()
        except Exception:
            self._service_state = "QUARANTINED"
            raise
        if self._service_state == "QUARANTINED":
            raise StateConflict("Executive terminal-return replay was quarantined")
        self._service_state = "READY"

    def _acquire_service_lock(self) -> None:
        self.runtime_state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        directory_info = self.runtime_state_dir.lstat()
        if (
            not stat.S_ISDIR(directory_info.st_mode)
            or stat.S_ISLNK(directory_info.st_mode)
            or directory_info.st_uid != os.geteuid()
        ):
            raise ServiceError("Executive runtime state directory is not owner-only")
        self.runtime_state_dir.chmod(0o700)
        if stat.S_IMODE(self.runtime_state_dir.lstat().st_mode) != 0o700:
            raise ServiceError("Executive runtime state directory is not owner-only")
        lock_path = self.service_lock_path
        flags = os.O_CREAT | os.O_RDWR
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(lock_path, flags, 0o600)
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_nlink != 1
            or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) & 0o077
        ):
            os.close(fd)
            raise ServiceError("Executive service lock is not an owner-only regular file")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            os.close(fd)
            raise ServiceError("another Executive control service holds the socket lock") from exc
        self._lock_fd = fd
        marker_flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        if hasattr(os, "O_NOFOLLOW"):
            marker_flags |= os.O_NOFOLLOW
        temporary = self.runtime_state_dir / (
            f".{self.running_marker_path.name}.{os.getpid()}.{uuid4().hex}.tmp"
        )
        marker_fd = os.open(temporary, marker_flags, 0o600)
        try:
            payload = _canonical_json(
                {"instance_id": self.instance_id, "pid": os.getpid()}
            )
            view = memoryview(payload)
            while view:
                written = os.write(marker_fd, view)
                if written <= 0:  # pragma: no cover - defensive filesystem failure
                    raise OSError("short write while persisting service marker")
                view = view[written:]
            os.fsync(marker_fd)
        finally:
            os.close(marker_fd)
        os.replace(temporary, self.running_marker_path)
        directory = os.open(
            self.runtime_state_dir,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
        )
        try:
            os.fsync(directory)
        finally:
            os.close(directory)

    def _release_service_lock(self) -> None:
        try:
            marker = json.loads(self.running_marker_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, ValueError, TypeError):
            marker = None
        if isinstance(marker, dict) and marker.get("instance_id") == self.instance_id:
            self.running_marker_path.unlink(missing_ok=True)
        if self._lock_fd is not None:
            try:
                fcntl.flock(self._lock_fd, fcntl.LOCK_UN)
            finally:
                os.close(self._lock_fd)
                self._lock_fd = None

    def _prepare_socket(self) -> None:
        self._acquire_service_lock()
        if self._launchd_activated:
            return
        parent = self.socket_path.parent
        parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        parent_info = parent.lstat()
        if (
            not stat.S_ISDIR(parent_info.st_mode)
            or stat.S_ISLNK(parent_info.st_mode)
            or parent_info.st_uid != os.geteuid()
        ):
            self._release_service_lock()
            raise ServiceError("control socket directory is not owned by the service uid")
        parent.chmod(0o700)
        try:
            info = self.socket_path.lstat()
        except FileNotFoundError:
            return
        if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.geteuid():
            self._release_service_lock()
            raise ServiceError("refusing to replace an unowned or non-socket control path")
        self.socket_path.unlink()

    def _database_health(self) -> dict[str, Any]:
        runtime = self._require_runtime()
        with runtime.store.read() as connection:
            quick_check = [str(row[0]) for row in connection.execute("PRAGMA quick_check")]
            foreign_keys = [list(row) for row in connection.execute("PRAGMA foreign_key_check")]
            journal_mode = str(connection.execute("PRAGMA journal_mode").fetchone()[0])
            migrations = [
                {
                    "version": int(row[0]),
                    "name": str(row[1]),
                    "checksum": str(row[2]),
                }
                for row in connection.execute(
                    "SELECT version,name,checksum FROM schema_migrations ORDER BY version"
                )
            ]
        healthy = quick_check == ["ok"] and not foreign_keys and journal_mode.lower() == "wal"
        return {
            "ok": healthy,
            "schema_version": SCHEMA_VERSION,
            "journal_mode": journal_mode,
            "quick_check": quick_check,
            "foreign_key_violations": len(foreign_keys),
            "migrations": migrations,
        }

    def _prepare_ceo_ingress_socket_path(self) -> None:
        """Directory/stale-node preparation for the dedicated CeoIngress path.

        Deliberately does NOT acquire/release the service lock: §8.1 is one
        process / one Runtime / one lock for BOTH listeners, and the single
        lock is already held by ``_prepare_socket()`` earlier in ``start()``.
        A failure here is handled uniformly by ``start()``'s outer
        ``except Exception: await self.close(); raise``.
        """

        assert self._ceo_ingress_socket_path is not None
        parent = self._ceo_ingress_socket_path.parent
        parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        parent_info = parent.lstat()
        if (
            not stat.S_ISDIR(parent_info.st_mode)
            or stat.S_ISLNK(parent_info.st_mode)
            or parent_info.st_uid != os.geteuid()
        ):
            raise ServiceError(
                "CeoIngress control socket directory is not owned by the service uid"
            )
        parent.chmod(0o700)
        try:
            info = self._ceo_ingress_socket_path.lstat()
        except FileNotFoundError:
            return
        if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.geteuid():
            raise ServiceError(
                "refusing to replace an unowned or non-socket CeoIngress control path"
            )
        self._ceo_ingress_socket_path.unlink()

    async def _bind_operator_server(self, *, start_serving: bool) -> None:
        """Construct (bind) the generic Operator listener.

        ``self._server`` is assigned IMMEDIATELY once ``start_unix_server``
        returns — before the activated-socket mode/world-accessible check
        below — so a failure in that check still leaves a real server object
        reachable from ``close()`` rather than leaking an unclosed socket.
        Passing ``start_serving=True`` (the legacy single-listener path)
        reproduces the previous unparameterized call byte-for-byte, since
        that was already asyncio's own default.
        """

        if self._activated_socket is None:
            self._server = await asyncio.start_unix_server(
                self._handle_connection,
                path=str(self.socket_path),
                limit=self.config.max_request_bytes + 1,
                start_serving=start_serving,
            )
            self.socket_path.chmod(0o600)
        else:
            activated, self._activated_socket = self._activated_socket, None
            activated_options: dict[str, Any] = {}
            if sys.version_info >= (3, 13):
                # Python 3.13 added cleanup_socket and otherwise removes the
                # launchd-owned pathname when the asyncio Server closes.
                activated_options["cleanup_socket"] = False
            self._server = await asyncio.start_unix_server(
                self._handle_connection,
                sock=activated,
                limit=self.config.max_request_bytes + 1,
                start_serving=start_serving,
                **activated_options,
            )
            mode = stat.S_IMODE(self.socket_path.stat().st_mode)
            if mode & 0o007:
                raise ServiceError("launchd control socket must not be world-accessible")

    async def _bind_ceo_ingress_server(self, *, start_serving: bool) -> None:
        """Construct (bind) the dedicated CeoIngress listener; see ``_bind_operator_server``."""

        assert self._ceo_ingress_socket_path is not None
        if self._ceo_ingress_activated_socket is None:
            self._prepare_ceo_ingress_socket_path()
            self._ceo_ingress_server = await asyncio.start_unix_server(
                self._handle_ceo_ingress_connection,
                path=str(self._ceo_ingress_socket_path),
                limit=ceo_ingress.MAX_REQUEST_BYTES + 1,
                start_serving=start_serving,
            )
            self._ceo_ingress_socket_path.chmod(0o600)
        else:
            activated, self._ceo_ingress_activated_socket = (
                self._ceo_ingress_activated_socket,
                None,
            )
            activated_options: dict[str, Any] = {}
            if sys.version_info >= (3, 13):
                activated_options["cleanup_socket"] = False
            self._ceo_ingress_server = await asyncio.start_unix_server(
                self._handle_ceo_ingress_connection,
                sock=activated,
                limit=ceo_ingress.MAX_REQUEST_BYTES + 1,
                start_serving=start_serving,
                **activated_options,
            )

    def _prepare_dialogue_observation_socket_path(self) -> None:
        """Prepare only the exact dedicated W3C directory and stale inode."""

        path = self._dialogue_observation_socket_path
        gid = self._dialogue_observation_group_gid
        assert path is not None and gid is not None
        parent = path.parent
        existed = parent.exists()
        parent.mkdir(mode=0o710, parents=True, exist_ok=True)
        try:
            parent_info = parent.lstat()
        except OSError as exc:
            raise ServiceError("CAPABILITY_NOT_READY") from exc
        if (
            not stat.S_ISDIR(parent_info.st_mode)
            or stat.S_ISLNK(parent_info.st_mode)
            or parent_info.st_uid != os.geteuid()
        ):
            raise ServiceError("CAPABILITY_NOT_READY")
        if not existed:
            try:
                os.chown(parent, os.geteuid(), gid, follow_symlinks=False)
                parent.chmod(0o710)
            except OSError as exc:
                raise ServiceError("CAPABILITY_NOT_READY") from exc
            parent_info = parent.lstat()
        if (
            parent_info.st_gid != gid
            or stat.S_IMODE(parent_info.st_mode) != 0o710
        ):
            raise ServiceError("CAPABILITY_NOT_READY")
        try:
            path.lstat()
        except FileNotFoundError:
            return
        # No durable marker proves a pre-existing node belongs to this fresh
        # service instance.  Even a lookalike socket is therefore ambiguous
        # and must never be reclaimed as a stale capability.
        raise ServiceError("CAPABILITY_NOT_READY")

    async def _bind_dialogue_observation_server(
        self, *, start_serving: bool
    ) -> None:
        path = self._dialogue_observation_socket_path
        gid = self._dialogue_observation_group_gid
        assert path is not None and gid is not None
        if self._dialogue_observation_activated_socket is None:
            self._prepare_dialogue_observation_socket_path()
            options: dict[str, Any] = {}
            if sys.version_info >= (3, 13):
                options["cleanup_socket"] = False
            self._dialogue_observation_server = await asyncio.start_unix_server(
                self._handle_dialogue_observation_connection,
                path=str(path),
                limit=DIALOGUE_OBSERVATION_MAX_REQUEST_BYTES + 1,
                start_serving=start_serving,
                **options,
            )
            try:
                bound = path.lstat()
                if (
                    not stat.S_ISSOCK(bound.st_mode)
                    or stat.S_ISLNK(bound.st_mode)
                    or bound.st_uid != os.geteuid()
                ):
                    raise ServiceError("CAPABILITY_NOT_READY")
                self._dialogue_observation_inode = (
                    bound.st_dev,
                    bound.st_ino,
                )
                os.chown(path, os.geteuid(), gid, follow_symlinks=False)
                path.chmod(0o660)
                info = path.lstat()
            except OSError as exc:
                raise ServiceError("CAPABILITY_NOT_READY") from exc
            if (
                not stat.S_ISSOCK(info.st_mode)
                or stat.S_ISLNK(info.st_mode)
                or info.st_uid != os.geteuid()
                or info.st_gid != gid
                or stat.S_IMODE(info.st_mode) != 0o660
                or (info.st_dev, info.st_ino)
                != self._dialogue_observation_inode
            ):
                raise ServiceError("CAPABILITY_NOT_READY")
            return

        activated, self._dialogue_observation_activated_socket = (
            self._dialogue_observation_activated_socket,
            None,
        )
        options = {}
        if sys.version_info >= (3, 13):
            options["cleanup_socket"] = False
        self._dialogue_observation_server = await asyncio.start_unix_server(
            self._handle_dialogue_observation_connection,
            sock=activated,
            limit=DIALOGUE_OBSERVATION_MAX_REQUEST_BYTES + 1,
            start_serving=start_serving,
            **options,
        )
        try:
            info = path.lstat()
        except OSError as exc:
            raise ServiceError("CAPABILITY_NOT_READY") from exc
        if (
            not stat.S_ISSOCK(info.st_mode)
            or stat.S_ISLNK(info.st_mode)
            or info.st_uid != os.geteuid()
            or info.st_gid != gid
            or stat.S_IMODE(info.st_mode) != 0o660
        ):
            raise ServiceError("CAPABILITY_NOT_READY")

    async def _start_dialogue_observation_serving(self) -> None:
        assert self._dialogue_observation_server is not None
        await self._dialogue_observation_server.start_serving()

    async def _start_ceo_ingress_serving(self) -> None:
        assert self._ceo_ingress_server is not None
        await self._ceo_ingress_server.start_serving()

    async def _start_operator_serving(self) -> None:
        assert self._server is not None
        await self._server.start_serving()

    async def start(self) -> None:
        if self._server is not None:
            raise ServiceError("Executive control service is already started")
        self._closing = False
        self._require_current_autonomy()
        self._prepare_socket()
        try:
            self.runtime = self._runtime_factory(self.config.runtime_root)
            health = self._database_health()
            if not health["ok"]:
                raise ServiceError(f"Executive database health check failed: {health!r}")
            if self._supervisor_factory is None:
                raise ServiceError("supervisor_factory is required for startup reconciliation")
            self.supervisor = self._supervisor_factory(self.runtime)
            if self.config.coo_operator_harness_armed:
                if self._operator_supervisor_factory is None:
                    raise ServiceError(
                        "armed COO Operator Harness has no supervisor composition"
                    )
                if self._operator_identity_verifier is None:
                    raise ServiceError(
                        "armed COO Operator Harness has no worker identity verifier"
                    )
                await self._operator_identity_verifier()
                self.operator_supervisor = self._operator_supervisor_factory(
                    self.runtime, self.supervisor
                )
            # Startup reconciliation must never auto-requeue.  LOST work returns
            # to QUEUED only through the explicit requeue command.
            if self._service_state == "READY":
                self._startup_reconciliation = await asyncio.to_thread(
                    self.supervisor.reconcile_restart, requeue_lost=False
                )
                if self.operator_supervisor is not None:
                    self._startup_reconciliation.extend(
                        await asyncio.to_thread(
                            self.operator_supervisor.reconcile_restart,
                            requeue_lost=False,
                        )
                    )
                await self._replay_terminal_returns_on_startup()
            if (
                self._ceo_ingress_socket_path is not None
                or self._dialogue_observation_socket_path is not None
            ):
                # Every configured listener binds with no-accept only after
                # Runtime reconciliation and the terminal phase audit.  Once
                # all binds succeed, acceptance begins in one deterministic
                # step under this service's single process/lock owner.
                if self._ceo_ingress_socket_path is not None:
                    await self._bind_ceo_ingress_server(start_serving=False)
                if self._dialogue_observation_socket_path is not None:
                    await self._bind_dialogue_observation_server(
                        start_serving=False
                    )
                await self._bind_operator_server(start_serving=False)
                if self._ceo_ingress_socket_path is not None:
                    await self._start_ceo_ingress_serving()
                if self._dialogue_observation_socket_path is not None:
                    await self._start_dialogue_observation_serving()
                await self._start_operator_serving()
                if self._ceo_ingress_socket_path is not None:
                    self._ceo_ingress_ready = True
                if self._dialogue_observation_socket_path is not None:
                    self._dialogue_observation_ready = True
            else:
                # Byte-compatible-unchanged: identical to the previous
                # unconditional call (start_serving defaults to True).
                await self._bind_operator_server(start_serving=True)
            # R2 §3: set/update _started_at exactly where the service records
            # successful startup — after BOTH listeners in dual-listener mode
            # (Operator starts second, so this line already runs after both),
            # unchanged single-listener timing otherwise.
            self._started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
            if self.config.coo_autonomy_armed:
                self._coo_shutdown_event = asyncio.Event()
                self._coo_tick_task = asyncio.create_task(
                    self._coo_tick_loop(),
                    name="executive-coo-bounded-tick",
                )
        except Exception:
            await self.close()
            raise

    async def close(self) -> None:
        # R1/R2: the startup latch is process lifecycle only; reset it before
        # anything else so a mid-startup failure or a fresh restart never
        # observes a stale true value.
        self._ceo_ingress_ready = False
        if hasattr(self, "_dialogue_observation_ready"):
            self._dialogue_observation_ready = False
        self._closing = True
        deferred_terminal_cancel: asyncio.CancelledError | None = None
        if self._coo_shutdown_event is not None:
            self._coo_shutdown_event.set()

        # §14.2 step 1 — stop BOTH listeners first, preventing new
        # connections, before awaiting either one's ``wait_closed()``.  Calling
        # ``.close()`` on both up front (rather than close+await, close+await)
        # is what actually "stops both listeners first": ``.close()`` alone
        # already stops the server from accepting new connections, so doing it
        # for both before either await removes the narrow window in which the
        # second listener could still accept a connection while this coroutine
        # is suspended awaiting the first listener's ``wait_closed()``.
        server, self._server = self._server, None
        observation_server = getattr(self, "_dialogue_observation_server", None)
        if hasattr(self, "_dialogue_observation_server"):
            self._dialogue_observation_server = None
        ceo_ingress_server, self._ceo_ingress_server = self._ceo_ingress_server, None
        if server is not None:
            server.close()
        if observation_server is not None:
            observation_server.close()
        if ceo_ingress_server is not None:
            ceo_ingress_server.close()
        if server is not None:
            await server.wait_closed()
        if observation_server is not None:
            await observation_server.wait_closed()
        if ceo_ingress_server is not None:
            await ceo_ingress_server.wait_closed()

        coo_tick, self._coo_tick_task = self._coo_tick_task, None
        if coo_tick is not None:
            # A CooCycle action can cross a durable mutation/claim boundary in
            # its worker thread.  Cancellation would not stop that thread, so
            # shutdown drains the one bounded action to a real return point.
            await asyncio.gather(coo_tick, return_exceptions=True)
        self._coo_shutdown_event = None
        current_task = asyncio.current_task()
        coo_actions = [
            task
            for task in self._coo_action_tasks
            if task is not current_task and not task.done()
        ]
        if coo_actions:
            await asyncio.gather(*coo_actions, return_exceptions=True)
        self._coo_action_tasks.clear()

        # Dispatch finishers are terminal-return producers.  Stop/drain them
        # before snapshotting the terminal flight registry so a finisher that
        # seals during shutdown cannot create a shielded Relay send after the
        # snapshot and outlive service ownership.
        tasks = [task for task in self._dispatch_tasks.values() if not task.done()]
        runtime = self.runtime
        if runtime is not None:
            for job_id, task in list(self._dispatch_tasks.items()):
                if task.done():
                    continue
                try:
                    job = runtime.jobs.get_job(job_id)
                    if job is not None and job.status in {
                        JobStatus.QUEUED,
                        JobStatus.RUNNING,
                        JobStatus.CHECKPOINTED,
                    }:
                        runtime.jobs.cancel_job(job_id)
                except RuntimeProofError:
                    # Restart reconciliation remains the fail-closed cleanup
                    # path if the shutdown request races a terminal transition.
                    pass
        if tasks:
            _done, pending = await asyncio.wait(
                tasks, timeout=self.config.shutdown_grace_seconds
            )
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
        self._dispatch_tasks.clear()

        # A terminal-return flight may already have crossed the durable
        # ATTEMPTED boundary. Drain it to POSTED/known-zero/EFFECT_UNKNOWN;
        # cancellation here would manufacture the very ambiguity this bridge
        # exists to prevent.  This snapshot deliberately follows every
        # dispatch producer's terminal point.
        terminal_flights = [
            task
            for _digest, task in self._terminal_return_flights.values()
            if task is not current_task and not task.done()
        ]
        if terminal_flights:
            terminal_drain = asyncio.gather(
                *terminal_flights,
                return_exceptions=True,
            )
            try:
                await asyncio.shield(terminal_drain)
            except asyncio.CancelledError as exc:
                # ``close()`` is itself caller-owned and may be cancelled,
                # but the already-ATTEMPTED Relay flight is service-owned.
                # Defer the caller cancellation until the flight reaches a
                # durable terminal phase and all service cleanup below has
                # completed.  Shield every subsequent wait so a repeated
                # cancellation request still cannot reach the owned flight.
                deferred_terminal_cancel = exc
                while not terminal_drain.done():
                    try:
                        await asyncio.shield(terminal_drain)
                    except asyncio.CancelledError:
                        continue
        self._terminal_return_flights.clear()

        # §14.2 — CeoIngress handler tasks are NEVER cancelled here, unlike the
        # dispatch tasks above.  A handler whose sync ``submit_intent`` thread
        # has already started cannot be safely cancelled (cancelling the
        # awaiting coroutine does not cancel the underlying thread/
        # transaction), so ``close()`` waits every already-started handler to
        # a REAL terminal outcome with no grace-period timeout.  The service
        # lock/marker below is not released until this drains.
        ceo_ingress_tasks = [task for task in self._ceo_ingress_tasks if not task.done()]
        if ceo_ingress_tasks:
            await asyncio.gather(*ceo_ingress_tasks, return_exceptions=True)
        self._ceo_ingress_tasks.clear()
        observation_task_set = getattr(self, "_dialogue_observation_tasks", None)
        observation_tasks = [
            task
            for task in observation_task_set or ()
            if task is not current_task and not task.done()
        ]
        if observation_tasks:
            await asyncio.gather(*observation_tasks, return_exceptions=True)
        if observation_task_set is not None:
            observation_task_set.clear()

        if not self._launchd_activated:
            try:
                info = self.socket_path.lstat()
            except FileNotFoundError:
                pass
            else:
                if stat.S_ISSOCK(info.st_mode):
                    self.socket_path.unlink()
        if self._ceo_ingress_socket_path is not None and not self._ceo_ingress_launchd_activated:
            try:
                info = self._ceo_ingress_socket_path.lstat()
            except FileNotFoundError:
                pass
            else:
                if stat.S_ISSOCK(info.st_mode):
                    self._ceo_ingress_socket_path.unlink()
        if (
            self._dialogue_observation_socket_path is not None
            and not getattr(self, "_dialogue_observation_launchd_activated", False)
            and getattr(self, "_dialogue_observation_inode", None) is not None
        ):
            try:
                info = self._dialogue_observation_socket_path.lstat()
            except FileNotFoundError:
                pass
            else:
                if (
                    stat.S_ISSOCK(info.st_mode)
                    and not stat.S_ISLNK(info.st_mode)
                    and (info.st_dev, info.st_ino)
                    == self._dialogue_observation_inode
                ):
                    self._dialogue_observation_socket_path.unlink()
        if hasattr(self, "_dialogue_observation_inode"):
            self._dialogue_observation_inode = None
        self._release_service_lock()
        if deferred_terminal_cancel is not None:
            raise deferred_terminal_cancel

    async def serve_until_stopped(self) -> None:
        await self.start()
        stopped = asyncio.Event()
        loop = asyncio.get_running_loop()
        installed: list[signal.Signals] = []
        for value in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.add_signal_handler(value, stopped.set)
                installed.append(value)
            except (NotImplementedError, RuntimeError):  # pragma: no cover - non-main loop
                continue
        try:
            await stopped.wait()
        finally:
            for value in installed:
                loop.remove_signal_handler(value)
            await self.close()

    def _allowed_peer_uids(self) -> set[int]:
        configured = {int(value) for value in self.config.allowed_peer_uids}
        return configured or {os.geteuid()}

    async def _handle_connection(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        try:
            connection = writer.get_extra_info("socket")
            if connection is None:
                raise ServiceError("control connection has no local socket identity")
            try:
                peer = _peer_uid(connection)
            except OSError:
                await self._send_error(
                    writer,
                    "peer_credentials_unavailable",
                    "kernel peer credentials could not be read",
                )
                return
            if peer is None:
                await self._send_error(
                    writer,
                    "peer_credentials_unavailable",
                    "platform exposes no trusted local peer uid",
                )
                return
            if peer not in self._allowed_peer_uids():
                await self._send_error(writer, "peer_denied", "peer uid is not authorized")
                return
            try:
                raw = await reader.readuntil(b"\n")
            except asyncio.LimitOverrunError:
                await self._send_error(writer, "request_too_large", "request exceeds byte limit")
                return
            except asyncio.IncompleteReadError as exc:
                raw = exc.partial
            if not raw or len(raw) > self.config.max_request_bytes:
                await self._send_error(writer, "request_too_large", "request exceeds byte limit")
                return
            try:
                request = json.loads(raw.decode("utf-8", errors="strict"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                await self._send_error(writer, "invalid_json", "request is not valid UTF-8 JSON")
                return
            try:
                result = await self._dispatch_request(request)
            except (RuntimeProofError, ValueError) as exc:
                await self._send_error(writer, "request_failed", str(exc)[:1000])
                return
            except WorkspaceError as exc:
                # WorkspaceError is a bare RuntimeError (see
                # control_plane/executive_workspace.py) so it is not a
                # RuntimeProofError/ValueError and does not match the branch
                # above; it is also not a subclass of RuntimeProofError or
                # ValueError, so that branch is not a subclass of this one
                # either. The two clauses are mutually exclusive by type, so
                # their relative order cannot change which one a given
                # exception hits -- only "before the generic `except
                # Exception` below" is load-bearing. Reuse the existing
                # `request_failed` code (no new wire contract) but sanitize
                # the reason first: workspace text originates outside this
                # process (paths, git/codex command output) and must not
                # cross the socket unredacted or unbounded.
                reason = sanitize_external_text(str(exc), limit=1000)
                await self._send_error(
                    writer,
                    "request_failed",
                    reason or "workspace preparation failed",
                )
                return
            except Exception as exc:  # fail closed without a traceback or local paths
                await self._send_error(
                    writer,
                    "internal_error",
                    f"{type(exc).__name__}: Executive request failed",
                )
                return
            await self._send(writer, {"ok": True, "result": result})
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except _CLIENT_GONE:
                pass

    async def _send_error(self, writer: asyncio.StreamWriter, code: str, message: str) -> None:
        await self._send(writer, {"ok": False, "error": {"code": code, "message": message}})

    async def _send(self, writer: asyncio.StreamWriter, payload: Mapping[str, Any]) -> None:
        raw = _canonical_json(payload)
        if len(raw) > self.config.max_response_bytes:
            raw = _canonical_json(
                {
                    "ok": False,
                    "error": {
                        "code": "response_too_large",
                        "message": "response exceeds byte limit",
                    },
                }
            )
        try:
            writer.write(raw)
            await writer.drain()
        except _CLIENT_GONE:
            # Delivery path only: the peer disconnected while this reply was in
            # flight.  Nothing the service decided changes, and the caller's
            # `finally` still tears the connection down.
            return

    async def _send_dialogue_observation(
        self, writer: asyncio.StreamWriter, payload: Mapping[str, Any]
    ) -> None:
        try:
            writer.write(dialogue_observation_response_bytes(payload))
            await asyncio.wait_for(
                writer.drain(),
                timeout=DIALOGUE_OBSERVATION_IO_TIMEOUT_SECONDS,
            )
        except (
            BrokenPipeError,
            ConnectionResetError,
            ConnectionAbortedError,
            asyncio.TimeoutError,
        ):
            return

    @staticmethod
    def _dialogue_source_matches_parent(
        source: Any, parent: Mapping[str, Any]
    ) -> bool:
        try:
            return bool(
                source is not None
                and source.work_ref == parent["work_ref"]
                and source.commission_ref.to_dict() == parent["commission_ref"]
                and source.watch_mode == parent["watch_mode"]
            )
        except (AttributeError, KeyError, TypeError, ValueError):
            return False

    def _runtime_dialogue_observation_facts(
        self,
        runtime: Runtime,
        parent: Mapping[str, Any],
        *,
        connection: sqlite3.Connection | None = None,
    ) -> DialogueObservationFacts:
        """Prepare exact current Runtime facts without writing or caching.

        Candidate enumeration and every active/terminal proof read share one
        Runtime snapshot.  The pure reducer remains the only mode selector.
        """

        from control_plane.executive_delegation_identity import (
            derive_delegation_identity,
        )
        from control_plane.runtime_binding_projection import project_runtime_binding
        from control_plane.session_targets import load_session_targets
        active: list[ActiveObservationFacts] = []
        terminal: list[TerminalObservationFacts] = []
        registry = load_session_targets()
        try:
            requested_source = normalize_executive_dialogue_source(
                {
                    "schema_version": EXECUTIVE_DIALOGUE_SOURCE_SCHEMA,
                    "work_ref": parent["work_ref"],
                    "commission_ref": parent["commission_ref"],
                    "watch_mode": parent["watch_mode"],
                },
                work_ref=parent["work_ref"],
            )
            requested_source_digest = hashlib.sha256(
                json.dumps(
                    requested_source.to_dict(),
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                    allow_nan=False,
                ).encode("utf-8")
            ).hexdigest()
        except (KeyError, RuntimeProofError, TypeError, ValueError):
            return DialogueObservationFacts(complete=False)
        with (
            runtime.store.read()
            if connection is None
            else nullcontext(connection)
        ) as connection:
            root_rows = connection.execute(
                """
                SELECT j.job_id
                FROM jobs AS j
                WHERE j.orchestration_role='aggregation'
                  AND j.root_job_id=j.job_id
                  AND EXISTS (
                    SELECT 1 FROM events AS root_event
                    WHERE root_event.event_type='JOB_CREATED'
                      AND root_event.job_id=j.job_id
                      AND json_extract(
                        root_event.payload_json,
                        '$.provenance.dialogue_source_digest'
                      )=?
                  )
                ORDER BY j.job_id
                LIMIT 2
                """,
                (requested_source_digest,),
            ).fetchall()
            if len(root_rows) != 1:
                return DialogueObservationFacts(
                    complete=not bool(len(root_rows) > 1)
                )
            root_job_id = str(root_rows[0]["job_id"] or "")
            try:
                source = _dialogue_source_from_root_creation(
                    connection,
                    root_job_id=root_job_id,
                )
            except RuntimeProofError:
                return DialogueObservationFacts(complete=False)
            if source != requested_source:
                return DialogueObservationFacts(complete=False)
            rows = connection.execute(
                """
                SELECT j.* FROM jobs AS j
                WHERE j.root_job_id=?
                  AND j.orchestration_role IN ('plan','work','review','repair')
                  AND j.current_attempt_id IS NOT NULL
                  AND j.status IN ('RUNNING','CHECKPOINTED','CANCEL_REQUESTED','COMPLETED')
                  AND ('exec-' || lower(j.job_id))=?
                  AND ('asd-session-exec-' || lower(j.job_id))=?
                ORDER BY j.job_id
                LIMIT 5
                """,
                (
                    root_job_id,
                    parent["operation_key"],
                    parent["session_ref"],
                ),
            ).fetchall()
            if len(rows) > 4:
                return DialogueObservationFacts(complete=False)
            for job_row in rows:
                if str(job_row["root_job_id"] or "") != root_job_id:
                    continue
                target_bindings = _dialogue_target_bindings_for_root(
                    runtime,
                    connection,
                    root_job_id=root_job_id,
                    registry=registry,
                )
                job = _job_from_row(job_row)
                try:
                    identity = derive_delegation_identity(job)
                except Exception:
                    continue
                if (
                    identity.operation_key != parent.get("operation_key")
                    or identity.session_ref != parent.get("session_ref")
                ):
                    continue
                attempt_id = str(job_row["current_attempt_id"])
                if job_row["status"] != JobStatus.COMPLETED.value:
                    attempt_row = connection.execute(
                        "SELECT * FROM attempts WHERE attempt_id=?",
                        (attempt_id,),
                    ).fetchone()
                    generation_row = connection.execute(
                        """
                        SELECT observed_attestation_json
                        FROM process_generations g
                        JOIN harness_session_epochs e
                          ON e.session_epoch_id=g.session_epoch_id
                        WHERE e.attempt_id=? AND e.state='CURRENT'
                          AND g.executive_writer_held=1
                        ORDER BY g.generation_number DESC
                        LIMIT 2
                        """,
                        (attempt_id,),
                    ).fetchall()
                    if attempt_row is None or len(generation_row) != 1:
                        continue
                    try:
                        binding_facts = runtime.current_harness_binding_source(
                            attempt_id,
                            connection=connection,
                        )
                        target = registry.resolve(binding_facts.owner_seat)
                        binding = project_runtime_binding(
                            runtime,
                            attempt_id,
                            target,
                            connection=connection,
                        )
                        requested = _strict_canonical_json_loads(
                            str(attempt_row["requested_execution_profile_json"]),
                            name="dialogue observation requested profile",
                        )
                        observed = _strict_canonical_json_loads(
                            str(generation_row[0]["observed_attestation_json"]),
                            name="dialogue observation harness attestation",
                        )
                    except (RuntimeProofError, PersistenceError, TypeError, ValueError):
                        continue
                    required = (
                        requested.get("capabilities", {}).get("required", [])
                        if isinstance(requested, dict)
                        else []
                    )
                    observed_capabilities = (
                        observed.get("capabilities", [])
                        if isinstance(observed, dict)
                        else []
                    )
                    expected_capabilities = [
                        value
                        for value in required
                        if isinstance(value, dict)
                        and value.get("kind") == "mcp_server"
                        and all(
                            isinstance(value.get(name), str) and value.get(name)
                            for name in (
                                "mcp_server_identity",
                                "mcp_server_version",
                                "tool_schema_digest",
                            )
                        )
                    ]
                    expected = (
                        expected_capabilities[0]
                        if len(expected_capabilities) == 1
                        else {}
                    )
                    attested = bool(
                        len(expected_capabilities) == 1
                        and any(
                            isinstance(value, dict)
                            and value.get("kind") == "mcp_server"
                            and value.get("mcp_server_identity")
                            == expected.get("mcp_server_identity")
                            and value.get("mcp_server_version")
                            == expected.get("mcp_server_version")
                            and value.get("tool_schema_digest")
                            == expected.get("tool_schema_digest")
                            for value in observed_capabilities
                        )
                    )
                    constraints = job.constraints
                    active.append(
                        ActiveObservationFacts(
                            root_job_id=job.root_job_id,
                            job_id=job.job_id,
                            attempt_id=attempt_id,
                            worker_id=str(attempt_row["worker_id"]),
                            attempt_status=str(attempt_row["status"]),
                            worker_status="BUSY",
                            execution_profile_id=str(
                                constraints.get("execution_profile_id") or ""
                            ),
                            execution_profile_digest=str(
                                constraints.get("execution_profile_digest") or ""
                            ),
                            capability_policy_digest=str(
                                constraints.get("capability_policy_digest") or ""
                            ),
                            runtime_binding=PublicRuntimeBindingFacts(
                                session_alias=binding.session_alias,
                                binding_id=binding.binding_id,
                                binding_generation=binding.binding_generation,
                                reasoning_surface=str(binding.reasoning_surface or ""),
                            ),
                            parent_fingerprint=str(parent["fingerprint"]),
                            company_dialogue_server_identity=str(
                                expected.get("mcp_server_identity") or ""
                            ),
                            company_dialogue_server_version=str(
                                expected.get("mcp_server_version") or ""
                            ),
                            company_dialogue_tool_schema_digest=str(
                                expected.get("tool_schema_digest") or ""
                            ),
                            company_dialogue_attested=attested,
                            target_bindings=target_bindings,
                        )
                    )
                    continue

                role = str(job_row["orchestration_role"] or "")
                try:
                    attempt_row, seal, terminal_receipt, role_result_digest = (
                        _validated_role_completion_material(
                            connection,
                            job_row=job_row,
                            expected_role=role,
                            root_job_id=root_job_id,
                        )
                    )
                    job_result = _strict_canonical_json_loads(
                        str(job_row["result_json"]),
                        name="dialogue observation terminal Job result",
                    )
                    attempt_result = _strict_canonical_json_loads(
                        str(attempt_row["result_json"]),
                        name="dialogue observation terminal Attempt result",
                    )
                    if job_result != terminal_receipt or attempt_result != terminal_receipt:
                        raise StateConflict("terminal result receipt drifted")
                    envelope = seal.get("result_envelope")
                    envelope_digest = seal.get("result_envelope_digest")
                    if (
                        not isinstance(envelope, dict)
                        or not isinstance(envelope_digest, str)
                        or not isinstance(role_result_digest, str)
                    ):
                        raise StateConflict("terminal result material is incomplete")
                    completion = ValidatedRoleCompletion(
                        job=job,
                        attempt=_attempt_from_row(attempt_row),
                        result_envelope=dict(envelope),
                        terminal_receipt=dict(terminal_receipt),
                        result_digest=envelope_digest,
                        role_result_digest=role_result_digest,
                        execution_mode=str(
                            attempt_row["execution_mode"]
                            or AttemptExecutionMode.SEALED_WORKER.value
                        ),
                        dialogue_source=source,
                    )
                    candidate = reduce_terminal_return(material=completion)
                    command_base, material = self._terminal_return_event_material(candidate)
                    phase = self._inspect_terminal_return_history(
                        connection,
                        candidate=candidate,
                        material=material,
                    )
                    receipt: Any = None
                    if phase == "APPLIED":
                        applied_command = self._terminal_return_phase_spec(command_base)[-1][2]
                        applied_event = runtime.store.get_event_by_command_id(
                            applied_command,
                            connection=connection,
                        )
                        if applied_event is None:
                            raise StateConflict("terminal APPLIED receipt disappeared")
                        normalized = self._normalize_terminal_return_projection_receipt(
                            applied_event.payload.get("projection_receipt"),
                            message_key=candidate.message_key,
                        )
                        normalized["duplicate_timestamps"] = tuple(
                            normalized["duplicate_timestamps"]
                        )
                        receipt = TerminalProjectionReceiptFacts(**normalized)
                    terminal.append(
                        TerminalObservationFacts(
                            candidate=candidate,
                            projection_receipt=receipt,
                            projection_effect=phase or "MISSING",
                            binding_revalidated=bool(
                                candidate.dialogue_source == source
                                and identity.root_job_id == candidate.root_job_id
                                and identity.operation_key == candidate.operation_key
                                and identity.session_ref == candidate.session_ref
                                and candidate.operation_key
                                == parent["operation_key"]
                                and candidate.session_ref == parent["session_ref"]
                            ),
                            target_bindings=target_bindings,
                        )
                    )
                except (RuntimeProofError, PersistenceError, TerminalReturnError, ValueError):
                    continue

        return DialogueObservationFacts(
            active=tuple(active),
            terminal=tuple(terminal),
        )

    def _runtime_canonical_terminal_facts(
        self,
        runtime: Runtime,
        candidate: CanonicalTerminalWakeCandidate,
        connection: sqlite3.Connection,
    ) -> DialogueObservationFacts:
        """Delegate canonical Runtime reconstruction to the W3C owner."""

        return dialogue_observation.runtime_canonical_terminal_facts(
            runtime,
            candidate,
            connection,
        )

    def read_canonical_dialogue_terminal_wake(
        self,
        *,
        source_root_job_id: str,
        candidate: CanonicalTerminalWakeCandidate,
        connection: sqlite3.Connection | None = None,
    ) -> CanonicalTerminalWakeRead:
        """Delegate the bounded local read to the standalone W3C owner."""

        return dialogue_observation.read_runtime_canonical_terminal_wake(
            runtime=self._require_runtime(),
            source_root_job_id=source_root_job_id,
            candidate=candidate,
            connection=connection,
        )

    async def _handle_dialogue_observation_connection(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        """Serve one peer-authenticated, payload-free-on-refusal lookup."""

        task = asyncio.current_task()
        if task is not None:
            self._dialogue_observation_tasks.add(task)
        try:
            connection = writer.get_extra_info("socket")
            if connection is None:
                await self._send_dialogue_observation(
                    writer,
                    {
                        "schema": DIALOGUE_OBSERVATION_RESPONSE_SCHEMA,
                        "state": "HELD",
                        "reason": "PEER_UID_REFUSED",
                    },
                )
                return
            try:
                peer = _peer_uid(connection)
            except OSError:
                peer = None
            if peer != self._dialogue_observation_peer_uid:
                await self._send_dialogue_observation(
                    writer,
                    {
                        "schema": DIALOGUE_OBSERVATION_RESPONSE_SCHEMA,
                        "state": "HELD",
                        "reason": "PEER_UID_REFUSED",
                    },
                )
                return
            if not self._dialogue_observation_ready:
                await self._send_dialogue_observation(
                    writer,
                    {
                        "schema": DIALOGUE_OBSERVATION_RESPONSE_SCHEMA,
                        "state": "HELD",
                        "reason": "LISTENER_UNAVAILABLE",
                    },
                )
                return
            try:
                raw = await asyncio.wait_for(
                    reader.readuntil(b"\n"),
                    timeout=DIALOGUE_OBSERVATION_IO_TIMEOUT_SECONDS,
                )
            except (
                asyncio.IncompleteReadError,
                asyncio.LimitOverrunError,
                asyncio.TimeoutError,
            ):
                await self._send_dialogue_observation(
                    writer,
                    {
                        "schema": DIALOGUE_OBSERVATION_RESPONSE_SCHEMA,
                        "state": "HELD",
                        "reason": "REQUEST_REFUSED",
                    },
                )
                return
            # A pipelined second frame is a closed refusal.  A later second
            # write receives EOF because every connection is one-shot.
            await asyncio.sleep(0)
            buffered = getattr(reader, "_buffer", b"")
            if buffered:
                await self._send_dialogue_observation(
                    writer,
                    {
                        "schema": DIALOGUE_OBSERVATION_RESPONSE_SCHEMA,
                        "state": "HELD",
                        "reason": "MULTIPLE_REQUESTS_REFUSED",
                    },
                )
                return
            provider = self._dialogue_observation_facts_provider
            runtime = self._require_runtime()
            try:
                delayed_ack_request = parse_delayed_ack_request(raw)
            except DialogueObservationProtocolError:
                delayed_ack_request = None
            if delayed_ack_request is not None:
                wake_handler = self._dialogue_wake_handler
                if (
                    type(wake_handler) is ExecutiveDialogueWakeBridge
                    and wake_handler.canary_profile is not None
                ):
                    delayed_result = await wake_handler.reconcile_delayed_ack(
                        runtime, delayed_ack_request
                    )
                else:
                    delayed_result = {
                        "state": "NOT_APPLICABLE",
                        "reason": "NONCANARY_PROFILE",
                    }
                await self._send_dialogue_observation(
                    writer,
                    {
                        "schema": DELAYED_ACK_RESPONSE_SCHEMA,
                        **delayed_result,
                    },
                )
                return
            try:
                source_request = parse_source_reconcile_request(raw)
            except DialogueObservationProtocolError:
                source_request = None
            if source_request is not None:
                wake_handler = self._dialogue_wake_handler
                if (
                    type(wake_handler) is ExecutiveDialogueWakeBridge
                    and wake_handler.canary_profile is not None
                ):
                    source_result = await asyncio.to_thread(
                        wake_handler.reconcile_dialogue_sources,
                        runtime,
                        source_request,
                    )
                else:
                    source_result = {
                        "state": "NOT_APPLICABLE",
                        "reason": "NONCANARY_PROFILE",
                    }
                await self._send_dialogue_observation(
                    writer,
                    {
                        "schema": SOURCE_RECONCILE_RESPONSE_SCHEMA,
                        **source_result,
                    },
                )
                return
            try:
                request = parse_observation_request(raw)
            except DialogueObservationProtocolError:
                try:
                    wake_request = parse_wake_request(raw)
                except DialogueObservationProtocolError:
                    await self._send_dialogue_observation(
                        writer,
                        {
                            "schema": DIALOGUE_OBSERVATION_RESPONSE_SCHEMA,
                            "state": "HELD",
                            "reason": "REQUEST_REFUSED",
                        },
                    )
                    return
                wake_result = DialogueWakeResult(
                    "MISSING", "STAGE_B1_RUNTIME_PROVIDER_REQUIRED"
                )
                if callable(provider):
                    try:
                        facts = await asyncio.to_thread(
                            provider, runtime, wake_request.parent
                        )
                        source_response = reduce_dialogue_observation(
                            parent=wake_request.parent,
                            thread_ts=wake_request.thread_ts,
                            facts=facts,
                        )
                    except Exception:
                        source_response = {}
                    if (
                        source_response.get("state") == "RESOLVED"
                        and _dialogue_candidate_from_response(source_response)
                        == wake_request.candidate
                    ):
                        wake_handler = self._dialogue_wake_handler
                        if callable(wake_handler):
                            try:
                                candidate = wake_handler(runtime, wake_request)
                                if inspect.isawaitable(candidate):
                                    candidate = await candidate
                                if not isinstance(candidate, DialogueWakeResult):
                                    raise TypeError("untyped dialogue Wake result")
                                wake_result = candidate
                            except Exception:
                                wake_result = DialogueWakeResult(
                                    "EFFECT_UNKNOWN",
                                    "WAKE_COORDINATION_EFFECT_UNKNOWN",
                                )
                    else:
                        wake_result = DialogueWakeResult(
                            "MISSING", "CANDIDATE_BINDING_REQUIRED"
                        )
                        wake_handler = self._dialogue_wake_handler
                        if (
                            type(wake_handler) is ExecutiveDialogueWakeBridge
                            and wake_handler.canary_profile is not None
                        ):
                            wake_result = await wake_handler.historical_only(
                                runtime, wake_request
                            )
                else:
                    wake_handler = self._dialogue_wake_handler
                    if (
                        type(wake_handler) is ExecutiveDialogueWakeBridge
                        and wake_handler.canary_profile is not None
                    ):
                        wake_result = await wake_handler.historical_only(
                            runtime, wake_request
                        )
                response = {
                    "schema": DIALOGUE_WAKE_RESPONSE_SCHEMA,
                    "state": wake_result.state,
                    "reason": wake_result.reason,
                }
            else:
                if not callable(provider):
                    response = {
                        "schema": DIALOGUE_OBSERVATION_RESPONSE_SCHEMA,
                        "state": "HELD",
                        "reason": "OBSERVATION_FACTS_UNAVAILABLE",
                    }
                else:
                    try:
                        facts = await asyncio.to_thread(
                            provider, runtime, request.parent
                        )
                        response = reduce_dialogue_observation(
                            parent=request.parent,
                            facts=facts,
                        )
                    except Exception:
                        response = {
                            "schema": DIALOGUE_OBSERVATION_RESPONSE_SCHEMA,
                            "state": "UNKNOWN",
                            "reason": "ACTIVE_RUNTIME_UNAVAILABLE",
                        }
            await self._send_dialogue_observation(writer, response)
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except _CLIENT_GONE:
                pass
            if task is not None:
                self._dialogue_observation_tasks.discard(task)

    # -----------------------------------------------------------------
    # MAS-75 PR-A: dedicated CeoIngress connection handling
    # -----------------------------------------------------------------

    def _ceo_ingress_ready_for_admission(self) -> bool:
        """R2 §5 final readiness predicate (minus the always-true "this
        service instance/lock is valid" clause, which holds trivially while
        the service itself is running): the startup latch, the host-owned
        arming decision, and the current service-state allowlist.  Every
        other/future/dynamic state (including ``QUARANTINED``) refuses.
        Arming this predicate never changes ``_service_state``, clears
        quarantine, or touches any worker/provider/broker.
        """

        return (
            self._ceo_ingress_ready
            and self._ceo_ingress_armed
            and self._service_state in {"READY", "AWAITING_CANARY"}
        )

    async def _send_ceo_ingress_response(
        self, writer: asyncio.StreamWriter, payload: Mapping[str, Any]
    ) -> None:
        """Dedicated bounded sender (§7.4) — the 32 KiB ingress ceiling, never
        the generic ``_send()``'s ``ServiceConfig.max_response_bytes``.  A
        successful canonical receipt above the ingress bound is a protocol/
        backend defect and refuses; it is never truncated."""

        raw = _canonical_json(payload)
        if len(raw) > ceo_ingress.MAX_RESPONSE_BYTES:
            raw = _canonical_json(
                {
                    "ok": False,
                    "error": {
                        "code": "response_too_large",
                        "message": "response exceeds byte limit",
                    },
                }
            )
        try:
            writer.write(raw)
            await writer.drain()
        except _CLIENT_GONE:
            return

    async def _send_ceo_ingress_error(
        self, writer: asyncio.StreamWriter, code: str, message: str
    ) -> None:
        await self._send_ceo_ingress_response(
            writer, {"ok": False, "error": {"code": code, "message": message}}
        )

    async def _handle_ceo_ingress_connection(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        """The dedicated CeoIngress protocol handler (§7, §8, R1 §2).

        Peer identity is authenticated against the ONE exact configured
        ingress peer uid — separate from the generic Operator
        ``allowed_peer_uids`` set — before any body read/parsing.  There is no
        generic dispatcher on this path: everything past peer authentication
        and the startup-readiness gate is delegated to
        ``executive_ceo_ingress.handle_frame``, which owns the three closed
        submit/status/state frame validators and typed error law.  Exactly one
        frame is read and one response is written per connection (§7.3).
        """

        task = asyncio.current_task()
        if task is not None:
            # §14.1: register on entry.  Removed in ``finally`` only once this
            # handler's admission/readback and response cleanup reaches the
            # real terminal point — a client disconnect does not remove it
            # while a canonical mutation is running.
            self._ceo_ingress_tasks.add(task)
        try:
            connection = writer.get_extra_info("socket")
            if connection is None:
                await self._send_ceo_ingress_error(
                    writer,
                    "peer_credentials_unavailable",
                    "control connection has no local socket identity",
                )
                return
            try:
                peer = _peer_uid(connection)
            except OSError:
                await self._send_ceo_ingress_error(
                    writer,
                    "peer_credentials_unavailable",
                    "kernel peer credentials could not be read",
                )
                return
            if peer is None:
                await self._send_ceo_ingress_error(
                    writer,
                    "peer_credentials_unavailable",
                    "platform exposes no trusted local peer uid",
                )
                return
            if peer != self._ceo_ingress_peer_uid:
                await self._send_ceo_ingress_error(
                    writer, "peer_denied", "peer uid is not authorized"
                )
                return
            # R1 §2.1 + R0 §4.2: startup remains refusal-only before ANY body
            # read.  Once both listeners are ready, exact-peer callers may
            # supply one bounded frame so R0 can identify the diagnostic state
            # schema.  PR-A submit/status still receive the unchanged full
            # admission predicate after schema discrimination and before any
            # grounding/business/ceo_intent call.
            if not self._ceo_ingress_ready:
                await self._send_ceo_ingress_error(
                    writer,
                    "ingress_unavailable",
                    "Executive CEO ingress is not currently admitting requests",
                )
                return
            try:
                raw = await reader.readuntil(b"\n")
            except asyncio.LimitOverrunError:
                await self._send_ceo_ingress_error(
                    writer, "request_too_large", "request exceeds byte limit"
                )
                return
            except asyncio.IncompleteReadError:
                # §7.3: EOF before newline is an incomplete/refused frame even
                # if the partial bytes would parse as valid JSON.
                await self._send_ceo_ingress_error(
                    writer, "invalid_json", "request frame is incomplete"
                )
                return
            # NIT 15b: unlike the generic Operator path (which falls through to
            # here with ``raw = exc.partial`` on ``IncompleteReadError`` and so
            # can reach this point with an empty ``raw``), BOTH exception
            # branches above ``return`` early; the only way to reach this line
            # is ``readuntil(b"\n")`` returning normally, which always yields
            # at least the separator byte.  ``not raw`` is therefore
            # unreachable here and is intentionally omitted (verified by
            # grepping both except clauses above: neither falls through).
            if len(raw) > ceo_ingress.MAX_REQUEST_BYTES:
                await self._send_ceo_ingress_error(
                    writer, "request_too_large", "request exceeds byte limit"
                )
                return
            try:
                text = raw.decode("utf-8", errors="strict")
            except UnicodeDecodeError:
                await self._send_ceo_ingress_error(
                    writer, "invalid_json", "request is not valid UTF-8"
                )
                return
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                await self._send_ceo_ingress_error(
                    writer, "invalid_json", "request is not valid JSON"
                )
                return
            if (
                isinstance(parsed, Mapping)
                and parsed.get("schema")
                in {ceo_ingress.SUBMIT_SCHEMA, ceo_ingress.STATUS_SCHEMA}
                and not self._ceo_ingress_ready_for_admission()
            ):
                await self._send_ceo_ingress_error(
                    writer,
                    "ingress_unavailable",
                    "Executive CEO ingress is not currently admitting requests",
                )
                return
            try:
                result = await ceo_ingress.handle_frame(
                    parsed,
                    runtime=self._require_runtime(),
                    grounding_provider=self._ceo_ingress_grounding_provider,
                    workspace_root=self.config.proof_workspace_root,
                    service_state=self._service_state,
                    ceo_ingress_armed=self._ceo_ingress_armed,
                    # Strict-v2 selection is trusted host composition.  The
                    # source-free public frame cannot opt itself into (or out
                    # of) the terminal-return admission path.
                    strict_v2_admission=(
                        self.config.terminal_return_armed
                        or self._ceo_ingress_dialogue_source_provider is not None
                    ),
                    execution_binding_provider=self._require_current_coo_binding,
                    dialogue_source_provider=(
                        self._ceo_ingress_dialogue_source_provider
                    ),
                )
            except ceo_ingress.CeoIngressError as exc:
                await self._send_ceo_ingress_error(writer, exc.code, exc.message)
                return
            except Exception:  # fail closed without a traceback or local paths
                await self._send_ceo_ingress_error(
                    writer, "internal_error", "Executive CEO ingress failed"
                )
                return
            await self._send_ceo_ingress_response(writer, {"ok": True, "result": result})
        finally:
            # §14.1 — remove the task from the drain set only AFTER its
            # admission/readback and response cleanup (writer close/drain)
            # reaches the real terminal point, so ``close()``'s drain-set wait
            # cannot observe this handler as "done" while its writer is still
            # being torn down.
            writer.close()
            try:
                await writer.wait_closed()
            except _CLIENT_GONE:
                pass
            if task is not None:
                self._ceo_ingress_tasks.discard(task)

    @staticmethod
    def _request(request: Any) -> tuple[str, dict[str, Any]]:
        if not isinstance(request, dict) or set(request) != {"version", "command", "args"}:
            raise ValueError("request must contain exactly version, command, and args")
        if request["version"] != CONTROL_PROTOCOL_VERSION:
            raise ValueError("unsupported control protocol version")
        command = request["command"]
        args = request["args"]
        if not isinstance(command, str) or not command:
            raise ValueError("command must be a non-empty string")
        if not isinstance(args, dict):
            raise ValueError("args must be an object")
        return command, args

    @staticmethod
    def _exact_args(args: Mapping[str, Any], expected: set[str]) -> None:
        if set(args) != expected:
            rendered = ", ".join(sorted(expected)) or "none"
            raise ValueError(f"command requires exactly these arguments: {rendered}")

    @staticmethod
    def _id(value: Any, name: str) -> str:
        if not isinstance(value, str) or _ID_RE.fullmatch(value) is None:
            raise ValueError(f"invalid {name}")
        return value

    def _proof_contract(self, *, workspace: Path, branch: str) -> dict[str, Any]:
        return {
            "objective": _PROOF_OBJECTIVE,
            "department": "executive-infrastructure",
            "priority": 0,
            "authority_level": "A0",
            "branch": branch,
            "worktree": str(workspace),
            "constraints": {
                "provider": self.config.provider,
                "model": self.config.model,
                "effort": self.config.effort,
                "cost_class": self.config.cost_class,
                "base_sha": self.config.proof_base_sha,
                "required_capabilities": ["code", "research", "tests"],
                "eligible_quota_classes": [self.config.quota_class],
            },
            "attempt_limit": 3,
            "requested_authorities": ["READ", "RESEARCH", "RUN_TESTS", "WRITE_BRANCH"],
            "allowed_write_paths": [_PROOF_ARTIFACT],
            "validation_commands": [list(_PROOF_VALIDATION)],
        }

    def _is_fixed_proof_job(self, job: Job) -> bool:
        if job.worktree is None or job.branch is None:
            return False
        workspace = Path(job.worktree)
        if not workspace.is_absolute() or workspace.parent != self.config.proof_workspace_root:
            return False
        match = _PROOF_WORKSPACE_RE.fullmatch(workspace.name)
        if match is None:
            return False
        nonce = match.group(1)
        if job.branch != f"{self.config.proof_branch}-{nonce}":
            return False
        expected = self._proof_contract(workspace=workspace, branch=job.branch)
        return (
            job.objective == expected["objective"]
            and job.department == expected["department"]
            and job.priority == expected["priority"]
            and job.authority_level == expected["authority_level"]
            and job.branch == expected["branch"]
            and job.worktree == expected["worktree"]
            and job.constraints == expected["constraints"]
            and job.attempt_limit == expected["attempt_limit"]
            and job.requested_authorities == expected["requested_authorities"]
            and job.allowed_write_paths == expected["allowed_write_paths"]
            and job.validation_commands == expected["validation_commands"]
        )

    def _register_worker(self) -> Any:
        runtime = self._require_runtime()
        binding = self._require_current_coo_binding()
        router = ModelRouter.load()
        alias = router.model_aliases[self.config.coo_model_alias]
        operator_alias = router.model_aliases[self.config.coo_operator_model_alias]
        coo_capabilities = list(alias.capabilities)
        operator_capabilities = list(operator_alias.capabilities)
        coo_metadata = {
            "service_managed": True,
            "purpose": "executive-coo-cycle",
            "model_alias": self.config.coo_model_alias,
            "routing_policy_version": binding["routing_policy_version"],
            "execution_profile_id": binding["execution_profile_id"],
            "execution_profile_digest": binding["execution_profile_digest"],
            "capability_policy_version": binding["capability_policy_version"],
            "capability_policy_digest": binding["capability_policy_digest"],
        }
        coo_default_metadata = dict(coo_metadata)
        coo_default_metadata.pop("model_alias", None)
        coo_default_metadata["capacity_variant"] = "default"
        operator_metadata = {
            "service_managed": True,
            "purpose": "executive-coo-operator-planner",
            "model_alias": self.config.coo_operator_model_alias,
            "routing_policy_version": binding[
                "operator_routing_policy_version"
            ],
            "execution_profile_id": binding[
                "operator_execution_profile_id"
            ],
            "execution_profile_digest": binding[
                "operator_execution_profile_digest"
            ],
            "capability_policy_version": binding[
                "operator_capability_policy_version"
            ],
            "capability_policy_digest": binding[
                "operator_capability_policy_digest"
            ],
            "harness_binary_digest": binding["operator_harness_binary_digest"],
            "harness_version": binding["operator_harness_version"],
        }
        proof_capabilities = ["code", "research", "tests"]
        existing = runtime.workers.get_worker(self.config.worker_id)
        if existing is not None:
            quota = runtime.workers.get_quota_class(
                self.config.worker_id, self.config.quota_class
            )
            if (
                existing.provider != self.config.provider
                or existing.account_label != self.config.worker_account_label
                or existing.worker_type != self.config.worker_type
                or quota is None
                or quota.provider != self.config.provider
                or quota.model != self.config.model
                or quota.effort != self.config.effort
                or quota.cost_class != self.config.cost_class
                or quota.capabilities != proof_capabilities
            ):
                raise StateConflict("configured worker identity already exists with different policy")
            runtime.workers.register_quota_class(
                self.config.worker_id,
                self.config.coo_quota_class,
                provider=str(binding["provider"]),
                model=str(binding["model"]),
                effort=str(binding["effort"]),
                cost_class=str(binding["cost_class"]),
                capabilities=coo_capabilities,
                metadata=coo_metadata,
            )
            runtime.workers.register_quota_class(
                self.config.worker_id,
                self.config.coo_default_quota_class,
                provider=str(binding["provider"]),
                model=str(binding["model"]),
                effort=str(binding["effort"]),
                cost_class="default",
                capabilities=coo_capabilities,
                metadata=coo_default_metadata,
            )
            if self.config.coo_operator_harness_armed:
                runtime.workers.register_quota_class(
                    self.config.worker_id,
                    self.config.coo_operator_quota_class,
                    provider=str(binding["operator_provider"]),
                    model=str(binding["operator_model"]),
                    effort=str(binding["operator_effort"]),
                    cost_class=str(binding["operator_cost_class"]),
                    capabilities=operator_capabilities,
                    metadata=operator_metadata,
                )
            refreshed = runtime.workers.get_worker(self.config.worker_id)
            assert refreshed is not None
            return refreshed
        return runtime.workers.register_worker(
            self.config.worker_id,
            provider=self.config.provider,
            account_label=self.config.worker_account_label,
            worker_type=self.config.worker_type,
            capabilities=sorted(
                set(proof_capabilities)
                | set(coo_capabilities)
                | (
                    set(operator_capabilities)
                    if self.config.coo_operator_harness_armed
                    else set()
                )
            ),
            quota_classes={
                self.config.quota_class: {
                    "provider": self.config.provider,
                    "model": self.config.model,
                    "effort": self.config.effort,
                    "cost_class": self.config.cost_class,
                    "capabilities": proof_capabilities,
                },
                self.config.coo_quota_class: {
                    "provider": binding["provider"],
                    "model": binding["model"],
                    "effort": binding["effort"],
                    "cost_class": binding["cost_class"],
                    "capabilities": coo_capabilities,
                    "metadata": coo_metadata,
                },
                self.config.coo_default_quota_class: {
                    "provider": binding["provider"],
                    "model": binding["model"],
                    "effort": binding["effort"],
                    "cost_class": "default",
                    "capabilities": coo_capabilities,
                    "metadata": coo_default_metadata,
                },
                **(
                    {
                        self.config.coo_operator_quota_class: {
                            "provider": binding["operator_provider"],
                            "model": binding["operator_model"],
                            "effort": binding["operator_effort"],
                            "cost_class": binding["operator_cost_class"],
                            "capabilities": operator_capabilities,
                            "metadata": operator_metadata,
                        }
                    }
                    if self.config.coo_operator_harness_armed
                    else {}
                ),
            },
            metadata={"service_managed": True},
        )

    async def _create_proof_job(self) -> Job:
        """Create one fresh exact-SHA, no-remote workspace for one proof Job."""

        runtime = self._require_runtime()
        async with self._workspace_lock:
            if any(not task.done() for task in self._dispatch_tasks.values()):
                raise StateConflict(
                    "cannot create a sibling proof workspace while a worker dispatch is active"
                )
            if runtime.workers.get_worker(self.config.worker_id) is None:
                raise StateConflict(
                    "register the configured Codex worker before creating proof work"
                )
            nonce = uuid4().hex
            workspace_name = f"proof-{nonce}"
            branch = f"{self.config.proof_branch}-{nonce}"
            receipt = await asyncio.to_thread(
                prepare_credentialless_clone,
                self.config.proof_source_repository,
                self.config.proof_workspace_root,
                job_id=workspace_name,
                base_sha=self.config.proof_base_sha,
                branch=branch,
                shared_gid=self.config.proof_shared_gid,
                shared_write_paths=(
                    (_PROOF_ARTIFACT,) if self.config.proof_shared_gid is not None else ()
                ),
            )
            workspace = Path(receipt.workspace_path)
            if (
                workspace.parent != self.config.proof_workspace_root
                or workspace.name != workspace_name
                or receipt.base_sha != self.config.proof_base_sha
                or receipt.branch != branch
                or receipt.remote_count != 0
            ):
                raise ServiceError("prepared proof workspace receipt drifted from policy")
            # The registry allocates the durable Job id.  The unguessable
            # service-created workspace/branch pair is persisted with that Job
            # and is the fixed proof identity checked again at dispatch.
            return runtime.jobs.create_job(
                **self._proof_contract(workspace=workspace, branch=branch)
            )

    @staticmethod
    def _path_exists(path: Path) -> bool:
        try:
            path.lstat()
        except FileNotFoundError:
            return False
        return True

    @staticmethod
    def _fsync_directory(path: Path) -> None:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    @staticmethod
    def _ensure_private_directory(path: Path) -> None:
        try:
            path.mkdir(mode=0o700)
        except FileExistsError:
            pass
        info = path.lstat()
        if (
            not stat.S_ISDIR(info.st_mode)
            or stat.S_ISLNK(info.st_mode)
            or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) & 0o077
        ):
            raise ServiceError(
                "workspace rotation receipt directory must be control-owned and owner-only"
            )

    def _observe_git(self, workspace: Path, arguments: list[str]) -> bytes:
        """Post-handoff observation-only Git. Mutation argv is refused here."""

        requested = tuple(arguments)
        if requested not in _SERVICE_GIT_OBSERVATION_ALLOWLIST:
            raise ServiceError(
                "proof workspace Git observer refuses mutating or unaudited operations"
            )
        home = self.config.proof_workspace_root / ".supervisor-home"
        environment = git_observation_env(
            {
                "PATH": "/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin:/opt/homebrew/bin",
                "HOME": str(home),
                "LANG": "C.UTF-8",
                "LC_ALL": "C.UTF-8",
                "TZ": "UTC",
                "GIT_CONFIG_GLOBAL": "/dev/null",
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_TERMINAL_PROMPT": "0",
                "GCM_INTERACTIVE": "never",
            }
        )
        try:
            completed = subprocess.run(
                ["git", "-C", str(workspace), *arguments],
                env=environment,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise ServiceError(f"proof workspace Git observation failed: {exc}") from exc
        if completed.returncode != 0:
            detail = completed.stderr.decode("utf-8", errors="replace").strip()[-500:]
            raise ServiceError(
                f"proof workspace Git observation failed ({completed.returncode}): {detail}"
            )
        return completed.stdout

    def _require_shared_git_handoff(self, workspace: Path) -> None:
        if self.config.proof_shared_gid is None:
            return
        try:
            validate_shared_git_handoff(
                workspace,
                control_uid=os.geteuid(),
                shared_gid=int(self.config.proof_shared_gid),
            )
        except GitHandoffError as exc:
            raise ServiceError(str(exc)) from exc

    def _workspace_observation(
        self,
        workspace: Path,
        *,
        require_fresh: bool,
        expected_branch: str,
    ) -> dict[str, Any]:
        info = workspace.lstat()
        if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
            raise ServiceError("proof workspace must be a real directory")
        head = self._observe_git(
            workspace, ["rev-parse", "--verify", "HEAD^{commit}"]
        ).decode("ascii", errors="strict").strip()
        branch = self._observe_git(
            workspace, ["rev-parse", "--abbrev-ref", "HEAD"]
        ).decode("utf-8", errors="strict").strip()
        cleanliness = observe_launch_cleanliness(
            lambda arguments: self._observe_git(workspace, list(arguments))
        )
        remotes = tuple(
            value
            for value in self._observe_git(workspace, ["remote"])
            .decode("utf-8", errors="strict")
            .splitlines()
            if value
        )
        if require_fresh and (
            head != self.config.proof_base_sha
            or branch != expected_branch
            or cleanliness.dirty
            or remotes
        ):
            raise ServiceError(
                "replacement proof workspace is not clean, exact-SHA, branch-bound, and no-remote"
            )
        if require_fresh:
            self._require_shared_git_handoff(workspace)
        return {
            "path": str(workspace),
            "device": int(info.st_dev),
            "inode": int(info.st_ino),
            "uid": int(info.st_uid),
            "gid": int(info.st_gid),
            "mode": stat.S_IMODE(info.st_mode),
            "head": head,
            "branch": branch,
            "status_sha256": hashlib.sha256(cleanliness.status).hexdigest(),
            "status_dirty": bool(cleanliness.status),
            "all_untracked_sha256": hashlib.sha256(
                cleanliness.all_untracked
            ).hexdigest(),
            "all_untracked_dirty": bool(cleanliness.all_untracked),
            "launch_clean": not cleanliness.dirty,
            "remote_count": len(remotes),
        }

    def _persist_rotation_receipt(
        self, receipt_path: Path, payload: Mapping[str, Any]
    ) -> tuple[dict[str, Any], str]:
        raw = _canonical_json(payload)
        temporary = receipt_path.with_name(
            f".{receipt_path.name}.{os.getpid()}.{uuid4().hex}.tmp"
        )
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(temporary, flags, 0o600)
        try:
            view = memoryview(raw)
            while view:
                written = os.write(descriptor, view)
                if written <= 0:  # pragma: no cover - defensive filesystem failure
                    raise OSError("short write while persisting workspace rotation receipt")
                view = view[written:]
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        try:
            # The receipt directory is private to the control UID.  A hard-link
            # publishes the fully fsynced bytes atomically and refuses overwrite.
            os.link(temporary, receipt_path, follow_symlinks=False)
        finally:
            temporary.unlink(missing_ok=True)
        self._fsync_directory(receipt_path.parent)
        return dict(payload), hashlib.sha256(raw).hexdigest()

    def _read_rotation_receipt(
        self,
        receipt_path: Path,
        *,
        job: Job,
        attempt_id: str,
        workspace: Path,
        archive_path: Path,
    ) -> tuple[dict[str, Any], str]:
        info = receipt_path.lstat()
        if (
            not stat.S_ISREG(info.st_mode)
            or stat.S_ISLNK(info.st_mode)
            or info.st_nlink != 1
            or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) & 0o077
        ):
            raise ServiceError("workspace rotation receipt is not an owner-only regular file")
        raw = receipt_path.read_bytes()
        try:
            payload = json.loads(raw.decode("utf-8", errors="strict"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ServiceError("workspace rotation receipt is invalid JSON") from exc
        if not isinstance(payload, dict) or (
            payload.get("schema_version") != _WORKSPACE_ROTATION_SCHEMA
            or payload.get("job_id") != job.job_id
            or payload.get("attempt_id") != attempt_id
            or payload.get("previous_status") != job.status.value
            or payload.get("workspace_path") != str(workspace)
            or payload.get("archive_path") != str(archive_path)
        ):
            raise ServiceError("workspace rotation receipt identity drifted")
        return payload, hashlib.sha256(raw).hexdigest()

    @staticmethod
    def _observation_matches_receipt(
        observed: Mapping[str, Any], recorded: Any
    ) -> bool:
        if not isinstance(recorded, dict):
            return False
        return all(recorded.get(key) == value for key, value in observed.items())

    def _rotate_proof_workspace(self, job: Job) -> dict[str, Any]:
        """Archive an interrupted attempt and recreate its exact persisted path."""

        runtime = self._require_runtime()
        if job.status not in {JobStatus.LOST, JobStatus.FAILED, JobStatus.RATE_LIMITED}:
            raise StateConflict(f"job {job.job_id} cannot requeue from {job.status.value}")
        attempt_id = job.current_attempt_id
        if attempt_id is None or _ID_RE.fullmatch(attempt_id) is None:
            raise StateConflict("proof requeue requires one terminal current attempt")
        attempt = runtime.attempts.get_attempt(attempt_id)
        if attempt is None or attempt.job_id != job.job_id:
            raise StateConflict("proof requeue lost its terminal attempt identity")
        if job.worktree is None or job.branch is None:
            raise StateConflict("proof requeue lost its workspace identity")
        workspace = Path(job.worktree)
        root = self.config.proof_workspace_root
        if workspace.parent != root or _PROOF_WORKSPACE_RE.fullmatch(workspace.name) is None:
            raise StateConflict("proof requeue workspace escaped its configured root")
        workspace_info = workspace.lstat()
        if (
            not stat.S_ISDIR(workspace_info.st_mode)
            or stat.S_ISLNK(workspace_info.st_mode)
            or workspace_info.st_uid != os.geteuid()
            or stat.S_IMODE(workspace_info.st_mode) != 0o700
        ):
            raise ServiceError(
                "proof requeue requires a control-owned sealed prior workspace"
            )
        root_info = root.lstat()
        if (
            not stat.S_ISDIR(root_info.st_mode)
            or stat.S_ISLNK(root_info.st_mode)
            or root_info.st_uid != os.geteuid()
            or stat.S_IMODE(root_info.st_mode) & 0o007
            or stat.S_IMODE(root_info.st_mode) & 0o020
        ):
            raise ServiceError("proof workspace root is not control-owned and protected")

        rotation_root = root / ".lost-attempts"
        self._ensure_private_directory(rotation_root)
        job_archive_root = rotation_root / job.job_id
        self._ensure_private_directory(job_archive_root)
        archive_path = job_archive_root / attempt_id
        receipt_path = job_archive_root / f"{attempt_id}.rotation.json"
        archive_exists = self._path_exists(archive_path)
        receipt_exists = self._path_exists(receipt_path)
        workspace_exists = self._path_exists(workspace)

        if receipt_exists:
            if not archive_exists or not workspace_exists:
                raise ServiceError("completed workspace rotation lost archived or replacement data")
            payload, receipt_sha256 = self._read_rotation_receipt(
                receipt_path,
                job=job,
                attempt_id=attempt_id,
                workspace=workspace,
                archive_path=archive_path,
            )
            old_observed = self._workspace_observation(
                archive_path, require_fresh=False, expected_branch=job.branch
            )
            old_observed["path"] = str(workspace)
            new_observed = self._workspace_observation(
                workspace, require_fresh=True, expected_branch=job.branch
            )
            if not self._observation_matches_receipt(
                old_observed, payload.get("old_workspace")
            ) or not self._observation_matches_receipt(
                new_observed, payload.get("new_workspace")
            ):
                raise ServiceError("workspace rotation evidence no longer matches its receipt")
        else:
            if archive_exists:
                old_observed = self._workspace_observation(
                    archive_path, require_fresh=False, expected_branch=job.branch
                )
                old_observed["path"] = str(workspace)
            else:
                if not workspace_exists:
                    raise ServiceError("proof workspace and interrupted evidence are both missing")
                old_observed = self._workspace_observation(
                    workspace, require_fresh=False, expected_branch=job.branch
                )
                os.rename(workspace, archive_path)
                self._fsync_directory(root)
                self._fsync_directory(job_archive_root)

            if not self._path_exists(workspace):
                clone = prepare_credentialless_clone(
                    self.config.proof_source_repository,
                    root,
                    job_id=workspace.name,
                    base_sha=self.config.proof_base_sha,
                    branch=job.branch,
                    shared_gid=self.config.proof_shared_gid,
                    shared_write_paths=(
                        (_PROOF_ARTIFACT,)
                        if self.config.proof_shared_gid is not None
                        else ()
                    ),
                )
                if Path(clone.workspace_path) != workspace:
                    raise ServiceError("replacement workspace path drifted from the durable Job")
            new_observed = self._workspace_observation(
                workspace, require_fresh=True, expected_branch=job.branch
            )
            payload = {
                "schema_version": _WORKSPACE_ROTATION_SCHEMA,
                "job_id": job.job_id,
                "attempt_id": attempt_id,
                "previous_status": job.status.value,
                "rotated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "workspace_path": str(workspace),
                "archive_path": str(archive_path),
                "old_workspace": old_observed,
                "new_workspace": new_observed,
            }
            payload, receipt_sha256 = self._persist_rotation_receipt(
                receipt_path, payload
            )

        event_payload = {
            "schema_version": _WORKSPACE_ROTATION_SCHEMA,
            "receipt_path": str(receipt_path),
            "receipt_sha256": receipt_sha256,
            "archive_path": str(archive_path),
            "workspace_path": str(workspace),
            "old_status_sha256": payload["old_workspace"]["status_sha256"],
            "new_head": payload["new_workspace"]["head"],
        }
        command_id = f"workspace-rotation-{receipt_sha256}"
        with runtime.store.transaction() as connection:
            exists = connection.execute(
                "SELECT 1 FROM events WHERE command_id=?", (command_id,)
            ).fetchone()
            if exists is None:
                runtime.store.append_event(
                    connection,
                    aggregate_type="job",
                    aggregate_id=job.job_id,
                    event_type="PROOF_WORKSPACE_ROTATED",
                    actor="executive-control-service",
                    job_id=job.job_id,
                    attempt_id=attempt_id,
                    payload=event_payload,
                    command_id=command_id,
                )
        return event_payload

    async def _requeue_proof_job(self, job_id: str) -> dict[str, Any]:
        runtime = self._require_runtime()
        async with self._workspace_lock:
            if any(not task.done() for task in self._dispatch_tasks.values()):
                raise StateConflict(
                    "cannot rotate a proof workspace while a worker dispatch is active"
                )
            job = runtime.jobs.get_job(job_id)
            if job is None or not self._is_fixed_proof_job(job):
                raise StateConflict("service requeue accepts only its fixed harmless proof job")
            rotation = await asyncio.to_thread(self._rotate_proof_workspace, job)
            requeued = await asyncio.to_thread(runtime.jobs.requeue_job, job_id)
            result = requeued.to_dict()
            result["workspace_rotation"] = rotation
            return result

    def _submit_service_intent(self, payload: Any) -> dict[str, Any]:
        """Submit through the existing sink with v2 host composition attached."""

        normalized = ceo_intent.validate_intent(payload)
        binding: dict[str, Any] | None = None
        dialogue_source: dict[str, Any] | None = None
        if normalized.get("schema") == ceo_intent.INTENT_SCHEMA_V2:
            # Replay/status is entirely durable. A current source provider is
            # admission evidence only and is never consulted for an existing
            # command, including while that provider is unavailable or moved.
            command_id = ceo_intent.command_id_for(str(normalized["intent_id"]))
            existing = self._require_runtime().store.find_event_by_command_id(
                command_id
            )
            if existing is not None:
                return ceo_intent.submit_intent(
                    self._require_runtime(),
                    normalized,
                    workspace_root=self.config.proof_workspace_root,
                )
            if normalized["grounding"].get("mastermind_sha") != self.config.proof_base_sha:
                raise ceo_intent.CeoIntentError(
                    "v2 intent grounding.mastermind_sha differs from the installed reviewed release"
                )
            binding = self._require_current_coo_binding()
            provider = self._ceo_ingress_dialogue_source_provider
            if self.config.terminal_return_armed and provider is None:
                raise ceo_intent.CeoIntentError(
                    "trusted host dialogue source is unavailable"
                )
            if provider is not None:
                intent_id = str(normalized["intent_id"])
                workstream = str(normalized.get("workstream") or "")
                try:
                    first_source = provider(intent_id, workstream)
                    if first_source is None:
                        raise StateConflict("trusted source is absent")
                    first_normalized = normalize_executive_dialogue_source(
                        first_source,
                        work_ref=workstream,
                    )
                    second_source = provider(intent_id, workstream)
                    if second_source is None:
                        raise StateConflict("trusted source is absent")
                    second_normalized = normalize_executive_dialogue_source(
                        second_source,
                        work_ref=workstream,
                    )
                except Exception as exc:
                    raise ceo_intent.CeoIntentError(
                        "trusted host dialogue source is unavailable"
                    ) from exc
                if first_normalized != second_normalized:
                    raise ceo_intent.CeoIntentConflict(
                        "trusted host dialogue source changed immediately before root creation"
                    )
                dialogue_source = second_normalized.to_dict()
        submit_kwargs: dict[str, Any] = {
            "workspace_root": self.config.proof_workspace_root,
        }
        if binding is not None:
            submit_kwargs["execution_binding"] = binding
            submit_kwargs["dialogue_source"] = dialogue_source
            submit_kwargs["require_dialogue_source"] = provider is not None
        receipt = ceo_intent.submit_intent(
            self._require_runtime(),
            normalized,
            **submit_kwargs,
        )
        if binding is not None:
            job = self._require_runtime().jobs.get_job(str(receipt.get("job_id") or ""))
            if job is None or not self._is_bound_coo_root(job):
                raise ceo_intent.CeoIntentError(
                    "accepted v2 intent is not bound to the current reviewed host profile"
                )
        return receipt

    def _is_bound_coo_root(self, root: Job) -> bool:
        binding = self._require_current_coo_binding()
        provenance = root.orchestration_provenance
        return bool(
            root.parent_job_id is None
            and root.root_job_id == root.job_id
            and root.depth == 0
            and root.orchestration_role == "aggregation"
            and isinstance(provenance, dict)
            and provenance.get("schema_version")
            == "mastermind.executive_orchestration_provenance/v1"
            and provenance.get("creator") == "ceo_intent"
            and provenance.get("job_id") == root.job_id
            and provenance.get("root_job_id") == root.job_id
            and provenance.get("parent_job_id") is None
            and root.worktree is not None
            and root.branch is not None
            and all(root.constraints.get(key) == value for key, value in binding.items())
        )

    def _require_bound_coo_job(self, job: Job) -> Job:
        runtime = self._require_runtime()
        root = runtime.jobs.get_job(job.root_job_id)
        if root is None or not self._is_bound_coo_root(root):
            raise StateConflict("COO dispatch root is not bound to the current host profile")
        if job.job_id != root.job_id and (
            job.parent_job_id != root.job_id
            or job.root_job_id != root.job_id
            or job.depth != 1
            or job.orchestration_role not in {"plan", "work", "review", "repair"}
        ):
            raise StateConflict("COO dispatch target is outside the direct strict-v2 subtree")
        binding = self._require_current_coo_binding()
        if (
            job.orchestration_role == "plan"
            and binding["operator_harness_armed"] is True
        ):
            expected = {
                "eligible_quota_classes": binding[
                    "operator_eligible_quota_classes"
                ],
                "provider": binding["operator_provider"],
                "model": binding["operator_model"],
                "effort": binding["operator_effort"],
                "cost_class": binding["operator_cost_class"],
                "base_sha": binding["base_sha"],
                "routing_policy_version": binding[
                    "operator_routing_policy_version"
                ],
                "execution_profile_id": binding[
                    "operator_execution_profile_id"
                ],
                "execution_profile_digest": binding[
                    "operator_execution_profile_digest"
                ],
                "capability_policy_version": binding[
                    "operator_capability_policy_version"
                ],
                "capability_policy_digest": binding[
                    "operator_capability_policy_digest"
                ],
                "harness_binary_digest": binding[
                    "operator_harness_binary_digest"
                ],
                "harness_version": binding["operator_harness_version"],
            }
        else:
            expected = {
                key: binding[key]
                for key in (
                    "eligible_quota_classes",
                    "provider",
                    "model",
                    "effort",
                    "base_sha",
                    "routing_policy_version",
                    "execution_profile_id",
                    "execution_profile_digest",
                    "capability_policy_version",
                    "capability_policy_digest",
                )
            }
            if job.constraints.get("cost_class") not in {"small", "default"}:
                raise StateConflict(
                    "COO Job cost class has no reviewed serialized capacity"
                )
        for key, value in expected.items():
            if job.constraints.get(key) != value:
                raise StateConflict(f"COO Job host binding drifted at {key}")
        if job.worktree != root.worktree or job.branch != root.branch:
            raise StateConflict("COO Job workspace/branch differs from its strict-v2 root")
        return root

    def _require_coo_workspace(self, job: Job) -> dict[str, Any]:
        root = self._require_bound_coo_job(job)
        assert root.worktree is not None and root.branch is not None
        workspace = Path(root.worktree).resolve(strict=False)
        if workspace.parent != self.config.proof_workspace_root:
            raise StateConflict("COO workspace is not a direct reviewed-root assignment")
        observation = self._workspace_observation(
            workspace,
            require_fresh=False,
            expected_branch=root.branch,
        )
        if observation["branch"] != root.branch or observation["remote_count"] != 0:
            raise ServiceError("COO workspace must remain branch-bound and credentialless")
        if (
            job.orchestration_role == "plan"
            and job.attempt_count == 0
            and (
                observation["head"] != self.config.proof_base_sha
                or observation["launch_clean"] is not True
            )
        ):
            raise ServiceError(
                "initial COO planner requires the clean exact reviewed-base workspace"
            )
        self._require_shared_git_handoff(workspace)
        return observation

    def _require_coo_worker_composed(self) -> None:
        runtime = self._require_runtime()
        binding = self._require_current_coo_binding()
        worker = runtime.workers.get_worker(self.config.worker_id)
        if (
            worker is None
            or worker.provider != binding["provider"]
            or worker.account_label != self.config.worker_account_label
            or worker.worker_type != self.config.worker_type
        ):
            raise StateConflict("reviewed COO worker identity is not registered")
        for quota_name, cost_class in (
            (self.config.coo_quota_class, "small"),
            (self.config.coo_default_quota_class, "default"),
        ):
            quota = runtime.workers.get_quota_class(self.config.worker_id, quota_name)
            if (
                quota is None
                or quota.provider != binding["provider"]
                or quota.model != binding["model"]
                or quota.effort != binding["effort"]
                or quota.cost_class != cost_class
                or any(
                    quota.metadata.get(key) != binding[key]
                    for key in (
                        "routing_policy_version",
                        "execution_profile_id",
                        "execution_profile_digest",
                        "capability_policy_version",
                        "capability_policy_digest",
                    )
                )
                or not set(ModelRouter.load().model_aliases[
                    self.config.coo_model_alias
                ].capabilities).issubset(set(quota.capabilities))
            ):
                raise StateConflict("reviewed COO worker quota identity is unavailable or drifted")
        if self.config.coo_operator_harness_armed:
            operator_quota = runtime.workers.get_quota_class(
                self.config.worker_id, self.config.coo_operator_quota_class
            )
            operator_alias = ModelRouter.load().model_aliases[
                self.config.coo_operator_model_alias
            ]
            if (
                operator_quota is None
                or operator_quota.provider != binding["operator_provider"]
                or operator_quota.model != binding["operator_model"]
                or operator_quota.effort != binding["operator_effort"]
                or operator_quota.cost_class != binding["operator_cost_class"]
                or any(
                    operator_quota.metadata.get(key) != binding[f"operator_{key}"]
                    for key in (
                        "routing_policy_version",
                        "execution_profile_id",
                        "execution_profile_digest",
                        "capability_policy_version",
                        "capability_policy_digest",
                    )
                )
                or operator_quota.metadata.get("harness_binary_digest")
                != binding["operator_harness_binary_digest"]
                or operator_quota.metadata.get("harness_version")
                != binding["operator_harness_version"]
                or not set(operator_alias.capabilities).issubset(
                    set(operator_quota.capabilities)
                )
            ):
                raise StateConflict(
                    "reviewed COO operator quota identity is unavailable or drifted"
                )

    async def _reconcile_unowned_cycle_attempts(self) -> None:
        if any(not task.done() for task in self._dispatch_tasks.values()):
            return
        runtime = self._require_runtime()
        active = [
            attempt
            for attempt in runtime.attempts.list_attempts()
            if attempt.status in _COO_ACTIVE_ATTEMPT_STATUSES
        ]
        if not active:
            return
        receipts = await asyncio.to_thread(
            self._require_supervisor().reconcile_restart,
            requeue_lost=False,
        )
        if self.operator_supervisor is not None:
            receipts.extend(
                await asyncio.to_thread(
                    self.operator_supervisor.reconcile_restart,
                    requeue_lost=False,
                )
            )
        self._startup_reconciliation.extend(receipts)
        ambiguous = [
            receipt
            for receipt in receipts
            if str(getattr(getattr(receipt, "status", None), "value", ""))
            == "IDENTITY_AMBIGUOUS"
        ]
        remaining = [
            attempt
            for attempt in runtime.attempts.list_attempts()
            if attempt.status in _COO_ACTIVE_ATTEMPT_STATUSES
        ]
        if ambiguous or remaining:
            self._service_state = "QUARANTINED"
            raise StateConflict(
                "unowned active Attempt identity could not be reconciled before COO claim"
            )

    async def _dispatch_cycle_job_exact(
        self, job_id: str, command_id: str
    ) -> OrchestrationDispatchOutcome:
        runtime = self._require_runtime()
        async with self._dispatch_lock:
            async with self._workspace_lock:
                live = {
                    value
                    for value, task in self._dispatch_tasks.items()
                    if not task.done()
                }
                if live and live != {job_id}:
                    raise StateConflict("the serialized worker already has another active dispatch")
                job = runtime.jobs.get_job(job_id)
                if job is None:
                    raise StateConflict(f"job {job_id!r} does not exist")
                self._require_bound_coo_job(job)
                if job.status not in {
                    JobStatus.QUEUED,
                    JobStatus.RUNNING,
                    JobStatus.CHECKPOINTED,
                }:
                    raise StateConflict(
                        f"job {job_id} cannot cycle-dispatch from {job.status.value}"
                    )
                if job.status is JobStatus.QUEUED:
                    self._require_coo_workspace(job)
                supervisor: Any = (
                    self._require_operator_supervisor()
                    if (
                        job.orchestration_role == "plan"
                        and self.config.coo_operator_harness_armed
                    )
                    else self._require_supervisor()
                )
                try:
                    started = await supervisor.start_cycle_job(
                        job_id, command_id=command_id
                    )
                except Exception as exc:
                    current = runtime.jobs.get_job(job_id)
                    if current is not None and current.status in {
                        JobStatus.RUNNING,
                        JobStatus.CHECKPOINTED,
                        JobStatus.CANCEL_REQUESTED,
                    }:
                        self._dispatch_errors[job_id] = (
                            f"{type(exc).__name__}: ambiguous cycle worker start; "
                            "restart reconciliation required"
                        )
                        self._service_state = "QUARANTINED"
                    raise
                if isinstance(started, OrchestrationDispatchOutcome):
                    if started.outcome == "TERMINAL":
                        await self._project_terminal_return(
                            started.job_id,
                            expected_attempt_id=started.attempt.attempt_id,
                        )
                    return started
                lease = getattr(started, "lease", None)
                attempt = getattr(lease, "attempt", None)
                token = getattr(lease, "lease_token", None)
                if attempt is None or not token:
                    raise ServiceError("cycle supervisor returned no active leased Attempt")
                task = asyncio.create_task(
                    self._finish_dispatched(job_id, started),
                    name=f"executive-cycle-finish-{job_id}",
                )
                self._dispatch_tasks[job_id] = task
                return OrchestrationDispatchOutcome(
                    command_id=command_id,
                    job_id=job_id,
                    attempt=attempt,
                    outcome="ACTIVE",
                    lease_token=token,
                )

    async def _run_coo_cycle_once(self, root_job_id: str) -> CooCycleOutcome:
        if self._closing:
            raise StateConflict("Executive control service is closing")
        if not self.config.coo_autonomy_armed:
            raise StateConflict("COO autonomy is not armed in reviewed host configuration")
        self._require_current_autonomy()
        if self._service_state != "READY":
            raise StateConflict(f"Executive control service is {self._service_state}")
        root_id = self._id(root_job_id, "root_job_id")
        async with self._coo_cycle_lock:
            self._require_coo_worker_composed()
            root = self._require_runtime().jobs.get_job(root_id)
            if root is None or not self._is_bound_coo_root(root):
                raise StateConflict("COO cycle accepts only an exact host-bound strict-v2 root")
            children = [
                job
                for job in self._require_runtime().jobs.list_jobs()
                if job.parent_job_id == root_id
            ]
            if not children:
                observation = self._require_coo_workspace(root)
                if (
                    observation["head"] != self.config.proof_base_sha
                    or observation["launch_clean"] is not True
                ):
                    raise ServiceError(
                        "new COO root requires the clean exact reviewed-base workspace"
                    )
            live = {
                value
                for value, task in self._dispatch_tasks.items()
                if not task.done()
            }
            live_jobs = [self._require_runtime().jobs.get_job(value) for value in live]
            if live and (
                any(value is None for value in live_jobs)
                or any(value.root_job_id != root_id for value in live_jobs if value is not None)
            ):
                raise StateConflict("another COO root owns the serialized worker")
            await self._reconcile_unowned_cycle_attempts()
            loop = asyncio.get_running_loop()

            def dispatch(job_id: str, command_id: str) -> OrchestrationDispatchOutcome:
                future = asyncio.run_coroutine_threadsafe(
                    self._dispatch_cycle_job_exact(job_id, command_id), loop
                )
                return future.result()

            outcome = await asyncio.to_thread(
                CooCycle(self._require_runtime(), dispatcher=dispatch).run_once,
                root_id,
            )
            self._coo_last_tick_at = datetime.now(timezone.utc).isoformat(
                timespec="seconds"
            )
            self._coo_last_outcome = outcome.to_dict()
            self._coo_last_error = None
            return outcome

    async def _run_coo_cycle(self, root_job_id: str) -> CooCycleOutcome:
        task = asyncio.current_task()
        if task is None:  # pragma: no cover - asyncio always owns service calls
            return await self._run_coo_cycle_once(root_job_id)
        self._coo_action_tasks.add(task)
        try:
            return await self._run_coo_cycle_once(root_job_id)
        finally:
            self._coo_action_tasks.discard(task)

    def _next_bound_coo_root(self) -> str | None:
        runtime = self._require_runtime()
        with runtime.store.read() as connection:
            rows = connection.execute(
                """
                SELECT job_id FROM jobs
                WHERE parent_job_id IS NULL AND root_job_id=job_id
                  AND orchestration_role='aggregation'
                  AND status IN ('QUEUED','RUNNING','CHECKPOINTED','RATE_LIMITED','FAILED','LOST')
                ORDER BY priority DESC,created_at_ms,job_id
                LIMIT ?
                """,
                (_COO_ROOT_SCAN_LIMIT + 1,),
            ).fetchall()
        if len(rows) > _COO_ROOT_SCAN_LIMIT:
            raise ServiceError("bounded COO root scan limit was exceeded")
        for row in rows:
            root = runtime.jobs.get_job(str(row["job_id"]))
            if root is None or not self._is_bound_coo_root(root):
                continue
            blocked = any(
                event.event_type == "COO_CYCLE_BLOCKED"
                for event in runtime.events.list_events(job_id=root.job_id)
            )
            if not blocked:
                return root.job_id
        return None

    def _record_coo_tick_refusal(self, root_job_id: str, exc: Exception) -> None:
        """Persist one idempotent, secret-free autonomous refusal receipt."""

        runtime = self._require_runtime()
        payload = {
            "schema_version": "mastermind.executive_coo_tick_refusal/v1",
            "root_job_id": root_job_id,
            "error_type": type(exc).__name__,
            "reason_code": "bounded_cycle_action_refused",
            "routing_policy_version": self._coo_execution_binding[
                "routing_policy_version"
            ],
            "capability_policy_digest": self._coo_execution_binding[
                "capability_policy_digest"
            ],
        }
        digest = hashlib.sha256(_canonical_json(payload)).hexdigest()
        command_id = f"coo-service-refusal:{digest}"
        with runtime.store.transaction() as connection:
            if connection.execute(
                "SELECT 1 FROM events WHERE command_id=?", (command_id,)
            ).fetchone() is None:
                runtime.store.append_event(
                    connection,
                    aggregate_type="job",
                    aggregate_id=root_job_id,
                    event_type="COO_SERVICE_TICK_REFUSED",
                    actor="executive-control-service",
                    job_id=root_job_id,
                    payload=payload,
                    command_id=command_id,
                )

    async def _coo_tick_loop(self) -> None:
        assert self._coo_shutdown_event is not None
        while not self._coo_shutdown_event.is_set():
            try:
                await asyncio.wait_for(
                    self._coo_shutdown_event.wait(),
                    timeout=float(self.config.coo_tick_interval_seconds),
                )
            except asyncio.TimeoutError:
                pass
            if self._coo_shutdown_event.is_set():
                return
            if self._service_state != "READY" or any(
                not task.done() for task in self._dispatch_tasks.values()
            ):
                continue
            root_id: str | None = None
            try:
                if not self.config.coo_autonomy_armed:
                    continue
                root_id = self._next_bound_coo_root()
                if root_id is not None:
                    await self._run_coo_cycle(root_id)
            except Exception as exc:
                self._coo_last_tick_at = datetime.now(timezone.utc).isoformat(
                    timespec="seconds"
                )
                self._coo_last_error = f"{type(exc).__name__}: {str(exc)[:500]}"
                if root_id is not None:
                    try:
                        self._record_coo_tick_refusal(root_id, exc)
                    except Exception:
                        # The original refusal remains the status truth.  A
                        # receipt-write defect must not trigger a second action
                        # or turn the same tick into an unbounded retry loop.
                        pass

    async def _finish_dispatched(self, job_id: str, active: Any) -> None:
        try:
            await self._require_supervisor().finish_job(active)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._dispatch_errors[job_id] = f"{type(exc).__name__}: {str(exc)[:500]}"
            # A finish/seal failure cannot be treated as an ordinary completed
            # dispatch.  Quarantine all mutating requests until an operator
            # restarts and identity-safely reconciles the still-active attempt.
            self._service_state = "QUARANTINED"
        else:
            lease = getattr(active, "lease", None)
            attempt = getattr(lease, "attempt", None)
            attempt_id = getattr(attempt, "attempt_id", None)
            if isinstance(attempt_id, str):
                await self._project_terminal_return(
                    job_id, expected_attempt_id=attempt_id
                )
        finally:
            current = asyncio.current_task()
            if self._dispatch_tasks.get(job_id) is current:
                self._dispatch_tasks.pop(job_id, None)

    async def _replay_terminal_returns_on_startup(self) -> None:
        """Re-offer durable terminal facts in canonical JobRegistry order."""

        if self._terminal_return_projector is None:
            return
        runtime = self._require_runtime()
        terminal_event_types = (
            _TERMINAL_RETURN_PREPARED_EVENT,
            _TERMINAL_RETURN_PRE_SUBMIT_REFUSED_EVENT,
            _TERMINAL_RETURN_ATTEMPTED_EVENT,
            _TERMINAL_RETURN_PROVEN_NO_EFFECT_EVENT,
            _TERMINAL_RETURN_EFFECT_UNKNOWN_EVENT,
            _TERMINAL_RETURN_APPLIED_EVENT,
        )

        # Phase evidence is authority-bearing, including an APPLIED receipt.
        # Validate every existing family read-only before counting or creating
        # any fresh obligation.  In particular, an orphan, alternate-command,
        # malformed, or duplicate APPLIED row must never suppress replay merely
        # because its aggregate id happens to equal a current Attempt id.
        event_placeholders = ",".join("?" for _ in terminal_event_types)
        with runtime.store.read() as connection:
            phase_rows = connection.execute(
                f"""
                SELECT DISTINCT
                       events.aggregate_type,
                       events.aggregate_id,
                       jobs.job_id,
                       jobs.current_attempt_id,
                       jobs.priority,
                       jobs.created_at_ms
                FROM events
                LEFT JOIN jobs
                  ON jobs.current_attempt_id=events.aggregate_id
                WHERE events.aggregate_type='terminal_return_projection'
                   OR events.event_type IN ({event_placeholders})
                   OR events.command_id LIKE 'terminal-return:%'
                ORDER BY jobs.priority DESC,jobs.created_at_ms,jobs.job_id,
                         events.aggregate_type,events.aggregate_id
                LIMIT ?
                """,
                (
                    *terminal_event_types,
                    _TERMINAL_RETURN_STARTUP_PHASE_AUDIT_LIMIT + 1,
                ),
            ).fetchall()

        if len(phase_rows) > _TERMINAL_RETURN_STARTUP_PHASE_AUDIT_LIMIT:
            self._service_state = "QUARANTINED"
            self._terminal_return_last_diagnostic = (
                "terminal-return:STARTUP_PHASE_AUDIT_LIMIT_EXCEEDED"
            )
            return

        unresolved: list[tuple[int, int, str, str]] = []
        saw_applied = False
        saw_source_free = False
        for row in phase_rows:
            job_id = row["job_id"]
            attempt_id = row["current_attempt_id"]
            if (
                row["aggregate_type"] != "terminal_return_projection"
                or not isinstance(job_id, str)
                or not isinstance(attempt_id, str)
                or row["aggregate_id"] != attempt_id
            ):
                self._service_state = "QUARANTINED"
                self._terminal_return_last_diagnostic = (
                    "terminal-return:EVIDENCE_REFUSED"
                )
                return
            try:
                completion = runtime.validated_role_completion(
                    job_id,
                    expected_attempt_id=attempt_id,
                )
                candidate = reduce_terminal_return(material=completion)
                _command_base, material = self._terminal_return_event_material(
                    candidate
                )
                with runtime.store.read() as connection:
                    phase = self._inspect_terminal_return_history(
                        connection,
                        candidate=candidate,
                        material=material,
                    )
            except (RuntimeProofError, TerminalReturnError):
                self._service_state = "QUARANTINED"
                self._terminal_return_last_diagnostic = (
                    "terminal-return:EVIDENCE_REFUSED"
                )
                return
            if phase is None:
                # The census found a namespace/event row, so a missing exact
                # family is itself drift rather than a fresh obligation.
                self._service_state = "QUARANTINED"
                self._terminal_return_last_diagnostic = (
                    "terminal-return:EVIDENCE_REFUSED"
                )
                return
            if (
                self._terminal_return_requires_source
                and candidate.dialogue_source is None
            ):
                # A complete source-free historical family is valid inert
                # history, not an armed Relay obligation.  It therefore
                # consumes neither replay budget nor transport activity.
                saw_source_free = True
                continue
            if phase == "APPLIED":
                saw_applied = True
            else:
                unresolved.append(
                    (
                        int(row["priority"]),
                        int(row["created_at_ms"]),
                        job_id,
                        attempt_id,
                    )
                )

        if len(unresolved) > _TERMINAL_RETURN_STARTUP_REPLAY_LIMIT:
            self._service_state = "QUARANTINED"
            self._terminal_return_last_diagnostic = (
                "terminal-return:STARTUP_REPLAY_LIMIT_EXCEEDED"
            )
            return

        source_gate = ""
        if self._terminal_return_requires_source:
            # Historical source-free roots are intentionally ineligible for
            # the armed bridge.  A partial source/digest record is retained in
            # the candidate set so canonical Runtime validation can refuse it
            # instead of laundering it as source-free history.
            source_gate = """
              AND EXISTS (
                    SELECT 1
                    FROM events AS root_created
                    WHERE root_created.event_type='JOB_CREATED'
                      AND root_created.job_id=jobs.root_job_id
                      AND (
                            json_type(
                                root_created.payload_json,
                                '$.provenance.dialogue_source'
                            ) IS NOT NULL
                            OR json_type(
                                root_created.payload_json,
                                '$.provenance.dialogue_source_digest'
                            ) IS NOT NULL
                      )
              )
            """
            with runtime.store.read() as connection:
                saw_source_free = saw_source_free or connection.execute(
                    """
                    SELECT 1
                    FROM jobs
                    WHERE status='COMPLETED'
                      AND orchestration_role IN ('plan','work','review','repair')
                      AND current_attempt_id IS NOT NULL
                      AND NOT EXISTS (
                            SELECT 1
                            FROM events AS phase
                            WHERE phase.aggregate_type='terminal_return_projection'
                              AND phase.aggregate_id=jobs.current_attempt_id
                      )
                      AND NOT EXISTS (
                            SELECT 1
                            FROM events AS root_created
                            WHERE root_created.event_type='JOB_CREATED'
                              AND root_created.job_id=jobs.root_job_id
                              AND (
                                    json_type(
                                        root_created.payload_json,
                                        '$.provenance.dialogue_source'
                                    ) IS NOT NULL
                                    OR json_type(
                                        root_created.payload_json,
                                        '$.provenance.dialogue_source_digest'
                                    ) IS NOT NULL
                              )
                      )
                    LIMIT 1
                    """
                ).fetchone() is not None
        with runtime.store.read() as connection:
            fresh_rows = connection.execute(
                f"""
                SELECT job_id,current_attempt_id,priority,created_at_ms
                FROM jobs
                WHERE status='COMPLETED'
                  AND orchestration_role IN ('plan','work','review','repair')
                  AND current_attempt_id IS NOT NULL
                  AND NOT EXISTS (
                        SELECT 1
                        FROM events AS phase
                        WHERE phase.aggregate_type='terminal_return_projection'
                          AND phase.aggregate_id=jobs.current_attempt_id
                  )
                  {source_gate}
                ORDER BY priority DESC,created_at_ms,job_id
                LIMIT ?
                """,
                (_TERMINAL_RETURN_STARTUP_REPLAY_LIMIT - len(unresolved) + 1,),
            ).fetchall()
        if len(unresolved) + len(fresh_rows) > _TERMINAL_RETURN_STARTUP_REPLAY_LIMIT:
            self._service_state = "QUARANTINED"
            self._terminal_return_last_diagnostic = (
                "terminal-return:STARTUP_REPLAY_LIMIT_EXCEEDED"
            )
            return
        for row in fresh_rows:
            job_id = str(row["job_id"])
            attempt_id = str(row["current_attempt_id"])
            try:
                completion = runtime.validated_role_completion(
                    job_id,
                    expected_attempt_id=attempt_id,
                )
                candidate = reduce_terminal_return(material=completion)
            except (RuntimeProofError, TerminalReturnError):
                self._service_state = "QUARANTINED"
                self._terminal_return_last_diagnostic = (
                    "terminal-return:EVIDENCE_REFUSED"
                )
                return
            if (
                self._terminal_return_requires_source
                and candidate.dialogue_source is None
            ):
                # The SQL source gate intentionally admits partial records so
                # Runtime can reject them.  A fully source-free candidate is
                # inert history and does not become an armed obligation.
                continue
            unresolved.append(
                (
                    int(row["priority"]),
                    int(row["created_at_ms"]),
                    job_id,
                    attempt_id,
                )
            )

        # Phase-bearing and fresh candidates share one canonical JobRegistry
        # order.  Classifying them in separate read-only passes must not change
        # which obligation receives the earliest external projection.
        unresolved.sort(key=lambda item: (-item[0], item[1], item[2]))
        for _priority, _created_at_ms, job_id, attempt_id in unresolved:
            await self._project_terminal_return(
                job_id,
                expected_attempt_id=attempt_id,
            )
        if saw_applied and not unresolved:
            self._terminal_return_last_diagnostic = (
                "terminal-return:ALREADY_APPLIED"
            )
        elif saw_source_free and not unresolved:
            self._terminal_return_last_diagnostic = (
                "terminal-return:SKIPPED_SOURCE_FREE"
            )

    @staticmethod
    def _terminal_return_event_material(
        candidate: TerminalReturnCandidate,
    ) -> tuple[str, dict[str, Any]]:
        return dialogue_observation.terminal_return_event_material(candidate)

    @staticmethod
    def _validate_terminal_return_event(
        event: Any,
        *,
        event_type: str,
        command_id: str,
        material: Mapping[str, Any],
        applied: bool,
    ) -> None:
        dialogue_observation.validate_terminal_return_event(
            event,
            event_type=event_type,
            command_id=command_id,
            material=material,
            applied=applied,
        )

    @staticmethod
    def _normalize_terminal_return_projection_receipt(
        receipt: Any,
        *,
        message_key: str,
    ) -> dict[str, Any]:
        return dialogue_observation.normalize_terminal_return_projection_receipt(
            receipt,
            message_key=message_key,
        )

    @staticmethod
    def _terminal_return_phase_spec(
        command_base: str,
    ) -> tuple[tuple[str, str, str], ...]:
        return dialogue_observation.terminal_return_phase_spec(command_base)

    def _begin_terminal_return_projection(
        self,
        candidate: TerminalReturnCandidate,
    ) -> tuple[str, str, dict[str, Any]]:
        """Create PREPARED and validate the complete exact phase history."""

        runtime = self._require_runtime()
        command_base, material = self._terminal_return_event_material(candidate)
        phase_spec = self._terminal_return_phase_spec(command_base)
        applied_command = phase_spec[-1][2]
        with runtime.store.transaction() as connection:
            phase = self._inspect_terminal_return_history(
                connection,
                candidate=candidate,
                material=material,
            )
            if phase is None:
                prepared_command = phase_spec[0][2]
                runtime.store.append_event(
                    connection,
                    aggregate_type="terminal_return_projection",
                    aggregate_id=candidate.attempt_id,
                    event_type=_TERMINAL_RETURN_PREPARED_EVENT,
                    actor="executive-control-service",
                    job_id=candidate.job_id,
                    attempt_id=candidate.attempt_id,
                    worker_id=candidate.worker_id,
                    payload=material,
                    command_id=prepared_command,
                )
                phase = "PREPARED"
        return phase, applied_command, material

    def _inspect_terminal_return_history(
        self,
        connection: sqlite3.Connection,
        *,
        candidate: TerminalReturnCandidate,
        material: Mapping[str, Any],
    ) -> str | None:
        return dialogue_observation.inspect_terminal_return_history(
            self._require_runtime(),
            connection,
            candidate=candidate,
            material=material,
        )

    def _record_terminal_return_phase(
        self,
        candidate: TerminalReturnCandidate,
        *,
        phase: str,
        material: Mapping[str, Any],
    ) -> None:
        runtime = self._require_runtime()
        command_base, expected_material = self._terminal_return_event_material(candidate)
        if dict(material) != expected_material:
            raise StateConflict("terminal-return projection material drifted")
        phase_by_name = {
            phase_name: (event_type, command_id)
            for phase_name, event_type, command_id in self._terminal_return_phase_spec(
                command_base
            )
        }
        if phase not in phase_by_name or phase in {"PREPARED", "APPLIED"}:
            raise StateConflict("terminal-return projection phase is invalid")
        event_type, command_id = phase_by_name[phase]
        with runtime.store.transaction() as connection:
            current_phase = self._inspect_terminal_return_history(
                connection,
                candidate=candidate,
                material=material,
            )
            existing = runtime.store.get_event_by_command_id(
                command_id,
                connection=connection,
            )
            if existing is not None:
                # The inspector validated this event and every predecessor as
                # one exact immutable family inside the same write lock.
                return
            if current_phase is None:
                raise StateConflict("terminal-return projection phase order drifted")
            allowed_next = {
                "PREPARED": {"PRE_SUBMIT_REFUSED", "ATTEMPTED"},
                "PRE_SUBMIT_REFUSED": {"ATTEMPTED"},
                "ATTEMPTED": {"PROVEN_NO_EFFECT", "EFFECT_UNKNOWN"},
                # A later explicitly commissioned retry may cross the same
                # already-recorded ATTEMPTED boundary.  Its ambiguous result
                # advances the durable state; a second known-zero receipt is
                # idempotent at the existing phase command.
                "PROVEN_NO_EFFECT": {"EFFECT_UNKNOWN"},
                "EFFECT_UNKNOWN": set(),
                "APPLIED": set(),
            }
            if phase not in allowed_next[current_phase]:
                raise StateConflict("terminal-return projection phase order drifted")
            runtime.store.append_event(
                connection,
                aggregate_type="terminal_return_projection",
                aggregate_id=candidate.attempt_id,
                event_type=event_type,
                actor="executive-control-service",
                job_id=candidate.job_id,
                attempt_id=candidate.attempt_id,
                worker_id=candidate.worker_id,
                payload=dict(material),
                command_id=command_id,
            )

    def _complete_terminal_return_projection(
        self,
        candidate: TerminalReturnCandidate,
        *,
        applied_command: str,
        material: Mapping[str, Any],
        projection_receipt: Any,
    ) -> None:
        runtime = self._require_runtime()
        command_base, expected_material = self._terminal_return_event_material(candidate)
        phase_spec = self._terminal_return_phase_spec(command_base)
        expected_applied_command = phase_spec[-1][2]
        if (
            dict(material) != expected_material
            or applied_command != expected_applied_command
        ):
            raise StateConflict("terminal-return projection material drifted")
        normalized_receipt = self._normalize_terminal_return_projection_receipt(
            projection_receipt,
            message_key=candidate.message_key,
        )
        payload = {**material, "projection_receipt": normalized_receipt}
        # Refuse unserializable/non-finite callback output before touching the
        # Runtime Event plane.
        _canonical_json(payload)
        with runtime.store.transaction() as connection:
            prior_phase = self._inspect_terminal_return_history(
                connection,
                candidate=candidate,
                material=material,
            )
            action = normalized_receipt["action"]
            if action == "POSTED" and prior_phase not in {
                "ATTEMPTED",
                "PROVEN_NO_EFFECT",
            }:
                raise StateConflict("terminal-return projection phase order drifted")
            if action == "RECOVERED" and prior_phase not in {
                "ATTEMPTED",
                "PROVEN_NO_EFFECT",
                "EFFECT_UNKNOWN",
            }:
                raise StateConflict("terminal-return projection phase order drifted")
            if action == "DUPLICATE" and prior_phase not in {
                "PREPARED",
                "PRE_SUBMIT_REFUSED",
                "ATTEMPTED",
                "PROVEN_NO_EFFECT",
            }:
                raise StateConflict("terminal-return projection phase order drifted")
            existing = runtime.store.get_event_by_command_id(
                applied_command,
                connection=connection,
            )
            if existing is not None:
                # The complete family, including APPLIED, was validated by the
                # inspector under this transaction's write lock.
                if existing.payload.get("projection_receipt") != normalized_receipt:
                    raise StateConflict("terminal-return projection receipt drifted")
                return
            runtime.store.append_event(
                connection,
                aggregate_type="terminal_return_projection",
                aggregate_id=candidate.attempt_id,
                event_type=_TERMINAL_RETURN_APPLIED_EVENT,
                actor="executive-control-service",
                job_id=candidate.job_id,
                attempt_id=candidate.attempt_id,
                worker_id=candidate.worker_id,
                payload=payload,
                command_id=applied_command,
            )

    async def _project_terminal_return(
        self, job_id: str, *, expected_attempt_id: str
    ) -> None:
        """Offer one freshly-reduced terminal candidate without changing Runtime truth."""

        projector = self._terminal_return_projector
        if projector is None:
            self._terminal_return_last_diagnostic = "terminal-return:PROJECTOR_UNBOUND"
            return
        runtime = self._require_runtime()
        try:
            material = runtime.validated_role_completion(
                job_id,
                expected_attempt_id=expected_attempt_id,
            )
        except RuntimeProofError:
            self._terminal_return_last_diagnostic = "terminal-return:EVIDENCE_REFUSED"
            return
        try:
            candidate = reduce_terminal_return(material=material)
        except TerminalReturnError as exc:
            self._terminal_return_last_diagnostic = f"terminal-return:{exc.code}"
            return
        command_base, _event_material = self._terminal_return_event_material(
            candidate
        )
        if self._terminal_return_requires_source and candidate.dialogue_source is None:
            existing = runtime.events.list_events(
                attempt_id=candidate.attempt_id,
                aggregate_type="terminal_return_projection",
                aggregate_id=candidate.attempt_id,
                command_id_prefix=f"{command_base}:",
            )
            if not existing:
                self._terminal_return_last_diagnostic = (
                    "terminal-return:SKIPPED_SOURCE_FREE"
                )
                return

        candidate_digest = hashlib.sha256(_canonical_json(candidate)).hexdigest()
        async with self._terminal_return_registry_lock:
            current = self._terminal_return_flights.get(command_base)
            if current is not None:
                current_digest, flight = current
                if current_digest != candidate_digest:
                    self._terminal_return_last_diagnostic = (
                        "terminal-return:EVIDENCE_REFUSED"
                    )
                    return
            else:
                flight = asyncio.create_task(
                    self._terminal_return_flight(
                        command_base,
                        candidate_digest,
                        candidate,
                    ),
                    name=f"executive-terminal-return-{candidate.attempt_id}",
                )
                self._terminal_return_flights[command_base] = (
                    candidate_digest,
                    flight,
                )
        await asyncio.shield(flight)

    async def _terminal_return_flight(
        self,
        command_base: str,
        candidate_digest: str,
        candidate: TerminalReturnCandidate,
    ) -> None:
        """Own one shielded same-candidate phase transition and Relay flight."""

        try:
            await self._project_terminal_return_once(candidate)
        finally:
            task = asyncio.current_task()
            async with self._terminal_return_registry_lock:
                current = self._terminal_return_flights.get(command_base)
                if current == (candidate_digest, task):
                    self._terminal_return_flights.pop(command_base, None)

    async def _project_terminal_return_once(
        self, candidate: TerminalReturnCandidate
    ) -> None:
        projector = self._terminal_return_projector
        assert projector is not None
        try:
            phase, applied_command, event_material = (
                self._begin_terminal_return_projection(candidate)
            )
        except RuntimeProofError:
            self._service_state = "QUARANTINED"
            self._terminal_return_last_diagnostic = "terminal-return:EVIDENCE_REFUSED"
            return
        if phase == "APPLIED":
            self._terminal_return_last_diagnostic = "terminal-return:ALREADY_APPLIED"
            return
        reconciling = phase in {"ATTEMPTED", "EFFECT_UNKNOWN"}
        retrying_known_zero = phase == "PROVEN_NO_EFFECT"
        crossed_write_boundary = False

        def before_write() -> None:
            nonlocal crossed_write_boundary
            try:
                self._record_terminal_return_phase(
                    candidate,
                    phase="ATTEMPTED",
                    material=event_material,
                )
            except RuntimeProofError:
                self._service_state = "QUARANTINED"
                self._terminal_return_last_diagnostic = (
                    "terminal-return:EVIDENCE_REFUSED"
                )
                raise
            crossed_write_boundary = True

        def preserve_pre_write_refusal(code: str) -> None:
            if retrying_known_zero:
                # No new write boundary was crossed.  Preserve the prior exact
                # no-effect fact rather than fabricating a later phase.
                self._terminal_return_last_diagnostic = (
                    f"terminal-return:PROVEN_NO_EFFECT:{code}"
                )
                return
            try:
                self._record_terminal_return_phase(
                    candidate,
                    phase="PRE_SUBMIT_REFUSED",
                    material=event_material,
                )
            except RuntimeProofError:
                self._service_state = "QUARANTINED"
                self._terminal_return_last_diagnostic = (
                    "terminal-return:EVIDENCE_REFUSED"
                )
                return
            self._terminal_return_last_diagnostic = (
                f"terminal-return:PRE_SUBMIT_REFUSED:{code}"
            )

        def preserve_effect_unknown(code: str | None = None) -> None:
            try:
                self._record_terminal_return_phase(
                    candidate,
                    phase="EFFECT_UNKNOWN",
                    material=event_material,
                )
            except RuntimeProofError:
                self._service_state = "QUARANTINED"
                self._terminal_return_last_diagnostic = (
                    "terminal-return:EVIDENCE_REFUSED"
                )
                return
            suffix = f":{code}" if code else ""
            self._terminal_return_last_diagnostic = (
                f"terminal-return:EFFECT_UNKNOWN{suffix}"
            )

        try:
            if reconciling:
                reconcile = getattr(projector, "reconcile", None)
                if not callable(reconcile):
                    self._terminal_return_last_diagnostic = (
                        "terminal-return:EFFECT_UNKNOWN"
                    )
                    return
                result = reconcile(candidate)
            else:
                project = getattr(projector, "project", None)
                target = project if callable(project) else projector
                try:
                    parameters = inspect.signature(target).parameters
                except (TypeError, ValueError):
                    parameters = {}
                if "before_write" in parameters:
                    result = target(candidate, before_write=before_write)
                else:
                    # Legacy injectable test projectors cannot expose their
                    # transport boundary. Conservatively record possible
                    # dispatch before invoking them; production always hooks it.
                    before_write()
                    result = target(candidate)
            if inspect.isawaitable(result):
                result = await result
            if reconciling and result is None:
                preserve_effect_unknown()
                return
            try:
                normalized_receipt = (
                    self._normalize_terminal_return_projection_receipt(
                        result,
                        message_key=candidate.message_key,
                    )
                )
            except StateConflict:
                # Receipt-shape failure is projector/transport evidence, not
                # corruption of the Runtime phase family.  After ATTEMPTED it
                # is therefore possible-effect uncertainty; before dispatch
                # it is a known-zero protocol refusal.
                if reconciling or crossed_write_boundary:
                    preserve_effect_unknown("StateConflict")
                else:
                    preserve_pre_write_refusal("PRE_SUBMIT_PROTOCOL_REFUSED")
                return
            if not crossed_write_boundary and not reconciling:
                if normalized_receipt["action"] != "DUPLICATE":
                    raise TerminalReturnProjectionError(
                        "PRE_SUBMIT_PROTOCOL_REFUSED"
                    )
            self._complete_terminal_return_projection(
                candidate,
                applied_command=applied_command,
                material=event_material,
                projection_receipt=normalized_receipt,
            )
            self._terminal_return_last_diagnostic = "terminal-return:APPLIED"
        except asyncio.CancelledError:
            raise
        except RuntimeProofError:
            # Runtime phase history is the projection authority.  Any drift
            # discovered after PREPARED is an evidence-integrity failure, not
            # a transport refusal and not permission to append a compensating
            # phase against the corrupt family.
            self._service_state = "QUARANTINED"
            self._terminal_return_last_diagnostic = (
                "terminal-return:EVIDENCE_REFUSED"
            )
        except TerminalReturnProjectionError as exc:
            if reconciling:
                preserve_effect_unknown()
            elif crossed_write_boundary and exc.code == "TRANSPORT_UNAVAILABLE":
                try:
                    self._record_terminal_return_phase(
                        candidate,
                        phase="PROVEN_NO_EFFECT",
                        material=event_material,
                    )
                except RuntimeProofError:
                    self._service_state = "QUARANTINED"
                    self._terminal_return_last_diagnostic = (
                        "terminal-return:EVIDENCE_REFUSED"
                    )
                    return
                self._terminal_return_last_diagnostic = (
                    "terminal-return:PROVEN_NO_EFFECT:TRANSPORT_UNAVAILABLE"
                )
            elif crossed_write_boundary:
                preserve_effect_unknown()
            else:
                preserve_pre_write_refusal(exc.code)
        except Exception as exc:
            code = type(exc).__name__
            if reconciling or crossed_write_boundary:
                preserve_effect_unknown(code)
            else:
                preserve_pre_write_refusal(code)

    async def _dispatch_job(self, job_id: str) -> dict[str, Any]:
        runtime = self._require_runtime()
        supervisor = self._require_supervisor()
        async with self._dispatch_lock:
            # The same lock guards every operation that can add, replace, or
            # rotate a direct child of either isolation root.  Hold it across
            # supervisor.start_job(): that call freezes the sibling manifest,
            # sends it to the worker broker, and returns only after the worker
            # process has spawned.  Register the active task before releasing
            # the lock so a concurrent creator cannot enter the snapshot/start
            # gap or slip through an unrecorded-active window.
            async with self._workspace_lock:
                if any(not task.done() for task in self._dispatch_tasks.values()):
                    raise StateConflict("the serialized worker already has an active dispatch")
                job = runtime.jobs.get_job(job_id)
                if job is None:
                    raise StateConflict(f"job {job_id!r} does not exist")
                if not self._is_fixed_proof_job(job):
                    raise StateConflict(
                        "service dispatch accepts only its fixed harmless proof job"
                    )
                if job.status is not JobStatus.QUEUED:
                    raise StateConflict(f"job {job_id} cannot dispatch from {job.status.value}")
                self._require_shared_git_handoff(Path(job.worktree))
                try:
                    active = await supervisor.start_job(job_id)
                except Exception as exc:
                    current = runtime.jobs.get_job(job_id)
                    if current is not None and current.status in {
                        JobStatus.RUNNING,
                        JobStatus.CHECKPOINTED,
                        JobStatus.CANCEL_REQUESTED,
                    }:
                        self._dispatch_errors[job_id] = (
                            f"{type(exc).__name__}: ambiguous worker start; "
                            "restart reconciliation required"
                        )
                        self._service_state = "QUARANTINED"
                    raise
                task = asyncio.create_task(
                    self._finish_dispatched(job_id, active),
                    name=f"executive-finish-{job_id}",
                )
                self._dispatch_tasks[job_id] = task
                attempt = getattr(getattr(active, "lease", None), "attempt", None)
                return {
                    "job_id": job_id,
                    "attempt": _jsonable(attempt) if attempt is not None else None,
                    "accepted": True,
                }

    def _backup_path(self, name: Any) -> Path:
        if self.config.backup_root is None:
            raise ServiceError("backup_root is not configured")
        if not isinstance(name, str) or _BACKUP_NAME_RE.fullmatch(name) is None:
            raise ValueError("backup name must be a simple .sqlite3 file name")
        root = self.config.backup_root.resolve(strict=False)
        path = (root / name).resolve(strict=False)
        if path.parent != root:
            raise ValueError("backup path escapes configured backup root")
        return path

    async def _dispatch_request(self, raw_request: Any) -> Any:
        command, args = self._request(raw_request)
        runtime = self._require_runtime()

        if command == "status":
            self._exact_args(args, set())
            active = sorted(
                job_id for job_id, task in self._dispatch_tasks.items() if not task.done()
            )
            return {
                "protocol": CONTROL_PROTOCOL_VERSION,
                "service_state": self._service_state,
                "instance_id": self.instance_id,
                "pid": os.getpid(),
                "started_at": self._started_at,
                "socket": str(self.socket_path),
                "active_dispatches": active,
                "dispatch_errors": dict(sorted(self._dispatch_errors.items())),
                "startup_reconciliation": _jsonable(self._startup_reconciliation),
                "coo_autonomy": {
                    "armed": self.config.coo_autonomy_armed,
                    "tick_interval_seconds": self.config.coo_tick_interval_seconds,
                    "model_alias": self.config.coo_model_alias,
                    "quota_classes": list(
                        self._coo_execution_binding["eligible_quota_classes"]
                    ),
                    "last_tick_at": self._coo_last_tick_at,
                    "last_outcome": self._coo_last_outcome,
                    "last_error": self._coo_last_error,
                },
            }
        if command == "health":
            self._exact_args(args, set())
            return self._database_health()
        if command == "activate-canary":
            self._exact_args(args, set())
            if self._service_state != "AWAITING_CANARY":
                raise StateConflict("Executive control service is not awaiting a canary")
            if self._canary_loader is None:
                raise ServiceError("Executive control service has no canary loader")
            verdict = await asyncio.to_thread(self._canary_loader)
            await self.activate_canary(verdict)
            return {"service_state": self._service_state}
        if self._service_state != "READY":
            raise StateConflict(
                f"Executive control service is {self._service_state}; "
                "only status, health, and canary activation are available"
            )
        if command == "workers":
            self._exact_args(args, set())
            return _jsonable(runtime.workers.list_workers())
        if command == "jobs":
            self._exact_args(args, set())
            return _jsonable(runtime.jobs.list_jobs())
        if command == "job":
            self._exact_args(args, {"job_id"})
            job_id = self._id(args["job_id"], "job_id")
            job = runtime.jobs.get_job(job_id)
            if job is None:
                raise StateConflict(f"job {job_id!r} does not exist")
            return _jsonable(job)
        if command == "attempt":
            self._exact_args(args, {"attempt_id"})
            attempt_id = self._id(args["attempt_id"], "attempt_id")
            attempt = runtime.attempts.get_attempt(attempt_id)
            if attempt is None:
                raise StateConflict(f"attempt {attempt_id!r} does not exist")
            return _jsonable(attempt)
        if command == "register-worker":
            self._exact_args(args, set())
            return _jsonable(self._register_worker())
        if command == "create-proof-job":
            self._exact_args(args, set())
            return _jsonable(await self._create_proof_job())
        if command == "dispatch":
            self._exact_args(args, {"job_id"})
            return await self._dispatch_job(self._id(args["job_id"], "job_id"))
        if command == "run-coo-cycle":
            self._exact_args(args, {"root_job_id"})
            return _jsonable(
                await self._run_coo_cycle(
                    self._id(args["root_job_id"], "root_job_id")
                )
            )
        if command == "submit-ceo-intent":
            # The bounded CEO write bridge (Phase 1E-A).  It validates one typed
            # envelope, lets the existing authority policy adjudicate it inside
            # create_job, and returns a receipt naming the resulting QUEUED Job.
            # Submission remains distinct from execution. V1 is structurally
            # undispatchable by this service. Strict v2 receives only the
            # reviewed host-owned G1 execution binding; a later, separately
            # armed run-coo-cycle action may advance that exact root.
            # ``CeoIntentError`` subclasses ValueError precisely so a refusal
            # lands on the existing `request_failed` code above rather than the
            # opaque `internal_error` path.
            self._exact_args(args, {"intent"})
            return _jsonable(
                await asyncio.to_thread(self._submit_service_intent, args["intent"])
            )
        if command == "ceo-intent-status":
            # Read-back only.  The durable JOB_CREATED event plus the Job row are
            # the whole record; no status store is introduced.
            self._exact_args(args, {"intent_id"})
            intent_id = self._id(args["intent_id"], "intent_id")
            return _jsonable(
                await asyncio.to_thread(
                    ceo_intent.resolve_intent,
                    runtime,
                    intent_id,
                )
            )
        if command == "cancel":
            self._exact_args(args, {"job_id"})
            return _jsonable(runtime.jobs.cancel_job(self._id(args["job_id"], "job_id")))
        if command == "reconcile":
            self._exact_args(args, set())
            if any(not task.done() for task in self._dispatch_tasks.values()):
                raise StateConflict("cannot reconcile while this service owns an active dispatch")
            return _jsonable(
                await asyncio.to_thread(
                    self._require_supervisor().reconcile_restart,
                    requeue_lost=False,
                )
            )
        if command == "requeue":
            self._exact_args(args, {"job_id"})
            job_id = self._id(args["job_id"], "job_id")
            return _jsonable(await self._requeue_proof_job(job_id))
        if command == "backup":
            self._exact_args(args, set())
            if self.config.backup_root is None:
                raise ServiceError("backup_root is not configured")
            self.config.backup_root.mkdir(mode=0o700, parents=True, exist_ok=True)
            self.config.backup_root.chmod(0o700)
            return _jsonable(
                await asyncio.to_thread(
                    self._backup_backend.create_online_backup,
                    runtime.store,
                    self.config.backup_root,
                )
            )
        if command == "verify-backup":
            self._exact_args(args, {"name"})
            database_path = self._backup_path(args["name"])
            manifest_path = database_path.with_suffix(".manifest.json")
            if not manifest_path.is_file() or manifest_path.is_symlink():
                raise ServiceError("backup has no canonical manifest and is not restorable")
            return _jsonable(
                await asyncio.to_thread(
                    self._backup_backend.verify_backup,
                    database_path,
                    manifest_path,
                )
            )
        raise ValueError(f"unknown control command {command!r}")


async def send_control_request(
    socket_path: str | Path,
    command: str,
    args: Mapping[str, Any] | None = None,
    *,
    max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
) -> dict[str, Any]:
    """Send one request over AF_UNIX; used by the thin operator CLI."""

    path = Path(socket_path)
    if not path.is_absolute():
        raise ServiceError("control socket path must be absolute")
    request = {
        "version": CONTROL_PROTOCOL_VERSION,
        "command": command,
        "args": dict(args or {}),
    }
    raw = _canonical_json(request)
    if len(raw) > DEFAULT_MAX_REQUEST_BYTES:
        raise ServiceError("control request exceeds byte limit")
    reader, writer = await asyncio.open_unix_connection(str(path), limit=max_response_bytes + 1)
    try:
        writer.write(raw)
        await writer.drain()
        try:
            response_raw = await reader.readuntil(b"\n")
        except asyncio.LimitOverrunError as exc:
            raise ServiceError("control response exceeds byte limit") from exc
        if len(response_raw) > max_response_bytes:
            raise ServiceError("control response exceeds byte limit")
        try:
            response = json.loads(response_raw.decode("utf-8", errors="strict"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ServiceError("control service returned invalid JSON") from exc
        if not isinstance(response, dict) or not isinstance(response.get("ok"), bool):
            raise ServiceError("control service returned an invalid envelope")
        return response
    finally:
        writer.close()
        await writer.wait_closed()


__all__ = [
    "BackupBackendProtocol",
    "CONTROL_PROTOCOL_VERSION",
    "DEFAULT_MAX_REQUEST_BYTES",
    "DEFAULT_MAX_RESPONSE_BYTES",
    "DialogueWakeResult",
    "DialogueWakeHistoricalTarget",
    "DialogueWakeTarget",
    "ExecutiveControlService",
    "ExecutiveDialogueWakeBridge",
    "ServiceConfig",
    "ServiceError",
    "SupervisorProtocol",
    "activate_launchd_socket",
    "send_control_request",
]
