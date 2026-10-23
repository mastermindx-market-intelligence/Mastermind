"""A real completed Runtime review round-trips to GitHub and its Slack thread."""
from control_plane.github_review_intent_ingress import PublishState
from control_plane.github_review_result_reader import ExecutiveVerifiedReviewResults
from integrations.github_review_return import GitHubReviewReturn
from integrations.github_review_slack_thread import (
    ExecutiveSlackReviewThreads, SlackReviewResultNotifier, CHANNEL_ID,
)
from integrations.slack_agent_dialogue.engine import SlackMessage
from integrations.slack_agent_dialogue.slack_web_api import SlackWebApiDialogueClient
from test_github_review_publish_workflow import git_api
from test_github_review_result_reader import completed_pair
from test_github_review_runtime_adapter import decision


def slack_components(runtime):
    client = SlackWebApiDialogueClient(
        token="test", workspace_id="T0BRD2AQXQV",
        channel_id=CHANNEL_ID, bot_user_id="U0BT71H4FQE",
    )
    threads = ExecutiveSlackReviewThreads(runtime=runtime)
    assert threads.reserve_parent_send(decision=decision(), job_id="JOB-002")
    threads.record_parent(
        decision=decision(), job_id="JOB-002",
        message=SlackMessage(
            ts="1792699000.000001", author_user_id="U0BT71H4FQE",
            text="Executive Job admitted",
        ),
    )
    replies = []
    async def fake_reply(*, channel_id, thread_ts, text):
        replies.append((channel_id, thread_ts, text))
        return SlackMessage(
            ts="1792699001.000002", author_user_id="U0BT71H4FQE",
            text=text, thread_ts=thread_ts,
        )
    client.post_reply = fake_reply
    return SlackReviewResultNotifier(client=client, threads=threads), replies


def test_full_verified_worker_return_posts_exact_github_and_one_slack_reply(tmp_path):
    runtime, builder, review = completed_pair(tmp_path)
    assert review == "JOB-002"
    github, gh_history = git_api()
    slack, messages = slack_components(runtime)
    reader = ExecutiveVerifiedReviewResults(
        runtime=runtime, builder_job_id_for_review=lambda id: builder,
    )
    handler = GitHubReviewReturn(
        runtime=runtime, github=github, results=reader,
        publication_guard=lambda: None, slack=slack,
    )
    result = handler.deliver(decision=decision(), job_id=review)
    assert result.publication.state is PublishState.PUBLISHED
    assert result.publication.review_id == "789"
    assert result.slack_receipt == "POSTED"
    assert len(gh_history["posts"]) == len(messages) == 1
    assert messages[0][1] == "1792699000.000001"
    assert "789" in messages[0][2]
    assert "example/repo" not in messages[0][2]
    second = handler.deliver(decision=decision(), job_id=review)
    assert second.publication.state is PublishState.ALREADY_PUBLISHED
    assert len(gh_history["posts"]) == len(messages) == 1


def test_missing_builder_identity_blocks_both_effects(tmp_path):
    runtime, builder, review = completed_pair(tmp_path)
    github, gh_history = git_api()
    slack, messages = slack_components(runtime)
    handler = GitHubReviewReturn(
        runtime=runtime, github=github,
        results=ExecutiveVerifiedReviewResults(runtime=runtime),
        publication_guard=lambda: None, slack=slack,
    )
    result = handler.deliver(decision=decision(), job_id=review)
    assert result.publication.state is PublishState.REFUSED
    assert not gh_history["posts"] and not messages


def test_slack_receipt_is_not_publication_acceptance_gate(tmp_path):
    runtime, builder, review = completed_pair(tmp_path)
    github, gh_history = git_api()
    slack, messages = slack_components(runtime)
    async def broken_reply(*, channel_id, thread_ts, text):
        raise OSError("slack lost ACK")
    slack._client.post_reply = broken_reply
    handler = GitHubReviewReturn(
        runtime=runtime, github=github,
        results=ExecutiveVerifiedReviewResults(
            runtime=runtime, builder_job_id_for_review=lambda _: builder,
        ),
        publication_guard=lambda: None, slack=slack,
    )
    receipt = handler.deliver(decision=decision(), job_id=review)
    assert receipt.publication.state is PublishState.PUBLISHED
    assert receipt.slack_receipt == "EFFECT_UNKNOWN"
    assert len(gh_history["posts"]) == 1


