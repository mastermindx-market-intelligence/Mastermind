from __future__ import annotations

import json
import math

import pytest

from control_plane.model_router import (
    ChatReasoningMode,
    CognitionRoute,
    MeteredCognitionReceipt,
    ModelRouter,
    ProModeReceipt,
    ProModeTaskClass,
    RouteMode,
    RoutingPolicyError,
    WorkRequest,
    route_work,
)


def _metered_receipt(**overrides):
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


def _pro_receipt(**overrides):
    values = {
        "task_class": ProModeTaskClass.CROSS_SYSTEM_ARCHITECTURE,
        "why_pro_mode": "the architecture decision spans multiple execution systems",
        "why_non_pro_insufficient": "the joined constraints need a sustained frontier pass",
        "expected_duration_minutes": 80,
        "stop_condition": "one coherent architecture decision or the first hard blocker",
    }
    values.update(overrides)
    return ProModeReceipt(**values)


def test_lead_work_defaults_to_included_chat_non_pro_without_receipts() -> None:
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
        assert decision.cognition_route is CognitionRoute.CHAT_INCLUDED_DEFAULT
        assert decision.chat_reasoning_mode is ChatReasoningMode.NON_PRO_DEFAULT
        assert decision.metered_cognition_receipt is None
        assert decision.pro_mode_receipt is None
        assert "chat_included_default" in decision.reason_codes
        assert "non_pro_default" in decision.reason_codes
        with pytest.raises(RoutingPolicyError, match="frontier-lead work"):
            decision.job_constraints()


def test_explicit_pro_mode_accepts_a_genuinely_long_receipted_task() -> None:
    router = ModelRouter.load()
    receipt = _pro_receipt(
        task_class="LONG_HORIZON_FRONTIER_REASONING",
        expected_duration_minutes=80,
    )

    decision = router.route(
        WorkRequest("planning"),
        chat_reasoning_mode="PRO_MODE_EXCEPTION",
        pro_mode_receipt=receipt,
    )

    assert receipt.task_class is ProModeTaskClass.LONG_HORIZON_FRONTIER_REASONING
    assert decision.cognition_route is CognitionRoute.CHAT_INCLUDED_DEFAULT
    assert decision.chat_reasoning_mode is ChatReasoningMode.PRO_MODE_EXCEPTION
    assert decision.pro_mode_receipt == receipt
    assert "chat_included_default" in decision.reason_codes
    assert "pro_mode_exception_receipt_complete" in decision.reason_codes
    assert "non_pro_default" not in decision.reason_codes


def test_pro_mode_requires_a_complete_receipt() -> None:
    router = ModelRouter.load()

    with pytest.raises(
        RoutingPolicyError,
        match="PRO_MODE_REFUSED / USE_NON_PRO_MODE",
    ):
        router.route(
            WorkRequest("planning"),
            chat_reasoning_mode=ChatReasoningMode.PRO_MODE_EXCEPTION,
        )


def test_pro_receipt_rejects_a_four_minute_handoff() -> None:
    with pytest.raises(
        RoutingPolicyError,
        match="PRO_MODE_REFUSED / USE_NON_PRO_MODE",
    ):
        _pro_receipt(expected_duration_minutes=4)


@pytest.mark.parametrize("duration", [True, False, 80.0, 80.5])
def test_pro_receipt_duration_must_be_an_integer_not_bool(duration: object) -> None:
    with pytest.raises(
        RoutingPolicyError,
        match="PRO_MODE_REFUSED / USE_NON_PRO_MODE",
    ):
        _pro_receipt(expected_duration_minutes=duration)


def test_pro_receipt_is_bounded_and_duration_has_a_hard_ceiling() -> None:
    for field in (
        "why_pro_mode",
        "why_non_pro_insufficient",
        "stop_condition",
    ):
        with pytest.raises(RoutingPolicyError):
            _pro_receipt(**{field: ""})
        with pytest.raises(RoutingPolicyError):
            _pro_receipt(**{field: "x" * 2049})

    with pytest.raises(
        RoutingPolicyError,
        match="PRO_MODE_REFUSED / USE_NON_PRO_MODE",
    ):
        _pro_receipt(expected_duration_minutes=1441)


