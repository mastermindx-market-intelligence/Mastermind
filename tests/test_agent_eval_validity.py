"""EVAL-R0 Task 4: run draft, deterministic validity, immutable run."""
from __future__ import annotations

import copy

import pytest

from scripts.agent_eval import contracts, validity
from scripts.agent_eval.errors import ContractError
from tests.agent_eval_factories import (
    build_alternate_configuration,
    build_baseline_configuration,
    build_baseline_scenario,
    build_run_draft,
    build_two_arm_experiment,
)

VALIDATOR_ID = "mastermind.eval_r0_finalizer.v1"
VALIDATOR_VERSION = "1"
VALIDATOR_CODE_REF = "git:mastermindx-market-intelligence/Mastermind@" + "a" * 40
VALIDATED_AT = "2026-08-25T00:00:10Z"
CREATED_AT = "2026-08-25T00:00:11Z"


def _graph():
    scenario = build_baseline_scenario()
    config_a = build_baseline_configuration()
    config_b = build_alternate_configuration()
    experiment = build_two_arm_experiment(scenario, config_a, config_b)
    return scenario, config_a, config_b, experiment


def _finalize(scenario, configuration, experiment, draft):
    return validity.finalize_run_receipt(
        scenario,
        configuration,
        experiment,
        draft,
        validator_id=VALIDATOR_ID,
        validator_version=VALIDATOR_VERSION,
        validator_code_ref=VALIDATOR_CODE_REF,
        validated_at=VALIDATED_AT,
        created_at=CREATED_AT,
    )


# ---------------------------------------------------------------------------
# Draft shape
# ---------------------------------------------------------------------------


def test_clean_draft_is_shape_valid() -> None:
    scenario, config_a, _, experiment = _graph()
    draft = build_run_draft(scenario, config_a, experiment, arm_id="arm_a", replicate_index=1)
    assert contracts.validate_run_draft_shape(draft) == "SHAPE_VALID"


def test_draft_rejects_unknown_field() -> None:
    scenario, config_a, _, experiment = _graph()
    draft = build_run_draft(scenario, config_a, experiment, arm_id="arm_a", replicate_index=1)
    draft["score"] = 1
    with pytest.raises(ContractError) as excinfo:
        contracts.validate_run_draft_shape(draft)
    assert any(d.code == "UNKNOWN_FIELD" for d in excinfo.value.defects)


@pytest.mark.parametrize("forbidden", ["pass_fail", "winner", "route", "policy_accepted"])
def test_draft_cannot_carry_runner_result_fields(forbidden: str) -> None:
    scenario, config_a, _, experiment = _graph()
    draft = build_run_draft(scenario, config_a, experiment, arm_id="arm_a", replicate_index=1)
    draft[forbidden] = True
    with pytest.raises(ContractError):
        contracts.validate_run_draft_shape(draft)


def test_draft_schema_forbids_validity_created_at_or_digest_fields() -> None:
    scenario, config_a, _, experiment = _graph()
    draft = build_run_draft(scenario, config_a, experiment, arm_id="arm_a", replicate_index=1)
    for forbidden in ("validity", "created_at", "run_digest"):
        mutated = dict(draft)
        mutated[forbidden] = "anything"
        with pytest.raises(ContractError):
            contracts.validate_run_draft_shape(mutated)


def test_standalone_run_without_experiment_requires_null_comparison() -> None:
    scenario, config_a, _, experiment = _graph()
    draft = build_run_draft(scenario, config_a, experiment, arm_id="arm_a", replicate_index=1)
    draft["comparison"] = {"experiment_id": None, "arm_id": "arm_a", "pair_key": None, "replicate_index": None}
    with pytest.raises(ContractError) as excinfo:
        contracts.validate_run_draft_shape(draft)
    assert any(d.code == "STANDALONE_RUN_MUST_HAVE_NULL_COMPARISON" for d in excinfo.value.defects)


def test_experiment_run_requires_arm_and_replicate() -> None:
    scenario, config_a, _, experiment = _graph()
    draft = build_run_draft(scenario, config_a, experiment, arm_id="arm_a", replicate_index=1)
    draft["comparison"]["arm_id"] = None
    with pytest.raises(ContractError) as excinfo:
        contracts.validate_run_draft_shape(draft)
    assert any(d.code == "EXPERIMENT_RUN_REQUIRES_ARM_AND_REPLICATE" for d in excinfo.value.defects)


