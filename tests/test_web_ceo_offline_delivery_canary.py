from __future__ import annotations

import json
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch

import pytest

import tests.test_executive_os_phase1fc as phase1fc_tests
from control_plane.dialogue_source_resolution import (
    DialogueSourceObservation,
    PhysicalDialogueSourceIdentity,
    attention_source_ref,
    correlated_source_ref,
)
from control_plane.executive_dialogue_observation import (
    CANONICAL_WAKE_EVENT_BUDGET,
    CanonicalTerminalWakeCandidate,
    DialogueObservationFacts,
    TerminalObservationFacts,
    TerminalProjectionReceiptFacts,
    read_canonical_terminal_wake,
    terminal_return_event_material,
    terminal_return_phase_spec,
)
from control_plane.ceo_intent import submit_intent as real_submit_intent
from control_plane.executive_runtime import JobStatus, Runtime
from control_plane.executive_orchestration_principal import digest
from control_plane.executive_terminal_return import reduce_terminal_return
from control_plane.wake_events import mint_obligation
from control_plane.wake_ledger import (
    AckMode,
    DeliveryAttempt,
    LedgerPhase,
    SourceReadHealth,
    SourceResolutionCode,
    TrustedAckContext,
    acknowledge,
    ack_record,
    attempt_record,
    ledger_command_id,
    requested_record,
    resolve_source,
    resolved_record,
)
from control_plane.wake_persist import WakeLedgerRepository
from scripts.web_ceo_offline_delivery_canary import (
    LEGACY_RECEIPT_SCHEMA,
    RECEIPT_SCHEMA,
    build_receipt,
    main,
)
from tests.test_executive_os_phase1fc import (
    _cycle_through_completed_work,
    _complete_ohf_role,
    _review_body,
)


EXPECTED_KEYS = {
    "schema",
    "release_sha",
    "root_job_id",
    "plan_digest",
    "work_revisions",
    "review_revisions",
    "repair_revisions",
    "aggregation_result_digest",
    "web_sol_turns_between_admission_and_handoff",
    "manual_continue_edges",
    "intervention_measurements",
    "terminal_return_projection_state",
    "wake_obligation_state",
    "wake_acknowledgement_mode",
    "semantic_parent_action_state",
    "production_acceptance_state",
    "stage_promotion_eligible",
    "proof_admissibility",
    "effect_uncertainty",
    "source_evidence",
    "observed_at",
}


def _offline_delivery_runtime(
    root_path: Path,
    *,
    with_dialogue_source: bool = False,
):
    dialogue_source = {
        "schema_version": "mastermind.executive_dialogue_source/v1",
        "work_ref": "WS:EXECUTIVE-INFRASTRUCTURE",
        "commission_ref": {
            "repository": "mastermindx-market-intelligence/Mastermind",
            "commit": "c" * 40,
            "path": "research/commission.md",
            "content_sha256": "d" * 64,
        },
        "watch_mode": "turn_watch_v1",
    }

    def submit_with_source(runtime, payload):
        source_bound_payload = {**payload, "workstream": dialogue_source["work_ref"]}
        return real_submit_intent(
            runtime,
            source_bound_payload,
            dialogue_source=dialogue_source,
            require_dialogue_source=True,
        )

    context = (
        patch.object(phase1fc_tests, "submit_intent", submit_with_source)
        if with_dialogue_source
        else nullcontext()
    )
    with context:
        runtime, cycle, dispatches, root, planner, work, work_seal = (
            _cycle_through_completed_work(
                root_path,
                intent_id="CEO-OFFLINE-RECEIPT",
                review_workers=["worker-b", "worker-b"],
            )
        )
    assert cycle.run_once(root.job_id).action == "REVIEW_CREATED"
    assert cycle.run_once(root.job_id).action == "DISPATCHED"
    rejecting_review = dispatches[-1]
    plan_digest = str(runtime.jobs.get_job(work.attempt.job_id).plan_digest)
    reject_body = _review_body(
        root_id=root.job_id,
        plan_attempt_id=planner.attempt.attempt_id,
        plan_digest=plan_digest,
        target_job_id=work.attempt.job_id,
        target_attempt_id=work.attempt.attempt_id,
        target_result_digest=work_seal["role_result_digest"],
        repair_round=0,
        verdict="reject",
    )
    reject_seal, _terminal = _complete_ohf_role(
        runtime, rejecting_review, reject_body, identity_seed=9401
    )

    assert cycle.run_once(root.job_id).action == "REPAIR_CREATED"
    assert cycle.run_once(root.job_id).action == "DISPATCHED"
    repair = dispatches[-1]
    repair_body = {
        "schema_version": "mastermind.repair_result/v1",
        "root_job_id": root.job_id,
        "plan_attempt_id": planner.attempt.attempt_id,
        "plan_digest": plan_digest,
        "plan_step_id": "step-1",
        "repair_round": 1,
        "supersedes_job_id": work.attempt.job_id,
        "rejected_review_job_id": rejecting_review.attempt.job_id,
        "rejected_review_result_digest": reject_seal["role_result_digest"],
        "artifacts": [],
        "evidence_digests": [],
    }
    repair_seal, _repair_terminal = _complete_ohf_role(
        runtime, repair, repair_body, identity_seed=9402
    )

    assert cycle.run_once(root.job_id).action == "REVIEW_CREATED"
    assert cycle.run_once(root.job_id).action == "DISPATCHED"
    approving_review = dispatches[-1]
    approval_body = _review_body(
        root_id=root.job_id,
        plan_attempt_id=planner.attempt.attempt_id,
        plan_digest=plan_digest,
        target_job_id=repair.attempt.job_id,
        target_attempt_id=repair.attempt.attempt_id,
        target_result_digest=repair_seal["role_result_digest"],
        repair_round=1,
        verdict="approve",
    )
    approval_seal, _approval_terminal = _complete_ohf_role(
        runtime, approving_review, approval_body, identity_seed=9403
    )

    assert cycle.run_once(root.job_id).action == "HANDOFF_CREATED"
    handoff = runtime.jobs.get_cycle_handoff(root.job_id)
    assert cycle.run_once(root.job_id).action == "DISPATCHED"
    aggregation = dispatches[-1]
    aggregation_body = {
        "schema_version": "mastermind.aggregation_result/v1",
        "root_job_id": root.job_id,
        "handoff_digest": handoff["handoff_digest"],
        "policy_sha": handoff["policy_sha"],
        "plan_attempt_id": handoff["plan_attempt_id"],
        "plan_digest": handoff["plan_digest"],
        "revisions": [
            {key: item[key] for key in {
                "ordinal",
                "plan_step_id",
                "current_job_id",
                "current_attempt_id",
                "current_result_digest",
                "repair_round",
                "review_required",
                "qualifying_review_job_id",
                "qualifying_review_attempt_id",
                "qualifying_review_result_digest",
            }}
            for item in handoff["revisions"]
        ],
        "aggregate_summary": "One bounded reviewed offline result is ready.",
        "evidence_digests": [],
    }
    aggregation_seal, _aggregation_terminal = _complete_ohf_role(
        runtime, aggregation, aggregation_body, identity_seed=9404
    )
    return (
        runtime,
        root.job_id,
        plan_digest,
        work_seal,
        reject_seal,
        repair_seal,
        approval_seal,
        aggregation_seal,
        "a" * 40,
    )


