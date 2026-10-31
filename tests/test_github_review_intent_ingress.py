"""tests.test_github_review_intent_ingress — guard file for the ingress walk.

D-row acceptance for :mod:`control_plane.github_review_intent_ingress`, the
composition layer that turns one signed delivery into at most one admitted
independent review run and at most one formal GitHub review.  Falsifier and
so-what for each row:

* D1 a bad signature stops the walk before the PR read, the ledger, and the
  Slack line.  Any one of those would make this an unauthenticated run
  trigger, and reporting the failure would leak a probe oracle.
* D2 an unsupported event/action is refused by name and earns no API read.
* D3 duplicate delivery of the same head reconciles to the same job instead of
  opening a second run.  The ledger's ``command_id`` UNIQUE index is the only
  dedupe store; this module keeps none of its own.
* D4 an unbound required port is a typed refusal, never a fallback to an
  unauthenticated client.
* D5 **the pull request is the signed payload's.**  This module accepts no
  pull-request number from its caller, and the authoritative read it performs
  must agree with the signed one.  A valid signed event for pull request A
  paired with a read of pull request B admits nothing.
* D6 **publication is fresh at the effect.**  The head is re-read through the
  current installation-scoped port immediately before the POST, so a head that
  moved after admission is refused rather than re-pointed.
* D7 an uncertain review POST is reconciled by readback, never retried blind.
* D8 a moved head refuses publication instead of silently re-pointing the
  review at the new commit.
* D9 publication is refused for an unverified result, an out-of-vocabulary
  verdict, an unknown reviewer, or a reviewer who is the builder.
* D10 a publish retry reconciles to the same publication command and never
  posts a second formal review.
* D11 a ``PASS`` verdict publishes a *comment*; no path mints ``APPROVE`` or
  any merge verb, and the concrete adapter refuses one outright.
* D12 visibility never gates an admission, and a transport failure surfaces as
  one fixed opaque code with none of the exception text.
* D13 the open comment channel is refused unless the host reverifies the
  actor's current permission.

Guard-test law: this file is the guard for every production module in the diff
(``control_plane/github_review_intent.py``,
``control_plane/github_review_intent_ingress.py``).  No marker is used anywhere
in this file (nothing is gated to one platform).
"""
from __future__ import annotations

import dataclasses
import inspect
import json
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from control_plane import github_review_intent as gri
from control_plane import github_review_intent_ingress as ing


SECRET = "webhook-secret-value"
REPOSITORY = "mastermindx-market-intelligence/Mastermind"
HEAD_SHA = "a" * 40
MOVED_HEAD_SHA = "b" * 40
DELIVERY_ID = "11111111-2222-3333-4444-555555555555"
JOB_ID = "JOB-042"
PULL_NUMBER = 1739
OTHER_PULL_NUMBER = 1740
EXPECTED_PUBLISHER = ing.ExpectedReviewPublisher(
    user_id=424242, login="mastermind-reviewer[bot]"
)


def _review_fact(**kwargs):
    return ing.PublishedReviewFacts(
        author_user_id=EXPECTED_PUBLISHER.user_id,
        author_login=EXPECTED_PUBLISHER.login,
        **kwargs,
    )


def _policy(**overrides) -> gri.ReviewIntentPolicy:
    base = {
        "repositories": frozenset({REPOSITORY}),
        "installation_ids": frozenset({4242}),
        "configured_reviewer": "mastermind-reviewer",
        "authorized_actors": frozenset({"alice"}),
    }
    base.update(overrides)
    return gri.ReviewIntentPolicy(**base)


def _pull_request(**overrides) -> gri.PullRequestFacts:
    base = {
        "repository": REPOSITORY,
        "number": PULL_NUMBER,
        "state": "open",
        "draft": False,
        "head_sha": HEAD_SHA,
        "head_repository": REPOSITORY,
        "base_repository": REPOSITORY,
        "base_sha": "c" * 40,
        "title": "feat: bounded review ingress",
        "body": "Adds a decision core and tests.",
    }
    base.update(overrides)
    return gri.PullRequestFacts(**base)


def _signed_pull_request() -> dict:
    return {"number": PULL_NUMBER, "base": {"repo": {"full_name": REPOSITORY}}}


def _signed_issue(link: bool = True) -> dict:
    if not link:
        return {"number": PULL_NUMBER}
    return {
        "number": PULL_NUMBER,
        "pull_request": {"url": f"https://api.github.com/repos/{REPOSITORY}/pulls/{PULL_NUMBER}"},
    }


def _label_body(*, sender="alice", label="independent-review") -> bytes:
    return json.dumps(
        {
            "action": "labeled",
            "installation": {"id": 4242},
            "repository": {"full_name": REPOSITORY},
            "number": PULL_NUMBER,
            "pull_request": _signed_pull_request(),
            "sender": {"login": sender},
            "label": {"name": label},
        }
    ).encode("utf-8")


def _comment_body(*, sender="alice", association="MEMBER", link=True) -> bytes:
    return json.dumps(
        {
            "action": "created",
            "installation": {"id": 4242},
            "repository": {"full_name": REPOSITORY},
            "issue": _signed_issue(link=link),
            "comment": {
                "body": "/independent-review",
                "user": {"login": sender},
                "author_association": association,
            },
        }
    ).encode("utf-8")


# ---------------------------------------------------------------------------
# fake ports
# ---------------------------------------------------------------------------


class FakePullRequests:
    """Returns whatever facts the test hands it; counts every read."""

    def __init__(self, facts: gri.PullRequestFacts | None = None) -> None:
        self.facts = facts if facts is not None else _pull_request()
        self.reads = 0
        self.seen: list[tuple[str, int]] = []

    def read_pull_request(self, *, repository: str, pull_number: int) -> gri.PullRequestFacts:
        self.reads += 1
        self.seen.append((repository, pull_number))
        return self.facts


class FakeFabric:
    """Mimics the existing ledger: one job per command_id, ever."""

    def __init__(self) -> None:
        self.jobs: dict[str, str] = {}
        self.objectives: list[str] = []
        self.admit_calls = 0

    def admitted_command_ids(self) -> frozenset[str]:
        return frozenset(self.jobs)

    def admit_review_intent(
        self, *, decision: gri.ReviewIntentDecision, objective: str
    ) -> str:
        assert decision.command_id is not None
        self.admit_calls += 1
        self.objectives.append(objective)
        if decision.command_id not in self.jobs:
            self.jobs[decision.command_id] = f"{JOB_ID}-{len(self.jobs) + 1}"
        return self.jobs[decision.command_id]


class FakeActors:
    """GitHub's current permission for an account, or ``None`` when unknown."""

    def __init__(self, permission: str | None = "write") -> None:
        self.permission = permission
        self.asked: list[tuple[str, str]] = []

    def read_current_permission(self, *, repository: str, login: str) -> str | None:
        self.asked.append((repository, login))
        return self.permission


class FakeVisibility:
    def __init__(self, *, boom: bool = False) -> None:
        self.admitted: list[str] = []
        self.refused: list[str] = []
        self._boom = boom

    def notify_review_admitted(self, *, summary, decision, job_id) -> None:
        if self._boom:
            raise RuntimeError(
                "slack transport unavailable for xoxb-not-a-real-token at C0CAUK8P8S3"
            )
        self.admitted.append(summary)

    def notify_review_refused(self, *, summary, decision) -> None:
        if self._boom:
            raise RuntimeError(
                "slack transport unavailable for xoxb-not-a-real-token at C0CAUK8P8S3"
            )
        self.refused.append(summary)


