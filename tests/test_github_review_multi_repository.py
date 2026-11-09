"""One mounted endpoint may serve several already-composed receivers.

Every assertion here is about *selection*: which receiver a delivery reaches,
which receiver is never consulted, and which credential is never read.  The
receiver's own signature, source, admission and Slack checks are unchanged.
"""
import asyncio
import dataclasses
import json
import threading

import pytest

from control_plane.github_review_intent import PullRequestFacts, sign_webhook_body
from control_plane.github_review_host_config import (
    EXACT_REVIEW_DELIVERY_PATH,
    ReviewHostSettings,
)
from control_plane.github_review_intent_ingress import ReviewIngressUnavailable
from integrations.github_review_asgi_mount import GitHubReviewASGIMount
from integrations.github_review_asgi_routing import MAX_ACTIVE_ROUTINGS
from integrations.github_review_ingress_asgi import GitHubReviewReceiver

INSTALLATION = 4242
OTHER_INSTALLATION = 5252
REPO_A = "example/alpha"
REPO_B = "example/beta"
SECRET_A = "alpha-delivery-secret"
SECRET_B = "beta-delivery-secret"
DELIVERY = "11111111-2222-3333-4444-555555555555"
SHA = "a" * 40


class Secret:
    def __init__(self, secret):
        self.secret = secret
        self.calls = []
    def webhook_secret(self, *, installation_id):
        self.calls.append(installation_id)
        return self.secret


class Pulls:
    def __init__(self):
        self.calls = []
    def read_pull_request(self, *, repository, pull_number):
        self.calls.append((repository, pull_number))
        return PullRequestFacts(
            repository=repository, number=42, state="open", draft=False,
            head_sha=SHA, base_sha="b" * 40,
            head_repository=repository, base_repository=repository,
            title="Fix review integration", body="Tests for event delivery.",
        )


class Actors:
    def read_current_permission(self, *, repository, login):
        return "write"


class Fabric:
    def __init__(self, error=None):
        self.keys = set()
        self.calls = 0
        self.error = error
    def admitted_command_ids(self):
        return frozenset(self.keys)
    def admit_review_intent(self, *, decision, objective):
        self.calls += 1
        if self.error is not None:
            raise self.error
        self.keys.add(decision.command_id)
        return "JOB-042"


class Existing:
    def __init__(self):
        self.calls = []
        self.receives = []
        self.bodies = []
    async def __call__(self, scope, receive, send):
        self.calls.append(scope["path"])
        self.receives.append(receive)
        chunks = []
        while True:
            message = await receive()
            if message.get("type") != "http.request":
                break
            chunks.append(message.get("body", b""))
            if not message.get("more_body", False):
                break
        self.bodies.append(b"".join(chunks))
        await send({"type": "http.response.start", "status": 418, "headers": []})
        await send({"type": "http.response.body", "body": b"existing"})


def settings(repository, *, installation_id=INSTALLATION, enabled=True,
             publication_enabled=True, expected_host="review.example.com",
             require_https=True, max_body_bytes=None):
    kwargs = dict(
        enabled=enabled, publication_enabled=publication_enabled,
        expected_host=expected_host, require_https=require_https,
        installation_id=installation_id,
        installation_ids=frozenset({installation_id}),
        repositories=frozenset({repository}),
        configured_reviewer="reviewer", authorized_actors=frozenset({"alice"}),
    )
    if max_body_bytes is not None:
        kwargs["max_body_bytes"] = max_body_bytes
    return ReviewHostSettings(**kwargs)


def receiver(repository, *, secret, installation_id=INSTALLATION, fabric_error=None,
             **setting_kwargs):
    secrets, pulls, fabric = Secret(secret), Pulls(), Fabric(fabric_error)
    app = GitHubReviewReceiver(
        settings=settings(repository, installation_id=installation_id, **setting_kwargs),
        secret_source=secrets, pull_requests=pulls, actors=Actors(), fabric=fabric,
    )
    return app, secrets, pulls, fabric


def mount_pair(*, secret_a=SECRET_A, secret_b=SECRET_B, existing=None, **kwargs):
    a = receiver(REPO_A, secret=secret_a, **kwargs)
    b = receiver(REPO_B, secret=secret_b, **kwargs)
    old = existing if existing is not None else Existing()
    mount = GitHubReviewASGIMount(
        existing_app=old,
        receiver_map={(INSTALLATION, REPO_A): a[0], (INSTALLATION, REPO_B): b[0]},
    )
    return mount, old, a, b


