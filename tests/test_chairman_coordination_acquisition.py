"""Concrete read adapters; real file and Runtime operations, fake model execution."""
from __future__ import annotations
import asyncio
import dataclasses
import hashlib
import importlib
import json
import os
from pathlib import Path
import pytest
from tests.test_chairman_coordination_host import host, complete, supervisor, command, ARTIFACT
from control_plane.executive_supervisor import SupervisorError
from control_plane.executive_runtime import JobStatus, AttemptStatus


def module():
    spec = importlib.util.find_spec("control_plane.chairman_coordination_acquisition")
    assert spec is not None, "concrete coordination acquisition is missing"
    return importlib.import_module("control_plane.chairman_coordination_acquisition")


def reader(h, **overrides):
    values=dict(runtime=h["reader"], workspace_root=Path(h["work"].worktree).parent,
                project_ref=h["x"]["project_ref"], job_id=h["work"].job_id, artifact_path=ARTIFACT)
    values.update(overrides)
    return module().SealedCoordinationArtifactReader(**values)


def fetch(r, receipt, **overrides):
    blob=(Path(receipt.job.worktree)/ARTIFACT).read_bytes()
    kwargs=dict(expected_sha256=hashlib.sha256(blob).hexdigest(),max_bytes=128*1024)
    kwargs.update(overrides)
    return r(receipt.job,receipt.attempt,ARTIFACT,**kwargs)


def test_actual_sealed_artifact_read_is_exact_and_leaves_runtime_and_files_unchanged(host):
    sup,done=complete(host);r=reader(host)
    file=Path(done.job.worktree)/ARTIFACT;before=file.stat()
    state=(host["runtime"].jobs.get_job(done.job.job_id).to_dict(),host["runtime"].attempts.get_attempt(done.attempt.attempt_id).to_dict())
    assert fetch(r,done)==host["adapter"].candidate_bytes
    after=file.stat()
    assert (before.st_ino,before.st_size,before.st_mtime_ns,before.st_mode)==(after.st_ino,after.st_size,after.st_mtime_ns,after.st_mode)
    assert state==(host["runtime"].jobs.get_job(done.job.job_id).to_dict(),host["runtime"].attempts.get_attempt(done.attempt.attempt_id).to_dict())
    assert host["namespace"].active is False


def test_one_supervisor_call_uses_concrete_file_acquisition_not_a_test_callback(host):
    r=reader(host);sup=supervisor(host)
    done,review=asyncio.run(sup.run_coordination_once(command_id=command(host),artifact_reader=r))
    assert done.job.status is JobStatus.COMPLETED and review["eligible_for_owner_revalidation"]
    assert not review["execution_authority_granted"] and not review["acceptance_granted"]
    replay,review2=asyncio.run(sup.run_coordination_once(command_id=command(host),artifact_reader=r))
    assert replay.outcome=="TERMINAL" and review2["candidate_digest"]==review["candidate_digest"]
    assert host["adapter"].start_count==1


@pytest.mark.parametrize("field,value",[("expected_sha256","0"*64),("expected_sha256","not-a-digest"),("max_bytes",0),("max_bytes",True),("max_bytes",128*1024+1),("max_bytes",1)])
def test_unbounded_or_wrong_expected_artifact_refuses(host,field,value):
    _,done=complete(host)
    with pytest.raises(SupervisorError):fetch(reader(host),done,**{field:value})


@pytest.mark.parametrize("field,value",[("job_id","JOB-999"),("worktree","/unrelated-root"),("status",JobStatus.RUNNING),("current_attempt_id","ATT-wrong")])
def test_caller_job_cannot_change_canonical_artifact_location(host,field,value):
    _,done=complete(host);r=reader(host)
    changed=dataclasses.replace(done.job,**{field:value})
    with pytest.raises(SupervisorError):r(changed,done.attempt,ARTIFACT,expected_sha256=hashlib.sha256(host["adapter"].candidate_bytes).hexdigest(),max_bytes=128*1024)


@pytest.mark.parametrize("field,value",[("attempt_id","ATT-wrong"),("job_id","JOB-999"),("status",AttemptStatus.RUNNING)])
def test_caller_attempt_does_not_select_another_result(host,field,value):
    _,done=complete(host)
    with pytest.raises(SupervisorError):reader(host)(done.job,dataclasses.replace(done.attempt,**{field:value}),ARTIFACT,expected_sha256=hashlib.sha256(host["adapter"].candidate_bytes).hexdigest(),max_bytes=128*1024)


