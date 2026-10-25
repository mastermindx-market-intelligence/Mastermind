"""Router/paid-cognition composition for the unarmed Fable API principal."""
from __future__ import annotations

import dataclasses
import json

import pytest

from control_plane.fable_api_principal import (
    FableApiPrincipal, FableApiRefused, FableRequest, CapacityReservation,
    ProviderDispatchReceipt,
)
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
        frontier_witness="materially conflicting architecture contracts across products",
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
        bound_root_id="source-root", bound_attempt_id="source-attempt",
        reserve=lambda *_: emitted.append("reserve"),
        record_dispatch=lambda *_: emitted.append("dispatch"),
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


def test_explicitly_qualified_mock_route_to_paid_advice_integration(tmp_path, monkeypatch):
    """Offline router -> Capacity -> dispatch -> credential -> API -> advice proof.

    Enabling a test descriptor is not production permission or a Fabric start.
    """
    from control_plane import worker_adapter

    source = json.loads(DEFAULT_POLICY_PATH.read_text(encoding="utf-8"))
    source["providers"]["anthropic_api"]["enabled"] = True
    source["providers"]["anthropic_api"]["autonomous_allowed"] = False
    fixture = tmp_path / "qualified-offline-mock.json"
    fixture.write_text(json.dumps(source), encoding="utf-8")
    desc = worker_adapter.adapter_descriptor("anthropic-api-principal")
    monkeypatch.setitem(
        worker_adapter.ADAPTER_DESCRIPTORS,
        "anthropic-api-principal",
        dataclasses.replace(desc, implemented=True),
    )
    router = ModelRouter.load(fixture)
    selected = router.route(
        WorkRequest("planning"),
        frontier_model_alias="fable.api.principal",
        cognition_route=CognitionRoute.METERED_EXCEPTION,
        metered_cognition_receipt=_receipt(),
    )

    observations = []
    def reserve(root, attempt, authority, estimate):
        observations.append("reserve")
        return CapacityReservation(root, attempt, authority, estimate, "res-mock1")
    def dispatch(root, attempt, reservation, digest):
        observations.append("dispatch")
        return ProviderDispatchReceipt(root, attempt, reservation, digest, "disp-mock1")
    def credential():
        observations.append("credential")
        return "sk-ant-mock-secret"
    def send(headers, body):
        observations.append("send")
        assert headers["x-api-key"] == "sk-ant-mock-secret"
        assert json.loads(body)["model"] == "claude-fable-5-1"
        return 200, json.dumps({
            "type": "message", "id": "msg_mock1234", "model": "claude-fable-5-1",
            "stop_reason": "end_turn", "content": [
                {"type": "text", "text": "Recommendation: validate architecture and risks."}],
            "usage": {"input_tokens": 200, "output_tokens": 100},
        }).encode()

    principal = FableApiPrincipal(
        router=router, decision=selected,
        bound_root_id="source-root", bound_attempt_id="source-attempt",
        reserve=reserve, record_dispatch=dispatch,
        credential_loader=credential, send=send,
    )
    response = principal.invoke(_request())
    assert observations == ["reserve", "credential", "dispatch", "send"]
    assert response.provider_message_id == "msg_mock1234"
    assert response.dispatch_ref == "disp-mock1"
    assert response.source_refs == ("https://github.com/example/repo/pull/10",)
    assert response.input_tokens == 200 and response.output_tokens == 100
    assert len(response.request_sha256) == 64 and len(response.response_sha256) == 64
    with pytest.raises(RoutingPolicyError, match="frontier-lead work"):
        selected.job_constraints()