def delivery(repository, *, installation_id=INSTALLATION):
    return json.dumps({
        "action": "labeled", "installation": {"id": installation_id},
        "repository": {"full_name": repository}, "number": 42,
        "pull_request": {
            "number": 42, "base": {"repo": {"full_name": repository}}},
        "sender": {"login": "alice"}, "label": {"name": "independent-review"},
    }).encode()


def invoke(app, *, body=None, secret=SECRET_A, headers=None, raw_headers=None,
           path=EXACT_REVIEW_DELIVERY_PATH, raw_path=None, method="POST",
           scheme="https", query=b"", content_length=None, chunks=None):
    payload = body if body is not None else delivery(REPO_A)
    if raw_headers is None:
        pairs = [
            (b"host", b"review.example.com"),
            (b"content-type", b"application/json"),
            (b"x-github-event", b"pull_request"),
            (b"x-github-delivery", DELIVERY.encode()),
            (b"x-hub-signature-256", sign_webhook_body(
                secret=secret, body=payload).encode()),
        ]
        if headers:
            for key, value in headers.items():
                pairs = [(k, v) for k, v in pairs if k != key.lower().encode()]
                pairs.append((key.lower().encode(), value.encode()))
        if content_length is not None:
            pairs = [(k, v) for k, v in pairs if k != b"content-length"]
            pairs.append((b"content-length", str(content_length).encode()))
        raw_headers = pairs
    messages = []
    pending = list(chunks) if chunks is not None else [payload]
    async def receive():
        if not pending:
            return {"type": "http.request", "body": b"", "more_body": False}
        chunk = pending.pop(0)
        return {"type": "http.request", "body": chunk, "more_body": bool(pending)}
    async def send(message):
        messages.append(message)
    scope = {
        "type": "http", "method": method, "path": path,
        "raw_path": raw_path if raw_path is not None else path.encode("ascii"),
        "query_string": query, "scheme": scheme, "headers": raw_headers,
    }
    asyncio.run(app(scope, receive, send))
    if not messages:
        return None, None
    raw = b"".join(
        message.get("body", b"") for message in messages
        if message["type"] == "http.response.body"
    )
    if not raw:
        return messages[0]["status"], None
    try:
        return messages[0]["status"], json.loads(raw)
    except json.JSONDecodeError:
        # The incumbent app's own body, not a delivery refusal.
        return messages[0]["status"], raw


# --- the two repositories share one endpoint and one installation ----------


def test_each_repository_selects_only_its_own_receiver():
    mount, old, a, b = mount_pair()
    status, data = invoke(mount, body=delivery(REPO_A), secret=SECRET_A)
    assert (status, data["status"]) == (202, "ADMITTED")
    assert a[2].calls == [(REPO_A, 42)] and b[2].calls == []
    assert a[1].calls == [INSTALLATION] and b[1].calls == []
    assert a[3].calls == 1 and b[3].calls == 0

    status, data = invoke(mount, body=delivery(REPO_B), secret=SECRET_B)
    assert (status, data["status"]) == (202, "ADMITTED")
    assert b[2].calls == [(REPO_B, 42)] and a[2].calls == [(REPO_A, 42)]
    assert b[1].calls == [INSTALLATION] and a[1].calls == [INSTALLATION]
    assert b[3].calls == 1 and a[3].calls == 1
    assert old.calls == []


def test_a_shared_installation_never_cross_selects_repositories():
    mount, old, a, b = mount_pair()
    # A body that names repository B but carries repository A's secret must
    # reach repository B's receiver, and only that one.
    status, data = invoke(mount, body=delivery(REPO_B), secret=SECRET_A)
    assert (status, data["status"]) == (401, "SIGNATURE_INVALID")
    assert b[1].calls == [INSTALLATION]
    assert a[1].calls == []
    assert a[2].calls == [] and b[2].calls == []
    assert a[3].calls == 0 and b[3].calls == 0
    assert old.calls == []


def test_an_unenrolled_installation_selects_no_receiver():
    mount, old, a, b = mount_pair()
    status, data = invoke(
        mount, body=delivery(REPO_A, installation_id=OTHER_INSTALLATION), secret=SECRET_A)
    assert (status, data["status"]) == (404, "REVIEW_RECEIVER_NOT_FOUND")
    assert a[1].calls == [] and b[1].calls == []
    assert a[3].calls == 0 and b[3].calls == 0


