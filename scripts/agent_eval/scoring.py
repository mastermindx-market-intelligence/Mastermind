"""EVAL-R0 append-only scorer passes and sanitized evidence references
(design §7.7/§7.8, plan Task 5).

Scorer passes live OUTSIDE the immutable run: they bind exact run ID/digest
and append (or supersede-by-new-record) without ever rewriting the run.
Evidence references summarize a COMPLETE, caller-enumerated set of runs and
scorer passes bound to one experiment (plan §5.6 complete-enumeration law --
this module never accepts a caller-selected subset silently). R0's grade
stays ``INSUFFICIENT_EVIDENCE`` and its verification scopes never include
``EVIDENCE_CONTENT_VERIFIED``.
"""
from __future__ import annotations

from typing import Any

from scripts.agent_eval import contracts
from scripts.agent_eval.canonical import add_document_digest, parse_prefixed_uuid4
from scripts.agent_eval.errors import ContractDefect, ContractError, VerificationContextError
from scripts.agent_eval.resolver import ArtifactResolver
from scripts.agent_eval.verification import (
    GRAPH_VERIFIED_SCOPE,
    VerificationResult,
    collect_run_evidence_refs,
)

SCORER_PASS_SCHEMA = "mastermind.agent_evaluation_scorer_pass.v1"
EVIDENCE_REF_SCHEMA = "mastermind.agent_evaluation_evidence_ref.v1"

TECHNICAL_INTEGRITY_SCORER_ID = "mastermind.technical_integrity.v1"
DIMENSIONS: tuple[str, ...] = ("cleanup_integrity", "configuration_integrity", "effect_integrity", "source_integrity")

REQUIRED_NON_AUTHORITY_STATEMENT = (
    "This evidence reference does not authorize routing, policy, release, merge, deployment, production execution, or acceptance."
)

_METHODS = frozenset({"DETERMINISTIC", "STATISTICAL", "MODEL_GENERATED", "HUMAN"})
_DIMENSION_STATUSES = frozenset({"PASS", "FAIL", "PARTIAL", "UNKNOWN", "NOT_APPLICABLE"})
_SCORED_PROJECTIONS = frozenset(
    {
        "VALID_PASS",
        "VALID_FAIL",
        "VALID_PARTIAL",
        "UNSCORED",
        "INVALID_CONFIGURATION",
        "INVALID_LEAKAGE",
        "INVALID_EFFECT_UNKNOWN",
        "INVALID_CLEANUP",
        "DEGRADED_DEPENDENCY",
    }
)
_VERIFICATION_SCOPE_VALUES = frozenset({"SHAPE_VALID", "EVALUATION_GRAPH_VERIFIED"})  # never EVIDENCE_CONTENT_VERIFIED

_CONFIGURATION_INTEGRITY_REASONS = frozenset(
    {
        "MODEL_SERVED_MISMATCH",
        "CONFIGURATION_FIELD_MISMATCH",
        "TOOL_SCHEMA_DRIFT",
        "CAPABILITY_DRIFT",
        "FORBIDDEN_CAPABILITY",
        "NETWORK_POLICY_MISMATCH",
        "UNEXPECTED_NETWORK_DESTINATION",
        "FRESH_PROCESS_UNPROVEN",
        "FRESH_WORKSPACE_UNPROVEN",
        "FRESH_SESSION_UNPROVEN",
        "RESUME_FORBIDDEN",
        "DEGRADATION_NOT_ALLOWED",
        "EXPERIMENT_ARM_MISMATCH",
        "PAIR_IDENTITY_MISSING",
        "SCENARIO_NOT_IN_EXPERIMENT",
        "CONFIGURATION_NOT_IN_EXPERIMENT",
        "REPLICATE_OUT_OF_RANGE",
        "TEMPORAL_CUTOFF_MISMATCH",
        "CORPUS_REVISION_MISMATCH",
        "SOURCE_POLICY_DIGEST_MISMATCH",
    }
)
_EFFECT_INTEGRITY_REASONS = frozenset({"EFFECT_UNKNOWN", "UNAUTHORIZED_EFFECT", "EFFECT_REFERENCE_MISMATCH"})
_CLEANUP_INTEGRITY_REASONS = frozenset({"CLEANUP_UNPROVEN"})
_SOURCE_INTEGRITY_REASONS = frozenset({"UNAUTHORIZED_SOURCE", "SOURCE_DIGEST_MISMATCH", "HIDDEN_SOLUTION_SOURCE"})

