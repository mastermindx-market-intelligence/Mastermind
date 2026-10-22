"""The GitHub webhook can be mounted without changing incumbent route behavior."""
import asyncio
import json

import pytest

from control_plane.github_review_host_config import (
    ReviewHostSettings, EXACT_REVIEW_DELIVERY_PATH,
)
from integrations.github_review_asgi_mount import GitHubReviewASGIMount
from integrations.github_review_ingress_asgi import GitHubReviewReceiver


class Inert:
    def webhook_secret(self, *, installation_id):
        raise AssertionError("disabled receiver must never ask for a secret")
    def read_pull_request(self, *, repository, pull_number):
        raise AssertionError("disabled receiver must never read GitHub")
    def read_current_permission(self, *, repository, login):
        raise AssertionError("disabled receiver must never check an actor")
    def admitted_command_ids(self):
        raise AssertionError("disabled receiver must never read Runtime")
    def admit_review_intent(self, *, decision, objective):
        raise AssertionError("disabled receiver must never write Runtime")


class Existing:
    def __init__(self):
        self.calls = []
    async def __call__(self, scope, receive, send):
        self.calls.append(scope["path"])
        await send({"type": "http.response.start", "status": 418, "headers": []})
        await send({"type": "http.response.body", "body": b"existing"})


def receiver():
    owner = Inert()
    return GitHubReviewReceiver(
        settings=ReviewHostSettings(
            enabled=False, publication_enabled=False,
            expected_host="review.example.com", require_https=True,
            installation_id=4242, installation_ids=frozenset({4242}),
            repositories=frozenset({"example/repo"}),
            configured_reviewer="reviewer",
            authorized_actors=frozenset({"alice"}),
        ),
        secret_source=owner, pull_requests=owner, actors=owner, fabric=owner,
    )


def invoke(app, *, path, raw_path=None):
    sent = []
    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}
    async def send(message):
        sent.append(message)
    scope = {
        "type": "http", "method": "POST", "path": path,
        "raw_path": raw_path if raw_path is not None else path.encode(),
        "query_string": b"", "scheme": "https", "headers": [],
    }
    asyncio.run(app(scope, receive, send))
    return sent[0]["status"]


def test_inactive_mount_is_byte_preserving_for_existing_routes():
    old = Existing()
    mount = GitHubReviewASGIMount(existing_app=old)
    assert invoke(mount, path="/os/executive/submit") == 418
    assert invoke(mount, path=EXACT_REVIEW_DELIVERY_PATH) == 418
    assert old.calls == ["/os/executive/submit", EXACT_REVIEW_DELIVERY_PATH]


def test_explicit_receiver_only_intercepts_one_exact_path():
    old = Existing()
    mount = GitHubReviewASGIMount(existing_app=old, receiver=receiver())
    assert invoke(mount, path="/os/executive/submit") == 418
    assert old.calls == ["/os/executive/submit"]
    # Disabled mounts must preserve the incumbent route rather than shadow it.
    assert invoke(mount, path=EXACT_REVIEW_DELIVERY_PATH) == 418
    assert old.calls == ["/os/executive/submit", EXACT_REVIEW_DELIVERY_PATH]


def test_receiver_cannot_shadow_os_or_mcp_route():
    with pytest.raises(ValueError):
        ReviewHostSettings(
            enabled=False, publication_enabled=False,
            expected_host="review.example.com", require_https=True,
            delivery_path="/mcp", installation_id=4242,
            installation_ids=frozenset({4242}),
            repositories=frozenset({"example/repo"}),
            configured_reviewer="reviewer",
            authorized_actors=frozenset({"alice"}),
        )