def test_review_job_from_pr_a_cannot_publish_on_pr_b(tmp_path):
    import dataclasses
    import pytest
    from control_plane.github_review_intent_ingress import ReviewVerificationRefused
    runtime, builder, review = completed_pair(tmp_path)
    github, gh_history = git_api()
    handler = GitHubReviewReturn(
        runtime=runtime, github=github,
        results=ExecutiveVerifiedReviewResults(
            runtime=runtime, builder_job_id_for_review=lambda _: builder,
        ),
        publication_guard=lambda: None,
    )
    tampered = dataclasses.replace(decision(), repository="attacker/other")
    with pytest.raises(ReviewVerificationRefused, match="SOURCE_IDENTITY_MISMATCH"):
        handler.deliver(decision=tampered, job_id=review)
    assert gh_history["posts"] == []


def test_authorized_external_return_binds_app_submitter_and_comment_only(tmp_path):
    from integrations.github_review_return import ReviewReturnSourceMode
    runtime, builder, review = completed_pair(
        tmp_path, review_verdict="reject",
    )
    github, history = git_api()
    handler = GitHubReviewReturn.for_authorized_source(
        runtime=runtime, github=github, publication_guard=lambda: None,
        source_mode=ReviewReturnSourceMode.EXTERNAL_GITHUB_ADVISORY,
    )
    assert handler._results.load_verified_result(job_id=review).source_basis == (
        "EXTERNAL_GITHUB_SUBMITTER"
    )
    first = handler.deliver(decision=decision(), job_id=review)
    assert first.publication.state is PublishState.PUBLISHED
    assert first.publication.review_id == "789"
    assert len(history["posts"]) == 1
    assert history["posts"][0]["event"] == "COMMENT"
    assert "not attested" in history["posts"][0]["body"].lower()
    assert "GitHub PR submitter: alice (account ID 314)" in history["posts"][0]["body"]
    assert handler.deliver(
        decision=decision(), job_id=review,
    ).publication.state is PublishState.ALREADY_PUBLISHED
    assert len(history["posts"]) == 1


def test_authorized_native_return_requires_real_distinct_builder(tmp_path):
    from integrations.github_review_return import ReviewReturnSourceMode
    runtime, builder, review = completed_pair(tmp_path)
    github, history = git_api()
    handler = GitHubReviewReturn.for_authorized_source(
        runtime=runtime, github=github, publication_guard=lambda: None,
        source_mode=ReviewReturnSourceMode.EXECUTIVE_BUILDER,
        builder_job_id_for_review=lambda _: builder,
    )
    receipt = handler.deliver(decision=decision(), job_id=review)
    assert receipt.publication.state is PublishState.PUBLISHED
    assert "Builder worker: builder-01" in history["posts"][0]["body"]
    assert "GitHub PR submitter:" not in history["posts"][0]["body"]


def test_native_mode_rejects_unrelated_builder_under_host_binding(tmp_path):
    from integrations.github_review_return import ReviewReturnSourceMode
    runtime, builder, review = completed_pair(
        tmp_path, builder_repository="other/repo",
    )
    github, history = git_api()
    handler = GitHubReviewReturn.for_authorized_source(
        runtime=runtime, github=github, publication_guard=lambda: None,
        source_mode=ReviewReturnSourceMode.EXECUTIVE_BUILDER,
        builder_job_id_for_review=lambda _: builder,
    )
    receipt = handler.deliver(decision=decision(), job_id=review)
    assert receipt.publication.state is PublishState.REFUSED
    assert not history["posts"]


def test_return_binding_refuses_implicit_or_mixed_source_modes(tmp_path):
    import pytest
    from control_plane.github_review_intent_ingress import ReviewVerificationRefused
    from integrations.github_review_return import ReviewReturnSourceMode

    runtime, builder, review = completed_pair(tmp_path)
    github, history = git_api()
    common = dict(
        runtime=runtime, github=github,
        publication_guard=lambda: None,
    )
    for mode, builder_ref, expected_refusal in (
        ("EXTERNAL_GITHUB_ADVISORY", None, "SOURCE_MODE_INVALID"),
        (None, None, "SOURCE_MODE_INVALID"),
        (ReviewReturnSourceMode.EXECUTIVE_BUILDER, None,
         "BUILDER_SOURCE_UNBOUND"),
        (ReviewReturnSourceMode.EXTERNAL_GITHUB_ADVISORY, lambda _: builder,
         "SOURCE_MODES_MIXED"),
    ):
        with pytest.raises(ReviewVerificationRefused, match=expected_refusal):
            GitHubReviewReturn.for_authorized_source(
                **common, source_mode=mode,
                builder_job_id_for_review=builder_ref,
            )
    with pytest.raises(ReviewVerificationRefused, match="UNARMED"):
        GitHubReviewReturn.for_authorized_source(
            runtime=runtime, github=github, publication_guard=None,
            source_mode=ReviewReturnSourceMode.EXTERNAL_GITHUB_ADVISORY,
        )
    assert history["posts"] == []


