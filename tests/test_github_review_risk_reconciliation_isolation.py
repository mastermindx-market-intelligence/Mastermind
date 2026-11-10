"""A PR-local risk hold cannot starve unrelated review candidates."""
from __future__ import annotations

import json
import re

import pytest

from control_plane import github_review_intent_ingress as ingress
from control_plane.github_review_risk_dispatch import RiskDispatchAdvice, ReviewDispatch
from control_plane.github_review_risk_policy import ReviewTier
from integrations.github_review_api import GitHubReviewAPI
from integrations.github_review_risk_consumer import GitHubReviewRiskConsumer
from test_github_review_repository_policy import Pages, scan, REPO, HEAD
from test_github_review_risk_admission import Ledger


class AppSource:
    """Real reader/collector/consumer with an in-memory, credentialless GET port."""
    def __init__(self, fault="missing_page", affected=42):
        self.fault = fault
        self.affected = affected
        self.calls = []
        self.api = object.__new__(GitHubReviewAPI)
        self.api._repository = REPO
        self.api._request = self.request

    def request(self, method, route, *, payload=None):
        assert method == "GET" and payload is None
        match = re.fullmatch(r"/repos/" + re.escape(REPO) + r"/pulls/(\d+)(/files\?per_page=100&page=1)?", route)
        assert match, route
        number = int(match.group(1))
        files = bool(match.group(2))
        self.calls.append((number, files))
        fault = self.fault if number == self.affected else None
        if fault == "permission":
            raise PermissionError("PR_SOURCE_PAGINATION_INCOMPLETE")
        if fault == "unknown":
            raise RuntimeError("PR_SOURCE_PAGINATION_INCOMPLETE")
        if files:
            if fault == "missing_page":
                return []
            return [{
                "filename": "security/handler.py", "status": "modified",
                "additions": 1, "deletions": 0,
                **({} if fault == "missing_patch" else {"patch": "@@ -1 +1 @@"}),
            }]
        reads = sum(n == number and not f for n, f in self.calls)
        sha = "c" * 40 if fault == "moved_during" and reads >= 2 else HEAD
        return {
            "number": number + 1 if fault == "identity" else number,
            "state": "closed" if fault == "closed" else "open", "draft": False,
            "head": {"sha": sha, "repo": {"full_name": REPO}},
            "base": {"sha": "b" * 40, "repo": {"full_name": REPO}},
            "changed_files": 257 if fault == "oversized" else 1,
            "additions": 1, "deletions": 0,
        }

    def gate(self):
        return GitHubReviewRiskConsumer(github=self.api, repository=REPO)


def pages(numbers=(42, 43)):
    return Pages({1: ingress.OpenPullRequestPage(numbers, False)})


def read_numbers(pulls):
    return [call[-1] for call in pulls.calls if call[0] == "read"]


@pytest.mark.parametrize("fault", [
    "missing_page", "missing_patch", "moved_during", "oversized", "closed",
])
def test_local_risk_failure_does_not_starve_the_next_pr(fault):
    source, pulls, ledger = AppSource(fault), pages(), Ledger()
    result = scan(pulls, ledger, review_risk_gate=source.gate())
    assert read_numbers(pulls) == [42, 43]
    assert ledger.calls == 1 and len(ledger.jobs) == 1
    assert [outcome.decision.pull_number for outcome in result.outcomes] == [43]
    assert result.complete and not result.all_sources_observed
    assert result.interruption is None
    assert [(failure.page, failure.pull_number) for failure in result.read_failures] == [(1, 42)]
    assert result.to_dict()["retry_read_pages"] == [1]
    assert all(number != 42 for _, decision in ledger.jobs.values() for number in [decision.pull_number])


