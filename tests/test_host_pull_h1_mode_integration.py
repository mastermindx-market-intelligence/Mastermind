"""Only disposable publisher/launchctl fixtures; no real service or host call."""
import hashlib
import json
import os
from pathlib import Path
import plistlib
import shlex
import shutil
import signal
import subprocess
import time

import pytest
from tests import test_host_pull_publisher_lifecycle as life
from tests.test_host_pull_publisher_lifecycle import workspace
from tests import test_host_pull_stdin_argv_limit as transport


def fixture_context(workspace):
    ctx=life.prepare(workspace)
    # Keep production SAFE-path checks intact on a source checkout whose
    # external volume name contains a space. Exact test-owned source copies.
    code=workspace/'source-code';code.mkdir()
    for original in (life.DAEMON,life.TEMPLATE,life.PUBLISHER):
        target=code/original.name;target.write_bytes(original.read_bytes());target.chmod(0o755)
    ctx['_daemon']=code/life.DAEMON.name;ctx['_publisher']=code/life.PUBLISHER.name
    # Simulated launchctl consumes the actual rendered plist independently
    # of the production expected_argv function.
    launcher=Path(ctx['env']['PATH'].split(':')[0])/'launchctl'
    text=launcher.read_text()
    index=text.index("    printf 'running",text.index('  bootstrap)'))
    script=r"""    python3 - "$3" "$STUB_STATE/argv" <<'MODEPLIST'
import plistlib,sys
try: value=plistlib.loads(open(sys.argv[1],'rb').read())['ProgramArguments']
except Exception: pass  # the original opaque rollback preimage fixture
else: open(sys.argv[2],'w').write(chr(10).join(value)+chr(10))
MODEPLIST
"""
    launcher.write_text(text[:index]+script+text[index:])
    return ctx


def run(ctx,**extra):
    return life.run(ctx,daemon=ctx['_daemon'],publisher=ctx['_publisher'],**extra)


def prepared(workspace, *, context='valid'):
    ctx=fixture_context(workspace)
    source=workspace/'qualified-source';(source/'ext').mkdir(parents=True)
    for relative in ('pool','ext/fabric_task.py','ext/remote_sub.sh','ext/host_pull.sh'):
        (source/relative).write_bytes((ctx['release']/relative).read_bytes())
    # Exact mode/lifecycle test seam for the selected Root-definition reader.
    # This module DOES NOT prove any installed Root context or grant readiness.
    data="""from contextlib import contextmanager
@contextmanager
def open_installed_context():
    class Context:
        binding={'schema_version':'mastermind.paid_host_readiness_context/v1','host':'ubuntu0','model':'glm-5.3-flash'}
        def check(self):pass
    yield Context()
"""
    if context=='refused':data=data.replace('    yield Context()','    raise ValueError("fixture refused")\n    yield Context()')
    if context=='foreign':data=data.replace("'ubuntu0'","'ubuntu1'")
    (source/'ext/paid_host_readiness.py').write_text(data)
    files={str(p.relative_to(source)):hashlib.sha256(p.read_bytes()).hexdigest() for p in source.rglob('*') if p.is_file()}
    release=life.GENERATION.publish(source,ctx['store'].parent/'ext',files)
    life.GENERATION.select(ctx['store'],release.name,ctx['release'].name)
    ctx.update(release=release,pin=release/'ext/host_pull.sh')
    return ctx


def test_explicit_qualified_mode_renders_and_checks_exact_service_argv(workspace):
    ctx=prepared(workspace)
    result=run(ctx,collector_mode='qualified_readiness')
    assert result.returncode==0,result.stderr
    args=plistlib.loads(ctx['plist'].read_bytes())['ProgramArguments']
    assert args==['/usr/bin/lockf','-t','0',str(ctx['lock']),'/bin/bash',str(ctx['pin']),'--qualified-readiness']
    assert (ctx['stub']/'argv').read_text().splitlines()==args
    again=run(ctx,collector_mode='qualified_readiness')
    assert again.returncode==0 and again.stdout==''
    assert life.launch_log(ctx).count('bootstrap ')==1
    life.assert_not_executed(ctx)


def test_collect_qualified_mode_keeps_lockf_and_one_fixed_option(workspace):
    ctx=prepared(workspace)
    result=run(ctx,command='collect',collector_mode='qualified_readiness')
    assert result.returncode==0,result.stderr
    assert (ctx['stub']/'lockf.args').read_text().splitlines()==['/bin/bash',str(ctx['pin']),'--qualified-readiness']
    life.assert_not_executed(ctx)


