"""Prospective planning tests use the real plan and reservation owners."""
import copy
import json
from pathlib import Path

import pytest

from control_plane.executive_coo_policy import CooCyclePolicy
from control_plane.executive_orchestration_result import OrchestrationResultError, _validate_plan
from control_plane.fabric_graph_planning import GraphPlanningError, analyze_plan
from scripts.fabric_graph_plan import main


def plan(count=1, *, version=4, reviewed=()):
    value = {"schema_version": f"mastermind.execution_plan/v{version}",
             "root_job_id": "root-1", "plan_attempt_id": "attempt-1", "steps": []}
    if version == 5:
        value["coordinator_job_id"] = "root-1"
    for index in range(count):
        step = {"ordinal": index, "step_id": f"s{index}", "objective": f"Outcome {index}",
                "business_impact": "material", "review_required": index in reviewed,
                "requested_authorities": ["READ"], "allowed_write_paths": [],
                "validation_ids": ["a" * 64], "attempt_limit": 2, "cost_class": "small"}
        if version in (2, 3):
            step["placement"] = {"provider_realm": "approved", "quota_class": "approved"}
        if version in (3, 4, 5):
            step["prerequisite_step_ids"] = []
        if version == 5:
            step["delegation"] = None
        value["steps"].append(step)
    return value


def analyze(value, **kwargs):
    return analyze_plan(value, expected_root_job_id="root-1", expected_plan_attempt_id="attempt-1", **kwargs)


@pytest.mark.parametrize("version", [1, 2, 3, 4, 5])
def test_custom_uses_existing_contract_without_mutation(version):
    value = plan(version=version, reviewed=(0,))
    original = copy.deepcopy(value)
    report = analyze(value)
    canonical = _validate_plan(value, outer={"run_id": "attempt-1", "expected_root_job_id": "root-1"})
    assert report["candidate_plan"] == canonical == original == value
    assert report["reservation"]["demand"] == 1 + CooCyclePolicy.load().reserved_step_slots(review_required=True)
    assert report["admission_state"] == "NOT_REQUESTED"
    assert report["runtime_changed"] is False
    assert report["declared_bounds_authenticated"] is False


def test_review_reservation_is_cumulative_even_in_a_pipeline():
    value = plan(2, reviewed=(0, 1))
    report = analyze(value, method="pipeline")
    assert report["reservation"] == {
        "demand": 19, "limit": 16, "shortfall": 3, "capacity_fits": False, "policy_compatible": False,
        "breakdown": [{"kind": "planner", "reserved_descendants": 1},
                      {"step_id": "s0", "kind": "work_review_repair", "reserved_descendants": 9},
                      {"step_id": "s1", "kind": "work_review_repair", "reserved_descendants": 9}],
    }
    assert all(step["review_required"] for step in report["candidate_plan"]["steps"])
    assert value["steps"][1]["prerequisite_step_ids"] == []
    assert report["static_status"] == "NEEDS_ATTENTION"


def test_fanout_join_preserves_review_scope_and_consumes_every_leaf():
    value = plan(4, reviewed=(3,))
    for index, step in enumerate(value["steps"]):
        step["allowed_write_paths"] = [f"src/lane{index}/**"]
    report = analyze(value, method="fanout_join")
    assert report["reservation"]["demand"] == 13
    assert report["dependency_layers"] == [["s0", "s1", "s2"], ["s3"]]
    assert report["terminal_step_ids"] == ["s3"]
    assert report["dependency_width"] == 3
    assert report["static_status"] == "COMPATIBLE"
    for before, after in zip(value["steps"], report["candidate_plan"]["steps"]):
        assert {k: v for k, v in before.items() if k != "prerequisite_step_ids"} == {
            k: v for k, v in after.items() if k != "prerequisite_step_ids"}


def test_fanout_cannot_delete_existing_dependency():
    value = plan(3)
    value["steps"][1]["prerequisite_step_ids"] = ["s0"]
    with pytest.raises(GraphPlanningError):
        analyze(value, method="fanout_join")


def test_shared_writers_require_ordering_and_transitive_edges_count():
    value = plan(3)
    value["steps"][0]["allowed_write_paths"] = ["src/**"]
    value["steps"][2]["allowed_write_paths"] = ["src/shared.py"]
    assert analyze(value)["findings"][0]["code"] == "UNORDERED_WRITE_SCOPE_MAY_OVERLAP"
    assert analyze(value, method="pipeline")["findings"] == []


def test_dependency_width_is_not_just_largest_ready_layer():
    value = plan(7)
    for index, prerequisites in {2: ["s0"], 3: ["s0"], 4: ["s1"], 5: ["s4"], 6: ["s4"]}.items():
        value["steps"][index]["prerequisite_step_ids"] = prerequisites
    report = analyze(value)
    assert max(map(len, report["dependency_layers"])) == 3
    assert report["dependency_width"] == 4


