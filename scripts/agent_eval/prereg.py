"""EVAL-E1: paired-pilot preregistration shape validator (design/plan: see
``docs/superpowers/plans/2026-09-01-agent-evaluation-e1-preregistration.md``).

Operation `mastermind-agent-evaluation-e1-prereg-20260901-fable-001`.
RECORDS ONLY. This module defines and validates a NEW closed contract,
``mastermind.agent_evaluation_e1_preregistration.v1``, that binds the
frozen E1 paired-pilot design (3 task classes x 2 configuration arms x 2
replicates = 6 pairs / 12 intended runs, deterministic seed 5601, no
early stopping, no sample replacement) to concrete, COMMITTED C0 corpus
scenario_ids and real R0 ``configuration``/``experiment`` documents built
with :mod:`scripts.agent_eval.contracts`'s own, unmodified builders --
never a parallel or looser schema.

**Stdlib-only, additive, environment-free: no network, process, or
credential access, and no execution of any scenario/experiment/run.**
Swept automatically by the same AST/subprocess inertness fence that
already covers every ``scripts/agent_eval/*.py`` file
(``tests/test_agent_eval_inertness.py``). This module never imports
``scripts.ohf.*``, never calls a provider, and never drives R0's
``store``/``validity`` finalizer -- it only shapes, cross-checks, and
seals a RECORD describing a future, separately-authorized, human-gated
execution wave.

Preregistration is prospective-capture law (design record, house-standing
practice): the design, the bound scenarios, the two arm identities, the
scoring plan, and the ex-ante expectation are all sealed BEFORE any run
exists, specifically so the sealed forecast cannot be revised after the
fact once real results are known.

**Disclosed schema-driven deviation (see the plan record §3 for the full
rationale, not restated here):** the E1 design is described elsewhere as
"one experiment" for all three task classes, but the three task classes'
own committed C0 capability profiles differ (``read_only_extract_
reviewer`` / ``bounded_patch_planner`` / ``carrier_protocol_reader``), and
:func:`scripts.agent_eval.contracts.scenario_configuration_defects`
requires a configuration's ``capabilities`` block to match ONE scenario's
``capability_policy`` exactly. A single two-arm configuration set
structurally cannot validate against three scenarios carrying three
distinct capability profiles under R0's real, unmodified compatibility
check. This module therefore preregisters E1 as three sibling R0
``experiment`` documents (one per task class, each with its own
scenario_ref and its own two arms), which together still total the frozen
3 x 2 x 2 = 12 runs / 6 pairs -- never a redesign of the frozen counts,
only an honest resolution of which schema-legal shape those counts take.

**Second disclosed schema-driven binding:** R0's ``pairing.random_seed``
is forbidden except under ``pairing.method == "BLOCKED"``
(``contracts._experiment_cross_field_defects``: ``PAIRED_BY_SCENARIO``/
``UNPAIRED`` require ``random_seed`` to be ``null``). The frozen design's
deterministic seed 5601 is therefore bound via ``pairing.method ==
"BLOCKED"`` with ``random_seed == 5601`` and block granularity
``(scenario_id, arm_id)`` -- the schema-legal way to carry a fixed seed
governing paired-replicate assignment order, not a redesign of the
pairing law.
"""
from __future__ import annotations

from typing import Any

from scripts.agent_eval import contracts, corpus
from scripts.agent_eval.canonical import (
    add_document_digest,
    digest_document,
    verify_document_digest,
)
from scripts.agent_eval.canonical import parse_prefixed_uuid4
from scripts.agent_eval.errors import ContractDefect, ContractError

PREREG_SCHEMA = "mastermind.agent_evaluation_e1_preregistration.v1"

#: Frozen E1 design law (packet-specified, never derived): the closed
#: evidence ceiling this preregistration -- and any run it later gates --
#: is capped at. Execution can never upgrade past this without a fresh,
#: separately-authorized preregistration.
EVIDENCE_CEILING = "DESCRIPTIVE_PAIRED_PILOT_NOT_POLICY_GRADE"

#: The two frozen OHF MAS-136 Skillpack arms this preregistration binds,
#: copied literally (never imported) exactly as
#: ``scripts.agent_eval.ohf_bridge.OHF_SKILLPACK_ARMS`` already does for
#: the same two arm identities -- this module does not import
#: ``ohf_bridge`` (keeping the two bridges independently auditable), it
#: only reproduces the same frozen, publicly-committed data.
ARM_IDENTITIES: dict[str, tuple[str, str]] = {
    "control-1.0.0": ("51f9942733b86e550bb9169d2a43462bd28e774f", "1.0.0"),
    "amended-1.1.0": ("8209e1f31da15f8effc23a9899a5c5a02d30cab4", "1.1.0"),
}

