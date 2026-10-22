"""Ingress orchestration for authenticated independent GitHub PR review.

This module owns no webhook server, HTTP route, GitHub client, GitHub App
credential, installation token, queue, watcher, scheduler, database, table,
lifecycle, retry plane, Slack transport, or review publisher.  It is the thin
composition layer that walks one delivery through the existing owners:

    verify delivery  ->  :mod:`control_plane.github_review_intent` (pure)
    re-read the PR   ->  ``PullRequestReadPort``      (authenticated read)
    decide intent    ->  :mod:`control_plane.github_review_intent` (pure)
    admit one run    ->  ``FabricJobAdmissionPort``   (existing ledger)
    make visible     ->  ``VisibilityPort``           (existing Slack/GitHub)
    publish a review ->  ``ReviewResultPort`` + ``ReviewPublicationPort``

Every port is a separately testable interface.  No concrete transport ships
here: the production GitHub App installation, its webhook secret, its Slack
token, and its reviewer identity are human-administered gates, and binding them
belongs to the host that already owns those credentials.  A missing port is a
typed refusal, never a fallback to an unauthenticated client.

Fencing laws
------------
* **Idempotency is the existing ledger's.**  The admission identity is the
  existing ``events.command_id`` UNIQUE index.  This module keeps no run
  registry, no cache, and no lock.
* **Head freeze.**  A run is admitted against one exact head SHA and every
  publication re-reads the PR and fails closed if that head moved.
* **No unfenced auto-approval.**  A ``PASS`` verdict publishes a *comment*;
  this module mints no ``APPROVE`` and no merge path at all.
* **Formal review by a genuinely separate worker.**  Publication refuses a
  result whose reviewer is the builder, or whose reviewer identity is unknown.
* **A publish retry is not a second review.**  Publication carries its own
  deterministic command id so a retry reconciles instead of double-posting.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
from collections.abc import Mapping
from enum import Enum
from typing import Protocol, runtime_checkable

from control_plane.github_review_intent import (
    REVIEW_VERDICTS,
    SUPPORTED_EVENTS,
    IntentSignal,
    PullRequestFacts,
    ReviewIntentDecision,
    ReviewIntentError,
    ReviewIntentPolicy,
    ReviewIntentRefusal,
    ReviewIntentSignatureError,
    build_review_objective,
    decide_review_intent,
    delivery_command_id,
    extract_intent_signal,
    intent_channel_for,
    parse_webhook_envelope,
    verify_frozen_head,
    verify_webhook_signature,
)


SCHEMA = "mastermind.github_review_intent_ingress.v1"

#: The GitHub review body verb for each incumbent verdict.  ``PASS`` maps to a
#: comment, never an approval: this ingress has no approval path at all.
REVIEW_VERDICT_EVENTS = {
    "PASS": "COMMENT",
    "REQUEST_CHANGES": "REQUEST_CHANGES",
    "BLOCKED_BY_CURRENT_SOURCE": "COMMENT",
}

MAX_VISIBILITY_SUMMARY_CHARS = 400
MAX_REVIEW_SUMMARY_CHARS = 16_000


class ReviewIngressError(RuntimeError):
    """The ingress could not complete one delivery."""


class ReviewIngressUnavailable(ReviewIngressError):
    """A required port is not bound on this host.  Fails closed."""


class ReviewVerificationRefused(ReviewIngressError):
    """A review result is not publishable as a formal GitHub review."""


class AdmissionState(str, Enum):
    ADMITTED = "ADMITTED"
    ALREADY_ADMITTED = "ALREADY_ADMITTED"
    REFUSED = "REFUSED"


class PublishState(str, Enum):
    PUBLISHED = "PUBLISHED"
    ALREADY_PUBLISHED = "ALREADY_PUBLISHED"
    REFUSED = "REFUSED"


# ---------------------------------------------------------------------------
# ports — the separately testable adapter interfaces
# ---------------------------------------------------------------------------


@runtime_checkable
class PullRequestReadPort(Protocol):
    """Exact PR facts from an installation-scoped authenticated GitHub read.

    Implementations mint a short-lived installation token from the configured
    GitHub App and call ``GET /repos/{repo}/pulls/{number}``.  This module never
    chooses the app, the installation, the host, or the credential.
    """

    def read_pull_request(self, *, repository: str, pull_number: int) -> PullRequestFacts:
        """Return the exact current PR facts, or raise."""


@runtime_checkable
class FabricJobAdmissionPort(Protocol):
    """The existing canonical Executive/Fabric ledger.

    Implementations bind to ``control_plane.executive_runtime``'s Job registry:
    ``admit_review_intent`` calls ``create_job(..., command_id=decision.command_id)``
    so the ``events.command_id`` UNIQUE index settles duplicates, and
    ``admitted_command_ids`` reads that same index back.  The Fabric owns
    Job/Attempt/Worker/lease authority; this module never creates, claims,
    retries, or completes any of them.
    """

    def admitted_command_ids(self) -> frozenset[str]:
        """Read the existing ledger's admitted command ids."""

    def admit_review_intent(
        self, *, decision: ReviewIntentDecision, objective: str
    ) -> str:
        """Admit exactly one run under ``decision.command_id``; return its job id.

        An identical retry returns the existing job id.  Implementations must
        not mint a second job, a second attempt, or a second worker claim.
        """


