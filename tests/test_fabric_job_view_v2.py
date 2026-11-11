"""G7 truth contract for mastermind.fabric_job_view.v2."""
from __future__ import annotations

import dataclasses
import json
from pathlib import Path

from control_plane import fabric_job_view
from control_plane.executive_runtime import JobPayload, Runtime


def _control(tmp_path: Path, *, armed: bool) -> Path:
    path = tmp_path / "control.json"
    path.write_text(json.dumps({
        "schema_version": "mastermind.executive_control_config/v1",
        "ceo_submit_armed": armed,
        "coo_autonomy_armed": False,
        "ceo_ingress_app_armed": False,
        "dialogue_bridge_armed": False,
        "terminal_return_armed": False,
    }))
    return path


def _completed_root(tmp_path: Path):
    root = tmp_path / "runtime"
    root.mkdir()
    runtime = Runtime.at(root)
    job = runtime.jobs.create_job(
        "root",
        provenance={
            "schema": "mastermind.ceo_intent.v1",
            "workstream": "WS:G7",
        },
    )
    runtime.workers.register_worker(
        "worker-01",
        provider="codex",
        account_label="fixture",
        worker_type="fixture",
        capabilities=["research"],
    )
    assert runtime.attempts.claim_job(job.job_id) is not None
    runtime.jobs.complete_job(
        job.job_id,
        JobPayload(
            summary="execution completed",
            next_actions=["await product acceptance"],
        ),
    )
    return root, job.job_id


def test_v1_remains_historical_while_v2_separates_acceptance(tmp_path):
    runtime_root, job_id = _completed_root(tmp_path)
    control = _control(tmp_path, armed=True)

    v1 = fabric_job_view.read_fabric_view(
        runtime_root, job_id, control_config_path=control
    )
    v2 = fabric_job_view.read_fabric_view_v2(
        runtime_root, job_id, control_config_path=control
    )

    assert v1["schema"] == "mastermind.fabric_job_view.v1"
    assert v1["root"]["result"]["state"] == "ACCEPTED"
    assert "acceptance" not in v1["root"]

    assert v2["schema"] == "mastermind.fabric_job_view.v2"
    assert v2["root"]["status"] == "COMPLETED"
    assert v2["root"]["result"]["state"] == "COMPLETED"
    assert v2["root"]["acceptance"] == {
        "state": "NOT_PROJECTED",
        "producer_owner": None,
        "reason": "product acceptance has no producer in this projection",
    }
    assert any(
        fact["missingness_class"] == "MISSING_PRODUCER"
        and fact["target_field"] == "acceptance.state"
        for fact in v2["missingness"]
    )


def test_v2_result_payload_cannot_forge_product_acceptance(tmp_path):
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()
    runtime = Runtime.at(runtime_root)
    job = runtime.jobs.create_job(
        "root",
        provenance={
            "schema": "mastermind.ceo_intent.v1",
            "workstream": "WS:G7-FORGE",
        },
    )
    runtime.workers.register_worker(
        "worker-01",
        provider="codex",
        account_label="fixture",
        worker_type="fixture",
        capabilities=["research"],
    )
    assert runtime.attempts.claim_job(job.job_id) is not None
    runtime.jobs.complete_job(
        job.job_id,
        JobPayload(
            summary="ACCEPTED_PRODUCT",
            artifacts=["accepted=true", "chairman-approved"],
        ),
    )

    doc = fabric_job_view.read_fabric_view_v2(
        runtime_root,
        job.job_id,
        control_config_path=_control(tmp_path, armed=True),
    )

    assert doc["root"]["result"]["state"] == "COMPLETED"
    assert doc["root"]["acceptance"]["state"] == "NOT_PROJECTED"
    assert doc["root"]["acceptance"]["producer_owner"] is None


def test_v2_disarm_preserves_existing_root_without_false_existential(tmp_path):
    runtime_root, job_id = _completed_root(tmp_path)

    doc = fabric_job_view.read_fabric_view_v2(
        runtime_root,
        job_id,
        control_config_path=_control(tmp_path, armed=False),
    )

    assert doc["root"]["job_id"] == job_id
    assert doc["root"]["status"] == "COMPLETED"
    assert any(
        entry
        == "ceo_submit_armed: false; new CEO submissions are unavailable through this arm"
        for entry in doc["degraded"]
    )
    assert all(
        "no Chairman-authenticated admitted job can exist yet" not in entry
        for entry in doc["degraded"]
    )

    roots = fabric_job_view.list_roots_v2(
        runtime_root,
        control_config_path=_control(tmp_path, armed=False),
    )
    assert roots["schema"] == "mastermind.fabric_job_root_list.v2"
    assert [row["job_id"] for row in roots["roots"]] == [job_id]
    assert (
        "ceo_submit_armed: false; new CEO submissions are unavailable through this arm"
        in roots["degraded"]
    )
    assert all(
        "no Chairman-authenticated admitted job can exist yet" not in entry
        for entry in roots["degraded"]
    )


