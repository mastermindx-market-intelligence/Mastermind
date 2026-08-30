from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "docs/superpowers/specs/2026-08-30-sol-capability-fabric-design.md"
CATALOG = ROOT / "docs/superpowers/plans/2026-08-30-sol-capability-fabric-tool-catalog.md"
PROGRAM = ROOT / "docs/superpowers/plans/2026-08-30-sol-capability-fabric-program.md"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_sol_capability_fabric_records_exist() -> None:
    assert SPEC.is_file()
    assert CATALOG.is_file()
    assert PROGRAM.is_file()


def test_architecture_preserves_canonical_owners_and_chat_native_cognition() -> None:
    text = _text(SPEC)
    for required in (
        "mastermind-sol-capability-fabric-20260830-sol-001",
        "COGNITION_ROUTE: CHAT_PRO_DEFAULT",
        "Executive OS",
        "Agent OS",
        "GitHub",
        "RuntimeBinding",
        "Wake",
        "Capacity Fabric / Model Router",
        "Executive Steward / Chairman Control Room",
        "One Experience, Federated Authority",
    ):
        assert required in text


def test_architecture_freezes_privilege_and_effect_semantics() -> None:
    text = _text(SPEC)
    for required in (
        "R0_OBSERVE",
        "W1_ROUTINE",
        "W2_CONSEQUENTIAL",
        "A3_ADMIN",
        "prepare_action",
        "commit_prepared_action",
        "NOT_APPLIED",
        "APPLIED",
        "EFFECT_UNKNOWN",
        "PARTIAL_CLOSEOUT",
        "No universal action router",
        "no durable prepared-action store",
    ):
        assert required in text


def test_architecture_rejects_duplicate_or_unbounded_control_surfaces() -> None:
    text = _text(SPEC)
    for forbidden_surface in (
        "generic shell",
        "generic SQL",
        "arbitrary browser click/type",
        "super-MCP",
        "plugin-owned memory",
        "MCP-owned scheduler",
        "provider process spawner",
        "second RuntimeBinding registry",
        "second lifecycle",
    ):
        assert forbidden_surface in text


def test_catalog_contains_closed_semantic_capability_groups() -> None:
    text = _text(CATALOG)
    for required in (
        "capability_status",
        "company_state",
        "operation_evidence",
        "assess_release_gate",
        "collision_census",
        "workflow_diagnosis",
        "runner_fleet",
        "explain_queued_job",
        "inspect_sol_surface",
        "provision_sol_surface",
        "rotate_sol_surface",
        "retire_sol_surface",
        "fleet_capacity",
        "commission_child",
        "host_fleet_health",
        "service_health",
        "prepare_action",
        "commit_prepared_action",
        "reconcile_effect",
    ):
        assert required in text


def test_catalog_never_makes_technical_permission_organizational_authority() -> None:
    text = _text(CATALOG)
    assert "Technical permission is not organizational authority" in text
    assert "OAuth authenticates; it does not elect an executive" in text
    assert "The model never selects a credential, host, account, branch writer, or runtime binding" in text


def test_program_is_vertical_and_has_real_promotion_proof() -> None:
    text = _text(PROGRAM)
    for wave in (
        "SCF-F0",
        "SCF-CAP1",
        "SCF-GH0",
        "SCF-GH1",
        "SCF-GH2",
        "SCF-RUN1",
        "SCF-S1",
        "SCF-E1",
        "SCF-SURF1",
        "SCF-SURF2",
        "SCF-SURF3",
        "SCF-FLEET1",
        "SCF-FLEET2",
        "SCF-OPS1",
        "SCF-OPS2",
        "SCF-A3",
        "SCF-OBS1",
        "SCF-UI1",
        "SCF-CANARY1",
        "SCF-CUTOVER",
    ):
        assert wave in text
    for required in (
        "one independently useful capability per PR",
        "real production path",
        "browser proof",
        "Chairman manual interventions",
        "Sol tokens spent on deterministic reconstruction",
        "time from worker RESULT to Sol adjudication",
        "No wave inherits START from this records carrier",
    ):
        assert required in text


def test_prepared_action_commit_uses_authenticated_storeless_token() -> None:
    combined = "\n".join(_text(path) for path in (SPEC, CATALOG, PROGRAM))
    assert "commit_prepared_action(prepared_token)" in combined
    assert "commit_prepared_action(prepared_digest)" not in combined
    assert "authenticated self-contained expiring token" in combined
    assert "server validates its integrity and expiry before use" in combined


def test_records_state_is_honest() -> None:
    combined = "\n".join(_text(path) for path in (SPEC, CATALOG, PROGRAM))
    assert "SPEC_ONLY / RECORDS_ONLY / PRODUCTION_INERT" in combined
    assert "This records wave creates no live MCP app" in combined
    assert "PROVEN_LIVE" in combined
