"""tests.test_operation_assurance_report — OLS-A1 immutable report wire contract.

Covers the exact top-level/nested report wire, non-circular content-addressed
identity, orthogonal axes, and the cross-field anti-inflation invariants from
docs/superpowers/specs/2026-08-30-operation-assurance-immutable-report-projection-clarification.md
(the highest-precedence wire authority after the 2026-08-31 finalization,
which changes only the top-level field *order*, already reflected here) plus
docs/superpowers/specs/2026-08-31-operation-assurance-a1-wire-release-finalization.md
(`repair_scope` removed).
"""
from __future__ import annotations

import re

import pytest

from control_plane.operation_assurance_report import (
    ReportValidationError,
    build_report,
    ExplorationReceipt,
    AnalysisProduct,
    Coverage,
    Assumptions,
    PropertyResult,
    Counterexample,
    RepairCandidate,
    StateDeltaStep,
    Change,
    TransitionReasonSnapshot,
    DisabledTransition,
    GuardFailure,
)
from control_plane.operation_assurance_model import parse_model_text, sha256_hex, canonical_json
from tests.operation_assurance_fixture_lib import dumps, minimal_model

GENERATED_AT = "2026-08-30T12:00:00Z"


def _model():
    return parse_model_text(dumps(minimal_model()))


def _receipt(**overrides) -> ExplorationReceipt:
    base = dict(
        checker_terminated_normally=True,
        base_graph_complete=True,
        declared_limits={"max_states": 1000, "max_depth": 1000},
        states_discovered=2,
        edges_materialized=1,
        transitions_considered=1,
        maximum_depth_reached=1,
        peak_frontier=1,
        state_limit_reached=False,
        depth_limit_reached=False,
        analysis_products=(
            AnalysisProduct("OPTION_TO_COMPLETE", True, 2, 1, None),
        ),
    )
    base.update(overrides)
    return ExplorationReceipt(**base)


def _coverage(evaluated: list[str], complete: list[str], not_applicable: list[str] | None = None) -> Coverage:
    not_applicable = not_applicable or []
    incomplete = [p for p in evaluated if p not in complete and p not in not_applicable]
    return Coverage(
        mandatory_property_ids=tuple(sorted(p for p in evaluated if p.isupper())),
        authored_property_ids=(),
        evaluated_property_ids=tuple(sorted(evaluated)),
        complete_property_ids=tuple(sorted(complete)),
        incomplete_property_ids=tuple(sorted(incomplete)),
        not_applicable_property_ids=tuple(sorted(not_applicable)),
    )


def _assumptions() -> Assumptions:
    return Assumptions((), (), (), ())


_ALL_GENERIC = sorted(
    {
        "OPTION_TO_COMPLETE",
        "PROPER_COMPLETION",
        "NO_DEAD_REQUIRED_TRANSITION",
        "NO_POST_TERMINAL_TRANSITION",
        "GATE_OR_WAIT_RETURN_PATH_VALID",
        "UNIVERSAL_PROGRESS",
        "RECURRING_PROGRESS_VALID",
        "NO_STARVATION_UNDER_DECLARED_FAIRNESS",
        "FAIRNESS_REALIZABLE",
    }
)


def _all_pass_results() -> tuple[PropertyResult, ...]:
    out = []
    for pid in _ALL_GENERIC:
        na = pid in ("RECURRING_PROGRESS_VALID", "NO_STARVATION_UNDER_DECLARED_FAIRNESS", "FAIRNESS_REALIZABLE")
        out.append(
            PropertyResult(
                property_id=pid,
                property_kind=pid,
                status="NOT_APPLICABLE" if na else "PASS",
                analysis_complete=True,
                counterexample_id=None,
                reason_codes=("NO_RELEVANT_DECLARATION",) if na else (),
                source_refs=(),
            )
        )
    return tuple(out)


