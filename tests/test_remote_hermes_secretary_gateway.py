"""Real mTLS profile routing with a synthetic native forwarder, not host proof."""
from __future__ import annotations
import asyncio
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from control_plane.remote_worker_broker_client import RemoteWorkerBrokerClient
from control_plane.remote_worker_transport import (
    BrokerTransportBinding, TransportEffect, TransportError, build_secretary_request,
)
from ops.executive_os.remote_worker_gateway import RemoteWorkerGateway
from ops.executive_os.remote_worker_gateway_config import (
    HermesRoleMetadataReadBinding, HermesSecretaryConversationBinding,
    HermesSecretaryGatewayConfig, SECRETARY_GATEWAY_CONFIG_SCHEMA,
    SECRETARY_GATEWAY_PROFILE, SECRETARY_CREDENTIAL_PATH,
)
from ops.executive_os.remote_worker_gateway_service import remote_worker_gateway_config_digest
from tests.test_remote_worker_gateway import (
    _gateway_fixture, _close_gateway, _cert_sha256, _openssl_available,
    _exchange, _client_context,
)
from tests.test_remote_hermes_secretary_transport import _submit, _native_result, SESSION, ROOT_ID

pytestmark = [pytest.mark.anyio, pytest.mark.skipif(not _openssl_available(), reason="openssl unavailable")]
SHA = "a" * 40


@pytest.fixture
def anyio_backend():
    return "asyncio"


async def secretary_gateway(tmp_path):
    fixture = await _gateway_fixture(tmp_path, server_san="DNS:localhost,IP:127.0.0.1")
    fixture.server.close()
    await fixture.server.wait_closed()
    old = fixture.config
    config = HermesSecretaryGatewayConfig(
        schema=SECRETARY_GATEWAY_CONFIG_SCHEMA, profile=SECRETARY_GATEWAY_PROFILE,
        host_ref=old.host_ref, listen_host=old.listen_host, listen_port=0,
        certificate_path=old.certificate_path, key_path=old.key_path, ca_path=old.ca_path,
        expected_control_fingerprint=old.expected_control_fingerprint,
        hermes_role_metadata_read=HermesRoleMetadataReadBinding(SHA),
        hermes_secretary_conversation=HermesSecretaryConversationBinding(
            SHA, ROOT_ID, SESSION, 8765, SECRETARY_CREDENTIAL_PATH),
    )
    fixture.config = config
    fixture.gateway = RemoteWorkerGateway(config)
    fixture.gateway._secretary_host_binding_sha256 = remote_worker_gateway_config_digest(config)
    fixture.gateway._secretary_forwarder = SimpleNamespace(request=AsyncMock(
        return_value=_native_result("ADMITTED", admission={"admission_id": "admission-0001"})))
    fixture.gateway.broker_call = AsyncMock(side_effect=AssertionError("Secretary cannot call Worker"))
    fixture.server = await fixture.gateway.start_server()
    fixture.endpoint = fixture.server.sockets[0].getsockname()[:2]
    binding = BrokerTransportBinding(
        endpoint=fixture.endpoint, ca_path=config.ca_path,
        client_cert_path=fixture.control_cert, client_key_path=fixture.control_key,
        expected_server_fingerprint=_cert_sha256(config.certificate_path), timeout_seconds=2)
    client = RemoteWorkerBrokerClient.for_secretary_conversation(
        binding, host_ref=config.host_ref, root_id=ROOT_ID, session_id=SESSION,
        expected_host_binding_sha256=fixture.gateway._secretary_host_binding_sha256,
        expected_implementation_sha=SHA)
    return fixture, client


async def test_real_mtls_secretary_dispatch_preserves_native_admission(tmp_path):
    fixture, client = await secretary_gateway(tmp_path)
    committed = []
    try:
        result = await client.request_secretary(_submit(), before_write=lambda *args: committed.append(args))
        assert result == _native_result("ADMITTED", admission={"admission_id": "admission-0001"})
        assert len(committed) == 1
        fixture.gateway._secretary_forwarder.request.assert_awaited_once()
        assert fixture.gateway._secretary_forwarder.request.call_args.args == (_submit(),)
        fixture.gateway.broker_call.assert_not_called()
        assert fixture.gateway._broker_client is None
    finally:
        await _close_gateway(fixture)


@pytest.mark.parametrize("change", ["root", "source", "config", "session"])
async def test_real_mtls_retargeting_refused_before_native_forwarding(tmp_path, change):
    fixture, client = await secretary_gateway(tmp_path)
    root, source, config = ROOT_ID, SHA, fixture.gateway._secretary_host_binding_sha256
    operation = {"operation": "observe", "session_id": SESSION}
    if change == "root": root += "-foreign"
    elif change == "source": source = "b" * 40
    elif change == "config": config = "c" * 64
    else: operation["session_id"] += "-foreign"
    request = build_secretary_request(fixture.config.host_ref, root, config, source, operation)
    context = _client_context(ca=fixture.config.ca_path, cert=fixture.control_cert, key=fixture.control_key)
    try:
        reply = await _exchange(fixture.endpoint, context, request)
        assert reply["outcome"] == "refused" and reply["result"] == {"code": "BINDING_CHANGED"}
        fixture.gateway._secretary_forwarder.request.assert_not_called()
        fixture.gateway.broker_call.assert_not_called()
    finally:
        await _close_gateway(fixture)


@pytest.mark.parametrize("native_effect", [TransportEffect.NO_EFFECT, TransportEffect.EFFECT_UNKNOWN])
async def test_real_mtls_transport_preserves_known_and_unknown_effects(tmp_path, native_effect):
    fixture, client = await secretary_gateway(tmp_path)
    fixture.gateway._secretary_forwarder.request.side_effect = TransportError("fixture", native_effect)
    try:
        with pytest.raises(TransportError) as failure:
            await client.request_secretary(_submit(), before_write=lambda *_: None)
        assert failure.value.classification is native_effect
        fixture.gateway._secretary_forwarder.request.assert_awaited_once()
    finally:
        await _close_gateway(fixture)


async def test_real_mtls_native_unknown_is_returned_without_upgrading_it(tmp_path):
    fixture, client = await secretary_gateway(tmp_path)
    expected = _native_result("EFFECT_UNKNOWN", reason="ORIGINAL_ADMISSION_UNRESOLVED")
    fixture.gateway._secretary_forwarder.request.return_value = expected
    try:
        assert await client.request_secretary(_submit(), before_write=lambda *_: None) == expected
    finally:
        await _close_gateway(fixture)


async def test_worker_profile_refuses_secretary_before_broker_grammar(tmp_path):
    fixture = await _gateway_fixture(tmp_path)
    fixture.gateway.broker_call = AsyncMock(side_effect=AssertionError("no Worker delegation"))
    request = build_secretary_request(fixture.config.host_ref, ROOT_ID, "b" * 64, SHA,
                                     {"operation": "observe", "session_id": SESSION})
    context = _client_context(ca=fixture.config.ca_path, cert=fixture.control_cert, key=fixture.control_key)
    try:
        response = await _exchange(fixture.endpoint, context, request)
        assert response["outcome"] == "refused"
        assert response["result"] == {"code": "PROFILE_UNAVAILABLE"}
        fixture.gateway.broker_call.assert_not_called()
    finally:
        await _close_gateway(fixture)
