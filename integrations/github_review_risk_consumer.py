"""Exact authenticated risk preflight for the existing GitHub review consumer.

Source-only integration. The incumbent signed ingress must call this after
origin, installation, actor and PR authorization and BEFORE creating an
Executive review Job. This adds no second webhook, retry, token, queue,
worker, source-owner, or release authority.

The existing 6-second webhook admission budget is an outer constraint. This
consumer never extends it and does not turn a slow/denied GitHub GET into an
admission or a no-review exemption.
"""
from __future__ import annotations

from collections.abc import Callable

from control_plane.github_review_intent import (
    IntentSource, PullRequestFacts, ReviewIntentDecision,
)
from control_plane.github_review_risk_dispatch import (
    ReviewDispatch,
    ReviewOrigin,
    RiskDispatchAdvice,
    advise_current_pr_review,
)
from control_plane.github_review_risk_policy import ReviewTier
from integrations.github_review_api import GitHubReviewAPI
from integrations.github_review_risk_reader import GitHubReviewRiskReader


_AUTOMATIC = frozenset({
    IntentSource.PR_LIFECYCLE,
    IntentSource.OPEN_PR_RECONCILIATION,
})
_MANUAL = frozenset({
    IntentSource.REVIEW_REQUESTED,
    IntentSource.COMMAND_COMMENT,
    IntentSource.INTENT_LABEL,
})


class GitHubRiskConsumerUnavailable(ValueError):
    """Missing host binding; no alternate reader or credential is permitted."""


class GitHubReviewRiskConsumer:
    """Use the existing bound GitHub App and live current-head verification."""

    def __init__(self, *, github: GitHubReviewAPI, repository: str) -> None:
        if type(github) is not GitHubReviewAPI or type(repository) is not str:
            raise GitHubRiskConsumerUnavailable("REVIEW_RISK_HOST_BINDING_INVALID")
        # Constructor refuses repository mismatches via the original API guard.
        self._reader = GitHubReviewRiskReader(api=github, repository=repository)
        self._repository = repository

    @staticmethod
    def _hold(reason: str) -> RiskDispatchAdvice:
        return RiskDispatchAdvice(
            action=ReviewDispatch.HOLD_UNQUALIFIED_SOURCE,
            source_tier=None,
            reason=reason,
        )

    def __call__(
        self,
        *, decision: ReviewIntentDecision, pull_request: PullRequestFacts,
        budget_check: Callable[[], None] | None = None,
    ) -> RiskDispatchAdvice:
        """Pre-admission advice, not a Runtime effect.

        The caller must already have verified signed payload/actor/host policy.
        All automatic inputs are bound to the admitted decision's exact
        source identity, never a PR body/label or caller-owned risk claim.
        Manual admitted review retains the existing authorized path and
        costs zero risk-source GETs.
        """
        if type(decision) is not ReviewIntentDecision or not decision.admitted:
            return self._hold("REVIEW_RISK_DECISION_NOT_ADMITTED")
        if decision.intent_source in _MANUAL:
            return RiskDispatchAdvice(
                action=ReviewDispatch.USE_EXISTING_MANUAL_INGRESS,
                source_tier=None,
                reason="MANUAL_INTENT_PRESERVED",
            )
        if decision.intent_source not in _AUTOMATIC:
            return self._hold("REVIEW_RISK_ORIGIN_UNSUPPORTED")
        # Only the existing signed standing-policy owner can produce an
        # automatic review requiring a zero-review exemption decision.
        if decision.policy_authority is None:
            return self._hold("REVIEW_RISK_POLICY_AUTHORITY_MISSING")
        if (
            type(pull_request) is not PullRequestFacts
            or decision.repository != self._repository
            or pull_request.repository != self._repository
            or type(decision.pull_number) is not int
            or decision.pull_number != pull_request.number
            or type(decision.frozen_head_sha) is not str
            or decision.frozen_head_sha != pull_request.head_sha
            or pull_request.state != "open"
            or pull_request.draft
        ):
            return self._hold("REVIEW_RISK_SIGNED_SOURCE_MISMATCH")

        # The admission owner supplies its original deadline guard. We never
        # create a new local timer, network transport, retry or admission.
        if budget_check is not None:
            if not callable(budget_check):
                return self._hold("REVIEW_RISK_BUDGET_GUARD_UNBOUND")
            budget_check()
        advice = advise_current_pr_review(
            self._reader,
            origin=ReviewOrigin.AUTOMATIC_POLICY,
            repository=self._repository,
            pull_number=decision.pull_number,
            signed_head_sha=decision.frozen_head_sha,
        )
        if budget_check is not None:
            budget_check()
        if advice.action in {
            ReviewDispatch.SKIP_NO_REVIEW_NEEDED,
            ReviewDispatch.AUTO_REVIEW_ELIGIBLE,
        }:
            if (
                advice.repository != decision.repository
                or advice.pull_number != decision.pull_number
                or advice.head_sha != decision.frozen_head_sha
                or advice.source_tier not in {
                    ReviewTier.FAST, ReviewTier.STANDARD, ReviewTier.CRITICAL,
                }
            ):
                return self._hold("REVIEW_RISK_SOURCE_ADVICE_MISMATCH")
        return advice
