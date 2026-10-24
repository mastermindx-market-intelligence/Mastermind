"""Bounded session-recovery/context diagnostics over existing Executive state.

These are projections, not another scheduler, memory store, provider router or
execution grant. The admitted owner must revalidate before every real operation.
"""
from __future__ import annotations

from collections import Counter
from typing import Any


def _count(name: str, value: Any, *, optional: bool = False, positive: bool = False):
    if optional and value is None:
        return
    if type(value) is not int or value < (1 if positive else 0):
        raise ValueError(f"{name} must be a {'positive' if positive else 'non-negative'} integer")


def _projection(action: str, **values) -> dict[str, Any]:
    return {"schema_version": "mastermind.session_recovery_diagnostic/v1",
            "authority_effect": "NONE", "operation_performed": False,
            "next_action": action, **values}


def context_plan(*, context_limit: int | None, used_tokens: int | None,
                 next_input_tokens: int, response_reserve: int, tool_reserve: int,
                 compaction_reserve: int, native_compaction_supported: bool | None,
                 durable_checkpoint_available: bool) -> dict[str, Any]:
    """Plan from adapter-observed token counts, never a universal model limit.

    Use the existing checkpoint INTENT/APPLIED owner for any compaction operation.
    An overflow does not authorize another overfull provider request. A usable
    durable frontier is a prerequisite to claiming state-preserving rotation.
    """
    _count("context_limit", context_limit, optional=True, positive=True)
    _count("used_tokens", used_tokens, optional=True)
    for name, value in (("next_input_tokens", next_input_tokens), ("response_reserve", response_reserve),
                        ("tool_reserve", tool_reserve), ("compaction_reserve", compaction_reserve)):
        _count(name, value)
    if native_compaction_supported is not None and type(native_compaction_supported) is not bool:
        raise TypeError("native_compaction_supported must be bool or None")
    if type(durable_checkpoint_available) is not bool:
        raise TypeError("durable_checkpoint_available must be bool")
    if context_limit is None or used_tokens is None:
        return _projection("OBSERVE_CONTEXT", reason="context_measurement_unknown")
    # Reserve recovery headroom before admitting the next turn, not only after
    # that turn has already filled the provider's context window.
    reserves = response_reserve + tool_reserve + compaction_reserve
    remaining = context_limit - used_tokens
    if next_input_tokens + reserves > context_limit:
        return _projection("REBUILD_NEXT_TURN_CONTEXT", remaining_tokens=remaining,
                           max_next_input_tokens=max(0, context_limit - reserves),
                           reason="next_turn_cannot_fit_even_after_compaction")
    required = used_tokens + next_input_tokens + reserves
    if required <= context_limit:
        return _projection("CONTINUE", remaining_tokens=remaining,
                           recovery_reserve_tokens=compaction_reserve)
    can_compact = used_tokens + compaction_reserve <= context_limit
    if not durable_checkpoint_available:
        return _projection("SAVE_DURABLE_FRONTIER" if can_compact else "RECONCILE_DURABLE_FRONTIER",
                           remaining_tokens=remaining, reason="portable_checkpoint_missing")
    if native_compaction_supported is True and can_compact:
        return _projection("COMPACT_SAME_SESSION", remaining_tokens=remaining,
                           remeasure_before_next_turn=True,
                           owner="existing_generation_bound_checkpoint_operation")
    return _projection("RESUME_FROM_DURABLE_CHECKPOINT", remaining_tokens=remaining,
                       owner="existing_retry_and_continuation_owners")


def portable_context_fit(*, target_context_limit: int, mandatory_tokens: int,
                         optional_tokens: int, response_reserve: int,
                         tool_reserve: int) -> dict[str, Any]:
    """Assess the source-owned capsule budget without truncating its contents."""
    _count("target_context_limit", target_context_limit, positive=True)
    for name, value in (("mandatory_tokens", mandatory_tokens), ("optional_tokens", optional_tokens),
                        ("response_reserve", response_reserve), ("tool_reserve", tool_reserve)):
        _count(name, value)
    budget = target_context_limit - response_reserve - tool_reserve
    optional_budget = max(0, budget - mandatory_tokens)
    if mandatory_tokens > budget:
        action = "TARGET_CONTEXT_TOO_SMALL"
    elif optional_tokens > optional_budget:
        action = "REBUILD_OPTIONAL_CONTEXT_FROM_REFS"
    else:
        action = "CONTEXT_FITS"
    return _projection(action, mandatory_tokens_dropped=0,
                       max_optional_tokens=optional_budget, available_input_tokens=max(0, budget))


