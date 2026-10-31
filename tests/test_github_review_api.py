"""Narrow GitHub App REST adapter contract tests using exact HTTP wire mock."""
import httpx
import pytest

from control_plane.github_review_intent import (
    IntentSource, ReviewIntentDecision, review_command_id, review_intent_id,
)
from control_plane.github_review_intent_ingress import (
    ExpectedReviewPublisher,
    FinalPullRequestCheck,
    PublicationEffectUnknown,
    ReconcilingReviewPublication,
    ReviewVerificationRefused,
)
from integrations.github_review_api import (
    GitHubReviewAPI,
    GitHubReviewAPIUnavailable,
)

REPO = "example/repo"
SHA = "a" * 40
PUBLISHER_USER_ID = 9001
PUBLISHER = ExpectedReviewPublisher(
    user_id=PUBLISHER_USER_ID, login="reviewer-bot[bot]"
)


class Tokens:
    def __init__(self):
        self.calls = 0
    def token_for_installation(self, *, installation_id):
        assert installation_id == 4242
        self.calls += 1
        return "private-test-token"


def source(handler):
    token = Tokens()
    client = httpx.Client(transport=httpx.MockTransport(handler))
    api = GitHubReviewAPI(
        repository=REPO, installation_id=4242,
        publisher_login="reviewer-bot[bot]", publisher_user_id=PUBLISHER_USER_ID,
        token_source=token,
        client=client,
    )
    return api, token


def pr():
    return {
        "number": 42, "state": "open", "draft": False,
        "head": {"sha": SHA, "repo": {"full_name": REPO}},
        "base": {"sha": "b" * 40, "repo": {"full_name": REPO}},
        "title": "Review it", "body": "No secrets",
    }


def _decision():
    intent_id = review_intent_id(repository=REPO, pull_number=42, head_sha=SHA)
    return ReviewIntentDecision(
        admitted=True, refusal=None, intent_source=IntentSource.INTENT_LABEL,
        intent_id=intent_id, command_id=review_command_id(intent_id),
        delivery_command_id="gh-review-delivery:" + "a" * 32,
        repository=REPO, pull_number=42, frozen_head_sha=SHA, actor="alice",
    )


class Ledger:
    """Test stand-in. Production reservation is the Executive EventStore."""

    def __init__(self):
        self.claims = {}
        self.done = set()

    def published_command_ids(self):
        return frozenset(self.done)

    def reserve_publication(
        self, *, publication_command_id, repository, pull_number,
        head_sha, event, body,
    ):
        identity = (repository, pull_number, head_sha, event, body)
        prior = self.claims.get(publication_command_id)
        if prior is None:
            self.claims[publication_command_id] = identity
            return True
        if prior != identity:
            raise ReviewVerificationRefused("publication claim identity mismatch")
        return False

    def confirm_publication(
        self, *, publication_command_id, repository, pull_number,
        head_sha, event, body, review_id,
    ):
        identity = (repository, pull_number, head_sha, event, body)
        if self.claims.get(publication_command_id) != identity:
            raise ReviewVerificationRefused("publication confirmation mismatch")
        self.done.add(publication_command_id)


def armed(api, published=None):
    return ReconcilingReviewPublication(
        transport=api,
        published=published if published is not None else Ledger(),
        expected_publisher=PUBLISHER,
        before_post=FinalPullRequestCheck(
            decision=_decision(), pull_requests=api,
        ),
    )


def handler(request):
    assert request.url.host == "api.github.com"
    assert request.headers["authorization"] == "Bearer private-test-token"
    assert not request.extensions.get("follow_redirects", False)
    if request.method == "GET" and request.url.path.endswith("/pulls/42"):
        return httpx.Response(200, json=pr())
    if request.method == "GET" and request.url.path.endswith("/collaborators/alice/permission"):
        return httpx.Response(200, json={"user": {"login": "alice"}, "permission": "write"})
    return httpx.Response(404, json={"message": "not found"})


def test_authentic_pull_and_collaborator_read_share_one_installation_scope():
    api, token = source(handler)
    result = api.read_pull_request(repository=REPO, pull_number=42)
    assert result.number == 42 and result.head_sha == SHA
    assert api.read_current_permission(repository=REPO, login="alice") == "write"
    assert token.calls == 2


def test_cross_repository_read_refused_before_token():
    api, token = source(handler)
    with pytest.raises(GitHubReviewAPIUnavailable, match="SCOPE"):
        api.read_pull_request(repository="other/repo", pull_number=42)
    assert token.calls == 0


def test_mismatched_pull_is_not_accepted():
    def wrong(req):
        obj = pr()
        obj["number"] = 43
        return httpx.Response(200, json=obj)
    api, _ = source(wrong)
    with pytest.raises(GitHubReviewAPIUnavailable, match="IDENTITY_MISMATCH"):
        api.read_pull_request(repository=REPO, pull_number=42)