_DIMENSION_REASON_BUCKETS = {
    "configuration_integrity": _CONFIGURATION_INTEGRITY_REASONS,
    "effect_integrity": _EFFECT_INTEGRITY_REASONS,
    "cleanup_integrity": _CLEANUP_INTEGRITY_REASONS,
    "source_integrity": _SOURCE_INTEGRITY_REASONS,
}


def parse_scorer_pass_id(value: Any, path: str = "$"):
    return parse_prefixed_uuid4(value, "scorer-pass", path)


def v_scorer_pass_id(value: Any, path: str) -> str:
    parse_scorer_pass_id(value, path)
    return value


def parse_evidence_ref_id(value: Any, path: str = "$"):
    return parse_prefixed_uuid4(value, "evidence-ref", path)


def v_evidence_ref_id(value: Any, path: str) -> str:
    parse_evidence_ref_id(value, path)
    return value


# ---------------------------------------------------------------------------
# Scorer pass contract
# ---------------------------------------------------------------------------


def _v_dimension_result(value: Any, path: str) -> dict:
    return contracts.validate_closed_object(
        value,
        path,
        {
            "dimension": contracts.v_str,
            "status": contracts.v_enum(_DIMENSION_STATUSES),
            "reason_codes": contracts.v_sorted_unique_str_list,
            "evidence_refs": contracts.v_artifact_list,
        },
    )


def _v_dimension_results(value: Any, path: str) -> list[dict]:
    items = contracts.v_list_of(_v_dimension_result)(value, path)
    dims = [item["dimension"] for item in items]
    defects: list[ContractDefect] = []
    if dims != sorted(dims):
        defects.append(ContractDefect(path, "LIST_NOT_SORTED", "dimension_results must be sorted by dimension"))
    if len(set(dims)) != len(dims):
        defects.append(ContractDefect(path, "LIST_HAS_DUPLICATES", "dimension_results must not repeat a dimension"))
    if defects:
        raise ContractError(defects)
    return items


_SCORER_PASS_FIELDS = {
    "schema": contracts.v_enum(frozenset({SCORER_PASS_SCHEMA})),
    "scorer_pass_id": v_scorer_pass_id,
    "run_id": contracts.v_run_id,
    "run_digest": contracts.v_digest,
    "scorer_id": contracts.v_scorer_id,
    "scorer_version": contracts.v_str,
    "scorer_code_ref": contracts.v_source_ref,
    "scorer_configuration_digest": contracts.v_digest,
    "method": contracts.v_enum(_METHODS),
    "input_evidence": contracts.v_artifact_list,
    "dimension_results": _v_dimension_results,
    "grader_identity": contracts.v_optional(contracts.v_str),
    "created_at": contracts.v_timestamp,
    "supersedes": contracts.v_optional(v_scorer_pass_id),
    "scorer_pass_digest": contracts.v_digest,
}


def _scorer_pass_cross_field_defects(document: dict) -> list[ContractDefect]:
    defects: list[ContractDefect] = []
    method = document.get("method")
    grader = document.get("grader_identity")
    if method in {"HUMAN", "MODEL_GENERATED"} and grader is None:
        defects.append(
            ContractDefect(
                "$.grader_identity", "GRADER_IDENTITY_REQUIRED", "HUMAN/MODEL_GENERATED methods require a non-null grader_identity"
            )
        )
    if method in {"DETERMINISTIC", "STATISTICAL"} and grader is not None:
        defects.append(
            ContractDefect(
                "$.grader_identity", "GRADER_IDENTITY_NOT_ALLOWED", "DETERMINISTIC/STATISTICAL methods must not carry grader_identity"
            )
        )
    if document.get("supersedes") is not None and document.get("supersedes") == document.get("scorer_pass_id"):
        defects.append(ContractDefect("$.supersedes", "SUPERSEDES_SELF", "a scorer pass must not supersede itself"))
    return defects


