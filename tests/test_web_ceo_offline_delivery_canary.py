from __future__ import annotations

import json
from pathlib import Path

import pytest

from control_plane.executive_runtime import Runtime
from scripts.web_ceo_offline_delivery_canary import (
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
    "parent_consumption_state",
    "production_acceptance_state",
    "effect_uncertainty",
    "source_evidence",
    "observed_at",
}


def _offline_delivery_runtime(root_path: Path):
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
    assert first["web_sol_turns_between_admission_and_handoff"] == 0
    assert first["manual_continue_edges"] == 0
    assert first["parent_consumption_state"] == "PENDING_UNCONSUMED"
    assert first["production_acceptance_state"] == "PENDING"
    assert first["effect_uncertainty"] == "NONE"
    assert first["source_evidence"] == {
        "aggregation_terminal": "RUNTIME_VALIDATED",
        "independent_review": "QUALIFIED",
        "terminal_projection": "NOT_ATTEMPTED",
        "wake_delivery": "NOT_REQUESTED",
    }
    assert first["observed_at"] == "2026-09-14T01:02:03Z"
    rendered = json.dumps(first, sort_keys=True, separators=(",", ":"))
    for forbidden in ("provider", "prompt", "cookie", "token", "secret", "account"):
        assert forbidden not in rendered.lower()

    with pytest.raises(ValueError, match="ROOT_NOT_FOUND"):
        build_receipt(runtime, root_job_id="JOB-999", expected_release_sha=release_sha)
    with pytest.raises(ValueError, match="EXPECTED_RELEASE_MISMATCH"):
        build_receipt(runtime, root_job_id=root_id, expected_release_sha="b" * 40)


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
