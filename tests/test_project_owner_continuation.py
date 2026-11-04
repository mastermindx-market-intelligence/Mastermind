"""Portable read-only owner projection; every owner/task fact here is inert fixture DATA."""
import copy
import hashlib
import io
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from integrations.session_bridge import project_owner_continuation as api

NOW = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)
WS = 'WS:FIXTURE'


def document():
    return {'schema': 'mm.harness.tasks', 'schema_version': '2.0.0',
        'project': 'fixture', 'workstream': WS, 'updated': '2026-11-02T12:00:00Z',
        'agentos': {'source_sha':'b'*40,'ws_status':'active','records':[{'workstream':WS,'record':'agentos/workstreams/WS-FIXTURE.md','exists':True,'status':'active'}]}, 'waves': [{'p':'P1','id':'delivery','workstream':WS,
            'status':'in_progress','source':'agentos','next_action':'execute arbitrary prose'}],
        'tasks': [{'id':'P1.T1','kind':'task','parent':None,'workstream':WS,
            'wave':'delivery','owner':'fixture-owner','status':'ready','depends_on':[],
            'acceptance':['source assertion'],'evidence':None,'superseded_by':[],
            'reason':None,'notes':[],'updated':'2026-11-02T12:00:00Z','history':[]}]}


def bundle():
    return {'schema':'context_bundle.v1','target':{'workstream':WS},
        'source_records_digest':'sha256:'+'a'*64,'generated_at':'2026-11-02T12:00:00Z',
        'repo_sha':'b'*40,'no_answer_reason':None,
        'sections':[{'id':'workstream','items':[{'kind':'workstream','key':WS,'status':'active','path':'agentos/workstreams/WS-FIXTURE.md','excerpt':'original objective and waves'}]},
                    {'id':'handoff','items':[{'kind':'handoff','path':'agentos/handoffs/WS-FIXTURE-2026-11-02.md','excerpt':'latest handoff'}]},
                    {'id':'artifacts','items':[{'kind':'artifact','path':'research/ORIGINAL_PLAN.md','excerpt':'original plan reference'}]}],
        'excluded':[],'omitted_due_to_budget':[],'degraded':[]}


def project(db=None, b=None):
    return api.project_tasks(document() if db is None else db, bundle() if b is None else b,
        workstream=WS, owner='fixture-owner', now=NOW)


def test_one_candidate_is_inert_and_exact_existing_selector_is_used(monkeypatch):
    selector=api.load_selector()
    calls=[]
    actual=selector['next_tasks']
    selector['next_tasks']=lambda db:(calls.append('next_tasks') or actual(db))
    monkeypatch.setattr(api,'load_selector',lambda:selector)
    db=document();before=copy.deepcopy(db)
    result=project(db)
    assert result['state']=='CANDIDATE' and result['candidate']['task_id']=='P1.T1'
    assert result['action_recommendation'] is False
    assert result['effect_eligibility']=='UNOBSERVED'
    assert db==before and calls==['next_tasks']
    assert 'execute arbitrary prose' not in json.dumps(result)


@pytest.mark.parametrize('change', ['empty','unbound','legacy','missing'])
def test_recovery_only_does_not_manufacture_tasks(change):
    db=document()
    if change=='empty':db['tasks']=[]
    if change=='unbound':db['workstream']=None
    if change=='legacy':db['schema_version']='1.0.0'
    if change=='missing':db=None
    result=api.project_tasks(db,bundle(),workstream=WS,owner='fixture-owner',now=NOW)
    assert result['state']=='RECOVER_CONTEXT' and result['candidate'] is None
    assert result['action_recommendation'] is False


@pytest.mark.parametrize('field,value', [('status','in_progress'),('status','accepted'),
    ('status','superseded'),('status','blocked'),('status','unknown'),
    ('owner',None),('owner','other-owner'),('owner',['fixture-owner','other']),
    ('reason','EFFECT_UNKNOWN'),('reason','explicit STOP'),
    ('superseded_by',['P1.T2']),('workstream','WS:FOREIGN'),
    ('updated','2026-10-01T12:00:00Z'),('updated','2026-11-03T12:00:00Z')])
def test_noneligible_facts_never_recommend_or_select(field,value):
    db=document();db['tasks'][0][field]=value
    result=project(db)
    assert result['candidate'] is None and result['action_recommendation'] is False


