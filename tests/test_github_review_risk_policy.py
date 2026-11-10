"""Risk-tier review relief: adversarial, no-IO qualification tests."""
from dataclasses import replace

import pytest

from control_plane.github_review_risk_policy import (
    ReviewChangeFacts,
    ReviewFileStat,
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
    ("docs/evidence/2026-11-02-github-release-triage.md",),
    ("docs/superpowers/plans/2026-10-22-reconciliation.md",),
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
    ("tests/conftest.py",),
    ("tests/test_ci_pytest_policy.py",),
    ("control_plane/executive_coo_policy.py",),
    ("control_plane/executive_workspace.py",),
    ("control_plane/executive_service.py",),
    ("scripts/mastermind_workspace.py",),
    ("integrations/studio_direct_mcp/git-publish.mjs",),
    ("config/unrun_test_waivers.yml",),
    ("skills/mastermind-fabric-delegate/SKILL.md",),
    ("plugins/mastermind-sol/skills/review-pull-request/SKILL.md",),
    ("pytest.ini",),
])
def test_small_sensitive_changes_keep_machine_critical_risk(paths):
    decision = assess_review_risk(facts(paths, additions=1, deletions=0))
    assert decision.tier is ReviewTier.CRITICAL
    assert decision.minimum_independent_assessments == 1
    assert decision.minimum_formal_non_author_approvals == 0
    assert not decision.fast_lane_candidate


@pytest.mark.parametrize("paths", [
    ("brain/risk/macro_models.py",),
    ("server/schema/handler.py",),
    ("app/src/portfolio/position.ts",),
    ("package-lock.json",),
    ("backend/schema/price.ts",),
    ("control_plane/ordinary_worker.py",),
    ("integrations/external_client.py",),
])
def test_consequential_code_keeps_machine_standard_risk(paths):
    decision = assess_review_risk(facts(paths))
    assert decision.tier is ReviewTier.STANDARD
    assert decision.minimum_independent_assessments == 0
    assert decision.minimum_formal_non_author_approvals == 0


def test_large_unremarkable_diff_gets_one_review():
    assert assess_review_risk(facts(additions=2401, deletions=0)).tier is ReviewTier.STANDARD


def test_many_small_paths_get_one_review():
    assert assess_review_risk(facts(tuple(f"ui/panel{i}.tsx" for i in range(41)))).tier is ReviewTier.STANDARD


def test_test_only_large_deletion_gets_one_review():
    assert assess_review_risk(facts(("tests/test_component.py",), additions=1, deletions=51)).tier is ReviewTier.STANDARD


def test_smaller_test_cleanup_keeps_smoke_ci():
    assert assess_review_risk(facts(("tests/test_component.py",), additions=1, deletions=49)).tier is ReviewTier.STANDARD


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



def test_authenticated_file_metrics_cannot_omit_changed_source():
    incomplete = replace(
        facts(("docs/proof.md", "app/src/panel.tsx"), additions=10, deletions=0),
        file_metrics=(ReviewFileStat(path="docs/proof.md", additions=10, deletions=0),),
    )
    with pytest.raises(RiskPolicyInputError, match="omit source paths"):
        assess_review_risk(incomplete)


def test_source_metric_aggregate_mismatch_refused():
    tampered = replace(
        facts(("docs/help.md",), additions=10, deletions=0),
        file_metrics=(ReviewFileStat(path="docs/help.md", additions=1, deletions=0),),
    )
    with pytest.raises(RiskPolicyInputError, match="authenticated aggregate"):
        assess_review_risk(tampered)


def test_previous_rename_path_is_accounted_for_in_verified_metrics():
    source = replace(
        facts(("docs/verification/now.md", "backend/auth.py"), additions=1, deletions=0),
        file_metrics=(ReviewFileStat(
            path="docs/verification/now.md", previous_path="backend/auth.py",
            additions=1, deletions=0,
        ),),
    )
    assert assess_review_risk(source).tier is ReviewTier.CRITICAL


def test_bounded_ui_executable_change_keeps_smoke_with_large_verification_evidence():
    source = replace(
        facts(("terminal/components/ChartPanel.tsx", "terminal/docs/verification/replay.log"),
              additions=900, deletions=3),
        file_metrics=(
            ReviewFileStat(path="terminal/components/ChartPanel.tsx", additions=20, deletions=3),
            ReviewFileStat(path="terminal/docs/verification/replay.log", additions=880, deletions=0),
        ),
    )
    assert assess_review_risk(source).tier is ReviewTier.STANDARD


@pytest.mark.parametrize("protected_path", [
    "tests/conftest.py",
    "tests/test_ci_pytest_policy.py",
    "skills/mastermind-fabric-delegate/SKILL.md",
    "plugins/mastermind-sol/skills/review-pull-request/SKILL.md",
    "config/unrun_test_waivers.yml",
    "app/src/components/ci_policy.tsx",
])
def test_verified_one_line_policy_and_test_gate_changes_never_fast(protected_path):
    source = replace(
        facts((protected_path,), additions=1, deletions=1),
        file_metrics=(ReviewFileStat(
            path=protected_path, additions=1, deletions=1
        ),),
    )
    verdict = assess_review_risk(source)
    assert verdict.tier is ReviewTier.CRITICAL
    assert not verdict.fast_lane_candidate


