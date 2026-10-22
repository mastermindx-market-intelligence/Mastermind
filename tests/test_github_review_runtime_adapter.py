"""A signed GitHub review intent becomes one real Executive Runtime Job, no fake builder."""
import pytest

from control_plane.executive_runtime import Runtime
from control_plane.github_review_intent import (
    IntentSource, ReviewIntentDecision, review_command_id, review_intent_id,
)
from control_plane.github_review_runtime_adapter import (
    ExecutiveReviewJobAdmission, ReviewAdmissionUnavailable,
)

REPO = "example/repo"
SHA = "a" * 40


def decision():
    intent_id = review_intent_id(repository=REPO, pull_number=42,
                                  head_sha=SHA)
    return ReviewIntentDecision(
        admitted=True, refusal=None, intent_source=IntentSource.INTENT_LABEL,
        intent_id=intent_id, command_id=review_command_id(intent_id),
        delivery_command_id="gh-review-delivery:" + "a" * 32,
        repository=REPO, pull_number=42, frozen_head_sha=SHA, actor="alice",
    )


def test_missing_host_arm_cannot_create_a_job(tmp_path):
    runtime = Runtime.at(tmp_path)
    adapter = ExecutiveReviewJobAdmission(runtime=runtime)
    with pytest.raises(ReviewAdmissionUnavailable, match="UNARMED"):
        adapter.admitted_command_ids()
    with pytest.raises(ReviewAdmissionUnavailable, match="UNARMED"):
        adapter.admit_review_intent(decision=decision(), objective="Review exact PR")
    assert runtime.jobs.list_jobs() == []


def test_exact_head_event_creates_one_read_only_runtime_root_and_replays(tmp_path):
    runtime = Runtime.at(tmp_path)
    adapter = ExecutiveReviewJobAdmission(runtime=runtime, admission_guard=lambda: None)
    d = decision()
    assert d.command_id not in adapter.admitted_command_ids()
    id1 = adapter.admit_review_intent(decision=d, objective="Review exact PR")
    assert id1.startswith("JOB-")
    assert d.command_id in adapter.admitted_command_ids()
    id2 = adapter.admit_review_intent(decision=d, objective="Review exact PR")
    assert id2 == id1
    assert len(runtime.jobs.list_jobs()) == 1
    job = runtime.jobs.get_job(id1)
    assert job.status.value == "QUEUED"
    assert job.attempt_limit == 1
    assert job.requested_authorities == ["READ"]
    assert job.review_required is False
    assert job.orchestration_role is None
    assert job.parent_job_id is None
    assert job.allowed_write_paths == []


def test_replay_with_different_objective_cannot_hijack_existing_job(tmp_path):
    runtime = Runtime.at(tmp_path)
    adapter = ExecutiveReviewJobAdmission(runtime=runtime, admission_guard=lambda: None)
    d = decision()
    adapter.admit_review_intent(decision=d, objective="Review exact PR")
    with pytest.raises(ReviewAdmissionUnavailable, match="PAYLOAD_CONFLICT"):
        adapter.admit_review_intent(decision=d, objective="Different task")
    assert len(runtime.jobs.list_jobs()) == 1


def test_refusing_admission_guard_has_no_effect(tmp_path):
    runtime = Runtime.at(tmp_path)
    def blocked():
        raise PermissionError("CEO submit arm closed")
    adapter = ExecutiveReviewJobAdmission(runtime=runtime, admission_guard=blocked)
    with pytest.raises(ReviewAdmissionUnavailable, match="REFUSED"):
        adapter.admit_review_intent(decision=decision(), objective="Review exact PR")
    assert runtime.jobs.list_jobs() == []

def test_commit_rechecks_external_authority_in_transaction(tmp_path):
    runtime = Runtime.at(tmp_path)
    checks = []
    def changing_guard():
        checks.append(True)
        if len(checks) > 1:
            raise PermissionError("retracted before commit")
    adapter = ExecutiveReviewJobAdmission(
        runtime=runtime, admission_guard=changing_guard
    )
    with pytest.raises(ReviewAdmissionUnavailable, match="REFUSED"):
        adapter.admit_review_intent(decision=decision(), objective="Review exact PR")
    assert len(checks) >= 2
    assert runtime.jobs.list_jobs() == []
