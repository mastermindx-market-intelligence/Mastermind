"""Only genuine completed distinct Executive Jobs can publish review results."""
from control_plane.executive_runtime import Runtime, JobPayload
from control_plane.github_review_result_reader import ExecutiveVerifiedReviewResults
from control_plane.github_review_runtime_adapter import ExecutiveReviewJobAdmission
from test_github_review_runtime_adapter import decision


def completed_pair(tmp_path, *, identical_worker=False, review_verdict="approve"):
    runtime = Runtime.at(tmp_path)
    runtime.workers.register_worker(
        "builder-01", provider="claude", account_label="builder",
        worker_type="mock", capabilities=["code"],
        quota_classes={"claude-native": ["code"]},
    )
    if not identical_worker:
        runtime.workers.register_worker(
            "reviewer-01", provider="codex", account_label="reviewer",
            worker_type="mock", capabilities=["code"],
            quota_classes={"codex-native": ["code"]},
        )
    builder = runtime.jobs.create_job("Build source for PR #42", constraints={"eligible_quota_classes": ["claude-native"]})
    runtime.jobs.assign_job(builder.job_id, "builder-01")
    runtime.jobs.complete_job(
        builder.job_id, JobPayload(summary="source completed")
    )
    adapter = ExecutiveReviewJobAdmission(
        runtime=runtime, admission_guard=lambda: None,
        constraints={"eligible_quota_classes": ["claude-native" if identical_worker else "codex-native"]},
    )
    reviewer_job = adapter.admit_review_intent(
        decision=decision(), objective="Review exact PR"
    )
    runtime.jobs.assign_job(
        reviewer_job, "builder-01" if identical_worker else "reviewer-01"
    )
    runtime.jobs.complete_job(reviewer_job, JobPayload(
        summary="No blocking issues found.", verdict=review_verdict
    ))
    return runtime, builder.job_id, reviewer_job


def test_real_distinct_terminal_jobs_yield_exact_result(tmp_path):
    runtime, builder, review = completed_pair(tmp_path)
    reader = ExecutiveVerifiedReviewResults(
        runtime=runtime, builder_job_id_for_review=lambda job_id: builder
    )
    result = reader.load_verified_result(job_id=review)
    assert result is not None
    assert result.job_id == review
    assert result.reviewer_worker_id == "reviewer-01"
    assert result.builder_worker_id == "builder-01"
    assert result.verdict == "PASS"
    assert len(result.result_digest) == 64


def test_missing_builder_provenance_refuses_review(tmp_path):
    runtime, builder, review = completed_pair(tmp_path)
    reader = ExecutiveVerifiedReviewResults(runtime=runtime)
    assert reader.load_verified_result(job_id=review) is None


def test_same_worker_cannot_be_its_own_review_proof(tmp_path):
    runtime, builder, review = completed_pair(tmp_path, identical_worker=True)
    reader = ExecutiveVerifiedReviewResults(
        runtime=runtime, builder_job_id_for_review=lambda job_id: builder
    )
    assert reader.load_verified_result(job_id=review) is None


def test_review_verdict_outside_closed_completion_vocabulary_refused(tmp_path):
    runtime, builder, review = completed_pair(tmp_path, review_verdict="")
    reader = ExecutiveVerifiedReviewResults(
        runtime=runtime, builder_job_id_for_review=lambda job_id: builder
    )
    assert reader.load_verified_result(job_id=review) is None