def test_canary_receipt_is_finite_deterministic_secret_safe_and_refuses_bad_input(
    tmp_path: Path,
) -> None:
    (
        runtime,
        root_id,
        plan_digest,
        work_seal,
        reject_seal,
        repair_seal,
        approval_seal,
        aggregation_seal,
        release_sha,
    ) = _offline_delivery_runtime(tmp_path / "runtime")

    first = build_receipt(
        runtime,
        root_job_id=root_id,
        expected_release_sha=release_sha,
        observed_at="2026-09-14T01:02:03Z",
    )
    second = build_receipt(
        Runtime.at(tmp_path / "runtime"),
        root_job_id=root_id,
        expected_release_sha=release_sha,
        observed_at="2026-09-14T01:02:03Z",
    )
    assert set(first) == EXPECTED_KEYS
    assert first == second
    assert RECEIPT_SCHEMA == "mastermind.web_ceo_offline_delivery_canary/v2"
    assert LEGACY_RECEIPT_SCHEMA == "mastermind.web_ceo_offline_delivery_canary/v1"
    assert first["schema"] == RECEIPT_SCHEMA
    assert first["release_sha"] == release_sha
    assert first["root_job_id"] == root_id
    assert first["plan_digest"] == plan_digest
    assert first["work_revisions"] == [
        {
            "job_id": work_seal["job_id"],
            "attempt_id": work_seal["attempt_id"],
            "result_digest": work_seal["role_result_digest"],
        }
    ]
    assert first["review_revisions"] == [
        {
            "job_id": reject_seal["job_id"],
            "attempt_id": reject_seal["attempt_id"],
            "result_digest": reject_seal["role_result_digest"],
            "verdict": "reject",
        },
        {
            "job_id": approval_seal["job_id"],
            "attempt_id": approval_seal["attempt_id"],
            "result_digest": approval_seal["role_result_digest"],
            "verdict": "approve",
        },
    ]
    assert first["repair_revisions"] == [
        {
            "job_id": repair_seal["job_id"],
            "attempt_id": repair_seal["attempt_id"],
            "result_digest": repair_seal["role_result_digest"],
        }
    ]
    assert first["aggregation_result_digest"] == (
        aggregation_seal["role_result_digest"]
    )
    assert first["web_sol_turns_between_admission_and_handoff"] is None
    assert first["manual_continue_edges"] is None
    assert first["intervention_measurements"] == {
        "web_sol_turns_between_admission_and_handoff": {
            "state": "UNMEASURED",
            "reason": "CANONICAL_EVENT_SOURCE_ABSENT",
            "interval_start": None,
            "interval_end": None,
        },
        "manual_continue_edges": {
            "state": "UNMEASURED",
            "reason": "CANONICAL_EVENT_SOURCE_ABSENT",
            "interval_start": None,
            "interval_end": None,
        },
    }
    assert first["terminal_return_projection_state"] == "NOT_ATTEMPTED"
    assert first["wake_obligation_state"] == "NOT_REQUESTED"
    assert first["wake_acknowledgement_mode"] is None
    assert first["semantic_parent_action_state"] == "NOT_OBSERVED"
    assert first["production_acceptance_state"] == "PENDING"
    assert first["stage_promotion_eligible"] is False
    assert first["proof_admissibility"] == {
        "scope": "SOURCE_LINEAGE_ONLY",
        "stage_promotion": "HOLD",
        "legacy_v1": "NON_PROMOTABLE",
    }
    assert first["effect_uncertainty"] == "NONE"
    assert first["source_evidence"] == {
        "aggregation_terminal": "RUNTIME_VALIDATED",
        "independent_review": "QUALIFIED",
        "terminal_projection": "NOT_ATTEMPTED",
        "wake_obligation": "NOT_REQUESTED",
        "semantic_parent_action": "NOT_OBSERVED",
        "intervention_measurements": "UNMEASURED",
    }
    assert first["observed_at"] == "2026-09-14T01:02:03Z"
    rendered = json.dumps(first, sort_keys=True, separators=(",", ":"))
    for forbidden in ("provider", "prompt", "cookie", "token", "secret", "account"):
        assert forbidden not in rendered.lower()

    with pytest.raises(ValueError, match="ROOT_NOT_FOUND"):
        build_receipt(runtime, root_job_id="JOB-999", expected_release_sha=release_sha)
    with pytest.raises(ValueError, match="EXPECTED_RELEASE_MISMATCH"):
        build_receipt(runtime, root_job_id=root_id, expected_release_sha="b" * 40)