def _proven_kwargs():
    model = _model()
    return dict(
        model_id=model.model_id,
        model_hash=model.model_hash,
        source_snapshot_hash=model.source_snapshot.snapshot_hash,
        checker_version="ols-a1-0.1.0",
        property_set_version="mastermind.operation_assurance.properties.v1",
        model_analysis_verdict="PROVEN_WITHIN_FINITE_MODEL",
        source_applicability_at_generation="AUTHOR_DECLARED_ONLY",
        abstraction_contract=model.abstraction_contract,
        progress_disposition="AUTONOMOUSLY_LIVE",
        admission_recommendation="REPORT_ONLY_NO_RECOMMENDATION",
        property_results=_all_pass_results(),
        counterexamples=(),
        coverage=_coverage(_ALL_GENERIC, [p for p in _ALL_GENERIC if p not in ("RECURRING_PROGRESS_VALID", "NO_STARVATION_UNDER_DECLARED_FAIRNESS", "FAIRNESS_REALIZABLE")], ["RECURRING_PROGRESS_VALID", "NO_STARVATION_UNDER_DECLARED_FAIRNESS", "FAIRNESS_REALIZABLE"]),
        assumptions=_assumptions(),
        known_model_gaps=(),
        exploration_receipt=_receipt(),
        generated_at=GENERATED_AT,
        supersedes_report_id=None,
    )


def test_proven_report_builds() -> None:
    r = build_report(**_proven_kwargs())
    assert r.schema == "mastermind.operation_assurance_report.v1"
    assert r.model_analysis_verdict == "PROVEN_WITHIN_FINITE_MODEL"
    assert r.report_id.startswith("oar_")
    assert r.report_hash


def test_report_field_order_matches_finalization() -> None:
    r = build_report(**_proven_kwargs())
    d = r.to_dict()
    assert list(d.keys()) == [
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
    ]


def test_withdrawn_fields_never_appear() -> None:
    r = build_report(**_proven_kwargs())
    d = r.to_dict()
    for withdrawn in (
        "assurance_verdict",
        "current_projection_verdict",
        "source_applicability",
        "current_assurance_status",
        "current_recommendation",
        "computed_at",
        "duration_ms",
        "repair_scope",
    ):
        assert withdrawn not in d


def test_report_only_procced_is_not_a_legal_recommendation() -> None:
    kwargs = _proven_kwargs()
    kwargs["admission_recommendation"] = "REPORT_ONLY_PROCEED"
    with pytest.raises(ReportValidationError):
        build_report(**kwargs)


def test_model_stale_or_invalid_is_not_a_legal_verdict() -> None:
    kwargs = _proven_kwargs()
    kwargs["model_analysis_verdict"] = "MODEL_STALE_OR_INVALID"
    with pytest.raises(ReportValidationError):
        build_report(**kwargs)


def test_report_hash_excludes_report_id_and_report_hash() -> None:
    r = build_report(**_proven_kwargs())
    d = r.to_dict()
    body = {k: v for k, v in d.items() if k not in ("report_id", "report_hash")}
    assert r.report_hash == sha256_hex(canonical_json(body))
    assert r.report_id == "oar_" + r.report_hash[:24]


def test_fixed_input_and_generated_at_is_byte_identical() -> None:
    r1 = build_report(**_proven_kwargs())
    r2 = build_report(**_proven_kwargs())
    assert r1.to_json() == r2.to_json()


def test_no_wall_clock_duration_in_canonical_output() -> None:
    r = build_report(**_proven_kwargs())
    assert "duration_ms" not in r.to_json()


def test_bad_generated_at_format_is_refused() -> None:
    kwargs = _proven_kwargs()
    kwargs["generated_at"] = "2026-08-30 12:00:00"
    with pytest.raises(ReportValidationError):
        build_report(**kwargs)


def test_generated_at_must_be_second_precision_utc_z() -> None:
    assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$", GENERATED_AT)
    kwargs = _proven_kwargs()
    kwargs["generated_at"] = "2026-08-30T12:00:00.123Z"
    with pytest.raises(ReportValidationError):
        build_report(**kwargs)


def test_unsafe_verdict_requires_at_least_one_failed_property() -> None:
    kwargs = _proven_kwargs()
    kwargs["model_analysis_verdict"] = "UNSAFE_COUNTEREXAMPLE"
    with pytest.raises(ReportValidationError):
        build_report(**kwargs)


def test_proven_verdict_requires_all_pass_or_legal_not_applicable() -> None:
    kwargs = _proven_kwargs()
    results = list(kwargs["property_results"])
    results[0] = PropertyResult(
        property_id=results[0].property_id,
        property_kind=results[0].property_kind,
        status="UNKNOWN",
        analysis_complete=False,
        counterexample_id=None,
        reason_codes=(),
        source_refs=(),
    )
    kwargs["property_results"] = tuple(results)
    kwargs["coverage"] = _coverage(
        _ALL_GENERIC,
        [p for p in _ALL_GENERIC if p != results[0].property_id and p not in ("RECURRING_PROGRESS_VALID", "NO_STARVATION_UNDER_DECLARED_FAIRNESS", "FAIRNESS_REALIZABLE")],
        ["RECURRING_PROGRESS_VALID", "NO_STARVATION_UNDER_DECLARED_FAIRNESS", "FAIRNESS_REALIZABLE"],
    )
    with pytest.raises(ReportValidationError):
        build_report(**kwargs)