#: R0 technical-validity statuses this preregistration's analysis plan
#: must account for (validity.py's own closed vocabulary, copied here as
#: the frozen set the analysis plan classifies against -- never redefined).
TECHNICAL_VALIDITY_STATUSES = frozenset(
    {
        "VALID",
        "DEGRADED_DEPENDENCY",
        "INVALID_CONFIGURATION",
        "INVALID_CLEANUP",
        "INVALID_LEAKAGE",
        "INVALID_EFFECT_UNKNOWN",
    }
)

#: Statuses counted as informative for the analysis (degraded/invalid runs
#: are reported, never silently dropped from the honest-N denominator).
DEGRADED_OR_INVALID_STATUSES = TECHNICAL_VALIDITY_STATUSES - {"VALID"}


# ---------------------------------------------------------------------------
# ID grammar
# ---------------------------------------------------------------------------


def parse_preregistration_id(value: Any, path: str = "$"):
    return parse_prefixed_uuid4(value, "preregistration", path)


def v_preregistration_id(value: Any, path: str) -> str:
    parse_preregistration_id(value, path)
    return value


# ---------------------------------------------------------------------------
# Nested field validators
# ---------------------------------------------------------------------------


def _v_arm_identity(value: Any, path: str) -> dict:
    return contracts.validate_closed_object(
        value,
        path,
        {
            "ohf_arm_name": contracts.v_str,
            "commit_sha": contracts.v_str,
            "skillpack_version": contracts.v_str,
        },
    )


def _v_arm_identities(value: Any, path: str) -> dict:
    if not isinstance(value, dict):
        raise ContractError([ContractDefect(path, "NOT_AN_OBJECT", "expected a JSON object")])
    defects: list[ContractDefect] = []
    if set(value) != {"control", "amended"}:
        defects.append(
            ContractDefect(path, "ARM_IDENTITY_KEYS", "arm_identities must have exactly the keys 'control' and 'amended'")
        )
    result: dict[str, Any] = {}
    for key, item in value.items():
        try:
            result[key] = _v_arm_identity(item, f"{path}.{key}")
        except ContractError as exc:
            defects.extend(exc.defects)
    if defects:
        raise ContractError(defects)
    return result


def _v_design_law(value: Any, path: str) -> dict:
    document = contracts.validate_closed_object(
        value,
        path,
        {
            "task_class_count": contracts.v_pos_int,
            "arm_count": contracts.v_pos_int,
            "replicates_per_arm": contracts.v_pos_int,
            "pairs": contracts.v_pos_int,
            "intended_runs": contracts.v_pos_int,
            "seed": contracts.v_int,
            "no_early_stopping": contracts.v_bool,
            "no_sample_replacement": contracts.v_bool,
            "evidence_ceiling": contracts.v_enum(frozenset({EVIDENCE_CEILING})),
        },
    )
    defects: list[ContractDefect] = []
    if document["task_class_count"] * document["arm_count"] * document["replicates_per_arm"] != document["intended_runs"]:
        defects.append(
            ContractDefect(
                f"{path}.intended_runs",
                "RUN_COUNT_MISMATCH",
                "intended_runs must equal task_class_count * arm_count * replicates_per_arm",
            )
        )
    if document["task_class_count"] * document["replicates_per_arm"] != document["pairs"]:
        defects.append(
            ContractDefect(
                f"{path}.pairs",
                "PAIR_COUNT_MISMATCH",
                "pairs must equal task_class_count * replicates_per_arm (one pair per replicate per task class)",
            )
        )
    if not document["no_early_stopping"] or not document["no_sample_replacement"]:
        defects.append(
            ContractDefect(path, "STOPPING_LAW_VIOLATED", "E1 design law requires no_early_stopping and no_sample_replacement")
        )
    if defects:
        raise ContractError(defects)
    return document


def _v_task_class_binding(value: Any, path: str) -> dict:
    return contracts.validate_closed_object(
        value,
        path,
        {
            "task_class_label": contracts.v_str,
            "scenario_family": contracts.v_scenario_family,
            "scorer_id": contracts.v_scorer_id,
            "all_dimensions": contracts.v_sorted_unique_str_list,
            "deterministic_dimensions": contracts.v_sorted_unique_str_list,
            "rubric_residue_dimension": contracts.v_str,
            "risk_tier": contracts.v_enum(frozenset({"LOW", "MEDIUM", "HIGH", "CRITICAL"})),
            "primary_scenario_ref": _v_scenario_ref_binding,
            "primary_scenario_rationale": contracts.v_str,
            "alternate_scenario_ids": contracts.v_sorted_unique_str_list,
        },
    )