@pytest.mark.parametrize('change', ['two-ready','duplicate','missing-dep','open-child','done-wave','missing-wave','foreign-wave','unknown-wave','bad-source','bad-digest'])
def test_ambiguity_and_unqualified_source_preserve_no_action(change):
    db=document();b=bundle()
    if change in ('two-ready','duplicate'):
        row=copy.deepcopy(db['tasks'][0]);row['id']='P1.T2' if change=='two-ready' else 'P1.T1';db['tasks'].append(row)
    elif change=='missing-dep':db['tasks'][0]['depends_on']=['P1.T9']
    elif change=='open-child':
        row=copy.deepcopy(db['tasks'][0]);row.update(id='P1.T1.S1',parent='P1.T1',owner='other-owner',status='blocked');db['tasks'].append(row)
    elif change=='done-wave':db['waves'][0]['status']='done'
    elif change=='missing-wave':db['waves']=[]
    elif change=='foreign-wave':db['waves'][0]['workstream']='WS:FOREIGN'
    elif change=='unknown-wave':db['waves'][0]['source']='agentos-missing'
    elif change=='bad-source':b['target']['workstream']='WS:FOREIGN'
    else:b['source_records_digest']='not-qualified'
    assert project(db,b)['candidate'] is None


@pytest.mark.parametrize('bad_id', ['P00.T1','P01.T1','P0.T0','P0.T01','P0.T1.S0','P0.T1.S01',
    'P0T1','p0.T1','P0.','P0.Tx1','Px.T1','P1.T0','P1.T1.S0','P0.T1.S2.S3'])
def test_p0_grammar_rejects_leading_zero_and_malformed_ids(bad_id):
    db=document();db['tasks'][0]['id']=bad_id
    result=project(db)
    assert result['state']=='NO_CANDIDATE' and result['reason']=='TASK_IDENTITY_AMBIGUOUS'
    assert result['candidate'] is None
    assert result['action_recommendation'] is False and result['effect_eligibility']=='UNOBSERVED'


def test_duplicate_p0_identity_stays_ambiguous():
    db=document();db['tasks'][0]['id']='P0.T1'
    archived=copy.deepcopy(db['tasks'][0]);archived.update(status='accepted',owner='fixture-owner')
    db['tasks'].append(archived)
    result=project(db)
    assert result['state']=='NO_CANDIDATE' and result['reason']=='TASK_IDENTITY_AMBIGUOUS'
    assert result['candidate'] is None and result['action_recommendation'] is False


def test_archived_p0_history_preserves_unique_ready_p1_candidate():
    db=document()
    db['waves'].append({'p':'P0','id':'bootstrap','workstream':WS,'status':'done','source':'agentos'})
    for task_id in ('P0.T1','P0.T2','P0.T3'):
        archived=copy.deepcopy(db['tasks'][0])
        archived.update(id=task_id,wave='bootstrap',status='accepted',owner='fixture-owner')
        db['tasks'].append(archived)
    assert [t['id'] for t in db['tasks']]==['P1.T1','P0.T1','P0.T2','P0.T3']
    result=project(db)
    assert result['state']=='CANDIDATE' and result['candidate']['task_id']=='P1.T1'
    assert result['candidate']['workstream']==WS
    assert result['action_recommendation'] is False and result['effect_eligibility']=='UNOBSERVED'


def test_ready_p0_task_and_subtask_qualify_under_existing_conditions():
    db=document()
    db['waves'][0].update(p='P0',id='bootstrap')
    db['tasks'][0].update(id='P0.T4',wave='bootstrap')
    for task_id in ('P0.T1','P0.T2','P0.T3'):
        archived=copy.deepcopy(db['tasks'][0])
        archived.update(id=task_id,wave='bootstrap',status='accepted',owner='fixture-owner')
        db['tasks'].append(archived)
    assert project(db)['candidate']['task_id']=='P0.T4'
    sub=copy.deepcopy(db)
    sub['tasks'][0].update(id='P0.T1.S2',parent='P0.T1',depends_on=[])
    result=project(sub)
    assert result['state']=='CANDIDATE' and result['candidate']['task_id']=='P0.T1.S2'
    assert result['action_recommendation'] is False and result['effect_eligibility']=='UNOBSERVED'


