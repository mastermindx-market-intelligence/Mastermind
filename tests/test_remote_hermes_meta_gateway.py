"""Dual role routing over one real disposable mTLS listener; no host admission."""
from __future__ import annotations
import asyncio
import copy
import dataclasses
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest

from control_plane.remote_worker_broker_client import RemoteWorkerBrokerClient
from control_plane.remote_worker_transport import BrokerTransportBinding, TransportEffect, TransportError
from ops.executive_os import remote_worker_gateway_config as config_module
from ops.executive_os import remote_worker_gateway_service as service
from ops.executive_os import hermes_secretary_forwarder as forwarding
from ops.executive_os.remote_worker_gateway import RemoteWorkerGateway
from tests.test_remote_hermes_secretary_gateway import secretary_gateway, anyio_backend, SHA
from tests.test_remote_hermes_secretary_transport import _submit, SESSION, ROOT_ID
from tests.test_remote_worker_gateway import _close_gateway, _cert_sha256, _openssl_available

META_SESSION = SESSION + "-meta"
META_ROOT = ROOT_ID + "-meta"
META_NATIVE = "mastermind.hermes_meta_native_control/v1"
SECRETARY_NATIVE = "mastermind.hermes_secretary_native_control/v1"


def dual_config(secretary):
    values = {field.name: getattr(secretary, field.name) for field in dataclasses.fields(secretary)}
    values.update(
        schema=config_module.CONVERSATION_GATEWAY_CONFIG_SCHEMA,
        profile=config_module.CONVERSATION_GATEWAY_PROFILE,
        hermes_meta_conversation=config_module.HermesMetaConversationBinding(
            SHA, META_ROOT, META_SESSION, 8765, config_module.META_CREDENTIAL_PATH))
    return config_module.HermesConversationGatewayConfig(**values)


async def dual_gateway(tmp_path):
    fixture, _ = await secretary_gateway(tmp_path)
    fixture.server.close()
    await fixture.server.wait_closed()
    secretary_forwarder = fixture.gateway._secretary_forwarder
    fixture.config = dual_config(fixture.config)
    fixture.gateway = RemoteWorkerGateway(fixture.config)
    pin = service.remote_worker_gateway_config_digest(fixture.config)
    fixture.gateway._secretary_host_binding_sha256 = pin
    fixture.gateway._meta_host_binding_sha256 = pin
    fixture.gateway._secretary_forwarder = secretary_forwarder
    fixture.gateway._meta_forwarder = SimpleNamespace(request=AsyncMock(return_value={
        "schema": META_NATIVE, "status": "ADMITTED", "admission": {"admission_id": "meta-admission-1"}}))
    fixture.gateway.broker_call = AsyncMock(side_effect=AssertionError("conversation called Worker"))
    fixture.server = await fixture.gateway.start_server()
    fixture.endpoint = fixture.server.sockets[0].getsockname()[:2]
    transport = BrokerTransportBinding(endpoint=fixture.endpoint, ca_path=fixture.config.ca_path,
        client_cert_path=fixture.control_cert, client_key_path=fixture.control_key,
        expected_server_fingerprint=_cert_sha256(fixture.config.certificate_path), timeout_seconds=2)
    clients = {}
    for family, root, session in (("secretary", ROOT_ID, SESSION), ("meta", META_ROOT, META_SESSION)):
        clients[family] = getattr(RemoteWorkerBrokerClient, "for_" + family + "_conversation")(
            transport, host_ref=fixture.config.host_ref, root_id=root, session_id=session,
            expected_host_binding_sha256=pin, expected_implementation_sha=SHA)
    return fixture, clients


@pytest.mark.anyio
@pytest.mark.skipif(not _openssl_available(), reason="openssl unavailable")
async def test_one_mtls_listener_routes_each_family_only_to_its_selected_forwarder(tmp_path):
    fixture, clients = await dual_gateway(tmp_path)
    try:
        for family, session, schema in (("secretary", SESSION, SECRETARY_NATIVE),
                                       ("meta", META_SESSION, META_NATIVE)):
            committed = []
            result = await getattr(clients[family], "request_" + family)(
                _submit(session), before_write=lambda *args: committed.append(args))
            assert result["schema"] == schema and result["status"] == "ADMITTED"
            assert len(committed) == 1
            forwarder = getattr(fixture.gateway, "_" + family + "_forwarder")
            forwarder.request.assert_awaited_once()
            assert forwarder.request.call_args.args == (_submit(session),)
        fixture.gateway.broker_call.assert_not_called()
        assert fixture.gateway._broker_client is None
    finally:
        await _close_gateway(fixture)


@pytest.mark.anyio
@pytest.mark.skipif(not _openssl_available(), reason="openssl unavailable")
@pytest.mark.parametrize("fault", ["root", "source", "config"])
async def test_meta_route_refuses_changed_binding_without_forwarding(tmp_path, fault):
    fixture, clients = await dual_gateway(tmp_path)
    try:
        original = clients["meta"]
        values = dict(host_ref=fixture.config.host_ref, root_id=META_ROOT, session_id=META_SESSION,
            expected_host_binding_sha256=fixture.gateway._meta_host_binding_sha256,
            expected_implementation_sha=SHA)
        if fault == "root":
            values["root_id"] = ROOT_ID
        elif fault == "source":
            values["expected_implementation_sha"] = "f" * 40
        else:
            values["expected_host_binding_sha256"] = "f" * 64
        # The transport endpoint stays fixed; only a closed identity pin differs.
        transport = BrokerTransportBinding(endpoint=fixture.endpoint, ca_path=fixture.config.ca_path,
            client_cert_path=fixture.control_cert, client_key_path=fixture.control_key,
            expected_server_fingerprint=_cert_sha256(fixture.config.certificate_path), timeout_seconds=2)
        client = RemoteWorkerBrokerClient.for_meta_conversation(transport, **values)
        with pytest.raises(TransportError) as caught:
            await client.request_meta(_submit(META_SESSION), before_write=lambda *_: None)
        assert caught.value.classification is TransportEffect.NO_EFFECT
        fixture.gateway._meta_forwarder.request.assert_not_called()
        fixture.gateway._secretary_forwarder.request.assert_not_called()
    finally:
        await _close_gateway(fixture)


