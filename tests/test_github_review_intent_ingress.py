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
* D5 a moved head refuses publication instead of silently re-pointing the
  review at the new commit.
* D6 publication is refused for an unverified result, an out-of-vocabulary
  verdict, an unknown reviewer, or a reviewer who is the builder.
* D7 a publish retry reconciles to the same publication command and never posts
  a second formal review.
* D8 a ``PASS`` verdict publishes a *comment*; no path mints ``APPROVE`` or any
  merge verb.
* D9 visibility never gates an admission: a raising Slack client is recorded,
  never propagated, and never re-admits.

Guard-test law: this file is the guard for every production module in the diff
(``control_plane/github_review_intent.py``,
``control_plane/github_review_intent_ingress.py``).  No marker is used anywhere
in this file (nothing is gated to one platform).
"""
from __future__ import annotations

import json

import pytest

from control_plane import github_review_intent as gri
from control_plane import github_review_intent_ingress as ing


SECRET = "webhook-secret-value"
REPOSITORY = "mastermindx-market-intelligence/Mastermind"
HEAD_SHA = "a" * 40
MOVED_HEAD_SHA = "b" * 40
DELIVERY_ID = "11111111-2222-3333-4444-555555555555"
JOB_ID = "JOB-042"


def _policy() -> gri.ReviewIntentPolicy:
    return gri.ReviewIntentPolicy(
        repositories=frozenset({REPOSITORY}),
        installation_ids=frozenset({4242}),
        configured_reviewer="mastermind-reviewer",
        authorized_actors=frozenset({"alice"}),
    )


def _pull_request(**overrides) -> gri.PullRequestFacts:
    base = {
        "repository": REPOSITORY,
        "number": 1739,
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


def _label_body(*, sender="alice", label="independent-review") -> bytes:
    return json.dumps(
        {
            "action": "labeled",
            "installation": {"id": 4242},
            "repository": {"full_name": REPOSITORY},
            "sender": {"login": sender},
            "label": {"name": label},
        }
    ).encode("utf-8")


# ---------------------------------------------------------------------------
# fake ports
# ---------------------------------------------------------------------------


class FakePullRequests:
    def __init__(self, facts: gri.PullRequestFacts) -> None:
        self.facts = facts
        self.reads = 0

    def read_pull_request(self, *, repository: str, pull_number: int) -> gri.PullRequestFacts:
        self.reads += 1
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


class FakeVisibility:
    def __init__(self, *, boom: bool = False) -> None:
        self.admitted: list[str] = []
        self.refused: list[str] = []
        self._boom = boom

    def notify_review_admitted(self, *, summary, decision, job_id) -> None:
        if self._boom:
            raise RuntimeError("slack transport unavailable")
        self.admitted.append(summary)

    def notify_review_refused(self, *, summary, decision) -> None:
        if self._boom:
            raise RuntimeError("slack transport unavailable")
        self.refused.append(summary)


class FakeResults:
    def __init__(self, result: ing.VerifiedReviewResult | None) -> None:
        self.result = result
        self.lookups: list[str] = []

    def load_verified_result(self, *, job_id: str):
        self.lookups.append(job_id)
        return self.result


class FakePublications:
    def __init__(self) -> None:
        self.published: dict[str, str] = {}
        self.calls: list[dict] = []

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
        if publication_command_id not in self.published:
            self.published[publication_command_id] = f"review-{len(self.published) + 1}"
        return self.published[publication_command_id]


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
    visibility=None,
    event="pull_request",
    signature: str | None = None,
):
    payload = body if body is not None else _label_body()
    fabric_port = fabric or FakeFabric()
    reads = pull_requests or FakePullRequests(_pull_request())
    if signature is None:
        signature = gri.sign_webhook_body(secret=SECRET, body=payload)
    return ing.admit_review_intent(
        secret=SECRET,
        body=payload,
        delivery_id=DELIVERY_ID,
        event=event,
        signature_header=signature,
        pull_number=1739,
        policy=_policy(),
        pull_requests=reads,
        fabric=fabric_port,
        visibility=visibility,
    )


def _admitted_decision():
    fabric = FakeFabric()
    outcome = _admit(fabric=fabric)
    assert outcome.state is ing.AdmissionState.ADMITTED
    return fabric, outcome


# ---------------------------------------------------------------------------
# D1/D2 — signature and unsupported channels
# ---------------------------------------------------------------------------


class TestSignatureStopsTheWalk:
    def test_bad_signature_raises_before_any_read_or_write(self) -> None:
        reads = FakePullRequests(_pull_request())
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
        reads = FakePullRequests(_pull_request())
        outcome = _admit(_label_body(), pull_requests=reads, event="push")
        assert outcome.state is ing.AdmissionState.REFUSED
        assert outcome.decision.refusal is gri.ReviewIntentRefusal.EVENT_NOT_SUPPORTED
        assert reads.reads == 0

    def test_unsupported_action_is_refused_without_a_read(self) -> None:
        parsed = json.loads(_label_body())
        parsed["action"] = "opened"
        reads = FakePullRequests(_pull_request())
        outcome = _admit(json.dumps(parsed).encode(), pull_requests=reads)
        assert outcome.decision.refusal is gri.ReviewIntentRefusal.ACTION_NOT_SUPPORTED
        assert reads.reads == 0


# ---------------------------------------------------------------------------
# D3/D9 — the admitted walk
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
            _label_body(), fabric=fabric, pull_requests=FakePullRequests(
                _pull_request(head_sha=MOVED_HEAD_SHA)
            )
        )
        assert moved.state is ing.AdmissionState.ADMITTED
        assert len(fabric.jobs) == 2

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
        assert outcome.visibility_error is not None
        assert "slack transport unavailable" in outcome.visibility_error

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
                pull_number=1739,
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
                pull_number=1739,
                policy=_policy(),
                pull_requests=FakePullRequests(_pull_request()),
                fabric=None,
            )

    def test_missing_result_port_refuses_publication(self) -> None:
        _, outcome = _admitted_decision()
        with pytest.raises(ing.ReviewIngressUnavailable):
            ing.publish_verified_review(
                decision=outcome.decision,
                job_id=outcome.job_id,
                pull_request=_pull_request(),
                results=None,
                publications=FakePublications(),
            )


# ---------------------------------------------------------------------------
# D5/D6/D7/D8 — publication
# ---------------------------------------------------------------------------


class TestPublication:
    def test_verified_independent_review_publishes(self) -> None:
        _, outcome = _admitted_decision()
        publications = FakePublications()
        published = ing.publish_verified_review(
            decision=outcome.decision,
            job_id=outcome.job_id,
            pull_request=_pull_request(),
            results=FakeResults(_verified(job_id=outcome.job_id)),
            publications=publications,
        )
        assert published.state is ing.PublishState.PUBLISHED
        assert published.review_id == "review-1"
        assert publications.calls[0]["head_sha"] == HEAD_SHA

    def test_pass_publishes_a_comment_never_an_approval(self) -> None:
        assert ing.REVIEW_VERDICT_EVENTS["PASS"] == "COMMENT"
        assert "APPROVE" not in ing.REVIEW_VERDICT_EVENTS.values()

    def test_request_changes_maps_to_the_github_verb(self) -> None:
        _, outcome = _admitted_decision()
        publications = FakePublications()
        ing.publish_verified_review(
            decision=outcome.decision,
            job_id=outcome.job_id,
            pull_request=_pull_request(),
            results=FakeResults(_verified(job_id=outcome.job_id, verdict="REQUEST_CHANGES")),
            publications=publications,
        )
        assert publications.calls[0]["event"] == "REQUEST_CHANGES"

    def test_publish_retry_does_not_post_a_second_review(self) -> None:
        _, outcome = _admitted_decision()
        publications = FakePublications()
        results = FakeResults(_verified(job_id=outcome.job_id))
        first = ing.publish_verified_review(
            decision=outcome.decision,
            job_id=outcome.job_id,
            pull_request=_pull_request(),
            results=results,
            publications=publications,
        )
        second = ing.publish_verified_review(
            decision=outcome.decision,
            job_id=outcome.job_id,
            pull_request=_pull_request(),
            results=results,
            publications=publications,
        )
        assert first.state is ing.PublishState.PUBLISHED
        assert second.state is ing.PublishState.ALREADY_PUBLISHED
        assert len(publications.calls) == 1

    def test_moved_head_refuses_publication(self) -> None:
        _, outcome = _admitted_decision()
        publications = FakePublications()
        published = ing.publish_verified_review(
            decision=outcome.decision,
            job_id=outcome.job_id,
            pull_request=_pull_request(head_sha=MOVED_HEAD_SHA),
            results=FakeResults(_verified(job_id=outcome.job_id)),
            publications=publications,
        )
        assert published.state is ing.PublishState.REFUSED
        assert published.refusal == gri.ReviewIntentRefusal.HEAD_MOVED.value
        assert publications.calls == []

    def test_unverified_result_refuses_publication(self) -> None:
        _, outcome = _admitted_decision()
        publications = FakePublications()
        published = ing.publish_verified_review(
            decision=outcome.decision,
            job_id=outcome.job_id,
            pull_request=_pull_request(),
            results=FakeResults(None),
            publications=publications,
        )
        assert published.refusal == "RESULT_NOT_VERIFIED"
        assert publications.calls == []

    def test_reviewer_equal_to_builder_refuses_publication(self) -> None:
        _, outcome = _admitted_decision()
        publications = FakePublications()
        published = ing.publish_verified_review(
            decision=outcome.decision,
            job_id=outcome.job_id,
            pull_request=_pull_request(),
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
        published = ing.publish_verified_review(
            decision=outcome.decision,
            job_id=outcome.job_id,
            pull_request=_pull_request(),
            results=FakeResults(_verified(job_id=outcome.job_id, reviewer_worker_id="")),
            publications=publications,
        )
        assert published.refusal == "REVIEWER_IDENTITY_UNKNOWN"
        assert publications.calls == []

    def test_out_of_vocabulary_verdict_refuses_publication(self) -> None:
        _, outcome = _admitted_decision()
        publications = FakePublications()
        published = ing.publish_verified_review(
            decision=outcome.decision,
            job_id=outcome.job_id,
            pull_request=_pull_request(),
            results=FakeResults(_verified(job_id=outcome.job_id, verdict="LGTM")),
            publications=publications,
        )
        assert published.refusal == "VERDICT_OUTSIDE_VOCABULARY"
        assert publications.calls == []

    def test_result_from_another_job_refuses_publication(self) -> None:
        _, outcome = _admitted_decision()
        published = ing.publish_verified_review(
            decision=outcome.decision,
            job_id=outcome.job_id,
            pull_request=_pull_request(),
            results=FakeResults(_verified(job_id="JOB-999")),
            publications=FakePublications(),
        )
        assert published.refusal == "RESULT_JOB_IDENTITY_DRIFT"

    def test_refused_decision_cannot_publish(self) -> None:
        outcome = _admit(_label_body(sender="stranger"))
        with pytest.raises(ing.ReviewVerificationRefused):
            ing.publish_verified_review(
                decision=outcome.decision,
                job_id="JOB-001",
                pull_request=_pull_request(),
                results=FakeResults(_verified()),
                publications=FakePublications(),
            )

    def test_publication_command_id_is_stable_and_binds_head(self) -> None:
        first = ing.publication_command_id(
            repository=REPOSITORY, pull_number=1739, head_sha=HEAD_SHA, job_id=JOB_ID
        )
        again = ing.publication_command_id(
            repository=REPOSITORY, pull_number=1739, head_sha=HEAD_SHA, job_id=JOB_ID
        )
        moved = ing.publication_command_id(
            repository=REPOSITORY, pull_number=1739, head_sha=MOVED_HEAD_SHA, job_id=JOB_ID
        )
        assert first == again
        assert first != moved
        assert first.startswith("gh-review-publish:")

    def test_review_body_carries_only_verified_facts(self) -> None:
        body = ing.render_review_body(
            result=_verified(), repository=REPOSITORY, pull_number=1739
        )
        assert "Verdict: PASS" in body
        assert "worker-reviewer" in body
        assert "worker-builder" in body