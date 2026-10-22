"""Real Executive event UNIQUE index arbitrates formal GitHub review effects."""
import httpx
import pytest

from control_plane.executive_runtime import Runtime
from control_plane.github_review_intent_ingress import (
    PublicationEffectUnknown, ReviewVerificationRefused,
    PublishedReviewFacts, publication_command_id,
)
from control_plane.github_review_publication_record import (
    ExecutiveReviewPublicationRecord,
)

REPO = "example/repo"
HEAD = "a" * 40
JOB = "JOB-777"
BODY = "Advisory review from independently verified worker."
COMMAND = publication_command_id(
    repository=REPO, pull_number=42, head_sha=HEAD, job_id=JOB,
)


class Transport:
    def __init__(self, *, unknown=False, lands=True, preexisting=False):
        self.unknown = unknown
        self.lands = lands
        self.submits = 0
        self.reads = 0
        self.review = (
            PublishedReviewFacts(
                review_id="789", commit_id=HEAD, event="COMMENT", body=BODY,
            ) if preexisting else None
        )
    def submit_review(self, *, repository, pull_number, commit_id, event, body):
        assert (repository, pull_number, commit_id, event, body) == (
            REPO, 42, HEAD, "COMMENT", BODY
        )
        self.submits += 1
        if self.lands:
            self.review = PublishedReviewFacts(
                review_id="789", commit_id=HEAD, event=event, body=body
            )
        if self.unknown:
            raise PublicationEffectUnknown("unknown")
        return "789"
    def read_reviews(self, *, repository, pull_number, commit_id):
        assert (repository, pull_number, commit_id) == (REPO, 42, HEAD)
        self.reads += 1
        return (self.review,) if self.review is not None else ()


def publisher(tmp_path, transport=None, guard=lambda: None, runtime=None):
    runtime = runtime or Runtime.at(tmp_path)
    transport = transport or Transport()
    return ExecutiveReviewPublicationRecord(
        runtime=runtime, transport=transport, job_id=JOB,
        publication_guard=guard,
    ), runtime, transport


def call(instance, *, body=BODY, event="COMMENT"):
    return instance.publish_review(
        publication_command_id=COMMAND, repository=REPO,
        pull_number=42, head_sha=HEAD, event=event, body=body,
    )


def test_one_real_sqlite_reservation_one_github_post_and_confirmed_readback(tmp_path):
    app, runtime, gh = publisher(tmp_path)
    assert app.published_command_ids() == frozenset()
    assert call(app) == "789"
    assert gh.submits == 1
    assert COMMAND in app.published_command_ids()
    assert call(app) == "789"
    assert gh.submits == 1
    assert runtime.store.get_event_by_command_id(COMMAND).event_type == (
        "GITHUB_REVIEW_PUBLICATION_RESERVED"
    )
    assert runtime.store.get_event_by_command_id(COMMAND + ":confirmed").payload[
        "review_id"
    ] == "789"


def test_uncertain_post_reconciles_success_without_repeating(tmp_path):
    app, runtime, gh = publisher(tmp_path, Transport(unknown=True, lands=True))
    assert call(app) == "789"
    assert gh.submits == 1
    assert COMMAND in app.published_command_ids()


def test_lost_effect_remains_reserved_without_duplicate_post(tmp_path):
    app, runtime, gh = publisher(tmp_path, Transport(unknown=True, lands=False))
    with pytest.raises(PublicationEffectUnknown):
        call(app)
    assert gh.submits == 1
    assert COMMAND not in app.published_command_ids()
    with pytest.raises(PublicationEffectUnknown):
        call(app)
    assert gh.submits == 1


def test_earlier_github_review_reconciles_after_missing_local_receipt(tmp_path):
    app, runtime, gh = publisher(tmp_path, Transport(preexisting=True))
    assert call(app) == "789"
    assert gh.submits == 0
    assert COMMAND in app.published_command_ids()


def test_existing_reservation_later_readback_repairs_local_commit(tmp_path):
    app, runtime, gh = publisher(tmp_path, Transport(unknown=True, lands=False))
    with pytest.raises(PublicationEffectUnknown):
        call(app)
    gh.review = PublishedReviewFacts(
        review_id="789", commit_id=HEAD, event="COMMENT", body=BODY,
    )
    assert call(app) == "789"
    assert gh.submits == 1
    assert COMMAND in app.published_command_ids()


def test_same_command_cannot_change_review_body_or_verb(tmp_path):
    app, runtime, gh = publisher(tmp_path)
    assert call(app) == "789"
    with pytest.raises(ReviewVerificationRefused, match="CONFLICT"):
        call(app, body="changed")
    with pytest.raises(ReviewVerificationRefused, match="CONFLICT"):
        call(app, event="REQUEST_CHANGES")
    assert gh.submits == 1


def test_publication_unarmed_never_reads_or_writes(tmp_path):
    app, runtime, gh = publisher(tmp_path, guard=None)
    with pytest.raises(ReviewVerificationRefused, match="UNARMED"):
        call(app)
    assert gh.submits == gh.reads == 0
    assert runtime.store.get_event_by_command_id(COMMAND) is None


def test_guard_retracts_during_claim_transaction(tmp_path):
    seen = []
    def retract():
        seen.append(True)
        if len(seen) > 1:
            raise PermissionError("retracted")
    app, runtime, gh = publisher(tmp_path, guard=retract)
    with pytest.raises(ReviewVerificationRefused, match="NOT_AUTHORIZED"):
        call(app)
    assert gh.submits == 0
    assert runtime.store.get_event_by_command_id(COMMAND) is None
