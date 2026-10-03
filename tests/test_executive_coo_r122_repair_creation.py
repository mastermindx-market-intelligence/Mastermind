"""Current-domain repair creation, immutable replay and public refusal controls.

Source proof uses genuinely enabled JSON loaded before immutable public root,
real typed hermetic plan/producer/seal/completion APIs and independent principals.
No native actor, historical migration or full provider-ledger acceptance claimed.
"""
import copy

import pytest

from control_plane.executive_orchestration_result import canonical_digest
from control_plane.executive_runtime import StateConflict, PersistenceError
from tests.test_executive_coo_hierarchy import _r7a_dispatch_cycle_work
from tests.test_executive_os_phase1fc import _complete_ohf_role
from tests.test_executive_coo_r121_role_body_projection import (
    _seeded_runtime, _inventory, _adversarial_update,
)


def _repair_command(fixture, rejected=None, review=None, review_seal=None):
    rejected = rejected or fixture["work"]
    review = review or fixture["review_job"]
    review_seal = review_seal or fixture["review_seal"]
    return (
        f"coo-cycle:{fixture['root'].job_id}:create-repair:{rejected.job_id}:"
        f"{review.job_id}:{review_seal['role_result_digest']}:{rejected.repair_round + 1}"
    )


def _create_repair(fixture, rejected=None, review=None, review_seal=None):
    rejected = rejected or fixture["work"]
    review = review or fixture["review_job"]
    return fixture["runtime"].jobs.create_cycle_repair(
        fixture["root"].job_id, rejected.job_id, review.job_id,
        command_id=_repair_command(fixture, rejected, review, review_seal),
    )


def _domain_identity(fixture):
    with fixture["runtime"].store.read() as connection:
        domain = connection.execute(
            "SELECT * FROM jobs WHERE job_id=?", (fixture["domain"].job_id,),
        ).fetchone()
        attempt = connection.execute(
            "SELECT * FROM attempts WHERE attempt_id=?", (fixture["domain_attempt_id"],),
        ).fetchone()
    return tuple(domain), tuple(attempt)


def _finish_repair_and_review(fixture, repair, *, verdict="approve", rejected=None,
                              rejecting_review=None, reject_seal=None):
    runtime, root = fixture["runtime"], fixture["root"]
    rejected = rejected or fixture["work"]
    rejecting_review = rejecting_review or fixture["review_job"]
    reject_seal = reject_seal or fixture["review_seal"]
    repair_dispatch = _r7a_dispatch_cycle_work(
        runtime, root_job_id=root.job_id, work_job_id=repair.job_id,
        worker_id="worker-r6a-work", quota_class="codex-coo",
    )
    evidence = canonical_digest({"role": "actual bounded repair producer",
                                 "job": repair.job_id, "round": repair.repair_round})
    repair_body = {
        **copy.deepcopy(fixture["work_body"]),
        "schema_version": "mastermind.repair_result/v1",
        "repair_round": repair.repair_round,
        "supersedes_job_id": rejected.job_id,
        "rejected_review_job_id": rejecting_review.job_id,
        "rejected_review_result_digest": reject_seal["role_result_digest"],
        "artifacts": [{"path": "RESULT.md", "digest": evidence}],
        "evidence_digests": [evidence],
    }
    repair_seal, _ = _complete_ohf_role(
        runtime, repair_dispatch, repair_body, identity_seed=812103 + repair.repair_round * 10,
    )
    review_job = runtime.jobs.create_cycle_review(
        root.job_id, repair.job_id,
        command_id=f"coo-cycle:{root.job_id}:create-review:{repair.job_id}:1",
    )
    review_dispatch = _r7a_dispatch_cycle_work(
        runtime, root_job_id=root.job_id, work_job_id=review_job.job_id,
        worker_id="worker-r6a-review", quota_class="codex-coo",
    )
    review_evidence = canonical_digest({"role": "independent repaired-result review",
                                        "job": review_job.job_id, "verdict": verdict})
    review_body = {
        **copy.deepcopy(fixture["review_body"]),
        "reviewed_job_id": repair.job_id,
        "reviewed_attempt_id": repair_dispatch.attempt.attempt_id,
        "reviewed_result_digest": repair_seal["role_result_digest"],
        "repair_round": repair.repair_round,
        "verdict": verdict,
        "evidence_digests": [review_evidence],
        "findings": [{"code": "REPAIRED_BODY_REVIEW",
                      "severity": "info" if verdict == "approve" else "blocking",
                      "message": "Exact independent repaired producer material",
                      "evidence_digests": [review_evidence]}],
    }
    review_seal, _ = _complete_ohf_role(
        runtime, review_dispatch, review_body, identity_seed=812104 + repair.repair_round * 10,
    )
    return locals()