@pytest.mark.parametrize(
    "forbidden_class",
    ["handoff", "status", "routing", "monitoring", "mechanical", "simple_review"],
)
def test_pro_receipt_rejects_non_pro_task_classes_at_construction(
    forbidden_class: str,
) -> None:
    with pytest.raises(
        RoutingPolicyError,
        match="PRO_MODE_REFUSED / USE_NON_PRO_MODE",
    ):
        _pro_receipt(task_class=forbidden_class)


def test_non_pro_chat_rejects_an_attached_pro_receipt_instead_of_ignoring_it() -> None:
    router = ModelRouter.load()

    with pytest.raises(
        RoutingPolicyError,
        match="PRO_MODE_REFUSED / USE_NON_PRO_MODE",
    ):
        router.route(
            WorkRequest("judgment"),
            chat_reasoning_mode=ChatReasoningMode.NON_PRO_DEFAULT,
            pro_mode_receipt=_pro_receipt(
                task_class=ProModeTaskClass.ADVERSARIAL_JUDGMENT
            ),
        )


@pytest.mark.parametrize("task_kind", ["mechanical", "tests"])
def test_pro_mode_is_hard_refused_for_mechanical_and_test_work(
    task_kind: str,
) -> None:
    router = ModelRouter.load()

    with pytest.raises(
        RoutingPolicyError,
        match="PRO_MODE_REFUSED / USE_NON_PRO_MODE",
    ):
        router.route(
            WorkRequest(task_kind, risk="critical"),
            chat_reasoning_mode=ChatReasoningMode.PRO_MODE_EXCEPTION,
            pro_mode_receipt=_pro_receipt(
                task_class=ProModeTaskClass.HARD_DEBUGGING
            ),
        )


@pytest.mark.parametrize(
    ("work_request", "task_class"),
    [
        (WorkRequest("planning"), ProModeTaskClass.HARD_DEBUGGING),
        (WorkRequest("judgment"), ProModeTaskClass.HARD_DEBUGGING),
        (WorkRequest("escalation"), ProModeTaskClass.LONG_HORIZON_FRONTIER_REASONING),
        (
            WorkRequest("implementation", risk="critical"),
            ProModeTaskClass.ADVERSARIAL_JUDGMENT,
        ),
        (
            WorkRequest("research", ambiguity="high"),
            ProModeTaskClass.CROSS_SYSTEM_ARCHITECTURE,
        ),
        (
            WorkRequest("review", risk="critical"),
            ProModeTaskClass.CROSS_SYSTEM_ARCHITECTURE,
        ),
    ],
)
def test_pro_mode_rejects_task_kind_and_task_class_mismatches(
    work_request: WorkRequest,
    task_class: ProModeTaskClass,
) -> None:
    router = ModelRouter.load()

    with pytest.raises(
        RoutingPolicyError,
        match="PRO_MODE_REFUSED / USE_NON_PRO_MODE",
    ):
        router.route(
            work_request,
            chat_reasoning_mode=ChatReasoningMode.PRO_MODE_EXCEPTION,
            pro_mode_receipt=_pro_receipt(task_class=task_class),
        )


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

    receipt = _metered_receipt()
    decision = router.route(
        WorkRequest("planning"),
        cognition_route=CognitionRoute.METERED_EXCEPTION,
        metered_cognition_receipt=receipt,
    )
    assert decision.cognition_route is CognitionRoute.METERED_EXCEPTION
    assert decision.chat_reasoning_mode is None
    assert decision.metered_cognition_receipt == receipt
    assert decision.pro_mode_receipt is None
    assert "metered_exception_receipt_complete" in decision.reason_codes
    with pytest.raises(RoutingPolicyError, match="frontier-lead work"):
        decision.job_constraints()


@pytest.mark.parametrize(
    "chat_fields",
    [
        {"chat_reasoning_mode": ChatReasoningMode.NON_PRO_DEFAULT},
        {
            "chat_reasoning_mode": ChatReasoningMode.PRO_MODE_EXCEPTION,
            "pro_mode_receipt": _pro_receipt(),
        },
        {"pro_mode_receipt": _pro_receipt()},
    ],
)
def test_metered_route_refuses_chat_mode_and_pro_receipt_fields(
    chat_fields: dict[str, object],
) -> None:
    router = ModelRouter.load()

    with pytest.raises(
        RoutingPolicyError,
        match="METERED_ROUTE_REFUSED / WAITING_FOR_LAWFUL_ROUTE",
    ):
        router.route(
            WorkRequest("planning"),
            cognition_route=CognitionRoute.METERED_EXCEPTION,
            metered_cognition_receipt=_metered_receipt(),
            **chat_fields,
        )


