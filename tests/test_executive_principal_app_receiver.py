"""Actual local service peer/framing; authority/effects are separate fixtures."""
import asyncio
import dataclasses
import json
import os

import pytest

from common.company_dialogue_principal_app_protocol import APP_REQUEST_SCHEMA, MAX_RESPONSE_BYTES
from control_plane.executive_service import CeoIngressAppBinding, ExecutiveControlService
from integrations.company_dialogue_principal_app_contract import decode_app_request
from integrations.mastermind_company_mcp.principal_schemas import principal_result_envelope
from tests.test_executive_ceo_ingress import (
    _config, _FakeGrounding, _FakeSupervisor, _raw_ceo_request,
    short_socket_root,  # noqa: F401
)
from tests.test_principal_app_dialogue_contract import encoded
from tests.test_principal_app_transport_bounds import large_frame


@pytest.mark.parametrize("change", [
    "none", "unselected", "disarmed", "c1", "foreign", "binding", "closing", "not_ready",
    "state", "routing", "qualification", "qualification_changed", "large", "large_unselected", "large_c1",
    "oversized", "duplicate", "unknown", "exception", "large_response", "oversized_response",
])
def test_exact_app_route_checks_current_host_and_preserves_frame(tmp_path, short_socket_root, monkeypatch, change):
    async def scenario():
        calls, factories, intent_guards = [], [], []

        def bounded_intent_guard(envelope):
            intent_guards.append(envelope)
            raise AssertionError("RULING must use guard_dialogue, not the bounded-intent guard")

        class Provider:
            async def ruling(self, raw, *, receiving_request_guard):
                request = decode_app_request(raw)
                calls.append((raw, request))
                receiving_request_guard()
                await asyncio.sleep(0)
                if change == "binding":
                    service._ceo_ingress_app_binding = dataclasses.replace(binding)
                elif change == "closing": service._closing = True
                elif change == "not_ready": service._ceo_ingress_ready = False
                elif change == "state": service._service_state = "STARTING"
                elif change == "routing":
                    monkeypatch.setattr(service, "_load_coo_execution_binding", lambda: {"changed": True})
                elif change == "qualification":
                    def refused(): raise ValueError("fixture qualification closed")
                    monkeypatch.setattr(service, "_require_attended_qualification", refused)
                elif change == "qualification_changed":
                    monkeypatch.setattr(service, "_require_attended_qualification", lambda: "valid-Q2")
                elif change == "exception": raise ValueError("PRIVATE_CANARY")
                # Deliberately omit the provider's post-await guard here to
                # prove the receiving service independently withholds results.
                size = MAX_RESPONSE_BYTES if change == "oversized_response" else 40000
                data = {"fixture": "x" * size} if "response" in change else {"fixture": True}
                return principal_result_envelope("ruling", data=data)

        def factory(runtime):
            assert runtime is service.runtime
            factories.append(runtime)
            return Provider()

        binding = CeoIngressAppBinding(peer_uid=os.geteuid(), armed=False,
            grounding_provider=_FakeGrounding(),
            principal_admission_armed=change != "disarmed",
            principal_admission_guard=bounded_intent_guard,
            principal_dialogue_provider_factory=None if "unselected" in change else factory)
        service = ExecutiveControlService(_config(tmp_path, socket_root=short_socket_root),
            supervisor_factory=lambda runtime: _FakeSupervisor(),
            ceo_ingress_socket_path=short_socket_root / "ceo.sock",
            ceo_ingress_peer_uid=os.geteuid()+1000,
            ceo_ingress_grounding_provider=_FakeGrounding(), ceo_ingress_armed=False,
            ceo_ingress_app_binding=binding)
        await service.start()
        try:
            before = service.runtime.events.list_events()
            raw = encoded()
            if change in {"large", "large_unselected", "large_c1", "oversized"}:
                frame = large_frame()
                if change == "oversized": frame["arguments"]["decision"] = "x" * 33000
                raw = json.dumps(frame, ensure_ascii=False).encode() + b"\n"
            if change == "duplicate":
                raw = raw.replace(b'"tool":"ruling"', b'"tool":"ruling","tool":"ruling"')
            if change == "unknown": raw = raw.replace(APP_REQUEST_SCHEMA.encode(), b"unknown")
            if change in {"c1", "large_c1", "foreign"}:
                uid = os.geteuid() + (2000 if change == "foreign" else 1000)
                monkeypatch.setattr("control_plane.executive_service._peer_uid", lambda _: uid)
            result = await _raw_ceo_request(service.ceo_ingress_socket_path, raw)
            if change in {"none", "large", "large_response"}:
                assert result["ok"] is True, result
                assert calls[0][0] == raw
                assert len(calls) == len(factories) == 1
                if change == "large_response": assert len(result["result"]["data"]["fixture"]) == 40000
            else:
                assert result["ok"] is False, result
                assert "PRIVATE_CANARY" not in json.dumps(result)
                if change in {"unselected", "disarmed", "c1", "foreign", "large_unselected", "large_c1", "oversized", "unknown"}:
                    assert calls == factories == []
                elif change == "duplicate": assert calls == [] and len(factories) == 1
                else: assert len(calls) == len(factories) == 1
            assert intent_guards == []
            assert service.runtime.events.list_events() == before
        finally:
            service._closing = False
            await service.close()
    asyncio.run(scenario())


