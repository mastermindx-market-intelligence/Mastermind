"""Nominal core boundary using real disposable Runtime/original reply owners.

Synthetic native metadata and private IPC remain the incumbent fixture seams;
no live bearer, host, provider, credentials, or service is accessed.
"""
import asyncio
import dataclasses
from types import SimpleNamespace

import pytest

from control_plane.installed_project_conversations_binding import require_installed_project_conversations
from integrations.session_bridge.project_conversations import RuntimeProjectConversationsReader
from integrations.session_bridge.schemas import BridgeError
from tests.test_session_bridge_runtime_return import setup, bind, populate
from tests.test_project_conversations import selection


def test_nominal_core_binding_keeps_actual_runtime_original_and_read_owner(setup):
    s = setup
    populate(s)
    s.service.calls.clear()  # Exclude original fixture setup, then measure READ only.
    owner = RuntimeProjectConversationsReader(s.owner)
    issued = owner.installed_binding()
    assert require_installed_project_conversations(issued, s.runtime) is issued
    before = s.runtime.events.list_events()
    page = issued.catalogue(s.projection, {'work_ref': s.binding.work_ref}, guard=lambda: True)
    result = asyncio.run(issued.read(s.projection, selection(page), guard=lambda: True))
    assert result['turns'][0]['state'] == 'AVAILABLE'
    assert result['turns'][0]['reply']['parent_consumed'] is False
    assert s.runtime.events.list_events() == before
    assert all(call['operation'] == 'read_thread' for call in s.service.calls)


@pytest.mark.parametrize('damage', ['duck', 'owner', 'foreign-runtime', 'source', 'method', 'qualifier'])
def test_changed_binding_refuses_before_source_callback(setup, monkeypatch, damage):
    s = setup
    bind(s)
    owner = RuntimeProjectConversationsReader(s.owner)
    issued = owner.installed_binding()
    calls = []
    runtime = s.runtime
    if damage == 'duck':
        issued = SimpleNamespace(**{field.name: getattr(issued, field.name) for field in dataclasses.fields(issued)})
    elif damage == 'owner':
        class ForeignOwner:
            def __getattr__(self, name):
                calls.append(name)
                raise AssertionError('foreign owner inspected before nominal qualification')
        issued = dataclasses.replace(issued, owner=ForeignOwner())
    elif damage == 'foreign-runtime':
        runtime = SimpleNamespace(store=s.runtime.store)
    elif damage == 'source':
        async def changed(*args, **kwargs):
            calls.append(True)
            raise AssertionError('changed source invoked')
        monkeypatch.setattr(s.owner, 'service_call', changed)
    elif damage == 'method':
        monkeypatch.setattr(owner, 'catalogue', lambda *a, **k: calls.append(True))
    else:
        issued = dataclasses.replace(issued, qualifier=lambda value: calls.append(True) or True)
    with pytest.raises(ValueError):
        require_installed_project_conversations(issued, runtime)
    assert not calls and not s.service.calls


def test_source_replaced_during_actual_await_is_withheld_before_next_private_read(setup):
    s = setup
    populate(s)
    issued = RuntimeProjectConversationsReader(s.owner).installed_binding()
    page = issued.catalogue(s.projection, {'work_ref': s.binding.work_ref}, guard=lambda: True)
    s.service.calls.clear()
    foreign = []
    async def changed(*args, **kwargs):
        foreign.append(True)
        raise AssertionError('foreign source reached')
    s.service.on_read = lambda: setattr(s.owner, 'service_call', changed)
    before = s.runtime.events.list_events()
    with pytest.raises((ValueError, BridgeError)):
        asyncio.run(issued.read(s.projection, selection(page), guard=lambda: True))
    assert len(s.service.calls) == 1 and not foreign
    assert s.runtime.events.list_events() == before


def test_reader_subclass_cannot_issue_core_installed_binding(setup):
    class ForeignReader(RuntimeProjectConversationsReader):
        pass
    with pytest.raises(ValueError):
        ForeignReader(setup.owner).installed_binding()


@pytest.mark.parametrize('replace_source', [False, True])
def test_actual_private_socket_nonempty_read_and_await_source_replacement(setup, tmp_path, replace_source):
    """Actual Service/socket/core binding -> real bounded original Event READ.

    Peer/startup and retained native/carrier facts are explicit disposable
    seams; the existing separate signed HTTP test covers bearer verification.
    """
    import json
    import os
    import tempfile
    from pathlib import Path
    from common import project_conversation_read_contract as wire
    from control_plane.executive_service import ExecutiveControlService, CeoIngressAppBinding
    from tests.test_executive_service import _config
    from tests.test_fresh_conversation import cleanup
    s = setup
    populate(s)
    page = RuntimeProjectConversationsReader(s.owner).catalogue(s.projection,
        {'work_ref': s.binding.work_ref}, guard=lambda: True)
    chosen = selection(page)
    s.service.calls.clear()
    service = ExecutiveControlService(_config(tmp_path / 'host', runtime_root=s.runtime.store.root))
    service.runtime = s.runtime
    service._ceo_ingress_ready = True  # Explicit temporary startup seam, no installed host.
    class NoExecutionGrounding:
        def observe(self):
            raise AssertionError('READ acquired execution grounding')
    service._ceo_ingress_app_binding = CeoIngressAppBinding(peer_uid=os.geteuid(), armed=True,
        grounding_provider=NoExecutionGrounding(), session_bridge_provider_factory=lambda runtime: None,
        project_conversation_read_provider_factory=lambda runtime:
            RuntimeProjectConversationsReader(s.owner).installed_binding())
    foreign = []
    async def changed(*args, **kwargs):
        foreign.append(True)
        raise AssertionError('replaced IPC source reached')
    if replace_source:
        s.service.on_read = lambda: setattr(s.owner, 'service_call', changed)
    before = s.runtime.events.list_events()
    async def run():
        try:
            with tempfile.TemporaryDirectory(prefix='nominal-conversation-', dir='/tmp') as directory:
                path = Path(directory) / 's'
                server = await asyncio.start_unix_server(service._handle_ceo_ingress_connection, path=path)
                try:
                    reader, writer = await asyncio.open_unix_connection(str(path))
                    projection = dataclasses.asdict(s.projection)
                    projection['scopes'] = list(projection['scopes'])
                    frame = wire.frame({'schema': wire.SCHEMA, 'operation': 'read',
                        'principal': projection, 'arguments': chosen})
                    writer.write(wire.encode_frame(frame)); await writer.drain(); writer.write_eof()
                    packet = await asyncio.wait_for(reader.readline(), 8)
                    writer.close(); await writer.wait_closed()
                    assert len(packet) <= wire.MAX_RESPONSE_BYTES
                    return json.loads(packet)
                finally:
                    server.close(); await server.wait_closed()
        finally:
            await cleanup(service)
            if service._ceo_ingress_tasks:
                await asyncio.wait_for(asyncio.gather(*service._ceo_ingress_tasks), 5)
    result = asyncio.run(run())
    if replace_source:
        assert result['ok'] is False and result['error']['code'] == 'ingress_unavailable'
        assert len(s.service.calls) == 1 and not foreign
        assert 'The bounded finding is confirmed.' not in repr(result)
    else:
        assert result['ok'] is True and result['result']['turns'][0]['state'] == 'AVAILABLE'
        assert result['result']['turns'][0]['reply']['parent_consumed'] is False
    assert s.runtime.events.list_events() == before
