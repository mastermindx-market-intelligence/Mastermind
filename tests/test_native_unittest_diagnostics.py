"""Closed live unittest facts through the existing fixed CI artifact only."""
import base64
import copy
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from unittest import mock

import pytest

from scripts import ci_fixed_diagnostics as fixed
from scripts import native_unittest_diagnostics as native

ROOT = Path(__file__).resolve().parents[1]
MODULE = 'ops/native_fabric/quota_continuity/tests/test_leaf.py'
G_O = ('tests', 'test_[g-o]*.py')
WRAPPER = 'tests/test_native_fabric_quota_continuity_g_o.py::test_native_quota_continuity_owners_g_o'
ROLLOUT = 'tests/test_native_fabric_quota_continuity.py::test_native_generation_and_ingress_rollout'
LEAF = '''import unittest
class Leaf(unittest.TestCase):
 def test_failure(self):
  self.fail("PRIVATE assertion https://user:password@private/?token=PRIVATE")
 def test_error(self):
  raise ValueError("PRIVATE env and parameters")
'''


def tracked(tmp_path, source=LEAF, module=MODULE):
    root=tmp_path/'repo';root.mkdir()
    for name in ['scripts/ci_fixed_diagnostics.py','scripts/native_unittest_diagnostics.py',
            'tests/test_native_fabric_quota_continuity.py',
            *(node.split('::')[0] for node in native.WRAPPER_SELECTIONS if node != ROLLOUT)]:
        p=root/name;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,p)
    sentinel='import unittest\nclass Sentinel(unittest.TestCase):\n def test_ok(self):pass\n'
    for name in ('test_alpha.py','test_leaf.py','test_zulu.py'):
        p=root/'ops/native_fabric/quota_continuity/tests'/name
        p.parent.mkdir(parents=True,exist_ok=True);p.write_text(sentinel)
    p=root/module;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(source)
    for args in [('init','-q'),('add','.'),('-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-qm','fixture')]:
        subprocess.run(['git','-C',str(root),*args],check=True,capture_output=True)
    return root


def run_child(root, invocation='a'*32, directory='tests', selection=G_O):
    with tempfile.TemporaryFile() as channel:
        head=fixed.PublicCatalog(root).head
        args=(['discover','-s',native.PREFIX+'tests','-p','test_commission_deadline.py']
            if selection==native.COMMISSION_SELECTION else ['discover','-s',directory,'-p',selection[1],'-v'])
        cwd=root if selection==native.COMMISSION_SELECTION else root/'ops/native_fabric/quota_continuity'
        command=[sys.executable,str(root/'scripts/native_unittest_diagnostics.py'),
            '--result-fd',str(channel.fileno()),'--head',head,'--invocation',invocation,*args]
        result=subprocess.run(command,cwd=cwd,
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,pass_fds=(channel.fileno(),),timeout=10)
        channel.seek(0);raw=channel.read(native.MAX_CHANNEL+1)
    return head,result,raw


def test_failure_and_error_are_live_public_records_and_original_exit(tmp_path):
    root=tracked(tmp_path);head,result,raw=run_child(root)
    assert result.returncode==1
    assert b'PRIVATE assertion' in result.stderr  # existing private unittest output remains ordinary
    assert b'PRIVATE' not in raw and b'password' not in raw
    value=native.decode(raw,head=head,invocation='a'*32,directory='tests',selection=G_O,catalog=fixed.PublicCatalog(root,native=True),returncode=1)
    assert value['counts']['tests_run']==2
    assert value['counts']['failures']==value['counts']['errors']==1
    assert {r['case'] for r in value['records']}=={'Leaf.test_failure','Leaf.test_error'}
    assert {r['kind'] for r in value['records']}=={'AssertionError','ValueError'}
    assert all(r['module']==MODULE and r['line'] in (4,6) for r in value['records'])


def test_cross_invocation_head_schema_and_nonpublic_payloads_refuse(tmp_path):
    root=tracked(tmp_path);head,result,raw=run_child(root);base=json.loads(raw)
    for change in ['head','invocation','directory','unknown','path','case','function','kind','line','count','counts-contradict','duplicate','nonfinite','malformed','oversize']:
        value=copy.deepcopy(base)
        if change=='head':value['head']='b'*40
        if change=='invocation':value['invocation']='b'*32
        if change=='directory':value['directory']='rollout'
        if change=='function':value['records'][0]['function']='PRIVATE_unknown_function'
        if change=='counts-contradict':value['counts']['failures']=0;value['counts']['errors']=0
        if change=='unknown':value['PRIVATE']='PRIVATE'
        if change=='path':value['records'][0]['module']='ops/private/test_secret.py'
        if change=='case':value['records'][0]['case']='Leaf.test_PRIVATE'
        if change=='kind':value['records'][0]['kind']='PRIVATE_EXCEPTION'
        if change=='line':value['records'][0]['line']=True
        if change=='count':value['counts']['tests_run']=True
        data=json.dumps(value).encode()
        if change=='duplicate':data=b'{"schema":"PRIVATE",'+data[1:]
        if change=='nonfinite':data=b'{"extra":NaN,'+data[1:]
        if change=='malformed':data=b'PRIVATE malformed'
        if change=='oversize':data=b'PRIVATE'+b'x'*native.MAX_CHANNEL
        with pytest.raises(ValueError,match='native_diagnostic_unavailable'):
            native.decode(data,head=head,invocation='a'*32,directory='tests',selection=G_O,catalog=fixed.PublicCatalog(root,native=True),returncode=1)


