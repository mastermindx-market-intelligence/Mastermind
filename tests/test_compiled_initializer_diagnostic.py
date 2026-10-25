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


@pytest.mark.parametrize('error,expected',[('KeyboardInterrupt("PRIVATE_INTERRUPT_CANARY")',-2),('SystemExit(19)',19)])
def test_interrupts_and_system_exit_are_not_converted_to_refusal(error,expected):
    child=run('try:\n raise '+error)
    assert child.returncode==expected
    assert d.decode_failure(child.stderr) is None
    assert b'CANARY' not in child.stderr


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
    variant=list(argv);variant[5]=diagnostic
    record_property('diagnostic_quoted_equivalent_bytes_with_nul',len(shlex.join(variant).encode())+1)


@pytest.mark.parametrize('change',[
    lambda v:v.update(private='CANARY'),lambda v:v.update(stage='CANARY'),
    lambda v:v.update(kind='CANARY'),lambda v:v.update(errno=True),
    lambda v:v.update(errno=4097),lambda v:v.update(sites=[{'function':'CANARY','line':1}]),
    lambda v:v.update(sites=[{'function':'pin','line':True}]),
    lambda v:v.update(sites=[{'function':'pin','line':1,'path':'CANARY'}]),
    lambda v:v.update(sites=[{'function':'pin','line':1}]*7),
    lambda v:v.update(node_role='/PRIVATE_CANARY'),lambda v:v.update(acl_key='PRIVATE_CANARY'),
    lambda v:v.update(schema='mastermind.inert_compiled_initializer_failure/v1'),
])
def test_private_or_unbounded_metadata_is_wholly_withheld(change):
    value=dict(schema=d.SCHEMA,stage='BOOTSTRAP',kind='REFUSAL',sites=[],errno=None,node_role='UNKNOWN',acl_key='UNKNOWN')
    change(value)
    assert d.decode_failure(json.dumps(value).encode()) is None


def test_duplicate_nul_and_overbound_frames_are_withheld():
    assert d.decode_failure(b'{"schema":1,"schema":2}') is None
    assert d.decode_failure(b'\0') is None
    assert d.decode_failure(b'x'*4097) is None


def test_reporter_failure_cannot_replace_test_outcome_and_interrupt_propagates():
    raw=json.dumps(dict(schema=d.SCHEMA,stage='BOOTSTRAP',kind='REFUSAL',sites=[],errno=None,node_role='UNKNOWN',acl_key='UNKNOWN')).encode()
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


@pytest.mark.parametrize('role,node',[
    ('HOME_ANCESTOR','/PRIVATE_CANARY'),('HOME','/PRIVATE_CANARY/account'),
    ('LANE_ROOT','/PRIVATE_CANARY/account/lanes'),('EXT','/PRIVATE_CANARY/account/lanes/ext'),
    ('HOST_ENV','/PRIVATE_CANARY/account/lanes/ext/HOST_ENV.sh'),
    ('NESTED_HELPER','/PRIVATE_CANARY/account/lanes/ext/.host_glm_token.sh'),
    ('CAPTURE_ROOT','/PRIVATE_CANARY/account/lanes/ext/lanes'),
])
@pytest.mark.parametrize('key,label',[('system.posix_acl_access','ACCESS'),('system.posix_acl_default','DEFAULT')])
def test_owned_guard_frames_report_only_fixture_role_and_acl_key(role,node,key,label):
    hook='/PRIVATE_CANARY/account/lanes/ext/HOST_ENV.sh'
    helper='/PRIVATE_CANARY/account/lanes/ext/.host_glm_token.sh'
    capture='/PRIVATE_CANARY/account/lanes/ext/lanes'
    selected=helper if role=='NESTED_HELPER' else capture if role=='CAPTURE_ROOT' else hook
    parts=selected.split('/')[1:];index=len(node.split('/'))-2
    code=('def run_bootstrap():\n'
        ' commitment='+repr(dict(account=dict(home='/PRIVATE_CANARY/account'),lane_root='/PRIVATE_CANARY/account/lanes',host_env=dict(path=hook),nested_helper=dict(path=helper)))+'\n'
        ' request='+repr(dict(capture_root=capture))+'\n'
        ' def pin(name):\n  fd=7\n  parts='+repr(parts)+'\n  index='+str(index)+'\n'
        '  def no_acl(fd):\n   key='+repr(key)+'\n   raise ValueError("PRIVATE_ACL_CANARY")\n'
        '  no_acl(fd)\n'
        ' pin('+repr(selected)+')\n')
    body='namespace={"__file__":"<qualified-paid_initializer.py>"}\nexec('+repr(code)+',namespace)\ntry:\n namespace["run_bootstrap"]()'
    child=run(body);value=d.decode_failure(child.stderr)
    assert child.returncode==78 and value['node_role']==role and value['acl_key']==label
    assert b'CANARY' not in child.stderr


def test_unjoined_frames_never_acquire_private_fixture_role():
    # Coincident names without the actual qualified module identity stay UNKNOWN.
    child=run('def run_bootstrap():\n def pin():\n  def no_acl():raise ValueError("PRIVATE_CANARY")\n  no_acl()\n pin()\ntry:\n run_bootstrap()')
    value=d.decode_failure(child.stderr)
    assert child.returncode==78 and value['node_role']==value['acl_key']=='UNKNOWN'