class FakeAdmittedJobs:
    """Canonical readback simulator: evidence is indexed by admission command."""

    def __init__(self, decision, job_id, *, override=None):
        self.lookups = []
        self.command_id = decision.command_id
        self.facts = (
            override if override is not None else
            ing.AdmittedJobFacts(
                job_id=job_id,
                command_id=decision.command_id,
                repository=decision.repository,
                pull_number=decision.pull_number,
                frozen_head_sha=decision.frozen_head_sha,
                actor=decision.actor,
                intent_id=decision.intent_id,
            )
        )

    def read_admitted_job(self, *, command_id):
        self.lookups.append(command_id)
        return self.facts if command_id == self.command_id else None


class FakeResults:
    def __init__(self, result: ing.VerifiedReviewResult | None) -> None:
        self.result = result
        self.lookups: list[str] = []

    def load_verified_result(self, *, job_id: str):
        self.lookups.append(job_id)
        return self.result


class FakePublications:
    def publishing_principal(self):
        return EXPECTED_PUBLISHER

    def __init__(self, *, unknown: bool = False) -> None:
        self.published: dict[str, str] = {}
        self.calls: list[dict] = []
        self._unknown = unknown

    def published_command_ids(self) -> frozenset[str]:
        return frozenset(self.published)

    def publish_review(
        self, *, publication_command_id, repository, pull_number, head_sha, event, body
    ) -> str:
        self.calls.append(
            {
                "publication_command_id": publication_command_id,
                "event": event,
                "head_sha": head_sha,
                "body": body,
            }
        )
        if self._unknown:
            raise ing.PublicationEffectUnknown("connection reset after request body sent")
        if publication_command_id not in self.published:
            self.published[publication_command_id] = f"review-{len(self.published) + 1}"
        return self.published[publication_command_id]


class FakeReadback:
    """The reviews already present at one exact commit."""

    def __init__(self, reviews: tuple[ing.PublishedReviewFacts, ...] = ()) -> None:
        self.reviews = reviews
        self.reads = 0

    def read_reviews(self, *, repository, pull_number, commit_id):
        self.reads += 1
        return self.reviews


class FakeTransport:
    """A GitHub review POST that can lose sight of its own effect."""

    def __init__(self, *, lands: bool) -> None:
        self.lands = lands
        self.submits = 0
        self.readbacks = 0
        self.landed: tuple[str, str, str, str] | None = None

    def submit_review(self, *, repository, pull_number, commit_id, event, body) -> str:
        self.submits += 1
        if self.lands:
            self.landed = (repository, str(pull_number), commit_id, event, body)
        raise ing.PublicationEffectUnknown("timeout after the request body was sent")

    def read_reviews(self, *, repository, pull_number, commit_id):
        self.readbacks += 1
        if self.landed is None:
            return ()
        _, _, landed_commit, landed_event, landed_body = self.landed
        return (
            _review_fact(
                review_id="review-recovered",
                commit_id=landed_commit,
                event=landed_event,
                body=landed_body,
            ),
        )


class FakeIndex:
    """Inert test stand-in for the canonical UNIQUE EventStore reservation.

    A shared lock models the first-writer property across adapter instances.
    Production must use the incumbent persistent events.command_id transaction.
    """

    def __init__(self, *ids: str) -> None:
        self.ids = set(ids)
        self.claims = {}
        self.lock = threading.Lock()

    def published_command_ids(self) -> frozenset[str]:
        with self.lock:
            return frozenset(self.ids)

    def reserve_publication(self, *, publication_command_id, repository,
                            pull_number, head_sha, event, body):
        identity = (repository, pull_number, head_sha, event, body)
        with self.lock:
            prior = self.claims.get(publication_command_id)
            if prior is None:
                self.claims[publication_command_id] = identity
                return True
            if prior != identity:
                raise ing.ReviewVerificationRefused("publication claim identity mismatch")
            return False

    def confirm_publication(self, *, publication_command_id, repository,
                            pull_number, head_sha, event, body, review_id):
        identity = (repository, pull_number, head_sha, event, body)
        with self.lock:
            if self.claims.get(publication_command_id) != identity:
                raise ing.ReviewVerificationRefused("publication confirmation mismatch")
            self.ids.add(publication_command_id)


class SuccessTransport:
    def __init__(self):
        self.lock = threading.Lock()
        self.submits = 0
        self.receipt = None

    def submit_review(self, *, repository, pull_number, commit_id, event, body):
        with self.lock:
            self.submits += 1
            self.receipt = _review_fact(
                review_id="review-real", commit_id=commit_id, event=event, body=body
            )
            return "review-real"

    def read_reviews(self, *, repository, pull_number, commit_id):
        with self.lock:
            return () if self.receipt is None else (self.receipt,)


def _verified(**overrides) -> ing.VerifiedReviewResult:
    base = {
        "job_id": f"{JOB_ID}-1",
        "attempt_id": "ATT-" + "c" * 32,
        "verdict": "PASS",
        "reviewer_worker_id": "worker-reviewer",
        "builder_worker_id": "worker-builder",
        "summary": "Reviewed. One nit, no blocking findings.",
        "result_digest": "d" * 64,
    }
    base.update(overrides)
    return ing.VerifiedReviewResult(**base)


def _admit(
    body: bytes | None = None,
    *,
    fabric=None,
    pull_requests=None,
    actors="default",
    visibility=None,
    event="pull_request",
    signature: str | None = None,
    policy=None,
):
    payload = body if body is not None else _label_body()
    fabric_port = fabric or FakeFabric()
    reads = pull_requests if pull_requests is not None else FakePullRequests()
    actor_port = FakeActors() if actors == "default" else actors
    if signature is None:
        signature = gri.sign_webhook_body(secret=SECRET, body=payload)
    return ing.admit_review_intent(
        secret=SECRET,
        body=payload,
        delivery_id=DELIVERY_ID,
        event=event,
        signature_header=signature,
        policy=policy if policy is not None else _policy(),
        pull_requests=reads,
        fabric=fabric_port,
        actors=actor_port,
        visibility=visibility,
    )


def _admitted_decision(policy=None):
    fabric = FakeFabric()
    outcome = _admit(fabric=fabric, policy=policy)
    assert outcome.state is ing.AdmissionState.ADMITTED
    return fabric, outcome


def _final_guard(pulls=None):
    _, admitted = _admitted_decision()
    return ing.FinalPullRequestCheck(
        decision=admitted.decision,
        pull_requests=pulls if pulls is not None else FakePullRequests(),
    )


def _publish(decision, job_id, *, results=None, publications=None,
             pull_requests=None, readback=None, admissions="default"):
    binding = FakeAdmittedJobs(decision, job_id) if admissions == "default" else admissions
    return ing.publish_verified_review(
        decision=decision,
        job_id=job_id,
        results=results if results is not None else FakeResults(_verified(job_id=job_id)),
        publications=publications if publications is not None else FakePublications(),
        pull_requests=pull_requests if pull_requests is not None else FakePullRequests(),
        admissions=binding,
        readback=readback,
    )


