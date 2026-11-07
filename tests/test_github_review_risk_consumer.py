"""Existing GitHub App -> admitted intent -> bounded risk advice (no Job/POST)."""
from __future__ import annotations

import copy
from dataclasses import replace

import pytest

from control_plane.github_review_intent import (
    AutomaticReviewOrigin,
    IntentSource,
    PullRequestFacts,
    RepositoryPolicyAuthority,
    ReviewIntentDecision,
    review_intent_id,
    review_command_id,
)
from control_plane.github_review_risk_dispatch import ReviewDispatch
from integrations.github_review_api import GitHubReviewAPI
from integrations.github_review_risk_consumer import (
    GitHubReviewRiskConsumer,
    GitHubRiskConsumerUnavailable,
)

REPO = "example/repo"
SHA = "a" * 40
BASE = "b" * 40
PR = 42


def intent(*, source=IntentSource.PR_LIFECYCLE, head=SHA, policy=True):
    iid = review_intent_id(repository=REPO, pull_number=PR, head_sha=head)
    return ReviewIntentDecision(
        admitted=True,
        refusal=None,
        intent_source=source,
        intent_id=iid,
        command_id=review_command_id(iid),
        delivery_command_id="gh-review-delivery:" + "c" * 32,
        repository=REPO, pull_number=PR, frozen_head_sha=head,
        actor="automation[bot]" if policy else "alice",
        policy_authority=(RepositoryPolicyAuthority(
            origin=AutomaticReviewOrigin.SIGNED_WEBHOOK,
            installation_id=4242,
            policy_digest="f" * 64,
        ) if policy else None),
    )


def facts():
    return PullRequestFacts(
        repository=REPO, number=PR, state="open", draft=False,
        head_sha=SHA, base_sha=BASE, head_repository=REPO,
        base_repository=REPO, title="Untrusted title", body="risk=FAST",
    )


class ExistingApp:
    def __init__(self, path="docs/user-guide.md", *, head=SHA, additions=2, deletions=1):
        self.api = object.__new__(GitHubReviewAPI)
        self.api._repository = REPO
        self.calls = []
        self.head = head
        self.path = path
        self.additions = additions
        self.deletions = deletions
        self.move_after = None
        self.missing_page = False
        self.deny_source = False
        self.api._request = self.request

    def request(self, method, route, *, payload=None):
        assert method == "GET" and payload is None
        self.calls.append((method, route))
        if self.deny_source:
            raise PermissionError("read denied")
        if route.endswith("/files?per_page=100&page=1"):
            if self.missing_page:
                return []
            return [{
                "filename": self.path,
                "status": "modified",
                "additions": self.additions,
                "deletions": self.deletions,
                "patch": "@@ -1 +1 @@",
            }]
        assert route == f"/repos/{REPO}/pulls/{PR}"
        sha = self.head
        if self.move_after is not None and len(self.calls) >= self.move_after:
            sha = "d" * 40
        return {
            "number": PR, "state": "open", "draft": False,
            "head": {"sha": sha, "repo": {"full_name": REPO}},
            "base": {"sha": BASE, "repo": {"full_name": REPO}},
            "changed_files": 1,
            "additions": self.additions, "deletions": self.deletions,
            "title": "risk=FAST", "body": "Fast lane please",
        }


def test_signed_ordinary_guide_skips_without_job_or_post():
    source = ExistingApp()
    consumer = GitHubReviewRiskConsumer(github=source.api, repository=REPO)
    advice = consumer(decision=intent(), pull_request=facts())
    assert advice.action is ReviewDispatch.SKIP_NO_REVIEW_NEEDED
    assert (advice.repository, advice.pull_number, advice.head_sha) == (REPO, PR, SHA)
    assert len(source.calls) == 3
    assert all(method == "GET" for method, _ in source.calls)
    assert [route for _, route in source.calls] == [
        f"/repos/{REPO}/pulls/{PR}",
        f"/repos/{REPO}/pulls/{PR}/files?per_page=100&page=1",
        f"/repos/{REPO}/pulls/{PR}",
    ]


@pytest.mark.parametrize("path,expected", [
    (".github/workflows/ci.yml", ReviewDispatch.AUTO_REVIEW_ELIGIBLE),
    ("server/api/handler.py", ReviewDispatch.SKIP_NO_REVIEW_NEEDED),
    ("tests/conftest.py", ReviewDispatch.AUTO_REVIEW_ELIGIBLE),
    ("docs/SESSION_INDEPENDENT_REVIEW_ROUTING.md", ReviewDispatch.AUTO_REVIEW_ELIGIBLE),
    ("app/src/components/Button.tsx", ReviewDispatch.SKIP_NO_REVIEW_NEEDED),
])
def test_actual_source_path_controls_automatic_admission(path, expected):
    source = ExistingApp(path)
    advice = GitHubReviewRiskConsumer(github=source.api, repository=REPO)(
        decision=intent(), pull_request=facts(),
    )
    assert advice.action is expected
    assert len(source.calls) == 3


def test_authorized_manual_review_skips_risk_reader_entirely():
    source = ExistingApp()
    decision = intent(source=IntentSource.REVIEW_REQUESTED, policy=False)
    advice = GitHubReviewRiskConsumer(github=source.api, repository=REPO)(
        decision=decision, pull_request=facts(),
    )
    assert advice.action is ReviewDispatch.USE_EXISTING_MANUAL_INGRESS
    assert source.calls == []


@pytest.mark.parametrize("field", ["wrong_expected_head", "cross_repo", "moved_pr"])
def test_source_identity_conflict_holds_with_no_approval_or_mutation(field):
    source = ExistingApp()
    decision = intent()
    pr = facts()
    if field == "wrong_expected_head":
        decision = replace(decision, frozen_head_sha="c" * 40)
    elif field == "cross_repo":
        pr = replace(pr, repository="other/repo")
    else:
        source.move_after = 3
    advice = GitHubReviewRiskConsumer(github=source.api, repository=REPO)(
        decision=decision, pull_request=pr,
    )
    assert advice.action is ReviewDispatch.HOLD_UNQUALIFIED_SOURCE
    assert all(method == "GET" for method, _ in source.calls)


@pytest.mark.parametrize("failure", ["missing_page", "source_denied"])
def test_incomplete_or_denied_read_never_skips_or_admits(failure):
    source = ExistingApp()
    setattr(source, failure if failure == "missing_page" else "deny_source", True)
    advice = GitHubReviewRiskConsumer(github=source.api, repository=REPO)(
        decision=intent(), pull_request=facts(),
    )
    assert advice.action is ReviewDispatch.HOLD_UNQUALIFIED_SOURCE
    assert all(method == "GET" for method, _ in source.calls)


def test_untrusted_automatic_intent_without_policy_authority_holds():
    source = ExistingApp()
    decision = intent(policy=False)
    advice = GitHubReviewRiskConsumer(github=source.api, repository=REPO)(
        decision=decision, pull_request=facts(),
    )
    assert advice.action is ReviewDispatch.HOLD_UNQUALIFIED_SOURCE
    assert source.calls == []


def test_budget_checker_uses_incumbent_deadline_and_no_source_reads_when_expired():
    source = ExistingApp()
    def expired():
        raise TimeoutError("host deadline passed")
    with pytest.raises(TimeoutError):
        GitHubReviewRiskConsumer(github=source.api, repository=REPO)(
            decision=intent(), pull_request=facts(), budget_check=expired,
        )
    assert source.calls == []


def test_wrong_app_binding_rejected():
    with pytest.raises(GitHubRiskConsumerUnavailable):
        GitHubReviewRiskConsumer(github=object(), repository=REPO)