@runtime_checkable
class VisibilityPort(Protocol):
    """Slack (and optionally GitHub) visibility for one admitted or refused run.

    Implementations reuse the existing Slack Web API client in
    ``integrations.slack_agent_dialogue.slack_web_api``.  Visibility is never
    load-bearing: a failure here is recorded, never raised, and never causes a
    second admission.
    """

    def notify_review_admitted(
        self, *, summary: str, decision: ReviewIntentDecision, job_id: str | None
    ) -> None:
        ...

    def notify_review_refused(self, *, summary: str, decision: ReviewIntentDecision) -> None:
        ...


@dataclasses.dataclass(frozen=True)
class VerifiedReviewResult:
    """A terminal review result that cleared the existing verification owners.

    ``reviewer_worker_id`` and ``builder_worker_id`` are the Fabric worker
    identities.  A formal review requires two genuinely different ones.
    """

    job_id: str
    attempt_id: str
    verdict: str
    reviewer_worker_id: str
    builder_worker_id: str
    summary: str
    result_digest: str


@runtime_checkable
class ReviewResultPort(Protocol):
    """Read a terminal review result through the existing verification owners.

    Implementations bind to ``Runtime.validated_role_completion`` and
    ``control_plane.fabric_result_projection.project_fabric_role_result``, and
    return ``None`` unless the projected receipt state is ``SAME``.  A result
    that is not terminal, or not independently verified, is ``None``.
    """

    def load_verified_result(self, *, job_id: str) -> VerifiedReviewResult | None:
        ...


@runtime_checkable
class ReviewPublicationPort(Protocol):
    """Publish the formal GitHub review, exactly once per command id."""

    def published_command_ids(self) -> frozenset[str]:
        ...

    def publish_review(
        self,
        *,
        publication_command_id: str,
        repository: str,
        pull_number: int,
        head_sha: str,
        event: str,
        body: str,
    ) -> str:
        """Submit one formal review; return its review id.

        An identical retry returns the existing review id rather than posting a
        second review.
        """


# ---------------------------------------------------------------------------
# outcomes
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class ReviewIngressOutcome:
    state: AdmissionState
    decision: ReviewIntentDecision
    job_id: str | None = None
    visibility_error: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": SCHEMA,
            "state": self.state.value,
            "decision": self.decision.to_dict(),
            "job_id": self.job_id,
            "visibility_error": self.visibility_error,
        }


@dataclasses.dataclass(frozen=True)
class ReviewPublishOutcome:
    state: PublishState
    publication_command_id: str
    review_id: str | None = None
    refusal: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": SCHEMA,
            "state": self.state.value,
            "publication_command_id": self.publication_command_id,
            "review_id": self.review_id,
            "refusal": self.refusal,
        }


def _require(port: object, *, name: str) -> object:
    if port is None:
        raise ReviewIngressUnavailable(f"{name} is not bound on this host")
    return port