# ---------------------------------------------------------------------------
# D1/D2 — signature and unsupported channels
# ---------------------------------------------------------------------------


class TestSignatureStopsTheWalk:
    def test_bad_signature_raises_before_any_read_or_write(self) -> None:
        reads = FakePullRequests()
        fabric = FakeFabric()
        with pytest.raises(gri.ReviewIntentSignatureError):
            _admit(
                fabric=fabric,
                pull_requests=reads,
                signature=gri.sign_webhook_body(secret="attacker-secret", body=_label_body()),
            )
        assert reads.reads == 0
        assert fabric.admit_calls == 0
        assert fabric.jobs == {}

    def test_bad_signature_is_not_reported_to_visibility(self) -> None:
        visibility = FakeVisibility()
        with pytest.raises(gri.ReviewIntentSignatureError):
            _admit(
                visibility=visibility,
                signature=gri.sign_webhook_body(secret="attacker-secret", body=_label_body()),
            )
        assert visibility.refused == []
        assert visibility.admitted == []

    def test_tampered_body_with_a_valid_prior_signature_is_refused(self) -> None:
        # A signature captured over one body must not admit a different body.
        good = gri.sign_webhook_body(secret=SECRET, body=_label_body())
        fabric = FakeFabric()
        with pytest.raises(gri.ReviewIntentSignatureError):
            _admit(_label_body(label="hold"), fabric=fabric, signature=good)
        assert fabric.jobs == {}


class TestUnsupportedChannel:
    def test_unsupported_event_is_refused_without_a_read(self) -> None:
        reads = FakePullRequests()
        outcome = _admit(_label_body(), pull_requests=reads, event="push")
        assert outcome.state is ing.AdmissionState.REFUSED
        assert outcome.decision.refusal is gri.ReviewIntentRefusal.EVENT_NOT_SUPPORTED
        assert reads.reads == 0

    def test_unsupported_action_is_refused_without_a_read(self) -> None:
        parsed = json.loads(_label_body())
        parsed["action"] = "opened"
        reads = FakePullRequests()
        outcome = _admit(json.dumps(parsed).encode(), pull_requests=reads)
        assert outcome.decision.refusal is gri.ReviewIntentRefusal.ACTION_NOT_SUPPORTED
        assert reads.reads == 0

    def test_undecodable_body_raises_without_leaking_the_decoder_message(self) -> None:
        with pytest.raises(ing.ReviewIngressError) as excinfo:
            _admit(b"{not json")
        assert "Expecting property name" not in str(excinfo.value)


# ---------------------------------------------------------------------------
# D3/D12 — the admitted walk and opaque visibility
# ---------------------------------------------------------------------------


class TestAdmittedWalk:
    def test_authorized_label_admits_one_run(self) -> None:
        outcome = _admit()
        assert outcome.state is ing.AdmissionState.ADMITTED
        assert outcome.job_id == f"{JOB_ID}-1"
        assert outcome.decision.intent_source is gri.IntentSource.INTENT_LABEL
        assert outcome.decision.frozen_head_sha == HEAD_SHA

    def test_objective_fences_the_untrusted_text(self) -> None:
        fabric, _ = _admitted_decision()
        objective = fabric.objectives[0]
        assert gri.UNTRUSTED_BLOCK_OPEN in objective
        assert gri.UNTRUSTED_BLOCK_CLOSE in objective

    def test_the_read_is_aimed_at_the_signed_pull_request(self) -> None:
        reads = FakePullRequests()
        _admit(pull_requests=reads)
        assert reads.seen == [(REPOSITORY, PULL_NUMBER)]

    def test_duplicate_delivery_opens_no_second_run(self) -> None:
        fabric = FakeFabric()
        first = _admit(fabric=fabric)
        second = _admit(fabric=fabric)
        assert first.state is ing.AdmissionState.ADMITTED
        assert second.state is ing.AdmissionState.ALREADY_ADMITTED
        assert second.decision.refusal is gri.ReviewIntentRefusal.ALREADY_ADMITTED
        assert len(fabric.jobs) == 1
        assert fabric.admit_calls == 1

    def test_a_new_head_is_a_new_run(self) -> None:
        fabric = FakeFabric()
        _admit(fabric=fabric)
        moved = _admit(
            _label_body(),
            fabric=fabric,
            pull_requests=FakePullRequests(_pull_request(head_sha=MOVED_HEAD_SHA)),
        )
        assert moved.state is ing.AdmissionState.ADMITTED
        assert len(fabric.jobs) == 2

    def test_two_channels_on_one_head_still_open_exactly_one_run(self) -> None:
        # A reviewer requested, a label applied and a slash command commented
        # in the same minute is one human intent.  Three distinct command ids
        # here would be three paid Fabric reviews of one exact commit.
        fabric = FakeFabric()
        label = _admit(_label_body(), fabric=fabric)
        comment = _admit(
            _comment_body(), fabric=fabric, event="issue_comment", actors=FakeActors("write")
        )
        assert label.state is ing.AdmissionState.ADMITTED
        assert comment.state is ing.AdmissionState.ALREADY_ADMITTED
        assert len(fabric.jobs) == 1
        assert fabric.admit_calls == 1

    def test_unauthorized_actor_is_refused(self) -> None:
        fabric = FakeFabric()
        outcome = _admit(_label_body(sender="stranger"), fabric=fabric)
        assert outcome.decision.refusal is gri.ReviewIntentRefusal.ACTOR_NOT_AUTHORIZED
        assert fabric.jobs == {}

    def test_fork_is_refused(self) -> None:
        fabric = FakeFabric()
        outcome = _admit(
            fabric=fabric,
            pull_requests=FakePullRequests(_pull_request(head_repository="attacker/evil")),
        )
        assert outcome.decision.refusal is gri.ReviewIntentRefusal.HEAD_REPOSITORY_MISMATCH
        assert fabric.jobs == {}

    def test_visibility_failure_never_gates_or_readmits(self) -> None:
        visibility = FakeVisibility(boom=True)
        outcome = _admit(visibility=visibility)
        assert outcome.state is ing.AdmissionState.ADMITTED
        assert outcome.job_id == f"{JOB_ID}-1"

    def test_a_visibility_failure_surfaces_only_the_opaque_code(self) -> None:
        outcome = _admit(visibility=FakeVisibility(boom=True))
        assert outcome.visibility_error == ing.VISIBILITY_ERROR_CODE
        serialised = json.dumps(outcome.to_dict())
        for leaked in ("slack", "xoxb", "C0CAUK8P8S3", "RuntimeError", "Traceback"):
            assert leaked not in serialised

    def test_an_outcome_cannot_even_construct_with_arbitrary_visibility_text(self) -> None:
        _, outcome = _admitted_decision()
        with pytest.raises(ing.ReviewIngressError):
            ing.ReviewIngressOutcome(
                state=outcome.state,
                decision=outcome.decision,
                job_id=outcome.job_id,
                visibility_error="RuntimeError: slack transport unavailable",
            )

    def test_visibility_receives_the_admitted_summary(self) -> None:
        visibility = FakeVisibility()
        _admit(visibility=visibility)
        assert len(visibility.admitted) == 1
        assert "independent review admitted" in visibility.admitted[0]