@pytest.mark.parametrize('task_id', ['P0.T1','P0.T10','P0.T3.S2','P0.T12.S7'])
def test_positive_p0_id_families_still_qualify(task_id):
    db=document()
    if task_id.count('.')==2:
        parent_id=task_id.rsplit('.',1)[0]
        db['tasks'][0].update(id=task_id,parent=parent_id)
        parent=copy.deepcopy(db['tasks'][0])
        parent.update(id=parent_id,status='accepted',owner='fixture-owner')
        db['tasks'].append(parent)
    else:
        db['tasks'][0]['id']=task_id
    assert project(db)['candidate']['task_id']==task_id
    assert project(db)['action_recommendation'] is False


def test_blocked_accepted_and_in_progress_p0_rows_never_become_candidates():
    db=document()
    db['waves'].append({'p':'P0','id':'bootstrap','workstream':WS,'status':'in_progress','source':'agentos'})
    blocked=copy.deepcopy(db['tasks'][0])
    blocked.update(id='P0.T1',wave='bootstrap',status='blocked',owner='fixture-owner',reason='EFFECT_UNKNOWN')
    accepted=copy.deepcopy(db['tasks'][0])
    accepted.update(id='P0.T2',wave='bootstrap',status='accepted',owner='fixture-owner')
    db['tasks'] += [blocked,accepted]
    result=project(db)
    assert result['state']=='CANDIDATE' and result['candidate']['task_id']=='P1.T1'
    assert result['action_recommendation'] is False
    active=copy.deepcopy(db['tasks'][0])
    active.update(id='P0.T3',wave='bootstrap',status='in_progress',owner='fixture-owner')
    db['tasks'].append(active)
    result=project(db)
    assert result['state']=='NO_CANDIDATE' and result['reason']=='OWNER_ALREADY_STARTED'
    assert result['candidate'] is None and result['action_recommendation'] is False


def test_semantic_identity_stable_across_time_and_raw_bundle_regeneration():
    first=project();b=bundle();b['generated_at']='2026-11-02T12:01:00Z'
    assert project(b=b)['candidate']==first['candidate']
    db=document();db['agentos']['source_sha']='c'*40;b['repo_sha']='c'*40
    assert project(db,b)['candidate']==first['candidate']
    for change in ('evidence','source','task'):
        db=document();b=bundle()
        if change=='evidence':db['tasks'][0]['evidence']='source:new-evidence'
        if change=='source':b['source_records_digest']='sha256:'+'c'*64
        if change=='task':db['tasks'][0]['id']='P1.T2'
        assert project(db,b)['candidate']['identity']!=first['candidate']['identity']
    db=document();db['tasks'][0]['status']='in_progress'
    assert project(db)['candidate'] is None


def reader(workstream,budget,*,owner_root):
    raw=json.dumps(bundle()).encode()
    return raw,{'workstream':WS,'execution_authority':False,'bundle_sha256':hashlib.sha256(raw).hexdigest()}


def test_active_turn_cli_does_not_forge_sessionstart_or_write(tmp_path):
    charter=tmp_path/'charter';charter.mkdir()
    (charter/'TASKS.json').write_text(json.dumps(document()))
    (charter/'HANDOFF.md').write_text('existing retained handoff')
    before={x.name:x.read_bytes() for x in charter.iterdir()}
    out=io.StringIO()
    result=api.main(['--workspace-root',str(tmp_path),'--charter-root',str(charter),
        '--macro-root',str(tmp_path),'--workstream',WS,'--owner','fixture-owner',
        '--owner-session','original-session'],stdout=out,reader=reader,
        environ={'CODEX_THREAD_ID':'original-session'},cwd=tmp_path,now=NOW)
    body=json.loads(out.getvalue())
    assert result==0 and body['projection']['candidate']['task_id']=='P1.T1'
    assert body['entrypoint']=='active_owner_boundary'
    assert body['projection']['action_recommendation'] is False
    assert before=={x.name:x.read_bytes() for x in charter.iterdir()}
    assert 'original objective' in json.dumps(body['context_bundle']) and 'latest handoff' in json.dumps(body['context_bundle'])
    assert 'ORIGINAL_PLAN.md' in json.dumps(body['context_bundle'])