def _check_scorer_pass_fields(document: Any, *, require_digest: bool) -> dict:
    optional = frozenset({"scorer_pass_digest"}) if not require_digest else frozenset()
    validated = contracts.validate_closed_object(document, "$", _SCORER_PASS_FIELDS, optional=optional)
    cross_defects = _scorer_pass_cross_field_defects(document if isinstance(document, dict) else {})
    if cross_defects:
        raise ContractError(cross_defects)
    if require_digest:
        contracts.verify_document_digest(document, "scorer_pass_digest")
    return validated


def validate_scorer_pass_shape(document: Any) -> str:
    _check_scorer_pass_fields(document, require_digest=True)
    return "SHAPE_VALID"


def build_technical_integrity_scorer_pass(
    run: dict,
    *,
    scorer_pass_id: str,
    scorer_code_ref: str,
    scorer_version: str = "1",
    created_at: str,
    grader_identity: str | None = None,
    supersedes: str | None = None,
) -> dict:
    """Build the append-only ``mastermind.technical_integrity.v1`` scorer
    pass for one immutable run. Uses run validity/reason_codes ONLY -- it
    never claims broad task correctness or product usefulness."""
    reasons = set(run["validity"]["reason_codes"])
    dimension_results = []
    for dimension in sorted(DIMENSIONS):
        bucket = _DIMENSION_REASON_BUCKETS[dimension]
        matched = sorted(reasons & bucket)
        status = "FAIL" if matched else "PASS"
        evidence_refs = [] if status == "PASS" else [dict(run["evidence"]["output"])]
        dimension_results.append(
            {"dimension": dimension, "status": status, "reason_codes": matched, "evidence_refs": evidence_refs}
        )

    fields = {
        "scorer_pass_id": scorer_pass_id,
        "run_id": run["run_id"],
        "run_digest": run["run_digest"],
        "scorer_id": TECHNICAL_INTEGRITY_SCORER_ID,
        "scorer_version": scorer_version,
        "scorer_code_ref": scorer_code_ref,
        "scorer_configuration_digest": contracts.digest_value(
            {"scorer_id": TECHNICAL_INTEGRITY_SCORER_ID, "scorer_version": scorer_version}
        ),
        "method": "DETERMINISTIC",
        "input_evidence": sorted(
            [dict(run["evidence"]["output"]), dict(run["evidence"]["tool_events"])],
            key=lambda item: item["artifact_ref"],
        ),
        "dimension_results": dimension_results,
        "grader_identity": grader_identity,
        "created_at": created_at,
        "supersedes": supersedes,
    }
    document = {"schema": SCORER_PASS_SCHEMA, **fields}
    _check_scorer_pass_fields(document, require_digest=False)
    return add_document_digest(document, "scorer_pass_digest")


def verify_scorer_pass_graph(document: dict, resolver: ArtifactResolver) -> VerificationResult:
    validate_scorer_pass_shape(document)
    run = resolver.resolve_run(document["run_id"])
    if run is None:
        raise VerificationContextError(
            [ContractDefect("$.run_id", "RUN_NOT_RESOLVED", "referenced run could not be resolved")]
        )
    if run.get("run_digest") != document["run_digest"]:
        raise VerificationContextError(
            [ContractDefect("$.run_digest", "RUN_DIGEST_MISMATCH", "resolved run digest does not match scorer pass")]
        )
    if document["scorer_id"] == TECHNICAL_INTEGRITY_SCORER_ID and document["method"] == "DETERMINISTIC":
        recomputed = build_technical_integrity_scorer_pass(
            run,
            scorer_pass_id=document["scorer_pass_id"],
            scorer_code_ref=document["scorer_code_ref"],
            scorer_version=document["scorer_version"],
            created_at=document["created_at"],
            grader_identity=document["grader_identity"],
            supersedes=document["supersedes"],
        )
        if recomputed["dimension_results"] != document["dimension_results"]:
            raise VerificationContextError(
                [
                    ContractDefect(
                        "$.dimension_results",
                        "SCORER_RESULT_NOT_RECOMPUTABLE",
                        "recomputed technical-integrity dimensions do not match the stored scorer pass",
                    )
                ]
            )
    external_refs = {item["artifact_ref"] for item in document["input_evidence"]}
    return VerificationResult(
        scope=GRAPH_VERIFIED_SCOPE,
        artifact_id=document["scorer_pass_id"],
        artifact_digest=document["scorer_pass_digest"],
        external_content_unverified_refs=tuple(sorted(external_refs)),
    )


