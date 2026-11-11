"""Protocol/custody fixtures only; no installed-role or provider admission proof."""
from __future__ import annotations

import asyncio
from contextlib import nullcontext
import dataclasses
import json
import os
from pathlib import Path
import socket
import stat
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from common import hermes_role_status_contract as wire
from common import workspace_byok_read_contract as workspace
from control_plane.remote_worker_transport import TransportEffect, TransportError
from integrations.hermes_runtime import gateway as role_gateway
from integrations.hermes_runtime import role_status_publisher as publisher
from integrations.hermes_runtime.constants import SECRETARY_ROLE_RESPONSE_SCHEMA, conversation_contract
from integrations.hermes_runtime.errors import RuntimeRefusal
from ops.executive_os import hermes_role_metadata_observer as observer
from ops.executive_os import hermes_secretary_forwarder as forwarding
from ops.executive_os.remote_worker_gateway_config import (
    HermesSecretaryConversationBinding, SECRETARY_CREDENTIAL_PATH,
    HermesMetaConversationBinding, META_CREDENTIAL_PATH,
)

SHA = "a" * 40
BOOT = "12345678-1234-1234-1234-123456789abc"
INVOCATION = "1" * 32
TOKEN = b"fixture-only-secretary-token"
LISTENER = {"host": "127.0.0.2", "port": 8765, "inode": "12345"}


@pytest.fixture
def anyio_backend():
    return "asyncio"


def status_document(role="mmsecretary"):
    return {
        "schema": wire.STATUS_SCHEMA_V3, "role": role, "host_boot_id": BOOT,
        "invocation_id": INVOCATION, "implementation_sha": SHA,
        "observed_at_ms": time.time_ns() // 1_000_000,
        "observed_monotonic_ms": time.monotonic_ns() // 1_000_000,
        "metadata": {"schema": wire.METADATA_SCHEMA, "role": role, "state": "ABSENT",
                     "reason": "INSTALL_MANIFEST_ABSENT", "source_binding": "NOT_ATTESTED",
                     "proof": workspace.proof()},
        "custody": {"pid": os.getpid(), "start_ticks": "1234", "uid": 1001, "gid": 1001,
                    "manifest_sha256": "b" * 64, "image_sha256": "c" * 64},
        "gateway_listener": dict(LISTENER, host=role_gateway.ROLE_PROXY_HOST[role]),
    }


@pytest.mark.parametrize("role", ["mmsecretary", "mmmeta"])
def test_listener_revision_is_closed_and_does_not_relax_v2(role):
    document = status_document(role)
    encoded = wire.encode_status_v3_text(document)
    assert wire.decode_status_custody_text(encoded, expected_role=role) == document
    with pytest.raises(wire.RoleStatusError):
        wire.validate_status_v2(document)
    with pytest.raises(wire.RoleStatusError):
        wire.decode_status_v2_text(encoded, expected_role=role)
    legacy = dict(document, schema=wire.STATUS_SCHEMA_V2)
    legacy.pop("gateway_listener")
    assert wire.validate_status_v2(legacy) == legacy
    for field, value in [("port", True), ("port", 80), ("host", "127.0.0.1"),
                         ("inode", "001"), ("inode", 12345), ("credential", "forbidden")]:
        malformed = dict(document, gateway_listener=dict(document["gateway_listener"], **{field: value}))
        with pytest.raises(wire.RoleStatusError):
            wire.validate_status_v3(malformed)
    sibling = "mmmeta" if role == "mmsecretary" else "mmsecretary"
    with pytest.raises(wire.RoleStatusError):
        wire.validate_status_v3(document, expected_role=sibling)
    with pytest.raises(wire.RoleStatusError):
        wire.validate_status_v3(dict(document, gateway_listener=dict(
            document["gateway_listener"], host=role_gateway.ROLE_PROXY_HOST[sibling])))


@pytest.mark.parametrize("role", ["mmsecretary", "mmmeta"])
def test_publisher_measures_listener_twice_and_refuses_drift(monkeypatch, tmp_path, role):
    document = status_document(role)
    witness = document["gateway_listener"]
    monkeypatch.setattr(publisher, "role_metadata", lambda *args: document["metadata"])
    custody = Mock(return_value=document["custody"])
    listener = Mock(side_effect=[dict(witness), dict(witness)])
    instance = publisher.RoleStatusPublisher(
        role, tmp_path, SHA, BOOT, INVOCATION, os.getpid(), "/tmp/fixture-notify",
        custody_observer=custody, listener_observer=listener,
    )
    result = wire.decode_status_v3_text(
        instance._custody_status_text(document["observed_at_ms"], document["observed_monotonic_ms"]),
        expected_role=role,
    )
    assert result == document and custody.call_count == listener.call_count == 2
    drifted = dataclasses.replace(instance, listener_observer=Mock(side_effect=[
        dict(witness), dict(witness, inode="12346"),
    ]))
    with pytest.raises(wire.RoleStatusError):
        drifted._custody_status_text(document["observed_at_ms"], document["observed_monotonic_ms"])
    assert dataclasses.replace(instance, listener_observer=None)._custody_status_text(
        document["observed_at_ms"], document["observed_monotonic_ms"]).startswith(wire.STATUS_PREFIX_V2)