def test_proven_verdict_requires_complete_base_graph() -> None:
    kwargs = _proven_kwargs()
    kwargs["exploration_receipt"] = _receipt(base_graph_complete=False)
    with pytest.raises(ReportValidationError):
        build_report(**kwargs)


def test_proven_verdict_requires_checker_terminated_normally() -> None:
    kwargs = _proven_kwargs()
    kwargs["exploration_receipt"] = _receipt(checker_terminated_normally=False)
    with pytest.raises(ReportValidationError):
        build_report(**kwargs)


def test_bounded_verdict_requires_a_declared_resource_bound_receipt() -> None:
    kwargs = _proven_kwargs()
    kwargs["model_analysis_verdict"] = "BOUNDED_NO_COUNTEREXAMPLE"
    kwargs["admission_recommendation"] = "REPORT_ONLY_NO_RECOMMENDATION"
    # no state/depth/product limit reached anywhere -> refused
    with pytest.raises(ReportValidationError):
        build_report(**kwargs)


def test_bounded_verdict_with_declared_bound_receipt_builds() -> None:
    kwargs = _proven_kwargs()
    kwargs["model_analysis_verdict"] = "BOUNDED_NO_COUNTEREXAMPLE"
    kwargs["admission_recommendation"] = "REPORT_ONLY_NO_RECOMMENDATION"
    results = list(kwargs["property_results"])
    results[0] = PropertyResult(
        property_id=results[0].property_id,
        property_kind=results[0].property_kind,
        status="UNKNOWN",
        analysis_complete=False,
        counterexample_id=None,
        reason_codes=("STATE_LIMIT_REACHED",),
        source_refs=(),
    )
    kwargs["property_results"] = tuple(results)
    kwargs["exploration_receipt"] = _receipt(base_graph_complete=False, state_limit_reached=True)
    changed_id = results[0].property_id
    na_ids = [
        p
        for p in ("RECURRING_PROGRESS_VALID", "NO_STARVATION_UNDER_DECLARED_FAIRNESS", "FAIRNESS_REALIZABLE")
        if p != changed_id
    ]
    kwargs["coverage"] = _coverage(
        _ALL_GENERIC,
        [p for p in _ALL_GENERIC if p != changed_id and p not in na_ids],
        na_ids,
    )
    r = build_report(**kwargs)
    assert r.model_analysis_verdict == "BOUNDED_NO_COUNTEREXAMPLE"


def test_duplicate_property_result_id_is_refused() -> None:
    kwargs = _proven_kwargs()
    kwargs["property_results"] = kwargs["property_results"] + (kwargs["property_results"][0],)
    with pytest.raises(ReportValidationError):
        build_report(**kwargs)


def test_illegal_not_applicable_is_refused() -> None:
    kwargs = _proven_kwargs()
    results = list(kwargs["property_results"])
    for i, r in enumerate(results):
        if r.property_id == "OPTION_TO_COMPLETE":
            results[i] = PropertyResult(
                property_id=r.property_id,
                property_kind=r.property_kind,
                status="NOT_APPLICABLE",
                analysis_complete=True,
                counterexample_id=None,
                reason_codes=(),
                source_refs=(),
            )
    kwargs["property_results"] = tuple(results)
    with pytest.raises(ReportValidationError):
        build_report(**kwargs)


def test_missing_mandatory_property_result_is_refused() -> None:
    kwargs = _proven_kwargs()
    kwargs["property_results"] = tuple(r for r in kwargs["property_results"] if r.property_id != "OPTION_TO_COMPLETE")
    with pytest.raises(ReportValidationError):
        build_report(**kwargs)