@pytest.mark.parametrize('observed', ['foreign-session',None])
def test_wrong_or_missing_native_owner_never_reads_or_projects(tmp_path,observed):
    calls=[];out=io.StringIO()
    def forbidden(*a,**k):calls.append(True);raise AssertionError
    api.main(['--workspace-root',str(tmp_path),'--charter-root',str(tmp_path),
        '--macro-root',str(tmp_path),'--workstream',WS,'--owner','fixture-owner',
        '--owner-session','original-session'],stdout=out,reader=forbidden,
        environ={} if observed is None else {'CODEX_THREAD_ID':observed},cwd=tmp_path,now=NOW)
    assert calls==[] and json.loads(out.getvalue())['projection']['candidate'] is None


def test_selector_payload_hash_drift_refuses_before_execution(tmp_path):
    p=tmp_path/'mmtask';p.write_text("raise AssertionError('must not execute')")
    with pytest.raises(api.ProjectionUnavailable,match='SELECTOR_SOURCE_UNQUALIFIED'):
        api.load_selector(p)


def test_resume_uses_same_projection_only_on_actual_protocol_focus(tmp_path,monkeypatch):
    from integrations.session_bridge import agentos_session_start as hook
    calls=[]
    def collect(**kwargs):
        calls.append(kwargs)
        return {'projection':{'candidate':None,'action_recommendation':False}}
    monkeypatch.setattr(api,'collect_context',collect)
    event={'hook_event_name':'SessionStart','source':'resume','session_id':'original-session','cwd':str(tmp_path)}
    options={'workspace_root':tmp_path,'workstream':WS,'owner_root':tmp_path,
        'owner_session':'original-session','owner':'fixture-owner','charter_root':tmp_path}
    body=hook.session_start_context(event,**options)
    text=json.loads(body['hookSpecificOutput']['additionalContext'])
    assert text['entrypoint']=='original_owner_resume'
    assert calls[0]['observed_session']=='original-session'
    assert text['projection']['action_recommendation'] is False
    for source in ('startup','compact','fork','clear'):
        assert hook.session_start_context(dict(event,source=source),**options)=={}
    assert len(calls)==1


def test_read_file_replacement_and_symlink_never_become_task_facts(tmp_path):
    real=tmp_path/'real';real.write_text('fixture')
    link=tmp_path/'link';link.symlink_to(real)
    with pytest.raises(OSError):api._read(link)
    with pytest.raises(api.ProjectionUnavailable):api._read(real,2)


def test_missing_or_blank_local_handoff_retains_passive_canonical_recovery(tmp_path):
    (tmp_path/'TASKS.json').write_text(json.dumps(document()))
    result=api.collect_context(workspace_root=tmp_path,observed_workspace=tmp_path,
        owner_session='original-session',observed_session='original-session',
        workstream=WS,owner='fixture-owner',charter_root=tmp_path,macro_root=tmp_path,
        reader=reader,now=NOW)
    assert result['projection']['state']=='RECOVER_CONTEXT'
    assert 'latest handoff' in json.dumps(result['context_bundle'])
    assert result['projection']['action_recommendation'] is False


def test_fifo_charter_read_is_bounded_before_data_observation(tmp_path):
    import os
    import subprocess
    import sys
    fifo=tmp_path/'TASKS.json';os.mkfifo(fifo)
    code='from integrations.session_bridge.project_owner_continuation import _read, ProjectionUnavailable\nimport sys\ntry: _read(sys.argv[1])\nexcept ProjectionUnavailable: pass\nelse: raise AssertionError("FIFO was qualified")'
    subprocess.run([sys.executable,'-B','-c',code,str(fifo)],cwd=Path(__file__).resolve().parents[1],timeout=2,check=True)


@pytest.mark.parametrize('change',['old-import','closed-canonical','owner-generation-change','missing-import-record'])
def test_fresh_local_ready_cannot_reopen_changed_canonical_import(change):
    db=document();b=bundle()
    if change in ('old-import','owner-generation-change'): b['repo_sha']='c'*40
    elif change=='closed-canonical': b['sections'][0]['items'][0]['status']='superseded'
    else: db['agentos']['records']=[]
    assert project(db,b)['candidate'] is None