def test_no_effect_state_must_have_null_refs() -> None:
    scenario, config_a, _, experiment = _graph()
    draft = build_run_draft(scenario, config_a, experiment, arm_id="arm_a", replicate_index=1)
    draft["effect"]["operation_ref"] = "op:demo"
    with pytest.raises(ContractError) as excinfo:
        contracts.validate_run_draft_shape(draft)
    assert any(d.code == "NO_EFFECT_MUST_HAVE_NULL_REFS" for d in excinfo.value.defects)


def test_proven_cleanup_requires_proof() -> None:
    scenario, config_a, _, experiment = _graph()
    draft = build_run_draft(scenario, config_a, experiment, arm_id="arm_a", replicate_index=1)
    draft["cleanup"]["proof"] = None
    with pytest.raises(ContractError) as excinfo:
        contracts.validate_run_draft_shape(draft)
    assert any(d.code == "PROVEN_CLEANUP_REQUIRES_PROOF" for d in excinfo.value.defects)


def test_unproven_cleanup_must_not_carry_proof() -> None:
    scenario, config_a, _, experiment = _graph()
    draft = build_run_draft(scenario, config_a, experiment, arm_id="arm_a", replicate_index=1)
    draft["cleanup"]["status"] = "UNPROVEN"
    with pytest.raises(ContractError) as excinfo:
        contracts.validate_run_draft_shape(draft)
    assert any(d.code == "UNPROVEN_CLEANUP_MUST_NOT_CARRY_PROOF" for d in excinfo.value.defects)


def test_duration_must_equal_elapsed_when_both_present() -> None:
    scenario, config_a, _, experiment = _graph()
    draft = build_run_draft(scenario, config_a, experiment, arm_id="arm_a", replicate_index=1)
    draft["timing"]["monotonic_duration_ms"] = 9999
    with pytest.raises(ContractError) as excinfo:
        contracts.validate_run_draft_shape(draft)
    assert any(d.code == "DURATION_ELAPSED_MISMATCH" for d in excinfo.value.defects)


def test_public_destination_requires_raw_value() -> None:
    scenario, config_a, _, experiment = _graph()
    draft = build_run_draft(scenario, config_a, experiment, arm_id="arm_a", replicate_index=1)
    draft["observations"]["observed_network_destinations"] = [
        {"destination_class": "PUBLIC", "value_digest": "sha256:" + "a" * 64, "raw_value": None}
    ]
    with pytest.raises(ContractError) as excinfo:
        contracts.validate_run_draft_shape(draft)
    assert any(d.code == "PUBLIC_DESTINATION_REQUIRES_RAW_VALUE" for d in excinfo.value.defects)


def test_nonpublic_destination_must_not_carry_raw_value() -> None:
    scenario, config_a, _, experiment = _graph()
    draft = build_run_draft(scenario, config_a, experiment, arm_id="arm_a", replicate_index=1)
    draft["observations"]["observed_network_destinations"] = [
        {"destination_class": "PRIVATE_RANGE", "value_digest": "sha256:" + "a" * 64, "raw_value": "10.0.0.5"}
    ]
    with pytest.raises(ContractError) as excinfo:
        contracts.validate_run_draft_shape(draft)
    assert any(d.code == "NONPUBLIC_DESTINATION_MUST_NOT_CARRY_RAW_VALUE" for d in excinfo.value.defects)


# ---------------------------------------------------------------------------
# MAJOR-1 review repair: §3.7 boundary enforcement -- shape validation must
# not merely trust a caller-supplied destination_class/value_digest pair.
# sanitize_observed_destination is the only law-abiding PRODUCER, but this
# is a shape-validation REFUSAL law, not merely a helper contract, so these
# probes hit _v_observed_destination directly (never via the helper).
# ---------------------------------------------------------------------------


