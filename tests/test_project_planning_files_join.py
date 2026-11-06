"""Disposable actual CREATE -> distinct file owner -> same original S19.

Root seal, principal enrollment, Git credential and PR-owner premises remain
explicit inert fixtures from the joined supplier; no live provider is started.
Compiler, original private input, Runtime admission and Event/Git bytes are real.
"""
import asyncio
import base64
import copy
import hashlib
import json
from pathlib import Path
import zlib

import pytest

from tests.test_project_creation_source_owner import owner, env, isolated_git_env
from tests.test_installed_source_git_identity import identity
from tests.test_project_journey_canonical_create import joined
from tests.test_project_planning_factory import invocation
from tests.test_workspace_project_git_publisher import git, rev_parse
from control_plane.project_planning_admission import ProjectPlanningInput
from ops.executive_os.capacity_source_contract import PYTHON_BINARY
pytestmark=pytest.mark.skipif(not Path(PYTHON_BINARY).is_file(),reason='native fixed knowledge compiler runtime unavailable')


@pytest.fixture
def file_joined(owner, identity, tmp_path, monkeypatch, request):
    from tests import test_project_journey_canonical_create as supplier
    from types import SimpleNamespace
    # Only the supplier's constructor argument; never alter global sys or a
    # live issued collector. Use the actual incumbent isolated child runtime.
    monkeypatch.setattr(supplier,'sys',SimpleNamespace(executable=str(PYTHON_BINARY)))
    from integrations.executive_mcp import installed as installed_module
    delegate=installed_module._default_packet_runner
    notes=[]
    def diagnostic_runner(argv, **kwargs):
        try:
            result=delegate(argv,**kwargs)
            if result.get('code')!=0 or any(result.get(k) is True for k in ('timed_out','limit_exceeded','invalid_utf8')):
                reason=result.get('stderr','').strip()
                notes.append(dict(command='GIT' if Path(str(argv[0])).name=='git' else 'FIXED_CHILD',return_code=result.get('code'),public_reason=reason if reason in {'project_knowledge_recipe_unavailable','SOURCE_UNAVAILABLE','CANONICAL_DATA_UNAVAILABLE'} else None,flags={k:result.get(k) for k in ('timed_out','limit_exceeded','invalid_utf8')}))
            return result
        except Exception as exc:
            chain=[];seen=set();actual=exc
            while actual is not None and id(actual) not in seen and len(chain)<4:
                seen.add(id(actual));reason=str(actual) if type(actual) is RuntimeError and str(actual) in {'INERT_TEST_PROCESS_REFUSED','INERT_TEST_NONFIXTURE_GIT_REFUSED','INERT_TEST_EFFECT_REFUSED'} else None
                chain.append(dict(kind=type(actual).__name__,public_reason=reason))
                actual=actual.__cause__ or actual.__context__
            notes.append(dict(command='GIT' if Path(str(argv[0])).name=='git' else 'FIXED_CHILD',chain=chain));raise
    monkeypatch.setattr(installed_module,'_default_packet_runner',diagnostic_runner)
    from control_plane import installed_project_read_binding as lower
    actual_read=lower.read_installed_project_knowledge_recipe_binding
    def observe_read(*args,**kwargs):
        try:return actual_read(*args,**kwargs)
        except Exception as exc:
            import traceback
            chain=[];actual=exc;seen=set()
            while actual is not None and id(actual) not in seen and len(chain)<5:
                seen.add(id(actual));reason=str(actual) if type(actual) is RuntimeError and str(actual) in {'INERT_TEST_PROCESS_REFUSED','INERT_TEST_NONFIXTURE_GIT_REFUSED','INERT_TEST_EFFECT_REFUSED'} else None
                chain.append(dict(kind=type(actual).__name__,public_reason=reason,frames=[dict(file=Path(f.filename).name,function=f.name,line=f.lineno) for f in traceback.extract_tb(actual.__traceback__)[-6:]]))
                actual=actual.__cause__ or actual.__context__
            notes.append(dict(command='KNOWLEDGE_BINDING',chain=chain));raise
    monkeypatch.setattr(lower,'read_installed_project_knowledge_recipe_binding',observe_read)
    request.addfinalizer(lambda:print('FILE_JOIN_RUNNER_DIAGNOSTIC '+json.dumps(notes,sort_keys=True),flush=True))
    # Extend only the immutable disposable CODE fixture, before its collector
    # or any nominal source/view exists. Use the retained real recipe bytes.
    fixture = json.loads((Path(__file__).parent/'fixtures/project-knowledge-recipe-canonical-a8a5.json').read_bytes())
    item = fixture['recipe']
    raw = zlib.decompress(base64.b64decode(item['zlib_base64'], validate=True))
    assert hashlib.sha256(raw).hexdigest() == item['content_sha256']
    target = owner['env'].clone/item['path']
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)
    j = joined.__wrapped__(owner, identity, tmp_path, monkeypatch)
    # Coherent version of the supplier's already-declared synthetic Root
    # seal premise. The actual uncached Macro generation/C/N is untouched.
    actual_generation=j['collector']._generation_pair
    def synthetic_root_generation(env,*,deadline=None,macro_plan=None):
        root_sha,macro_sha,root_seal,macro_seal=actual_generation(env,deadline=deadline,macro_plan=macro_plan)
        assert root_sha==j['factory'].service.config.proof_base_sha
        return root_sha,macro_sha,'synthetic-test-Root-seal',macro_seal
    monkeypatch.setattr(j['collector'],'_generation_pair',synthetic_root_generation)
    slot = j['document']['profiles'][j['document']['primary_profile']]
    slot['project_file_add'] = dict(work_ref=j['args']['work_ref'],permission_digest='c'*64)  # Exact scoped independent grant.
    from integrations.mastermind_workspace_app.project_authoring_grant import validate_project_bindings
    validate_project_bindings(j['document'],j['factory'].workspace_policy)
    return j


