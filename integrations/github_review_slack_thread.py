"""Slack parent/reply correlation using existing Executive event log and Relay bot.

Slack remains a nonauthoritative visibility projection. A lost Slack POST
receipt never causes another automatic write; exact recipient, thread and
one-attempt identity are recorded in the incumbent EventStore (no new table).
"""
from __future__ import annotations

import asyncio
import hashlib
import re

from control_plane.executive_runtime import Runtime
from control_plane.github_review_intent import ReviewIntentDecision
from control_plane.github_review_socket_contract import (
    REVIEW_SLACK_CHANNEL_ID as CHANNEL_ID, SlackReviewThreadUnavailable,
)
from integrations.slack_agent_dialogue.engine import SlackMessage
from integrations.slack_agent_dialogue.slack_web_api import SlackWebApiDialogueClient

_PARENT = "GITHUB_REVIEW_SLACK_PARENT_OBSERVED"
_PARENT_SEND = "GITHUB_REVIEW_SLACK_PARENT_SEND_RESERVED"
_REPLY = "GITHUB_REVIEW_SLACK_REPLY_RESERVED"
_SCHEMA = "mastermind.github_review_slack_visibility.v1"
_TS_RE = re.compile(r"\A[0-9]{10,16}\.[0-9]{6}\Z")
_ID_RE = re.compile(r"\A[A-Za-z0-9:._-]{1,128}\Z")
MAX_PARENT_NOTICE_CHARS = 700


def review_parent_body(
    *, decision: ReviewIntentDecision, job_id: str,
    public_repository_names_authorized: bool = False,
) -> str:
    """Existing Slack-owned deterministic parent text, used by host readback.

    The control plane binds this pure function through an explicit injected
    callback; there is no forbidden control_plane -> integrations import.
    """
    if (not isinstance(decision, ReviewIntentDecision)
            or decision.admitted is not True
            or type(job_id) is not str
            or _ID_RE.fullmatch(job_id) is None
            or type(public_repository_names_authorized) is not bool):
        raise SlackReviewThreadUnavailable("SLACK_PARENT_IDENTITY_INVALID")
    subject = (
        f"{decision.repository}#{decision.pull_number}"
        if public_repository_names_authorized else "authorized GitHub pull request"
    )
    return (
        "Independent review admitted through Executive/Fabric: "
        + subject + "\n"
        + f"Executive Job: {job_id}\n"
        + f"Review command: {decision.command_id}\n"
        + "Status: QUEUED (not worker START; no verdict yet)"
    )[:MAX_PARENT_NOTICE_CHARS]


