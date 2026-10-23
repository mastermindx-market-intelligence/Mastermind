"""Transport-neutral GitHub review frames and Slack receipt contract.

Control-plane-owned definitions only. Importing this module opens no Runtime,
network, socket, credential, scheduler, integration client or database.
"""
from __future__ import annotations

import re
from typing import Protocol, runtime_checkable

from control_plane.github_review_intent import ReviewIntentDecision

FRAME_SCHEMA = "mastermind.github_review_socket_admission.v1"
RESPONSE_SCHEMA = "mastermind.github_review_socket_receipt.v1"
MAX_FRAME_BYTES = 8192
MAX_RESPONSE_BYTES = 8192
REVIEW_SLACK_CHANNEL_ID = "C0CAUK8P8S3"
MAX_PARENT_NOTICE_CHARS = 700
_PARENT_JOB_ID_RE = re.compile(r"\A[A-Za-z0-9:._-]{1,128}\Z")


class SlackReviewThreadUnavailable(RuntimeError):
    """Opaque canonical Slack thread/receipt refusal."""


@runtime_checkable
class SlackParentMessage(Protocol):
    """Read-only structural receipt from a host-authenticated Slack GET.

    The host-supplied source reader, never a webhook frame, owns authenticity.
    The protocol avoids reversing control_plane -> integrations dependencies.
    """

    ts: str
    author_user_id: str
    text: str
    thread_ts: str | None
    edited: bool
    deleted: bool


def review_parent_body(
    *, decision: ReviewIntentDecision, job_id: str,
    public_repository_names_authorized: bool = False,
) -> str:
    """One canonical deterministic parent text for publish and readback."""
    if (not isinstance(decision, ReviewIntentDecision)
            or decision.admitted is not True
            or type(job_id) is not str
            or _PARENT_JOB_ID_RE.fullmatch(job_id) is None
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
