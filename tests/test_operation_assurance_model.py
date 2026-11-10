"""tests.test_operation_assurance_model — OLS-A1 parser/grammar/identity contract.

Covers the strict JSON boundary, exact closed wire, bidirectional reference
law, hard resource ceilings, and canonical model identity described in
(precedence order):

1. docs/superpowers/specs/2026-08-31-operation-assurance-a1-wire-release-finalization.md
2. docs/superpowers/specs/2026-08-30-operation-assurance-immutable-report-projection-clarification.md
3. docs/superpowers/specs/2026-08-30-operation-assurance-model-fidelity-counterexample-validation-amendment.md
4. docs/superpowers/specs/2026-08-30-operation-assurance-a1-trusted-input-total-proof-clarification.md
5. docs/superpowers/specs/2026-08-30-operation-assurance-a1-controlling-execution-overlay.md
6. docs/superpowers/plans/2026-08-30-operation-assurance-core.md
"""
from __future__ import annotations

import json

import pytest

from control_plane.operation_assurance_model import (
    ModelParseError,
    parse_model_text,
    canonical_json,
    sha256_hex,
)
from tests.operation_assurance_fixture_lib import (
    REF,
    abstraction_contract,
    clone,
    dumps,
    effect,
    environment_assumption,
    fairness,
    gate,
    guard,
    minimal_model,
    model_gap,
    obligation,
    outcome,
    resource,
    source_record,
    source_snapshot,
    state_forbidden,
    transition,
    transition_forbidden,
)


def test_minimal_model_parses() -> None:
    m = parse_model_text(dumps(minimal_model()))
    assert m.schema == "mastermind.operation_assurance_model.v1"
    assert m.model_id == "om_minimal_v1"
    assert len(m.transitions) == 1
    assert m.transitions[0].transition_id == "finish"


def test_missing_abstraction_contract_is_refused() -> None:
    d = clone(minimal_model())
    del d["abstraction_contract"]
    with pytest.raises(ModelParseError):
        parse_model_text(dumps(d))


def test_unknown_top_level_field_is_refused() -> None:
    d = clone(minimal_model())
    d["unexpected_field"] = "x"
    with pytest.raises(ModelParseError):
        parse_model_text(dumps(d))


def test_unknown_nested_field_is_refused() -> None:
    d = clone(minimal_model())
    d["transitions"][0]["extra_key"] = "nope"
    with pytest.raises(ModelParseError):
        parse_model_text(dumps(d))


def test_duplicate_top_level_json_key_is_refused() -> None:
    raw = dumps(minimal_model())
    # inject a duplicate "schema" key manually — json.dumps never does this,
    # so we hand-craft the raw text.
    hostile = raw[:-1] + ', "schema": "mastermind.operation_assurance_model.v1"}'
    with pytest.raises(ModelParseError):
        parse_model_text(hostile)


def test_duplicate_nested_json_key_is_refused() -> None:
    hostile = (
        '{"schema": "mastermind.operation_assurance_model.v1", '
        '"outer": {"a": 1, "a": 2}}'
    )
    with pytest.raises(ModelParseError):
        parse_model_text(hostile)


@pytest.mark.parametrize("token", ["NaN", "Infinity", "-Infinity"])
def test_non_finite_json_constants_are_refused(token: str) -> None:
    hostile = '{"schema": "x", "bad": %s}' % token
    with pytest.raises(ModelParseError):
        parse_model_text(hostile)


def test_oversized_input_is_refused() -> None:
    d = clone(minimal_model())
    d["operation_ref"]["operation_key"] = "x" * 5_000_000
    with pytest.raises(ModelParseError):
        parse_model_text(dumps(d))


def test_malformed_json_is_refused() -> None:
    with pytest.raises(ModelParseError):
        parse_model_text("{not json")


def test_non_object_top_level_is_refused() -> None:
    with pytest.raises(ModelParseError):
        parse_model_text("[1, 2, 3]")


def test_trailing_garbage_after_json_is_refused() -> None:
    raw = dumps(minimal_model()) + " garbage"
    with pytest.raises(ModelParseError):
        parse_model_text(raw)


def test_excessive_json_depth_is_refused() -> None:
    inner = "1"
    for _ in range(200):
        inner = "[%s]" % inner
    hostile = '{"schema": "x", "deep": %s}' % inner
    with pytest.raises(ModelParseError):
        parse_model_text(hostile)


