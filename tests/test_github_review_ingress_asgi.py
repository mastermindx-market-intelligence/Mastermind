"""ASGI-bound regressions: real byte stream/header → existing policy/admission ports."""
import asyncio
import json

import pytest

from control_plane.github_review_intent import PullRequestFacts, sign_webhook_body
from control_plane.github_review_host_config import ReviewHostSettings
from integrations.github_review_ingress_asgi import GitHubReviewReceiver

REPO = "example/repo"
DELIVERY = "11111111-2222-3333-4444-555555555555"
SECRET = "signed-request-secret"
SHA = "a" * 40


class Secret:
    def __init__(self):
        self.calls = []
    def webhook_secret(self, *, installation_id):
        self.calls.append(installation_id)
        return SECRET


class Pulls:
    def __init__(self):
        self.calls = []
    def read_pull_request(self, *, repository, pull_number):
        self.calls.append((repository, pull_number))
        return PullRequestFacts(
            repository=REPO, number=42, state="open", draft=False,
            head_sha=SHA, base_sha="b" * 40,
            head_repository=REPO, base_repository=REPO,
            title="Fix review integration", body="Tests for event delivery.",
        )


class Actors:
    def read_current_permission(self, *, repository, login):
        assert repository == REPO and login == "alice"
        return "write"


class Fabric:
    def __init__(self):
        self.keys = set()
        self.calls = 0
    def admitted_command_ids(self):
        return frozenset(self.keys)
    def admit_review_intent(self, *, decision, objective):
        self.calls += 1
        self.keys.add(decision.command_id)
        return "JOB-042"


def settings(**kwargs):
    defaults = dict(
        expected_host="review.example.com", require_https=True,
        enabled=True, publication_enabled=True, installation_id=4242,
        installation_ids=frozenset({4242}), repositories=frozenset({REPO}),
        configured_reviewer="reviewer", authorized_actors=frozenset({"alice"}),
    )
    defaults.update(kwargs)
    return ReviewHostSettings(**defaults)


def delivery():
    return json.dumps({
        "action": "labeled", "installation": {"id": 4242},
        "repository": {"full_name": REPO}, "number": 42,
        "pull_request": {
            "number": 42, "base": {"repo": {"full_name": REPO}}},
        "sender": {"login": "alice"}, "label": {"name": "independent-review"},
    }).encode()


def invoke(app, *, body=None, headers=None, path=None, method="POST", scheme="https"):
    payload = body if body is not None else delivery()
    pairs = [
        (b"host", b"review.example.com"),
        (b"content-type", b"application/json"),
        (b"x-github-event", b"pull_request"),
        (b"x-github-delivery", DELIVERY.encode()),
        (b"x-hub-signature-256", sign_webhook_body(secret=SECRET, body=payload).encode()),
    ]
    if headers:
        for key, value in headers.items():
            pairs = [(k, v) for k, v in pairs if k != key.lower().encode()]
            pairs.append((key.lower().encode(), value.encode()))
    messages = []
    async def receive():
        return {"type": "http.request", "body": payload, "more_body": False}
    async def send(message):
        messages.append(message)
    scope = {
        "type": "http", "method": method, "path": path or app._settings.delivery_path,
        "query_string": b"", "scheme": scheme, "headers": pairs,
    }
    asyncio.run(app(scope, receive, send))
    return messages[0]["status"], json.loads(messages[1]["body"])


def make(settings_override=None):
    secrets, pulls, fabric = Secret(), Pulls(), Fabric()
    app = GitHubReviewReceiver(
        settings=settings_override or settings(), secret_source=secrets,
        pull_requests=pulls, actors=Actors(), fabric=fabric,
    )
    return app, secrets, pulls, fabric