def test_an_unenrolled_repository_selects_no_receiver():
    mount, old, a, b = mount_pair()
    status, data = invoke(mount, body=delivery("example/gamma"), secret=SECRET_A)
    assert (status, data["status"]) == (404, "REVIEW_RECEIVER_NOT_FOUND")
    assert a[1].calls == [] and b[1].calls == []
    assert a[3].calls == 0 and b[3].calls == 0


def test_one_receiver_is_never_retried_after_a_refusal():
    mount, old, a, b = mount_pair()
    status, _ = invoke(mount, body=delivery(REPO_B), secret=SECRET_A)
    assert status == 401
    # A second delivery for the same tenant must not make the mount try the
    # other receiver either.
    status, _ = invoke(mount, body=delivery(REPO_B), secret=SECRET_A)
    assert status == 401
    assert a[1].calls == [] and b[1].calls == [INSTALLATION, INSTALLATION]


def test_uncertain_admission_is_not_retried_on_another_receiver():
    a = receiver(REPO_A, secret=SECRET_A, fabric_error=ReviewIngressUnavailable("X"))
    b = receiver(REPO_B, secret=SECRET_B)
    old = Existing()
    mount = GitHubReviewASGIMount(
        existing_app=old,
        receiver_map={(INSTALLATION, REPO_A): a[0], (INSTALLATION, REPO_B): b[0]},
    )
    status, data = invoke(mount, body=delivery(REPO_A), secret=SECRET_A)
    assert (status, data["status"]) == (503, "ADMISSION_UNAVAILABLE_OR_UNKNOWN")
    assert a[1].calls == [INSTALLATION]
    assert b[1].calls == []


# --- strict hints fail closed before any receiver is chosen ---------------


@pytest.mark.parametrize("body", [
    b'{"action":"labeled","installation":{"id":4242},'
    b'"repository":{"full_name":"example/alpha"},'
    b'"repository":{"full_name":"example/beta"}}',
    b'{"action":"labeled","installation":{"id":4242},'
    b'"repository":{"full_name":"example/alpha"},"extra":NaN}',
    b'{"action":"labeled","installation":{"id":4242},'
    b'"repository":{"full_name":"example/alpha"},"extra":1e999}',
    b'{"action":"labeled","installation":{"id":4242},',
    b'[]',
    b'"example/alpha"',
])
def test_a_malformed_or_ambiguous_body_selects_no_receiver(body):
    mount, old, a, b = mount_pair()
    status, data = invoke(mount, body=body, secret=SECRET_A)
    assert (status, data["status"]) == (400, "DELIVERY_BODY_INVALID")
    assert a[1].calls == [] and b[1].calls == []
    assert a[3].calls == 0 and b[3].calls == 0


@pytest.mark.parametrize("body", [
    b'{"action":"labeled","repository":{"full_name":"example/alpha"}}',
    b'{"action":"labeled","installation":{"id":0},'
    b'"repository":{"full_name":"example/alpha"}}',
    b'{"action":"labeled","installation":{"id":"4242"},'
    b'"repository":{"full_name":"example/alpha"}}',
    b'{"action":"labeled","installation":{"id":4242},'
    b'"repository":{"full_name":"not canonical"}}',
])
def test_an_unusable_tenant_hint_selects_no_receiver(body):
    mount, old, a, b = mount_pair()
    status, data = invoke(mount, body=body, secret=SECRET_A)
    assert (status, data["status"]) == (400, "DELIVERY_BODY_INVALID")
    assert a[1].calls == [] and b[1].calls == []


# --- the edge surface is validated before routing -------------------------


def test_the_wrong_method_is_refused_before_any_credential():
    mount, old, a, b = mount_pair()
    status, data = invoke(mount, body=delivery(REPO_A), secret=SECRET_A, method="GET")
    assert (status, data["status"]) == (405, "METHOD_NOT_ALLOWED")
    assert a[1].calls == [] and b[1].calls == []


def test_the_wrong_host_is_refused_before_any_credential():
    mount, old, a, b = mount_pair()
    status, data = invoke(
        mount, body=delivery(REPO_A), secret=SECRET_A,
        headers={"host": "evil.example"})
    assert (status, data["status"]) == (403, "HOST_NOT_ALLOWED")
    assert a[1].calls == [] and b[1].calls == []


def test_plaintext_is_refused_before_any_credential():
    mount, old, a, b = mount_pair()
    status, data = invoke(
        mount, body=delivery(REPO_A), secret=SECRET_A, scheme="http")
    assert (status, data["status"]) == (403, "TLS_REQUIRED")
    assert a[1].calls == [] and b[1].calls == []