def _append_terminal_phase(
    runtime: Runtime,
    root_id: str,
    *,
    final_phase: str,
    duplicate_applied: bool = False,
):
    root = runtime.jobs.get_job(root_id)
    assert root is not None and root.current_attempt_id is not None
    material = runtime.validated_role_completion(
        root_id, expected_attempt_id=root.current_attempt_id
    )
    candidate = reduce_terminal_return(material=material)
    command_base, event_material = terminal_return_event_material(candidate)
    by_phase = {
        phase_name: (event_type, command_id)
        for phase_name, event_type, command_id in terminal_return_phase_spec(
            command_base
        )
    }
    sequences = {
        "PREPARED": ("PREPARED",),
        "PRE_SUBMIT_REFUSED": ("PREPARED", "PRE_SUBMIT_REFUSED"),
        "ATTEMPTED": ("PREPARED", "ATTEMPTED"),
        "PROVEN_NO_EFFECT": ("PREPARED", "ATTEMPTED", "PROVEN_NO_EFFECT"),
        "EFFECT_UNKNOWN": ("PREPARED", "ATTEMPTED", "EFFECT_UNKNOWN"),
        "APPLIED": ("PREPARED", "ATTEMPTED", "APPLIED"),
    }
    projection_receipt = {
        "action": "POSTED",
        "message_key": candidate.message_key,
        "fingerprint": "b" * 64,
        "message_ts": "1787961600.000002",
        "duplicate_timestamps": [],
        "thread_ts": "1787961600.000001",
        "parent_author_user_id": "U0123456789",
        "parent_fingerprint": "e" * 64,
    }
    with runtime.store.transaction() as connection:
        for phase in sequences[final_phase]:
            event_type, command_id = by_phase[phase]
            payload = dict(event_material)
            if phase == "APPLIED":
                payload["projection_receipt"] = projection_receipt
            runtime.store.append_event(
                connection,
                aggregate_type="terminal_return_projection",
                aggregate_id=candidate.attempt_id,
                event_type=event_type,
                actor="executive-control-service",
                job_id=candidate.job_id,
                attempt_id=candidate.attempt_id,
                worker_id=candidate.worker_id,
                payload=payload,
                command_id=command_id,
            )
        if duplicate_applied:
            event_type, command_id = by_phase["APPLIED"]
            runtime.store.append_event(
                connection,
                aggregate_type="terminal_return_projection",
                aggregate_id=candidate.attempt_id,
                event_type=event_type,
                actor="executive-control-service",
                job_id=candidate.job_id,
                attempt_id=candidate.attempt_id,
                worker_id=candidate.worker_id,
                payload={**event_material, "projection_receipt": projection_receipt},
                command_id=f"{command_id}:duplicate",
            )
    return candidate, projection_receipt


def test_canary_rejects_unresolved_terminal_effect_unknown(tmp_path: Path) -> None:
    runtime, root_id, *_args, release_sha = _offline_delivery_runtime(
        tmp_path / "runtime"
    )
    _append_terminal_phase(runtime, root_id, final_phase="EFFECT_UNKNOWN")

    with pytest.raises(ValueError, match="EFFECT_UNKNOWN_UNRESOLVED"):
        build_receipt(
            runtime,
            root_job_id=root_id,
            expected_release_sha=release_sha,
            observed_at="2026-09-14T01:02:03Z",
        )


def test_canary_rejects_attempted_terminal_projection_as_unresolved_effect(
    tmp_path: Path,
) -> None:
    runtime, root_id, *_args, release_sha = _offline_delivery_runtime(
        tmp_path / "runtime"
    )
    _append_terminal_phase(runtime, root_id, final_phase="ATTEMPTED")
    with pytest.raises(ValueError, match="EFFECT_UNKNOWN_UNRESOLVED"):
        build_receipt(
            runtime,
            root_job_id=root_id,
            expected_release_sha=release_sha,
            observed_at="2026-09-14T01:02:03Z",
        )


@pytest.mark.parametrize(
    "phase",
    ("PREPARED", "PRE_SUBMIT_REFUSED", "PROVEN_NO_EFFECT"),
)
def test_canary_reports_exact_known_terminal_projection_phase(
    tmp_path: Path,
    phase: str,
) -> None:
    runtime, root_id, *_args, release_sha = _offline_delivery_runtime(
        tmp_path / "runtime"
    )
    _append_terminal_phase(runtime, root_id, final_phase=phase)
    receipt = build_receipt(
        runtime,
        root_job_id=root_id,
        expected_release_sha=release_sha,
        observed_at="2026-09-14T01:02:03Z",
    )
    assert receipt["terminal_return_projection_state"] == phase
    assert receipt["effect_uncertainty"] == "NONE"


def test_canary_rejects_malformed_terminal_projection_family(tmp_path: Path) -> None:
    runtime, root_id, *_args, release_sha = _offline_delivery_runtime(
        tmp_path / "runtime"
    )
    root = runtime.jobs.get_job(root_id)
    assert root is not None and root.current_attempt_id is not None
    material = runtime.validated_role_completion(
        root_id, expected_attempt_id=root.current_attempt_id
    )
    with runtime.store.transaction() as connection:
        runtime.store.append_event(
            connection,
            aggregate_type="terminal_return_projection",
            aggregate_id=material.attempt.attempt_id,
            event_type="EXECUTIVE_TERMINAL_RETURN_APPLIED",
            attempt_id=material.attempt.attempt_id,
        )
    with pytest.raises(ValueError, match="TERMINAL_PROJECTION_INVALID"):
        build_receipt(
            runtime,
            root_job_id=root_id,
            expected_release_sha=release_sha,
            observed_at="2026-09-14T01:02:03Z",
        )