def test_compiler_invocation_mode_must_be_authored_input() -> None:
    d = clone(minimal_model())
    d["compiler"]["invocation_mode"] = "TRUSTED_COMPILER"
    with pytest.raises(ModelParseError):
        parse_model_text(dumps(d))


def test_unknown_abstraction_kind_is_refused() -> None:
    d = clone(minimal_model())
    d["abstraction_contract"]["kind"] = "NOT_A_REAL_KIND"
    with pytest.raises(ModelParseError):
        parse_model_text(dumps(d))


def test_unknown_preserves_value_is_refused() -> None:
    d = clone(minimal_model())
    d["abstraction_contract"]["preserves"] = ["NOT_A_PRESERVE"]
    with pytest.raises(ModelParseError):
        parse_model_text(dumps(d))


def test_strong_fairness_is_rejected() -> None:
    d = clone(minimal_model())
    d["fairness_assumptions"] = [
        {"fairness_id": "f1", "kind": "STRONG", "transition_ids": ["finish"], "source_refs": [REF]}
    ]
    d["transitions"][0]["fairness_ref"] = "f1"
    with pytest.raises(ModelParseError):
        parse_model_text(dumps(d))


def test_one_sided_fairness_reference_is_refused() -> None:
    d = clone(minimal_model())
    d["fairness_assumptions"] = [fairness("f1", ["finish"])]
    # transition never sets fairness_ref="f1" -> one-sided
    with pytest.raises(ModelParseError):
        parse_model_text(dumps(d))


def test_transition_fairness_ref_without_declaration_is_refused() -> None:
    d = clone(minimal_model())
    d["transitions"][0]["fairness_ref"] = "f_missing"
    with pytest.raises(ModelParseError):
        parse_model_text(dumps(d))


def test_one_sided_environment_assumption_reference_is_refused() -> None:
    d = clone(minimal_model())
    d["environment_assumptions"] = [environment_assumption("a1", ["finish"], ["OPTION_TO_COMPLETE"])]
    with pytest.raises(ModelParseError):
        parse_model_text(dumps(d))


def test_one_sided_gate_transition_reference_is_refused() -> None:
    d = clone(minimal_model())
    d["state_domains"]["gate_x"] = ["WAITING", "DONE"]
    d["initial_state"]["gate_x"] = "WAITING"
    d["external_gates"] = [
        gate(
            "g1",
            "EXTERNAL_GATE",
            [guard("gate_x", "EQ", "WAITING")],
            ["finish"],
            "finish",
        )
    ]
    # "finish" transition never lists gate_refs=["g1"] -> one-sided
    with pytest.raises(ModelParseError):
        parse_model_text(dumps(d))


def test_duplicate_effect_for_same_variable_is_refused() -> None:
    d = clone(minimal_model())
    d["transitions"][0]["effects"].append(effect("phase", "START"))
    with pytest.raises(ModelParseError):
        parse_model_text(dumps(d))


def test_duplicate_transition_id_is_refused() -> None:
    d = clone(minimal_model())
    d["transitions"].append(clone(d["transitions"][0]))
    with pytest.raises(ModelParseError):
        parse_model_text(dumps(d))


def test_guard_value_outside_domain_is_refused() -> None:
    d = clone(minimal_model())
    d["transitions"][0]["guards"][0]["value"] = "NOT_IN_DOMAIN"
    with pytest.raises(ModelParseError):
        parse_model_text(dumps(d))


def test_effect_value_outside_domain_is_refused() -> None:
    d = clone(minimal_model())
    d["transitions"][0]["effects"][0]["value"] = "NOT_IN_DOMAIN"
    with pytest.raises(ModelParseError):
        parse_model_text(dumps(d))


def test_unresolved_variable_reference_is_refused() -> None:
    d = clone(minimal_model())
    d["transitions"][0]["guards"][0]["variable"] = "no_such_variable"
    with pytest.raises(ModelParseError):
        parse_model_text(dumps(d))


def test_initial_state_key_set_must_equal_domain_key_set() -> None:
    d = clone(minimal_model())
    d["initial_state"]["extra_var"] = "X"
    with pytest.raises(ModelParseError):
        parse_model_text(dumps(d))


def test_initial_state_missing_key_is_refused() -> None:
    d = clone(minimal_model())
    del d["initial_state"]["phase"]
    with pytest.raises(ModelParseError):
        parse_model_text(dumps(d))


