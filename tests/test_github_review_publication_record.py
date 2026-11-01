"""Real Executive event UNIQUE index arbitrates formal GitHub review effects."""
import pytest

from control_plane.executive_runtime import Runtime
from control_plane.github_review_intent import PullRequestFacts
from control_plane.github_review_intent_ingress import (
    ExpectedReviewPublisher, ExternalCommentAdvisory, ExternalGitHubSourceFacts,
    FinalPostRefusal, PublicationEffectUnknown, ReviewVerificationRefused,
    PublishedReviewFacts, publication_command_id,
)
from control_plane.github_review_publication_record import (
    ExecutiveReviewPublicationRecord,
)
from test_github_review_runtime_adapter import decision

REPO = "example/repo"
HEAD = "a" * 40
JOB = "JOB-777"
BODY = "Advisory review from independently verified worker."
COMMAND = publication_command_id(
    repository=REPO, pull_number=42, head_sha=HEAD, job_id=JOB,
)
PUBLISHER = ExpectedReviewPublisher(user_id=9001, login="reviewer-bot[bot]")


def review_fact(**overrides):
    base = dict(
        review_id="789", commit_id=HEAD, event="COMMENT", body=BODY,
        author_user_id=PUBLISHER.user_id, author_login=PUBLISHER.login,
    )
    base.update(overrides)
    return PublishedReviewFacts(**base)


class OpenPull:
    def __init__(self, **overrides):
        self.overrides = overrides
        self.reads = 0

    def read_pull_request(self, *, repository, pull_number):
        self.reads += 1
        base = dict(
            repository=REPO, number=42, state="open", draft=False,
            head_sha=HEAD, head_repository=REPO, base_repository=REPO,
            base_sha="c" * 40, title="Reviewed source",
            body="Separate worker review.",
        )
        base.update(self.overrides)
        return PullRequestFacts(**base)


class Transport:
    def __init__(self, *, unknown=False, lands=True, preexisting=False):
        self.unknown = unknown
        self.lands = lands
        self.submits = 0
        self.reads = 0
        self.review = review_fact() if preexisting else None
    def submit_review(self, *, repository, pull_number, commit_id, event, body):
        assert (repository, pull_number, commit_id, event, body) == (
            REPO, 42, HEAD, "COMMENT", BODY
        )
        self.submits += 1
        if self.lands:
            self.review = review_fact(event=event, body=body)
        if self.unknown:
            raise PublicationEffectUnknown("unknown")
        return "789"
    def read_reviews(self, *, repository, pull_number, commit_id):
        assert (repository, pull_number, commit_id) == (REPO, 42, HEAD)
        self.reads += 1
        return (self.review,) if self.review is not None else ()


