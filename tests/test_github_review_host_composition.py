"""Real host composition: signed GitHub event → App JWT/token → PR/actor → Runtime Job → Slack."""
import asyncio
import datetime
import json
import time

import httpx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from control_plane.executive_runtime import Runtime
from control_plane.github_review_host_config import ReviewHostSettings
from control_plane.github_review_intent import sign_webhook_body
from integrations.github_review_host_composition import compose_github_review_host
from integrations.slack_agent_dialogue.slack_web_api import SlackWebApiDialogueClient
from integrations.slack_agent_dialogue.engine import SlackMessage

REPO = "example/repo"
SHA = "a" * 40
SECRET = "test-webhook-secret"


def credentials():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )


class Hook:
    def webhook_secret(self, *, installation_id):
        assert installation_id == 4242
        return SECRET


def _settings(enabled=True):
    return ReviewHostSettings(
        enabled=enabled, publication_enabled=enabled,
        expected_host="review.example.com", require_https=True,
        installation_id=4242, installation_ids=frozenset({4242}),
        repositories=frozenset({REPO}), configured_reviewer="reviewer",
        authorized_actors=frozenset({"alice"}),
    )


def _run(app):
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
        (b"x-github-delivery", b"11111111-2222-3333-4444-555555555555"),
        (b"x-hub-signature-256", sign_webhook_body(secret=SECRET, body=body).encode()),
    ]
    events = []
    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}
    async def send(event):
        events.append(event)
    asyncio.run(app({
        "type": "http", "method": "POST", "path": app._settings.delivery_path,
        "query_string": b"", "scheme": "https", "headers": headers,
    }, receive, send))
    return events[0]["status"], json.loads(events[1]["body"])


def test_composition_proves_job_and_no_duplicate_with_real_app_jwt(tmp_path):
    now = time.time()
    pem = credentials()
    calls = []
    expires = datetime.datetime.fromtimestamp(
        now + 2400, tz=datetime.timezone.utc
    ).isoformat().replace("+00:00", "Z")

    def token_http(req):
        assert req.url.path.endswith("/app/installations/4242/access_tokens")
        return httpx.Response(201, json={
            "token": "ghs_APPID_JWT_nonfixed_new_format",
            "expires_at": expires,
            "permissions": {"metadata": "read", "contents": "read",
                            "pull_requests": "write"},
            "repositories": [{"full_name": REPO}],
        })

    def github_http(req):
        calls.append(req.url.path)
        assert req.headers["authorization"].startswith("Bearer ghs_")
        if req.url.path.endswith("/collaborators/alice/permission"):
            return httpx.Response(200, json={
                "user": {"login": "alice"}, "permission": "write",
            })
        if req.url.path.endswith("/pulls/42"):
            return httpx.Response(200, json={
                "number": 42, "state": "open", "draft": False,
                "head": {"sha": SHA, "repo": {"full_name": REPO}},
                "base": {"sha": "b" * 40, "repo": {"full_name": REPO}},
                "title": "Advisory review", "body": "No code execution",
            })
        raise AssertionError(req.url.path)

    slack = SlackWebApiDialogueClient(
        token="dummy", workspace_id="T0BRD2AQXQV",
        channel_id="C0CAUK8P8S3", bot_user_id="U0BT71H4FQE",
    )
    sent = []
    async def fake_post(*, channel_id, text):
        sent.append(text)
        return SlackMessage(
            ts="1792699000.000001", author_user_id="U0BT71H4FQE", text=text,
        )
    slack.post_parent = fake_post

    runtime = Runtime.at(tmp_path)
    app = compose_github_review_host(
        settings=_settings(), app_id=123,
        private_key_source=lambda: pem,
        webhook_secret_source=Hook(), runtime=runtime,
        admission_guard=lambda: None,
        relay_client=slack, publisher_login="reviewer-bot[bot]",
        app_token_http_client=httpx.Client(transport=httpx.MockTransport(token_http)),
        github_http_client=httpx.Client(transport=httpx.MockTransport(github_http)),
    )
    assert _run(app)[0] == 202
    assert _run(app)[1]["status"] == "ALREADY_ADMITTED"
    assert len(runtime.jobs.list_jobs()) == 1
    assert len(sent) == 1
    assert all(REPO not in item for item in sent)
    assert len(calls) == 4


def test_disabled_composition_touches_neither_credentials_nor_runtime(tmp_path):
    runtime = Runtime.at(tmp_path)
    calls = []
    def key():
        calls.append("secret")
        raise AssertionError("disabled receiver must not load key")
    def unavailable(req):
        raise AssertionError("no network on disabled receiver")
    slack = SlackWebApiDialogueClient(
        token="dummy", workspace_id="T0BRD2AQXQV",
        channel_id="C0CAUK8P8S3", bot_user_id="U0BT71H4FQE",
    )
    app = compose_github_review_host(
        settings=_settings(enabled=False), app_id=123,
        private_key_source=key, webhook_secret_source=Hook(), runtime=runtime,
        admission_guard=lambda: None, relay_client=slack,
        publisher_login="reviewer-bot[bot]",
        app_token_http_client=httpx.Client(transport=httpx.MockTransport(unavailable)),
        github_http_client=httpx.Client(transport=httpx.MockTransport(unavailable)),
    )
    assert _run(app)[0] == 404
    assert calls == []
    assert runtime.jobs.list_jobs() == []