@pytest.mark.parametrize("role", ["mmsecretary", "mmmeta"])
def test_gateway_witness_comes_from_own_exclusive_listening_socket(monkeypatch, role):
    instance = role_gateway.Gateway.__new__(role_gateway.Gateway)
    instance._process_pid = os.getpid()
    instance._conversation_contract = conversation_contract(role)
    witness = dict(LISTENER, host=role_gateway.ROLE_PROXY_HOST[role])
    instance._conversation_handler = lambda value: value
    instance.host, instance.port = witness["host"], witness["port"]
    options = {socket.SO_ACCEPTCONN: 1, socket.SO_REUSEADDR: 0, socket.SO_REUSEPORT: 0}
    channel = SimpleNamespace(family=socket.AF_INET, type=socket.SOCK_STREAM,
        fileno=lambda: 7, get_inheritable=lambda: False,
        getsockname=lambda: (instance.host, instance.port),
        getsockopt=lambda level, option: options[option])
    instance._httpd = SimpleNamespace(socket=channel)
    # Bind narrow stand-ins on the gateway module only. Patching the shared os
    # and sys modules would replace os.fstat and sys.platform for the whole
    # process, so unrelated teardown code reading os.fstat(...).st_size would
    # receive this fixture's SimpleNamespace instead of a real stat result.
    real_getpid, real_geteuid = os.getpid, os.geteuid
    fake_os = SimpleNamespace(
        getpid=real_getpid,
        geteuid=real_geteuid,
        fstat=lambda fd: SimpleNamespace(
            st_mode=stat.S_IFSOCK, st_uid=real_geteuid(), st_ino=12345))
    fake_sys = SimpleNamespace(platform="linux")
    monkeypatch.setattr(role_gateway, "os", fake_os)
    monkeypatch.setattr(role_gateway, "sys", fake_sys)
    assert instance.listener_custody() == witness
    for key, invalid in [(socket.SO_ACCEPTCONN, 0), (socket.SO_REUSEADDR, 1),
                         (socket.SO_REUSEPORT, 1)]:
        original = options[key]
        options[key] = invalid
        with pytest.raises(RuntimeRefusal, match="SECRETARY_LISTENER_UNQUALIFIED"):
            instance.listener_custody()
        options[key] = original
    instance.host = role_gateway.ROLE_PROXY_HOST["mmmeta" if role == "mmsecretary" else "mmsecretary"]
    with pytest.raises(RuntimeRefusal, match="LISTENER_UNQUALIFIED"):
        instance.listener_custody()


@pytest.mark.anyio
@pytest.mark.parametrize("failure", [None, "legacy", "inactive", "stale", "before-start",
                                      "wrong-port", "duplicate", "wildcard", "wrong-inode"])
