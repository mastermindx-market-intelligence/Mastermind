"""Hermetic existing-GitHub-App reader -> risk -> pre-admission contract."""
from __future__ import annotations

from copy import deepcopy

import pytest

from control_plane.github_review_risk_dispatch import (
    ReviewDispatch, ReviewOrigin, decide_risk_dispatch,
    advise_current_pr_review,
)
from control_plane.github_review_risk_policy import ReviewTier
from control_plane.github_review_risk_source import (
    RiskSourceUnavailable, assess_current_pr_risk,
)
from integrations.github_review_api import GitHubReviewAPI
from integrations.github_review_risk_reader import (
    GitHubReviewRiskReader, GitHubReviewRiskReadUnavailable,
)

REPO = "mastermindx-market-intelligence/Mastermind"
SHA = "a" * 40
BASE = "b" * 40
PR = 1989


def pull(*, path="docs/guide.md", changed_files=1, additions=3, deletions=1):
    return {
        "number": PR, "state": "open", "draft": False,
        "head": {"sha": SHA, "repo": {"full_name": REPO}},
        "base": {"sha": BASE, "repo": {"full_name": REPO}},
        "changed_files": changed_files,
        "additions": additions, "deletions": deletions,
        "title": "Untrusted title ignored",
        "body": "risk=FAST (PR text is not authorization)",
    }


def file(path="docs/guide.md", *, additions=3, deletions=1, status="modified",
         patch="@@ -1 +1 @@"):
    return {
        "filename": path, "additions": additions, "deletions": deletions,
        "status": status, **({"patch": patch} if patch is not None else {}),
    }


class ApiFixture:
    def __init__(self, snapshot=None, files=None, *, snapshot_after=None):
        self.snapshot = snapshot if snapshot is not None else pull()
        self.snapshot_after = snapshot_after
        self.files = files if files is not None else [file()]
        self.calls = []
        self.pr_calls = 0
        self.api = object.__new__(GitHubReviewAPI)
        self.api._repository = REPO
        self.api._request = self.request
        self.reader = GitHubReviewRiskReader(api=self.api, repository=REPO)

    def request(self, method, route, *, payload=None):
        self.calls.append((method, route))
        assert method == "GET" and payload is None
        if "/files?" in route:
            assert route == f"/repos/{REPO}/pulls/{PR}/files?per_page=100&page=1"
            return deepcopy(self.files)
        assert route == f"/repos/{REPO}/pulls/{PR}"
        self.pr_calls += 1
        if self.pr_calls > 1 and self.snapshot_after is not None:
            return deepcopy(self.snapshot_after)
        return deepcopy(self.snapshot)


def assess(fixture):
    return assess_current_pr_risk(fixture.reader, repository=REPO, pull_number=PR)


def auto_decide(fixture, assessment):
    return decide_risk_dispatch(
        origin=ReviewOrigin.AUTOMATIC_POLICY, assessment=assessment,
        expected_repository=REPO, expected_pull_number=PR,
        expected_head_sha=SHA,
        current_source=fixture.reader.read_pr_risk_source(
            repository=REPO, pull_number=PR,
        ),
    )


def test_full_existing_api_bridge_skips_plain_docs_before_dispatch():
    fixture = ApiFixture()
    risk = assess(fixture)
    result = auto_decide(fixture, risk)
    assert risk.tier is ReviewTier.FAST
    assert result.action is ReviewDispatch.SKIP_NO_REVIEW_NEEDED
    assert len(fixture.calls) == 4


def test_auth_change_is_critical_even_when_pr_claims_fast():
    fixture = ApiFixture(files=[file("backend/auth/session.py")])
    risk = assess(fixture)
    assert risk.tier is ReviewTier.CRITICAL
    assert auto_decide(fixture, risk).action is ReviewDispatch.AUTO_REVIEW_ELIGIBLE


def test_manual_intent_is_unaffected_even_when_source_is_fast():
    fixture = ApiFixture()
    assert decide_risk_dispatch(
        origin=ReviewOrigin.MANUAL_AUTHORIZED, assessment=assess(fixture),
    ).action is ReviewDispatch.USE_EXISTING_MANUAL_INGRESS


def test_pr_head_movement_during_file_read_refuses_fast_lane():
    newer = pull()
    newer["head"]["sha"] = "c" * 40
    fixture = ApiFixture(snapshot_after=newer)
    with pytest.raises(RiskSourceUnavailable, match="MOVED"):
        assess(fixture)


@pytest.mark.parametrize("mismatch", [
    {"changed_files": 2},
    {"additions": 4},
    {"deletions": 0},
])
def test_source_file_coverage_or_totals_drift_refuses(mismatch):
    snapshot = pull()
    snapshot.update(mismatch)
    fixture = ApiFixture(snapshot=snapshot)
    with pytest.raises(RiskSourceUnavailable):
        assess(fixture)


def test_unavailable_code_patch_refuses_fast_lane():
    fixture = ApiFixture(files=[file("app/src/dashboard.tsx", patch=None)])
    with pytest.raises(RiskSourceUnavailable, match="PATCH"):
        assess(fixture)


def test_binary_evidence_allowed_without_patch():
    fixture = ApiFixture(
        snapshot=pull(additions=0, deletions=0),
        files=[file("docs/screenshot.png", additions=0, deletions=0, patch=None)],
    )
    assert assess(fixture).tier is ReviewTier.FAST


def test_source_repo_mismatch_refuses():
    snapshot = pull()
    snapshot["head"]["repo"]["full_name"] = "attacker/fork"
    with pytest.raises(RiskSourceUnavailable, match="REPOSITORY"):
        assess(ApiFixture(snapshot=snapshot))