def test_unrelated_hold_and_historical_handoff_label_are_not_global_task_authority():
    db=document();blocked=copy.deepcopy(db['tasks'][0])
    blocked.update(id='P1.T2',status='blocked',reason='EFFECT_UNKNOWN',owner='other-owner')
    db['tasks'].append(blocked);b=bundle();b['sections'][1]['items'][0]['status']='blocked'
    result=project(db,b)
    assert result['candidate']['task_id']=='P1.T1'
    assert result['action_recommendation'] is False


@pytest.mark.parametrize('which',['TASKS.json','HANDOFF.md'])
@pytest.mark.parametrize('entry',['boundary','resume'])
def test_fifo_never_blocks_either_normal_context_entry(tmp_path,which,entry):
    import os
    import subprocess
    import sys
    charter=tmp_path/'charter';charter.mkdir()
    for name,body in [('TASKS.json',json.dumps(document())),('HANDOFF.md','existing handoff')]:
        if name==which:os.mkfifo(charter/name)
        else:(charter/name).write_text(body)
    code='''import hashlib,json,sys
from pathlib import Path
from integrations.session_bridge import project_owner_continuation as api
from integrations.session_bridge import agentos_session_start as hook
workspace,charter,entry=map(str,sys.argv[1:])
b=json.loads(sys.stdin.read())
def reader(*args,**kwargs):
 raw=json.dumps(b).encode();return raw,{'workstream':'WS:FIXTURE','execution_authority':False,'bundle_sha256':hashlib.sha256(raw).hexdigest()}
kw=dict(workspace_root=workspace,workstream='WS:FIXTURE',owner_session='original-session',owner='fixture-owner',charter_root=charter,reader=reader)
if entry=='boundary':
 r=api.collect_context(**kw,macro_root=workspace,observed_workspace=workspace,observed_session='original-session')
else:
 r=hook.session_start_context({'hook_event_name':'SessionStart','source':'resume','session_id':'original-session','cwd':workspace},**kw,owner_root=workspace)
 r=json.loads(r['hookSpecificOutput']['additionalContext'])
assert r['projection']['candidate'] is None
assert r['projection']['action_recommendation'] is False
'''
    subprocess.run([sys.executable,'-B','-c',code,str(tmp_path),str(charter),entry],
        cwd=Path(__file__).resolve().parents[1],input=json.dumps(bundle()),text=True,timeout=2,check=True)


def test_projection_cannot_write_start_or_dispatch(monkeypatch):
    import os
    import subprocess
    calls=[]
    def forbidden(*a,**k):calls.append(True);raise AssertionError('projection effect')
    real_open=os.open
    def readonly(path,flags,*args,**kwargs):
        assert not flags & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC)
        return real_open(path,flags,*args,**kwargs)
    monkeypatch.setattr(os,'open',readonly)
    monkeypatch.setattr(os,'replace',forbidden)
    monkeypatch.setattr(subprocess,'Popen',forbidden)
    monkeypatch.setattr(Path,'write_text',forbidden)
    result=project()
    assert result['candidate']['task_id']=='P1.T1' and not calls
    assert result['action_recommendation'] is False


def test_complete_delivery_bound_includes_owner_metadata(tmp_path,monkeypatch):
    from integrations.session_bridge import agentos_session_start as hook
    body={'context_bundle':'','projection':{'candidate':None,'action_recommendation':False}}
    body['context_bundle']='x'*(api.MAX_CONTEXT_BYTES-len(json.dumps(body,sort_keys=True,ensure_ascii=False).encode()))
    assert len(json.dumps(body,sort_keys=True,ensure_ascii=False).encode())==api.MAX_CONTEXT_BYTES
    monkeypatch.setattr(api,'collect_context',lambda **kw:copy.deepcopy(body))
    output=hook.session_start_context({'hook_event_name':'SessionStart','source':'resume',
        'session_id':'original-session','cwd':str(tmp_path)},workspace_root=tmp_path,
        workstream=WS,owner_root=tmp_path,charter_root=tmp_path,owner='fixture-owner',
        owner_session='original-session')
    text=output['hookSpecificOutput']['additionalContext']
    assert len(text.encode())<=api.MAX_CONTEXT_BYTES
    result=json.loads(text)
    assert result['projection']['candidate'] is None
    assert result['projection']['reason']=='CONTEXT_DELIVERY_TOO_LARGE'
    assert 'context_bundle' not in result