def test_metered_receipt_is_bounded_and_expected_cost_cannot_exceed_cap() -> None:
    for field in (
        "why_metered",
        "why_pro_chat_insufficient",
        "stop_condition",
        "budget_authority",
    ):
        with pytest.raises(RoutingPolicyError):
            _metered_receipt(**{field: ""})
        with pytest.raises(RoutingPolicyError):
            _metered_receipt(**{field: "x" * 2049})

    with pytest.raises(RoutingPolicyError):
        _metered_receipt(expected_max_cost=11.0, hard_budget_cap=10.0)
    with pytest.raises(RoutingPolicyError):
        _metered_receipt(expected_max_cost=-1.0)
    with pytest.raises(RoutingPolicyError):
        _metered_receipt(hard_budget_cap=0.0)
    with pytest.raises(RoutingPolicyError):
        _metered_receipt(expected_max_cost=math.inf)
    with pytest.raises(RoutingPolicyError):
        _metered_receipt(hard_budget_cap=math.nan)


def test_chat_default_rejects_an_attached_metered_receipt_instead_of_ignoring_it() -> None:
    router = ModelRouter.load()

    with pytest.raises(RoutingPolicyError, match="metered receipt"):
        router.route(
            WorkRequest("judgment"),
            cognition_route=CognitionRoute.CHAT_INCLUDED_DEFAULT,
            metered_cognition_receipt=_metered_receipt(),
        )


def test_worker_routes_remain_economical_and_have_no_sol_cognition_fields() -> None:
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
        assert decision.chat_reasoning_mode is None
        assert decision.metered_cognition_receipt is None
        assert decision.pro_mode_receipt is None
        assert decision.job_constraints()["preferred_model_aliases"]


@pytest.mark.parametrize(
    ("sol_fields", "error_match"),
    [
        ({"cognition_route": CognitionRoute.CHAT_INCLUDED_DEFAULT}, "Sol cognition"),
        (
            {
                "cognition_route": CognitionRoute.METERED_EXCEPTION,
                "metered_cognition_receipt": _metered_receipt(),
            },
            "Sol cognition",
        ),
        (
            {"chat_reasoning_mode": ChatReasoningMode.NON_PRO_DEFAULT},
            "Sol cognition",
        ),
        (
            {"pro_mode_receipt": _pro_receipt()},
            "PRO_MODE_REFUSED / USE_NON_PRO_MODE",
        ),
    ],
)
def test_worker_route_refuses_all_sol_cognition_fields(
    sol_fields: dict[str, object],
    error_match: str,
) -> None:
    router = ModelRouter.load()

    with pytest.raises(RoutingPolicyError, match=error_match):
        router.route(WorkRequest("implementation"), **sol_fields)


def test_pro_lead_projection_is_json_safe_and_names_mode_and_receipt() -> None:
    receipt = _pro_receipt(task_class=ProModeTaskClass.CROSS_SYSTEM_ARCHITECTURE)
    decision = route_work(
        "planning",
        cognition_route="CHAT_INCLUDED_DEFAULT",
        chat_reasoning_mode="PRO_MODE_EXCEPTION",
        pro_mode_receipt=receipt,
    )

    payload = decision.to_dict()
    assert payload["cognition_route"] == "CHAT_INCLUDED_DEFAULT"
    assert payload["chat_reasoning_mode"] == "PRO_MODE_EXCEPTION"
    assert payload["metered_cognition_receipt"] is None
    assert payload["pro_mode_receipt"] == {
        "task_class": "CROSS_SYSTEM_ARCHITECTURE",
        "why_pro_mode": receipt.why_pro_mode,
        "why_non_pro_insufficient": receipt.why_non_pro_insufficient,
        "expected_duration_minutes": 80,
        "stop_condition": receipt.stop_condition,
    }
    json.dumps(payload)