@pytest.mark.parametrize("path",["../proof.md","/tmp/proof.md","research/./proof.md","research/proof.md/","research/other.json",".git/config"])
def test_only_configured_canonical_relative_artifact_is_read(host,path):
    _,done=complete(host)
    with pytest.raises(SupervisorError):reader(host)(done.job,done.attempt,path,expected_sha256=hashlib.sha256(host["adapter"].candidate_bytes).hexdigest(),max_bytes=128*1024)


@pytest.mark.parametrize("mutation",["symlink","hardlink","fifo","directory","changed-content","world-writable"])
def test_unsafe_or_changed_artifact_fails_closed_without_touching_other_file(host,mutation,tmp_path):
    _,done=complete(host);r=reader(host);file=Path(done.job.worktree)/ARTIFACT;blob=file.read_bytes();other=tmp_path/"unrelated";other.write_bytes(blob)
    if mutation=="symlink":file.unlink();file.symlink_to(other)
    elif mutation=="hardlink":file.unlink();os.link(other,file)
    elif mutation=="fifo":file.unlink();os.mkfifo(file)
    elif mutation=="directory":file.unlink();file.mkdir()
    elif mutation=="world-writable":file.chmod(0o666)
    else:file.write_bytes(blob+b" ")
    with pytest.raises(SupervisorError):r(done.job,done.attempt,ARTIFACT,expected_sha256=hashlib.sha256(blob).hexdigest(),max_bytes=128*1024)
    assert other.read_bytes()==blob


@pytest.mark.parametrize("mutation",["unsealed-root","replaced-root","symlinked-parent"])
def test_sealed_workspace_identity_is_not_just_a_path_string(host,mutation):
    _,done=complete(host);r=reader(host);root=Path(done.job.worktree);blob=host["adapter"].candidate_bytes
    if mutation=="unsealed-root":root.chmod(0o750)
    elif mutation=="replaced-root":
        moved=root.with_name(root.name+"-old");root.rename(moved);root.mkdir(mode=0o700);(root/"research").mkdir();(root/ARTIFACT).write_bytes(blob)
    else:
        old=root/"research";moved=root/"moved";old.rename(moved);old.symlink_to(moved,target_is_directory=True)
    with pytest.raises(SupervisorError):r(done.job,done.attempt,ARTIFACT,expected_sha256=hashlib.sha256(blob).hexdigest(),max_bytes=128*1024)


def test_bound_runtime_required_for_artifact_read(host):
    _,done=complete(host)
    with pytest.raises(SupervisorError):fetch(reader(host,runtime=host["runtime"]),done)


def test_workstream_membership_cannot_be_relabelled(host):
    _,done=complete(host)
    with pytest.raises(SupervisorError):fetch(reader(host,project_ref="WS:OTHER"),done)


def test_wrong_configured_workspace_scope_never_opens_artifact(host,tmp_path):
    _,done=complete(host);different=tmp_path/"different";different.mkdir(mode=0o700)
    with pytest.raises(SupervisorError):fetch(reader(host,workspace_root=different),done)


def test_missing_nofollow_support_fails_without_fallback(host,monkeypatch):
    _,done=complete(host);r=reader(host)
    monkeypatch.delattr(os,"O_NOFOLLOW")
    with pytest.raises(SupervisorError):fetch(r,done)


def test_reader_never_returns_private_path_in_public_error(host,tmp_path):
    _,done=complete(host);r=reader(host);file=Path(done.job.worktree)/ARTIFACT;file.unlink()
    with pytest.raises(SupervisorError) as exc:r(done.job,done.attempt,ARTIFACT,expected_sha256=hashlib.sha256(host["adapter"].candidate_bytes).hexdigest(),max_bytes=128*1024)
    assert str(tmp_path) not in str(exc.value) and ARTIFACT not in str(exc.value)


def test_construction_does_not_open_files_or_claim_work(host,monkeypatch):
    module()
    def forbidden(*a,**k):raise AssertionError("construction opened a file")
    monkeypatch.setattr(os,"open",forbidden)
    reader(host)
    assert host["adapter"].start_count==0