def test_canary_rejects_ambiguous_terminal_projection(tmp_path: Path) -> None:
    runtime, root_id, *_args, release_sha = _offline_delivery_runtime(
        tmp_path / "runtime"
    )
    _append_terminal_phase(
        runtime, root_id, final_phase="APPLIED", duplicate_applied=True
    )

    with pytest.raises(ValueError, match="TERMINAL_PROJECTION_AMBIGUOUS"):
        build_receipt(
            runtime,
            root_job_id=root_id,
            expected_release_sha=release_sha,
            observed_at="2026-09-14T01:02:03Z",
        )


def test_canary_rejects_incomplete_non_current_or_incomplete_child_lineage(
    tmp_path: Path,
) -> None:
    runtime, root_id, *_args, release_sha = _offline_delivery_runtime(
        tmp_path / "runtime"
    )
    child = next(
        job
        for job in runtime.jobs.list_jobs()
        if job.root_job_id == root_id
        and job.orchestration_role == "work"
        and job.status is JobStatus.COMPLETED
    )
    with runtime.store.transaction() as connection:
        connection.execute(
            "UPDATE jobs SET status='QUEUED',current_attempt_id=NULL,"
            "assigned_worker_id=NULL,assigned_quota_class=NULL WHERE job_id=?",
            (child.job_id,),
        )

    with pytest.raises(ValueError, match="CHILD_LINEAGE_INCOMPLETE"):
        build_receipt(
            runtime,
            root_job_id=root_id,
            expected_release_sha=release_sha,
            observed_at="2026-09-14T01:02:03Z",
        )


def test_canary_rejects_non_current_child_attempt(tmp_path: Path) -> None:
    runtime, root_id, *_args, release_sha = _offline_delivery_runtime(
        tmp_path / "runtime"
    )
    child = next(
        job
        for job in runtime.jobs.list_jobs()
        if job.root_job_id == root_id
        and job.orchestration_role == "work"
    )
    with runtime.store.transaction() as connection:
        row = dict(
            connection.execute(
                "SELECT * FROM jobs WHERE job_id=?", (child.job_id,)
            ).fetchone()
        )
        row["job_id"] = "JOB-996"
        row["plan_step_id"] = "step-non-current-attempt"
        row["current_attempt_id"] = None
        row["assigned_worker_id"] = None
        row["assigned_quota_class"] = None
        row["status"] = "QUEUED"
        row["attempt_count"] = 2
        provenance = dict(json.loads(row["orchestration_provenance_json"]))
        provenance["job_id"] = row["job_id"]
        row["orchestration_provenance_json"] = json.dumps(
            provenance, sort_keys=True, separators=(",", ":")
        )
        row["orchestration_provenance_digest"] = digest(provenance)
        columns = ",".join("?" for _ in row)
        connection.execute(
            f"INSERT INTO jobs({','.join(row)}) VALUES ({columns})",
            tuple(row.values()),
        )

    with pytest.raises(ValueError, match="REVISION_CURRENT_AMBIGUOUS"):
        build_receipt(
            runtime,
            root_job_id=root_id,
            expected_release_sha=release_sha,
            observed_at="2026-09-14T01:02:03Z",
        )


def test_canary_rejects_non_completed_child_attempt(tmp_path: Path) -> None:
    runtime, root_id, *_args, release_sha = _offline_delivery_runtime(
        tmp_path / "runtime"
    )
    child = next(
        job
        for job in runtime.jobs.list_jobs()
        if job.root_job_id == root_id
        and job.orchestration_role == "work"
    )
    with runtime.store.transaction() as connection:
        connection.execute(
            "UPDATE jobs SET status='QUEUED',current_attempt_id=NULL,"
            "assigned_worker_id=NULL,assigned_quota_class=NULL WHERE job_id=?",
            (child.job_id,),
        )

    with pytest.raises(ValueError, match="CHILD_LINEAGE_INCOMPLETE"):
        build_receipt(
            runtime,
            root_job_id=root_id,
            expected_release_sha=release_sha,
            observed_at="2026-09-14T01:02:03Z",
        )


def _revision_job(runtime: Runtime, root_id: str, role: str) -> object:
    return next(
        job
        for job in runtime.jobs.list_jobs()
        if job.root_job_id == root_id and job.orchestration_role == role
    )


def test_canary_rejects_duplicate_current_revision(tmp_path: Path) -> None:
    runtime, root_id, *_args, release_sha = _offline_delivery_runtime(
        tmp_path / "runtime"
    )
    work = _revision_job(runtime, root_id, "work")
    with runtime.store.transaction() as connection:
        row = dict(
            connection.execute(
                "SELECT * FROM jobs WHERE job_id=?", (work.job_id,)
            ).fetchone()
        )
        row["job_id"] = "JOB-999"
        row["plan_step_id"] = "step-duplicate-current"
        provenance = dict(json.loads(row["orchestration_provenance_json"]))
        provenance["job_id"] = row["job_id"]
        row["orchestration_provenance_json"] = json.dumps(
            provenance, sort_keys=True, separators=(",", ":")
        )
        row["orchestration_provenance_digest"] = digest(provenance)
        row["current_attempt_id"] = None
        row["assigned_worker_id"] = None
        row["assigned_quota_class"] = None
        row["status"] = "QUEUED"
        columns = ",".join("?" for _ in row)
        connection.execute(
            f"INSERT INTO jobs({','.join(row)}) VALUES ({columns})",
            tuple(row.values()),
        )

    with pytest.raises(ValueError, match="CHILD_LINEAGE_INCOMPLETE"):
        build_receipt(
            runtime,
            root_job_id=root_id,
            expected_release_sha=release_sha,
            observed_at="2026-09-14T01:02:03Z",
        )


