"""Risk-tier pre-admission integration: no duplicate Jobs for FAST/unknown.

These fixtures verify signed webhook identity, preserved manual intent and
the original review admission port. They never use live GitHub/Executive data.
"""
from __future__ import annotations

from dataclasses import replace

import pytest

from control_plane.github_review_intent import (
    ReviewIntentRefusal, sign_webhook_body,
)
from control_plane.github_review_intent_ingress import (
    AdmissionState, admit_review_intent, automatic_review_risk_disposition,
)
from control_plane.github_review_risk_dispatch import (
    ReviewDispatch, RiskDispatchAdvice,
)
from control_plane.github_review_risk_policy import ReviewTier
from test_github_review_lifecycle import (
    Actors, DELIVERY, Fabric, HEAD, Pulls, REPO, SECRET, payload, policy,
)
from test_github_review_source_guard import automatic, reconciled
from test_github_review_runtime_adapter import decision as manual_decision


def qualified(decision, tier=ReviewTier.STANDARD):
    return RiskDispatchAdvice(
        action=(ReviewDispatch.SKIP_NO_REVIEW_NEEDED if tier is ReviewTier.FAST
                else ReviewDispatch.AUTO_REVIEW_ELIGIBLE),
        source_tier=tier, reason="VERIFIED_CURRENT_SOURCE",
        repository=decision.repository,
        pull_number=decision.pull_number,
        head_sha=decision.frozen_head_sha,
    )


def webhook_admit(gate):
    body = payload()
    fabric = Fabric()
    receipt = admit_review_intent(
        secret=SECRET, body=body, delivery_id=DELIVERY,
        event="pull_request",
        signature_header=sign_webhook_body(secret=SECRET, body=body),
        policy=policy(), pull_requests=Pulls(), actors=Actors(),
        fabric=fabric, automatic_review_gate=gate,
    )
    return receipt, fabric


def test_signed_fast_webhook_returns_normal_no_job_disposition():
    outcome, fabric = webhook_admit(lambda d: qualified(d, ReviewTier.FAST))
    assert outcome.state is AdmissionState.REFUSED
    assert outcome.decision.refusal is ReviewIntentRefusal.AUTOMATIC_REVIEW_NOT_REQUIRED
    assert outcome.job_id is None
    assert fabric.calls == 0


def test_signed_standard_webhook_creates_one_existing_review_job():
    outcome, fabric = webhook_admit(lambda d: qualified(d))
    assert outcome.state is AdmissionState.ADMITTED
    assert fabric.calls == 1


def test_signed_critical_webhook_is_eligible_for_existing_review_job():
    outcome, fabric = webhook_admit(lambda d: qualified(d, ReviewTier.CRITICAL))
    assert outcome.state is AdmissionState.ADMITTED
    assert fabric.calls == 1


@pytest.mark.parametrize("gate", [
    None,
    lambda d: None,
    lambda d: replace(qualified(d, ReviewTier.FAST), head_sha="c" * 40),
    lambda d: replace(qualified(d), repository="other/repo"),
    lambda d: replace(qualified(d, ReviewTier.FAST), source_tier=ReviewTier.CRITICAL),
    lambda d: replace(qualified(d), source_tier=ReviewTier.FAST),
    lambda d: (_ for _ in ()).throw(RuntimeError("missing GitHub")),
])
def test_auto_unqualified_or_stale_source_refuses_before_any_job(gate):
    outcome, fabric = webhook_admit(gate)
    assert outcome.state is AdmissionState.REFUSED
    assert outcome.decision.refusal is ReviewIntentRefusal.AUTOMATIC_REVIEW_RISK_UNVERIFIED
    assert fabric.calls == 0


def test_direct_reconciled_source_remains_fail_closed_without_gate():
    chosen = reconciled()
    outcome = automatic_review_risk_disposition(
        decision=chosen, automatic_review_gate=None,
    )
    assert outcome.state is AdmissionState.REFUSED
    assert outcome.decision.refusal is ReviewIntentRefusal.AUTOMATIC_REVIEW_RISK_UNVERIFIED


def test_direct_reconciled_fast_skips_without_job():
    chosen = reconciled()
    outcome = automatic_review_risk_disposition(
        decision=chosen,
        automatic_review_gate=lambda d: qualified(d, ReviewTier.FAST),
    )
    assert outcome.state is AdmissionState.REFUSED
    assert outcome.decision.refusal is ReviewIntentRefusal.AUTOMATIC_REVIEW_NOT_REQUIRED


def test_explicit_manual_review_does_not_call_risk_gate():
    def unexpected(_):
        raise AssertionError("manual request wrongly gated")
    assert automatic_review_risk_disposition(
        decision=manual_decision(),
        automatic_review_gate=unexpected,
    ) is None



def test_existing_open_pr_reconciliation_fast_returns_no_job(tmp_path):
    from control_plane.github_review_intent_ingress import OpenPullRequestPage
    from test_github_review_repository_policy import Pages, adapter, scan
    runtime, fabric = adapter(tmp_path)
    pulls = Pages({1: OpenPullRequestPage((42,), False)})
    result = scan(
        pulls, fabric,
        automatic_review_gate=lambda d: qualified(d, ReviewTier.FAST),
    )
    assert result.complete
    assert len(result.outcomes) == 1
    outcome = result.outcomes[0]
    assert outcome.state is AdmissionState.REFUSED
    assert outcome.decision.refusal is ReviewIntentRefusal.AUTOMATIC_REVIEW_NOT_REQUIRED
    assert runtime.jobs.list_jobs() == []


def test_existing_open_pr_reconciliation_missing_proof_fails_closed(tmp_path):
    from control_plane.github_review_intent_ingress import OpenPullRequestPage
    from test_github_review_repository_policy import Pages, adapter, scan
    runtime, fabric = adapter(tmp_path)
    pulls = Pages({1: OpenPullRequestPage((42,), False)})
    result = scan(pulls, fabric, automatic_review_gate=lambda _: None)
    assert result.complete
    assert len(result.outcomes) == 1
    outcome = result.outcomes[0]
    assert outcome.state is AdmissionState.REFUSED
    assert outcome.decision.refusal is ReviewIntentRefusal.AUTOMATIC_REVIEW_RISK_UNVERIFIED
    assert runtime.jobs.list_jobs() == []
