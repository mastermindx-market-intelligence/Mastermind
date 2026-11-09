"""Control-local observation keeps the Relay-only transport boundary intact."""
import asyncio
import json
import os

import pytest

from control_plane.executive_service import ExecutiveControlService
from integrations.slack_agent_dialogue.host_local_observation import HostLocalDialogueObservationReader
from integrations.slack_agent_dialogue.executive_observation_client import ExecutiveDialogueObservationClient
from tests.test_executive_service import _strict_dialogue_runtime
from tests.test_executive_ceo_ingress import _config, _FakeSupervisor, short_socket_root  # noqa: F401
from tests import test_principal_source_reader as relay


@pytest.mark.parametrize("fault", ["none", "runtime", "closing", "not_ready", "state", "runtime_during", "close_during", "invalid_parent", "invalid_thread", "provider_during"])
def test_exact_existing_runtime_read_with_no_observation_socket(tmp_path, monkeypatch, fault):
    fixture = _strict_dialogue_runtime(tmp_path, monkeypatch)
    runtime = fixture.runtime
    service = ExecutiveControlService(_config(tmp_path / "host", socket_root=tmp_path))
    service.runtime = runtime
    service._ceo_ingress_ready = True
    service._service_state = "READY"
    reader = HostLocalDialogueObservationReader(service, runtime)
    calls = []
    read_facts = service._runtime_dialogue_observation_facts
    def facts(current, parent):
        calls.append(parent)
        value = read_facts(current, parent)
        if fault == "runtime_during": service.runtime = None
        elif fault == "close_during": service._closing = True
        elif fault == "provider_during": service._dialogue_observation_facts_provider = lambda *_: value
        return value
    monkeypatch.setattr(service, "_runtime_dialogue_observation_facts", facts)
    async def no_socket(*_, **__): raise AssertionError("host-local reader must not use a socket")
    monkeypatch.setattr(asyncio, "open_unix_connection", no_socket)
    if fault == "runtime": service.runtime = None
    elif fault == "closing": service._closing = True
    elif fault == "not_ready": service._ceo_ingress_ready = False
    elif fault == "state": service._service_state = "STARTING"
    before = runtime.events.list_events()
    async def scenario():
        if fault == "none":
            observed = await reader.resolve(parent=fixture.parent, thread_ts=relay.THREAD)
            assert observed.candidate == fixture.candidate
        else:
            with pytest.raises(Exception):
                await reader.resolve(parent={} if fault == "invalid_parent" else fixture.parent,
                    thread_ts="invalid" if fault == "invalid_thread" else relay.THREAD)
    asyncio.run(scenario())
    assert len(calls) == (1 if fault in {"none", "runtime_during", "close_during", "provider_during"} else 0)
    assert runtime.events.list_events() == before
    # This type is deliberately not a subtype of the client that can write Wake.
    assert not isinstance(reader, ExecutiveDialogueObservationClient)
    assert not any(hasattr(reader, name) for name in ("submit", "reconcile", "_wake_exchange", "_exchange"))


@pytest.mark.parametrize("listener_ready", [False, True])
@pytest.mark.parametrize("custom_provider", [False, True])
def test_local_reader_requires_canonical_provider_but_not_listener_readiness(tmp_path, monkeypatch,
                                                                          listener_ready, custom_provider):
    fixture = _strict_dialogue_runtime(tmp_path, monkeypatch)
    calls = []
    def custom(*args):
        calls.append(args)
        raise AssertionError("custom listener provider cannot authorize local reads")
    service = ExecutiveControlService(_config(tmp_path / "host", socket_root=tmp_path),
        dialogue_observation_socket_path=tmp_path / "observation.sock",
        dialogue_observation_peer_uid=457, dialogue_observation_group_gid=os.getegid(),
        dialogue_observation_facts_provider=custom if custom_provider else None)
    service.runtime = fixture.runtime
    service._ceo_ingress_ready = True
    service._service_state = "READY"
    service._dialogue_observation_ready = listener_ready
    before = fixture.runtime.events.list_events()
    if custom_provider:
        with pytest.raises(Exception, match="UNAVAILABLE_ZERO_EFFECT"):
            HostLocalDialogueObservationReader(service, fixture.runtime)
    else:
        reader = HostLocalDialogueObservationReader(service, fixture.runtime)
        result = asyncio.run(reader.resolve(parent=fixture.parent, thread_ts=relay.THREAD))
        assert result.candidate == fixture.candidate
    assert calls == []
    assert fixture.runtime.events.list_events() == before


def test_host_local_reader_requires_exact_existing_owner(tmp_path, monkeypatch):
    fixture = _strict_dialogue_runtime(tmp_path, monkeypatch)
    service = ExecutiveControlService(_config(tmp_path / "host", socket_root=tmp_path))
    with pytest.raises(ValueError):
        HostLocalDialogueObservationReader(service, fixture.runtime)
    with pytest.raises(ValueError):
        HostLocalDialogueObservationReader(object(), fixture.runtime)


def test_observation_listener_still_refuses_control_uid_450(tmp_path, short_socket_root, monkeypatch):
    # The production roles are simulated at the kernel-peer seam; this proves
    # source enforcement on a real local socket, not installed UID deployment.
    monkeypatch.setattr("control_plane.executive_service._peer_uid", lambda _: 450)
    calls = []
    def forbidden(*args):
        calls.append(args)
        raise AssertionError("Control peer cannot acquire via Relay-only listener")
    async def scenario():
        path = short_socket_root / "obs" / "dialogue.sock"
        service = ExecutiveControlService(_config(tmp_path, socket_root=short_socket_root / "ctl"),
            supervisor_factory=lambda _: _FakeSupervisor(),
            dialogue_observation_socket_path=path, dialogue_observation_peer_uid=457,
            dialogue_observation_group_gid=os.getegid(), dialogue_observation_facts_provider=forbidden)
        await service.start()
        try:
            reader, writer = await asyncio.open_unix_connection(path)
            try:
                response = json.loads(await reader.readline())
                assert response["state"] == "HELD"
                assert response["reason"] == "PEER_UID_REFUSED"
                assert calls == []
                assert service._dialogue_observation_peer_uid == 457
            finally:
                writer.close()
                await writer.wait_closed()
        finally:
            await service.close()
    asyncio.run(scenario())
