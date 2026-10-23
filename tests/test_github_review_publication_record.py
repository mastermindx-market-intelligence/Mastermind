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


def test_second_gitHub_readback_outage_is_typed_unknown_and_never_reposts(tmp_path):
    class LostReadAfterPost(Transport):
        def read_reviews(self, *, repository, pull_number, commit_id):
            self.reads += 1
            if self.reads >= 2:
                raise RuntimeError("GitHub GET unavailable after ambiguous POST")
            return ()
    gh = LostReadAfterPost(unknown=True, lands=True)
    app, runtime, gh = publisher(tmp_path, gh)
    with pytest.raises(PublicationEffectUnknown, match="EFFECT_UNKNOWN"):
        call(app)
    assert gh.submits == 1
    assert runtime.store.get_event_by_command_id(COMMAND) is not None
    with pytest.raises(PublicationEffectUnknown, match="EFFECT_UNKNOWN"):
        call(app)
    assert gh.submits == 1


def test_preexisting_reservation_unavailable_readback_stays_unknown(tmp_path):
    app, runtime, gh = publisher(tmp_path, Transport(unknown=True, lands=False))
    with pytest.raises(PublicationEffectUnknown):
        call(app)
    def broken_read(*, repository, pull_number, commit_id):
        raise RuntimeError("GitHub readback unavailable")
    gh.read_reviews = broken_read
    with pytest.raises(PublicationEffectUnknown, match="EFFECT_UNKNOWN"):
        call(app)
    assert gh.submits == 1

def test_concurrent_publication_reservation_allows_only_one_github_post(tmp_path):
    """The existing SQLite UNIQUE event command arbitrates concurrent callers.

    The reviewer flagged potential parallel duplicate advisory comments. Hold
    the first POST *after* reservation; another caller must see the reservation
    and may only attempt readback, never a second POST.
    """
    import threading

    entered = threading.Event()
    release = threading.Event()

    class HeldTransport(Transport):
        def submit_review(self, *, repository, pull_number, commit_id, event, body):
            entered.set()
            if not release.wait(timeout=5):
                raise RuntimeError("test publication barrier timed out")
            return super().submit_review(
                repository=repository, pull_number=pull_number,
                commit_id=commit_id, event=event, body=body,
            )

    app, runtime, gh = publisher(tmp_path, HeldTransport())
    success = []
    errors = []

    def first_publisher():
        try:
            success.append(call(app))
        except Exception as exc:
            errors.append(exc)

    thread = threading.Thread(target=first_publisher, daemon=True)
    thread.start()
    try:
        assert entered.wait(timeout=5), "first publisher never reserved"
        with pytest.raises(PublicationEffectUnknown, match="EFFECT_UNKNOWN"):
            call(app)
        assert gh.submits == 0, "second caller must not POST"
    finally:
        release.set()
        thread.join(timeout=5)
    assert not thread.is_alive()
    assert errors == []
    assert success == ["789"]
    assert gh.submits == 1
    assert call(app) == "789"
    assert gh.submits == 1
    assert runtime.store.get_event_by_command_id(COMMAND + ":confirmed") is not None

def test_publication_guard_revoked_during_readback_refuses_before_post(tmp_path):
    allowed = {"value": True}

    def guard():
        if not allowed["value"]:
            raise PermissionError("review publishing revoked")

    class RevokingReadback(Transport):
        def read_reviews(self, *, repository, pull_number, commit_id):
            allowed["value"] = False
            return super().read_reviews(
                repository=repository, pull_number=pull_number, commit_id=commit_id
            )

    app, runtime, gh = publisher(tmp_path, transport=RevokingReadback(), guard=guard)
    with pytest.raises(ReviewVerificationRefused, match="NOT_AUTHORIZED"):
        call(app)
    assert gh.submits == 0
    assert runtime.store.get_event_by_command_id(COMMAND) is not None
    assert COMMAND not in app.published_command_ids()
