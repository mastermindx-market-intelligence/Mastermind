"""Exact-source risk preflight bound to the incumbent GitHub App client.

This adapter owns no webhook, credential, queue, reviewer, worker or lifecycle.
The existing admission owner has already verified signed intent, enrollment
and actor authorization. It must call this before Executive Job creation.
"""
from __future__ import annotations

from control_plane.github_review_intent import (
    IntentSource, ReviewIntentDecision,
)
from control_plane.github_review_risk_dispatch import (
    ReviewOrigin, RiskDispatchAdvice, advise_current_pr_review,
)
from integrations.github_review_api import GitHubReviewAPI
from integrations.github_review_risk_reader import GitHubReviewRiskReader


class GitHubReviewRiskGate:
    """One GitHub App installation-scoped source reader; no extra HTTP client."""

    def __init__(self, *, github: GitHubReviewAPI, repository: str) -> None:
        if type(github) is not GitHubReviewAPI:
            raise ValueError("REVIEW_RISK_GITHUB_CLIENT_UNBOUND")
        self._reader = GitHubReviewRiskReader(api=github, repository=repository)
        self._repository = repository

    def __call__(self, decision: ReviewIntentDecision) -> RiskDispatchAdvice:
        if (type(decision) is not ReviewIntentDecision or not decision.admitted
                or decision.repository != self._repository
                or decision.intent_source not in {
                    IntentSource.PR_LIFECYCLE,
                    IntentSource.OPEN_PR_RECONCILIATION,
                }):
            raise ValueError("REVIEW_RISK_VERIFIED_AUTOMATIC_DECISION_REQUIRED")
        return advise_current_pr_review(
            self._reader,
            origin=ReviewOrigin.AUTOMATIC_POLICY,
            repository=decision.repository,
            pull_number=decision.pull_number,
            signed_head_sha=decision.frozen_head_sha,
        )
