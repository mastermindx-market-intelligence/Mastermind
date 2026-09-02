"""Contract pins for the OLS-A2 bounded gather/source-compiler seam design."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DESIGN = (
    ROOT
    / "docs"
    / "superpowers"
    / "specs"
    / "2026-09-01-operation-assurance-a2-source-seam-design.md"
)
LEDGER = (
    ROOT
    / "research"
    / "MASTERMIND_OPERATION_LIVENESS_SOUNDNESS_CAPABILITY_LEDGER_2026-08-30.md"
)

EXPECTED_FAILURE_STATES = (
    "INVALID_SOURCE_BUNDLE",
    "SOURCE_MISSING",
    "SOURCE_PARTIAL",
    "SOURCE_TRUNCATED",
    "SOURCE_STALE",
    "SOURCE_CONFLICTED",
    "SOURCE_SUPERSEDED",
    "SOURCE_ATTESTATION_UNAVAILABLE",
    "INPUT_TOO_LARGE",
    "DUPLICATE_KEY",
    "UNRESOLVED_REFERENCE",
    "UNSUPPORTED_SEMANTICS",
)


def _text() -> str:
    assert DESIGN.is_file(), "missing OLS-A2 source-seam design record"
    return " ".join(DESIGN.read_text(encoding="utf-8").split())


def test_design_is_the_narrow_controlling_a2_seam_record() -> None:
    text = _text()
    assert "NARROW CONTROLLING DESIGN / SPEC_ONLY / RECORDS_ONLY / PRODUCTION_INERT" in text
    assert "mastermind-operation-assurance-full-production-20260901-fable-003" in text
    assert "separately accepted bounded gather/source-compiler seam" in text
    assert "It authorizes no implementation by itself" in text


def test_seam_separation_is_exact() -> None:
    text = _text()
    assert "control_plane/operation_assurance_sources.py` — the ONLY module with read I/O" in text
    assert "control_plane/operation_assurance_compiler.py` — pure (stdlib-only, zero I/O)" in text
    assert "scripts/operation_assurance_compile.py" in text
    assert "no cache, no persistence, no retry loops" in text
    assert "protected OLS-A1 checker (unchanged; never side-reads)" in text


def test_first_owner_adapter_and_target_operation_are_frozen() -> None:
    text = _text()
    assert "exactly ONE owner adapter: **Agent OS records**" in text
    assert "agentos.workstream.v1" in text
    assert "read at ONE pinned git revision" in text
    assert "`WS:OPERATION-ASSURANCE` workstream itself" in text
    assert "the record BODY (human truth) is never parsed" in text
    for absent_adapter in (
        "Executive OS runtime (Job/Attempt/Worker/Event)",
        "SCF/GitHub (whose packets OLS must never counterfeit",
    ):
        assert absent_adapter in text


def test_trust_ceiling_cannot_be_minted_by_gathering() -> None:
    text = _text()
    assert "PROVENANCE_CLOSED_UNATTESTED / AUTHOR_DECLARED_ONLY` at most" in text
    assert "does NOT mint `CURRENT_SOURCE_ATTESTED`" in text
    assert "REPORT_ONLY_PROCEED" not in text
    assert "The compiler cannot self-upgrade" in text


def test_no_rebuild_boundary_names_the_forbidden_planes() -> None:
    text = _text()
    for forbidden in (
        "parallel federated reader",
        "second Steward",
        "side-read owners from the A1 checker",
        "elect sources by recency",
        "persist gathered facts anywhere",
        "import `chairman_cognition_sources`",
    ):
        assert forbidden in text


def test_failure_states_are_the_exact_frozen_subset() -> None:
    text = _text()
    for state in EXPECTED_FAILURE_STATES:
        assert f"`{state}`" in text, f"missing failure state {state}"
    assert "never degrades to an apparently healthy compilation" in text


def test_ledger_reverse_links_to_this_design() -> None:
    ledger_text = " ".join(LEDGER.read_text(encoding="utf-8").split())
    assert "2026-09-01-operation-assurance-a2-source-seam-design.md" in ledger_text, (
        "capability ledger must point to the current A2 seam design"
    )
