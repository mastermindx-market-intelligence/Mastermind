"""One inert Runtime -> canonical Workspace -> Activity -> original result operand.

No provider/process collection or live Runtime is used. Exact OHF lifecycle writes
are to tmp_path; source/JWT/kernel/namespace seams remain explicit fixture inputs.
"""
import asyncio
import dataclasses
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time

import pytest
from common import executive_workspace_contract as wire
from common import executive_workspace_activity_contract as activity
from control_plane.executive_runtime import Runtime,OperatorHarnessRegistry
from control_plane.workspace_read_service import WorkspaceReadService
from control_plane.operator_harness_contract import NormalizedEvent
from integrations.mastermind_workspace_app.contract import principal_frame
from tests.fresh_conversation_full_cache import CanonicalFixtureCache
from tests.test_workspace_mission_result_service import _all_severity_chain
from tests.test_fabric_result_projection import _bound_reader,_release
from tests.test_executive_coo_host import setup as coo_fixture
from tests.test_workspace_read_app import rsa_key

MACRO_REVISION='69206df50e394e2af97692101e0fe35dec0f8876'
ORIGINAL_ORIGIN=Path('/var/folders/sb/h3rq5rvj1b3_r18p6w9swyp80000gn/T/mmos-s34-source-measure-7ff7-01a1aa3d/test_signed_created_n_preview_0/origin.git').resolve()
PRIVATE='PRIVATE-COLLECTOR-COMMAND-AND-REASONING-NOT-PUBLIC'


def source_revision(environ):
    value=environ.get('PROJECT_ACTIVITY_SOURCE_REVISION')
    if type(value) is not str or len(value)!=40 or any(c not in '0123456789abcdef' for c in value):
        raise ValueError('EXPLICIT_SOURCE_REVISION_REQUIRED')
    return value


def test_source_metadata_input_performs_no_fallback_process(monkeypatch):
    def refused(*args,**kwargs):raise AssertionError('source metadata attempted process fallback')
    import inspect
    from tests import test_workspace_admitted_plan_read as transport_suite
    inspect.signature(CanonicalFixtureCache).bind(Path('/inert-macro'),Path('/inert-cache'),mastermind_revision='a'*40)
    inspect.signature(_all_severity_chain).bind(Path('/inert-runtime'),workstream='WS:ONE')
    inspect.signature(coo_fixture).bind(Path('/inert-coo'))
    inspect.signature(transport_suite.transport).bind({},object(),Path('/inert-app'),Path('/inert-socket'))
    inspect.signature(NormalizedEvent).bind('attempt','epoch','generation','turn','item/started',payload_redacted={})
    monkeypatch.setattr(subprocess,'Popen',refused)
    assert source_revision({'PROJECT_ACTIVITY_SOURCE_REVISION':'a'*40})=='a'*40
    for environ in ({},{'PROJECT_ACTIVITY_SOURCE_REVISION':'HEAD'},{'PROJECT_ACTIVITY_SOURCE_REVISION':None}):
        with pytest.raises(ValueError,match='EXPLICIT_SOURCE_REVISION_REQUIRED'):source_revision(environ)


def git(root,*args):
    return subprocess.check_output(['git','-C',str(root),*args],text=True).strip()


def checkpoint(value):
    name=os.environ.get('PROJECT_ACTIVITY_EXPORT')
    if not name:return
    target=Path(name);target.parent.mkdir(parents=True,exist_ok=True)
    payload=json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False).encode()+b'\n'
    fd,tmp=tempfile.mkstemp(prefix=target.name+'.',dir=target.parent)
    try:
        with os.fdopen(fd,'wb')as out:out.write(payload);out.flush();os.fsync(out.fileno())
        os.replace(tmp,target)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)


@pytest.fixture
def activity_socket_root():
    # Same already-qualified single-owner fixture namespace as the incumbent
    # socket-aware planning guard, not a general AF_UNIX/network allowance.
    import stat
    with tempfile.TemporaryDirectory(prefix='mm-plan-activity-',dir='/tmp')as name:
        root=Path(name);record=root.lstat()
        assert record.st_uid==os.geteuid() and stat.S_IMODE(record.st_mode)==0o700 and not stat.S_ISLNK(record.st_mode)
        yield root


def owned_fixture_client(factory,root):
    """Select the same actual listener inode through the guard's declared name.

    Control canonicalizes /tmp to /private/tmp on Darwin. The already-approved
    guard names /tmp/mm-plan-*/ceo.sock. No alternative endpoint or broad alias
    permission: prove BOTH names address that exact owned socket first.
    """
    import stat
    def current(path,*args,**kwargs):
        target=root/'ceo.sock'
        assert target.samefile(path)
        observed=target.lstat();parent=root.lstat()
        assert stat.S_ISSOCK(observed.st_mode) and observed.st_uid==os.geteuid()
        assert parent.st_uid==os.geteuid() and stat.S_IMODE(parent.st_mode)==0o700 and not stat.S_ISLNK(parent.st_mode)
        return factory(target,*args,**kwargs)
    return current