def test_honest_loopback_with_raw_value_is_refused() -> None:
    # reviewer's exact probe: raw 127.0.0.1 with an HONEST LOOPBACK class
    # must still be refused -- raw_value must be null for any non-PUBLIC
    # class, honesty of the class does not create an exception.
    scenario, config_a, _, experiment = _graph()
    draft = build_run_draft(scenario, config_a, experiment, arm_id="arm_a", replicate_index=1)
    assert contracts.classify_destination("127.0.0.1") == "LOOPBACK"
    draft["observations"]["observed_network_destinations"] = [
        {
            "destination_class": "LOOPBACK",
            "value_digest": contracts.digest_value("127.0.0.1"),
            "raw_value": "127.0.0.1",
        }
    ]
    with pytest.raises(ContractError) as excinfo:
        contracts.validate_run_draft_shape(draft)
    assert any(d.code == "NONPUBLIC_DESTINATION_MUST_NOT_CARRY_RAW_VALUE" for d in excinfo.value.defects)


def test_forged_public_class_over_a_private_literal_is_refused() -> None:
    # reviewer's exact probe: claiming PUBLIC over a private literal (to
    # smuggle a raw value past the PUBLIC-only raw_value rule) must be
    # refused by recomputing classify_destination(raw_value) and comparing.
    scenario, config_a, _, experiment = _graph()
    draft = build_run_draft(scenario, config_a, experiment, arm_id="arm_a", replicate_index=1)
    assert contracts.classify_destination("10.0.0.5") == "PRIVATE_RANGE"
    draft["observations"]["observed_network_destinations"] = [
        {
            "destination_class": "PUBLIC",  # forged
            "value_digest": contracts.digest_value("10.0.0.5"),
            "raw_value": "10.0.0.5",
        }
    ]
    with pytest.raises(ContractError) as excinfo:
        contracts.validate_run_draft_shape(draft)
    assert any(d.code == "DESTINATION_CLASS_FORGED" for d in excinfo.value.defects)


def test_forged_value_digest_is_refused() -> None:
    # reviewer's exact probe: an honest PUBLIC class but a digest that does
    # not actually hash the declared raw_value must be refused.
    scenario, config_a, _, experiment = _graph()
    draft = build_run_draft(scenario, config_a, experiment, arm_id="arm_a", replicate_index=1)
    draft["observations"]["observed_network_destinations"] = [
        {
            "destination_class": "PUBLIC",
            "value_digest": "sha256:" + "9" * 64,  # does not match digest_value("8.8.8.8")
            "raw_value": "8.8.8.8",
        }
    ]
    with pytest.raises(ContractError) as excinfo:
        contracts.validate_run_draft_shape(draft)
    assert any(d.code == "DESTINATION_DIGEST_FORGED" for d in excinfo.value.defects)


def test_honest_public_destination_still_passes() -> None:
    # positive control: an honestly-produced PUBLIC observation (exactly
    # what sanitize_observed_destination emits) is accepted.
    scenario, config_a, _, experiment = _graph()
    draft = build_run_draft(scenario, config_a, experiment, arm_id="arm_a", replicate_index=1)
    draft["observations"]["observed_network_destinations"] = [contracts.sanitize_observed_destination("8.8.8.8")]
    assert contracts.validate_run_draft_shape(draft) == "SHAPE_VALID"


# ---------------------------------------------------------------------------
# R-B1-2/R-B1-3: destination classifier
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw_value,expected",
    [
        ("127.0.0.1", "LOOPBACK"),
        ("127.0.0.1:8080", "LOOPBACK"),
        ("::1", "LOOPBACK"),
        ("10.0.0.5", "PRIVATE_RANGE"),
        ("192.168.1.20", "PRIVATE_RANGE"),
        ("169.254.1.1", "PRIVATE_RANGE"),
        ("8.8.8.8", "PUBLIC"),
        ("8.8.8.8:443", "PUBLIC"),
        ("example.com", "UNRESOLVED_NAME"),
        ("example.com:443", "UNRESOLVED_NAME"),
        ("not an ip at all", "UNRESOLVED_NAME"),
    ],
)
def test_classify_destination_uses_ipaddress_semantics_only(raw_value: str, expected: str) -> None:
    assert contracts.classify_destination(raw_value) == expected


def test_hostname_destinations_always_classify_unresolved_name() -> None:
    # R-B1-3: because R0 may never resolve names, every hostname is
    # UNRESOLVED_NAME by design (fail-closed), never treated as PUBLIC.
    for hostname in ("api.anthropic.com", "internal-service.corp", "localhost.example"):
        assert contracts.classify_destination(hostname) == "UNRESOLVED_NAME"