@pytest.fixture
def compiler_repo(tmp_path):
    """Small committed CLI stand-in; production reader still calls real subprocesses."""
    import subprocess
    import sys
    from test_chairman_coordination import bundle_fixture
    root=tmp_path/"macro"; (root/"scripts").mkdir(parents=True);(root/"agentos").mkdir()
    _p,_x,_c,bundle=bundle_fixture()
    (root/"agentos/context.json").write_text(json.dumps(bundle))
    source = """import argparse,json,subprocess\nfrom pathlib import Path\np=argparse.ArgumentParser();p.add_argument('command');p.add_argument('--workstream');p.add_argument('--budget',type=int);p.add_argument('--root');p.add_argument('--json',action='store_true');p.add_argument('--now');a=p.parse_args()\nr=Path(__file__).resolve().parents[1];b=json.loads((Path(a.root)/'context.json').read_text());b['generated_at']=a.now;b['repo_sha']=subprocess.check_output(['git','-C',str(r),'rev-parse','HEAD'],text=True).strip();print(json.dumps(b))\n"""
    script=root/"scripts/agentos.py";script.write_text(source)
    def git(*args):return subprocess.check_output(['git','-C',str(root),*args],text=True)
    git('init','-q');git('add','.');git('-c','user.name=fixture','-c','user.email=fixture@example.invalid','commit','-qm','fixture compiler')
    return dict(root=root,commit=git('rev-parse','HEAD').strip(),compiler_sha256=hashlib.sha256(script.read_bytes()).hexdigest(),python=sys.executable,project=bundle['target']['workstream'],as_of=bundle['generated_at'],original=bundle)


def context_reader(repo,**overrides):
    values=dict(macro_root=repo['root'],expected_macro_sha=repo['commit'],expected_compiler_sha256=repo['compiler_sha256'],python_executable=Path(repo['python']),project_ref=repo['project'],as_of=repo['as_of'],token_budget=8000)
    values.update(overrides)
    factory=getattr(module(),'AgentOSCompileContextReader',None)
    assert callable(factory),'actual Agent OS compiler acquisition is missing'
    return factory(**values)


def test_context_is_acquired_by_exact_existing_cli_with_no_new_memory_store(compiler_repo):
    r=context_reader(compiler_repo);first=r.read()
    bundle=first.context_bundle
    assert bundle['repo_sha']==compiler_repo['commit']
    assert bundle['target']['workstream']==compiler_repo['project']
    assert bundle['sections']==compiler_repo['original']['sections']
    assert first.revalidate() is None
    assert first.context_bundle==bundle
    bundle['sections'].clear()
    assert first.context_bundle['sections']!=[]  # no mutable alias in the observation
    assert not (compiler_repo['root']/'.coordination').exists()


@pytest.mark.parametrize('field,value',[('expected_macro_sha','0'*40),('expected_compiler_sha256','0'*64),('project_ref','WS:WRONG')])
def test_wrong_source_or_project_never_produces_a_usable_context(compiler_repo,field,value):
    with pytest.raises(SupervisorError):context_reader(compiler_repo,**{field:value}).read()


@pytest.mark.parametrize('field,value',[('token_budget',True),('token_budget',0),('token_budget',9999999),('as_of','not-time'),('as_of','2026-08-30T15:00:00'),('expected_macro_sha','short'),('python_executable',Path('python3'))])
def test_context_configuration_refuses_unbounded_or_ambiguous_inputs(compiler_repo,field,value):
    with pytest.raises(SupervisorError):context_reader(compiler_repo,**{field:value})


@pytest.mark.parametrize('mutation',['compiler','records','repo-head'])
def test_context_revalidator_detects_changed_owner_material(compiler_repo,mutation):
    import subprocess
    r=context_reader(compiler_repo);observation=r.read();root=compiler_repo['root']
    if mutation=='compiler':(root/'scripts/agentos.py').write_text('raise RuntimeError("wrong-source")')
    elif mutation=='records':
        p=root/'agentos/context.json';b=json.loads(p.read_text());b['sections'][0]['items'][0]['excerpt']='new Chairman correction';p.write_text(json.dumps(b))
    else:
        subprocess.run(['git','-C',str(root),'-c','user.name=fixture','-c','user.email=fixture@example.invalid','commit','--allow-empty','-qm','later-head'],check=True)
    with pytest.raises(SupervisorError):observation.revalidate()


def test_degraded_and_omitted_context_is_preserved_not_relabelled_complete(compiler_repo):
    p=compiler_repo['root']/'agentos/context.json';b=json.loads(p.read_text());b['degraded']=['owner source unavailable'];b['omitted_due_to_budget']=[{'key':'DEC:MISSING','reason':'budget'}];p.write_text(json.dumps(b))
    out=context_reader(compiler_repo).read()
    assert out.context_bundle['degraded']==b['degraded']
    assert out.context_bundle['omitted_due_to_budget']==b['omitted_due_to_budget']
    assert out.revalidate() is None


