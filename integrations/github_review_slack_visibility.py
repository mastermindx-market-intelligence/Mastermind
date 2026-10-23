"""Review admission visibility through the EXISTING exact-channel Slack client.

This is never a task queue or admission authority; Slack cannot originate
an Executive Job. Host must inject the already-enrolled Mastermind Executive
Relay dialogue client bound specifically to the review channel. The original
A2 #agent-dispatch binding must remain untouched.
"""
from __future__ import annotations

import asyncio

from control_plane.github_review_intent import ReviewIntentDecision
from integrations.slack_agent_dialogue.slack_web_api import SlackWebApiDialogueClient
from integrations.github_review_slack_thread import (
    ExecutiveSlackReviewThreads, review_parent_body, MAX_PARENT_NOTICE_CHARS,
)
from integrations.github_review_socket_client import ExecutiveReviewSocketClient

REVIEW_CHANNEL_ID = "C0CAUK8P8S3"
MAX_NOTICE_CHARS = MAX_PARENT_NOTICE_CHARS


class SlackReviewVisibility:
    def __init__(
        self,
        *,
        client: SlackWebApiDialogueClient,
        channel_id: str = REVIEW_CHANNEL_ID,
        public_repository_names_authorized: bool = False,
        threads: ExecutiveSlackReviewThreads | ExecutiveReviewSocketClient | None = None,
    ) -> None:
        if not isinstance(client, SlackWebApiDialogueClient):
            raise ValueError("existing Slack dialogue client must be bound")
        if threads is not None and not isinstance(
            threads, (ExecutiveSlackReviewThreads, ExecutiveReviewSocketClient)
        ):
            raise ValueError("canonical Executive Slack parent recorder required")
        if channel_id != REVIEW_CHANNEL_ID:
            raise ValueError("review status must use the exact enrolled channel")
        self._client = client
        self._channel_id = channel_id
        self._publish_repo_names = public_repository_names_authorized
        self._threads = threads

    def notify_review_admitted(
        self, *, summary: str, decision: ReviewIntentDecision, job_id: str | None
    ) -> None:
        if not decision.admitted or not isinstance(job_id, str) or not job_id:
            raise ValueError("review must already be admitted by Executive OS")
        # The exact template is shared with installed Slack readback. Never
        # echo webhook title/body or introduce a second renderer on the host.
        message = review_parent_body(
            decision=decision, job_id=job_id,
            public_repository_names_authorized=self._publish_repo_names,
        )
        # Called inside the ingress' to_thread, not inside an existing event
        # loop. Reuse the real client's exact-channel, validated write receipt.
        receipt = asyncio.run(self._client.post_parent(channel_id=self._channel_id, text=message))
        if self._threads is not None:
            self._threads.record_parent(
                decision=decision, job_id=job_id, message=receipt,
            )

    def notify_review_refused(
        self, *, summary: str, decision: ReviewIntentDecision
    ) -> None:
        # Refusals are not events to broadcast to a public channel:
        # doing so would leak repository or actor existence.
        return
