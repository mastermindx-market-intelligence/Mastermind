from __future__ import annotations

import math

import pytest

from control_plane.model_router import (
    CognitionRoute,
    MeteredCognitionReceipt,
    ModelRouter,
    RouteMode,
    RoutingPolicyError,
    WorkRequest,
)


def _receipt(**overrides):
    values = {
        "why_metered": "the required programmatic surface is unavailable on included Chat",
        "why_pro_chat_insufficient": "this bounded operation requires a machine-only callback",
        "expected_max_cost": 5.0,
        "hard_budget_cap": 10.0,
        "stop_condition": "one accepted bounded result or first refusal",
        "budget_authority": "chairman-envelope:cnm-r1-test",
    }
    values.update(overrides)
    return MeteredCognitionReceipt(**values)


def test_lead_work_defaults_to_chat_pro_without_a_metered_receipt() -> None:
    router = ModelRouter.load()

    for request in (
        WorkRequest("planning"),
        WorkRequest("judgment"),
        WorkRequest("escalation"),
        WorkRequest("implementation", risk="critical"),
        WorkRequest("implementation", ambiguity="high"),
    ):
        decision = router.route(request)
        assert decision.mode is RouteMode.FRONTIER_LEAD
        assert decision.cognition_route is CognitionRoute.CHAT_PRO_DEFAULT
        assert decision.metered_cognition_receipt is None
        assert "chat_pro_default" in decision.reason_codes
        with pytest.raises(RoutingPolicyError, match="frontier-lead work"):
            decision.job_constraints()


def test_explicit_metered_lead_route_requires_complete_receipt() -> None:
    router = ModelRouter.load()

    with pytest.raises(
        RoutingPolicyError,
        match="METERED_ROUTE_REFUSED / WAITING_FOR_LAWFUL_ROUTE",
    ):
        router.route(
            WorkRequest("planning"),
            cognition_route=CognitionRoute.METERED_EXCEPTION,
        )

    receipt = _receipt()
    decision = router.route(
        WorkRequest("planning"),
        cognition_route=CognitionRoute.METERED_EXCEPTION,
        metered_cognition_receipt=receipt,
    )
    assert decision.cognition_route is CognitionRoute.METERED_EXCEPTION
    assert decision.metered_cognition_receipt == receipt
    assert "metered_exception_receipt_complete" in decision.reason_codes
    with pytest.raises(RoutingPolicyError, match="frontier-lead work"):
        decision.job_constraints()


def test_metered_receipt_is_bounded_and_expected_cost_cannot_exceed_cap() -> None:
    for field in (
        "why_metered",
        "why_pro_chat_insufficient",
        "stop_condition",
        "budget_authority",
    ):
        with pytest.raises(RoutingPolicyError):
            _receipt(**{field: ""})
        with pytest.raises(RoutingPolicyError):
            _receipt(**{field: "x" * 2049})

    with pytest.raises(RoutingPolicyError):
        _receipt(expected_max_cost=11.0, hard_budget_cap=10.0)
    with pytest.raises(RoutingPolicyError):
        _receipt(expected_max_cost=-1.0)
    with pytest.raises(RoutingPolicyError):
        _receipt(hard_budget_cap=0.0)
    with pytest.raises(RoutingPolicyError):
        _receipt(expected_max_cost=math.inf)
    with pytest.raises(RoutingPolicyError):
        _receipt(hard_budget_cap=math.nan)


def test_chat_default_rejects_an_attached_metered_receipt_instead_of_ignoring_it() -> None:
    router = ModelRouter.load()

    with pytest.raises(RoutingPolicyError, match="metered receipt"):
        router.route(
            WorkRequest("judgment"),
            cognition_route=CognitionRoute.CHAT_PRO_DEFAULT,
            metered_cognition_receipt=_receipt(),
        )


def test_worker_routes_remain_economical_and_have_no_sol_cognition_route() -> None:
    router = ModelRouter.load()

    implementation = router.route(WorkRequest("implementation"))
    research = router.route(WorkRequest("research"))
    review = router.route(WorkRequest("review"))

    assert implementation.mode is RouteMode.WORKER
    assert implementation.preferred_model_aliases == (
        "fast.engineering",
        "standard.engineering",
    )
    assert research.preferred_model_aliases == (
        "fast.research",
        "standard.research",
    )
    assert review.preferred_model_aliases == ("standard.review",)
    for decision in (implementation, research, review):
        assert decision.cognition_route is None
        assert decision.metered_cognition_receipt is None
        assert decision.job_constraints()["preferred_model_aliases"]


def test_worker_route_refuses_sol_metered_parameters() -> None:
    router = ModelRouter.load()

    with pytest.raises(RoutingPolicyError, match="Sol cognition route"):
        router.route(
            WorkRequest("implementation"),
            cognition_route=CognitionRoute.METERED_EXCEPTION,
            metered_cognition_receipt=_receipt(),
        )


def test_lead_projection_is_json_safe_and_names_the_route_receipt() -> None:
    router = ModelRouter.load()
    receipt = _receipt()
    decision = router.route(
        WorkRequest("planning"),
        cognition_route="METERED_EXCEPTION",
        metered_cognition_receipt=receipt,
    )

    payload = decision.to_dict()
    assert payload["cognition_route"] == "METERED_EXCEPTION"
    assert payload["metered_cognition_receipt"] == {
        "why_metered": receipt.why_metered,
        "why_pro_chat_insufficient": receipt.why_pro_chat_insufficient,
        "expected_max_cost": 5.0,
        "hard_budget_cap": 10.0,
        "stop_condition": receipt.stop_condition,
        "budget_authority": receipt.budget_authority,
    }
