"""Fixed host reads, real mTLS routing and refusal of unqualified source.

Synthetic publisher/installed-source fixtures test protocol behavior only.
They do not attest a deployed Hermes role or enroll a provider credential.
"""
from __future__ import annotations

import asyncio
import copy
import dataclasses
import hashlib
import json
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from common import hermes_role_status_contract as status
from common import workspace_byok_read_contract as workspace
from control_plane import remote_worker_broker_client as client_module
from control_plane import remote_worker_transport as transport
from ops.executive_os import hermes_role_metadata_observer as observer
from ops.executive_os import remote_worker_gateway_service as service
from ops.executive_os.remote_worker_gateway import RemoteWorkerGateway
from ops.executive_os.remote_worker_gateway_config import HermesRoleMetadataReadBinding
from tests.test_remote_worker_gateway import (
    _cert_sha256, _close_gateway, _gateway_fixture, _openssl_available,
)
from tests.test_remote_worker_gateway_service import _fixture, _load, _write
from tests.test_remote_worker_transport import HOST_REF, IDENTITY

pytestmark = pytest.mark.anyio
NOW = 1_800_000_000_000
MONOTONIC = 100_000
IMPLEMENTATION = "a" * 40
BINDING = "b" * 64
BOOT = "12345678-1234-1234-1234-123456789abc"
PEER = b"hermes-host-observation-fixture-peer"


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _observation(*, now_ms=NOW):
    rows = []
    for index, (role, unit) in enumerate(zip(status.ROLES, status.UNITS)):
        metadata = {
            "schema": status.METADATA_SCHEMA, "role": role,
            "state": "CONFIGURATION_OBSERVED", "reason": "CONFIGURATION_CONSISTENT",
            "source_binding": "NOT_ATTESTED", "proof": workspace.proof(),
            "requested": {"provider_id": "minimax", "native_provider": "openai",
                          "requested_model": "MiniMax-M3"},
            "provenance": {"upstream_sha": "c" * 40, "release": "20261105",
                           "manifest_sha256": "d" * 64, "profile_sha256": "e" * 64,
                           "hermes_config_sha256": "f" * 64, "upstream_attested": False},
        }
        age = 1000 - index * 500
        invocation = str(index + 1) * 32
        rows.append({"role": role, "unit": unit, "main_pid": 100 + index,
                     "main_start_monotonic_us": 50_000_000, "invocation_id": invocation,
                     "status": {"schema": status.STATUS_SCHEMA, "role": role,
                                "host_boot_id": BOOT, "invocation_id": invocation,
                                "implementation_sha": IMPLEMENTATION,
                                "observed_at_ms": now_ms - age,
                                "observed_monotonic_ms": MONOTONIC - age,
                                "metadata": metadata}})
    return {"host_binding_sha256": BINDING, "host_boot_id": BOOT,
            "implementation_sha": IMPLEMENTATION, "roles": rows}


def _snapshots():
    value = _observation()
    rows = [dict(row, notify_access="main", active_state="active", sub_state="running")
            for row in value["roles"]]
    before = {"host_boot_id": BOOT, "implementation_sha": IMPLEMENTATION,
              "source_identity": "9" * 64, "roles": rows,
              "observed_at_ms": NOW - 100, "observed_monotonic_ms": MONOTONIC - 100}
    after = copy.deepcopy(before)
    after.update(observed_at_ms=NOW - 50, observed_monotonic_ms=MONOTONIC - 50)
    return before, after


def _qualify(before, after):
    return observer.qualify_pair(before, after, host_binding_sha256=BINDING,
                                 implementation_sha=IMPLEMENTATION, now_ms=NOW,
                                 now_monotonic_ms=MONOTONIC)