def _v_scenario_ref_binding(value: Any, path: str) -> dict:
    return contracts.validate_closed_object(
        value,
        path,
        {
            "scenario_id": contracts.v_scenario_id,
            "scenario_version": contracts.v_pos_int,
            "scenario_digest": contracts.v_digest,
            "corpus_revision": contracts.v_corpus_revision,
        },
    )


def _v_task_class_bindings(value: Any, path: str) -> list[dict]:
    items = contracts.v_list_of(_v_task_class_binding)(value, path)
    defects: list[ContractDefect] = []
    if len(items) != 3:
        defects.append(ContractDefect(path, "NOT_THREE_TASK_CLASSES", "E1 design requires exactly three task-class bindings"))
    labels = [item["task_class_label"] for item in items]
    if len(set(labels)) != len(labels):
        defects.append(ContractDefect(path, "DUPLICATE_TASK_CLASS_LABEL", "task_class_label values must be unique"))
    families = [item["scenario_family"] for item in items]
    if len(set(families)) != len(families):
        defects.append(
            ContractDefect(path, "DUPLICATE_SCENARIO_FAMILY", "each task class must bind a materially different scenario_family")
        )
    if defects:
        raise ContractError(defects)
    return items


def _v_ex_ante_forecast(value: Any, path: str) -> dict:
    return contracts.validate_closed_object(
        value,
        path,
        {
            "task_class_label": contracts.v_str,
            "directional_expectation": contracts.v_str,
            "expected_effect_size_band": contracts.v_str,
            "uncertainty_statement": contracts.v_str,
            "falsification_condition": contracts.v_str,
        },
    )


def _v_ex_ante_expectation(value: Any, path: str) -> dict:
    return contracts.validate_closed_object(
        value,
        path,
        {
            "sealed": contracts.v_enum(frozenset({True})),
            "sealed_at": contracts.v_timestamp,
            "seal_method": contracts.v_str,
            "forecasts": contracts.v_list_of(_v_ex_ante_forecast),
            "disclosed_as": contracts.v_str,
        },
    )


def _v_invalid_degraded_handling(value: Any, path: str) -> dict:
    document = contracts.validate_closed_object(
        value,
        path,
        {
            "statuses": contracts.v_sorted_unique_str_list,
            "analysis_treatment": contracts.v_str,
            "reporting_law": contracts.v_str,
            "replacement_policy": contracts.v_str,
        },
    )
    if set(document["statuses"]) != set(TECHNICAL_VALIDITY_STATUSES):
        raise ContractError(
            [ContractDefect(f"{path}.statuses", "STATUS_SET_MISMATCH", "statuses must be exactly R0's closed technical-validity vocabulary")]
        )
    return document


def _v_leakage_audit_requirement(value: Any, path: str) -> dict:
    return contracts.validate_closed_object(
        value,
        path,
        {
            "required": contracts.v_enum(frozenset({True})),
            "independence_law": contracts.v_str,
            "scope": contracts.v_sorted_unique_str_list,
            "failure_disposition": contracts.v_str,
        },
    )


def _v_execution_gate_condition(value: Any, path: str) -> dict:
    return contracts.validate_closed_object(
        value,
        path,
        {
            "condition_id": contracts.v_str,
            "description": contracts.v_str,
            "satisfied": contracts.v_bool,
        },
    )


def _v_execution_gate(value: Any, path: str) -> dict:
    document = contracts.validate_closed_object(
        value,
        path,
        {"conditions": contracts.v_list_of(_v_execution_gate_condition), "gate_law": contracts.v_str},
    )
    if len(document["conditions"]) < 2:
        raise ContractError(
            [ContractDefect(f"{path}.conditions", "EXECUTION_GATE_UNDERSPECIFIED", "execution_gate requires at least the runner-proven and fresh-authorization conditions")]
        )
    if any(condition["satisfied"] for condition in document["conditions"]):
        raise ContractError(
            [
                ContractDefect(
                    f"{path}.conditions",
                    "EXECUTION_GATE_PREMATURELY_SATISFIED",
                    "a preregistration is sealed before execution -- no execution_gate condition may already be satisfied",
                )
            ]
        )
    return document


def _v_analysis_plan(value: Any, path: str) -> dict:
    return contracts.validate_closed_object(
        value,
        path,
        {
            "paired_difference_method": contracts.v_str,
            "invalid_degraded_rate_reporting": contracts.v_str,
            "uncertainty_reporting": contracts.v_str,
            "no_causal_claim_statement": contracts.v_str,
            "honest_n_law": contracts.v_str,
        },
    )


