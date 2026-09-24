from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AMENDMENT = (
    ROOT
    / "docs"
    / "superpowers"
    / "specs"
    / "2026-08-31-operation-liveness-soundness-executive-steward-reconciliation.md"
)
LAW = ROOT / "docs" / "OPERATION_LIVENESS_SOUNDNESS_LAW.md"
DESIGN = (
    ROOT
    / "docs"
    / "superpowers"
    / "specs"
    / "2026-08-30-operation-liveness-soundness-design.md"
)
PLAN = (
    ROOT
    / "docs"
    / "superpowers"
    / "plans"
    / "2026-08-30-operation-assurance-core.md"
)
LEDGER = (
    ROOT
    / "research"
    / "MASTERMIND_OPERATION_LIVENESS_SOUNDNESS_CAPABILITY_LEDGER_2026-08-30.md"
)
AMENDMENT_NAME = AMENDMENT.name


def _read(path: Path) -> str:
    assert path.is_file(), f"missing protected source artifact: {path.relative_to(ROOT)}"
    return " ".join(path.read_text(encoding="utf-8").split())


def test_current_protected_steward_reconciliation_is_exact_and_discoverable() -> None:
    text = _read(AMENDMENT)
    assert "eccf0a3fae8b8597c2ad0bc4f830e31b220415d2" in text
    assert "dcce6f7ab6efad360f4854d748ad0d65dc9e0f7c" in text
    assert "OCR-6R: protect Executive Steward read core (#228)" in text
    for path in (
        "control_plane/executive_steward.py",
        "tests/test_executive_steward.py",
        "tests/test_executive_steward_filter_integrity.py",
    ):
        assert path in text

    for parent in (LAW, DESIGN, PLAN, LEDGER):
        assert AMENDMENT_NAME in _read(parent), (
            f"{parent.relative_to(ROOT)} must point to current Steward reconciliation"
        )


def test_steward_protection_satisfies_only_the_pure_read_core_predecessor() -> None:
    text = _read(AMENDMENT)
    assert "mastermind.executive_steward.result.v1" in text
    assert "pure read core" in text
    assert "BUILT_NOT_PROVEN / PRODUCTION_INERT" in text
    assert "satisfies only the pure composition-core predecessor" in text
    assert "gather adapter" in text
    assert "canonical acquisition" in text
    assert "current-source attestation" in text
    assert "production composition" in text
    assert "NOT_BUILT" in text


def test_ols_a2_reuses_steward_without_creating_a_parallel_reader() -> None:
    text = _read(AMENDMENT)
    assert "OLS-A2 remains `NOT_BUILT`" in text
    assert "accepted and protected OLS-A1" in text
    assert "separately accepted bounded gather/source-compiler seam" in text
    assert "caller-supplied, source-attributed facts" in text
    assert "must not create a parallel federated reader" in text
    assert "must not side-read existing owners" in text
    assert "typed uncertainty or refusal" in text


def test_steward_merge_does_not_inflate_ols_or_production_capability() -> None:
    text = _read(AMENDMENT)
    for not_made_true in (
        "OLS checker",
        "OLS source compiler",
        "Control Room assurance experience",
        "admission attachment",
        "runtime conformance",
        "production-live organizational continuity",
    ):
        assert not_made_true in text
    assert "records-only OLS-F0" in text
    assert "No Ready transition, merge, implementation commission, or OLS-A1 start" in text