def test_sanitize_observed_destination_hides_raw_value_unless_public() -> None:
    private = contracts.sanitize_observed_destination("10.0.0.5")
    assert private["destination_class"] == "PRIVATE_RANGE"
    assert private["raw_value"] is None
    public = contracts.sanitize_observed_destination("8.8.8.8")
    assert public["destination_class"] == "PUBLIC"
    assert public["raw_value"] == "8.8.8.8"


# ---------------------------------------------------------------------------
# evaluate_validity / finalize_run_receipt: the two-arm vertical
# ---------------------------------------------------------------------------


def test_clean_baseline_run_is_technically_valid() -> None:
    scenario, config_a, _, experiment = _graph()
    draft = build_run_draft(scenario, config_a, experiment, arm_id="arm_a", replicate_index=1)
    run = _finalize(scenario, config_a, experiment, draft)
    assert run["validity"]["status"] == "VALID"
    assert run["validity"]["reason_codes"] == []


def test_clean_completion_yields_valid_not_valid_pass() -> None:
    # completion status never determines task correctness (design §5.3/plan
    # Task4 acceptance) -- a runner cannot assert VALID_PASS.
    scenario, config_a, _, experiment = _graph()
    draft = build_run_draft(scenario, config_a, experiment, arm_id="arm_a", replicate_index=1)
    run = _finalize(scenario, config_a, experiment, draft)
    assert run["validity"]["status"] not in {"VALID_PASS", "VALID_FAIL", "VALID_PARTIAL"}


def test_served_model_mismatch_run_is_invalid_configuration() -> None:
    scenario, config_a, _, experiment = _graph()
    draft = build_run_draft(scenario, config_a, experiment, arm_id="arm_a", replicate_index=1, model_served="claude-opus-9")
    run = _finalize(scenario, config_a, experiment, draft)
    assert run["validity"]["status"] == "INVALID_CONFIGURATION"
    assert "MODEL_SERVED_MISMATCH" in run["validity"]["reason_codes"]


def test_finalizer_recomputes_from_stored_fields_only_no_runner_self_grade() -> None:
    # a draft cannot smuggle in its own validity claim -- the schema itself
    # forbids a validity field on the draft (see test_draft_schema_forbids_...)
    scenario, config_a, _, experiment = _graph()
    draft = build_run_draft(scenario, config_a, experiment, arm_id="arm_a", replicate_index=1)
    assert "validity" not in draft
    run = _finalize(scenario, config_a, experiment, draft)
    assert run["validity"]["validator_id"] == VALIDATOR_ID


def test_finalizer_rejects_wrong_supplied_scenario() -> None:
    scenario, config_a, config_b, experiment = _graph()
    other_scenario = build_baseline_scenario()  # equal-content but let's mutate identity instead
    draft = build_run_draft(scenario, config_a, experiment, arm_id="arm_a", replicate_index=1)
    wrong_scenario = copy.deepcopy(scenario)
    wrong_scenario["scenario_version"] = 999  # will not match draft's claimed version -- forces mismatch path
    # Because build_scenario requires internal consistency we instead assert
    # that finalize_run_receipt raises when scenario identity disagrees with
    # the draft's own claim.
    from scripts.agent_eval.canonical import add_document_digest as _add_digest

    tampered_scenario_fields = {k: v for k, v in wrong_scenario.items() if k != "scenario_digest"}
    tampered_scenario_fields["scenario_id"] = "scenario:evaluation_contract_integrity:other_case"
    tampered_scenario_fields["supersedes"] = None
    tampered_scenario_fields["scenario_version"] = 1
    tampered_scenario = _add_digest(tampered_scenario_fields, "scenario_digest")
    with pytest.raises(ContractError) as excinfo:
        _finalize(tampered_scenario, config_a, experiment, draft)
    assert any(d.code == "SCENARIO_IDENTITY_MISMATCH" for d in excinfo.value.defects)


def test_finalizer_rejects_wrong_supplied_configuration() -> None:
    scenario, config_a, config_b, experiment = _graph()
    draft = build_run_draft(scenario, config_a, experiment, arm_id="arm_a", replicate_index=1)
    with pytest.raises(ContractError) as excinfo:
        _finalize(scenario, config_b, experiment, draft)
    assert any(d.code == "CONFIGURATION_IDENTITY_MISMATCH" for d in excinfo.value.defects)


