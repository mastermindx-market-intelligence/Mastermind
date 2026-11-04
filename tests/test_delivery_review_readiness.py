"""Regression for the native GitHub review-readiness sequencing contract.

The intended fix is to advance a locally qualified PR out of Draft before
GitHub review_requested, not to relax draft-review admission or resend a refused
Fabric review. The source workflow must never confuse CI-pending with unready.
"""
from pathlib import Path

from control_plane import github_review_intent as gri


ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "mastermindx-market-intelligence/Mastermind"


def _decision(
    *, draft: bool, reviewer: str = "independent-reviewer",
    action: str = "review_requested", allow_lifecycle_review: bool = False,
    current_permission: gri.CurrentPermission | None = None,
):
    envelope = gri.WebhookEnvelope(
        delivery_id="11111111-2222-3333-4444-555555555555",
        event="pull_request",
        action=action,
        repository=REPOSITORY,
        installation_id=4242,
        pull_number=1924,
    )
    signal = gri.IntentSignal(
        actor_login="authorized-maintainer",
        permission_basis=(
            gri.ActorPermissionBasis.REVERIFIED_LIFECYCLE_PERMISSION
            if action == "ready_for_review"
            else gri.ActorPermissionBasis.GITHUB_ENFORCED_TRIAGE_WRITE
        ),
        requested_reviewer=reviewer,
    )
    pull_request = gri.PullRequestFacts(
        repository=REPOSITORY,
        number=1924,
        state="open",
        draft=draft,
        head_sha="a" * 40,
        head_repository=REPOSITORY,
        base_repository=REPOSITORY,
        base_sha="b" * 40,
        title="docs: review readiness",
        body="Locally qualified and ready for non-author review.",
    )
    policy = gri.ReviewIntentPolicy(
        repositories=frozenset({REPOSITORY}),
        installation_ids=frozenset({4242}),
        configured_reviewer="independent-reviewer",
        authorized_actors=frozenset({"authorized-maintainer"}),
        allow_lifecycle_review=allow_lifecycle_review,
    )
    return gri.decide_review_intent(
        envelope=envelope,
        policy=policy,
        pull_request=pull_request,
        signal=signal,
        current_permission=current_permission,
    )


def test_draft_review_requested_is_a_real_refusal_not_a_pending_review():
    decision = _decision(draft=True)
    assert decision.admitted is False
    assert decision.refusal is gri.ReviewIntentRefusal.PULL_REQUEST_DRAFT


def test_reviewable_ready_pr_admits_only_configured_review_intent():
    eligible = _decision(draft=False)
    wrong_recipient = _decision(draft=False, reviewer="different-reviewer")
    assert eligible.admitted is True
    assert eligible.frozen_head_sha == "a" * 40
    assert wrong_recipient.admitted is False
    assert (
        wrong_recipient.refusal
        is gri.ReviewIntentRefusal.REVIEW_REQUEST_FOR_OTHER_REVIEWER
    )


def test_ready_transition_does_not_implicitly_admit_an_automatic_review():
    decision = _decision(draft=False, action="ready_for_review")
    assert decision.admitted is False
    assert decision.refusal is gri.ReviewIntentRefusal.AUTOMATIC_REVIEW_DISABLED


def test_opt_in_ready_review_requires_fresh_permission_and_shares_manual_identity():
    unverified = _decision(
        draft=False, action="ready_for_review", allow_lifecycle_review=True,
    )
    assert unverified.admitted is False
    assert unverified.refusal is gri.ReviewIntentRefusal.ACTOR_PERMISSION_NOT_REVERIFIED

    automatic = _decision(
        draft=False, action="ready_for_review", allow_lifecycle_review=True,
        current_permission=gri.CurrentPermission(
            REPOSITORY, "authorized-maintainer", "write",
        ),
    )
    manual = _decision(draft=False)
    assert automatic.admitted is True
    assert automatic.intent_source is gri.IntentSource.PR_LIFECYCLE
    assert manual.intent_source is gri.IntentSource.REVIEW_REQUESTED
    assert automatic.command_id == manual.command_id


def test_delivery_workflow_guides_review_ready_before_request_without_ci_bypass():
    workflow = (ROOT / "docs/DELIVERY_WORKFLOW.md").read_text(encoding="utf-8")
    assert "## Review-readiness liveness" in workflow
    assert "Ready for Review" in workflow
    assert "before asking the reviewer" in workflow
    assert "pending" in workflow.lower()
    assert "PULL_REQUEST_DRAFT" in workflow
    assert "ready_for_review" in workflow
    assert "does **not** replay it" in workflow
    assert "actual non-author review readback" in workflow
    assert "native merge" in workflow
    assert "Do not infer" in workflow
    assert "never duplicate a refused Fabric" in workflow