# ---------------------------------------------------------------------------
# D4 — unbound ports fail closed
# ---------------------------------------------------------------------------


class TestUnboundPorts:
    def test_missing_pull_request_port_refuses(self) -> None:
        with pytest.raises(ing.ReviewIngressUnavailable):
            ing.admit_review_intent(
                secret=SECRET,
                body=_label_body(),
                delivery_id=DELIVERY_ID,
                event="pull_request",
                signature_header=gri.sign_webhook_body(secret=SECRET, body=_label_body()),
                policy=_policy(),
                pull_requests=None,
                fabric=FakeFabric(),
            )

    def test_missing_fabric_port_refuses(self) -> None:
        with pytest.raises(ing.ReviewIngressUnavailable):
            ing.admit_review_intent(
                secret=SECRET,
                body=_label_body(),
                delivery_id=DELIVERY_ID,
                event="pull_request",
                signature_header=gri.sign_webhook_body(secret=SECRET, body=_label_body()),
                policy=_policy(),
                pull_requests=FakePullRequests(),
                fabric=None,
            )

    def test_missing_result_port_refuses_publication(self) -> None:
        _, outcome = _admitted_decision()
        with pytest.raises(ing.ReviewIngressUnavailable):
            ing.publish_verified_review(
                decision=outcome.decision,
                job_id=outcome.job_id,
                results=None,
                publications=FakePublications(),
                pull_requests=FakePullRequests(),
            )

    def test_missing_pull_request_port_refuses_publication(self) -> None:
        _, outcome = _admitted_decision()
        with pytest.raises(ing.ReviewIngressUnavailable):
            ing.publish_verified_review(
                decision=outcome.decision,
                job_id=outcome.job_id,
                results=FakeResults(_verified(job_id=outcome.job_id)),
                publications=FakePublications(),
                pull_requests=None,
            )


# ---------------------------------------------------------------------------
# D5/D13 — the signed pull request, and actor permission freshness
# ---------------------------------------------------------------------------


class TestSignedIdentityBinding:
    def test_the_walk_takes_no_pull_number_from_its_caller(self) -> None:
        # Structural, not documentary: with no parameter there is nothing left
        # for a wrong route, tenant id, or operator input to cross-bind.
        parameters = inspect.signature(ing.admit_review_intent).parameters
        assert "pull_number" not in parameters
        assert "pull_request" not in parameters

    def test_a_signed_event_for_a_paired_with_a_read_of_b_admits_nothing(self) -> None:
        fabric = FakeFabric()
        reads = FakePullRequests(_pull_request(number=OTHER_PULL_NUMBER))
        outcome = _admit(pull_requests=reads, fabric=fabric)
        assert outcome.state is ing.AdmissionState.REFUSED
        assert outcome.decision.refusal is gri.ReviewIntentRefusal.PULL_NUMBER_MISMATCH
        assert reads.seen == [(REPOSITORY, PULL_NUMBER)]
        assert fabric.jobs == {}

    def test_a_comment_on_a_plain_issue_earns_no_read_and_no_job(self) -> None:
        fabric = FakeFabric()
        reads = FakePullRequests()
        visibility = FakeVisibility()
        outcome = _admit(
            _comment_body(link=False, sender="outsider"),
            event="issue_comment", pull_requests=reads,
            fabric=fabric, visibility=visibility,
        )
        assert outcome.state is ing.AdmissionState.REFUSED
        assert outcome.decision.refusal is gri.ReviewIntentRefusal.PULL_REQUEST_IDENTITY_UNBOUND
        assert reads.reads == 0
        assert fabric.jobs == {}
        assert visibility.admitted == []
        assert visibility.refused == []
        assert outcome.visibility_error is None


class TestActorPermissionPort:
    def test_the_comment_channel_is_refused_when_no_actor_port_is_bound(self) -> None:
        fabric = FakeFabric()
        outcome = _admit(_comment_body(), event="issue_comment", actors=None, fabric=fabric)
        assert outcome.state is ing.AdmissionState.REFUSED
        assert outcome.decision.refusal is (
            gri.ReviewIntentRefusal.ACTOR_PERMISSION_NOT_REVERIFIED
        )
        assert fabric.jobs == {}

    def test_the_comment_channel_admits_on_a_reverified_permission(self) -> None:
        actors = FakeActors("write")
        outcome = _admit(_comment_body(), event="issue_comment", actors=actors)
        assert outcome.state is ing.AdmissionState.ADMITTED
        assert actors.asked == [(REPOSITORY, "alice")]

    def test_a_revoked_actor_is_refused_on_the_comment_channel(self) -> None:
        fabric = FakeFabric()
        outcome = _admit(
            _comment_body(), event="issue_comment", actors=FakeActors("none"), fabric=fabric
        )
        assert outcome.decision.refusal is gri.ReviewIntentRefusal.ACTOR_PERMISSION_INSUFFICIENT
        assert fabric.jobs == {}

    def test_an_out_of_vocabulary_permission_is_treated_as_unverified(self) -> None:
        fabric = FakeFabric()
        outcome = _admit(
            _comment_body(), event="issue_comment", actors=FakeActors("superuser"), fabric=fabric
        )
        assert outcome.decision.refusal is (
            gri.ReviewIntentRefusal.ACTOR_PERMISSION_NOT_REVERIFIED
        )
        assert fabric.jobs == {}

    def test_an_unreadable_permission_is_treated_as_unverified(self) -> None:
        fabric = FakeFabric()
        outcome = _admit(
            _comment_body(), event="issue_comment", actors=FakeActors(None), fabric=fabric
        )
        assert outcome.decision.refusal is (
            gri.ReviewIntentRefusal.ACTOR_PERMISSION_NOT_REVERIFIED
        )
        assert fabric.jobs == {}

    def test_the_actor_is_read_before_the_pull_request(self) -> None:
        # An actor who cannot be authorized earns no authenticated PR read.
        reads = FakePullRequests()
        _admit(
            _comment_body(sender="stranger"), event="issue_comment", actors=FakeActors("write"),
            pull_requests=reads,
        )
        assert reads.reads == 0


# ---------------------------------------------------------------------------
# D6/D8 — publication freshness at the effect
# ---------------------------------------------------------------------------


