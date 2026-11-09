"""Pinned conversation selection; filesystem ownership is a test fixture."""
from __future__ import annotations
import copy
import json
from unittest.mock import AsyncMock

import pytest

from control_plane import executive_fabric_composition as composition
from control_plane.remote_worker_broker_client import RemoteWorkerBrokerClient
from control_plane.remote_worker_transport import TransportEffect, TransportError
from tests.test_executive_fabric_composition import root_stats, installed


@pytest.fixture
def anyio_backend():
    return "asyncio"


def document(tmp_path):
    paths = {}
    for field, name in (("ca_path", "ca.pem"), ("client_cert_path", "client.pem"),
                        ("client_key_path", "client.key")):
        path = tmp_path / name
        path.write_bytes(b"fixture material; not a real enrolled credential")
        path.chmod(0o600)
        paths[field] = str(path)
    transport = dict(endpoint_host="127.0.0.1", endpoint_port=9443,
                     expected_server_fingerprint="d" * 64, timeout_seconds=2, **paths)
    common = dict(host_ref="host-" + "a" * 64, transport=transport,
                  expected_host_binding_sha256="b" * 64, expected_implementation_sha="c" * 40)
    observation = dict(schema=composition.HERMES_HOST_READ_SCHEMA, **common)
    secretary = dict(schema=composition.HERMES_SECRETARY_HOST_SCHEMA, **common,
                     root_id="transport-root", root_job_id="JOB-001", work_ref="WS:SECRETARY",
                     session_id="native-session", profile_id="native-profile", principal_id="native-principal")
    return dict(schema_version=composition.SECRETARY_CONFIG_SCHEMA_VERSION, bindings=[],
                remote_transports=[], hermes_role_metadata_read=observation,
                hermes_secretary_conversation=secretary)


def source_for(tmp_path, document):
    path, digest = installed(tmp_path, json.dumps(document).encode())
    return composition.FabricBindingSource.from_path(path, digest)


def test_native_selection_is_separate_from_worker_execution(tmp_path, root_stats):
    source = source_for(tmp_path, document(tmp_path))
    selection = source.hermes_secretary_selection()
    assert selection.root_id == "transport-root"
    assert selection.root_job_id == "JOB-001"
    assert selection.work_ref == "WS:SECRETARY"
    assert source.has_execution_bindings is False
    assert source.bindings == ()
    client = source.hermes_secretary_client(root_id=selection.root_id, session_id=selection.session_id)
    assert client._client.identity == {} and client._client.allowed_operations == frozenset()
    assert source.hermes_roles_reader() is not None
    with pytest.raises(composition.FabricCompositionError):
        source.hermes_secretary_client(root_id="foreign-root", session_id=selection.session_id)


@pytest.mark.parametrize("fault", ["extra", "missing", "root", "job", "session", "work",
                                    "profile", "principal", "host", "source", "config", "transport"])
def test_closed_selection_and_shared_host_custody_are_required(tmp_path, root_stats, fault):
    data = document(tmp_path)
    selected = data["hermes_secretary_conversation"]
    if fault == "extra": selected["worker_id"] = "invented"
    elif fault == "missing": selected.pop("principal_id")
    elif fault == "root": selected["root_id"] = True
    elif fault == "job": selected["root_job_id"] = "a bad job"
    elif fault == "session": selected["session_id"] = "bad\nidentity"
    elif fault == "work": selected["work_ref"] = ""
    elif fault == "profile": selected["profile_id"] = ""
    elif fault == "principal": selected["principal_id"] = ""
    elif fault == "host": selected["host_ref"] = "host-" + "f" * 64
    elif fault == "source": selected["expected_implementation_sha"] = "e" * 40
    elif fault == "config": selected["expected_host_binding_sha256"] = "e" * 64
    else: selected["transport"] = dict(selected["transport"], endpoint_port=9444)
    with pytest.raises(composition.FabricCompositionError):
        source_for(tmp_path, data)


def test_v3_does_not_acquire_conversation_authority(tmp_path, root_stats):
    data = document(tmp_path)
    data["schema_version"] = composition.HOST_READ_CONFIG_SCHEMA_VERSION
    with pytest.raises(composition.FabricCompositionError):
        source_for(tmp_path, data)
    data.pop("hermes_secretary_conversation")
    source = source_for(tmp_path, data)
    assert source.hermes_secretary_selection() is None
    assert source.hermes_secretary_client(root_id="transport-root", session_id="native-session") is None
    assert source.has_execution_bindings is False


@pytest.mark.anyio
@pytest.mark.parametrize("change_at", ["before", "callback", "after"])
async def test_binding_changes_do_not_forge_nonexecution(tmp_path, root_stats, monkeypatch, change_at):
    source = source_for(tmp_path, document(tmp_path))
    selection = source.hermes_secretary_selection()
    events = []
    def change():
        source.path.write_bytes(source.path.read_bytes() + b" ")
    class FakeClient:
        async def request_secretary(self, request, *, before_write=None):
            events.append("transport")
            if before_write is not None:
                try:
                    before_write("submit", copy.deepcopy(request))
                except Exception:
                    raise TransportError("before_write_refused", TransportEffect.NO_EFFECT) from None
            events.append("write")
            if change_at == "after": change()
            return {"schema": "mastermind.hermes_secretary_native_control/v1", "status": "ADMITTED"}
    monkeypatch.setattr(RemoteWorkerBrokerClient, "for_secretary_conversation",
                        lambda *args, **kwargs: FakeClient())
    client = source.hermes_secretary_client(root_id=selection.root_id, session_id=selection.session_id)
    if change_at == "before": change()
    def commit(operation, request):
        events.append("commit")
        if change_at == "callback": change()
    with pytest.raises(TransportError) as failure:
        await client.request_secretary({"operation": "submit"}, before_write=commit)
    assert failure.value.classification is (TransportEffect.EFFECT_UNKNOWN if change_at == "after"
                                            else TransportEffect.NO_EFFECT)
    assert ("write" in events) is (change_at == "after")
    if change_at == "before": assert events == []


