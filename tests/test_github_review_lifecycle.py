"""Automatic PR events use the existing authenticated admission, not a new runner."""
import asyncio
import dataclasses
import json

import pytest

from control_plane import github_review_intent as core
from control_plane import github_review_intent_ingress as ingress
from control_plane.github_review_host_config import ReviewHostConfigError, ReviewHostSettings
from integrations.github_review_ingress_asgi import GitHubReviewReceiver

REPO = "example/repo"
HEAD = "a" * 40
BASE = "b" * 40
DELIVERY = "11111111-2222-3333-4444-555555555555"
SECRET = "test-only-review-signature"
ACTIONS = ("opened", "synchronize", "reopened", "ready_for_review")


def policy(**kwargs):
    values = dict(
        repositories=frozenset({REPO}), installation_ids=frozenset({4242}),
        configured_reviewer="reviewer", authorized_actors=frozenset({"alice"}),
        allow_lifecycle_review=True,
    )
    values.update(kwargs)
    return core.ReviewIntentPolicy(**values)


def facts(**kwargs):
    values = dict(
        repository=REPO, number=42, state="open", draft=False,
        head_sha=HEAD, base_sha=BASE, head_repository=REPO, base_repository=REPO,
        title="Correct stale result handling", body="Review the source and regression evidence.",
    )
    values.update(kwargs)
    return core.PullRequestFacts(**values)


def payload(action="opened", sender="alice", installation=4242):
    return json.dumps({
        "action": action, "installation": {"id": installation},
        "repository": {"full_name": REPO}, "number": 42,
        "pull_request": {
            "number": 42, "base": {"repo": {"full_name": REPO}},
            # Authorship is data, never request authority.
            "user": {"login": "dependabot[bot]"}, "head": {"sha": "d" * 40},
        },
        "sender": {"login": sender}, "label": {"name": "independent-review"},
    }).encode()


class Pulls:
    def __init__(self, current=None):
        self.current = current or facts()
        self.reads = 0

    def read_pull_request(self, *, repository, pull_number):
        assert (repository, pull_number) == (REPO, 42)
        self.reads += 1
        return self.current


class Actors:
    def __init__(self, permission="write"):
        self.permission = permission
        self.reads = 0

    def read_current_permission(self, *, repository, login):
        assert (repository, login) == (REPO, "alice")
        self.reads += 1
        return self.permission


class Fabric:
    """A port fixture; tests claiming durable dedupe use the real Runtime below."""
    def __init__(self):
        self.commands = set()
        self.reads = 0
        self.calls = 0

    def admitted_command_ids(self):
        self.reads += 1
        return frozenset(self.commands)

    def admit_review_intent(self, *, decision, objective):
        self.calls += 1
        self.commands.add(decision.command_id)
        assert decision.frozen_head_sha in objective
        return "job-review-fixture"


class Secrets:
    def webhook_secret(self, *, installation_id):
        assert installation_id == 4242
        return SECRET


def admit(*, body=None, selected_policy=None, pulls=None, actors=None, fabric=None):
    body = body or payload()
    return ingress.admit_review_intent(
        secret=SECRET, body=body, delivery_id=DELIVERY, event="pull_request",
        signature_header=core.sign_webhook_body(secret=SECRET, body=body),
        policy=selected_policy or policy(), pull_requests=pulls or Pulls(),
        actors=actors or Actors(), fabric=fabric or Fabric(),
    )


def settings(**kwargs):
    values = dict(
        enabled=True, publication_enabled=True, expected_host="review.example.com",
        require_https=True, installation_id=4242, installation_ids=frozenset({4242}),
        repositories=frozenset({REPO}), configured_reviewer="reviewer",
        authorized_actors=frozenset({"alice"}), allow_lifecycle_review=True,
    )
    values.update(kwargs)
    return ReviewHostSettings(**values)


def http(app, body, *, signature=None):
    responses = []

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message):
        responses.append(message)

    asyncio.run(app({
        "type": "http", "method": "POST", "scheme": "https",
        "path": app._settings.delivery_path, "query_string": b"",
        "headers": [
            (b"host", b"review.example.com"), (b"content-type", b"application/json"),
            (b"x-github-event", b"pull_request"),
            (b"x-github-delivery", DELIVERY.encode()),
            (b"x-hub-signature-256", (signature or core.sign_webhook_body(
                secret=SECRET, body=body)).encode()),
        ],
    }, receive, send))
    return responses[0]["status"], json.loads(responses[1]["body"])