def _v_disclosed_placeholders(value: Any, path: str) -> list[dict]:
    def _v_entry(item: Any, item_path: str) -> dict:
        return contracts.validate_closed_object(
            item,
            item_path,
            {
                "field_path": contracts.v_str,
                "reason": contracts.v_str,
                "bound_at_execution_by": contracts.v_str,
            },
        )

    return contracts.v_list_of(_v_entry)(value, path)


# ---------------------------------------------------------------------------
# Top-level preregistration contract
# ---------------------------------------------------------------------------

_PREREG_FIELDS: dict[str, Any] = {
    "schema": contracts.v_enum(frozenset({PREREG_SCHEMA})),
    "preregistration_id": v_preregistration_id,
    "operation_key": contracts.v_str,
    "base_commit": contracts.v_source_ref,
    "corpus_revision": contracts.v_corpus_revision,
    "design_law": _v_design_law,
    "arm_identities": _v_arm_identities,
    "task_classes": _v_task_class_bindings,
    "experiments": lambda value, path: _v_experiments(value, path),
    "configurations": lambda value, path: _v_configurations(value, path),
    "disclosed_placeholders": _v_disclosed_placeholders,
    "scoring_plan": contracts.v_str,
    "ex_ante_expectation": _v_ex_ante_expectation,
    "invalid_degraded_handling": _v_invalid_degraded_handling,
    "leakage_audit_requirement": _v_leakage_audit_requirement,
    "execution_gate": _v_execution_gate,
    "analysis_plan": _v_analysis_plan,
    "non_goals": contracts.v_sorted_unique_str_list,
    "authorship": contracts._v_authorship,
    "created_at": contracts.v_timestamp,
    "preregistration_digest": contracts.v_digest,
}


def _v_experiments(value: Any, path: str) -> list[dict]:
    if not isinstance(value, list):
        raise ContractError([ContractDefect(path, "NOT_A_LIST", "expected a list")])
    defects: list[ContractDefect] = []
    items = []
    for index, item in enumerate(value):
        try:
            contracts.validate_experiment_shape(item)
            items.append(item)
        except ContractError as exc:
            defects.extend(ContractDefect(f"{path}[{index}]::{d.path}", d.code, d.message) for d in exc.defects)
    if len(value) != 3:
        defects.append(ContractDefect(path, "NOT_THREE_EXPERIMENTS", "E1 preregisters exactly three sibling experiments, one per task class"))
    if defects:
        raise ContractError(defects)
    return items


def _v_configurations(value: Any, path: str) -> list[dict]:
    if not isinstance(value, list):
        raise ContractError([ContractDefect(path, "NOT_A_LIST", "expected a list")])
    defects: list[ContractDefect] = []
    items = []
    for index, item in enumerate(value):
        try:
            contracts.validate_configuration_shape(item)
            items.append(item)
        except ContractError as exc:
            defects.extend(ContractDefect(f"{path}[{index}]::{d.path}", d.code, d.message) for d in exc.defects)
    if len(value) != 6:
        defects.append(ContractDefect(path, "NOT_SIX_CONFIGURATIONS", "E1 preregisters exactly six configurations (three task classes x two arms)"))
    if defects:
        raise ContractError(defects)
    return items


def _check_preregistration_fields(document: Any, *, require_digest: bool) -> dict:
    optional = frozenset({"preregistration_digest"}) if not require_digest else frozenset()
    validated = contracts.validate_closed_object(document, "$", _PREREG_FIELDS, optional=optional)
    if require_digest:
        verify_document_digest(document, "preregistration_digest")
    return validated


def validate_preregistration_shape(document: Any) -> str:
    """Validate a persisted E1 preregistration document. Returns 'SHAPE_VALID'.

    Never executes anything -- pure structural/cross-field validation, the
    same discipline as ``contracts.validate_scenario_shape`` /
    ``validate_configuration_shape`` / ``validate_experiment_shape``."""
    _check_preregistration_fields(document, require_digest=True)
    return "SHAPE_VALID"


def build_preregistration(fields: dict) -> dict:
    """Assemble, validate, and digest an E1 preregistration document.

    ``fields`` must NOT include ``schema`` or ``preregistration_digest``.
    """
    if not isinstance(fields, dict) or "schema" in fields or "preregistration_digest" in fields:
        raise ContractError(
            [
                ContractDefect(
                    "$",
                    "BUILD_FIELDS_MUST_EXCLUDE_SCHEMA_AND_DIGEST",
                    "fields must omit schema and preregistration_digest",
                )
            ]
        )
    document = {"schema": PREREG_SCHEMA, **fields}
    _check_preregistration_fields(document, require_digest=False)
    return add_document_digest(document, "preregistration_digest")


