from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FINALIZATION = (
    ROOT
    / "docs"
    / "superpowers"
    / "specs"
    / "2026-08-31-operation-assurance-a1-wire-release-finalization.md"
)
LAW = ROOT / "docs" / "OPERATION_LIVENESS_SOUNDNESS_LAW.md"
DESIGN = (
    ROOT
    / "docs"
    / "superpowers"
    / "specs"
    / "2026-08-30-operation-liveness-soundness-design.md"
)
PLAN = ROOT / "docs" / "superpowers" / "plans" / "2026-08-30-operation-assurance-core.md"
LEDGER = (
    ROOT
    / "research"
    / "MASTERMIND_OPERATION_LIVENESS_SOUNDNESS_CAPABILITY_LEDGER_2026-08-30.md"
)
CLARIFICATION = (
    ROOT
    / "docs"
    / "superpowers"
    / "specs"
    / "2026-08-30-operation-assurance-immutable-report-projection-clarification.md"
)

EXPECTED_REPORT_FIELDS = (
    "schema",
    "report_id",
    "model_id",
    "model_hash",
    "source_snapshot_hash",
    "checker_version",
    "property_set_version",
    "model_analysis_verdict",
    "source_applicability_at_generation",
    "abstraction_contract",
    "progress_disposition",
    "admission_recommendation",
    "property_results",
    "counterexamples",
    "coverage",
    "assumptions",
    "known_model_gaps",
    "exploration_receipt",
    "generated_at",
    "supersedes_report_id",
    "report_hash",
)


def _fenced_fields(path: Path, marker: str) -> tuple[str, ...]:
    raw = path.read_text(encoding="utf-8")
    assert marker in raw, f"missing wire marker in {path.name}"
    tail = raw.split(marker, 1)[1]
    assert "```text" in tail, f"missing wire fence in {path.name}"
    block = tail.split("```text", 1)[1].split("```", 1)[0]
    return tuple(line.strip() for line in block.splitlines() if line.strip())


def _text() -> str:
    assert FINALIZATION.is_file(), "missing final OLS-A1 wire and release clarification"
    return " ".join(FINALIZATION.read_text(encoding="utf-8").split())


def test_finalization_is_the_narrow_controlling_source() -> None:
    text = _text()
    assert "FINAL NARROW CONTROLLING CLARIFICATION" in text
    assert "mastermind-operation-liveness-soundness-20260830-sol-001" in text
    assert "dcce6f7ab6efad360f4854d748ad0d65dc9e0f7c" in text
    for source in (
        "2026-08-30-operation-assurance-immutable-report-projection-clarification.md",
        "2026-08-30-operation-assurance-model-fidelity-counterexample-validation-amendment.md",
        "2026-08-30-operation-assurance-a1-trusted-input-total-proof-clarification.md",
        "2026-08-30-operation-assurance-a1-controlling-execution-overlay.md",
        "2026-08-30-operation-assurance-core.md",
    ):
        assert source in text
    assert "This finalization wins on the exact immutable report field list" in text


def test_exact_immutable_report_wire_includes_all_generation_time_axes() -> None:
    text = _text()
    positions = [text.index(field) for field in EXPECTED_REPORT_FIELDS]
    assert positions == sorted(positions)
    assert "progress_disposition and admission_recommendation are immutable generation-time axes" in text
    assert "included in the canonical report body hashed into report_hash" in text
    assert "current recommendation is recomputed" in text
    assert "MODEL_STALE_OR_INVALID remains outside model_analysis_verdict" in text


def test_parent_plan_is_navigation_only_where_superseded() -> None:
    text = _text()
    assert "Do not implement stale parent snippets by copying them literally" in text
    assert "The parent plan remains the task-order and file-map scaffold" in text
    assert "The controlling overlay and narrow clarifications define the executable wire" in text
    assert "missing abstraction_contract" in text
    assert "assurance_verdict" in text
    assert "REPORT_ONLY_PROCEED" in text


def test_external_grok_browser_placement_is_not_a_release_gate() -> None:
    text = _text()
    assert "mastermind-operation-liveness-f0-audit-placement-20260830-sol-002" in text
    assert "CANCELLED_PRESTART / effect=NONE" in text
    assert "No Grok, browser-created chat, numbered account, or external placement is required" in text
    assert "External reviewer availability cannot strand an otherwise verified records-only release" in text
    assert "Independent OLS-A1R review remains a later technical quality wave" in text


def test_f0_direct_release_gate_preserves_quality_without_ceremony() -> None:
    text = _text()
    for gate in (
        "current protected Mastermind and same-SHA Skillpack pin",
        "exact candidate head and changed-path digest",
        "latest-base pull-request mergeability",
        "terminal-success required hosted checks",
        "zero unresolved blocking reviews or review threads",
        "Program-CEO adversarial acceptance receipt",
        "expected-head merge",
    ):
        assert gate in text
    assert "Green CI alone is insufficient" in text
    assert "The Program-CEO review must reject" in text


def test_steward_protection_clears_only_the_a2_source_predecessor() -> None:
    text = _text()
    assert "OCR-6R: protect Executive Steward read core (#228)" in text
    assert "BUILT_NOT_PROVEN / PRODUCTION_INERT" in text
    assert "The old wait-for-#228-protection predecessor is cleared" in text
    assert "OLS-A2 still cannot start before accepted OLS-A1" in text
    assert "does not make a gather adapter or live source compiler exist" in text


def test_finalization_remains_records_only_and_creates_no_duplicate_owner() -> None:
    text = _text()
    assert "SPEC_ONLY / RECORDS_ONLY / PRODUCTION_INERT" in text
    for forbidden in (
        "creates no Job",
        "creates no lifecycle",
        "creates no source compiler",
        "performs no GitHub effect",
        "performs no runtime mutation",
    ):
        assert forbidden in text
    assert "Protecting OLS-F0 still does not build OLS-A1" in text


def test_exact_wire_field_list_is_tuple_exact_not_positional() -> None:
    fields = _fenced_fields(FINALIZATION, "field order is:")
    assert fields == EXPECTED_REPORT_FIELDS
    for forbidden in (
        "repair_scope",
        "current_recommendation",
        "assurance_verdict",
        "source_applicability",
        "current_projection_verdict",
        "current_assurance_status",
        "computed_at",
    ):
        assert forbidden not in fields


def test_wire_field_list_matches_immutable_report_clarification() -> None:
    final_fields = _fenced_fields(FINALIZATION, "field order is:")
    clarification_fields = _fenced_fields(
        CLARIFICATION,
        "`mastermind.operation_assurance_report.v1` contains exactly:",
    )
    assert final_fields == clarification_fields


def test_finalization_is_reverse_linked_from_every_entrypoint() -> None:
    for parent in (LAW, DESIGN, PLAN, LEDGER):
        parent_text = " ".join(parent.read_text(encoding="utf-8").split())
        assert (
            "2026-08-31-operation-assurance-a1-wire-release-finalization.md" in parent_text
        ), f"{parent.name} must point to the controlling wire-release finalization"


def test_repair_scope_is_ruled_out_of_the_f0_wire() -> None:
    text = _text()
    assert "`repair_scope` is likewise not an immutable report field" in text
    assert "superseded on this field" in text
    assert "schema-closure task must either freeze a closed `repair_scope` vocabulary" in text