# ---------------------------------------------------------------------------
# Evidence reference contract
# ---------------------------------------------------------------------------


def _v_evidence_scenario_ref(value: Any, path: str) -> dict:
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


def _v_evidence_experiment_ref(value: Any, path: str) -> dict:
    return contracts.validate_closed_object(
        value, path, {"experiment_id": contracts.v_experiment_id, "experiment_digest": contracts.v_digest}
    )


def _v_configuration_ref_with_arm(value: Any, path: str) -> dict:
    return contracts.validate_closed_object(
        value,
        path,
        {
            "configuration_id": contracts.v_configuration_id,
            "configuration_digest": contracts.v_digest,
            "arm_id": contracts.v_arm_id,
        },
    )


def _v_configuration_ref_list(value: Any, path: str) -> list[dict]:
    items = contracts.v_list_of(_v_configuration_ref_with_arm)(value, path)
    arm_ids = [item["arm_id"] for item in items]
    if arm_ids != sorted(arm_ids):
        raise ContractError([ContractDefect(path, "LIST_NOT_SORTED", "configuration_refs must be sorted by arm_id")])
    if len(set(arm_ids)) != len(arm_ids):
        raise ContractError([ContractDefect(path, "LIST_HAS_DUPLICATES", "configuration_refs must not repeat an arm_id")])
    return items


def _v_run_entry(value: Any, path: str) -> dict:
    return contracts.validate_closed_object(
        value,
        path,
        {
            "run_id": contracts.v_run_id,
            "run_digest": contracts.v_digest,
            "arm_id": contracts.v_optional(contracts.v_arm_id),
            "pair_key": contracts.v_pair_key,
            "replicate_index": contracts.v_optional(contracts.v_pos_int),
            "technical_validity": contracts.v_enum(
                frozenset(
                    {
                        "VALID",
                        "INVALID_CONFIGURATION",
                        "INVALID_LEAKAGE",
                        "INVALID_EFFECT_UNKNOWN",
                        "INVALID_CLEANUP",
                        "DEGRADED_DEPENDENCY",
                    }
                )
            ),
            "scored_projection": contracts.v_enum(_SCORED_PROJECTIONS),
        },
    )


def _v_run_entries(value: Any, path: str) -> list[dict]:
    items = contracts.v_list_of(_v_run_entry)(value, path)
    run_ids = [item["run_id"] for item in items]
    if run_ids != sorted(run_ids):
        raise ContractError([ContractDefect(path, "LIST_NOT_SORTED", "run_entries must be sorted by run_id")])
    if len(set(run_ids)) != len(run_ids):
        raise ContractError([ContractDefect(path, "LIST_HAS_DUPLICATES", "run_entries must not repeat a run_id")])
    return items


def _v_scorer_ref(value: Any, path: str) -> dict:
    return contracts.validate_closed_object(
        value, path, {"scorer_pass_id": v_scorer_pass_id, "scorer_pass_digest": contracts.v_digest}
    )


def _v_scorer_ref_list(value: Any, path: str) -> list[dict]:
    items = contracts.v_list_of(_v_scorer_ref)(value, path)
    ids = [item["scorer_pass_id"] for item in items]
    if ids != sorted(ids):
        raise ContractError([ContractDefect(path, "LIST_NOT_SORTED", "scorer_refs must be sorted by scorer_pass_id")])
    if len(set(ids)) != len(ids):
        raise ContractError([ContractDefect(path, "LIST_HAS_DUPLICATES", "scorer_refs must not repeat a scorer_pass_id")])
    return items