def test_command_failure_has_no_fallback_or_private_error(compiler_repo,monkeypatch):
    from control_plane import chairman_control_room_remote as owner
    original=owner.default_runner;calls=[]
    def fail(argv,**kw):
        calls.append(list(argv))
        if 'compile-context' in argv:return dict(code=1,stdout='',stderr='private-diagnostic',timed_out=False,limit_exceeded=False,invalid_utf8=False)
        return original(argv,**kw)
    monkeypatch.setattr(owner,'default_runner',fail)
    with pytest.raises(SupervisorError) as exc:context_reader(compiler_repo).read()
    assert 'private-diagnostic' not in str(exc.value)
    assert sum('compile-context' in a for a in calls)==1


def test_duplicate_json_and_truncated_output_are_refused(compiler_repo,monkeypatch):
    from control_plane import chairman_control_room_remote as owner
    original=owner.default_runner
    def malformed(argv,**kw):
        if 'compile-context' in argv:return dict(code=0,stdout='{"schema":"context_bundle.v1","schema":"context_bundle.v1"}',stderr='',timed_out=False,limit_exceeded=False,invalid_utf8=False)
        return original(argv,**kw)
    monkeypatch.setattr(owner,'default_runner',malformed)
    with pytest.raises(SupervisorError):context_reader(compiler_repo).read()


def test_compiler_acquisition_uses_existing_hard_bounded_runner(compiler_repo,monkeypatch):
    from control_plane import chairman_control_room_remote as owner
    original=owner.default_runner;calls=[]
    def record(argv,**kw):calls.append((list(argv),kw));return original(argv,**kw)
    monkeypatch.setattr(owner,'default_runner',record)
    context_reader(compiler_repo).read()
    compile_call=next(c for c in calls if 'compile-context'in c[0])
    assert compile_call[0][1]=='-I'
    assert compile_call[1]['timeout']>0 and compile_call[1]['timeout']<=60
    assert 0<compile_call[1]['max_bytes']<=512*1024
    assert '--root'in compile_call[0] and str(compiler_repo['root']/'agentos')in compile_call[0]


@pytest.mark.parametrize('mutation',['replace-after-read','rewrite-after-read','replace-parent-after-read'])
def test_file_race_refuses_original_bytes_in_changed_namespace(host,monkeypatch,mutation):
    _,done=complete(host);r=reader(host);file=Path(done.job.worktree)/ARTIFACT;blob=file.read_bytes();real=os.read;changed=[]
    def racing(fd,n):
        data=real(fd,n)
        if data and not changed and os.fstat(fd).st_size==len(blob):
            changed.append(True)
            if mutation=='replace-after-read':
                file.rename(file.with_name('old-artifact'));file.write_bytes(blob)
            elif mutation=='rewrite-after-read':file.write_bytes(blob+b' ')
            else:
                parent=file.parent;parent.rename(parent.with_name('old-research'));parent.mkdir();file.write_bytes(blob)
        return data
    monkeypatch.setattr(os,'read',racing)
    with pytest.raises(SupervisorError):r(done.job,done.attempt,ARTIFACT,expected_sha256=hashlib.sha256(blob).hexdigest(),max_bytes=128*1024)
    assert changed==[True]


@pytest.mark.parametrize('missing',[False,True])
def test_artifact_file_descriptors_close_on_success_and_refusal(host,monkeypatch,missing):
    _,done=complete(host);r=reader(host);root=Path(done.job.worktree).parent;blob=host['adapter'].candidate_bytes
    if missing:(Path(done.job.worktree)/ARTIFACT).unlink()
    original=os.open;opened=[];started=[]
    def tracked(path,*args,**kwargs):
        fd=original(path,*args,**kwargs)
        if str(path)==str(root):started.append(True)
        if started:opened.append(fd)
        return fd
    monkeypatch.setattr(os,'open',tracked)
    if missing:
        with pytest.raises(SupervisorError):r(done.job,done.attempt,ARTIFACT,expected_sha256=hashlib.sha256(blob).hexdigest(),max_bytes=128*1024)
    else:assert fetch(r,done)==blob
    assert opened
    for fd in opened:
        with pytest.raises(OSError):os.fstat(fd)


@pytest.fixture
def composed_source(compiler_repo):
    from test_chairman_cognition_sources import _bundle,_boot_packet
    path=compiler_repo['root']/'agentos/context.json';data=json.loads(path.read_text());data['source_records_digest']='sha256:'+'d'*64;path.write_text(json.dumps(data))
    obs=context_reader(compiler_repo).read()
    source=_bundle(boot=_boot_packet(macro_sha=compiler_repo['commit']))
    source['agentos_revision_attestation']['revision']=compiler_repo['commit']
    return source,obs


def compose_with_context(source,observed):
    import inspect
    from control_plane.chairman_cognition_sources import compose_input
    assert 'compiled_context'in inspect.signature(compose_input).parameters,'dedicated compiled Agent OS source binding is missing'
    return compose_input(source,compiled_context=observed.context_bundle if hasattr(observed,"context_bundle") else observed,compiled_context_attestation=observed.source_attestation if hasattr(observed,"source_attestation") else None)