def test_mutating_observed_source_digest_changes_recomputed_validity() -> None:
    # mutating/deleting any validity input changes recomputation (Task4
    # acceptance criterion)
    scenario, config_a, _, experiment = _graph()
    draft = build_run_draft(scenario, config_a, experiment, arm_id="arm_a", replicate_index=1)
    draft["observations"]["observed_sources"][0]["digest"] = "sha256:" + "9" * 64
    run = _finalize(scenario, config_a, experiment, draft)
    assert run["validity"]["status"] == "INVALID_LEAKAGE"
    assert "SOURCE_DIGEST_MISMATCH" in run["validity"]["reason_codes"]


def test_unauthorized_source_yields_invalid_leakage() -> None:
    scenario, config_a, _, experiment = _graph()
    draft = build_run_draft(scenario, config_a, experiment, arm_id="arm_a", replicate_index=1)
    draft["observations"]["observed_sources"].append(
        {"artifact_ref": "git:mastermindx-market-intelligence/Mastermind@" + "c" * 40 + "#not_allowlisted.md", "digest": "sha256:" + "1" * 64}
    )
    run = _finalize(scenario, config_a, experiment, draft)
    assert run["validity"]["status"] == "INVALID_LEAKAGE"
    assert "UNAUTHORIZED_SOURCE" in run["validity"]["reason_codes"]


def test_hidden_solution_source_yields_invalid_leakage() -> None:
    scenario, config_a, _, experiment = _graph()
    draft = build_run_draft(scenario, config_a, experiment, arm_id="arm_a", replicate_index=1)
    hidden_ref = scenario["source_policy"]["solution_refs_hidden"][0]
    draft["observations"]["observed_sources"].append({"artifact_ref": hidden_ref, "digest": "sha256:" + "2" * 64})
    run = _finalize(scenario, config_a, experiment, draft)
    assert run["validity"]["status"] == "INVALID_LEAKAGE"
    assert "HIDDEN_SOLUTION_SOURCE" in run["validity"]["reason_codes"]


def test_effect_unknown_always_invalidates_with_top_precedence() -> None:
    scenario, config_a, _, experiment = _graph()
    draft = build_run_draft(scenario, config_a, experiment, arm_id="arm_a", replicate_index=1)
    # also introduce a leakage-tier violation to prove EFFECT_UNKNOWN wins precedence
    draft["observations"]["observed_sources"][0]["digest"] = "sha256:" + "9" * 64
    draft["effect"] = {"state": "EFFECT_UNKNOWN", "operation_ref": None, "reconciliation_ref": None}
    run = _finalize(scenario, config_a, experiment, draft)
    assert run["validity"]["status"] == "INVALID_EFFECT_UNKNOWN"
    assert "EFFECT_UNKNOWN" in run["validity"]["reason_codes"]
    # lower-priority reason still retained even though it did not decide status
    assert "SOURCE_DIGEST_MISMATCH" in run["validity"]["reason_codes"]


def test_cleanup_unproven_outranks_configuration_mismatch() -> None:
    scenario, config_a, _, experiment = _graph()
    draft = build_run_draft(scenario, config_a, experiment, arm_id="arm_a", replicate_index=1, model_served="claude-opus-9")
    draft["cleanup"] = {"status": "UNPROVEN", "proof": None}
    run = _finalize(scenario, config_a, experiment, draft)
    assert run["validity"]["status"] == "INVALID_CLEANUP"
    assert "CLEANUP_UNPROVEN" in run["validity"]["reason_codes"]
    assert "MODEL_SERVED_MISMATCH" in run["validity"]["reason_codes"]  # retained, lower priority


def test_forbidden_capability_observed_is_invalid_configuration() -> None:
    scenario, config_a, _, experiment = _graph()
    draft = build_run_draft(scenario, config_a, experiment, arm_id="arm_a", replicate_index=1)
    draft["observations"]["observed_capability_ids"] = ["execute_shell"]
    draft["capabilities"]["profile_id"] = config_a["capabilities"]["profile_id"]  # keep other fields aligned
    run = _finalize(scenario, config_a, experiment, draft)
    assert run["validity"]["status"] == "INVALID_CONFIGURATION"
    assert "FORBIDDEN_CAPABILITY" in run["validity"]["reason_codes"]


