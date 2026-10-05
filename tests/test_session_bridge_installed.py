"""Private installed Session Bridge transport over the existing CeoIngress App peer."""
from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path

import pytest

from integrations.business_mcp_auth.contracts import VerifiedPrincipal
from integrations.mastermind_executive_app.gateway import (
    CeoIngressResponse,
    TRANSPORT_NOT_SENT,
    TRANSPORT_SENT_OK,
    TRANSPORT_SENT_UNKNOWN,
)
from integrations.session_bridge.schemas import BridgeError
from integrations.session_bridge.installed import private_ingress_owner

ISSUER = "https://auth.example.test/"
PRINCIPAL = VerifiedPrincipal(
    policy_id="session-profile",
    issuer=ISSUER,
    issuer_digest=hashlib.sha256(ISSUER.encode()).hexdigest(),
    resource="https://exec.example.test/mcp",
    subject_digest="1" * 64,
    client_ref="2" * 64,
    scopes=("mastermind.executive.read", "mastermind.executive.intent.submit"),
    issued_at=1791000000,
    expires_at=1791003600,
    jti_digest="3" * 64,
)


class FakeCeoIngress:
    def __init__(self, response):
        self.response = response
        self.calls = []

    async def send_frame(self, socket_path, frame):
        self.calls.append((str(socket_path), frame))
        return self.response


def ok_result(tool, data):
    from integrations.session_bridge.installed import PRIVATE_RESULT_SCHEMA
    return CeoIngressResponse(
        transport=TRANSPORT_SENT_OK,
        ok=True,
        result={
            "schema": PRIVATE_RESULT_SCHEMA,
            "tool": tool,
            "ok": True,
            "data": data,
            "error": None,
        },
    )


def client(response):
    from integrations.session_bridge.installed import InstalledSessionBridgeClient
    fake = FakeCeoIngress(response)
    return InstalledSessionBridgeClient(
        "/private/tmp/ceo-ingress.sock",
        client=fake,
    ), fake


def test_installed_client_sends_one_closed_principal_bound_targets_frame():
    from integrations.session_bridge.installed import PRIVATE_SCHEMA
    c, fake = client(ok_result("session_targets", [{"target_ref": "codex:bind-1"}]))
    result = asyncio.run(c.targets(PRINCIPAL, "codex"))
    assert result == [{"target_ref": "codex:bind-1"}]
    assert len(fake.calls) == 1
    path, frame = fake.calls[0]
    assert path == "/private/tmp/ceo-ingress.sock"
    assert frame["schema"] == PRIVATE_SCHEMA
    assert frame["tool"] == "session_targets"
    assert frame["arguments"] == {"kind": "codex"}
    assert set(frame["principal"]) == {
        "policy_id", "issuer", "issuer_digest", "resource", "subject_digest",
        "client_ref", "scopes", "issued_at", "expires_at", "jti_digest",
    }
    rendered = repr(frame)
    assert "Bearer " not in rendered
    assert "authorization" not in rendered.lower()


@pytest.mark.parametrize("tool", ["session_send", "session_summon"])
def test_sent_unknown_modifying_frame_is_effect_unknown_without_retry(tool):
    c, fake = client(CeoIngressResponse(transport=TRANSPORT_SENT_UNKNOWN))
    args = ({
        "target_ref": "codex:bind-1",
        "instruction": "Continue.",
        "stop_condition": "Stop after one result.",
        "operation_key": "installed-effect-001",
    } if tool == "session_send" else {
        "objective": "Inspect one bounded issue.",
        "execution_profile": "research_only",
        "operation_key": "installed-effect-002",

                                         "department": "executive-infrastructure",
                                         "priority": 0,
                                         "workstream": "WS:DOT-SESSION-BRIDGE",
                                         "attempt_limit": 2,
                                         "allowed_write_paths": [],
                                         "validation": {}
                                     })
    call = c.send if tool == "session_send" else c.summon
    with pytest.raises(BridgeError) as error:
        asyncio.run(call(PRINCIPAL, args))
    assert error.value.code == "effect_unknown"
    assert len(fake.calls) == 1


