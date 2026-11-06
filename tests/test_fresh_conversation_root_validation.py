"""Actual Fresh root receipt -> synchronous pure Root validation; no native I/O."""
import asyncio
import copy
import dataclasses
import time
import pytest

from tests.test_fresh_conversation_created_project import (
    joined,owner,env,isolated_git_env,identity,rsa_key,_native_read_owner,
    fatal_only_traceback_diagnostics,
)
from tests.test_fresh_conversation import case,cleanup
from tests.test_fresh_conversation_http import mounted,post
from control_plane.principal_projection import neutral_principal_projection
from tests.test_workspace_project_git_publisher import git


def test_actual_fresh_root_validation_reads_once_and_refuses_clones_sql_expiry_grants_and_default(joined,tmp_path,monkeypatch,rsa_key):
    async def run():
        j=joined;reader,doc=_native_read_owner(j,tmp_path)
        workspace=neutral_principal_projection(**dataclasses.asdict(j['workspace']))
        def actual_case(principal):
            return case(tmp_path/'native-root-proof',principal,runtime_override=j['runtime'],workspace_override=workspace,
                workspace_reader_override=reader,work_ref_override=j['args']['work_ref'])
        app,token,wt,service,runtime,request,adapters,calls,sink=await mounted(tmp_path/'http',rsa_key,monkeypatch,
            case_factory=actual_case,executive_policy=j['factory'].policies.submit,
            workspace_policy=j['factory'].workspace_policy,
            claims=dict(iss=j['factory'].policies.submit.issuer,sub='inert-chairman',client_id='inert-client',aud=j['factory'].policies.submit.resource))
        owner=service._fixture_fresh_owner
        acquisitions=[];evidence=[];retained=[];unexpected=[]
        from control_plane import installed_canonical_project_data_binding as binding_module
        from control_plane.foreground_operation import current_foreground_operation, ForegroundOperationRefusal
        from control_plane.project_canonical_data import _CAPTURE
        from control_plane.fresh_conversation_membership import _PHASE
        actual=binding_module.read_installed_project_data
        def observed(*args,**kwargs):
            acquisitions.append(time.monotonic());return actual(*args,**kwargs)
        monkeypatch.setattr(binding_module,'read_installed_project_data',observed)
        async def inspect_before_workspace_effect(root,current):
            operation=current_foreground_operation();source=operation._fresh_conversation_creation_source[0]
            retained.append((operation,source))
            assert operation._root==root.job_id and source._operation is operation
            assert not adapters and _CAPTURE.get() is None
            acquisitions.clear();operation._require_root_current(root.job_id)
            assert len(acquisitions)==2
            acquisitions.clear();operation.require_root(root.job_id)
            assert len(acquisitions)==1 and _CAPTURE.get() is None and _PHASE.get() is None
            evidence.append('actual_strict2_private1')
            before=runtime.events.list_events();acquisitions.clear()
            for cloned,op in ((copy.copy(source),operation),(source,copy.copy(operation)),
                    (dataclasses.replace(source,_issuer=copy.copy(owner)),operation)):
                with pytest.raises(ValueError):
                    with cloned._root_validation_scope(op):pass
            assert not acquisitions and runtime.events.list_events()==before
            evidence.append('clone_issuer_operation_before_read')
            # A plain canonical scope is not the nominal source/operation and
            # cannot make a copied source qualify for the optimized branch.
            from control_plane.fresh_conversation_membership import _project_validation_phase
            with _project_validation_phase(owner,source._project_principal,workspace,request['work_ref']):
                with pytest.raises(ValueError):
                    with copy.copy(source)._root_validation_scope(operation):pass
            assert _CAPTURE.get() is None
            find=runtime.store.find_event_by_command_id
            def sql_guard(action):
                def blocked(command):
                    found=find(command)
                    if command==operation._command:
                        capture=_CAPTURE.get();assert capture is not None and capture.active
                        action(capture)
                    return found
                return blocked
            with monkeypatch.context() as m:
                slot=j['document']['profiles'][j['document']['primary_profile']]
                m.setattr(runtime.store,'find_event_by_command_id',sql_guard(lambda _:m.setitem(slot,'project_canonical_data_read',None)))
                with pytest.raises((ValueError,ForegroundOperationRefusal)) as refused:operation.require_root(root.job_id)
                evidence.append("actual_refusal:"+type(refused.value).__name__)
            evidence.append('sql_midread_latest_revoked')
            assert _CAPTURE.get() is None and _PHASE.get() is None
            def real_expiry(capture):
                time.sleep(max(0,capture.operation.read_deadline-time.monotonic())+0.01)
            with monkeypatch.context() as m:
                m.setattr(runtime.store,'find_event_by_command_id',sql_guard(real_expiry))
                with pytest.raises((ValueError,ForegroundOperationRefusal)) as refused:operation.require_root(root.job_id)
                evidence.append("actual_refusal:"+type(refused.value).__name__)
            evidence.append('sql_real_original15s_expiry')
            assert _CAPTURE.get() is None and _PHASE.get() is None
            def drift(_):
                root=j['integrator'];path=root/'root-validation-default.txt';path.write_text('actual independent default change')
                git(root,'add',str(path.relative_to(root)));git(root,'commit','-m','Independent default during pure Root SQL')
                git(root,'push','origin','main')
            with monkeypatch.context() as m:
                m.setattr(runtime.store,'find_event_by_command_id',sql_guard(drift))
                with pytest.raises((ValueError,ForegroundOperationRefusal)) as refused:operation.require_root(root.job_id)
                evidence.append("actual_refusal:"+type(refused.value).__name__)
            evidence.append('sql_default_changed_outerexit')
            assert _CAPTURE.get() is None and _PHASE.get() is None
            assert runtime.events.list_events()==before and not adapters
            # Actual root admission occurred, but no physical allocation/claim/
            # native start follows this intentionally interrupted inert proof.
            raise ValueError('INERT_AFTER_ROOT_VALIDATION_PROOF')
        async def traced_probe(*args):
            try:return await inspect_before_workspace_effect(*args)
            except BaseException as exc:
                if str(exc)!='INERT_AFTER_ROOT_VALIDATION_PROOF':
                    frames=[];tb=exc.__traceback__
                    while tb is not None:frames.append(tb.tb_frame.f_code.co_name);tb=tb.tb_next
                    unexpected.append(dict(kind=type(exc).__name__,code=getattr(exc,'code',None),frames=frames))
                raise
        monkeypatch.setattr(owner,'_prepare_workspace',traced_probe)
        try:
            _,preview=await post(app,'preview',request,token,wt)
            code,result=await post(app,'create',{**request,'preview_digest':preview['data']['preview']['digest']},token,wt,timeout_seconds=300)
            assert code==202 and not result['ok'] and result['error']['code']=='effect_unknown',result
            assert not unexpected,unexpected
            assert [entry for entry in evidence if not entry.startswith('actual_refusal:')]==['actual_strict2_private1','clone_issuer_operation_before_read',
                'sql_midread_latest_revoked','sql_real_original15s_expiry','sql_default_changed_outerexit'],evidence
            assert len(runtime.jobs.list_jobs())==1 and not runtime.attempts.list_attempts() and not adapters
            operation,source=retained[0];acquisitions.clear()
            assert operation._closed
            with pytest.raises(ValueError):
                with source._root_validation_scope(operation):pass
            assert not acquisitions and _CAPTURE.get() is None
            print('actual_root_validation',evidence,'closed_original_before_read','1Root/0Attempt/0native')
        finally:await cleanup(service)
    asyncio.run(run())
