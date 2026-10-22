"""Only genuine completed distinct Executive Jobs can publish review results."""
from control_plane.executive_runtime import Runtime, JobPayload
from control_plane.github_review_result_reader import ExecutiveVerifiedReviewResults
from control_plane.github_review_runtime_adapter import ExecutiveReviewJobAdmission
from test_github_review_runtime_adapter import decision


def completed_pair(tmp_path, *, identical_worker=False, review_verdict="approve", builder_repository="example/repo", builder_sha="a" * 40):
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
    builder = runtime.jobs.create_job(
        "Build source for PR #42",
        constraints={"eligible_quota_classes": ["claude-native"]},
        provenance={
            "schema": "mastermind.github_review_builder_source.v1",
            "repository": builder_repository,
            "pull_number": 42,
            "frozen_head_sha": builder_sha,
        },
    )
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

def test_unrelated_builder_job_on_different_repository_is_not_independence(tmp_path):
    runtime, builder, review = completed_pair(
        tmp_path, builder_repository="attacker/unrelated"
    )
    reader = ExecutiveVerifiedReviewResults(
        runtime=runtime, builder_job_id_for_review=lambda _: builder
    )
    assert reader.load_verified_result(job_id=review) is None


def test_same_repository_wrong_builder_head_is_not_independence(tmp_path):
    runtime, builder, review = completed_pair(tmp_path, builder_sha="b" * 40)
    reader = ExecutiveVerifiedReviewResults(
        runtime=runtime, builder_job_id_for_review=lambda _: builder
    )
    assert reader.load_verified_result(job_id=review) is None

# Direct source-reader contract coverage complements the publication workflow
# tests. A GitHub submitter is NEVER an attested native builder worker.
from dataclasses import replace

import pytest

from control_plane.github_review_intent_ingress import ExternalGitHubSourceFacts


class _AuthenticatedExternalSource:
    def __init__(self, facts=None, *, unavailable=False):
        self.facts = facts or ExternalGitHubSourceFacts(
            repository="example/repo", pull_number=42,
            head_sha="a" * 40, submitter_login="alice",
            submitter_id=314,
        )
        self.unavailable = unavailable
        self.lookups = []

    def read_external_source(self, *, repository, pull_number):
        self.lookups.append((repository, pull_number))
        if self.unavailable:
            raise OSError("authenticated GitHub lookup unavailable")
        return self.facts


def test_external_reader_uses_actual_terminal_job_and_distinct_submitter(tmp_path):
    runtime, builder, reviewer = completed_pair(tmp_path)
    source = _AuthenticatedExternalSource()
    reader = ExecutiveVerifiedReviewResults(
        runtime=runtime, external_source=source,
        publisher_login="reviewer-bot[bot]",
    )
    result = reader.load_verified_result(job_id=reviewer)
    assert result is not None
    assert result.source_basis == "EXTERNAL_GITHUB_SUBMITTER"
    assert result.builder_worker_id == ""
    assert result.reviewer_worker_id == "reviewer-01"
    assert result.source_github_submitter_login == "alice"
    assert result.source_github_submitter_id == 314
    assert source.lookups == [("example/repo", 42)]


@pytest.mark.parametrize("delta", [
    {"submitter_login": "reviewer-bot[bot]"},
    {"submitter_login": ""},
    {"submitter_id": 0},
    {"submitter_id": True},
    {"head_sha": "b" * 40},
    {"repository": "unrelated/repo"},
    {"pull_number": 43},
])
def test_external_reader_refuses_unverified_or_self_source(tmp_path, delta):
    runtime, builder, reviewer = completed_pair(tmp_path)
    canonical = _AuthenticatedExternalSource().facts
    source = _AuthenticatedExternalSource(replace(canonical, **delta))
    reader = ExecutiveVerifiedReviewResults(
        runtime=runtime, external_source=source,
        publisher_login="reviewer-bot[bot]",
    )
    assert reader.load_verified_result(job_id=reviewer) is None


def test_external_reader_refuses_when_authenticated_source_is_unavailable(tmp_path):
    runtime, builder, reviewer = completed_pair(tmp_path)
    source = _AuthenticatedExternalSource(unavailable=True)
    reader = ExecutiveVerifiedReviewResults(
        runtime=runtime, external_source=source,
        publisher_login="reviewer-bot[bot]",
    )
    assert reader.load_verified_result(job_id=reviewer) is None
