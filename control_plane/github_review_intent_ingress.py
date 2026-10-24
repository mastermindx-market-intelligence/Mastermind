"""Ingress orchestration for authenticated independent GitHub PR review.

This module owns no webhook server, HTTP route, GitHub client, GitHub App
credential, installation token, queue, watcher, scheduler, database, table,
lifecycle, retry plane, Slack transport, or review publisher.  It is the thin
composition layer that walks one delivery through the existing owners:

    verify delivery  ->  :mod:`control_plane.github_review_intent` (pure)
    re-read the PR   ->  ``PullRequestReadPort``      (authenticated read)
    read the actor   ->  ``ActorPermissionPort``      (authenticated read)
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
* **The pull request is the signed payload's.**  This module accepts no
  pull-request number from its caller.  The number comes from the verified
  delivery body, the authoritative re-read must agree with it, and a delivery
  that identifies no pull request earns no read, no ledger write, and no
  visibility line.  A correct HMAC proves who signed the bytes; it never
  proves which pull request a wrong route selected.
* **Idempotency is the existing ledger's.**  The admission identity is the
  existing ``events.command_id`` UNIQUE index, bound to one exact head and *not*
  to the intent channel, so one head earns one run however many channels fire.
  This module keeps no run registry, no cache, and no lock.
* **Freshness at the effect boundary.**  Publication performs its own
  installation-scoped read of the pull request immediately before the review
  POST and fails closed if that head moved.  No caller-supplied snapshot can
  stand in for that read.
* **An uncertain POST is reconciled, never retried blind.**  When an adapter
  cannot observe its own review POST, the effect is read back at the exact
  commit and body; only a positive match avoids a duplicate formal review, and
  an unmatched effect is reported as an unknown effect for a human.
* **No unfenced auto-approval.**  A ``PASS`` verdict publishes a *comment*;
  this module mints no ``APPROVE`` and no merge path at all, and the concrete
  publication adapter refuses any verb outside the mapped set.
* **Formal review by a genuinely separate worker.**  Publication refuses a
  result whose reviewer is the builder, or whose reviewer identity is unknown.
* **Visibility is non-gating and opaque.**  A visibility failure is recorded as
  one fixed code.  Transport exception text can carry hostnames, tokens,
  channel ids, and message ids, so none of it crosses to an external consumer.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import re
from collections.abc import Mapping
from enum import Enum
from typing import Protocol, runtime_checkable

from control_plane.github_review_intent import (
    REVIEW_VERDICTS,
    SUPPORTED_EVENTS,
    CurrentPermission,
    IntentSignal,
    PullRequestFacts,
    ReviewIntentDecision,
    ReviewIntentError,
    ReviewIntentPolicy,
    ReviewIntentRefusal,
    ReviewIntentSignatureError,
    build_review_objective,
    current_permission_is_valid,
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

#: The closed set of verbs any bound publication transport may submit.  An
#: adapter that is handed anything else refuses before it can reach a socket.
ALLOWED_REVIEW_EVENTS = frozenset(REVIEW_VERDICT_EVENTS.values())

#: The single opaque code a visibility failure may ever surface as.  Nothing
#: about the failing transport — exception type, message, host, channel, or
#: token — crosses an external boundary.
VISIBILITY_ERROR_CODE = "VISIBILITY_TRANSPORT_UNAVAILABLE"

MAX_VISIBILITY_SUMMARY_CHARS = 400
MAX_REVIEW_SUMMARY_CHARS = 16_000
MAX_REVIEW_BODY_CHARS = 24_000
_REVIEW_ID_RE = r"^[0-9A-Za-z:._-]{1,128}$"


class ReviewIngressError(RuntimeError):
    """The ingress could not complete one delivery."""


class ReviewIngressUnavailable(ReviewIngressError):
    """A required port is not bound on this host.  Fails closed."""


class ReviewVerificationRefused(ReviewIngressError):
    """A review result is not publishable as a formal GitHub review."""


class PublicationEffectUnknown(ReviewIngressError):
    """A review POST was submitted but its effect could not be observed.

    The honest outcome of a timeout, a dropped connection, or an ambiguous 5xx
    after a POST.  It is never treated as a refusal (which would invite a blind
    retry) and never treated as success; the caller must reconcile by readback.
    """


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

    Publication calls this port itself, immediately before the review POST.  A
    caller-supplied snapshot is not a substitute: only a read taken at the
    effect boundary can say what the head is *now*.
    """

    def read_pull_request(self, *, repository: str, pull_number: int) -> PullRequestFacts:
        """Return the exact current PR facts, or raise."""


