from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ESTATE = ROOT / "research/sol_capability_fabric/GITHUB_CURRENT_ESTATE_LEDGER_2026-08-30.md"
REUSE = ROOT / "research/sol_capability_fabric/GITHUB_NATIVE_CUSTOM_REUSE_MATRIX_2026-08-30.md"
SEMANTICS = ROOT / "research/sol_capability_fabric/GITHUB_SEMANTIC_CONTRACT_2026-08-30.md"
GH1_PLAN = ROOT / "docs/superpowers/plans/2026-08-30-sol-capability-fabric-gh1.md"

OPERATION = "mastermind-sol-capability-fabric-gh0-20260830-sol-001"
PROTECTED_SHA = "98bc7a71dcd70947c7a18eb5af7493a2f62a2571"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_gh0_records_exist() -> None:
    for path in (ESTATE, REUSE, SEMANTICS, GH1_PLAN):
        assert path.is_file(), path


def test_gh0_records_pin_current_protected_source_and_honest_state() -> None:
    combined = "\n".join(_text(path) for path in (ESTATE, REUSE, SEMANTICS, GH1_PLAN))
    assert OPERATION in combined
    assert PROTECTED_SHA in combined
    assert "SPEC_ONLY / RECORDS_ONLY / PRODUCTION_INERT" in combined
    assert "COGNITION_ROUTE: CHAT_PRO_DEFAULT" in combined
    assert "no runtime implementation or GitHub mutation" in combined


def test_estate_ledger_uses_company_capability_vocabulary_and_source_limits() -> None:
    text = _text(ESTATE)
    for required in (
        "PROVEN_LIVE",
        "BUILT_NOT_PROVEN",
        "PARTIAL",
        "DARK_OR_DISCONNECTED",
        "BROKEN",
        "SPEC_ONLY",
        "NOT_BUILT",
        "REJECTED_BY_DESIGN",
        "repository / branch / commit / file",
        "pull request / issue / review",
        "workflow run / job / step / log / artifact",
        "expected_head_sha",
        "Repository.fullDatabaseId",
        "first page",
        "technical permission is not organizational authority",
        "runner inventory",
        "organization audit log",
        "app installation",
    ):
        assert required in text


def test_reuse_matrix_preserves_native_actuators_and_existing_owners() -> None:
    text = _text(REUSE)
    for required in (
        "Native GitHub connector",
        "scripts/github_estate_governance.py",
        "tests/test_github_estate_governance.py",
        "Code Intelligence Fabric",
        "exact local Git",
        "expected-head merge",
        "read-back reconciliation",
        "GitHub remains implementation/evidence truth",
    ):
        assert required in text
    for forbidden in (
        "super GitHub MCP",
        "generic GitHub endpoint actuator",
        "second PR database",
        "second check-run store",
        "model-selected repository",
        "model-selected branch writer",
    ):
        assert forbidden in text


def test_semantic_contract_is_closed_storeless_and_effect_safe() -> None:
    text = _text(SEMANTICS)
    for required in (
        "mastermind.github_status.v1",
        "mastermind.github_prepared_action.v1",
        "ELIGIBLE | HELD | REFUSED | UNKNOWN",
        "NOT_APPLIED | APPLIED | EFFECT_UNKNOWN",
        "expected_head_sha",
        "prepared_token",
        "one carrier",
        "OPERATION_CARRIER_CONFLICT",
        "current-source revalidation",
        "no durable prepared-action store",
        "no universal action router",
        "no blind retry",
    ):
        assert required in text


def test_gh1_plan_freezes_pure_release_collision_engine_before_live_composition() -> None:
    text = _text(GH1_PLAN)
    for required in (
        "SCF-GH1",
        "control_plane/github_release_assessment.py",
        "tests/test_github_release_assessment.py",
        "pure",
        "no network",
        "no mutation",
        "ELIGIBLE",
        "HELD",
        "REFUSED",
        "UNKNOWN",
        "records-only PR",
        "production proof",
        "permutation-stable",
        "SCF-GH2",
        "SCF-RUN1",
    ):
        assert required in text
    assert "Stop at `BUILT_NOT_PROVEN / PRODUCTION_INERT`" in text


def test_gh0_does_not_claim_live_git_control() -> None:
    combined = "\n".join(_text(path) for path in (ESTATE, REUSE, SEMANTICS, GH1_PLAN))
    assert "GH0 installs no app, connector, credential, runner, workflow, service or actuator" in combined
    assert "GitHub status composer = NOT_BUILT" in combined
    assert "GitHub prepared action executor = NOT_BUILT" in combined