class TestPublicationFreshness:
    def test_publication_performs_its_own_read_of_the_current_head(self) -> None:
        _, outcome = _admitted_decision()
        reads = FakePullRequests()
        publications = FakePublications()
        published = _publish(
            outcome.decision, outcome.job_id, publications=publications, pull_requests=reads
        )
        assert published.state is ing.PublishState.PUBLISHED
        assert reads.reads == 1
        assert reads.seen == [(REPOSITORY, PULL_NUMBER)]

    def test_a_head_that_moved_after_admission_refuses_publication(self) -> None:
        # The admitted snapshot still says the old head; only a read taken now
        # can say the review would land on the wrong commit.
        _, outcome = _admitted_decision()
        publications = FakePublications()
        published = _publish(
            outcome.decision,
            outcome.job_id,
            publications=publications,
            pull_requests=FakePullRequests(_pull_request(head_sha=MOVED_HEAD_SHA)),
        )
        assert published.state is ing.PublishState.REFUSED
        assert published.refusal == gri.ReviewIntentRefusal.HEAD_MOVED.value
        assert publications.calls == []

    def test_a_read_about_another_pull_request_refuses_publication(self) -> None:
        _, outcome = _admitted_decision()
        publications = FakePublications()
        published = _publish(
            outcome.decision,
            outcome.job_id,
            publications=publications,
            pull_requests=FakePullRequests(_pull_request(number=OTHER_PULL_NUMBER)),
        )
        assert published.state is ing.PublishState.REFUSED
        assert published.refusal == gri.ReviewIntentRefusal.PULL_NUMBER_MISMATCH.value
        assert publications.calls == []

    def test_a_stale_result_is_refused_before_any_read(self) -> None:
        # Result verification has no external effect, so a failed attempt costs
        # no authenticated API call.
        _, outcome = _admitted_decision()
        reads = FakePullRequests()
        _publish(
            outcome.decision, outcome.job_id, results=FakeResults(None), pull_requests=reads
        )
        assert reads.reads == 0


# ---------------------------------------------------------------------------
# D7 — an uncertain POST is reconciled, never retried
# ---------------------------------------------------------------------------


class TestPublicationEffectUncertainty:
    def _landed_review(self) -> ing.PublishedReviewFacts:
        _, outcome = _admitted_decision()
        body = ing.render_review_body(
            result=_verified(job_id=outcome.job_id),
            repository=REPOSITORY,
            pull_number=PULL_NUMBER,
        )
        return _review_fact(
            review_id="review-recovered",
            commit_id=HEAD_SHA,
            event="COMMENT",
            body=body,
        )

    def test_an_unknown_post_is_reconciled_and_posts_nothing_twice(self) -> None:
        _, outcome = _admitted_decision()
        publications = FakePublications(unknown=True)
        readback = FakeReadback((self._landed_review(),))
        published = _publish(
            outcome.decision, outcome.job_id, publications=publications, readback=readback
        )
        assert published.state is ing.PublishState.ALREADY_PUBLISHED
        assert published.review_id == "review-recovered"
        assert len(publications.calls) == 1
        assert readback.reads == 1

    def test_an_unmatched_unknown_post_is_reported_not_retried(self) -> None:
        _, outcome = _admitted_decision()
        publications = FakePublications(unknown=True)
        readback = FakeReadback(())
        published = _publish(
            outcome.decision, outcome.job_id, publications=publications, readback=readback
        )
        assert published.state is ing.PublishState.REFUSED
        assert published.refusal == "PUBLICATION_EFFECT_UNKNOWN"
        assert len(publications.calls) == 1
        assert readback.reads == 1

    def test_an_unknown_post_without_a_bound_readback_is_reported_not_retried(self) -> None:
        _, outcome = _admitted_decision()
        publications = FakePublications(unknown=True)
        published = _publish(
            outcome.decision, outcome.job_id, publications=publications, readback=None
        )
        assert published.state is ing.PublishState.REFUSED
        assert published.refusal == "PUBLICATION_EFFECT_UNKNOWN"
        assert len(publications.calls) == 1

    def test_reconciliation_only_matches_the_exact_commit_event_and_body(self) -> None:
        _, outcome = _admitted_decision()
        body = ing.render_review_body(
            result=_verified(job_id=outcome.job_id),
            repository=REPOSITORY,
            pull_number=PULL_NUMBER,
        )
        for wrong in (
            _review_fact(
                review_id="r", commit_id=MOVED_HEAD_SHA, event="COMMENT", body=body
            ),
            _review_fact(
                review_id="r", commit_id=HEAD_SHA, event="REQUEST_CHANGES", body=body
            ),
            _review_fact(
                review_id="r", commit_id=HEAD_SHA, event="COMMENT", body=body + " edited"
            ),
        ):
            publications = FakePublications(unknown=True)
            published = _publish(
                outcome.decision,
                outcome.job_id,
                publications=publications,
                readback=FakeReadback((wrong,)),
            )
            assert published.refusal == "PUBLICATION_EFFECT_UNKNOWN"

    def test_the_concrete_adapter_reconciles_internally_and_returns_one_review_id(self) -> None:
        transport = FakeTransport(lands=True)
        adapter = ing.ReconcilingReviewPublication(expected_publisher=EXPECTED_PUBLISHER, before_post=_final_guard(), 
            transport=transport, published=FakeIndex()
        )
        _, outcome = _admitted_decision()
        published = _publish(
            outcome.decision,
            outcome.job_id,
            publications=adapter,
            readback=transport,
        )
        # The adapter resolved the uncertainty itself and returned the real id,
        # so the caller sees one published review, not an unknown effect.
        assert published.state is ing.PublishState.PUBLISHED
        assert published.review_id == "review-recovered"
        assert transport.submits == 1
        assert transport.readbacks == 2

    def test_the_concrete_adapter_reraises_an_unmatched_effect(self) -> None:
        transport = FakeTransport(lands=False)
        adapter = ing.ReconcilingReviewPublication(expected_publisher=EXPECTED_PUBLISHER, before_post=_final_guard(), 
            transport=transport, published=FakeIndex()
        )
        with pytest.raises(ing.PublicationEffectUnknown):
            adapter.publish_review(
                publication_command_id="gh-review-publish:" + "0" * 32,
                repository=REPOSITORY,
                pull_number=PULL_NUMBER,
                head_sha=HEAD_SHA,
                event="COMMENT",
                body="Verdict: PASS",
            )
        assert transport.submits == 1

    def test_the_concrete_adapter_refuses_an_approval_verb_outright(self) -> None:
        transport = FakeTransport(lands=True)
        adapter = ing.ReconcilingReviewPublication(expected_publisher=EXPECTED_PUBLISHER, before_post=_final_guard(), 
            transport=transport, published=FakeIndex()
        )
        with pytest.raises(ing.ReviewVerificationRefused):
            adapter.publish_review(
                publication_command_id="gh-review-publish:" + "0" * 32,
                repository=REPOSITORY,
                pull_number=PULL_NUMBER,
                head_sha=HEAD_SHA,
                event="APPROVE",
                body="Looks great",
            )
        assert transport.submits == 0

    def test_the_concrete_adapter_refuses_an_unbound_transport(self) -> None:
        with pytest.raises(ing.ReviewIngressError):
            ing.ReconcilingReviewPublication(expected_publisher=EXPECTED_PUBLISHER, before_post=_final_guard(), transport=object(), published=FakeIndex())
        with pytest.raises(ing.ReviewIngressError):
            ing.ReconcilingReviewPublication(expected_publisher=EXPECTED_PUBLISHER, before_post=_final_guard(), 
                transport=FakeTransport(lands=False), published=object()
            )


# ---------------------------------------------------------------------------
# D9/D10/D11 — the rest of the publication fences
# ---------------------------------------------------------------------------