def _unsafe_counterexample(model_hash: str, *, realizability="DECLARED_MODEL_ONLY") -> Counterexample:
    body_without_id = dict(
        witness_kind="TRACE",
        property_id="OPTION_TO_COMPLETE",
        realizability=realizability,
        validation_refs=(),
        invalidating_gap_ids=(),
        initial_state=(("phase", "START"),),
        shortest_prefix=("finish",),
        cycle=(),
        state_delta_per_step=(
            StateDeltaStep(
                segment="PREFIX",
                step_index=0,
                from_state_fingerprint="f0",
                transition_id="finish",
                to_state_fingerprint="f1",
                changes=(Change("phase", "START", "DONE"),),
            ),
        ),
        enabled_and_disabled_transition_reasons=(
            TransitionReasonSnapshot(
                segment="PREFIX",
                step_index=0,
                state_fingerprint="f0",
                enabled_transition_ids=("finish",),
                disabled_transitions=(),
            ),
        ),
        source_refs=(),
        repair_candidates=(RepairCandidate("rep_1", "ADD_OR_CORRECT_TRANSITION", ("finish",), "fix it", ()),),
        limitations=(),
    )
    from control_plane.operation_assurance_report import compute_counterexample_id

    placeholder = Counterexample(counterexample_id="ocx_placeholder", **body_without_id)
    serialized_body = {k: v for k, v in placeholder.to_dict().items() if k != "counterexample_id"}
    cid = compute_counterexample_id(model_hash, serialized_body)
    return Counterexample(counterexample_id=cid, **body_without_id)


def test_unsafe_report_with_matching_counterexample_builds() -> None:
    model = _model()
    kwargs = _proven_kwargs()
    cx = _unsafe_counterexample(model.model_hash)
    results = list(kwargs["property_results"])
    for i, r in enumerate(results):
        if r.property_id == "OPTION_TO_COMPLETE":
            results[i] = PropertyResult(
                property_id=r.property_id,
                property_kind=r.property_kind,
                status="FAIL",
                analysis_complete=True,
                counterexample_id=cx.counterexample_id,
                reason_codes=(),
                source_refs=(),
            )
    kwargs["property_results"] = tuple(results)
    kwargs["counterexamples"] = (cx,)
    kwargs["model_analysis_verdict"] = "UNSAFE_COUNTEREXAMPLE"
    kwargs["progress_disposition"] = "NO_PROGRESS"
    kwargs["admission_recommendation"] = "REPORT_ONLY_REPAIR"
    r = build_report(**kwargs)
    assert r.model_analysis_verdict == "UNSAFE_COUNTEREXAMPLE"
    assert r.counterexamples[0].counterexample_id.startswith("ocx_")


def test_counterexample_id_excludes_itself_from_hash() -> None:
    model = _model()
    cx = _unsafe_counterexample(model.model_hash)
    body = {k: v for k, v in cx.to_dict().items() if k != "counterexample_id"}
    from control_plane.operation_assurance_report import compute_counterexample_id

    assert cx.counterexample_id == compute_counterexample_id(model.model_hash, body)


def test_unreferenced_counterexample_is_refused() -> None:
    model = _model()
    kwargs = _proven_kwargs()
    cx = _unsafe_counterexample(model.model_hash)
    kwargs["counterexamples"] = (cx,)
    # no property_result references it -> refused regardless of verdict
    with pytest.raises(ReportValidationError):
        build_report(**kwargs)


def test_pass_result_must_not_reference_a_counterexample() -> None:
    kwargs = _proven_kwargs()
    results = list(kwargs["property_results"])
    results[0] = PropertyResult(
        property_id=results[0].property_id,
        property_kind=results[0].property_kind,
        status="PASS",
        analysis_complete=True,
        counterexample_id="ocx_deadbeefdeadbeefdeadbeef",
        reason_codes=(),
        source_refs=(),
    )
    kwargs["property_results"] = tuple(results)
    with pytest.raises(ReportValidationError):
        build_report(**kwargs)


def test_coverage_and_property_results_must_agree() -> None:
    kwargs = _proven_kwargs()
    bad_coverage = kwargs["coverage"]
    kwargs["coverage"] = Coverage(
        mandatory_property_ids=bad_coverage.mandatory_property_ids,
        authored_property_ids=(),
        evaluated_property_ids=bad_coverage.evaluated_property_ids,
        complete_property_ids=("SOME_UNKNOWN_ID",),
        incomplete_property_ids=bad_coverage.incomplete_property_ids,
        not_applicable_property_ids=bad_coverage.not_applicable_property_ids,
    )
    with pytest.raises(ReportValidationError):
        build_report(**kwargs)