def test_not_sent_modifying_frame_is_bounded_availability_error():
    c, fake = client(CeoIngressResponse(transport=TRANSPORT_NOT_SENT))
    with pytest.raises(BridgeError) as error:
        asyncio.run(c.send(PRINCIPAL, {
            "target_ref": "codex:bind-1",
            "instruction": "Continue.",
            "stop_condition": "Stop after one result.",
            "operation_key": "installed-no-effect-001",
        }))
    assert error.value.code == "backend_unavailable"
    assert len(fake.calls) == 1


class Owners:
    def __init__(self):
        self.calls = []

    def project(self, principal, kind):
        self.calls.append(("targets", principal, kind))
        return [{"target_ref": "claude:exact-1", "kind": "claude"}]

    def send(self, principal, args):
        self.calls.append(("send", principal, dict(args)))
        return {"reply_committed": True, "attention": {"state": "ATTENTION_ACCEPTED"}}

    def summon(self, principal, args):
        self.calls.append(("summon", principal, dict(args)))
        return {"admission_requested": True, "operation_key": args["operation_key"]}


def principal_frame():
    from integrations.session_bridge.installed import principal_frame
    return principal_frame(PRINCIPAL)


def test_private_provider_validates_and_passes_neutral_principal_to_owner():
    from control_plane.principal_projection import NeutralPrincipalProjection
    from integrations.session_bridge.installed import (
        InstalledSessionBridgeProvider, PRIVATE_RESULT_SCHEMA, PRIVATE_SCHEMA,
    )
    owners = Owners()
    provider = InstalledSessionBridgeProvider(
        target_projector=owners.project,
        reply_handler=owners.send,
        summon_handler=owners.summon,
    )
    frame = {
        "schema": PRIVATE_SCHEMA,
        "tool": "session_targets",
        "principal": principal_frame(),
        "arguments": {"kind": "claude"},
    }
    result = asyncio.run(provider.handle_frame(frame))
    assert result["schema"] == PRIVATE_RESULT_SCHEMA
    assert result["ok"] is True
    assert result["data"] == [{"target_ref": "claude:exact-1", "kind": "claude"}]
    assert len(owners.calls) == 1
    assert type(owners.calls[0][1]) is NeutralPrincipalProjection


def test_private_provider_modifying_exception_is_effect_unknown_once():
    from integrations.session_bridge.installed import InstalledSessionBridgeProvider, PRIVATE_SCHEMA
    calls = []
    def possible_effect(principal, args):
        calls.append((principal, dict(args)))
        raise RuntimeError("private backend detail")
    provider = InstalledSessionBridgeProvider(
        target_projector=lambda *_: [],
        reply_handler=possible_effect,
        summon_handler=lambda *_: None,
    )
    result = asyncio.run(provider.handle_frame({
        "schema": PRIVATE_SCHEMA,
        "tool": "session_send",
        "principal": principal_frame(),
        "arguments": {
            "target_ref": "codex:bind-1",
            "instruction": "Continue.",
            "stop_condition": "Stop.",
            "operation_key": "private-owner-effect-001",
        },
    }))
    assert result["ok"] is False
    assert result["error"]["code"] == "effect_unknown"
    assert len(calls) == 1
    assert "private backend detail" not in repr(result)


def test_private_frame_rejects_model_supplied_identity_or_transport_fields():
    from integrations.session_bridge.installed import InstalledSessionBridgeProvider, PRIVATE_SCHEMA
    provider = InstalledSessionBridgeProvider(
        target_projector=lambda *_: [], reply_handler=lambda *_: {}, summon_handler=lambda *_: {},
    )
    frame = {
        "schema": PRIVATE_SCHEMA,
        "tool": "session_targets",
        "principal": principal_frame(),
        "arguments": {},
        "socket_path": "/tmp/forged.sock",
    }
    with pytest.raises(BridgeError) as error:
        asyncio.run(provider.handle_frame(frame))
    assert error.value.code == "invalid_input"

