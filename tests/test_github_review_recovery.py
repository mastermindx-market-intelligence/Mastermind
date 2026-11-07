"""Recover known review effects without rerunning workers or uncertain POSTs."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import dataclasses
import hashlib
import threading

import pytest

from control_plane.executive_runtime import Runtime
from control_plane.github_review_intent_ingress import (
    FinalPostRefusal, PublicationEffectUnknown, PublicationPreflightUnavailable,
    PublishState, ReviewVerificationRefused,
)
from integrations.github_review_return import GitHubReviewReturn, ReviewReturnSourceMode
from test_github_review_publication_record import (
    BODY, COMMAND, HEAD, JOB, PUBLISHER, REPO, OpenPull, Transport, call,
    publisher, review_fact,
)
from test_github_review_publish_workflow import git_api
from test_github_review_result_reader import completed_pair
from test_github_review_runtime_adapter import decision


def test_unavailable_review_get_does_not_reserve_and_fresh_preflight_recovers(tmp_path):
    class OnceUnavailable(Transport):
        def read_reviews(self, **kwargs):
            if not self.reads:
                self.reads += 1
                raise OSError("temporary read failure")
            return super().read_reviews(**kwargs)

    app, runtime, gh = publisher(tmp_path, OnceUnavailable())
    with pytest.raises(PublicationPreflightUnavailable):
        call(app)
    assert runtime.store.get_event_by_command_id(COMMAND) is None
    assert gh.submits == 0
    assert call(app) == "789"
    assert gh.submits == 1


def test_unavailable_final_pr_read_does_not_consume_publication(tmp_path):
    class OnceUnavailable(OpenPull):
        def read_pull_request(self, **kwargs):
            if not self.reads:
                self.reads += 1
                raise OSError("temporary source read")
            return super().read_pull_request(**kwargs)

    app, runtime, gh = publisher(tmp_path, pulls=OnceUnavailable())
    with pytest.raises(FinalPostRefusal, match="POST_GUARD_READ_UNAVAILABLE"):
        call(app)
    assert runtime.store.get_event_by_command_id(COMMAND) is None
    assert gh.submits == 0
    assert call(app) == "789"
    assert gh.submits == 1


def test_database_wait_expires_preflight_before_reservation(tmp_path, monkeypatch):
    app, runtime, gh = publisher(tmp_path)
    now = [10.0]
    app._clock = lambda: now[0]
    transaction = runtime.store.transaction

    @contextmanager
    def delayed_transaction():
        with transaction() as conn:
            now[0] += 4.0  # lock acquisition delay, without a real sleep
            yield conn

    monkeypatch.setattr(runtime.store, "transaction", delayed_transaction)
    with pytest.raises(PublicationPreflightUnavailable, match="EXPIRED"):
        call(app)
    assert gh.submits == 0
    assert runtime.store.get_event_by_command_id(COMMAND) is None
    monkeypatch.setattr(runtime.store, "transaction", transaction)
    assert call(app) == "789"


def test_delay_after_committed_claim_remains_unknown_without_post(tmp_path, monkeypatch):
    app, runtime, gh = publisher(tmp_path)
    now = [10.0]
    app._clock = lambda: now[0]
    transaction = runtime.store.transaction

    @contextmanager
    def slow_commit():
        with transaction() as conn:
            yield conn
        now[0] += 4.0

    monkeypatch.setattr(runtime.store, "transaction", slow_commit)
    with pytest.raises(PublicationEffectUnknown, match="EXPIRED_AFTER_CLAIM"):
        call(app)
    assert runtime.store.get_event_by_command_id(COMMAND) is not None
    assert gh.submits == 0
    monkeypatch.setattr(runtime.store, "transaction", transaction)
    with pytest.raises(PublicationEffectUnknown):
        call(app)
    assert gh.submits == 0


def test_two_runtime_connections_race_preflight_but_only_one_can_post(tmp_path):
    barrier = threading.Barrier(2)

    class Together(OpenPull):
        def read_pull_request(self, **kwargs):
            result = super().read_pull_request(**kwargs)
            barrier.wait(timeout=5)
            return result

    gh = Transport()
    first, runtime, _ = publisher(tmp_path, gh, pulls=Together())
    second, _, _ = publisher(tmp_path, gh, runtime=Runtime.at(tmp_path), pulls=Together())

    def attempt(app):
        try:
            return call(app)
        except PublicationEffectUnknown:
            return "UNKNOWN"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, (first, second)))
    assert "789" in results
    assert gh.submits == 1
    assert runtime.store.get_event_by_command_id(COMMAND + ":confirmed") is not None


def recovered(app):
    return app.reconcile_existing_publication(
        publication_command_id=COMMAND, repository=REPO,
        pull_number=42, head_sha=HEAD, job_id=JOB,
    )


def test_new_reservation_retains_original_publisher(tmp_path):
    app, runtime, gh = publisher(tmp_path)
    assert call(app) == "789"
    identity = runtime.store.get_event_by_command_id(COMMAND).payload
    assert identity["schema"] == "mastermind.github_review_publication_event.v2"
    assert identity["publisher_user_id"] == PUBLISHER.user_id
    assert identity["publisher_login"] == PUBLISHER.login


@pytest.mark.parametrize("source_mode", list(ReviewReturnSourceMode))
def test_landed_review_recovers_after_head_moves_without_rechecking_new_source(tmp_path, source_mode):
    runtime, builder, review = completed_pair(tmp_path)
    github, history = git_api(unknown_post=True, readback_unavailable_after_post=True)
    args = {"builder_job_id_for_review": lambda _: builder} if source_mode is ReviewReturnSourceMode.EXECUTIVE_BUILDER else {}
    handler = GitHubReviewReturn.for_authorized_source(
        runtime=runtime, github=github, publication_guard=lambda: None,
        source_mode=source_mode, **args,
    )
    first = handler.deliver(decision=decision(), job_id=review)
    assert first.publication.refusal == "PUBLICATION_EFFECT_UNKNOWN"
    assert len(history["posts"]) == 1
    reads = history["source_reads"]
    history.update(moved_head=True, readback_unavailable_after_post=False)
    second = handler.deliver(decision=decision(), job_id=review)
    assert second.publication.state is PublishState.ALREADY_PUBLISHED
    assert second.publication.review_id == "789"
    assert len(history["posts"]) == 1
    assert history["source_reads"] == reads
    assert handler.deliver(decision=decision(), job_id=review).publication.review_id == "789"


@pytest.mark.parametrize("mutation", ["body", "commit", "publisher_id", "publisher_login", "duplicate"])
def test_ambiguous_or_foreign_historical_readback_never_confirms_or_posts(tmp_path, mutation):
    runtime, builder, review = completed_pair(tmp_path)
    github, history = git_api(unknown_post=True, readback_unavailable_after_post=True)
    handler = GitHubReviewReturn.for_authorized_source(
        runtime=runtime, github=github, publication_guard=lambda: None,
        source_mode=ReviewReturnSourceMode.EXTERNAL_GITHUB_ADVISORY,
    )
    first = handler.deliver(decision=decision(), job_id=review)
    assert first.publication.refusal == "PUBLICATION_EFFECT_UNKNOWN"
    history.update(moved_head=True, readback_unavailable_after_post=False)
    row = history["reviews"][0]
    if mutation == "body":
        row["body"] += "changed"
    elif mutation == "commit":
        row["commit_id"] = "b" * 40
    elif mutation == "publisher_id":
        row["user"]["id"] += 1
    elif mutation == "publisher_login":
        row["user"]["login"] = "another-bot[bot]"
    else:
        history["reviews"].append({**row, "id": 790})
    second = handler.deliver(decision=decision(), job_id=review)
    assert second.publication.refusal == "PUBLICATION_EFFECT_UNKNOWN"
    assert len(history["posts"]) == 1
    assert runtime.store.get_event_by_command_id(first.publication.publication_command_id + ":confirmed") is None


def test_return_uses_exact_publication_index_not_history_scan(tmp_path, monkeypatch):
    runtime, builder, review = completed_pair(tmp_path)
    github, history = git_api()
    listing = runtime.store.list_events

    def bounded(**kwargs):
        assert kwargs.get("command_id_prefix") != "gh-review-publish:", "whole publication history loaded"
        return listing(**kwargs)

    monkeypatch.setattr(runtime.store, "list_events", bounded)
    handler = GitHubReviewReturn.for_authorized_source(
        runtime=runtime, github=github, publication_guard=lambda: None,
        source_mode=ReviewReturnSourceMode.EXECUTIVE_BUILDER,
        builder_job_id_for_review=lambda _: builder,
    )
    assert handler.deliver(decision=decision(), job_id=review).publication.state is PublishState.PUBLISHED
    assert handler.deliver(decision=decision(), job_id=review).publication.state is PublishState.ALREADY_PUBLISHED
    assert len(history["posts"]) == 1


@pytest.mark.parametrize("confirmed", [False, True])
def test_legacy_receipt_preserves_facts_without_inventing_original_publisher(tmp_path, confirmed):
    app, runtime, gh = publisher(tmp_path, Transport(preexisting=True))
    identity = {
        "schema": "mastermind.github_review_publication_event.v1", "job_id": JOB,
        "repository": REPO, "pull_number": 42, "head_sha": HEAD,
        "event": "COMMENT", "body_sha256": hashlib.sha256(BODY.encode()).hexdigest(),
    }
    with runtime.store.transaction() as conn:
        runtime.store.append_event(
            conn, aggregate_type="github_review_publication", aggregate_id=COMMAND,
            event_type="GITHUB_REVIEW_PUBLICATION_RESERVED", command_id=COMMAND,
            actor="github-review-publisher", payload=identity,
        )
        if confirmed:
            runtime.store.append_event(
                conn, aggregate_type="github_review_publication", aggregate_id=COMMAND,
                event_type="GITHUB_REVIEW_PUBLICATION_CONFIRMED", command_id=COMMAND + ":confirmed",
                actor="github-review-publisher", payload={**identity, "identity": identity,
                    "original_command_id": COMMAND, "review_id": "789"},
            )
    if confirmed:
        assert recovered(app) == "789"
        assert call(app) == "789"  # original public port remains compatible
        with pytest.raises(ReviewVerificationRefused, match="CONFLICT"):
            app.publish_review(publication_command_id=COMMAND, repository=REPO,
                pull_number=42, head_sha=HEAD, event="COMMENT", body=BODY + "changed")
    else:
        with pytest.raises(PublicationEffectUnknown, match="ORIGINAL_PUBLISHER_UNAVAILABLE"):
            recovered(app)
        with pytest.raises(PublicationEffectUnknown, match="ORIGINAL_PUBLISHER_UNAVAILABLE"):
            call(app)
    assert gh.reads == gh.submits == 0


def test_duplicate_matching_reviews_are_not_arbitrarily_selected(tmp_path):
    class Duplicate(Transport):
        def read_reviews(self, **kwargs):
            return (review_fact(), review_fact(review_id="790"))

    app, runtime, gh = publisher(tmp_path, Duplicate())
    with pytest.raises(PublicationPreflightUnavailable):
        call(app)
    assert gh.submits == 0
    assert runtime.store.get_event_by_command_id(COMMAND) is None


@pytest.mark.parametrize("confirmed", [False, True])
@pytest.mark.parametrize("fields", [
    {"publisher_user_id": 0}, {"publisher_user_id": True},
    {"publisher_login": "not/a/login"}, {"publisher_login": None},
])
def test_malformed_v2_publisher_never_becomes_a_historical_receipt(tmp_path, confirmed, fields):
    app, runtime, gh = publisher(tmp_path)
    identity = {
        "schema": "mastermind.github_review_publication_event.v2", "job_id": JOB,
        "repository": REPO, "pull_number": 42, "head_sha": HEAD,
        "event": "COMMENT", "body_sha256": hashlib.sha256(BODY.encode()).hexdigest(),
        "publisher_user_id": PUBLISHER.user_id, "publisher_login": PUBLISHER.login,
        **fields,
    }
    with runtime.store.transaction() as conn:
        runtime.store.append_event(conn, aggregate_type="github_review_publication",
            aggregate_id=COMMAND, event_type="GITHUB_REVIEW_PUBLICATION_RESERVED",
            command_id=COMMAND, actor="github-review-publisher", payload=identity)
        if confirmed:
            runtime.store.append_event(conn, aggregate_type="github_review_publication",
                aggregate_id=COMMAND, event_type="GITHUB_REVIEW_PUBLICATION_CONFIRMED",
                command_id=COMMAND + ":confirmed", actor="github-review-publisher",
                payload={**identity, "identity": identity, "original_command_id": COMMAND,
                         "review_id": "789"})
    with pytest.raises(ReviewVerificationRefused, match="RESERVATION_CONFLICT"):
        recovered(app)
    assert gh.reads == gh.submits == 0