def _modern_stop_without_legacy_quota_proof(con, *, job_id: str,
                                            attempt_id: str, worker_id: str,
                                            quota_class: str) -> bool:
    """Recognize a valid existing stop receipt, never grant quota requeue.

    This explains one known source integration gap. An OPERATION_APPLIED receipt
    proves that the current Runtime stop path committed, but is not the old
    OHF_GRACEFUL_STOP event required by the existing positive quota proof.
    All retry/reconciliation authority remains with the existing COO owner.
    """
    from .executive_runtime import (
        OHF_INTERNAL_GENERATION_OPERATION_SCHEMA_VERSION, _json_loads,
    )
    from .operator_harness_contract import (
        OperationId, OperationReceiptKind, operation_receipt_command_id,
    )

    modern = con.execute(
        "SELECT aggregate_id,command_id,payload_json FROM events "
        "WHERE event_type='OPERATOR_OPERATION_APPLIED' "
        "AND aggregate_type='operator_operation' AND actor='supervisor' "
        "AND job_id=? AND attempt_id=? AND worker_id=? AND quota_class=? "
        "ORDER BY event_id",
        (job_id, attempt_id, worker_id, quota_class),
    ).fetchall()
    for event in modern:
        payload = _json_loads(event["payload_json"], fallback={})
        if not isinstance(payload, dict) or set(payload) != {
            "schema_version", "operation_kind", "process_generation_id",
            "process_liveness", "provider_writer_state",
            "executive_writer_released",
        }:
            continue
        if (payload.get("schema_version")
                != OHF_INTERNAL_GENERATION_OPERATION_SCHEMA_VERSION
                or payload.get("operation_kind") != "graceful_stop"
                or payload.get("process_liveness") != "PROVEN_DEAD"
                or payload.get("provider_writer_state") != "RELEASED"
                or payload.get("executive_writer_released") is not True
                or not isinstance(payload.get("process_generation_id"), str)
                or not payload["process_generation_id"]):
            continue
        bound_generation = con.execute(
            "SELECT g.session_epoch_id,h.provider_session_id "
            "FROM process_generations g JOIN harness_session_epochs h "
            "ON h.session_epoch_id=g.session_epoch_id "
            "WHERE g.process_generation_id=? AND g.worker_id=? "
            "AND h.attempt_id=? AND h.worker_id=? "
            "AND g.ended_at_ms IS NOT NULL AND g.executive_writer_held=0 "
            "AND g.provider_writer_state='RELEASED' LIMIT 1",
            (payload["process_generation_id"], worker_id, attempt_id, worker_id),
        ).fetchone()
        if bound_generation is None:
            continue
        # An APPLIED-looking row is not proof of the existing supervisor
        # operation unless it has the exact deterministic receipt identity and
        # its own source-bound INTENT. This remains a diagnostic, not a new
        # quota stop/requeue proof.
        try:
            operation = OperationId(str(event["aggregate_id"] or ""))
            applied_id = operation_receipt_command_id(
                operation, OperationReceiptKind.APPLIED,
            )
        except (TypeError, ValueError):
            continue
        if event["command_id"] != applied_id:
            continue
        intent = con.execute(
            "SELECT payload_json FROM events "
            "WHERE event_type='OPERATOR_OPERATION_INTENT' "
            "AND aggregate_type='operator_operation' AND actor='supervisor' "
            "AND aggregate_id=? AND command_id=? "
            "AND job_id=? AND attempt_id=? AND worker_id=? AND quota_class=? "
            "LIMIT 1",
            (operation.command_id, operation.command_id, job_id,
             attempt_id, worker_id, quota_class),
        ).fetchone()
        if intent is None:
            continue
        expected_intent = {
            "schema_version": OHF_INTERNAL_GENERATION_OPERATION_SCHEMA_VERSION,
            "operation_kind": "graceful_stop",
            "attempt_id": attempt_id,
            "session_epoch_id": bound_generation["session_epoch_id"],
            "process_generation_id": payload["process_generation_id"],
            "worker_id": worker_id,
            "provider_session_id": bound_generation["provider_session_id"],
        }
        if _json_loads(intent["payload_json"], fallback=None) != expected_intent:
            continue
        legacy = con.execute(
            "SELECT 1 FROM events WHERE event_type='OHF_GRACEFUL_STOP' "
            "AND aggregate_type='process_generation' AND aggregate_id=? "
            "AND job_id=? AND attempt_id=? AND worker_id=? AND quota_class=? "
            "LIMIT 1",
            (payload["process_generation_id"], job_id, attempt_id,
             worker_id, quota_class),
        ).fetchone()
        if legacy is None:
            return True
    return False