def test_existing_control_service_app_peer_routes_private_session_frame(tmp_path, short_socket_root, monkeypatch):
    import dataclasses
    import json
    from integrations.executive_mcp.web_ceo_sessions import WEB_CEO_SESSIONS_PROFILE
    from tests.test_executive_ceo_ingress import _raw_ceo_request
    from tests.test_executive_mcp_installed_fabric_composition import factory_service
    from integrations.session_bridge.installed import (
        InstalledSessionBridgeProvider, PRIVATE_SCHEMA,
    )

    async def run():
        async with factory_service(
            tmp_path, short_socket_root, monkeypatch, profile=WEB_CEO_SESSIONS_PROFILE
        ) as (service, raw, _):
            owners = Owners()
            provider = InstalledSessionBridgeProvider(
                target_projector=owners.project,
                reply_handler=owners.send,
                summon_handler=owners.summon,
            )
            binding = service._ceo_ingress_app_binding
            service._ceo_ingress_app_binding = dataclasses.replace(
                binding,
                session_bridge_provider_factory=lambda _runtime: private_ingress_owner(provider),
            )
            await service.start()
            response = await _raw_ceo_request(
                Path(raw["ceo_ingress_socket_path"]),
                (json.dumps({
                    "schema": PRIVATE_SCHEMA,
                    "tool": "session_targets",
                    "principal": principal_frame(),
                    "arguments": {"kind": "claude"},
                }, sort_keys=True) + "\n").encode(),
            )
            assert response["ok"] is True
            assert response["result"]["ok"] is True
            assert response["result"]["data"] == [
                {"target_ref": "claude:exact-1", "kind": "claude"}
            ]
            assert [item[0] for item in owners.calls] == ["targets"]

    asyncio.run(run())


def test_existing_control_service_refuses_session_frame_without_owner(tmp_path, short_socket_root, monkeypatch):
    import json
    import dataclasses
    from integrations.executive_mcp.web_ceo_sessions import WEB_CEO_SESSIONS_PROFILE
    from tests.test_executive_ceo_ingress import _raw_ceo_request
    from tests.test_executive_mcp_installed_fabric_composition import factory_service
    from integrations.session_bridge.installed import PRIVATE_SCHEMA

    async def run():
        async with factory_service(
            tmp_path, short_socket_root, monkeypatch, profile=WEB_CEO_SESSIONS_PROFILE
        ) as (service, raw, _):
            service._ceo_ingress_app_binding = dataclasses.replace(
                service._ceo_ingress_app_binding, session_bridge_provider_factory=None)
            await service.start()
            response = await _raw_ceo_request(
                Path(raw["ceo_ingress_socket_path"]),
                (json.dumps({
                    "schema": PRIVATE_SCHEMA,
                    "tool": "session_targets",
                    "principal": principal_frame(),
                    "arguments": {},
                }, sort_keys=True) + "\n").encode(),
            )
            assert response["ok"] is False
            assert response["error"]["code"] == "ingress_unavailable"

    asyncio.run(run())


@pytest.mark.parametrize("tool,arguments", [
    ("session_targets", {}),
    ("session_send", {"target_ref": "fabric_attempt:exact", "instruction": "Continue.",
                      "stop_condition": "Return evidence.", "operation_key": "continue-001"}),
    ("session_summon", {"objective": "Read existing source.", "execution_profile": "research_only",
                        "operation_key": "summon-001",
                           "department": "executive-infrastructure",
                           "priority": 0,
                           "workstream": "WS:DOT-SESSION-BRIDGE",
                           "attempt_limit": 2,
                           "allowed_write_paths": [],
                           "validation": {}
                       }),
])
def test_disarmed_session_route_enters_no_factory_or_owner(tmp_path, short_socket_root, monkeypatch, tool, arguments):
    import dataclasses
    import json
    from integrations.executive_mcp.web_ceo_sessions import WEB_CEO_SESSIONS_PROFILE
    from tests.test_executive_ceo_ingress import _raw_ceo_request
    from tests.test_executive_mcp_installed_fabric_composition import factory_service
    from integrations.session_bridge.installed import PRIVATE_SCHEMA

    async def run():
        async with factory_service(
            tmp_path, short_socket_root, monkeypatch, profile=WEB_CEO_SESSIONS_PROFILE
        ) as (service, raw, _):
            calls = []
            def forbidden_factory(runtime):
                calls.append(runtime)
                raise AssertionError("disarmed route entered factory")
            service._ceo_ingress_app_binding = dataclasses.replace(
                service._ceo_ingress_app_binding, armed=False,
                session_bridge_provider_factory=forbidden_factory,
            )
            await service.start()
            response = await _raw_ceo_request(Path(raw["ceo_ingress_socket_path"]), (
                json.dumps({"schema": PRIVATE_SCHEMA, "tool": tool, "principal": principal_frame(),
                            "arguments": arguments}) + "\n").encode())
            assert response["error"]["code"] == "ingress_unavailable"
            assert calls == []
    asyncio.run(run())