class TestPublication:
    def test_verified_independent_review_publishes(self) -> None:
        _, outcome = _admitted_decision()
        publications = FakePublications()
        published = _publish(
            outcome.decision, outcome.job_id, publications=publications
        )
        assert published.state is ing.PublishState.PUBLISHED
        assert published.review_id == "review-1"
        assert publications.calls[0]["head_sha"] == HEAD_SHA

    def test_pass_publishes_a_comment_never_an_approval(self) -> None:
        assert ing.REVIEW_VERDICT_EVENTS["PASS"] == "COMMENT"
        assert "APPROVE" not in ing.REVIEW_VERDICT_EVENTS.values()
        assert ing.ALLOWED_REVIEW_EVENTS == frozenset({"COMMENT", "REQUEST_CHANGES"})

    def test_request_changes_maps_to_the_github_verb(self) -> None:
        _, outcome = _admitted_decision()
        publications = FakePublications()
        _publish(
            outcome.decision,
            outcome.job_id,
            results=FakeResults(_verified(job_id=outcome.job_id, verdict="REQUEST_CHANGES")),
            publications=publications,
        )
        assert publications.calls[0]["event"] == "REQUEST_CHANGES"

    def test_publish_retry_does_not_post_a_second_review(self) -> None:
        _, outcome = _admitted_decision()
        publications = FakePublications()
        results = FakeResults(_verified(job_id=outcome.job_id))
        first = _publish(outcome.decision, outcome.job_id, results=results, publications=publications)
        second = _publish(outcome.decision, outcome.job_id, results=results, publications=publications)
        assert first.state is ing.PublishState.PUBLISHED
        assert second.state is ing.PublishState.ALREADY_PUBLISHED
        assert len(publications.calls) == 1

    def test_moved_head_refuses_publication(self) -> None:
        _, outcome = _admitted_decision()
        publications = FakePublications()
        published = _publish(
            outcome.decision, outcome.job_id,
            pull_requests=FakePullRequests(_pull_request(head_sha=MOVED_HEAD_SHA)),
            publications=publications,
        )
        assert published.state is ing.PublishState.REFUSED
        assert published.refusal == gri.ReviewIntentRefusal.HEAD_MOVED.value
        assert publications.calls == []

    def test_unverified_result_refuses_publication(self) -> None:
        _, outcome = _admitted_decision()
        publications = FakePublications()
        published = _publish(
            outcome.decision, outcome.job_id, results=FakeResults(None), publications=publications
        )
        assert published.refusal == "RESULT_NOT_VERIFIED"
        assert publications.calls == []

    def test_reviewer_equal_to_builder_refuses_publication(self) -> None:
        _, outcome = _admitted_decision()
        publications = FakePublications()
        published = _publish(
            outcome.decision,
            outcome.job_id,
            results=FakeResults(
                _verified(job_id=outcome.job_id, builder_worker_id="worker-reviewer")
            ),
            publications=publications,
        )
        assert published.refusal == "REVIEW_NOT_INDEPENDENT"
        assert publications.calls == []

    def test_unknown_reviewer_refuses_publication(self) -> None:
        _, outcome = _admitted_decision()
        publications = FakePublications()
        published = _publish(
            outcome.decision,
            outcome.job_id,
            results=FakeResults(
                _verified(job_id=outcome.job_id, reviewer_worker_id="")
            ),
            publications=publications,
        )
        assert published.refusal == "REVIEWER_IDENTITY_UNKNOWN"
        assert publications.calls == []

    def test_out_of_vocabulary_verdict_refuses_publication(self) -> None:
        _, outcome = _admitted_decision()
        publications = FakePublications()
        published = _publish(
            outcome.decision,
            outcome.job_id,
            results=FakeResults(_verified(job_id=outcome.job_id, verdict="LGTM")),
            publications=publications,
        )
        assert published.refusal == "VERDICT_OUTSIDE_VOCABULARY"
        assert publications.calls == []

    def test_result_from_another_job_refuses_publication(self) -> None:
        _, outcome = _admitted_decision()
        published = _publish(
            outcome.decision,
            outcome.job_id,
            results=FakeResults(_verified(job_id="JOB-999")),
        )
        assert published.refusal == "RESULT_JOB_IDENTITY_DRIFT"

    def test_refused_decision_cannot_publish(self) -> None:
        outcome = _admit(_label_body(sender="stranger"))
        with pytest.raises(ing.ReviewVerificationRefused):
            _publish(outcome.decision, "JOB-001")

    def test_publication_command_id_is_stable_and_binds_head(self) -> None:
        first = ing.publication_command_id(
            repository=REPOSITORY, pull_number=PULL_NUMBER, head_sha=HEAD_SHA, job_id=JOB_ID
        )
        again = ing.publication_command_id(
            repository=REPOSITORY, pull_number=PULL_NUMBER, head_sha=HEAD_SHA, job_id=JOB_ID
        )
        moved = ing.publication_command_id(
            repository=REPOSITORY, pull_number=PULL_NUMBER, head_sha=MOVED_HEAD_SHA, job_id=JOB_ID
        )
        assert first == again
        assert first != moved
        assert first.startswith("gh-review-publish:")

    def test_review_body_carries_only_verified_facts(self) -> None:
        body = ing.render_review_body(
            result=_verified(), repository=REPOSITORY, pull_number=PULL_NUMBER
        )
        assert "Verdict: PASS" in body
        assert "worker-reviewer" in body
        assert "worker-builder" in body

# ---------------------------------------------------------------------------
# Audit #1741: publication facts MUST be freshly sourced on exact frozen head.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "changed,refusal",
    [
        ({"state": "closed"}, gri.ReviewIntentRefusal.PULL_REQUEST_NOT_OPEN.value),
        ({"draft": True}, gri.ReviewIntentRefusal.PULL_REQUEST_DRAFT.value),
        ({"head_repository": "attacker/fork"}, gri.ReviewIntentRefusal.HEAD_REPOSITORY_MISMATCH.value),
        ({"title": "xoxb-secret-shaped-token"}, gri.ReviewIntentRefusal.UNTRUSTED_CONTENT_DETECTED.value),
        ({"title": "A" * 13000, "body": "B" * 13000}, gri.ReviewIntentRefusal.UNTRUSTED_CONTENT_DETECTED.value),
        ({"number": 9001}, gri.ReviewIntentRefusal.PULL_NUMBER_MISMATCH.value),
    ],
)
def test_publication_refuses_changed_current_pr_facts_without_head_change(changed, refusal):
    _, admitted = _admitted_decision()
    reads = FakePullRequests(_pull_request(**changed))
    publications = FakePublications()
    result = ing.publish_verified_review(
        decision=admitted.decision,
        job_id=admitted.job_id,
        pull_requests=reads,
        results=FakeResults(_verified(job_id=admitted.job_id)),
        publications=publications,
        admissions=FakeAdmittedJobs(admitted.decision, admitted.job_id),
    )
    assert reads.reads == 1
    assert result.state is ing.PublishState.REFUSED
    assert result.refusal == refusal
    assert publications.calls == []


def test_publication_fetches_current_facts_not_admission_snapshot():
    _, admitted = _admitted_decision()
    reads = FakePullRequests(_pull_request(head_sha=MOVED_HEAD_SHA))
    publications = FakePublications()
    result = ing.publish_verified_review(
        decision=admitted.decision,
        job_id=admitted.job_id,
        pull_requests=reads,
        results=FakeResults(_verified(job_id=admitted.job_id)),
        publications=publications,
        admissions=FakeAdmittedJobs(admitted.decision, admitted.job_id),
    )
    assert reads.reads == 1
    assert result.refusal == gri.ReviewIntentRefusal.HEAD_MOVED.value
    assert publications.calls == []


