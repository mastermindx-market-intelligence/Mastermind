from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AMENDMENT = (
    ROOT
    / "docs"
    / "superpowers"
    / "specs"
    / "2026-08-30-operation-liveness-soundness-runtime-observability-reconciliation.md"
)


def _text() -> str:
    assert AMENDMENT.is_file()
    return " ".join(AMENDMENT.read_text(encoding="utf-8").split())


def test_ols_reconciles_current_protected_source_without_rewriting_history() -> None:
    text = _text()
    assert "28d365cceaef6efb0a26e0ac9af51ead44695d60" in text
    assert "be4cb72c7c6c663ae7c09a7e2d22543ab406b027" in text
    assert "Runtime Observability Fabric F0" in text
    assert "path-disjoint but semantically adjacent" in text


def test_runtime_observability_and_operation_assurance_remain_orthogonal() -> None:
    text = _text()
    assert "A complete trace is not proof that an operation is live" in text
    assert "A missing trace is not proof that an operation is dead" in text
    assert "Runtime Observability Fabric answers" in text
    assert "Operation Assurance answers" in text
    assert "never authorizes" in text


def test_ols_cannot_create_a_second_diagnostic_evidence_plane() -> None:
    text = _text()
    for forbidden_owner in (
        "mastermind.runtime_diagnostic/v1",
        "runtime diagnostic emitter",
        "observability sidecar",
        "OpenTelemetry exporter or collector",
        "runtime probe scheduler",
        "second runtime health or observability read plane",
    ):
        assert forbidden_owner in text

    assert "OLS-A1 remains pure, fixture-driven, standard-library-only" in text
    assert "zero network, socket, subprocess, telemetry" in text


def test_source_compiler_must_use_corrected_canonical_read_seams() -> None:
    text = _text()
    assert "corrected and protected Executive Steward/OCR-6 read seam" in text
    assert "must not side-read raw Grafana/Loki/Prometheus/Jaeger stores" in text
    assert "separately accepted bounded Runtime Observability read contract" in text
    assert "UNAVAILABLE" in text
    assert "never become healthy defaults" in text


def test_runtime_diagnostics_never_originate_lifecycle_or_assurance_truth() -> None:
    text = _text()
    for forbidden_inference in (
        "Job, Attempt or Worker completion",
        "retry safety",
        "RuntimeBinding",
        "effect reconciliation",
        "target ACK/consumption",
        "parent continuation",
    ):
        assert forbidden_inference in text

    assert "a log/metric/trace cannot originate the canonical divergence fact by itself" in text


def test_ols_a2_and_a6_gates_are_explicit() -> None:
    text = _text()
    assert "OLS-A2 remains additionally blocked on corrected Steward" in text
    assert "an accepted observability read contract" in text
    assert "Runtime conformance stays separate from diagnostic collection" in text
    assert "creates no probe, collector, sidecar or telemetry alert" in text
