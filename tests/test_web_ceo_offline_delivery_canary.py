from __future__ import annotations

import json
from pathlib import Path

import pytest

from control_plane.executive_runtime import JobStatus, Runtime
from control_plane.executive_orchestration_principal import digest
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


def test_canary_rejects_unresolved_terminal_effect_unknown(tmp_path: Path) -> None:
    runtime, root_id, *_args, release_sha = _offline_delivery_runtime(
        tmp_path / "runtime"
    )
    material = runtime.validated_role_completion(
        root_id, expected_attempt_id=runtime.jobs.get_job(root_id).current_attempt_id
    )
    with runtime.store.transaction() as connection:
        runtime.store.append_event(
            connection,
            aggregate_type="terminal_return_projection",
            aggregate_id=material.attempt.attempt_id,
            event_type="EXECUTIVE_TERMINAL_RETURN_EFFECT_UNKNOWN",
            attempt_id=material.attempt.attempt_id,
        )

    with pytest.raises(ValueError, match="EFFECT_UNKNOWN_UNRESOLVED"):
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
    material = runtime.validated_role_completion(
        root_id, expected_attempt_id=runtime.jobs.get_job(root_id).current_attempt_id
    )
    for _ in range(2):
        with runtime.store.transaction() as connection:
            runtime.store.append_event(
                connection,
                aggregate_type="terminal_return_projection",
                aggregate_id=material.attempt.attempt_id,
                event_type="EXECUTIVE_TERMINAL_RETURN_APPLIED",
                attempt_id=material.attempt.attempt_id,
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


def test_cli_emits_receipt_and_closed_errors(tmp_path: Path, capsys) -> None:
    import asyncio
    import tempfile
    import threading
    from test_executive_service import _service, _config

    runtime, root_id, *_args, release_sha = _offline_delivery_runtime(tmp_path / "runtime")
    with tempfile.TemporaryDirectory(prefix="canary-control-") as directory:
        config = _config(tmp_path / "service", socket_root=Path(directory),
                         runtime_root=runtime.store.root)
        service, _ = _service(tmp_path / "service", config=config)
        loop = asyncio.new_event_loop()
        ready = threading.Event()
        errors = []
        def serve():
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(service.start())
            except BaseException as exc:
                errors.append(exc)
                ready.set()
                return
            ready.set()
            loop.run_forever()
            loop.close()
        thread = threading.Thread(target=serve)
        thread.start()
        assert ready.wait(5)
        assert not errors
        argv = ["--runtime-root", str(runtime.store.root),
                "--control-socket", str(service.socket_path),
                "--root-job-id", root_id, "--expected-release-sha", release_sha,
                "--observed-at", "2026-09-14T01:02:03Z"]
        try:
            assert main(argv) == 0
            assert set(json.loads(capsys.readouterr().out)) == EXPECTED_KEYS
            invalid = list(argv)
            invalid[invalid.index(release_sha)] = "not-a-sha"
            assert main(invalid) == 2
            assert json.loads(capsys.readouterr().out)["error"] == "INPUT_REFUSED"
            assert main(["--runtime-root", str(runtime.store.root),
                         "--root-job-id", root_id]) == 2
            assert json.loads(capsys.readouterr().out)["error"] == "INPUT_REFUSED"
        finally:
            asyncio.run_coroutine_threadsafe(service.close(), loop).result(timeout=5)
            loop.call_soon_threadsafe(loop.stop)
            thread.join(5)
