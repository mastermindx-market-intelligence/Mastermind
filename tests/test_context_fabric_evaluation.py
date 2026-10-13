from __future__ import annotations

import copy

import pytest

from control_plane.context_fabric_evaluation import (
    ContextFabricEvaluationError,
    REQUIRED_TASK_FAMILIES,
    RUN_SCHEMA,
    evaluate_runs,
)


def _run(
    case_id, family, cohort, *, calls, bytes_, accepted=True, observed=None, **counts
):
    expected = (f"critical:{case_id}:law", f"critical:{case_id}:carrier")
    return {
        "schema": RUN_SCHEMA,
        "run_id": f"{case_id}:{cohort}",
        "case_id": case_id,
        "task_family": family,
        "cohort": cohort,
        "accepted_outcome": accepted,
        "prework_tool_calls": calls,
        "prework_retrieved_bytes": bytes_,
        "critical_refs_expected": list(expected),
        "critical_refs_observed": list(expected if observed is None else observed),
        "stale_owner_errors": counts.get("stale_owner_errors", 0),
        "collision_misses": counts.get("collision_misses", 0),
        "invalidator_false_positives": counts.get("invalidator_false_positives", 0),
        "invalidator_false_negatives": counts.get("invalidator_false_negatives", 0),
        "authority_violations": counts.get("authority_violations", 0),
    }


def _full_candidate():
    rows = []
    for index, family in enumerate(sorted(REQUIRED_TASK_FAMILIES), start=1):
        case = f"case-{index}"
        rows.append(_run(case, family, "EXHAUSTIVE", calls=10, bytes_=100_000))
        rows.append(_run(case, family, "CONTEXT_FABRIC", calls=3, bytes_=30_000))
    return rows


def test_full_qualified_candidate_passes():
    result = evaluate_runs(_full_candidate())
    assert result["status"] == "PASS"
    assert result["matched_cases"] == 8
    assert result["metrics"]["critical_ref_recall"] == 1.0
    assert result["metrics"]["median_prework_tool_calls"][
        "reduction_fraction"
    ] == pytest.approx(0.7)
    assert result["metrics"]["median_prework_retrieved_bytes"][
        "reduction_fraction"
    ] == pytest.approx(0.7)
    assert all(result["gates"].values())


def test_missing_task_family_fails():
    rows = _full_candidate()[:-2]
    result = evaluate_runs(rows)
    assert result["status"] == "FAIL"
    assert result["gates"]["all_task_families_represented"] is False
    assert len(result["missing_task_families"]) == 1


@pytest.mark.parametrize(
    ("field", "gate"),
    [
        ("authority_violations", "zero_authority_violations"),
        ("stale_owner_errors", "zero_stale_owner_errors"),
        ("collision_misses", "zero_collision_misses"),
        ("invalidator_false_negatives", "zero_invalidator_false_negatives"),
    ],
)
def test_guardrail_violation_fails(field, gate):
    rows = _full_candidate()
    for row in rows:
        if row["cohort"] == "CONTEXT_FABRIC":
            row[field] = 1
            break
    result = evaluate_runs(rows)
    assert result["status"] == "FAIL"
    assert result["gates"][gate] is False


def test_critical_ref_miss_fails():
    rows = _full_candidate()
    candidate = next(row for row in rows if row["cohort"] == "CONTEXT_FABRIC")
    candidate["critical_refs_observed"] = candidate["critical_refs_observed"][:-1]
    result = evaluate_runs(rows)
    assert result["status"] == "FAIL"
    assert result["gates"]["critical_ref_recall_100pct"] is False


def test_efficiency_below_threshold_fails():
    rows = []
    for index, family in enumerate(sorted(REQUIRED_TASK_FAMILIES), start=1):
        case = f"case-{index}"
        rows.append(_run(case, family, "EXHAUSTIVE", calls=10, bytes_=100_000))
        rows.append(_run(case, family, "CONTEXT_FABRIC", calls=5, bytes_=50_000))
    result = evaluate_runs(rows)
    assert result["status"] == "FAIL"
    assert result["gates"]["median_tool_call_reduction_ge_60pct"] is False
    assert result["gates"]["median_retrieved_byte_reduction_ge_60pct"] is False


def test_candidate_acceptance_cannot_be_worse():
    rows = _full_candidate()
    candidate = next(row for row in rows if row["cohort"] == "CONTEXT_FABRIC")
    candidate["accepted_outcome"] = False
    result = evaluate_runs(rows)
    assert result["status"] == "FAIL"
    assert result["gates"]["candidate_acceptance_not_worse"] is False


def test_unmatched_runs_do_not_fake_family_coverage():
    rows = _full_candidate()
    rows = rows[:-2]
    rows.append(
        _run(
            "unmatched",
            sorted(REQUIRED_TASK_FAMILIES)[-1],
            "CONTEXT_FABRIC",
            calls=1,
            bytes_=1,
        )
    )
    result = evaluate_runs(rows)
    assert result["gates"]["all_task_families_represented"] is False


def test_mismatched_critical_contract_is_refused():
    rows = _full_candidate()
    candidate = next(row for row in rows if row["cohort"] == "CONTEXT_FABRIC")
    candidate["critical_refs_expected"] = ["different"]
    with pytest.raises(ContextFabricEvaluationError, match="critical-ref"):
        evaluate_runs(rows)


def test_duplicate_run_id_is_refused():
    rows = _full_candidate()
    duplicate = copy.deepcopy(rows[0])
    duplicate["case_id"] = "other-case"
    rows.append(duplicate)
    with pytest.raises(ContextFabricEvaluationError, match="duplicate run_id"):
        evaluate_runs(rows)


def test_empty_input_is_refused():
    with pytest.raises(ContextFabricEvaluationError, match="collection"):
        evaluate_runs([])


def test_false_positives_are_reported_but_not_release_blocking_by_themselves():
    rows = _full_candidate()
    candidate = next(row for row in rows if row["cohort"] == "CONTEXT_FABRIC")
    candidate["invalidator_false_positives"] = 2
    result = evaluate_runs(rows)
    assert result["status"] == "PASS"
    assert result["metrics"]["guardrails"]["invalidator_false_positives"] == 2