def compute_seal(document: dict) -> str:
    """Recompute the deterministic canonical self-digest (design: 'the
    prereg SEAL') without trusting the document's own stored value."""
    return digest_document(document, "preregistration_digest")


def verify_seal(document: dict) -> None:
    """Raise :class:`ContractError` unless the stored
    ``preregistration_digest`` matches the recomputed seal -- this is how
    a later execution wave proves no drift against the sealed record."""
    verify_document_digest(document, "preregistration_digest")


# ---------------------------------------------------------------------------
# Cross-checks against the committed corpus / embedded documents
# ---------------------------------------------------------------------------


def verify_scenario_bindings(document: dict, *, corpus_root, repo_root) -> None:
    """Confirm every ``task_classes[*].primary_scenario_ref`` names a
    scenario that is ACTUALLY present, byte-consistent, and digest-matched
    in the committed C0 corpus tree. Delegates the tree-level consistency
    check to :func:`scripts.agent_eval.corpus.verify_corpus_tree_consistency`
    (never re-implements it) and additionally cross-checks each bound
    scenario_id/version/digest against the corpus's own persisted scenario
    documents. Read-only filesystem access to the committed corpus tree
    only -- no network, no process, no scenario/experiment execution."""
    report = corpus.verify_corpus_tree_consistency(corpus_root, repo_root)
    if report.result != "CONSISTENT":
        raise ContractError(
            [ContractDefect("$.corpus", "CORPUS_NOT_CONSISTENT", f"committed corpus tree is not CONSISTENT: {report.defects}")]
        )
    defects: list[ContractDefect] = []
    for index, task_class in enumerate(document["task_classes"]):
        ref = task_class["primary_scenario_ref"]
        family, case = contracts.parse_scenario_id(ref["scenario_id"])
        scenario_path = corpus_root / "scenarios" / family / case / f"v{ref['scenario_version']}" / "scenario.json"
        if not scenario_path.is_file():
            defects.append(
                ContractDefect(
                    f"$.task_classes[{index}].primary_scenario_ref",
                    "BOUND_SCENARIO_NOT_FOUND",
                    f"no committed scenario file at {scenario_path}",
                )
            )
            continue
        raw = corpus.read_bounded_bytes(scenario_path)
        import json as _json

        scenario_document = _json.loads(raw.decode("utf-8"))
        try:
            contracts.validate_scenario_shape(scenario_document)
        except ContractError as exc:
            defects.extend(
                ContractDefect(f"$.task_classes[{index}].primary_scenario_ref::{d.path}", d.code, d.message) for d in exc.defects
            )
            continue
        if scenario_document["scenario_digest"] != ref["scenario_digest"]:
            defects.append(
                ContractDefect(
                    f"$.task_classes[{index}].primary_scenario_ref.scenario_digest",
                    "BOUND_SCENARIO_DIGEST_MISMATCH",
                    "preregistration's bound scenario_digest does not match the committed corpus scenario's own digest",
                )
            )
        if scenario_document["scenario_id"] != ref["scenario_id"]:
            defects.append(
                ContractDefect(
                    f"$.task_classes[{index}].primary_scenario_ref.scenario_id",
                    "BOUND_SCENARIO_ID_MISMATCH",
                    "preregistration's bound scenario_id does not match the committed corpus scenario at that path",
                )
            )
    if defects:
        raise ContractError(defects)


def verify_configuration_digests(document: dict) -> None:
    """Recompute every embedded configuration document's own
    ``configuration_digest`` and confirm it matches the stored value --
    stability/recomputability, no filesystem or corpus access needed
    (every configuration is embedded, not referenced)."""
    defects: list[ContractDefect] = []
    for index, configuration in enumerate(document["configurations"]):
        try:
            verify_document_digest(configuration, "configuration_digest")
        except ContractError as exc:
            defects.extend(
                ContractDefect(f"$.configurations[{index}]::{d.path}", d.code, d.message) for d in exc.defects
            )
    if defects:
        raise ContractError(defects)


def verify_experiment_digests(document: dict) -> None:
    """Recompute every embedded experiment document's own
    ``experiment_digest`` and confirm it matches the stored value."""
    defects: list[ContractDefect] = []
    for index, experiment in enumerate(document["experiments"]):
        try:
            verify_document_digest(experiment, "experiment_digest")
        except ContractError as exc:
            defects.extend(ContractDefect(f"$.experiments[{index}]::{d.path}", d.code, d.message) for d in exc.defects)
    if defects:
        raise ContractError(defects)