@pytest.mark.parametrize("action", ACTIONS)
def test_lifecycle_default_off_has_no_authenticated_or_ledger_reads(action):
    pulls, actors, fabric = Pulls(), Actors(), Fabric()
    result = admit(body=payload(action), selected_policy=policy(allow_lifecycle_review=False),
                   pulls=pulls, actors=actors, fabric=fabric)
    assert result.decision.refusal is core.ReviewIntentRefusal.AUTOMATIC_REVIEW_DISABLED
    assert (pulls.reads, actors.reads, fabric.reads, fabric.calls) == (0, 0, 0, 0)


@pytest.mark.parametrize("action", ACTIONS)
def test_enabled_lifecycle_freezes_authoritative_head_not_webhook_head(action):
    result = admit(body=payload(action))
    assert result.state is ingress.AdmissionState.ADMITTED
    assert result.decision.intent_source is core.IntentSource.PR_LIFECYCLE
    assert result.decision.frozen_head_sha == HEAD  # payload carries a different SHA
    assert result.decision.actor == "alice"


@pytest.mark.parametrize("static_fallback", [False, True])
@pytest.mark.parametrize("permission", [None, "unexpected"])
def test_lifecycle_missing_permission_never_uses_static_fallback(static_fallback, permission):
    pulls, fabric = Pulls(), Fabric()
    result = admit(
        selected_policy=policy(allow_static_actor_authority=static_fallback),
        actors=Actors(permission), pulls=pulls, fabric=fabric,
    )
    assert result.decision.refusal is core.ReviewIntentRefusal.ACTOR_PERMISSION_NOT_REVERIFIED
    assert pulls.reads == fabric.reads == fabric.calls == 0


@pytest.mark.parametrize("permission", ["none", "read"])
def test_revoked_or_insufficient_actor_cannot_start_review(permission):
    fabric = Fabric()
    result = admit(actors=Actors(permission), fabric=fabric)
    assert result.decision.refusal is core.ReviewIntentRefusal.ACTOR_PERMISSION_INSUFFICIENT
    assert fabric.calls == 0


@pytest.mark.parametrize("current", [
    None,
    core.CurrentPermission(REPO, "mallory", "write"),
    core.CurrentPermission("other/repo", "alice", "write"),
])
def test_pure_decision_cannot_forge_lifecycle_permission_basis(current):
    body = json.loads(payload())
    envelope = core.parse_webhook_envelope(delivery_id=DELIVERY, event="pull_request", body=body)
    # A forged explicit-channel basis must not let a direct caller skip the read.
    signal = core.IntentSignal("alice", core.ActorPermissionBasis.GITHUB_ENFORCED_TRIAGE_WRITE)
    result = core.decide_review_intent(
        envelope=envelope, policy=policy(allow_static_actor_authority=True),
        pull_request=facts(), signal=signal, current_permission=current,
    )
    assert result.refusal is core.ReviewIntentRefusal.ACTOR_PERMISSION_NOT_REVERIFIED


@pytest.mark.parametrize("action", ACTIONS)
def test_automatic_drafts_defer_but_authorized_manual_advisory_stays_available(action):
    pulls = Pulls(facts(draft=True))
    result = admit(body=payload(action), pulls=pulls)
    assert result.decision.refusal is core.ReviewIntentRefusal.PULL_REQUEST_DRAFT
    manual = admit(body=payload("labeled"), pulls=pulls)
    assert manual.state is ingress.AdmissionState.ADMITTED


@pytest.mark.parametrize("change,reason", [
    ({"state": "closed"}, core.ReviewIntentRefusal.PULL_REQUEST_NOT_OPEN),
    ({"head_repository": "outsider/fork"}, core.ReviewIntentRefusal.HEAD_REPOSITORY_MISMATCH),
    ({"number": 43}, core.ReviewIntentRefusal.PULL_NUMBER_MISMATCH),
])
def test_lifecycle_does_not_relax_existing_source_fences(change, reason):
    fabric = Fabric()
    result = admit(pulls=Pulls(facts(**change)), fabric=fabric)
    assert result.decision.refusal is reason
    assert fabric.calls == 0


