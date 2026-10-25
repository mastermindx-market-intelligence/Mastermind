"""Router/paid-cognition composition for the unarmed Fable API principal."""
from __future__ import annotations

import json

import pytest

from control_plane.fable_api_principal import FableApiPrincipal, FableApiRefused, FableRequest
from control_plane.model_router import (
    CognitionRoute, DEFAULT_POLICY_PATH, MeteredCognitionReceipt, ModelRouter,
    RouteMode, RoutingPolicyError, WorkRequest,
)


def _receipt():
    return MeteredCognitionReceipt(
        why_metered="bounded machine-consumed strategic advice from provider API",
        why_pro_chat_insufficient="included Chat has no authenticated machine result callback",
        expected_max_cost=3.0,
        hard_budget_cap=3.0,
        stop_condition="one complete strategic advice response or first refusal",
        budget_authority="approved-metered-envelope-fixture",
    )


def _request():
    return FableRequest(
        root_id="source-root", attempt_id="source-attempt",
        question="Which architecture should be built?",
        evidence_brief="Two documented designs conflict.",
        source_refs=("https://github.com/example/repo/pull/10",),
        max_output_tokens=2048,
    )


def test_exact_fable_api_catalogue_route_is_disabled_and_not_a_worker():
    router = ModelRouter.load()
    profile = router.resolve_frontier_model_alias("fable.api.principal")
    assert profile.model == "claude-fable-5-1"
    assert profile.provider_alias == "anthropic_api"
    assert profile.adapter_id == "anthropic-api-principal"
    assert not profile.worker_eligible
    assert not router.providers["anthropic_api"].enabled
    assert not router.providers["anthropic_api"].autonomous_allowed
    with pytest.raises(RoutingPolicyError, match="not worker eligible"):
        router.resolve_model_alias("fable.api.principal")


def test_paid_route_selection_carries_receipt_but_not_api_execution_authority():
    router = ModelRouter.load()
    decision = router.route(
        WorkRequest("planning"), frontier_model_alias="fable.api.principal",
        cognition_route=CognitionRoute.METERED_EXCEPTION,
        metered_cognition_receipt=_receipt(),
    )
    assert decision.mode is RouteMode.FRONTIER_LEAD
    assert decision.preferred_model_aliases == ("fable.api.principal",)
    assert decision.metered_cognition_receipt is not None
    emitted = []
    principal = FableApiPrincipal(
        router=router, decision=decision,
        reserve=lambda *_: emitted.append("reserve"),
        credential_loader=lambda: emitted.append("credential"),
        send=lambda *_: emitted.append("provider"),
    )
    with pytest.raises(FableApiRefused, match="not a qualified admitted route"):
        principal.invoke(_request())
    assert emitted == []


def test_cannot_just_flip_disabled_api_provider_to_live(tmp_path):
    policy = json.loads(DEFAULT_POLICY_PATH.read_text(encoding="utf-8"))
    policy["providers"]["anthropic_api"]["enabled"] = True
    policy["providers"]["anthropic_api"]["autonomous_allowed"] = False
    path = tmp_path / "attempt-to-arm.json"
    path.write_text(json.dumps(policy), encoding="utf-8")
    with pytest.raises(RoutingPolicyError, match="unimplemented adapter"):
        ModelRouter.load(path)


def test_missing_paid_receipt_is_rejected_before_advice_path():
    router = ModelRouter.load()
    with pytest.raises(RoutingPolicyError, match="complete metered cognition receipt"):
        router.route(
            WorkRequest("planning"), frontier_model_alias="fable.api.principal",
            cognition_route=CognitionRoute.METERED_EXCEPTION,
        )
