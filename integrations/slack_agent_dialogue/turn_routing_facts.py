"""Trusted projection from current-worker identity to turn-routing facts.

This adapter is deliberately pure. It consumes one already-resolved WP-3
Company Dialogue binding, the canonical SessionTargetRegistry, and fresh
RuntimeBinding snapshots. It owns no lifecycle, persistence, transport,
credential, retry, queue, or provider state.
"""
from __future__ import annotations

import copy
import re
from collections.abc import Callable, Mapping
from typing import Any

from common.commission_ref import CommissionRef
from control_plane.executive_delegation_identity import ExecutiveDelegationIdentity
from control_plane.executive_runtime import (
    AttemptStatus,
    ExecutiveDialogueSource,
    WorkerStatus,
)
from control_plane.executive_terminal_return import TerminalReturnCandidate
from control_plane.session_targets import (
    RuntimeBinding,
    SessionTargetError,
    SessionTargetRegistry,
)
from integrations.slack_agent_dialogue.company_dialogue_runtime_binding import (
    BindingReason,
    BindingState,
    CompanyDialogueBindingResolution,
    CurrentWorkerDialogueSnapshot,
)
from integrations.slack_agent_dialogue.contract import DialogueContractError
from integrations.slack_agent_dialogue.contract_v2 import validate_parent_v2
from integrations.slack_agent_dialogue.executive_terminal_return_projector import (
    ResolvedTerminalReturnBinding,
    TerminalReturnProjectionReceipt,
)
from integrations.slack_agent_dialogue.turn_watcher import TurnRoutingFacts


_ERROR_CODES = frozenset(
    {
        "DIALOGUE_PARENT_INVALID",
        "CURRENT_WORKER_UNRESOLVED",
        "DIALOGUE_BINDING_MISMATCH",
        "CURRENT_WORKER_BINDING_DRIFT",
        "TARGET_BINDING_MISMATCH",
        "TERMINAL_RESULT_BINDING_MISMATCH",
        "TERMINAL_RESULT_RECEIPT_MISMATCH",
    }
)
_THREAD_TS_RE = re.compile(r"\A[1-9][0-9]{9,15}\.[0-9]{6}\Z")
_DIGEST_RE = re.compile(r"\A[0-9a-f]{64}\Z")
_SLACK_USER_ID_RE = re.compile(r"\A[UW][A-Z0-9]{8,31}\Z")
_ALLOWED_MESSAGE_TYPES = (
    "ACK",
    "BLOCKED",
    "DECISION_REQUEST",
    "PROGRESS",
    "RESULT",
)


class TurnRoutingFactsError(RuntimeError):
    """Closed routing refusal that never renders provider-private identity."""

    def __init__(self, code: str) -> None:
        if code not in _ERROR_CODES:
            raise ValueError("unknown turn routing facts error code")
        self.code = code
        super().__init__(code)


def _refuse(code: str) -> None:
    raise TurnRoutingFactsError(code)


def _validated_parent(dialogue_parent: Mapping[str, Any]) -> dict[str, Any]:
    try:
        return validate_parent_v2(copy.deepcopy(dict(dialogue_parent)))
    except (DialogueContractError, TypeError, ValueError):
        _refuse("DIALOGUE_PARENT_INVALID")
    raise AssertionError("unreachable")


def _binding_matches_current(
    resolution: CompanyDialogueBindingResolution,
    parent: Mapping[str, Any],
    current: CurrentWorkerDialogueSnapshot,
) -> bool:
    binding = resolution.binding
    if binding is None:
        return False

    expected_actor = {
        "kind": "worker_attempt",
        "job_id": current.job_id,
        "attempt_id": current.attempt_id,
        "worker_id": current.worker_id,
    }
    expected_applies_to = {
        "kind": "executive_attempt",
        "job_id": current.job_id,
        "attempt_id": current.attempt_id,
        "worker_id": current.worker_id,
    }
    try:
        return bool(
            binding.work_ref == parent["work_ref"]
            and dict(binding.commission_ref) == dict(parent["commission_ref"])
            and binding.session_ref == parent["session_ref"]
            and binding.operation_key == parent["operation_key"]
            and binding.watch_mode == parent["watch_mode"]
            and dict(binding.actor_ref) == expected_actor
            and dict(binding.applies_to) == expected_applies_to
            and binding.allowed_message_types == _ALLOWED_MESSAGE_TYPES
            and binding.reply_to_message_key is None
            and isinstance(binding.thread_ts, str)
            and binding.thread_ts != ""
        )
    except (AttributeError, KeyError, TypeError, ValueError):
        return False


