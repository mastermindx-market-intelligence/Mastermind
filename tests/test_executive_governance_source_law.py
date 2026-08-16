"""Conformance tests for the Executive OS G0 source-law substrate.

These tests close the independent Phase 1G architecture review's B1/B2/B3 class:
executive seat labels must never grant capability; decision altitude must be
enumerated in the existing authority map; strategy/ranking/runtime priority must
have one owner each; Phase 1F bounds/review rulings must be explicit; and
constitutional paths must fail closed against autonomous write grants.

The file is intentionally a config-conformance test, not an execution engine.
Nothing here arms CEO wake, production MCP writes, merge/deploy, or scheduling.
"""
from __future__ import annotations

from pathlib import Path

import yaml


_ROOT = Path(__file__).resolve().parent.parent
_AUTHORITY_MAP = _ROOT / "config" / "authority_map.yml"


def _doc() -> dict:
    value = yaml.safe_load(_AUTHORITY_MAP.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_executive_seats_are_identity_only_and_strictly_ranked():
    seats = _doc()["executive_seats"]
    assert seats["schema_version"] == 1
    assert set(seats) == {"schema_version", "chairman", "ceo", "coo"}

    assert seats["chairman"]["occupant_label"] == "Chris"
    assert seats["ceo"]["occupant_label"] == "Sol"
    assert seats["coo"]["occupant_label"] == "Fable"

    assert seats["chairman"]["escalation_rank"] > seats["ceo"]["escalation_rank"]
    assert seats["ceo"]["escalation_rank"] > seats["coo"]["escalation_rank"]

    for seat_id in ("chairman", "ceo", "coo"):
        assert seats[seat_id]["authority"] == "none", (
            f"seat label {seat_id} must never confer runtime capability"
        )


def test_decision_policy_has_only_declared_executive_altitudes():
    policy = _doc()["executive_decision_policy"]
    assert policy["schema_version"] == 1
    categories = policy["categories"]
    assert categories
    allowed = {"chairman", "ceo", "coo"}
    assert {entry["minimum_decision_seat"] for entry in categories.values()} <= allowed


def test_chairman_reserved_categories_are_pinned():
    categories = _doc()["executive_decision_policy"]["categories"]
    required = {
        "CONSTITUTION_OR_CHARTER_CHANGE",
        "EXECUTIVE_HIERARCHY_CHANGE",
        "EXECUTIVE_AUTHORITY_POLICY_CHANGE",
        "COMPANY_PHASE_NORTH_STAR_OR_STANDING_CONSTRAINT_CHANGE",
        "PRODUCTION_AUTONOMY_ARM_OR_EXPANSION",
        "PRODUCTION_WRITE_TRUST_MODEL_CHANGE",
        "AUTONOMOUS_MERGE_DEPLOY_SERVICE_CONTROL_OR_CAPITAL_EXECUTION",
        "CONSTITUTIONAL_PROTECTED_PATH_POLICY_CHANGE",
        "REASONING_GOVERNOR_CONSTITUTIONAL_CHANGE",
        "CHAIRMAN_DECISION_REQUEST",
    }
    assert required <= set(categories)
    assert all(categories[name]["minimum_decision_seat"] == "chairman" for name in required)


def test_ceo_delegated_categories_are_pinned():
    categories = _doc()["executive_decision_policy"]["categories"]
    required = {
        "P0_OBJECTIVE_ADD_RETIRE_OR_RESCOPE",
        "RESOURCE_POLICY_REBALANCE",
        "PROJECT_INITIATE_WITHIN_ACTIVE_P0",
        "PROJECT_STOP_OR_REPRIORITIZE_WITHIN_ACTIVE_P0",
        "PROJECT_SCOPE_REFRAME_WITHIN_DELEGATED_AUTHORITY",
        "EXECUTIVE_REASONING_ESCALATION_REQUEST",
        "CEO_ROUTE_REPUBLISH_WITHIN_APPROVED_POLICY",
    }
    assert required <= set(categories)
    assert all(categories[name]["minimum_decision_seat"] == "ceo" for name in required)


def test_coo_categories_are_strictly_bounded_execution_not_strategy():
    categories = _doc()["executive_decision_policy"]["categories"]
    required = {
        "PROJECT_DECOMPOSE_ACCEPTED_OBJECTIVE",
        "BOUNDED_CHILD_JOB_CREATE",
        "BOUNDED_REPAIR_OR_REVIEW",
        "DETERMINISTIC_PROVIDER_PLACEMENT",
        "SHRINK_ONLY_PAUSE_STOP_OR_DRAIN",
        "EXECUTIVE_EXCEPTION_ESCALATE",
    }
    assert required <= set(categories)
    assert all(categories[name]["minimum_decision_seat"] == "coo" for name in required)


def test_decision_category_is_server_derived_not_model_authority():
    policy = _doc()["executive_decision_policy"]
    assert policy["derivation"] == "server_from_canonical_operation_and_state"
    assert policy["model_supplied_category_authority"] == "none"
    assert policy["semantic_demotion"] == "prohibited"


def test_strategy_ranking_and_runtime_order_have_one_owner_each():
    policy = _doc()["executive_strategy_policy"]
    assert policy["schema_version"] == 1

    assert policy["company_strategy"]["canonical_artifact"] == "config/strategic_state.yml"
    assert policy["company_strategy"]["runtime_role"] == "advisory_and_orientation_only"

    assert policy["candidate_ranking"]["canonical_generator"] == "brain/improvement_agenda.py"
    assert policy["candidate_ranking"]["authority"] == "derived_advisory_only"
    assert policy["candidate_ranking"]["direct_executive_mutation"] == "prohibited"

    assert policy["admitted_work"]["lifecycle_authority"] == "executive_sqlite"
    assert policy["admitted_work"]["job_priority_role"] == "already_admitted_work_order_only"
    assert policy["admitted_work"]["strategy_authority"] == "none"


def test_project_admission_requires_strategy_reference_and_typed_directive():
    requirements = set(_doc()["executive_strategy_policy"]["project_admission_requires"])
    assert {
        "active_p0_or_recorded_strategy_decision",
        "exact_strategic_state_revision",
        "typed_directive_or_intent",
        "authority_policy_pass",
    } <= requirements


def test_phase1f_coo_bounds_are_pinned_to_the_ceo_ruling():
    p = _doc()["coo_cycle_policy"]
    assert p == {
        "schema_version": 1,
        "max_fan_out_per_parent": 8,
        "max_depth": 2,
        "max_repair_rounds": 2,
        "max_review_attempts_per_job": 2,
        "max_children_total": 16,
        "allowed_child_cost_classes": ["default", "small"],
        "review_verdicts": ["approve", "reject"],
    }


def test_review_independence_starvation_fails_closed_without_waiver():
    p = _doc()["executive_review_policy"]
    implementation = p["implementation_result"]
    assert implementation["minimum_independence"] == "worker_only"
    assert implementation["starvation_disposition"] == "escalate"
    assert implementation["waiver_allowed"] is False

    dissent = p["executive_dissent"]
    assert dissent["required_independence"] == "policy_selected"
    assert dissent["unavailable_disposition"] == "DISSENT_UNAVAILABLE"
    assert dissent["clear_on_degraded_independence"] is False


def test_protected_paths_cover_constitution_governance_and_control_surfaces():
    p = _doc()["executive_protected_paths"]
    assert p["schema_version"] == 1
    paths = set(p["paths"])
    required = {
        "research/MASTERMIND_CHARTER_V2.md",
        "config/authority_map.yml",
        "config/strategic_state.yml",
        "AGENTS.md",
        "CLAUDE.md",
        "integrations/executive_mcp/**",
        "ops/executive_os/**",
        ".github/workflows/**",
    }
    assert required <= paths
    assert p["autonomous_write"] == "prohibited"
    assert p["self_widening"] == "prohibited"


def test_existing_worker_policy_remains_narrow_and_denies_prod_power():
    p = _doc()["executive_worker_policy"]
    assert set(p["allowed_capabilities"]) == {"READ", "RESEARCH", "WRITE_BRANCH", "RUN_TESTS"}
    denied = set(p["denied_capabilities"])
    assert {"MERGE", "DEPLOY", "SERVICE_CONTROL", "CAPITAL_EXECUTION", "CREDENTIAL_ADMIN"} <= denied