def test_projection_keeps_original_time_digest_and_unproven_proof():
    value = _observation()
    result = status.project_observation(value, expected_host_binding_sha256=BINDING,
                                       expected_implementation_sha=IMPLEMENTATION, now_ms=NOW)
    assert result["state"] == "OBSERVED"
    assert result["source_observation"]["observed_at_ms"] == NOW - 1000
    assert result["source_observation"]["metadata_sha256"] == hashlib.sha256(
        status.canonical([row["status"]["metadata"] for row in value["roles"]])).hexdigest()
    assert result["proof"] == workspace.proof()
    for row in result["roles"]:
        assert set(row) == {"role", "state", "requested_provider", "requested_model"}
    assert b"main_pid" not in status.canonical(result)
    assert b"invocation_id" not in status.canonical(result)


@pytest.mark.parametrize("mutation", ["bool-pid", "wrong-unit", "wrong-role", "invocation",
                                      "boot", "implementation", "start", "proof", "extra"])
def test_private_observation_refuses_identity_or_authority_drift(mutation):
    value = _observation()
    row = value["roles"][0]
    if mutation == "bool-pid": row["main_pid"] = True
    elif mutation == "wrong-unit": row["unit"] = status.UNITS[1]
    elif mutation == "wrong-role": row["status"]["role"] = status.ROLES[1]
    elif mutation == "invocation": row["invocation_id"] = "3" * 32
    elif mutation == "boot": row["status"]["host_boot_id"] = "0" * 36
    elif mutation == "implementation": row["status"]["implementation_sha"] = "0" * 40
    elif mutation == "start": row["main_start_monotonic_us"] = MONOTONIC * 1000
    elif mutation == "proof": row["status"]["metadata"]["proof"]["credential_enrollment"] = "VERIFIED"
    else: row["credential"] = "fixture-only-never-allowed"
    with pytest.raises(status.RoleStatusError):
        status.validate_observation(value)


def test_status_text_is_closed_bounded_and_duplicate_free():
    value = _observation()["roles"][0]["status"]
    encoded = status.encode_status_text(value)
    assert len(encoded.encode()) <= status.MAX_STATUS_BYTES
    assert status.decode_status_text(encoded, expected_role=status.ROLES[0]) == value
    duplicate = encoded.replace('"role":', '"role":"mmmeta","role":', 1)
    for raw in (duplicate, encoded + "\n", encoded + " " * 2048,
                status.STATUS_PREFIX + '{"schema":NaN}', "wrong:" + encoded):
        with pytest.raises(status.RoleStatusError):
            status.decode_status_text(raw, expected_role=status.ROLES[0])


@pytest.mark.parametrize("mutation", ["pid", "invocation", "source", "boot", "status",
                                      "notify", "inactive", "clock-jump", "future-publication",
                                      "expired", "source-boolean"])
def test_pair_requires_stable_pid1_source_and_consistent_publisher_clocks(mutation):
    before, after = _snapshots()
    assert _qualify(before, after) == _observation()
    if mutation == "pid": after["roles"][0]["main_pid"] += 1
    elif mutation == "invocation": after["roles"][0]["invocation_id"] = "3" * 32
    elif mutation == "source": after["source_identity"] = "8" * 64
    elif mutation == "boot": after["host_boot_id"] = "00000000-1234-1234-1234-123456789abc"
    elif mutation == "status": after["roles"][0]["status"]["observed_at_ms"] += 1
    elif mutation in {"notify", "inactive", "source-boolean"}:
        for snapshot in (before, after):
            if mutation == "notify": snapshot["roles"][0]["notify_access"] = "all"
            elif mutation == "inactive": snapshot["roles"][0]["active_state"] = "inactive"
            else: snapshot["source_identity"] = True
    else:
        for snapshot in (before, after):
            publication = snapshot["roles"][0]["status"]
            if mutation == "clock-jump":
                publication["observed_monotonic_ms"] = MONOTONIC - 29_000
            elif mutation == "future-publication":
                publication.update(observed_at_ms=NOW - 25, observed_monotonic_ms=MONOTONIC - 25)
            else:
                publication.update(observed_at_ms=NOW - 31_000, observed_monotonic_ms=MONOTONIC - 31_000)
    with pytest.raises(status.RoleStatusError):
        _qualify(before, after)