def test_one_runtime_activity_and_original_result_export(tmp_path,monkeypatch,rsa_key,activity_socket_root):
    if not ORIGINAL_ORIGIN.is_dir():pytest.skip('retained inert canonical Macro source unavailable; no live substitute')
    if not os.environ.get('PROJECT_ACTIVITY_SOURCE_REVISION'):pytest.skip('source-issued exporter needs explicit recorded source revision')
    import tests.test_workspace_read_app as auth_suite
    import tests.test_workspace_admitted_plan_read as plan_suite
    from integrations.mastermind_executive_app.coo_binding import _digest
    from integrations.mastermind_executive_app.os_transport import _context_payload
    from control_plane.coo_principal_host import CooHostProvider
    from dataclasses import replace
    now=int(time.time())
    # NEW fixture inputs use the actual clock before token/source issuance. No
    # deadline monkeypatch or extension of an existing observation is involved.
    monkeypatch.setattr(auth_suite,'NOW',now);monkeypatch.setattr(plan_suite,'NOW',now)
    macro=tmp_path/'canonical-macro'
    subprocess.run(['git','clone','--quiet','--no-hardlinks',str(ORIGINAL_ORIGIN),str(macro)],check=True,cwd=tmp_path)
    git(macro,'checkout','--detach',MACRO_REVISION)
    revision=source_revision(os.environ)
    assert git(macro,'rev-parse','HEAD')==MACRO_REVISION
    canonical=CanonicalFixtureCache(macro,tmp_path,mastermind_revision=revision)
    assert canonical.commit==MACRO_REVISION
    work=canonical.owner.state_cache['doc']['work'][0]['work_ref']
    token=auth_suite._workspace_token(rsa_key)
    principal=asyncio.run(auth_suite._authenticator(rsa_key).verify_authorization_header('Bearer '+token,now=now))
    viewer=principal_frame(principal)
    (tmp_path/'coo').mkdir()
    coo,mutable,_previous,path=coo_fixture(tmp_path/'coo')
    policy=mutable['policy'];policy['issuer']=auth_suite._authenticator(rsa_key).policy.issuer
    policy['authorization_servers']=[policy['issuer']];policy['jwks_uri']=policy['issuer']+'/.well-known/jwks.json'
    policy['allowed_subject_digests']=[viewer['subject_digest']]
    enrolled=mutable['binding']['binding']
    for key in ('issuer_digest','subject_digest','client_ref'):enrolled[key]=viewer[key]
    mutable['missions'][0]['work_ref']=work
    mutable['missions'][0]['principal_binding_digest']=_digest(enrolled)
    membership=coo.source.for_workspace_read_principal
    assert membership(viewer,work)[0]['enabled'] is True
    data=dict(schema='mastermind.project_activity_source_journey.v1',source_revision=revision,
        fixture_scope='DISPOSABLE_RUNTIME_ACTUAL_OHF_WORKSPACE_CANONICAL_COMPILER; SYNTHETIC_PROVIDER_KERNEL_NAMESPACE_AUTH; NOT_LIVE',
        clock=dict(verified_at=now,verified_expiry=principal.expires_at),workspace_context=_context_payload(principal),
        canonical_source=canonical.provenance(),active=None,final=None)
    checkpoint(data)

    def reader(runtime,bounded):
        def authorize(frame):return frame==viewer
        authorize.binding_digest=lambda frame:'f'*64 if frame==viewer else None
        return WorkspaceReadService(cache=canonical.cache,runtime=runtime,authorize=authorize,armed={},runtime_identity={'db_present':True},
            bounded_runtime=lambda actual:bounded if actual is runtime else pytest.fail('foreign Runtime'),activity_membership=membership)
    def local_read(service,operation,selection=None):
        schema=activity.FRAME_SCHEMA if operation==activity.OPERATION else wire.FRAME_SCHEMA_V3 if operation=='admitted_plan' else wire.FRAME_SCHEMA_V2 if operation in ('mission_v3','result','result_references') else wire.FRAME_SCHEMA
        result=asyncio.run(service.handle_frame(dict(schema=schema,operation=operation,selection=selection,principal=viewer)))
        assert result.get('ok') is True,result
        return result

    original=OperatorHarnessRegistry.record_candidate_evidence
    def record_actual_candidate(self,**kw):
        turn=kw['turn']
        # Deterministic synthetic adapter inputs pass through the ACTUAL sole
        # Runtime candidate owner. No SQL insertion, inferred progress or output
        # authority. All private payload fields must be absent from projection.
        kw['events']=tuple(NormalizedEvent(turn.attempt_id,turn.session_epoch_id,turn.process_generation_id,turn.turn_id,kind,
            payload_redacted={'private_command':PRIVATE,'private_output':PRIVATE})for kind in ('item/started','item/completed','turn/completed'))
        original(self,**kw)
        observed=Runtime.at(self.store.root,create=False)
        attempt=observed.attempts.get_attempt(turn.attempt_id);job=observed.jobs.get_job(attempt.job_id)
        if job.orchestration_role!='work':return
        assert attempt.status not in ('COMPLETED','FAILED')
        canonical.publish(observed)
        keeper,namespace,binding,bounded=_bound_reader(observed)
        try:
            service=reader(observed,bounded);pair=dict(work_ref=work,root_job_id=job.root_job_id)
            selected=dict(pair,job_id=job.job_id,attempt_id=attempt.attempt_id)
            data['selection']=pair;data['activity_selection']=selected
            data['active']=dict(programs=local_read(service,'programs'),work=local_read(service,'work'),mission=local_read(service,'mission_v3',pair),
                plan=local_read(service,'admitted_plan',pair),activity=local_read(service,activity.OPERATION,selected),
                result_references=local_read(service,'result_references',pair),job_status=job.status,attempt_status=attempt.status)
            checkpoint(data)
        finally:_release(keeper,binding)
    monkeypatch.setattr(OperatorHarnessRegistry,'record_candidate_evidence',record_actual_candidate)
    runtime,root,work_result,review_result=_all_severity_chain(tmp_path/'runtime',workstream=work)
    assert data['active'] is not None
    keeper,namespace,binding,bounded=_bound_reader(runtime)
    try:
        canonical.publish(runtime)
        owner=dict(writer=runtime,reader=bounded,cache=canonical.cache)
        def service_factory(subject,authorize):
            assert subject is owner
            return WorkspaceReadService(cache=canonical.cache,runtime=runtime,authorize=authorize,armed={},runtime_identity={'db_present':True},
                bounded_runtime=lambda actual:bounded if actual is runtime else pytest.fail('foreign Runtime'),activity_membership=membership)
        monkeypatch.setattr(plan_suite,'service',service_factory)
        original_control=plan_suite.control
        def control_with_actual_coo(tmp,socket_root,factory):
            service=original_control(tmp,socket_root,factory)
            service._ceo_ingress_app_binding=replace(service._ceo_ingress_app_binding,
                principal_facts_factory=lambda actual:CooHostProvider(coo.source,factory(actual)),principal_admission_armed=True,
                principal_admission_guard=lambda envelope:None)
            return service
        monkeypatch.setattr(plan_suite,'control',control_with_actual_coo)
        monkeypatch.setattr(plan_suite,'CeoIngressWorkspaceClient',owned_fixture_client(plan_suite.CeoIngressWorkspaceClient,activity_socket_root))
        selected=dict(work_ref=work,root_job_id=root.job_id,job_id=work_result.job.job_id,attempt_id=work_result.attempt.attempt_id,
            result_envelope_digest=work_result.result_digest)
        assert all(selected[key]==data['activity_selection'][key]for key in data['activity_selection'])
        data['result_selection']=selected
        before=len(runtime.events.list_events())
        async def run():
            async with plan_suite.transport(owner,rsa_key,tmp_path,activity_socket_root)as(http,bearer,slots,seen,client,verified,mounted):
                assert principal_frame(verified)==viewer
                responses={}
                for name,route,selection in [('programs','programs',None),('work','work',None),('mission','mission/v3',data['selection']),
                    ('plan','plan',data['selection']),('activity','operator/activity',data['activity_selection']),
                    ('result_references','result-references',data['selection']),('result','result',selected)]:
                    response=await http.get('/workspace/'+route+'/current',params=selection,headers={'Authorization':'Bearer '+bearer})
                    responses[name]=dict(status=response.status_code,body=response.json())
                    data['final']=responses;checkpoint(data)
                assert all(item['status']==200 for item in responses.values()),{name:item['status']for name,item in responses.items()}
                return responses
        final=asyncio.run(run())
        data['readers_zero_new_events']=len(runtime.events.list_events())==before
        data['counts']=dict(jobs=len(runtime.jobs.list_jobs()),attempts=len(runtime.attempts.list_attempts()),events=len(runtime.events.list_events()))
        data['export_completed']=True
        checkpoint(data)
        assert data['readers_zero_new_events']
        assert PRIVATE not in json.dumps(data)
        assert final['activity']['body']['availability']=='AVAILABLE'
        assert final['result']['body']['availability']=='AVAILABLE'
    finally:_release(keeper,binding)


def test_incumbent_owned_socket_programs_preflight(tmp_path,activity_socket_root,monkeypatch):
    from tests import test_workspace_read_socket as source
    monkeypatch.setattr(source,'CeoIngressWorkspaceClient',owned_fixture_client(source.CeoIngressWorkspaceClient,activity_socket_root))
    source.test_actual_service_programs_reads_exact_cache_and_runtime_is_injected(tmp_path,activity_socket_root)
