"""Pure evaluator for Mastermind Context Fabric cold-start benchmarks.

The evaluator consumes explicit exported run evidence. It owns no telemetry store,
runtime, task scheduler, model route, context cache, or source of truth.
"""

from __future__ import annotations

import dataclasses
import statistics
from collections.abc import Mapping, Sequence
from typing import Any

RUN_SCHEMA = "mastermind.context_fabric_eval_run.v1"
RESULT_SCHEMA = "mastermind.context_fabric_eval_result.v1"
COHORTS = frozenset({"EXHAUSTIVE", "CONTEXT_FABRIC"})
REQUIRED_TASK_FAMILIES = frozenset(
    {
        "source_implementation_debugging",
        "cross_repo_architecture",
        "program_recovery",
        "research_retrieval",
        "runtime_incident",
        "active_pr_continuation",
        "local_dirty_worktree_continuation",
        "historical_plan_recovery",
    }
)
MAX_RUNS = 4096
MAX_REFS = 512


class ContextFabricEvaluationError(ValueError):
    """Evaluation evidence is malformed or incomparable."""


@dataclasses.dataclass(frozen=True)
class EvaluationRun:
    run_id: str
    case_id: str
    task_family: str
    cohort: str
    accepted_outcome: bool
    prework_tool_calls: int
    prework_retrieved_bytes: int
    critical_refs_expected: tuple[str, ...]
    critical_refs_observed: tuple[str, ...]
    stale_owner_errors: int
    collision_misses: int
    invalidator_false_positives: int
    invalidator_false_negatives: int
    authority_violations: int

    def __post_init__(self) -> None:
        for label, value in (
            ("run_id", self.run_id),
            ("case_id", self.case_id),
            ("task_family", self.task_family),
            ("cohort", self.cohort),
        ):
            if (
                type(value) is not str
                or not value
                or "\x00" in value
                or len(value.encode("utf-8")) > 256
            ):
                raise ContextFabricEvaluationError(f"{label} is invalid")
        if self.cohort not in COHORTS:
            raise ContextFabricEvaluationError("cohort is invalid")
        if self.task_family not in REQUIRED_TASK_FAMILIES:
            raise ContextFabricEvaluationError(
                "task_family is not in the benchmark contract"
            )
        if type(self.accepted_outcome) is not bool:
            raise ContextFabricEvaluationError("accepted_outcome must be boolean")
        for label, value in (
            ("prework_tool_calls", self.prework_tool_calls),
            ("prework_retrieved_bytes", self.prework_retrieved_bytes),
            ("stale_owner_errors", self.stale_owner_errors),
            ("collision_misses", self.collision_misses),
            ("invalidator_false_positives", self.invalidator_false_positives),
            ("invalidator_false_negatives", self.invalidator_false_negatives),
            ("authority_violations", self.authority_violations),
        ):
            if type(value) is not int or isinstance(value, bool) or value < 0:
                raise ContextFabricEvaluationError(
                    f"{label} must be a non-negative integer"
                )
        for label, values in (
            ("critical_refs_expected", self.critical_refs_expected),
            ("critical_refs_observed", self.critical_refs_observed),
        ):
            if (
                type(values) is not tuple
                or len(values) > MAX_REFS
                or len(values) != len(set(values))
                or any(
                    type(item) is not str
                    or not item
                    or "\x00" in item
                    or len(item.encode("utf-8")) > 512
                    for item in values
                )
            ):
                raise ContextFabricEvaluationError(f"{label} is invalid")


def load_run(value: object) -> EvaluationRun:
    if not isinstance(value, Mapping) or value.get("schema") != RUN_SCHEMA:
        raise ContextFabricEvaluationError("run schema is invalid")
    expected = {
        "schema",
        "run_id",
        "case_id",
        "task_family",
        "cohort",
        "accepted_outcome",
        "prework_tool_calls",
        "prework_retrieved_bytes",
        "critical_refs_expected",
        "critical_refs_observed",
        "stale_owner_errors",
        "collision_misses",
        "invalidator_false_positives",
        "invalidator_false_negatives",
        "authority_violations",
    }
    if set(value) != expected:
        raise ContextFabricEvaluationError("run shape is invalid")
    try:
        return EvaluationRun(
            run_id=value["run_id"],  # type: ignore[arg-type]
            case_id=value["case_id"],  # type: ignore[arg-type]
            task_family=value["task_family"],  # type: ignore[arg-type]
            cohort=value["cohort"],  # type: ignore[arg-type]
            accepted_outcome=value["accepted_outcome"],  # type: ignore[arg-type]
            prework_tool_calls=value["prework_tool_calls"],  # type: ignore[arg-type]
            prework_retrieved_bytes=value["prework_retrieved_bytes"],  # type: ignore[arg-type]
            critical_refs_expected=tuple(value["critical_refs_expected"]),  # type: ignore[arg-type]
            critical_refs_observed=tuple(value["critical_refs_observed"]),  # type: ignore[arg-type]
            stale_owner_errors=value["stale_owner_errors"],  # type: ignore[arg-type]
            collision_misses=value["collision_misses"],  # type: ignore[arg-type]
            invalidator_false_positives=value["invalidator_false_positives"],  # type: ignore[arg-type]
            invalidator_false_negatives=value["invalidator_false_negatives"],  # type: ignore[arg-type]
            authority_violations=value["authority_violations"],  # type: ignore[arg-type]
        )
    except (KeyError, TypeError):
        raise ContextFabricEvaluationError("run shape is invalid") from None