def test_unenrolled_installation_is_inert_before_external_reads():
    pulls, actors, fabric = Pulls(), Actors(), Fabric()
    result = admit(body=payload(installation=9999), pulls=pulls, actors=actors, fabric=fabric)
    assert result.decision.refusal is core.ReviewIntentRefusal.INSTALLATION_NOT_ALLOWLISTED
    assert pulls.reads == actors.reads == fabric.reads == fabric.calls == 0


@pytest.mark.parametrize("sender", ["mallory", "dependabot[bot]", "github-actions[bot]"])
def test_unlisted_sender_is_explicitly_classified_without_authority_or_reads(sender):
    pulls, actors, fabric = Pulls(), Actors(), Fabric()
    result = admit(body=payload(sender=sender), pulls=pulls, actors=actors, fabric=fabric)
    assert result.decision.refusal is core.ReviewIntentRefusal.ACTOR_NOT_AUTHORIZED
    assert pulls.reads == actors.reads == fabric.reads == fabric.calls == 0


def test_bot_observation_does_not_enlarge_authorized_principal_policy():
    with pytest.raises(core.ReviewIntentError):
        policy(authorized_actors=frozenset({"dependabot[bot]"}))


@pytest.mark.parametrize("value", [1, "true", None, [], {}])
def test_host_and_policy_flags_reject_truthy_or_malformed_values(value):
    with pytest.raises(core.ReviewIntentError):
        policy(allow_lifecycle_review=value)
    with pytest.raises(ReviewHostConfigError):
        settings(allow_lifecycle_review=value)


def test_host_projection_and_receipt_keep_the_explicit_flag():
    for value in (False, True):
        host = settings(allow_lifecycle_review=value)
        assert host.review_policy().allow_lifecycle_review is value
        assert host.to_dict()["allow_lifecycle_review"] is value


def test_http_reports_closed_refusal_reason_and_bad_signature_is_inert():
    pulls, actors, fabric = Pulls(), Actors(), Fabric()
    app = GitHubReviewReceiver(
        settings=settings(allow_lifecycle_review=False), secret_source=Secrets(),
        pull_requests=pulls, actors=actors, fabric=fabric,
    )
    status, result = http(app, payload())
    assert (status, result["status"], result["reason"]) == (
        200, "REFUSED", "AUTOMATIC_REVIEW_DISABLED",
    )
    assert http(app, payload(), signature="sha256=" + "0" * 64)[0] == 401
    assert pulls.reads == actors.reads == fabric.reads == fabric.calls == 0


def test_signed_http_lifecycle_and_manual_intents_share_real_runtime_identity(tmp_path):
    from control_plane.executive_runtime import Runtime
    from control_plane.github_review_runtime_adapter import ExecutiveReviewJobAdmission

    runtime = Runtime.at(tmp_path)
    fabric = ExecutiveReviewJobAdmission(runtime=runtime, admission_guard=lambda: None)
    pulls = Pulls()
    app = GitHubReviewReceiver(
        settings=settings(), secret_source=Secrets(), pull_requests=pulls,
        actors=Actors(), fabric=fabric,
    )
    assert http(app, payload("opened"))[0] == 202
    for action in ("synchronize", "reopened", "ready_for_review", "labeled"):
        status, result = http(app, payload(action))
        assert (status, result["status"]) == (200, "ALREADY_ADMITTED")
    jobs = runtime.jobs.list_jobs()
    assert len(jobs) == 1
    assert jobs[0].status.value == "QUEUED"
    assert jobs[0].requested_authorities == ["READ"]
    assert jobs[0].attempt_count == 0  # This test never claims provider START.

    pulls.current = dataclasses.replace(pulls.current, head_sha="c" * 40)
    assert http(app, payload("synchronize"))[0] == 202
    assert len(runtime.jobs.list_jobs()) == 2


def test_automatic_coverage_does_not_add_approval_or_merge():
    assert ingress.REVIEW_VERDICT_EVENTS["PASS"] == "COMMENT"
    assert "APPROVE" not in ingress.ALLOWED_REVIEW_EVENTS