def test_canary_rejects_non_current_repair_revision(tmp_path: Path) -> None:
    runtime, root_id, *_args, release_sha = _offline_delivery_runtime(
        tmp_path / "runtime"
    )
    repair = _revision_job(runtime, root_id, "repair")
    assert repair.supersedes_job_id is not None
    prior = runtime.jobs.get_job(str(repair.supersedes_job_id))
    assert prior is not None and prior.current_attempt_id is not None
    with runtime.store.transaction() as connection:
        row = dict(
            connection.execute(
                "SELECT * FROM jobs WHERE job_id=?", (repair.job_id,)
            ).fetchone()
        )
        row["job_id"] = "JOB-998"
        provenance = dict(json.loads(row["orchestration_provenance_json"]))
        provenance["job_id"] = row["job_id"]
        row["orchestration_provenance_json"] = json.dumps(
            provenance, sort_keys=True, separators=(",", ":")
        )
        row["orchestration_provenance_digest"] = digest(provenance)
        row["supersedes_job_id"] = repair.job_id
        row["repair_round"] = 2
        row["plan_step_id"] = "step-non-current-repair"
        row["current_attempt_id"] = None
        row["assigned_worker_id"] = None
        row["assigned_quota_class"] = None
        row["status"] = "QUEUED"
        columns = ",".join("?" for _ in row)
        connection.execute(
            f"INSERT INTO jobs({','.join(row)}) VALUES ({columns})",
            tuple(row.values()),
        )

    with pytest.raises(ValueError, match="REVISION_NOT_CURRENT"):
        build_receipt(
            runtime,
            root_job_id=root_id,
            expected_release_sha=release_sha,
            observed_at="2026-09-14T01:02:03Z",
        )


def test_canary_rejects_review_sequence_that_does_not_qualify_current_repair(
    tmp_path: Path,
) -> None:
    runtime, root_id, *_args, release_sha = _offline_delivery_runtime(
        tmp_path / "runtime"
    )
    reviews = [
        job
        for job in runtime.jobs.list_jobs()
        if job.root_job_id == root_id and job.orchestration_role == "review"
    ]
    approving_review = reviews[-1]
    assert approving_review.current_attempt_id is not None
    with runtime.store.transaction() as connection:
        row = dict(
            connection.execute(
                "SELECT * FROM jobs WHERE job_id=?", (approving_review.job_id,)
            ).fetchone()
        )
        row["job_id"] = "JOB-997"
        row["reviews_job_id"] = _revision_job(runtime, root_id, "plan").job_id
        provenance = dict(json.loads(row["orchestration_provenance_json"]))
        provenance["job_id"] = row["job_id"]
        row["orchestration_provenance_json"] = json.dumps(
            provenance, sort_keys=True, separators=(",", ":")
        )
        row["orchestration_provenance_digest"] = digest(provenance)
        row["current_attempt_id"] = None
        row["assigned_worker_id"] = None
        row["assigned_quota_class"] = None
        row["status"] = "QUEUED"
        columns = ",".join("?" for _ in row)
        connection.execute(
            f"INSERT INTO jobs({','.join(row)}) VALUES ({columns})",
            tuple(row.values()),
        )

    with pytest.raises(ValueError, match="INDEPENDENT_REVIEW_INCOMPLETE"):
        build_receipt(
            runtime,
            root_job_id=root_id,
            expected_release_sha=release_sha,
            observed_at="2026-09-14T01:02:03Z",
        )




def _append_terminal_applied(runtime: Runtime, root_id: str):
    return _append_terminal_phase(runtime, root_id, final_phase="APPLIED")


def _terminal_projection_evidence_digest(
    runtime: Runtime,
    candidate,
    projection_receipt: dict,
) -> str:
    receipt = TerminalProjectionReceiptFacts(
        **{
            **projection_receipt,
            "duplicate_timestamps": tuple(
                projection_receipt["duplicate_timestamps"]
            ),
        }
    )
    canonical_candidate = CanonicalTerminalWakeCandidate(
        root_job_id=candidate.root_job_id,
        job_id=candidate.job_id,
        attempt_id=candidate.attempt_id,
        worker_id=candidate.worker_id,
    )

    def facts_provider(_runtime, requested, _connection):
        assert requested == canonical_candidate
        return DialogueObservationFacts(
            terminal=(
                TerminalObservationFacts(
                    candidate=candidate,
                    projection_receipt=receipt,
                    projection_effect="APPLIED",
                    binding_revalidated=True,
                ),
            )
        )

    canonical = read_canonical_terminal_wake(
        runtime=runtime,
        source_root_job_id=candidate.root_job_id,
        candidate=canonical_candidate,
        facts_provider=facts_provider,
    )
    assert canonical.terminal is not None
    assert canonical.terminal_applied is True
    return canonical.terminal.evidence_digest