class ExecutiveSlackReviewThreads:
    """One parent and at most one reply attempt for an exact review Job."""

    def __init__(self, *, runtime: Runtime) -> None:
        if not isinstance(runtime, Runtime):
            raise TypeError("existing Executive Runtime is required")
        self._runtime = runtime

    @staticmethod
    def _parent_command(decision: ReviewIntentDecision) -> str:
        if (
            not isinstance(decision, ReviewIntentDecision)
            or not decision.admitted or not decision.intent_id
        ):
            raise SlackReviewThreadUnavailable("REVIEW_INTENT_INVALID")
        return "gh-review-slack-parent:" + decision.intent_id

    @classmethod
    def _parent_send_command(cls, decision: ReviewIntentDecision) -> str:
        return "gh-review-slack-send:" + cls._parent_command(decision)

    def reserve_parent_send(
        self, *, decision: ReviewIntentDecision, job_id: str
    ) -> bool:
        """Atomic one-attempt Slack parent send right from incumbent EventStore.

        Return False for both an already reserved attempt and an already
        observed legacy parent. A send whose ACK was lost is NOT retryable.
        """
        if type(job_id) is not str or _ID_RE.fullmatch(job_id) is None:
            raise SlackReviewThreadUnavailable("SLACK_PARENT_JOB_INVALID")
        parent_key = self._parent_command(decision)
        send_key = self._parent_send_command(decision)
        material = {
            "schema": _SCHEMA, "job_id": job_id,
            "review_command_id": decision.command_id,
            "head_sha": decision.frozen_head_sha, "channel_id": CHANNEL_ID,
        }
        with self._runtime.store.transaction() as conn:
            observed = self._runtime.store.get_event_by_command_id(
                parent_key, connection=conn
            )
            if observed is not None:
                if (observed.event_type != _PARENT
                        or observed.payload.get("job_id") != job_id
                        or observed.payload.get("review_command_id") != decision.command_id
                        or observed.payload.get("head_sha") != decision.frozen_head_sha
                        or observed.payload.get("channel_id") != CHANNEL_ID):
                    raise SlackReviewThreadUnavailable("SLACK_PARENT_EFFECT_CONFLICT")
                return False
            existing = self._runtime.store.get_event_by_command_id(
                send_key, connection=conn
            )
            if existing is not None:
                if existing.event_type != _PARENT_SEND or existing.payload != material:
                    raise SlackReviewThreadUnavailable("SLACK_PARENT_SEND_CONFLICT")
                return False
            self._runtime.store.append_event(
                conn, aggregate_type="github_review_slack",
                aggregate_id=send_key, event_type=_PARENT_SEND,
                command_id=send_key, actor="github-review-slack-relay",
                payload=material,
            )
            return True

    def record_parent(
        self, *, decision: ReviewIntentDecision, job_id: str, message: SlackMessage
    ) -> None:
        if (
            not isinstance(message, SlackMessage)
            or message.thread_ts is not None or message.edited or message.deleted
            or not isinstance(job_id, str) or not job_id
        ):
            raise SlackReviewThreadUnavailable("SLACK_PARENT_NOT_VERIFIED")
        command_id = self._parent_command(decision)
        material = {
            "schema": _SCHEMA, "job_id": job_id,
            "review_command_id": decision.command_id,
            "head_sha": decision.frozen_head_sha,
            "channel_id": CHANNEL_ID, "thread_ts": message.ts,
        }
        with self._runtime.store.transaction() as conn:
            found = self._runtime.store.get_event_by_command_id(
                command_id, connection=conn
            )
            if found is not None:
                if found.event_type != _PARENT or found.payload != material:
                    raise SlackReviewThreadUnavailable("SLACK_PARENT_EFFECT_CONFLICT")
                return
            # No unsolicited parent observation without the send reservation
            # created atomically *before* Slack POST.
            expected = {
                "schema": _SCHEMA, "job_id": job_id,
                "review_command_id": decision.command_id,
                "head_sha": decision.frozen_head_sha, "channel_id": CHANNEL_ID,
            }
            reserved = self._runtime.store.get_event_by_command_id(
                self._parent_send_command(decision), connection=conn
            )
            if (reserved is None or reserved.event_type != _PARENT_SEND
                    or reserved.payload != expected):
                raise SlackReviewThreadUnavailable("SLACK_PARENT_SEND_UNRESERVED")
            self._runtime.store.append_event(
                conn, aggregate_type="github_review_slack",
                aggregate_id=command_id,
                event_type=_PARENT, command_id=command_id,
                actor="github-review-slack-relay",
                payload=material,
            )

    def parent_thread(
        self, *, decision: ReviewIntentDecision, job_id: str
    ) -> str | None:
        found = self._runtime.store.get_event_by_command_id(
            self._parent_command(decision)
        )
        if found is None:
            return None
        material = found.payload
        if (
            found.event_type != _PARENT or material.get("schema") != _SCHEMA
            or material.get("job_id") != job_id
            or material.get("review_command_id") != decision.command_id
            or material.get("head_sha") != decision.frozen_head_sha
            or material.get("channel_id") != CHANNEL_ID
            or not isinstance(material.get("thread_ts"), str)
            or _TS_RE.fullmatch(material["thread_ts"]) is None
        ):
            raise SlackReviewThreadUnavailable("SLACK_PARENT_EFFECT_CONFLICT")
        return material["thread_ts"]

    def reserve_result_reply(
        self, *, decision: ReviewIntentDecision, job_id: str, review_id: str
    ) -> str | None:
        thread = self.parent_thread(decision=decision, job_id=job_id)
        if thread is None:
            return None
        if not isinstance(review_id, str) or _ID_RE.fullmatch(review_id) is None:
            raise SlackReviewThreadUnavailable("GITHUB_REVIEW_ID_INVALID")
        key = "gh-review-slack-result:" + hashlib.sha256(
            self._parent_command(decision).encode("utf-8")
        ).hexdigest()[:32]
        material = {
            "schema": _SCHEMA, "job_id": job_id,
            "review_command_id": decision.command_id, "channel_id": CHANNEL_ID,
            "thread_ts": thread, "github_review_id": review_id,
        }
        with self._runtime.store.transaction() as conn:
            found = self._runtime.store.get_event_by_command_id(
                key, connection=conn
            )
            if found is not None:
                if found.event_type != _REPLY or found.payload != material:
                    raise SlackReviewThreadUnavailable("SLACK_REPLY_EFFECT_CONFLICT")
                # A previous post may be in flight or its reply lost. No retry.
                return None
            self._runtime.store.append_event(
                conn, aggregate_type="github_review_slack",
                aggregate_id=key,
                event_type=_REPLY, command_id=key,
                actor="github-review-slack-relay", payload=material,
            )
        return thread


class SlackReviewResultNotifier:
    """One attempt to post a formal-review receipt to its original thread."""

    def __init__(
        self, *,
        client: SlackWebApiDialogueClient, threads: ExecutiveSlackReviewThreads
    ) -> None:
        if not isinstance(client, SlackWebApiDialogueClient):
            raise TypeError("existing Slack dialogue client required")
        if not isinstance(threads, ExecutiveSlackReviewThreads):
            raise TypeError("existing Executive thread projection required")
        self._client = client
        self._threads = threads

    def notify_result(
        self, *, decision: ReviewIntentDecision, job_id: str, review_id: str
    ) -> bool:
        thread = self._threads.reserve_result_reply(
            decision=decision, job_id=job_id, review_id=review_id,
        )
        if thread is None:
            return False
        body = (
            "Independent review published on GitHub.\n"
            f"Executive Job: {job_id}\n"
            f"Formal GitHub review ID: {review_id}\n"
            "Receipt: GitHub confirmed; no automatic merge or approval."
        )
        try:
            asyncio.run(self._client.post_reply(
                channel_id=CHANNEL_ID, thread_ts=thread, text=body
            ))
        except Exception:
            # The one-attempt event remains reserved; no retry.
            raise SlackReviewThreadUnavailable(
                "SLACK_REVIEW_RESULT_EFFECT_UNKNOWN"
            ) from None
        return True
