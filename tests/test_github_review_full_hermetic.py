"""One complete hermetic signed HTTP → GitHub reads → Executive ledger → Slack wire."""
import asyncio
import json

import httpx

from control_plane.executive_runtime import Runtime
from control_plane.github_review_intent import sign_webhook_body
from control_plane.github_review_host_config import ReviewHostSettings
from control_plane.github_review_runtime_adapter import ExecutiveReviewJobAdmission
from integrations.github_review_api import GitHubReviewAPI
from integrations.github_review_ingress_asgi import GitHubReviewReceiver
from integrations.github_review_slack_visibility import SlackReviewVisibility
from integrations.github_review_slack_thread import ExecutiveSlackReviewThreads
from integrations.slack_agent_dialogue.engine import SlackMessage
from integrations.github_review_slack_visibility import REVIEW_CHANNEL_ID
from integrations.slack_agent_dialogue.slack_web_api import SlackWebApiDialogueClient

REPO = "example/repo"
DELIVERY = "11111111-2222-3333-4444-555555555555"
SHA = "a" * 40
SECRET = "bounded-test-secret"


class HostCredentials:
    def webhook_secret(self, *, installation_id):
        assert installation_id == 4242
        return SECRET
    def token_for_installation(self, *, installation_id):
        assert installation_id == 4242
        return "only-test-token"


def test_real_wiring_is_one_queued_job_and_one_sanitized_slack_notice(tmp_path):
    github_requests = []
    def handler(request):
        github_requests.append((request.method, request.url.path))
        assert request.url.host == "api.github.com"
        assert request.headers["authorization"] == "Bearer only-test-token"
        if "/collaborators/" in request.url.path:
            return httpx.Response(200, json={
                "user": {"login": "alice"}, "permission": "write"
            })
        if request.url.path.endswith("/pulls/42"):
            return httpx.Response(200, json={
                "number": 42, "state": "open", "draft": False,
                "head": {"sha": SHA, "repo": {"full_name": REPO}},
                "base": {"sha": "b" * 40, "repo": {"full_name": REPO}},
                "title": "Review test", "body": "Never run code from PR text.",
            })
        raise AssertionError(f"unexpected GitHub request: {request.url}")

    runtime = Runtime.at(tmp_path)
    # Hermetic opt-in is intentionally not a production-admission grant.
    fabric = ExecutiveReviewJobAdmission(
        runtime=runtime, admission_guard=lambda: None
    )
    github = GitHubReviewAPI(
        repository=REPO, installation_id=4242,
        token_source=HostCredentials(), publisher_login="reviewer-bot[bot]",
        publisher_user_id=9001,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    slack = SlackWebApiDialogueClient(
        token="dummy", workspace_id="T0BRD2AQXQV",
        channel_id=REVIEW_CHANNEL_ID, bot_user_id="U0BT71H4FQE",
    )
    messages = []
    async def fake_post_parent(*, channel_id, text):
        messages.append((channel_id, text))
        return SlackMessage(ts="1792699000.000001", author_user_id="U0BT71H4FQE", text=text)
    slack.post_parent = fake_post_parent
    visibility = SlackReviewVisibility(
        client=slack, threads=ExecutiveSlackReviewThreads(runtime=runtime)
    )
    settings = ReviewHostSettings(
        enabled=True, publication_enabled=True, expected_host="review.example.com",
        require_https=True, installation_id=4242,
        installation_ids=frozenset({4242}), repositories=frozenset({REPO}),
        configured_reviewer="reviewer", authorized_actors=frozenset({"alice"}),
    )
    ingress = GitHubReviewReceiver(
        settings=settings, secret_source=HostCredentials(),
        pull_requests=github, actors=github, fabric=fabric, visibility=visibility,
    )
    body = json.dumps({
        "action": "labeled", "installation": {"id": 4242},
        "repository": {"full_name": REPO}, "number": 42,
        "pull_request": {"number": 42, "base": {"repo": {"full_name": REPO}}},
        "sender": {"login": "alice"}, "label": {"name": "independent-review"},
    }).encode()
    headers = [
        (b"host", b"review.example.com"),
        (b"content-type", b"application/json"),
        (b"x-github-event", b"pull_request"),
        (b"x-github-delivery", DELIVERY.encode()),
        (b"x-hub-signature-256", sign_webhook_body(secret=SECRET, body=body).encode()),
    ]

    def deliver(headers_override=None):
        response = []
        async def receive():
            return {"type": "http.request", "body": body, "more_body": False}
        async def send(msg):
            response.append(msg)
        scope = {
            "type": "http", "method": "POST", "scheme": "https",
            "path": settings.delivery_path, "query_string": b"",
            "headers": headers_override or headers,
        }
        asyncio.run(ingress(scope, receive, send))
        return response[0]["status"], json.loads(response[1]["body"])

    status, result = deliver()
    assert (status, result["status"]) == (202, "ADMITTED")
    assert len(runtime.jobs.list_jobs()) == 1
    job = runtime.jobs.list_jobs()[0]
    assert job.status.value == "QUEUED" and job.review_required is False
    assert job.requested_authorities == ["READ"]
    assert job.attempt_count == 0  # No invented START or Fabric execution.
    assert messages[0][0] == REVIEW_CHANNEL_ID
    assert "QUEUED" in messages[0][1]
    assert REPO not in messages[0][1]  # No private repo leak to public Slack.
    assert github_requests == [
        ("GET", "/repos/example/repo/collaborators/alice/permission"),
        ("GET", "/repos/example/repo/pulls/42"),
    ]
    status, result = deliver()
    assert (status, result["status"]) == (200, "ALREADY_ADMITTED")
    assert len(runtime.jobs.list_jobs()) == 1
    assert len(messages) == 1

    # A signed event delivered with a tampered body is never admitted or read.
    bad_headers = [
        (k, b"sha256=" + b"0" * 64 if k == b"x-hub-signature-256" else v)
        for k, v in headers
    ]
    status, result = deliver(bad_headers)
    assert (status, result["status"]) == (401, "SIGNATURE_INVALID")
    assert len(runtime.jobs.list_jobs()) == 1