def test_a_non_json_content_type_is_refused_before_any_credential():
    mount, old, a, b = mount_pair()
    status, data = invoke(
        mount, body=delivery(REPO_A), secret=SECRET_A,
        headers={"content-type": "text/plain"})
    assert (status, data["status"]) == (415, "CONTENT_TYPE_INVALID")
    assert a[1].calls == [] and b[1].calls == []


def test_a_raw_path_spoof_is_refused_before_any_credential():
    mount, old, a, b = mount_pair()
    status, data = invoke(
        mount, body=delivery(REPO_A), secret=SECRET_A,
        raw_path=EXACT_REVIEW_DELIVERY_PATH.encode("ascii") + b"/")
    assert (status, data["status"]) == (404, "PATH_NOT_FOUND")
    assert a[1].calls == [] and b[1].calls == []


def test_a_query_string_spoof_is_refused_before_any_credential():
    mount, old, a, b = mount_pair()
    status, data = invoke(
        mount, body=delivery(REPO_A), secret=SECRET_A, query=b"repository=example/beta")
    assert (status, data["status"]) == (404, "PATH_NOT_FOUND")
    assert a[1].calls == [] and b[1].calls == []


def test_a_duplicate_header_is_refused_before_any_credential():
    mount, old, a, b = mount_pair()
    payload = delivery(REPO_A)
    raw_headers = [
        (b"host", b"review.example.com"), (b"host", b"review.example.com"),
        (b"content-type", b"application/json"),
        (b"x-github-event", b"pull_request"),
        (b"x-github-delivery", DELIVERY.encode()),
        (b"x-hub-signature-256", sign_webhook_body(
            secret=SECRET_A, body=payload).encode()),
    ]
    status, data = invoke(mount, body=payload, raw_headers=raw_headers)
    assert (status, data["status"]) == (400, "HEADERS_INVALID")
    assert a[1].calls == [] and b[1].calls == []


def test_a_missing_delivery_header_is_refused_before_any_credential():
    mount, old, a, b = mount_pair()
    payload = delivery(REPO_A)
    raw_headers = [
        (b"host", b"review.example.com"),
        (b"content-type", b"application/json"),
        (b"x-github-event", b"pull_request"),
        (b"x-hub-signature-256", sign_webhook_body(
            secret=SECRET_A, body=payload).encode()),
    ]
    status, data = invoke(mount, body=payload, raw_headers=raw_headers)
    assert (status, data["status"]) == (400, "DELIVERY_HEADERS_MISSING")
    assert a[1].calls == [] and b[1].calls == []


# --- bounded body reads ---------------------------------------------------


def test_an_oversized_content_length_is_refused_before_any_credential():
    mount, old, a, b = mount_pair(max_body_bytes=64)
    status, data = invoke(
        mount, body=delivery(REPO_A), secret=SECRET_A, content_length=4096)
    assert (status, data["status"]) == (413, "BODY_TOO_LARGE")
    assert a[1].calls == [] and b[1].calls == []


def test_an_oversized_body_is_refused_before_any_credential():
    mount, old, a, b = mount_pair(max_body_bytes=64)
    status, data = invoke(mount, body=delivery(REPO_A), secret=SECRET_A)
    assert (status, data["status"]) == (413, "BODY_TOO_LARGE")
    assert a[1].calls == [] and b[1].calls == []


def test_a_content_length_mismatch_is_refused_before_any_credential():
    mount, old, a, b = mount_pair()
    payload = delivery(REPO_A)
    status, data = invoke(
        mount, body=payload, secret=SECRET_A, content_length=len(payload) + 5)
    assert (status, data["status"]) == (400, "CONTENT_LENGTH_MISMATCH")
    assert a[1].calls == [] and b[1].calls == []


