"""Prospective closed exit facts, synthetic tracked public source and owned child."""
import json
import subprocess
import sys
import time
from pathlib import Path
from unittest import mock
import pytest
from scripts.ci_fixed_diagnostics import PublicCatalog, FixedDiagnostics, EXIT_EVENTS
from tests.test_ci_fixed_diagnostics import tracked,private_directory,plugin_child


def test_public_live_frames_exclude_private_names_locals_and_untracked_paths(tmp_path):
    source='def capture(d):\n secret="PRIVATE_LOCAL_CANARY"\n d.lifecycle_record("SESSION_FINISH_ENTERED",0)\ndef test_public():pass\n'
    root=tracked(tmp_path,source);d=FixedDiagnostics(PublicCatalog(root),private_directory(tmp_path))
    namespace={};exec(compile(source,str(root/'tests/test_public.py'),'exec'),namespace)
    namespace['capture'](d)
    value=json.loads((d.directory/'ci-fixed-diagnostics.json').read_bytes())
    assert value['schema']=='ci.fixed-diagnostics.v2'
    assert value['lifecycle'][0]==dict(event=EXIT_EVENTS[0],exitstatus=0,sources=[dict(module='tests/test_public.py',line=3)])
    assert 'PRIVATE' not in json.dumps(value) and str(tmp_path) not in json.dumps(value)
    foreign='def capture(d):\n d.lifecycle_record("SESSION_FINISH_RETURNED",0)\n'
    exec(compile(foreign,str(root/'tests/test_untracked_PRIVATE.py'),'exec'),namespace)
    namespace['capture'](d)
    assert d.lifecycle[-1]['sources']==[]


def test_changed_source_and_unavailable_frame_api_refuse_locations_without_losing_phase(tmp_path):
    source='def capture(d):\n d.lifecycle_record("SESSION_FINISH_ENTERED",1)\ndef test_public():pass\n'
    root=tracked(tmp_path,source);d=FixedDiagnostics(PublicCatalog(root),private_directory(tmp_path))
    namespace={};exec(compile(source,str(root/'tests/test_public.py'),'exec'),namespace)
    (root/'tests/test_public.py').write_text(source+'# changed\n')
    namespace['capture'](d);assert d.lifecycle[0]['sources']==[]
    with mock.patch('sys._current_frames',side_effect=RuntimeError('PRIVATE_ERROR')):
        d.lifecycle_record(EXIT_EVENTS[1],1)
    assert d.lifecycle[-1]==dict(event=EXIT_EVENTS[1],exitstatus=1,sources=[])
    assert 'PRIVATE' not in (d.directory/'ci-fixed-diagnostics.json').read_text()


def test_phase_order_and_exitstatus_types_are_closed_and_do_not_mint_success(tmp_path):
    d=FixedDiagnostics(PublicCatalog(tracked(tmp_path)),private_directory(tmp_path))
    for event,status in [('PRIVATE',0),(EXIT_EVENTS[1],0),(EXIT_EVENTS[0],True),(EXIT_EVENTS[0],6),(EXIT_EVENTS[0],'0')]:
        d.lifecycle_record(event,status)
    assert d.lifecycle==[]
    for event in EXIT_EVENTS:d.lifecycle_record(event,1)
    before=(d.directory/'ci-fixed-diagnostics.json').read_bytes()
    d.lifecycle_record(EXIT_EVENTS[0],0)
    assert (d.directory/'ci-fixed-diagnostics.json').read_bytes()==before
    assert [r['exitstatus'] for r in d.lifecycle]==[1]*4


@pytest.mark.parametrize('source,expected', [('def test_public():pass\n',0),('def test_public():assert False\n',1)])
def test_actual_plugin_records_returned_hooks_preserving_actual_process_exit(tmp_path,source,expected):
    root,out,env,argv=plugin_child(tmp_path,source)
    child=subprocess.run(argv,cwd=root,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=20)
    assert child.returncode==expected
    value=json.loads((out/'ci-fixed-diagnostics.json').read_bytes())
    assert [r['event'] for r in value['lifecycle']]==list(EXIT_EVENTS)
    assert all(r['exitstatus']==expected for r in value['lifecycle'])
    assert value['schema']=='ci.fixed-diagnostics.v2'


