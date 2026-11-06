"""Existing transport, exact identity, complete pages and no delivery mutations."""
from copy import deepcopy

import httpx
import pytest

from control_plane.github_review_host_config import ReviewHostSettings
from integrations.github_pr_delivery_consumer import (
    GitHubPRDeliveryConsumer, GitHubPRDeliveryUnavailable,
)
from integrations.github_review_api import GitHubReviewAPI, GitHubReviewReadDeferred
from integrations.github_review_ingress_asgi import GitHubReviewReceiver, ReviewIngressUnavailable

REPO = "example/project"
HEAD, BASE = "a" * 40, "b" * 40


def source(**changes):
    p = dict(number=7, state="open", merged=False, draft=True,
        head={"sha": HEAD, "repo": {"full_name": REPO}},
        base={"sha": BASE, "repo": {"full_name": REPO}},
        changed_files=1, comments=0, review_comments=0,
        updated_at="2026-11-05T08:00:00Z", title="Change", body="",
        labels=[], auto_merge=None, mergeable_state="clean")
    p.update(changes)
    return p


class Tokens:
    def token_for_installation(self, *, installation_id):
        assert installation_id == 31
        return "nonproduction-test-token"


class SourceServer:
    def __init__(self, before=None, after=None):
        self.before = before or source()
        self.after = deepcopy(self.before) if after is None else after
        self.calls = []
        self.pr_reads = 0
        self.pages = {}
        self.hook = None

    def __call__(self, request):
        assert request.method == "GET"
        assert request.url.host == "api.github.com"
        assert request.headers["authorization"] == "Bearer nonproduction-test-token"
        path = request.url.path
        self.calls.append(str(request.url))
        assert path.startswith("/repos/" + REPO + "/")
        if self.hook:
            override = self.hook(request)
            if override is not None:
                return override
        page = int(request.url.params.get("page", "1"))
        if path == f"/repos/{REPO}/pulls/7":
            self.pr_reads += 1
            return httpx.Response(200, json=self.before if self.pr_reads == 1 else self.after)
        key = (path, page)
        if key in self.pages:
            return httpx.Response(200, json=self.pages[key])
        if path.endswith("/files"):
            result = [{"filename": "app.py"}]
        elif path.endswith("/check-runs"):
            assert request.url.params["filter"] == "latest"
            result = {"total_count": 1, "check_runs": [{"id": 3, "status": "completed",
                "head_sha": HEAD, "conclusion": "success", "app": {"id": 15368}}]}
        else:
            result = []
        return httpx.Response(200, json=result)


def consumer(server, **kwargs):
    api = GitHubReviewAPI(repository=REPO, installation_id=31, token_source=Tokens(),
        publisher_login="delivery-test", publisher_user_id=37,
        client=httpx.Client(transport=httpx.MockTransport(server)))
    kwargs.setdefault("ci_observations_enabled", True)
    return GitHubPRDeliveryConsumer(github=api, repository=REPO, **kwargs)


def settings(*, enabled=True, repository=REPO):
    return ReviewHostSettings(enabled=enabled, expected_host="review.example.com",
        require_https=True, installation_id=31, installation_ids=frozenset({31}),
        repositories=frozenset({repository}), configured_reviewer="reviewer",
        authorized_actors=frozenset({"alice"}))


def receiver(bound, *, enabled=True, guard=None):
    return GitHubReviewReceiver(
        settings=settings(enabled=enabled),
        secret_source=None, pull_requests=None, actors=None, fabric=None,
        reconciliation_guard=guard, delivery_consumer=bound,
    )


def test_live_adapter_uses_existing_transport_and_reads_head_again():
    server = SourceServer(); result = consumer(server).inspect(pull_number=7, expected_head_sha=HEAD)
    assert result["metadata_coverage_complete"]
    assert result["read_request_count"] == len(server.calls)
    assert server.pr_reads == 2
    assert result["release_authorized"] is False
    assert result["source_maturity"] == "NOT_INFERRED"


def test_expected_head_mismatch_stops_before_other_sources():
    server = SourceServer()
    with pytest.raises(GitHubPRDeliveryUnavailable, match="EXPECTED_HEAD_MOVED"):
        consumer(server).inspect(pull_number=7, expected_head_sha=BASE)
    assert len(server.calls) == 1


def test_complete_numeric_pagination_not_response_links():
    server = SourceServer(before=source(changed_files=101, comments=101))
    server.pages[(f"/repos/{REPO}/pulls/7/files", 1)] = [{"filename": f"src/f{i}.py"} for i in range(100)]
    server.pages[(f"/repos/{REPO}/pulls/7/files", 2)] = [{"filename": "src/f100.py"}]
    server.pages[(f"/repos/{REPO}/issues/7/comments", 1)] = [{"id": i + 1, "body": "ordinary"} for i in range(100)]
    server.pages[(f"/repos/{REPO}/issues/7/comments", 2)] = [{"id": 101, "body": "HOLD: do not merge"}]
    result = consumer(server).inspect(pull_number=7)
    assert result["metadata_coverage_complete"]
    assert result["content_footprint"]["executable_or_style_source"] == 101
    assert result["possible_restriction_refs"] == [f"https://github.com/{REPO}/pull/7#issuecomment-101"]
    assert result["next_action"] == "ADJUDICATE_RECORDED_RESTRICTIONS"
    assert all("page=" in x for x in server.calls if not x.endswith("/7"))