def test_capability_drift_when_observed_exceeds_declared() -> None:
    scenario, config_a, _, experiment = _graph()
    draft = build_run_draft(scenario, config_a, experiment, arm_id="arm_a", replicate_index=1)
    draft["observations"]["observed_capability_ids"] = ["read_file", "search_repo"]
    # search_repo IS declared/allowed, so widen with something declared but
    # not part of the baseline observation set is not itself drift; force
    # real drift by observing a tool digest that was never declared.
    draft["observations"]["observed_tool_schema_digests"] = ["sha256:" + "7" * 64]
    run = _finalize(scenario, config_a, experiment, draft)
    assert run["validity"]["status"] == "INVALID_CONFIGURATION"
    assert "TOOL_SCHEMA_DRIFT" in run["validity"]["reason_codes"]


def test_fresh_process_unproven_is_invalid_configuration() -> None:
    scenario, config_a, _, experiment = _graph()
    draft = build_run_draft(scenario, config_a, experiment, arm_id="arm_a", replicate_index=1)
    draft["execution"]["fresh_process_observed"] = False
    run = _finalize(scenario, config_a, experiment, draft)
    assert run["validity"]["status"] == "INVALID_CONFIGURATION"
    assert "FRESH_PROCESS_UNPROVEN" in run["validity"]["reason_codes"]


def test_resume_used_when_forbidden_is_invalid_configuration() -> None:
    scenario, config_a, _, experiment = _graph()
    draft = build_run_draft(scenario, config_a, experiment, arm_id="arm_a", replicate_index=1)
    draft["execution"]["resume_used"] = True
    run = _finalize(scenario, config_a, experiment, draft)
    assert run["validity"]["status"] == "INVALID_CONFIGURATION"
    assert "RESUME_FORBIDDEN" in run["validity"]["reason_codes"]


def test_unexpected_network_destination_recomputes_from_digest_never_raw_value() -> None:
    scenario, config_a, _, experiment = _graph()
    draft = build_run_draft(scenario, config_a, experiment, arm_id="arm_a", replicate_index=1)
    draft["observations"]["observed_network_destinations"] = [contracts.sanitize_observed_destination("10.0.0.9")]
    run = _finalize(scenario, config_a, experiment, draft)
    assert run["validity"]["status"] == "INVALID_CONFIGURATION"
    assert "UNEXPECTED_NETWORK_DESTINATION" in run["validity"]["reason_codes"]
    # sanitized: no raw private IP anywhere in the persisted run
    assert "10.0.0.9" not in str(run)


def test_degradation_not_allowed_when_undeclared() -> None:
    scenario, config_a, _, experiment = _graph()
    draft = build_run_draft(scenario, config_a, experiment, arm_id="arm_a", replicate_index=1)
    draft["observations"]["dependency_degradations"] = ["UNDECLARED_DEGRADATION"]
    run = _finalize(scenario, config_a, experiment, draft)
    assert run["validity"]["status"] == "INVALID_CONFIGURATION"
    assert "DEGRADATION_NOT_ALLOWED" in run["validity"]["reason_codes"]


def test_allowed_degradation_yields_degraded_dependency() -> None:
    scenario, config_a, _, experiment = _graph()
    draft = build_run_draft(scenario, config_a, experiment, arm_id="arm_a", replicate_index=1)
    draft["observations"]["dependency_degradations"] = list(scenario["execution_policy"]["allowed_degradations"])
    run = _finalize(scenario, config_a, experiment, draft)
    assert run["validity"]["status"] == "DEGRADED_DEPENDENCY"
    assert run["validity"]["reason_codes"] == []


def test_pair_identity_missing_when_pair_key_does_not_match_derivation() -> None:
    scenario, config_a, _, experiment = _graph()
    draft = build_run_draft(scenario, config_a, experiment, arm_id="arm_a", replicate_index=1)
    draft["comparison"]["pair_key"] = "pair:wrong:v1:r1"
    run = _finalize(scenario, config_a, experiment, draft)
    assert "PAIR_IDENTITY_MISSING" in run["validity"]["reason_codes"]


def test_pair_identity_missing_when_null_under_paired_by_scenario() -> None:
    scenario, config_a, _, experiment = _graph()
    draft = build_run_draft(scenario, config_a, experiment, arm_id="arm_a", replicate_index=1)
    draft["comparison"]["pair_key"] = None
    run = _finalize(scenario, config_a, experiment, draft)
    assert "PAIR_IDENTITY_MISSING" in run["validity"]["reason_codes"]