def project_root_recovery(runtime, root_job_id: str, *, limit: int = 100,
                          after_job_id: str | None = None) -> dict[str, Any]:
    """One read snapshot for an already-authorized original root's worker triage.

    Caller authentication/root access remains with the existing Executive entry
    point. No raw transcript, credentials, queue position, capacity ETA or liveness
    is invented. Counts describe the bounded returned set, not an unseen whole fleet.
    """
    from .executive_runtime import _retry_safety_material, _json_loads
    from .executive_retry_safety import classify_retry_safety, RetrySafetyDecision
    from .executive_registered_supply import registered_supply_projection
    from .executive_coo_policy import CooCyclePolicy

    policy = CooCyclePolicy.load()
    if not isinstance(root_job_id, str) or not root_job_id or root_job_id.strip() != root_job_id:
        raise ValueError("an exact existing root_job_id is required")
    if type(limit) is not int or not 1 <= limit <= 500:
        raise ValueError("limit must be between 1 and 500")
    if after_job_id is not None and (
        not isinstance(after_job_id, str) or not after_job_id
        or len(after_job_id) > 256 or after_job_id.strip() != after_job_id
    ):
        raise ValueError("cursor must be an exact worker Job ID")
    items = []
    with runtime.store.read() as con:
        root = con.execute("SELECT job_id,root_job_id,status,current_attempt_id FROM jobs WHERE job_id=?", (root_job_id,)).fetchone()
        if root is None or root["root_job_id"] != root_job_id:
            raise ValueError("root Job is absent or is not an original root")
        if after_job_id is not None and con.execute(
            "SELECT 1 FROM jobs WHERE job_id=? AND root_job_id=? AND job_id!=?",
            (after_job_id, root_job_id, root_job_id),
        ).fetchone() is None:
            raise ValueError("cursor is not a worker of this original root")
        total_jobs = con.execute(
            "SELECT COUNT(*) FROM jobs WHERE root_job_id=? AND job_id!=?",
            (root_job_id, root_job_id),
        ).fetchone()[0]
        direct_children = con.execute(
            "SELECT COUNT(*) FROM jobs WHERE parent_job_id=?",
            (root_job_id,),
        ).fetchone()[0]
        observed_event_id = con.execute(
            "SELECT COALESCE(MAX(e.event_id),0) FROM events e JOIN jobs j ON j.job_id=e.job_id "
            "WHERE j.root_job_id=?", (root_job_id,),
        ).fetchone()[0]
        rows = list(con.execute(
            "SELECT * FROM jobs WHERE root_job_id=? AND job_id!=? "
            "AND (? IS NULL OR job_id>?) ORDER BY job_id LIMIT ?",
            (root_job_id, root_job_id, after_job_id, after_job_id, limit + 1)))
        for row in rows[:limit]:
            status = row["status"]
            attempt_id = row["current_attempt_id"]
            current = con.execute(
                "SELECT a.worker_id,a.quota_class,q.status AS pool_status,q.provider,q.model "
                "FROM attempts a LEFT JOIN worker_quota_classes q "
                "ON q.worker_id=a.worker_id AND q.quota_class=a.quota_class "
                "WHERE a.attempt_id=? AND a.job_id=?", (attempt_id, row["job_id"]),
            ).fetchone() if attempt_id else None
            previous = None
            stop_reason = "QUOTA_OR_RATE_LIMIT" if status == "RATE_LIMITED" else None
            stop_reason_scope = "current_attempt" if stop_reason else None
            action = "INSPECT_CURRENT_ATTEMPT"
            reasons = []
            retry = None
            quota_stop_gap = None
            if status == "QUEUED" and attempt_id is None:
                action = "WAIT_FOR_EXISTING_SCHEDULER"
                reasons.append("canonical_job_queued_capacity_not_resolved_by_this_view")
                # Preserve the last observed stop through the existing Event /
                # Attempt join. This is history, not a new retry authorization.
                previous = con.execute(
                    "SELECT a.attempt_id,a.worker_id,a.quota_class,a.status,q.status AS pool_status "
                    "FROM events e JOIN attempts a "
                    "ON a.attempt_id=e.attempt_id AND a.job_id=e.job_id "
                    "LEFT JOIN worker_quota_classes q ON q.worker_id=a.worker_id "
                    "AND q.quota_class=a.quota_class "
                    "WHERE e.job_id=? AND e.event_type='JOB_REQUEUED' "
                    "AND e.aggregate_type='job' AND e.aggregate_id=e.job_id "
                    "AND e.actor='operator' AND e.worker_id=a.worker_id "
                    "AND e.quota_class=a.quota_class "
                    "ORDER BY e.event_id DESC LIMIT 1", (row["job_id"],),
                ).fetchone()
                if previous is not None and previous["status"] == "RATE_LIMITED":
                    stop_reason = "QUOTA_OR_RATE_LIMIT"
                    stop_reason_scope = "previous_attempt"
                    reasons.append("requeued_after_quota_limit")
            elif status in {"COMPLETED", "CANCELLED"}:
                action = "INSPECT_TERMINAL_RESULT"
            elif status in {"RATE_LIMITED", "FAILED", "LOST"} and attempt_id:
                material = _retry_safety_material(con, job_id=row["job_id"], expected_attempt_id=attempt_id)
                evidence = material.projection.evidence
                decision = classify_retry_safety(evidence)
                retry = decision.value
                if decision is RetrySafetyDecision.SAFE_REQUEUE:
                    action = "REQUEUE_WITH_EXISTING_COO"
                elif decision is RetrySafetyDecision.TERMINAL_NO_RETRY:
                    action = "ATTEMPT_ALLOWANCE_DECISION_REQUIRED"
                elif decision is RetrySafetyDecision.NEEDS_RECONCILIATION:
                    action = "RECONCILE_ORIGINAL_ATTEMPT"
                else:
                    action = "OWNER_DIAGNOSIS_REQUIRED"
                if evidence.writer_or_provider_generation_live:
                    reasons.append("predecessor_writer_not_released")
                if evidence.effect_unknown:
                    reasons.append("unresolved_effect_or_missing_positive_release_proof")
                    if (status == "RATE_LIMITED" and current is not None
                            and _modern_stop_without_legacy_quota_proof(
                                con, job_id=row["job_id"], attempt_id=attempt_id,
                                worker_id=current["worker_id"],
                                quota_class=current["quota_class"],
                            )):
                        quota_stop_gap = "MODERN_STOP_NOT_LEGACY_QUOTA_PROOF"
                        reasons.append("modern_stop_applied_but_quota_proof_not_recognized")
                if not evidence.effective_grant_non_modifying:
                    reasons.append("modifying_or_unknown_grant_requires_existing_continuation_gate")
                if evidence.candidate_present or evidence.result_present or evidence.seal_present:
                    reasons.append("existing_work_or_result_must_be_reconciled_not_replayed")
            # Registered supply is a diagnostic only. It never establishes
            # model equivalence, shared-budget independence, or an admitted slot.
            supply = (
                registered_supply_projection(con, _json_loads(row["constraints_json"], fallback=None))
                if status == "QUEUED" and attempt_id is None else None
            )
            items.append({
                "job_id": row["job_id"], "attempt_id": attempt_id,
                "source_status": status, "next_action": action,
                "stop_reason": stop_reason, "stop_reason_scope": stop_reason_scope,
                "previous_attempt_id": previous["attempt_id"] if previous is not None else None,
                "previous_worker_id": previous["worker_id"] if previous is not None else None,
                "previous_quota_class": previous["quota_class"] if previous is not None else None,
                "previous_pool_status": previous["pool_status"] if previous is not None else None,
                "current_worker_id": current["worker_id"] if current is not None else None,
                "current_quota_class": current["quota_class"] if current is not None else None,
                "current_pool_status": current["pool_status"] if current is not None else None,
                "current_provider": current["provider"] if current is not None else None,
                "current_model": current["model"] if current is not None else None,
                "route_observation_scope": "REGISTERED_QUOTA_NOT_SERVED_MODEL",
                "capacity_assessment": "NOT_EVALUATED",
                "registered_supply": supply,
                "parent_job_id": row["parent_job_id"],
                "orchestration_role": row["orchestration_role"],
                "attempts_remaining": max(0, row["attempt_limit"] - row["attempt_count"]),
                "retry_decision": retry, "reason_codes": reasons,
                "quota_stop_receipt_gap": quota_stop_gap,
                "checkpoint_available": row["checkpoint_json"] is not None,
                "queue_position": None, "capacity_eta": None,
            })
    return {"schema_version": "mastermind.root_session_recovery/v1",
            "root_job_id": root_job_id, "authority_effect": "NONE", "operation_performed": False,
            "jobs": items, "included_count": len(items), "has_more": len(rows) > limit,
            "next_after_job_id": items[-1]["job_id"] if len(rows) > limit else None,
            "page_consistency": "LIVE_KEYSET", "returned_counts_only": True,
            "registered_free_slots_not_additive_across_jobs": True,
            "read_only_supply_scope": "REGISTRY_NOT_GLOBAL_CAPACITY_ADMISSION",
            "recovery_queue_count": sum(item["source_status"] == "QUEUED" for item in items),
            "total_jobs": total_jobs, "observed_event_id": observed_event_id,
            "reviewed_coo_policy": {
                "policy_sha256": policy.policy_sha256,
                "max_fan_out_per_parent": policy.max_fan_out_per_parent,
                "max_children_total": policy.max_children_total,
                "max_depth": policy.max_depth,
                "direct_children_observed": direct_children,
                "state": ("EXCEEDS_REVIEWED_CHILD_CEILING"
                          if direct_children > policy.max_children_total
                          else "WITHIN_REVIEWED_BOUNDS"),
                "observation_scope": "DIRECT_CHILD_COUNT_NOT_ADMISSION",
                "capacity_admitted_by_view": False,
                "one_root_can_admit_30_workers": (
                    policy.max_fan_out_per_parent >= 30
                    and policy.max_children_total >= 30
                ),
                "native_fabric_lease_capacity_unchanged": True,
            },
            "root_status": root["status"], "root_attempt_id": root["current_attempt_id"],
            "count_by_action": dict(sorted(Counter(item["next_action"] for item in items).items()))}


