"""Calibrated child fit must not inherit principal cost or lose risk gates."""
import dataclasses
import json
import pytest

from control_plane.executive_responsibility import ResponsibilityIntent
from control_plane.model_router import (
    ChatReasoningMode, CognitionRoute, ModelRouter, RouteMode, RoutingPolicyError,
    SuitabilityTier, TaskFit, WorkRequest,
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


@pytest.mark.parametrize("kind", ["implementation", "mechanical", "tests", "research", "review"])
def test_c2_uses_reviewed_stronger_worker_band_without_relabelling_execution_risk(kind):
    router = ModelRouter.load()
    decision = router.route(WorkRequest(kind, task_fit=TaskFit("C2")))
    stronger = router.route(WorkRequest(kind, risk="elevated"))
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



def test_task_fit_preserves_the_existing_positional_responsibility_argument():
    role = ResponsibilityIntent("operator", "execute")
    fit = TaskFit("C1", business_impact="material")
    request = WorkRequest("implementation", "routine", "low", (), (), role, fit)
    assert request.responsibility_intent == role
    assert request.task_fit is fit
    decision = ModelRouter.load().route(request)
    assert decision.responsibility_intent == role
    assert decision.task_fit is fit
    malformed = {**role.to_dict(), "allowed_child_roles": ["worker"]}
    with pytest.raises(RoutingPolicyError):
        WorkRequest("implementation", "routine", "low", (), (), malformed, fit)


@pytest.mark.parametrize("with_role, with_fit", [
    (False, False), (True, False), (False, True), (True, True),
])
def test_task_fit_and_responsibility_keep_independent_wire_contracts(with_role, with_fit):
    role = ResponsibilityIntent("operator", "execute")
    fit = TaskFit("C1", business_impact="material")
    decision = ModelRouter.load().route(WorkRequest(
        "implementation",
        excluded_worker_ids=("worker-author",),
        responsibility_intent=role if with_role else None,
        task_fit=fit if with_fit else None,
    ))
    wire = decision.to_dict()
    constraints = decision.job_constraints()
    if with_role:
        assert wire["responsibility_intent"] == role.to_dict()
        assert wire["responsibility_intent_digest"] == role.digest
        assert constraints["responsibility_intent"] == role.to_dict()
        assert constraints["responsibility_intent_digest"] == role.digest
    else:
        for value in (wire, constraints):
            assert "responsibility_intent" not in value
            assert "responsibility_intent_digest" not in value
    if with_fit:
        assert wire["task_fit"] == fit.to_dict()
        assert wire["independent_review_required"] is True
    else:
        assert "task_fit" not in wire
        assert "independent_review_required" not in wire
    assert constraints["excluded_worker_ids"] == ["worker-author"]


@pytest.mark.parametrize("complexity", ["C1", "C2"])
@pytest.mark.parametrize("topology", ["worker", "coordinator"])
def test_classification_cannot_convert_coordinate_intent_to_worker_admission(complexity, topology):
    decision = ModelRouter.load().route(WorkRequest(
        "implementation",
        responsibility_intent=ResponsibilityIntent("operator", "coordinate"),
        task_fit=TaskFit(complexity, topology=topology),
    ))
    assert decision.mode is RouteMode.WORKER
    with pytest.raises(RoutingPolicyError, match="coordinator admission"):
        decision.job_constraints()


def test_c2_preserves_elevated_tier_order_and_first_profile():
    router = ModelRouter.load()
    first = router.routes["implementation"]["elevated"][0]
    later = SuitabilityTier(
        "implementation.elevated.later",
        router.routes["implementation"]["routine"][0].model_aliases,
    )
    router.routes["implementation"]["elevated"] = (first, later)
    decision = router.route(WorkRequest("implementation", task_fit=TaskFit("C2")))
    assert decision.suitability_tiers == (first, later)
    assert decision.preferred_model_aliases == first.model_aliases
    assert decision.execution_profile_id == router.model_aliases[first.model_aliases[0]].execution_profile_id
    assert decision.risk == "routine"


def test_c3_preserves_responsibility_and_current_frontier_selection_guards():
    router = ModelRouter.load()
    role = ResponsibilityIntent("operator", "execute")
    fit = TaskFit("C3", frontier_witness_kind="hard_debugging",
                  frontier_witness="Resolve incompatible custody and rollback constraints.")
    request = WorkRequest("implementation", responsibility_intent=role, task_fit=fit)
    decision = router.route(request, frontier_model_alias="frontier.orchestrator")
    assert decision.mode is RouteMode.FRONTIER_LEAD
    assert decision.responsibility_intent == role
    assert decision.task_fit is fit
    assert decision.to_dict()["responsibility_intent_digest"] == role.digest
    with pytest.raises(RoutingPolicyError):
        decision.job_constraints()
    with pytest.raises(RoutingPolicyError, match="non-worker"):
        router.route(request, frontier_model_alias="standard.engineering")
    router.model_aliases["frontier.orchestrator"] = dataclasses.replace(
        router.model_aliases["frontier.orchestrator"],
        capabilities=("implementation",),
    )
    with pytest.raises(RoutingPolicyError, match="lead capabilities"):
        router.route(request, frontier_model_alias="frontier.orchestrator")


@pytest.mark.parametrize("kwargs", [
    {"frontier_model_alias": "frontier.orchestrator"},
    {"cognition_route": CognitionRoute.CHAT_INCLUDED_DEFAULT},
    {"chat_reasoning_mode": ChatReasoningMode.PRO_MODE_EXCEPTION},
    {"pro_mode_receipt": object()},
])
def test_c2_does_not_acquire_frontier_cognition_or_pro_authority(kwargs):
    with pytest.raises(RoutingPolicyError):
        ModelRouter.load().route(
            WorkRequest("implementation", task_fit=TaskFit("C2")), **kwargs,
        )


def test_legacy_unrouted_creation_keeps_business_impact_without_task_fit(tmp_path, capsys):
    assert main(["--root", str(tmp_path), "create-job", "legacy bounded work",
                 "--business-impact", "critical"]) == 0
    job = json.loads(capsys.readouterr().out)
    assert job["business_impact"] == "critical"
    assert job["review_required"] is False
    assert "routing_reason_codes" not in job["constraints"]


def test_explicit_review_still_binds_a_calibrated_review_job(tmp_path, capsys):
    assert main(["--root", str(tmp_path), "create-job", "explicit review gate",
                 "--task-kind", "review", "--task-complexity", "C1",
                 "--business-impact", "critical", "--review-required"]) == 0
    job = json.loads(capsys.readouterr().out)
    assert job["review_required"] is True
    assert "task_complexity_c1" in job["constraints"]["routing_reason_codes"]