def test_signed_labeled_delivery_executes_single_durable_admission():
    app, secrets, pulls, fabric = make()
    status, data = invoke(app)
    assert (status, data["status"], data["job_id"]) == (202, "ADMITTED", "JOB-042")
    assert pulls.calls == [(REPO, 42)] and secrets.calls == [4242]
    assert fabric.calls == 1
    status, data = invoke(app)
    assert (status, data["status"]) == (200, "ALREADY_ADMITTED")
    assert fabric.calls == 1


def test_default_off_is_inert_before_secret_and_ports():
    app, secrets, pulls, fabric = make(settings(enabled=False, publication_enabled=False))
    assert invoke(app) == (404, {"schema": "mastermind.github_review_delivery_http.v1", "status": "RECEIVER_DISABLED"})
    assert secrets.calls == pulls.calls == [] and fabric.calls == 0


def test_publication_gate_is_independent_of_receiver_gate():
    app, secrets, pulls, fabric = make(settings(publication_enabled=False))
    assert invoke(app)[0] == 404
    assert secrets.calls == pulls.calls == [] and fabric.calls == 0


@pytest.mark.parametrize("header,code", [
    ({"host": "evil.example"}, "HOST_NOT_ALLOWED"),
    ({"content-type": "text/plain"}, "CONTENT_TYPE_INVALID"),
    ({"x-hub-signature-256": "sha256=" + "0" * 64}, "SIGNATURE_INVALID"),
])
def test_host_content_type_and_signature_refuse_before_fabric(header, code):
    app, secrets, pulls, fabric = make()
    status, result = invoke(app, headers=header)
    assert status in {401, 403, 415}
    assert result["status"] == code
    assert pulls.calls == [] and fabric.calls == 0


def test_tls_required_even_with_correct_host_and_signature():
    app, _, pulls, fabric = make()
    assert invoke(app, scheme="http")[1]["status"] == "TLS_REQUIRED"
    assert pulls.calls == [] and fabric.calls == 0


def test_payload_length_fence_refuses_before_credential():
    app, secrets, pulls, fabric = make(settings(max_body_bytes=64))
    status, result = invoke(app)
    assert (status, result["status"]) == (413, "BODY_TOO_LARGE")
    assert secrets.calls == pulls.calls == [] and fabric.calls == 0


def test_header_duplicates_refuse_before_credential():
    app, secrets, pulls, fabric = make()
    # The regular constructor deliberately guards this without model inference.
    payload = delivery()
    sent = []
    async def send(msg):
        sent.append(msg)
    async def receive():
        return {"type": "http.request", "body": payload, "more_body": False}
    scope = {
        "type": "http", "method": "POST", "scheme": "https",
        "path": app._settings.delivery_path, "query_string": b"",
        "headers": [(b"host", b"review.example.com"), (b"host", b"review.example.com")],
    }
    asyncio.run(app(scope, receive, send))
    assert sent[0]["status"] == 400
    assert secrets.calls == pulls.calls == [] and fabric.calls == 0

def test_never_ending_body_is_bounded_before_secret(monkeypatch):
    from integrations import github_review_ingress_asgi as receiver_module
    monkeypatch.setattr(receiver_module, "BODY_DEADLINE_SECONDS", 0.01)
    app, secrets, pulls, fabric = make()
    messages = []
    async def receive():
        await asyncio.sleep(0.1)
        return {"type": "http.request", "body": b"a", "more_body": True}
    async def send(message):
        messages.append(message)
    scope = {
        "type": "http", "method": "POST", "path": app._settings.delivery_path,
        "query_string": b"", "scheme": "https",
        "headers": [(b"host", b"review.example.com"),
                    (b"content-type", b"application/json"),
                    (b"x-github-event", b"pull_request"),
                    (b"x-github-delivery", DELIVERY.encode()),
                    (b"x-hub-signature-256", sign_webhook_body(secret=SECRET, body=delivery()).encode())],
    }
    asyncio.run(app(scope, receive, send))
    assert messages[0]["status"] == 408
    assert json.loads(messages[1]["body"])["status"] == "BODY_TIMEOUT"
    assert secrets.calls == pulls.calls == [] and fabric.calls == 0
