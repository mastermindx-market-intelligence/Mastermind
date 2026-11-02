"""Transport-neutral GitHub review frames and Slack receipt contract.

Control-plane-owned definitions only. Importing this module opens no Runtime,
network, socket, credential, scheduler, integration client or database.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

FRAME_SCHEMA = "mastermind.github_review_socket_admission.v1"
RESPONSE_SCHEMA = "mastermind.github_review_socket_receipt.v1"
MAX_FRAME_BYTES = 8192
MAX_RESPONSE_BYTES = 8192
REVIEW_SLACK_CHANNEL_ID = "C0CAUK8P8S3"


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