def _append_matching_wake(
    runtime: Runtime,
    root_id: str,
    *,
    source_hex: str = "f",
    final_phase: LedgerPhase,
    ack_mode: AckMode = AckMode.REASONING_SESSION,
    physical_source_mode: str = "exact",
    extra_history_events: int = 0,
) -> None:
    root = runtime.jobs.get_job(root_id)
    assert root is not None and root.current_attempt_id is not None
    material = runtime.validated_role_completion(
        root_id, expected_attempt_id=root.current_attempt_id
    )
    candidate = reduce_terminal_return(material=material)
    command_base, _event_material = terminal_return_event_material(candidate)
    applied_command = terminal_return_phase_spec(command_base)[-1][2]
    applied = runtime.events.get_event_by_command_id(applied_command)
    if applied is None:
        raise AssertionError("terminal APPLIED fixture is required before Wake")
    projection_receipt = dict(applied.payload["projection_receipt"])
    evidence_digest = _terminal_projection_evidence_digest(
        runtime, candidate, projection_receipt
    )
    physical_candidate = {
        "mode": "TERMINAL_RESULT",
        "root_job_id": candidate.root_job_id,
        "job_id": candidate.job_id,
        "attempt_id": candidate.attempt_id,
        "worker_id": candidate.worker_id,
        "evidence_digest": (
            "9" * 64
            if physical_source_mode == "wrong_evidence"
            else evidence_digest
        ),
    }
    parent_fingerprint = projection_receipt["parent_fingerprint"]
    predecessor_key = candidate.message_key
    predecessor_fingerprint = (
        "8" * 64
        if physical_source_mode == "wrong_fingerprint"
        else projection_receipt["fingerprint"]
    )
    target_seat = "coo" if physical_source_mode == "wrong_target" else "ceo"
    attention = attention_source_ref(
        parent_fingerprint=parent_fingerprint,
        message_key=predecessor_key,
        target_seat=target_seat,
    )
    logical_source_ref = correlated_source_ref(
        attention_source_ref=attention,
        parent_fingerprint=parent_fingerprint,
        operation_key=candidate.operation_key,
        candidate=physical_candidate,
    )
    obligation = mint_obligation(
        wake_kind="dialogue_turn_pending",
        source_kind="agent_dialogue_attention",
        source_ref=(
            "agent_dialogue_attention:" + source_hex * 64
            if physical_source_mode == "foreign_obligation"
            else logical_source_ref
        ),
        declared_target_seat=target_seat,
        job_id=root_id,
        attempt_id=material.attempt.attempt_id,
        root_job_id=root_id,
        source_workstream=str(candidate.dialogue_source.work_ref),
        source_created_at="2026-09-14T00:00:01Z",
        emitted_at="2026-09-14T00:00:02Z",
    )
    physical_source = None
    if physical_source_mode not in {"missing", "foreign_obligation"}:
        physical_source = PhysicalDialogueSourceIdentity.create(
            logical_source_ref=logical_source_ref,
            obligation_id=obligation.obligation_id,
            observation=DialogueSourceObservation(
                workspace_id="T0123456789",
                channel_id="C0123456789",
                thread_ts=(
                    "1787961600.999999"
                    if physical_source_mode == "wrong_thread"
                    else projection_receipt["thread_ts"]
                ),
                predecessor_message_key=predecessor_key,
                predecessor_message_fingerprint=predecessor_fingerprint,
            ),
            parent_fingerprint=parent_fingerprint,
            operation_key=candidate.operation_key,
            target_seat=target_seat,
            candidate=physical_candidate,
        )
    repo = WakeLedgerRepository(runtime)
    repo.append_record(
        requested_record(obligation, physical_source=physical_source),
        obligation=obligation,
    )
    if extra_history_events:
        with runtime.store.transaction() as connection:
            for index in range(extra_history_events):
                runtime.store.append_event(
                    connection,
                    aggregate_type="wake",
                    aggregate_id=obligation.obligation_id,
                    event_type="fixture-extra",
                    actor="fixture",
                    payload={"index": index},
                    command_id=f"fixture-extra:{obligation.obligation_id}:{index}",
                )
    if final_phase is LedgerPhase.WAKE_REQUESTED:
        return
    delivery = DeliveryAttempt(
        obligation_id=obligation.obligation_id,
        attempt_n=1,
        attempt_command_id=ledger_command_id(
            obligation.obligation_id, LedgerPhase.DELIVERY_ATTEMPT, attempt_n=1
        ),
        destination_digest="d" * 64,
        route_digest="e" * 64,
        binding_id="bind-canary-ceo-01",
        binding_generation=1,
        session_alias="EXECUTIVE-CEO-A",
        reasoning_surface="codex",
        wake_transport="codex-app-server",
    )
    repo.append_record(attempt_record(delivery, LedgerPhase.DELIVERY_ATTEMPT))
    if final_phase is LedgerPhase.DELIVERY_ATTEMPT:
        return
    repo.append_record(attempt_record(delivery, LedgerPhase.DELIVERED))
    if final_phase is LedgerPhase.DELIVERED:
        return
    trusted = TrustedAckContext(
        ack_mode=ack_mode,
        target_seat="ceo",
        session_alias="EXECUTIVE-CEO-A",
        reasoning_surface="codex",
        binding_id="bind-canary-ceo-01" if ack_mode is AckMode.REASONING_SESSION else None,
        binding_generation=1 if ack_mode is AckMode.REASONING_SESSION else None,
        acknowledged_at="2026-09-14T00:00:03Z",
        operator_authority_receipt=(
            None if ack_mode is AckMode.REASONING_SESSION else "operator-receipt-001"
        ),
    )
    ack = acknowledge(
        obligation,
        trusted=trusted,
        claimed_obligation_ids=(obligation.obligation_id,),
        delivered_command_id=(
            ledger_command_id(
                obligation.obligation_id, LedgerPhase.DELIVERED, attempt_n=1
            )
            if ack_mode is AckMode.REASONING_SESSION
            else None
        ),
    )
    repo.append_record(ack_record(obligation, ack))
    if final_phase is LedgerPhase.TARGET_ACKNOWLEDGED:
        return
    resolution = resolve_source(
        obligation,
        code=SourceResolutionCode.DIALOGUE_ATTENTION_ABSENT,
        health=SourceReadHealth.HEALTHY,
        source_present=False,
        snapshot_digest="a" * 64,
        resolved_at="2026-09-14T00:00:04Z",
    )
    repo.append_record(resolved_record(obligation, resolution))


