"""Actual signed ASGI admission path with the accepted risk gate, no network."""
from __future__ import annotations

import asyncio
import json

import pytest

from control_plane.github_review_host_config import ReviewHostSettings
from control_plane.github_review_intent import sign_webhook_body
from integrations.github_review_ingress_asgi import GitHubReviewReceiver
from integrations.github_review_risk_consumer import GitHubReviewRiskConsumer
from test_github_review_risk_consumer import ExistingApp, REPO
from test_github_review_risk_admission import Ledger

SECRET = "signed-hermetic-risk-test"
DELIVERY = "11111111-2222-3333-4444-555555555555"


class Secret:
    def webhook_secret(self, *, installation_id):
        assert installation_id == 4242
        return SECRET


def settings():
    return ReviewHostSettings(
        enabled=True, publication_enabled=True,
        expected_host="review.example.com", require_https=True,
        installation_id=4242, installation_ids=frozenset({4242}),
        repositories=frozenset({REPO}), configured_reviewer="reviewer",
        authorized_actors=frozenset({"alice"}),
        allow_lifecycle_review=True, allow_repository_policy_review=True,
    )


def host(path="docs/user-guide.md", *, missing=False):
    source = ExistingApp(path)
    source.missing_page = missing
    ledger = Ledger()
    source.api.read_current_permission = lambda *, repository, login: "write"
    app = GitHubReviewReceiver(
        settings=settings(), secret_source=Secret(), pull_requests=source.api,
        actors=source.api, fabric=ledger,
        risk_consumer=GitHubReviewRiskConsumer(github=source.api, repository=REPO),
    )
    return app, source, ledger


async def deliver(app, *, action="opened", sender="dependabot[bot]", bad_sig=False):
    body = json.dumps({
        "action": action,
        "installation": {"id": 4242},
        "repository": {"full_name": REPO},
        "number": 42,
        "pull_request": {"number": 42, "base": {"repo": {"full_name": REPO}}},
        "sender": {"login": sender},
        "label": {"name": "independent-review"},
    }).encode("ascii")
    signature = sign_webhook_body(secret=SECRET, body=body)
    if bad_sig:
        signature = "sha256=" + "0" * 64
    headers = [
        (b"host", b"review.example.com"),
        (b"content-type", b"application/json"),
        (b"x-github-event", b"pull_request"),
        (b"x-github-delivery", DELIVERY.encode("ascii")),
        (b"x-hub-signature-256", signature.encode("ascii")),
    ]
    responses = []
    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}
    async def send(frame):
        responses.append(frame)
    await app({
        "type": "http", "method": "POST", "scheme": "https",
        "path": settings().delivery_path, "query_string": b"",
        "headers": headers,
    }, receive, send)
    return responses[0]["status"], json.loads(responses[-1]["body"])


def test_signed_fast_webhook_skips_without_admitting_or_notifying():
    app, source, ledger = host("docs/user-guide.md")
    status, body = asyncio.run(deliver(app))
    assert status == 200
    assert body["status"] == "SKIPPED_NOT_REQUIRED"
    assert body["reason"] == "REVIEW_NOT_REQUIRED"
    assert "job_id" not in body
    assert ledger.jobs == {} and ledger.calls == 0
    assert len(source.calls) == 4
    assert all(method == "GET" for method, _ in source.calls)


@pytest.mark.parametrize("path", [
    ".github/workflows/ci.yml",
])
def test_signed_critical_uses_original_one_job(path):
    app, source, ledger = host(path)
    status, body = asyncio.run(deliver(app))
    assert status == 202 and body["status"] == "ADMITTED", body
    assert body["job_id"] == "JOB-1"
    assert len(ledger.jobs) == 1
    assert len(source.calls) == 4


def test_signed_source_incomplete_holds_no_admission():
    app, source, ledger = host(missing=True)
    status, body = asyncio.run(deliver(app))
    assert status == 503 and body["status"] == "ADMISSION_UNAVAILABLE_OR_UNKNOWN"
    assert ledger.jobs == {} and ledger.calls == 0


def test_signature_invalid_is_rejected_before_any_source_or_job():
    app, source, ledger = host()
    status, body = asyncio.run(deliver(app, bad_sig=True))
    assert status == 401 and body["status"] == "SIGNATURE_INVALID"
    assert source.calls == [] and ledger.jobs == {}


def test_manual_label_preserves_existing_authorized_route_with_one_pr_get():
    app, source, ledger = host()
    status, body = asyncio.run(deliver(app, action="labeled", sender="alice"))
    assert status == 202 and body["status"] == "ADMITTED", body
    assert len(ledger.jobs) == 1
    assert len(source.calls) == 1


def test_duplicate_signed_critical_event_joins_original_command():
    app, source, ledger = host("security/handler.py")
    status1, body1 = asyncio.run(deliver(app))
    status2, body2 = asyncio.run(deliver(app))
    assert status1 == 202 and body1["job_id"] == "JOB-1"
    assert status2 == 200 and body2["status"] == "ALREADY_ADMITTED", body2
    assert ledger.calls == 2 and len(ledger.jobs) == 1


def test_signed_standard_skips_before_job_admission():
    app, source, ledger = host("server/api/handler.py")
    status, body = asyncio.run(deliver(app))
    assert status == 200 and body["status"] == "SKIPPED_NOT_REQUIRED"
    assert ledger.jobs == {} and ledger.calls == 0
    assert len(source.calls) == 4