def test_selection_requires_callable_and_defaults_off():
    binding = CeoIngressAppBinding(peer_uid=os.geteuid(), armed=False, grounding_provider=_FakeGrounding())
    assert binding.principal_dialogue_provider_factory is None
    with pytest.raises(ValueError): dataclasses.replace(binding, principal_dialogue_provider_factory=True)


@pytest.mark.parametrize("fault", ["duplicate", "tool", "caller", "nan"])
def test_real_provider_refuses_raw_frame_before_acquisition(monkeypatch, fault):
    from integrations import mastermind_company_principal_app_receiver as receiver
    calls = []
    async def forbidden(**kwargs):
        calls.append(kwargs)
        raise AssertionError("source must not be acquired")
    monkeypatch.setattr(receiver, "build_acquired_principal_decision_host", forbidden)
    raw = encoded()
    if fault == "duplicate": raw = raw.replace(b'"tool":"ruling"', b'"tool":"ruling","tool":"ruling"')
    elif fault == "tool": raw = raw.replace(b'"tool":"ruling"', b'"tool":"continue"')
    elif fault == "caller": raw = raw.replace(b'"owed_seat":"coo"', b'"owed_seat":"ceo"')
    else: raw = raw.replace(b'"tool":"ruling"', b'"tool":NaN')
    provider = receiver.PrincipalDialogueAppReceiver(None, None, None, None)
    with pytest.raises(ValueError):
        asyncio.run(provider.ruling(raw, receiving_request_guard=lambda: None))
    assert calls == []


@pytest.mark.parametrize("inner_size", [MAX_RESPONSE_BYTES - 1, MAX_RESPONSE_BYTES, MAX_RESPONSE_BYTES + 1])
@pytest.mark.parametrize("unicode_payload", [False, True])
def test_full_principal_result_fits_exact_app_envelope(tmp_path, short_socket_root, inner_size, unicode_payload):
    from common.company_dialogue_principal_app_protocol import MAX_APP_RESPONSE_BYTES, APP_RESPONSE_ENVELOPE_BYTES
    from integrations.company_dialogue_principal_host_contract import encode_json_frame, validate_response
    from integrations.mastermind_executive_app.gateway import CeoIngressClient, TRANSPORT_SENT_OK
    from control_plane.executive_service import _canonical_json

    async def scenario():
        result = principal_result_envelope("ruling", data={"fixture": ""})
        padding = inner_size - len(_canonical_json(result))
        result["data"]["fixture"] = ("原" * (padding // 3) + "x" * (padding % 3)
                                     if unicode_payload else "x" * padding)
        assert len(_canonical_json(result)) == inner_size
        assert len(_canonical_json({"ok": True, "result": result})) == inner_size + APP_RESPONSE_ENVELOPE_BYTES
        assert MAX_APP_RESPONSE_BYTES == MAX_RESPONSE_BYTES + APP_RESPONSE_ENVELOPE_BYTES
        class Provider:
            async def ruling(self, raw, *, receiving_request_guard):
                decode_app_request(raw)
                receiving_request_guard()
                return validate_response(encode_json_frame(result, limit=MAX_RESPONSE_BYTES), tool="ruling")
        binding = CeoIngressAppBinding(peer_uid=os.geteuid(), armed=False, grounding_provider=_FakeGrounding(),
            principal_admission_armed=True, principal_admission_guard=lambda _: None,
            principal_dialogue_provider_factory=lambda _: Provider())
        service = ExecutiveControlService(_config(tmp_path, socket_root=short_socket_root),
            supervisor_factory=lambda _: _FakeSupervisor(),
            ceo_ingress_socket_path=short_socket_root / "ceo.sock", ceo_ingress_peer_uid=os.geteuid()+1000,
            ceo_ingress_grounding_provider=_FakeGrounding(), ceo_ingress_armed=False,
            ceo_ingress_app_binding=binding)
        await service.start()
        try:
            response = await CeoIngressClient().send_frame(service.ceo_ingress_socket_path, json.loads(encoded()))
            assert response.transport == TRANSPORT_SENT_OK
            assert response.ok is (inner_size <= MAX_RESPONSE_BYTES)
            if response.ok:
                assert response.result == result
            else:
                assert response.result is None
        finally:
            await service.close()
    asyncio.run(scenario())