@pytest.mark.parametrize("fault", ["binding_rotation", "closing", "response_write"])
def test_session_effect_cannot_be_reclassified_as_invalid_input(tmp_path, short_socket_root, monkeypatch, fault):
    import dataclasses
    import json
    from integrations.executive_mcp.web_ceo_sessions import WEB_CEO_SESSIONS_PROFILE
    from tests.test_executive_ceo_ingress import _raw_ceo_request
    from tests.test_executive_mcp_installed_fabric_composition import factory_service
    from integrations.session_bridge.installed import InstalledSessionBridgeProvider, PRIVATE_SCHEMA

    async def run():
        async with factory_service(
            tmp_path, short_socket_root, monkeypatch, profile=WEB_CEO_SESSIONS_PROFILE
        ) as (service, raw, _):
            calls, writes = [], []
            def send(principal, arguments):
                calls.append(arguments)
                if fault == "binding_rotation":
                    service._ceo_ingress_app_binding = dataclasses.replace(service._ceo_ingress_app_binding)
                elif fault == "closing":
                    service._closing = True
                return {"reply_committed": True}
            provider = InstalledSessionBridgeProvider(
                target_projector=lambda *_: [], reply_handler=send, summon_handler=send)
            service._ceo_ingress_app_binding = dataclasses.replace(
                service._ceo_ingress_app_binding, session_bridge_provider_factory=lambda _: private_ingress_owner(provider))
            original_send = service._send_ceo_ingress_response
            async def record_response(writer, payload, **kwargs):
                writes.append(payload)
                if fault == "response_write":
                    raise ConnectionResetError("reply lost after owner effect")
                return await original_send(writer, payload, **kwargs)
            monkeypatch.setattr(service, "_send_ceo_ingress_response", record_response)
            await service.start()
            payload = (json.dumps({"schema": PRIVATE_SCHEMA, "tool": "session_send",
                "principal": principal_frame(), "arguments": {"target_ref": "fabric_attempt:exact",
                "instruction": "Continue.", "stop_condition": "Return evidence.",
                "operation_key": "continue-001"}}) + "\n").encode()
            try:
                response = await _raw_ceo_request(Path(raw["ceo_ingress_socket_path"]), payload)
            except (json.JSONDecodeError, ConnectionError):
                assert fault == "response_write"
            else:
                if fault == "response_write":
                    assert response is None
                else:
                    assert response["result"]["error"]["code"] == "effect_unknown"
            finally:
                service._closing = False
            assert len(calls) == 1
            assert len(writes) == 1
            assert writes[0]["ok"] is True
    asyncio.run(run())


