"""Pre-admission review decision for the incumbent GitHub/Executive ingress.

This is a pure projection, NOT an ingress, authorization, auto-review trigger,
queue, new review registry or release decision. Only a verified *automatic*
lifecycle or repository-policy event uses the risk fast lane. Explicit manual
review requests retain their incumbent signed/permission-gated behavior.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from control_plane.github_review_risk_policy import (
    ReviewRiskAssessment,
    ReviewTier,
)


class ReviewRiskDispatchError(ValueError):
    """Refuse missing or untrusted typed risk/origin facts."""


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


def decide_risk_dispatch(
    *, origin: ReviewOrigin, assessment: ReviewRiskAssessment | None
) -> RiskDispatchAdvice:
    """Return an advisory pre-admission action; never mutates Executive state.

    The existing signed webhook/host policy and current actor permission must
    first verify `origin`. A model or PR author cannot supply it as authority.
    A caller must not infer a review PASS, approval or merge from this advice.
    """
    if type(origin) is not ReviewOrigin:
        raise ReviewRiskDispatchError("origin must come from the verified ingress")
    if origin is ReviewOrigin.MANUAL_AUTHORIZED:
        # Do not weaken or duplicate the original signed manual review path.
        return RiskDispatchAdvice(
            ReviewDispatch.USE_EXISTING_MANUAL_INGRESS, None,
            "MANUAL_INTENT_PRESERVED",
        )
    if type(assessment) is not ReviewRiskAssessment:
        return RiskDispatchAdvice(
            ReviewDispatch.HOLD_UNQUALIFIED_SOURCE, None,
            "TRUSTED_CURRENT_RISK_ASSESSMENT_MISSING",
        )
    if assessment.tier is ReviewTier.HOLD:
        return RiskDispatchAdvice(
            ReviewDispatch.HOLD_UNQUALIFIED_SOURCE, ReviewTier.HOLD,
            "CURRENT_SOURCE_INCOMPLETE",
        )
    if assessment.tier is ReviewTier.FAST:
        return RiskDispatchAdvice(
            ReviewDispatch.SKIP_NO_REVIEW_NEEDED, ReviewTier.FAST,
            "FAST_NO_INDEPENDENT_REVIEW_REQUIRED",
        )
    if assessment.tier in (ReviewTier.STANDARD, ReviewTier.CRITICAL):
        return RiskDispatchAdvice(
            ReviewDispatch.AUTO_REVIEW_ELIGIBLE, assessment.tier,
            "INDEPENDENT_REVIEW_REQUIRED",
        )
    raise ReviewRiskDispatchError("unknown risk tier")