async def test_missing_installed_source_refuses_before_unit_or_private_io(monkeypatch):
    monkeypatch.setattr(observer.sys, "platform", "linux")
    assert observer._installed_source_identity(IMPLEMENTATION) is None
    def forbidden(*args, **kwargs):
        raise AssertionError("source gate must precede host reads")
    monkeypatch.setattr(observer, "_boot_id", forbidden)
    monkeypatch.setattr(observer, "_query_fixed_pid1", forbidden)
    instance = observer.HermesRoleMetadataObserver(host_binding_sha256=BINDING,
                                                  implementation_sha=IMPLEMENTATION)
    with pytest.raises(status.RoleStatusError, match="SOURCE_UNAVAILABLE"):
        await instance.read_pair()


def test_host_family_has_no_worker_identity_and_rejects_replay_or_open_json():
    request = transport.build_host_observation_request(HOST_REF, "1" * 64)
    assert set(request) == {"schema", "host_ref", "operation", "nonce", "request_sha256"}
    raw = status.canonical(request)
    assert transport.decode_host_observation_request(raw, expected_host_ref=HOST_REF) == request
    for bad in (raw.replace(b'"nonce":', b'"nonce":"duplicate","nonce":', 1),
                b"\xff", raw + b" " * 1024, b'{"a":NaN}'):
        with pytest.raises(transport.TransportValidationError):
            transport.decode_host_observation_request(bad, expected_host_ref=HOST_REF)
    response = transport.build_host_observation_response(request, observation=_observation())
    another = transport.build_host_observation_request(HOST_REF, "2" * 64)
    with pytest.raises(transport.TransportValidationError):
        transport.validate_host_observation_response(response, another)
    with pytest.raises(transport.TransportValidationError):
        transport.validate_request(request, expected_host_ref=HOST_REF,
                                   allowed_worker_ids={"WORKER-001"}, allowed_operations={"status"})
    worker = transport.build_request(IDENTITY, "status", {})
    with pytest.raises(transport.TransportValidationError):
        transport.validate_host_observation_request(worker, expected_host_ref=HOST_REF)


def test_optional_capability_preserves_legacy_canonical_bytes_and_secure_loader(tmp_path):
    root, path, document = _fixture(tmp_path)
    legacy = _load(service, root, path)
    expected = json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    assert service._canonical_config(legacy) == expected
    assert service.remote_worker_gateway_config_digest(legacy) == hashlib.sha256(expected).hexdigest()
    assert legacy.hermes_role_metadata_read is None
    capability = HermesRoleMetadataReadBinding(IMPLEMENTATION).to_wire()
    document["hermes_role_metadata_read"] = capability
    _write(path, json.dumps(document), 0o440)
    bound = _load(service, root, path)
    assert bound.hermes_role_metadata_read.implementation_sha == IMPLEMENTATION
    assert json.loads(service._canonical_config(bound)) == document
    for bad in (None, dict(capability, unit="arbitrary.service"), dict(capability, implementation_sha=True)):
        document["hermes_role_metadata_read"] = bad
        _write(path, json.dumps(document), 0o440)
        with pytest.raises(service.RemoteWorkerGatewayServiceError):
            _load(service, root, path)


class _Writer:
    def __init__(self, reader, response=None, *, drain_delay=0):
        self.reader = reader
        self.response = response
        self.drain_delay = drain_delay
        self.writes = []
        self.closed = False
        self.aborted = False
        self.buffered = b""
        self.transport = self

    def get_extra_info(self, name):
        return SimpleNamespace(getpeercert=lambda binary_form=False: PEER) if name == "ssl_object" else None

    def write(self, raw):
        self.writes.append(raw)
        self.buffered += raw
        if self.response is not None:
            request = json.loads(raw[4:])
            self.reader.feed_data(self.response(request))

    async def drain(self):
        await asyncio.sleep(self.drain_delay)

    def close(self):
        self.closed = True

    async def wait_closed(self):
        return None

    def abort(self):
        self.aborted = True
        self.buffered = b""


