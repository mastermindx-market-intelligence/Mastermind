"""Read-only native tool and optional actual installed-Hermes API canary."""
from __future__ import annotations
import asyncio
import importlib
import json
import os
from pathlib import Path
import httpx
import pytest
from tests.test_hermes_leadership import access_for, reader_for
from tests.test_secretary_team_mission import mission_body
from tests.test_workspace_result_service import result_owner


def native(): return importlib.import_module('integrations.hermes_leadership.native')


def test_native_module_exists():
    assert importlib.util.find_spec('integrations.hermes_leadership.native') is not None


def test_handler_consumes_real_mission(mission_body):
    body,owner=mission_body
    async def exercise():
        access,transport,calls=access_for(body,owner)
        async with transport:
            handler=native().native_handler(reader_for(access))
            reply=json.loads(await handler({},session_id='native-a'))
        assert reply['state']=='AVAILABLE' and len(calls)==1
        assert reply['charter']['key']=='secretary' and reply['admitted'] is False
    asyncio.run(exercise())


@pytest.mark.parametrize('arguments',[None,[],True,'{}',{'role':'meta_ceo'},
 {'session_id':'native-a'},{'action':'submit'},{'model':'expensive'}])
def test_model_cannot_choose_role_route_or_scope(mission_body,arguments):
    body,owner=mission_body
    async def exercise():
        access,transport,calls=access_for(body,owner)
        async with transport:
            reply=json.loads(await native().native_handler(reader_for(access))(arguments,session_id='native-a'))
        assert reply['state']=='REFUSED' and calls==[]
    asyncio.run(exercise())


@pytest.mark.parametrize('kwargs',[{}, {'session_id':'wrong'}, {'session_id':'native-a','task_id':'child'}])
def test_native_lineage_is_not_model_identity(mission_body,kwargs):
    body,owner=mission_body
    async def exercise():
        access,transport,calls=access_for(body,owner)
        async with transport:
            reply=json.loads(await native().native_handler(reader_for(access))({},**kwargs))
        assert reply['state']=='REFUSED' and calls==[]
    asyncio.run(exercise())


@pytest.fixture
def upstream(tmp_path,monkeypatch):
    raw=os.environ.get('HERMES_LEADERSHIP_UPSTREAM')
    if not raw:
        pytest.skip('actual native source not supplied; no installed proof inferred')
    root=Path(raw)
    assert (root/'hermes_cli/plugins.py').is_file()
    monkeypatch.setenv('HERMES_HOME',str(tmp_path))
    monkeypatch.delenv('HERMES_PROFILE',raising=False)
    from integrations.hermes_harness.tests.test_native_tool_registration import _Upstream
    owner=_Upstream(root)
    return owner,tmp_path


def make_ctx(owner,home,name='one'):
    scope=home/name
    scope.mkdir()
    manager=owner.PluginManager(scope_key=str(scope))
    manifest=owner.PluginManifest(name='mastermind-leadership',version='1',source='project',
        path=str(scope),provides_tools=[native().TOOL_NAME],key='mastermind-leadership')
    return owner.PluginContext(manifest,manager),str(scope)


def test_real_native_register_readback_and_lease_disposal(upstream,mission_body):
    owner,home=upstream
    ctx,scope=make_ctx(owner,home)
    body,source=mission_body
    async def exercise():
        access,transport,calls=access_for(body,source)
        async with transport:
            reader=reader_for(access)
            lease=native().register_native_tool(ctx,reader,profile_id=ctx.profile_name)
            entry=owner.registry.snapshot_registration(native().TOOL_NAME,scope=scope)
            assert entry.handler is lease.handler and entry.is_async is True
            assert entry.schema['parameters']['additionalProperties'] is False
            reply=json.loads(await entry.handler({},session_id='native-a'))
            assert reply['state']=='AVAILABLE' and len(calls)==1
            lease.dispose()
            assert owner.registry.snapshot_registration(native().TOOL_NAME,scope=scope) is None
    asyncio.run(exercise())


def test_real_native_collision_preserves_original_entry(upstream,mission_body):
    owner,home=upstream
    ctx,scope=make_ctx(owner,home)
    body,source=mission_body
    async def exercise():
        access,transport,_=access_for(body,source)
        async with transport:
            reader=reader_for(access)
            lease=native().register_native_tool(ctx,reader,profile_id=ctx.profile_name)
            entry=owner.registry.snapshot_registration(native().TOOL_NAME,scope=scope)
            try:
                with pytest.raises(RuntimeError,match='NATIVE_TOOL_COLLISION'):
                    native().register_native_tool(ctx,reader,profile_id=ctx.profile_name)
                assert owner.registry.snapshot_registration(native().TOOL_NAME,scope=scope) is entry
            finally: lease.dispose()
    asyncio.run(exercise())


def test_real_native_wrong_profile_refuses_without_registration(upstream,mission_body):
    owner,home=upstream
    ctx,scope=make_ctx(owner,home)
    body,source=mission_body
    async def exercise():
        access,transport,_=access_for(body,source)
        async with transport:
            with pytest.raises(RuntimeError,match='NATIVE_PROFILE_MISMATCH'):
                native().register_native_tool(ctx,reader_for(access),profile_id='foreign-profile')
        assert owner.registry.snapshot_registration(native().TOOL_NAME,scope=scope) is None
    asyncio.run(exercise())