def _reduction(baseline: float, candidate: float) -> float | None:
    if baseline <= 0:
        return None
    return (baseline - candidate) / baseline


def _critical_recall(run: EvaluationRun) -> tuple[int, int]:
    expected = set(run.critical_refs_expected)
    observed = set(run.critical_refs_observed)
    return len(expected & observed), len(expected)


def evaluate_runs(values: Sequence[object]) -> dict[str, Any]:
    if (
        not isinstance(values, Sequence)
        or isinstance(values, (str, bytes))
        or not values
        or len(values) > MAX_RUNS
    ):
        raise ContextFabricEvaluationError("run collection is invalid")
    runs = [load_run(value) for value in values]
    run_ids = [run.run_id for run in runs]
    if len(run_ids) != len(set(run_ids)):
        raise ContextFabricEvaluationError("duplicate run_id")

    by_case: dict[str, dict[str, EvaluationRun]] = {}
    for run in runs:
        slot = by_case.setdefault(run.case_id, {})
        if run.cohort in slot:
            raise ContextFabricEvaluationError("case has duplicate cohort run")
        slot[run.cohort] = run

    matched: list[tuple[EvaluationRun, EvaluationRun]] = []
    for case_id, slot in sorted(by_case.items()):
        if set(slot) != COHORTS:
            continue
        baseline = slot["EXHAUSTIVE"]
        candidate = slot["CONTEXT_FABRIC"]
        if baseline.task_family != candidate.task_family:
            raise ContextFabricEvaluationError(
                f"matched case {case_id} changes task_family"
            )
        if baseline.critical_refs_expected != candidate.critical_refs_expected:
            raise ContextFabricEvaluationError(
                f"matched case {case_id} changes critical-ref contract"
            )
        matched.append((baseline, candidate))

    represented = {candidate.task_family for _, candidate in matched}
    missing_families = sorted(REQUIRED_TASK_FAMILIES - represented)

    baseline_calls = [baseline.prework_tool_calls for baseline, _ in matched]
    candidate_calls = [candidate.prework_tool_calls for _, candidate in matched]
    baseline_bytes = [baseline.prework_retrieved_bytes for baseline, _ in matched]
    candidate_bytes = [candidate.prework_retrieved_bytes for _, candidate in matched]

    if matched:
        median_baseline_calls = float(statistics.median(baseline_calls))
        median_candidate_calls = float(statistics.median(candidate_calls))
        median_baseline_bytes = float(statistics.median(baseline_bytes))
        median_candidate_bytes = float(statistics.median(candidate_bytes))
    else:
        median_baseline_calls = median_candidate_calls = 0.0
        median_baseline_bytes = median_candidate_bytes = 0.0

    call_reduction = _reduction(median_baseline_calls, median_candidate_calls)
    byte_reduction = _reduction(median_baseline_bytes, median_candidate_bytes)

    candidate_runs = [candidate for _, candidate in matched]
    critical_hits = 0
    critical_total = 0
    for run in candidate_runs:
        hits, total = _critical_recall(run)
        critical_hits += hits
        critical_total += total
    critical_recall = critical_hits / critical_total if critical_total else 1.0

    candidate_accepted = sum(1 for run in candidate_runs if run.accepted_outcome)
    baseline_accepted = sum(1 for baseline, _ in matched if baseline.accepted_outcome)

    guardrails = {
        "authority_violations": sum(run.authority_violations for run in candidate_runs),
        "stale_owner_errors": sum(run.stale_owner_errors for run in candidate_runs),
        "collision_misses": sum(run.collision_misses for run in candidate_runs),
        "invalidator_false_negatives": sum(
            run.invalidator_false_negatives for run in candidate_runs
        ),
        "invalidator_false_positives": sum(
            run.invalidator_false_positives for run in candidate_runs
        ),
    }

    gates = {
        "all_task_families_represented": not missing_families,
        "critical_ref_recall_100pct": critical_recall == 1.0,
        "zero_authority_violations": guardrails["authority_violations"] == 0,
        "zero_stale_owner_errors": guardrails["stale_owner_errors"] == 0,
        "zero_collision_misses": guardrails["collision_misses"] == 0,
        "zero_invalidator_false_negatives": (
            guardrails["invalidator_false_negatives"] == 0
        ),
        "median_tool_call_reduction_ge_60pct": (
            call_reduction is not None and call_reduction >= 0.60
        ),
        "median_retrieved_byte_reduction_ge_60pct": (
            byte_reduction is not None and byte_reduction >= 0.60
        ),
        "candidate_acceptance_not_worse": candidate_accepted >= baseline_accepted,
    }
    status = "PASS" if all(gates.values()) else "FAIL"
    if not matched:
        status = "INSUFFICIENT_EVIDENCE"

    return {
        "schema": RESULT_SCHEMA,
        "status": status,
        "matched_cases": len(matched),
        "represented_task_families": sorted(represented),
        "missing_task_families": missing_families,
        "metrics": {
            "median_prework_tool_calls": {
                "exhaustive": median_baseline_calls,
                "context_fabric": median_candidate_calls,
                "reduction_fraction": call_reduction,
            },
            "median_prework_retrieved_bytes": {
                "exhaustive": median_baseline_bytes,
                "context_fabric": median_candidate_bytes,
                "reduction_fraction": byte_reduction,
            },
            "critical_ref_recall": critical_recall,
            "accepted_outcomes": {
                "exhaustive": baseline_accepted,
                "context_fabric": candidate_accepted,
            },
            "guardrails": guardrails,
        },
        "gates": gates,
    }
