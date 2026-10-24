from __future__ import annotations

import json

import pytest

from control_plane.model_router import (
    DEFAULT_POLICY_PATH,
    ChatReasoningMode,
    CognitionRoute,
    MeteredCognitionReceipt,
    ModelRouter,
    ProModeReceipt,
    RouteMode,
    RoutingPolicyError,
    WorkRequest,
    route_work,
)


def _policy(tmp_path, *, provider="codex", remove_default=False, disable_provider=False):
    raw = json.loads(DEFAULT_POLICY_PATH.read_text(encoding="utf-8"))
    if disable_provider:
        raw["providers"][provider]["enabled"] = False
        raw["providers"][provider]["autonomous_allowed"] = False
    raw["model_aliases"]["fixture.frontier"] = {
        **raw["model_aliases"]["frontier.orchestrator"],
        "provider_alias": provider,
        "model": "fixture-frontier-model",
        "execution_profile_id": "operator.appserver.readonly.docs-mcp.native-helper.v1",
    }
    if disable_provider:
        # Closed disabled catalogue: a deliberately disabled provider must not
        # keep any armed alias. worker_eligible=False is forced on EVERY alias
        # matching the disabled provider, including fixture.frontier above.
        for alias in raw["model_aliases"].values():
            if alias["provider_alias"] == provider:
                alias["worker_eligible"] = False
    if remove_default:
        del raw["model_aliases"]["frontier.orchestrator"]
    path = tmp_path / "routes.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    return ModelRouter.load(path)


@pytest.mark.parametrize(
    "work_request",
    [
        WorkRequest("planning"),
        WorkRequest("judgment"),
        WorkRequest("escalation"),
        WorkRequest("implementation", risk="critical"),
        WorkRequest("implementation", ambiguity="high"),
    ],
)
def test_explicit_frontier_selection_returns_selected_identity_without_worker_authority(
    tmp_path, work_request
):
    router = _policy(tmp_path)
    selected = router.resolve_frontier_model_alias("fixture.frontier")
    decision = router.route(work_request, frontier_model_alias="fixture.frontier")

    assert decision.mode is RouteMode.FRONTIER_LEAD
    assert decision.preferred_model_aliases == ("fixture.frontier",)
    assert decision.execution_profile_id == selected.execution_profile_id
    assert decision.execution_profile_digest == selected.execution_profile_digest
    assert decision.execution_profile_digest != (
        router.model_aliases["frontier.orchestrator"].execution_profile_digest
    )
    assert decision.capability_policy_version == selected.capability_policy_version
    assert decision.capability_policy_digest == selected.capability_policy_digest
    assert "frontier_model_selected" in decision.reason_codes
    assert decision.cognition_route is CognitionRoute.CHAT_INCLUDED_DEFAULT
    assert decision.chat_reasoning_mode is ChatReasoningMode.NON_PRO_DEFAULT
    assert not selected.worker_eligible
    with pytest.raises(RoutingPolicyError, match="frontier-lead work"):
        decision.job_constraints()
    with pytest.raises(RoutingPolicyError, match="not worker eligible"):
        router.resolve_model_alias("fixture.frontier")


@pytest.mark.parametrize("provider", ["anthropic", "glm", "xai"])
def test_disabled_provider_can_describe_logical_cognition_without_admission(
    tmp_path, provider
):
    router = _policy(tmp_path, provider=provider, disable_provider=True)
    assert not router.providers[provider].enabled
    assert not router.providers[provider].autonomous_allowed
    assert router.model_aliases["fixture.frontier"].worker_eligible is False

    decision = router.route(
        WorkRequest("planning"), frontier_model_alias="fixture.frontier"
    )

    assert decision.preferred_model_aliases == ("fixture.frontier",)
    with pytest.raises(RoutingPolicyError, match="frontier-lead work"):
        decision.job_constraints()


@pytest.mark.parametrize(
    ("alias", "message"),
    [
        ("unregistered.frontier", "unknown frontier model alias"),
        ("fast.engineering", "must be non-worker"),
        ("coo.operator.readonly", "must be non-worker"),
        ("minimax.attended", "lacks required lead capabilities"),
        ("", "bounded lowercase identifier"),
        ("provider/model", "bounded lowercase identifier"),
        (123, "must be a string"),
        (True, "must be a string"),
        ({}, "must be a string"),
    ],
)
def test_invalid_explicit_selection_refuses_without_default_fallback(
    tmp_path, alias, message
):
    router = _policy(tmp_path)
    with pytest.raises(RoutingPolicyError, match=message):
        router.route(WorkRequest("planning"), frontier_model_alias=alias)


def test_frontier_resolver_uses_existing_alias_normalization(tmp_path):
    router = _policy(tmp_path)
    assert router.resolve_frontier_model_alias(
        "  FIXTURE.FRONTIER  "
    ).model_alias == "fixture.frontier"