@pytest.mark.parametrize("fault", ["permission", "unknown", "identity"])
def test_shared_or_unclassified_failure_still_stops_the_scan(fault):
    source, pulls, ledger = AppSource(fault), pages(), Ledger()
    result = scan(pulls, ledger, review_risk_gate=source.gate())
    assert read_numbers(pulls) == [42]
    assert ledger.calls == 0 and ledger.jobs == {}
    assert result.interruption == "REVIEW_RECONCILIATION_RISK_HOLD"
    assert not result.complete and result.read_failures == ()
    assert "PR_SOURCE_PAGINATION_INCOMPLETE" not in json.dumps(result.to_dict())


@pytest.mark.parametrize("reason", [
    "UNRECOGNIZED", "CURRENT_AUTHENTICATED_SOURCE_UNAVAILABLE",
    "SIGNED_EXACT_HEAD_OR_PR_IDENTITY_MISMATCH", "REVIEW_RISK_POLICY_AUTHORITY_MISSING",
])
def test_reason_classification_is_closed_and_does_not_relax_identity(reason):
    pulls, ledger = pages(), Ledger()
    def gate(**_):
        return RiskDispatchAdvice(ReviewDispatch.HOLD_UNQUALIFIED_SOURCE, None, reason)
    result = scan(pulls, ledger, review_risk_gate=gate)
    assert result.interruption == "REVIEW_RECONCILIATION_RISK_HOLD"
    assert read_numbers(pulls) == [42] and ledger.calls == 0


def test_owner_revocation_during_local_hold_prevents_the_next_source_read():
    source, pulls, ledger = AppSource(), pages(), Ledger()
    allowed = [True]
    real_gate = source.gate()
    def gate(**kwargs):
        advice = real_gate(**kwargs)
        allowed[0] = False
        return advice
    result = scan(pulls, ledger, review_risk_gate=gate,
                  authorize=lambda _: None if allowed[0] else False)
    assert result.interruption == "REVIEW_RECONCILIATION_OWNER_UNARMED"
    assert read_numbers(pulls) == [42] and ledger.calls == 0
    assert [(f.page, f.pull_number) for f in result.read_failures] == [(1, 42)]


def test_local_hold_consumes_the_original_time_budget():
    source, pulls, ledger = AppSource(), pages(), Ledger()
    now = [0.0]
    real_gate = source.gate()
    def gate(**kwargs):
        advice = real_gate(**kwargs)
        now[0] = 2.0
        return advice
    result = scan(pulls, ledger, review_risk_gate=gate,
                  clock=lambda: now[0], time_budget_seconds=1)
    assert result.interruption == "REVIEW_RECONCILIATION_BUDGET_EXHAUSTED"
    assert read_numbers(pulls) == [42] and ledger.calls == 0
    assert result.elapsed_seconds == 2.0


def test_final_page_hold_preserves_prior_admission_and_incomplete_coverage():
    source, pulls, ledger = AppSource(affected=43), pages(), Ledger()
    result = scan(pulls, ledger, review_risk_gate=source.gate())
    assert result.complete and result.next_page is None
    assert not result.all_sources_observed
    assert [outcome.decision.pull_number for outcome in result.outcomes] == [42]
    assert [(f.page, f.pull_number) for f in result.read_failures] == [(1, 43)]
    assert ledger.calls == 1


def test_existing_admission_is_not_duplicated_after_a_local_hold():
    source, ledger = AppSource(), Ledger()
    first = scan(pages(), ledger, review_risk_gate=source.gate())
    second = scan(pages(), ledger, review_risk_gate=source.gate())
    assert first.outcomes[0].state is ingress.AdmissionState.ADMITTED
    assert second.outcomes[0].state is ingress.AdmissionState.ALREADY_ADMITTED
    assert first.outcomes[0].job_id == second.outcomes[0].job_id
    assert len(ledger.jobs) == 1