@pytest.mark.parametrize("role", ["mmsecretary", "mmmeta"])
async def test_listener_qualification_requires_current_unique_main_socket(monkeypatch, failure, role):
    from integrations.hermes_runtime import isolation_probe
    document = status_document(role)
    listener = dict(LISTENER, host=role_gateway.ROLE_PROXY_HOST[role])
    row = {"role": role, "notify_access": "main", "active_state": "active",
           "sub_state": "running", "main_start_monotonic_us": 1, "status": document,
           "unit_properties": {"fixture": "source-owner-input"}}
    kernel = [{"host": listener["host"], "port": listener["port"], "inode": 12345}]
    if failure == "legacy":
        document["schema"] = wire.STATUS_SCHEMA_V2
        document.pop("gateway_listener")
    elif failure == "inactive": row["active_state"] = "inactive"
    elif failure == "stale": document["observed_monotonic_ms"] -= 31_000
    elif failure == "before-start": row["main_start_monotonic_us"] = (document["observed_monotonic_ms"] + 1) * 1000
    elif failure == "wrong-port": document["gateway_listener"]["port"] += 1
    elif failure == "duplicate": kernel.append(dict(kernel[0]))
    elif failure == "wildcard": kernel.append(dict(kernel[0], host="0.0.0.0"))
    elif failure == "wrong-inode": kernel[0]["inode"] += 1
    held = SimpleNamespace(check=Mock(), role_facts=Mock(return_value={"fixture_main_pid": 123}))
    monkeypatch.setattr(observer, "_boot_id", lambda: BOOT)
    query = AsyncMock(return_value=[row])
    monkeypatch.setattr(observer, "_query_fixed_pid1", query)
    monkeypatch.setattr(isolation_probe, "_kernel_listeners", lambda port: kernel)
    qualify = observer.qualify_secretary_listener if role == "mmsecretary" else observer.qualify_meta_listener
    call = qualify(held, gateway_port=8765,
                                               deadline=asyncio.get_running_loop().time() + 1)
    if failure is None:
        assert await call == {"facts": {"fixture_main_pid": 123}, "listener": listener}
        held.role_facts.assert_called_once_with(role, row["unit_properties"], BOOT)
    else:
        with pytest.raises(wire.RoleStatusError):
            await call
    query.assert_awaited_once_with(role=role)


class FixtureWriter:
    def __init__(self, role="mmsecretary"):
        self.host = role_gateway.ROLE_PROXY_HOST[role]
        self.writes = []
        self.transport = SimpleNamespace(abort=Mock())
        self.close = Mock()
        self.drain = AsyncMock()

    def write(self, payload):
        self.writes.append(payload)

    def get_extra_info(self, key):
        return {"peername": (self.host, LISTENER["port"]),
                "sockname": (self.host, 30000),
                "socket": SimpleNamespace(family=socket.AF_INET)}.get(key)


def setup_forwarder(monkeypatch, *, response=None, role="mmsecretary"):
    contract = conversation_contract(role)
    binding_type = HermesSecretaryConversationBinding if role == "mmsecretary" else HermesMetaConversationBinding
    forwarder_type = forwarding.HermesSecretaryForwarder if role == "mmsecretary" else forwarding.HermesMetaForwarder
    token_path = SECRETARY_CREDENTIAL_PATH if role == "mmsecretary" else META_CREDENTIAL_PATH
    binding = binding_type(
        SHA, "mission-1", "session-1", LISTENER["port"], token_path)
    monkeypatch.setattr(forwarder_type, "_read_token", lambda self: TOKEN)
    instance = forwarder_type(binding, expected_group_gid=1001, timeout_seconds=1)
    monkeypatch.setattr(forwarding, "_HeldRoleQualification", lambda sha: nullcontext(object()))
    qualification = AsyncMock(return_value={"stable": "same-native-main-listener"})
    monkeypatch.setattr(forwarding, "qualify_secretary_listener" if role == "mmsecretary"
                        else "qualify_meta_listener", qualification)
    body = json.dumps(response or {
        "schema": contract.response_schema, "implementation_sha": SHA,
        "result": {"outcome": "OBSERVED", "session_id": "session-1"},
    }).encode()
    reader = asyncio.StreamReader()
    reader.feed_data(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: "
                     + str(len(body)).encode() + b"\r\n\r\n" + body)
    reader.feed_eof()
    writer = FixtureWriter(role)
    connect = AsyncMock(return_value=(reader, writer))
    monkeypatch.setattr(forwarding.asyncio, "open_connection", connect)
    return instance, writer, qualification, connect


@pytest.mark.anyio
@pytest.mark.parametrize("role", ["mmsecretary", "mmmeta"])
async def test_forwarder_accepts_closed_response_and_writes_once(monkeypatch, role):
    instance, writer, qualification, connect = setup_forwarder(monkeypatch, role=role)
    result = await instance.request({"operation": "observe", "session_id": "session-1"},
                                    deadline=asyncio.get_running_loop().time() + 1)
    assert result == {"outcome": "OBSERVED", "session_id": "session-1"}
    assert len(writer.writes) == 1 and qualification.await_count == 3
    assert writer.writes[0].startswith(("POST " + conversation_contract(role).path + " HTTP/1.1\r\n").encode())
    assert connect.call_args.args[:2] == (role_gateway.ROLE_PROXY_HOST[role], LISTENER["port"])
    assert connect.call_args.kwargs["family"] == socket.AF_INET
    writer.transport.abort.assert_called_once()


