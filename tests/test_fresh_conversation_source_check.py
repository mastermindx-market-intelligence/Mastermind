"""Fresh pre-Root source check shares only one synchronous qualified DATA read."""
import asyncio
import copy
import dataclasses
from contextlib import contextmanager
import time
import pytest

from tests.test_fresh_conversation_created_project import (
    joined,owner,env,isolated_git_env,identity,rsa_key,_native_read_owner,
    fatal_only_traceback_diagnostics,
)
from tests.test_fresh_conversation import case,cleanup
from tests.test_fresh_conversation_http import mounted,post
from control_plane.principal_projection import neutral_principal_projection
from control_plane.foreground_operation import ForegroundOperationRefusal
from tests.test_workspace_project_git_publisher import git


def test_actual_source_check_three_to_one_and_currentness_refuses_before_root_event(joined,tmp_path,monkeypatch,rsa_key):
    async def run():
        from control_plane.fresh_conversation_admission import FreshConversationCreationSource
        from control_plane.project_canonical_data import _CAPTURE
        from control_plane.fresh_conversation_membership import _PHASE
        from control_plane import installed_canonical_project_data_binding as binding_module
        j=joined;reader,doc=_native_read_owner(j,tmp_path)
        workspace=neutral_principal_projection(**dataclasses.asdict(j['workspace']))
        def actual_case(principal):
            return case(tmp_path/'native-source-proof',principal,runtime_override=j['runtime'],workspace_override=workspace,
                workspace_reader_override=reader,work_ref_override=j['args']['work_ref'])
        app,token,wt,service,runtime,request,adapters,calls,sink=await mounted(tmp_path/'http',rsa_key,monkeypatch,
            case_factory=actual_case,executive_policy=j['factory'].policies.submit,
            workspace_policy=j['factory'].workspace_policy,
            claims=dict(iss=j['factory'].policies.submit.issuer,sub='inert-chairman',client_id='inert-client',aud=j['factory'].policies.submit.resource))
        owner=service._fixture_fresh_owner
        acquisitions=[];evidence=[];retained=[];unexpected=[];started=[False]
        read=binding_module.read_installed_project_data
        def counted(*args,**kwargs):
            acquisitions.append(time.monotonic());return read(*args,**kwargs)
        monkeypatch.setattr(binding_module,'read_installed_project_data',counted)
        actual_check=FreshConversationCreationSource.check
        def inspect_source(source):
            if started[0]:return actual_check(source)
            started[0]=True;retained.append(source)
            operation=source._operation
            assert operation._root is None and _CAPTURE.get() is None
            before=runtime.events.list_events()
            acquisitions.clear();source._check_current()
            assert len(acquisitions)==3
            acquisitions.clear();actual_check(source)
            assert len(acquisitions)==1 and _CAPTURE.get() is None and _PHASE.get() is None
            evidence.append('actual_strict3_private1')
            acquisitions.clear()
            for cloned in (copy.copy(source),dataclasses.replace(source,_issuer=copy.copy(owner)),
                    dataclasses.replace(source,_operation=copy.copy(operation))):
                with pytest.raises(ValueError):actual_check(cloned)
            assert not acquisitions and runtime.events.list_events()==before
            evidence.append('copied_foreign_issuer_operation_before_read')
            original_project=owner._project
            def inject(action):
                done=[False]
                def project(*args,**kwargs):
                    capture=_CAPTURE.get()
                    if capture is not None and not done[0]:
                        done[0]=True;action(capture)
                    return original_project(*args,**kwargs)
                return project
            with monkeypatch.context() as m:
                slot=j['document']['profiles'][j['document']['primary_profile']]
                m.setattr(owner,'_project',inject(lambda _:m.setitem(slot,'project_canonical_data_read',None)))
                with pytest.raises((ValueError,ForegroundOperationRefusal)) as refused:actual_check(source)
                evidence.append('revoked:'+type(refused.value).__name__)
            assert _CAPTURE.get() is None and _PHASE.get() is None
            def real_expiry(capture):
                time.sleep(max(0,capture.operation.read_deadline-time.monotonic())+0.01)
            with monkeypatch.context() as m:
                m.setattr(owner,'_project',inject(real_expiry))
                with pytest.raises((ValueError,ForegroundOperationRefusal)) as refused:actual_check(source)
                evidence.append('expired:'+type(refused.value).__name__)
            assert _CAPTURE.get() is None and _PHASE.get() is None
            # Mutate real operation identity only AFTER the actual Macro
            # scope's blocking full postcheck has finished. This discriminator
            # must refuse before Source.check can return to a Root Event sink.
            from control_plane.project_canonical_data import CanonicalProjectDataView
            capture_scope=CanonicalProjectDataView.capture_scope
            with monkeypatch.context() as m:
                @contextmanager
                def expired_after_full_post(view,*args,**kwargs):
                    with capture_scope(view,*args,**kwargs) as capture:yield capture
                    phase=_PHASE.get()
                    if phase is not None and phase.view is view:
                        m.setattr(operation,'_principal',dataclasses.replace(operation._principal,expires_at=int(time.time())-1))
                m.setattr(CanonicalProjectDataView,'capture_scope',expired_after_full_post)
                with pytest.raises((ValueError,ForegroundOperationRefusal)) as refused:actual_check(source)
                evidence.append('late_post_identity:'+type(refused.value).__name__)
            assert _CAPTURE.get() is None and _PHASE.get() is None
            with monkeypatch.context() as m:
                @contextmanager
                def closed_after_full_post(view,*args,**kwargs):
                    with capture_scope(view,*args,**kwargs) as capture:yield capture
                    phase=_PHASE.get()
                    if phase is not None and phase.view is view:
                        m.setattr(operation,'_closed',True)
                m.setattr(CanonicalProjectDataView,'capture_scope',closed_after_full_post)
                with pytest.raises((ValueError,ForegroundOperationRefusal)) as refused:actual_check(source)
                evidence.append('late_post_closed:'+type(refused.value).__name__)
            assert _CAPTURE.get() is None and _PHASE.get() is None
            def default_change(_):
                root=j['integrator'];path=root/'source-check-default.txt';path.write_text('independent default movement')
                git(root,'add',str(path.relative_to(root)));git(root,'commit','-m','External default during pure source check')
                git(root,'push','origin','main')
            with monkeypatch.context() as m:
                m.setattr(owner,'_project',inject(default_change))
                with pytest.raises((ValueError,ForegroundOperationRefusal)) as refused:actual_check(source)
                evidence.append('default:'+type(refused.value).__name__)
            assert _CAPTURE.get() is None and _PHASE.get() is None
            assert runtime.events.list_events()==before and not runtime.jobs.list_jobs() and not adapters
            raise ValueError('INERT_AFTER_SOURCE_CHECK_PROOF')
        def traced(source):
            try:return inspect_source(source)
            except BaseException as exc:
                if str(exc)!='INERT_AFTER_SOURCE_CHECK_PROOF':
                    frames=[];tb=exc.__traceback__
                    while tb is not None:frames.append(tb.tb_frame.f_code.co_name);tb=tb.tb_next
                    unexpected.append(dict(kind=type(exc).__name__,code=getattr(exc,'code',None),frames=frames))
                raise
        monkeypatch.setattr(FreshConversationCreationSource,'check',traced)
        try:
            _,preview=await post(app,'preview',request,token,wt)
            code,result=await post(app,'create',{**request,'preview_digest':preview['data']['preview']['digest']},token,wt,timeout_seconds=300)
            assert code==202 and not result['ok'] and result['error']['code']=='effect_unknown',result
            assert not unexpected,unexpected
            assert evidence[:2]==['actual_strict3_private1','copied_foreign_issuer_operation_before_read'],evidence
            assert len(evidence)==7 and evidence[2].startswith('revoked:') and evidence[3].startswith('expired:') and evidence[4].startswith('late_post_identity:') and evidence[5].startswith('late_post_closed:') and evidence[6].startswith('default:'),evidence
            assert not runtime.jobs.list_jobs() and not runtime.attempts.list_attempts() and not adapters
            source=retained[0];assert source._operation._closed;acquisitions.clear()
            with pytest.raises(ValueError):actual_check(source)
            assert not acquisitions and _CAPTURE.get() is None
            print('actual_source_check',evidence,'closed_before_read','0Root/0Attempt/0native')
        finally:await cleanup(service)
    asyncio.run(run())