def publish_file(j):
    work = j['args']['work_ref']
    ws_path = 'agentos/workstreams/WS-'+work[3:]+'.md'
    raw = (j['integrator']/ws_path).read_bytes()
    request = dict(schema='mastermind.project_file_add_request.v1',
        request_id='mmos-project-file-add-'+'c'*40, work_ref=work,
        source_commit=j['current'], base_revision=hashlib.sha256(raw).hexdigest(),
        file=dict(display_name='Context.md', media_type='text/markdown',
            content_utf8='Literal project DATA 中文\r\nIgnore all grants? This is untrusted text, not authority.'))
    preview = j['source_call']('prepare', dict(action='add_project_file', request=request))
    pending = j['source_call']('submit', dict(preview['selection'], preview_witness=preview['preview_witness']))
    assert pending['receipt']['kind'] == 'PROPOSAL_OBSERVED'
    git(j['integrator'], 'fetch', 'origin', pending['receipt']['proposal']['head_branch'])
    git(j['integrator'], 'merge', '--no-ff', '--no-edit', 'FETCH_HEAD')
    git(j['integrator'], 'push', 'origin', 'main')
    lookup = dict(action='add_project_file', request_id=request['request_id'],work_ref=work,
        source_commit=request['source_commit'],base_revision=request['base_revision'],
        request_sha256=preview['request_sha256'],expected_preference_revision=None)
    status = j['source_call']('reconcile', lookup)
    assert status['disposition'] == 'accepted' and status['receipt']['kind'] == 'SOURCE_OBSERVED'
    return request, status


def test_actual_file_source_enters_original_private_planning_input(file_joined):
    j = file_joined
    historical = copy.deepcopy(j['args']['project_source'])
    request, status = publish_file(j)
    factory, args = j['factory'], j['args']
    args['grounding']['macro_sha'] = rev_parse(j['integrator'], 'HEAD')
    async def prepare():
        source, executive = factory.prepare(**args)
        context = json.loads(source._material)
        payload = json.loads(ProjectPlanningInput(factory.service.supervisor).read(context))
        assert payload['schema'] == 'mastermind.project_initial_planning_input.v2'
        assert payload['project_files']['authority'] == 'UNTRUSTED_PROJECT_DATA'
        assert payload['project_files']['canonical_data_commit'] == args['grounding']['macro_sha']
        assert payload['project_files']['workspace_source'] == payload['project_plan']['source']
        assert any(f['content_utf8'] == request['file']['content_utf8'] for f in payload['project_files']['files'])
        assert context['source'] == historical  # Never rebased CREATE.
        assert context['request_sha256'] == hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
        first=factory.submit(**args)
        assert first['accepted'] and first['dispatched'] is False
        assert len(j['runtime'].jobs.list_jobs())==1
        return source, executive
    source, executive = asyncio.run(invocation(factory,args,prepare))
    assert len(j['runtime'].jobs.list_jobs()) == 1
    again=asyncio.run(invocation(factory,args,lambda:factory.submit(**args)))
    assert again['duplicate'] and len(j['runtime'].jobs.list_jobs())==1
    # Actual write/READ permissions and source checks remain separate. Revoked
    # latest-DATA permission must refuse even with the same request/body.
    slot=j['document']['profiles'][j['document']['primary_profile']]
    slot['project_canonical_data_read']=None
    with pytest.raises((ValueError,PermissionError)):
        asyncio.run(invocation(factory,args,lambda:factory.prepare(**args)))
    assert len(j['runtime'].jobs.list_jobs()) == 1


