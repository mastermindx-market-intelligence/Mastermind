"""Discriminating contract pins for the OLS-A2 bounded gather/source-compiler seam design.

Strengthened per Sol review 5086088649: these tests must FAIL if the Steward step is removed,
an imaginary predecessor wire is cited as protected, fidelity/currentness is promoted, or the
property subset becomes unconstrained.
"""

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

SUPPORTED_PROPERTIES = (
    "OPTION_TO_COMPLETE",
    "PROPER_COMPLETION",
    "NO_DEAD_REQUIRED_TRANSITION",
    "TERMINAL_ABSORPTION",
    "GATE_WAIT_RETURN_VALIDITY",
    "UNIVERSAL_PROGRESS",
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


def test_steward_composition_step_is_mandatory_and_real() -> None:
    text = _text()
    assert "existing Executive Steward pure composition (mastermind.executive_steward.result.v1)" in text
    assert "The mandatory Steward step is real, not decorative" in text
    assert "compiler performs ZERO identity resolution" in text
    assert "the Steward is the only identity/source normalizer" in text
    assert "reused, never copied, subclassed, or reimplemented" in text


def test_source_facts_wire_is_defined_here_not_claimed_protected() -> None:
    text = _text()
    assert "No protected source-bundle or predecessor \"A2-S0\" wire exists in the repository today" in text
    assert "this design DEFINES the wire" in text
    assert "invocation-local and non-persistent" in text
    assert "no source store" in text
    assert "already frozen and parsed" not in text
    assert "protected A1/A2-S0 contract family" not in text


def test_property_subset_is_frozen_and_proof_ceiling_is_honest() -> None:
    text = _text()
    for prop in SUPPORTED_PROPERTIES:
        assert f"`{prop}`" in text, f"missing supported property {prop}"
    assert "Unsupported in this vertical (each an explicit load-bearing model gap" in text
    assert "starvation-under-declared-fairness" in text
    assert "never proof-eligible" in text
    assert "never mints `PROVEN_WITHIN_FINITE_MODEL` for a live workstream" in text
    assert "compiler-template behavior grounded in exact record fields" in text
    assert "never presented as owner-attested runtime fact" in text


def test_attestation_time_and_correction_law_is_closed() -> None:
    text = _text()
    assert "full 40-hex commit SHA" in text
    assert "abbreviated SHAs are refused" in text
    assert "ONE `observed_at` cutoff covers the entire gather" in text
    assert "Corrections are immutable and append-only" in text or "corrections are immutable and append-only" in text
    assert "Agent-OS-only evidence can never yield whole-operation currentness" in text
    assert "REPORT_ONLY_PROCEED" in text  # named exactly once, as non-existent
    assert "the value does not exist in the protected wire" in text


def test_hostile_fixture_is_the_current_stale_revision() -> None:
    text = _text()
    assert "itself the named hostile stale/coverage-incomplete case" in text
    assert "durable `next_action` still names predecessor-era state" in text
    assert "later corrected, schema-valid pinned revision" in text
    assert "Schema validity is never laundered into semantic currentness" in text


def test_no_rebuild_boundary_names_the_forbidden_planes() -> None:
    text = _text()
    for forbidden in (
        "parallel federated reader",
        "second Steward",
        "copy or reimplement Steward dataclasses or identity logic",
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


def test_ledger_reverse_links_and_current_status_is_truthful() -> None:
    ledger_text = " ".join(LEDGER.read_text(encoding="utf-8").split())
    assert "2026-09-01-operation-assurance-a2-source-seam-design.md" in ledger_text
    assert "A1 deterministic engine: PROTECTED at master merge `c6af57d1" in ledger_text
    assert "A2: design-candidate under repair on PR #339" in ledger_text
