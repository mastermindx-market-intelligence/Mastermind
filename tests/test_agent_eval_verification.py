"""EVAL-R0 Task 3: experiment and evaluation-graph verification."""
from __future__ import annotations

import copy

import pytest

from scripts.agent_eval import contracts, verification
from scripts.agent_eval.errors import ContractError, VerificationContextError
from scripts.agent_eval.resolver import ArtifactResolver
from tests.agent_eval_factories import (
    MemoryArtifactResolver,
    build_alternate_configuration,
    build_baseline_configuration,
    build_baseline_scenario,
    build_two_arm_experiment,
)


def _graph():
    scenario = build_baseline_scenario()
    config_a = build_baseline_configuration()
    config_b = build_alternate_configuration()
    experiment = build_two_arm_experiment(scenario, config_a, config_b)
    resolver = MemoryArtifactResolver.build(scenarios=(scenario,), configurations=(config_a, config_b))
    return scenario, config_a, config_b, experiment, resolver


# ---------------------------------------------------------------------------
# Resolver protocol shape
# ---------------------------------------------------------------------------


def test_memory_artifact_resolver_satisfies_the_protocol() -> None:
    _, _, _, _, resolver = _graph()
    assert isinstance(resolver, ArtifactResolver)


def test_resolver_protocol_has_no_write_search_or_fallback_method() -> None:
    forbidden = {"add", "update", "delete", "search", "fallback", "create", "write", "remove"}
    protocol_methods = {name for name in dir(ArtifactResolver) if not name.startswith("_")}
    assert not (protocol_methods & forbidden)


# ---------------------------------------------------------------------------
# Scenario / configuration graph verification
# ---------------------------------------------------------------------------


def test_verify_scenario_graph_reports_exact_scope_and_unverified_refs() -> None:
    scenario, _, _, _, resolver = _graph()
    result = verification.verify_scenario_graph(scenario, resolver)
    assert result.scope == "EVALUATION_GRAPH_VERIFIED"
    assert result.artifact_id == scenario["scenario_id"]
    assert result.artifact_digest == scenario["scenario_digest"]
    assert scenario["input_fixture"]["artifact_ref"] in result.external_content_unverified_refs
    assert scenario["expected_contract"]["artifact_ref"] in result.external_content_unverified_refs


def test_verify_scenario_graph_never_claims_content_verified() -> None:
    scenario, _, _, _, resolver = _graph()
    result = verification.verify_scenario_graph(scenario, resolver)
    assert result.scope != "EVIDENCE_CONTENT_VERIFIED"


def test_verify_scenario_graph_rejects_shape_invalid_document() -> None:
    scenario, _, _, _, resolver = _graph()
    del scenario["objective"]
    with pytest.raises(ContractError):
        verification.verify_scenario_graph(scenario, resolver)


def test_verify_configuration_graph_reports_exact_scope() -> None:
    _, config_a, _, _, resolver = _graph()
    result = verification.verify_configuration_graph(config_a, resolver)
    assert result.scope == "EVALUATION_GRAPH_VERIFIED"
    assert result.artifact_id == config_a["configuration_id"]
    assert config_a["context"]["context_packet"]["artifact_ref"] in result.external_content_unverified_refs


# ---------------------------------------------------------------------------
# Experiment shape
# ---------------------------------------------------------------------------


def test_experiment_is_shape_valid() -> None:
    _, _, _, experiment, _ = _graph()
    assert contracts.validate_experiment_shape(experiment) == "SHAPE_VALID"


def test_experiment_requires_at_least_two_arms() -> None:
    scenario, config_a, _, experiment, _ = _graph()
    fields = copy.deepcopy(experiment)
    fields["arms"] = [fields["arms"][0]]
    del fields["experiment_digest"]
    del fields["schema"]
    with pytest.raises(ContractError) as excinfo:
        contracts.build_experiment(fields)
    assert any(d.code == "TOO_FEW_ARMS" for d in excinfo.value.defects)


def test_experiment_requires_unique_configuration_ids_across_arms() -> None:
    scenario, config_a, _, experiment, _ = _graph()
    fields = copy.deepcopy(experiment)
    fields["arms"][1]["configuration_id"] = fields["arms"][0]["configuration_id"]
    fields["arms"][1]["configuration_digest"] = fields["arms"][0]["configuration_digest"]
    del fields["experiment_digest"]
    del fields["schema"]
    with pytest.raises(ContractError) as excinfo:
        contracts.build_experiment(fields)
    assert any(d.code == "DUPLICATE_ARM_CONFIGURATION_ID" for d in excinfo.value.defects)