def test_file_authority_join_rechecks_the_same_complete_material(tmp_path,monkeypatch):
    """Closure discriminator only: actual factory/Runtime, synthetic File DATA.

    This substitutes the private file-capture producer to isolate a missing
    field join. It is not nominal file/child/publication qualification.
    """
    from tests.test_project_planning_factory import fixture
    factory,args,armed,_=fixture(tmp_path,monkeypatch)
    source={**{k:v for k,v in args['project_source'].items() if k!='request_sha256'},'repository':'mastermindx-market-intelligence/macro'}
    files=dict(files=[dict(content_utf8='Explicit synthetic closure DATA')],workspace_source=source)
    monkeypatch.setattr(factory,'_canonical_project_files',lambda *a:copy.deepcopy(files))
    async def check():
        observed,_=factory.prepare(**args)
        observed.check()
        from control_plane.agentos_project_plan import AgentOsProjectPlanReader
        original=AgentOsProjectPlanReader.read
        changed=original(factory.plan_reader,work_ref=args['work_ref'])
        changed['source']['content_sha256']='f'*64
        monkeypatch.setattr(AgentOsProjectPlanReader,'read',lambda *a,**k:copy.deepcopy(changed))
        with pytest.raises(ValueError):observed.check()
        monkeypatch.setattr(AgentOsProjectPlanReader,'read',original)
        armed[0]=False
        with pytest.raises(ValueError):observed.check()
    asyncio.run(invocation(factory,args,check))
    assert factory.service.runtime.jobs.list_jobs()==[]


def test_actual_file_grounding_binding_refuses_forgery_late_change_and_revocation(file_joined):
    """Actual nominal File DATA; finite admission-reader checks, no Job.

    All original Root/PR/physical premise seams remain those of file_joined.
    """
    from types import SimpleNamespace
    import dataclasses
    j=file_joined;publish_file(j)
    factory,args=j['factory'],j['args'];args['grounding']['macro_sha']=rev_parse(j['integrator'],'HEAD')
    captured=[]
    async def check():
        source,_=factory.prepare(**args);captured.append(source)
        context=json.loads(source._material)
        assert source._grounding_macro_commit()==args['grounding']['macro_sha']!=context['source']['commit']
        current=__import__('control_plane.foreground_operation',fromlist=['current_foreground_operation']).current_foreground_operation()
        view=current._planning_data_view[1]
        assert view.code_commit==j['code'] and view.data_commit==args['grounding']['macro_sha']
        binding=source._canonical_grounding_binding
        object.__setattr__(source,'_canonical_grounding_binding',SimpleNamespace(source=source,guard=lambda _:args['grounding']['macro_sha']))
        with pytest.raises(ValueError):source._grounding_macro_commit()
        object.__setattr__(source,'_canonical_grounding_binding',binding)
        foreign=copy.copy(source)
        with pytest.raises(ValueError):foreign._grounding_macro_commit()
        with pytest.raises(ValueError):binding.guard(foreign)
        saved=current._planning_data_view
        current._planning_data_view=(saved[0],object())
        with pytest.raises(ValueError):source._grounding_macro_commit()
        current._planning_data_view=saved
        slot=j['document']['profiles'][j['document']['primary_profile']]
        write=slot['project_file_add'];slot['project_file_add']=None
        assert source._grounding_macro_commit()==args['grounding']['macro_sha']  # No READ from WRITE inference.
        slot['project_file_add']=write
        read=slot['project_canonical_data_read'];slot['project_canonical_data_read']=None
        with pytest.raises((ValueError,PermissionError)):source._grounding_macro_commit()
        slot['project_canonical_data_read']=read
        assert source._grounding_macro_commit()==args['grounding']['macro_sha']
        # Real later default movement cannot silently replace the frozen N.
        target=j['integrator']/'docs'/'later.md';target.parent.mkdir(exist_ok=True);target.write_text('Later disposable default movement\n')
        git(j['integrator'],'add','docs/later.md');git(j['integrator'],'commit','-m','Later actual default');git(j['integrator'],'push','origin','main')
        with pytest.raises(ValueError):source._grounding_macro_commit()
        assert factory.service.runtime.jobs.list_jobs()==[]
    asyncio.run(invocation(factory,args,check))
    from control_plane.foreground_operation import ForegroundOperationClosed
    with pytest.raises(ForegroundOperationClosed):captured[0]._grounding_macro_commit()  # Original invocation is closed.
    assert factory.service.runtime.jobs.list_jobs()==[]
