"""EVAL-R0 Task 2: closed scenario and configuration contracts.

RED-before-GREEN: every negative test asserts a specific structured defect
code, never a bare exception.
"""
from __future__ import annotations

import copy

import pytest

from scripts.agent_eval import contracts
from scripts.agent_eval.errors import ContractError
from tests.agent_eval_factories import (
    build_alternate_configuration,
    build_baseline_configuration,
    build_baseline_scenario,
    build_baseline_scenario_fields,
)


def _scenario_fields():
    return copy.deepcopy(build_baseline_scenario_fields())


def _scenario():
    return copy.deepcopy(build_baseline_scenario())


def _configuration():
    return copy.deepcopy(build_baseline_configuration())


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_baseline_scenario_is_shape_valid() -> None:
    assert contracts.validate_scenario_shape(_scenario()) == "SHAPE_VALID"


def test_scenario_v2_keeps_equal_content_at_distinct_refs_without_changing_v1():
    fields = _scenario_fields()
    pairs = [{"artifact_ref": "git:fixture/sources@" + "c" * 40 + "#" + path,
              "digest": "sha256:" + "e" * 64} for path in ("one.md", "two.md")]
    fields["source_policy"]["allowlist_artifacts"] = sorted(
        fields["source_policy"]["allowlist_artifacts"] + pairs, key=lambda row: row["artifact_ref"])
    fields["privacy"]["model_visible_artifact_refs"] = sorted(
        set(fields["privacy"]["model_visible_artifact_refs"]) | {row["artifact_ref"] for row in pairs})
    with pytest.raises(ContractError) as old:
        contracts.build_scenario(fields)
    assert "DUPLICATE_ARTIFACT_DIGEST" in {d.code for d in old.value.defects}
    current = contracts.build_scenario(fields, schema=contracts.SCENARIO_SCHEMA_V2)
    assert contracts.validate_document_shape(current) == "SHAPE_VALID"
    assert all(pair in current["source_policy"]["allowlist_artifacts"] for pair in pairs)
    assert contracts.build_scenario(_scenario_fields())["schema"] == contracts.SCENARIO_SCHEMA
    # Unrelated evidence-artifact collections retain their older identity rule.
    with pytest.raises(ContractError) as unrelated:
        contracts.v_artifact_list(pairs, "$.evidence.artifacts")
    assert "DUPLICATE_ARTIFACT_DIGEST" in {d.code for d in unrelated.value.defects}


@pytest.mark.parametrize("mutation,code", [
    ("same-ref", "DUPLICATE_ARTIFACT_REF"), ("reverse", "LIST_NOT_SORTED"),
    ("digest", "DIGEST_SHAPE"), ("extra", "UNKNOWN_FIELD"),
])
def test_ref_unique_source_list_still_closes_shape_and_order(mutation, code):
    pairs = [{"artifact_ref": "git:fixture/sources@" + "c" * 40 + "#" + path,
              "digest": "sha256:" + "e" * 64} for path in ("one.md", "two.md")]
    if mutation == "same-ref":
        pairs[1]["artifact_ref"] = pairs[0]["artifact_ref"]
    elif mutation == "reverse":
        pairs.reverse()
    elif mutation == "digest":
        pairs[0]["digest"] = "configured-label"
    else:
        pairs[0]["alias_authorized"] = True
    with pytest.raises(ContractError) as error:
        contracts.v_source_artifact_list(pairs, "$.observed_sources")
    assert code in {d.code for d in error.value.defects}


def test_two_configurations_share_model_but_differ_in_digest() -> None:
    c1 = build_baseline_configuration()
    c2 = build_alternate_configuration()
    assert c1["execution"]["model_requested"] == c2["execution"]["model_requested"]
    assert c1["configuration_digest"] != c2["configuration_digest"]
    assert contracts.validate_configuration_shape(c1) == "SHAPE_VALID"
    assert contracts.validate_configuration_shape(c2) == "SHAPE_VALID"


def test_scenario_configuration_defects_empty_for_compatible_pair() -> None:
    assert contracts.scenario_configuration_defects(_scenario(), _configuration()) == ()


