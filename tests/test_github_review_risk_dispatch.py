"""Pure automatic-review skip gate tests; never executes an ingress."""
import pytest

from control_plane.github_review_risk_dispatch import (
    ReviewDispatch,
    ReviewOrigin,
    ReviewRiskDispatchError,
    decide_risk_dispatch,
)
from control_plane.github_review_risk_policy import (
    ReviewChangeFacts,
    ReviewTier,
    assess_review_risk,
)

REPO = "mastermindx-market-intelligence/Mastermind"


def risk(paths=("docs/readme.md",), *, verified=True):
    return assess_review_risk(ReviewChangeFacts(
        repository=REPO, pull_number=10, head_sha="a" * 40,
        changed_paths=paths, additions=2, deletions=0,
        complete_source_verified=verified,
    ))


def test_auto_fast_skips_review_job():
    result = decide_risk_dispatch(
        origin=ReviewOrigin.AUTOMATIC_POLICY, assessment=risk(),
    )
    assert result.action is ReviewDispatch.SKIP_NO_REVIEW_NEEDED
    assert result.source_tier is ReviewTier.FAST


def test_auto_consequential_gets_review():
    result = decide_risk_dispatch(
        origin=ReviewOrigin.AUTOMATIC_POLICY,
        assessment=risk(("server/api/refresh.py",)),
    )
    assert result.action is ReviewDispatch.AUTO_REVIEW_ELIGIBLE
    assert result.source_tier is ReviewTier.STANDARD


def test_auto_sensitive_gets_review():
    result = decide_risk_dispatch(
        origin=ReviewOrigin.AUTOMATIC_POLICY,
        assessment=risk((".github/workflows/release.yml",)),
    )
    assert result.action is ReviewDispatch.AUTO_REVIEW_ELIGIBLE
    assert result.source_tier is ReviewTier.CRITICAL


def test_auto_partial_source_cannot_claim_exemption_or_auto_review():
    result = decide_risk_dispatch(
        origin=ReviewOrigin.AUTOMATIC_POLICY,
        assessment=risk(verified=False),
    )
    assert result.action is ReviewDispatch.HOLD_UNQUALIFIED_SOURCE


def test_auto_missing_risk_holds():
    assert decide_risk_dispatch(
        origin=ReviewOrigin.AUTOMATIC_POLICY, assessment=None,
    ).action is ReviewDispatch.HOLD_UNQUALIFIED_SOURCE


def test_manual_review_does_not_run_fast_lane():
    result = decide_risk_dispatch(
        origin=ReviewOrigin.MANUAL_AUTHORIZED, assessment=risk(),
    )
    assert result.action is ReviewDispatch.USE_EXISTING_MANUAL_INGRESS


def test_manual_review_without_risk_stays_on_existing_ingress():
    assert decide_risk_dispatch(
        origin=ReviewOrigin.MANUAL_AUTHORIZED, assessment=None,
    ).action is ReviewDispatch.USE_EXISTING_MANUAL_INGRESS


@pytest.mark.parametrize("bad_origin", [
    "AUTOMATIC_POLICY", None, True, 1,
])
def test_caller_text_is_not_verified_origin(bad_origin):
    with pytest.raises(ReviewRiskDispatchError):
        decide_risk_dispatch(origin=bad_origin, assessment=risk())