def publisher(tmp_path, transport=None, guard=lambda: None, runtime=None, pulls=None):
    runtime = runtime or Runtime.at(tmp_path)
    transport = transport or Transport()
    pulls = pulls or OpenPull()
    return ExecutiveReviewPublicationRecord(
        runtime=runtime, transport=transport, job_id=JOB,
        publication_guard=guard,
        expected_publisher=PUBLISHER,
        decision=decision(),
        pull_requests=pulls,
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
    gh.review = review_fact()
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


@pytest.mark.parametrize("author", [
    {"author_user_id": 8},
    {"author_login": "other-actor"},
])
def test_identical_body_from_a_different_author_still_posts_once(tmp_path, author):
    gh = Transport(preexisting=True)
    gh.review = review_fact(**author)
    app, runtime, transport = publisher(tmp_path, gh)
    assert call(app) == "789"
    assert transport.submits == 1
    assert COMMAND in app.published_command_ids()
    stored = runtime.store.get_event_by_command_id(COMMAND + ":confirmed")
    assert stored.payload["review_id"] == "789"


@pytest.mark.parametrize("mutation,code", [
    ({"head_sha": "b" * 40}, "HEAD_MOVED"),
    ({"draft": True}, "PULL_REQUEST_DRAFT"),
    ({"state": "closed"}, "PULL_REQUEST_NOT_OPEN"),
    ({"head_repository": "other/repo"}, "HEAD_REPOSITORY_MISMATCH"),
])
def test_mutation_during_reviews_get_refuses_before_post(tmp_path, mutation, code):
    pulls = OpenPull()

    class Mutating(Transport):
        def read_reviews(self, *, repository, pull_number, commit_id):
            pulls.overrides.update(mutation)
            return super().read_reviews(
                repository=repository, pull_number=pull_number, commit_id=commit_id
            )

    app, runtime, gh = publisher(tmp_path, Mutating(), pulls=pulls)
    with pytest.raises(FinalPostRefusal, match=code):
        call(app)
    assert gh.submits == 0
    assert runtime.store.get_event_by_command_id(COMMAND) is not None
    assert COMMAND not in app.published_command_ids()
    with pytest.raises(PublicationEffectUnknown):
        call(app)
    assert gh.submits == 0


class DraftAdvisoryPull(OpenPull):
    def __init__(self, *, submitter_id=314, submitter_login="alice"):
        super().__init__(draft=True)
        self.submitter_id = submitter_id
        self.submitter_login = submitter_login

    def read_external_source(self, *, repository, pull_number):
        return ExternalGitHubSourceFacts(
            repository=repository, pull_number=pull_number, head_sha=HEAD,
            submitter_login=self.submitter_login, submitter_id=self.submitter_id,
        )


def test_approve_verb_is_refused_before_reservation(tmp_path):
    app, runtime, gh = publisher(tmp_path)
    with pytest.raises(ReviewVerificationRefused, match="VERB_REFUSED"):
        call(app, event="APPROVE")
    assert gh.submits == gh.reads == 0
    assert runtime.store.get_event_by_command_id(COMMAND) is None


def test_unsealed_draft_is_not_a_bypass(tmp_path):
    app, runtime, gh = publisher(tmp_path, pulls=DraftAdvisoryPull())
    with pytest.raises(FinalPostRefusal, match="PULL_REQUEST_DRAFT"):
        call(app)
    assert gh.submits == 0
    assert runtime.store.get_event_by_command_id(COMMAND) is not None


def test_sealed_comment_advisory_posts_once_on_a_draft(tmp_path):
    app, runtime, gh = publisher(tmp_path, pulls=DraftAdvisoryPull())
    app.seal_external_comment_advisory(ExternalCommentAdvisory(
        submitter_user_id=314, submitter_login="alice",
    ))
    assert call(app) == "789"
    assert gh.submits == 1
    assert call(app) == "789"
    assert gh.submits == 1


def test_sealed_advisory_cannot_use_request_changes(tmp_path):
    app, runtime, gh = publisher(tmp_path, pulls=DraftAdvisoryPull())
    app.seal_external_comment_advisory(ExternalCommentAdvisory(
        submitter_user_id=314, submitter_login="alice",
    ))
    with pytest.raises(FinalPostRefusal, match="EXTERNAL_ADVISORY_VERB_REFUSED"):
        call(app, event="REQUEST_CHANGES")
    assert gh.submits == 0
    assert runtime.store.get_event_by_command_id(COMMAND) is not None
    assert COMMAND not in app.published_command_ids()


def test_sealed_advisory_refuses_submitter_drift_before_post(tmp_path):
    app, runtime, gh = publisher(
        tmp_path, pulls=DraftAdvisoryPull(submitter_id=315),
    )
    app.seal_external_comment_advisory(ExternalCommentAdvisory(
        submitter_user_id=314, submitter_login="alice",
    ))
    with pytest.raises(FinalPostRefusal, match="EXTERNAL_SOURCE_DRIFT"):
        call(app)
    assert gh.submits == 0
    assert COMMAND not in app.published_command_ids()
