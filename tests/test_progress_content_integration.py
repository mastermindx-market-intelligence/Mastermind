"""Progress release uses the original Runtime/profile/broker grant, never implicit access."""
import asyncio
import dataclasses
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from common.executive_content_contract import ACCESS_SCHEMA, PAGE_SCHEMA
from control_plane.executive_worker_broker import BrokerStateError
from control_plane.visible_turn_projection import VisibleTurnProjection, TurnKey
from scripts.ohf.laboratory import AppServerClient
from test_executive_content_observer import profile
from test_executive_content_observer_reconcile import _observer
from test_steward_content_integration import fixture


def test_progress_decision_is_explicit_and_digest_bound():
    old = profile()
    assert 'release_profile' not in old.broker_payload()
    new = profile(content_decision='allowed_visible_response_and_progress_metadata')
    assert new.profile_digest != old.profile_digest
    assert new.broker_payload()['release_profile'] == 'visible_response_and_progress_metadata'
    with pytest.raises(ValueError):
        type(old).from_mapping(dict(dataclasses.asdict(old), content_decision=new.content_decision))


def test_real_demultiplexer_publishes_before_terminal_without_second_reader():
    projection = VisibleTurnProjection()
    key = TurnKey('attempt', 'epoch', 'generation', 1, 'worker', 'local', 'native')
    grant = projection.mint_grant(key, progress_thread_id='thread')
    client = AppServerClient([], env={}, cwd=Path('.'))
    client.visible_projection = projection
    event = dict(jsonrpc='2.0', method='item/started', params=dict(threadId='thread', turnId='native',
        startedAtMs=1, item=dict(type='commandExecution', id='SECRET-ID', command='SECRET-CMD')))
    with client._transport_lock:
        assert client._accept_stdout_frame_locked((json.dumps(event) + '\n').encode())
    page = projection.read(key, reader_grant=grant, cursor=None, max_items=64)
    assert len(page.items) == 1 and not page.terminal
    assert 'SECRET' not in repr(page)
    assert client._reader is None  # No new reader was started by projection.


def test_content_observer_progress_profile_joins_original_runtime_and_rechecks_permission(tmp_path):
    clock, runtime, old, adapter, broker = fixture(tmp_path)
    p = profile(**{k:v for k,v in dataclasses.asdict(old).items()
        if k not in ('profile_digest', 'viewer_binding_digest', 'content_decision')},
        content_decision='allowed_visible_response_and_progress_metadata')
    adapter.expected_harness_version = 'codex-cli 0.159.2'
    state = adapter._generations[p.process_generation_id]
    state.provider_session_id = 'SESSION-G1'
    current = [p]
    async def run():
        observer = _observer(runtime, broker, p, clock)
        observer.profile_loader = lambda: current[0]
        assert (await observer.enroll())['status'] == 'ACTIVE'
        adapter.visible_turn_projection.publish_demultiplexed(None, payload=dict(
            method='turn/plan/updated', params=dict(threadId='SESSION-G1', turnId='NATIVE-G1',
                plan=[dict(step='SECRET-PLAN', status='inProgress')], explanation='SECRET-EXPLANATION')))
        access = await observer.handle_frame(p.frame(ACCESS_SCHEMA))
        assert access['ok']
        frame = dict(p.frame(PAGE_SCHEMA), access_ticket_digest=access['access']['ticket_digest'],
                     cursor=None, max_items=64)
        page = await observer.handle_frame(frame)
        assert page['ok'] and len(page['page']['items']) == 1
        assert 'SECRET' not in repr(page)
        current[0] = None
        refused = await observer.handle_frame(frame)
        assert refused['ok'] is False
        current[0] = p
        await observer.revoke()
        assert (await observer.handle_frame(frame))['ok'] is False
    asyncio.run(run())


def test_unqualified_version_and_other_collectors_cannot_enroll_progress(tmp_path):
    clock, runtime, old, adapter, broker = fixture(tmp_path)
    p = profile(**{k:v for k,v in dataclasses.asdict(old).items()
        if k not in ('profile_digest', 'viewer_binding_digest', 'content_decision')},
        content_decision='allowed_visible_response_and_progress_metadata')
    adapter.expected_harness_version = 'codex-cli 0.0.0'
    async def run():
        with pytest.raises(BrokerStateError):
            await broker._dispatch('ohf-observer-enroll', p.broker_payload())
        broker._operator_run.adapter = SimpleNamespace()
        with pytest.raises(BrokerStateError):
            await broker._dispatch('ohf-observer-enroll', p.broker_payload())
    asyncio.run(run())