def test_v2_receipt_reports_applied_terminal_without_correlated_wake(
    tmp_path: Path,
) -> None:
    runtime, root_id, *_args, release_sha = _offline_delivery_runtime(
        tmp_path / "runtime", with_dialogue_source=True
    )
    _append_terminal_applied(runtime, root_id)
    receipt = build_receipt(
        runtime,
        root_job_id=root_id,
        expected_release_sha=release_sha,
        observed_at="2026-09-14T01:02:03Z",
    )
    assert receipt["terminal_return_projection_state"] == "APPLIED"
    assert receipt["wake_obligation_state"] == "NOT_REQUESTED"
    assert receipt["wake_acknowledgement_mode"] is None
    assert receipt["semantic_parent_action_state"] == "NOT_OBSERVED"
    assert receipt["production_acceptance_state"] == "PENDING"
    assert receipt["stage_promotion_eligible"] is False


def test_v2_receipt_rejects_applied_terminal_without_dialogue_provenance(
    tmp_path: Path,
) -> None:
    runtime, root_id, *_args, release_sha = _offline_delivery_runtime(
        tmp_path / "runtime"
    )
    _append_terminal_applied(runtime, root_id)
    with pytest.raises(ValueError, match="WAKE_CORRELATION_UNAVAILABLE"):
        build_receipt(
            runtime,
            root_job_id=root_id,
            expected_release_sha=release_sha,
            observed_at="2026-09-14T01:02:03Z",
        )


@pytest.mark.parametrize(
    ("physical_source_mode", "error"),
    (
        ("missing", "WAKE_PHYSICAL_SOURCE_INVALID"),
        ("wrong_evidence", "WAKE_PHYSICAL_SOURCE_INVALID"),
        ("wrong_thread", "WAKE_PHYSICAL_SOURCE_INVALID"),
        ("wrong_fingerprint", "WAKE_PHYSICAL_SOURCE_INVALID"),
        ("wrong_target", "WAKE_PHYSICAL_SOURCE_INVALID"),
    ),
)
def test_v2_receipt_rejects_unbound_physical_wake_source(
    tmp_path: Path,
    physical_source_mode: str,
    error: str,
) -> None:
    runtime, root_id, *_args, release_sha = _offline_delivery_runtime(
        tmp_path / "runtime", with_dialogue_source=True
    )
    _append_terminal_applied(runtime, root_id)
    _append_matching_wake(
        runtime,
        root_id,
        final_phase=LedgerPhase.WAKE_REQUESTED,
        physical_source_mode=physical_source_mode,
    )
    with pytest.raises(ValueError, match=error):
        build_receipt(
            runtime,
            root_job_id=root_id,
            expected_release_sha=release_sha,
            observed_at="2026-09-14T01:02:03Z",
        )


def test_v2_receipt_rejects_wake_history_over_canonical_budget(
    tmp_path: Path,
) -> None:
    runtime, root_id, *_args, release_sha = _offline_delivery_runtime(
        tmp_path / "runtime", with_dialogue_source=True
    )
    _append_terminal_applied(runtime, root_id)
    _append_matching_wake(
        runtime,
        root_id,
        final_phase=LedgerPhase.WAKE_REQUESTED,
        extra_history_events=CANONICAL_WAKE_EVENT_BUDGET,
    )
    with pytest.raises(ValueError, match="WAKE_EVENT_BUDGET_EXCEEDED"):
        build_receipt(
            runtime,
            root_job_id=root_id,
            expected_release_sha=release_sha,
            observed_at="2026-09-14T01:02:03Z",
        )


def test_v2_reader_uses_exact_event_scopes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime, root_id, *_args, release_sha = _offline_delivery_runtime(
        tmp_path / "runtime", with_dialogue_source=True
    )
    root = runtime.jobs.get_job(root_id)
    assert root is not None and root.current_attempt_id is not None
    original = runtime.events.list_events
    calls: list[dict[str, str]] = []

    def recording_list_events(**kwargs):
        calls.append(dict(kwargs))
        return original(**kwargs)

    monkeypatch.setattr(runtime.events, "list_events", recording_list_events)
    receipt = build_receipt(
        runtime,
        root_job_id=root_id,
        expected_release_sha=release_sha,
        observed_at="2026-09-14T01:02:03Z",
    )

    assert receipt["root_job_id"] == root_id
    assert {
        "job_id": root_id,
        "aggregate_type": "job",
        "aggregate_id": root_id,
    } in calls
    assert not any(call.get("aggregate_type") == "wake" for call in calls)


def test_v2_receipt_keeps_read_time_out_of_unmeasured_intervals(tmp_path: Path) -> None:
    runtime, root_id, *_args, release_sha = _offline_delivery_runtime(
        tmp_path / "runtime", with_dialogue_source=True
    )
    first = build_receipt(
        runtime,
        root_job_id=root_id,
        expected_release_sha=release_sha,
        observed_at="2026-09-14T01:02:03Z",
    )
    later = build_receipt(
        runtime,
        root_job_id=root_id,
        expected_release_sha=release_sha,
        observed_at="2026-09-14T02:03:04Z",
    )
    assert first["observed_at"] != later["observed_at"]
    assert first["intervention_measurements"] == later["intervention_measurements"]
    assert all(
        metric["interval_start"] is None and metric["interval_end"] is None
        for metric in first["intervention_measurements"].values()
    )


