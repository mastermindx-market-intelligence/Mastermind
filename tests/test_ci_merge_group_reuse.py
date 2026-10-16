"""Fail-closed observation proof for avoiding *duplicate* postmerge CI work.

This test suite does not skip, alter, or own protected CI. The pure verifier is
not yet wired into any GitHub Actions step or a release decision.
"""
from __future__ import annotations

import copy

import pytest

from scripts.ci_merge_group_reuse import qualify_merge_group_proof

REPOSITORY = "mastermindx-market-intelligence/Mastermind"
HEAD = "c" * 40
RUN = 38885403814
WORKFLOW = 324108847
JOB_STEPS = {
    "pytest shard 0": [
        "Verify Paper direct pinned MCP SDK",
        "Verify private Fabric HTTP compatibility and incumbent backend lifetime",
        "Compile source", "Validate shell scripts", "Run repository test shard",
    ],
    "pytest shard 1": ["Run repository test shard"],
    "pytest shard 2": ["Run repository test shard"],
    "test": ["Run repository test gate"],
}


def proof_fixture():
    run = {
        "id": RUN, "workflow_id": WORKFLOW, "head_sha": HEAD,
        "head_branch": "gh-readonly-queue/master/pr-1476-fixture",
        "event": "merge_group", "status": "completed", "conclusion": "success",
        "path": ".github/workflows/ci.yml", "run_attempt": 1,
        "repository": {"full_name": REPOSITORY},
        "head_repository": {"full_name": REPOSITORY},
        "created_at": "2026-10-16T10:10:00Z",
        "updated_at": "2026-10-16T10:42:10Z",
    }
    jobs = []
    for index, (name, steps) in enumerate(JOB_STEPS.items(), start=1):
        jobs.append({
            "id": index, "name": name, "run_id": RUN,
            "run_attempt": 1, "head_sha": HEAD,
            "status": "completed", "conclusion": "success",
            "started_at": "2026-10-16T10:15:00Z",
            "completed_at": "2026-10-16T10:41:59Z",
            "steps": [
                {"name": step, "status": "completed", "conclusion": "success"}
                for step in steps
            ],
        })
    return run, {"total_count": len(jobs), "jobs": jobs}


def qualified(run, jobs, *, event="push", ref="refs/heads/master", sha=HEAD,
              repo=REPOSITORY, workflow=WORKFLOW, push_at="2026-10-16T10:43:00Z"):
    return qualify_merge_group_proof(
        repository=repo, head_sha=sha, current_event=event, current_ref=ref,
        current_created_at=push_at, expected_workflow_id=workflow,
        workflow_run=run, workflow_jobs=jobs,
    )


def test_a_complete_prior_native_merge_group_proof_is_eligible():
    run, jobs = proof_fixture()
    ok, reason = qualified(run, jobs)
    assert ok and reason == "PRIOR_EXACT_MERGE_GROUP_CI_PROVEN"


@pytest.mark.parametrize("event,ref", [
    ("pull_request", "refs/heads/master"),
    ("merge_group", "refs/heads/master"),
    ("push", "refs/heads/feature"),
    ("workflow_dispatch", "refs/heads/master"),
])
def test_only_master_pushes_are_eligible(event, ref):
    run, jobs = proof_fixture()
    assert not qualified(run, jobs, event=event, ref=ref)[0]


@pytest.mark.parametrize("mutation", [
    "head_mismatch", "event_not_merge_group", "workflow_path", "workflow_identity",
    "run_not_complete", "run_failure", "run_retry", "run_id_missing",
    "wrong_source_repository", "wrong_head_repository", "untrusted_queue_branch",
    "future_run", "corrupt_run_timestamp", "different_candidate_head",
])
def test_run_identity_and_causal_proof_fail_closed(mutation):
    run, jobs = proof_fixture()
    if mutation == "head_mismatch":run["head_sha"] = "d" * 40
    if mutation == "event_not_merge_group":run["event"] = "workflow_dispatch"
    if mutation == "workflow_path":run["path"] = ".github/workflows/unreviewed.yml"
    if mutation == "workflow_identity":run["workflow_id"] += 1
    if mutation == "run_not_complete":run["status"] = "in_progress"
    if mutation == "run_failure":run["conclusion"] = "failure"
    if mutation == "run_retry":run["run_attempt"] = 2
    if mutation == "run_id_missing":run.pop("id")
    if mutation == "wrong_source_repository":run["repository"]["full_name"] = "attacker/project"
    if mutation == "wrong_head_repository":run["head_repository"]["full_name"] = "attacker/project"
    if mutation == "untrusted_queue_branch":run["head_branch"] = "main"
    if mutation == "future_run":run["updated_at"] = "2026-10-16T10:44:01Z"
    if mutation == "corrupt_run_timestamp":run["updated_at"] = "garbage"
    if mutation == "different_candidate_head":
        assert not qualified(run, jobs, sha="e" * 40)[0]
        return
    assert not qualified(run, jobs)[0], mutation