def _v_dimension_gate(value: Any, path: str) -> dict:
    return contracts.validate_closed_object(
        value,
        path,
        {
            "dimension": contracts.v_str,
            "required": contracts.v_bool,
            "valid_pass_count": contracts.v_nonneg_int,
            "valid_fail_count": contracts.v_nonneg_int,
            "valid_partial_count": contracts.v_nonneg_int,
            "unscored_count": contracts.v_nonneg_int,
        },
    )


def _v_dimension_gates(value: Any, path: str) -> list[dict]:
    items = contracts.v_list_of(_v_dimension_gate)(value, path)
    dims = [item["dimension"] for item in items]
    if dims != sorted(dims):
        raise ContractError([ContractDefect(path, "LIST_NOT_SORTED", "dimension_gates must be sorted by dimension")])
    if len(set(dims)) != len(dims):
        raise ContractError([ContractDefect(path, "LIST_HAS_DUPLICATES", "dimension_gates must not repeat a dimension")])
    return items


def _v_counts(value: Any, path: str) -> dict:
    return contracts.validate_closed_object(
        value,
        path,
        {
            "valid_count": contracts.v_nonneg_int,
            "invalid_count": contracts.v_nonneg_int,
            "degraded_count": contracts.v_nonneg_int,
            "unscored_count": contracts.v_nonneg_int,
            "total_count": contracts.v_nonneg_int,
        },
    )


def _v_verification_scopes(value: Any, path: str) -> list[str]:
    items = contracts.v_sorted_unique_str_list(value, path)
    unknown = [item for item in items if item not in _VERIFICATION_SCOPE_VALUES | {"EVIDENCE_CONTENT_VERIFIED"}]
    if unknown:
        raise ContractError([ContractDefect(path, "UNKNOWN_VERIFICATION_SCOPE", f"unrecognized scope(s): {unknown}")])
    if "EVIDENCE_CONTENT_VERIFIED" in items:
        raise ContractError(
            [
                ContractDefect(
                    path, "CONTENT_VERIFICATION_OVERCLAIMED", "R0 must never claim EVIDENCE_CONTENT_VERIFIED"
                )
            ]
        )
    return items


_EVIDENCE_REF_FIELDS = {
    "schema": contracts.v_enum(frozenset({EVIDENCE_REF_SCHEMA})),
    "evidence_ref_id": v_evidence_ref_id,
    "scenario_ref": _v_evidence_scenario_ref,
    "experiment_ref": _v_evidence_experiment_ref,
    "configuration_refs": _v_configuration_ref_list,
    "run_entries": _v_run_entries,
    "scorer_refs": _v_scorer_ref_list,
    "dimension_gates": _v_dimension_gates,
    "counts": _v_counts,
    "sample_size": contracts.v_nonneg_int,
    "uncertainty": contracts.v_enum(frozenset({"NOT_ESTIMATED"})),
    "limitations": contracts.v_sorted_unique_str_list,
    "evidence_grade": contracts.v_enum(frozenset({"INSUFFICIENT_EVIDENCE"})),
    "verification_scopes": _v_verification_scopes,
    "phase": contracts.v_enum(
        frozenset({"RETROSPECTIVE", "REPLAY", "PROSPECTIVE_SHADOW", "CANARY", "PROMOTED"})
    ),
    "intended_owner": contracts.v_str,
    "review_at": contracts.v_timestamp,
    "non_authority_statement": contracts.v_enum(frozenset({REQUIRED_NON_AUTHORITY_STATEMENT})),
    "created_at": contracts.v_timestamp,
    "analysis_version": contracts.v_str,
    "evidence_ref_digest": contracts.v_digest,
}


