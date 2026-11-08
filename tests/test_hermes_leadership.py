"""Role context over the existing canonical Mission producer and reader."""
from __future__ import annotations
import asyncio
import copy
import importlib
import json
import httpx
import pytest

from integrations.secretary_team_access.client import SecretaryAccessClient
from integrations.secretary_team_access.mission import summarize_mission
from tests.test_secretary_team_mission import mission_body, _selection, _STAMP_EPOCH
from tests.test_workspace_result_service import result_owner


def api():
    return importlib.import_module('integrations.hermes_leadership')


def test_package_is_implemented():
    assert importlib.util.find_spec('integrations.hermes_leadership') is not None


def access_for(body, owner, handler=None, clock=None):
    calls = []
    def default(request):
        calls.append(request)
        return httpx.Response(200, json=body)
    transport = httpx.AsyncClient(base_url='https://owner.test',
        transport=httpx.MockTransport(handler or default),
        headers={'authorization': 'Bearer synthetic-host-token'}, follow_redirects=False)
    client = SecretaryAccessClient(**_selection(owner), workspace=transport,
                                  clock=clock or (lambda: _STAMP_EPOCH + 30))
    return client, transport, calls


def reader_for(client, *, key='secretary', session='native-a', guard=None):
    return api().LeadershipReader(charter_key=key, session_id=session,
        access=client, currentness_guard=guard or (lambda: True))


def test_all_charters_use_existing_responsibility_syntax():
    from control_plane.executive_responsibility import normalize_responsibility_intent
    keys = api().CHARTER_KEYS
    assert set(keys) == {'meta_ceo','autonomy_ceo','secretary','delivery','engineering','reliability',
                         'product','intelligence','assurance','grok_adviser'}
    for key in keys:
        c = api().charter_for(key)
        assert c['key'] == key and c['authority_grant'] is False
        normalize_responsibility_intent(c['responsibility_intent'])
        assert c['objective'] and c['completion_evidence'] and c['limits']
        assert any('maintained open-source' in limit and 'docs/REUSE_FIRST_ENGINEERING.md' in limit
                   for limit in c['limits'])
        assert c['routing']['advisory_only'] is True
        assert not {'model', 'provider', 'account', 'host', 'api_key'} & c['routing'].keys()


def test_charter_copy_is_detached():
    first = api().charter_for('secretary')
    first['limits'].append('unsafe')
    first['routing']['advisory_only'] = False
    second = api().charter_for('secretary')
    assert 'unsafe' not in second['limits'] and second['routing']['advisory_only']


@pytest.mark.parametrize('key', ['unknown', '', None, True, [], {'key':'secretary'}])
def test_unknown_role_fails_closed(key):
    with pytest.raises(ValueError, match='invalid_charter'):
        api().charter_for(key)


def test_real_mission_brief_preserves_original_facts(mission_body):
    body, owner = mission_body
    async def exercise():
        client, transport, calls = access_for(body, owner)
        async with transport:
            reader = reader_for(client)
            one = await reader.read(session_id='native-a')
            two = await reader.read(session_id='native-a')
        expected = summarize_mission(body, selection=_selection(owner), now=_STAMP_EPOCH+30)
        assert one['state'] == 'AVAILABLE' and one['mission'] == expected
        assert two == one
        assert one['admitted'] is False and one['dispatched'] is False
        assert one['replay_authorized'] is False and one['reasoning_wake'] is False
        assert one['mission']['acceptance']['state'] == 'NOT_PROJECTED'
        assert one['mission']['execution']['state'] == 'NOT_STARTED'
        assert one['continuity']['next_action'] == 'CONSULT_CANONICAL_PLAN'
        assert one['continuity']['missing_fields'] == ['objective','done_when','next_action','unresolved_effects']
        assert one['continuity']['new_work_authorized'] is False
        assert 'synthetic-host-token' not in json.dumps(one)
        assert len(json.dumps(one).encode()) < 24576
        assert len(calls) == 2
        assert all(r.method == 'GET' and r.url.path == '/workspace/mission/v3/current' for r in calls)
        assert all(dict(r.url.params) == _selection(owner) for r in calls)
    asyncio.run(exercise())


def test_wrong_session_and_revoked_binding_do_not_read(mission_body):
    body, owner = mission_body
    async def exercise():
        client, transport, calls = access_for(body, owner)
        async with transport:
            for reader, session in [(reader_for(client), 'foreign'),
                    (reader_for(client, guard=lambda: False), 'native-a')]:
                reply = await reader.read(session_id=session)
                assert reply['state'] == 'REFUSED' and 'mission' not in reply
        assert calls == []
    asyncio.run(exercise())


def test_revocation_during_await_discards_all_facts(mission_body):
    body, owner = mission_body
    valid = [True]
    async def handler(request):
        valid[0] = False
        return httpx.Response(200, json=body)
    async def exercise():
        client, transport, _ = access_for(body, owner, handler)
        async with transport:
            result = await reader_for(client, guard=lambda: valid[0]).read(session_id='native-a')
        assert result['state'] == 'REFUSED' and result['reason'] == 'binding_not_current'
        assert 'mission' not in result and 'charter' not in result
    asyncio.run(exercise())


@pytest.mark.parametrize('change', ['selection','transport','clock'])
def test_host_binding_replacement_refuses_before_read(mission_body, change):
    body, owner = mission_body
    async def exercise():
        client, transport, calls = access_for(body, owner)
        async with transport:
            reader = reader_for(client)
            if change == 'selection': client.selection['work_ref'] = 'WS:OTHER'
            elif change == 'transport': client._workspace = object()
            else: client._clock = lambda: _STAMP_EPOCH + 30
            reply = await reader.read(session_id='native-a')
            assert reply['state'] == 'REFUSED' and not calls
    asyncio.run(exercise())


