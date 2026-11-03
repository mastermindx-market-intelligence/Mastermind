"""Risk-tier review relief: adversarial, no-IO qualification tests."""
from dataclasses import replace

import pytest

from control_plane.github_review_risk_policy import (
    ReviewChangeFacts,
    ReviewTier,
    RiskPolicyInputError,
    assess_review_risk,
)

HEAD = "a" * 40


def facts(paths=("app/src/component.tsx",), *, additions=12, deletions=4,
          complete_source_verified=True, risk_hints=()):
    return ReviewChangeFacts(
        repository="mastermindx-market-intelligence/Mastermind",
        pull_number=137,
        head_sha=HEAD,
        changed_paths=paths,
        additions=additions,
        deletions=deletions,
        complete_source_verified=complete_source_verified,
        risk_hints=risk_hints,
    )


@pytest.mark.parametrize("paths", [
    ("docs/user-guide.md",),
    ("README.md", "docs/screenshots/welcome.png"),
    ("app/src/component.tsx",),
    ("tests/test_model.py",),
])
def test_bounded_routine_changes_need_no_independent_review(paths):
    decision = assess_review_risk(facts(paths))
    assert decision.tier is ReviewTier.FAST
    assert decision.fast_lane_candidate is True
    assert decision.minimum_independent_assessments == 0
    assert decision.minimum_formal_non_author_approvals == 0


@pytest.mark.parametrize("paths", [
    (".github/workflows/ci.yml",),
    ("docs/sol_skills/INDEX.md",),
    ("docs/DELIVERY_WORKFLOW.md",),
    ("docs/REVIEW_RISK_POLICY.md",),
    ("config/authority_map.yml",),
    ("control_plane/github_review_intent.py",),
    ("integrations/github_review_api.py",),
    ("app/security/token.py",),
    ("backend/oauth/refresh.py",),
    ("backend/auth.py",),
    ("db/migrations/2026_nov.sql",),
    ("trading/strategy.py",),
    ("scripts/deploy_from_git.sh",),
    ("AGENTS.md",),
])
def test_small_sensitive_changes_never_use_fast_lane(paths):
    decision = assess_review_risk(facts(paths, additions=1, deletions=0))
    assert decision.tier is ReviewTier.CRITICAL
    assert decision.minimum_independent_assessments == 2
    assert decision.minimum_formal_non_author_approvals == 1
    assert not decision.fast_lane_candidate


@pytest.mark.parametrize("paths", [
    ("control_plane/executive_coo_policy.py",),
    ("brain/macro_models.py",),
    ("server/handler.py",),
    ("package-lock.json",),
    ("backend/schema/price.ts",),
])
def test_consequential_code_gets_one_review(paths):
    decision = assess_review_risk(facts(paths))
    assert decision.tier is ReviewTier.STANDARD
    assert decision.minimum_independent_assessments == 1
    assert decision.minimum_formal_non_author_approvals == 1


def test_large_unremarkable_diff_gets_one_review():
    assert assess_review_risk(facts(additions=201, deletions=0)).tier is ReviewTier.STANDARD


def test_many_small_paths_get_one_review():
    assert assess_review_risk(facts(tuple(f"ui/panel{i}.tsx" for i in range(9)))).tier is ReviewTier.STANDARD


def test_test_only_large_deletion_gets_one_review():
    assert assess_review_risk(facts(("tests/test_component.py",), additions=1, deletions=51)).tier is ReviewTier.STANDARD


def test_smaller_test_cleanup_stays_fast():
    assert assess_review_risk(facts(("tests/test_component.py",), additions=1, deletions=49)).tier is ReviewTier.FAST


@pytest.mark.parametrize("hint,expected", [
    ("cross_service", ReviewTier.STANDARD),
    ("data_contract", ReviewTier.STANDARD),
    ("auth", ReviewTier.CRITICAL),
    ("financial_execution", ReviewTier.CRITICAL),
    ("review_policy", ReviewTier.CRITICAL),
])
def test_trusted_hints_only_escalate(hint, expected):
    assert assess_review_risk(facts(risk_hints=(hint,))).tier is expected


def test_unverified_diff_holds_even_tiny_docs():
    result = assess_review_risk(facts(("docs/intro.md",), additions=1, deletions=0, complete_source_verified=False))
    assert result.tier is ReviewTier.HOLD
    assert not result.fast_lane_candidate


def test_empty_diff_holds():
    assert assess_review_risk(facts(())).tier is ReviewTier.HOLD


def test_function_is_pure_and_deterministic():
    snapshot = facts(("ui/src/panel.tsx",), additions=40, deletions=30)
    assert assess_review_risk(snapshot) == assess_review_risk(snapshot)


@pytest.mark.parametrize("tamper", [
    {"head_sha": "abc"},
    {"head_sha": "A" * 40},
    {"pull_number": True},
    {"complete_source_verified": 1},
    {"additions": True},
    {"deletions": -1},
    {"changed_paths": ["docs/help.md"]},
    {"changed_paths": ("../docs/help.md",)},
    {"changed_paths": ("docs//help.md",)},
    {"changed_paths": ("/docs/help.md",)},
    {"changed_paths": ("docs\\help.md",)},
    {"changed_paths": ("docs/help.md", "docs/HELP.md")},
    {"risk_hints": ("trusted_low_risk",)},
    {"risk_hints": ("auth", "auth")},
    {"repository": "wrong-name"},
])
def test_malformed_or_untrusted_inputs_never_produce_exemption(tamper):
    with pytest.raises(RiskPolicyInputError):
        assess_review_risk(replace(facts(), **tamper))