def test_real_installed_factory_projects_runtime_wake_and_binds_continuation(tmp_path, short_socket_root, monkeypatch):
    import json
    from integrations.executive_mcp.web_ceo_sessions import WEB_CEO_SESSIONS_PROFILE
    from tests.test_executive_ceo_ingress import _raw_ceo_request
    from tests.test_executive_mcp_installed_fabric_composition import factory_service
    from tests.test_company_consultation_target_resolution import _seed
    from integrations.session_bridge.installed import PRIVATE_SCHEMA
    from integrations.session_bridge.runtime_owner import RuntimeFabricTargetProjector, RuntimeExecutiveReplyBindingResolver

    # Real Runtime registries, immutable root source, process/harness generations,
    # and Wake ledger; only the pre-existing synthetic worker/provider fixture.
    seed = _seed(tmp_path, monkeypatch, physical=True, root_source=True)

    from types import SimpleNamespace
    from integrations.session_bridge import runtime_return
    monkeypatch.setattr(runtime_return, "time", SimpleNamespace(time=lambda: 1791000100))

    async def run():
        async with factory_service(
            tmp_path, short_socket_root, monkeypatch, profile=WEB_CEO_SESSIONS_PROFILE
        ) as (service, raw, _):
            assert callable(service._ceo_ingress_app_binding.session_bridge_provider_factory)
            await service.start()
            async def call(tool, arguments):
                return await _raw_ceo_request(Path(raw["ceo_ingress_socket_path"]), (
                    json.dumps({"schema": PRIVATE_SCHEMA, "tool": tool, "principal": principal_frame(),
                                "arguments": arguments}) + "\n").encode())
            response = await call("session_targets", {})
            assert response["ok"] is True
            assert response["result"]["ok"] is True
            targets = response["result"]["data"]
            assert len(targets) == 2
            p = RuntimeFabricTargetProjector(service._require_runtime())
            resolver = RuntimeExecutiveReplyBindingResolver(p)
            for target in targets:
                assert target["kind"] == "fabric_attempt"
                binding = resolver.resolve(target["target_ref"])
                assert binding.continuation_operation_key == target["continuation_operation_key"]
                assert binding.current_writer["worker_id"] in {seed.a[2], seed.b[2]}
                assert binding.reply_to_message_key in {"asd-target-a-0001", "asd-target-b-0001"}
            for unsupported in ("codex", "claude"):
                result = await call("session_targets", {"kind": unsupported})
                assert result["result"]["data"] == []
            result = await call("session_send", {
                "target_ref": targets[1]["target_ref"],
                "operation_key": targets[0]["continuation_operation_key"],
                "instruction": "Inspect current source.", "stop_condition": "Return one finding."})
            # Refuses before touching the canonical production Dialogue socket.
            assert result["result"]["error"]["code"] == "operation_carrier_conflict"
            result = await call("session_summon", {
                "objective": "Inspect current source.", "execution_profile": "research_only",
                "operation_key": "not-a-host-commission",
                                                      "department": "executive-infrastructure",
                                                      "priority": 0,
                                                      "workstream": "WS:DOT-SESSION-BRIDGE",
                                                      "attempt_limit": 2,
                                                      "allowed_write_paths": [],
                                                      "validation": {}
                                                  })
            assert result["result"]["error"]["code"] == "grounding_unavailable"

    asyncio.run(run())


@pytest.mark.parametrize("fault,code", [
    ("unwrapped", "ingress_unavailable"),
    ("unknown_tool", "invalid_input"),
    ("invalid_arguments", "invalid_input"),
    ("validator_failure", "ingress_unavailable"),
    ("factory_binding_rotation", "ingress_unavailable"),
    ("validator_binding_rotation", "ingress_unavailable"),
])
def test_neutral_ingress_boundary_refuses_before_effect(
    tmp_path, short_socket_root, monkeypatch, fault, code
):
    import dataclasses
    import json
    from common.session_bridge_private_contract import SessionBridgeIngressOwner
    from integrations.executive_mcp.web_ceo_sessions import WEB_CEO_SESSIONS_PROFILE
    from tests.test_executive_ceo_ingress import _raw_ceo_request
    from tests.test_executive_mcp_installed_fabric_composition import factory_service
    from integrations.session_bridge.installed import (
        InstalledSessionBridgeProvider, PRIVATE_SCHEMA, validate_private_frame,
    )

    async def run():
        async with factory_service(
            tmp_path, short_socket_root, monkeypatch, profile=WEB_CEO_SESSIONS_PROFILE
        ) as (service, raw, _):
            calls = []
            def send(*args):
                calls.append(args)
                return {"committed": True}
            provider = InstalledSessionBridgeProvider(
                target_projector=lambda *_: [], reply_handler=send, summon_handler=send)
            def rotate():
                service._ceo_ingress_app_binding = dataclasses.replace(
                    service._ceo_ingress_app_binding)
            def validator(frame):
                if fault == "unknown_tool":
                    return "session_execute_arbitrary"
                if fault == "validator_failure":
                    raise ValueError("invalid owner configuration")
                if fault == "validator_binding_rotation":
                    rotate()
                return validate_private_frame(frame)[0]
            def factory(_runtime):
                if fault == "unwrapped":
                    return provider
                if fault == "factory_binding_rotation":
                    rotate()
                return SessionBridgeIngressOwner(validator, provider.handle_frame)
            service._ceo_ingress_app_binding = dataclasses.replace(
                service._ceo_ingress_app_binding, session_bridge_provider_factory=factory)
            await service.start()
            arguments = {"target_ref": "fabric_attempt:exact", "instruction": "Continue.",
                         "stop_condition": "Return.", "operation_key": "boundary-test"}
            if fault == "invalid_arguments":
                arguments["provider"] = "unreviewed"
            response = await _raw_ceo_request(Path(raw["ceo_ingress_socket_path"]), (
                json.dumps({"schema": PRIVATE_SCHEMA, "tool": "session_send",
                            "principal": principal_frame(), "arguments": arguments}) + "\n").encode())
            assert response["ok"] is False
            assert response["error"]["code"] == code
            assert calls == []
    asyncio.run(run())