def _evidence_ref_cross_field_defects(document: dict) -> list[ContractDefect]:
    defects: list[ContractDefect] = []
    entries = document.get("run_entries")
    counts = document.get("counts")
    if isinstance(entries, list) and isinstance(counts, dict):
        valid = sum(1 for e in entries if isinstance(e, dict) and e.get("technical_validity") == "VALID")
        degraded = sum(1 for e in entries if isinstance(e, dict) and e.get("technical_validity") == "DEGRADED_DEPENDENCY")
        invalid = sum(
            1
            for e in entries
            if isinstance(e, dict) and isinstance(e.get("technical_validity"), str) and e["technical_validity"].startswith("INVALID_")
        )
        unscored = sum(1 for e in entries if isinstance(e, dict) and e.get("scored_projection") == "UNSCORED")
        expectations = {
            "valid_count": valid,
            "invalid_count": invalid,
            "degraded_count": degraded,
            "unscored_count": unscored,
            "total_count": len(entries),
        }
        for key, expected in expectations.items():
            if counts.get(key) != expected:
                defects.append(ContractDefect(f"$.counts.{key}", "COUNT_MISMATCH", f"{key} does not match run_entries"))
    if isinstance(entries, list) and document.get("sample_size") != len(entries):
        defects.append(
            ContractDefect("$.sample_size", "SAMPLE_SIZE_MISMATCH", "sample_size must equal the number of run_entries")
        )
    return defects


def _check_evidence_ref_fields(document: Any, *, require_digest: bool) -> dict:
    optional = frozenset({"evidence_ref_digest"}) if not require_digest else frozenset()
    validated = contracts.validate_closed_object(document, "$", _EVIDENCE_REF_FIELDS, optional=optional)
    cross_defects = _evidence_ref_cross_field_defects(document if isinstance(document, dict) else {})
    if cross_defects:
        raise ContractError(cross_defects)
    if require_digest:
        contracts.verify_document_digest(document, "evidence_ref_digest")
    return validated


def validate_evidence_ref_shape(document: Any) -> str:
    _check_evidence_ref_fields(document, require_digest=True)
    return "SHAPE_VALID"


def _scored_projection(run: dict, required_dimensions: set[str], scorer_passes_for_run: list[dict]) -> str:
    status = run["validity"]["status"]
    if status != "VALID":
        return status  # invalid/degraded technical-state passthrough
    dimension_status: dict[str, str] = {}
    for pass_doc in scorer_passes_for_run:
        for result in pass_doc["dimension_results"]:
            if result["dimension"] in required_dimensions:
                dimension_status[result["dimension"]] = result["status"]
    if not required_dimensions.issubset(dimension_status.keys()):
        return "UNSCORED"
    statuses = {dimension_status[d] for d in required_dimensions}
    if "FAIL" in statuses:
        return "VALID_FAIL"
    if statuses <= {"PASS"}:
        return "VALID_PASS"
    if "PARTIAL" in statuses:
        return "VALID_PARTIAL"
    return "UNSCORED"