def _visibility_summary(decision: ReviewIntentDecision) -> str:
    if decision.admitted:
        channel = None if decision.intent_source is None else decision.intent_source.value
        return (
            f"independent review admitted: {decision.repository}#{decision.pull_number} "
            f"via {channel} by {decision.actor} at {decision.frozen_head_sha}"
        )[:MAX_VISIBILITY_SUMMARY_CHARS]
    reason = "UNKNOWN" if decision.refusal is None else decision.refusal.value
    return (
        f"independent review refused ({reason}): "
        f"{decision.repository}#{decision.pull_number} delivery "
        f"{decision.delivery_command_id}"
    )[:MAX_VISIBILITY_SUMMARY_CHARS]


def _notify(
    visibility: VisibilityPort | None, decision: ReviewIntentDecision, *, job_id: str | None
) -> str | None:
    """Visibility never gates an admission and never re-raises."""

    if visibility is None:
        return None
    summary = _visibility_summary(decision)
    try:
        if decision.admitted:
            visibility.notify_review_admitted(
                summary=summary, decision=decision, job_id=job_id
            )
        else:
            visibility.notify_review_refused(summary=summary, decision=decision)
    except Exception as exc:  # noqa: BLE001 - visibility is explicitly non-gating
        return f"{type(exc).__name__}: {exc}"
    return None


def _simple_refusal(
    *,
    refusal: ReviewIntentRefusal,
    delivery_id: str,
    repository: str,
    pull_number: int,
) -> ReviewIntentDecision:
    """A refusal decided before any PR read, ledger write, or objective build."""

    return ReviewIntentDecision(
        admitted=False,
        refusal=refusal,
        intent_source=None,
        intent_id=None,
        command_id=None,
        delivery_command_id=delivery_command_id(delivery_id),
        repository=repository,
        pull_number=pull_number,
        frozen_head_sha=None,
        actor=None,
    )


def _parse_delivery(
    *,
    secret: str,
    body: bytes,
    delivery_id: str,
    event: str,
    signature_header: str,
) -> tuple[object, IntentSignal | None]:
    """Signature-verify, then read routing facts.  The order is load-bearing.

    Returns a ``None`` signal when the delivery carries no supported intent
    channel, so an unrelated event is *refused by name* rather than raising
    and crashing the ingress.
    """

    verify_webhook_signature(secret=secret, body=body, signature_header=signature_header)
    parsed = json.loads(body.decode("utf-8"))
    if not isinstance(parsed, Mapping):
        raise ReviewIntentError("delivery body must be a JSON object")
    envelope = parse_webhook_envelope(delivery_id=delivery_id, event=event, body=parsed)
    if intent_channel_for(envelope.event, envelope.action) is None:
        return envelope, None
    signal = extract_intent_signal(
        body=parsed, event=envelope.event, action=envelope.action
    )
    return envelope, signal