def test_revoked_actor_permission_is_not_fabricated_from_payload():
    api, _ = source(lambda req: httpx.Response(404, json={"message": "not found"}))
    assert api.read_current_permission(repository=REPO, login="alice") is None


def test_submit_posts_exact_commit_and_never_approves():
    seen = []
    def submit(req):
        seen.append(req)
        return httpx.Response(200, json={"id": 19})
    api, _ = source(submit)
    result = api.submit_review(repository=REPO, pull_number=42, commit_id=SHA,
                               event="COMMENT", body="Advisory review")
    assert result == "19"
    assert seen[0].url.path == "/repos/example/repo/pulls/42/reviews"
    assert seen[0].method == "POST"
    assert seen[0].read().decode().find('"commit_id":"' + SHA + '"') >= 0
    with pytest.raises(GitHubReviewAPIUnavailable, match="EVENT_REFUSED"):
        api.submit_review(repository=REPO, pull_number=42, commit_id=SHA,
                          event="APPROVE", body="Danger")
    assert len(seen) == 1


def test_uncertain_post_must_reconcile_from_own_review_readback():
    attempts = []
    reads = []
    def transport(req):
        if req.method == "POST":
            attempts.append(req)
            raise httpx.ReadTimeout("response lost", request=req)
        if req.url.path.endswith("/pulls/42/reviews"):
            reads.append(req)
            if not attempts:
                return httpx.Response(200, json=[])
            return httpx.Response(200, json=[
                {"id": 123, "commit_id": SHA, "state": "COMMENTED", "body": "review body",
                 "user": {"login": "reviewer-bot[bot]", "id": PUBLISHER_USER_ID}},
                {"id": 124, "commit_id": SHA, "state": "COMMENTED", "body": "review body",
                 "user": {"login": "not-our-bot", "id": 8}},
            ])
        if req.url.path.endswith("/pulls/42"):
            return httpx.Response(200, json=pr())
        return httpx.Response(404, json={"message": "not found"})
    api, _ = source(transport)
    published = armed(api)
    review_id = published.publish_review(
        publication_command_id="gh-review-publish:" + "a" * 32,
        repository=REPO, pull_number=42, head_sha=SHA,
        event="COMMENT", body="review body",
    )
    assert review_id == "123"
    assert len(attempts) == 1


def test_uncertain_post_without_exact_readback_remains_uncertain():
    attempts = []
    def transport(req):
        if req.method == "POST":
            attempts.append(req)
            raise httpx.ReadTimeout("response lost", request=req)
        if req.url.path.endswith("/pulls/42/reviews"):
            return httpx.Response(200, json=[])
        if req.url.path.endswith("/pulls/42"):
            return httpx.Response(200, json=pr())
        return httpx.Response(404, json={"message": "not found"})
    api, _ = source(transport)
    published = armed(api)
    with pytest.raises(PublicationEffectUnknown):
        published.publish_review(
            publication_command_id="gh-review-publish:" + "a" * 32,
            repository=REPO, pull_number=42, head_sha=SHA,
            event="COMMENT", body="review body",
        )
    assert len(attempts) == 1


def test_redirect_never_sends_token_to_third_party():
    def redirect(req):
        return httpx.Response(302, headers={"location": "https://evil.example/hijack"})
    api, _ = source(redirect)
    with pytest.raises(GitHubReviewAPIUnavailable, match="READ_REFUSED"):
        api.read_pull_request(repository=REPO, pull_number=42)


def test_missing_local_receipt_does_not_duplicate_a_review_already_on_github():
    posts = []
    def transport(req):
        if req.method == "POST":
            posts.append(req)
            raise AssertionError("preexisting review must not be reposted")
        if req.url.path.endswith("/pulls/42/reviews"):
            return httpx.Response(200, json=[
                {"id": 867, "commit_id": SHA, "state": "COMMENTED", "body": "same review",
                 "user": {"login": "reviewer-bot[bot]", "id": PUBLISHER_USER_ID}},
            ])
        if req.url.path.endswith("/pulls/42"):
            return httpx.Response(200, json=pr())
        return httpx.Response(404, json={"message": "not found"})
    api, _ = source(transport)
    published = armed(api)
    assert published.publish_review(
        publication_command_id="gh-review-publish:" + "a" * 32,
        repository=REPO, pull_number=42, head_sha=SHA,
        event="COMMENT", body="same review",
    ) == "867"
    assert posts == []

def test_current_permission_uses_exact_standard_maintain_role_not_legacy_write():
    def collaborator(req):
        return httpx.Response(200, json={
            "user": {"login": "alice"},
            "permission": "write", "role_name": "maintain",
        })
    api, _ = source(collaborator)
    assert api.read_current_permission(repository=REPO, login="alice") == "maintain"