def test_a_never_ending_body_is_bounded_before_any_credential(monkeypatch):
    from integrations import github_review_asgi_mount as mount_module
    monkeypatch.setattr(mount_module, "ROUTING_BODY_DEADLINE_SECONDS", 0.01)
    mount, old, a, b = mount_pair()
    messages = []
    async def receive():
        await asyncio.sleep(0.1)
        return {"type": "http.request", "body": b"a", "more_body": True}
    async def send(message):
        messages.append(message)
    scope = {
        "type": "http", "method": "POST", "path": EXACT_REVIEW_DELIVERY_PATH,
        "raw_path": EXACT_REVIEW_DELIVERY_PATH.encode("ascii"),
        "query_string": b"", "scheme": "https",
        "headers": [(b"host", b"review.example.com"),
                    (b"content-type", b"application/json"),
                    (b"x-github-event", b"pull_request"),
                    (b"x-github-delivery", DELIVERY.encode()),
                    (b"x-hub-signature-256", sign_webhook_body(
                        secret=SECRET_A, body=delivery(REPO_A)).encode())],
    }
    asyncio.run(mount(scope, receive, send))
    assert messages[0]["status"] == 408
    assert json.loads(messages[1]["body"])["status"] == "BODY_TIMEOUT"
    assert a[1].calls == [] and b[1].calls == []


def test_a_client_disconnect_answers_nothing_and_reads_no_credential():
    mount, old, a, b = mount_pair()
    messages = []
    async def receive():
        return {"type": "http.disconnect"}
    async def send(message):
        messages.append(message)
    scope = {
        "type": "http", "method": "POST", "path": EXACT_REVIEW_DELIVERY_PATH,
        "raw_path": EXACT_REVIEW_DELIVERY_PATH.encode("ascii"),
        "query_string": b"", "scheme": "https",
        "headers": [(b"host", b"review.example.com"),
                    (b"content-type", b"application/json"),
                    (b"x-github-event", b"pull_request"),
                    (b"x-github-delivery", DELIVERY.encode()),
                    (b"x-hub-signature-256", sign_webhook_body(
                        secret=SECRET_A, body=delivery(REPO_A)).encode())],
    }
    asyncio.run(mount(scope, receive, send))
    assert messages == []
    assert a[1].calls == [] and b[1].calls == []


# --- bounded routing pressure, no queue ------------------------------------


def test_routing_saturation_refuses_instead_of_queueing():
    mount, old, a, b = mount_pair()
    entered = 0
    all_entered = asyncio.Event()
    release = asyncio.Event()
    saturated = []

    async def blocking_receive():
        nonlocal entered
        entered += 1
        if entered >= MAX_ACTIVE_ROUTINGS:
            all_entered.set()
        await release.wait()
        return {"type": "http.request", "body": delivery(REPO_A), "more_body": False}

    def scope_for():
        payload = delivery(REPO_A)
        return {
            "type": "http", "method": "POST", "path": EXACT_REVIEW_DELIVERY_PATH,
            "raw_path": EXACT_REVIEW_DELIVERY_PATH.encode("ascii"),
            "query_string": b"", "scheme": "https",
            "headers": [(b"host", b"review.example.com"),
                        (b"content-type", b"application/json"),
                        (b"x-github-event", b"pull_request"),
                        (b"x-github-delivery", DELIVERY.encode()),
                        (b"x-hub-signature-256", sign_webhook_body(
                            secret=SECRET_A, body=payload).encode())],
        }

    async def main():
        async def drain(message):
            saturated.append(message)
        held = [
            asyncio.create_task(mount(scope_for(), blocking_receive, drain))
            for _ in range(MAX_ACTIVE_ROUTINGS)
        ]
        await asyncio.wait_for(all_entered.wait(), timeout=5)
        async def immediate():
            return {"type": "http.request", "body": delivery(REPO_A), "more_body": False}
        await mount(scope_for(), immediate, drain)
        release.set()
        await asyncio.gather(*held)

    asyncio.run(main())
    assert saturated[0]["status"] == 503
    assert json.loads(saturated[1]["body"])["status"] == "ROUTING_BUSY"


# --- the routed receiver gets the original bytes and the original headers ---


def test_the_routed_receiver_receives_the_original_headers_and_scope(monkeypatch):
    owner = Secret(SECRET_A)
    recorder = GitHubReviewReceiver(
        settings=settings(REPO_A), secret_source=owner,
        pull_requests=Pulls(), actors=Actors(), fabric=Fabric(),
    )
    old = Existing()
    mount = GitHubReviewASGIMount(
        existing_app=old, receiver_map={(INSTALLATION, REPO_A): recorder},
    )
    scopes = []
    original = GitHubReviewReceiver.__call__
    async def record(self, scope, receive, send):
        scopes.append(scope)
        return await original(self, scope, receive, send)
    monkeypatch.setattr(GitHubReviewReceiver, "__call__", record)
    payload = delivery(REPO_A)
    status, data = invoke(mount, body=payload, secret=SECRET_A)
    assert (status, data["status"]) == (202, "ADMITTED")
    assert len(scopes) == 1
    handed = scopes[0]
    assert handed["path"] == EXACT_REVIEW_DELIVERY_PATH
    assert handed["method"] == "POST"
    assert handed["scheme"] == "https"
    assert handed["query_string"] == b""
    assert dict(handed["headers"])[b"x-hub-signature-256"] == sign_webhook_body(
        secret=SECRET_A, body=payload).encode()
    assert dict(handed["headers"])[b"x-github-delivery"] == DELIVERY.encode()