def test_admission_exception_cannot_impersonate_a_pre_effect_local_hold():
    source, pulls = AppSource(fault=None), pages()
    class UncertainLedger(Ledger):
        def admit_or_join_review_intent(self, **kwargs):
            super().admit_or_join_review_intent(**kwargs)
            raise ingress.ReviewRiskSourceUnqualified(
                "REVIEW_RISK_SOURCE_UNQUALIFIED",
                source_reason="PR_SOURCE_PAGINATION_INCOMPLETE",
            )
    ledger = UncertainLedger()
    result = scan(pulls, ledger, review_risk_gate=source.gate())
    assert result.interruption == "REVIEW_RECONCILIATION_ADMISSION_UNRECONCILED"
    assert read_numbers(pulls) == [42] and ledger.calls == 1
    assert len(ledger.jobs) == 1 and result.read_failures == ()


def test_mixed_local_success_global_failure_keeps_only_the_known_success():
    source, pulls, ledger = AppSource(), pages((42, 43, 44, 45)), Ledger()
    real_gate = source.gate()
    def gate(**kwargs):
        if kwargs["decision"].pull_number == 44:
            return RiskDispatchAdvice(ReviewDispatch.HOLD_UNQUALIFIED_SOURCE, None,
                                      "CURRENT_AUTHENTICATED_SOURCE_UNAVAILABLE")
        return real_gate(**kwargs)
    result = scan(pulls, ledger, review_risk_gate=gate, per_page=4)
    assert read_numbers(pulls) == [42, 43, 44]
    assert [outcome.decision.pull_number for outcome in result.outcomes] == [43]
    assert result.interruption == "REVIEW_RECONCILIATION_RISK_HOLD"
    assert result.interrupted_pull_number == 44
    assert len(ledger.jobs) == 1 and ledger.calls == 1


def test_all_local_holds_finish_enumeration_without_claiming_coverage():
    pulls, ledger = pages(), Ledger()
    def gate(**_):
        return RiskDispatchAdvice(ReviewDispatch.HOLD_UNQUALIFIED_SOURCE, ReviewTier.HOLD,
                                  "CURRENT_SOURCE_INCOMPLETE")
    result = scan(pulls, ledger, review_risk_gate=gate)
    assert result.complete and not result.all_sources_observed
    assert read_numbers(pulls) == [42, 43] and ledger.calls == 0
    assert [f.pull_number for f in result.read_failures] == [42, 43]


def test_owner_revocation_after_qualified_preflight_prevents_admission():
    source, pulls, ledger = AppSource(fault=None), pages(), Ledger()
    allowed = [True]
    real_gate = source.gate()
    def gate(**kwargs):
        advice = real_gate(**kwargs)
        allowed[0] = False
        return advice
    result = scan(pulls, ledger, review_risk_gate=gate,
                  authorize=lambda _: None if allowed[0] else False)
    assert result.interruption == "REVIEW_RECONCILIATION_ADMISSION_UNRECONCILED"
    assert read_numbers(pulls) == [42]
    assert ledger.calls == 0 and ledger.jobs == {}
    assert not result.complete and result.read_failures == ()


@pytest.mark.parametrize("max_pages", [1, 2])
def test_local_hold_continues_only_within_the_original_page_budget(max_pages):
    source, ledger = AppSource(), Ledger()
    pulls = Pages({
        1: ingress.OpenPullRequestPage((42,), True),
        2: ingress.OpenPullRequestPage((43,), False),
    })
    result = scan(pulls, ledger, review_risk_gate=source.gate(),
                  per_page=1, max_pages=max_pages)
    assert result.pages_read == max_pages
    assert [(f.page, f.pull_number) for f in result.read_failures] == [(1, 42)]
    assert not result.all_sources_observed
    if max_pages == 1:
        assert read_numbers(pulls) == [42]
        assert not result.complete and result.next_page == 2
        assert ledger.calls == 0 and ledger.jobs == {}
    else:
        assert read_numbers(pulls) == [42, 43]
        assert result.complete and result.next_page is None
        assert ledger.calls == 1 and len(ledger.jobs) == 1
        assert [o.decision.pull_number for o in result.outcomes] == [43]