@pytest.mark.parametrize("change", [
    {"number": 1988}, {"draft": "false"}, {"state": "unknown"},
    {"changed_files": True}, {"additions": -1},
    {"head": {"sha": SHA, "repo": {}}},
])
def test_malformed_rest_snapshot_refuses(change):
    snapshot = pull()
    snapshot.update(change)
    with pytest.raises((RiskSourceUnavailable, GitHubReviewRiskReadUnavailable)):
        assess(ApiFixture(snapshot=snapshot))


@pytest.mark.parametrize("rows", [
    "not a list", [{}], [file(status=42)],
    [file(additions="3")], [file(patch=123)], [file(path="")],
])
def test_invalid_rest_files_refuse(rows):
    with pytest.raises((RiskSourceUnavailable, GitHubReviewRiskReadUnavailable)):
        assess(ApiFixture(files=rows))


def test_null_rest_file_response_refused():
    fixture = ApiFixture()
    fixture.files = None
    with pytest.raises(GitHubReviewRiskReadUnavailable):
        assess(fixture)


def test_wrong_repository_or_non_int_pr_cannot_issue_any_get():
    fixture = ApiFixture()
    for repo, num in [("not/this", PR), (REPO, "1989"), (REPO, True)]:
        with pytest.raises((GitHubReviewRiskReadUnavailable, ValueError)):
            fixture.reader.read_pr_risk_source(repository=repo, pull_number=num)
    assert fixture.calls == []


@pytest.mark.parametrize("page,per_page", [(0, 100), (4, 100), (1, 200), (True, 100)])
def test_file_page_cannot_expand_scope(page, per_page):
    fixture = ApiFixture()
    with pytest.raises(GitHubReviewRiskReadUnavailable):
        fixture.reader.read_pr_risk_file_page(
            repository=REPO, pull_number=PR, page=page, per_page=per_page,
        )
    assert fixture.calls == []


def test_non_app_fake_reader_refused():
    with pytest.raises(GitHubReviewRiskReadUnavailable):
        GitHubReviewRiskReader(api=object(), repository=REPO)


def test_full_signed_current_head_preflight_uses_three_authenticated_gets():
    fixture = ApiFixture()
    advice = advise_current_pr_review(
        fixture.reader, origin=ReviewOrigin.AUTOMATIC_POLICY,
        repository=REPO, pull_number=PR, signed_head_sha=SHA,
    )
    assert advice.action is ReviewDispatch.SKIP_NO_REVIEW_NEEDED
    assert advice.head_sha == SHA
    assert len(fixture.calls) == 3
    assert fixture.calls[0][1].endswith("/pulls/1989")
    assert fixture.calls[1][1].endswith("/files?per_page=100&page=1")
    assert fixture.calls[2][1].endswith("/pulls/1989")


def test_changed_head_after_completed_census_fails_closed():
    fixture = ApiFixture()
    assessment = assess(fixture)
    fixture.snapshot["head"]["sha"] = "c" * 40
    assert auto_decide(fixture, assessment).action is ReviewDispatch.HOLD_UNQUALIFIED_SOURCE


def test_signed_event_head_mismatch_after_complete_github_census_holds():
    fixture = ApiFixture()
    advice = advise_current_pr_review(
        fixture.reader, origin=ReviewOrigin.AUTOMATIC_POLICY,
        repository=REPO, pull_number=PR, signed_head_sha="c" * 40,
    )
    assert advice.action is ReviewDispatch.HOLD_UNQUALIFIED_SOURCE


@pytest.mark.parametrize("path,tier", [
    ("docs/SOL_CEO_ACCOUNT_INSTRUCTIONS.md", ReviewTier.CRITICAL),
    ("docs/SESSION_INDEPENDENT_REVIEW_ROUTING.md", ReviewTier.CRITICAL),
    ("docs/EXECUTIVE_WEB_SOL_CONTEXT_ROTATION_LAW.md", ReviewTier.CRITICAL),
    ("tests/conftest.py", ReviewTier.CRITICAL),
    ("skills/mastermind-fabric-delegate/SKILL.md", ReviewTier.CRITICAL),
    ("app/src/lib/session_client.ts", ReviewTier.STANDARD),
    ("app/src/components/Button.tsx", ReviewTier.STANDARD),
    ("terminal/components/ChartPanel.tsx", ReviewTier.STANDARD),
    ("docs/guides/AGENTS.md", ReviewTier.CRITICAL),
    ("docs/verification/CLAUDE.md", ReviewTier.CRITICAL),
    ("terminal/assets/icon.svg", ReviewTier.STANDARD),
    ("docs/user-guide.md", ReviewTier.FAST),
])
def test_real_reviewer_falsifiers_through_signed_reader_and_dispatch(path, tier):
    fixture = ApiFixture(
        snapshot=pull(additions=1, deletions=1),
        files=[file(path, additions=1, deletions=1)],
    )
    assessment = assess(fixture)
    assert assessment.tier is tier
    advice = auto_decide(fixture, assessment)
    expected = (ReviewDispatch.SKIP_NO_REVIEW_NEEDED if tier in (ReviewTier.FAST, ReviewTier.STANDARD)
                else ReviewDispatch.AUTO_REVIEW_ELIGIBLE)
    assert advice.action is expected
    assert advice.source_tier is tier


def test_explicit_manual_review_skips_risk_preflight_and_keeps_original_route():
    fixture = ApiFixture()
    advice = advise_current_pr_review(
        fixture.reader, origin=ReviewOrigin.MANUAL_AUTHORIZED,
        repository=REPO, pull_number=PR, signed_head_sha=SHA,
    )
    assert advice.action is ReviewDispatch.USE_EXISTING_MANUAL_INGRESS
    assert fixture.calls == []