def test_a_chunked_body_is_replayed_byte_for_byte():
    mount, old, a, b = mount_pair()
    payload = delivery(REPO_A)
    chunks = [payload[:40], payload[40:120], payload[120:]]
    # A signature over the whole body only verifies if the receiver is handed
    # the exact original bytes, not a re-serialised copy.
    status, data = invoke(mount, body=payload, secret=SECRET_A, chunks=chunks)
    assert (status, data["status"]) == (202, "ADMITTED")
    assert a[2].calls == [(REPO_A, 42)]


def test_a_cancelled_route_releases_its_routing_slot():
    mount, old, a, b = mount_pair()
    started = asyncio.Event()

    async def blocking_receive():
        started.set()
        await asyncio.sleep(30)
        return {"type": "http.request", "body": delivery(REPO_A), "more_body": False}

    def scope_for():
        payload = delivery(REPO_A)
        return {
            "type": "http", "method": "POST", "path": EXACT_REVIEW_DELIVERY_PATH,
            "raw_path": EXACT_REVIEW_DELIVERY_PATH.encode("ascii"),
            "query_string": b"", "scheme": "https",
            "headers": [(b"host", b"review.example.com"),
                        (b"content-type", b"application/json"),
                        (b"x-github-event", b"pull_request"),
                        (b"x-github-delivery", DELIVERY.encode()),
                        (b"x-hub-signature-256", sign_webhook_body(
                            secret=SECRET_A, body=payload).encode())],
        }

    async def main():
        async def drain(message):
            return None
        task = asyncio.create_task(mount(scope_for(), blocking_receive, drain))
        await asyncio.wait_for(started.wait(), timeout=5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(main())
    # The cancelled route must not have left its routing slot taken.
    status, data = invoke(mount, body=delivery(REPO_A), secret=SECRET_A)
    assert (status, data["status"]) == (202, "ADMITTED")


# --- default-off and unrelated routes --------------------------------------


def test_a_disabled_receiver_leaves_the_incumbent_route_in_charge():
    mount, old, a, b = mount_pair(enabled=False, publication_enabled=False)
    status, data = invoke(mount, body=delivery(REPO_A), secret=SECRET_A)
    assert status == 418
    assert old.calls == [EXACT_REVIEW_DELIVERY_PATH]
    # The incumbent app still receives the whole delivery body: a closed
    # receiver must not shadow the route and must not eat the body.
    assert old.bodies == [delivery(REPO_A)]
    assert a[1].calls == [] and b[1].calls == []


def test_an_unrelated_route_is_unchanged_and_unconsumed():
    mount, old, a, b = mount_pair()
    status, _ = invoke(mount, path="/os/executive/submit", body=delivery(REPO_A),
                       secret=SECRET_A)
    assert status == 418
    assert old.calls == ["/os/executive/submit"]
    assert old.bodies == [delivery(REPO_A)]
    assert a[1].calls == [] and b[1].calls == []


def test_the_exact_delivery_path_is_the_only_intercepted_route():
    mount, old, a, b = mount_pair()
    status, _ = invoke(mount, path="/internal/github/review-intent/other",
                       body=delivery(REPO_A), secret=SECRET_A)
    assert status == 418
    assert old.calls == ["/internal/github/review-intent/other"]
    assert a[1].calls == [] and b[1].calls == []


# Parent qualification of the returned proposal's isolation/resource boundaries.
async def _async_delivery(app, repository=REPO_A, secret=SECRET_A, send_override=None):
    payload = delivery(repository)
    scope = {
        "type": "http", "method": "POST", "path": EXACT_REVIEW_DELIVERY_PATH,
        "raw_path": EXACT_REVIEW_DELIVERY_PATH.encode(), "query_string": b"",
        "scheme": "https", "headers": [
            (b"host", b"review.example.com"), (b"content-type", b"application/json"),
            (b"x-github-event", b"pull_request"), (b"x-github-delivery", DELIVERY.encode()),
            (b"x-hub-signature-256", sign_webhook_body(secret=secret, body=payload).encode()),
        ],
    }
    async def receive():
        return {"type": "http.request", "body": payload, "more_body": False}
    sent = []
    async def send(message):
        sent.append(message)
        if send_override is not None:
            await send_override(message)
    await app(scope, receive, send)
    return sent[0]["status"], json.loads(sent[1]["body"])


def test_routing_slots_do_not_block_other_repository_during_secret_reads():
    mount, old, a, b = mount_pair()
    entered = threading.Event()
    release = threading.Event()
    lock = threading.Lock()
    count = 0
    def slow_secret(*, installation_id):
        nonlocal count
        with lock:
            count += 1
            if count == MAX_ACTIVE_ROUTINGS:
                entered.set()
        assert release.wait(5), "test did not release the secret read"
        return SECRET_A
    a[1].webhook_secret = slow_secret
    async def exercise():
        tasks = [asyncio.create_task(_async_delivery(mount)) for _ in range(MAX_ACTIVE_ROUTINGS)]
        try:
            assert await asyncio.to_thread(entered.wait, 3)
            status, result = await asyncio.wait_for(_async_delivery(mount, REPO_B, SECRET_B), 2)
            assert (status, result["status"]) == (202, "ADMITTED")
            assert b[3].calls == 1 and not release.is_set()
        finally:
            release.set()
            await asyncio.gather(*tasks)
    asyncio.run(exercise())


def test_slow_refusal_response_does_not_hold_routing_slots():
    mount, old, a, b = mount_pair()
    entered = 0
    all_entered = asyncio.Event()
    release = asyncio.Event()
    async def slow_send(message):
        nonlocal entered
        if message["type"] == "http.response.start":
            entered += 1
            if entered == MAX_ACTIVE_ROUTINGS:
                all_entered.set()
            await release.wait()
    async def exercise():
        tasks = [asyncio.create_task(_async_delivery(
            mount, "example/missing", send_override=slow_send)) for _ in range(MAX_ACTIVE_ROUTINGS)]
        try:
            await asyncio.wait_for(all_entered.wait(), 2)
            status, result = await asyncio.wait_for(_async_delivery(mount, REPO_B, SECRET_B), 2)
            assert (status, result["status"]) == (202, "ADMITTED")
        finally:
            release.set()
            await asyncio.gather(*tasks)
    asyncio.run(exercise())


def test_disabled_selection_on_active_route_never_calls_incumbent():
    a = receiver(REPO_A, secret=SECRET_A, enabled=False)
    b = receiver(REPO_B, secret=SECRET_B)
    old = Existing()
    mount = GitHubReviewASGIMount(existing_app=old, receiver_map={
        (INSTALLATION, REPO_A): a[0], (INSTALLATION, REPO_B): b[0],
    })
    status, result = invoke(mount)
    assert (status, result["status"]) == (404, "REVIEW_RECEIVER_NOT_FOUND")
    assert old.calls == a[1].calls == b[1].calls == []
    assert a[3].calls == b[3].calls == 0


@pytest.mark.parametrize("disabled", [False, True])
def test_mixed_body_caps_are_refused_at_enrollment(disabled):
    a = receiver(REPO_A, secret=SECRET_A, max_body_bytes=64, enabled=not disabled)
    b = receiver(REPO_B, secret=SECRET_B, max_body_bytes=1024)
    with pytest.raises(ValueError, match="body limit"):
        GitHubReviewASGIMount(existing_app=Existing(), receiver_map={
            (INSTALLATION, REPO_A): a[0], (INSTALLATION, REPO_B): b[0],
        })
    assert a[1].calls == b[1].calls == []


def test_fragmented_body_retention_and_replay_are_byte_bounded():
    from integrations.github_review_ingress_asgi import read_bounded_request_body
    from integrations.github_review_asgi_routing import replay_request_body
    payload = delivery(REPO_A)
    fragments = iter([b""] * 10000 + [bytes([value]) for value in payload])
    async def receive():
        try:
            return {"type": "http.request", "body": next(fragments), "more_body": True}
        except StopIteration:
            return {"type": "http.request", "body": b"", "more_body": False}
    async def exercise():
        read = await read_bounded_request_body(receive, max_bytes=len(payload), deadline_seconds=2)
        assert read.failure is None and read.total == len(payload)
        # Storage contains at most one body, independent of empty/tiny fragment count.
        assert len(read.chunks) <= 1 and b"".join(read.chunks) == payload
        replay = replay_request_body(read.chunks)
        assert await replay() == {"type": "http.request", "body": payload, "more_body": False}
        assert (await replay())["body"] == b""
    asyncio.run(exercise())


def test_map_bound_and_generator_refusal_do_not_consume_unbounded_input():
    class NeverIterate:
        def __iter__(self):
            raise AssertionError("unbounded input must not be materialized")
    with pytest.raises(TypeError):
        GitHubReviewASGIMount(existing_app=Existing(), receiver_map=NeverIterate())
    entries = {(INSTALLATION, f"example/repo{i}"): receiver(
        f"example/repo{i}", secret=SECRET_A)[0] for i in range(33)}
    with pytest.raises(ValueError, match="too many"):
        GitHubReviewASGIMount(existing_app=Existing(), receiver_map=entries)


def test_receiver_subclass_cannot_replace_authentication():
    class Bypass(GitHubReviewReceiver):
        async def __call__(self, *args):
            raise AssertionError("unqualified receiver must never run")
    candidate = Bypass(settings=settings(REPO_A), secret_source=Secret(SECRET_A),
                       pull_requests=Pulls(), actors=Actors(), fabric=Fabric())
    with pytest.raises(TypeError):
        GitHubReviewASGIMount(existing_app=Existing(), receiver_map={(INSTALLATION, REPO_A): candidate})


@pytest.mark.parametrize("name", ["repositories", "installation_ids", "authorized_actors", "allowed_associations"])
def test_mutable_settings_are_not_enrolled(name):
    a = receiver(REPO_A, secret=SECRET_A)
    a[0]._settings = dataclasses.replace(a[0]._settings, **{name: set(getattr(a[0]._settings, name))})
    with pytest.raises(TypeError):
        GitHubReviewASGIMount(existing_app=Existing(), receiver_map={(INSTALLATION, REPO_A): a[0]})


def test_original_mapping_mutation_cannot_replace_selected_receiver():
    a = receiver(REPO_A, secret=SECRET_A)
    substitute = receiver(REPO_A, secret=SECRET_B)
    entries = {(INSTALLATION, REPO_A): a[0]}
    mount = GitHubReviewASGIMount(existing_app=Existing(), receiver_map=entries)
    entries[(INSTALLATION, REPO_A)] = substitute[0]
    assert invoke(mount)[0] == 202
    assert a[1].calls == [INSTALLATION] and substitute[1].calls == []


@pytest.mark.parametrize("when", ["selection", "queued"])
def test_settings_drift_refuses_before_credential_selection(monkeypatch, when):
    mount, old, a, b = mount_pair()
    def change_binding():
        a[0]._settings = dataclasses.replace(
            a[0]._settings, installation_id=OTHER_INSTALLATION,
            installation_ids=frozenset({OTHER_INSTALLATION}),
        )
    if when == "selection":
        change_binding()
    else:
        original = GitHubReviewReceiver._schedule
        def schedule(slot, function, *args, **kwargs):
            if function.__name__ == "_admit":
                change_binding()
            return original(slot, function, *args, **kwargs)
        monkeypatch.setattr(GitHubReviewReceiver, "_schedule", staticmethod(schedule))
    status, result = invoke(mount)
    assert status == 503
    assert result["status"] == ("REVIEW_RECEIVER_BINDING_CHANGED" if when == "selection"
                                else "ADMISSION_UNAVAILABLE_OR_UNKNOWN")
    assert a[1].calls == b[1].calls == a[2].calls == b[2].calls == old.calls == []
    assert a[3].calls == b[3].calls == 0


def test_broader_configured_allowlist_does_not_enroll_another_installation():
    a = receiver(REPO_A, secret=SECRET_A)
    a[0]._settings = dataclasses.replace(
        a[0]._settings, installation_ids=frozenset({INSTALLATION, OTHER_INSTALLATION}),
    )
    mount = GitHubReviewASGIMount(existing_app=Existing(), receiver_map={(INSTALLATION, REPO_A): a[0]})
    status, result = invoke(mount, body=delivery(REPO_A, installation_id=OTHER_INSTALLATION))
    assert (status, result["status"]) == (404, "REVIEW_RECEIVER_NOT_FOUND")
    assert a[1].calls == []
    assert invoke(mount)[0] == 202
    assert a[1].calls == [INSTALLATION]
