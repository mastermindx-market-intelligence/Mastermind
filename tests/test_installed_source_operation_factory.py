"""Real installed factory/host binding; identity sealing is an explicit fixture.
No Git API, publication, installed configuration or execution effect occurs.
"""
import time

import pytest
from tests.test_installed_source_git_identity import identity
from tests.test_knowledge_installed_source_join import owner, env, isolated_git_env, install_actual_compiler
from integrations.mastermind_workspace_app.installed_source_operations import InstalledWorkspaceSourceOperations
from integrations.mastermind_workspace_app.contract import principal_frame
from control_plane.workspace_source_operation_binding import invoke_source_operation
from control_plane.mixed_worker_supervisor import MixedExecutionOwnerSupervisor
from common.workspace_source_operation_wire import FRAME_SCHEMA


@pytest.mark.parametrize('mixed',[False,True])
def test_factory_binds_actual_runtime_and_private_primary_without_compile_for_status(owner,identity,tmp_path,monkeypatch,mixed):
    o=owner;git_identity,_,_,_=identity
    collector,_=install_actual_compiler(o,tmp_path,monkeypatch)
    checked=[]
    def runtime_guard(runtime):
        assert runtime is o['runtime'];checked.append(runtime);return True
    factory=InstalledWorkspaceSourceOperations(collector=collector,policy=o['service']._permissions.policy,
        load_bindings=lambda:o['bindings'],git_identity=git_identity,runtime_guard=runtime_guard)
    primary=o['private'].supervisor
    host=MixedExecutionOwnerSupervisor(primary,{'planner':primary}) if mixed else primary
    binding=factory(o['runtime'],host)
    lookup={'action':'add_project_file','request_id':o['request']['request_id'],'work_ref':'WS:ALPHA',
        'source_commit':o['request']['source_commit'],'base_revision':o['request']['base_revision'],
        'request_sha256':'7'*64,'expected_preference_revision':None}
    frame={'schema':FRAME_SCHEMA,'operation':'read','principal':principal_frame(o['who']),
        'verified_expires_at':int(time.time())+300,'request':lookup}
    result=invoke_source_operation(binding,frame,runtime=o['runtime'],supervisor=host,host_guard=lambda:True)
    assert result['reason']=='ORIGINAL_OPERATION_NOT_OBSERVED' and result['receipt'] is None
    assert len(checked)>=2 and all(rt is o['runtime'] for rt in checked)
    assert o['runtime'].store.list_events()==[] and o['runtime'].jobs.list_jobs()==[]
    with pytest.raises(PermissionError):
        invoke_source_operation(binding,frame,runtime=o['runtime'],supervisor=host,host_guard=lambda:False)
    if mixed:
        host.owners={}
        with pytest.raises(PermissionError):
            invoke_source_operation(binding,frame,runtime=o['runtime'],supervisor=host,host_guard=lambda:True)


def test_factory_refuses_unqualified_objects_and_foreign_supervisor(owner,identity,tmp_path,monkeypatch):
    o=owner;git_identity,_,_,_=identity
    collector,_=install_actual_compiler(o,tmp_path,monkeypatch)
    with pytest.raises(TypeError):
        InstalledWorkspaceSourceOperations(collector=collector,policy=o['service']._permissions.policy,
            load_bindings=lambda:o['bindings'],git_identity=object(),runtime_guard=lambda _:True)
    factory=InstalledWorkspaceSourceOperations(collector=collector,policy=o['service']._permissions.policy,
        load_bindings=lambda:o['bindings'],git_identity=git_identity,runtime_guard=lambda _:True)
    with pytest.raises(ValueError):factory(o['runtime'],object())