def summarize_experiment(
    experiment: dict,
    scenario: dict,
    runs: tuple[dict, ...],
    scorer_passes: tuple[dict, ...],
    *,
    evidence_ref_id: str,
    intended_owner: str,
    review_at: str,
    created_at: str,
    analysis_version: str,
) -> dict:
    """Build one sanitized evidence reference from a COMPLETE, caller-
    enumerated set of runs/scorer-passes (plan §5.6 complete-enumeration
    law -- the caller, typically the CLI's ``summarize`` command, performs
    the deterministic sorted filesystem enumeration; this function is pure
    summarization logic and never accepts a caller-selected subset
    silently: every run whose ``comparison.experiment_id`` matches the
    target experiment is included here, regardless of validity)."""
    matching_runs = tuple(
        sorted(
            (run for run in runs if run["comparison"]["experiment_id"] == experiment["experiment_id"]),
            key=lambda run: run["run_id"],
        )
    )
    matching_ids = {run["run_id"] for run in matching_runs}
    scorer_passes_by_run: dict[str, list[dict]] = {run_id: [] for run_id in matching_ids}
    for pass_doc in scorer_passes:
        if pass_doc["run_id"] in scorer_passes_by_run:
            scorer_passes_by_run[pass_doc["run_id"]].append(pass_doc)

    required_dimensions = set(scenario["scoring_policy"]["required_dimensions"])

    run_entries = []
    dimension_status_by_dimension: dict[str, list[str]] = {d: [] for d in required_dimensions}
    for run in matching_runs:
        projection = _scored_projection(run, required_dimensions, scorer_passes_by_run[run["run_id"]])
        run_entries.append(
            {
                "run_id": run["run_id"],
                "run_digest": run["run_digest"],
                "arm_id": run["comparison"]["arm_id"],
                "pair_key": run["comparison"]["pair_key"],
                "replicate_index": run["comparison"]["replicate_index"],
                "technical_validity": run["validity"]["status"],
                "scored_projection": projection,
            }
        )
        if run["validity"]["status"] == "VALID":
            dim_status: dict[str, str] = {}
            for pass_doc in scorer_passes_by_run[run["run_id"]]:
                for result in pass_doc["dimension_results"]:
                    if result["dimension"] in required_dimensions:
                        dim_status[result["dimension"]] = result["status"]
            for dimension in required_dimensions:
                dimension_status_by_dimension[dimension].append(dim_status.get(dimension, "UNSCORED"))

    configuration_refs = sorted(
        (
            {
                "configuration_id": arm["configuration_id"],
                "configuration_digest": arm["configuration_digest"],
                "arm_id": arm["arm_id"],
            }
            for arm in experiment["arms"]
        ),
        key=lambda item: item["arm_id"],
    )

    scorer_ref_pairs = sorted(
        {
            (pass_doc["scorer_pass_id"], pass_doc["scorer_pass_digest"])
            for run_id in matching_ids
            for pass_doc in scorer_passes_by_run[run_id]
        }
    )
    scorer_refs = [{"scorer_pass_id": sid, "scorer_pass_digest": sdigest} for sid, sdigest in scorer_ref_pairs]

    dimension_gates = []
    for dimension in sorted(required_dimensions):
        statuses = dimension_status_by_dimension[dimension]
        dimension_gates.append(
            {
                "dimension": dimension,
                "required": True,
                "valid_pass_count": statuses.count("PASS"),
                "valid_fail_count": statuses.count("FAIL"),
                "valid_partial_count": statuses.count("PARTIAL"),
                "unscored_count": statuses.count("UNSCORED"),
            }
        )

    valid_count = sum(1 for e in run_entries if e["technical_validity"] == "VALID")
    degraded_count = sum(1 for e in run_entries if e["technical_validity"] == "DEGRADED_DEPENDENCY")
    invalid_count = sum(1 for e in run_entries if e["technical_validity"].startswith("INVALID_"))
    unscored_count = sum(1 for e in run_entries if e["scored_projection"] == "UNSCORED")

    fields = {
        "evidence_ref_id": evidence_ref_id,
        "scenario_ref": {
            "scenario_id": scenario["scenario_id"],
            "scenario_version": scenario["scenario_version"],
            "scenario_digest": scenario["scenario_digest"],
            "corpus_revision": scenario["corpus_revision"],
        },
        "experiment_ref": {"experiment_id": experiment["experiment_id"], "experiment_digest": experiment["experiment_digest"]},
        "configuration_refs": configuration_refs,
        "run_entries": run_entries,
        "scorer_refs": scorer_refs,
        "dimension_gates": dimension_gates,
        "counts": {
            "valid_count": valid_count,
            "invalid_count": invalid_count,
            "degraded_count": degraded_count,
            "unscored_count": unscored_count,
            "total_count": len(run_entries),
        },
        "sample_size": len(run_entries),
        "uncertainty": "NOT_ESTIMATED",
        "limitations": sorted(
            {
                "R0 implements SHAPE_VALID and EVALUATION_GRAPH_VERIFIED only; EVIDENCE_CONTENT_VERIFIED is not claimed.",
                "R0 has no independent task-correctness scorer beyond technical_integrity; scored_projection reflects technical integrity dimensions only.",
            }
        ),
        "evidence_grade": "INSUFFICIENT_EVIDENCE",
        "verification_scopes": sorted(["EVALUATION_GRAPH_VERIFIED", "SHAPE_VALID"]),
        "phase": experiment["phase"],
        "intended_owner": intended_owner,
        "review_at": review_at,
        "non_authority_statement": REQUIRED_NON_AUTHORITY_STATEMENT,
        "created_at": created_at,
        "analysis_version": analysis_version,
    }
    document = {"schema": EVIDENCE_REF_SCHEMA, **fields}
    _check_evidence_ref_fields(document, require_digest=False)
    return add_document_digest(document, "evidence_ref_digest")


