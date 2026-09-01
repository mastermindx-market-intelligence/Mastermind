"""EVAL-R0 deterministic run validity (design §7.6, plan Task 4).

``evaluate_validity`` derives technical validity from stored evaluation
artifacts ONLY -- the scenario, configuration, optional experiment, and the
run/draft's own fields. No unstored side input (no "RunFacts", no runner
self-grade) ever enters the computation, so the same four documents always
recompute the same status/reason_codes -- that recomputability is what
:func:`scripts.agent_eval.verification.verify_run_graph` relies on to
detect a forged or stale ``validity`` block.

Completion status never determines task correctness; a clean COMPLETED run
with no reasons yields technical ``VALID``, never ``VALID_PASS`` (task
pass/fail is a scorer's job, plan Task 5, never the finalizer's).
"""
from __future__ import annotations

from scripts.agent_eval import contracts
from scripts.agent_eval.canonical import add_document_digest, digest_value
from scripts.agent_eval.errors import ContractDefect, ContractError
from scripts.agent_eval.verification import (
    closed_input_resolver,
    verify_configuration_graph,
    verify_run_graph,
    verify_scenario_graph,
)

REASON_CODES = frozenset(
    {
        "MODEL_SERVED_MISMATCH",
        "CONFIGURATION_FIELD_MISMATCH",
        "TOOL_SCHEMA_DRIFT",
        "CAPABILITY_DRIFT",
        "FORBIDDEN_CAPABILITY",
        "UNAUTHORIZED_SOURCE",
        "SOURCE_DIGEST_MISMATCH",
        "HIDDEN_SOLUTION_SOURCE",
        "UNEXPECTED_NETWORK_DESTINATION",
        "FRESH_PROCESS_UNPROVEN",
        "FRESH_WORKSPACE_UNPROVEN",
        "FRESH_SESSION_UNPROVEN",
        "RESUME_FORBIDDEN",
        "NETWORK_POLICY_MISMATCH",
        "DEGRADATION_NOT_ALLOWED",
        "CLEANUP_UNPROVEN",
        "EFFECT_UNKNOWN",
        "UNAUTHORIZED_EFFECT",
        "EFFECT_REFERENCE_MISMATCH",
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

_LEAKAGE_REASONS = frozenset({"UNAUTHORIZED_SOURCE", "SOURCE_DIGEST_MISMATCH", "HIDDEN_SOLUTION_SOURCE"})
_CONFIGURATION_REASONS = frozenset(
    {
        "MODEL_SERVED_MISMATCH",
        "CONFIGURATION_FIELD_MISMATCH",
        "TOOL_SCHEMA_DRIFT",
        "CAPABILITY_DRIFT",
        "FORBIDDEN_CAPABILITY",
        "UNEXPECTED_NETWORK_DESTINATION",
        "FRESH_PROCESS_UNPROVEN",
        "FRESH_WORKSPACE_UNPROVEN",
        "FRESH_SESSION_UNPROVEN",
        "RESUME_FORBIDDEN",
        "NETWORK_POLICY_MISMATCH",
        "DEGRADATION_NOT_ALLOWED",
        "UNAUTHORIZED_EFFECT",
        "EFFECT_REFERENCE_MISMATCH",
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


def _require_matching_identity(scenario: dict, configuration: dict, experiment, run_like: dict) -> None:
    """Hard precondition: the caller must supply the scenario/configuration/
    experiment that the run/draft itself claims to be about. This is not a
    validity outcome -- it is a caller-supplied-the-wrong-artifact error."""
    defects: list[ContractDefect] = []
    run_scenario = run_like["scenario"]
    if run_scenario["scenario_id"] != scenario["scenario_id"] or run_scenario["scenario_version"] != scenario["scenario_version"]:
        defects.append(
            ContractDefect(
                "$.scenario", "SCENARIO_IDENTITY_MISMATCH", "run/draft scenario_id/version does not match the supplied scenario"
            )
        )
    if run_like["configuration"]["configuration_id"] != configuration["configuration_id"]:
        defects.append(
            ContractDefect(
                "$.configuration",
                "CONFIGURATION_IDENTITY_MISMATCH",
                "run/draft configuration_id does not match the supplied configuration",
            )
        )
    experiment_id = run_like["comparison"]["experiment_id"]
    if experiment is None:
        if experiment_id is not None:
            defects.append(
                ContractDefect(
                    "$.comparison.experiment_id",
                    "EXPERIMENT_NOT_SUPPLIED",
                    "run/draft names an experiment_id but no experiment was supplied to the finalizer",
                )
            )
    else:
        if experiment_id != experiment["experiment_id"]:
            defects.append(
                ContractDefect(
                    "$.comparison.experiment_id",
                    "EXPERIMENT_IDENTITY_MISMATCH",
                    "run/draft experiment_id does not match the supplied experiment",
                )
            )
    if defects:
        raise ContractError(defects)


def _gather_reason_codes(scenario: dict, configuration: dict, experiment, run_like: dict) -> set[str]:
    reasons: set[str] = set()
    execution = run_like["execution"]
    config_execution = configuration["execution"]

    if execution["model_served"] != config_execution["model_requested"]:
        reasons.add("MODEL_SERVED_MISMATCH")

    field_mismatch = False
    for field in ("execution_surface", "execution_surface_version", "provider", "model_requested", "reasoning_effort", "auth_realm_class"):
        if execution[field] != config_execution[field]:
            field_mismatch = True
    if run_like["procedure"] != configuration["procedure"]:
        field_mismatch = True
    if run_like["context"]["context_packet"] != configuration["context"]["context_packet"]:
        field_mismatch = True
    if run_like["context"]["retrieval_configuration"] != configuration["context"]["retrieval_configuration"]:
        field_mismatch = True
    if run_like["randomness"] != configuration["randomness"]:
        field_mismatch = True
    if run_like["configuration"]["configuration_digest"] != configuration["configuration_digest"]:
        field_mismatch = True
    run_caps = run_like["capabilities"]
    config_caps = configuration["capabilities"]
    if run_caps["profile_id"] != config_caps["profile_id"] or run_caps["profile_digest"] != config_caps["profile_digest"]:
        field_mismatch = True
    if run_caps["sandbox_digest"] != config_caps["sandbox_digest"]:
        field_mismatch = True
    if run_caps["environment_digest"] != config_caps["environment_digest"]:
        field_mismatch = True
    if contracts.scenario_configuration_defects(scenario, configuration):
        field_mismatch = True
    if field_mismatch:
        reasons.add("CONFIGURATION_FIELD_MISMATCH")

    observed_tools = set(run_like["observations"]["observed_tool_schema_digests"])
    declared_tools = set(configuration["capabilities"]["declared_tool_schema_digests"])
    if not observed_tools.issubset(declared_tools):
        reasons.add("TOOL_SCHEMA_DRIFT")

    observed_caps = set(run_like["observations"]["observed_capability_ids"])
    declared_caps = set(configuration["capabilities"]["declared_capability_ids"])
    if not observed_caps.issubset(declared_caps):
        reasons.add("CAPABILITY_DRIFT")

    forbidden_caps = set(scenario["capability_policy"]["forbidden_capability_ids"])
    if observed_caps & forbidden_caps:
        reasons.add("FORBIDDEN_CAPABILITY")

    allowlisted = {item["artifact_ref"]: item["digest"] for item in scenario["source_policy"]["allowlist_artifacts"]}
    denylisted = set(scenario["source_policy"]["denylist_refs"])
    hidden = set(scenario["source_policy"]["solution_refs_hidden"])
    for source in run_like["observations"]["observed_sources"]:
        ref = source["artifact_ref"]
        if ref in hidden:
            reasons.add("HIDDEN_SOLUTION_SOURCE")
        if ref in denylisted or ref not in allowlisted:
            reasons.add("UNAUTHORIZED_SOURCE")
        elif allowlisted[ref] != source["digest"]:
            reasons.add("SOURCE_DIGEST_MISMATCH")

    authorized_digests = {digest_value(v) for v in scenario["execution_policy"]["network_allowlist"]}
    for destination in run_like["observations"]["observed_network_destinations"]:
        if destination["value_digest"] not in authorized_digests:
            reasons.add("UNEXPECTED_NETWORK_DESTINATION")

    execution_policy = scenario["execution_policy"]
    if execution_policy["fresh_process_required"] and not execution["fresh_process_observed"]:
        reasons.add("FRESH_PROCESS_UNPROVEN")
    if execution_policy["fresh_workspace_required"] and not execution["fresh_workspace_observed"]:
        reasons.add("FRESH_WORKSPACE_UNPROVEN")
    if execution_policy["fresh_session_required"] and not execution["fresh_session_observed"]:
        reasons.add("FRESH_SESSION_UNPROVEN")
    if not execution_policy["resume_allowed"] and execution["resume_used"]:
        reasons.add("RESUME_FORBIDDEN")

    expected_network_policy_digest = contracts.compute_scenario_network_policy_digest(scenario)
    if run_like["capabilities"]["network_policy_digest"] != expected_network_policy_digest:
        reasons.add("NETWORK_POLICY_MISMATCH")
    if run_like["capabilities"]["network_policy_digest"] != configuration["capabilities"]["network_policy_digest"]:
        reasons.add("NETWORK_POLICY_MISMATCH")

    allowed_degradations = set(execution_policy["allowed_degradations"])
    observed_degradations = set(run_like["observations"]["dependency_degradations"])
    if not observed_degradations.issubset(allowed_degradations):
        reasons.add("DEGRADATION_NOT_ALLOWED")

    cleanup = run_like["cleanup"]
    if cleanup["status"] == "UNPROVEN":
        reasons.add("CLEANUP_UNPROVEN")
    elif cleanup["status"] == "NOT_REQUIRED":
        nothing_to_clean = (
            run_like["effect"]["state"] == "NO_EFFECT"
            and not execution_policy["fresh_process_required"]
            and not execution_policy["fresh_workspace_required"]
        )
        if not nothing_to_clean:
            reasons.add("CLEANUP_UNPROVEN")

    effect = run_like["effect"]
    if effect["state"] == "EFFECT_UNKNOWN":
        reasons.add("EFFECT_UNKNOWN")
    elif effect["state"] == "EFFECT_KNOWN":
        allowed_ops = set(scenario["effect_policy"]["allowed_operation_refs"])
        if scenario["effect_policy"]["mode"] != "DECLARED_EFFECT_ALLOWED" or effect["operation_ref"] not in allowed_ops:
            reasons.add("UNAUTHORIZED_EFFECT")
    elif effect["state"] == "NO_EFFECT":
        if effect["operation_ref"] is not None or effect["reconciliation_ref"] is not None:
            reasons.add("EFFECT_REFERENCE_MISMATCH")

    comparison = run_like["comparison"]
    run_scenario_ref = run_like["scenario"]
    if experiment is None:
        if comparison["pair_key"] is not None:
            reasons.add("PAIR_IDENTITY_MISSING")
    else:
        scenario_key = (run_scenario_ref["scenario_id"], run_scenario_ref["scenario_version"])
        scenario_in_experiment = any(
            (ref["scenario_id"], ref["scenario_version"]) == scenario_key for ref in experiment["scenario_refs"]
        )
        if not scenario_in_experiment:
            reasons.add("SCENARIO_NOT_IN_EXPERIMENT")

        arm_lookup = {arm["arm_id"]: arm for arm in experiment["arms"]}
        config_ids_in_experiment = {arm["configuration_id"] for arm in experiment["arms"]}
        if run_like["configuration"]["configuration_id"] not in config_ids_in_experiment:
            reasons.add("CONFIGURATION_NOT_IN_EXPERIMENT")

        arm = arm_lookup.get(comparison["arm_id"])
        if arm is None or arm["configuration_id"] != run_like["configuration"]["configuration_id"]:
            reasons.add("EXPERIMENT_ARM_MISMATCH")

        replicate_index = comparison["replicate_index"]
        target = experiment["replicates_per_arm_target"]
        if replicate_index is None or not (1 <= replicate_index <= target):
            reasons.add("REPLICATE_OUT_OF_RANGE")

        method = experiment["pairing"]["method"]
        pair_key = comparison["pair_key"]
        if method == "PAIRED_BY_SCENARIO":
            expected_pair_key = None
            if replicate_index is not None:
                expected_pair_key = f"pair:{run_scenario_ref['scenario_id']}:v{run_scenario_ref['scenario_version']}:r{replicate_index}"
            if pair_key is None or pair_key != expected_pair_key:
                reasons.add("PAIR_IDENTITY_MISSING")
        elif method == "UNPAIRED":
            if pair_key is not None:
                reasons.add("PAIR_IDENTITY_MISSING")
        elif method == "BLOCKED":
            if pair_key is None or not pair_key.startswith("block:"):
                reasons.add("PAIR_IDENTITY_MISSING")

    if run_scenario_ref["scenario_digest"] != scenario["scenario_digest"] or run_scenario_ref["corpus_revision"] != scenario["corpus_revision"]:
        reasons.add("CORPUS_REVISION_MISMATCH")
    if run_scenario_ref["temporal_cutoff"] != scenario["temporal"]["cutoff_at"]:
        reasons.add("TEMPORAL_CUTOFF_MISMATCH")

    expected_source_policy_digest = digest_value(scenario["source_policy"])
    if run_like["context"]["source_policy_digest"] != expected_source_policy_digest:
        reasons.add("SOURCE_POLICY_DIGEST_MISMATCH")

    return reasons


def _status_from_reasons(reasons: set[str], run_like: dict) -> str:
    if "EFFECT_UNKNOWN" in reasons:
        return "INVALID_EFFECT_UNKNOWN"
    if reasons & _LEAKAGE_REASONS:
        return "INVALID_LEAKAGE"
    if "CLEANUP_UNPROVEN" in reasons:
        return "INVALID_CLEANUP"
    if reasons & _CONFIGURATION_REASONS:
        return "INVALID_CONFIGURATION"
    if run_like["observations"]["dependency_degradations"]:
        return "DEGRADED_DEPENDENCY"
    return "VALID"


def evaluate_validity(scenario: dict, configuration: dict, experiment, draft: dict) -> dict:
    """Derive ``{"status": ..., "reason_codes": (...)}`` from stored
    evaluation artifacts only. Deterministic and pure: the same four
    documents always yield the same result, which is what lets
    :func:`scripts.agent_eval.verification.verify_run_graph` recompute and
    catch a forged or stale ``validity`` block."""
    _require_matching_identity(scenario, configuration, experiment, draft)
    reasons = _gather_reason_codes(scenario, configuration, experiment, draft)
    status = _status_from_reasons(reasons, draft)
    return {"status": status, "reason_codes": tuple(sorted(reasons))}


def finalize_run_receipt(
    scenario: dict,
    configuration: dict,
    experiment_or_none,
    draft: dict,
    *,
    validator_id: str,
    validator_version: str,
    validator_code_ref: str,
    validated_at: str,
    created_at: str,
) -> dict:
    """Graph-verify inputs, shape-validate the draft, derive validity,
    switch schema, insert validator provenance/time/digest, and
    graph-verify the final run before returning it. The caller has already
    resolved scenario/configuration/experiment (e.g. from the real
    ArtifactStore) for THIS run's own arm; this function verifies those
    inputs are internally consistent using a production closed-input
    resolver scoped to exactly those documents -- it performs no
    filesystem/network resolution of its own, and it does not require the
    experiment's *other* arms' configurations to be supplied (that full
    cross-arm graph check is :func:`scripts.agent_eval.verification.verify_experiment_graph`,
    used separately once every arm's configuration is available)."""
    resolver = closed_input_resolver(
        scenarios=(scenario,),
        configurations=(configuration,),
        experiments=(experiment_or_none,) if experiment_or_none is not None else (),
    )
    verify_scenario_graph(scenario, resolver)
    verify_configuration_graph(configuration, resolver)
    if experiment_or_none is not None:
        contracts.validate_experiment_shape(experiment_or_none)

    contracts.validate_run_draft_shape(draft)

    validity = evaluate_validity(scenario, configuration, experiment_or_none, draft)

    run_document = {key: value for key, value in draft.items() if key != "schema"}
    run_document["schema"] = contracts.RUN_SCHEMA
    run_document["validity"] = {
        "status": validity["status"],
        "reason_codes": list(validity["reason_codes"]),
        "validator_id": validator_id,
        "validator_version": validator_version,
        "validator_code_ref": validator_code_ref,
        "validated_at": validated_at,
    }
    run_document["created_at"] = created_at
    run_document = add_document_digest(run_document, "run_digest")

    verify_run_graph(run_document, resolver)

    return run_document