def _fresh_binding(
    current_binding_for: Callable[[str], RuntimeBinding | None],
    seat: str,
    *,
    error_code: str,
) -> RuntimeBinding | None:
    try:
        binding = current_binding_for(seat)
    except Exception:
        _refuse(error_code)
    if binding is not None and not isinstance(binding, RuntimeBinding):
        _refuse(error_code)
    return binding


def _target_is_bound(
    registry: SessionTargetRegistry,
    *,
    seat: str,
    root_job_id: str,
    binding: RuntimeBinding | None,
) -> bool:
    try:
        registry.resolve(
            seat,
            root_job_id=root_job_id,
            binding=binding,
        )
    except SessionTargetError:
        _refuse("TARGET_BINDING_MISMATCH")
    return binding is not None


def resolve_turn_routing_facts(
    *,
    dialogue_parent: Mapping[str, Any],
    current_worker: CurrentWorkerDialogueSnapshot,
    binding_resolution: CompanyDialogueBindingResolution,
    registry: SessionTargetRegistry,
    current_binding_for: Callable[[str], RuntimeBinding | None],
) -> TurnRoutingFacts:
    """Derive the only routing facts accepted by the turn classifier.

    WP-3 remains the owner of exact-current-worker authentication. This
    adapter validates that immutable projection against the supplied parent,
    rechecks the current worker RuntimeBinding before any target lookup, and
    lets SessionTargetRegistry resolve the logical CEO/COO destinations.
    """

    parent = _validated_parent(dialogue_parent)
    if (
        not isinstance(current_worker, CurrentWorkerDialogueSnapshot)
        or not isinstance(binding_resolution, CompanyDialogueBindingResolution)
        or not isinstance(registry, SessionTargetRegistry)
        or not callable(current_binding_for)
    ):
        _refuse("CURRENT_WORKER_UNRESOLVED")

    if (
        binding_resolution.state is not BindingState.RESOLVED
        or binding_resolution.reason is not BindingReason.EXACT_CURRENT_WORKER
        or binding_resolution.binding is None
    ):
        _refuse("CURRENT_WORKER_UNRESOLVED")

    if (
        current_worker.parent_fingerprint != parent["fingerprint"]
        or not _binding_matches_current(binding_resolution, parent, current_worker)
    ):
        _refuse("DIALOGUE_BINDING_MISMATCH")

    current_coo = _fresh_binding(
        current_binding_for,
        "coo",
        error_code="CURRENT_WORKER_BINDING_DRIFT",
    )
    if current_coo != current_worker.runtime_binding:
        _refuse("CURRENT_WORKER_BINDING_DRIFT")

    coo_bound = _target_is_bound(
        registry,
        seat="coo",
        root_job_id=current_worker.root_job_id,
        binding=current_coo,
    )
    current_ceo = _fresh_binding(
        current_binding_for,
        "ceo",
        error_code="TARGET_BINDING_MISMATCH",
    )
    ceo_bound = _target_is_bound(
        registry,
        seat="ceo",
        root_job_id=current_worker.root_job_id,
        binding=current_ceo,
    )

    return TurnRoutingFacts(
        bound_operation_key=str(parent["operation_key"]),
        bound_commission_fingerprint=str(parent["fingerprint"]),
        root_job_id=current_worker.root_job_id,
        routing_workstream=None,
        source_workstream=str(parent["work_ref"]),
        ceo_target_bound=ceo_bound,
        coo_target_bound=coo_bound,
    )