def test_inert_evidence_only_stays_fast_with_full_verified_metrics():
    source = replace(
        facts(("docs/screenshots/chart.webp", "docs/user-guide.md"),
              additions=9, deletions=1),
        file_metrics=(
            ReviewFileStat(path="docs/screenshots/chart.webp", additions=0, deletions=0),
            ReviewFileStat(path="docs/user-guide.md", additions=9, deletions=1),
        ),
    )
    assert assess_review_risk(source).tier is ReviewTier.FAST


def test_test_only_one_line_addition_is_smoke_even_without_sensitive_paths():
    source = replace(
        facts(("tests/test_behavior.py",), additions=1, deletions=0),
        file_metrics=(ReviewFileStat(
            path="tests/test_behavior.py", additions=1, deletions=0
        ),),
    )
    assert assess_review_risk(source).tier is ReviewTier.STANDARD


def test_real_managed_workspace_identity_change_is_critical_with_verified_metrics():
    # Mastermind #1993 is a real managed-source identity and publisher precheck change.
    # Its small size must not reduce scrutiny of source-custody boundaries.
    source = replace(
        facts((
            "control_plane/executive_workspace.py",
            "scripts/mastermind_workspace.py",
            "tests/test_mastermind_workspace_repositories.py",
        ), additions=173, deletions=2),
        file_metrics=(
            ReviewFileStat("control_plane/executive_workspace.py", 69, 2),
            ReviewFileStat("scripts/mastermind_workspace.py", 5, 0),
            ReviewFileStat("tests/test_mastermind_workspace_repositories.py", 99, 0),
        ),
    )
    verdict = assess_review_risk(source)
    assert verdict.tier is ReviewTier.CRITICAL
    assert verdict.minimum_independent_assessments == 1
    assert verdict.minimum_formal_non_author_approvals == 0


@pytest.mark.parametrize("path", [
    "app/src/components/PriceChart.tsx",
    "app/static/landing.css",
    "server/handler.py",
    "backend/formatters.py",
    "tests/test_component.py",
    "tests/test_model.py",
    "scripts/helpers.py",
])
def test_attended_web_waiver_keeps_signed_machine_code_smoke(path):
    result = assess_review_risk(facts((path,), additions=90, deletions=20))
    assert result.tier is ReviewTier.STANDARD
    assert result.minimum_independent_assessments == 0
    assert result.minimum_formal_non_author_approvals == 0


@pytest.mark.parametrize("path", [
    "backend/auth/session.py",
    "server/payment/charge.py",
    "app/src/trade_execution/order.ts",
    ".github/workflows/ci.yml",
    "tests/test_security_gateway.py",
    "integrations/github_review_risk_reader.py",
    "docs/sol_skills/ACTIVE_EXECUTION.md",
    "config/ci_checks.yml",
])
def test_broadening_never_downgrades_privileged_changes(path):
    assert assess_review_risk(facts((path,), additions=1, deletions=0)).tier is ReviewTier.CRITICAL


def test_broad_fast_lane_does_not_accept_unknown_executable_format():
    assert assess_review_risk(facts(("app/native/main.rs",))).tier is ReviewTier.STANDARD


_CONSTITUTIONAL_CRITICAL_PATHS = (
    "control_plane/packet_gate.py",
    "control_plane/governance.py",
    "control_plane/strategic_state.py",
    "config/strategic_state.yml",
    "config/contracts.yml",
    "research/MASTERMIND_CHARTER_V2.md",
    "DOCTRINE.md",
)


@pytest.mark.parametrize("path", _CONSTITUTIONAL_CRITICAL_PATHS)
def test_one_line_authority_source_remains_critical_in_machine_risk(path):
    for candidate in (path, path.upper()):
        decision = assess_review_risk(
            facts((candidate,), additions=1, deletions=0)
        )
        assert decision.tier is ReviewTier.CRITICAL, candidate
        assert decision.minimum_independent_assessments == 1
        assert decision.minimum_formal_non_author_approvals == 0


def test_sensitive_previous_rename_path_remains_critical():
    source = replace(
        facts(("docs/screenshots/new.webp", "control_plane/packet_gate.py"),
              additions=1, deletions=0),
        file_metrics=(ReviewFileStat(
            path="docs/screenshots/new.webp",
            previous_path="control_plane/packet_gate.py",
            additions=1, deletions=0,
        ),),
    )
    assert assess_review_risk(source).tier is ReviewTier.CRITICAL


@pytest.mark.parametrize("path", [
    "app/mastermind_os/src/components/Widget.tsx",
    "app/src/component.jsx", "app/static/layout.css",
    "app/src/index.js", "tests/test_component.py",
    "frontend/views/card.vue", "frontend/views/card.svelte",
    "frontend/views/card.html",
])
def test_ci_2016_static_only_fast_never_classifies_active_source(path):
    verdict = assess_review_risk(facts(("docs/user-guide.md", path),
                                       additions=2, deletions=0))
    assert verdict.tier is ReviewTier.STANDARD
    assert not verdict.fast_lane_candidate
    assert verdict.minimum_independent_assessments == 0


def test_ci_2016_still_allows_static_only_fast_for_passive_docs():
    assert assess_review_risk(facts(("docs/user-guide.md",),
                                    additions=2, deletions=0)).tier is ReviewTier.FAST