@pytest.mark.parametrize('context',['refused','foreign'])
def test_qualified_mode_context_refusal_precedes_launchctl(workspace,context):
    ctx=prepared(workspace,context=context)
    result=run(ctx,collector_mode='qualified_readiness')
    assert result.returncode==78
    assert life.launch_log(ctx)=='' and not ctx['plist'].exists()
    life.assert_not_executed(ctx)


@pytest.mark.parametrize('mode',['ubuntu1','legacy --host ubuntu1','--qualified-readiness',''])
def test_mode_is_closed_not_arbitrary_arguments(workspace,mode):
    ctx=fixture_context(workspace)
    result=run(ctx,collector_mode=mode)
    assert result.returncode==78
    assert life.launch_log(ctx)==''
    life.assert_not_executed(ctx)


@pytest.mark.parametrize('outcome',['NO_EFFECT','RECOVERED','EFFECT_UNKNOWN'])
def test_only_proven_clean_outcomes_release_original_install_marker(workspace,outcome):
    ctx=fixture_context(workspace);life.arm_running(ctx,workspace)
    options={}
    if outcome=='NO_EFFECT':(ctx['stub']/'bootout-rc').write_text('1\n')
    elif outcome=='RECOVERED':options['fault']='install-before-replace'
    else:options['fault']='post-bootout-print'
    first=run(ctx,**options)
    assert first.returncode==78
    assert life.receipt_body(ctx)['outcome']==outcome
    marker=ctx['store']/'.install-transaction.marker'
    if outcome=='EFFECT_UNKNOWN':
        assert marker.exists()
        before=life.launch_log(ctx)
        again=run(ctx)
        assert again.returncode==78 and 'install transaction incomplete' in again.stderr
        assert life.launch_log(ctx)==before
    else:
        assert not marker.exists()
        (ctx['stub']/'bootout-rc').unlink(missing_ok=True)
        # New normal operation, fresh immutable backup/receipt destination.
        # The original retained preimage and outcome are never overwritten.
        again=run(ctx,backup_dir=workspace/'next-operation-backup')
        assert 'install transaction incomplete' not in again.stderr
        assert again.returncode==0,again.stderr
    life.assert_not_executed(ctx)


def test_cancelled_probe_cannot_resume_after_foreground_child_hup(tmp_path):
    wrapper=transport._fixed_remote_wrapper(tmp_path)
    env=transport._inert_python_env(tmp_path)
    marker=tmp_path/'continuation-must-not-run'
    child=subprocess.Popen(['/bin/sh','-c','export TMPDIR="$HOME"; '+wrapper],env=env,
        stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,start_new_session=True)
    try:
        child.stdin.write("trap ':' HUP INT TERM\necho READY\n/bin/sleep 20\necho CONTINUED > "+shlex.quote(str(marker))+"\n")
        child.stdin.close()
        assert child.stdout.readline()=='READY\n'
        os.killpg(child.pid,signal.SIGHUP)
        child.wait(timeout=5)
        assert child.returncode==129
        assert not marker.exists()
        assert list(tmp_path.glob('host_pull_probe.*'))==[]
    finally:
        if child.poll() is None:
            os.killpg(child.pid,signal.SIGKILL);child.wait(timeout=5)



def test_legacy_mode_keeps_old_argv_without_qualified_context(workspace):
    ctx=prepared(workspace,context='refused')
    result=run(ctx,collector_mode='legacy')
    assert result.returncode==0,result.stderr
    assert plistlib.loads(ctx['plist'].read_bytes())['ProgramArguments']==['/usr/bin/lockf','-t','0',str(ctx['lock']),'/bin/bash',str(ctx['pin'])]
    life.assert_not_executed(ctx)


def test_selected_qualified_mode_never_accepts_extra_service_arguments(workspace):
    ctx=prepared(workspace)
    result=run(ctx,collector_mode='qualified_readiness')
    assert result.returncode==0,result.stderr
    with (ctx['stub']/'argv').open('a') as out:out.write('--host\nubuntu1\n')
    before=life.launch_log(ctx)
    result=run(ctx,collector_mode='qualified_readiness')
    assert result.returncode==78 and 'disagree' in result.stderr
    assert life.launch_log(ctx)[len(before):].count('bootout ')==0
    assert life.launch_log(ctx)[len(before):].count('bootstrap ')==0
    life.assert_not_executed(ctx)


