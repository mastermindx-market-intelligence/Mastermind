from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AMENDMENT = (
    ROOT
    / "docs"
    / "superpowers"
    / "specs"
    / "2026-08-31-operation-liveness-soundness-sol-capability-fabric-reconciliation.md"
)
SCF_CONTRACT = (
    ROOT
    / "research"
    / "sol_capability_fabric"
    / "GITHUB_SEMANTIC_CONTRACT_2026-08-30.md"
)


def _read(path: Path) -> str:
    assert path.is_file(), f"missing protected source artifact: {path.relative_to(ROOT)}"
    return " ".join(path.read_text(encoding="utf-8").split())


def test_ols_reconciles_current_protected_scf_source_without_rewriting_history() -> None:
    text = _read(AMENDMENT)
    assert "e19ef1c54cc6f2b7bfc652a78bf94a209fcb42b9" in text
    assert "eccf0a3fae8b8597c2ad0bc4f830e31b220415d2" in text
    assert "Sol Capability Fabric GH0, Mastermind PR #294" in text
    assert "path-disjoint but semantically adjacent" in text
    for protected_path in (
        "GITHUB_CURRENT_ESTATE_LEDGER_2026-08-30.md",
        "GITHUB_NATIVE_CUSTOM_REUSE_MATRIX_2026-08-30.md",
        "GITHUB_SEMANTIC_CONTRACT_2026-08-30.md",
        "2026-08-30-sol-capability-fabric-gh1.md",
        "test_sol_capability_fabric_gh0.py",
    ):
        assert protected_path in text


def test_ols_does_not_duplicate_scf_github_contracts_or_authority() -> None:
    amendment = _read(AMENDMENT)
    scf = _read(SCF_CONTRACT)
    for schema in (
        "mastermind.github_status.v1",
        "mastermind.github_release_assessment.v1",
        "mastermind.github_prepared_action.v1",
        "mastermind.github_action_receipt.v1",
        "mastermind.github_runner_status.v1",
    ):
        assert schema in amendment
        assert schema in scf

    for forbidden_owner in (
        "a GitHub mirror",
        "an operation-to-GitHub carrier registry",
        "a second release/collision/completion assessor",
        "a prepared-action database",
        "a GitHub effect-reconciliation service",
        "a runner observatory",
        "a generic HTTP/GraphQL actuator",
    ):
        assert forbidden_owner in amendment


def test_release_eligibility_and_operation_liveness_are_orthogonal() -> None:
    text = _read(AMENDMENT)
    assert "A GitHub release assessment of `ELIGIBLE` is not `PROVEN_WITHIN_FINITE_MODEL`" in text
    assert "An OLS result of `PROVEN_WITHIN_FINITE_MODEL` is not GitHub merge or release eligibility" in text
    assert "GitHub check success is not runtime conformance" in text
    assert "a held or refused release does not by itself prove an operation deadlocked" in text
    assert "Neither answer upgrades or replaces the other" in text


def test_ols_a1_remains_pure_and_cannot_import_scf_effect_surfaces() -> None:
    text = _read(AMENDMENT)
    assert "OLS-A1 remains the same pure vertical" in text
    for marker in (
        "must not import a GitHub connector",
        "control_plane.github_release_assessment",
        "zero network, socket, subprocess",
        "zero GitHub acquisition or effect",
        "AUTHOR_DECLARED_ONLY",
    ):
        assert marker in text
    assert "No SCF implementation, GitHub reader, release assessor, prepared action" in text


def test_ols_a2_must_consume_protected_owner_packets_and_fail_closed() -> None:
    text = _read(AMENDMENT)
    assert "corrected and protected Executive Steward/OCR-6 normalized read seam" in text
    assert "separately accepted bounded SCF machine-read seam" in text
    assert "may not side-read raw GitHub APIs" in text
    assert "The absence of a protected SCF implementation does not authorize OLS" in text
    for state in ("UNKNOWN", "HELD", "REFUSED", "NOT_BUILT"):
        assert state in text
    assert "never converted to empty, false, healthy, eligible, or safe defaults" in text


def test_scf_effect_unknown_is_a_source_owned_no_escape_fact() -> None:
    text = _read(AMENDMENT)
    assert "NOT_APPLIED | APPLIED | EFFECT_UNKNOWN" in text
    assert "OLS never calls `reconcile_github_effect`" in text
    assert "`EFFECT_UNKNOWN` remains a source-owned hard no-escape fact" in text
    for forbidden_escape in (
        "retry",
        "alternate app",
        "alternate connector",
        "alternate account",
        "alternate branch writer",
        "alternate carrier",
        "cross-surface failover",
    ):
        assert forbidden_escape in text


def test_control_room_cannot_conflate_scf_ols_and_runtime_evidence() -> None:
    text = _read(AMENDMENT)
    assert "The eventual Control Room composition joins, without conflating" in text
    assert "must not render GitHub `ELIGIBLE` as an OLS proof" in text
    assert "render OLS finite-model proof as merge-ready" in text
    assert "render green CI as `PROVEN_LIVE`" in text
    assert "render SCF `APPLIED` as target consumption" in text
    assert "A source gap in any axis remains visible" in text


def test_current_capability_state_remains_records_only_and_predecessor_gated() -> None:
    text = _read(AMENDMENT)
    assert "OLS-F0 remains records-only and production-inert" in text
    assert "Protecting SCF-GH0 did not make any GitHub app" in text
    assert "exact-head hosted checks and a fresh independent Auditor Sol review remain mandatory" in text
    assert "OLS-A1 remains predecessor-gated" in text
    assert "No merge, Ready transition, implementation commission" in text