def test_experiment_requires_arms_sorted_by_arm_id() -> None:
    _, _, _, experiment, _ = _graph()
    fields = copy.deepcopy(experiment)
    fields["arms"] = list(reversed(fields["arms"]))
    del fields["experiment_digest"]
    del fields["schema"]
    with pytest.raises(ContractError) as excinfo:
        contracts.build_experiment(fields)
    assert any(d.code == "LIST_NOT_SORTED" for d in excinfo.value.defects)


def test_experiment_requires_positive_replicate_target() -> None:
    _, _, _, experiment, _ = _graph()
    fields = copy.deepcopy(experiment)
    fields["replicates_per_arm_target"] = 0
    fields["stopping_rule"]["value"] = 0
    del fields["experiment_digest"]
    del fields["schema"]
    with pytest.raises(ContractError) as excinfo:
        contracts.build_experiment(fields)
    assert any(d.code == "NOT_POSITIVE" for d in excinfo.value.defects)


def test_experiment_stopping_rule_must_match_replicate_target() -> None:
    _, _, _, experiment, _ = _graph()
    fields = copy.deepcopy(experiment)
    fields["stopping_rule"]["value"] = 5
    del fields["experiment_digest"]
    del fields["schema"]
    with pytest.raises(ContractError) as excinfo:
        contracts.build_experiment(fields)
    assert any(d.code == "STOPPING_RULE_MISMATCH" for d in excinfo.value.defects)


def test_experiment_primary_and_guardrail_dimensions_must_be_disjoint() -> None:
    _, _, _, experiment, _ = _graph()
    fields = copy.deepcopy(experiment)
    fields["guardrail_dimensions"] = list(fields["primary_dimensions"])
    del fields["experiment_digest"]
    del fields["schema"]
    with pytest.raises(ContractError) as excinfo:
        contracts.build_experiment(fields)
    assert any(d.code == "DIMENSION_NOT_DISJOINT" for d in excinfo.value.defects)


def test_experiment_blocked_pairing_requires_random_seed() -> None:
    _, _, _, experiment, _ = _graph()
    fields = copy.deepcopy(experiment)
    fields["pairing"] = {"method": "BLOCKED", "random_seed": None}
    del fields["experiment_digest"]
    del fields["schema"]
    with pytest.raises(ContractError) as excinfo:
        contracts.build_experiment(fields)
    assert any(d.code == "BLOCKED_REQUIRES_SEED" for d in excinfo.value.defects)


def test_experiment_paired_by_scenario_forbids_random_seed() -> None:
    _, _, _, experiment, _ = _graph()
    fields = copy.deepcopy(experiment)
    fields["pairing"] = {"method": "PAIRED_BY_SCENARIO", "random_seed": 7}
    del fields["experiment_digest"]
    del fields["schema"]
    with pytest.raises(ContractError) as excinfo:
        contracts.build_experiment(fields)
    assert any(d.code == "SEED_NOT_ALLOWED_EXCEPT_BLOCKED" for d in excinfo.value.defects)


def test_experiment_phase_must_be_in_closed_enum() -> None:
    _, _, _, experiment, _ = _graph()
    fields = copy.deepcopy(experiment)
    fields["phase"] = "SHIPPED"
    del fields["experiment_digest"]
    del fields["schema"]
    with pytest.raises(ContractError) as excinfo:
        contracts.build_experiment(fields)
    assert any(d.code == "NOT_IN_ENUM" for d in excinfo.value.defects)


def test_experiment_authorship_reviewer_must_be_independent() -> None:
    _, _, _, experiment, _ = _graph()
    fields = copy.deepcopy(experiment)
    fields["authorship"] = {"author_ref": "person:sol", "independent_reviewer_ref": "person:sol"}
    del fields["experiment_digest"]
    del fields["schema"]
    with pytest.raises(ContractError) as excinfo:
        contracts.build_experiment(fields)
    assert any(d.code == "REVIEWER_NOT_INDEPENDENT" for d in excinfo.value.defects)