def _durability_fixture(ctx, failure='none'):
    """Intercept only fsync/unlink in actual disposable helper children."""
    import sys
    script = '''#!EXECUTABLE
import os,stat,sys
if len(sys.argv)>2 and sys.argv[1]=='-' and sys.argv[2] in ('write-receipt','install-transaction-complete'):
    source=sys.stdin.read();sys.argv=sys.argv[1:]
    command=sys.argv[1];expected=sys.argv[2]
    original_sync=os.fsync;original_unlink=os.unlink
    log=os.environ['DURABILITY_LOG'];failure=os.environ['DURABILITY_FAIL']
    def emit(value):
        with open(log,'a') as out:out.write(value+'\\n')
    def sync(fd):
        info=os.fstat(fd);kind='dir' if stat.S_ISDIR(info.st_mode) else 'file'
        if kind=='dir':
            actual=os.stat(expected,follow_symlinks=False)
            if (info.st_dev,info.st_ino)!=(actual.st_dev,actual.st_ino):
                raise RuntimeError('wrong fixture directory synced')
        emit(command+':'+kind)
        if failure==command+':'+kind:raise OSError('injected fixture durability failure')
        return original_sync(fd)
    def unlink(path,*args,**kwargs):
        if str(path).endswith('.install-transaction.marker'):emit('marker-unlink')
        return original_unlink(path,*args,**kwargs)
    os.fsync=sync;os.unlink=unlink
    exec(compile(source,'<actual-publisher-helper>','exec'),{'__name__':'__main__'})
else:os.execv(sys.executable,[sys.executable]+sys.argv[1:])
'''.replace('EXECUTABLE',sys.executable)
    launcher=Path(ctx['env']['PATH'].split(':')[0])/'python3'
    launcher.write_text(script);launcher.chmod(0o755)
    log=ctx['stub']/'durability.log'
    ctx['env'].update(DURABILITY_LOG=str(log),DURABILITY_FAIL=failure)
    return log


def test_clean_outcome_receipt_directory_commits_before_marker_removal(workspace):
    ctx=fixture_context(workspace);life.arm_running(ctx,workspace)
    (ctx['stub']/'bootout-rc').write_text('1\n')
    log=_durability_fixture(ctx)
    result=run(ctx)
    assert result.returncode==78 and 'bootout had no effect' in result.stderr
    assert log.read_text().splitlines()==[
        'write-receipt:file','write-receipt:dir','marker-unlink','install-transaction-complete:dir']
    assert life.receipt_body(ctx)['outcome']=='NO_EFFECT'
    assert not (ctx['store']/'.install-transaction.marker').exists()


@pytest.mark.parametrize('failure',['write-receipt:file','write-receipt:dir'])
def test_failed_receipt_commit_retains_marker_and_blocks_next_mutation(workspace,failure):
    ctx=fixture_context(workspace);life.arm_running(ctx,workspace)
    (ctx['stub']/'bootout-rc').write_text('1\n')
    log=_durability_fixture(ctx,failure)
    result=run(ctx)
    assert result.returncode==78 and 'receipt failed' in result.stderr
    assert (ctx['store']/'.install-transaction.marker').exists()
    assert 'marker-unlink' not in log.read_text()
    before=life.launch_log(ctx)
    again=run(ctx)
    assert again.returncode==78 and 'install transaction incomplete' in again.stderr
    assert life.launch_log(ctx)==before


def test_marker_unlink_directory_failure_never_claims_durable_clean_completion(workspace):
    ctx=fixture_context(workspace);life.arm_running(ctx,workspace)
    (ctx['stub']/'bootout-rc').write_text('1\n')
    log=_durability_fixture(ctx,'install-transaction-complete:dir')
    result=run(ctx)
    assert result.returncode==78 and 'clean marker closure unconfirmed' in result.stderr
    assert log.read_text().splitlines()==[
        'write-receipt:file','write-receipt:dir','marker-unlink','install-transaction-complete:dir']
    assert life.receipt_body(ctx)['outcome']=='NO_EFFECT'
    assert not (ctx['store']/'.install-transaction.marker').exists()
    assert life.launch_log(ctx).count('bootout ')==1
    assert life.launch_log(ctx).count('bootstrap ')==0