def test_explicit_selection_does_not_depend_on_a_legacy_default_alias(tmp_path):
    router = _policy(tmp_path, remove_default=True)

    decision = router.route(
        WorkRequest("planning"), frontier_model_alias="fixture.frontier"
    )

    assert decision.preferred_model_aliases == ("fixture.frontier",)


def test_explicit_selection_checks_caller_capabilities_without_worker_route_inheritance(
    tmp_path,
):
    router = _policy(tmp_path)
    selected = router.route(
        WorkRequest("implementation", risk="critical"),
        frontier_model_alias="fixture.frontier",
    )
    assert selected.required_capabilities == ()

    compatible = router.route(
        WorkRequest("planning", required_capabilities=("judgment",)),
        frontier_model_alias="fixture.frontier",
    )
    assert compatible.required_capabilities == ("judgment",)

    with pytest.raises(RoutingPolicyError, match="cannot satisfy requested capabilities"):
        router.route(
            WorkRequest(
                "implementation", risk="critical", required_capabilities=("code",)
            ),
            frontier_model_alias="fixture.frontier",
        )

    # Existing callers keep the legacy critical/high-ambiguity lead behavior.
    legacy = router.route(
        WorkRequest("implementation", risk="critical", required_capabilities=("code",))
    )
    assert legacy.preferred_model_aliases == ("frontier.orchestrator",)
    assert "frontier_model_selected" not in legacy.reason_codes


@pytest.mark.parametrize("task_kind", ["implementation", "mechanical", "tests", "research", "review"])
def test_frontier_selection_cannot_convert_or_be_ignored_for_worker_work(tmp_path, task_kind):
    router = _policy(tmp_path)
    with pytest.raises(RoutingPolicyError, match="worker work does not accept"):
        router.route(
            WorkRequest(task_kind), frontier_model_alias="fixture.frontier"
        )
    assert router.route(WorkRequest(task_kind)).mode is RouteMode.WORKER


@pytest.mark.parametrize(
    ("options", "message"),
    [
        ({"cognition_route": "METERED_EXCEPTION"}, "complete metered cognition receipt"),
        ({"chat_reasoning_mode": "PRO_MODE_EXCEPTION"}, "complete Pro mode receipt"),
    ],
)
def test_selection_does_not_waive_cognition_receipt_requirements(
    tmp_path, options, message
):
    router = _policy(tmp_path)
    with pytest.raises(RoutingPolicyError, match=message):
        router.route(
            WorkRequest("planning"),
            frontier_model_alias="fixture.frontier",
            **options,
        )


def test_selected_lead_retains_receipted_cognition_modes(tmp_path):
    router = _policy(tmp_path)
    metered_receipt = MeteredCognitionReceipt(
        why_metered="The bounded fixture requires a machine callback.",
        why_pro_chat_insufficient="The callback is not available in included Chat.",
        expected_max_cost=1.0,
        hard_budget_cap=2.0,
        stop_condition="One bounded result or first refusal.",
        budget_authority="fixture:frontier-selection",
    )
    metered = router.route(
        WorkRequest("planning"),
        frontier_model_alias="fixture.frontier",
        cognition_route=CognitionRoute.METERED_EXCEPTION,
        metered_cognition_receipt=metered_receipt,
    )
    assert metered.preferred_model_aliases == ("fixture.frontier",)
    assert metered.metered_cognition_receipt is metered_receipt
    assert metered.chat_reasoning_mode is None

    pro_receipt = ProModeReceipt(
        task_class="CROSS_SYSTEM_ARCHITECTURE",
        why_pro_mode="A bounded architecture decision spans multiple systems.",
        why_non_pro_insufficient="The joined constraints require a sustained pass.",
        expected_duration_minutes=80,
        stop_condition="One coherent architecture decision or first blocker.",
    )
    pro = router.route(
        WorkRequest("planning"),
        frontier_model_alias="fixture.frontier",
        chat_reasoning_mode=ChatReasoningMode.PRO_MODE_EXCEPTION,
        pro_mode_receipt=pro_receipt,
    )
    assert pro.preferred_model_aliases == ("fixture.frontier",)
    assert pro.pro_mode_receipt is pro_receipt
    assert pro.chat_reasoning_mode is ChatReasoningMode.PRO_MODE_EXCEPTION


def test_route_work_forwards_explicit_logical_selection(tmp_path):
    router = _policy(tmp_path)

    decision = route_work(
        "planning",
        frontier_model_alias="fixture.frontier",
        policy_path=router.source_path,
    )

    assert decision.preferred_model_aliases == ("fixture.frontier",)
    with pytest.raises(RoutingPolicyError, match="frontier-lead work"):
        decision.job_constraints()