def _binding(tmp_path, *, timeout=0.5):
    paths = [tmp_path / name for name in ("ca.pem", "client.pem", "client.key")]
    for path in paths: path.write_bytes(b"fixture")
    return transport.BrokerTransportBinding(
        endpoint=("localhost", 7443), ca_path=paths[0], client_cert_path=paths[1],
        client_key_path=paths[2], expected_server_fingerprint=hashlib.sha256(PEER).hexdigest(),
        timeout_seconds=timeout,
    )


def _client(binding):
    return client_module.RemoteWorkerBrokerClient.for_host_observation(
        binding, host_ref=HOST_REF, expected_host_binding_sha256=BINDING,
        expected_implementation_sha=IMPLEMENTATION,
    )


def _reply(request, value=None):
    response = transport.build_host_observation_response(request, observation=value or _observation())
    return transport.encode_frame(status.canonical(response))


async def test_client_one_request_strips_private_fields_and_refuses_worker_calls(tmp_path, monkeypatch):
    client = _client(_binding(tmp_path))
    reader = asyncio.StreamReader()
    writer = _Writer(reader, _reply)
    opened = AsyncMock(return_value=(reader, writer))
    monkeypatch.setattr(client, "_open_connection", opened)
    monkeypatch.setattr(client_module, "time", SimpleNamespace(time_ns=lambda: NOW * 1_000_000))
    result = await client.read_hermes_roles()
    assert result["state"] == "OBSERVED"
    assert result["source_observation"]["observed_at_ms"] == NOW - 1000
    assert opened.await_count == 1 and len(writer.writes) == 1
    assert writer.closed and writer.aborted
    with pytest.raises(transport.TransportError):
        await client.request("status", {})
    with pytest.raises(transport.TransportValidationError):
        client.bind_payload_identity(session_epoch_id="EPOCH-001", process_generation_id="GEN-001")
    assert opened.await_count == 1


@pytest.mark.parametrize("failure", ["oversize", "partial", "nonce", "pin", "binding", "stale"])
async def test_client_failures_return_closed_unavailable_without_retry(tmp_path, monkeypatch, failure):
    client = _client(_binding(tmp_path))
    reader = asyncio.StreamReader()
    def respond(request):
        if failure == "oversize": return (8193).to_bytes(4, "big")
        if failure == "partial": return (10).to_bytes(4, "big") + b"{}"
        value = _observation()
        if failure == "binding": value["host_binding_sha256"] = "0" * 64
        if failure == "stale": value = _observation(now_ms=NOW - 31_000)
        if failure == "nonce": request = transport.build_host_observation_request(HOST_REF, "0" * 64)
        return _reply(request, value)
    writer = _Writer(reader, respond)
    opened = AsyncMock(return_value=(reader, writer))
    monkeypatch.setattr(client, "_open_connection", opened)
    monkeypatch.setattr(client_module, "time", SimpleNamespace(time_ns=lambda: NOW * 1_000_000))
    if failure == "pin": monkeypatch.setattr(client, "_server_pin_matches", lambda _writer: False)
    if failure == "partial":
        original = writer.write
        def write(raw):
            original(raw)
            reader.feed_eof()
        writer.write = write
    result = await client.read_hermes_roles()
    assert result["state"] == "UNAVAILABLE"
    assert result["proof"] == workspace.proof()
    assert opened.await_count == 1 and len(writer.writes) <= 1
    assert writer.closed
    if failure == "oversize": assert not reader._buffer