def test_generic_shape_dispatch_accepts_persisted_scenario_schema() -> None:
    assert contracts.validate_document_shape(_scenario()) == "SHAPE_VALID"


def test_generic_shape_dispatch_accepts_persisted_configuration_schema() -> None:
    assert contracts.validate_document_shape(_configuration()) == "SHAPE_VALID"


def test_generic_shape_dispatch_rejects_draft_schema() -> None:
    with pytest.raises(ContractError) as excinfo:
        contracts.validate_document_shape({"schema": contracts.RUN_DRAFT_SCHEMA})
    assert excinfo.value.defects[0].code == "DRAFT_SCHEMA_REJECTED"


def test_generic_shape_dispatch_rejects_unknown_schema() -> None:
    with pytest.raises(ContractError) as excinfo:
        contracts.validate_document_shape({"schema": "mastermind.something_unknown.v1"})
    assert excinfo.value.defects[0].code == "UNKNOWN_SCHEMA"


# ---------------------------------------------------------------------------
# Closed-object: unknown / missing fields
# ---------------------------------------------------------------------------


def test_scenario_rejects_unknown_top_level_field() -> None:
    doc = _scenario()
    doc["winner"] = "arm_a"
    with pytest.raises(ContractError) as excinfo:
        contracts.validate_scenario_shape(doc)
    assert any(d.code == "UNKNOWN_FIELD" for d in excinfo.value.defects)


def test_scenario_rejects_missing_required_field() -> None:
    doc = _scenario()
    del doc["objective"]
    with pytest.raises(ContractError) as excinfo:
        contracts.validate_scenario_shape(doc)
    assert any(d.code == "FIELD_MISSING" and d.path == "$.objective" for d in excinfo.value.defects)


def test_configuration_rejects_unknown_top_level_field() -> None:
    doc = _configuration()
    doc["route"] = "fast_lane"
    with pytest.raises(ContractError) as excinfo:
        contracts.validate_configuration_shape(doc)
    assert any(d.code == "UNKNOWN_FIELD" for d in excinfo.value.defects)


@pytest.mark.parametrize(
    "forbidden_field", ["served_model", "route", "capacity", "suitability", "policy", "score", "winner", "authority", "approval", "acceptance"]
)
def test_configuration_cannot_carry_authority_or_score_fields(forbidden_field: str) -> None:
    doc = _configuration()
    doc[forbidden_field] = "anything"
    with pytest.raises(ContractError) as excinfo:
        contracts.validate_configuration_shape(doc)
    assert any(d.code == "UNKNOWN_FIELD" and forbidden_field in d.path for d in excinfo.value.defects)


# ---------------------------------------------------------------------------
# ID / ref / digest grammar
# ---------------------------------------------------------------------------


def test_scenario_id_rejects_bad_grammar() -> None:
    fields = _scenario_fields()
    fields["scenario_id"] = "scenario:BadFamily:case"
    with pytest.raises(ContractError):
        contracts.build_scenario(fields)


def test_scenario_id_rejects_missing_colon_segment() -> None:
    fields = _scenario_fields()
    fields["scenario_id"] = "scenario:onlyfamily"
    with pytest.raises(ContractError):
        contracts.build_scenario(fields)


def test_scenario_family_rejects_non_mastermind_grammar() -> None:
    fields = _scenario_fields()
    fields["scenario_family"] = "not_a_valid_family_string"
    with pytest.raises(ContractError) as excinfo:
        contracts.build_scenario(fields)
    assert any(d.code == "SCENARIO_FAMILY_SHAPE" for d in excinfo.value.defects)


def test_corpus_revision_requires_source_qualified_ref() -> None:
    fields = _scenario_fields()
    fields["corpus_revision"] = "a" * 40  # bare commit hash
    with pytest.raises(ContractError):
        contracts.build_scenario(fields)


def test_configuration_id_requires_prefixed_uuid4() -> None:
    doc = _configuration()
    doc["configuration_id"] = "configuration:not-a-uuid"
    with pytest.raises(ContractError):
        contracts.validate_configuration_shape(doc)


