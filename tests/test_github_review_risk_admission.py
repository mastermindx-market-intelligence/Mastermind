"""Risk pre-admission effect-boundary tests: no fake Job, no new queue."""
from __future__ import annotations

from dataclasses import replace

import pytest

from control_plane.github_review_intent import IntentSource, ReviewIntentRefusal
from control_plane.github_review_intent_ingress import (
    AdmissionState, ReviewAdmissionReceipt, ReviewIngressUnavailable,
    ReviewRiskSourceUnqualified, ReviewAdmissionPreflightExpired,
    admit_decided_review,
)
from integrations.github_review_risk_consumer import GitHubReviewRiskConsumer
from test_github_review_risk_consumer import ExistingApp, facts, intent


class Ledger:
    """Synchronous canonical command model; no networking, worker, or launch."""
    def __init__(self):
        self.jobs = {}
        self.calls = 0

    def has_admitted_command(self, command_id):
        return command_id in self.jobs

    def admitted_command_ids(self):
        return frozenset(self.jobs)

    def admit_review_intent(self, *, decision, objective):
        return self.admit_or_join_review_intent(
            decision=decision, objective=objective,
        ).job_id

    def admit_or_join_review_intent(self, *, decision, objective):
        self.calls += 1
        if decision.command_id in self.jobs:
            job_id, original = self.jobs[decision.command_id]
            return ReviewAdmissionReceipt(
                job_id=job_id, decision=original, created=False,
            )
        job_id = f"JOB-{len(self.jobs) + 1}"
        self.jobs[decision.command_id] = (job_id, decision)
        return ReviewAdmissionReceipt(
            job_id=job_id, decision=decision, created=True,
        )


def ready(source, ledger, chosen=None, budget=None):
    chosen = chosen if chosen is not None else intent()
    consumer = GitHubReviewRiskConsumer(github=source.api, repository="example/repo")
    return admit_decided_review(
        decision=chosen, pull_request=facts(), fabric=ledger,
        before_admission=budget,
        review_risk_gate=lambda *, decision, pull_request: consumer(
            decision=decision, pull_request=pull_request,
            budget_check=budget,
        ),
    )


def test_fast_skip_is_typed_no_job_no_visibility_and_preserves_exact_source():
    source = ExistingApp("docs/user-guide.md")
    ledger = Ledger()
    outcome = ready(source, ledger)
    assert outcome.state is AdmissionState.SKIPPED
    assert outcome.job_id is None and outcome.visibility_error is None
    assert outcome.decision.refusal is ReviewIntentRefusal.REVIEW_NOT_REQUIRED
    assert outcome.decision.admitted is False
    assert outcome.decision.frozen_head_sha == "a" * 40
    assert ledger.calls == 0 and ledger.jobs == {}


@pytest.mark.parametrize("path", [
    ".github/workflows/ci.yml",
    "tests/conftest.py",
    "docs/SESSION_INDEPENDENT_REVIEW_ROUTING.md",
])
def test_critical_stays_on_original_single_command(path):
    source = ExistingApp(path)
    ledger = Ledger()
    outcome = ready(source, ledger)
    assert outcome.state is AdmissionState.ADMITTED
    assert outcome.job_id == "JOB-1"
    assert ledger.calls == 1 and len(ledger.jobs) == 1


def test_auto_existing_job_not_hidden_by_later_fast_classification():
    source = ExistingApp("security/handler.py")
    ledger = Ledger()
    first = ready(source, ledger)
    assert first.state is AdmissionState.ADMITTED
    source.path = "docs/user-guide.md"
    again = ready(source, ledger)
    assert again.state is AdmissionState.ALREADY_ADMITTED
    assert again.job_id == first.job_id
    assert ledger.calls == 2 and len(ledger.jobs) == 1


def test_manual_intent_uses_existing_path_without_risk_reads():
    source = ExistingApp()
    ledger = Ledger()
    choice = intent(source=IntentSource.REVIEW_REQUESTED, policy=False)
    outcome = ready(source, ledger, chosen=choice)
    assert outcome.state is AdmissionState.ADMITTED
    assert ledger.calls == 1
    assert source.calls == []


@pytest.mark.parametrize("failure", ["missing_page", "deny_source"])
def test_incomplete_or_denied_source_holds_before_job(failure):
    source = ExistingApp()
    setattr(source, failure, True)
    ledger = Ledger()
    with pytest.raises(ReviewRiskSourceUnqualified):
        ready(source, ledger)
    assert ledger.calls == 0 and ledger.jobs == {}


def test_stale_signed_source_holds_before_job():
    source = ExistingApp()
    source.move_after = 3
    ledger = Ledger()
    with pytest.raises(ReviewRiskSourceUnqualified):
        ready(source, ledger)
    assert ledger.calls == 0


def test_missing_canonical_status_port_refuses_skip():
    source = ExistingApp()
    ledger = Ledger()
    ledger.has_admitted_command = None
    with pytest.raises(ReviewIngressUnavailable, match="STATUS_UNAVAILABLE"):
        ready(source, ledger)
    assert ledger.calls == 0


def test_budget_expiry_fences_admission():
    source = ExistingApp()
    ledger = Ledger()
    def expired():
        raise ReviewAdmissionPreflightExpired("DEADLINE_EXPIRED")
    with pytest.raises(ReviewAdmissionPreflightExpired):
        ready(source, ledger, budget=expired)
    assert ledger.calls == 0
    assert source.calls == []


def test_standard_skip_creates_no_job_and_manual_request_still_admits():
    source, ledger = ExistingApp("server/api/handler.py"), Ledger()
    skipped = ready(source, ledger)
    assert skipped.state is AdmissionState.SKIPPED
    assert ledger.calls == 0 and ledger.jobs == {}
    manual = intent(source=IntentSource.REVIEW_REQUESTED, policy=False)
    admitted = ready(source, ledger, chosen=manual)
    assert admitted.state is AdmissionState.ADMITTED
    assert ledger.calls == 1 and len(ledger.jobs) == 1