def test_private_rehearsal_guard_refuses_fetch_and_foreign_repository(tmp_path):
    """A swallowed pull failure is visible, and the Git backend never runs."""
    import json
    import os
    import subprocess

    from integrations.session_bridge.rehearse_project_owner import install_read_guard

    private = tmp_path / 'private'
    bin_dir = private / 'bin'
    bin_dir.mkdir(parents=True)
    foreign = tmp_path / 'foreign'
    foreign.mkdir()
    log = private / 'calls.jsonl'
    never_executed = private / 'missing-backend'
    install_read_guard(bin_dir, str(never_executed), private, log)
    for args in (['pull'], ['-C', str(foreign), 'log'], ['show', '--output=outside']):
        result = subprocess.run([bin_dir / 'git', *args], cwd=private,
                                env={'PATH': os.defpath}, capture_output=True)
        assert result.returncode == 77, result.stderr
    assert [json.loads(line) for line in log.read_text().splitlines()] == [
        {'command': 'rejected', 'allowed': False}] * 3


def big_bundle_reader(padding):
    def reader(workstream, budget, *, owner_root):
        b = bundle()
        b['sections'][1]['items'][0]['excerpt'] = 'latest handoff ' + 'h' * padding
        raw = json.dumps(b).encode()
        return raw, {'workstream': workstream, 'execution_authority': False,
            'bundle_sha256': hashlib.sha256(raw).hexdigest()}
    return reader


def test_canonical_mandatory_body_above_legacy_bound_survives_collect_and_resume(tmp_path):
    charter = tmp_path / 'charter'; charter.mkdir()
    (charter / 'TASKS.json').write_text(json.dumps(document()))
    (charter / 'HANDOFF.md').write_text('existing retained handoff')
    b = bundle()
    b['sections'][0]['items'][0]['excerpt'] = 'original objective and waves ' + 'm' * (45 * 1024)
    b['omitted_due_to_budget'] = [{'path': 'research/OMITTED_PLAN.md', 'tokens': 1000}]
    b['degraded'] = ['mandatory context exceeds the requested packing budget']
    b['excluded'] = [{'key': 'WS:UNRELATED', 'reason': 'outside focus'}]
    raw = json.dumps(b).encode()
    assert 32 * 1024 < len(raw) <= api.MAX_BUNDLE_BYTES
    def reader(workstream, budget, *, owner_root):
        return raw, {'workstream': workstream, 'execution_authority': False,
            'bundle_sha256': hashlib.sha256(raw).hexdigest()}
    result = api.collect_context(workspace_root=tmp_path, observed_workspace=tmp_path,
        owner_session='original-session', observed_session='original-session',
        workstream=WS, owner='fixture-owner', charter_root=charter, macro_root=tmp_path,
        reader=reader, now=NOW)
    assert result['projection']['candidate']['task_id'] == 'P1.T1'
    assert result['context_bundle'] == b
    assert result['context_bundle']['omitted_due_to_budget'] == b['omitted_due_to_budget']
    assert result['context_bundle']['degraded'] == b['degraded']
    assert [s['id'] for s in result['context_bundle']['sections']] == ['workstream', 'handoff', 'artifacts']
    out = io.StringIO()
    assert api.main(['--workspace-root', str(tmp_path), '--charter-root', str(charter),
        '--macro-root', str(tmp_path), '--workstream', WS, '--owner', 'fixture-owner',
        '--owner-session', 'original-session'], stdout=out, reader=reader,
        environ={'CODEX_THREAD_ID': 'original-session'}, cwd=tmp_path, now=NOW) == 0
    delivered = json.loads(out.getvalue())
    assert delivered['projection']['candidate']['task_id'] == 'P1.T1'
    assert delivered['context_bundle'] == b
    assert 32 * 1024 < len(out.getvalue().encode()) <= api.MAX_CONTEXT_BYTES
    from integrations.session_bridge import agentos_session_start as hook
    fresh = document()
    stamp = datetime.now(timezone.utc).isoformat()
    fresh['updated'] = stamp; fresh['tasks'][0]['updated'] = stamp
    (charter / 'TASKS.json').write_text(json.dumps(fresh))
    output = hook.session_start_context({'hook_event_name': 'SessionStart',
        'source': 'resume', 'session_id': 'original-session', 'cwd': str(tmp_path)},
        workspace_root=tmp_path, workstream=WS, owner_root=tmp_path,
        charter_root=charter, owner='fixture-owner', owner_session='original-session',
        reader=reader)
    text = output['hookSpecificOutput']['additionalContext']
    assert 32 * 1024 < len(text.encode()) <= api.MAX_CONTEXT_BYTES
    assert json.loads(text)['context_bundle'] == b
    assert json.loads(text)['projection']['candidate']['task_id'] == 'P1.T1'