def test_v2_missing_result_is_damage_not_fake_nonacceptance(tmp_path):
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()
    runtime = Runtime.at(runtime_root)
    job = runtime.jobs.create_job(
        "root",
        provenance={
            "schema": "mastermind.ceo_intent.v1",
            "workstream": "WS:G7-MISSING",
        },
    )
    runtime.workers.register_worker(
        "worker-01",
        provider="codex",
        account_label="fixture",
        worker_type="fixture",
        capabilities=["research"],
    )
    assert runtime.attempts.claim_job(job.job_id) is not None
    runtime.jobs.complete_job(job.job_id, JobPayload())
    observed = runtime.jobs.get_job(job.job_id)
    assert observed is not None
    damaged = dataclasses.replace(observed, result=None)
    attempts = runtime.attempts.list_attempts(job.job_id)
    armed = {
        "ceo_submit_armed": True,
        "coo_autonomy_armed": False,
        "ceo_ingress_app_armed": False,
        "dialogue_bridge_armed": False,
        "terminal_return_armed": False,
        "source": "control.json",
    }

    doc = fabric_job_view.compose_fabric_view_v2(
        root_job_id=job.job_id,
        root_job=damaged,
        jobs=[damaged],
        attempts_by_job={job.job_id: attempts},
        joined_job_ids={job.job_id},
        runtime_identity={
            "root": str(runtime_root),
            "db_present": True,
            "identity": None,
        },
        armed=armed,
        degraded=[],
    )

    assert doc["root"]["result"]["state"] == "COMPLETED"
    assert doc["root"]["result"]["summary"] is None
    assert doc["root"]["acceptance"]["state"] == "NOT_PROJECTED"
    reasons = [fact["reason"] for fact in doc["missingness"]]
    assert "COMPLETED job carries no result payload" in reasons
    assert all("accepted result payload" not in reason for reason in reasons)


def test_v2_approved_review_still_does_not_manufacture_acceptance(tmp_path):
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()
    runtime = Runtime.at(runtime_root)
    root = runtime.jobs.create_job(
        "root",
        provenance={
            "schema": "mastermind.ceo_intent.v1",
            "workstream": "WS:G7-REVIEW",
        },
    )
    subject = runtime.jobs.create_job(
        "subject",
        parent_job_id=root.job_id,
        provenance={
            "schema": "mastermind.ceo_intent.v1",
            "workstream": "WS:G7-REVIEW",
        },
    )
    reviewer = runtime.jobs.create_job(
        "review",
        parent_job_id=root.job_id,
        reviews_job_id=subject.job_id,
    )
    runtime.workers.register_worker(
        "worker-01",
        provider="codex",
        account_label="fixture",
        worker_type="fixture",
        capabilities=["research"],
    )
    assert runtime.attempts.claim_job(subject.job_id) is not None
    runtime.jobs.complete_job(subject.job_id, JobPayload(summary="execution done"))
    assert runtime.attempts.claim_job(reviewer.job_id) is not None
    runtime.jobs.complete_job(reviewer.job_id, JobPayload(verdict="approve"))

    # This is the pure execution/acceptance regression. Legacy v1 creation
    # events no longer grant a bounded network provenance join; the separate
    # bounded acquisition tests prove their explicit partial visibility.
    jobs = runtime.jobs.list_jobs()
    doc = fabric_job_view.compose_fabric_view_v2(
        root_job_id=root.job_id, root_job=runtime.jobs.get_job(root.job_id),
        jobs=jobs, attempts_by_job={job.job_id: runtime.attempts.list_attempts(job.job_id) for job in jobs},
        joined_job_ids={root.job_id, subject.job_id},
        runtime_identity={"root": str(runtime_root), "db_present": True, "identity": None},
        armed={"ceo_submit_armed": True}, degraded=[],
    )
    subject_card = next(
        card for card in doc["children"] if card["job_id"] == subject.job_id
    )

    assert subject_card["status"] == "COMPLETED"
    assert subject_card["review"]["verdict"] == "approve"
    assert subject_card["result"]["state"] == "COMPLETED"
    assert subject_card["acceptance"]["state"] == "NOT_PROJECTED"
    assert subject_card["acceptance"]["producer_owner"] is None