def test_existing_source_composer_binds_real_compiled_observation_without_new_authority(composed_source):
    import copy
    from control_plane.chairman_cognition import evaluate_document
    from control_plane.chairman_cognition_sources import compose_input
    source,obs=composed_source;before=copy.deepcopy(source)
    baseline=compose_input(source);out=compose_with_context(source,obs)
    fixed='AGENT_OS:compiled_project_context'
    row=next(r for r in out['source_receipts']if r['source_ref']==fixed)
    assert row['owner']=='AGENT_OS' and row['state']=='CURRENT'
    from control_plane.wake_events import canonical_json_bytes
    assert row['revision']=='sha256:'+hashlib.sha256(canonical_json_bytes(obs.context_bundle)).hexdigest()
    assert row['observed_at']==obs.context_bundle['generated_at']
    assert out['delegation_envelope']==baseline['delegation_envelope']
    assert out['options']==baseline['options'] and source==before
    assert evaluate_document(out)['execution_authority_granted'] is False


def test_compiled_context_receipt_cannot_be_injected_through_generic_additions(composed_source):
    from control_plane.chairman_cognition_sources import ChairmanCognitionSourceError,compose_input
    source,obs=composed_source;out=compose_with_context(source,obs)
    source['additional_source_receipts'].append(next(r for r in out['source_receipts']if r['source_ref']=='AGENT_OS:compiled_project_context'))
    with pytest.raises(ChairmanCognitionSourceError):compose_input(source)


@pytest.mark.parametrize('mutation',['revision','not-current','future-time','not-object'])
def test_compiled_binding_refuses_foreign_or_future_owner_evidence(composed_source,mutation):
    from control_plane.chairman_cognition_sources import ChairmanCognitionSourceError
    source,obs=composed_source
    if mutation=='revision':source['agentos_revision_attestation']['revision']='f'*40
    elif mutation=='not-current':source['agentos_revision_attestation']['state']='STALE'
    elif mutation=='future-time':
        b=obs.context_bundle;b['generated_at']='2099-01-01T00:00:00Z';obs=module().CompiledAgentOSContext(b,obs._owner)
    else:obs=['not-a-context-object']
    with pytest.raises(ChairmanCognitionSourceError):compose_with_context(source,obs)


def test_source_composition_stays_pure_without_reinvoking_the_compiler(composed_source,monkeypatch):
    source,obs=composed_source
    def forbidden(*args,**kwargs):raise AssertionError('pure composer performed source I/O')
    monkeypatch.setattr(obs,'revalidate',forbidden)
    compose_with_context(source,obs)


def test_source_binding_preserves_partial_context_without_claiming_complete_memory(composed_source):
    source,obs=composed_source;b=obs.context_bundle;b['degraded']=['not all sources available'];b['omitted_due_to_budget']=[{'key':'DEC:NEEDED'}]
    partial=module().CompiledAgentOSContext(b,obs._owner)
    out=compose_with_context(source,partial)
    # CURRENT describes the acquired record snapshot, not semantic completeness.
    row=next(r for r in out['source_receipts']if r['source_ref']=='AGENT_OS:compiled_project_context')
    assert row['owner']=='AGENT_OS' and out['delegation_envelope']==source['delegation_envelope']
    assert partial.context_bundle['degraded']==b['degraded']


def test_compiled_observation_does_not_authorize_cross_project_option(composed_source):
    from control_plane.chairman_cognition_sources import ChairmanCognitionSourceError
    source,obs=composed_source
    source['options'][0]['source_refs'].append('AGENT_OS:compiled_project_context')
    source['options'][0]['scope_refs']=['WS:OTHER']
    with pytest.raises(ChairmanCognitionSourceError):compose_with_context(source,obs)


@pytest.mark.parametrize('field,value',[('source_records_digest','UNRESOLVED'),('sections',None),('excluded',None),('omitted_due_to_budget',False),('degraded',False),('token_budget',True),('token_estimate',-1),('no_answer_reason',True)])
def test_dedicated_source_binding_validates_complete_compiler_shape(composed_source,field,value):
    from control_plane.chairman_cognition_sources import compose_input,ChairmanCognitionSourceError
    source,obs=composed_source;data=obs.context_bundle;data[field]=value
    if field=='source_records_digest':source['agentos_revision_attestation']['source_records_digest']=value
    with pytest.raises(ChairmanCognitionSourceError):compose_input(source,compiled_context=data,compiled_context_attestation=obs.source_attestation)