def test_procedure_refs_require_source_qualified_grammar() -> None:
    doc = _configuration()
    doc["procedure"]["protected_source_ref"] = "bare-ref-without-repo-or-sha"
    with pytest.raises(ContractError):
        contracts.validate_configuration_shape(doc)


# ---------------------------------------------------------------------------
# Sorted / unique lists
# ---------------------------------------------------------------------------


def test_scenario_rejects_unsorted_allowlist_artifacts() -> None:
    fields = _scenario_fields()
    fields["source_policy"]["allowlist_artifacts"] = list(
        reversed(fields["source_policy"]["allowlist_artifacts"])
    )
    with pytest.raises(ContractError) as excinfo:
        contracts.build_scenario(fields)
    assert any(d.code == "LIST_NOT_SORTED" for d in excinfo.value.defects)


def test_scenario_rejects_duplicate_artifact_ref_in_allowlist() -> None:
    fields = _scenario_fields()
    first = fields["source_policy"]["allowlist_artifacts"][0]
    fields["source_policy"]["allowlist_artifacts"] = sorted(
        [first, dict(first, digest="sha256:" + "9" * 64)], key=lambda item: item["artifact_ref"]
    )
    with pytest.raises(ContractError) as excinfo:
        contracts.build_scenario(fields)
    assert any(d.code == "DUPLICATE_ARTIFACT_REF" for d in excinfo.value.defects)


def test_scenario_rejects_duplicate_digest_in_allowlist_even_with_distinct_refs() -> None:
    fields = _scenario_fields()
    first = fields["source_policy"]["allowlist_artifacts"][0]
    duplicate = dict(first, artifact_ref=first["artifact_ref"] + "-zzz")
    fields["source_policy"]["allowlist_artifacts"] = sorted(
        [first, duplicate], key=lambda item: item["artifact_ref"]
    )
    with pytest.raises(ContractError) as excinfo:
        contracts.build_scenario(fields)
    assert any(d.code == "DUPLICATE_ARTIFACT_DIGEST" for d in excinfo.value.defects)


def test_scenario_rejects_unsorted_capability_ids() -> None:
    fields = _scenario_fields()
    fields["capability_policy"]["allowed_capability_ids"] = ["search_repo", "read_file"]
    with pytest.raises(ContractError) as excinfo:
        contracts.build_scenario(fields)
    assert any(d.code == "LIST_NOT_SORTED" for d in excinfo.value.defects)


def test_scenario_rejects_duplicate_capability_ids() -> None:
    fields = _scenario_fields()
    fields["capability_policy"]["allowed_capability_ids"] = ["read_file", "read_file"]
    with pytest.raises(ContractError) as excinfo:
        contracts.build_scenario(fields)
    assert any(d.code == "LIST_HAS_DUPLICATES" for d in excinfo.value.defects)


def test_configuration_rejects_unsorted_declared_tool_schema_digests() -> None:
    doc = _configuration()
    doc["capabilities"]["declared_tool_schema_digests"] = list(
        reversed(doc["capabilities"]["declared_tool_schema_digests"])
    )
    with pytest.raises(ContractError):
        contracts.validate_configuration_shape(doc)


# ---------------------------------------------------------------------------
# Network / effect policy consistency (DENY_ALL / ALLOWLIST, NO_EFFECT / DECLARED)
# ---------------------------------------------------------------------------


def test_deny_all_requires_empty_network_allowlist() -> None:
    fields = _scenario_fields()
    fields["execution_policy"]["network_policy"] = "DENY_ALL"
    fields["execution_policy"]["network_allowlist"] = ["example.com"]
    with pytest.raises(ContractError) as excinfo:
        contracts.build_scenario(fields)
    assert any(d.code == "DENY_ALL_REQUIRES_EMPTY_ALLOWLIST" for d in excinfo.value.defects)


def test_allowlist_requires_nonempty_network_allowlist() -> None:
    fields = _scenario_fields()
    fields["execution_policy"]["network_policy"] = "ALLOWLIST"
    fields["execution_policy"]["network_allowlist"] = []
    with pytest.raises(ContractError) as excinfo:
        contracts.build_scenario(fields)
    assert any(d.code == "ALLOWLIST_REQUIRES_NONEMPTY" for d in excinfo.value.defects)