@pytest.mark.parametrize("foreign", [False, True])
def test_public_read_uses_installed_private_projection_and_original_principal(foreign):
    import dataclasses
    from control_plane.principal_projection import NeutralPrincipalProjection
    from integrations.session_bridge.installed import InstalledSessionBridgeClient, InstalledSessionBridgeProvider
    from integrations.session_bridge.return_tools import NativeReplyReadTool
    from tests.test_session_bridge_native_read import Resolver, reader, PRINCIPAL as READ_PRINCIPAL, READ_REF
    resolver = Resolver()
    read_owner = reader(resolver, projected_principal=True)
    def forbidden(*args):
        raise AssertionError("Read must not use a modifying owner")
    provider = InstalledSessionBridgeProvider(target_projector=forbidden,
        reply_handler=forbidden, summon_handler=forbidden, reply_read_handler=read_owner)
    class Ingress(FakeCeoIngress):
        async def send_frame(self, socket_path, frame):
            self.calls.append((str(socket_path), frame))
            return CeoIngressResponse(transport=TRANSPORT_SENT_OK, ok=True,
                result=await provider.handle_frame(frame))
    fake = Ingress(None)
    tool = NativeReplyReadTool(InstalledSessionBridgeClient(
        "/private/tmp/ceo-ingress.sock", client=fake))
    principal = (dataclasses.replace(READ_PRINCIPAL, subject_digest="9" * 64)
                 if foreign else READ_PRINCIPAL)
    result = asyncio.run(tool.handle(principal, "session_reply_read", {"read_ref": READ_REF}))
    assert result["ok"] is (not foreign)
    if foreign:
        assert result["error"]["code"] == "reply_unavailable"
        assert not resolver.service.calls
    else:
        assert result["data"]["parent_consumed"] is False
        assert result["data"]["reply_committed"] is True
        assert [c["operation"] for c in resolver.service.calls] == ["read_thread"]
    assert resolver.calls and all(type(p) is NeutralPrincipalProjection for p, _ in resolver.calls)
    assert len(fake.calls) == 1
    frame = fake.calls[0][1]
    assert set(frame) == {"schema", "tool", "principal", "arguments"}
    assert "Bearer " not in repr(frame) and "authorization" not in repr(frame).lower()


def test_projected_reader_rejects_direct_verified_principal_and_public_tool_rejects_projection():
    from integrations.business_mcp_auth.principal_projection import principal_projection
    from integrations.session_bridge.return_tools import NativeReplyReadTool
    from tests.test_session_bridge_native_read import Resolver, reader, PRINCIPAL as READ_PRINCIPAL, READ_REF
    resolver = Resolver()
    projected = reader(resolver, projected_principal=True)
    with pytest.raises(BridgeError):
        asyncio.run(projected(READ_PRINCIPAL, {"read_ref": READ_REF}))
    result = asyncio.run(NativeReplyReadTool(reader(resolver)).handle(
        principal_projection(READ_PRINCIPAL), "session_reply_read", {"read_ref": READ_REF}))
    assert result["error"]["code"] == "reply_unavailable"
    assert not resolver.calls and not resolver.service.calls