@pytest.mark.parametrize(
    ("final_phase", "expected_state", "expected_ack_mode"),
    [
        (LedgerPhase.DELIVERED, "DELIVERED", None),
        (LedgerPhase.TARGET_ACKNOWLEDGED, "TARGET_ACKNOWLEDGED", "reasoning_session"),
        (LedgerPhase.SOURCE_RESOLVED, "SOURCE_RESOLVED", "reasoning_session"),
    ],
)
def test_v2_receipt_separates_wake_phase_from_semantic_and_production_acceptance(
    tmp_path: Path,
    final_phase: LedgerPhase,
    expected_state: str,
    expected_ack_mode: str | None,
) -> None:
    runtime, root_id, *_args, release_sha = _offline_delivery_runtime(
        tmp_path / "runtime", with_dialogue_source=True
    )
    _append_terminal_applied(runtime, root_id)
    _append_matching_wake(runtime, root_id, final_phase=final_phase)

    receipt = build_receipt(
        runtime,
        root_job_id=root_id,
        expected_release_sha=release_sha,
        observed_at="2026-09-14T01:02:03Z",
    )

    assert receipt["terminal_return_projection_state"] == "APPLIED"
    assert receipt["wake_obligation_state"] == expected_state
    assert receipt["wake_acknowledgement_mode"] == expected_ack_mode
    assert receipt["semantic_parent_action_state"] == "NOT_OBSERVED"
    assert receipt["production_acceptance_state"] == "PENDING"
    assert receipt["stage_promotion_eligible"] is False
    assert "parent_consumption_state" not in receipt


def test_v2_receipt_preserves_human_ack_mode_without_claiming_sol_action(
    tmp_path: Path,
) -> None:
    runtime, root_id, *_args, release_sha = _offline_delivery_runtime(
        tmp_path / "runtime", with_dialogue_source=True
    )
    _append_terminal_applied(runtime, root_id)
    _append_matching_wake(
        runtime,
        root_id,
        final_phase=LedgerPhase.TARGET_ACKNOWLEDGED,
        ack_mode=AckMode.HUMAN_OPERATOR,
    )
    receipt = build_receipt(
        runtime,
        root_job_id=root_id,
        expected_release_sha=release_sha,
        observed_at="2026-09-14T01:02:03Z",
    )
    assert receipt["wake_obligation_state"] == "TARGET_ACKNOWLEDGED"
    assert receipt["wake_acknowledgement_mode"] == "human_operator"
    assert receipt["semantic_parent_action_state"] == "NOT_OBSERVED"


def test_v2_receipt_reports_requested_wake_without_claiming_delivery(
    tmp_path: Path,
) -> None:
    runtime, root_id, *_args, release_sha = _offline_delivery_runtime(
        tmp_path / "runtime", with_dialogue_source=True
    )
    _append_terminal_applied(runtime, root_id)
    _append_matching_wake(
        runtime, root_id, final_phase=LedgerPhase.WAKE_REQUESTED
    )
    receipt = build_receipt(
        runtime,
        root_job_id=root_id,
        expected_release_sha=release_sha,
        observed_at="2026-09-14T01:02:03Z",
    )
    assert receipt["wake_obligation_state"] == "WAKE_REQUESTED"
    assert receipt["wake_acknowledgement_mode"] is None
    assert receipt["semantic_parent_action_state"] == "NOT_OBSERVED"
    assert receipt["effect_uncertainty"] == "NONE"


def test_v2_receipt_rejects_unresolved_wake_delivery_effect(tmp_path: Path) -> None:
    runtime, root_id, *_args, release_sha = _offline_delivery_runtime(
        tmp_path / "runtime", with_dialogue_source=True
    )
    _append_terminal_applied(runtime, root_id)
    _append_matching_wake(
        runtime, root_id, final_phase=LedgerPhase.DELIVERY_ATTEMPT
    )
    with pytest.raises(ValueError, match="EFFECT_UNKNOWN_UNRESOLVED"):
        build_receipt(
            runtime,
            root_job_id=root_id,
            expected_release_sha=release_sha,
            observed_at="2026-09-14T01:02:03Z",
        )


def test_v2_receipt_rejects_multiple_matching_wake_obligations(tmp_path: Path) -> None:
    runtime, root_id, *_args, release_sha = _offline_delivery_runtime(
        tmp_path / "runtime", with_dialogue_source=True
    )
    _append_terminal_applied(runtime, root_id)
    _append_matching_wake(
        runtime,
        root_id,
        source_hex="e",
        final_phase=LedgerPhase.WAKE_REQUESTED,
        physical_source_mode="foreign_obligation",
    )
    _append_matching_wake(
        runtime,
        root_id,
        source_hex="f",
        final_phase=LedgerPhase.WAKE_REQUESTED,
        physical_source_mode="foreign_obligation",
    )
    with pytest.raises(ValueError, match="WAKE_OBLIGATION_AMBIGUOUS"):
        build_receipt(
            runtime,
            root_job_id=root_id,
            expected_release_sha=release_sha,
            observed_at="2026-09-14T01:02:03Z",
        )

def test_cli_emits_receipt_and_closed_errors(tmp_path: Path, capsys) -> None:
    fixture = _offline_delivery_runtime(tmp_path / "runtime")
    runtime, root_id, *_args, release_sha = fixture
    runtime_root = tmp_path / "runtime"
    good = main(
        [
            "--runtime-root",
            str(runtime_root),
            "--root-job-id",
            root_id,
            "--expected-release-sha",
            release_sha,
            "--observed-at",
            "2026-09-14T01:02:03Z",
        ]
    )
    assert good == 0
    payload = json.loads(capsys.readouterr().out)
    assert set(payload) == EXPECTED_KEYS

    for argv in (
        ["--runtime-root", str(runtime_root), "--root-job-id", root_id],
        [
            "--runtime-root",
            str(runtime_root),
            "--root-job-id",
            root_id,
            "--expected-release-sha",
            "not-a-sha",
        ],
        [
            "--runtime-root",
            str(runtime_root),
            "--root-job-id",
            "JOB-999",
            "--expected-release-sha",
            release_sha,
        ],
    ):
        capsys.readouterr()
        assert main(argv) == 2
        error = json.loads(capsys.readouterr().out)
        assert set(error) == {"schema", "error", "root_job_id"}
        assert error["schema"] == "mastermind.web_ceo_offline_delivery_canary.error/v1"