def test_no_effect_only_requires_empty_operation_refs() -> None:
    fields = _scenario_fields()
    fields["effect_policy"] = {"mode": "NO_EFFECT_ONLY", "allowed_operation_refs": ["op:demo"]}
    with pytest.raises(ContractError) as excinfo:
        contracts.build_scenario(fields)
    assert any(d.code == "NO_EFFECT_ONLY_REQUIRES_EMPTY_REFS" for d in excinfo.value.defects)


def test_declared_effect_allowed_requires_nonempty_operation_refs() -> None:
    fields = _scenario_fields()
    fields["effect_policy"] = {"mode": "DECLARED_EFFECT_ALLOWED", "allowed_operation_refs": []}
    with pytest.raises(ContractError) as excinfo:
        contracts.build_scenario(fields)
    assert any(d.code == "DECLARED_EFFECT_ALLOWED_REQUIRES_NONEMPTY" for d in excinfo.value.defects)


# ---------------------------------------------------------------------------
# Hidden-source subset, cutoff order, privacy/ref consistency, authorship
# ---------------------------------------------------------------------------


def test_hidden_solution_refs_must_be_subset_of_denylist() -> None:
    fields = _scenario_fields()
    fields["source_policy"]["solution_refs_hidden"] = ["git:mastermindx-market-intelligence/Mastermind@" + "c" * 40]
    with pytest.raises(ContractError) as excinfo:
        contracts.build_scenario(fields)
    assert any(d.code == "HIDDEN_SOLUTION_NOT_IN_DENYLIST" for d in excinfo.value.defects)


def test_cutoff_must_be_at_or_before_authored() -> None:
    fields = _scenario_fields()
    fields["temporal"] = {"cutoff_at": "2026-09-01T00:00:00Z", "authored_at": "2026-08-01T00:00:00Z"}
    with pytest.raises(ContractError) as excinfo:
        contracts.build_scenario(fields)
    assert any(d.code == "CUTOFF_AFTER_AUTHORED" for d in excinfo.value.defects)


def test_privacy_visible_refs_must_be_allowlisted() -> None:
    fields = _scenario_fields()
    fields["privacy"]["model_visible_artifact_refs"] = ["git:mastermindx-market-intelligence/Mastermind@" + "a" * 40 + "#fixtures/not_allowlisted.md"]
    with pytest.raises(ContractError) as excinfo:
        contracts.build_scenario(fields)
    assert any(d.code == "PRIVACY_REF_NOT_ALLOWLISTED" for d in excinfo.value.defects)


def test_authorship_reviewer_must_be_independent_of_author_scenario() -> None:
    fields = _scenario_fields()
    fields["authorship"] = {"author_ref": "person:sol", "independent_reviewer_ref": "person:sol"}
    with pytest.raises(ContractError) as excinfo:
        contracts.build_scenario(fields)
    assert any(d.code == "REVIEWER_NOT_INDEPENDENT" for d in excinfo.value.defects)


def test_authorship_reviewer_must_be_independent_of_author_configuration() -> None:
    doc = _configuration()
    doc["authorship"] = {"author_ref": "person:sol", "independent_reviewer_ref": "person:sol"}
    with pytest.raises(ContractError) as excinfo:
        contracts.validate_configuration_shape(doc)
    assert any(d.code == "REVIEWER_NOT_INDEPENDENT" for d in excinfo.value.defects)


def test_scenario_source_qualified_procedure_refs_via_configuration() -> None:
    doc = _configuration()
    doc["procedure"]["skillpack_source_ref"] = "not-source-qualified"
    with pytest.raises(ContractError):
        contracts.validate_configuration_shape(doc)


# ---------------------------------------------------------------------------
# Supersession
# ---------------------------------------------------------------------------


