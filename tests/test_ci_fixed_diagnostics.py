"""Closed prospective facts, synthetic tracked source and owned child only."""
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest

from scripts.ci_fixed_diagnostics import PublicCatalog, FixedDiagnostics, MAX_SNAPSHOT

SOURCE = 'def helper():\n raise ValueError("PRIVATE_CANARY")\ndef test_public():\n helper()\n'


def tracked(tmp_path, source=SOURCE):
    root = tmp_path/'repo'; (root/'tests').mkdir(parents=True)
    (root/'tests/test_public.py').write_text(source)
    for argv in (['init', '-q'], ['add', 'tests/test_public.py'],
            ['-c','user.name=fixture','-c','user.email=fixture@example.invalid','commit','-qm','public fixture']):
        subprocess.run(['git','-C',str(root),*argv],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    return root


def private_directory(tmp_path):
    out=tmp_path/'diagnostics';out.mkdir(mode=0o700)
    return out


def test_ast_bound_failure_redacts_parameters_messages_and_unknown_names(tmp_path):
    root=tracked(tmp_path); catalog=PublicCatalog(root); namespace={}
    exec(compile(SOURCE,str(root/'tests/test_public.py'),'exec'),namespace)
    try:namespace['test_public']()
    except ValueError as error:
        value=catalog.failure('tests/test_public.py::test_public[PRIVATE\x1b]', 'call', error=error)
    assert value==dict(module='tests/test_public.py',case='test_public',function='helper',phase='call',line=2,kind='ValueError')
    assert 'PRIVATE' not in json.dumps(value) and '\\u001b' not in json.dumps(value)
    unknown=catalog.failure('tests/test_public.py::test_PRIVATE', 'call', error=type('PRIVATE_KIND',(Exception,),{})('PRIVATE'))
    assert unknown['case'] is None and unknown['kind']=='UNKNOWN'
    assert catalog.failure('/PRIVATE/test_public.py::test_public','call') is None
    assert catalog.failure('tests/test_public.py::test_public','PRIVATE') is None


def test_source_drift_untracked_symlinks_and_foreign_names_are_closed(tmp_path):
    root=tracked(tmp_path);catalog=PublicCatalog(root)
    assert catalog.source('tests/test_public.py') is not None
    path=root/'tests/test_public.py';path.write_text(SOURCE+'def test_PRIVATE():pass\n')
    assert catalog.source('tests/test_public.py') is None
    (root/'tests/test_untracked.py').write_text(SOURCE)
    assert catalog.source('tests/test_untracked.py') is None
    path.unlink();path.symlink_to(root/'tests/test_untracked.py')
    assert catalog.source('tests/test_public.py') is None
    path.unlink();path.write_text(SOURCE)
    (root/'tests').rename(root/'public-tests')
    (root/'tests').symlink_to(root/'public-tests',target_is_directory=True)
    assert catalog.source('tests/test_public.py') is None


def test_exception_attribute_hooks_are_not_invoked_for_new_metadata(tmp_path):
    source='def test_public():\n raise Foreign("PRIVATE")\n'
    root=tracked(tmp_path,source);catalog=PublicCatalog(root)
    class Foreign(Exception):
        def __getattribute__(self,name):
            if name=='__traceback__':raise AssertionError('PRIVATE attribute hook invoked')
            return super().__getattribute__(name)
        def __str__(self):raise AssertionError('PRIVATE string hook invoked')
    namespace={'Foreign':Foreign};exec(compile(source,str(root/'tests/test_public.py'),'exec'),namespace)
    try:namespace['test_public']()
    except Foreign as error:value=catalog.failure('tests/test_public.py::test_public','call',error=error)
    assert value['kind']=='UNKNOWN' and value['function']=='test_public' and value['line']==2


def test_gitless_catalogue_and_safe_collect_line_bounds(tmp_path):
    empty=PublicCatalog(tmp_path)
    assert empty.head is None and empty.source('tests/test_public.py') is None
    catalog=PublicCatalog(tracked(tmp_path))
    crash=SimpleNamespace(path=str(catalog.root/'tests/test_public.py'),lineno=2)
    assert catalog.failure('tests/test_public.py','collect',crash=crash)['line']==2
    for line in (True,-1,0,10000000):
        crash.lineno=line
        assert catalog.failure('tests/test_public.py','collect',crash=crash)['line'] is None


def test_static_class_cases_and_unparseable_collection_have_closed_identities(tmp_path):
    root=tracked(tmp_path,'class TestCase:\n def test_method(self):pass\n')
    catalog=PublicCatalog(root)
    assert catalog.failure('tests/test_public.py::TestCase::test_method[PRIVATE]','call')['case']=='TestCase.test_method'
    other=tmp_path/'other';other.mkdir()
    broken=PublicCatalog(tracked(other,'def test_bad(:\n'))
    value=broken.failure('tests/test_public.py','collect',error=SyntaxError('PRIVATE'))
    assert value==dict(module='tests/test_public.py',case=None,function=None,phase='collect',line=None,kind='SyntaxError')


@pytest.mark.parametrize('field,value', [('cases_started',True),('cases_started',-1),
    ('cases_finished',2),('reported_seconds',float('nan')),('reported_seconds',float('inf')),
    ('reported_seconds',True),('reported_seconds',-1),('reported_seconds',7201)])
def test_progress_rejects_nonfinite_boolean_negative_and_inconsistent_fields(tmp_path,field,value):
    out=private_directory(tmp_path);diagnostics=FixedDiagnostics(PublicCatalog(tracked(tmp_path)),out)
    fields=dict(cases_started=1,cases_finished=1,reported_seconds=1.0);fields[field]=value
    diagnostics.progress_record('summary','tests/test_public.py',**fields)
    assert json.loads((out/'ci-fixed-diagnostics.json').read_text())['progress']==[]


def test_snapshot_is_bounded_private_and_preserves_foreign_replacement(tmp_path):
    out=private_directory(tmp_path);d=FixedDiagnostics(PublicCatalog(tracked(tmp_path)),out)
    for unused in range(520):d.progress_record('start','tests/test_public.py')
    path=out/'ci-fixed-diagnostics.json';value=json.loads(path.read_text())
    assert len(value['progress'])==512 and value['truncated'] is True
    assert path.stat().st_size<=MAX_SNAPSHOT and stat.S_IMODE(path.stat().st_mode)==0o600
    foreign=out/'replacement';foreign.write_bytes(b'PRIVATE_FOREIGN');foreign.replace(path)
    d.progress_record('start','tests/test_public.py')
    assert path.read_bytes()==b'PRIVATE_FOREIGN'


def test_preexisting_leaf_and_symlink_directory_are_never_adopted(tmp_path):
    root=tracked(tmp_path);out=private_directory(tmp_path);secret=tmp_path/'private';secret.write_bytes(b'PRIVATE')
    (out/'ci-fixed-diagnostics.json').symlink_to(secret)
    d=FixedDiagnostics(PublicCatalog(root),out);d.progress_record('start','tests/test_public.py')
    assert secret.read_bytes()==b'PRIVATE' and (out/'ci-fixed-diagnostics.json').is_symlink()
    alias=tmp_path/'alias';alias.symlink_to(out,target_is_directory=True)
    assert FixedDiagnostics(PublicCatalog(root),alias).directory is None


def test_serialization_refuses_mutated_private_fields_and_detaches_returned_facts(tmp_path):
    root=tracked(tmp_path);out=private_directory(tmp_path);d=FixedDiagnostics(PublicCatalog(root),out)
    value=d.failure_record('tests/test_public.py::test_public','call',error=ValueError('PRIVATE'))
    value['private']='PRIVATE';d.flush()
    path=out/'ci-fixed-diagnostics.json';safe=path.read_bytes();assert b'PRIVATE' not in safe
    d.progress.append({'event':'start','module':'tests/test_public.py','private':'PRIVATE'})
    d.flush();assert path.read_bytes()==safe
    d.progress.clear();d.catalog.head='PRIVATE';d.flush();assert path.read_bytes()==safe


def test_destination_swap_during_write_is_preserved_before_replace(tmp_path,monkeypatch):
    from scripts import ci_fixed_diagnostics as module
    root=tracked(tmp_path);out=private_directory(tmp_path);d=FixedDiagnostics(PublicCatalog(root),out)
    path=out/'ci-fixed-diagnostics.json';foreign=out/'foreign';foreign.write_bytes(b'PRIVATE_FOREIGN');foreign.chmod(0o600)
    real_write=module.os.write;swapped=[]
    def write(fd,raw):
        result=real_write(fd,raw)
        if not swapped:foreign.replace(path);swapped.append(True)
        return result
    with monkeypatch.context() as patch:
        patch.setattr(module.os,'write',write)
        d.progress_record('start','tests/test_public.py')
    assert swapped and path.read_bytes()==b'PRIVATE_FOREIGN'
    d.progress_record('start','tests/test_public.py')
    assert path.read_bytes()==b'PRIVATE_FOREIGN' and not (out/'.ci-fixed-diagnostics.next').exists()


def test_foreign_inode_after_replace_is_not_adopted_or_overwritten(tmp_path,monkeypatch):
    from scripts import ci_fixed_diagnostics as module
    root=tracked(tmp_path);out=private_directory(tmp_path);d=FixedDiagnostics(PublicCatalog(root),out)
    path=out/'ci-fixed-diagnostics.json';foreign=out/'foreign';foreign.write_bytes(b'PRIVATE_FOREIGN');foreign.chmod(0o600)
    own_before=d.file_identity;real_replace=module.os.replace
    def replace(src,dst,**kwargs):
        real_replace(src,dst,**kwargs)
        real_replace(foreign,path)
    with monkeypatch.context() as patch:
        patch.setattr(module.os,'replace',replace)
        d.progress_record('start','tests/test_public.py')
    assert d.directory is None and d.file_identity==own_before
    assert path.read_bytes()==b'PRIVATE_FOREIGN'
    d.progress_record('start','tests/test_public.py');assert path.read_bytes()==b'PRIVATE_FOREIGN'


def test_postpublication_wrong_metadata_disables_writer_without_repair(tmp_path,monkeypatch):
    from scripts import ci_fixed_diagnostics as module
    root=tracked(tmp_path);out=private_directory(tmp_path);d=FixedDiagnostics(PublicCatalog(root),out)
    path=out/'ci-fixed-diagnostics.json';real_replace=module.os.replace
    def replace(src,dst,**kwargs):
        real_replace(src,dst,**kwargs);path.chmod(0o644)
    with monkeypatch.context() as patch:
        patch.setattr(module.os,'replace',replace)
        d.progress_record('start','tests/test_public.py')
    assert d.directory is None and stat.S_IMODE(path.stat().st_mode)==0o644


def plugin_child(tmp_path, source):
    root=tracked(tmp_path,source);scripts=root/'scripts';scripts.mkdir();(scripts/'__init__.py').write_bytes(b'')
    original=Path(__file__).resolve().parents[1]/'scripts'
    for name in ('ci_fixed_diagnostics.py','ci_pytest_timing.py'):
        shutil.copyfile(original/name,scripts/name)
    out=private_directory(tmp_path)
    env={**os.environ,'PYTEST_DISABLE_PLUGIN_AUTOLOAD':'1','PYTHONDONTWRITEBYTECODE':'1',
        'PYTHONPATH':str(root),'MMX_CI_FIXED_DIAGNOSTICS_DIR':str(out)}
    argv=[sys.executable,'-m','pytest','--noconftest','-q','-p','no:cacheprovider','-p','scripts.ci_pytest_timing','tests/test_public.py']
    return root,out,env,argv


def test_actual_plugin_preserves_failure_and_emits_only_closed_facts(tmp_path):
    root,out,env,argv=plugin_child(tmp_path,SOURCE)
    child=subprocess.run(argv,cwd=root,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=20)
    assert child.returncode==1
    notices=[line for line in child.stdout.splitlines() if line.startswith(b'::error title=CI fixed failure metadata::')]
    assert len(notices)==1 and b'PRIVATE' not in notices[0]
    value=json.loads((out/'ci-fixed-diagnostics.json').read_text())
    assert value['failures'][0]['case']=='test_public' and value['failures'][0]['kind']=='ValueError'
    assert value['progress'][-1]['event']=='summary' and value['progress'][-1]['cases_finished']==1
    assert 'PRIVATE' not in json.dumps(value)


def test_fresh_snapshot_survives_owned_test_process_timeout(tmp_path):
    source='def test_public():\n import time\n time.sleep(60)\n'
    root,out,env,argv=plugin_child(tmp_path,source)
    child=subprocess.Popen(argv,cwd=root,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        deadline=time.monotonic()+10;path=out/'ci-fixed-diagnostics.json'
        while child.poll() is None and time.monotonic()<deadline:
            if path.exists() and json.loads(path.read_text())['progress']:break
            time.sleep(.02)
        assert path.exists() and json.loads(path.read_text())['progress']
        with pytest.raises(subprocess.TimeoutExpired):child.wait(timeout=.1)
    finally:
        if child.poll() is None:child.terminate()
        try:child.wait(timeout=5)
        except subprocess.TimeoutExpired:child.kill();child.wait(timeout=5)
    value=json.loads(path.read_text())
    assert value['progress'][-1]==dict(event='start',module='tests/test_public.py')
    assert value['failures']==[] and path.stat().st_size<=MAX_SNAPSHOT
    # This proves a persisted closed input survives a synthetic test timeout.
    # Real upload/artifact consumption remains a separate hosted-CI obligation.


def test_workflow_retains_job_limit_and_bounds_upload_opportunity():
    import yaml
    from scripts.ci_parallel_shard import validate_parallel_workflow
    from scripts.ci_pytest import _WorkflowYAMLLoader
    text=(Path(__file__).resolve().parents[1]/'.github/workflows/ci.yml').read_text()
    validate_parallel_workflow(text)
    workflow=yaml.load(text,Loader=_WorkflowYAMLLoader);job=workflow['jobs']['pytest_shards']
    step=next(s for s in job['steps']if s.get('name')=='Run repository test shard')
    upload=next(s for s in job['steps']if s.get('name')=='Upload fixed test diagnostics')
    assert job['timeout-minutes']==45 and step['timeout-minutes']==38
    assert upload['if']=='always()' and upload['timeout-minutes']==2
    assert upload['uses']=='actions/upload-artifact@v4'
    assert upload['with']['path']=='${{ env.MMX_CI_FIXED_DIAGNOSTICS_DIR }}/ci-fixed-diagnostics.json'
    assert upload['with']['name']=='ci-fixed-diagnostics-${{ matrix.index }}'
    assert upload['with']['if-no-files-found']=='warn'
    assert job['steps'].index(step)<job['steps'].index(upload)