def resolve_terminal_turn_routing_facts(
    *,
    delegation_identity: ExecutiveDelegationIdentity,
    dialogue_parent: Mapping[str, Any],
    thread_ts: str,
    current_worker: CurrentWorkerDialogueSnapshot,
    terminal_candidate: TerminalReturnCandidate,
    projection_receipt: TerminalReturnProjectionReceipt,
    resolved_binding: ResolvedTerminalReturnBinding,
    registry: SessionTargetRegistry,
    current_binding_for: Callable[[str], RuntimeBinding | None],
) -> TurnRoutingFacts:
    """Derive terminal routing only from protected R2 and current owners."""

    parent = _validated_parent(dialogue_parent)
    if (
        type(delegation_identity) is not ExecutiveDelegationIdentity
        or type(current_worker) is not CurrentWorkerDialogueSnapshot
        or type(terminal_candidate) is not TerminalReturnCandidate
        or type(resolved_binding) is not ResolvedTerminalReturnBinding
        or not isinstance(registry, SessionTargetRegistry)
        or not callable(current_binding_for)
    ):
        _refuse("TERMINAL_RESULT_BINDING_MISMATCH")

    terminal = terminal_candidate
    source = terminal.dialogue_source
    expected_actor = {
        "kind": "worker_attempt",
        "job_id": terminal.job_id,
        "attempt_id": terminal.attempt_id,
        "worker_id": terminal.worker_id,
    }
    expected_applies_to = {
        "kind": "executive_attempt",
        "job_id": terminal.job_id,
        "attempt_id": terminal.attempt_id,
        "worker_id": terminal.worker_id,
    }
    try:
        source_commission = (
            source.commission_ref.to_dict()
            if type(source) is ExecutiveDialogueSource
            and type(source.commission_ref) is CommissionRef
            else None
        )
        binding_commission = dict(resolved_binding.commission_ref)
        binding_actor = dict(resolved_binding.actor_ref)
        binding_applies_to = dict(resolved_binding.applies_to)
    except (AttributeError, TypeError, ValueError):
        _refuse("TERMINAL_RESULT_BINDING_MISMATCH")

    if (
        type(source) is not ExecutiveDialogueSource
        or current_worker.attempt_status is not AttemptStatus.COMPLETED
        or current_worker.worker_status is not WorkerStatus.AVAILABLE
        or terminal.runtime_status != "COMPLETED"
        or terminal.result_status != "RESULT"
        or (
            current_worker.job_id,
            current_worker.attempt_id,
            current_worker.worker_id,
            current_worker.root_job_id,
        )
        != (
            terminal.job_id,
            terminal.attempt_id,
            terminal.worker_id,
            terminal.root_job_id,
        )
        or (
            delegation_identity.job_id,
            delegation_identity.root_job_id,
            delegation_identity.operation_key,
            delegation_identity.session_ref,
        )
        != (
            terminal.job_id,
            terminal.root_job_id,
            terminal.operation_key,
            terminal.session_ref,
        )
        or current_worker.parent_fingerprint != parent["fingerprint"]
        or parent["operation_key"] != terminal.operation_key
        or parent["session_ref"] != terminal.session_ref
        or parent["work_ref"] != source.work_ref
        or parent["commission_ref"] != source_commission
        or parent["watch_mode"] != source.watch_mode
        or resolved_binding.work_ref != parent["work_ref"]
        or binding_commission != parent["commission_ref"]
        or resolved_binding.session_ref != parent["session_ref"]
        or resolved_binding.operation_key != parent["operation_key"]
        or resolved_binding.watch_mode != parent["watch_mode"]
        or binding_actor != expected_actor
        or binding_applies_to != expected_applies_to
        or resolved_binding.allowed_message_types != ("RESULT",)
    ):
        _refuse("TERMINAL_RESULT_BINDING_MISMATCH")

    if (
        type(projection_receipt) is not TerminalReturnProjectionReceipt
        or projection_receipt.action not in {"POSTED", "RECOVERED", "DUPLICATE"}
        or projection_receipt.message_key != terminal.message_key
        or projection_receipt.thread_ts != thread_ts
        or projection_receipt.parent_fingerprint != parent["fingerprint"]
        or projection_receipt.duplicate_timestamps != ()
        or not isinstance(thread_ts, str)
        or not isinstance(projection_receipt.message_ts, str)
        or not isinstance(projection_receipt.fingerprint, str)
        or not isinstance(projection_receipt.parent_author_user_id, str)
        or _THREAD_TS_RE.fullmatch(thread_ts) is None
        or _THREAD_TS_RE.fullmatch(projection_receipt.message_ts) is None
        or _DIGEST_RE.fullmatch(projection_receipt.fingerprint) is None
        or _SLACK_USER_ID_RE.fullmatch(
            projection_receipt.parent_author_user_id
        )
        is None
    ):
        _refuse("TERMINAL_RESULT_RECEIPT_MISMATCH")

    current_coo = _fresh_binding(
        current_binding_for,
        "coo",
        error_code="TARGET_BINDING_MISMATCH",
    )
    coo_bound = _target_is_bound(
        registry,
        seat="coo",
        root_job_id=terminal.root_job_id,
        binding=current_coo,
    )
    current_ceo = _fresh_binding(
        current_binding_for,
        "ceo",
        error_code="TARGET_BINDING_MISMATCH",
    )
    ceo_bound = _target_is_bound(
        registry,
        seat="ceo",
        root_job_id=terminal.root_job_id,
        binding=current_ceo,
    )
    return TurnRoutingFacts(
        bound_operation_key=str(parent["operation_key"]),
        bound_commission_fingerprint=str(parent["fingerprint"]),
        root_job_id=terminal.root_job_id,
        routing_workstream=None,
        source_workstream=str(parent["work_ref"]),
        ceo_target_bound=ceo_bound,
        coo_target_bound=coo_bound,
    )


__all__ = [
    "TurnRoutingFactsError",
    "resolve_terminal_turn_routing_facts",
    "resolve_turn_routing_facts",
]
