"""One-shot GitHub review return consumer over the existing canonical owners.

The Executive host invokes this only after its own Job completion/return
observation; this is NOT a watcher, poller, scheduler, queue or review
adjudicator. It never fabricates reviewer evidence or an approving GitHub verb.
"""
from __future__ import annotations

import dataclasses
from typing import Protocol

from control_plane.executive_runtime import Runtime
from control_plane.github_review_intent import ReviewIntentDecision
from control_plane.github_review_intent_ingress import (
    PublishState, ReviewPublishOutcome, ReviewResultPort,
    ReviewVerificationRefused, publish_verified_review,
)
from control_plane.github_review_publication_record import (
    ExecutiveReviewPublicationRecord,
)
from integrations.github_review_api import GitHubReviewAPI
from integrations.github_review_slack_thread import (
    SlackReviewResultNotifier, SlackReviewThreadUnavailable,
)


@dataclasses.dataclass(frozen=True)
class ReviewReturnReceipt:
    publication: ReviewPublishOutcome
    slack_receipt: str

    def to_dict(self) -> dict:
        return {
            "schema": "mastermind.github_review_return.v1",
            "github": self.publication.to_dict(),
            "slack": self.slack_receipt,
        }


class GitHubReviewReturn:
    def __init__(
        self, *,
        runtime: Runtime,
        github: GitHubReviewAPI,
        results: ReviewResultPort,
        publication_guard,
        slack: SlackReviewResultNotifier | None = None,
    ) -> None:
        if not isinstance(runtime, Runtime) or not isinstance(github, GitHubReviewAPI):
            raise TypeError("canonical Runtime and authenticated GitHub API are required")
        if not isinstance(results, ReviewResultPort):
            raise TypeError("existing verified review result port is required")
        if not callable(publication_guard):
            raise TypeError("publisher authorization guard must be bound")
        if slack is not None and not isinstance(slack, SlackReviewResultNotifier):
            raise TypeError("existing Slack result notifier must be bound")
        self._runtime = runtime
        self._github = github
        self._results = results
        self._guard = publication_guard
        self._slack = slack

    def deliver(
        self, *, decision: ReviewIntentDecision, job_id: str
    ) -> ReviewReturnReceipt:
        if not isinstance(decision, ReviewIntentDecision) or not decision.admitted:
            raise ReviewVerificationRefused("admitted review intent required")
        if not isinstance(job_id, str) or not job_id:
            raise ReviewVerificationRefused("canonical review Job required")
        # A completed Job for PR A must never be used to publish on PR B.
        # Bind the incoming decision to the immutable original Executive
        # JOB_CREATED source receipt before any GitHub API read or POST.
        event = self._runtime.store.get_event_by_command_id(
            decision.command_id or ""
        )
        if (
            event is None or event.event_type != "JOB_CREATED"
            or event.job_id != job_id
            or not isinstance(event.payload.get("provenance"), dict)
        ):
            raise ReviewVerificationRefused("REVIEW_JOB_SOURCE_IDENTITY_MISMATCH")
        provenance = event.payload["provenance"]
        if (
            provenance.get("schema") != "mastermind.github_review_runtime_admission.v1"
            or provenance.get("repository") != decision.repository
            or provenance.get("pull_number") != decision.pull_number
            or provenance.get("frozen_head_sha") != decision.frozen_head_sha
            or provenance.get("command_id") != decision.command_id
            or provenance.get("actor") != decision.actor
        ):
            raise ReviewVerificationRefused("REVIEW_JOB_SOURCE_IDENTITY_MISMATCH")
        # VerifiedReviewResult/its source checks still live in the existing
        # result owner's port; this layer never synthesizes a worker verdict.
        publication = ExecutiveReviewPublicationRecord(
            runtime=self._runtime, transport=self._github,
            job_id=job_id, publication_guard=self._guard,
        )
        outcome = publish_verified_review(
            decision=decision, job_id=job_id, results=self._results,
            publications=publication, pull_requests=self._github,
            readback=self._github,
        )
        visibility = "NOT_APPLICABLE"
        if outcome.state in {PublishState.PUBLISHED, PublishState.ALREADY_PUBLISHED}:
            review_id = outcome.review_id
            if review_id is None:
                # A prior confirmed exact effect is inside the original
                # Executive events ledger, not an invented publication store.
                record = self._runtime.store.get_event_by_command_id(
                    outcome.publication_command_id + ":confirmed"
                )
                if record is not None:
                    candidate = record.payload.get("review_id")
                    if isinstance(candidate, str):
                        review_id = candidate
            if self._slack is not None and review_id is not None:
                try:
                    wrote = self._slack.notify_result(
                        decision=decision, job_id=job_id, review_id=review_id,
                    )
                    visibility = "POSTED" if wrote else "NOT_SENT_OR_ALREADY_ATTEMPTED"
                except SlackReviewThreadUnavailable:
                    # GitHub review publication remains true even when Slack's
                    # separate transport ACK/effect is unknowable.
                    visibility = "EFFECT_UNKNOWN"
            elif self._slack is not None:
                visibility = "REVIEW_ID_UNVERIFIED"
        return ReviewReturnReceipt(publication=outcome, slack_receipt=visibility)
