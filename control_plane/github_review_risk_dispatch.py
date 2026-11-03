"""Source-bound risk preflight for the incumbent GitHub/Executive review ingress.

Pure advice; never creates a webhook, approval, merge, Job, credential or
scheduler. The existing signed receiver must derive origin, PR number and
head SHA from its authenticated event/host authority. A FAST assessment is
bound to one exact repo/PR/head and freshly checked again before a skip.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re

from control_plane.github_review_risk_policy import (
    SCHEMA,
    ReviewRiskAssessment,
    ReviewTier,
)
from control_plane.github_review_risk_source import (
    RiskGitHubReadPort,
    RiskSourceUnavailable,
    SourcePR,
    assess_current_pr_risk,
)


_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$")
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class ReviewRiskDispatchError(ValueError):
    """A caller provided an invalid authority-independent input shape."""


class ReviewOrigin(str, Enum):
    MANUAL_AUTHORIZED = "MANUAL_AUTHORIZED"
    AUTOMATIC_POLICY = "AUTOMATIC_POLICY"


class ReviewDispatch(str, Enum):
    USE_EXISTING_MANUAL_INGRESS = "USE_EXISTING_MANUAL_INGRESS"
    SKIP_NO_REVIEW_NEEDED = "SKIP_NO_REVIEW_NEEDED"
    AUTO_REVIEW_ELIGIBLE = "AUTO_REVIEW_ELIGIBLE"
    HOLD_UNQUALIFIED_SOURCE = "HOLD_UNQUALIFIED_SOURCE"


@dataclass(frozen=True)
class RiskDispatchAdvice:
    action: ReviewDispatch
    source_tier: ReviewTier | None
    reason: str
    repository: str | None = None
    pull_number: int | None = None
    head_sha: str | None = None


def _hold(reason: str, tier: ReviewTier | None = None) -> RiskDispatchAdvice:
    return RiskDispatchAdvice(
        ReviewDispatch.HOLD_UNQUALIFIED_SOURCE, tier, reason,
    )


def decide_risk_dispatch(
    *,
    origin: ReviewOrigin,
    assessment: ReviewRiskAssessment | None,
    expected_repository: str | None = None,
    expected_pull_number: int | None = None,
    expected_head_sha: str | None = None,
    current_source: SourcePR | None = None,
) -> RiskDispatchAdvice:
    """Advise a trusted pre-admission owner; do not authorize a merge.

    For AUTO, expected identity comes only from a signed/current event and
    current_source comes from a fresh authenticated GitHub App GET *after* the
    source census. A caller must never pass PR author-provided facts here.
    A second EventStore admission/return still uses incumbent authority.
    """
    if type(origin) is not ReviewOrigin:
        raise ReviewRiskDispatchError("origin must be verified by existing ingress")
    if origin is ReviewOrigin.MANUAL_AUTHORIZED:
        return RiskDispatchAdvice(
            ReviewDispatch.USE_EXISTING_MANUAL_INGRESS, None,
            "MANUAL_INTENT_PRESERVED",
        )
    if type(assessment) is not ReviewRiskAssessment:
        return _hold("TRUSTED_CURRENT_RISK_ASSESSMENT_MISSING")
    if (type(expected_repository) is not str or _REPO_RE.fullmatch(expected_repository) is None
            or type(expected_pull_number) is not int or expected_pull_number <= 0
            or type(expected_head_sha) is not str or _SHA_RE.fullmatch(expected_head_sha) is None):
        return _hold("EXPECTED_SIGNED_SOURCE_IDENTITY_UNAVAILABLE")
    if type(current_source) is not SourcePR:
        return _hold("CURRENT_AUTHENTICATED_PR_READ_UNAVAILABLE")
    if (
        assessment.schema != SCHEMA
        or assessment.repository != expected_repository
        or assessment.pull_number != expected_pull_number
        or assessment.head_sha != expected_head_sha
        or current_source.repository != expected_repository
        or current_source.pull_number != expected_pull_number
        or current_source.head_sha != expected_head_sha
        or current_source.head_repository != expected_repository
        or current_source.base_repository != expected_repository
        or current_source.open is not True
        or current_source.draft is not False
    ):
        return _hold("SIGNED_EXACT_HEAD_OR_PR_IDENTITY_MISMATCH")
    if assessment.tier is ReviewTier.HOLD:
        return _hold("CURRENT_SOURCE_INCOMPLETE", ReviewTier.HOLD)
    bound = {
        "repository": expected_repository,
        "pull_number": expected_pull_number,
        "head_sha": expected_head_sha,
    }
    if assessment.tier in (ReviewTier.FAST, ReviewTier.STANDARD):
        # Routine code and test changes need CI/self-check, not another
        # mandatory independent worker or formal approval per edit. The
        # separate explicitly authorized manual review route is unchanged.
        return RiskDispatchAdvice(
            ReviewDispatch.SKIP_NO_REVIEW_NEEDED, assessment.tier,
            ("FAST_NO_INDEPENDENT_REVIEW_REQUIRED"
             if assessment.tier is ReviewTier.FAST
             else "STANDARD_NO_MANDATORY_INDEPENDENT_REVIEW"), **bound,
        )
    if assessment.tier is ReviewTier.CRITICAL:
        return RiskDispatchAdvice(
            ReviewDispatch.AUTO_REVIEW_ELIGIBLE, assessment.tier,
            "INDEPENDENT_REVIEW_REQUIRED", **bound,
        )
    return _hold("RISK_TIER_INVALID")


def advise_current_pr_review(
    reader: RiskGitHubReadPort,
    *,
    origin: ReviewOrigin,
    repository: str,
    pull_number: int,
    signed_head_sha: str,
) -> RiskDispatchAdvice:
    """Bounded source-census -> fresh PR read -> exact-head preflight.

    Host must first authenticate and authorize the origin and delivery, and
    bind the existing GitHub App reader. This function calls no side-effecting
    API and admits no Job. Read failures fail CLOSED, not to extra review or
    author-controlled no-review exemption.
    """
    if type(origin) is not ReviewOrigin:
        raise ReviewRiskDispatchError("origin must come from trusted ingress")
    if origin is ReviewOrigin.MANUAL_AUTHORIZED:
        return decide_risk_dispatch(origin=origin, assessment=None)
    try:
        assessment = assess_current_pr_risk(
            reader, repository=repository, pull_number=pull_number,
        )
        latest = reader.read_pr_risk_source(
            repository=repository, pull_number=pull_number,
        )
    except Exception:
        # A bounded upstream source failure is no permission to skip or admit.
        return _hold("CURRENT_AUTHENTICATED_SOURCE_UNAVAILABLE")
    return decide_risk_dispatch(
        origin=origin, assessment=assessment,
        expected_repository=repository, expected_pull_number=pull_number,
        expected_head_sha=signed_head_sha, current_source=latest,
    )