def test_real_native_two_scopes_have_independent_leases(upstream,mission_body):
    owner,home=upstream
    ca,sa=make_ctx(owner,home,'a'); cb,sb=make_ctx(owner,home,'b')
    body,source=mission_body
    async def exercise():
        access,transport,_=access_for(body,source)
        async with transport:
            la=native().register_native_tool(ca,reader_for(access),profile_id=ca.profile_name)
            lb=native().register_native_tool(cb,reader_for(access,key='engineering',session='native-b'),profile_id=cb.profile_name)
            try:
                la.dispose()
                entry=owner.registry.snapshot_registration(native().TOOL_NAME,scope=sb)
                reply=json.loads(await entry.handler({},session_id='native-b'))
                assert reply['charter']['key']=='engineering'
                assert owner.registry.snapshot_registration(native().TOOL_NAME,scope=sa) is None
            finally: lb.dispose()
    asyncio.run(exercise())


def test_host_session_resolver_contract_exists():
    assert hasattr(native(),'HostLeadershipBinding')


def test_one_native_profile_serves_isolated_host_sessions(upstream,mission_body):
    owner,home=upstream
    ctx,scope=make_ctx(owner,home)
    body,source=mission_body
    async def exercise():
        access,transport,_=access_for(body,source)
        async with transport:
            # This dict stands in for the incumbent host's native session owner.
            readers={'native-a':reader_for(access),'native-b':reader_for(access,key='engineering',session='native-b')}
            binding=native().HostLeadershipBinding(profile_id=ctx.profile_name,
                resolve_reader=readers.get,currentness_guard=lambda:True)
            lease=native().register_native_tool(ctx,binding,profile_id=ctx.profile_name)
            try:
                a=json.loads(await lease.handler({},session_id='native-a'))
                b=json.loads(await lease.handler({},session_id='native-b'))
                assert a['charter']['key']=='secretary' and b['charter']['key']=='engineering'
                missing=json.loads(await lease.handler({},session_id='not-enrolled'))
                assert missing['state']=='REFUSED' and 'mission' not in missing
                del readers['native-a']
                revoked=json.loads(await lease.handler({},session_id='native-a'))
                assert revoked['state']=='REFUSED'
                lease.dispose()
                stale=json.loads(await lease.handler({},session_id='native-b'))
                assert stale['state']=='REFUSED' and 'mission' not in stale
            finally: lease.dispose()
    asyncio.run(exercise())


def test_host_reader_replaced_during_await_discards_original_result(mission_body):
    body,source=mission_body
    readers={}
    async def handler(req):
        readers['native-a']=None
        return httpx.Response(200,json=body)
    async def exercise():
        access,transport,_=access_for(body,source,handler)
        async with transport:
            readers['native-a']=reader_for(access)
            binding=native().HostLeadershipBinding(profile_id='default',
                resolve_reader=readers.get,currentness_guard=lambda:True)
            result=json.loads(await native().native_handler(binding)({},session_id='native-a'))
        assert result['state']=='REFUSED' and 'mission' not in result
    asyncio.run(exercise())


def test_native_profile_readback_failure_rolls_back_owned_lease(upstream,mission_body,monkeypatch):
    owner,home=upstream
    ctx,scope=make_ctx(owner,home)
    body,source=mission_body
    original=ctx.register_tool
    async def exercise():
        access,transport,_=access_for(body,source)
        async with transport:
            def corrupt(**kwargs):
                kwargs['toolset']='wrong-toolset'
                return original(**kwargs)
            monkeypatch.setattr(ctx,'register_tool',corrupt)
            with pytest.raises(RuntimeError,match='NATIVE_TOOL_READBACK_MISMATCH'):
                native().register_native_tool(ctx,reader_for(access),profile_id=ctx.profile_name)
        assert owner.registry.snapshot_registration(native().TOOL_NAME,scope=scope) is None
    asyncio.run(exercise())


def test_registration_exception_retains_exact_original_tool(upstream,mission_body,monkeypatch):
    owner,home=upstream
    ctx,scope=make_ctx(owner,home)
    body,source=mission_body
    original=ctx.register_tool
    handles=[]
    def ambiguous(**kwargs):
        handles.append(original(**kwargs))
        raise RuntimeError('SECRET_REGISTRATION')
    async def exercise():
        access,transport,calls=access_for(body,source)
        async with transport:
            monkeypatch.setattr(ctx,'register_tool',ambiguous)
            try:
                with pytest.raises(RuntimeError,match='NATIVE_TOOL_REGISTRATION_EFFECT_UNKNOWN') as error:
                    native().register_native_tool(ctx,reader_for(access),profile_id=ctx.profile_name)
                assert error.value.original_tool_name==native().TOOL_NAME
                assert error.value.original_context is ctx
                assert 'SECRET_REGISTRATION' not in str(error.value)
                entry=owner.registry.snapshot_registration(native().TOOL_NAME,scope=scope)
                result=json.loads(await entry.handler({},session_id='native-a'))
                assert result['state']=='REFUSED' and not calls
            finally:
                for handle in handles: handle.dispose()
        assert owner.registry.snapshot_registration(native().TOOL_NAME,scope=scope) is None
    asyncio.run(exercise())