def verify_evidence_ref_graph(document: dict, resolver: ArtifactResolver) -> VerificationResult:
    validate_evidence_ref_shape(document)
    scenario_ref = document["scenario_ref"]
    scenario = resolver.resolve_scenario(scenario_ref["scenario_id"], scenario_ref["scenario_version"])
    experiment = resolver.resolve_experiment(document["experiment_ref"]["experiment_id"])
    defects: list[ContractDefect] = []
    if scenario is None:
        defects.append(ContractDefect("$.scenario_ref", "SCENARIO_NOT_RESOLVED", "referenced scenario could not be resolved"))
    if experiment is None:
        defects.append(
            ContractDefect("$.experiment_ref", "EXPERIMENT_NOT_RESOLVED", "referenced experiment could not be resolved")
        )
    if defects:
        raise VerificationContextError(sorted(set(defects)))

    runs: list[dict] = []
    for entry in document["run_entries"]:
        run = resolver.resolve_run(entry["run_id"])
        if run is None:
            defects.append(ContractDefect(f"$.run_entries[{entry['run_id']}]", "RUN_NOT_RESOLVED", "referenced run could not be resolved"))
            continue
        runs.append(run)
    scorer_passes: list[dict] = []
    for ref in document["scorer_refs"]:
        pass_doc = resolver.resolve_scorer_pass(ref["scorer_pass_id"])
        if pass_doc is None:
            defects.append(
                ContractDefect(
                    f"$.scorer_refs[{ref['scorer_pass_id']}]", "SCORER_PASS_NOT_RESOLVED", "referenced scorer pass could not be resolved"
                )
            )
            continue
        scorer_passes.append(pass_doc)
    if defects:
        raise VerificationContextError(sorted(set(defects)))

    recomputed = summarize_experiment(
        experiment,
        scenario,
        tuple(runs),
        tuple(scorer_passes),
        evidence_ref_id=document["evidence_ref_id"],
        intended_owner=document["intended_owner"],
        review_at=document["review_at"],
        created_at=document["created_at"],
        analysis_version=document["analysis_version"],
    )
    for field_name in ("run_entries", "counts", "dimension_gates", "scorer_refs", "configuration_refs", "sample_size"):
        if recomputed[field_name] != document[field_name]:
            raise VerificationContextError(
                [
                    ContractDefect(
                        f"$.{field_name}",
                        "EVIDENCE_NOT_RECOMPUTABLE",
                        f"recomputed {field_name} does not match the stored evidence reference",
                    )
                ]
            )

    external_refs: set[str] = set()
    for run in runs:
        external_refs |= collect_run_evidence_refs(run)

    return VerificationResult(
        scope=GRAPH_VERIFIED_SCOPE,
        artifact_id=document["evidence_ref_id"],
        artifact_digest=document["evidence_ref_digest"],
        external_content_unverified_refs=tuple(sorted(external_refs)),
    )


# Register this module's shape validators with the generic contracts
# dispatcher (contracts.validate_document_shape imports this module lazily
# to avoid a circular import at load time; see contracts.py).
contracts.register_shape_validator(SCORER_PASS_SCHEMA, validate_scorer_pass_shape)
contracts.register_shape_validator(EVIDENCE_REF_SCHEMA, validate_evidence_ref_shape)