@pytest.mark.parametrize('status', [401,403,500])
def test_source_denial_or_unavailability_has_no_cached_context(mission_body,status):
    body, owner = mission_body
    state = [200]
    def handler(req):
        return httpx.Response(state[0], json=body if state[0]==200 else {'error':{'code':'source_refused'}})
    async def exercise():
        client, transport, _ = access_for(body, owner, handler)
        async with transport:
            reader = reader_for(client)
            assert (await reader.read(session_id='native-a'))['state'] == 'AVAILABLE'
            state[0] = status
            reply = await reader.read(session_id='native-a')
        assert reply['state'] == ('REFUSED' if status in (401,403) else 'UNAVAILABLE')
        assert 'mission' not in reply and 'charter' not in reply
    asyncio.run(exercise())


@pytest.mark.parametrize('clock', [lambda: _STAMP_EPOCH+1000, lambda: _STAMP_EPOCH-1,
                                 lambda: float('nan'), lambda: float('inf')])
def test_stale_future_or_invalid_clock_is_not_current(mission_body,clock):
    body, owner = mission_body
    async def exercise():
        client, transport, _ = access_for(body, owner, clock=clock)
        async with transport:
            result = await reader_for(client).read(session_id='native-a')
        assert result['state'] == 'UNAVAILABLE' and 'mission' not in result
    asyncio.run(exercise())


def test_concurrent_roles_are_detached(mission_body):
    body, owner = mission_body
    async def exercise():
        client, transport, _ = access_for(body, owner)
        async with transport:
            a,b = reader_for(client,key='secretary'),reader_for(client,key='engineering',session='native-b')
            replies = await asyncio.gather(*(r.read(session_id=s) for _ in range(8)
                for r,s in [(a,'native-a'),(b,'native-b')]))
        assert all(r['state']=='AVAILABLE' for r in replies)
        assert replies[0]['charter']['key']=='secretary' and replies[1]['charter']['key']=='engineering'
        replies[0]['mission']['mission']['status']='FAKE'
        assert all(r['mission']['mission']['status']!='FAKE' for r in replies[1:])
    asyncio.run(exercise())


def test_guard_error_is_value_free(mission_body):
    body, owner = mission_body
    def guard(): raise RuntimeError('SECRET_SENTINEL')
    async def exercise():
        client,transport,calls=access_for(body,owner)
        async with transport:
            result=await reader_for(client,guard=guard).read(session_id='native-a')
        assert result['state']=='REFUSED' and 'SECRET_SENTINEL' not in json.dumps(result)
        assert not calls
    asyncio.run(exercise())


def test_adviser_without_meter_is_explicitly_held(mission_body):
    body,owner=mission_body
    async def exercise():
        access,transport,_=access_for(body,owner)
        async with transport:
            reply=await reader_for(access,key='grok_adviser').read(session_id='native-a')
        assert reply['state']=='AVAILABLE'
        assert reply['adviser_budget']['decision']=='HOLD'
        assert reply['adviser_budget']['reason']=='meter_unbound'
    asyncio.run(exercise())


def test_adviser_composes_host_meter_without_admission(mission_body):
    from tests.test_hermes_leadership_budget import snapshot,request,START,NOW,iso
    from datetime import datetime,timedelta,timezone
    body,owner=mission_body
    now=datetime.fromtimestamp(_STAMP_EPOCH+30,timezone.utc)
    observed=[]
    async def meter():
        observed.append(1)
        return {'snapshot':snapshot(window_start=iso(now-timedelta(seconds=30)),
            window_end=iso(now-timedelta(seconds=30)+timedelta(days=7)),observed_at=iso(now)),
            'request':request(estimate=500)}
    async def exercise():
        access,transport,_=access_for(body,owner)
        async with transport:
            reader=api().LeadershipReader(charter_key='grok_adviser',session_id='native-a',
                access=access,currentness_guard=lambda:True,adviser_budget_reader=meter)
            reply=await reader.read(session_id='native-a')
        assert reply['state']=='AVAILABLE' and observed==[1]
        assert reply['adviser_budget']['decision']=='ELIGIBLE_FOR_CAPACITY_CHECK'
        assert reply['adviser_budget']['admitted'] is False and reply['admitted'] is False
    asyncio.run(exercise())


def test_adviser_meter_error_is_value_free_hold(mission_body):
    body,owner=mission_body
    async def meter(): raise RuntimeError('SECRET_METER')
    async def exercise():
        access,transport,_=access_for(body,owner)
        async with transport:
            reader=api().LeadershipReader(charter_key='grok_adviser',session_id='native-a',
                access=access,currentness_guard=lambda:True,adviser_budget_reader=meter)
            reply=await reader.read(session_id='native-a')
        assert reply['adviser_budget']['decision']=='HOLD'
        assert 'SECRET_METER' not in json.dumps(reply)
    asyncio.run(exercise())


def test_adviser_revoked_during_meter_read_discards_brief(mission_body):
    body,owner=mission_body
    valid=[True]
    async def meter():
        valid[0]=False
        return {}
    async def exercise():
        access,transport,_=access_for(body,owner)
        async with transport:
            reader=api().LeadershipReader(charter_key='grok_adviser',session_id='native-a',
                access=access,currentness_guard=lambda:valid[0],adviser_budget_reader=meter)
            reply=await reader.read(session_id='native-a')
        assert reply['state']=='REFUSED' and 'mission' not in reply
    asyncio.run(exercise())
