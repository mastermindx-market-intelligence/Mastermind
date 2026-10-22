"""Actual Runtime terminal receipts -> exact SHA -> GitHub review POST & readback."""
import httpx

from control_plane.github_review_intent_ingress import (
    PublishState, publish_verified_review,
)
from control_plane.github_review_publication_record import ExecutiveReviewPublicationRecord
from control_plane.github_review_result_reader import ExecutiveVerifiedReviewResults
from integrations.github_review_api import GitHubReviewAPI
from test_github_review_result_reader import completed_pair
from test_github_review_runtime_adapter import decision

REPO = "example/repo"
HEAD = "a" * 40


class Tokens:
    def token_for_installation(self, *, installation_id):
        assert installation_id == 4242
        return "bounded-test-token"


def git_api(*, moved_head=False, unknown_post=False):
    state = {"posts": [], "reviews": []}

    def handler(req):
        assert req.url.host == "api.github.com"
        assert req.headers["authorization"] == "Bearer bounded-test-token"
        if req.url.path.endswith("/pulls/42"):
            return httpx.Response(200, json={
                "number": 42, "state": "open", "draft": False,
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
                "user": {"login": "reviewer-bot[bot]"},
            })
            if unknown_post:
                raise httpx.ReadTimeout("lost response after landed", request=req)
            return httpx.Response(200, json={"id": 789})
        raise AssertionError(f"unrecognized GitHub API path: {req.url}")

    api = GitHubReviewAPI(
        repository=REPO, installation_id=4242, token_source=Tokens(),
        publisher_login="reviewer-bot[bot]",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    return api, state


def test_completed_distinct_worker_review_publishes_one_comment_and_readback(tmp_path):
    runtime, builder, reviewer_job = completed_pair(tmp_path)
    reader = ExecutiveVerifiedReviewResults(
        runtime=runtime, builder_job_id_for_review=lambda job_id: builder
    )
    api, history = git_api()
    pub = ExecutiveReviewPublicationRecord(
        runtime=runtime, transport=api, job_id=reviewer_job,
        publication_guard=lambda: None,
    )
    args = dict(
        decision=decision(), job_id=reviewer_job, results=reader,
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
    publisher = ExecutiveReviewPublicationRecord(
        runtime=runtime, transport=api, job_id=reviewer_job,
        publication_guard=lambda: None,
    )
    outcome = publish_verified_review(
        decision=decision(), job_id=reviewer_job, results=reader,
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
    publisher = ExecutiveReviewPublicationRecord(
        runtime=runtime, transport=api, job_id=reviewer_job,
        publication_guard=lambda: None,
    )
    args = dict(
        decision=decision(), job_id=reviewer_job, results=reader,
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
        publications=publications, pull_requests=api, readback=readback,
    )
    assert result.state is PublishState.REFUSED
    assert result.refusal == "PUBLICATION_EFFECT_UNKNOWN"
    assert publications.calls == readback.calls == 1
    assert history["posts"] == []