def load_wrapper(root):
    spec=importlib.util.spec_from_file_location('synthetic_native_wrapper',root/'tests/test_native_fabric_quota_continuity.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def test_existing_artifact_ingests_only_current_live_wrapper_facts(tmp_path,monkeypatch):
    root=tracked(tmp_path);directory=tmp_path/'fixed';directory.mkdir(mode=0o700)
    monkeypatch.setenv('MMX_CI_FIXED_DIAGNOSTICS_DIR',str(directory))
    wrapper=load_wrapper(root)
    with pytest.raises(AssertionError) as caught:wrapper._qualify(WRAPPER,timeout_seconds=10)
    catalog=fixed.PublicCatalog(root);diagnostics=fixed.FixedDiagnostics(catalog,directory)
    diagnostics.failure_record(WRAPPER,'call',error=caught.value)
    data=(directory/'ci-fixed-diagnostics.json').read_bytes();value=json.loads(data)
    assert value['schema']=='ci.fixed-diagnostics.v1'
    assert len(value['failures'])==3
    assert sum(row['module']==MODULE for row in value['failures'])==2
    assert b'PRIVATE' not in data and b'password' not in data
    facts=caught.value._mmx_native_facts
    for record in value['failures']:
        if record['module']==MODULE:
            assert record['native_invocation']==facts.invocation
            assert record['native_wrapper']=='test_native_quota_continuity_owners_g_o'
            assert set(record)=={'module','case','function','phase','line','kind','native_invocation','native_wrapper'}
    with pytest.raises(ValueError,match='native_diagnostic_unavailable'):
        native.decode(facts.raw,head=facts.head,invocation='f'*32,directory='tests',selection=G_O,catalog=fixed.PublicCatalog(root,native=True),returncode=1)
    records,truncated=native.records_for_error(caught.value,'tests/test_native_fabric_quota_continuity.py::test_native_generation_and_ingress_rollout',root,catalog.head)
    assert records==[] and truncated is True
    records,truncated=native.records_for_error(caught.value,'tests/test_other.py::test_private',root,catalog.head)
    assert records==[] and truncated is False


def test_discovery_order_exit_success_skip_and_private_stream_semantics_unchanged(tmp_path):
    source='''import unittest
class Leaf(unittest.TestCase):
 def test_b(self):pass
 @unittest.skip("PRIVATE skip reason")
 def test_c(self):pass
 def test_a(self):pass
'''
    root=tracked(tmp_path,source);head,result,raw=run_child(root)
    ordinary=subprocess.run([sys.executable,'-m','unittest','discover','-s','tests','-p','test_[g-o]*.py','-v'],cwd=root/'ops/native_fabric/quota_continuity',capture_output=True,timeout=10)
    assert result.returncode==ordinary.returncode==0
    for stream in (result.stderr,ordinary.stderr):
        assert stream.index(b'test_a')<stream.index(b'test_b')<stream.index(b'test_c')
        assert b'Ran 3 tests' in stream and b'OK (skipped=1)' in stream
    value=native.decode(raw,head=head,invocation='a'*32,directory='tests',selection=G_O,catalog=fixed.PublicCatalog(root,native=True),returncode=0)
    assert value['records']==[] and value['counts']['tests_run']==3 and value['counts']['skipped']==1
    assert b'PRIVATE' not in raw


def test_subtest_parameters_and_attacker_exception_name_never_escape(tmp_path):
    source='''import unittest
class PRIVATE_EXCEPTION(Exception):pass
class Leaf(unittest.TestCase):
 def test_subtest(self):
  with self.subTest(PRIVATE="password https://user:pw@private"):
   raise PRIVATE_EXCEPTION("PRIVATE text")
'''
    root=tracked(tmp_path,source);head,result,raw=run_child(root)
    value=native.decode(raw,head=head,invocation='a'*32,directory='tests',selection=G_O,catalog=fixed.PublicCatalog(root,native=True),returncode=1)
    assert len(value['records'])==1 and value['records'][0]['kind']=='UNKNOWN'
    assert value['records'][0]['case']=='Leaf.test_subtest'
    assert b'PRIVATE' not in raw and b'password' not in raw


def test_only_exact_native_roots_and_head_bytes_are_admitted(tmp_path):
    root=tracked(tmp_path);head,result,raw=run_child(root);catalog=fixed.PublicCatalog(root,native=True)
    assert catalog.source('tests/test_native_fabric_quota_continuity.py') is None
    assert catalog.source('ops/native_fabric/test_private.py') is None
    p=root/MODULE;p.write_text(LEAF+'# changed\n')
    with pytest.raises(ValueError,match='native_diagnostic_unavailable'):
        native.decode(raw,head=head,invocation='a'*32,directory='tests',selection=G_O,catalog=catalog,returncode=1)
    p.write_text(LEAF);p.rename(p.with_suffix('.private'));p.symlink_to(p.with_suffix('.private'))
    with pytest.raises(ValueError,match='native_diagnostic_unavailable'):
        native.decode(raw,head=head,invocation='a'*32,directory='tests',selection=G_O,catalog=fixed.PublicCatalog(root,native=True),returncode=1)


def test_missing_or_bad_channel_does_not_change_wrapper_result_and_limits(tmp_path,monkeypatch):
    root=tracked(tmp_path,'import unittest\nclass Leaf(unittest.TestCase):\n def test_ok(self):pass\n');wrapper=load_wrapper(root)
    monkeypatch.delenv('MMX_CI_FIXED_DIAGNOSTICS_DIR',raising=False)
    with mock.patch.object(native.subprocess,'run',return_value=subprocess.CompletedProcess([],0,'','Ran 1 test\nOK\n')) as call:
        wrapper._qualify(WRAPPER,timeout_seconds=300)
        assert call.call_args.args[0]==[sys.executable,'-m','unittest','discover','-s','tests','-p','test_[g-o]*.py','-v']
        assert call.call_args.kwargs['timeout']==300
    monkeypatch.setenv('MMX_CI_FIXED_DIAGNOSTICS_DIR','inert')
    with mock.patch.object(native.subprocess,'run',return_value=subprocess.CompletedProcess([],1,'PRIVATE stdout','PRIVATE stderr')):
        # No writer supplied facts; original AssertionError and private message remain ordinary.
        with pytest.raises(AssertionError) as error:wrapper._qualify(WRAPPER,timeout_seconds=300)
        assert str(error.value)=='PRIVATE stdoutPRIVATE stderr'
        assert not hasattr(error.value,'_mmx_native_facts')
    with mock.patch.object(native.subprocess,'run',side_effect=subprocess.TimeoutExpired('inert',240)):
        with pytest.raises(subprocess.TimeoutExpired):wrapper._qualify(ROLLOUT,timeout_seconds=240)


def test_live_class_setup_error_is_public_metadata_without_message(tmp_path):
    source='''import unittest
class Leaf(unittest.TestCase):
 @classmethod
 def setUpClass(cls):raise RuntimeError("PRIVATE setup")
 def test_a(self):pass
'''
    root=tracked(tmp_path,source);head,result,raw=run_child(root)
    value=native.decode(raw,head=head,invocation='a'*32,directory='tests',selection=G_O,catalog=fixed.PublicCatalog(root,native=True),returncode=1)
    assert value['counts']['tests_run']==0 and value['counts']['errors']==1
    assert value['records']==[dict(module=MODULE,case=None,function='setUpClass',phase='setup',line=4,kind='RuntimeError')]
    assert b'PRIVATE' not in raw


def test_actual_pytest_wrapper_publishes_native_facts_in_same_artifact(tmp_path):
    root=tracked(tmp_path)
    for name in ['scripts/__init__.py','scripts/ci_pytest_timing.py']:
        shutil.copyfile(ROOT/name,root/name)
    subprocess.run(['git','-C',str(root),'add','.'],check=True,capture_output=True)
    subprocess.run(['git','-C',str(root),'-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-qm','plugin'],check=True,capture_output=True)
    directory=tmp_path/'job';directory.mkdir(mode=0o700)
    env=dict(os.environ,MMX_CI_FIXED_DIAGNOSTICS_DIR=str(directory),PYTHONDONTWRITEBYTECODE='1')
    result=subprocess.run([sys.executable,'-m','pytest','-p','scripts.ci_pytest_timing','-q',
        WRAPPER],cwd=root,env=env,capture_output=True,timeout=20)
    assert result.returncode==1
    raw=(directory/'ci-fixed-diagnostics.json').read_bytes();value=json.loads(raw)
    assert value['head']==fixed.PublicCatalog(root).head
    assert len(value['failures'])==3 and sum(r['module']==MODULE for r in value['failures'])==2
    assert b'PRIVATE' not in raw and b'password' not in raw
    assert sorted(p.name for p in directory.iterdir())==['ci-fixed-diagnostics.json']


def test_import_failure_has_public_module_without_private_import_text(tmp_path):
    source='raise ImportError("PRIVATE import location")\n'
    root=tracked(tmp_path,source);head,result,raw=run_child(root)
    value=native.decode(raw,head=head,invocation='a'*32,directory='tests',selection=G_O,catalog=fixed.PublicCatalog(root,native=True),returncode=1)
    assert value['counts']['errors']==1
    assert value['records']==[dict(module=MODULE,case=None,function=None,phase='collect',line=None,kind='ImportError')]
    assert b'PRIVATE' not in raw


def test_incomplete_live_identity_is_explicitly_truncated_and_never_guessed(tmp_path):
    source='''import unittest
class Leaf(unittest.TestCase):
 def test_public(self):raise ValueError("PRIVATE")
 def id(self):return "PRIVATE id must never be called by projection"
# A runtime alias is not an AST-bound test case; it must not be projected.
Leaf.test_alias=Leaf.test_public
'''
    root=tracked(tmp_path,source);head,result,raw=run_child(root)
    value=native.decode(raw,head=head,invocation='a'*32,directory='tests',selection=G_O,catalog=fixed.PublicCatalog(root,native=True),returncode=1)
    assert value['counts']['errors']==2 and len(value['records'])==1 and value['truncated'] is True
    assert value['records'][0]['case']=='Leaf.test_public' and b'PRIVATE' not in raw


def test_complete_old_carrier_cannot_be_replayed_into_later_invocation(tmp_path,monkeypatch):
    root=tracked(tmp_path);directory=tmp_path/'fixed';directory.mkdir(mode=0o700)
    monkeypatch.setenv('MMX_CI_FIXED_DIAGNOSTICS_DIR',str(directory));wrapper=load_wrapper(root)
    errors=[]
    for _ in range(2):
        with pytest.raises(AssertionError) as caught:wrapper._qualify(WRAPPER,timeout_seconds=10)
        errors.append(caught.value)
    old=errors[0]._mmx_native_facts;fresh=errors[1]._mmx_native_facts
    assert old.invocation!=fresh.invocation
    errors[1]._mmx_native_facts=old
    node=WRAPPER
    records,truncated=native.records_for_error(errors[1],node,root,fixed.PublicCatalog(root).head)
    assert records==[] and truncated is True
    records,truncated=native.records_for_error(errors[0],node,root,fixed.PublicCatalog(root).head)
    assert len(records)==2
    records,truncated=native.records_for_error(errors[0],node,root,fixed.PublicCatalog(root).head)
    assert records==[] and truncated is True


@pytest.mark.parametrize('body',[
    'import unittest\n',
    'import unittest\nclass Leaf(unittest.TestCase):\n def test_ok(self):pass\n',
    'import unittest\nclass Leaf(unittest.TestCase):\n def test_fail(self):self.fail("PRIVATE")\n'])
def test_real_unittest_cli_exit_code_is_preserved_including_zero_tests(tmp_path,body):
    root=tracked(tmp_path,body);head,result,raw=run_child(root)
    ordinary=subprocess.run([sys.executable,'-m','unittest','discover','-s','tests','-p','test_[g-o]*.py','-v'],cwd=root/'ops/native_fabric/quota_continuity',capture_output=True,timeout=10)
    assert result.returncode==ordinary.returncode
    if b'Ran 0 tests' in ordinary.stderr and ordinary.returncode!=0:
        assert raw==b''  # unsupported zero-test diagnostic never changes CLI exit


def test_legacy_unittest_boolean_systemexit_is_observed_without_changing_exit(tmp_path):
    root=tracked(tmp_path);head=fixed.PublicCatalog(root).head
    code='''import sys,unittest
sys.path.insert(0,sys.argv.pop(1))
import native_unittest_diagnostics as native
original=unittest.TestProgram.runTests
def legacy(self):
 try:original(self)
 except SystemExit as stopped:
  if type(stopped.code) is int and stopped.code in (0,1):raise SystemExit(bool(stopped.code))
  raise
unittest.TestProgram.runTests=legacy
raise SystemExit(native.main())
'''
    with tempfile.TemporaryFile() as channel:
        result=subprocess.run([sys.executable,'-c',code,str(root/'scripts'),'--result-fd',str(channel.fileno()),'--head',head,'--invocation','a'*32,'discover','-s','tests','-p','test_[g-o]*.py','-v'],cwd=root/'ops/native_fabric/quota_continuity',capture_output=True,pass_fds=(channel.fileno(),),timeout=10)
        channel.seek(0);raw=channel.read(native.MAX_CHANNEL+1)
    assert result.returncode==1
    value=native.decode(raw,head=head,invocation='a'*32,directory='tests',selection=G_O,catalog=fixed.PublicCatalog(root,native=True),returncode=1)
    assert len(value['records'])==2 and b'PRIVATE' not in raw


def test_catalog_head_change_between_validation_and_publication_refuses(tmp_path,monkeypatch):
    root=tracked(tmp_path);directory=tmp_path/'fixed';directory.mkdir(mode=0o700)
    monkeypatch.setenv('MMX_CI_FIXED_DIAGNOSTICS_DIR',str(directory));wrapper=load_wrapper(root)
    with pytest.raises(AssertionError) as caught:wrapper._qualify(WRAPPER,timeout_seconds=10)
    original=fixed.PublicCatalog;catalog=original(root)
    diagnostics=fixed.FixedDiagnostics(catalog,directory)
    before=(directory/'ci-fixed-diagnostics.json').read_bytes();calls=[0]
    def change_head(*args,**kwargs):
        calls[0]+=1
        if calls[0]==2:
            subprocess.run(['git','-C',str(root),'-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','--allow-empty','-qm','new-head'],check=True,capture_output=True)
        return original(*args,**kwargs)
    with mock.patch.object(fixed,'PublicCatalog',side_effect=change_head):
        diagnostics.failure_record(WRAPPER,'call',error=caught.value)
    assert calls[0]==2 and diagnostics.native_catalog.head!=catalog.head
    assert (directory/'ci-fixed-diagnostics.json').read_bytes()==before


SELECTION_MODULES = {
    ('tests', 'test_[a-f]*.py'): 'ops/native_fabric/quota_continuity/tests/test_alpha.py',
    ('tests', 'test_[g-o]*.py'): MODULE,
    ('tests', 'test_[p-z]*.py'): 'ops/native_fabric/quota_continuity/tests/test_zulu.py',
    ('rollout', 'test_*.py'): 'ops/native_fabric/quota_continuity/rollout/test_leaf.py',
    native.COMMISSION_SELECTION: 'ops/native_fabric/quota_continuity/tests/test_commission_deadline.py',
}


def selection_node(selection):
    return next(node for node,value in native.WRAPPER_SELECTIONS.items() if value == selection)


@pytest.mark.parametrize('selection', tuple(SELECTION_MODULES))
def test_selected_cli_matches_ordinary_exit_order_and_private_skip(selection, tmp_path):
    source = LEAF + '''
 def test_ok(self):pass
 @unittest.skip("PRIVATE selected skip")
 def test_skip(self):pass
'''
    module = SELECTION_MODULES[selection]
    root = tracked(tmp_path, source, module)
    head,result,raw = run_child(root, directory=selection[0], selection=selection)
    args=(['discover','-s',native.PREFIX+'tests','-p','test_commission_deadline.py']
        if selection==native.COMMISSION_SELECTION else ['discover','-s',selection[0],'-p',selection[1],'-v'])
    cwd=root if selection==native.COMMISSION_SELECTION else root/'ops/native_fabric/quota_continuity'
    ordinary = subprocess.run([sys.executable,'-m','unittest',*args], cwd=cwd,
        capture_output=True, timeout=10)
    assert result.returncode == ordinary.returncode == 1
    for stream in (result.stderr, ordinary.stderr):
        if selection != native.COMMISSION_SELECTION:
            assert stream.index(b'test_error') < stream.index(b'test_failure') < stream.index(b'test_ok') < stream.index(b'test_skip')
        assert b'Ran 4 tests' in stream and b'skipped=1' in stream
    value = native.decode(raw, head=head, invocation='a'*32, directory=selection[0],
        selection=selection, catalog=fixed.PublicCatalog(root,native=True), returncode=1)
    assert value['counts']['tests_run'] == 4 and value['counts']['skipped'] == 1
    assert value['counts']['failures'] == value['counts']['errors'] == 1
    assert {row['module'] for row in value['records']} == {module}
    assert b'PRIVATE' not in raw and b'password' not in raw


@pytest.mark.parametrize('selection', tuple(SELECTION_MODULES))
@pytest.mark.parametrize('phase,source', [
    ('collect', 'raise ImportError("PRIVATE import")\n'),
    ('setup', 'import unittest\nclass Leaf(unittest.TestCase):\n def test_a(self):pass\ndef setUpModule():raise RuntimeError("PRIVATE setup")\n'),
    ('setup', 'import unittest\nclass Leaf(unittest.TestCase):\n @classmethod\n def setUpClass(cls):raise RuntimeError("PRIVATE class")\n def test_a(self):pass\n'),
    ('teardown', 'import unittest\nclass Leaf(unittest.TestCase):\n def test_a(self):pass\ndef tearDownModule():raise RuntimeError("PRIVATE teardown")\n'),
])
def test_selected_import_and_fixture_failures_keep_qualified_module(selection, phase, source, tmp_path):
    module = SELECTION_MODULES[selection]
    root = tracked(tmp_path, source, module)
    head,result,raw = run_child(root, directory=selection[0], selection=selection)
    args=(['discover','-s',native.PREFIX+'tests','-p','test_commission_deadline.py']
        if selection==native.COMMISSION_SELECTION else ['discover','-s',selection[0],'-p',selection[1],'-v'])
    cwd=root if selection==native.COMMISSION_SELECTION else root/'ops/native_fabric/quota_continuity'
    ordinary = subprocess.run([sys.executable,'-m','unittest',*args], cwd=cwd,
        capture_output=True, timeout=10)
    assert result.returncode == ordinary.returncode != 0
    value = native.decode(raw, head=head, invocation='a'*32, directory=selection[0],
        selection=selection, catalog=fixed.PublicCatalog(root,native=True), returncode=result.returncode)
    assert len(value['records']) == 1 and value['records'][0]['module'] == module
    assert value['records'][0]['phase'] == phase and b'PRIVATE' not in raw


@pytest.mark.parametrize('selection', tuple(SELECTION_MODULES))
def test_every_route_binds_immutable_selection_and_rejects_relabel_replay(selection, tmp_path, monkeypatch):
    from dataclasses import FrozenInstanceError
    module = SELECTION_MODULES[selection]
    root = tracked(tmp_path, LEAF, module)
    directory = tmp_path/'fixed';directory.mkdir(mode=0o700)
    monkeypatch.setenv('MMX_CI_FIXED_DIAGNOSTICS_DIR', str(directory))
    invocation = native.NativeInvocation(selection[0], selection)
    result,facts = native.run_native(selection[0], selection=selection, timeout_seconds=10,
        root=root, cwd=root if selection==native.COMMISSION_SELECTION else root/'ops/native_fabric/quota_continuity', invocation=invocation)
    assert result.returncode == 1 and facts.selection == invocation.selection == selection
    with pytest.raises(FrozenInstanceError):
        facts.selection = G_O
    other = ('tests','test_[a-f]*.py') if selection==G_O else G_O
    error = AssertionError('PRIVATE wrapper')
    assert not native.bind_facts(error, facts, invocation, selection_node(other))
    assert native.bind_facts(error, facts, invocation, selection_node(selection))
    records,truncated = native.records_for_error(error, selection_node(other), root, facts.head)
    assert records == [] and truncated is True
    catalog = fixed.PublicCatalog(root, native=True)
    for head,token in ((facts.head, 'f'*32), ('f'*40, facts.invocation)):
        with pytest.raises(ValueError,match='native_diagnostic_unavailable'):
            native.decode(facts.raw, head=head, invocation=token, directory=selection[0],
                selection=selection, catalog=catalog, returncode=1)
    with pytest.raises(ValueError,match='native_diagnostic_unavailable'):
        native.decode(facts.raw, head=facts.head, invocation=facts.invocation, directory=other[0],
            selection=other, catalog=catalog, returncode=1)
    diagnostics = fixed.FixedDiagnostics(fixed.PublicCatalog(root), directory)
    diagnostics.failure_record(selection_node(selection), 'call', error=error)
    destination = directory/'ci-fixed-diagnostics.json'
    before = destination.read_bytes()
    native_rows = [row for row in diagnostics.failures if row['module'] == module]
    assert len(native_rows) == 2
    native_rows[0]['native_wrapper'] = selection_node(other).split('::')[1]
    assert not diagnostics._closed()
    diagnostics.flush()
    assert destination.read_bytes() == before
    records,truncated = native.records_for_error(error, selection_node(selection), root, facts.head)
    assert records == [] and truncated is True


@pytest.mark.parametrize('selection', tuple(SELECTION_MODULES))
def test_selected_empty_suite_cannot_pass_wrapper(selection, tmp_path, monkeypatch):
    root = tracked(tmp_path, 'import unittest\n', SELECTION_MODULES[selection])
    monkeypatch.delenv('MMX_CI_FIXED_DIAGNOSTICS_DIR', raising=False)
    head,result,raw = run_child(root, directory=selection[0], selection=selection)
    args=(['discover','-s',native.PREFIX+'tests','-p','test_commission_deadline.py']
        if selection==native.COMMISSION_SELECTION else ['discover','-s',selection[0],'-p',selection[1],'-v'])
    cwd=root if selection==native.COMMISSION_SELECTION else root/'ops/native_fabric/quota_continuity'
    ordinary = subprocess.run([sys.executable,'-m','unittest',*args], cwd=cwd,
        capture_output=True, timeout=10)
    assert result.returncode == ordinary.returncode
    with pytest.raises(AssertionError):
        native.qualify_wrapper(selection_node(selection), timeout_seconds=10,
            root=root, cwd=root if selection==native.COMMISSION_SELECTION else root/'ops/native_fabric/quota_continuity')


@pytest.mark.parametrize('selection', [
    ('tests','test_*.py'), ('tests','../test_*.py'), ('tests','test_[A-Z]*.py'),
    ('rollout','test_[a-f]*.py'), ('private','test_*.py'), ['tests','test_[a-f]*.py'], None,
])
def test_unknown_selection_refuses_before_any_child_or_fallback(selection, tmp_path):
    with mock.patch.object(native.subprocess,'run') as child:
        with pytest.raises(ValueError,match='native_selection_unavailable'):
            native.run_native('tests', selection=selection, timeout_seconds=1, root=tmp_path, cwd=tmp_path)
        child.assert_not_called()


def test_public_out_of_group_node_and_import_holder_are_not_projected(tmp_path):
    import unittest
    root = tracked(tmp_path)
    path = root/'ops/native_fabric/quota_continuity/tests/test_alpha.py'
    spec = importlib.util.spec_from_file_location('test_alpha', path)
    module = importlib.util.module_from_spec(spec)
    with mock.patch.dict(sys.modules, {'test_alpha':module}):
        spec.loader.exec_module(module)
        catalog = fixed.PublicCatalog(root, native=True)
        assert native._node(module.Sentinel('test_ok'), catalog, 'tests', G_O) is None
        failed = unittest.loader._FailedTest('test_alpha', ImportError('PRIVATE'))
        assert native._holder(failed, catalog, 'tests', G_O) is None
        holder = unittest.suite._ErrorHolder('setUpClass (test_alpha.Sentinel)')
        assert native._holder(holder, catalog, 'tests', G_O) is None


def test_exact_commission_profile_publishes_live_leaf_without_broadening_discovery(tmp_path,monkeypatch):
    root=tracked(tmp_path, 'import unittest\nclass PrivateOther(unittest.TestCase):\n def test_not_selected(self):raise RuntimeError("PRIVATE other file")\n')
    leaf=root/native.PREFIX/'tests/test_commission_deadline.py';leaf.write_text(LEAF)
    subprocess.run(['git','-C',str(root),'add','.'],check=True,capture_output=True)
    subprocess.run(['git','-C',str(root),'-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-qm','profile'],check=True,capture_output=True)
    spec=importlib.util.spec_from_file_location('commission_wrapper',root/'tests/test_fabric_request_turn_budget.py')
    wrapper=importlib.util.module_from_spec(spec);spec.loader.exec_module(wrapper)
    monkeypatch.setenv('MMX_CI_FIXED_DIAGNOSTICS_DIR',str(tmp_path/'unused'))
    args=[sys.executable,'-m','unittest',*native.COMMISSION_ARGS]
    ordinary=subprocess.run(args,cwd=root,capture_output=True,text=True,timeout=10)
    with pytest.raises(AssertionError) as error:wrapper._run(args,timeout=240)
    assert str(error.value).endswith('FAILED (failures=1, errors=1)\n')
    directory=tmp_path/'fixed';directory.mkdir(mode=0o700)
    diagnostics=fixed.FixedDiagnostics(fixed.PublicCatalog(root),directory)
    diagnostics.failure_record('tests/test_fabric_request_turn_budget.py::test_existing_commission_deadlines_remain_binding','call',error=error.value)
    raw=(directory/'ci-fixed-diagnostics.json').read_bytes();value=json.loads(raw)
    rows=[row for row in value['failures'] if row['module'].startswith(native.PREFIX)]
    assert value['head']==fixed.PublicCatalog(root).head and not value['truncated']
    assert len(value['failures'])==3 and b'PRIVATE' not in raw
    assert all(row['native_wrapper']=='test_existing_commission_deadlines_remain_binding' for row in rows)
    assert ordinary.returncode==1 and len(rows)==2
    assert {row['case'] for row in rows}=={'Leaf.test_failure','Leaf.test_error'}
    assert all(row['module']==native.PREFIX+'tests/test_commission_deadline.py' for row in rows)
    assert 'PRIVATE' not in json.dumps(rows)
    assert native.records_for_error(error.value,'tests/test_fabric_request_turn_budget.py::test_existing_commission_deadlines_remain_binding',root,fixed.PublicCatalog(root).head)[0]==[]


def test_commission_profile_original_command_environment_and_limit_are_exact(tmp_path,monkeypatch):
    monkeypatch.delenv('MMX_CI_FIXED_DIAGNOSTICS_DIR',raising=False)
    env={'PRIVATE_ENV':'unchanged','PYTHONDONTWRITEBYTECODE':'1'}
    with mock.patch.object(native.subprocess,'run',return_value=subprocess.CompletedProcess([],0,'ordinary','OK')) as run:
        result,facts=native.run_native('tests',timeout_seconds=240,root=tmp_path,cwd=tmp_path,
            selection=native.COMMISSION_SELECTION,env=env)
    assert result.returncode==0 and facts is None
    assert run.call_args.args[0]==[sys.executable,'-m','unittest',*native.COMMISSION_ARGS]
    assert run.call_args.kwargs==dict(cwd=tmp_path,env=env,capture_output=True,text=True,timeout=240)
    assert native.COMMISSION_ARGS==['discover','-s','ops/native_fabric/quota_continuity/tests','-p','test_commission_deadline.py']
    for directory,selection,cwd in [
        ('rollout',native.COMMISSION_SELECTION,tmp_path),
        ('tests',('tests','test_private.py'),tmp_path),
        ('tests',('tests','../private'),tmp_path),
        ('tests',native.COMMISSION_SELECTION,tmp_path/'wrong')]:
        with mock.patch.object(native.subprocess,'run') as child:
            with pytest.raises(ValueError):native.run_native(directory,selection=selection,
                timeout_seconds=240,root=tmp_path,cwd=cwd)
            child.assert_not_called()


def test_timeout_kind_is_exact_stdlib_type_not_attacker_name_or_output():
    error=subprocess.TimeoutExpired(['PRIVATE command'],300,output='PRIVATE stdout',stderr='PRIVATE stderr')
    assert fixed.KINDS.get(type(error))=='TimeoutExpired'
    impostor=type('TimeoutExpired',(Exception,),{})('PRIVATE message')
    subclass=type('PrivateTimeout',(subprocess.TimeoutExpired,),{})('PRIVATE',300)
    assert type(impostor) not in fixed.KINDS and type(subclass) not in fixed.KINDS


def test_partitioned_owners_preserve_rollout_and_dedicated_commission_limits(tmp_path):
    root=tracked(tmp_path)
    for node,selection in native.WRAPPER_SELECTIONS.items():
        path,name=node.split('::')
        spec=importlib.util.spec_from_file_location('closed_wrapper_'+name,root/path)
        wrapper=importlib.util.module_from_spec(spec);spec.loader.exec_module(wrapper)
        if selection==native.COMMISSION_SELECTION:
            with mock.patch.object(wrapper,'_run',return_value='Ran 1 test\nOK\n') as run:
                getattr(wrapper,name)()
            assert run.call_args.args[0]==[sys.executable,'-m','unittest',
                'discover','-s','ops/native_fabric/quota_continuity/tests','-p','test_commission_deadline.py']
            assert run.call_args.kwargs['timeout']==240
            assert set(run.call_args.kwargs['extra_env'])=={'NATIVE_ROLLOUT_TEST_ROOT'}
        else:
            target=native if selection[0]=='rollout' else wrapper
            with mock.patch.object(target,'qualify_wrapper') as qualify:
                getattr(wrapper,name)()
            assert qualify.call_args==mock.call(node,
                timeout_seconds=240 if selection[0]=='rollout' else 300,
                root=root,cwd=root/'ops/native_fabric/quota_continuity')


@pytest.mark.parametrize('mutation', [
    'commission-to-af','af-to-commission','borrow-origin','swap-origins',
    'replace-copy','borrow-row-object','repeat-row','swap-row-objects','drop-row',
])
def test_overlapping_commission_and_partition_keep_admitted_row_provenance(tmp_path,monkeypatch,mutation):
    root=tracked(tmp_path,LEAF,native.PREFIX+'tests/test_commission_deadline.py')
    directory=tmp_path/'fixed';directory.mkdir(mode=0o700)
    monkeypatch.setenv('MMX_CI_FIXED_DIAGNOSTICS_DIR',str(directory))
    commission=selection_node(native.COMMISSION_SELECTION)
    af=selection_node(('tests','test_[a-f]*.py'))
    errors=[]
    for node,cwd in ((commission,root),(af,root/'ops/native_fabric/quota_continuity')):
        with pytest.raises(AssertionError) as caught:
            native.qualify_wrapper(node,timeout_seconds=10,root=root,cwd=cwd)
        errors.append(caught.value)
    diagnostics=fixed.FixedDiagnostics(fixed.PublicCatalog(root),directory)
    for node,error in zip((commission,af),errors):
        diagnostics.failure_record(node,'call',error=error)
    assert diagnostics._closed()
    rows=[(i,row) for i,row in enumerate(diagnostics.failures)
        if row['module']==native.PREFIX+'tests/test_commission_deadline.py']
    assert len(rows)==4
    ci,c=next((i,row) for i,row in rows
        if row['native_wrapper']==commission.split('::')[1] and row['case']=='Leaf.test_failure')
    ai,a=next((i,row) for i,row in rows
        if row['native_wrapper']==af.split('::')[1] and row['case']=='Leaf.test_failure')
    assert c['native_invocation']!=a['native_invocation']
    destination=directory/'ci-fixed-diagnostics.json';before=destination.read_bytes()
    if mutation=='commission-to-af':c['native_wrapper']=a['native_wrapper']
    elif mutation=='af-to-commission':a['native_wrapper']=c['native_wrapper']
    elif mutation=='borrow-origin':
        for key in ('native_invocation','native_wrapper'):c[key]=a[key]
    elif mutation=='swap-origins':
        for key in ('native_invocation','native_wrapper'):c[key],a[key]=a[key],c[key]
    elif mutation=='replace-copy':diagnostics.failures[ci]=c.copy()
    elif mutation=='borrow-row-object':diagnostics.failures[ci]=a
    elif mutation=='repeat-row':diagnostics.failures.append(c)
    elif mutation=='swap-row-objects':diagnostics.failures[ci],diagnostics.failures[ai]=a,c
    elif mutation=='drop-row':del diagnostics.failures[ci]
    assert not diagnostics._closed()
    diagnostics.flush()
    assert destination.read_bytes()==before