def test_combined_objective_over_bound_refused_before_ledger():
    fabric = FakeFabric()
    outcome = _admit(
        fabric=fabric,
        pull_requests=FakePullRequests(_pull_request(
            title="A" * 13000, body="B" * 13000
        )),
    )
    assert outcome.state is ing.AdmissionState.REFUSED
    assert outcome.decision.refusal is gri.ReviewIntentRefusal.UNTRUSTED_CONTENT_DETECTED
    assert fabric.admit_calls == 0
    assert fabric.jobs == {}


# Security review #1748 / cabfccbc: source-bound Job and atomic publication.
class TestCurrentHeadIndependentSecurityFindings:
    def test_valid_unrelated_job_b_cannot_publish_its_result_on_pr_a(self):
        _, pr_a = _admitted_decision()
        job_a = pr_a.job_id
        job_b = "JOB-for-valid-other-PR"
        results_b = FakeResults(_verified(job_id=job_b))
        publications = FakePublications()
        current = FakePullRequests()
        owner = FakeAdmittedJobs(pr_a.decision, job_a)
        out = _publish(
            pr_a.decision, job_b, results=results_b,
            publications=publications, pull_requests=current,
            admissions=owner,
        )
        assert out.state is ing.PublishState.REFUSED
        assert out.refusal == "ADMITTED_JOB_SOURCE_IDENTITY_MISMATCH"
        assert owner.lookups == [pr_a.decision.command_id]
        assert results_b.lookups == []
        assert current.reads == 0
        assert publications.calls == []

    def test_swapping_two_genuine_admission_records_never_cross_binds(self):
        _, pr_a = _admitted_decision()
        _, pr_b = _admitted_decision()
        other = ing.AdmittedJobFacts(
            job_id="JOB-B", command_id="gh-review-intent:other",
            repository=REPOSITORY, pull_number=OTHER_PULL_NUMBER,
            frozen_head_sha=MOVED_HEAD_SHA, actor="alice", intent_id="intent-b",
        )
        owner = FakeAdmittedJobs(pr_a.decision, pr_a.job_id, override=other)
        pub = FakePublications()
        outcome = _publish(
            pr_a.decision, "JOB-B",
            results=FakeResults(_verified(job_id="JOB-B")),
            publications=pub, admissions=owner,
        )
        assert outcome.refusal == "ADMITTED_JOB_SOURCE_IDENTITY_MISMATCH"
        assert pub.calls == []

    def test_canonical_job_read_is_required_and_fails_closed(self):
        _, admitted = _admitted_decision()
        with pytest.raises(ing.ReviewIngressUnavailable):
            _publish(admitted.decision, admitted.job_id, admissions=None)
        with pytest.raises(ing.ReviewIngressUnavailable):
            _publish(admitted.decision, admitted.job_id, admissions=object())
        class Unavailable:
            def read_admitted_job(self, *, command_id):
                raise OSError("DB unreachable")
        with pytest.raises(ing.ReviewVerificationRefused, match="ADMITTED_JOB_READ_UNAVAILABLE"):
            _publish(admitted.decision, admitted.job_id, admissions=Unavailable())

    @pytest.mark.parametrize("secret", [
        "xoxb-fake-reviewer-token", "github_pat_not-real-example",
        "authorization: Bearer_secret_here", "-----BEGIN PRIVATE KEY-----",
    ])
    def test_verified_secret_shaped_summary_cannot_be_posted(self, secret):
        _, admitted = _admitted_decision()
        p = FakePublications()
        outcome = _publish(
            admitted.decision, admitted.job_id, publications=p,
            results=FakeResults(_verified(job_id=admitted.job_id, summary=secret)),
        )
        assert outcome.refusal == "REVIEW_SUMMARY_SECRET_SHAPED"
        assert p.calls == []

    def test_concrete_success_sequential_two_calls_post_exactly_once(self):
        tx, ledger = SuccessTransport(), FakeIndex()
        adapter1 = ing.ReconcilingReviewPublication(expected_publisher=EXPECTED_PUBLISHER, before_post=_final_guard(), transport=tx, published=ledger)
        adapter2 = ing.ReconcilingReviewPublication(expected_publisher=EXPECTED_PUBLISHER, before_post=_final_guard(), transport=tx, published=ledger)
        fields = dict(
            publication_command_id="gh-review-publish:" + "c"*32,
            repository=REPOSITORY, pull_number=PULL_NUMBER,
            head_sha=HEAD_SHA, event="COMMENT", body="Reviewed, accepted.",
        )
        assert adapter1.publish_review(**fields) == "review-real"
        assert adapter2.publish_review(**fields) == "review-real"
        assert tx.submits == 1
        assert fields["publication_command_id"] in ledger.published_command_ids()
        assert len(ledger.claims) == 1

    def test_concrete_success_concurrent_across_eight_instances_posts_only_once(self):
        tx, ledger = SuccessTransport(), FakeIndex()
        adapters = [
            ing.ReconcilingReviewPublication(expected_publisher=EXPECTED_PUBLISHER, before_post=_final_guard(), transport=tx, published=ledger)
            for _ in range(8)
        ]
        fields = dict(
            publication_command_id="gh-review-publish:" + "d"*32,
            repository=REPOSITORY, pull_number=PULL_NUMBER,
            head_sha=HEAD_SHA, event="COMMENT", body="Identical reviewed body.",
        )
        def attempt(adapter):
            try:
                return adapter.publish_review(**fields)
            except ing.PublicationEffectUnknown:
                return "EFFECT_UNKNOWN"
        with ThreadPoolExecutor(max_workers=8) as executor:
            outputs = list(executor.map(attempt, adapters))
        assert tx.submits == 1
        assert "review-real" in outputs
        assert all(x in {"review-real", "EFFECT_UNKNOWN"} for x in outputs)
        assert len(ledger.claims) == 1

    def test_effect_claim_is_sticky_if_readback_unavailable(self):
        class BrokenReadback(SuccessTransport):
            def read_reviews(self, **kwargs):
                raise OSError("repository API timeout")
        tx, ledger = BrokenReadback(), FakeIndex()
        adapter = ing.ReconcilingReviewPublication(expected_publisher=EXPECTED_PUBLISHER, before_post=_final_guard(), transport=tx, published=ledger)
        fields = dict(
            publication_command_id="gh-review-publish:" + "e"*32,
            repository=REPOSITORY, pull_number=PULL_NUMBER,
            head_sha=HEAD_SHA, event="COMMENT", body="review",
        )
        for _ in range(2):
            with pytest.raises(ing.PublicationEffectUnknown):
                adapter.publish_review(**fields)
        assert tx.submits == 0
        assert len(ledger.claims) == 1

    def test_concrete_post_unknown_and_readback_failure_remain_effect_unknown(self):
        class LostReadback(SuccessTransport):
            def submit_review(self, **kwargs):
                super().submit_review(**kwargs)
                raise ing.PublicationEffectUnknown("lost POST response")
            def read_reviews(self, **kwargs):
                if self.submits:
                    raise OSError("readback timeout")
                return ()
        tx, ledger = LostReadback(), FakeIndex()
        adapter = ing.ReconcilingReviewPublication(expected_publisher=EXPECTED_PUBLISHER, before_post=_final_guard(), transport=tx, published=ledger)
        fields = dict(
            publication_command_id="gh-review-publish:" + "f"*32,
            repository=REPOSITORY, pull_number=PULL_NUMBER,
            head_sha=HEAD_SHA, event="COMMENT", body="review",
        )
        with pytest.raises(ing.PublicationEffectUnknown):
            adapter.publish_review(**fields)
        with pytest.raises(ing.PublicationEffectUnknown):
            adapter.publish_review(**fields)
        assert tx.submits == 1

    def test_concrete_requires_atomic_canonical_claim_and_conflict_fails(self):
        class ReadOnly:
            def published_command_ids(self):
                return frozenset()
        with pytest.raises(ing.ReviewIngressError):
            ing.ReconcilingReviewPublication(expected_publisher=EXPECTED_PUBLISHER, before_post=_final_guard(), transport=SuccessTransport(), published=ReadOnly())
        ledger = FakeIndex()
        adapter = ing.ReconcilingReviewPublication(expected_publisher=EXPECTED_PUBLISHER, before_post=_final_guard(), transport=SuccessTransport(), published=ledger)
        fields = dict(
            publication_command_id="gh-review-publish:" + "1"*32,
            repository=REPOSITORY, pull_number=PULL_NUMBER,
            head_sha=HEAD_SHA, event="COMMENT", body="review",
        )
        assert adapter.publish_review(**fields) == "review-real"
        with pytest.raises(ing.ReviewVerificationRefused):
            adapter.publish_review(**{**fields, "body": "other review"})

    def test_unavailable_reconciliation_read_stays_typed_unknown(self):
        _, admitted = _admitted_decision()
        class Broken:
            def read_reviews(self, **kwargs):
                raise OSError("lost readback")
        p = FakePublications(unknown=True)
        out = _publish(
            admitted.decision, admitted.job_id, publications=p, readback=Broken()
        )
        assert out.refusal == "PUBLICATION_EFFECT_UNKNOWN"
        assert len(p.calls) == 1

    def test_blank_canonical_admission_does_not_post(self):
        _, admitted = _admitted_decision()
        class Missing:
            def read_admitted_job(self, *, command_id):
                return None
        p = FakePublications()
        out = _publish(admitted.decision, admitted.job_id, admissions=Missing(), publications=p)
        assert out.refusal == "ADMITTED_JOB_SOURCE_IDENTITY_MISMATCH"
        assert p.calls == []


