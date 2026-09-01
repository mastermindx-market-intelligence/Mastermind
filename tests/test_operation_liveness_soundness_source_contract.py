from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LAW = ROOT / "docs" / "OPERATION_LIVENESS_SOUNDNESS_LAW.md"
DESIGN = (
    ROOT
    / "docs"
    / "superpowers"
    / "specs"
    / "2026-08-30-operation-liveness-soundness-design.md"
)
LEDGER = (
    ROOT
    / "research"
    / "MASTERMIND_OPERATION_LIVENESS_SOUNDNESS_CAPABILITY_LEDGER_2026-08-30.md"
)
PLAN = (
    ROOT
    / "docs"
    / "superpowers"
    / "plans"
    / "2026-08-30-operation-assurance-core.md"
)


def _read(path: Path) -> str:
    assert path.is_file(), f"missing protected source artifact: {path.relative_to(ROOT)}"
    return " ".join(path.read_text(encoding="utf-8").split())


def test_ols_f0_artifacts_exist_and_bind_one_operation() -> None:
    operation = "mastermind-operation-liveness-soundness-20260830-sol-001"
    for path in (LAW, DESIGN, LEDGER):
        assert operation in _read(path)
    assert "Operation Assurance Core Implementation Plan" in _read(PLAN)


def test_ols_law_preserves_existing_canonical_owners() -> None:
    text = _read(LAW)
    required = (
        "Executive OS",
        "Agent OS",
        "Agent Dialogue / Company Dialogue",
        "Executive Inbox / Wake",
        "SessionTarget/RuntimeBinding",
        "Capacity Fabric / Model Router",
        "corrected Executive Steward / OCR-6",
        "Chairman Control Room",
        "Executive Attention Frontier",
        "GitHub",
        "Linear",
        "Slack / Agent Relay",
    )
    for marker in required:
        assert marker in text

    forbidden_claims = (
        "assurance database is canonical",
        "liveness scheduler owns",
        "hard gate is live",
        "production proven checker",
    )
    lowered = text.lower()
    for claim in forbidden_claims:
        assert claim not in lowered


def test_ols_proof_language_cannot_collapse_bounds_into_proof() -> None:
    text = _read(LAW)
    for marker in (
        "UNSAFE_COUNTEREXAMPLE",
        "PROVEN_WITHIN_FINITE_MODEL",
        "BOUNDED_NO_COUNTEREXAMPLE",
        "INCONCLUSIVE_MODEL_GAP",
        "MODEL_STALE_OR_INVALID",
        "complete reachable state space",
        "It must never be rendered as proved safe",
    ):
        assert marker in text

    assert "V1 is report-only" in text
    assert "A checker exception, timeout, state limit" in text
    assert "It can never produce a pass" in text


def test_ols_model_and_report_schemas_are_frozen() -> None:
    combined = _read(LAW) + "\n" + _read(DESIGN) + "\n" + _read(PLAN)
    assert "mastermind.operation_assurance_model.v1" in combined
    assert "mastermind.operation_assurance_report.v1" in combined
    assert "mastermind.operation_assurance.properties.v1" in combined
    assert "strong fairness" in combined.lower()
    assert "outside OLS-A1" in combined


def test_ols_counterexample_is_actionable_and_liveness_uses_a_lasso() -> None:
    text = _read(LAW) + "\n" + _read(DESIGN)
    for marker in (
        "shortest_prefix",
        "cycle",
        "state_delta_per_step",
        "enabled_and_disabled_transition_reasons",
        "source_refs",
        "minimal deterministic repair candidates",
        "prefix + cycle",
    ):
        assert marker in text


def test_ols_adjacent_program_boundaries_are_explicit() -> None:
    text = _read(LAW) + "\n" + _read(DESIGN) + "\n" + _read(LEDGER)
    for marker in (
        "Executive Attention Frontier",
        "PR #268",
        "PR #228",
        "never ranks",
        "parallel federated reader",
    ):
        assert marker in text


def test_ols_a1_plan_is_pure_report_only_and_path_bounded() -> None:
    text = _read(PLAN)
    required_paths = (
        "control_plane/operation_assurance_model.py",
        "control_plane/operation_assurance_report.py",
        "control_plane/operation_assurance_checker.py",
        "scripts/operation_assurance.py",
        "tests/fixtures/operation_assurance",
    )
    for path in required_paths:
        assert path in text

    for protected_path in (
        "Executive Runtime",
        "Executive Steward",
        "Wake",
        "SessionTarget",
        "RuntimeBinding",
        "Model Router",
        "Agent OS",
        "Control Room",
    ):
        assert protected_path in text

    assert "No edits to Executive Runtime" in text
    assert "A valid unsafe model still produces a report and normal CLI process completion" in text
    assert "OLS-A1 stops at a pure report-only CLI" in text


def test_ols_completion_honesty_is_explicit() -> None:
    text = _read(LAW)
    assert "Protecting OLS-F0 makes only the architecture and no-rebuild law true" in text
    for not_live in (
        "checker",
        "compiler",
        "product",
        "admission integration",
        "runtime conformance",
        "canary",
    ):
        assert not_live in text