def admit_review_intent(
    *,
    secret: str,
    body: bytes,
    delivery_id: str,
    event: str,
    signature_header: str,
    pull_number: int,
    policy: ReviewIntentPolicy,
    pull_requests: PullRequestReadPort,
    fabric: FabricJobAdmissionPort,
    visibility: VisibilityPort | None = None,
) -> ReviewIngressOutcome:
    """Walk one signed delivery to at most one admitted review run."""

    pull_read = _require(pull_requests, name="PullRequestReadPort")
    fabric_port = _require(fabric, name="FabricJobAdmissionPort")
    assert isinstance(pull_read, PullRequestReadPort)
    assert isinstance(fabric_port, FabricJobAdmissionPort)

    try:
        envelope, signal = _parse_delivery(
            secret=secret,
            body=body,
            delivery_id=delivery_id,
            event=event,
            signature_header=signature_header,
        )
    except ReviewIntentSignatureError:
        # A bad signature never reaches the allowlist, the PR read, the ledger,
        # or any visibility surface: nothing about it is trustworthy enough to
        # report, and reporting it would leak a probe oracle.
        raise
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ReviewIngressError(f"delivery body is not decodable JSON: {exc}") from exc

    if signal is None:
        # An unrelated delivery never earns a GitHub read, a ledger write, or a
        # visibility line that could be read as review activity.
        decision = _simple_refusal(
            refusal=(
                ReviewIntentRefusal.EVENT_NOT_SUPPORTED
                if envelope.event not in SUPPORTED_EVENTS
                else ReviewIntentRefusal.ACTION_NOT_SUPPORTED
            ),
            delivery_id=delivery_id,
            repository=envelope.repository,
            pull_number=pull_number,
        )
        return ReviewIngressOutcome(
            state=AdmissionState.REFUSED,
            decision=decision,
            visibility_error=_notify(visibility, decision, job_id=None),
        )

    if envelope.repository not in policy.repositories:
        decision = _simple_refusal(
            refusal=ReviewIntentRefusal.REPOSITORY_NOT_ALLOWLISTED,
            delivery_id=delivery_id,
            repository=envelope.repository,
            pull_number=pull_number,
        )
        return ReviewIngressOutcome(
            state=AdmissionState.REFUSED,
            decision=decision,
            visibility_error=_notify(visibility, decision, job_id=None),
        )

    pull_request = pull_read.read_pull_request(
        repository=envelope.repository, pull_number=pull_number
    )
    if not isinstance(pull_request, PullRequestFacts):
        raise ReviewIngressError("PullRequestReadPort returned a non-exact fact shape")

    decision = decide_review_intent(
        envelope=envelope,
        policy=policy,
        pull_request=pull_request,
        signal=signal,
        admitted_command_ids=fabric_port.admitted_command_ids(),
    )

    if decision.refusal is ReviewIntentRefusal.ALREADY_ADMITTED:
        return ReviewIngressOutcome(
            state=AdmissionState.ALREADY_ADMITTED,
            decision=decision,
            visibility_error=_notify(visibility, decision, job_id=None),
        )
    if not decision.admitted:
        return ReviewIngressOutcome(
            state=AdmissionState.REFUSED,
            decision=decision,
            visibility_error=_notify(visibility, decision, job_id=None),
        )

    objective = build_review_objective(
        pull_request=pull_request, intent_source=decision.intent_source
    )
    job_id = fabric_port.admit_review_intent(decision=decision, objective=objective)
    return ReviewIngressOutcome(
        state=AdmissionState.ADMITTED,
        decision=decision,
        job_id=job_id,
        visibility_error=_notify(visibility, decision, job_id=job_id),
    )


# ---------------------------------------------------------------------------
# publication
# ---------------------------------------------------------------------------