class TestAuthorBoundReadbackAndFinalEffectGuard:
    def test_matching_foreign_review_cannot_confirm_and_first_authorized_writer_posts(self):
        tx, ledger = SuccessTransport(), FakeIndex()
        tx.receipt = ing.PublishedReviewFacts(
            review_id="review-alien", commit_id=HEAD_SHA, event="COMMENT",
            body="same body", author_user_id=99, author_login="other-actor",
        )
        adapter = ing.ReconcilingReviewPublication(
            transport=tx, published=ledger, expected_publisher=EXPECTED_PUBLISHER,
            before_post=_final_guard(),
        )
        fields = dict(
            publication_command_id="gh-review-publish:" + "8" * 32,
            repository=REPOSITORY, pull_number=PULL_NUMBER,
            head_sha=HEAD_SHA, event="COMMENT", body="same body",
        )
        assert adapter.publish_review(**fields) == "review-real"
        assert tx.submits == 1
        assert fields["publication_command_id"] in ledger.published_command_ids()

    def test_alien_readback_does_not_settle_previous_unconfirmed_claim(self):
        tx, ledger = SuccessTransport(), FakeIndex()
        fields = dict(
            publication_command_id="gh-review-publish:" + "9" * 32,
            repository=REPOSITORY, pull_number=PULL_NUMBER,
            head_sha=HEAD_SHA, event="COMMENT", body="same body",
        )
        tx.receipt = ing.PublishedReviewFacts(
            review_id="review-alien", commit_id=HEAD_SHA, event="COMMENT",
            body="same body", author_user_id=99, author_login="other-actor",
        )
        assert ledger.reserve_publication(**fields)
        adapter = ing.ReconcilingReviewPublication(
            transport=tx, published=ledger, expected_publisher=EXPECTED_PUBLISHER,
            before_post=_final_guard(),
        )
        with pytest.raises(ing.PublicationEffectUnknown):
            adapter.publish_review(**fields)
        assert tx.submits == 0
        assert not ledger.published_command_ids()

    @pytest.mark.parametrize("mutation,reason", [
        ({"head_sha": MOVED_HEAD_SHA}, gri.ReviewIntentRefusal.HEAD_MOVED.value),
        ({"draft": True}, gri.ReviewIntentRefusal.PULL_REQUEST_DRAFT.value),
        ({"state": "closed"}, gri.ReviewIntentRefusal.PULL_REQUEST_NOT_OPEN.value),
        ({"head_repository": "other/repo"}, gri.ReviewIntentRefusal.HEAD_REPOSITORY_MISMATCH.value),
    ])
    def test_mutation_during_reviews_get_refuses_before_post(self, mutation, reason):
        _, admitted = _admitted_decision()
        pulls = FakePullRequests()
        class MutatingReadback(SuccessTransport):
            def read_reviews(self, **kwargs):
                pulls.facts = _pull_request(**mutation)
                return super().read_reviews(**kwargs)
        tx, ledger = MutatingReadback(), FakeIndex()
        adapter = ing.ReconcilingReviewPublication(
            transport=tx, published=ledger,
            expected_publisher=EXPECTED_PUBLISHER,
            before_post=ing.FinalPullRequestCheck(
                decision=admitted.decision, pull_requests=pulls,
            ),
        )
        outcome = _publish(
            admitted.decision, admitted.job_id,
            publications=adapter, pull_requests=pulls, readback=tx,
        )
        assert outcome.state is ing.PublishState.REFUSED
        assert outcome.refusal == reason
        assert tx.submits == 0
        assert pulls.reads == 2
        assert len(ledger.claims) == 1

    def test_publisher_id_and_login_both_required(self):
        expected = _review_fact(
            review_id="review-good", commit_id=HEAD_SHA, event="COMMENT", body="body",
        )
        for alien in (
            dataclasses.replace(expected, author_user_id=8),
            dataclasses.replace(expected, author_login="unrelated"),
        ):
            assert ing.reconcile_publication(
                reviews=(alien,), commit_id=HEAD_SHA, event="COMMENT", body="body",
                expected_publisher=EXPECTED_PUBLISHER,
            ) is None

    def test_untrusted_or_missing_publisher_and_final_guard_refuse_at_construction(self):
        tx, ledger = SuccessTransport(), FakeIndex()
        with pytest.raises(TypeError):
            ing.ReconcilingReviewPublication(transport=tx, published=ledger)
        with pytest.raises(ing.ReviewIngressError):
            ing.ReconcilingReviewPublication(
                transport=tx, published=ledger,
                expected_publisher=object(), before_post=_final_guard(),
            )
        with pytest.raises(ing.ReviewIngressError):
            ing.ReconcilingReviewPublication(
                transport=tx, published=ledger,
                expected_publisher=EXPECTED_PUBLISHER, before_post=lambda: None,
            )
        assert tx.submits == 0