def test_pair_identity_missing_when_nonnull_under_unpaired_method() -> None:
    # MAJOR-2 review repair: R-B1-1 condition 3 ("method is UNPAIRED and
    # pair_key is non-null") had no direct test -- a mutation of the
    # UNPAIRED branch's guard could have survived undetected. Build a fresh
    # UNPAIRED-method experiment (PAIRED_BY_SCENARIO is the only method the
    # shared two-arm factory produces) and supply a non-null pair_key.
    from tests.agent_eval_factories import build_two_arm_experiment_fields

    scenario, config_a, config_b, experiment = _graph()
    unpaired_fields = build_two_arm_experiment_fields(scenario, config_a, config_b)
    unpaired_fields["pairing"] = {"method": "UNPAIRED", "random_seed": None}
    unpaired_experiment = contracts.build_experiment(unpaired_fields)

    draft = build_run_draft(scenario, config_a, unpaired_experiment, arm_id="arm_a", replicate_index=1)
    draft["comparison"]["pair_key"] = f"pair:{scenario['scenario_id']}:v{scenario['scenario_version']}:r1"  # non-null, forbidden under UNPAIRED
    run = _finalize(scenario, config_a, unpaired_experiment, draft)

    assert "PAIR_IDENTITY_MISSING" in run["validity"]["reason_codes"]
    assert run["validity"]["status"] == "INVALID_CONFIGURATION"


def test_replicate_out_of_range() -> None:
    scenario, config_a, _, experiment = _graph()
    draft = build_run_draft(scenario, config_a, experiment, arm_id="arm_a", replicate_index=1)
    draft["comparison"]["replicate_index"] = 5  # target is 1
    draft["comparison"]["pair_key"] = f"pair:{scenario['scenario_id']}:v{scenario['scenario_version']}:r5"
    run = _finalize(scenario, config_a, experiment, draft)
    assert "REPLICATE_OUT_OF_RANGE" in run["validity"]["reason_codes"]


def test_experiment_arm_mismatch_when_arm_and_configuration_disagree() -> None:
    scenario, config_a, _, experiment = _graph()
    draft = build_run_draft(scenario, config_a, experiment, arm_id="arm_b", replicate_index=1)
    run = _finalize(scenario, config_a, experiment, draft)
    assert "EXPERIMENT_ARM_MISMATCH" in run["validity"]["reason_codes"]


def test_temporal_cutoff_mismatch() -> None:
    scenario, config_a, _, experiment = _graph()
    draft = build_run_draft(scenario, config_a, experiment, arm_id="arm_a", replicate_index=1)
    draft["scenario"]["temporal_cutoff"] = "2020-01-01T00:00:00Z"
    run = _finalize(scenario, config_a, experiment, draft)
    assert "TEMPORAL_CUTOFF_MISMATCH" in run["validity"]["reason_codes"]


def test_source_policy_digest_mismatch() -> None:
    scenario, config_a, _, experiment = _graph()
    draft = build_run_draft(scenario, config_a, experiment, arm_id="arm_a", replicate_index=1)
    draft["context"]["source_policy_digest"] = "sha256:" + "3" * 64
    run = _finalize(scenario, config_a, experiment, draft)
    assert "SOURCE_POLICY_DIGEST_MISMATCH" in run["validity"]["reason_codes"]


def test_standalone_run_without_experiment_can_still_be_finalized() -> None:
    scenario, config_a, _, experiment = _graph()
    draft = build_run_draft(scenario, config_a, experiment, arm_id="arm_a", replicate_index=1)
    draft["comparison"] = {"experiment_id": None, "arm_id": None, "pair_key": None, "replicate_index": None}
    run = _finalize(scenario, config_a, None, draft)
    assert run["validity"]["status"] == "VALID"


def test_time_order_started_before_completed_before_validated_before_created() -> None:
    scenario, config_a, _, experiment = _graph()
    draft = build_run_draft(scenario, config_a, experiment, arm_id="arm_a", replicate_index=1)
    with pytest.raises(ContractError):
        # validated_at BEFORE completed_at violates the order law
        validity.finalize_run_receipt(
            scenario,
            config_a,
            experiment,
            draft,
            validator_id=VALIDATOR_ID,
            validator_version=VALIDATOR_VERSION,
            validator_code_ref=VALIDATOR_CODE_REF,
            validated_at="2020-01-01T00:00:00Z",
            created_at=CREATED_AT,
        )