def publication_command_id(
    *, repository: str, pull_number: int, head_sha: str, job_id: str
) -> str:
    """Deterministic publication identity bound to job and frozen head.

    A retry of the same verified review therefore reconciles to the same
    publication command instead of posting a second formal review.
    """

    material = json.dumps(
        {
            "domain": "mastermind.github_review_intent.publication.v1",
            "repository": repository,
            "pull_number": pull_number,
            "head_sha": head_sha,
            "job_id": job_id,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("ascii")
    return f"gh-review-publish:{hashlib.sha256(material).hexdigest()[:32]}"


def render_review_body(
    *, result: VerifiedReviewResult, repository: str, pull_number: int
) -> str:
    """Render the formal review body from verified facts only."""

    return "\n".join(
        (
            f"Verdict: {result.verdict}",
            f"Repository: {repository}#{pull_number}",
            f"Reviewed job: {result.job_id}",
            f"Reviewer worker: {result.reviewer_worker_id}",
            f"Builder worker: {result.builder_worker_id}",
            f"Result digest: {result.result_digest}",
            "",
            result.summary,
        )
    )


def publish_verified_review(
    *,
    decision: ReviewIntentDecision,
    job_id: str,
    pull_request: PullRequestFacts,
    results: ReviewResultPort,
    publications: ReviewPublicationPort,
) -> ReviewPublishOutcome:
    """Publish one formal GitHub review, only after verified independent work.

    Refuses — rather than approximates — when the result is missing, unverified,
    outside the incumbent verdict vocabulary, produced by the builder, or when
    the PR head has moved away from the frozen admission SHA.
    """

    result_port = _require(results, name="ReviewResultPort")
    publication_port = _require(publications, name="ReviewPublicationPort")
    assert isinstance(result_port, ReviewResultPort)
    assert isinstance(publication_port, ReviewPublicationPort)

    if not decision.admitted or decision.frozen_head_sha is None:
        raise ReviewVerificationRefused("only an admitted decision may publish a review")
    if decision.repository is None or decision.pull_number is None:
        raise ReviewVerificationRefused("admitted decision is missing its pull identity")
    if not isinstance(job_id, str) or not job_id:
        raise ReviewVerificationRefused("publication requires the admitted job id")

    command = publication_command_id(
        repository=decision.repository,
        pull_number=decision.pull_number,
        head_sha=decision.frozen_head_sha,
        job_id=job_id,
    )

    if command in publication_port.published_command_ids():
        return ReviewPublishOutcome(
            state=PublishState.ALREADY_PUBLISHED, publication_command_id=command
        )

    # Head freeze, re-checked against a fresh read immediately before effect.
    try:
        verify_frozen_head(decision=decision, pull_request=pull_request)
    except ReviewIntentError:
        return ReviewPublishOutcome(
            state=PublishState.REFUSED,
            publication_command_id=command,
            refusal=ReviewIntentRefusal.HEAD_MOVED.value,
        )

    result = result_port.load_verified_result(job_id=job_id)
    if result is None:
        return ReviewPublishOutcome(
            state=PublishState.REFUSED,
            publication_command_id=command,
            refusal="RESULT_NOT_VERIFIED",
        )
    if not isinstance(result, VerifiedReviewResult):
        raise ReviewVerificationRefused("ReviewResultPort returned a non-exact result shape")
    if result.verdict not in REVIEW_VERDICTS:
        return ReviewPublishOutcome(
            state=PublishState.REFUSED,
            publication_command_id=command,
            refusal="VERDICT_OUTSIDE_VOCABULARY",
        )
    if not result.reviewer_worker_id or not result.builder_worker_id:
        return ReviewPublishOutcome(
            state=PublishState.REFUSED,
            publication_command_id=command,
            refusal="REVIEWER_IDENTITY_UNKNOWN",
        )
    if result.reviewer_worker_id == result.builder_worker_id:
        return ReviewPublishOutcome(
            state=PublishState.REFUSED,
            publication_command_id=command,
            refusal="REVIEW_NOT_INDEPENDENT",
        )
    if result.job_id != job_id:
        return ReviewPublishOutcome(
            state=PublishState.REFUSED,
            publication_command_id=command,
            refusal="RESULT_JOB_IDENTITY_DRIFT",
        )
    if len(result.summary) > MAX_REVIEW_SUMMARY_CHARS:
        return ReviewPublishOutcome(
            state=PublishState.REFUSED,
            publication_command_id=command,
            refusal="REVIEW_SUMMARY_OVER_BOUND",
        )

    event = REVIEW_VERDICT_EVENTS[result.verdict]
    review_id = publication_port.publish_review(
        publication_command_id=command,
        repository=decision.repository,
        pull_number=decision.pull_number,
        head_sha=decision.frozen_head_sha,
        event=event,
        body=render_review_body(
            result=result,
            repository=decision.repository,
            pull_number=decision.pull_number,
        ),
    )
    return ReviewPublishOutcome(
        state=PublishState.PUBLISHED,
        publication_command_id=command,
        review_id=review_id,
    )


__all__ = [
    "AdmissionState",
    "FabricJobAdmissionPort",
    "MAX_REVIEW_SUMMARY_CHARS",
    "PublishState",
    "REVIEW_VERDICT_EVENTS",
    "ReviewIngressError",
    "ReviewIngressOutcome",
    "ReviewIngressUnavailable",
    "ReviewPublicationPort",
    "ReviewResultPort",
    "ReviewVerificationRefused",
    "ReviewPublishOutcome",
    "SCHEMA",
    "VerifiedReviewResult",
    "VisibilityPort",
    "PullRequestReadPort",
    "admit_review_intent",
    "publication_command_id",
    "publish_verified_review",
    "render_review_body",
]