def test_dedicated_source_binding_refuses_missing_accounting_tail(composed_source):
    from control_plane.chairman_cognition_sources import compose_input,ChairmanCognitionSourceError
    source,obs=composed_source;data=obs.context_bundle;del data['omitted_due_to_budget']
    with pytest.raises(ChairmanCognitionSourceError):compose_input(source,compiled_context=data,compiled_context_attestation=obs.source_attestation)


def test_compiled_source_reference_is_usable_by_an_explicit_same_project_option(composed_source):
    from control_plane.chairman_cognition_sources import compose_input,COMPILED_CONTEXT_SOURCE_REF
    from control_plane.chairman_cognition import evaluate_document
    source,obs=composed_source;source['options'][0]['source_refs'].append(COMPILED_CONTEXT_SOURCE_REF)
    out=compose_input(source,compiled_context=obs.context_bundle,compiled_context_attestation=obs.source_attestation)
    assert COMPILED_CONTEXT_SOURCE_REF in out['options'][0]['source_refs']
    assert evaluate_document(out)['execution_authority_granted'] is False


def test_context_compiler_source_symlink_is_not_executed(compiler_repo,tmp_path):
    source=compiler_repo['root']/'scripts/agentos.py';outside=tmp_path/'copied.py';outside.write_bytes(source.read_bytes());source.unlink();source.symlink_to(outside)
    with pytest.raises(SupervisorError):context_reader(compiler_repo).read()


def test_clock_only_revalidation_never_rewrites_observed_bundle_time(compiler_repo):
    first=context_reader(compiler_repo).read();before=first.context_bundle['generated_at']
    assert first.revalidate() is None
    assert first.context_bundle['generated_at']==before



@pytest.mark.parametrize("change_during_work",[False,True])
def test_complete_host_path_composes_acquired_context_and_reads_the_sealed_file(host,compiler_repo,change_during_work):
    """Real compiler subprocess/files, source composer and Runtime; reasoning stays fake."""
    from test_chairman_cognition_sources import _bundle,_boot_packet
    from control_plane.chairman_cognition_sources import compose_input,COMPILED_CONTEXT_SOURCE_REF
    from control_plane.chairman_coordination_host import CoordinationWorkSources
    from control_plane.chairman_coordination import render_coordination_brief
    metadata=compiler_repo['root']/'agentos/context.json';data=json.loads(metadata.read_text());data['source_records_digest']='sha256:'+'d'*64;metadata.write_text(json.dumps(data))
    compiled=context_reader(compiler_repo)
    source=_bundle(boot=_boot_packet(macro_sha=compiler_repo['commit']))
    source['agentos_revision_attestation']['revision']=compiler_repo['commit']
    target_ref='RUNTIME_BINDING:fixture-current-target'
    source['additional_source_receipts'].append(dict(source_ref=target_ref,owner='RUNTIME_BINDING',revision='generation-fixture',state='CURRENT',load_bearing=True,observed_at=source['as_of']))
    refs=[source['chairman_directive']['source_ref'],'GITHUB:Mastermind:protected-master','STRATEGIC_STATE:config/strategic_state.yml','AGENT_OS:canonical-revision','AGENT_OS:ceo_brief',COMPILED_CONTEXT_SOURCE_REF,'GITHUB:A1',target_ref]
    source['options'][0]['source_refs']=refs
    def acquire(job,attempt):
        observed=compiled.read()
        fields=dict(schema='mastermind.chairman_coordination_context.v1',project_ref=host['x']['project_ref'],intent_source_ref=source['chairman_directive']['source_ref'],accepted_plan_source_ref='GITHUB:A1',coverage='COMPLETE',omissions=[],required_return_refs=[],required_acceptance_refs=['GITHUB:A1'],target_ref='TARGET-A',target_source_ref=target_ref,effect_hold_refs=[],permission_hold_refs=[])
        return module().bind_coordination_work_sources(source_bundle=source,compiled_context=observed,context_fields=fields,artifact_path=ARTIFACT,revalidate_source=lambda:None)
    initial=acquire(host['work'],None)
    briefing=render_coordination_brief(initial.document,context=initial.context,context_bundle=initial.context_bundle,bundle_source_ref=initial.bundle_source_ref)
    proposal=json.loads(briefing['messages'][1]['content'])['candidate_template']
    proposal.update(option_id=source['options'][0]['option_id'],decision='CONTINUE',consumed_return_refs=[],evidence_refs=['GITHUB:A1'],rationale='Fixture evidence resolves the existing bounded question.',next_step='Advance only the accepted slice; return the owed proof without repeating accepted design.')
    host['adapter'].proposal=proposal
    if change_during_work:
        original=host['adapter'].collect_result
        async def amended(ref):
            result=await original(ref)
            changed=json.loads(metadata.read_text());changed['sections'][0]['items'][0]['excerpt']='Current source correction changed the permitted next task.'
            metadata.write_text(json.dumps(changed))
            return result
        host['adapter'].collect_result=amended
    sup=supervisor(host,coordination_sources=acquire)
    done,review=asyncio.run(sup.run_coordination_once(command_id=command(host),artifact_reader=reader(host)))
    assert done.job.status is JobStatus.COMPLETED
    assert review['eligible_for_owner_revalidation'] is (not change_during_work)
    assert not review['execution_authority_granted'] and not review['acceptance_granted']
    assert review['runtime_result_evidence']['summary_used'] is False
    assert host['adapter'].start_count==1
    assert host['runtime'].jobs.get_job(host['root'].job_id).status is not JobStatus.COMPLETED