@pytest.mark.anyio
@pytest.mark.skipif(not _openssl_available(), reason="openssl unavailable")
@pytest.mark.parametrize("family,session,foreign", [
    ("secretary", SESSION, META_NATIVE), ("meta", META_SESSION, SECRETARY_NATIVE)])
async def test_mtls_foreign_native_result_cannot_forge_no_effect(tmp_path, family, session, foreign):
    fixture, clients = await dual_gateway(tmp_path)
    try:
        forwarder = getattr(fixture.gateway, "_" + family + "_forwarder")
        forwarder.request.return_value = {"schema": foreign, "status": "ADMITTED"}
        with pytest.raises(TransportError) as caught:
            await getattr(clients[family], "request_" + family)(
                _submit(session), before_write=lambda *_: None)
        assert caught.value.classification is TransportEffect.EFFECT_UNKNOWN
        forwarder.request.assert_awaited_once()
    finally:
        await _close_gateway(fixture)


def inert_config(tmp_path):
    paths = {}
    for field in ("certificate_path", "key_path", "ca_path"):
        path = tmp_path / (field + ".fixture")
        path.write_bytes(b"inert noncredential fixture")
        paths[field] = path
    secretary = config_module.HermesSecretaryGatewayConfig(
        schema=config_module.SECRETARY_GATEWAY_CONFIG_SCHEMA,
        profile=config_module.SECRETARY_GATEWAY_PROFILE,
        host_ref="host-" + "a" * 64, listen_host="127.0.0.1", listen_port=9443,
        expected_control_fingerprint="b" * 64,
        hermes_role_metadata_read=config_module.HermesRoleMetadataReadBinding(SHA),
        hermes_secretary_conversation=config_module.HermesSecretaryConversationBinding(
            SHA, ROOT_ID, SESSION, 8765, config_module.SECRETARY_CREDENTIAL_PATH), **paths)
    return dual_config(secretary)


def test_dual_loader_qualifies_two_fixed_credentials_and_closed_family(tmp_path, monkeypatch):
    config = inert_config(tmp_path)
    document = json.loads(service._canonical_config(config))
    monkeypatch.setattr(service.sys, "platform", "linux")
    monkeypatch.setattr(service, "_trusted_observation_ancestors", lambda *_: None)
    monkeypatch.setattr(service, "_qualified_tls_paths", lambda *a, **k: {
        key: getattr(config, key) for key in ("certificate_path", "key_path", "ca_path")})
    observed = []
    monkeypatch.setattr(service, "_secure_regular_file", lambda path, **kw: observed.append((path, kw)))
    loaded = service.decode_conversation_gateway_config(json.dumps(document).encode(), expected_group_gid=1001)
    assert service._canonical_config(loaded) == service._canonical_config(config)
    assert [path for path, _ in observed] == [
        config_module.SECRETARY_CREDENTIAL_PATH, config_module.META_CREDENTIAL_PATH]
    assert all(kw["expected_owner_uid"] == 0 and kw["expected_group_gid"] == 1001
               and kw["read_bytes"] is False for _, kw in observed)
    foreign = copy.deepcopy(document)
    foreign["hermes_meta_conversation"] = dict(document["hermes_secretary_conversation"])
    with pytest.raises(service.RemoteWorkerGatewayServiceError):
        service.decode_conversation_gateway_config(json.dumps(foreign).encode(), expected_group_gid=1001)
    with pytest.raises(service.RemoteWorkerGatewayServiceError):
        service.decode_secretary_gateway_config(json.dumps(document).encode(), expected_group_gid=1001)


@pytest.mark.anyio
@pytest.mark.parametrize("alias", [False, True])
async def test_service_rejects_credential_alias_before_starting_listener(tmp_path, monkeypatch, alias):
    config = inert_config(tmp_path)
    monkeypatch.setattr(forwarding.HermesSecretaryForwarder, "_read_token",
                        lambda self: b"fixture-secretary-token")
    monkeypatch.setattr(forwarding.HermesMetaForwarder, "_read_token",
                        lambda self: b"fixture-secretary-token" if alias else b"fixture-meta-token")
    class Server:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        def close(self): pass
        async def wait_closed(self): pass
    gateway = SimpleNamespace(start_server=AsyncMock(return_value=Server()))
    shutdown = AsyncMock()
    if alias:
        with pytest.raises(service.RemoteWorkerGatewayServiceError, match="GATEWAY_CONVERSATION_CREDENTIAL_ALIAS"):
            await service.serve_remote_worker_gateway(config, gateway_factory=lambda _: gateway,
                                                     shutdown_waiter=shutdown)
        gateway.start_server.assert_not_called()
        shutdown.assert_not_called()
    else:
        await service.serve_remote_worker_gateway(config, gateway_factory=lambda _: gateway,
                                                 shutdown_waiter=shutdown)
        gateway.start_server.assert_awaited_once()
        assert gateway._secretary_host_binding_sha256 == gateway._meta_host_binding_sha256
        assert gateway._meta_forwarder._contract.role == "mmmeta"
        assert gateway._secretary_forwarder._contract.role == "mmsecretary"