@pytest.mark.anyio
async def test_pinned_client_preserves_the_durable_guard_and_native_result(tmp_path, root_stats, monkeypatch):
    source = source_for(tmp_path, document(tmp_path))
    selection = source.hermes_secretary_selection()
    expected = {"schema": "mastermind.hermes_secretary_native_control/v1", "status": "EFFECT_UNKNOWN"}
    called = []
    class FakeClient:
        async def request_secretary(self, request, *, before_write=None):
            assert before_write("submit", request) is None
            return expected
    monkeypatch.setattr(RemoteWorkerBrokerClient, "for_secretary_conversation",
                        lambda *args, **kwargs: FakeClient())
    client = source.hermes_secretary_client(root_id=selection.root_id, session_id=selection.session_id)
    request = {"operation": "submit", "fixture": "sealed"}
    assert await client.request_secretary(request, before_write=lambda *args: called.append(args)) == expected
    assert called == [("submit", request)]

def dual_document(tmp_path):
    data = document(tmp_path)
    meta = copy.deepcopy(data["hermes_secretary_conversation"])
    meta.update(schema=composition.HERMES_META_HOST_SCHEMA, root_id="meta-root",
                root_job_id="JOB-002", work_ref="WS:META", session_id="meta-session",
                profile_id="meta-profile")
    data.update(schema_version=composition.CONVERSATION_CONFIG_SCHEMA_VERSION,
                hermes_meta_conversation=meta)
    return data


def test_v5_keeps_two_distinct_selections_on_one_qualified_host(tmp_path, root_stats):
    source = source_for(tmp_path, dual_document(tmp_path))
    secretary, meta = source.hermes_secretary_selection(), source.hermes_meta_selection()
    assert type(secretary) is composition.HermesSecretaryHostBinding
    assert type(meta) is composition.HermesMetaHostBinding
    assert secretary.transport == meta.transport
    assert secretary.session_id != meta.session_id
    assert source.has_execution_bindings is False
    client = source.hermes_meta_client(root_id=meta.root_id, session_id=meta.session_id)
    assert client._client._conversation_role == "mmmeta"
    with pytest.raises(composition.FabricCompositionError):
        source.hermes_meta_client(root_id=secretary.root_id, session_id=secretary.session_id)


@pytest.mark.parametrize("field,value", [
    ("schema", composition.HERMES_SECRETARY_HOST_SCHEMA),
    ("host_ref", "host-" + "f" * 64),
    ("expected_host_binding_sha256", "e" * 64),
    ("expected_implementation_sha", "e" * 40),
    ("session_id", ""), ("root_job_id", "not-a-job"),
])
def test_v5_refuses_foreign_family_or_source(tmp_path, root_stats, field, value):
    data = dual_document(tmp_path)
    data["hermes_meta_conversation"][field] = value
    with pytest.raises(composition.FabricCompositionError):
        source_for(tmp_path, data)


def test_v4_never_acquires_meta_from_a_secretary_selection(tmp_path, root_stats):
    source = source_for(tmp_path, document(tmp_path))
    assert source.hermes_meta_selection() is None
    assert source.hermes_meta_client(root_id="transport-root", session_id="native-session") is None


@pytest.mark.anyio
@pytest.mark.parametrize("change_at", ["before", "callback", "after"])
async def test_meta_pinned_client_retains_exact_effect_boundary(tmp_path, root_stats, monkeypatch, change_at):
    source = source_for(tmp_path, dual_document(tmp_path))
    selected = source.hermes_meta_selection()
    events = []
    def change():
        source.path.write_bytes(source.path.read_bytes() + b" ")
    class Fake:
        async def request_meta(self, request, *, before_write=None):
            events.append("transport")
            try:
                before_write("submit", copy.deepcopy(request))
            except Exception:
                raise TransportError("before_write_refused", TransportEffect.NO_EFFECT) from None
            events.append("write")
            if change_at == "after":
                change()
            return {"schema": "mastermind.hermes_meta_native_control/v1", "status": "ADMITTED"}
    monkeypatch.setattr(RemoteWorkerBrokerClient, "for_meta_conversation", lambda *a, **k: Fake())
    client = source.hermes_meta_client(root_id=selected.root_id, session_id=selected.session_id)
    if change_at == "before":
        change()
    def commit(*_):
        events.append("commit")
        if change_at == "callback":
            change()
    with pytest.raises(TransportError) as caught:
        await client.request_meta({"operation": "submit"}, before_write=commit)
    assert caught.value.classification is (TransportEffect.EFFECT_UNKNOWN if change_at == "after"
                                           else TransportEffect.NO_EFFECT)
    assert ("write" in events) is (change_at == "after")