@pytest.mark.parametrize("mutation", [
    "truncated", "extra_job", "duplicate_job", "missing_shard_zero", "skipped_shard",
    "failed_required_fanin", "wrong_sha", "wrong_run_id", "wrong_attempt",
    "uncompleted_shard", "missing_paper_gate", "missing_fabric_gate", "missing_shell_gate",
    "missing_compile", "missing_pytest", "missing_fanin", "skipped_fabric_gate",
    "future_job", "unknown_job_id", "invalid_steps",
])
def test_truncated_wrong_or_missing_job_proof_fails_closed(mutation):
    run, jobs = proof_fixture()
    target = jobs["jobs"][0]
    if mutation == "truncated":jobs["jobs"].pop()
    if mutation == "extra_job":
        jobs["jobs"].append(copy.deepcopy(target)); jobs["total_count"] += 1
    if mutation == "duplicate_job":jobs["jobs"][1]["name"] = target["name"]
    if mutation == "missing_shard_zero":target["name"] = "other"
    if mutation == "skipped_shard":target["conclusion"] = "skipped"
    if mutation == "failed_required_fanin":jobs["jobs"][-1]["conclusion"] = "failure"
    if mutation == "wrong_sha":target["head_sha"] = "d" * 40
    if mutation == "wrong_run_id":target["run_id"] += 1
    if mutation == "wrong_attempt":target["run_attempt"] += 1
    if mutation == "uncompleted_shard":target["status"] = "queued"
    if mutation == "missing_paper_gate":target["steps"] = [s for s in target["steps"] if not s["name"].startswith("Verify Paper")]
    if mutation == "missing_fabric_gate":target["steps"] = [s for s in target["steps"] if "Fabric HTTP" not in s["name"]]
    if mutation == "missing_shell_gate":target["steps"] = [s for s in target["steps"] if "shell scripts" not in s["name"]]
    if mutation == "missing_compile":target["steps"] = [s for s in target["steps"] if s["name"]!="Compile source"]
    if mutation == "missing_pytest":target["steps"] = [s for s in target["steps"] if s["name"]!="Run repository test shard"]
    if mutation == "missing_fanin":jobs["jobs"][-1]["steps"] = []
    if mutation == "skipped_fabric_gate":
        next(s for s in target["steps"] if "Fabric HTTP" in s["name"])["conclusion"]="skipped"
    if mutation == "future_job":target["completed_at"] = "2026-10-16T10:44:01Z"
    if mutation == "unknown_job_id":target["id"] = None
    if mutation == "invalid_steps":target["steps"] = "not a list"
    assert not qualified(run, jobs)[0], mutation


def test_unavailable_or_malformed_remote_evidence_does_not_authorize_reuse():
    run, jobs = proof_fixture()
    for artifact in (None, "not-json", [], {}, 1):
        assert not qualified(artifact, jobs)[0]
        assert not qualified(run, artifact)[0]


def test_unknown_or_invalid_expected_workflow_cannot_be_adopted():
    run, jobs = proof_fixture()
    for workflow in (None, -1, 0, True, "324108847", 324108848):
        assert not qualified(run, jobs, workflow=workflow)[0]


def test_boolean_attempts_and_inconsistent_job_clock_are_not_qualified():
    run, jobs = proof_fixture()
    run["run_attempt"] = True
    assert not qualified(run, jobs)[0]
    run, jobs = proof_fixture()
    jobs["jobs"][0]["run_attempt"] = True
    assert not qualified(run, jobs)[0]
    run, jobs = proof_fixture()
    jobs["jobs"][0]["completed_at"] = "2026-10-16T10:42:30Z"
    assert not qualified(run, jobs)[0], "A job cannot complete after the run"


def test_missing_or_naive_created_at_is_refused_before_any_consideration():
    run, jobs = proof_fixture()
    for stamp in (None, "", "2026-10-16T10:43:00", "not-an-iso-date", 0):
        assert not qualified(run, jobs, push_at=stamp)[0]


def test_duplicate_step_identity_is_not_a_success_witness():
    run, jobs = proof_fixture()
    steps = jobs["jobs"][0]["steps"]
    steps.append(copy.deepcopy(next(s for s in steps if s["name"] == "Run repository test shard")))
    assert not qualified(run, jobs)[0]