def test_scenario_supersedes_must_be_same_family_and_case() -> None:
    fields = _scenario_fields()
    fields["scenario_version"] = 2
    fields["supersedes"] = "scenario:other_family:other_case"
    with pytest.raises(ContractError) as excinfo:
        contracts.build_scenario(fields)
    assert any(d.code == "SUPERSEDES_LINEAGE_MISMATCH" for d in excinfo.value.defects)


def test_scenario_version_one_must_not_supersede() -> None:
    fields = _scenario_fields()
    fields["supersedes"] = "scenario:evaluation_contract_integrity:baseline_case"
    with pytest.raises(ContractError) as excinfo:
        contracts.build_scenario(fields)
    assert any(d.code == "SUPERSEDES_ON_FIRST_VERSION" for d in excinfo.value.defects)


def test_configuration_must_not_supersede_itself() -> None:
    doc = _configuration()
    doc["supersedes"] = doc["configuration_id"]
    with pytest.raises(ContractError) as excinfo:
        contracts.validate_configuration_shape(doc)
    assert any(d.code == "SUPERSEDES_SELF" for d in excinfo.value.defects)


# ---------------------------------------------------------------------------
# Own digest
# ---------------------------------------------------------------------------


def test_scenario_digest_mismatch_after_mutation_is_rejected() -> None:
    doc = _scenario()
    doc["objective"] = "a different objective than what was digested"
    with pytest.raises(ContractError) as excinfo:
        contracts.validate_scenario_shape(doc)
    assert any(d.code == "DIGEST_MISMATCH" for d in excinfo.value.defects)


def test_configuration_digest_mismatch_after_mutation_is_rejected() -> None:
    doc = _configuration()
    doc["randomness"]["seed"] = 999
    with pytest.raises(ContractError) as excinfo:
        contracts.validate_configuration_shape(doc)
    assert any(d.code == "DIGEST_MISMATCH" for d in excinfo.value.defects)


# ---------------------------------------------------------------------------
# Compatibility: profile equality; capability subset/disjoint; tool subset;
# network-policy digest equality
# ---------------------------------------------------------------------------


def test_compatibility_fails_on_profile_mismatch() -> None:
    scenario = _scenario()
    configuration = _configuration()
    configuration["capabilities"]["profile_id"] = "different_profile"
    defects = contracts.scenario_configuration_defects(scenario, configuration)
    assert any(d.code == "CAPABILITY_PROFILE_MISMATCH" for d in defects)


def test_compatibility_fails_when_declared_capability_not_allowed() -> None:
    scenario = _scenario()
    configuration = _configuration()
    configuration["capabilities"]["declared_capability_ids"] = ["read_file", "search_repo", "write_file"]
    defects = contracts.scenario_configuration_defects(scenario, configuration)
    assert any(d.code == "CAPABILITY_NOT_ALLOWED" for d in defects)


def test_compatibility_fails_when_declared_capability_is_forbidden() -> None:
    scenario = _scenario()
    configuration = _configuration()
    configuration["capabilities"]["declared_capability_ids"] = ["execute_shell"]
    defects = contracts.scenario_configuration_defects(scenario, configuration)
    assert any(d.code == "CAPABILITY_FORBIDDEN" for d in defects)


def test_compatibility_fails_when_declared_tool_not_allowed() -> None:
    scenario = _scenario()
    configuration = _configuration()
    configuration["capabilities"]["declared_tool_schema_digests"] = ["sha256:" + "9" * 64]
    defects = contracts.scenario_configuration_defects(scenario, configuration)
    assert any(d.code == "TOOL_SCHEMA_NOT_ALLOWED" for d in defects)


def test_compatibility_fails_when_network_policy_digest_mismatched() -> None:
    scenario = _scenario()
    configuration = _configuration()
    configuration["capabilities"]["network_policy_digest"] = "sha256:" + "9" * 64
    defects = contracts.scenario_configuration_defects(scenario, configuration)
    assert any(d.code == "NETWORK_POLICY_DIGEST_MISMATCH" for d in defects)


def test_compatibility_is_empty_only_for_the_matched_baseline_pair() -> None:
    scenario = _scenario()
    configuration = _configuration()
    assert contracts.scenario_configuration_defects(scenario, configuration) == ()
