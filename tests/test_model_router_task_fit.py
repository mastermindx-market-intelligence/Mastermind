"""Calibrated child fit must not inherit principal cost or lose risk gates."""
import json
import pytest

from control_plane.model_router import (
    ModelRouter, RouteMode, RoutingPolicyError, TaskFit, WorkRequest,
)
from scripts.executive_os_phase1b import main


@pytest.mark.parametrize("kind", ["implementation", "mechanical", "tests", "research", "review"])
@pytest.mark.parametrize("impact", ["routine", "material", "critical"])
@pytest.mark.parametrize("topology", ["principal", "coordinator", "worker", "subagent", "reviewer"])
def test_importance_and_hierarchy_do_not_promote_bounded_work(kind, impact, topology):
    router = ModelRouter.load()
    baseline = router.route(WorkRequest(kind))
    fit = TaskFit("C1", business_impact=impact, topology=topology)
    decision = router.route(WorkRequest(kind, task_fit=fit))
    assert decision.mode is RouteMode.WORKER
    assert decision.suitability_tiers == baseline.suitability_tiers
    assert decision.risk == "routine"
    assert decision.requires_independent_review == (impact != "routine" and kind != "review")
    assert "task_complexity_c1" in decision.job_constraints()["routing_reason_codes"]
    assert f"business_impact_{impact}" in decision.job_constraints()["routing_reason_codes"]
    assert f"task_topology_{topology}" in decision.job_constraints()["routing_reason_codes"]


def test_c2_uses_reviewed_stronger_worker_band_without_relabelling_execution_risk():
    router = ModelRouter.load()
    decision = router.route(WorkRequest("implementation", task_fit=TaskFit("C2")))
    stronger = router.route(WorkRequest("implementation", risk="elevated"))
    assert decision.mode is RouteMode.WORKER
    assert decision.suitability_tiers == stronger.suitability_tiers
    assert decision.risk == "routine"
    assert "complexity_c2_stronger_suitability" in decision.reason_codes


@pytest.mark.parametrize("complexity", ["C0", "C1", "C2"])
def test_critical_execution_risk_is_never_downgraded(complexity):
    result = ModelRouter.load().route(WorkRequest(
        "implementation", risk="critical", task_fit=TaskFit(complexity)))
    assert result.mode is RouteMode.FRONTIER_LEAD
    assert result.task_fit.complexity == complexity
    assert "critical_risk" in result.reason_codes
    with pytest.raises(RoutingPolicyError):
        result.job_constraints()


def test_c3_has_a_bounded_witness_and_still_cannot_self_dispatch():
    fit = TaskFit("C3", frontier_witness_kind="cross_system_tradeoff",
                  frontier_witness="Choose between incompatible custody and latency constraints.")
    result = ModelRouter.load().route(WorkRequest("implementation", task_fit=fit))
    assert result.mode is RouteMode.FRONTIER_LEAD
    assert result.to_dict()["task_fit"] == fit.to_dict()
    assert result.to_dict()["task_fit"]["classification_is_authority"] is False
    with pytest.raises(RoutingPolicyError):
        result.job_constraints()


@pytest.mark.parametrize("kwargs", [
    {"complexity": "C3"},
    {"complexity": "C3", "frontier_witness_kind": "important", "frontier_witness": "important"},
    {"complexity": "C3", "frontier_witness_kind": "hard_debugging", "frontier_witness": " "},
    {"complexity": "C3", "frontier_witness_kind": "hard_debugging", "frontier_witness": "x" * 2049},
    {"complexity": "C1", "frontier_witness_kind": "hard_debugging", "frontier_witness": "No."},
    {"complexity": True}, {"complexity": "C4"},
    {"complexity": "C1", "business_impact": "unlimited"},
    {"complexity": "C1", "topology": "unbounded_recursion"},
])
def test_malformed_or_inconsistent_fit_is_rejected(kwargs):
    with pytest.raises(RoutingPolicyError):
        TaskFit(**kwargs)


@pytest.mark.parametrize("complexity", ["C0", "C1", "C2"])
def test_unresolved_work_cannot_claim_a_bounded_fit(complexity):
    with pytest.raises(RoutingPolicyError):
        WorkRequest("implementation", ambiguity="high", task_fit=TaskFit(complexity))
    with pytest.raises(RoutingPolicyError):
        WorkRequest("planning", task_fit=TaskFit(complexity))


def test_legacy_wire_and_routing_stay_unchanged():
    result = ModelRouter.load().route(WorkRequest("implementation"))
    assert "task_fit" not in result.to_dict()
    assert result.requires_independent_review is False
    assert ModelRouter.load().route(WorkRequest("implementation", ambiguity="high")).mode is RouteMode.FRONTIER_LEAD
    with pytest.raises(RoutingPolicyError):
        WorkRequest("implementation", task_fit={"complexity": "C1"})


def test_native_cli_preview_consumes_fit_without_creating_state(tmp_path, capsys):
    root = tmp_path / "cli-state-must-not-exist"
    assert main(["--root", str(root), "route", "implementation",
                 "--task-complexity", "C1", "--business-impact", "critical",
                 "--task-topology", "subagent"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["mode"] == "worker"
    assert data["task_fit"]["business_impact"] == "critical"
    assert data["independent_review_required"] is True
    assert not root.exists()


@pytest.mark.parametrize("flags", [
    ["--task-topology", "subagent"],
    ["--business-impact", "critical"],
    ["--frontier-witness", "Not a complete classification."],
])
def test_native_preview_cannot_silently_drop_partial_fit(tmp_path, capsys, flags):
    root = tmp_path / "cli-state-must-not-exist"
    assert main(["--root", str(root), "route", "implementation", *flags]) == 2
    assert not root.exists()


def test_calibrated_create_job_is_blocked_without_task_kind(tmp_path, capsys):
    root = tmp_path / "cli-state-must-not-exist"
    assert main(["--root", str(root), "create-job", "bounded task",
                 "--task-complexity", "C1"]) == 2
    assert not root.exists()


@pytest.mark.parametrize("kind, expected", [("implementation", True), ("review", False)])
def test_calibrated_cli_seeds_existing_review_gate_not_a_second_review_loop(tmp_path, capsys, kind, expected):
    assert main(["--root", str(tmp_path), "create-job", "fixture bounded work",
                 "--task-kind", kind, "--task-complexity", "C1",
                 "--business-impact", "critical"]) == 0
    job = json.loads(capsys.readouterr().out)
    assert job["review_required"] is expected
    assert job["business_impact"] == "critical"
    assert "task_complexity_c1" in job["constraints"]["routing_reason_codes"]