async def test_client_has_one_total_deadline_and_propagates_cancellation(tmp_path, monkeypatch):
    client = _client(_binding(tmp_path, timeout=0.15))
    reader = asyncio.StreamReader()
    writer = _Writer(reader, _reply, drain_delay=0.10)
    calls = 0
    async def open_delayed():
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.10)
        return reader, writer
    monkeypatch.setattr(client, "_open_connection", open_delayed)
    monkeypatch.setattr(client_module, "time", SimpleNamespace(time_ns=lambda: NOW * 1_000_000))
    result = await client.read_hermes_roles()
    assert result["state"] == "UNAVAILABLE" and calls == 1 and writer.closed
    reader = asyncio.StreamReader()
    writer = _Writer(reader)
    monkeypatch.setattr(client, "_open_connection", AsyncMock(return_value=(reader, writer)))
    task = asyncio.create_task(client.read_hermes_roles())
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError): await task
    assert writer.closed and writer.aborted


async def test_gateway_success_preserves_buffer_and_auth_precedes_frame_read():
    gateway = RemoteWorkerGateway.__new__(RemoteWorkerGateway)
    gateway.config = SimpleNamespace(host_ref=HOST_REF, request_timeout_seconds=0.5,
                                     max_frame_bytes=8192,
                                     hermes_role_metadata_read=HermesRoleMetadataReadBinding(IMPLEMENTATION))
    gateway._host_observer = SimpleNamespace(read_pair=AsyncMock(return_value=_observation()))
    gateway._peer_is_expected_control = lambda _writer: True
    gateway.broker_call = AsyncMock(side_effect=AssertionError("host read entered Worker Broker"))
    request = transport.build_host_observation_request(HOST_REF, "1" * 64)
    reader = asyncio.StreamReader()
    reader.feed_data(transport.encode_frame(status.canonical(request)))
    writer = _Writer(reader)
    await gateway._handle_connection(reader, writer)
    assert writer.closed and not writer.aborted and writer.buffered
    response = transport.decode_host_observation_response(writer.buffered[4:], request)
    assert response["state"] == "OBSERVED"
    gateway.broker_call.assert_not_awaited()
    gateway._peer_is_expected_control = lambda _writer: False
    gateway._read_frame = AsyncMock(side_effect=AssertionError("unauthenticated frame read"))
    await gateway._handle_connection(asyncio.StreamReader(), _Writer(asyncio.StreamReader()))
    gateway._read_frame.assert_not_awaited()


@pytest.mark.skipif(not _openssl_available(), reason="openssl unavailable")
async def test_real_mtls_host_family_isolated_and_existing_worker_path_preserved(tmp_path):
    fixture = await _gateway_fixture(tmp_path)
    fixture.gateway.config = dataclasses.replace(
        fixture.config, hermes_role_metadata_read=HermesRoleMetadataReadBinding(IMPLEMENTATION))
    binding = transport.BrokerTransportBinding(
        endpoint=("localhost", fixture.endpoint[1]), ca_path=fixture.config.ca_path,
        client_cert_path=fixture.control_cert, client_key_path=fixture.control_key,
        expected_server_fingerprint=_cert_sha256(fixture.config.certificate_path),
    )
    original_broker = fixture.gateway.broker_call
    blocked_broker = AsyncMock(side_effect=AssertionError("host read entered Worker Broker"))
    fixture.gateway.broker_call = blocked_broker
    observed = _observation(now_ms=time.time_ns() // 1_000_000)
    read_pair = AsyncMock(return_value=observed)
    fixture.gateway._host_observer = SimpleNamespace(read_pair=read_pair)
    try:
        result = await _client(binding).read_hermes_roles()
        assert result["state"] == "OBSERVED"
        read_pair.assert_awaited_once()
        blocked_broker.assert_not_awaited()
        fixture.gateway.config = fixture.config
        result = await _client(binding).read_hermes_roles()
        assert result["state"] == "UNAVAILABLE"
        assert read_pair.await_count == 1
        blocked_broker.assert_not_awaited()
        fixture.gateway.broker_call = original_broker
        worker = client_module.RemoteWorkerBrokerClient(binding, IDENTITY, allowed_operations={"status"})
        assert await worker.request("status", {"run_id": "ATT-001"}) == {"worker": "ATT-001"}
    finally:
        await _close_gateway(fixture)