def adapter_stop_diagnostic(failure, *, guard_refusal: str | None = None) -> dict[str, Any]:
    """Explain a typed adapter stop; routing reassessment is never retry authority.

    Guard refusals come from the existing policy/auth owner and dominate provider
    labels. Raw log strings are deliberately not classified as quota exhaustion.
    """
    from .operator_harness_contract import AdapterFailureClass

    if failure is not None and not isinstance(failure, AdapterFailureClass):
        raise TypeError("failure must be AdapterFailureClass or None")
    guards = {"permission", "safety", "authentication", "human_approval"}
    if guard_refusal is not None and guard_refusal not in guards:
        raise ValueError("guard_refusal is not a closed policy-owner cause")
    if guard_refusal is not None:
        action, reassess, reason = "RETURN_TO_EXISTING_GUARD_OWNER", False, guard_refusal
    elif failure in {AdapterFailureClass.QUOTA_OR_RATE_LIMIT, AdapterFailureClass.PROVIDER_CONCURRENCY}:
        action, reassess, reason = "REASSESS_EXISTING_CAPACITY", True, failure.value
    elif failure is AdapterFailureClass.AUTH_FAILURE:
        action, reassess, reason = "REPAIR_AUTHENTICATION", False, failure.value
    elif failure is AdapterFailureClass.HUMAN_APPROVAL_REQUIRED:
        action, reassess, reason = "WAIT_FOR_HUMAN_APPROVAL", False, failure.value
    elif failure in {AdapterFailureClass.PROCESS_CRASH, AdapterFailureClass.SESSION_MISSING,
                     AdapterFailureClass.ACTIVE_WRITER_CONFLICT,
                     AdapterFailureClass.MCP_OR_TOOL_TRANSPORT_FAILURE}:
        action, reassess, reason = "RECONCILE_ORIGINAL_GENERATION", False, failure.value
    elif failure is None:
        action, reassess, reason = "OWNER_DIAGNOSIS_REQUIRED", False, "UNKNOWN_STOP_CAUSE"
    else:
        action, reassess, reason = "OWNER_DIAGNOSIS_REQUIRED", False, failure.value
    return _projection(action, reason=reason, reassess_capacity=reassess, retry_authorized=False)