def test_genuine_non_daemon_exit_stall_keeps_hook_returns_and_public_source_only(tmp_path):
    source='''import threading
_STOP=threading.Event()
def retained_worker():
 private="PRIVATE_THREAD_LOCAL"
 _STOP.wait()
def test_public():
 threading.Thread(target=retained_worker,name="PRIVATE_THREAD_NAME",daemon=False).start()
'''
    root,out,env,argv=plugin_child(tmp_path,source)
    child=subprocess.Popen(argv,cwd=root,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        deadline=time.monotonic()+10;path=out/'ci-fixed-diagnostics.json';value={}
        while time.monotonic()<deadline and child.poll() is None:
            if path.exists():
                value=json.loads(path.read_bytes())
                if len(value.get('lifecycle',[]))==4:break
            time.sleep(.02)
        assert child.poll() is None
        assert [r['event'] for r in value['lifecycle']]==list(EXIT_EVENTS)
        assert all(r['exitstatus']==0 for r in value['lifecycle'])
        assert dict(module='tests/test_public.py',line=5) in value['lifecycle'][-1]['sources']
        assert value['progress'][-1]['event']=='summary'
        assert 'PRIVATE' not in json.dumps(value) and str(tmp_path) not in json.dumps(value)
        # Returned pytest hooks/exitstatus0 are NOT a completed process verdict.
        with pytest.raises(subprocess.TimeoutExpired):child.wait(timeout=.1)
    finally:
        if child.poll() is None:child.terminate()
        try:child.wait(timeout=5)
        except subprocess.TimeoutExpired:child.kill();child.wait(timeout=5)


def test_unqualified_lifecycle_mutation_never_overwrites_last_closed_snapshot(tmp_path):
    d=FixedDiagnostics(PublicCatalog(tracked(tmp_path)),private_directory(tmp_path))
    d.lifecycle_record(EXIT_EVENTS[0],0)
    path=d.directory/'ci-fixed-diagnostics.json';before=path.read_bytes()
    for mutation in [dict(event=EXIT_EVENTS[1],exitstatus=True,sources=[]),
                     dict(event=EXIT_EVENTS[1],exitstatus=0,sources=[dict(module='tests/test_PRIVATE.py',line=1)]),
                     dict(event=EXIT_EVENTS[1],exitstatus=0,sources=[],PRIVATE='secret')]:
        d.lifecycle.append(mutation);d.flush();assert path.read_bytes()==before;d.lifecycle.pop()


def test_source_frames_are_count_depth_bounded_and_do_not_read_foreign_modules(tmp_path,monkeypatch):
    from types import SimpleNamespace
    root=tracked(tmp_path);d=FixedDiagnostics(PublicCatalog(root),private_directory(tmp_path))
    foreign=SimpleNamespace(f_code=SimpleNamespace(co_filename='/PRIVATE/nonrepo.py'),f_lineno=1)
    foreign.f_back=foreign
    with mock.patch('sys._current_frames',return_value={999:foreign}), \
         mock.patch.object(d.catalog,'source',side_effect=AssertionError('foreign body read')):
        d.lifecycle_record(EXIT_EVENTS[0],0)
    assert d.lifecycle[0]['sources']==[]
    assert 'PRIVATE' not in (d.directory/'ci-fixed-diagnostics.json').read_text()


def test_actual_late_hook_failure_is_not_masked_or_converted_to_pass(tmp_path):
    root,out,env,argv=plugin_child(tmp_path,'def test_public():pass\n')
    (root/'blocking_plugin.py').write_text('def pytest_sessionfinish(session,exitstatus):\n raise RuntimeError("PRIVATE_LATE_HOOK_ERROR")\n')
    argv[argv.index('tests/test_public.py'):argv.index('tests/test_public.py')]=['-p','blocking_plugin']
    child=subprocess.run(argv,cwd=root,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=20)
    assert child.returncode!=0
    value=json.loads((out/'ci-fixed-diagnostics.json').read_bytes())
    assert value['lifecycle'][0]['event']=='SESSION_FINISH_ENTERED'
    assert 'PRIVATE' not in json.dumps(value)
    # exitstatus is an observed pytest hook input, never a process success claim.
    assert value['lifecycle'][0]['exitstatus']==0