def test_project_context_and_company_brief_have_distinct_record_digest_scopes(composed_source):
    source,obs=composed_source
    data=obs.context_bundle;data['source_records_digest']='sha256:'+'c'*64
    scoped=module().CompiledAgentOSContext(data,obs._owner)
    # The existing compiler hashes only project-relevant opened records, while
    # the company brief hashes the broader store. They need not be equal.
    out=compose_with_context(source,scoped)
    assert next(r for r in out['source_receipts'] if r['source_ref']=='AGENT_OS:compiled_project_context')['state']=='CURRENT'
    assert source['agentos_revision_attestation']['source_records_digest'] != data['source_records_digest']


@pytest.mark.parametrize('field,value',[('project_ref','WS:OTHER'),('repository_revision','f'*40),('source_records_digest','sha256:'+'f'*64),('payload_digest','sha256:'+'f'*64),('compiler_sha256','bad'),('observed_at','2099-01-01T00:00:00Z'),('schema','unreviewed.v2')])
def test_compiled_context_requires_its_own_exact_acquisition_attestation(composed_source,field,value):
    from control_plane.chairman_cognition_sources import compose_input,ChairmanCognitionSourceError
    source,obs=composed_source
    assert hasattr(obs,'source_attestation'),'scoped context acquisition attestation missing'
    attested=obs.source_attestation;attested[field]=value
    with pytest.raises(ChairmanCognitionSourceError):
        compose_input(source,compiled_context=obs.context_bundle,compiled_context_attestation=attested)


def test_compiled_payload_without_acquisition_attestation_is_not_self_authorizing(composed_source):
    from control_plane.chairman_cognition_sources import compose_input,ChairmanCognitionSourceError
    source,obs=composed_source
    with pytest.raises(ChairmanCognitionSourceError):compose_input(source,compiled_context=obs.context_bundle)


def test_scoped_attestation_is_immutable_and_does_not_relabel_company_receipt(composed_source):
    from control_plane.chairman_cognition_sources import compose_input,AGENT_OS_SOURCE_REF
    source,obs=composed_source
    assert hasattr(obs,'source_attestation'),'scoped context acquisition attestation missing'
    original=obs.source_attestation;changed=obs.source_attestation;changed['project_ref']='WS:WRONG'
    assert obs.source_attestation==original
    before=next(r for r in compose_input(source)['source_receipts']if r['source_ref']==AGENT_OS_SOURCE_REF)
    result=compose_input(source,compiled_context=obs.context_bundle,compiled_context_attestation=original)
    assert next(r for r in result['source_receipts']if r['source_ref']==AGENT_OS_SOURCE_REF)==before



def test_unrelated_workspace_creation_does_not_invalidate_selected_sealed_artifact(host,monkeypatch):
    _,done=complete(host);r=reader(host);root=Path(done.job.worktree).parent;blob=host['adapter'].candidate_bytes
    real=os.read;created=[]
    def alongside(fd,n):
        data=real(fd,n)
        if data and not created and os.fstat(fd).st_size==len(blob):
            created.append(True);(root/'another-project-workspace').mkdir(mode=0o700)
        return data
    monkeypatch.setattr(os,'read',alongside)
    assert r(done.job,done.attempt,ARTIFACT,expected_sha256=hashlib.sha256(blob).hexdigest(),max_bytes=128*1024)==blob
    assert created==[True]