def test_page_cap_is_partial_not_silent_truncation():
    server = SourceServer(before=source(changed_files=101))
    server.pages[(f"/repos/{REPO}/pulls/7/files", 1)] = [{"filename": f"src/f{i}.py"} for i in range(100)]
    result = consumer(server).inspect(pull_number=7, max_pages=1)
    assert not result["metadata_coverage_complete"]
    assert not result["coverage"]["files"]
    assert result["next_action"] == "RECONCILE_OBSERVATION"


def test_changed_source_during_scan_invalidates_evidence():
    server = SourceServer(after=source(body="stay Draft"))
    result = consumer(server).inspect(pull_number=7)
    assert not result["source_stable"]
    assert result["next_action"] == "RECONCILE_OBSERVATION"


def test_full_body_is_not_truncated_to_review_excerpt_size():
    server = SourceServer(before=source(body="x" * 20000 + "\ndo not merge"))
    result = consumer(server).inspect(pull_number=7)
    assert result["possible_restriction_refs"]


def test_shared_rate_limit_stops_without_fallback_or_extra_calls():
    server = SourceServer()
    server.hook = lambda req: httpx.Response(429, headers={"retry-after": "10"}) if req.url.path.endswith("/files") else None
    with pytest.raises(GitHubReviewReadDeferred):
        consumer(server).inspect(pull_number=7)
    assert len(server.calls) == 2


def test_budget_exhaustion_stops_after_the_original_bounded_read():
    server = SourceServer(); clock = [0.0]
    def hook(request):
        if request.url.path.endswith("/files"):
            clock[0] = 5.0
    server.hook = hook
    with pytest.raises(GitHubPRDeliveryUnavailable, match="BUDGET_EXHAUSTED"):
        consumer(server, clock=lambda: clock[0]).inspect(pull_number=7, time_budget_seconds=5)
    assert len(server.calls) == 2


@pytest.mark.parametrize("kwargs", [
    {"max_pages": 0}, {"max_pages": 31}, {"max_pages": True},
    {"time_budget_seconds": float("nan")}, {"time_budget_seconds": float("inf")},
    {"time_budget_seconds": 0}, {"time_budget_seconds": 61},
    {"time_budget_seconds": True}, {"expected_head_sha": "bad"},
])
def test_invalid_bounds_do_not_touch_github(kwargs):
    server = SourceServer()
    with pytest.raises((ValueError, GitHubPRDeliveryUnavailable)):
        consumer(server).inspect(pull_number=7, **kwargs)
    assert not server.calls


def test_missing_existing_transport_is_refused():
    with pytest.raises(GitHubPRDeliveryUnavailable, match="OWNER_UNBOUND"):
        GitHubPRDeliveryConsumer(github=object(), repository=REPO)


def test_internal_host_consumer_runs_only_after_owner_guard():
    server = SourceServer(); seen = []
    host = receiver(consumer(server), guard=lambda ref: seen.append(ref))
    result = host.inspect_pull_request_delivery(owner_execution_ref="existing-owner-1", pull_number=7)
    assert seen == ["existing-owner-1"]
    assert result["head_sha"] == HEAD
    assert result["release_authorized"] is False


@pytest.mark.parametrize("enabled,guard,code", [
    (False, lambda _: None, "DISABLED"), (True, None, "OWNER_UNARMED"),
])
def test_unarmed_host_cannot_read(enabled, guard, code):
    server = SourceServer(); host = receiver(consumer(server), enabled=enabled, guard=guard)
    with pytest.raises(ReviewIngressUnavailable, match=code):
        host.inspect_pull_request_delivery(owner_execution_ref="owner-1", pull_number=7)
    assert not server.calls


def test_owner_denial_is_not_retried_or_converted_to_partial_success():
    server = SourceServer()
    def deny(ref):
        raise PermissionError("owner denied")
    host = receiver(consumer(server), guard=deny)
    with pytest.raises(PermissionError):
        host.inspect_pull_request_delivery(owner_execution_ref="owner-1", pull_number=7)
    assert not server.calls


def test_host_binding_cannot_mix_repositories():
    server = SourceServer(); bound = consumer(server)
    with pytest.raises(TypeError, match="enrolled"):
        GitHubReviewReceiver(settings=settings(repository="other/repo"),
            secret_source=None, pull_requests=None, actors=None, fabric=None,
            delivery_consumer=bound)


def test_default_host_permission_envelope_does_not_call_ci_routes():
    server = SourceServer()
    result = consumer(server, ci_observations_enabled=False).inspect(pull_number=7)
    assert result["source_record_coverage_complete"]
    assert not result["ci_observation_coverage_complete"]
    assert not result["metadata_coverage_complete"]
    assert result["ci_binding"] == "NOT_ENROLLED"
    assert all("/check-runs" not in path and "/statuses" not in path for path in server.calls)
    assert result["required_checks_satisfied"] is None
    assert result["release_authorized"] is False


@pytest.mark.parametrize("value", [False, True, "approved"])
def test_owner_guard_contract_cannot_silently_accept_boolean_or_prose(value):
    server = SourceServer(); host = receiver(consumer(server), guard=lambda _: value)
    with pytest.raises(ReviewIngressUnavailable, match="GUARD_INVALID_RETURN"):
        host.inspect_pull_request_delivery(owner_execution_ref="owner-1", pull_number=7)
    assert not server.calls
