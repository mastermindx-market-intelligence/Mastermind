from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLARIFICATION = (
    ROOT
    / "docs"
    / "superpowers"
    / "specs"
    / "2026-08-30-operation-assurance-immutable-report-projection-clarification.md"
)


def _text() -> str:
    assert CLARIFICATION.is_file()
    return CLARIFICATION.read_text(encoding="utf-8")


def test_immutable_report_uses_generation_time_truth_only() -> None:
    text = _text()
    assert "mastermind.operation_assurance_report.v1" in text
    assert "model_analysis_verdict" in text
    assert "source_applicability_at_generation" in text
    assert "The report is content-addressed and immutable" in text
    assert "never mutates\nthese fields" in text


def test_current_projection_fields_are_withdrawn_from_report_wire() -> None:
    text = _text()
    assert "withdrawn from the immutable report wire" in text
    for field in (
        "assurance_verdict",
        "current_projection_verdict",
        "source_applicability",
    ):
        assert field in text
    assert "MODEL_STALE_OR_INVALID` is not a model-analysis verdict" in text


def test_current_status_is_an_existing_owner_read_composition() -> None:
    text = _text()
    assert "mastermind.operation_assurance_status.v1" in text
    assert "corrected Executive Steward / Control Room" in text
    assert "read composition, not a new truth store or lifecycle" in text
    assert "owns no retry,\nrecheck schedule, admission, report mutation, or source correction" in text


def test_ols_a1_cannot_emit_current_operational_status() -> None:
    text = _text()
    assert "OLS-A1 emits only `mastermind.operation_assurance_report.v1`" in text
    assert "source_applicability_at_generation = AUTHOR_DECLARED_ONLY" in text
    assert "does not emit `mastermind.operation_assurance_status.v1`" in text
    assert "does not claim the report is current for a live operation" in text


def test_generation_time_conflict_preserves_model_result_without_operational_claim() -> None:
    text = _text()
    assert "model_analysis_verdict = UNSAFE_COUNTEREXAMPLE" in text
    assert "source_applicability_at_generation = CONFLICTED" in text
    assert "admission_recommendation = REPORT_ONLY_RECONCILE" in text
    assert "does not claim the current operation is unsafe" in text


def test_current_recommendation_cannot_survive_staleness_by_history() -> None:
    text = _text()
    assert "A stale/superseded report can never retain a current `REPORT_ONLY_PROCEED`" in text
    assert "without modifying the report" in text
    assert "part of the OLS-F0 release contract" in text
