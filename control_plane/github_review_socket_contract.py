"""Transport-neutral GitHub review frames and Slack receipt contract.

Control-plane-owned definitions only. Importing this module opens no Runtime,
network, socket, credential, scheduler, integration client or database.
"""
from __future__ import annotations

import dataclasses
import math
import time
from collections.abc import Callable
from typing import Protocol, runtime_checkable

from control_plane.github_review_intent import ReviewIntentDecision

FRAME_SCHEMA = "mastermind.github_review_socket_admission.v1"
RESPONSE_SCHEMA = "mastermind.github_review_socket_receipt.v1"
MAX_FRAME_BYTES = 8192
MAX_RESPONSE_BYTES = 8192
REVIEW_SLACK_CHANNEL_ID = "C0CAUK8P8S3"
MAX_SOURCE_OBSERVATION_SECONDS = 3.0


@dataclasses.dataclass(frozen=True)
class PreparedReviewSourceCheck:
    """Host-only, request-local source observation; never accepted from a frame.

    Network reads precede construction. The binding callback is an incumbent
    host's LOCAL configuration/authorization fence and must perform no I/O.
    Repeated checks never renew the original observation deadline.
    """

    decision: ReviewIntentDecision
    observed_at: float
    deadline: float
    current_binding_guard: Callable[[], None] = dataclasses.field(repr=False, compare=False)
    clock: Callable[[], float] = dataclasses.field(default=time.monotonic, repr=False, compare=False)

    def __post_init__(self) -> None:
        if type(self.decision) is not ReviewIntentDecision:
            raise ValueError("REVIEW_PREPARED_SOURCE_DECISION_INVALID")
        closed = ReviewIntentDecision.from_admitted_dict(self.decision.to_dict())
        if closed != self.decision:
            raise ValueError("REVIEW_PREPARED_SOURCE_DECISION_INVALID")
        if (type(self.observed_at) not in {int, float}
                or type(self.deadline) not in {int, float}
                or not math.isfinite(self.observed_at) or not math.isfinite(self.deadline)
                or self.observed_at < 0 or self.deadline <= self.observed_at
                or self.deadline > self.observed_at + MAX_SOURCE_OBSERVATION_SECONDS
                or not callable(self.current_binding_guard) or not callable(self.clock)):
            raise ValueError("REVIEW_PREPARED_SOURCE_FRESHNESS_INVALID")

    def _within_observation(self) -> None:
        now = self.clock()
        if (type(now) not in {int, float} or not math.isfinite(now)
                or now < self.observed_at or now >= self.deadline):
            raise ValueError("REVIEW_SOURCE_OBSERVATION_EXPIRED")

    def verify(self, decision: ReviewIntentDecision) -> None:
        if type(decision) is not ReviewIntentDecision or decision != self.decision:
            raise ValueError("REVIEW_PREPARED_SOURCE_IDENTITY_MISMATCH")
        self._within_observation()
        if self.current_binding_guard() is not None:
            raise ValueError("REVIEW_SOURCE_BINDING_REVOKED")
        self._within_observation()


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