def test_external_return_refuses_stale_github_head_before_post(tmp_path):
    from integrations.github_review_return import ReviewReturnSourceMode

    runtime, builder, review = completed_pair(tmp_path)
    github, history = git_api(moved_head=True)
    handler = GitHubReviewReturn.for_authorized_source(
        runtime=runtime, github=github, publication_guard=lambda: None,
        source_mode=ReviewReturnSourceMode.EXTERNAL_GITHUB_ADVISORY,
    )
    receipt = handler.deliver(decision=decision(), job_id=review)
    assert receipt.publication.state is PublishState.REFUSED
    assert history["posts"] == []


def test_return_factory_rejects_publisher_spoofing_api_subclass(tmp_path):
    import httpx
    import pytest
    from control_plane.github_review_intent_ingress import ReviewVerificationRefused
    from integrations.github_review_api import GitHubReviewAPI
    from integrations.github_review_return import ReviewReturnSourceMode
    from test_github_review_publish_workflow import Tokens

    class ForgedPublisher(GitHubReviewAPI):
        @property
        def publisher_login(self):
            return "alice"  # PR submitter, not the real App bot

    runtime, builder, reviewer = completed_pair(tmp_path)
    forged = ForgedPublisher(
        repository="example/repo", installation_id=4242,
        publisher_login="reviewer-bot[bot]", token_source=Tokens(),
        client=httpx.Client(transport=httpx.MockTransport(
            lambda req: httpx.Response(200, json={})
        )),
    )
    assert forged.publisher_login == "alice"
    with pytest.raises(ReviewVerificationRefused, match="OWNER_UNBOUND"):
        GitHubReviewReturn.for_authorized_source(
            runtime=runtime, github=forged, publication_guard=lambda: None,
            source_mode=ReviewReturnSourceMode.EXTERNAL_GITHUB_ADVISORY,
        )


def test_return_factory_rejects_malformed_host_owner(tmp_path):
    import pytest
    from control_plane.github_review_intent_ingress import ReviewVerificationRefused
    from integrations.github_review_return import ReviewReturnSourceMode
    runtime, builder, reviewer = completed_pair(tmp_path)
    github, history = git_api()
    for bound_runtime, bound_github in ((None, github), (runtime, None)):
        with pytest.raises(ReviewVerificationRefused, match="OWNER_UNBOUND"):
            GitHubReviewReturn.for_authorized_source(
                runtime=bound_runtime, github=bound_github,
                publication_guard=lambda: None,
                source_mode=ReviewReturnSourceMode.EXTERNAL_GITHUB_ADVISORY,
            )
    assert history["posts"] == []


def test_return_factory_refuses_publisher_self_review_without_post(tmp_path):
    import httpx
    from integrations.github_review_return import ReviewReturnSourceMode
    from test_github_review_api import pr, source

    runtime, builder, review = completed_pair(tmp_path)
    attempted = []
    def github_wire(request):
        attempted.append((request.method, request.url.path))
        assert request.method == "GET"
        current = pr()
        current["user"] = {"login": "reviewer-bot[bot]", "id": 999}
        return httpx.Response(200, json=current)

    github, source_tokens = source(github_wire)
    handler = GitHubReviewReturn.for_authorized_source(
        runtime=runtime, github=github, publication_guard=lambda: None,
        source_mode=ReviewReturnSourceMode.EXTERNAL_GITHUB_ADVISORY,
    )
    outcome = handler.deliver(decision=decision(), job_id=review)
    assert outcome.publication.state is PublishState.REFUSED
    assert attempted == [("GET", "/repos/example/repo/pulls/42")]
    assert source_tokens.calls == 1


def test_return_factory_refuses_submitter_drift_before_post(tmp_path):
    from integrations.github_review_return import ReviewReturnSourceMode

    runtime, builder, review = completed_pair(tmp_path)
    github, history = git_api(changed_submitter=True)
    handler = GitHubReviewReturn.for_authorized_source(
        runtime=runtime, github=github, publication_guard=lambda: None,
        source_mode=ReviewReturnSourceMode.EXTERNAL_GITHUB_ADVISORY,
    )
    outcome = handler.deliver(decision=decision(), job_id=review)
    assert outcome.publication.state is PublishState.REFUSED
    assert outcome.publication.refusal == "EXTERNAL_SOURCE_DRIFT"
    assert history["posts"] == []