def test_empty_domain_is_refused() -> None:
    d = clone(minimal_model())
    d["state_domains"]["phase"] = []
    with pytest.raises(ModelParseError):
        parse_model_text(dumps(d))


def test_duplicate_domain_value_is_refused() -> None:
    d = clone(minimal_model())
    d["state_domains"]["phase"] = ["START", "START", "DONE"]
    with pytest.raises(ModelParseError):
        parse_model_text(dumps(d))


def test_boolean_is_never_coerced_to_integer() -> None:
    d = clone(minimal_model())
    d["exploration_limits"]["max_states"] = True
    with pytest.raises(ModelParseError):
        parse_model_text(dumps(d))


def test_max_states_zero_is_refused() -> None:
    d = clone(minimal_model())
    d["exploration_limits"]["max_states"] = 0
    with pytest.raises(ModelParseError):
        parse_model_text(dumps(d))


def test_max_states_above_hard_ceiling_is_refused() -> None:
    d = clone(minimal_model())
    d["exploration_limits"]["max_states"] = 10_000_000
    with pytest.raises(ModelParseError):
        parse_model_text(dumps(d))


def test_operation_ref_requires_exactly_one_identity() -> None:
    d = clone(minimal_model())
    d["operation_ref"]["pre_admission_identity"] = "pre_1"
    # both root_job_id and pre_admission_identity now set -> refused
    with pytest.raises(ModelParseError):
        parse_model_text(dumps(d))

    d2 = clone(minimal_model())
    d2["operation_ref"]["root_job_id"] = None
    # neither set -> refused
    with pytest.raises(ModelParseError):
        parse_model_text(dumps(d2))


def test_mismatched_source_snapshot_hash_is_refused() -> None:
    d = clone(minimal_model())
    d["source_snapshot"]["snapshot_hash"] = "0" * 64
    with pytest.raises(ModelParseError):
        parse_model_text(dumps(d))


def test_valid_source_snapshot_with_records_parses() -> None:
    d = clone(minimal_model())
    d["source_snapshot"] = source_snapshot([source_record()])
    m = parse_model_text(dumps(d))
    assert len(m.source_snapshot.sources) == 1


def test_unresolved_source_ref_is_refused() -> None:
    d = clone(minimal_model())
    d["transitions"][0]["source_refs"] = ["not-a-real-canonical-ref token with spaces"]
    with pytest.raises(ModelParseError):
        parse_model_text(dumps(d))


def test_safety_property_state_forbidden_parses() -> None:
    d = clone(minimal_model())
    d["safety_properties"] = [
        state_forbidden("NO_DONE_WHILE_START", [guard("phase", "EQ", "DONE")])
    ]
    m = parse_model_text(dumps(d))
    assert m.safety_properties[0].property_id == "NO_DONE_WHILE_START"


def test_safety_property_transition_forbidden_parses() -> None:
    d = clone(minimal_model())
    d["safety_properties"] = [
        transition_forbidden(
            "NO_EFFECT_UNKNOWN_ESCAPE",
            [guard("phase", "EQ", "START")],
            ["RETRY"],
        )
    ]
    m = parse_model_text(dumps(d))
    assert m.safety_properties[0].kind == "TRANSITION_FORBIDDEN"


def test_safety_property_mixed_shape_is_refused() -> None:
    d = clone(minimal_model())
    bad = state_forbidden("BAD", [guard("phase", "EQ", "DONE")])
    bad["when"] = [guard("phase", "EQ", "START")]
    d["safety_properties"] = [bad]
    with pytest.raises(ModelParseError):
        parse_model_text(dumps(d))


def test_safety_property_id_colliding_with_generic_mandatory_is_refused() -> None:
    d = clone(minimal_model())
    d["safety_properties"] = [
        state_forbidden("OPTION_TO_COMPLETE", [guard("phase", "EQ", "DONE")])
    ]
    with pytest.raises(ModelParseError):
        parse_model_text(dumps(d))


def test_model_gap_unresolved_affected_id_is_refused() -> None:
    d = clone(minimal_model())
    d["known_model_gaps"] = [
        model_gap("gap1", "unmodeled behavior", True, affects_transition_ids=["no_such_transition"])
    ]
    with pytest.raises(ModelParseError):
        parse_model_text(dumps(d))