def test_near_upstream_max_bundle_still_delivers_complete(tmp_path):
    charter = tmp_path / 'charter'; charter.mkdir()
    (charter / 'TASKS.json').write_text(json.dumps(document()))
    (charter / 'HANDOFF.md').write_text('existing retained handoff')
    reader = big_bundle_reader(api.MAX_BUNDLE_BYTES - 4 * 1024)
    result = api.collect_context(workspace_root=tmp_path, observed_workspace=tmp_path,
        owner_session='original-session', observed_session='original-session',
        workstream=WS, owner='fixture-owner', charter_root=charter, macro_root=tmp_path,
        reader=reader, now=NOW)
    raw, _ = reader(WS, 4000, owner_root=tmp_path)
    assert api.MAX_BUNDLE_BYTES - 8 * 1024 < len(raw) <= api.MAX_BUNDLE_BYTES
    assert result['projection']['candidate']['task_id'] == 'P1.T1'
    assert result['context_bundle'] == json.loads(raw)
    assert len(json.dumps(result, ensure_ascii=False).encode()) <= api.MAX_CONTEXT_BYTES


def test_oversize_owner_metadata_fails_closed_under_real_constants(tmp_path):
    raw = json.dumps(bundle()).encode()
    noise = 'y' * (api.METADATA_ALLOWANCE_BYTES + 2048)
    def reader(workstream, budget, *, owner_root):
        return raw, {'workstream': workstream, 'execution_authority': False,
            'bundle_sha256': hashlib.sha256(raw).hexdigest(), 'projection_padding': noise}
    result = api.collect_context(workspace_root=tmp_path, observed_workspace=tmp_path,
        owner_session='original-session', observed_session='original-session',
        workstream=WS, owner='fixture-owner', charter_root=tmp_path, macro_root=tmp_path,
        reader=reader, now=NOW)
    assert result['projection']['state'] == 'NO_CANDIDATE'
    assert result['projection']['reason'] == 'CONTEXT_UNAVAILABLE'
    assert result['projection']['candidate'] is None
    assert result['projection']['action_recommendation'] is False
    assert 'context_bundle' not in result


def test_final_serialized_bound_still_fails_closed(monkeypatch, tmp_path):
    monkeypatch.setattr(api, 'METADATA_ALLOWANCE_BYTES', 1 << 20)
    monkeypatch.setattr(api, 'MAX_CONTEXT_BYTES', 2048)
    reader = big_bundle_reader(2048)
    result = api.collect_context(workspace_root=tmp_path, observed_workspace=tmp_path,
        owner_session='original-session', observed_session='original-session',
        workstream=WS, owner='fixture-owner', charter_root=tmp_path, macro_root=tmp_path,
        reader=reader, now=NOW)
    assert result['projection']['state'] == 'NO_CANDIDATE'
    assert result['projection']['reason'] == 'CONTEXT_UNAVAILABLE'
    assert 'context_bundle' not in result


def test_final_entrypoint_metadata_counts_toward_allowance():
    body = {'context_bundle': bundle(), 'entrypoint': 'active_owner_boundary',
            'padding': ''}
    metadata = {key: value for key, value in body.items() if key != 'context_bundle'}
    body['padding'] = 'x' * (api.METADATA_ALLOWANCE_BYTES
        - len(json.dumps(metadata, sort_keys=True, ensure_ascii=False).encode()) + 1)
    assert len(json.dumps(body, ensure_ascii=False).encode()) < api.MAX_CONTEXT_BYTES
    result = json.loads(api.bounded_json(body))
    assert result['projection']['reason'] == 'CONTEXT_DELIVERY_TOO_LARGE'
    assert 'context_bundle' not in result
