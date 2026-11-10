"""control_plane.operation_assurance_report — OLS-A1 immutable report wire (OLS-F0).

Builds and validates one ``mastermind.operation_assurance_report.v1`` value
per the controlling wire authority
(``docs/superpowers/specs/2026-08-30-operation-assurance-immutable-report-projection-clarification.md``,
top-level field order corrected by
``docs/superpowers/specs/2026-08-31-operation-assurance-a1-wire-release-finalization.md``
Section 2).

The report is content-addressed and non-circular: ``report_hash`` is computed
over the canonical body excluding ``report_id``/``report_hash`` themselves;
``report_id`` is then derived from that hash. The same non-circular law
applies per-counterexample. No wall-clock duration enters the canonical
body. This module performs zero I/O and is standard-library only.
"""
from __future__ import annotations

import dataclasses
import re
from typing import Any

from control_plane.operation_assurance_model import (
    AbstractionContract,
    ModelGap,
    canonical_json,
    sha256_hex,
)

SCHEMA = "mastermind.operation_assurance_report.v1"

MODEL_ANALYSIS_VERDICTS = frozenset(
    {
        "UNSAFE_COUNTEREXAMPLE",
        "PROVEN_WITHIN_FINITE_MODEL",
        "BOUNDED_NO_COUNTEREXAMPLE",
        "INCONCLUSIVE_MODEL_GAP",
    }
)
SOURCE_APPLICABILITY_VALUES = frozenset(
    {
        "AUTHOR_DECLARED_ONLY",
        "CURRENT_SOURCE_ATTESTED",
        "HISTORICAL_SOURCE_ATTESTED",
        "STALE",
        "CONFLICTED",
        "INCOMPLETE",
        "UNKNOWN",
    }
)
PROGRESS_DISPOSITIONS = frozenset(
    {
        "AUTONOMOUSLY_LIVE",
        "FAIRNESS_CONDITIONAL",
        "EXTERNALLY_GATED",
        "INTENTIONAL_WAIT",
        "RECURRING_SERVICE",
        "NO_PROGRESS",
        "UNKNOWN",
    }
)
# OLS-A1 never emits REPORT_ONLY_PROCEED: it is not a member of this closed set.
ADMISSION_RECOMMENDATIONS = frozenset(
    {
        "REPORT_ONLY_REPAIR",
        "REPORT_ONLY_RECONCILE",
        "REPORT_ONLY_AWAIT_GATE",
        "REPORT_ONLY_NO_RECOMMENDATION",
    }
)
PROPERTY_STATUSES = frozenset({"PASS", "FAIL", "UNKNOWN", "NOT_APPLICABLE"})
PROPERTY_KINDS = frozenset(
    {
        "AUTHORED_STATE_SAFETY",
        "AUTHORED_TRANSITION_SAFETY",
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
_NOT_APPLICABLE_ELIGIBLE = frozenset(
    {"RECURRING_PROGRESS_VALID", "NO_STARVATION_UNDER_DECLARED_FAIRNESS", "FAIRNESS_REALIZABLE"}
)
_GENERIC_MANDATORY = frozenset(
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
WITNESS_KINDS = frozenset({"TRACE", "LASSO", "GLOBAL_CERTIFICATE"})
REALIZABILITY_VALUES = frozenset(
    {
        "DECLARED_MODEL_ONLY",
        "SOURCE_CONTRACT_VALIDATED",
        "RUNTIME_REPLAY_CONFIRMED",
        "POTENTIALLY_SPURIOUS",
        "INVALIDATED",
    }
)
# A1 may emit only these two; the wider closed set exists for wire compatibility.
A1_REALIZABILITY_VALUES = frozenset({"DECLARED_MODEL_ONLY", "POTENTIALLY_SPURIOUS"})
REPAIR_KINDS = frozenset(
    {
        "ADD_OR_CORRECT_TRANSITION",
        "DISCHARGE_OBLIGATION",
        "RELEASE_RESOURCE",
        "ADD_OR_CORRECT_TERMINAL_OUTCOME",
        "ADD_OR_CORRECT_RECURRING_OUTCOME",
        "ADD_OR_CORRECT_GATE_RETURN",
        "RECONCILE_SOURCE",
        "RECONCILE_EFFECT",
        "RECONCILE_AUTHORITY_OR_BINDING",
        "REVISE_FAIRNESS_ASSUMPTION",
        "REDUCE_MODEL_GAP",
        "INCREASE_DECLARED_BOUND",
    }
)
LIMIT_REASONS = frozenset(
    {
        "STATE_LIMIT_REACHED",
        "DEPTH_LIMIT_REACHED",
        "FAIRNESS_PRODUCT_STATE_LIMIT_REACHED",
        "DEPENDENT_ANALYSIS_INCOMPLETE",
    }
)
SEGMENTS = frozenset({"PREFIX", "CYCLE"})
REASON_SEGMENTS = frozenset({"PREFIX", "CYCLE", "FINAL"})

_GENERATED_AT_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


class ReportValidationError(ValueError):
    def __init__(self, reason_code: str, message: str, path: str = ""):
        self.reason_code = reason_code
        self.path = path
        super().__init__(f"{reason_code} at {path or '<root>'}: {message}")


def _fail(reason_code: str, message: str, path: str = "") -> "ReportValidationError":
    return ReportValidationError(reason_code, message, path)


def _dc_to_dict(value: Any) -> Any:
    if dataclasses.is_dataclass(value):
        return {f.name: _dc_to_dict(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, tuple):
        return [_dc_to_dict(v) for v in value]
    return value


# ---------------------------------------------------------------------------
# Nested value objects
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class PropertyResult:
    property_id: str
    property_kind: str
    status: str
    analysis_complete: bool
    counterexample_id: str | None
    reason_codes: tuple[str, ...]
    source_refs: tuple[str, ...]


@dataclasses.dataclass(frozen=True)
class Change:
    variable: str
    before: str
    after: str


@dataclasses.dataclass(frozen=True)
class StateDeltaStep:
    segment: str
    step_index: int
    from_state_fingerprint: str
    transition_id: str
    to_state_fingerprint: str
    changes: tuple[Change, ...]


@dataclasses.dataclass(frozen=True)
class GuardFailure:
    variable: str
    op: str
    expected: str
    actual: str


@dataclasses.dataclass(frozen=True)
class DisabledTransition:
    transition_id: str
    reason_codes: tuple[str, ...]
    guard_failures: tuple[GuardFailure, ...]


@dataclasses.dataclass(frozen=True)
class TransitionReasonSnapshot:
    segment: str
    step_index: int
    state_fingerprint: str
    enabled_transition_ids: tuple[str, ...]
    disabled_transitions: tuple[DisabledTransition, ...]


@dataclasses.dataclass(frozen=True)
class RepairCandidate:
    repair_id: str
    kind: str
    target_ids: tuple[str, ...]
    summary: str
    source_refs: tuple[str, ...]


@dataclasses.dataclass(frozen=True)
class Counterexample:
    counterexample_id: str
    witness_kind: str
    property_id: str
    realizability: str
    validation_refs: tuple[str, ...]
    invalidating_gap_ids: tuple[str, ...]
    initial_state: tuple[tuple[str, str], ...]
    shortest_prefix: tuple[str, ...]
    cycle: tuple[str, ...]
    state_delta_per_step: tuple[StateDeltaStep, ...]
    enabled_and_disabled_transition_reasons: tuple[TransitionReasonSnapshot, ...]
    source_refs: tuple[str, ...]
    repair_candidates: tuple[RepairCandidate, ...]
    limitations: tuple[str, ...]

    def to_dict(self) -> dict:
        return _dc_to_dict(self)


@dataclasses.dataclass(frozen=True)
class Coverage:
    mandatory_property_ids: tuple[str, ...]
    authored_property_ids: tuple[str, ...]
    evaluated_property_ids: tuple[str, ...]
    complete_property_ids: tuple[str, ...]
    incomplete_property_ids: tuple[str, ...]
    not_applicable_property_ids: tuple[str, ...]


@dataclasses.dataclass(frozen=True)
class Assumptions:
    declared_fairness_assumption_ids: tuple[str, ...]
    fairness_assumption_ids_used_to_exclude_candidates: tuple[str, ...]
    declared_environment_assumption_ids: tuple[str, ...]
    environment_assumption_ids_required_by_results: tuple[str, ...]


@dataclasses.dataclass(frozen=True)
class AnalysisProduct:
    analysis_id: str
    complete: bool
    states_examined: int
    transitions_considered: int
    limit_reason: str | None


@dataclasses.dataclass(frozen=True)
class ExplorationReceipt:
    checker_terminated_normally: bool
    base_graph_complete: bool
    declared_limits: dict
    states_discovered: int
    edges_materialized: int
    transitions_considered: int
    maximum_depth_reached: int
    peak_frontier: int
    state_limit_reached: bool
    depth_limit_reached: bool
    analysis_products: tuple[AnalysisProduct, ...]

    def any_bound_reached(self) -> bool:
        if self.state_limit_reached or self.depth_limit_reached:
            return True
        return any(p.limit_reason is not None for p in self.analysis_products)


# ---------------------------------------------------------------------------
# Report value object
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class OperationAssuranceReport:
    schema: str
    report_id: str
    model_id: str
    model_hash: str
    source_snapshot_hash: str
    checker_version: str
    property_set_version: str
    model_analysis_verdict: str
    source_applicability_at_generation: str
    abstraction_contract: AbstractionContract
    progress_disposition: str
    admission_recommendation: str
    property_results: tuple[PropertyResult, ...]
    counterexamples: tuple[Counterexample, ...]
    coverage: Coverage
    assumptions: Assumptions
    known_model_gaps: tuple[ModelGap, ...]
    exploration_receipt: ExplorationReceipt
    generated_at: str
    supersedes_report_id: str | None
    report_hash: str

    def to_dict(self) -> dict:
        return {
            "schema": self.schema,
            "report_id": self.report_id,
            "model_id": self.model_id,
            "model_hash": self.model_hash,
            "source_snapshot_hash": self.source_snapshot_hash,
            "checker_version": self.checker_version,
            "property_set_version": self.property_set_version,
            "model_analysis_verdict": self.model_analysis_verdict,
            "source_applicability_at_generation": self.source_applicability_at_generation,
            "abstraction_contract": _dc_to_dict(self.abstraction_contract),
            "progress_disposition": self.progress_disposition,
            "admission_recommendation": self.admission_recommendation,
            "property_results": [_dc_to_dict(p) for p in self.property_results],
            "counterexamples": [c.to_dict() for c in self.counterexamples],
            "coverage": _dc_to_dict(self.coverage),
            "assumptions": _dc_to_dict(self.assumptions),
            "known_model_gaps": [_dc_to_dict(g) for g in self.known_model_gaps],
            "exploration_receipt": _dc_to_dict(self.exploration_receipt),
            "generated_at": self.generated_at,
            "supersedes_report_id": self.supersedes_report_id,
            "report_hash": self.report_hash,
        }

    def to_json(self) -> str:
        return canonical_json(self.to_dict())


def compute_counterexample_id(model_hash: str, body_without_id: dict) -> str:
    payload = {"model_hash": model_hash, "counterexample": body_without_id}
    h = sha256_hex(canonical_json(payload))
    return "ocx_" + h[:24]


# ---------------------------------------------------------------------------
# build_report — validate + finalize identity
# ---------------------------------------------------------------------------


def build_report(
    *,
    model_id: str,
    model_hash: str,
    source_snapshot_hash: str,
    checker_version: str,
    property_set_version: str,
    model_analysis_verdict: str,
    source_applicability_at_generation: str,
    abstraction_contract: AbstractionContract,
    progress_disposition: str,
    admission_recommendation: str,
    property_results: tuple[PropertyResult, ...],
    counterexamples: tuple[Counterexample, ...],
    coverage: Coverage,
    assumptions: Assumptions,
    known_model_gaps: tuple[ModelGap, ...],
    exploration_receipt: ExplorationReceipt,
    generated_at: str,
    supersedes_report_id: str | None = None,
) -> OperationAssuranceReport:
    if model_analysis_verdict not in MODEL_ANALYSIS_VERDICTS:
        raise _fail("UNKNOWN_ENUM_VALUE", "not a legal model_analysis_verdict", "model_analysis_verdict")
    if source_applicability_at_generation not in SOURCE_APPLICABILITY_VALUES:
        raise _fail("UNKNOWN_ENUM_VALUE", "not a legal source_applicability_at_generation", "source_applicability_at_generation")
    if progress_disposition not in PROGRESS_DISPOSITIONS:
        raise _fail("UNKNOWN_ENUM_VALUE", "not a legal progress_disposition", "progress_disposition")
    if admission_recommendation not in ADMISSION_RECOMMENDATIONS:
        raise _fail("UNKNOWN_ENUM_VALUE", "not a legal admission_recommendation (A1 never emits REPORT_ONLY_PROCEED)", "admission_recommendation")
    if not _GENERATED_AT_RE.match(generated_at):
        raise _fail("BAD_GENERATED_AT", "generated_at must be second-precision UTC ...Z", "generated_at")

    _validate_property_results(property_results, coverage)
    _validate_counterexamples(counterexamples, property_results, model_hash)
    _validate_coverage(coverage, property_results)
    _validate_verdict_preconditions(
        model_analysis_verdict, property_results, exploration_receipt, abstraction_contract, known_model_gaps, counterexamples
    )

    body = {
        "schema": SCHEMA,
        "model_id": model_id,
        "model_hash": model_hash,
        "source_snapshot_hash": source_snapshot_hash,
        "checker_version": checker_version,
        "property_set_version": property_set_version,
        "model_analysis_verdict": model_analysis_verdict,
        "source_applicability_at_generation": source_applicability_at_generation,
        "abstraction_contract": _dc_to_dict(abstraction_contract),
        "progress_disposition": progress_disposition,
        "admission_recommendation": admission_recommendation,
        "property_results": [_dc_to_dict(p) for p in property_results],
        "counterexamples": [c.to_dict() for c in counterexamples],
        "coverage": _dc_to_dict(coverage),
        "assumptions": _dc_to_dict(assumptions),
        "known_model_gaps": [_dc_to_dict(g) for g in known_model_gaps],
        "exploration_receipt": _dc_to_dict(exploration_receipt),
        "generated_at": generated_at,
        "supersedes_report_id": supersedes_report_id,
    }
    report_hash = sha256_hex(canonical_json(body))
    report_id = "oar_" + report_hash[:24]

    return OperationAssuranceReport(
        schema=SCHEMA,
        report_id=report_id,
        model_id=model_id,
        model_hash=model_hash,
        source_snapshot_hash=source_snapshot_hash,
        checker_version=checker_version,
        property_set_version=property_set_version,
        model_analysis_verdict=model_analysis_verdict,
        source_applicability_at_generation=source_applicability_at_generation,
        abstraction_contract=abstraction_contract,
        progress_disposition=progress_disposition,
        admission_recommendation=admission_recommendation,
        property_results=property_results,
        counterexamples=counterexamples,
        coverage=coverage,
        assumptions=assumptions,
        known_model_gaps=known_model_gaps,
        exploration_receipt=exploration_receipt,
        generated_at=generated_at,
        supersedes_report_id=supersedes_report_id,
        report_hash=report_hash,
    )


def _validate_property_results(results: tuple[PropertyResult, ...], coverage: Coverage) -> None:
    seen_ids: set[str] = set()
    seen_mandatory: set[str] = set()
    for r in results:
        if r.property_id in seen_ids:
            raise _fail("DUPLICATE_ID", "duplicate property_id in property_results", "property_results")
        seen_ids.add(r.property_id)
        if r.property_kind in _GENERIC_MANDATORY:
            seen_mandatory.add(r.property_kind)
        if r.status not in PROPERTY_STATUSES:
            raise _fail("UNKNOWN_ENUM_VALUE", "not a legal property status", f"property_results[{r.property_id}].status")
        if r.property_kind not in PROPERTY_KINDS:
            raise _fail("UNKNOWN_ENUM_VALUE", "not a legal property_kind", f"property_results[{r.property_id}].property_kind")
        if r.status == "NOT_APPLICABLE" and r.property_kind not in _NOT_APPLICABLE_ELIGIBLE:
            raise _fail("ILLEGAL_NOT_APPLICABLE", "NOT_APPLICABLE is not legal for this property", f"property_results[{r.property_id}]")
        if r.status in ("PASS", "NOT_APPLICABLE") and r.counterexample_id is not None:
            raise _fail("INVALID_COUNTEREXAMPLE_REFERENCE", "PASS/NOT_APPLICABLE must not reference a counterexample", f"property_results[{r.property_id}]")
        if r.status == "FAIL" and r.counterexample_id is None:
            raise _fail("MISSING_COUNTEREXAMPLE_REFERENCE", "FAIL must reference exactly one counterexample", f"property_results[{r.property_id}]")
    missing_mandatory = _GENERIC_MANDATORY - seen_mandatory
    if missing_mandatory:
        raise _fail("MISSING_MANDATORY_PROPERTY", f"missing mandatory property result(s) {sorted(missing_mandatory)}", "property_results")


def _validate_counterexamples(
    counterexamples: tuple[Counterexample, ...],
    property_results: tuple[PropertyResult, ...],
    model_hash: str,
) -> None:
    seen_ids: set[str] = set()
    referenced: dict[str, str] = {}
    for r in property_results:
        if r.counterexample_id is not None:
            if r.counterexample_id in referenced:
                raise _fail("DUPLICATE_COUNTEREXAMPLE_REFERENCE", "one counterexample referenced by more than one property", r.counterexample_id)
            referenced[r.counterexample_id] = r.property_id

    for cx in counterexamples:
        if cx.counterexample_id in seen_ids:
            raise _fail("DUPLICATE_ID", "duplicate counterexample_id", "counterexamples")
        seen_ids.add(cx.counterexample_id)
        if cx.witness_kind not in WITNESS_KINDS:
            raise _fail("UNKNOWN_ENUM_VALUE", "not a legal witness_kind", f"counterexamples[{cx.counterexample_id}]")
        if cx.realizability not in A1_REALIZABILITY_VALUES:
            raise _fail("UNKNOWN_ENUM_VALUE", "OLS-A1 may emit only DECLARED_MODEL_ONLY or POTENTIALLY_SPURIOUS", f"counterexamples[{cx.counterexample_id}]")
        if cx.counterexample_id not in referenced:
            raise _fail("UNREFERENCED_COUNTEREXAMPLE", "every counterexample must be referenced by exactly one property result", cx.counterexample_id)
        if referenced[cx.counterexample_id] != cx.property_id:
            raise _fail("COUNTEREXAMPLE_PROPERTY_MISMATCH", "counterexample.property_id must match its referencing property result", cx.counterexample_id)
        body = {k: v for k, v in cx.to_dict().items() if k != "counterexample_id"}
        expected = compute_counterexample_id(model_hash, body)
        if cx.counterexample_id != expected:
            raise _fail("BAD_COUNTEREXAMPLE_ID", "counterexample_id does not match recomputed content hash", cx.counterexample_id)
        for rc in cx.repair_candidates:
            if rc.kind not in REPAIR_KINDS:
                raise _fail("UNKNOWN_ENUM_VALUE", "not a legal repair-candidate kind", f"counterexamples[{cx.counterexample_id}].repair_candidates")

    dangling = set(referenced) - seen_ids
    if dangling:
        raise _fail("DANGLING_COUNTEREXAMPLE_REFERENCE", f"property result references missing counterexample(s) {sorted(dangling)}", "property_results")


def _validate_coverage(coverage: Coverage, property_results: tuple[PropertyResult, ...]) -> None:
    result_ids = {r.property_id for r in property_results}
    coverage_ids = set(coverage.evaluated_property_ids)
    if result_ids != coverage_ids:
        raise _fail("COVERAGE_MISMATCH", "coverage.evaluated_property_ids must equal property_results ids", "coverage")
    complete = set(coverage.complete_property_ids)
    incomplete = set(coverage.incomplete_property_ids)
    na = set(coverage.not_applicable_property_ids)
    if complete & incomplete:
        raise _fail("COVERAGE_MISMATCH", "complete and incomplete property ids must be disjoint", "coverage")
    if (complete | incomplete | na) != coverage_ids:
        raise _fail("COVERAGE_MISMATCH", "complete+incomplete+not_applicable must partition evaluated_property_ids", "coverage")
    for r in property_results:
        if r.property_id in na and r.status != "NOT_APPLICABLE":
            raise _fail("COVERAGE_MISMATCH", "coverage not_applicable set disagrees with property status", r.property_id)
        if r.status == "NOT_APPLICABLE" and r.property_id not in na:
            raise _fail("COVERAGE_MISMATCH", "coverage not_applicable set disagrees with property status", r.property_id)
        if r.analysis_complete and r.property_id not in (complete | na):
            raise _fail("COVERAGE_MISMATCH", "analysis_complete property must be in coverage.complete or not_applicable", r.property_id)
        if not r.analysis_complete and r.property_id not in incomplete:
            raise _fail("COVERAGE_MISMATCH", "incomplete-analysis property must be in coverage.incomplete", r.property_id)


def _validate_verdict_preconditions(
    verdict: str,
    property_results: tuple[PropertyResult, ...],
    receipt: ExplorationReceipt,
    abstraction_contract: AbstractionContract,
    known_model_gaps: tuple[ModelGap, ...],
    counterexamples: tuple[Counterexample, ...],
) -> None:
    any_fail = any(r.status == "FAIL" for r in property_results)
    any_unknown = any(r.status == "UNKNOWN" for r in property_results)
    any_spurious = any(c.realizability == "POTENTIALLY_SPURIOUS" for c in counterexamples)
    any_load_bearing_gap = any(g.load_bearing for g in known_model_gaps)

    if verdict == "UNSAFE_COUNTEREXAMPLE":
        if not any_fail:
            raise _fail("VERDICT_PRECONDITION", "UNSAFE_COUNTEREXAMPLE requires at least one FAIL property result", "model_analysis_verdict")
    elif verdict == "PROVEN_WITHIN_FINITE_MODEL":
        if any_fail or any_unknown:
            raise _fail("VERDICT_PRECONDITION", "PROVEN_WITHIN_FINITE_MODEL requires every property PASS or legal NOT_APPLICABLE", "model_analysis_verdict")
        if not receipt.base_graph_complete:
            raise _fail("VERDICT_PRECONDITION", "PROVEN_WITHIN_FINITE_MODEL requires a complete base graph", "model_analysis_verdict")
        if not receipt.checker_terminated_normally:
            raise _fail("VERDICT_PRECONDITION", "PROVEN_WITHIN_FINITE_MODEL requires normal checker termination", "model_analysis_verdict")
        if any(not p.complete for p in receipt.analysis_products):
            raise _fail("VERDICT_PRECONDITION", "PROVEN_WITHIN_FINITE_MODEL requires every load-bearing analysis product complete", "model_analysis_verdict")
        if any_load_bearing_gap:
            raise _fail("VERDICT_PRECONDITION", "PROVEN_WITHIN_FINITE_MODEL cannot coexist with a load-bearing model gap", "model_analysis_verdict")
        if abstraction_contract.kind != "DECLARED_EXACT":
            raise _fail("VERDICT_PRECONDITION", "OLS-A1 proof requires a DECLARED_EXACT abstraction contract", "model_analysis_verdict")
    elif verdict == "BOUNDED_NO_COUNTEREXAMPLE":
        if any_fail:
            raise _fail("VERDICT_PRECONDITION", "BOUNDED_NO_COUNTEREXAMPLE must carry no complete definite counterexample", "model_analysis_verdict")
        if not receipt.any_bound_reached():
            raise _fail("VERDICT_PRECONDITION", "BOUNDED_NO_COUNTEREXAMPLE requires at least one declared resource-bound receipt", "model_analysis_verdict")
    elif verdict == "INCONCLUSIVE_MODEL_GAP":
        pass