def source_binding_inputs(source,obs):
    from control_plane.chairman_cognition_sources import COMPILED_CONTEXT_SOURCE_REF
    source['options'][0]['source_refs'].append(COMPILED_CONTEXT_SOURCE_REF)
    return dict(schema='mastermind.chairman_coordination_context.v1',project_ref=obs.context_bundle['target']['workstream'],intent_source_ref=source['chairman_directive']['source_ref'],accepted_plan_source_ref='GITHUB:A1',coverage='COMPLETE',omissions=[],required_return_refs=[],required_acceptance_refs=['GITHUB:A1'],target_ref=None,target_source_ref=None,effect_hold_refs=[],permission_hold_refs=[])


def bind_sources(source,obs,fields,check=lambda:None):
    factory=getattr(module(),'bind_coordination_work_sources',None)
    assert callable(factory),'concrete host source composition is missing'
    return factory(source_bundle=source,compiled_context=obs,context_fields=fields,artifact_path=ARTIFACT,revalidate_source=check)


def test_binding_returns_existing_host_sources_and_derived_exact_revisions(composed_source):
    from control_plane.chairman_coordination_host import CoordinationWorkSources
    source,obs=composed_source;fields=source_binding_inputs(source,obs);out=bind_sources(source,obs,fields)
    assert type(out) is CoordinationWorkSources
    assert out.context['source_revisions']=={r['source_ref']:r['revision']for r in out.document['source_receipts']}
    assert out.context_bundle==obs.context_bundle
    assert out.revalidate() is None
    assert out.document['options']==source['options']
    assert out.document['delegation_envelope']==source['delegation_envelope']


@pytest.mark.parametrize('value',[False,True,'CURRENT',0])
def test_binding_requires_real_source_revalidation_not_status_tokens(composed_source,value):
    source,obs=composed_source
    with pytest.raises(SupervisorError):bind_sources(source,obs,source_binding_inputs(source,obs),lambda:value)


def test_binding_source_mutation_is_rejected_not_silently_promoted(composed_source):
    source,obs=composed_source;fields=source_binding_inputs(source,obs);out=bind_sources(source,obs,fields)
    source['chairman_directive']['revision']='later-ruling'
    with pytest.raises(SupervisorError):out.revalidate()


def test_binding_does_not_hide_compiler_omissions(composed_source):
    source,obs=composed_source;data=obs.context_bundle
    data['omitted_due_to_budget']=[{'key':'DEC:UNREAD','reason':'budget'}];data['degraded']=['required source unavailable']
    obs=module().CompiledAgentOSContext(data,obs._owner)
    out=bind_sources(source,obs,source_binding_inputs(source,obs))
    assert out.context['coverage']=='PARTIAL'
    assert out.context['omissions']
    assert out.context_bundle['omitted_due_to_budget']==data['omitted_due_to_budget']


def test_binding_does_not_accept_caller_rewritten_source_revision_map(composed_source):
    source,obs=composed_source;fields=source_binding_inputs(source,obs);fields['source_revisions']={'made-up':'revision'}
    with pytest.raises(SupervisorError):bind_sources(source,obs,fields)


def test_binding_wrong_project_fails_before_producing_a_task(composed_source):
    source,obs=composed_source;fields=source_binding_inputs(source,obs);fields['project_ref']='WS:OTHER'
    with pytest.raises(SupervisorError):bind_sources(source,obs,fields)



def test_project_context_default_reserves_room_for_decisions_and_handoffs():
    import inspect
    # The actual company project carries >8k standing context before any decision
    # or handoff rows. Keep the budget explicit and overridable, not a model grant.
    signature=inspect.signature(module().AgentOSCompileContextReader)
    assert signature.parameters['token_budget'].default == 16384



def test_equal_utc_timestamp_spellings_do_not_invent_source_drift(composed_source):
    from control_plane.chairman_cognition_sources import compose_input,COMPILED_CONTEXT_SOURCE_REF
    source,obs=composed_source;attestation=obs.source_attestation
    attestation['observed_at']=attestation['observed_at'].replace('Z','+00:00')
    out=compose_input(source,compiled_context=obs.context_bundle,compiled_context_attestation=attestation)
    assert next(r for r in out['source_receipts']if r['source_ref']==COMPILED_CONTEXT_SOURCE_REF)['state']=='CURRENT'



def test_sealed_directory_permission_mode_remains_distinct_from_os_identity():
    import difflib
    from test_ceo_submit_armed_composition import _scan_added_identity_diff
    path='control_plane/chairman_coordination_acquisition.py'
    source=(Path(__file__).resolve().parents[1]/path).read_text()
    added=''.join(difflib.unified_diff([],source.splitlines(keepends=True),fromfile='/dev/null',tofile='b/'+path,n=0))
    assert _scan_added_identity_diff(added,source_postimages={path:source})==[]
    assert module()._SEALED_DIRECTORY_MODE == 0o700