@pytest.mark.anyio
@pytest.mark.parametrize("stage", ["before-connect", "before-write", "after-write"])
@pytest.mark.parametrize("role", ["mmsecretary", "mmmeta"])
async def test_listener_drift_preserves_the_actual_send_boundary(monkeypatch, stage, role):
    instance, writer, qualification, connect = setup_forwarder(monkeypatch, role=role)
    stable = {"stable": "same-native-main-listener"}
    if stage == "before-connect":
        qualification.side_effect = wire.RoleStatusError()
    elif stage == "before-write":
        qualification.side_effect = [stable, {"stable": "changed"}]
    else:
        qualification.side_effect = [stable, stable, {"stable": "changed"}]
    with pytest.raises(TransportError) as failure:
        await instance.request({"operation": "observe", "session_id": "session-1"},
                               deadline=asyncio.get_running_loop().time() + 1)
    assert failure.value.classification is (TransportEffect.EFFECT_UNKNOWN if stage == "after-write"
                                    else TransportEffect.NO_EFFECT)
    assert len(writer.writes) == (1 if stage == "after-write" else 0)
    if stage == "before-connect": connect.assert_not_called()


@pytest.mark.anyio
@pytest.mark.parametrize("role", ["mmsecretary", "mmmeta"])
async def test_prewrite_deadline_expiry_never_transmits(monkeypatch, role):
    instance, writer, qualification, connect = setup_forwarder(monkeypatch, role=role)
    calls = 0
    def current():
        nonlocal calls
        calls += 1
        if calls == 2:
            time.sleep(0.03)
    monkeypatch.setattr(instance, "_require_current_token", current)
    with pytest.raises(TransportError) as failure:
        await instance.request({"operation": "observe", "session_id": "session-1"},
                               deadline=asyncio.get_running_loop().time() + 0.02)
    assert failure.value.classification is TransportEffect.NO_EFFECT
    assert writer.writes == []


@pytest.mark.anyio
@pytest.mark.parametrize("fault", ["source", "token", "framing", "write-failure"])
@pytest.mark.parametrize("role", ["mmsecretary", "mmmeta"])
async def test_untrusted_response_or_write_failure_stays_unknown(monkeypatch, fault, role):
    response = {"schema": conversation_contract(role).response_schema, "implementation_sha": SHA,
                "result": {"outcome": "OBSERVED"}}
    if fault == "source": response["implementation_sha"] = "b" * 40
    elif fault == "token": response["result"]["answer"] = TOKEN.decode()
    instance, writer, qualification, connect = setup_forwarder(monkeypatch, response=response, role=role)
    if fault == "framing":
        reader = asyncio.StreamReader()
        reader.feed_data(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nContent-Length: 2\r\n\r\n{}")
        reader.feed_eof()
        connect.return_value = (reader, writer)
    elif fault == "write-failure":
        writer.drain.side_effect = OSError("fixture-error")
    with pytest.raises(TransportError) as failure:
        await instance.request({"operation": "observe", "session_id": "session-1"},
                               deadline=asyncio.get_running_loop().time() + 1)
    assert failure.value.classification is TransportEffect.EFFECT_UNKNOWN
    assert TOKEN.decode() not in str(failure.value)
    assert len(writer.writes) == 1


@pytest.mark.anyio
@pytest.mark.parametrize("role", ["mmsecretary", "mmmeta"])
async def test_original_lookup_maps_absent_admission_to_native_null(monkeypatch, role):
    instance, writer, qualification, connect = setup_forwarder(monkeypatch, role=role)
    original = {"operation": "read_original", "session_id": "session-1",
                "submission_id": "submission-1", "input_sha256": "d" * 64}
    await instance.request(original, deadline=asyncio.get_running_loop().time() + 1)
    transmitted = json.loads(writer.writes[0].split(b"\r\n\r\n", 1)[1])
    assert transmitted["request"] == dict(original, admission_id=None)
    assert "admission_id" not in original


@pytest.mark.anyio
@pytest.mark.parametrize("role", ["mmsecretary", "mmmeta"])
async def test_foreign_role_http_response_is_never_adopted(monkeypatch, role):
    sibling = "mmmeta" if role == "mmsecretary" else "mmsecretary"
    response = {"schema": conversation_contract(sibling).response_schema,
                "implementation_sha": SHA, "result": {"outcome": "OBSERVED"}}
    instance, writer, _, _ = setup_forwarder(monkeypatch, response=response, role=role)
    with pytest.raises(TransportError) as caught:
        await instance.request({"operation": "observe", "session_id": "session-1"},
                               deadline=asyncio.get_running_loop().time() + 1)
    assert caught.value.classification is TransportEffect.EFFECT_UNKNOWN
    assert len(writer.writes) == 1