def test_exact_repair_creation_replay_is_no_effect_before_and_after_completion(tmp_path, monkeypatch):
    f = _seeded_runtime(tmp_path, monkeypatch, verdict="reject")
    domain_before = _domain_identity(f)
    repair = _create_repair(f)
    assert repair.parent_job_id == f["domain"].job_id
    assert repair.depth == 2 and repair.constraints["remaining_depth"] == 0
    assert repair.repair_round == 1 and repair.supersedes_job_id == f["work"].job_id
    before = _inventory(f["runtime"])
    assert _create_repair(f).job_id == repair.job_id
    assert _inventory(f["runtime"]) == before
    _finish_repair_and_review(f, repair)
    before = _inventory(f["runtime"])
    assert _create_repair(f).job_id == repair.job_id
    assert _inventory(f["runtime"]) == before
    assert _domain_identity(f) == domain_before


@pytest.mark.parametrize("corruption", ["wrong-command", "foreign-review", "same-principal", "wrong-review-target", "foreign-predecessor-parent", "foreign-review-parent"])
def test_invalid_repair_request_refuses_without_any_durable_change(tmp_path, monkeypatch, corruption):
    f = _seeded_runtime(tmp_path, monkeypatch, verdict="reject")
    runtime, root, work, review = f["runtime"], f["root"], f["work"], f["review_job"]
    command = _repair_command(f)
    review_id = review.job_id
    if corruption == "wrong-command":
        command += ":fork"
    elif corruption == "foreign-review":
        review_id = "absent-foreign-review"
    elif corruption == "same-principal":
        # Negative-only corruption: genuine sealed independent review then a
        # forged work principal. Restore original trigger definitions.
        _adversarial_update(runtime, "attempts",
                            "UPDATE attempts SET worker_id=? WHERE attempt_id=?",
                            ("worker-r6a-work", f["review_dispatch"].attempt.attempt_id))
    elif corruption == "foreign-predecessor-parent":
        _adversarial_update(runtime, "jobs", "UPDATE jobs SET parent_job_id=? WHERE job_id=?",
                            ("foreign-domain", work.job_id))
    elif corruption == "foreign-review-parent":
        _adversarial_update(runtime, "jobs", "UPDATE jobs SET parent_job_id=? WHERE job_id=?",
                            ("foreign-domain", review.job_id))
    else:
        _adversarial_update(runtime, "jobs",
                            "UPDATE jobs SET reviews_job_id=? WHERE job_id=?",
                            ("absent-foreign-work", review.job_id))
    before = _inventory(runtime)
    expected_refusal = PersistenceError if corruption in {"foreign-predecessor-parent", "foreign-review-parent"} else StateConflict
    with pytest.raises(expected_refusal):
        runtime.jobs.create_cycle_repair(root.job_id, work.job_id, review_id, command_id=command)
    assert _inventory(runtime) == before


def test_orphaned_creation_receipt_cannot_fork_the_noncurrent_predecessor(tmp_path, monkeypatch):
    f = _seeded_runtime(tmp_path, monkeypatch, verdict="reject")
    repair = _create_repair(f)
    runtime = f["runtime"]
    _adversarial_update(runtime, "events", "DELETE FROM events WHERE command_id=?",
                        (_repair_command(f),))
    before = _inventory(runtime)
    with pytest.raises(StateConflict, match="current|provenance|creation|receipt"):
        _create_repair(f)
    assert _inventory(runtime) == before
    assert runtime.jobs.get_job(repair.job_id).job_id == repair.job_id


@pytest.mark.parametrize("column,value", [("depth", 1), ("plan_step_id", "foreign-step")])
def test_repair_replay_rejects_stored_child_semantic_drift(tmp_path, monkeypatch, column, value):
    f = _seeded_runtime(tmp_path, monkeypatch, verdict="reject")
    repair = _create_repair(f)
    runtime = f["runtime"]
    _adversarial_update(runtime, "jobs", f"UPDATE jobs SET {column}=? WHERE job_id=?",
                        (value, repair.job_id))
    before = _inventory(runtime)
    with pytest.raises(StateConflict, match="semantic|lineage|depth|step|provenance"):
        _create_repair(f)
    assert _inventory(runtime) == before


def test_actual_repair_round_ceiling_refuses_without_new_child_or_credit(tmp_path, monkeypatch):
    f = _seeded_runtime(tmp_path, monkeypatch, verdict="reject")
    repair1 = _create_repair(f)
    first = _finish_repair_and_review(f, repair1, verdict="reject")
    repair2 = _create_repair(f, repair1, first["review_job"], first["review_seal"])
    second = _finish_repair_and_review(f, repair2, verdict="reject", rejected=repair1,
                                       rejecting_review=first["review_job"], reject_seal=first["review_seal"])
    assert repair2.repair_round == 2
    before = _inventory(f["runtime"])
    with pytest.raises(StateConflict, match="rounds|exhausted"):
        _create_repair(f, repair2, second["review_job"], second["review_seal"])
    assert _inventory(f["runtime"]) == before