@pytest.mark.parametrize("change", [
    lambda p: p["steps"][0].update(prerequisite_step_ids=["s0"]),
    lambda p: p["steps"][0].update(prerequisite_step_ids=["s1"]),
    lambda p: p["steps"][1].update(prerequisite_step_ids=["absent"]),
    lambda p: p["steps"][1].update(step_id="s0"),
    lambda p: p["steps"][0].update(ordinal=True),
    lambda p: p["steps"][0].update(review_required="false"),
    lambda p: p["steps"][0].update(allowed_write_paths=["../outside"]),
    lambda p: p.update(root_job_id="other-root"),
    lambda p: p.update(plan_attempt_id="other-attempt"),
    lambda p: p.update(schema_version="mastermind.execution_plan/v999"),
    lambda p: p.update(new_authority=True),
])
def test_custom_cannot_bypass_incumbent_validation(change):
    value = plan(2)
    change(value)
    with pytest.raises(OrchestrationResultError):
        analyze(value)


def test_proposal_does_not_mint_an_attempt_from_invalid_expected_identity():
    value = plan()
    value["plan_attempt_id"] = None
    with pytest.raises(OrchestrationResultError):
        analyze_plan(value, expected_root_job_id="root-1", expected_plan_attempt_id=None)


def test_hierarchy_uses_explicit_subtree_and_original_policy():
    value = plan(version=5)
    value["steps"][0]["delegation"] = {"descendant_limit": 10, "max_depth": 3}
    report = analyze(value, method="hierarchical")
    assert report["reservation"]["demand"] == 12
    assert report["declared_max_runtime_depth"] == 3
    assert report["reservation"]["capacity_fits"] is True
    assert report["reservation"]["policy_compatible"] is True
    report = analyze(value, method="hierarchical", max_depth=1)
    assert report["reservation"]["capacity_fits"] is True
    assert report["reservation"]["shortfall"] == 0
    assert report["reservation"]["policy_compatible"] is False


def test_nested_candidate_requires_complete_inherited_bounds():
    value = plan(version=5, reviewed=(0,))
    value["coordinator_job_id"] = "domain-1"
    with pytest.raises(GraphPlanningError):
        analyze(value)
    report = analyze(value, coordinator_depth=1, descendant_limit=10, max_depth=3)
    assert report["reservation"]["demand"] == 10
    assert report["candidate_plan"]["root_job_id"] == "root-1"
    assert report["candidate_plan"]["coordinator_job_id"] == "domain-1"
    with pytest.raises(GraphPlanningError):
        analyze(value, coordinator_depth=1, descendant_limit=17, max_depth=3)


@pytest.mark.parametrize("method", ["unknown", "hierarchical", "fanout_join"])
def test_inapplicable_method_refuses(method):
    with pytest.raises(GraphPlanningError):
        analyze(plan(), method=method)


def test_tighter_declared_limit_does_not_rewrite_review():
    report = analyze(plan(reviewed=(0,)), descendant_limit=9)
    assert report["reservation"]["shortfall"] == 1
    assert report["reservation"]["capacity_fits"] is False
    assert report["reservation"]["policy_compatible"] is False
    assert report["candidate_plan"]["steps"][0]["review_required"] is True


def test_real_cli_produces_candidate_and_retains_failure_boundary(tmp_path, capsys):
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(plan(2, reviewed=(0, 1))))
    before = path.read_bytes()
    code = main(["plan", str(path), "--root-job-id", "root-1", "--plan-attempt-id", "attempt-1", "--method", "pipeline"])
    result = json.loads(capsys.readouterr().out)
    assert code == 1 and result["reservation"]["demand"] == 19
    assert path.read_bytes() == before
    assert result["admission_state"] == "NOT_REQUESTED"
    path.write_text('{"schema_version": 1, "schema_version": 2}')
    assert main(["plan", str(path), "--root-job-id", "root-1", "--plan-attempt-id", "attempt-1"]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "INVALID_INPUT"


@pytest.mark.parametrize("filename,method,expected", [
    ("direct", "direct", 0), ("fanout_join", "fanout_join", 0),
    ("hierarchical", "hierarchical", 0), ("over_capacity", "pipeline", 1),
    ("fanout_join", "custom", 0),
])
def test_documented_examples_use_the_real_consumer(filename, method, expected, capsys):
    path = Path(__file__).resolve().parents[1] / "examples" / "fabric_graph" / f"{filename}.json"
    original = path.read_bytes()
    assert main(["plan", str(path), "--root-job-id", "example-root",
                 "--plan-attempt-id", "example-plan-attempt", "--method", method]) == expected
    result = json.loads(capsys.readouterr().out)
    assert result["admission_state"] == "NOT_REQUESTED"
    assert result["integration_contract_semantics"] == "NOT_EVALUATED"
    assert path.read_bytes() == original
