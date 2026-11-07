"""Actual shared installed DATA factory→hosted CCR→Workspace READ source join.

Temporary Git/Runtime/AF_UNIX only; publication/principal/native/source-seal
premises remain the existing joined fixtures. No provider or installed service.
"""
import asyncio
import copy
import json
import os
from pathlib import Path

import pytest

from tests.test_project_discovery_installed_plan import full_joined, actual_child
from tests.test_project_creation_source_owner import owner, env, isolated_git_env
from tests.test_installed_source_git_identity import identity
from tests.test_fabric_result_projection import _bound_reader, _release
from tests.test_project_planning_factory import invocation
from tests.fresh_conversation_full_cache import CanonicalFixtureCache
from tests.executive_installed_control_fixture import spawn_workspace_room_listener
from integrations.mastermind_workspace_app.installed_source_operations import InstalledWorkspaceSourceOperations
from integrations.mastermind_workspace_app.contract import principal_frame, workspace_authorizers
from integrations.mastermind_workspace_app.project_authoring_grant import legacy_workspace_document
from control_plane.workspace_control_room_lifecycle import HostedControlRoom
from control_plane.workspace_read_service import workspace_provider_factory
from scripts import chairman_control_room as publisher


def test_shared_installed_read_factory_uses_one_owner_without_supervisor_and_real_current_n(full_joined,monkeypatch):
    j=full_joined
    actual_child(j,monkeypatch)
    created=asyncio.run(invocation(j['factory'],j['args'],lambda:j['factory'].submit(**j['args'])))
    old=j['data']
    factory=InstalledWorkspaceSourceOperations(collector=old.collector,policy=old.policy,
        load_bindings=old.loader,git_identity=old.identity,runtime_guard=lambda rt:rt is j['runtime'])
    pair=factory.read_bindings(j['runtime'])
    assert pair[0].owner is pair[1].owner.data
    assert pair[0].store is pair[1].store is j['runtime'].store
    assert pair[0].owner.collector is old.collector and pair[0].owner.identity is old.identity
    # No Supervisor/private input/Job is needed for the READ composition.
    before=j['runtime'].events.list_events()
    baseline=CanonicalFixtureCache(j['code_root'],j['tmp_path']/'canonical-baseline',
        mastermind_revision=j['factory'].service.config.proof_base_sha)
    cfg=publisher.ServerConfig(repo_root=Path.cwd(),macro_root=str(j['code_root']),bindings_path=None,
        token='inert-fixed-read',origin=publisher.UNIX_CONTROL_ROOM_ORIGIN,port=0,state_ttl=3600,
        validity_sample_fn=baseline.owner.validity_sample_fn)
    cfg.compose_inputs=lambda *_args,**_kwargs:baseline.compile()
    listener,path=spawn_workspace_room_listener(monkeypatch)
    hosted=HostedControlRoom(cfg,listener=listener,socket_path=path,allowed_peer_uids=(os.geteuid(),))
    keeper,namespace,runtime_binding,bounded=_bound_reader(j['runtime'])
    _,authorize=workspace_authorizers(policy=old.policy,
        load_bindings=lambda:legacy_workspace_document(j['document'],old.policy))
    provide=workspace_provider_factory(control_room=hosted,authorize=authorize,armed={},runtime_identity={},
        bounded_runtime=lambda rt:bounded,canonical_project_read_bindings_factory=factory.read_bindings)
    async def run():
        await hosted.start()
        try:
            reader=provide(j['runtime'])
            assert reader._canonical_project_data.owner is reader._project_discovery.owner.data
            assert reader._canonical_project_data.store is j['runtime'].store
            frame=dict(schema='mastermind.executive_workspace_read.v1',operation='programs',selection=None,
                principal=principal_frame(j['workspace']))
            slot=j['document']['profiles'][j['document']['primary_profile']]
            stamp=slot['project_canonical_data_read'];slot['project_canonical_data_read']=None
            initial=await reader.handle_frame(frame)
            assert initial['result']['schema']=='mastermind.workspace_programs.v1'
            slot['project_canonical_data_read']=stamp
            current=await reader.handle_frame(frame)
            assert current['result']['schema']=='mastermind.workspace_programs.v2',current
            selected=dict(work_ref=j['args']['work_ref'],root_job_id=created['job_id'])
            mission=await reader.handle_frame(dict(frame,schema='mastermind.executive_workspace_read.v2',operation='mission_v3',selection=selected))
            assert mission['ok'] and mission['result']['mission']['root_job_id']==created['job_id'],mission
            plan=await reader.handle_frame(dict(frame,schema='mastermind.workspace_project_plan_read.v1',operation='project_plan',selection={'work_ref':selected['work_ref']}))
            assert plan['ok'] and plan['result']['availability']=='AVAILABLE',plan
            assert plan['result']['source']['commit']==j['current']
            assert initial['result']['control_room']==current['result']['control_room']
            assert len(current['result']['canonical_projects'])==1
            # No grant from method presence; a mismatched nominal owner pair
            # is rejected before any read, even in the same Runtime namespace.
            another=factory.read_bindings(j['runtime'])
            wrong=workspace_provider_factory(control_room=hosted,authorize=authorize,armed={},runtime_identity={},
                canonical_project_read_bindings_factory=lambda rt:(pair[0],another[1]))
            with pytest.raises(ValueError,match='owners differ'):wrong(j['runtime'])
            assert j['runtime'].events.list_events()==before
            target=os.environ.get('MMOS_DISCOVERY_APP_SOURCE_OUTPUT')
            if target:
                Path(target).write_text(json.dumps(dict(programs_before=initial['result'],programs=current['result'],
                    mission=mission['result'],selected_plan=plan['result'],
                    source_premises=baseline.provenance()),sort_keys=True,ensure_ascii=False))
        finally:
            await hosted.close()
    try:asyncio.run(run())
    finally:
        _release(keeper,runtime_binding)
        listener.close();Path(path).unlink(missing_ok=True)


def test_phase1c_registers_the_existing_source_factory_paired_read_method(tmp_path,monkeypatch,identity):
    from control_plane import workspace_read_provider_binding as binding
    from tests.test_workspace_source_join import test_installed_factory_is_inert_and_uses_late_service_custody
    from types import MethodType
    original=binding.bind_installed_read_provider
    seen=[]
    def capture(factory, method):
        # Observe the constructor's existing binding seam. Replacing the factory
        # itself would invalidate the code identity this composition must prove.
        assert type(method) is MethodType
        assert type(method.__self__) is InstalledWorkspaceSourceOperations
        assert method.__func__ is InstalledWorkspaceSourceOperations.read_bindings
        seen.append(method)
        return original(factory, method)
    monkeypatch.setattr(binding,'bind_installed_read_provider',capture)
    test_installed_factory_is_inert_and_uses_late_service_custody(tmp_path,monkeypatch,True,True,identity)
    assert len(seen)==1
