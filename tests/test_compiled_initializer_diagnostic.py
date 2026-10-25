import json
import subprocess
import sys
from types import SimpleNamespace

import pytest
from tests import compiled_initializer_diagnostic as d


def run(body):
    source='import sys\n'+body+'\nexcept Exception:sys.exit(78)\n'
    return subprocess.run([sys.executable,'-I','-S','-B','-c',d.instrument_entry(source,preamble='import sys\n')],
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=5)


def test_final_exception_not_prior_handled_optional_probe_is_reported():
    child=run('def pin():\n raise PermissionError(13,"PRIVATE_CANARY /private/path")\n'
        'try:\n try:raise OSError(61,"HANDLED_CANARY")\n except OSError:pass\n pin()')
    assert child.returncode==78 and child.stdout==b''
    value=d.decode_failure(child.stderr)
    assert value['kind']=='PermissionError' and value['errno']==13
    assert any(v['function']=='pin' for v in value['sites'])
    assert b'CANARY' not in child.stderr and b'/private' not in child.stderr


@pytest.mark.parametrize('error,expected',[('KeyboardInterrupt()',-2),('SystemExit(19)',19)])
def test_interrupts_and_system_exit_are_not_converted_to_refusal(error,expected):
    child=run('try:\n raise '+error)
    assert child.returncode==expected
    assert d.decode_failure(child.stderr) is None


def test_success_stdout_and_no_failure_frame_are_preserved():
    child=run('try:\n sys.stdout.write("inert-result")')
    assert child.returncode==0 and child.stdout==b'inert-result' and child.stderr==b''


def test_unhandled_entry_error_keeps_exit_one_without_private_traceback():
    child=run('raise ValueError("PRIVATE_CANARY")\ntry:\n pass')
    assert child.returncode==1 and d.decode_failure(child.stderr)['stage']=='ENTRY'
    assert b'CANARY' not in child.stderr


def test_child_reporter_failure_keeps_the_original_refusal_exit():
    child=run('class Sink:\n def write(self,value):raise ValueError("PRIVATE_CANARY")\n def flush(self):pass\n'
        'sys.stderr=Sink()\ntry:\n raise ValueError("PRIVATE_CANARY")')
    assert child.returncode==78 and not child.stdout and not child.stderr


def test_real_compiler_input_is_measured_before_diagnostic_variant(monkeypatch,record_property):
    import hashlib,shlex
    from pathlib import Path
    from tests import test_paid_host_qualification as fixture
    from tests import test_paid_initializer_nested_join as joined
    from ops.native_fabric.quota_continuity.candidate import paid_initializer as owner
    q=fixture.m;source=Path(owner.__file__).read_bytes()
    monkeypatch.setattr(q,'_initializer_module',lambda expected:(owner,source) if expected==hashlib.sha256(source).hexdigest() else q._refuse())
    req=joined._compiled_fixture(q,monkeypatch)
    req['initializer_commitment']['startup']['profile']=owner.NO_SITE_PROFILE
    req['initializer_commitment_sha256']=q._digest(req['initializer_commitment'])
    alias,command=q.build_paid_probe(req);argv=shlex.split(command);original=tuple(argv)
    diagnostic=d.instrument_entry(argv[5],preamble=owner.NO_SITE_PREAMBLE)
    assert tuple(argv)==original and alias==req['transport_alias']
    assert diagnostic.startswith(owner.NO_SITE_PREAMBLE)
    assert len(command.encode())+1<=q.MAX_REMOTE_COMMAND_BYTES==100000
    assert len(diagnostic.encode())+1<131072
    record_property('original_command_bytes_with_nul',len(command.encode())+1)
    record_property('diagnostic_code_bytes_with_nul',len(diagnostic.encode())+1)


@pytest.mark.parametrize('change',[
    lambda v:v.update(private='CANARY'),lambda v:v.update(stage='CANARY'),
    lambda v:v.update(kind='CANARY'),lambda v:v.update(errno=True),
    lambda v:v.update(errno=4097),lambda v:v.update(sites=[{'function':'CANARY','line':1}]),
    lambda v:v.update(sites=[{'function':'pin','line':True}]),
    lambda v:v.update(sites=[{'function':'pin','line':1,'path':'CANARY'}]),
    lambda v:v.update(sites=[{'function':'pin','line':1}]*7),
])
def test_private_or_unbounded_metadata_is_wholly_withheld(change):
    value=dict(schema=d.SCHEMA,stage='BOOTSTRAP',kind='REFUSAL',sites=[],errno=None)
    change(value)
    assert d.decode_failure(json.dumps(value).encode()) is None


def test_duplicate_nul_and_overbound_frames_are_withheld():
    assert d.decode_failure(b'{"schema":1,"schema":2}') is None
    assert d.decode_failure(b'\0') is None
    assert d.decode_failure(b'x'*4097) is None


def test_reporter_failure_cannot_replace_test_outcome_and_interrupt_propagates():
    raw=json.dumps(dict(schema=d.SCHEMA,stage='BOOTSTRAP',kind='REFUSAL',sites=[],errno=None)).encode()
    class Capture:
        def __enter__(self):return self
        def __exit__(self,*args):return False
    class Reporter:
        failure=ValueError()
        def write_line(self,line):raise self.failure
    reporter=Reporter()
    request=SimpleNamespace(config=SimpleNamespace(pluginmanager=SimpleNamespace(getplugin=lambda name:reporter)),
        getfixturevalue=lambda name:SimpleNamespace(disabled=lambda:Capture()))
    assert d.failure_notice(request,raw) is None
    reporter.failure=KeyboardInterrupt()
    with pytest.raises(KeyboardInterrupt):d.failure_notice(request,raw)


def test_shape_refuses_instead_of_adapting_unknown_compiler():
    with pytest.raises(ValueError):d.instrument_entry('private source',preamble='import sys\n')


def test_real_pytest_failure_does_not_render_completed_process_values(tmp_path):
    from pathlib import Path
    import os
    program=tmp_path/'test_inert_compiled_failure.py'
    program.write_text('from types import SimpleNamespace\n'
        'from subprocess import CompletedProcess\n'
        'from tests.compiled_initializer_diagnostic import require_execution_success\n'
        'def test_actual_refusal():\n'
        ' value=CompletedProcess(["SYNTHETIC_COMMAND_CANARY"],78,b"SYNTHETIC_OUTPUT_CANARY",b"SYNTHETIC_ERROR_CANARY")\n'
        ' require_execution_success(value,None)\n')
    # Helper source is exact current code. The child does no initializer work.
    child=subprocess.run([sys.executable,'-m','pytest','-q','--tb=short','-p','no:cacheprovider',str(program)],
        cwd=Path(__file__).resolve().parents[1],env={**os.environ,'PYTEST_DISABLE_PLUGIN_AUTOLOAD':'1'},
        stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=30)
    assert child.returncode==1
    assert b'compiled diagnostic variant refused' in child.stdout
    assert b'SYNTHETIC_' not in child.stdout and b'1 failed' in child.stdout