@runtime_checkable
class ActorPermissionPort(Protocol):
    """An account's *current* collaborator permission, freshly read.

    Implementations call the authenticated collaborator/permission read for the
    repository and return GitHub's own permission vocabulary (see
    ``github_review_intent.PERMISSION_VALUES``), or ``None`` when the read
    cannot be made.  This module never invents a permission, and never falls
    back to the association claimed in the delivery payload.
    """

    def read_current_permission(self, *, repository: str, login: str) -> str | None:
        """Return the account's current permission, or ``None`` when unavailable."""


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
        second review.  Raise :class:`PublicationEffectUnknown` when the POST
        was submitted but its effect could not be observed.
        """


@dataclasses.dataclass(frozen=True)
class PublishedReviewFacts:
    """One review already present on a pull request, as read back."""

    review_id: str
    commit_id: str
    event: str
    body: str


def published_review_is_valid(review: object) -> bool:
    """Whether a readback fact is exact and in vocabulary."""

    return (
        isinstance(review, PublishedReviewFacts)
        and isinstance(review.review_id, str)
        and re.fullmatch(_REVIEW_ID_RE, review.review_id) is not None
        and isinstance(review.commit_id, str)
        and isinstance(review.event, str)
        and review.event in ALLOWED_REVIEW_EVENTS
        and isinstance(review.body, str)
        and len(review.body) <= MAX_REVIEW_BODY_CHARS
    )


def reconcile_publication(
    *,
    reviews: tuple[PublishedReviewFacts, ...],
    commit_id: str,
    event: str,
    body: str,
) -> str | None:
    """Find the review id this exact POST already produced, or ``None``.

    The reconciliation key is the triple GitHub itself fixes: the commit the
    review was pinned to, the verb it was submitted with, and the exact body.
    Two independent reviews of one commit with byte-identical bodies cannot be
    distinguished — and that is precisely the case reconciliation exists to
    prevent from happening a second time.
    """

    for review in reviews:
        if not published_review_is_valid(review):
            continue
        if review.commit_id == commit_id and review.event == event and review.body == body:
            return review.review_id
    return None


@runtime_checkable
class ReviewTransportPort(Protocol):
    """The GitHub review POST and its authenticated readback.

    Implementations bind to ``POST /repos/{repo}/pulls/{n}/reviews`` and
    ``GET /repos/{repo}/pulls/{n}/reviews``, both installation-scoped.  This
    module supplies no HTTP client and binds no credential.
    """

    def submit_review(
        self, *, repository: str, pull_number: int, commit_id: str, event: str, body: str
    ) -> str:
        """Post one review and return its review id.

        Raise :class:`PublicationEffectUnknown` — never return a fabricated id —
        when the request was submitted but its effect cannot be observed.
        """

    def read_reviews(
        self, *, repository: str, pull_number: int, commit_id: str
    ) -> tuple[PublishedReviewFacts, ...]:
        """Read the reviews already present at one exact commit."""


@runtime_checkable
class PublishedCommandIndex(Protocol):
    """The host's existing record of already-published command ids.

    Injected, never created here: this module owns no publication registry.
    """

    def published_command_ids(self) -> frozenset[str]:
        ...


class ReconcilingReviewPublication:
    """The concrete publication adapter: one POST, reconciled when uncertain.

    It owns three things and nothing else — the verb fence, the exact-commit
    conditioning, and the uncertain-effect reconciliation.  It creates no
    registry, no queue, no retry engine, and no approval path: the durable
    record of what has already been published is the injected
    ``PublishedCommandIndex``, and an unknown effect is reconciled against
    GitHub itself rather than against local state.
    """

    def __init__(
        self, *, transport: ReviewTransportPort, published: PublishedCommandIndex
    ) -> None:
        if not isinstance(transport, ReviewTransportPort):
            raise ReviewIngressError("ReviewTransportPort is not bound on this host")
        if not isinstance(published, PublishedCommandIndex):
            raise ReviewIngressError("PublishedCommandIndex is not bound on this host")
        self._transport = transport
        self._published = published

    def published_command_ids(self) -> frozenset[str]:
        return self._published.published_command_ids()

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
        if event not in ALLOWED_REVIEW_EVENTS:
            # The approval verb is unreachable from any caller, not merely
            # absent from the default mapping.
            raise ReviewVerificationRefused("review event is outside the closed verb set")
        if len(body) > MAX_REVIEW_BODY_CHARS:
            raise ReviewVerificationRefused("review body exceeds its bound")
        try:
            return self._transport.submit_review(
                repository=repository,
                pull_number=pull_number,
                commit_id=head_sha,
                event=event,
                body=body,
            )
        except PublicationEffectUnknown:
            # The POST may or may not have landed.  Reconcile it by reading the
            # reviews at the exact commit and body this call submitted before
            # anything is retried; an unmatched effect is re-raised, so no
            # caller can turn an unknown into a duplicate formal review.
            recovered = reconcile_publication(
                reviews=self._transport.read_reviews(
                    repository=repository, pull_number=pull_number, commit_id=head_sha
                ),
                commit_id=head_sha,
                event=event,
                body=body,
            )
            if recovered is not None:
                return recovered
            raise


# ---------------------------------------------------------------------------
# outcomes
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class ReviewIngressOutcome:
    state: AdmissionState
    decision: ReviewIntentDecision
    job_id: str | None = None
    visibility_error: str | None = None

    def __post_init__(self) -> None:
        # Structural, not documentary: an outcome physically cannot carry
        # transport exception text, so a leak is unrepresentable rather than
        # merely discouraged.
        if self.visibility_error is not None and self.visibility_error != VISIBILITY_ERROR_CODE:
            raise ReviewIngressError(
                "visibility_error must be the closed opaque code or absent"
            )

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
    """Visibility never gates an admission, never re-raises, and never leaks.

    A transport failure collapses to one fixed code.  The exception type and
    text are discarded on the way out: a Slack or webhook client error routinely
    embeds the workspace id, channel id, message id, API URL, and occasionally a
    token fragment, and none of that belongs in a caller-visible outcome.
    """

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
    except Exception:  # noqa: BLE001 - visibility is explicitly non-gating
        return VISIBILITY_ERROR_CODE
    return None


def _simple_refusal(
    *,
    refusal: ReviewIntentRefusal,
    delivery_id: str,
    repository: str,
    pull_number: int | None,
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


def _current_permission(
    actors: ActorPermissionPort | None,
    *,
    repository: str,
    login: str,
) -> CurrentPermission | None:
    """Read the actor's current permission, or ``None`` when it is unavailable.

    ``None`` is an honest "not reverified", not a fallback to the association
    claimed in the payload.  The decision core refuses on it.
    """

    if actors is None:
        return None
    if not isinstance(actors, ActorPermissionPort):
        raise ReviewIngressUnavailable("ActorPermissionPort is not an exact port shape")
    permission = actors.read_current_permission(repository=repository, login=login)
    if permission is None:
        return None
    candidate = CurrentPermission(repository=repository, login=login, permission=permission)
    if not current_permission_is_valid(candidate):
        # An out-of-vocabulary permission is not a permission.
        return None
    return candidate


def admit_review_intent(
    *,
    secret: str,
    body: bytes,
    delivery_id: str,
    event: str,
    signature_header: str,
    policy: ReviewIntentPolicy,
    pull_requests: PullRequestReadPort,
    fabric: FabricJobAdmissionPort,
    actors: ActorPermissionPort | None = None,
    visibility: VisibilityPort | None = None,
) -> ReviewIngressOutcome:
    """Walk one signed delivery to at most one admitted review run.

    There is deliberately no ``pull_number`` parameter.  The pull request is
    whatever the signature-verified payload says it is, so there is no
    caller-supplied value left to cross-bind against the signed one, and no
    route, tenant id, or operator input that can aim a genuine delivery at the
    wrong pull request.
    """

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
        # The decoder's own message quotes the offending payload; it is
        # chained for a local traceback and never put in the raised text.
        raise ReviewIngressError("delivery body is not decodable JSON") from exc

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
            pull_number=envelope.pull_number,
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
            pull_number=envelope.pull_number,
        )
        return ReviewIngressOutcome(
            state=AdmissionState.REFUSED,
            decision=decision,
            visibility_error=_notify(visibility, decision, job_id=None),
        )

    if envelope.pull_number is None:
        # A supported channel whose signed payload identifies no pull request —
        # a slash command on a plain issue.  Refused before any read, ledger
        # write, or reviewer-visible line.
        decision = _simple_refusal(
            refusal=ReviewIntentRefusal.PULL_REQUEST_IDENTITY_UNBOUND,
            delivery_id=delivery_id,
            repository=envelope.repository,
            pull_number=None,
        )
        return ReviewIngressOutcome(
            state=AdmissionState.REFUSED,
            decision=decision,
            visibility_error=_notify(visibility, decision, job_id=None),
        )

    # A login that is not on the allowlist can never be authorized, and that
    # check is static — so it is made before the pull request, and an
    # unauthorized actor earns no authenticated PR read at all.
    if not policy.actor_is_listed(login=signal.actor_login):
        decision = _simple_refusal(
            refusal=ReviewIntentRefusal.ACTOR_NOT_AUTHORIZED,
            delivery_id=delivery_id,
            repository=envelope.repository,
            pull_number=envelope.pull_number,
        )
        return ReviewIngressOutcome(
            state=AdmissionState.REFUSED,
            decision=decision,
            visibility_error=_notify(visibility, decision, job_id=None),
        )

    # The actor's current permission is read before the pull request, so a
    # stale or under-privileged actor costs no authenticated PR read either.
    current_permission = _current_permission(
        actors, repository=envelope.repository, login=signal.actor_login
    )

    pull_request = pull_read.read_pull_request(
        repository=envelope.repository, pull_number=envelope.pull_number
    )
    if not isinstance(pull_request, PullRequestFacts):
        raise ReviewIngressError("PullRequestReadPort returned a non-exact fact shape")

    decision = decide_review_intent(
        envelope=envelope,
        policy=policy,
        pull_request=pull_request,
        signal=signal,
        admitted_command_ids=fabric_port.admitted_command_ids(),
        current_permission=current_permission,
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
    results: ReviewResultPort,
    publications: ReviewPublicationPort,
    pull_requests: PullRequestReadPort,
    readback: ReviewTransportPort | None = None,
) -> ReviewPublishOutcome:
    """Publish one formal GitHub review, only after verified independent work.

    Refuses — rather than approximates — when the result is missing, unverified,
    outside the incumbent verdict vocabulary, produced by the builder, or when
    the PR head has moved away from the frozen admission SHA.

    The pull-request read is performed *here*, at the effect boundary, against
    the current installation-scoped port.  Nothing the caller observed at
    admission time is trusted for that check, because the whole question is
    what the head is *now*; a snapshot cannot answer it and a snapshot that
    happens to be current is a coincidence.
    """

    result_port = _require(results, name="ReviewResultPort")
    publication_port = _require(publications, name="ReviewPublicationPort")
    pull_read = _require(pull_requests, name="PullRequestReadPort")
    assert isinstance(result_port, ReviewResultPort)
    assert isinstance(publication_port, ReviewPublicationPort)
    assert isinstance(pull_read, PullRequestReadPort)

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
        # Nothing is posted, so there is nothing that a moved head could stale.
        return ReviewPublishOutcome(
            state=PublishState.ALREADY_PUBLISHED, publication_command_id=command
        )

    # Result verification happens before the read so a failed publication
    # attempt costs no authenticated API call; it has no external effect.
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
    body = render_review_body(
        result=result,
        repository=decision.repository,
        pull_number=decision.pull_number,
    )

    # Obtain *new* installation-scoped facts at the effect boundary, never
    # reuse a caller's admission-time snapshot or trust an unchanged SHA to
    # prove that draft/state/PR text has not changed.
    current = pull_read.read_pull_request(
        repository=decision.repository, pull_number=decision.pull_number
    )
    if not isinstance(current, PullRequestFacts):
        raise ReviewVerificationRefused("PullRequestReadPort returned a non-exact fact shape")

    def refused(reason: ReviewIntentRefusal) -> ReviewPublishOutcome:
        return ReviewPublishOutcome(
            state=PublishState.REFUSED,
            publication_command_id=command,
            refusal=reason.value,
        )

    if current.repository != decision.repository or current.number != decision.pull_number:
        return refused(ReviewIntentRefusal.PULL_NUMBER_MISMATCH)
    try:
        verify_frozen_head(decision=decision, pull_request=current)
    except ReviewIntentError:
        return refused(ReviewIntentRefusal.HEAD_MOVED)
    if current.state != "open":
        return refused(ReviewIntentRefusal.PULL_REQUEST_NOT_OPEN)
    if current.draft:
        return refused(ReviewIntentRefusal.PULL_REQUEST_DRAFT)
    if (current.base_repository != decision.repository
            or current.head_repository != current.base_repository):
        return refused(ReviewIntentRefusal.HEAD_REPOSITORY_MISMATCH)
    if decision.intent_source is None:
        raise ReviewVerificationRefused("admitted decision lacks an intent source")
    try:
        # This also checks secret/fence forms and the *combined* objective bound.
        build_review_objective(
            pull_request=current, intent_source=decision.intent_source
        )
    except ReviewIntentError:
        return refused(ReviewIntentRefusal.UNTRUSTED_CONTENT_DETECTED)

    try:
        review_id = publication_port.publish_review(
            publication_command_id=command,
            repository=decision.repository,
            pull_number=decision.pull_number,
            head_sha=decision.frozen_head_sha,
            event=event,
            body=body,
        )
    except PublicationEffectUnknown:
        # The POST may or may not have landed.  Reconcile it by readback at the
        # exact commit and body before anything is retried; a positive match
        # settles it as already published, and an unmatched effect is reported
        # as unknown rather than resolved by posting again.
        if readback is None:
            return ReviewPublishOutcome(
                state=PublishState.REFUSED,
                publication_command_id=command,
                refusal="PUBLICATION_EFFECT_UNKNOWN",
            )
        recovered = reconcile_publication(
            reviews=readback.read_reviews(
                repository=decision.repository,
                pull_number=decision.pull_number,
                commit_id=decision.frozen_head_sha,
            ),
            commit_id=decision.frozen_head_sha,
            event=event,
            body=body,
        )
        if recovered is None:
            return ReviewPublishOutcome(
                state=PublishState.REFUSED,
                publication_command_id=command,
                refusal="PUBLICATION_EFFECT_UNKNOWN",
            )
        return ReviewPublishOutcome(
            state=PublishState.ALREADY_PUBLISHED,
            publication_command_id=command,
            review_id=recovered,
        )

    return ReviewPublishOutcome(
        state=PublishState.PUBLISHED,
        publication_command_id=command,
        review_id=review_id,
    )


__all__ = [
    "ALLOWED_REVIEW_EVENTS",
    "AdmissionState",
    "ActorPermissionPort",
    "FabricJobAdmissionPort",
    "MAX_REVIEW_BODY_CHARS",
    "MAX_REVIEW_SUMMARY_CHARS",
    "MAX_VISIBILITY_SUMMARY_CHARS",
    "PublicationEffectUnknown",
    "PublishState",
    "PublishedCommandIndex",
    "PublishedReviewFacts",
    "REVIEW_VERDICT_EVENTS",
    "ReconcilingReviewPublication",
    "ReviewIngressError",
    "ReviewIngressOutcome",
    "ReviewIngressUnavailable",
    "ReviewPublicationPort",
    "ReviewPublishOutcome",
    "ReviewResultPort",
    "ReviewTransportPort",
    "ReviewVerificationRefused",
    "SCHEMA",
    "VISIBILITY_ERROR_CODE",
    "VerifiedReviewResult",
    "VisibilityPort",
    "PullRequestReadPort",
    "admit_review_intent",
    "publication_command_id",
    "publish_verified_review",
    "published_review_is_valid",
    "reconcile_publication",
    "render_review_body",
]