def test_model_gap_empty_affected_requires_non_load_bearing() -> None:
    d = clone(minimal_model())
    d["known_model_gaps"] = [model_gap("gap1", "cannot affect anything checked", True)]
    with pytest.raises(ModelParseError):
        parse_model_text(dumps(d))

    d2 = clone(minimal_model())
    d2["known_model_gaps"] = [model_gap("gap1", "cannot affect anything checked", False)]
    parse_model_text(dumps(d2))  # does not raise


def test_gate_without_release_transition_ids_is_refused() -> None:
    d = clone(minimal_model())
    d["state_domains"]["gate_x"] = ["WAITING", "DONE"]
    d["initial_state"]["gate_x"] = "WAITING"
    d["external_gates"] = [
        gate("g1", "EXTERNAL_GATE", [guard("gate_x", "EQ", "WAITING")], [], "finish")
    ]
    with pytest.raises(ModelParseError):
        parse_model_text(dumps(d))


def test_gate_escalation_path_must_name_a_release_transition() -> None:
    d = clone(minimal_model())
    d["state_domains"]["gate_x"] = ["WAITING", "DONE"]
    d["initial_state"]["gate_x"] = "WAITING"
    d["transitions"][0]["gate_refs"] = ["g1"]
    d["external_gates"] = [
        gate("g1", "EXTERNAL_GATE", [guard("gate_x", "EQ", "WAITING")], ["finish"], "not_a_release_id")
    ]
    with pytest.raises(ModelParseError):
        parse_model_text(dumps(d))


def test_recurring_outcome_in_terminal_list_is_refused() -> None:
    d = clone(minimal_model())
    d["terminal_outcomes"].append(outcome("bad", "RECURRING_PROGRESS", [guard("phase", "EQ", "DONE")]))
    with pytest.raises(ModelParseError):
        parse_model_text(dumps(d))


def test_obligation_pending_and_discharged_must_be_disjoint() -> None:
    d = clone(minimal_model())
    d["obligations"] = [obligation("ob1", "phase", ["START"], ["START"])]
    with pytest.raises(ModelParseError):
        parse_model_text(dumps(d))


def test_resource_released_value_outside_domain_is_refused() -> None:
    d = clone(minimal_model())
    d["resources"] = [resource("r1", "phase", ["NOT_A_VALUE"])]
    with pytest.raises(ModelParseError):
        parse_model_text(dumps(d))


def test_canonical_json_is_key_sorted_and_compact() -> None:
    assert canonical_json({"b": 1, "a": 2}) == '{"a":2,"b":1}'


def test_sha256_hex_matches_hashlib() -> None:
    import hashlib

    assert sha256_hex("abc") == hashlib.sha256(b"abc").hexdigest()


def test_model_hash_is_stable_under_key_permutation() -> None:
    d1 = minimal_model()
    d2 = json.loads(json.dumps(d1))
    # reorder top-level keys by rebuilding the dict in reverse order
    d2 = {k: d2[k] for k in reversed(list(d2.keys()))}
    m1 = parse_model_text(json.dumps(d1))
    m2 = parse_model_text(json.dumps(d2))
    assert m1.model_hash == m2.model_hash


def test_model_hash_changes_when_semantics_change() -> None:
    d1 = minimal_model()
    d2 = clone(d1)
    d2["model_id"] = "om_minimal_v2_different"
    m1 = parse_model_text(dumps(d1))
    m2 = parse_model_text(dumps(d2))
    assert m1.model_hash != m2.model_hash


def test_canonical_token_pattern_is_enforced_on_transition_kind() -> None:
    d = clone(minimal_model())
    d["transitions"][0]["kind"] = "not-a-canonical-token"
    with pytest.raises(ModelParseError):
        parse_model_text(dumps(d))


def test_stable_id_pattern_rejects_leading_non_alphanumeric() -> None:
    d = clone(minimal_model())
    d["transitions"][0]["transition_id"] = "-leading-dash"
    with pytest.raises(ModelParseError):
        parse_model_text(dumps(d))


def test_too_many_state_variables_is_refused() -> None:
    d = clone(minimal_model())
    for i in range(200):
        var = f"extra_var_{i}"
        d["state_domains"][var] = ["A", "B"]
        d["initial_state"][var] = "A"
    with pytest.raises(ModelParseError):
        parse_model_text(dumps(d))


def test_too_many_domain_values_is_refused() -> None:
    d = clone(minimal_model())
    d["state_domains"]["phase"] = [f"V{i}" for i in range(200)]
    d["initial_state"]["phase"] = "V0"
    with pytest.raises(ModelParseError):
        parse_model_text(dumps(d))