def test_oversized_successful_post_is_effect_unknown_not_no_effect():
    def oversized(req):
        return httpx.Response(201, content=b"z" * ((1 << 20) + 1))
    api, _ = source(oversized)
    with pytest.raises(PublicationEffectUnknown):
        api.submit_review(
            repository=REPO, pull_number=42, commit_id=SHA,
            event="COMMENT", body="Published but receipt too large",
        )


def test_missing_review_id_on_success_is_effect_unknown_not_definite_refusal():
    api, _ = source(lambda req: httpx.Response(200, json={"state": "COMMENTED"}))
    with pytest.raises(PublicationEffectUnknown):
        api.submit_review(
            repository=REPO, pull_number=42, commit_id=SHA,
            event="COMMENT", body="Published but no id",
        )

def test_preflight_read_unavailable_is_typed_effect_unknown_without_post():
    posts = []
    def outage(req):
        if req.method == "POST":
            posts.append(req)
            return httpx.Response(200, json={"id": 222})
        return httpx.Response(503, json={"message": "temporarily unavailable"})
    api, _ = source(outage)
    publisher = armed(api)
    with pytest.raises(PublicationEffectUnknown):
        publisher.publish_review(
            publication_command_id="gh-review-publish:" + "a" * 32,
            repository=REPO, pull_number=42, head_sha=SHA,
            event="COMMENT", body="outage preflight",
        )
    assert posts == []


def test_external_source_is_verified_app_pr_submitter_not_webhook_claim():
    def authenticated(req):
        obj = pr()
        obj["user"] = {"login": "alice", "id": 314}
        return httpx.Response(200, json=obj)
    api, tokens = source(authenticated)
    origin = api.read_external_source(repository=REPO, pull_number=42)
    assert origin.repository == REPO
    assert origin.pull_number == 42 and origin.head_sha == SHA
    assert origin.submitter_login == "alice" and origin.submitter_id == 314
    assert tokens.calls == 1


@pytest.mark.parametrize("mutator", [
    lambda obj: obj.pop("user", None),
    lambda obj: obj["user"].update({"id": 0}),
    lambda obj: obj["user"].update({"login": "reviewer-bot[bot]"}),
    lambda obj: obj.update({"draft": "true"}),
    lambda obj: obj["head"]["repo"].update({"full_name": "fork/other"}),
    lambda obj: obj["head"].update({"sha": "not-a-valid-sha"}),
])
def test_external_source_refuses_unverified_invalid_or_self_origin(mutator):
    def authenticated(req):
        obj = pr()
        obj["user"] = {"login": "alice", "id": 314}
        mutator(obj)
        return httpx.Response(200, json=obj)
    api, _ = source(authenticated)
    with pytest.raises(GitHubReviewAPIUnavailable):
        api.read_external_source(repository=REPO, pull_number=42)


def test_authenticated_draft_pr_submitter_is_valid_for_comment_only_advisory():
    def authenticated(req):
        obj = pr()
        obj["draft"] = True
        obj["user"] = {"login": "alice", "id": 314}
        return httpx.Response(200, json=obj)
    api, tokens = source(authenticated)
    origin = api.read_external_source(repository=REPO, pull_number=42)
    assert origin.repository == REPO
    assert origin.pull_number == 42 and origin.head_sha == SHA
    assert origin.submitter_login == "alice" and origin.submitter_id == 314
    assert tokens.calls == 1


@pytest.mark.parametrize("user", [
    {"login": "not-our-bot", "id": 8},
    {"login": "reviewer-bot[bot]", "id": 8},
    {"login": "not-our-bot", "id": PUBLISHER_USER_ID},
    {"login": "reviewer-bot[bot]"},
])
def test_readback_does_not_fill_or_accept_a_foreign_author(user):
    posts = []

    def transport(req):
        if req.method == "POST":
            posts.append(req)
            return httpx.Response(200, json={"id": 555})
        if req.url.path.endswith("/pulls/42/reviews"):
            return httpx.Response(200, json=[{
                "id": 124, "commit_id": SHA, "state": "COMMENTED",
                "body": "review body", "user": user,
            }])
        if req.url.path.endswith("/pulls/42"):
            return httpx.Response(200, json=pr())
        return httpx.Response(404, json={"message": "not found"})

    api, _ = source(transport)
    assert armed(api).publish_review(
        publication_command_id="gh-review-publish:" + "b" * 32,
        repository=REPO, pull_number=42, head_sha=SHA,
        event="COMMENT", body="review body",
    ) == "555"
    assert len(posts) == 1
    reviews = api.read_reviews(repository=REPO, pull_number=42, commit_id=SHA)
    if "id" not in user:
        assert reviews == ()
    else:
        assert reviews[0].author_user_id == user["id"]
        assert reviews[0].author_login == user["login"]
        assert reviews[0].review_id == "124"
