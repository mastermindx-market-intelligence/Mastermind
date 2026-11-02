"""Actual Runtime terminal receipts -> exact SHA -> GitHub review POST & readback."""
import httpx

from control_plane.github_review_intent_ingress import (
    PublishState, publish_verified_review,
)
from control_plane.github_review_publication_record import ExecutiveReviewPublicationRecord
from control_plane.github_review_result_reader import ExecutiveVerifiedReviewResults
from control_plane.github_review_runtime_adapter import ExecutiveReviewJobAdmission
from integrations.github_review_api import GitHubReviewAPI
from test_github_review_result_reader import completed_pair
from test_github_review_runtime_adapter import decision

REPO = "example/repo"
HEAD = "a" * 40
PUBLISHER_USER_ID = 9001


class Tokens:
    def token_for_installation(self, *, installation_id):
        assert installation_id == 4242
        return "bounded-test-token"


def git_api(*, moved_head=False, unknown_post=False, changed_submitter=False, draft=False):
    state = {"posts": [], "reviews": [], "source_reads": 0}

    def handler(req):
        assert req.url.host == "api.github.com"
        assert req.headers["authorization"] == "Bearer bounded-test-token"
        if req.url.path.endswith("/pulls/42"):
            state["source_reads"] += 1
            current_submitter_id = (
                315 if changed_submitter and state["source_reads"] >= 2
                else 314
            )
            return httpx.Response(200, json={
                "number": 42, "state": "open", "draft": draft,
                "user": {"login": "alice", "id": current_submitter_id},
                "head": {"sha": ("b" if moved_head else "a") * 40,
                         "repo": {"full_name": REPO}},
                "base": {"sha": "c" * 40, "repo": {"full_name": REPO}},
                "title": "Reviewed source", "body": "Separate worker review.",
            })
        if req.method == "GET" and req.url.path.endswith("/pulls/42/reviews"):
            return httpx.Response(200, json=state["reviews"])
        if req.method == "POST" and req.url.path.endswith("/pulls/42/reviews"):
            body = __import__("json").loads(req.content)
            assert body["commit_id"] == HEAD
            assert body["event"] == "COMMENT"
            state["posts"].append(body)
            state["reviews"].append({
                "id": 789, "commit_id": HEAD, "state": "COMMENTED",
                "body": body["body"],
                "user": {"login": "reviewer-bot[bot]", "id": PUBLISHER_USER_ID},
            })
            if unknown_post:
                raise httpx.ReadTimeout("lost response after landed", request=req)
            return httpx.Response(200, json={"id": 789})
        raise AssertionError(f"unrecognized GitHub API path: {req.url}")

    api = GitHubReviewAPI(
        repository=REPO, installation_id=4242, token_source=Tokens(),
        publisher_login="reviewer-bot[bot]", publisher_user_id=PUBLISHER_USER_ID,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    return api, state


def publication_record(runtime, api, job_id):
    return ExecutiveReviewPublicationRecord(
        runtime=runtime, transport=api, job_id=job_id,
        publication_guard=lambda: None,
        expected_publisher=api.expected_publisher(),
        decision=decision(), pull_requests=api,
    )


def admitted_jobs(runtime):
    return ExecutiveReviewJobAdmission(runtime=runtime)


def test_completed_distinct_worker_review_publishes_one_comment_and_readback(tmp_path):
    runtime, builder, reviewer_job = completed_pair(tmp_path)
    reader = ExecutiveVerifiedReviewResults(
        runtime=runtime, builder_job_id_for_review=lambda job_id: builder
    )
    api, history = git_api()
    pub = publication_record(runtime, api, reviewer_job)
    args = dict(
        decision=decision(), job_id=reviewer_job, results=reader,
        admissions=admitted_jobs(runtime),
        publications=pub, pull_requests=api, readback=api,
    )
    first = publish_verified_review(**args)
    assert first.state is PublishState.PUBLISHED
    assert first.review_id == "789"
    assert len(history["posts"]) == 1
    assert "Verdict: PASS" in history["posts"][0]["body"]
    assert "Builder worker: builder-01" in history["posts"][0]["body"]
    assert "Reviewer worker: reviewer-01" in history["posts"][0]["body"]
    second = publish_verified_review(**args)
    assert second.state is PublishState.ALREADY_PUBLISHED
    assert len(history["posts"]) == 1


def test_moved_head_refuses_before_github_review_post(tmp_path):
    runtime, builder, reviewer_job = completed_pair(tmp_path)
    reader = ExecutiveVerifiedReviewResults(
        runtime=runtime, builder_job_id_for_review=lambda job_id: builder
    )
    api, history = git_api(moved_head=True)
    publisher = publication_record(runtime, api, reviewer_job)
    outcome = publish_verified_review(
        decision=decision(), job_id=reviewer_job, results=reader,
        admissions=admitted_jobs(runtime),
        publications=publisher, pull_requests=api, readback=api,
    )
    assert outcome.state is PublishState.REFUSED
    assert history["posts"] == []


def test_lost_post_reconciles_exact_github_review_without_duplicate(tmp_path):
    runtime, builder, reviewer_job = completed_pair(tmp_path)
    reader = ExecutiveVerifiedReviewResults(
        runtime=runtime, builder_job_id_for_review=lambda job_id: builder
    )
    api, history = git_api(unknown_post=True)
    publisher = publication_record(runtime, api, reviewer_job)
    args = dict(
        decision=decision(), job_id=reviewer_job, results=reader,
        admissions=admitted_jobs(runtime),
        publications=publisher, pull_requests=api, readback=api,
    )
    assert publish_verified_review(**args).state is PublishState.PUBLISHED
    assert len(history["posts"]) == 1
    assert publish_verified_review(**args).state is PublishState.ALREADY_PUBLISHED
    assert len(history["posts"]) == 1


def test_top_level_unavailable_unknown_post_readback_reports_effect_unknown(tmp_path):
    """A second GitHub GET outage must not misstate an uncertain POST as absent."""
    from control_plane.github_review_intent_ingress import PublicationEffectUnknown

    runtime, builder, reviewer_job = completed_pair(tmp_path)
    reader = ExecutiveVerifiedReviewResults(
        runtime=runtime, builder_job_id_for_review=lambda job_id: builder
    )
    api, history = git_api()
    class UnknownPublication:
        def __init__(self):
            self.calls = 0

        def publishing_principal(self):
            return api.expected_publisher()

        def published_command_ids(self):
            return frozenset()

        def publish_review(self, **kwargs):
            self.calls += 1
            raise PublicationEffectUnknown("GITHUB_REVIEW_EFFECT_UNKNOWN")

    class UnavailableReadback:
        def __init__(self):
            self.calls = 0

        def read_reviews(self, *, repository, pull_number, commit_id):
            self.calls += 1
            assert (repository, pull_number, commit_id) == (REPO, 42, HEAD)
            raise OSError("lost authenticated GitHub GET")

    publications = UnknownPublication()
    readback = UnavailableReadback()
    result = publish_verified_review(
        decision=decision(), job_id=reviewer_job, results=reader,
        admissions=admitted_jobs(runtime),
        publications=publications, pull_requests=api, readback=readback,
    )
    assert result.state is PublishState.REFUSED
    assert result.refusal == "PUBLICATION_EFFECT_UNKNOWN"
    assert publications.calls == readback.calls == 1
    assert history["posts"] == []


def test_external_github_pr_without_builder_job_publishes_labeled_advisory_comment(tmp_path):
    """External authenticated submitter is NOT misrepresented as a Fabric builder."""
    from integrations.github_review_return import GitHubReviewReturn
    runtime, builder, review_job = completed_pair(tmp_path)
    github, history = git_api()
    results = ExecutiveVerifiedReviewResults(
        runtime=runtime, external_source=github,
        publisher_login="reviewer-bot[bot]",
    )
    observed = results.load_verified_result(job_id=review_job)
    assert observed is not None
    assert observed.builder_worker_id == ""
    assert observed.source_basis == "EXTERNAL_GITHUB_SUBMITTER"
    assert observed.source_github_submitter_id == 314
    handler = GitHubReviewReturn(
        runtime=runtime, github=github, results=results,
        publication_guard=lambda: None,
    )
    first = handler.deliver(decision=decision(), job_id=review_job)
    assert first.publication.state is PublishState.PUBLISHED
    assert first.publication.review_id == "789"
    assert len(history["posts"]) == 1
    assert history["posts"][0]["event"] == "COMMENT"
    body = history["posts"][0]["body"]
    assert "Automated advisory review" in body
    assert "NOT attested" in body
    assert "GitHub PR submitter: alice (account ID 314)" in body
    assert "Builder worker:" not in body
    assert handler.deliver(
        decision=decision(), job_id=review_job
    ).publication.state is PublishState.ALREADY_PUBLISHED
    assert len(history["posts"]) == 1


def test_external_request_changes_verdict_cannot_request_changes_github_verb(tmp_path):
    from integrations.github_review_return import GitHubReviewReturn
    runtime, builder, review_job = completed_pair(tmp_path, review_verdict="reject")
    github, history = git_api()
    results = ExecutiveVerifiedReviewResults(
        runtime=runtime, external_source=github,
        publisher_login="reviewer-bot[bot]",
    )
    handler = GitHubReviewReturn(
        runtime=runtime, github=github, results=results,
        publication_guard=lambda: None,
    )
    receipt = handler.deliver(decision=decision(), job_id=review_job)
    assert receipt.publication.state is PublishState.PUBLISHED
    assert len(history["posts"]) == 1
    assert history["posts"][0]["event"] == "COMMENT"
    assert "Verdict: REQUEST_CHANGES (advisory)" in history["posts"][0]["body"]


def test_external_submitter_identity_changes_before_publication_refuses(tmp_path):
    runtime, builder, review_job = completed_pair(tmp_path)
    github, history = git_api(changed_submitter=True)
    results = ExecutiveVerifiedReviewResults(
        runtime=runtime, external_source=github,
        publisher_login="reviewer-bot[bot]",
    )
    pub = publication_record(runtime, github, review_job)
    receipt = publish_verified_review(
        decision=decision(), job_id=review_job, results=results,
        admissions=admitted_jobs(runtime),
        publications=pub, pull_requests=github, readback=github,
    )
    assert receipt.state is PublishState.REFUSED
    assert receipt.refusal == "EXTERNAL_SOURCE_DRIFT"
    assert history["posts"] == []


def test_external_mode_and_native_builder_mode_are_mutually_exclusive(tmp_path):
    import pytest
    runtime, builder, review_job = completed_pair(tmp_path)
    github, history = git_api()
    with pytest.raises(TypeError):
        ExecutiveVerifiedReviewResults(
            runtime=runtime, external_source=github,
            builder_job_id_for_review=lambda _: builder,
            publisher_login="reviewer-bot[bot]",
        )
    with pytest.raises(TypeError):
        ExecutiveVerifiedReviewResults(
            runtime=runtime, publisher_login="reviewer-bot[bot]",
        )


def test_external_origin_without_publication_source_port_refuses_before_post(tmp_path):
    runtime, builder, review_job = completed_pair(tmp_path)
    github, history = git_api()
    results = ExecutiveVerifiedReviewResults(
        runtime=runtime, external_source=github,
        publisher_login="reviewer-bot[bot]",
    )
    class PRHeadOnly:
        def read_pull_request(self, *, repository, pull_number):
            return github.read_pull_request(
                repository=repository, pull_number=pull_number
            )
    pub = publication_record(runtime, github, review_job)
    receipt = publish_verified_review(
        decision=decision(), job_id=review_job, results=results,
        admissions=admitted_jobs(runtime),
        publications=pub, pull_requests=PRHeadOnly(), readback=github,
    )
    assert receipt.state is PublishState.REFUSED
    assert receipt.refusal == "EXTERNAL_SOURCE_PORT_UNBOUND"
    assert history["posts"] == []


def test_external_moved_head_is_not_given_a_builder_identity(tmp_path):
    runtime, builder, review_job = completed_pair(tmp_path)
    github, history = git_api(moved_head=True)
    results = ExecutiveVerifiedReviewResults(
        runtime=runtime, external_source=github,
        publisher_login="reviewer-bot[bot]",
    )
    assert results.load_verified_result(job_id=review_job) is None
    pub = publication_record(runtime, github, review_job)
    receipt = publish_verified_review(
        decision=decision(), job_id=review_job, results=results,
        admissions=admitted_jobs(runtime),
        publications=pub, pull_requests=github, readback=github,
    )
    assert receipt.state is PublishState.REFUSED
    assert receipt.refusal == "RESULT_NOT_VERIFIED"
    assert history["posts"] == []


def test_draft_external_pr_can_receive_advisory_comment_without_readiness_or_approval(tmp_path):
    from integrations.github_review_return import GitHubReviewReturn, ReviewReturnSourceMode
    runtime, builder, review_job = completed_pair(tmp_path, review_verdict="reject")
    github, history = git_api(draft=True)
    owner = GitHubReviewReturn.for_authorized_source(
        runtime=runtime, github=github, publication_guard=lambda: None,
        source_mode=ReviewReturnSourceMode.EXTERNAL_GITHUB_ADVISORY,
    )
    result = owner.deliver(decision=decision(), job_id=review_job)
    assert result.publication.state is PublishState.PUBLISHED
    assert result.publication.review_id == "789"
    assert len(history["posts"]) == 1
    assert history["posts"][0]["commit_id"] == HEAD
    assert history["posts"][0]["event"] == "COMMENT"
    assert "REQUEST_CHANGES (advisory)" in history["posts"][0]["body"]
    assert "NOT attested" in history["posts"][0]["body"]
    assert owner.deliver(
        decision=decision(), job_id=review_job
    ).publication.state is PublishState.ALREADY_PUBLISHED
    assert len(history["posts"]) == 1