def test_experiment_own_digest_verified() -> None:
    _, _, _, experiment, _ = _graph()
    tampered = copy.deepcopy(experiment)
    tampered["analysis_version"] = "mastermind.tampered_analysis.v1"
    with pytest.raises(ContractError) as excinfo:
        contracts.validate_experiment_shape(tampered)
    assert any(d.code == "DIGEST_MISMATCH" for d in excinfo.value.defects)


# ---------------------------------------------------------------------------
# Experiment graph verification
# ---------------------------------------------------------------------------


def test_verify_experiment_graph_succeeds_for_a_consistent_experiment() -> None:
    _, _, _, experiment, resolver = _graph()
    result = verification.verify_experiment_graph(experiment, resolver)
    assert result.scope == "EVALUATION_GRAPH_VERIFIED"
    assert result.artifact_id == experiment["experiment_id"]


def test_verify_experiment_graph_fails_on_missing_configuration() -> None:
    scenario, config_a, _, experiment, _ = _graph()
    resolver = MemoryArtifactResolver.build(scenarios=(scenario,), configurations=(config_a,))  # config_b missing
    with pytest.raises(VerificationContextError) as excinfo:
        verification.verify_experiment_graph(experiment, resolver)
    assert any(d.code == "CONFIGURATION_NOT_RESOLVED" for d in excinfo.value.defects)


def test_verify_experiment_graph_fails_on_missing_scenario() -> None:
    _, config_a, config_b, experiment, _ = _graph()
    resolver = MemoryArtifactResolver.build(configurations=(config_a, config_b))  # scenario missing
    with pytest.raises(VerificationContextError) as excinfo:
        verification.verify_experiment_graph(experiment, resolver)
    assert any(d.code == "SCENARIO_NOT_RESOLVED" for d in excinfo.value.defects)


def _redigest_configuration(document: dict) -> dict:
    from scripts.agent_eval.canonical import add_document_digest

    return add_document_digest({k: v for k, v in document.items() if k != "configuration_digest"}, "configuration_digest")


def _redigest_experiment(document: dict) -> dict:
    from scripts.agent_eval.canonical import add_document_digest

    return add_document_digest({k: v for k, v in document.items() if k != "experiment_digest"}, "experiment_digest")


def test_verify_experiment_graph_fails_on_substituted_configuration_digest() -> None:
    scenario, config_a, config_b, experiment, _ = _graph()
    tampered = copy.deepcopy(config_a)
    tampered["randomness"]["seed"] = 999999
    tampered = _redigest_configuration(tampered)
    # resolver now holds a configuration whose digest no longer matches what
    # the (unmodified) experiment manifest recorded for that configuration_id
    resolver = MemoryArtifactResolver.build(scenarios=(scenario,), configurations=(tampered, config_b))
    with pytest.raises(VerificationContextError) as excinfo:
        verification.verify_experiment_graph(experiment, resolver)
    assert any(d.code == "CONFIGURATION_DIGEST_MISMATCH" for d in excinfo.value.defects)


def test_verify_experiment_graph_fails_on_incompatible_configuration() -> None:
    scenario, config_a, config_b, experiment, _ = _graph()
    incompatible = copy.deepcopy(config_a)
    incompatible["capabilities"]["declared_capability_ids"] = ["execute_shell", "read_file", "search_repo"]
    incompatible = _redigest_configuration(incompatible)
    # experiment must reference the tampered digest so the experiment's own
    # shape validation matches what's now in the resolver
    tampered_experiment = copy.deepcopy(experiment)
    for arm in tampered_experiment["arms"]:
        if arm["configuration_id"] == incompatible["configuration_id"]:
            arm["configuration_digest"] = incompatible["configuration_digest"]
    tampered_experiment = _redigest_experiment(tampered_experiment)
    resolver = MemoryArtifactResolver.build(scenarios=(scenario,), configurations=(incompatible, config_b))
    with pytest.raises(VerificationContextError) as excinfo:
        verification.verify_experiment_graph(tampered_experiment, resolver)
    assert any(d.code == "CAPABILITY_FORBIDDEN" for d in excinfo.value.defects)


def test_verify_experiment_graph_never_downgrades_missing_artifact_to_warning() -> None:
    # a missing scenario/configuration must raise, never silently return a
    # partial VerificationResult
    scenario, config_a, config_b, experiment, _ = _graph()
    empty_resolver = MemoryArtifactResolver.build()
    with pytest.raises(VerificationContextError):
        verification.verify_experiment_graph(experiment, empty_resolver)
